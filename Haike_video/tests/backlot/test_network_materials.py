"""Network materials: durable local HTTP jobs with fake account/download services."""
import asyncio
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backlot import network_materials as network
from backlot.studio import atomic_private

_REAL_RUN_JOB = network.run_job


def account(**patch):
    return {"id": 7, "platform": "douyin", "name": "测试账号",
            "download_status": "ready", "publish_status": "active",
            "saved_at": "2026-10-16T00:00:00Z", "last_checked_at": "2026-10-16T00:01:00Z",
            **patch}


def body(**patch):
    return {"client_request_id": str(uuid4()), "url": "https://v.douyin.com/fixture/",
            "account_id": 7, "quality": "highest", "rights_confirmed": True, **patch}


@pytest.fixture
def fixture_service(tmp_path, monkeypatch):
    service = SimpleNamespace(private=tmp_path / "private")
    calls, scheduled = [], []

    def fake_creator(path, data=None, **_kwargs):
        calls.append((path, data))
        if path in {"/api/download-sessions", "/api/accounts"}:
            rows = [account()]
            return {"items": rows, "available": True} if path.endswith("sessions") else rows
        if path.startswith("/api/download-sessions/7/"):
            return {"ok": True, "account": account()}
        if path == "/api/download-sessions/login":
            return {"task_id": "a" * 32, "status": "waiting"}
        if path == "/api/download-sessions/login/" + "a" * 32:
            return {"status": "done"}
        raise AssertionError("unexpected fixture endpoint: " + path)

    async def queued(_service, job):
        scheduled.append(job["id"])

    monkeypatch.setattr(network, "creator_call", fake_creator)
    monkeypatch.setattr(network, "run_job", queued)
    app = FastAPI()
    app.state.studio = service
    app.include_router(network.router)
    with TestClient(app) as client:
        yield SimpleNamespace(service=service, client=client, calls=calls, scheduled=scheduled,
                              fake_creator=fake_creator)


def frozen(service, **patch):
    payload = network.input_request(body())
    value = {"id": str(uuid4()), "status": "queued", "message": "排队中",
             "instance": network._INSTANCE, "input": payload,
             "fingerprint": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
             "created_at": "2026-10-16T00:00:00Z", "updated_at": "2026-10-16T00:00:00Z", **patch}
    atomic_private(network.job_path(service, value["id"]), value)
    return value


def test_sessions_separate_download_and_publish_and_never_return_credentials(fixture_service, monkeypatch):
    row = account(cookie="SECRET_COOKIE", storage_state="SECRET_STATE", profile_dir="PRIVATE_PATH")
    monkeypatch.setattr(network, "creator_call", lambda *_args, **_kwargs: {"items": [row], "available": True})
    response = fixture_service.client.get("/api/studio/download-sessions")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["download_status"] == "available"
    assert item["publish_status"] == "unconfirmed", "DB active snapshot is not a current publish proof"
    assert all(secret not in response.text for secret in ("SECRET_COOKIE", "SECRET_STATE", "PRIVATE_PATH"))
    assert network.session_view(account(publish_verified=True))["publish_status"] == "available"
    assert network.session_view(account(download_status="future_unknown"))["download_status"] == "unconfirmed"


@pytest.fixture
def search_clock(monkeypatch):
    now = datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is not None else now.replace(tzinfo=None)

    monkeypatch.setattr(network, "datetime", Clock)
    return now


@pytest.mark.parametrize("raw,expected", [("network_error", "network_error"),
    ("login_required", "login_required"), ("unconfirmed", "unconfirmed"),
    ("active", "unconfirmed")])
def test_publish_check_negative_evidence_is_visible_without_faking_verified(raw, expected):
    checked = "2026-10-17T03:24:00Z"
    value = network.session_view(account(publish_status=raw, publish_verified=False,
                                         publish_checked_at=checked))
    assert value["publish_status"] == expected
    assert value["publish_checked_at"] == checked


