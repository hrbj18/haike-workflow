"""Offline contracts for the ledger; never submit media or publishing jobs."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot.automation_task_center import LocalSources, TaskCenter
from backlot.automation_task_center_api import router
from backlot.work_catalog import WorkError


@pytest.fixture
def center(tmp_path):
    return TaskCenter(tmp_path / "private/task-center.sqlite3", template_ids={"avatar-deepblue-n1-v1"})


def payload(client_id="first-n1", **patch):
    return {"client_id": client_id, "title": "科技新闻·深蓝视窗 N1", "stage": "核对新闻来源",
            "budget": {"limit_micros": 5_000_000}, **patch}


def test_result_projection_exposes_existing_media_copy_and_ids_without_private_paths(tmp_path):
    private = tmp_path / '.backlot';private.mkdir()
    with sqlite3.connect(private / 'works.sqlite3') as db:
        db.execute('CREATE TABLE works(id TEXT,data TEXT)')
        db.execute('INSERT INTO works VALUES(?,?)', ('work-test', json.dumps({
            'work_id': 'work-test', 'title': '科技新闻', 'final_version_id': 'v1',
            'materials': [{'version_id': 'v1', 'data': {'title': '发布标题', 'desc': '真实详情', 'topics': '科技', 'cover_path': 'C:/private/cover.jpg'}}],
            'attempts': [{'platform': 'douyin', 'account_id': 3, 'status': 'done', 'identity_verified': True,
                          'acceptance': {'work_id': '1234567890', 'unique_work': True, 'evidence_path': 'C:/private/proof.png'}}]})))
    center = TaskCenter(private / 'task-center.sqlite3', sources=LocalSources(tmp_path / 'projects'))
    row = center.create(payload(links={'work_id': 'work-test'}, facts={'snapshot': {'publishing': {'targets': [{'platform': 'douyin', 'account_id': 3}]}}}))
    detail = center.detail(row['id'])
    work = detail['sources']['work']
    assert work['result'] == {'video_url': '/api/works/work-test/media?version=v1', 'cover_url': '/api/works/work-test/cover?version=v1', 'title': '发布标题', 'desc': '真实详情', 'topics': '科技'}
    assert work['attempts'][0]['platform_work_id'] == '1234567890'
    assert work['attempts'][0]['work_url'] == 'https://www.douyin.com/video/1234567890'
    assert work['attempts'][0]['public_visible'] is None
    assert 'C:/private' not in json.dumps(detail)
    assert detail['expected_targets'] == [{'platform': 'douyin', 'account_id': 3}]
    assert center.summary()['changes'][0]['expected_targets'] == detail['expected_targets']


def test_create_is_durable_and_client_id_is_idempotent_not_overwritable(center):
    original = center.create(payload())
    reopened = TaskCenter(center.db_path)
    assert reopened.create(payload()) == original
    assert reopened.detail(original["id"])["title"] == "科技新闻·深蓝视窗 N1"
    with pytest.raises(WorkError, match="不同任务") as exc:
        reopened.create(payload(title="另一条新闻"))
    assert exc.value.code == "conflict"
    assert len(reopened.list()["items"]) == 1
    assert original["budget"] == {"currency": "CNY", "limit_micros": 5_000_000,
        "actual_micros": None, "reserved_micros": None, "estimated_micros": None}


def test_concurrent_same_client_and_revision_use_sqlite_atomicity(center):
    barrier = Barrier(2)

    def create():
        barrier.wait(timeout=5)
        return center.create(payload())

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: create(), range(2)))
    assert values[0]["id"] == values[1]["id"]
    original = values[0]
    barrier = Barrier(2)

    def update(index):
        barrier.wait(timeout=5)
        try:
            return center.update(original["id"], {"expected_revision": 1, "stage": f"阶段{index}"})
        except WorkError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, range(2)))
    assert sum(isinstance(item, dict) for item in results) == 1
    assert [item.code for item in results if isinstance(item, WorkError)] == ["conflict"]
    assert center.detail(original["id"])["revision"] == 2


def test_patch_budget_preserves_unknown_and_sub_cent_precision(center):
    task = center.create(payload())
    updated = center.update(task["id"], {"expected_revision": 1, "budget": {
        "actual_micros": 2160, "reserved_micros": 720000, "estimated_micros": 800000}})
    assert updated["budget"] == {"currency": "CNY", "limit_micros": 5000000,
        "actual_micros": 2160, "reserved_micros": 720000, "estimated_micros": 800000}
    for invalid in (False, -1, 0.00216, "0", 10**16):
        with pytest.raises(WorkError):
            center.update(task["id"], {"expected_revision": 2, "budget": {"actual_micros": invalid}})
    assert center.detail(task["id"])["revision"] == 2


@pytest.mark.parametrize("patch", [
    {"stage": "字幕已恢复🤖"}, {"status": "completed"}, {"summary": "原字幕阻碍已解除，成片待核验。"},
])
def test_patch_records_one_current_snapshot_for_each_progress_field(center, patch):
    task = center.create(payload(status="running", summary="原字幕任务等待恢复"))
    changed = center.update(task["id"], {"expected_revision": task["revision"], **patch})
    reopened = TaskCenter(center.db_path)
    events = reopened.events(task["id"])["items"]
    assert len(events) == 1
    event = events[0]
    assert event["kind"] == "stage" and event["stage"] == changed["stage"]
    assert event["message"] == changed["summary"]
    assert event["facts"] == {"status": changed["status"], "task_revision": changed["revision"],
                              "changed_fields": list(patch)}
    assert event["created_at"] == changed["updated_at"] == changed["last_progress_at"]
    assert reopened.detail(task["id"])["budget"]["actual_micros"] is None


def test_combined_patch_appends_one_snapshot_and_preserves_ascending_event_cursor(center):
    task = center.create(payload(status="running", stage="字幕受阻", summary="18:24旧字幕等待恢复"))
    old = center.append_event(task["id"], {"client_id": "old-block", "kind": "stage",
        "stage": "字幕受阻", "message": "18:24旧字幕等待恢复"})
    state = center.detail(task["id"])
    changed = center.update(task["id"], {"expected_revision": state["revision"], "stage": "制作完成",
        "status": "completed", "summary": "新成片已生成，平台结果分别核验。"})
    first = center.events(task["id"], limit=1)
    second = center.events(task["id"], cursor=first["next_cursor"], limit=1)
    assert first["items"] == [old] and first["has_more"] is True
    assert len(second["items"]) == 1 and second["has_more"] is False
    latest = second["items"][0]
    assert latest["id"] > old["id"] and latest["stage"] == changed["stage"]
    assert latest["message"] == changed["summary"]
    assert latest["facts"]["changed_fields"] == ["stage", "status", "summary"]
    assert [item["id"] for item in center.detail(task["id"])["events"]] == [old["id"], latest["id"]]


def test_noop_patch_and_heartbeat_do_not_create_progress_snapshots(center):
    task = center.create(payload(status="running", summary="等待实际产物"))
    cursor = center.summary()["next_cursor"]
    unchanged = center.update(task["id"], {"expected_revision": task["revision"],
        "stage": "  " + task["stage"] + "  ", "status": task["status"], "summary": task["summary"],
        "budget": {"actual_micros": None}})
    assert unchanged == task
    assert center.summary(cursor=cursor)["changes"] == []
    assert center.events(task["id"])["items"] == []
    beat = center.append_event(task["id"], {"client_id": "still-alive", "kind": "heartbeat", "message": "仍在响应"})
    current = center.detail(task["id"])
    assert current["last_progress_at"] == task["last_progress_at"]
    assert current["heartbeat_at"] == beat["created_at"]
    assert [item["kind"] for item in current["events"]] == ["heartbeat"]


def test_budget_only_change_does_not_fabricate_stage_or_settle_unknown_cost(center):
    task = center.create(payload(status="running"))
    reserved = center.update(task["id"], {"expected_revision": task["revision"],
        "budget": {"reserved_micros": 2531064}})
    assert center.events(task["id"])["items"] == []
    finished = center.update(task["id"], {"expected_revision": reserved["revision"], "status": "completed"})
    assert finished["budget"]["actual_micros"] is None
    assert finished["budget"]["reserved_micros"] == 2531064
    event = center.events(task["id"])["items"][0]
    assert event["message"] and event["facts"]["status"] == "completed"


def test_snapshot_insert_failure_rolls_back_task_revision_progress_and_change_cursor(center):
    task = center.create(payload(status="running"))
    cursor = center.summary()["next_cursor"]
    with center.connection(write=True) as db:
        db.execute("""CREATE TRIGGER reject_snapshot BEFORE INSERT ON task_center_events
            BEGIN SELECT RAISE(ABORT, 'isolated snapshot insert failure'); END""")
    with pytest.raises(WorkError) as exc:
        center.update(task["id"], {"expected_revision": task["revision"], "status": "completed",
                                  "stage": "制作完成", "summary": "不得提交一半更新"})
    assert exc.value.code == "unavailable"
    detail = center.detail(task["id"])
    for field in ("revision", "stage", "status", "summary", "updated_at", "last_progress_at", "budget"):
        assert detail[field] == task[field]
    assert detail["events"] == [] and center.summary(cursor=cursor)["changes"] == []


def test_summary_incremental_cursor_compacts_changes_without_losing_updates(center):
    first = center.create(payload("one"))
    second = center.create(payload("two"))
    page = center.summary(limit=1)
    assert [item["id"] for item in page["changes"]] == [first["id"]]
    assert page["has_more"] is True
    page2 = center.summary(cursor=page["next_cursor"], limit=1)
    assert [item["id"] for item in page2["changes"]] == [second["id"]]
    assert page2["has_more"] is False
    for revision in range(1, 4):
        center.update(first["id"], {"expected_revision": revision, "summary": f"进展{revision}"})
    changed = center.summary(cursor=page2["next_cursor"])
    assert len(changed["changes"]) == 1
    assert changed["changes"][0]["summary"] == "进展3"
    assert "events" not in changed["changes"][0] and "facts" not in changed["changes"][0]
    empty = center.summary(cursor=changed["next_cursor"])
    assert empty["changes"] == [] and empty["next_cursor"] == changed["next_cursor"]
    assert empty["worker_available"] is False


def test_event_idempotency_pagination_and_heartbeat_are_distinct_from_progress(center):
    task = center.create(payload())
    beat = {"client_id": "beat-1", "kind": "heartbeat", "message": "控制窗口仍在运行"}
    first = center.append_event(task["id"], beat)
    assert center.append_event(task["id"], beat) == first
    state = center.detail(task["id"])
    assert state["last_progress_at"] == task["last_progress_at"]
    assert state["heartbeat_at"] == first["created_at"]
    with pytest.raises(WorkError) as exc:
        center.append_event(task["id"], {**beat, "message": "不同事件"})
    assert exc.value.code == "conflict"
    for index in range(3):
        center.append_event(task["id"], {"client_id": f"stage-{index}", "kind": "stage", "stage": "资料核实", "message": f"完成核实{index}"})
    one = center.events(task["id"], limit=2)
    two = center.events(task["id"], cursor=one["next_cursor"], limit=2)
    assert one["has_more"] and not two["has_more"]
    assert [event["id"] for event in one["items"] + two["items"]] == [1, 2, 3, 4]
    assert center.detail(task["id"])["last_progress_at"] > task["last_progress_at"]
    assert center.detail(task["id"])["stage"] == task["stage"]  # Events never silently rewrite the reported task.
    for cursor, limit in ((-1, 50), (0, 0), (0, 201)):
        with pytest.raises(WorkError):
            center.events(task["id"], cursor=cursor, limit=limit)


def test_long_history_detail_is_bounded_and_older_events_remain_reachable(center):
    task = center.create(payload())
    for index in range(53):
        center.append_event(task["id"], {"client_id": f"note-{index}", "kind": "note", "message": str(index)})
    detail = center.detail(task["id"])
    assert len(detail["events"]) == 50 and detail["events_has_more"] is True
    assert detail["events"][0]["message"] == "3"
    assert center.events(task["id"], limit=1)["items"][0]["message"] == "0"


def test_report_and_pause_commands_are_durable_requests_not_execution(center):
    task = center.create(payload(status="running"))
    request = {"client_id": "pause-1", "kind": "pause_requested"}
    command = center.request_command(task["id"], request)
    assert center.request_command(task["id"], request) == command
    assert command["status"] == "requested" and command["acknowledged_at"] is None
    assert center.detail(task["id"])["status"] == "running"
    assert center.summary()["pending_commands_count"] == 1
    assert center.commands()["items"] == [command]
    ack = {"status": "acknowledged", "result": "已收到暂停请求，底层正在结束当前步骤，尚未暂停"}
    receipt = center.acknowledge(command["id"], ack)
    assert receipt["status"] == "acknowledged" and receipt["acknowledged_at"]
    assert center.acknowledge(command["id"], ack) == receipt
    assert center.detail(task["id"])["status"] == "running"
    assert center.summary()["pending_commands_count"] == 0
    with pytest.raises(WorkError) as exc:
        center.acknowledge(command["id"], {"status": "rejected", "result": "不能覆盖原应答"})
    assert exc.value.code == "conflict"
    with pytest.raises(WorkError):
        center.request_command(task["id"], {"client_id": "paid-1", "kind": "publish_now"})


def test_secrets_paths_signed_urls_never_enter_ledger_or_responses(center):
    secret = "hk_" + "sensitive_credential_" * 2
    password = "private-password-123"
    task = center.create(payload(summary=f"错误 Bearer {secret}", facts={
        "api_key": secret, "nested": {"cookie": "private-cookie", "password": password},
        "raw": secret, "local_file": r"C:\Users\private\secret.wav",
        "error_detail": "请求 https://user:password@example.com/api?signature=private-signed 失败"}, evidence=[{
        "label": "来源", "ref": "https://user:password@example.com/news?signature=private-signed#fragment", "kind": "source"}]))
    center.append_event(task["id"], {"client_id": "event-1", "kind": "report", "message": secret, "facts": {"authorization": secret}})
    command = center.request_command(task["id"], {"client_id": "report-1", "kind": "report_now"})
    center.acknowledge(command["id"], {"status": "acknowledged", "result": f"Cookie: private-cookie; {secret}"})
    raw = center.db_path.read_bytes()
    output = json.dumps(center.detail(task["id"]), ensure_ascii=False)
    for sensitive in (secret, password, "private-cookie", r"C:\Users\private", "private-signed", "user:password"):
        assert sensitive.encode() not in raw
        assert sensitive not in output
    detail = center.detail(task["id"])
    assert detail["facts"]["nested"] == {}
    assert detail["evidence"][0]["ref"] == "https://example.com/news"
    with pytest.raises(WorkError):
        center.create(payload(secret))
    with pytest.raises(WorkError):
        center.create(payload("large", facts={"text": "x" * 12001}))


def test_sources_are_read_only_authoritative_receipts_and_not_public_visibility(tmp_path):
    projects = tmp_path / "projects"
    private = tmp_path / ".backlot"
    private.mkdir()
    queue_path = private / "production-queue.sqlite3"
    works_path = private / "works.sqlite3"
    # Exact source fields needed by the projection, without starting a worker.
    with sqlite3.connect(queue_path) as db:
        db.execute("CREATE TABLE production_jobs(job_id TEXT,project_id TEXT,status TEXT,stage TEXT,revision INTEGER,updated_at TEXT,started_at TEXT,finished_at TEXT,result_json TEXT,error_json TEXT,retryable INTEGER,safe_resume_point TEXT)")
        db.execute("INSERT INTO production_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("PQ-test", "project-test", "running", "真实配音阶段", 2, "2026-10-16T01:00:00Z", None, None, '{"work_id":"work-test"}', '{}', 0, None))
    with sqlite3.connect(works_path) as db:
        db.execute("CREATE TABLE works(id TEXT,data TEXT)")
        db.execute("INSERT INTO works VALUES(?,?)", ("work-test", json.dumps({"work_id": "work-test", "title": "真实作品", "revision": 1, "final_version_id": "v1", "attempts": [
            {"platform": "douyin", "account_id": 3, "task_id": 31, "status": "done", "acceptance_status": "verified", "identity_verified": True},
            {"platform": "kuaishou", "account_id": 2, "status": "uncertain", "error": "等待原提交核对"},
            {"platform": "shipinhao", "account_id": 1, "status": "failed", "error": "需要重新登录"}]})))
    center = TaskCenter(private / "task-center.sqlite3", sources=LocalSources(projects))
    task = center.create(payload(links={"queue_job_id": "PQ-test"}, status="planned"))
    detail = center.detail(task["id"])
    assert detail["status"] == "planned" and detail["status_source"] == "reported"
    assert detail["sources"]["queue"]["status"] == "running"
    assert detail["sources"]["queue"]["stage"] == "真实配音阶段"
    attempts = detail["sources"]["work"]["attempts"]
    assert [attempt["status"] for attempt in attempts] == ["done", "uncertain", "failed"]
    assert all(attempt["public_visible"] is None for attempt in attempts)
    assert attempts[0]["acceptance_status"] == "verified"
    before = center.summary()["next_cursor"]
    queue_bytes, work_bytes = queue_path.read_bytes(), works_path.read_bytes()
    assert center.summary(cursor=before)["changes"] == []
    assert queue_path.read_bytes() == queue_bytes and works_path.read_bytes() == work_bytes
    with sqlite3.connect(queue_path) as db:
        db.execute("UPDATE production_jobs SET status='failed',stage='本地真实错误',revision=3")
    changes = center.summary(cursor=before)["changes"]
    assert len(changes) == 1 and changes[0]["sources"]["queue"]["status"] == "failed"
    assert changes[0]["revision"] == task["revision"]  # Projection does not spuriously invalidate reporter CAS.
    with sqlite3.connect(queue_path) as db:
        db.execute("UPDATE production_jobs SET result_json='invalid json'")
    assert center.detail(task["id"])["sources"]["queue"]["availability"] == "unavailable"


def test_missing_sources_do_not_create_any_production_database(tmp_path):
    private = tmp_path / ".backlot"
    center = TaskCenter(private / "task-center.sqlite3", sources=LocalSources(tmp_path / "projects"))
    task = center.create(payload(links={"queue_job_id": "PQ-missing", "work_id": "work-missing", "calendar_id": "calendar-missing"}))
    sources = center.detail(task["id"])["sources"]
    assert all(value["availability"] == "missing" for value in sources.values())
    assert sorted(path.name for path in private.iterdir()) == ["task-center.sqlite3"]


def plan_payload(**patch):
    return {"expected_revision": 0, "enabled": False, "timezone": "Asia/Shanghai", "start_time": "02:00", "slots": [
        {"template_id": "avatar-deepblue-n1-v1", "accounts": [], "budget_limit_micros": 5000000, "topic": "最新科技新闻"}], **patch}


def test_daily_plan_is_cas_configuration_only_and_cannot_enable_executor(center):
    assert center.plan()["enabled"] is False and center.plan()["worker_available"] is False
    plan = center.save_plan(plan_payload())
    assert plan["revision"] == 1 and plan["slots"][0]["accounts"] == []
    assert TaskCenter(center.db_path).plan() == plan
    with pytest.raises(WorkError) as exc:
        center.save_plan(plan_payload())
    assert exc.value.code == "conflict"
    with pytest.raises(WorkError, match="尚未接入"):
        center.save_plan(plan_payload(expected_revision=1, enabled=True))
    assert center.plan() == plan
    for patch in ({"timezone": "UTC"}, {"start_time": "25:00"}, {"slots": [{"template_id": "unknown"}]}):
        with pytest.raises(WorkError):
            center.save_plan(plan_payload(expected_revision=1, **patch))


@pytest.fixture
def app(center):
    app = FastAPI()
    app.state.task_center = center
    app.include_router(router)
    return app


def client(app, *, host="127.0.0.1", peer="127.0.0.1"):
    return TestClient(app, base_url=f"http://{host}", client=(peer, 54321))


def test_api_roundtrip_exposes_safe_durable_detail_events_and_commands(app):
    with client(app) as c:
        created = c.post("/api/task-center/tasks", json=payload())
        assert created.status_code == 200
        task = created.json()
        assert c.get("/api/task-center/summary").headers["cache-control"] == "private, no-store"
        assert c.patch(f"/api/task-center/tasks/{task['id']}", json={"expected_revision": 1, "status": "running"}).status_code == 200
        assert c.patch(f"/api/task-center/tasks/{task['id']}", json={"expected_revision": 1, "status": "completed"}).status_code == 409
        event = c.post(f"/api/task-center/tasks/{task['id']}/events", json={"client_id": "report-1", "kind": "report", "message": "本地准备完毕"})
        assert event.status_code == 200
        command = c.post(f"/api/task-center/tasks/{task['id']}/commands", json={"client_id": "cmd-1", "kind": "report_now"}).json()
        assert c.get("/api/task-center/commands").json()["items"] == [command]
        ack = c.post(f"/api/task-center/commands/{command['id']}/ack", json={"status": "acknowledged", "result": "真实已完成准备，未提交任何生成服务"})
        assert ack.status_code == 200 and ack.json()["status"] == "acknowledged"
        detail = c.get(f"/api/task-center/tasks/{task['id']}").json()
        assert [item["kind"] for item in detail["events"]] == ["stage", "report"]
        assert detail["events"][0]["facts"]["status"] == "running"
        assert detail["events"][1]["message"] == "本地准备完毕"
        assert detail["commands"][0]["status"] == "acknowledged"
        assert c.get("/api/task-center/tasks/absent").status_code == 404
        assert c.get("/api/task-center/summary?limit=201").status_code == 422
        assert c.put("/api/task-center/plan", json=plan_payload()).status_code == 200


@pytest.mark.parametrize("host,peer,origin", [
    ("evil.example", "127.0.0.1", None), ("127.0.0.1", "192.168.1.10", None),
    ("127.0.0.1", "127.0.0.1", "https://evil.example"), ("127.0.0.1", "127.0.0.1", "null"),
])
def test_api_rejects_remote_peer_dns_rebinding_and_cross_origin_without_touching_ledger(app, monkeypatch, host, peer, origin):
    def no_handler(*args, **kwargs):
        pytest.fail("private API handler ran before local access control")
    monkeypatch.setattr("backlot.automation_task_center_api.center", no_handler)
    headers = {"Origin": origin} if origin else {}
    with client(app, host=host, peer=peer) as c:
        assert c.get("/api/task-center/summary", headers=headers).status_code == 403
        assert c.post("/api/task-center/tasks", json=payload(), headers=headers).status_code == 403


def test_api_accepts_same_origin_loopback_and_requires_json(app):
    with client(app) as c:
        assert c.post("/api/task-center/tasks", json=payload(), headers={"Origin": "http://127.0.0.1"}).status_code == 200
        assert c.post("/api/task-center/tasks", content=json.dumps(payload("two")), headers={"Content-Type": "text/plain"}).status_code == 415
        assert c.get("/api/task-center/summary", headers={"X-Forwarded-For": "192.168.1.10"}).status_code == 200
