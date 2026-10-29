"""Offline contracts: billing-safe recovery, frozen voices and timestamp parsing."""
import io
import json
import struct
import wave
from pathlib import Path

import pytest
import requests

from backlot import audio_center, bailian_asr, bailian_config, tts_runtime
from lib import bailian_speech as api
from tools.audio.bailian_tts import BailianTTS, split_text
from tools.base_tool import ToolStatus


class Response:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status
        self.ok = status < 400
    def json(self):
        return self.data


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "unit-test-secret")
    monkeypatch.setenv("DASHSCOPE_WORKSPACE_ID", "")
    monkeypatch.setenv("BAILIAN_ASR_STORAGE", "temporary")
    monkeypatch.setattr(audio_center, "AUDIO_CENTER_FILE", tmp_path / "audio_center.json")
    monkeypatch.setattr(audio_center, "PREVIEW_DIRECTORY", tmp_path / "previews")
    monkeypatch.setattr(audio_center.VoiceboxTTS, "get_status", lambda *args: ToolStatus.UNAVAILABLE)
    monkeypatch.setattr(bailian_config, "HEALTH_FILE", tmp_path / "health.json")
    monkeypatch.setattr(bailian_config, "_secrets_path", lambda: tmp_path / ".env.secrets.local")
    # Any unexpected network path fails rather than touching a real account.
    monkeypatch.setattr(requests, "post", lambda *a, **kw: pytest.fail("unexpected HTTP POST"))
    monkeypatch.setattr(requests, "get", lambda *a, **kw: pytest.fail("unexpected HTTP GET"))


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        writer.writeframes(b"\x03\x00" * 2400)
    data = bytearray(buffer.getvalue())
    struct.pack_into("<I", data, 4, 0x7FFFFFBF)
    struct.pack_into("<I", data, 40, 0x7FFFFF9B)
    return bytes(data)


def test_inline_audio_is_redacted_from_provider_errors():
    assert "QUJDRA==" not in api.safe_error("BadAudio data:audio/wav;base64,QUJDRA==")


@pytest.mark.parametrize("http_status,provider_code,kind,definitive", [
    (401,"InvalidApiKey","invalid_key",True),
    (400,"invalid_api_key","invalid_key",True),
    (401,None,"invalid_key",True),
    (400,"Arrearage","insufficient_balance",True),
    (400,"isv.OUT_OF_SERVICE","insufficient_balance",True),
    (403,"AccessDenied.Unpurchased","other",True),
    (403,"Model.AccessDenied","other",True),
    (429,"Throttling","other",True),
    (400,"QuotaExceeded","other",True),
    (500,"InternalError","other",False),
])
def test_provider_rejections_have_precise_safe_failure_facts(http_status, provider_code, kind, definitive):
    payload = {"message":"余额不足配额提示不能覆盖真实错误码 unit-test-secret https://private.example/token"}
    if provider_code is not None:
        payload["code"] = provider_code
    with pytest.raises(api.BailianSpeechError) as caught:
        api.response_json(Response(payload,status=http_status))
    error = caught.value
    assert error.failure_kind == kind
    assert error.provider_code == provider_code
    assert error.http_status == http_status
    assert error.definitive is definitive
    assert error.accepted is False
    assert "unit-test-secret" not in str(error) and "private.example" not in str(error)


def test_config_preserves_other_keys_and_never_exposes_secrets(tmp_path):
    path = tmp_path / ".env.secrets.local"
    path.write_text("OTHER_SETTING=keep\n", encoding="utf-8")
    result = bailian_config.save_bailian_config({"api_key": "new-test-secret", "workspace_id": "example"})
    assert result["configured"]
    assert "new-test-secret" not in json.dumps(result)
    assert "OTHER_SETTING=keep" in path.read_text()
    bailian_config.save_bailian_config({"api_key": "", "workspace_id": ""})
    assert "new-test-secret" in path.read_text()
    assert not bailian_config.clear_bailian_config()["configured"]
    assert "OTHER_SETTING=keep" in path.read_text()


