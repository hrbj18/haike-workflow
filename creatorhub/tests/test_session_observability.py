"""Maintenance receipts use temporary DBs, fixed clocks, and no browser/network."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.db as db
from app import main, download_sessions, session_observability as observation
from app.browser.identity import Identity
from app.config import Config
from app.engine import monitor
from app.models import AppSetting, DouyinAccount


@pytest.fixture
def account_fixture(tmp_path, monkeypatch):
    previous = db._engine
    db.init_db(str(tmp_path / "fixture.db"))
    with db.get_session() as session:
        account = DouyinAccount(platform="shipinhao", profile_dir=str(tmp_path / "private-profile"),
            storage_state='{"cookies": [{"name":"sessionid","value":"SECRET_COOKIE","domain":"channels.weixin.qq.com"}]}',
            status="active", last_active_at=datetime(2026, 10, 16, 1))
        session.add(account)
        session.commit()
        session.refresh(account)
        account_id = account.id
    config = Config(db_path=str(tmp_path / "fixture.db"))
    config.engine.account_check_interval_seconds = 1800
    config.engine.idle_keepalive_hours = 6
    config.engine.scan_jitter = .15
    config.engine.invalid_auth_recheck_interval_seconds = 3600
    engine = object.__new__(monitor.MonitorEngine)
    engine.cfg = config
    engine._running = True
    engine._last_acct_check = datetime(2026, 10, 16, 1, tzinfo=timezone.utc).timestamp()
    engine._last_invalid_recheck = engine._last_acct_check
    engine.browser = SimpleNamespace(identity_for=lambda item: Identity(account_id=item.id,
        platform=item.platform, profile_dir=item.profile_dir))
    runtime = SimpleNamespace(cfg=config, engine=engine, browser=engine.browser)
    monkeypatch.setattr(download_sessions, "_runtime", lambda: runtime)
    monkeypatch.setattr(download_sessions, "capture_enabled_download_snapshot", lambda *_: False)
    monkeypatch.setenv("HAIKE_DOWNLOAD_CREDENTIALS_DIR", str(tmp_path / "private-downloads"))
    try:
        yield SimpleNamespace(account_id=account_id, runtime=runtime, engine=engine, config=config)
    finally:
        db._engine.dispose()
        db._engine = previous


def account(fixture):
    with db.get_session() as session:
        value = session.get(DouyinAccount, fixture.account_id)
        session.expunge(value)
        return value


def probe(fixture):
    return fixture.engine._account_probe_tuple(account(fixture))


def test_metadata_read_does_not_invent_history_or_create_receipts(account_fixture):
    fixture = account_fixture
    for _ in range(2):
        value = download_sessions.download_session_metadata(fixture.account_id)
        assert value["login_record_saved"] is True
        assert value["observability"]["checkpoint_at"] is None
        assert value["observability"]["background_health_checked_at"] is None
        assert value["observability"]["account_last_active_at"] == "2026-10-16T01:00:00Z"
        assert value["publish_status"] == "unconfirmed"
        assert "SECRET_COOKIE" not in json.dumps(value)
    with db.get_session() as session:
        assert session.get(AppSetting, f"session_observability.v1:{fixture.account_id}") is None


def test_actual_checkpoint_hook_records_success_even_when_state_unchanged_without_login_claim(account_fixture, monkeypatch):
    fixture = account_fixture
    original = observation.record_checkpoint
    times = iter([datetime(2026, 10, 16, 2, tzinfo=timezone.utc), datetime(2026, 10, 16, 3, tzinfo=timezone.utc)])
    monkeypatch.setattr(observation, "record_checkpoint", lambda session, row: original(session, row, at=next(times)))
    row = account(fixture)
    identity = fixture.engine.browser.identity_for(row)
    state = json.loads(row.storage_state)
    assert main._persist_account_session_state(identity, state) is True
    assert main._persist_account_session_state(identity, state) is True
    result = observation.session_metadata(account(fixture), fixture.runtime)
    assert result["checkpoint_at"] == "2026-10-16T03:00:00Z"
    assert result["background_health_checked_at"] is None
    assert account(fixture).last_active_at == row.last_active_at
    assert account(fixture).status == "active"
    identity.profile_dir += "-foreign"
    assert main._persist_account_session_state(identity, state) is False
    assert observation.session_metadata(account(fixture), fixture.runtime)["checkpoint_at"] == result["checkpoint_at"]


def test_checkpoint_receipt_rolls_back_with_the_session_write(account_fixture):
    with db.get_session() as session:
        row = session.get(DouyinAccount, account_fixture.account_id)
        observation.record_checkpoint(session, row)
        row.storage_state = "changed-but-rolled-back"
        session.add(row)
        session.rollback()
    result = observation.session_metadata(account(account_fixture), account_fixture.runtime)
    assert result["checkpoint_at"] is None
    assert "SECRET_COOKIE" in account(account_fixture).storage_state


def test_health_receipts_exclude_deferred_attempts_and_never_store_raw_errors_or_credentials(account_fixture):
    fixture = account_fixture
    assert observation.record_background_health(probe(fixture), {"deferred": True}, trigger="keepalive") is False
    assert observation.session_metadata(account(fixture), fixture.runtime)["background_health_checked_at"] is None
    when = datetime(2026, 10, 16, 4, tzinfo=timezone.utc)
    assert observation.record_background_health(probe(fixture), {"ok": False,"error": "SECRET_URL_AND_TOKEN"}, trigger="keepalive", at=when)
    result = observation.session_metadata(account(fixture), fixture.runtime)
    assert result["background_health_checked_at"] == "2026-10-16T04:00:00Z"
    assert result["background_health_outcome"] == "unconfirmed"
    with db.get_session() as session:
        receipt = session.get(AppSetting, f"session_observability.v1:{fixture.account_id}").value
        for private in ("SECRET_COOKIE", "SECRET_URL_AND_TOKEN", account(fixture).profile_dir):
            assert private not in receipt
        assert len(json.loads(receipt)["profile"]) == 64
    assert account(fixture).status == "active"


def test_profile_or_platform_changes_hide_old_receipts(account_fixture):
    fixture = account_fixture
    assert observation.record_background_health(probe(fixture), {"ok": True}, trigger="keepalive")
    with db.get_session() as session:
        row = session.get(DouyinAccount, fixture.account_id)
        row.profile_dir += "-new"
        session.add(row)
        session.commit()
    assert observation.session_metadata(account(fixture), fixture.runtime)["background_health_checked_at"] is None
    assert observation.record_background_health((fixture.account_id, "kuaishou", "", "", "", SimpleNamespace(profile_dir="different")), {"ok": True}, trigger="keepalive") is False


def test_successful_background_observation_does_not_grant_current_publish_proof(account_fixture):
    fixture = account_fixture
    assert observation.record_background_health(probe(fixture), {"ok": True}, trigger="keepalive")
    result = download_sessions.download_session_metadata(fixture.account_id)
    assert result["observability"]["background_health_outcome"] == "verified"
    assert result["publish_verified"] is False
    assert result["publish_status"] == "unconfirmed"
    assert result["publish_check_status"] is None
    assert result["download_check_status"] is None


def test_scope_history_survives_checkpoint_and_background_health_updates(account_fixture):
    fixture = account_fixture
    row = account(fixture)
    when = datetime(2026, 10, 16, 5, tzinfo=timezone.utc)
    assert observation.record_scope_check(row, "download", "ready", at=when)
    assert observation.record_scope_check(row, "publish", "login_required", at=when)
    with db.get_session() as session:
        current = session.get(DouyinAccount, row.id)
        observation.record_checkpoint(session, current)
        session.commit()
    assert observation.record_background_health(probe(fixture), {"ok": True}, trigger="keepalive")
    history = observation.scope_check_metadata(account(fixture))
    assert history == {"download_check_status": "ready", "download_checked_at": "2026-10-16T05:00:00Z",
                       "publish_check_status": "login_required", "publish_checked_at": "2026-10-16T05:00:00Z"}
    result = observation.session_metadata(account(fixture), fixture.runtime)
    assert result["checkpoint_at"]
    assert result["background_health_outcome"] == "verified"
    with db.get_session() as session:
        receipt = session.get(AppSetting, f"session_observability.v1:{row.id}").value
        for private in ("SECRET_COOKIE", row.profile_dir):
            assert private not in receipt


def test_scope_history_writer_rejects_stale_profile_or_unknown_results(account_fixture):
    fixture = account_fixture
    stale = account(fixture)
    with db.get_session() as session:
        current = session.get(DouyinAccount, stale.id)
        current.profile_dir += "-replacement"
        session.add(current)
        session.commit()
    assert observation.record_scope_check(stale, "publish", "ready") is False
    current = account(fixture)
    assert observation.record_scope_check(current, "publish", "SECRET_ERROR_DETAIL") is False
    assert observation.record_scope_check(current, "general_health", "ready") is False
    assert all(value is None for value in observation.scope_check_metadata(current).values())


@pytest.mark.parametrize("bad", [
    {"publish_check_status": "ready"},
    {"publish_check_status": "ready", "publish_checked_at": "not-a-date"},
    {"publish_check_status": "active", "publish_checked_at": "2026-10-16T05:00:00Z"},
    {"publish_check_status": {"untrusted": "ready"}, "publish_checked_at": "2026-10-16T05:00:00Z"},
])
def test_incomplete_or_unknown_scope_receipts_are_not_login_evidence(account_fixture, bad):
    row = account(account_fixture)
    with db.get_session() as session:
        session.add(AppSetting(key=f"session_observability.v1:{row.id}", value=json.dumps({
            "version": 1, "platform": row.platform,
            "profile": observation.profile_identity(row.profile_dir), **bad})))
        session.commit()
    history = observation.scope_check_metadata(row)
    assert history["publish_check_status"] is None
    assert history["publish_checked_at"] is None


def test_existing_keepalive_loop_records_actual_attempt_but_does_not_add_checks(account_fixture):
    fixture = account_fixture
    with db.get_session() as session:
        row = session.get(DouyinAccount, fixture.account_id)
        row.last_active_at = datetime(2000, 1, 1)
        session.add(row)
        session.commit()
    fixture.engine._last_acct_check = 0
    fixture.engine._probe_account_health = AsyncMock(return_value={"ok": True})
    asyncio.run(fixture.engine._check_accounts())
    assert fixture.engine._probe_account_health.await_count == 1
    result = observation.session_metadata(account(fixture), fixture.runtime)
    assert result["background_health_outcome"] == "verified"
    assert result["background_health_trigger"] == "keepalive"
    checked = result["background_health_checked_at"]
    asyncio.run(fixture.engine._check_accounts())
    assert fixture.engine._probe_account_health.await_count == 1
    assert observation.session_metadata(account(fixture), fixture.runtime)["background_health_checked_at"] == checked


def test_auth_recheck_uses_its_existing_cadence_and_skips_risk_deferrals(account_fixture):
    fixture = account_fixture
    with db.get_session() as session:
        row = session.get(DouyinAccount, fixture.account_id)
        row.status = "invalid"
        session.add(row)
        session.commit()
    fixture.engine._last_invalid_recheck = 0
    fixture.engine._probe_account_health = AsyncMock(return_value={"deferred": True})
    asyncio.run(fixture.engine._check_invalid_accounts())
    assert observation.session_metadata(account(fixture), fixture.runtime)["background_health_checked_at"] is None
    fixture.engine._last_invalid_recheck = 0
    fixture.engine._probe_account_health = AsyncMock(return_value={"ok": False, "error": "logged_out"})
    asyncio.run(fixture.engine._check_invalid_accounts())
    assert fixture.engine._probe_account_health.await_count == 1
    result = observation.session_metadata(account(fixture), fixture.runtime)
    assert result["background_health_outcome"] == "login_required"
    assert result["background_health_trigger"] == "auth_recheck"


def test_displayed_earliest_window_matches_real_idle_due_boundary_and_stays_stable(account_fixture, monkeypatch):
    fixture = account_fixture
    row = account(fixture)
    now = datetime(2026, 10, 16, 2, tzinfo=timezone.utc)
    first = observation.keepalive_metadata(row, fixture.runtime, now=now)
    second = observation.keepalive_metadata(row, fixture.runtime, now=now + timedelta(minutes=10))
    assert first["next_eligible_at"] == second["next_eligible_at"]
    deadline = datetime.fromisoformat(first["next_eligible_at"].replace("Z", "+00:00")).replace(tzinfo=None)
    assert row.last_active_at + timedelta(hours=6) <= deadline <= row.last_active_at + timedelta(hours=6.9)
    class Clock:
        current = deadline - timedelta(seconds=1)
        @classmethod
        def utcnow(cls):
            return cls.current
    monkeypatch.setattr(monitor, "datetime", Clock)
    assert not fixture.engine._keepalive_due(row.last_active_at, account_id=row.id)
    Clock.current = deadline + timedelta(microseconds=1)
    assert fixture.engine._keepalive_due(row.last_active_at, account_id=row.id)
    assert first["schedule_status"] == "waiting"


@pytest.mark.parametrize("mode", ["stopped", "disabled", "missing", "invalid"])
def test_no_guaranteed_schedule_when_unavailable_or_different_recheck_mode(account_fixture, mode):
    fixture = account_fixture
    row = account(fixture)
    if mode == "stopped":
        fixture.engine._running = False
    elif mode == "disabled":
        fixture.config.engine.account_check_interval_seconds = 0
    elif mode == "missing":
        row.storage_state = row.creator_storage_state = ""
    else:
        row.status = "invalid"
    result = observation.keepalive_metadata(row, fixture.runtime)
    if mode == "invalid":
        assert result["mode"] == "auth_recheck" and result["check_interval_seconds"] == 3600
    else:
        assert result["next_eligible_at"] is None
        assert result["schedule_status"] == {"stopped":"engine_stopped", "disabled":"disabled", "missing":"no_saved_session"}[mode]
