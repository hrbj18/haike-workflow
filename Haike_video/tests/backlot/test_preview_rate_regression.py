"""Offline regression for the multiplier selected for a CosyVoice audition."""

from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path

import pytest
import requests

from backlot import audio_center
from lib import bailian_speech as api
from lib.ffmpeg_locator import resolve_ffmpeg
from tools.base_tool import ToolStatus


MODEL = api.COSYVOICE_TTS_MODEL
VOICE = "cosyvoice-v3.5-flash-rate-test-voice"


@pytest.fixture
def isolated_cosyvoice_preview(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "offline-test-secret")
    monkeypatch.setenv("DASHSCOPE_WORKSPACE_ID", "")
    monkeypatch.setattr(audio_center, "AUDIO_CENTER_FILE", tmp_path / "audio_center.json")
    monkeypatch.setattr(audio_center, "PREVIEW_DIRECTORY", tmp_path / "previews")
    monkeypatch.setattr(audio_center.VoiceboxTTS, "get_status", lambda *args: ToolStatus.UNAVAILABLE)
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: pytest.fail("unexpected HTTP POST"))
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: pytest.fail("unexpected HTTP GET"))
    center = audio_center.add_custom_cloud_voice({
        "provider": "bailian", "name": "檬檬1", "voice_id": VOICE,
        "model_id": MODEL, "playback_rate": 1.0,
    })
    profile = next(row for row in center["profiles"] if row["model_id"] == MODEL)
    return profile["id"]


def _wav_bytes(duration):
    samples = round(24000 * duration)
    data = b"".join(struct.pack("<h", round(12000 * math.sin(2 * math.pi * 440 * index / 24000)))
                    for index in range(samples))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        writer.writeframes(data)
    return buffer.getvalue()


def test_saved_cosyvoice_multiplier_is_used_when_request_omits_rate(isolated_cosyvoice_preview):
    profile_id = isolated_cosyvoice_preview
    audio_center.set_cloud_voice_playback_rate(profile_id, {"playback_rate": 1.1})

    queued = audio_center.start_preview({"profile_id": profile_id, "text": "使用保存的语速。"})

    assert queued["preview_job"]["playback_rate"] == 1.1
    frozen = audio_center._load()["preview_job"]["profile_snapshot"]
    assert frozen["speech_rate"] == 1.1
    assert frozen["provider_speech_rate"] == 1.1
    assert frozen["model_id"] == MODEL


def test_explicit_cosyvoice_multiplier_reaches_provider_and_recent_preview(
    tmp_path, monkeypatch, isolated_cosyvoice_preview,
):
    assert resolve_ffmpeg(), "The audio normalisation contract needs the installed FFmpeg."
    profile_id = isolated_cosyvoice_preview
    posted = []
    # This is the cloud's already accelerated output, not a local tempo operation.
    provider_duration = 6.0 / 1.1
    provider_audio = _wav_bytes(provider_duration)

    class Response:
        status_code = 200
        ok = True

        def json(self):
            return {"request_id": "offline-rate-request", "usage": {"characters": 12},
                    "output": {"audio": {"url": "https://example.oss-cn-beijing.aliyuncs.com/rate.wav"}}}

    def post(url, **kwargs):
        assert url.endswith("/services/audio/tts/SpeechSynthesizer")
        posted.append(kwargs["json"])
        return Response()

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(api, "download", lambda url, target: target.write_bytes(provider_audio))
    monkeypatch.setattr(audio_center, "_apply_local_preview_tempo",
                        lambda *args: pytest.fail("CosyVoice must not receive a second tempo adjustment"))

    queued = audio_center.start_preview({
        "profile_id": profile_id, "text": "这是选择一点一倍速后的试听。", "playback_rate": 1.1,
    })
    assert queued["preview_job"]["playback_rate"] == 1.1
    audio_center.set_cloud_voice_playback_rate(profile_id, {"playback_rate": 1.4})
    audio_center.remove_custom_cloud_voice(profile_id)

    completed = audio_center.generate_preview()

    assert completed["preview_job"]["status"] == "completed", completed["preview_job"].get("error")
    assert len(posted) == 1
    assert posted[0]["model"] == MODEL
    assert posted[0]["input"]["voice"] == VOICE
    assert posted[0]["input"]["rate"] == 1.1
    preview = completed["previews"][0]
    assert preview["playback_rate"] == 1.1
    assert preview["provider_id"] == "bailian"
    assert preview["profile_name"] == "檬檬1"
    with wave.open(str(audio_center.preview_audio_path(preview["id"])), "rb") as reader:
        assert reader.getframerate() == 24000
        assert reader.getnchannels() == 1
        assert reader.getsampwidth() == 2
        actual_duration = reader.getnframes() / reader.getframerate()
    assert actual_duration == pytest.approx(provider_duration, abs=1 / 24000)
    assert preview["duration_seconds"] == pytest.approx(actual_duration)
    metadata = api.read_record(Path(preview["metadata_path"]))
    assert metadata["rate"] == 1.1
    assert metadata["model"] == MODEL
