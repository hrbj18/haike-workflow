"""Local-only account/download session controls; never returns cookie values."""
import asyncio
import time
import uuid
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from .download_credentials import DownloadCredentialError
from . import download_sessions as service


router = APIRouter(prefix="/api/download-sessions", tags=["download-sessions"])
_LOGIN_TASKS = {}
_LOGIN_LOCKS = {}
_TERMINAL = {"confirmed", "error", "expired"}
_PREVIEW_PENDING = {"opening", "waiting", "verification", "persisted"}


def _public_login(info, task_id):
    status = info.get("status", "waiting")
    hints = {"opening": "正在打开平台登录窗口", "waiting": "请在账号窗口完成扫码登录",
             "verification": "请在账号窗口完成平台要求的验证",
             "persisted": "扫码已确认，正在检查账号", "confirmed": "扫码登录已完成",
             "error": "登录尚未完成，请在账号窗口检查后重试", "expired": "扫码登录已超时，请重新打开"}
    result = {"task_id": task_id, "status": status,
            "account_id": info.get("account_id"), "platform": info.get("platform"),
            "hint": hints.get(status, "请在账号窗口完成登录")}
    if task_id and status in _PREVIEW_PENDING:
        result["preview_url"] = f"/api/download-sessions/login/{quote(task_id, safe='')}/preview.png"
    return result


def _account_window_info(own):
    runtime = service._runtime()
    lease = runtime.open_browsers.get(own["account_id"])
    active = (lease is not None and lease.active
              and id(lease.context) == own.get("preview_context_id")
              and time.monotonic() - own["created"] <= 660)
    return {"status": "waiting" if active else "expired",
            "platform": own["platform"], "account_id": own["account_id"]}


def _confirm_account_windows(account):
    for task_id, own in list(_LOGIN_TASKS.items()):
        if own.get("kind") == "account-window" and own.get("account_id") == account["id"]:
            own["terminal"] = {**_public_login({"status": "confirmed", "platform": account["platform"],
                                               "account_id": account["id"]}, task_id),
                               "account": account}


class DownloadLoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Literal["douyin", "kuaishou", "shipinhao", "xhs"]


@router.get("")
def list_sessions():
    return service.list_download_sessions()


@router.post("/login")
async def add_download_account(body: DownloadLoginInput):
    requested_at = time.monotonic()
    runtime = service._runtime()
    start = {"douyin": runtime.login_browser_start,
             "kuaishou": runtime.login_ks_start,
             "shipinhao": runtime.login_channels_start,
             "xhs": runtime.login_xhs_start}[body.platform]
    result = await start()
    task_id = result.get("task_id")
    if task_id:
        # Bounded in-memory polling state contains IDs and metadata only.
        for old_id, old in list(_LOGIN_TASKS.items()):
            if time.monotonic() - old["created"] > 1800:
                _LOGIN_TASKS.pop(old_id, None)
                _LOGIN_LOCKS.pop(old_id, None)
        if len(_LOGIN_TASKS) >= 128:
            oldest = min(_LOGIN_TASKS, key=lambda key: _LOGIN_TASKS[key]["created"])
            _LOGIN_TASKS.pop(oldest, None)
            _LOGIN_LOCKS.pop(oldest, None)
        _LOGIN_TASKS[task_id] = {"created": time.monotonic(), "platform": body.platform,
                               "account_id": result.get("account_id"),
                               "context_created_after": 0 if result.get("reused") else requested_at}
        _LOGIN_LOCKS.setdefault(task_id, asyncio.Lock())
        info = runtime.login_tasks.get(task_id)
        if info is not None and info.get("status") in _PREVIEW_PENDING:
            # This changes only how long our UI waits for the owner to scan;
            # it does not extend a platform QR/token/cookie lifetime.
            info["ui_timeout_seconds"] = 600
    return _public_login(result, task_id)


@router.get("/login/{task_id}")
async def login_task(task_id: str):
    own = _LOGIN_TASKS.get(task_id)
    if own is None:
        raise HTTPException(404, "下载登录任务不存在，请重新打开登录窗口")
    async with _LOGIN_LOCKS[task_id]:
        if own.get("terminal") is not None:
            return own["terminal"]
        if own.get("kind") == "account-window":
            result = _public_login(_account_window_info(own), task_id)
            if result["status"] in _TERMINAL:
                own["terminal"] = result
            return result
        # Do not consume main's terminal poll record: the ordinary account UI
        # may be waiting for the same task. Retain our own redacted terminal.
        info = service._runtime().login_tasks.get(task_id)
        if info is None:
            raise HTTPException(404, "登录任务已结束，请刷新账号列表")
        result = _public_login(info, task_id)
        if result["status"] == "confirmed" and type(result.get("account_id")) is int:
            try:
                account = await service.refresh_download_session(result["account_id"])
                result["account"] = account
                if account["download_status"] == "ready":
                    store = service.credential_store()
                    if store.selected_account(account["platform"]) is None:
                        result["account"] = service.select_download_session(account["id"])
            except Exception:
                # A completed QR login is distinct from a confirmed download
                # scope. Keep that distinction visible without leaking errors.
                result["download_status"] = "unconfirmed"
                result["hint"] = "扫码已完成，下载登录仍需检查，请在账号列表重试检查"
        if result["status"] in _TERMINAL:
            own["terminal"] = result
        return result


