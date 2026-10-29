import io
import os
import wave
from types import SimpleNamespace

import pytest
from test_commerce import enable, fund, real_quote
from test_platform import key, submit

from gateway_client import HaikeClient
from platform_app import adapters, gateway, providers
from platform_app.store import Problem


def test_cosyvoice_uses_provider_usage_receipt_and_voice(monkeypatch, tmp_path):
    from dashscope.audio.http_tts.http_speech_synthesizer import HttpSpeechSynthesizer

    vault = providers.Vault(tmp_path)
    vault.update(
        "bailian",
        {"api_key": "test-supplier-only", "voice": "test-voice", "enabled": True},
    )
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            status_code=200,
            usage={"characters": 8},
            audio_url="https://example.test/audio.wav",
            audio_id="audio-test",
        )

    monkeypatch.setattr(HttpSpeechSynthesizer, "call", fake)
    result = adapters.Adapter(vault, tmp_path).execute(
        "haike/cosyvoice", {"text": "海 客  "}, lambda _: None
    )
    assert result["usage"] == {"characters": 8}
    assert captured["audio_format"] == "wav" and captured["voice"] == "test-voice"
    assert captured["api_key"] == "test-supplier-only"
    assert captured["url"] == "https://dashscope.aliyuncs.com/api/v1"
    assert "test-supplier-only" not in str(result)


def test_runninghub_exact_frame_contract_and_resume_queries_only(monkeypatch, tmp_path):
    vault = providers.Vault(tmp_path)
    vault.update("runninghub", {"api_key": "test-supplier-only", "enabled": True})
    (tmp_path / "image").write_bytes(b"image")
    (tmp_path / "audio").write_bytes(b"audio")
    requests, checkpointed = [], []

    def fake(url, headers, body=None, raw=None, method=None):
        requests.append((url, headers, body, raw))
        if url.endswith("/upload/binary"):
            return {"data": {"fileName": "test-uploaded"}}
        if url.endswith("/create"):
            return {"data": {"taskId": "test-task-id"}}
        return {
            "status": "SUCCESS",
            "results": [{"outputType": "mp4", "url": "https://example.test/video.mp4"}],
        }

    monkeypatch.setattr(adapters, "http", fake)
    adapter = adapters.Adapter(vault, tmp_path)
    result = adapter.execute(
        "haike/avatar",
        {"audio_file": "audio", "image_file": "image", "total_frames": 222},
        checkpointed.append,
    )
    create = next(r[2] for r in requests if r[0].endswith("/create"))
    assert (
        create["instanceType"] == "plus"
        and create["workflowId"] == "2094449979141218305"
    )
    assert {"nodeId": "35", "fieldName": "value", "fieldValue": 222} in create[
        "nodeInfoList"
    ]
    assert checkpointed == ["test-task-id"] and result["upstream_id"] == "test-task-id"
    requests.clear()
    adapter.execute("haike/avatar", {}, checkpointed.append, upstream_id="test-task-id")
    assert len(requests) == 1 and requests[0][0].endswith("/openapi/v2/query")


def test_upload_duration_ownership_and_unknown_restart_without_resubmit(env):
    store, _, client, _outsider, _, user, other = env
    enable(store)
    wave_bytes = io.BytesIO()
    with wave.open(wave_bytes, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\0\0" * 16001)
    uploaded = gateway.upload(store, user["id"], "audio", wave_bytes.getvalue())
    assert uploaded["seconds"] == 2 and uploaded["total_frames"] == 26
    with store.read() as db, pytest.raises(Problem):
        gateway.clean_input(
            db, other["id"], "haike/tencent-asr", {"audio_file": uploaded["id"]}
        )
    headers, _ = key(client)
    fund(env)
    job = submit(client, headers, real_quote(client, headers)).json()
    with store.write() as db:
        db.execute(
            "UPDATE gateway_jobs SET status='submitting' WHERE id=?", (job["id"],)
        )
    gateway.recover(store)
    assert gateway.get_job(store, user, job["id"])["status"] == "submission_unknown"
    with store.write() as db:
        db.execute(
            "UPDATE gateway_jobs SET status='submitting',upstream_id='persisted-provider-task' WHERE id=?",
            (job["id"],),
        )
    gateway.recover(store)
    assert gateway.get_job(store, user, job["id"])["status"] == "running"


def test_sdk_lost_submission_response_recovers_original_job(env, tmp_path):
    store, _, client, _, _, user, _ = env
    enable(store)
    fund(env)
    headers, created = key(client)
    sdk = HaikeClient("http://127.0.0.1/v2", created["secret"], tmp_path)
    lost = [False]

    def request(path, body=None, idem=None, raw=None):
        h = {**headers, **({"Idempotency-Key": idem} if idem else {})}
        response = (
            client.post("/v2" + path, json=body, headers=h)
            if body is not None
            else client.get("/v2" + path, headers=h)
        )
        assert response.status_code == 200, response.text
        if path == "/jobs" and not lost[0]:
            lost[0] = True
            raise ConnectionError("simulated lost response")
        return response.json()

    sdk.request = request
    q = sdk.quote("haike/cosyvoice", {"text": "海客"})
    intent = sdk.confirm(q, 1000000)
    assert not gateway.list_jobs(store, user)
    with pytest.raises(ConnectionError):
        sdk.resume(intent)
    job = sdk.resume(intent)
    assert sdk.resume(intent)["id"] == job["id"]
    assert len(gateway.list_jobs(store, user)) == 1
    journal_path = tmp_path / (intent + ".json")
    assert journal_path.is_file()
    if os.name != "nt":  # Windows stat exposes read-only flags, not POSIX permissions/ACLs.
        assert journal_path.stat().st_mode & 0o777 == 0o600
