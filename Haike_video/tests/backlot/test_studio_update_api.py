from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import hashlib
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from portable import update_service as updates
from backlot import studio_update_api as api


def client(tmp_path):
    (tmp_path / "VERSION.json").write_text('{"version":"1.0.0"}', encoding="utf-8")
    app = FastAPI()
    app.state.app_update_service = updates.UpdateService(tmp_path)
    api.attach(app)
    app.post("/api/synthetic-write")(lambda: {"ok": True})
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 1234)), app


def test_local_origin_and_host_guards(tmp_path):
    web, app = client(tmp_path)
    assert web.get("/api/studio/app-update").status_code == 200
    assert web.post("/api/studio/app-update/check", json={}).status_code == 403
    assert web.post("/api/studio/app-update/install", json={}, headers={"Origin": "https://untrusted.test"}).status_code == 403
    assert web.get("/api/studio/app-update", headers={"Host": "untrusted.test"}).status_code == 403
    response = web.post("/api/studio/app-update/install", json={"version": "1.0.1", "confirmed": True}, headers={"Origin": "http://127.0.0.1"})
    assert response.status_code == 409


def test_maintenance_blocks_new_writes_and_retains_read_access(tmp_path):
    web, app = client(tmp_path)
    updates.set_operation(tmp_path, "waiting", "等待现有任务结束")
    assert web.post("/api/synthetic-write").status_code == 503
    assert web.get("/api/studio/app-update").status_code == 200
    assert web.post("/api/studio/app-update/cancel", json={}, headers={"Origin": "http://127.0.0.1"}).json()["operation"]["status"] == "cancelled"
    assert web.post("/api/synthetic-write").status_code == 200


def test_readiness_requires_helper_token_and_all_tasks_idle(tmp_path, monkeypatch):
    web, app = client(tmp_path)
    identity = "a" * 24
    updates.set_operation(tmp_path, "waiting", "等待", id=identity)
    updates.write_json(updates.private_path(tmp_path, identity + "/operation.json"), {"token": "synthetic-token"})
    app.state.production_queue = SimpleNamespace(list=lambda **kw: {"active_count": 1})
    monkeypatch.setattr(api, "publisher_busy", lambda root: "")
    assert web.get("/api/studio/app-update/readiness").status_code == 403
    headers = {"X-Haike-Update-Token": "synthetic-token"}
    assert not web.get("/api/studio/app-update/readiness", headers=headers).json()["ready"]
    app.state.production_queue = SimpleNamespace(list=lambda **kw: {})
    assert web.get("/api/studio/app-update/readiness", headers=headers).json()["ready"]
    monkeypatch.setattr(api, "publisher_busy", lambda root: "正在发布")
    assert not web.get("/api/studio/app-update/readiness", headers=headers).json()["ready"]


def test_cli_admission_and_interrupted_receipt_guard(tmp_path, monkeypatch):
    from backlot import production_queue as queue
    monkeypatch.setattr(queue, "__file__", str(tmp_path / "Haike_video/backlot/production_queue.py"))
    assert not queue._update_maintenance()
    updates.set_operation(tmp_path, "waiting", "等待")
    assert queue._update_maintenance()
    assert not queue._update_maintenance(claiming=True)
    updates.set_operation(tmp_path, "failed", "中断")
    receipt = updates.private_path(tmp_path, "synthetic/receipt.json")
    updates.write_json(receipt, {"status": "applying"})
    assert queue._update_maintenance(claiming=True)
    assert updates.maintenance(tmp_path)


def test_publishing_blocks_restart_but_future_schedule_is_preserved(tmp_path, monkeypatch):
    from backlot import work_publish
    expected = hashlib.sha256(str((tmp_path / "creatorhub").resolve()).replace("\\", "/").casefold().encode()).hexdigest()
    rows = [{"status": "pending", "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}]
    class Gateway:
        def tasks(self): return rows
        def call(self, path):
            return {"service_fingerprint": expected} if path == "/api/download-sessions" else []
    monkeypatch.setattr(work_publish, "CreatorGateway", Gateway)
    assert api.publisher_busy(tmp_path) == ""
    for status in ("publishing", "doing", "uncertain", "pending"):
        rows[:] = [{"status": status}]
        assert api.publisher_busy(tmp_path)