def _pending_preview_task(task_id):
    own = _LOGIN_TASKS.get(task_id)
    if own is None:
        raise HTTPException(404, "下载登录任务不存在")
    info = (_account_window_info(own) if own.get("kind") == "account-window"
            else service._runtime().login_tasks.get(task_id))
    if (info is None or info.get("status") not in _PREVIEW_PENDING
            or own.get("terminal") is not None
            or time.monotonic() - own["created"] > 660):
        raise HTTPException(410, "该扫码任务已结束，请重新打开登录窗口")
    if info.get("platform") != own["platform"]:
        raise HTTPException(409, "登录任务与窗口不匹配")
    return own


@router.get("/login/{task_id}/preview.png")
async def login_preview(task_id: str):
    own = _pending_preview_task(task_id)
    content, context_id = await service.login_preview_png(
        own["platform"], own.get("account_id"),
        created_after=own.get("context_created_after", 0),
        context_id=own.get("preview_context_id"))
    # A successful scan may finish while screenshot() is in flight. Never
    # serve a post-login page after the task has become terminal.
    _pending_preview_task(task_id)
    own["preview_context_id"] = context_id
    return Response(content, media_type="image/png", headers={
        "Cache-Control": "no-store", "Pragma": "no-cache", "Expires": "0"})


@router.get("/{account_id}")
def session_metadata(account_id: int):
    return service.download_session_metadata(account_id)


@router.post("/{account_id}/check")
async def check_session(account_id: int):
    try:
        account = await service.refresh_download_session(account_id)
        if account["download_status"] == "ready":
            _confirm_account_windows(account)
        return {"ok": account["download_status"] == "ready", "account": account}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "下载登录暂时无法检查，请稍后重试") from None


@router.post("/{account_id}/open-login")
async def open_login(account_id: int):
    try:
        result = await service.open_download_login(account_id)
        runtime = service._runtime()
        account = service._account(account_id)
        lease = runtime.open_browsers.get(account_id)
        if lease is None or not lease.active:
            raise HTTPException(409, "账号窗口尚未就绪，请稍后重试")
        # Reopening an owned window only adds an in-app preview. It does not
        # start force_reauth, clear cookies, or create a second browser.
        for old_id, old in list(_LOGIN_TASKS.items()):
            if old.get("kind") == "account-window" and old.get("account_id") == account_id:
                old["terminal"] = _public_login({"status": "expired",
                    "platform": old["platform"], "account_id": account_id}, old_id)
        task_id = uuid.uuid4().hex
        _LOGIN_TASKS[task_id] = {"created": time.monotonic(), "platform": account.platform,
            "account_id": account.id, "kind": "account-window", "context_created_after": 0,
            "preview_context_id": id(lease.context)}
        _LOGIN_LOCKS[task_id] = asyncio.Lock()
        return {**result, **_public_login({"status": "waiting", "platform": account.platform,
                                          "account_id": account.id}, task_id),
                "hint": "请在下方账号页面完成登录，再点击检查并保存下载登录"}
    except HTTPException as error:
        if error.status_code < 500:
            raise
        raise HTTPException(503, "账号窗口暂时无法打开，请检查浏览器服务") from None
    except Exception:
        raise HTTPException(503, "账号窗口暂时无法打开，请检查浏览器服务") from None


@router.post("/{account_id}/checkpoint-close")
async def checkpoint_close(account_id: int):
    for own in list(_LOGIN_TASKS.values()):
        if (own.get("kind") == "account-window" and own.get("account_id") == account_id
                and own.get("terminal") is None
                and _account_window_info(own)["status"] == "waiting"):
            raise HTTPException(409, "账号登录窗口仍在等待检查，请先完成扫码并检查登录")
    try:
        return await service.checkpoint_close_download_account(account_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "登录态暂时无法安全保存，本次未关闭浏览器，请稍后重试") from None


@router.post("/{account_id}/select")
def select_session(account_id: int):
    try:
        return {"ok": True, "account": service.select_download_session(account_id)}
    except DownloadCredentialError as error:
        raise HTTPException(400, str(error)) from None


@router.delete("/{account_id}")
def remove_session(account_id: int):
    account = service._account(account_id)
    service.credential_store().delete(account.platform, account.id)
    return {"ok": True, "account": service.download_session_metadata(account.id)}