@pytest.mark.parametrize("age,status", [(0, "available"), (300, "available"),
    (301, "available"), (28800, "available"), (28801, "unconfirmed"),
    (86400, "unconfirmed"), (-1, "unconfirmed")])
def test_search_login_requires_recent_evidence_without_changing_other_scopes(search_clock, age, status):
    checked = (search_clock - timedelta(seconds=age)).isoformat().replace("+00:00", "Z")
    value = network.session_view(account(last_checked_at=checked, selected=True,
        publish_verified=True, publish_checked_at=checked, login_record_saved=True))
    assert value["search_supported"] is True
    assert value["search_status"] == status
    assert value["search_checked_at"] == checked
    assert value["selected"] is True
    assert value["download_status"] == "available"
    assert value["publish_status"] == "available"
    assert value["publish_checked_at"] == checked
    assert value["login_record_saved"] is True


def test_persisted_scope_history_is_display_only_and_does_not_approve_execution(search_clock):
    checked = (search_clock - timedelta(hours=7)).isoformat()
    value = network.session_view(account(download_status="stored_unverified",
        publish_status="unconfirmed", publish_verified=False,
        download_check_status="ready", download_checked_at=checked,
        publish_check_status="ready", publish_checked_at=checked))
    assert value["download_check_status"] == "available"
    assert value["publish_check_status"] == "available"
    assert value["search_status"] == "available"
    assert value["download_checked_at"] == value["search_checked_at"] == checked.replace("+00:00", "Z")
    assert value["publish_checked_at"] == checked.replace("+00:00", "Z")
    assert value["download_status"] == value["publish_status"] == "unconfirmed"


@pytest.mark.parametrize("scope", ["download", "publish"])
@pytest.mark.parametrize("raw,expected", [("ready", "available"),
    ("login_required", "login_required"), ("network_error", "network_error"),
    ("unconfirmed", "unconfirmed"), ("future_unknown", "unconfirmed"),
    ({}, "unconfirmed"), ([], "unconfirmed")])
def test_scope_history_keeps_known_failures_and_sanitizes_unknown_results(scope, raw, expected):
    value = network.session_view(account(**{f"{scope}_check_status": raw,
        f"{scope}_checked_at": "2026-10-17T03:00:00Z"}))
    assert value[f"{scope}_check_status"] == expected


def test_stored_publishing_snapshot_is_not_a_fabricated_history():
    value = network.session_view(account(publish_verified=False))
    assert value["publish_check_status"] == "unconfirmed"
    assert value["publish_checked_at"] is None


@pytest.mark.parametrize("checked", [None, "not-a-date", 0, {}])
def test_search_ready_without_readable_time_needs_check(search_clock, checked):
    value = network.session_view(account(last_checked_at=checked))
    assert value["search_status"] == "unconfirmed"
    assert value["search_checked_at"] is None


@pytest.mark.parametrize("raw,status", [("not_saved", "login_required"),
    ("login_required", "login_required"), ("network_error", "network_error"),
    ("unconfirmed", "unconfirmed"), ("stored_unverified", "unconfirmed"),
    ("profile_changed", "unconfirmed"), ("future_unknown", "unknown"),
    (None, "unknown"), ({}, "unknown")])
def test_search_unknown_or_network_failure_never_becomes_logged_out(raw, status):
    value = network.session_view(account(download_status=raw))
    assert value["search_supported"] is True
    assert value["search_status"] == status


@pytest.mark.parametrize("platform", ["kuaishou", "shipinhao", "xhs", "unknown"])
def test_other_platform_sessions_cannot_unlock_keyword_search(search_clock, platform):
    value = network.session_view(account(platform=platform,
        last_checked_at=search_clock.isoformat(), publish_verified=True, selected=True))
    assert value["search_supported"] is False
    assert value["search_status"] == "unsupported"
    assert value["search_checked_at"] is None
    assert value["download_status"] == value["publish_status"] == "available"


