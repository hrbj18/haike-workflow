"""Enrollment boundaries: no real uploads, cloud enrollment, or paid TTS calls."""
import io
import json
import math
from pathlib import Path
import struct
from types import SimpleNamespace
import wave

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot import audio_center as center
from backlot import bailian_voice_clone as clone
from backlot.bailian_voice_upload import receive_cloud_clone
from lib import bailian_speech as api
from tools.base_tool import ToolStatus

VOICE = api.COSYVOICE_TTS_MODEL + "-haike-test123"


def wav(seconds=6):
    result = io.BytesIO()
    with wave.open(result, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(24000)
        stream.writeframes(b"".join(struct.pack("<h", int(4000 * math.sin(i / 9))) for i in range(int(seconds * 24000))))
    return result.getvalue()


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(center, "AUDIO_CENTER_DIR", tmp_path / "audio")
    monkeypatch.setattr(center, "AUDIO_CENTER_FILE", tmp_path / "audio/audio_center.json")
    monkeypatch.setattr(center, "PREVIEW_DIRECTORY", tmp_path / "audio/previews")
    # The catalog checks the local tool directly before provider_status(). A
    # cloud enrollment fixture must never probe an optional background service.
    monkeypatch.setattr(center.VoiceboxTTS, "get_status", classmethod(lambda cls: ToolStatus.UNAVAILABLE))
    monkeypatch.setattr(center.VoiceboxTTS, "list_profiles", classmethod(lambda cls: []))
    monkeypatch.setattr(center, "provider_status", lambda _: ToolStatus.AVAILABLE)
    monkeypatch.setattr(center, "find_avatar_role_by_voice_profile", lambda _: None)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-not-a-real-key")
    monkeypatch.delenv("DASHSCOPE_WORKSPACE_ID", raising=False)
    for env, value in (("BAILIAN_OSS_ENDPOINT", "https://oss-cn-beijing.aliyuncs.com"),
                       ("BAILIAN_OSS_BUCKET", "private-test"), ("BAILIAN_OSS_ACCESS_KEY_ID", "fake-access"),
                       ("BAILIAN_OSS_ACCESS_KEY_SECRET", "fake-secret")):
        monkeypatch.setenv(env, value)
    uploaded, deleted, calls = [], [], []
    bucket = SimpleNamespace(put_object_from_file=lambda key, path, headers: uploaded.append((key, Path(path).read_bytes(), headers)),
                             sign_url=lambda *args, **kwargs: "https://private-test.oss-cn-beijing.aliyuncs.com/reference.wav?Signature=fake",
                             delete_object=lambda key: deleted.append(key))
    monkeypatch.setattr(clone, "_oss_bucket", lambda: bucket)
    binary = Path(__file__).resolve().parents[3] / "dist/haike-workflow-windows-x64-20261009/runtime/ffmpeg/ffmpeg.exe"
    if not binary.exists():
        from lib.ffmpeg_locator import resolve_ffmpeg
        binary = resolve_ffmpeg()
    if not binary: pytest.skip("FFmpeg required")
    monkeypatch.setattr(clone, "resolve_ffmpeg", lambda: str(binary))
    def post(url, **kwargs):
        assert url == api.api_base() + "/services/audio/tts/customization"
        assert kwargs["allow_redirects"] is False
        body = kwargs["json"]
        calls.append(body)
        output = {"voice_id": VOICE} if body["input"]["action"] == "create_voice" else {"status": "OK", "target_model": api.COSYVOICE_TTS_MODEL}
        return SimpleNamespace(status_code=200, ok=True, json=lambda: {"output": output, "request_id": "fake-request"})
    monkeypatch.setattr(clone.requests, "post", post)
    monkeypatch.setattr(clone.requests, "get", lambda *a, **k: pytest.fail("Unexpected network GET"))
    center.add_custom_cloud_voice({"provider": "bailian", "name": "原默认", "voice_id": api.TEST_VOICE, "model_id": api.TTS_MODEL})
    center.set_default_voice({"profile_id": center.read_audio_center()["profiles"][-1]["id"]})
    source = tmp_path / "reference.wav"
    source.write_bytes(wav())
    return SimpleNamespace(source=source, uploaded=uploaded, deleted=deleted, calls=calls, post=post, bucket=bucket)


def create(rig, name="我的声音"):
    return clone.create_voice(name, api.COSYVOICE_TTS_MODEL, rig.source, "yes")


def test_enroll_register_default_preserved_and_repeat_does_not_create(rig):
    default = center._load()["default_profile_id"]
    result = create(rig)
    assert result["status"] == "completed" and result["voice_id"] == VOICE
    assert center._load()["default_profile_id"] == default
    assert [c["input"]["action"] for c in rig.calls] == ["create_voice", "query_voice"]
    assert rig.calls[0]["model"] == "voice-enrollment"
    assert rig.calls[0]["input"]["target_model"] == api.COSYVOICE_TTS_MODEL
    assert rig.uploaded[0][2] == {"x-oss-object-acl": "private"}
    assert len(rig.deleted) == 1
    assert create(rig) == result and len(rig.calls) == 2
    record = clone._path(result["id"]).read_text(encoding="utf-8")
    assert "Signature=" not in record and "fake-secret" not in record and "test-not-a-real-key" not in record
    assert len(center._load()["custom_cloud_profiles"]) == 2


def test_create_timeout_is_durable_ambiguous_never_resubmitted(rig, monkeypatch):
    def timeout(*args, **kwargs):
        rig.calls.append(kwargs["json"])
        raise requests.Timeout("do not expose raw details")
    monkeypatch.setattr(clone.requests, "post", timeout)
    result = create(rig)
    assert result["status"] == "ambiguous"
    assert create(rig)["status"] == "ambiguous" and len(rig.calls) == 1
    assert "do not expose" not in result["error"]
    with pytest.raises(center.AudioCenterError, match="没有可查询"):
        clone.resume_voice(result["id"])
    assert not rig.deleted


def test_query_failure_recovers_saved_id_without_new_create(rig, monkeypatch):
    def post(url, **kwargs):
        if kwargs["json"]["input"]["action"] == "query_voice":
            raise requests.Timeout()
        return rig.post(url, **kwargs)
    monkeypatch.setattr(clone.requests, "post", post)
    result = create(rig)
    assert result["status"] == "checking" and result["voice_id"] == VOICE
    monkeypatch.setattr(clone.requests, "post", rig.post)
    assert clone.resume_voice(result["id"])["status"] == "completed"
    assert [c["input"]["action"] for c in rig.calls].count("create_voice") == 1


@pytest.mark.parametrize("status,expected", [("DEPLOYING", "checking"), ("UNDEPLOYED", "failed"), ("NEW_UNKNOWN", "checking")])
def test_provider_status_not_registered_until_ok(rig, monkeypatch, status, expected):
    def post(url, **kwargs):
        if kwargs["json"]["input"]["action"] == "query_voice":
            return SimpleNamespace(status_code=200, ok=True, json=lambda: {"output": {"status": status}})
        return rig.post(url, **kwargs)
    monkeypatch.setattr(clone.requests, "post", post)
    result = create(rig)
    assert result["status"] == expected
    assert len(center._load()["custom_cloud_profiles"]) == 1
    monkeypatch.setattr(clone.requests, "post", rig.post)
    assert clone.resume_voice(result["id"])["status"] == "completed"
    assert sum(c["input"]["action"] == "create_voice" for c in rig.calls) == 1


def test_registration_failure_recovers_without_new_cloud_voice(rig, monkeypatch):
    real = clone._register
    monkeypatch.setattr(clone, "_register", lambda _: (_ for _ in ()).throw(OSError("disk full")))
    result = create(rig)
    assert result["status"] == "checking" and result["voice_id"] == VOICE
    monkeypatch.setattr(clone, "_register", real)
    assert clone.resume_voice(result["id"])["status"] == "completed"
    assert sum(c["input"]["action"] == "create_voice" for c in rig.calls) == 1


def test_cleanup_failure_retains_saved_voice_and_warning(rig, monkeypatch):
    rig.bucket.delete_object = lambda _: (_ for _ in ()).throw(OSError())
    result = create(rig)
    assert result["status"] == "completed" and "生命周期" in result["cleanup_warning"]


def test_account_change_cannot_query_old_voice(rig, monkeypatch):
    result = create(rig)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "another-test-key")
    with pytest.raises(center.AudioCenterError, match="账号"):
        clone.resume_voice(result["id"])
    assert len(rig.calls) == 2


