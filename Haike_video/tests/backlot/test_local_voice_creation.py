from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import urllib.request
import wave

import pytest
from fastapi.testclient import TestClient

from backlot import audio_center as center
from backlot import local_voice_upload as upload
from backlot import server
from tools.audio.openmontage_tts_engine import ProfileStore
from tools.base_tool import ToolStatus


def _wav_bytes(seconds: float = 1.5) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(24000)
        stream.writeframes(b"\0\0" * int(24000 * seconds))
    return buffer.getvalue()


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    data_dir = tmp_path / "private-tts"
    monkeypatch.setenv("OPENMONTAGE_TTS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("OPENMONTAGE_TTS_BASE_URL", "http://127.0.0.1:17494")
    monkeypatch.setattr(center, "AUDIO_CENTER_DIR", tmp_path / "audio")
    monkeypatch.setattr(center, "AUDIO_CENTER_FILE", tmp_path / "audio" / "audio_center.json")
    monkeypatch.setattr(center, "PREVIEW_DIRECTORY", tmp_path / "audio" / "previews")
    monkeypatch.setattr(center.VoiceboxTTS, "get_status", classmethod(lambda cls: ToolStatus.AVAILABLE))
    default_file = tmp_path / "defaults.json"
    default_file.write_text('{"profiles": []}', encoding="utf-8")
    monkeypatch.setattr(center.VoiceboxTTS, "list_profiles", classmethod(
        lambda cls: ProfileStore(data_dir, default_file=default_file).public_profiles()))
    monkeypatch.setattr(center, "provider_status", lambda provider:
        ToolStatus.AVAILABLE if provider == center.LOCAL_PROVIDER_ID else ToolStatus.UNAVAILABLE)
    health = {"service": "openmontage-local-tts", "status": "healthy", "data_dir": str(data_dir)}
    probes = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, count):
            assert count == 65537
            return json.dumps(health).encode("utf-8")

    class Opener:
        def open(self, request, timeout):
            assert timeout == 3
            probes.append(request.full_url)
            return Response()

    def opener(*handlers):
        proxy = next(handler for handler in handlers if isinstance(handler, urllib.request.ProxyHandler))
        assert proxy.proxies == {}
        assert any(isinstance(handler, center._NoLocalRedirects) for handler in handlers)
        return Opener()

    monkeypatch.setattr(center.urllib.request, "build_opener", opener)
    from lib import ffmpeg_locator
    bundled = Path(__file__).resolve().parents[2].parent / "dist" / "haike-workflow-windows-x64-20261009" / "runtime" / "ffmpeg" / "ffmpeg.exe"
    binary = str(bundled) if bundled.is_file() else ffmpeg_locator.resolve_ffmpeg()
    if binary is None:
        pytest.skip("a local FFmpeg runtime is required for enrollment decoding tests")
    monkeypatch.setattr(ffmpeg_locator, "resolve_ffmpeg", lambda: binary)
    return data_dir, health, probes


@pytest.mark.parametrize("name,text,expected", [
    ("", "原文", "显示名称"),
    ("我的声音", " \n ", "逐字原文"),
    ("声" * 81, "原文", "80"),
    ("我的声音", "文" * 5001, "5000"),
    ("声音\n新行", "原文", "控制字符"),
], ids=["empty-name", "empty-text", "long-name", "long-text", "control-character"])
def test_rejects_invalid_fields_without_touching_service(local_store, tmp_path, name, text, expected):
    data_dir, _, probes = local_store
    audio = tmp_path / "audio.wav"
    audio.write_bytes(_wav_bytes())
    with pytest.raises(center.AudioCenterError, match=expected):
        center.add_local_clone_voice(name, text, audio)
    assert probes == []
    assert not data_dir.exists()


@pytest.mark.parametrize("url", [
    "https://tts.example.com", "http://127.0.0.2:17494", "http://localhost.evil.test",
    "http://user:pass@localhost:17494", "http://localhost:bad", "file:///health",
    "http://localhost:17494/not-root", "http://localhost:17494?server=other",
])
def test_rejects_remote_or_ambiguous_service_before_network(local_store, monkeypatch, url):
    data_dir, _, probes = local_store
    monkeypatch.setenv("OPENMONTAGE_TTS_BASE_URL", url)
    with pytest.raises(center.AudioCenterError, match="本机"):
        center._local_clone_data_dir()
    assert not probes
    assert not data_dir.exists()