def test_sessions_only_read_metadata_and_preserve_selection(fixture_service, monkeypatch, search_clock):
    calls = []

    def creator(path, data=None, **_kwargs):
        calls.append((path, data))
        return {"available": True, "items": [account(selected=True,
            last_checked_at=search_clock.isoformat(), cookies="SECRET_COOKIE")]}

    monkeypatch.setattr(network, "creator_call", creator)
    response = fixture_service.client.get("/api/studio/download-sessions")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["search_status"] == "available" and item["selected"] is True
    assert "SECRET" not in response.text
    assert calls == [("/api/download-sessions", None)], "reading status must never probe an account"


@pytest.mark.parametrize("payload", [None, [], {}, {"items": None},
    {"items": [None], "available": True}, {"items": [{}], "available": True},
    {"items": [{"id": True}], "available": True}])
def test_unreadable_session_list_reports_unknown(fixture_service, monkeypatch, payload):
    monkeypatch.setattr(network, "creator_call", lambda *_args, **_kwargs: payload)
    response = fixture_service.client.get("/api/studio/download-sessions")
    assert response.status_code == 200
    assert response.json() == {"items": [], "available": False, "status": "unknown"}


def test_sessions_project_only_safe_maintenance_receipts_and_keep_login_required_distinct(fixture_service, monkeypatch):
    row = account(publish_status="login_required", login_record_saved=True, download_saved=True,
        publish_saved=True, observability={"checkpoint_at":"2026-10-16T02:00:00Z",
            "background_health_checked_at":"2026-10-16T03:00:00Z", "background_health_outcome":"verified",
            "account_last_active_at":"2026-10-16T03:00:00Z", "profile":"SECRET_PROFILE_HASH", "cookie":"SECRET_COOKIE",
            "keepalive":{"configured":True,"engine_running":True,"mode":"keepalive","idle_hours":6,
                "check_interval_seconds":1800,"jitter_ratio":.15,"next_eligible_at":"2026-10-16T09:00:00Z",
                "schedule_status":"waiting", "proxy":"SECRET_PROXY"}})
    monkeypatch.setattr(network, "creator_call", lambda *_args, **_kwargs: {"items":[row], "available":True})
    response = fixture_service.client.get("/api/studio/download-sessions")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["publish_status"] == "login_required"
    assert item["login_record_saved"] is True
    assert item["observability"]["checkpoint_at"] == "2026-10-16T02:00:00Z"
    assert item["observability"]["keepalive"]["check_interval_seconds"] == 1800
    assert item["observability"]["keepalive"]["next_eligible_at"] == "2026-10-16T09:00:00Z"
    assert "SECRET" not in response.text
    malformed = network.session_view(account(observability={"checkpoint_at":"SECRET_INVALID_DATE",
        "background_health_outcome":{}, "keepalive":{"mode":[],"idle_hours":True,"next_eligible_at":"SECRET_PATH"}}))
    assert malformed["observability"]["checkpoint_at"] is None
    assert malformed["observability"]["keepalive"]["idle_hours"] is None
    assert "SECRET" not in json.dumps(malformed)


@pytest.mark.parametrize("action", ["check", "open-login", "select"])
def test_account_actions_use_local_bridge_and_project_safe_record(fixture_service, action):
    response = fixture_service.client.post(f"/api/studio/download-sessions/7/{action}", json={})
    assert response.status_code == 200
    assert response.json()["account"]["download_status"] == "available"
    assert fixture_service.calls[-1] == (f"/api/download-sessions/7/{action}", {})


def test_existing_account_login_keeps_preview_task_and_scrubs_private_record(fixture_service, monkeypatch):
    def fake_creator(path, data=None, **_kwargs):
        assert path == "/api/download-sessions/7/open-login"
        return {"ok": True, "account": account(cookies="SECRET_COOKIE"),
                "task_id": "b" * 32, "status": "waiting",
                "preview_url": "/api/download-sessions/login/" + "b" * 32 + "/preview.png",
                "storage_state": "SECRET_STATE"}
    monkeypatch.setattr(network, "creator_call", fake_creator)
    response = fixture_service.client.post("/api/studio/download-sessions/7/open-login", json={})
    assert response.status_code == 200
    result = response.json()
    assert result["task_id"] == "b" * 32 and result["status"] == "waiting"
    assert result["preview_url"] == "/api/studio/download-sessions/login/" + "b" * 32 + "/preview.png"
    assert "SECRET" not in response.text and "storage_state" not in result


