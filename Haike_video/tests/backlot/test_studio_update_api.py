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


def test_historical_local_audio_is_ready_but_active_lock_blocks(tmp_path):
    import json
    from lib.bailian_speech import operation_lock
    identity = 'call_' + 'a' * 32
    folder = tmp_path / 'Haike_video/.backlot/audio-center-internal/local/operations' / identity
    folder.mkdir(parents=True)
    (folder / '.lock').write_bytes(b'0')
    (folder / 'operation.json').write_text(json.dumps({'id': identity, 'status': 'submission_unknown',
        'signature': 'a' * 64, 'quote_id': 'iq_' + 'a' * 32, 'maximum': 100,
        'request': {'kind': 'clone', 'credential_identity': 'synthetic'}}), encoding='utf-8')
    app = SimpleNamespace(state=SimpleNamespace())
    assert api.audio_busy(app, tmp_path) == ''
    with operation_lock(folder):
        assert '音色操作' in api.audio_busy(app, tmp_path)


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


def test_local_zip_upload_accepts_binary_but_retains_origin_and_type_guards(tmp_path, monkeypatch):
    web, app = client(tmp_path)
    monkeypatch.setattr(updates, 'capability', lambda *a: {'can_install':True})
    received=[]
    def imported(path):
        received.append(path.read_bytes())
        return {'update':{'status':'available','source':'local'}}
    monkeypatch.setattr(app.state.app_update_service, 'import_archive', imported)
    route='/api/studio/app-update/import'
    raw={'Origin':'http://127.0.0.1','Content-Type':'application/octet-stream'}
    assert web.post(route,content=b'zip',headers={**raw,'Origin':'https://other.test'}).status_code==403
    assert web.post(route,json={},headers={'Origin':'http://127.0.0.1'}).status_code==415
    response=web.post(route,content=b'zip',headers=raw)
    assert response.status_code==200 and received==[b'zip']


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


def test_update_waits_for_native_template_preparation(tmp_path, monkeypatch):
    from backlot import studio_motion_templates_api as motion
    web, app = client(tmp_path)
    identity = 'b'*24
    updates.set_operation(tmp_path, 'waiting', '等待', id=identity)
    updates.write_json(updates.private_path(tmp_path, identity+'/operation.json'), {'token':'test-token'})
    app.state.production_queue = SimpleNamespace(list=lambda **kw: {})
    monkeypatch.setattr(api, 'publisher_busy', lambda root: '')
    monkeypatch.setattr(motion, '_ACTIVE_PREPARATIONS', {'synthetic-motion-session'})
    response = web.get('/api/studio/app-update/readiness', headers={'X-Haike-Update-Token':'test-token'})
    assert response.status_code == 200
    assert response.json()['ready'] is False
    assert '动效模板' in response.json()['message']


def test_readiness_preserves_seven_held_results_but_blocks_a_real_worker(tmp_path, monkeypatch):
    import sqlite3
    from contextlib import closing
    web, app = client(tmp_path)
    identity = 'e' * 24
    updates.set_operation(tmp_path, 'waiting', '等待', id=identity)
    updates.write_json(updates.private_path(tmp_path, identity+'/operation.json'), {'token':'test-token'})
    path = tmp_path/'queue.sqlite3'
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE production_jobs(job_id TEXT,status TEXT,worker_id TEXT,lease_expires_at TEXT)')
        db.executemany('INSERT INTO production_jobs VALUES (?,?,?,?)', [(str(i),'ambiguous',None,None) for i in range(7)])
        db.commit()
    original = path.read_bytes()
    app.state.production_queue = SimpleNamespace(db_path=path, list=lambda **kw: {'waiting_count':7})
    monkeypatch.setattr(api, 'publisher_busy', lambda root: '')
    headers = {'X-Haike-Update-Token':'test-token'}
    result = web.get('/api/studio/app-update/readiness',headers=headers).json()
    assert result['ready'] and result['held_jobs_preserved']==7 and path.read_bytes()==original
    for status in ['paused', 'awaiting_human']:
        with closing(sqlite3.connect(path)) as db:
            db.execute('UPDATE production_jobs SET status=?', (status,)); db.commit()
        original = path.read_bytes()
        counts = {'paused_count': 7} if status == 'paused' else {'waiting_count': 7}
        app.state.production_queue.list = lambda **kw: counts
        result = web.get('/api/studio/app-update/readiness', headers=headers).json()
        assert result['ready'] and result['held_jobs_preserved'] == 7 and path.read_bytes() == original
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE production_jobs SET status='running',worker_id='worker' WHERE job_id='0'"); db.commit()
    assert not web.get('/api/studio/app-update/readiness',headers=headers).json()['ready']


def test_readiness_reports_all_independent_blockers_once(tmp_path, monkeypatch):
    web, app = client(tmp_path)
    identity = 'f' * 24
    updates.set_operation(tmp_path, 'waiting', '等待', id=identity)
    updates.write_json(updates.private_path(tmp_path, identity+'/operation.json'), {'token':'test-token'})
    app.state.production_queue = SimpleNamespace(list=lambda **kw: {})
    app.state.update_inflight = 1
    monkeypatch.setattr(api, 'audio_busy', lambda *args: '音色仍在执行')
    monkeypatch.setattr(api, 'publisher_busy', lambda *args: '发布仍在执行')
    result = web.get('/api/studio/app-update/readiness', headers={'X-Haike-Update-Token':'test-token'}).json()
    assert not result['ready'] and len(result['blockers']) == 3
    assert '音色仍在执行' in result['message'] and '发布仍在执行' in result['message']


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