@pytest.mark.parametrize("bad", ["../etc", "BC-" + "a" * 31, "x"])
def test_job_path_cannot_escape(bad):
    with pytest.raises(center.AudioCenterError): clone.resume_voice(bad)


@pytest.mark.parametrize("seconds", [1])
def test_invalid_duration_rejected_before_upload(rig, seconds):
    rig.source.write_bytes(wav(seconds))
    with pytest.raises(center.AudioCenterError, match="5 秒"):
        create(rig)
    assert not rig.uploaded and not rig.calls


def test_name_collision_prevents_cloud_call(rig):
    with pytest.raises(center.AudioCenterError, match="同名"):
        create(rig, "原默认")
    assert not rig.uploaded and not rig.calls


@pytest.fixture
def client():
    app = FastAPI()
    app.post("/clone")(receive_cloud_clone)
    return TestClient(app)


def test_multipart_endpoint_creates_without_transcript(rig, client):
    response = client.post("/clone", data={"name": "本人声音", "model_id": api.COSYVOICE_TTS_MODEL, "consent": "yes"}, files={"audio": ("record.wav", rig.source.read_bytes(), "audio/wav")})
    assert response.status_code == 200 and response.json()["status"] == "completed"


@pytest.mark.parametrize("consent", ["no", "", "true"])
def test_consent_required_before_network(rig, client, consent):
    response = client.post("/clone", data={"name": "本人声音", "model_id": api.COSYVOICE_TTS_MODEL, "consent": consent}, files={"audio": ("record.wav", b"bad")})
    assert response.status_code == 422 and not rig.calls and not rig.uploaded