def test_login_only_accepts_platform_and_returns_recoverable_task(fixture_service):
    client = fixture_service.client
    response = client.post("/api/studio/download-sessions/login", json={"platform": "kuaishou"})
    assert response.json() == {"task_id": "a" * 32, "status": "waiting"}
    assert client.get("/api/studio/download-sessions/login/" + "a" * 32).json()["status"] == "done"
    count = len(fixture_service.calls)
    for request in ({"platform": "other"}, {"platform": "douyin", "cookie": "SECRET"}):
        response = client.post("/api/studio/download-sessions/login", json=request)
        assert response.status_code == 422 and "SECRET" not in response.text
    assert client.get("/api/studio/download-sessions/login/../secret").status_code in {404, 422}
    assert len(fixture_service.calls) == count


def test_uuid_submission_is_private_durable_and_idempotent(fixture_service):
    client, request = fixture_service.client, body()
    response = client.post("/api/studio/network-download", json=request)
    assert response.status_code == 200
    first = response.json()
    assert first["id"] == request["client_request_id"]
    persisted = json.loads(network.job_path(fixture_service.service, first["id"]).read_text(encoding="utf-8"))
    assert persisted["input"]["account_id"] == 7
    for _ in range(2):
        assert client.post("/api/studio/network-download", json=request).json()["id"] == first["id"]
    assert fixture_service.scheduled == [first["id"]]
    assert set(first).isdisjoint({"input", "fingerprint", "instance"})
    conflicting = client.post("/api/studio/network-download", json={**request, "quality": "720p"})
    assert conflicting.status_code == 409
    assert fixture_service.scheduled == [first["id"]]


@pytest.mark.parametrize("patch", [
    {"rights_confirmed": False}, {"account_id": True}, {"quality": "4k"},
    {"url": "file:///C:/Cookies"}, {"url": "https://user:SECRET@v.douyin.com/video"},
    {"client_request_id": "../../SECRET"}, {"api_key": "SECRET"},
])
def test_bad_inputs_rejected_without_forwarding_secrets(fixture_service, patch):
    response = fixture_service.client.post("/api/studio/network-download", json=body(**patch))
    assert response.status_code == 422
    assert "SECRET" not in response.text
    assert not fixture_service.scheduled


def test_cross_origin_cannot_mutate_accounts_or_downloads(fixture_service):
    response = fixture_service.client.post("/api/studio/network-download", json=body(),
                                           headers={"Origin": "https://other.example"})
    assert response.status_code == 403
    assert not fixture_service.scheduled and not fixture_service.calls


def test_learning_purpose_stays_explicit_and_does_not_claim_general_usage_rights(tmp_path, monkeypatch):
    service = SimpleNamespace(private=tmp_path / "private")
    payload = network.input_request(body(usage_purpose="local_learning_test"))
    job = {**frozen(service), "input": payload}
    folder = network.job_path(service, job["id"]).parent / "media"
    folder.mkdir(parents=True)
    media = folder / "study.mp4"
    media.write_bytes(b"fixture video")
    captured = []
    def register(path, metadata):
        captured.append(metadata)
        return {"media_ids": ["fixture-study"]}
    monkeypatch.setattr(network.library, "register_file", register)
    network.register_result(service, job, {"results": [{"ok": True, "input_platform": "douyin",
        "files": [{"role": "media", "path": str(media)}], "metadata": {"id": "video"}}]})
    assert captured[0]["rights_status"] == "local_learning_only"
    with pytest.raises(HTTPException):
        network.input_request(body(usage_purpose="commercial_authorized"))


