"""Background login probes are opt-in; manual and task checks remain available."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import Config
from app.db import get_session
from app.engine.monitor import MonitorEngine
from app.engine_settings import load_persisted_engine_settings, save_engine_settings
from app.models import AccountRiskState, DouyinAccount
from test_project_optimizations import local_project, store


PROCESSES = ("_check_accounts", "_check_invalid_accounts", "_process_risk_recovery")


def seeded_engine(project, process, count=1):
    project.cfg.engine.idle_keepalive_hours = 0
    for _ in range(count):
        account_id = store(DouyinAccount(
            platform="shipinhao", status="invalid" if process == "_check_invalid_accounts" else "active",
            storage_state='{"cookies":[]}', last_active_at=datetime(2000, 1, 1)))
        if process == "_process_risk_recovery":
            with get_session() as session:
                session.add(AccountRiskState(account_id=account_id, risk_level=1))
                session.commit()
    project.browser.identity_for = lambda account: SimpleNamespace(profile_dir=account.profile_dir)
    engine = MonitorEngine(project.cfg, project.browser)
    engine._last_acct_check = engine._last_invalid_recheck = 0
    return engine


@pytest.mark.parametrize("process", PROCESSES)
def test_new_install_does_not_probe_accounts_on_background_tick(local_project, process):
    engine = seeded_engine(local_project, process)
    assert engine.cfg.engine.background_account_checks_enabled is False
    engine._probe_account_health = AsyncMock(return_value={"ok": True})
    asyncio.run(getattr(engine, process)())
    engine._probe_account_health.assert_not_awaited()
    assert engine._last_acct_check == engine._last_invalid_recheck == 0


@pytest.mark.parametrize("process", PROCESSES)
def test_setting_enables_and_disables_each_existing_probe_path(local_project, process):
    engine = seeded_engine(local_project, process)
    engine._probe_account_health = AsyncMock(return_value={"ok": True})
    save_engine_settings(engine.cfg, {"background_account_checks_enabled": True})
    asyncio.run(getattr(engine, process)())
    assert engine._probe_account_health.await_count == 1
    assert engine._probe_account_health.await_args.kwargs["automatic"] is True
    save_engine_settings(engine.cfg, {"background_account_checks_enabled": False})
    engine._last_acct_check = engine._last_invalid_recheck = 0
    asyncio.run(getattr(engine, process)())
    assert engine._probe_account_health.await_count == 1
    restarted = Config()
    assert load_persisted_engine_settings(restarted)
    assert restarted.engine.background_account_checks_enabled is False


@pytest.mark.parametrize("process", PROCESSES)
def test_disabling_during_a_batch_stops_remaining_accounts(local_project, process):
    engine = seeded_engine(local_project, process, count=2)
    engine.cfg.engine.background_account_checks_enabled = True

    async def disable(*_args, **_kwargs):
        engine.cfg.engine.background_account_checks_enabled = False
        return {"ok": True}

    engine._probe_account_health = AsyncMock(side_effect=disable)
    asyncio.run(getattr(engine, process)())
    assert engine._probe_account_health.await_count == 1


def test_check_waiting_for_account_lock_respects_a_newly_disabled_switch(local_project, monkeypatch):
    engine = seeded_engine(local_project, "_check_accounts")
    engine.cfg.engine.background_account_checks_enabled = True
    engine.risk.preflight = lambda *_args, **_kwargs: SimpleNamespace(allowed=True)
    verify = AsyncMock()
    monkeypatch.setattr(engine, "_verify_proxy_region", verify)

    @asynccontextmanager
    async def waiting_guard(*_args):
        engine.cfg.engine.background_account_checks_enabled = False
        yield

    monkeypatch.setattr(engine, "_operation_guard", waiting_guard)
    result = asyncio.run(engine._probe_account_health(
        (1, "shipinhao", "", "", "", SimpleNamespace(timezone_id="Asia/Shanghai")), automatic=True))
    assert result["deferred"] is True
    verify.assert_not_awaited()