def test_oversize_and_extra_field_rejected(rig, client):
    data = {"name": "本人声音", "model_id": api.COSYVOICE_TTS_MODEL, "consent": "yes"}
    response = client.post("/clone", data=data, files={"audio": ("record.wav", b"x" * (clone.MAX_UPLOAD_BYTES + 1))})
    assert response.status_code == 413
    response = client.post("/clone", data={**data, "server_path": "C:/secret"}, files={"audio": ("record.wav", b"bad")})
    assert response.status_code == 422 and not rig.calls


def test_actual_workbench_routes_expose_new_flow(rig, monkeypatch):
    from backlot import server
    monkeypatch.setenv("HAIKE_INTERNAL_TESTING", "1")
    client = TestClient(server.create_app())
    response = client.post("/api/audio-center/bailian-clones", data={"name": "路由测试", "model_id": api.COSYVOICE_TTS_MODEL, "consent": "yes"},
                           files={"audio": ("record.wav", rig.source.read_bytes())})
    assert response.status_code == 201 and response.json()["status"] == "completed"
    listing = client.get("/api/audio-center/bailian-clones")
    assert listing.status_code == 200 and listing.json()["jobs"][0]["voice_id"] == VOICE
    assert "account" not in listing.text and "Signature" not in listing.text
    assert client.post("/api/audio-center/bailian-clones/not-a-job/resume").status_code == 422
    # The retained internal API no longer ships the retired global-audio UI.
    assert client.get("/ui/audio_center.js").status_code == 404


@pytest.mark.parametrize("response", [
    SimpleNamespace(status_code=503, ok=False, json=lambda: {}),
    SimpleNamespace(status_code=200, ok=True, json=lambda: {"output": {}}),
])
def test_uncertain_create_responses_do_not_repeat(rig, monkeypatch, response):
    monkeypatch.setattr(clone.requests, "post", lambda *a, **k: (rig.calls.append(k["json"]) or response))
    result = create(rig)
    assert result["status"] == "ambiguous"
    assert create(rig)["status"] == "ambiguous" and len(rig.calls) == 1


def test_rejected_create_can_only_retry_explicitly(rig, monkeypatch):
    response = SimpleNamespace(status_code=400, ok=False, json=lambda: {"code": "BadAudio", "message": "sample invalid"})
    monkeypatch.setattr(clone.requests, "post", lambda *a, **k: response)
    result = create(rig)
    assert result["status"] == "rejected" and len(rig.deleted) == 1
    monkeypatch.setattr(clone.requests, "post", rig.post)
    assert create(rig)["status"] == "completed"


def test_resume_readiness_never_uploads_or_calls_cloud(rig):
    assert clone.list_jobs()["jobs"] == []
    assert not rig.calls and not rig.uploaded


