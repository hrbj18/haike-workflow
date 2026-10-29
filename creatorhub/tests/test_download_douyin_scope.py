"""Douyin creator proof uses the owned browser and never uploads or publishes."""
import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.db as db
from app import download_sessions as service
from app.browser.identity import Identity
from app.models import DouyinAccount


@pytest.fixture
def account_runtime(tmp_path, monkeypatch):
    previous = db._engine
    db.init_db(str(tmp_path / "accounts.db"))
    cookie = {"name": "sessionid", "value": "offline-fixture", "domain": ".douyin.com",
              "path": "/", "expires": -1}
    with db.get_session() as session:
        account = DouyinAccount(platform="douyin", nickname="fixture", status="active",
            profile_dir=str(tmp_path / "profile"), ua="fixture-UA",
            storage_state=json.dumps({"cookies": [cookie]}),
            creator_storage_state="unchanged-publish-snapshot")
        session.add(account)
        session.commit()
        session.refresh(account)
        account_id = account.id

    context = SimpleNamespace(cookies=AsyncMock(return_value=[cookie]))

    class Browser:
        def identity_for(self, value):
            return Identity.from_account(value, str(tmp_path / "profiles"), "fixture-UA")

        @asynccontextmanager
        async def lock_for(self, _key):
            yield

        async def context_for(self, _identity):
            return context

    runtime = SimpleNamespace(browser=Browser(), engine=None, open_browsers={},
                              cfg=SimpleNamespace(db_path=str(tmp_path / "accounts.db")))
    monkeypatch.setattr(service, "_runtime", lambda: runtime)
    monkeypatch.setattr(service, "_PUBLISH_EVIDENCE", {})
    monkeypatch.setattr(service, "_CHECK_LOCKS", {})
    monkeypatch.setenv("HAIKE_DOWNLOAD_CREDENTIALS_DIR", str(tmp_path / "credentials"))
    monkeypatch.setattr(service, "_probe_download_scope", AsyncMock(return_value="ready"))
    yield SimpleNamespace(id=account_id, context=context, runtime=runtime, cookie=cookie)
    db._engine.dispose()
    db._engine = previous


def test_fresh_douyin_creator_check_becomes_separate_publish_proof(account_runtime, monkeypatch):
    probe = AsyncMock(return_value="ready")
    monkeypatch.setattr(service, "_probe_douyin_publish_scope", probe, raising=False)
    result = asyncio.run(service.refresh_download_session(account_runtime.id))
    assert result["download_status"] == "ready"
    assert result["publish_verified"] is True, "Douyin creator proof must not remain permanently unconfirmed"
    assert result["publish_status"] == "active"
    assert result["publish_checked_at"]
    probe.assert_awaited_once_with(account_runtime.context)
    with db.get_session() as session:
        account = session.get(DouyinAccount, account_runtime.id)
        assert account.status == "active"
        assert account.creator_storage_state == "unchanged-publish-snapshot"
        assert json.loads(account.storage_state)["cookies"] == [account_runtime.cookie]


@pytest.mark.parametrize("status", ["login_required", "network_error", "unconfirmed"])
def test_publisher_failure_keeps_verified_download_scope(account_runtime, monkeypatch, status):
    monkeypatch.setattr(service, "_probe_douyin_publish_scope", AsyncMock(return_value=status))
    result = asyncio.run(service.refresh_download_session(account_runtime.id))
    assert result["download_status"] == "ready"
    assert result["publish_status"] == status
    assert result["publish_verified"] is False
    assert result["publish_available"] is False
    assert result["publish_checked_at"]
    assert service._PUBLISH_EVIDENCE[account_runtime.id]["status"] == status
    for secret in ("offline-fixture", "unchanged-publish-snapshot"):
        assert secret not in json.dumps(result)
    with db.get_session() as session:
        account = session.get(DouyinAccount, account_runtime.id)
        assert account.status == "active"
        assert account.creator_storage_state == "unchanged-publish-snapshot"


