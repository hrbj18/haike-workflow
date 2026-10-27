"""Windows journal paths must remain durable before any paid HTTP request."""
import os

import pytest
import requests

from lib import bailian_speech as api
from tools.audio.bailian_tts import BailianTTS


@pytest.mark.skipif(os.name != "nt", reason="Windows MAX_PATH regression")
def test_atomic_record_survives_a_243_character_parent(tmp_path):
    padding = 243 - len(str(tmp_path)) - 1
    assert padding > 0
    folder = tmp_path / ("x" * padding)
    folder.mkdir()
    target = folder / "0000.json"
    api.write_record(target, {"status": "submitting"})
    assert api.read_record(target) == {"status": "submitting"}
    api.write_record(target, {"status": "accepted", "request_id": "test-receipt"})
    assert api.read_record(target)["request_id"] == "test-receipt"
    assert list(folder.iterdir()) == [target]


@pytest.mark.skipif(os.name != "nt", reason="Windows MAX_PATH regression")
def test_receipted_download_survives_its_long_temporary_name(tmp_path, monkeypatch):
    folder = tmp_path / ("x" * (243 - len(str(tmp_path)) - 1))
    folder.mkdir()
    target = folder / "0000.raw.wav"
    response = type("Response", (), {"status_code": 200, "content": b"existing-paid-audio"})()
    monkeypatch.setattr(requests, "get", lambda *a, **kw: response)
    monkeypatch.setattr(requests, "post", lambda *a, **kw: pytest.fail("must reuse existing receipt"))
    api.download("https://result.oss-cn-beijing.aliyuncs.com/original.wav", target)
    assert target.read_bytes() == b"existing-paid-audio"
    assert list(folder.iterdir()) == [target]


def test_submit_journal_failure_never_reaches_paid_http(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("DASHSCOPE_API_KEY", "isolated-test-key")
    monkeypatch.setenv("DASHSCOPE_WORKSPACE_ID", "")
    monkeypatch.setattr("tools.audio.bailian_tts.resolve_ffmpeg", lambda: "unused-ffmpeg")
    def fail_journal(*args, **kwargs):
        raise FileNotFoundError("isolated journal failure")
    monkeypatch.setattr(api, "write_record", fail_journal)
    monkeypatch.setattr(requests, "post", lambda *a, **kw: calls.append("paid-http"))
    result = BailianTTS().execute({"text": "隔离测试。", "voice_id": api.TEST_VOICE,
                                  "model": api.TTS_MODEL, "rate": 1.0,
                                  "output_path": str(tmp_path / "voice.wav")})
    assert not result.success
    assert "isolated journal failure" in result.error
    assert calls == []
