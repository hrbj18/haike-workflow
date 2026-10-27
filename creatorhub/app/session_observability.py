"""Credential-free receipts for session saves and scheduled health attempts.

These receipts are observations, never authentication evidence. Existing accounts
have no fabricated historical timestamps; profile changes invalidate old receipts.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

from .db import get_session
from .download_credentials import profile_identity
from .engine.cadence import periodic_deadline
from .models import AppSetting, DouyinAccount


_SCOPE_CHECK_STATUSES = frozenset({"ready", "login_required", "network_error", "unconfirmed"})


def _iso(value):
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _key(account_id):
    return f"session_observability.v1:{account_id}"


def _timestamp(value):
    try:
        return _iso(datetime.fromisoformat(value.replace("Z", "+00:00"))) if isinstance(value, str) else None
    except ValueError:
        return None


def _receipt(session, account):
    row = session.get(AppSetting, _key(account.id))
    try:
        value = json.loads(row.value) if row else {}
    except (TypeError, ValueError):
        value = {}
    scope = {"version": 1, "platform": account.platform,
             "profile": profile_identity(account.profile_dir)}
    if not isinstance(value, dict) or any(value.get(k) != v for k, v in scope.items()):
        value = scope
    clean = {**scope, **{key: _timestamp(value.get(key)) for key in (
        "checkpoint_at", "background_health_checked_at") if _timestamp(value.get(key))}}
    for key, allowed in (("background_health_outcome", {"verified", "login_required", "unconfirmed"}),
                         ("background_health_trigger", {"keepalive", "auth_recheck"})):
        if isinstance(value.get(key), str) and value[key] in allowed:
            clean[key] = value[key]
    for checked_scope in ("download", "publish"):
        status = value.get(f"{checked_scope}_check_status")
        checked_at = _timestamp(value.get(f"{checked_scope}_checked_at"))
        if isinstance(status, str) and status in _SCOPE_CHECK_STATUSES and checked_at:
            clean[f"{checked_scope}_check_status"] = status
            clean[f"{checked_scope}_checked_at"] = checked_at
    return row, clean


def _save(session, account, values):
    row, value = _receipt(session, account)
    value.update(values)
    if row is None:
        row = AppSetting(key=_key(account.id))
    row.value = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    session.add(row)


def record_checkpoint(session, account, *, at=None):
    """Participate in the same transaction as the actual owned session save."""
    if not account.id or not account.profile_dir:
        return
    _save(session, account, {"checkpoint_at": _iso(at or datetime.now(timezone.utc))})


def record_background_health(probe, result, *, trigger, at=None):
    """Store a finished scheduler attempt, never risk-gated skips or raw errors."""
    if not isinstance(result, dict) or result.get("deferred"):
        return False
    if trigger not in {"keepalive", "auth_recheck"}:
        return False
    try:
        aid, platform, _state, _creator_state, _proxy, identity = probe
        with get_session() as session:
            account = session.get(DouyinAccount, aid)
            if (not account or account.platform != platform or not account.profile_dir
                    or profile_identity(account.profile_dir) != profile_identity(identity.profile_dir)):
                return False
            outcome = "verified" if result.get("ok") is True else (
                "login_required" if result.get("error") == "logged_out" else "unconfirmed")
            _save(session, account, {"background_health_checked_at": _iso(at or datetime.now(timezone.utc)),
                "background_health_outcome": outcome, "background_health_trigger": trigger})
            session.commit()
        return True
    except Exception:
        # Observability must not disrupt the existing scheduler or log secrets.
        return False


def record_scope_check(checked_account, checked_scope, status, *, at=None):
    """Remember an actual scope probe, independently of short-lived live proof.

    Only the result and time are stored. Cookie rotation, checkpoint saves and
    process restarts do not erase history or turn it into execution permission.
    """
    if (checked_scope not in {"download", "publish"}
            or not isinstance(status, str) or status not in _SCOPE_CHECK_STATUSES):
        return False
    try:
        with get_session() as session:
            account = session.get(DouyinAccount, checked_account.id)
            if (not account or not account.profile_dir or account.platform != checked_account.platform
                    or profile_identity(account.profile_dir) != profile_identity(checked_account.profile_dir)):
                return False
            _save(session, account, {f"{checked_scope}_check_status": status,
                f"{checked_scope}_checked_at": _iso(at or datetime.now(timezone.utc))})
            session.commit()
        return True
    except Exception:
        # Historical display cannot change a probe's authentication outcome.
        return False


def scope_check_metadata(account):
    """Read historical checks without migrating snapshots or probing a platform."""
    with get_session() as session:
        _row, receipt = _receipt(session, account)
    return {key: receipt.get(key) for checked_scope in ("download", "publish")
            for key in (f"{checked_scope}_check_status", f"{checked_scope}_checked_at")}


def _number(value, *, minimum=0):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and (minimum is None or value >= minimum) else None


def keepalive_metadata(account, runtime, *, now=None):
    """Expose existing cadence's lower bound, not a promised execution time."""
    now = now or datetime.now(timezone.utc)
    now = now.replace(tzinfo=now.tzinfo or timezone.utc).astimezone(timezone.utc)
    config = getattr(getattr(runtime, "cfg", None), "engine", None)
    engine = getattr(runtime, "engine", None)
    interval = _number(getattr(config, "account_check_interval_seconds", None))
    hours = _number(getattr(config, "idle_keepalive_hours", None), minimum=None)
    jitter = _number(getattr(config, "scan_jitter", None))
    running = getattr(engine, "_running", None)
    running = running if isinstance(running, bool) else None
    mode = "auth_recheck" if account.status == "invalid" else "keepalive"
    if mode == "auth_recheck":
        interval = _number(getattr(config, "invalid_auth_recheck_interval_seconds", None))
    value = {"engine_running": running, "configured": interval > 0 if interval is not None else None,
             "mode": mode, "idle_hours": hours, "check_interval_seconds": interval,
             "jitter_ratio": jitter, "next_eligible_at": None, "schedule_status": "unknown"}
    if interval is None:
        return value
    if interval <= 0:
        value["schedule_status"] = "disabled"
        return value
    if running is not True:
        value["schedule_status"] = "engine_stopped" if running is False else "unknown"
        return value
    if not (account.storage_state or account.creator_storage_state):
        value["schedule_status"] = "no_saved_session"
        return value
    cycle = _number(getattr(engine, "_last_invalid_recheck" if mode == "auth_recheck" else "_last_acct_check", None))
    if cycle is None or (mode == "keepalive" and (hours is None or jitter is None)):
        return value
    lower = datetime.fromtimestamp(cycle, timezone.utc) + timedelta(seconds=interval) if cycle else None
    if mode == "keepalive" and hours > 0:
        deadline = periodic_deadline(account.last_active_at, hours * 3600,
                                     key=f"keepalive:{account.id}", jitter=jitter)
        if deadline is not None:
            deadline = deadline.replace(tzinfo=deadline.tzinfo or timezone.utc).astimezone(timezone.utc)
            lower = max(lower, deadline) if lower is not None else deadline
    value["next_eligible_at"] = _iso(lower)
    value["schedule_status"] = "waiting" if lower is not None and lower > now else "due"
    return value


def session_metadata(account, runtime):
    with get_session() as session:
        _row, receipt = _receipt(session, account)
    return {"checkpoint_at": receipt.get("checkpoint_at"),
            "background_health_checked_at": receipt.get("background_health_checked_at"),
            "background_health_outcome": receipt.get("background_health_outcome"),
            "background_health_trigger": receipt.get("background_health_trigger"),
            "account_last_active_at": _iso(account.last_active_at),
            "keepalive": keepalive_metadata(account, runtime)}