@pytest.mark.parametrize("change", ["expiry", "cookies", "profile"])
def test_creator_proof_expires_and_is_bound_to_same_profile_and_cookies(account_runtime, monkeypatch, change):
    monkeypatch.setattr(service, "_probe_douyin_publish_scope", AsyncMock(return_value="ready"))
    result = asyncio.run(service.refresh_download_session(account_runtime.id))
    assert result["publish_verified"] is True
    proof = service._PUBLISH_EVIDENCE[account_runtime.id]
    assert 290 < proof["expires"] - service.time.monotonic() <= 300
    if change == "expiry":
        proof["expires"] = 0
    elif change == "cookies":
        account = service._account(account_runtime.id)
        service.credential_store().refresh_snapshot("douyin", account.id,
            [{**account_runtime.cookie, "value": "rotated-offline-fixture"}], profile_dir=account.profile_dir)
    else:
        with db.get_session() as session:
            account = session.get(DouyinAccount, account_runtime.id)
            account.profile_dir += "-different"
            session.add(account)
            session.commit()
    metadata = service.download_session_metadata(account_runtime.id)
    assert metadata["publish_verified"] is False
    assert metadata["publish_checked_at"] == (None if change == "profile" else result["publish_checked_at"])
    assert metadata["publish_status"] == "stored_unverified"


@pytest.mark.parametrize("change", ["restart", "normal_cookie_rotation"])
def test_scope_history_survives_without_granting_current_publish_proof(account_runtime, monkeypatch, change):
    monkeypatch.setattr(service, "_probe_douyin_publish_scope", AsyncMock(return_value="ready"))
    checked = asyncio.run(service.refresh_download_session(account_runtime.id))
    if change == "restart":
        service._PUBLISH_EVIDENCE.clear()
        db._engine.dispose()
        db.init_db(account_runtime.runtime.cfg.db_path)
    else:
        account = service._account(account_runtime.id)
        service.credential_store().refresh_snapshot("douyin", account.id, [account_runtime.cookie,
            {**account_runtime.cookie, "name": "ui_preference", "value": "normal-rotation"}],
            profile_dir=account.profile_dir)
    history = service.download_session_metadata(account_runtime.id)
    assert history["publish_checked_at"] == checked["publish_checked_at"]
    assert history["publish_check_status"] == "ready"
    assert history["download_checked_at"] == checked["download_checked_at"]
    assert history["download_check_status"] == "ready"
    assert history["publish_verified"] is False
    assert history["publish_status"] == "stored_unverified"


@pytest.mark.parametrize("status", ["login_required", "network_error", "unconfirmed"])
def test_new_scope_history_replaces_prior_success(account_runtime, monkeypatch, status):
    monkeypatch.setattr(service, "_probe_douyin_publish_scope", AsyncMock(return_value="ready"))
    asyncio.run(service.refresh_download_session(account_runtime.id))
    monkeypatch.setattr(service, "_probe_douyin_publish_scope", AsyncMock(return_value=status))
    checked = asyncio.run(service.refresh_download_session(account_runtime.id))
    service._PUBLISH_EVIDENCE.clear()
    metadata = service.download_session_metadata(account_runtime.id)
    assert metadata["publish_check_status"] == status
    assert metadata["publish_checked_at"] == checked["publish_checked_at"]
    assert metadata["download_check_status"] == "ready"


def test_download_failure_records_only_the_scope_actually_checked(account_runtime, monkeypatch):
    publisher = AsyncMock(return_value="ready")
    monkeypatch.setattr(service, "_probe_douyin_publish_scope", publisher)
    checked = asyncio.run(service.refresh_download_session(account_runtime.id))
    monkeypatch.setattr(service, "_probe_download_scope", AsyncMock(return_value="login_required"))
    metadata = asyncio.run(service.refresh_download_session(account_runtime.id))
    assert metadata["download_check_status"] == "login_required"
    assert metadata["publish_check_status"] == "ready"
    assert metadata["publish_checked_at"] == checked["publish_checked_at"]
    assert publisher.await_count == 1
    assert metadata["publish_verified"] is False