def test_voice_model_rate_are_frozen_and_duplicate_guard_uses_identity():
    result = audio_center.add_custom_cloud_voice({"provider": "bailian", "name": "测试百炼", "voice_id": api.TEST_VOICE})
    public = next(p for p in result["profiles"] if p["provider_id"] == "bailian")
    assert public["speech_rate"] == 1
    assert public["model_id"] == api.TTS_MODEL
    profile = audio_center.get_voice_profile(public["id"])
    snapshot = audio_center.freeze_voice_profile(profile)
    audio_center.set_cloud_voice_playback_rate(public["id"], {"playback_rate": 1.4})
    assert snapshot["speech_rate"] == 1
    assert audio_center.get_voice_profile(public["id"])["voice_signature"] != snapshot["voice_signature"]
    with pytest.raises(audio_center.AudioCenterError, match="已存在"):
        audio_center.add_custom_cloud_voice({"provider": "bailian", "name": "另一个名称", "voice_id": api.TEST_VOICE})
    with pytest.raises(audio_center.AudioCenterError, match="模型"):
        audio_center.add_custom_cloud_voice({"provider": "bailian", "name": "未知模型", "voice_id": "new", "model_id": "unknown"})


@pytest.mark.parametrize("model,voice,usage,billing_unit", [
    (api.TTS_MODEL, api.TEST_VOICE, {"input_tokens": 5, "output_tokens": 10}, "tokens"),
    (api.COSYVOICE_TTS_MODEL, "cosyvoice-v3.5-flash-test-voice", {"characters": 42}, "characters"),
])
def test_tts_download_failure_recovers_without_paid_resubmit_and_normalises_header(
    tmp_path, monkeypatch, model, voice, usage, billing_unit,
):
    posted, downloads = [], []
    def post(url, **kwargs):
        posted.append(kwargs["json"])
        return Response({"request_id": "req", "output": {"audio": {"url": "https://example.oss-cn-beijing.aliyuncs.com/file.wav"}},
                         "usage": usage})
    def download(url, target):
        downloads.append(url)
        if len(downloads) == 1:
            raise api.BailianSpeechError("下载暂时失败")
        target.write_bytes(wav_bytes())
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(api, "download", download)
    profile = {"id": "test", "name": "测试", "provider_id": "bailian", "provider_voice_id": voice,
               "model_id": model, "speech_rate": 1.2}
    target = tmp_path / "take.wav"
    first = tts_runtime.generate_voice_audio(text="你好。", profile=profile, output_path=target)
    assert not first.success
    second = tts_runtime.generate_voice_audio(text="你好。", profile=profile, output_path=target)
    assert second.success, second.error
    assert len(posted) == 1
    assert posted[0]["model"] == model
    assert posted[0]["input"]["voice"] == voice
    assert posted[0]["input"]["rate"] == 1.2
    assert second.data["billing_unit"] == billing_unit
    assert second.data["estimated_cost_cny"] == api.tts_cost(usage, model) > 0
    if model == api.COSYVOICE_TTS_MODEL:
        assert second.data["estimated_cost_cny"] == 0.00336
    with wave.open(str(target)) as reader:
        assert reader.getnframes() == 2400
    assert second.data["audio_duration_seconds"] == 0.1
    assert "audio_url" not in json.dumps(second.data)


def test_cosyvoice_clone_is_visible_and_freezes_model_rate_and_billing():
    voice = "cosyvoice-v3.5-flash-test-voice"
    result = audio_center.add_custom_cloud_voice({"provider": "bailian", "name": "测试复刻音色",
        "voice_id": voice, "model_id": api.COSYVOICE_TTS_MODEL, "playback_rate": 1.0})
    public = next(p for p in result["profiles"] if p["model_id"] == api.COSYVOICE_TTS_MODEL)
    assert public["available"] and public["voice_type"] == "cloud_clone"
    assert public["billing_unit"] == "characters"
    profile = audio_center.get_voice_profile(public["id"])
    frozen = audio_center.freeze_voice_profile(profile)
    audio_center.set_cloud_voice_playback_rate(public["id"], {"playback_rate": 1.3})
    assert frozen["model_id"] == api.COSYVOICE_TTS_MODEL
    assert frozen["provider_voice_id"] == voice
    assert frozen["speech_rate"] == 1.0 and frozen["billing_unit"] == "characters"
    assert frozen["voice_signature"] != audio_center.get_voice_profile(public["id"])["voice_signature"]
    assert api.COSYVOICE_TTS_MODEL in bailian_config.read_bailian_config()["tts_models"]
    with pytest.raises(audio_center.AudioCenterError, match="已存在"):
        audio_center.add_custom_cloud_voice({"provider": "bailian", "name": "重复复刻音色",
            "voice_id": voice, "model_id": api.COSYVOICE_TTS_MODEL})


def test_cosyvoice_model_mismatch_is_rejected_before_provider_submission(tmp_path):
    voice = "cosyvoice-v3.5-flash-test-voice"
    with pytest.raises(audio_center.AudioCenterError, match="不一致"):
        audio_center.add_custom_cloud_voice({"provider": "bailian", "name": "模型错配", "voice_id": voice})
    result = BailianTTS().execute({"text": "测试", "voice_id": voice,
        "model": api.TTS_MODEL, "output_path": str(tmp_path / "mismatch.wav")})
    assert not result.success and "不一致" in result.error