def test_existing_voice_can_resume_without_oss_credentials(rig, monkeypatch):
    result = create(rig)
    record_path = clone._path(result["id"])
    record = api.read_record(record_path)
    record["status"] = "checking"
    api.write_record(record_path, record)
    for env in ("BAILIAN_OSS_ENDPOINT", "BAILIAN_OSS_BUCKET", "BAILIAN_OSS_ACCESS_KEY_ID",
                "BAILIAN_OSS_ACCESS_KEY_SECRET"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(clone, "_oss_bucket", lambda: pytest.fail("Query must not require storage"))
    assert clone.resume_voice(result["id"])["status"] == "completed"
    assert [call["input"]["action"] for call in rig.calls] == ["create_voice", "query_voice", "query_voice"]


@pytest.fixture
def temporary_rig(rig, monkeypatch):
    for env in ("BAILIAN_OSS_ENDPOINT", "BAILIAN_OSS_BUCKET", "BAILIAN_OSS_ACCESS_KEY_ID",
                "BAILIAN_OSS_ACCESS_KEY_SECRET"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(clone, "_oss_bucket", lambda: pytest.fail("Temporary upload must not use private OSS"))
    def get(url, **kwargs):
        assert url == api.api_base() + "/uploads"
        assert kwargs["params"] == {"action": "getPolicy", "model": "voice-enrollment"}
        return SimpleNamespace(status_code=200, ok=True, json=lambda: {"data": {
            "upload_host": "https://temporary.oss-cn-beijing.aliyuncs.com",
            "upload_dir": "test-temporary", "oss_access_key_id": "temporary-id",
            "signature": "temporary-signature", "policy": "temporary-policy"}})
    def post(url, **kwargs):
        if url == "https://temporary.oss-cn-beijing.aliyuncs.com":
            assert kwargs["allow_redirects"] is False
            assert kwargs["data"]["x-oss-object-acl"] == "private"
            audio = kwargs["files"]["file"][1].read()
            with wave.open(io.BytesIO(audio), "rb") as stream:
                assert (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) == (1, 2, 24000)
            rig.uploaded.append(audio)
            return SimpleNamespace(status_code=204)
        action = kwargs["json"]["input"]["action"]
        if action == "create_voice":
            assert kwargs["headers"]["X-DashScope-OssResourceResolve"] == "enable"
            assert kwargs["json"]["input"]["url"].startswith("oss://test-temporary/")
        else:
            assert "X-DashScope-OssResourceResolve" not in kwargs["headers"]
        return rig.post(url, **kwargs)
    monkeypatch.setattr(clone.requests, "get", get)
    monkeypatch.setattr(clone.requests, "post", post)
    return rig


def test_cosyvoice_temporary_upload_needs_only_api_key_preserves_model_and_default(temporary_rig):
    default = center._load()["default_profile_id"]
    assert clone.readiness()["ready"] and clone.readiness()["storage_mode"] == "temporary"
    result = create(temporary_rig)
    assert result["status"] == "completed" and result["model_id"] == api.COSYVOICE_TTS_MODEL
    assert center._load()["default_profile_id"] == default
    assert len(temporary_rig.uploaded) == 1 and not temporary_rig.deleted
    assert create(temporary_rig) == result and len(temporary_rig.calls) == 2
    assert len(temporary_rig.uploaded) == 1
    record = clone._path(result["id"]).read_text(encoding="utf-8")
    assert "temporary-signature" not in record and "oss://" not in record


def test_long_recording_uses_first_twenty_seconds(temporary_rig):
    temporary_rig.source.write_bytes(wav(61))
    result = create(temporary_rig)
    assert result["status"] == "completed" and result["reference_trimmed"]
    assert result["reference_duration_seconds"] == 20
    with wave.open(io.BytesIO(temporary_rig.uploaded[0]), "rb") as stream:
        assert stream.getnframes() / stream.getframerate() == 20


def test_temporary_actual_workbench_upload_and_catalog(temporary_rig, monkeypatch):
    from backlot import server
    monkeypatch.setenv("HAIKE_INTERNAL_TESTING", "1")
    client = TestClient(server.create_app())
    response = client.post("/api/audio-center/bailian-clones", data={
        "name": "临时上传路由", "model_id": api.COSYVOICE_TTS_MODEL, "consent": "yes"},
        files={"audio": ("sample.wav", temporary_rig.source.read_bytes(), "audio/wav")})
    assert response.status_code == 201 and response.json()["status"] == "completed"
    profile_id = response.json()["profile_id"]
    profile = next(item for item in client.get("/api/audio-center").json()["profiles"] if item["id"] == profile_id)
    assert profile["voice_type"] == "cloud_clone" and profile["model_id"] == api.COSYVOICE_TTS_MODEL
    assert profile["available"] and len(temporary_rig.calls) == 2


def test_temporary_rejection_has_no_private_storage_cleanup(temporary_rig, monkeypatch):
    post = clone.requests.post
    def rejected(url, **kwargs):
        if url.endswith("/customization"):
            return SimpleNamespace(status_code=400, ok=False, json=lambda: {
                "code": "BadAudio", "message": "invalid data:audio/wav;base64,QUJDRA=="})
        return post(url, **kwargs)
    monkeypatch.setattr(clone.requests, "post", rejected)
    result = create(temporary_rig)
    assert result["status"] == "rejected" and "QUJDRA==" not in json.dumps(result)
    assert not temporary_rig.deleted