def test_scope_history_read_does_not_invent_or_persist_checks(account_runtime):
    from app.models import AppSetting
    metadata = service.download_session_metadata(account_runtime.id)
    for key in ("download_check_status", "download_checked_at", "publish_check_status", "publish_checked_at"):
        assert metadata[key] is None
    with db.get_session() as session:
        assert session.get(AppSetting, f"session_observability.v1:{account_runtime.id}") is None


@pytest.mark.parametrize("change", ["profile_dir", "platform"])
def test_scope_history_cannot_follow_a_different_account_context(account_runtime, monkeypatch, change):
    monkeypatch.setattr(service, "_probe_douyin_publish_scope", AsyncMock(return_value="ready"))
    asyncio.run(service.refresh_download_session(account_runtime.id))
    with db.get_session() as session:
        account = session.get(DouyinAccount, account_runtime.id)
        setattr(account, change, account.profile_dir + "-other" if change == "profile_dir" else "kuaishou")
        session.add(account)
        session.commit()
    metadata = service.download_session_metadata(account_runtime.id)
    for key in ("download_check_status", "download_checked_at", "publish_check_status", "publish_checked_at"):
        assert metadata[key] == ("unconfirmed" if change == "profile_dir" and key == "download_check_status" else None)


@pytest.mark.parametrize("state", ["account_invalid", "download_login_required", "profile_changed"])
def test_known_invalid_state_overrides_old_success_without_inventing_new_check(account_runtime, monkeypatch, state):
    from app import session_observability as observation
    monkeypatch.setattr(service, "_probe_douyin_publish_scope", AsyncMock(return_value="ready"))
    checked = asyncio.run(service.refresh_download_session(account_runtime.id))
    account = service._account(account_runtime.id)
    if state == "account_invalid":
        with db.get_session() as session:
            row = session.get(DouyinAccount, account.id)
            row.status = "invalid"
            session.add(row)
            session.commit()
    elif state == "download_login_required":
        service.credential_store().update_status("douyin", account.id, "login_required", profile_dir=account.profile_dir)
    else:
        service.credential_store().save("douyin", account.id, [account_runtime.cookie],
                                      verified=True, profile_dir=account.profile_dir + "-other")
    metadata = service.download_session_metadata(account.id)
    assert metadata["download_check_status"] == ("unconfirmed" if state == "profile_changed" else "login_required")
    assert metadata["download_checked_at"] == checked["download_checked_at"]
    assert metadata["publish_checked_at"] == checked["publish_checked_at"]
    if state == "account_invalid":
        assert metadata["publish_check_status"] == "login_required"
    # The current invalidity changes presentation; it is not a fabricated probe.
    assert observation.scope_check_metadata(service._account(account.id))["download_check_status"] == "ready"


def test_creator_probe_checkpoints_current_state_without_changing_frozen_publish_snapshot(account_runtime, monkeypatch):
    state = {"cookies": [account_runtime.cookie]}
    account_runtime.context.storage_state = AsyncMock(return_value=state)
    capture = Mock(return_value=True)
    monkeypatch.setattr(service, "capture_enabled_download_snapshot", capture)

    async def probe(context, *, checkpoint_callback):
        assert context is account_runtime.context
        await checkpoint_callback()
        return "ready"

    monkeypatch.setattr(service, "_probe_douyin_publish_scope", probe)
    result = asyncio.run(service.refresh_download_session(account_runtime.id))
    assert result["publish_verified"] is True
    identity, captured = capture.call_args.args
    assert identity.account_id == account_runtime.id
    assert captured == state
    account_runtime.context.storage_state.assert_awaited_once()
    assert service._account(account_runtime.id).creator_storage_state == "unchanged-publish-snapshot"


class CreatorPage:
    def __init__(self, *, url=None, body="创作者中心", controls=None, error=None, status=200):
        self.url = url or "https://creator.douyin.com/creator-micro/content/upload"
        self.inner_text = AsyncMock(return_value=body)
        self.evaluate = AsyncMock(return_value=controls or {})
        self.goto = AsyncMock(return_value=SimpleNamespace(status=status), side_effect=error)
        self.close = AsyncMock()