def test_tts_ambiguous_submit_blocks_duplicate_charge(tmp_path, monkeypatch):
    calls = []
    def post(*args, **kwargs):
        calls.append(True)
        raise requests.Timeout("timeout")
    monkeypatch.setattr(requests, "post", post)
    payload = {"text": "测试", "voice_id": api.TEST_VOICE, "output_path": str(tmp_path / "test.wav")}
    assert BailianTTS().execute(payload).data["status"] == "ambiguous"
    assert BailianTTS().execute(payload).data["status"] == "ambiguous"
    assert len(calls) == 1


def test_asr_poll_failure_resumes_task_and_preserves_word_timestamps(tmp_path, monkeypatch):
    audio = tmp_path / "source.wav"
    audio.write_bytes(wav_bytes())
    submits, queries, accepted = [], [], []
    monkeypatch.setattr(bailian_asr, "upload_audio", lambda *a: {"file_url": "oss://test/audio.wav", "storage": "temporary"})
    def post(url, **kwargs):
        submits.append(kwargs)
        return Response({"output": {"task_id": "task-test"}, "request_id": "req-test"})
    def get(url, **kwargs):
        queries.append(url)
        if len(queries) == 1:
            raise requests.Timeout("poll timeout")
        return Response({"output": {"task_status": "SUCCEEDED", "results": [{"subtask_status": "SUCCEEDED", "transcription_url": "https://example.oss-cn-beijing.aliyuncs.com/result.json"}]}, "usage": {"input_tokens": 10, "output_tokens": 3}})
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(api, "download", lambda url, path: path.write_text(json.dumps({"transcripts": [{"text": "你好", "sentences": [{"begin_time": 120, "end_time": 900, "text": "你好", "words": [{"begin_time": 120, "end_time": 400, "text": "你"}]}]}]}), encoding="utf-8"))
    with pytest.raises(api.BailianSpeechError) as interrupted:
        bailian_asr.transcribe_file(audio, artifact_dir=tmp_path)
    assert interrupted.value.accepted is True and interrupted.value.task_id == "task-test"
    assert interrupted.value.definitive is False
    text, rows, metadata = bailian_asr.transcribe_file(audio, artifact_dir=tmp_path, on_accepted=accepted.append)
    assert text == "你好" and rows[0]["start"] == 0.12
    assert metadata["words"][0]["end"] == 0.4
    assert len(submits) == 1 and accepted == ["task-test"]
    assert submits[0]["headers"]["X-DashScope-OssResourceResolve"] == "enable"
    assert submits[0]["json"]["input"] == {"file_urls": ["oss://test/audio.wav"]}


def test_asr_ambiguous_submit_is_never_repeated(tmp_path, monkeypatch):
    audio = tmp_path / "source.wav"
    audio.write_bytes(wav_bytes())
    calls = []
    monkeypatch.setattr(bailian_asr, "upload_audio", lambda *a: {"file_url": "oss://test/audio.wav", "storage": "temporary"})
    def post(*args, **kwargs):
        calls.append(True)
        raise requests.Timeout("timeout")
    monkeypatch.setattr(requests, "post", post)
    for _ in range(2):
        with pytest.raises(api.BailianAmbiguous):
            bailian_asr.transcribe_file(audio, artifact_dir=tmp_path)
    assert len(calls) == 1


def test_long_tts_split_preserves_text():
    text = "长句" * 801 + "。末尾！"
    chunks = split_text(text)
    assert "".join(chunks) == text
    assert all(len(c) <= 400 for c in chunks)


def test_frozen_review_line_uses_saved_model_and_rate(tmp_path, monkeypatch):
    from backlot import review_preview_pipeline as pipeline
    from tools.base_tool import ToolResult
    captured = []
    def synth(**kwargs):
        captured.append(kwargs["profile"])
        kwargs["output_path"].write_bytes(b"test")
        return ToolResult(success=True, data={})
    monkeypatch.setattr(pipeline, "generate_voice_audio", synth)
    monkeypatch.setattr(audio_center, "get_voice_profile", lambda _: pytest.fail("must use frozen profile"))
    snapshot = {"id": "sample", "provider_id": "bailian", "model_id": api.TTS_MODEL, "speech_rate": 1.15}
    pipeline._synthesize_frozen_line({"text": "测试"}, tmp_path / "out.wav", {"profile_id": "sample", "provider": "bailian", "profile_snapshot": snapshot})
    assert captured == [snapshot]