def test_requires_healthy_own_service_and_matching_directory(local_store, tmp_path):
    data_dir, health, probes = local_store
    health["service"] = "unrelated-server"
    with pytest.raises(center.AudioCenterError, match="尚未就绪"):
        center._local_clone_data_dir()
    health["service"] = "openmontage-local-tts"
    health["status"] = "degraded"
    with pytest.raises(center.AudioCenterError, match="尚未就绪"):
        center._local_clone_data_dir()
    health["status"] = "healthy"
    health["data_dir"] = str(tmp_path / "another-workspace")
    with pytest.raises(center.AudioCenterError, match="目录不同"):
        center._local_clone_data_dir()
    assert len(probes) == 3
    assert not data_dir.exists()


def test_unavailable_service_preserves_private_store(local_store, monkeypatch):
    data_dir, _, _ = local_store

    def unavailable(*_args):
        raise OSError("socket unavailable with a private path")

    monkeypatch.setattr(center.urllib.request, "build_opener", unavailable)
    with pytest.raises(center.AudioCenterError, match="先安装并启动") as error:
        center._local_clone_data_dir()
    assert "private path" not in str(error.value)
    assert not data_dir.exists()


def test_creates_stable_private_profile_and_returns_public_catalog(local_store, tmp_path):
    data_dir, _, probes = local_store
    source = tmp_path / "supplied.wav"
    source.write_bytes(_wav_bytes())
    text = "这是一段不得出现在公开目录里的测试原文。"
    result = center.add_local_clone_voice("测试自己的声音", text, source)
    profile_id = result["created_local_voice_id"]
    profile = next(item for item in result["profiles"] if item["id"] == profile_id)
    assert profile["voice_type"] == "cloned"
    assert profile["default_engine"] == "qwen"
    assert profile["provider_id"] == "voicebox_tts"
    assert profile["provider_name"] == "本地 Qwen3-TTS"
    assert profile["available"]
    assert len(profile["voice_signature"]) == 64
    assert result["created_local_voice_name"] == "测试自己的声音"
    public = json.dumps(result, ensure_ascii=False)
    assert text not in public and str(data_dir) not in public and "reference.wav" not in public
    private = json.loads((data_dir / "profiles.json").read_text(encoding="utf-8"))
    sample = private["profiles"][0]["samples"][0]
    assert sample["reference_text"] == text
    with wave.open(str(data_dir / sample["audio_path"]), "rb") as stream:
        assert (stream.getnchannels(), stream.getframerate(), stream.getsampwidth()) == (1, 24000, 2)
    again = center.add_local_clone_voice("测试自己的声音", text, source)
    assert again["created_local_voice_id"] == profile_id
    assert len(json.loads((data_dir / "profiles.json").read_text(encoding="utf-8"))["profiles"]) == 1
    assert probes == ["http://127.0.0.1:17494/health"] * 2


def test_bad_audio_leaves_no_profile_and_no_lock(local_store, tmp_path):
    data_dir, _, _ = local_store
    source = tmp_path / "invalid.mp3"
    source.write_bytes(b"not a real recording")
    with pytest.raises(center.AudioCenterError, match="无法读取参考录音"):
        center.add_local_clone_voice("我的声音", "原文", source)
    assert not (data_dir / "profiles.json").exists()
    assert not (data_dir / "enroll.lock").exists()


def test_mp3_is_decoded_without_trusting_upload_extension(local_store, tmp_path):
    from lib.ffmpeg_locator import resolve_ffmpeg

    wav = tmp_path / "source.wav"
    wav.write_bytes(_wav_bytes())
    mp3 = tmp_path / "input.mp3"
    subprocess.run([resolve_ffmpeg(), "-nostdin", "-v", "error", "-i", str(wav), str(mp3)],
                   check=True, capture_output=True, timeout=10)
    renamed = tmp_path / "reference.audio"
    mp3.rename(renamed)
    state = center.add_local_clone_voice("MP3测试", "测试原文", renamed)
    assert state["created_local_voice_name"] == "MP3测试"