@pytest.mark.parametrize(("controls", "expected"), [
    ({"videoInput": True, "uploadControl": True}, "ready"),
    ({"videoInput": True, "editorControl": True}, "ready"),
    ({"videoInput": False, "uploadControl": True, "editorControl": True}, "unconfirmed"),
    ({"videoInput": True}, "unconfirmed"),
    ({}, "unconfirmed"),
])
def test_creator_requires_video_input_and_actionable_creator_control(controls, expected):
    page = CreatorPage(controls=controls)
    context = SimpleNamespace(new_page=AsyncMock(return_value=page))
    assert asyncio.run(service._probe_douyin_publish_scope(context, response_timeout=0)) == expected
    page.close.assert_awaited_once()
    assert page.goto.call_args.args == ("https://creator.douyin.com/creator-micro/content/upload",)


@pytest.mark.parametrize(("url", "body"), [
    ("https://creator.douyin.com/creator-micro/content/upload", "扫码登录\n验证码登录\n登录"),
    ("https://creator.douyin.com/login", ""),
    ("https://passport.douyin.com/", ""),
])
def test_real_login_page_wins_even_if_creator_url_or_controls_remain(url, body):
    page = CreatorPage(url=url, body=body, controls={"videoInput": True, "uploadControl": True})
    context = SimpleNamespace(new_page=AsyncMock(return_value=page))
    assert asyncio.run(service._probe_douyin_publish_scope(context, response_timeout=0)) == "login_required"
    page.evaluate.assert_not_awaited()
    page.close.assert_awaited_once()


@pytest.mark.parametrize("error", [OSError("offline"), asyncio.TimeoutError()])
def test_network_failure_is_not_reported_as_logout_and_page_closes(error):
    page = CreatorPage(error=error)
    context = SimpleNamespace(new_page=AsyncMock(return_value=page))
    assert asyncio.run(service._probe_douyin_publish_scope(context, response_timeout=0)) == "network_error"
    page.close.assert_awaited_once()


def test_http_error_does_not_reuse_stale_editor_controls():
    page = CreatorPage(status=503, controls={"videoInput": True, "uploadControl": True})
    context = SimpleNamespace(new_page=AsyncMock(return_value=page))
    assert asyncio.run(service._probe_douyin_publish_scope(context, response_timeout=0)) == "network_error"
    page.close.assert_awaited_once()


def test_redirect_without_login_or_creator_evidence_stays_unconfirmed():
    page = CreatorPage(url="https://www.douyin.com/", controls={"videoInput": True, "uploadControl": True})
    context = SimpleNamespace(new_page=AsyncMock(return_value=page))
    assert asyncio.run(service._probe_douyin_publish_scope(context, response_timeout=0)) == "unconfirmed"
    page.close.assert_awaited_once()


@pytest.mark.parametrize("cancelled", [False, True])
def test_checkpoint_precedes_close_and_never_supplies_positive_proof(cancelled):
    events = []
    page = CreatorPage(error=asyncio.CancelledError() if cancelled else None)

    async def checkpoint():
        events.append("checkpoint")
        raise OSError("fixture snapshot failure")

    async def close():
        events.append("close")

    page.close.side_effect = close
    context = SimpleNamespace(new_page=AsyncMock(return_value=page))
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(service._probe_douyin_publish_scope(context, response_timeout=0,
                                                           checkpoint_callback=checkpoint))
    else:
        assert asyncio.run(service._probe_douyin_publish_scope(context, response_timeout=0,
                           checkpoint_callback=checkpoint)) == "unconfirmed"
    assert events == ["checkpoint", "close"]


def test_page_creation_failure_is_network_error():
    context = SimpleNamespace(new_page=AsyncMock(side_effect=OSError("offline")))
    assert asyncio.run(service._probe_douyin_publish_scope(context)) == "network_error"