def test_async_worker_registers_only_scoped_media_with_provenance(tmp_path, monkeypatch):
    service = SimpleNamespace(private=tmp_path / "private")
    job, calls, registered = frozen(service), [], []

    def creator(path, request=None, **_kwargs):
        calls.append((path, request))
        if path == "/api/download-sessions":
            return {"items": [account()], "available": True}
        assert path == "/api/share-download"
        output = Path(request["output_dir"])
        output.mkdir(parents=True)
        media, thumb = output / "video.mp4", output / "thumb.jpg"
        media.write_bytes(b"fixture video")
        thumb.write_bytes(b"fixture thumbnail")
        return {"ok": True, "results": [{"ok": True, "input_platform": "douyin",
                 "files": [{"path": str(media), "role": "media"}, {"path": str(thumb), "role": "thumbnail"}],
                 "metadata": {"id": "fixture-video", "title": "合法测试素材"}}]}

    def register(path, metadata):
        registered.append((path, metadata))
        return {"media_ids": ["MAT-fixture"], "registered": 1}

    monkeypatch.setattr(network, "creator_call", creator)
    monkeypatch.setattr(network.library, "register_file", register)
    asyncio.run(network.run_job(service, job))
    result = network.read_job(service, job["id"])
    assert result["status"] == "completed"
    assert result["result"] == {"media_count": 1, "items": [{"id": "MAT-fixture", "title": "合法测试素材"}]}
    shares = [request for path, request in calls if path == "/api/share-download"]
    assert len(shares) == 1
    assert shares[0]["account_id"] == 7 and shares[0]["share_text"] == job["input"]["url"]
    assert len(registered) == 1
    assert registered[0][0].is_relative_to(network.job_path(service, job["id"]).parent / "media")
    assert registered[0][1]["rights_status"] == "confirmed"
    assert registered[0][1]["source_url"] == job["input"]["url"]


@pytest.mark.parametrize("bad_position", ["first", "last"])
def test_whole_result_paths_validated_before_any_registry_write(tmp_path, monkeypatch, bad_position):
    service = SimpleNamespace(private=tmp_path / "private")
    job, registered = frozen(service), []
    output = network.job_path(service, job["id"]).parent / "media"
    output.mkdir()
    good, bad = output / "good.mp4", tmp_path / "outside.mp4"
    good.write_bytes(b"fixture")
    bad.write_bytes(b"fixture")
    files = [{"path": str(path), "role": "media"} for path in ([bad, good] if bad_position == "first" else [good, bad])]
    monkeypatch.setattr(network.library, "register_file", lambda *args: registered.append(args) or {"media_ids": ["MAT-good"]})
    with pytest.raises(HTTPException, match="下载文件位置不符"):
        network.register_result(service, job, {"ok": True, "results": [{"ok": True, "files": files}]})
    assert not registered, "an invalid batch must not leave partial library registrations"


@pytest.mark.parametrize("status", ["queued", "running"])
def test_restart_preserves_original_id_and_does_not_resubmit_unknown(fixture_service, status):
    service, client = fixture_service.service, fixture_service.client
    job = frozen(service, status=status, instance="previous-process")
    result = client.get("/api/studio/network-download/" + job["id"])
    assert result.status_code == 200
    assert result.json()["id"] == job["id"] and result.json()["status"] == "submission_unknown"
    replay = {**job["input"], "client_request_id": job["id"]}
    assert client.post("/api/studio/network-download", json=replay).json()["status"] == "submission_unknown"
    assert not fixture_service.scheduled
    assert client.get("/api/studio/network-download/" + str(uuid4())).status_code == 404