def test_playlist_is_not_loaded_as_a_recording(local_store, tmp_path):
    source = tmp_path / "playlist.m3u"
    source.write_text("#EXTM3U\nhttp://127.0.0.1:1/not-an-audio-upload\n", encoding="utf-8")
    with pytest.raises(center.AudioCenterError, match="无法读取参考录音"):
        center.add_local_clone_voice("我的声音", "原文", source)
    assert not (local_store[0] / "profiles.json").exists()


def test_corrupt_private_catalog_is_never_overwritten(local_store, tmp_path):
    data_dir, _, _ = local_store
    data_dir.mkdir()
    catalog = data_dir / "profiles.json"
    catalog.write_text("{broken", encoding="utf-8")
    source = tmp_path / "recording.wav"
    source.write_bytes(_wav_bytes())
    with pytest.raises(center.AudioCenterError, match="未覆盖"):
        center.add_local_clone_voice("我的声音", "原文", source)
    assert catalog.read_text() == "{broken"
    assert not (data_dir / "enroll.lock").exists()


def _app_client():
    # TestClient without a context does not execute the production lifespan.
    return TestClient(server.create_app())


def test_multipart_route_uploads_and_cleans_temporary_input(local_store, monkeypatch, internal_supplier_mode):
    client = _app_client()
    original = upload.add_local_clone_voice
    saved_paths = []

    def enroll(name, text, path):
        saved_paths.append(path)
        assert path.is_file()
        return original(name, text, path)

    monkeypatch.setattr(upload, "add_local_clone_voice", enroll)
    response = client.post("/api/audio-center/local-voices", data={"name": "新声音", "reference_text": "测试逐字原文"},
                           files={"audio": ("../../not-a-server-path.wav", _wav_bytes(), "audio/wav")})
    assert response.status_code == 201, response.text
    assert response.json()["created_local_voice_name"] == "新声音"
    assert saved_paths and not saved_paths[0].exists() and not saved_paths[0].parent.exists()


def test_route_cleans_temporary_input_on_enrollment_failure(local_store, monkeypatch, internal_supplier_mode):
    paths = []

    def fail(_name, _text, path):
        paths.append(path)
        raise center.AudioCenterError("本地服务尚未就绪")

    monkeypatch.setattr(upload, "add_local_clone_voice", fail)
    response = _app_client().post("/api/audio-center/local-voices",
        data={"name": "声音", "reference_text": "原文"}, files={"audio": ("recording.wav", _wav_bytes(), "audio/wav")})
    assert response.status_code == 422
    assert paths and not paths[0].exists() and not paths[0].parent.exists()


@pytest.mark.parametrize("data", [
    {"name": "新声音"},
    {"name": " ", "reference_text": "原文"},
    {"name": "新声音", "reference_text": "原文", "data_dir": "D:/arbitrary"},
])
def test_route_rejects_missing_fields_and_client_directory(local_store, data, internal_supplier_mode):
    response = _app_client().post("/api/audio-center/local-voices", data=data,
                                  files={"audio": ("audio.wav", _wav_bytes(), "audio/wav")})
    assert response.status_code == 422
    assert not local_store[0].exists()


def test_route_bounds_audio_during_multipart_parse(local_store, monkeypatch, internal_supplier_mode):
    # Use a small limit to exercise the exact same streaming guard without
    # allocating a 20 MB fixture. No server-side enrollment must be called.
    monkeypatch.setattr(upload, "MAX_LOCAL_VOICE_UPLOAD_BYTES", 128)
    response = _app_client().post("/api/audio-center/local-voices",
                                  data={"name": "声音", "reference_text": "原文"},
                                  files={"audio": ("large.wav", b"x" * 129, "audio/wav")})
    assert response.status_code == 413
    assert not local_store[0].exists()


def test_route_rejects_large_declared_body_before_parsing(local_store, internal_supplier_mode):
    response = _app_client().post("/api/audio-center/local-voices", content=b"",
        headers={"Content-Type": "multipart/form-data; boundary=x", "Content-Length": str(21 * 1024 * 1024)})
    assert response.status_code == 413
    assert not local_store[0].exists()
