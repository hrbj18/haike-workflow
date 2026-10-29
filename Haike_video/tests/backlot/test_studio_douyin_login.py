"""Legacy login routes consume unified scoped checks; never a UI checkbox."""
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot.studio import Studio, atomic_private
from backlot.studio_api import router
from backlot import network_materials, studio_storyboard


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("HAIKE_DOWNLOAD_CREDENTIALS_DIR", str(tmp_path / "credentials"))
    service = Studio(tmp_path / "projects")
    studio_storyboard.download_account(service)
    from douyin_intelligence.download_credentials_adapter import credential_store
    store = credential_store()
    cookies = [{"name": "sessionid", "value": "PRIVATE_TEST_COOKIE", "domain": ".douyin.com", "path": "/", "expires": -1}]
    crawler = tmp_path / "crawler"
    crawler.mkdir()
    (crawler / "main.py").write_text("# fixture")
    python = crawler / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("fixture")
    chrome = tmp_path / "chrome.exe"
    chrome.write_text("fixture")
    config = {"douyin_commercial_authorized": True, "crawler_root": str(crawler), "chrome_path": str(chrome)}
    atomic_private(service.private / "studio-ai/relay.json", config)
    app = FastAPI()
    app.state.studio = service
    app.include_router(router)
    calls = []

    def creator(path, data=None, **kwargs):
        calls.append((path, data))
        if path == "/api/download-sessions/login":
            return {"task_id": "a" * 32, "status": "waiting"}
        return {"ok": True, "account": {"id": 17, "platform": "douyin", "download_status": "ready"},
                "status": "waiting", "task_id": "b" * 32}

    monkeypatch.setattr(network_materials, "creator_call", creator)
    with TestClient(app) as client:
        yield service, store, cookies, config, client, calls, python


def selected(fixture):
    service, store, cookies, *_ = fixture
    store.save("douyin", 17, cookies, verified=True)
    store.select("douyin", 17)


def test_manual_confirmation_cannot_create_or_modify_login_state(fixture):
    service, _, _, _, client, calls, _ = fixture
    before = (service.private / "studio-ai/relay.json").read_bytes()
    response = client.post("/api/studio/ai/douyin/login-confirmed", json={"confirmed": True})
    assert response.status_code == 409
    assert not calls
    assert (service.private / "studio-ai/relay.json").read_bytes() == before


def test_selected_account_is_rechecked_and_never_writes_legacy_boolean(fixture):
    selected(fixture)
    service, _, _, _, client, calls, _ = fixture
    response = client.post("/api/studio/ai/douyin/login-confirmed", json={"confirmed": True})
    assert response.status_code == 200
    assert calls == [("/api/download-sessions/17/check", {})]
    assert response.json()["douyin_login_confirmed"] is True
    assert response.json()["douyin_collection_ready"] is True
    assert "PRIVATE_TEST_COOKIE" not in response.text
    assert "douyin_login_confirmed" not in json.loads((service.private / "studio-ai/relay.json").read_text())


@pytest.mark.parametrize("state", ["unconfirmed", "login_required", "network_error"])
def test_unverified_scope_cannot_resume(fixture, monkeypatch, state):
    selected(fixture)
    _, store, _, _, client, _, _ = fixture
    store.update_status("douyin", 17, state)
    monkeypatch.setattr(network_materials, "creator_call", lambda *a, **k: {"ok": False, "account": {"id": 17, "platform": "douyin", "download_status": state}})
    response = client.post("/api/studio/ai/douyin/login-confirmed", json={"confirmed": True})
    assert response.status_code == 409
    assert "PRIVATE_TEST_COOKIE" not in response.text


def test_ready_api_response_without_ready_shared_snapshot_is_not_success(fixture):
    selected(fixture)
    _, store, _, _, client, _, _ = fixture
    store.update_status("douyin", 17, "unconfirmed")
    assert client.post("/api/studio/ai/douyin/login-confirmed", json={"confirmed": True}).status_code == 409


def test_missing_mediacrawler_is_not_reported_collection_ready(fixture):
    selected(fixture)
    *_, client, calls, python = fixture
    python.unlink()
    response = client.post("/api/studio/ai/douyin/login-confirmed", json={"confirmed": True})
    assert response.status_code == 503
    assert "MediaCrawler" in response.text


def test_runtime_files_do_not_replace_commercial_authorization(fixture, monkeypatch):
    monkeypatch.setenv("HAIKE_LOCAL_LEARNING_TEST", "1")
    selected(fixture)
    service, _, _, config, client, _, _ = fixture
    config["douyin_commercial_authorized"] = False
    atomic_private(service.private / "studio-ai/relay.json", config)
    response = client.post("/api/studio/ai/douyin/login-confirmed", json={"confirmed": True})
    assert response.status_code == 503
    assert "商用授权" in response.text


def test_login_delegates_to_unified_existing_or_new_account_service(fixture):
    _, _, _, _, client, calls, _ = fixture
    response = client.post("/api/studio/ai/douyin/login", json={"confirmed": True})
    assert response.status_code == 200 and response.json()["status"] == "waiting"
    assert calls[-1] == ("/api/download-sessions/login", {"platform": "douyin"})
    selected(fixture)
    response = client.post("/api/studio/ai/douyin/login", json={"confirmed": True})
    assert response.status_code == 200
    assert calls[-1] == ("/api/download-sessions/17/open-login", {})


def test_old_routes_keep_origin_and_input_guards(fixture):
    *_, client, calls, python = fixture
    for path in ("login", "login-confirmed"):
        assert client.post(f"/api/studio/ai/douyin/{path}", json={"confirmed": True}, headers={"Origin": "https://outside.example"}).status_code == 403
        assert client.post(f"/api/studio/ai/douyin/{path}", json={"confirmed": True, "cookie": "PRIVATE_TEST_COOKIE"}).status_code == 422
    assert not calls
