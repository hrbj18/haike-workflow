"""Offline contracts for an opt-in publish-only active window."""
import asyncio
from datetime import datetime, timedelta

import httpx
import pytest

import app.db as db
import app.main as main
import app.engine.monitor as monitor
from app.config import Config
from app.models import DouyinAccount, PublishTask
from app.risk import OperationKind, RiskController
from app.risk_admin import (RiskSettingsError, apply_risk_settings,
                            export_risk_settings, load_persisted_risk_settings)


@pytest.fixture
def local(tmp_path, monkeypatch):
    previous = db._engine
    db.init_db(str(tmp_path / "publish-hours.db"))
    cfg = Config()
    monkeypatch.setattr(main, "cfg", cfg)
    monkeypatch.setattr(main, "engine", None)
    monkeypatch.setenv("CREATORHUB_ADMIN_TOKEN", "fixture-admin-only")
    with db.get_session() as session:
        account = DouyinAccount(platform="kuaishou", status="active", timezone_id="Asia/Shanghai")
        session.add(account); session.commit(); session.refresh(account)
        account_id = account.id
    try:
        yield cfg, account_id
    finally:
        db._engine.dispose()
        db._engine = previous


def test_default_publish_window_inherits_the_original_quiet_hours(local):
    cfg, account_id = local
    assert cfg.engine.publish_active_hours_start is None
    assert cfg.engine.publish_active_hours_end is None
    risk = RiskController(cfg)
    night = datetime(2026, 10, 16, 17, 0)  # Shanghai 01:00 next day.
    for kind in (OperationKind.PUBLISH, OperationKind.COMMENT, OperationKind.DM):
        decision = risk.preflight(account_id, kind, now=night)
        assert not decision.allowed and decision.signal == "quiet_hours"
        assert decision.next_allowed_at == datetime(2026, 10, 17, 0, 0)


def test_publish_all_day_does_not_open_comment_dm_or_social_windows(local):
    cfg, account_id = local
    cfg.engine.publish_active_hours_start = 0
    cfg.engine.publish_active_hours_end = 24
    risk = RiskController(cfg)
    night = datetime(2026, 10, 16, 17, 0)
    assert risk.preflight(account_id, OperationKind.PUBLISH, now=night).allowed
    for kind in (OperationKind.COMMENT, OperationKind.DM, OperationKind.SOCIAL):
        decision = risk.preflight(account_id, kind, now=night)
        assert not decision.allowed and decision.signal == "quiet_hours"
    assert (cfg.engine.active_hours_start, cfg.engine.active_hours_end) == (8, 24)


def test_publish_override_keeps_the_conservative_two_hour_gap_and_daily_cap(local):
    cfg, account_id = local
    cfg.engine.publish_active_hours_start = 0
    cfg.engine.publish_active_hours_end = 24
    cfg.risk_control.publish_min_gap_seconds = 0  # Conservative hard minimum remains.
    risk = RiskController(cfg)
    now = datetime(2026, 10, 16, 23, 0)  # Shanghai 07:00.
    risk.record_success(account_id, OperationKind.PUBLISH, now=now - timedelta(seconds=7199))
    decision = risk.preflight(account_id, OperationKind.PUBLISH, now=now)
    assert decision.signal == "kind_gap" and decision.next_allowed_at == now + timedelta(seconds=1)
    risk.record_success(account_id, OperationKind.PUBLISH, now=now - timedelta(hours=4))
    risk.record_success(account_id, OperationKind.PUBLISH, now=now - timedelta(hours=6))
    decision = risk.preflight(account_id, OperationKind.PUBLISH, now=now + timedelta(seconds=1))
    assert not decision.allowed and decision.signal == "daily_cap"


def test_publish_window_deferral_uses_its_own_next_opening(local):
    cfg, account_id = local
    cfg.engine.publish_active_hours_start = 20
    cfg.engine.publish_active_hours_end = 26
    decision = RiskController(cfg).preflight(account_id, OperationKind.PUBLISH,
        now=datetime(2026, 10, 16, 19, 0))  # Shanghai 03:00, outside 20:00–02:00.
    assert not decision.allowed and decision.signal == "quiet_hours"
    assert decision.next_allowed_at == datetime(2026, 10, 17, 12, 0)  # Shanghai 20:00.


def test_monitor_publish_gate_reaches_original_gap_instead_of_global_quiet_hours(local, monkeypatch):
    cfg, account_id = local
    cfg.engine.publish_active_hours_start = 0
    cfg.engine.publish_active_hours_end = 24
    now = datetime(2026, 10, 16, 17, 0)
    class Clock(datetime):
        @classmethod
        def utcnow(cls):
            return now
    monkeypatch.setattr(monitor, "datetime", Clock)
    monkeypatch.setattr("app.risk._utcnow", lambda: now)
    engine = monitor.MonitorEngine(cfg, object())
    monkeypatch.setattr(engine, "_native_write_environment_error", lambda *a, **k: "")
    engine.risk.record_success(account_id, OperationKind.PUBLISH, now=now - timedelta(hours=1))
    with db.get_session() as session:
        task = PublishTask(account_id=account_id, platform="kuaishou", status="pending")
        session.add(task); session.commit(); session.refresh(task)
        task_id = task.id
    result = asyncio.run(engine._publish_task_locked(task_id))
    assert not result["ok"]
    with db.get_session() as session:
        task = session.get(PublishTask, task_id)
        assert task.status == "pending" and task.blocked_signal == "kind_gap"
        assert task.next_allowed_at == now + timedelta(hours=1)
    assert not engine._in_active_window(account_id)  # Other monitor writes still quiet.


def test_publish_schedule_http_roundtrip_persist_and_explicit_reset(local):
    cfg, _ = local
    async def scenario():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1",
                headers={"X-CreatorHub-Admin-Token": "fixture-admin-only"}) as client:
            initial = (await client.get("/api/risk-control/config")).json()
            assert initial["schedule"]["publish_active_hours_start"] is None
            response = await client.put("/api/risk-control/config", json={"risk_control": {}, "schedule": {
                "publish_active_hours_start": 0, "publish_active_hours_end": 24}})
            assert response.status_code == 200
            data = response.json()
            assert (data["schedule"]["active_hours_start"], data["schedule"]["active_hours_end"]) == (8, 24)
            assert data["risk_control"]["publish_min_gap_seconds"] == 7200
            restored = Config()
            assert load_persisted_risk_settings(restored)
            assert (restored.engine.publish_active_hours_start, restored.engine.publish_active_hours_end) == (0, 24)
            response = await client.put("/api/risk-control/config", json={"risk_control": {}, "schedule": {
                "publish_active_hours_start": None, "publish_active_hours_end": None}})
            assert response.status_code == 200
            assert load_persisted_risk_settings(restored)
            assert restored.engine.publish_active_hours_start is None and restored.engine.publish_active_hours_end is None
    asyncio.run(scenario())


@pytest.mark.parametrize("patch", [
    {"publish_active_hours_start": 0},
    {"publish_active_hours_start": 0, "publish_active_hours_end": None},
    {"publish_active_hours_start": True, "publish_active_hours_end": 24},
    {"publish_active_hours_start": 22, "publish_active_hours_end": 2},
    {"publish_active_hours_start": 0, "publish_active_hours_end": 48},
])
def test_invalid_publish_window_is_rejected_without_partial_risk_changes(local, patch):
    cfg, _ = local
    before = export_risk_settings(cfg)
    with pytest.raises(RiskSettingsError):
        apply_risk_settings(cfg, {"risk_control": {"publish_min_gap_seconds": 9000}, "schedule": patch})
    assert export_risk_settings(cfg) == before