def test_interruption_records_unknown_in_original_job(tmp_path, monkeypatch):
    service = SimpleNamespace(private=tmp_path / "private")
    job = frozen(service)

    def cancelled(*_args, **_kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(network, "creator_call", cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(network.run_job(service, job))
    assert network.read_job(service, job["id"])["status"] == "submission_unknown"


@pytest.mark.parametrize("exc", [ValueError("cookie=SECRET_COOKIE; api_key=SECRET_API"), RuntimeError("SECRET_INTERNAL")])
def test_worker_exception_is_safe_in_public_and_private_job(tmp_path, monkeypatch, exc):
    service = SimpleNamespace(private=tmp_path / "private")
    job = frozen(service)

    def broken(*_args, **_kwargs):
        raise exc

    monkeypatch.setattr(network, "creator_call", broken)
    asyncio.run(network.run_job(service, job))
    saved = network.read_job(service, job["id"])
    assert saved["status"] == "failed"
    assert "SECRET" not in json.dumps(saved)
    assert "SECRET" not in json.dumps(network.public_job(saved))


@pytest.mark.parametrize("url", ["https://v.kuaishou.com/fixture/", "https://douyin.com.example.org/video/123", "http://127.0.0.1/private"])
def test_server_rejects_wrong_platform_or_untrusted_url_before_download(fixture_service, monkeypatch, url):
    # Parent preflight is allowed to reject before queuing; any accepted job must
    # still reject before handing the selected account to /share-download.
    response = fixture_service.client.post("/api/studio/network-download", json=body(url=url))
    if response.status_code < 400:
        persisted = network.read_job(fixture_service.service, response.json()["id"])
        asyncio.run(_REAL_RUN_JOB(fixture_service.service, persisted))
        persisted = network.read_job(fixture_service.service, persisted["id"])
        assert persisted["status"] in {"failed", "login_required"}, "server must reject account/platform mismatch before acquisition"
    else:
        assert response.status_code in {400, 401, 403, 409, 422}
    assert not any(path == "/api/share-download" for path, _ in fixture_service.calls)


@pytest.mark.parametrize("scope", ["unconfirmed", "invalid", "network_error"])
def test_server_rechecks_scope_instead_of_trusting_frontend(fixture_service, monkeypatch, scope):
    calls = []

    def creator(path, data=None, **_kwargs):
        calls.append(path)
        if path == "/api/download-sessions":
            return {"items": [account(download_status=scope)], "available": True}
        if path == "/api/accounts":
            return [account(download_status=scope)]
        if path == "/api/download-sessions/7/check":
            return {"ok": False, "account": account(download_status=scope)}
        raise AssertionError("must not acquire with unverified session")

    monkeypatch.setattr(network, "creator_call", creator)
    response = fixture_service.client.post("/api/studio/network-download", json=body())
    if response.status_code < 400:
        persisted = network.read_job(fixture_service.service, response.json()["id"])
        asyncio.run(_REAL_RUN_JOB(fixture_service.service, persisted))
        assert network.read_job(fixture_service.service, persisted["id"])["status"] != "completed"
    else:
        assert response.status_code in {400, 401, 403, 409, 422, 503}
    assert "/api/share-download" not in calls


@pytest.mark.parametrize("exception", [
    HTTPError("http://127.0.0.1/test", 401, "fixture", {}, io.BytesIO(b'{"detail":"cookie=sessionid=SECRET_COOKIE"}')),
    URLError("token=SECRET_TOKEN"),
])
def test_creator_transport_sanitizes_private_errors(monkeypatch, exception):
    class Opener:
        def open(self, *_args, **_kwargs):
            raise exception

    monkeypatch.setattr(network, "CreatorGateway", lambda: SimpleNamespace(base_url="http://127.0.0.1:8000", opener=Opener()))
    with pytest.raises(HTTPException) as raised:
        network.creator_call("/api/download-sessions")
    assert "SECRET" not in str(raised.value.detail)


def test_creator_transport_never_sends_local_login_request_to_remote_host(monkeypatch):
    class Forbidden:
        def open(self, *_args, **_kwargs):
            raise AssertionError("must not send account requests to remote service")

    monkeypatch.setattr(network, "CreatorGateway", lambda: SimpleNamespace(base_url="https://outside.example", opener=Forbidden()))
    with pytest.raises(HTTPException, match="本机回环"):
        network.creator_call("/api/download-sessions")
