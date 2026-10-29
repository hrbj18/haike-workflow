"""Account-scoped, read-only acquisition of current browser download sessions."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlmodel import select

from .db import get_session
from .download_credentials import (
    DownloadCredentialError, DownloadCredentialStore, PLATFORM_DOMAINS,
    platform_domain_allowed, profile_identity, resolve_store_root,
)
from .models import DouyinAccount, PublishTask


_CHECK_LOCKS = {}
_PUBLISH_EVIDENCE = {}
_PROBE_CHECKPOINT_TIMEOUT_SECONDS = 15
_HOME = {
    "douyin": "https://www.douyin.com/user/self",
    "kuaishou": "https://www.kuaishou.com/new-reco",
    "xhs": "https://www.xiaohongshu.com/",
    "shipinhao": "https://channels.weixin.qq.com/platform",
}
_AUTH_COOKIES = {
    "douyin": {"sessionid", "sessionid_ss", "sid_tt", "sid_guard"},
    "kuaishou": {"passToken", "kuaishou.server.web_st", "kuaishou.server.webday7_st"},
    "xhs": {"web_session"},
    "shipinhao": {"_finder_auth", "sessionid"},
}


def _login_preview_url_allowed(platform, url):
    """Only the known login/home routes used by our interactive QR flows."""
    try:
        parsed = urlsplit(str(url or ""))
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return False
    host, path = (parsed.hostname or "").lower(), parsed.path.rstrip("/") or "/"
    if platform == "douyin":
        return (host in {"passport.douyin.com", "sso.douyin.com", "login.douyin.com"}
                or host == "www.douyin.com" and (
                    path in {"/", "/jingxuan", "/user/self"}
                    or path.startswith(("/passport/", "/login"))))
    if platform == "kuaishou":
        return (host == "passport.kuaishou.com"
                or host == "www.kuaishou.com" and path in {"/", "/new-reco"}
                or host == "cp.kuaishou.com" and (
                    path in {"/", "/profile", "/article/publish/video"}
                    or path.startswith(("/passport/", "/login"))))
    if platform == "shipinhao":
        return host == "channels.weixin.qq.com" and (
            path in {"/", "/platform", "/login", "/login.html"}
            or path.startswith("/login/"))
    if platform == "xhs":
        return (host == "www.xiaohongshu.com" and path in {"/", "/explore"}
                or host == "creator.xiaohongshu.com" and path in {"/", "/login"}
                or host == "passport.xiaohongshu.com")
    return False


async def login_preview_png(platform, account_id=None, *, created_after=0, context_id=None):
    """Capture the existing owned login page; never navigate or open a browser."""
    browser = _runtime().browser
    lookup = getattr(browser, "interactive_login_context", None)
    context = lookup(platform, account_id, created_after=created_after) if callable(lookup) else None
    if context is None or context_id is not None and id(context) != context_id:
        raise HTTPException(409, "登录窗口尚未就绪，请稍候")
    pages = []
    for page in reversed(list(context.pages)):
        try:
            if not page.is_closed() and _login_preview_url_allowed(platform, page.url):
                pages.append(page)
        except Exception:
            continue
    if not pages:
        raise HTTPException(409, "登录页面仍在加载，请稍候")
    # Prefer an actual passport/login tab over a platform homepage; never take
    # BrowserScan or an arbitrary tab merely because it is the newest page.
    page = max(pages, key=lambda candidate: int(
        "login" in candidate.url.lower() or "passport" in candidate.url.lower()))
    try:
        try:
            content = await asyncio.wait_for(page.screenshot(
                type="png", full_page=False, timeout=5000), timeout=6)
        except Exception:
            # Chromium's normal screenshot can wait for remote fonts or page
            # animations forever. Capture the same owned visible surface as a
            # bounded fallback, without navigating or changing the login page.
            if not _login_preview_url_allowed(platform, page.url):
                raise HTTPException(409, "登录页面已切换，请稍候")
            session = await asyncio.wait_for(context.new_cdp_session(page), timeout=1)
            try:
                frame = await asyncio.wait_for(session.send("Page.captureScreenshot", {
                    "format": "png", "fromSurface": True,
                    "captureBeyondViewport": False}), timeout=2)
                encoded = frame.get("data", "")
                if not isinstance(encoded, str) or len(encoded) > 12 * 1024 * 1024:
                    raise ValueError("Invalid preview frame")
                content = base64.b64decode(encoded, validate=True)
            finally:
                try:
                    await asyncio.wait_for(session.detach(), timeout=0.5)
                except Exception:
                    pass
        if not _login_preview_url_allowed(platform, page.url):
            raise HTTPException(409, "登录页面已切换，请稍候")
        if (not isinstance(content, bytes) or not content.startswith(b"\x89PNG\r\n\x1a\n")
                or len(content) > 8 * 1024 * 1024):
            raise HTTPException(409, "登录预览暂时无法显示")
        return content, id(context)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(409, "登录预览暂时无法显示，请稍候") from None


def _runtime():
    # Import lazily: main includes our router after creating its app.
    from . import main
    return main


def _has_auth_cookies(platform, cookies):
    names = {cookie.get("name") for cookie in cookies
             if isinstance(cookie, dict) and cookie.get("value")
             and platform_domain_allowed(platform, cookie.get("domain"))}
    if platform == "kuaishou":
        from .browser.login import _ks_web_login_ready
        return _ks_web_login_ready(names)
    return bool(names & _AUTH_COOKIES[platform])


def credential_store():
    return DownloadCredentialStore(resolve_store_root(db_path=_runtime().cfg.db_path))


def _account(account_id):
    if type(account_id) is not int or account_id <= 0:
        raise HTTPException(400, "下载账号无效")
    with get_session() as session:
        account = session.get(DouyinAccount, account_id)
        if not account:
            raise HTTPException(404, "账号不存在")
        if account.platform not in PLATFORM_DOMAINS:
            raise HTTPException(400, "暂不支持这个下载平台")
        session.expunge(account)
        return account


def _cookie_evidence(cookies):
    normalized = sorted(cookies, key=lambda cookie: (
        cookie.get("name", ""), cookie.get("domain", ""), cookie.get("path", "/")))
    return hashlib.sha256(json.dumps(normalized, sort_keys=True,
        ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def download_session_metadata(account_id):
    account = _account(account_id)
    try:
        metadata = credential_store().metadata(
            account.platform, account.id, profile_dir=account.profile_dir)
    except DownloadCredentialError:
        metadata = {"status": "unconfirmed", "enabled": True,
                    "message": "下载凭据无法读取，请重新检查登录", "cookie_count": 0}
    publish_status = ("login_required" if account.status == "invalid" else
                      "stored_unverified" if account.creator_storage_state else "unconfirmed")
    publish_verified = False
    proof_current = False
    proof = _PUBLISH_EVIDENCE.get(account.id)
    if proof is not None:
        try:
            cookies = credential_store().read_cookies(account.platform, account.id,
                                                       profile_dir=account.profile_dir)
            proof_current = bool(account.platform in {"douyin", "shipinhao", "kuaishou"}
                and proof.get("platform") == account.platform
                and time.monotonic() < proof["expires"]
                and profile_identity(account.profile_dir) == proof["profile"]
                and _cookie_evidence(cookies) == proof["cookies"])
            proof_status = proof.get("status", "ready" if proof.get("verified", True) else "unconfirmed")
            publish_verified = proof_current and proof_status == "ready"
        except DownloadCredentialError:
            pass
        if not proof_current:
            _PUBLISH_EVIDENCE.pop(account.id, None)
    if publish_verified:
        publish_status = "active"
    elif proof_current:
        publish_status = proof_status if proof_status in {
            "login_required", "network_error", "unconfirmed"} else "unconfirmed"
    from .session_observability import scope_check_metadata, session_metadata
    history = scope_check_metadata(account)
    # Known invalidity overrides historical success without inventing a new check.
    if account.status == "invalid":
        history["download_check_status"] = "login_required"
        history["publish_check_status"] = "login_required"
    elif metadata["status"] == "login_required":
        history["download_check_status"] = "login_required"
    elif metadata["status"] == "profile_changed":
        history["download_check_status"] = "unconfirmed"
    return {"id": account.id, "account_id": account.id,
            "platform": account.platform, "name": account.nickname or "未命名账号",
            "download_status": metadata["status"], "enabled": metadata.get("enabled", False),
            "download_check_status": history["download_check_status"],
            "download_checked_at": history["download_checked_at"],
            "publish_status": publish_status,
            "publish_available": publish_verified, "publish_verified": publish_verified,
            "publish_check_status": history["publish_check_status"] or (proof_status if proof_current else None),
            "publish_checked_at": history["publish_checked_at"] or (proof["checked_at"] if proof_current else None),
            "login_record_saved": bool(account.storage_state or account.creator_storage_state),
            "download_saved": bool(metadata.get("enabled")),
            "publish_saved": bool(account.creator_storage_state),
            "observability": session_metadata(account, _runtime()),
            "saved_at": metadata.get("saved_at"),
            "last_checked_at": metadata.get("last_checked_at"),
            "captured_at": metadata.get("captured_at"),
            "message": metadata["message"], "cookie_count": metadata["cookie_count"],
            "selected": metadata.get("selected", False)}


def list_download_sessions():
    with get_session() as session:
        ids = [account.id for account in session.exec(
            select(DouyinAccount).where(DouyinAccount.platform.in_(tuple(PLATFORM_DOMAINS)))
            .order_by(DouyinAccount.id)).all()]
    return {"items": [download_session_metadata(account_id) for account_id in ids],
            "available": _runtime().browser is not None,
            "service_fingerprint": hashlib.sha256(str(Path(__file__).resolve().parents[1])
                .replace("\\", "/").casefold().encode()).hexdigest()}


def _pending_account_login(account):
    return any(info.get("platform") == account.platform
               and info.get("account_id") in (None, account.id)
               and info.get("status") in {"opening", "waiting", "verification", "persisted"}
               for info in _runtime().login_tasks.values())


def _publishing_account(account_id):
    with get_session() as session:
        return session.exec(select(PublishTask.id).where(
            PublishTask.account_id == account_id, PublishTask.status == "publishing")).first() is not None


def _context_profile_owned(browser, identity, context):
    """Validate the actual manager ownership record, not only an account ID."""
    expected = Path(identity.profile_dir).expanduser().resolve()
    backend = browser.effective_browser_backend(identity)
    if backend == "fingerprint_chromium":
        runtime_id = browser.effective_fingerprint_runtime_id(identity)
        expected = browser._runtime_profile_dir(identity, runtime_id).resolve()
    session = getattr(browser, "_cdp_sessions", {}).get(identity.key)
    if session is not None:
        return (session.context is context
                and Path(session.owned.profile_dir).resolve() == expected)
    process_lock = getattr(browser, "_profile_process_locks", {}).get(identity.key)
    return process_lock is not None and process_lock.path.parent.resolve() == expected


async def checkpoint_close_download_account(account_id):
    """Save and close one exact owned account session for a controlled restart."""
    runtime = _runtime()
    if runtime.browser is None:
        raise HTTPException(503, "账号浏览器尚未启动")
    account = _account(account_id)
    if _pending_account_login(account):
        raise HTTPException(409, "该平台仍有扫码登录等待完成，请先完成或关闭扫码窗口")
    if _publishing_account(account.id):
        raise HTTPException(409, "该账号有发布任务正在执行，暂时不能关闭浏览器")
    check_lock = _CHECK_LOCKS.setdefault(account.id, asyncio.Lock())
    if check_lock.locked():
        raise HTTPException(409, "该账号正在检查下载登录，请稍后再关闭")
    async with check_lock:
        identity = runtime.browser.identity_for(account)
        lease = runtime.open_browsers.get(account.id)
        guard = runtime.browser.lock_for(f"acc:{account.id}")
        if lease is not None and lease.active:
            lookup = getattr(runtime.browser, "interactive_login_context", None)
            owned = lookup(account.platform, account.id) if callable(lookup) else None
            if (owned is not lease.context or not guard.locked()
                    or not _context_profile_owned(runtime.browser, identity, lease.context)):
                raise HTTPException(409, "账号窗口的归属已变化，请先在原窗口正常关闭")
            context = lease.context
        else:
            if guard.locked():
                raise HTTPException(409, "该账号正在执行其他操作，暂时不能关闭浏览器")
            context = getattr(runtime.browser, "_contexts", {}).get(identity.key)
            if context is None:
                return {"ok": True, "closed": False, "already_closed": True,
                        "account": download_session_metadata(account.id)}
            if not _context_profile_owned(runtime.browser, identity, context):
                raise HTTPException(409, "账号浏览器的归属已变化，请先正常关闭原窗口")

        async def checkpoint():
            # The manager callback verifies account/platform/Profile and keeps
            # publishing status unchanged. Closing flushes the native Profile.
            if account.platform in {"kuaishou", "shipinhao"}:
                if not await runtime.browser.snapshot_session(identity, context):
                    raise HTTPException(409, "登录态尚未成功保存，本次未关闭浏览器，请稍后重试")
            else:
                state = await asyncio.wait_for(context.storage_state(), timeout=5)
                capture_enabled_download_snapshot(identity, state)

        if lease is not None and lease.active:
            await checkpoint()
            await runtime._release_open_browser(account.id, lease)
        else:
            async with guard:
                # Recheck after taking the account guard: another caller may
                # have replaced or closed this context while waiting.
                if getattr(runtime.browser, "_contexts", {}).get(identity.key) is not context:
                    raise HTTPException(409, "账号窗口已切换，请重新检查")
                await checkpoint()
                await runtime.browser.close_context(identity.key)
        return {"ok": True, "closed": True, "already_closed": False,
                "account": download_session_metadata(account.id)}


def _response_verdict(platform, payload):
    """Recognize current-user business responses, never public profile cards."""
    if not isinstance(payload, dict):
        return False
    data = payload.get("data") or {}
    if platform == "douyin":
        user = payload.get("user") or (data.get("user") if isinstance(data, dict) else {}) or {}
        return payload.get("status_code") in (0, "0") and bool(
            isinstance(user, dict) and (user.get("sec_uid") or user.get("uid")))
    if platform == "kuaishou":
        from .browser.ks_fetcher import _extract_rest_profile
        profile, _keys = _extract_rest_profile(payload)
        return payload.get("result") in (1, "1") and bool(profile)
    if platform == "xhs":
        return bool(isinstance(data, dict) and data.get("guest") is not True
                    and (data.get("user_id") or data.get("red_id"))
                    and payload.get("success") is not False
                    and (payload.get("code") in (0, "0") or (
                        "code" not in payload and payload.get("success") is True)))
    if platform == "shipinhao":
        from .browser.login import channels_auth_code_ok, channels_auth_err_code
        from .browser.channels_fetcher import _dig_data, _rf
        if not channels_auth_code_ok(channels_auth_err_code(payload)):
            return False
        data = _dig_data(payload)
        finder = _rf(data, "finderUser", "finder", "finderInfo", default=None) or data
        return isinstance(finder, dict) and bool(finder.get("nickname") or finder.get("nickName"))
    return False


def _business_response_succeeded(platform, payload):
    if not isinstance(payload, dict):
        return False
    if platform == "douyin":
        return payload.get("status_code") in (0, "0")
    if platform == "kuaishou":
        return payload.get("result") in (1, "1")
    if platform == "xhs":
        return payload.get("success") is not False and (
            payload.get("code") in (0, "0") or (
                "code" not in payload and payload.get("success") is True))
    if platform == "shipinhao":
        from .browser.login import channels_auth_code_ok, channels_auth_err_code
        return channels_auth_code_ok(channels_auth_err_code(payload))
    return False


def _ks_profile_user_ids(payload):
    if not isinstance(payload, dict):
        return set()
    result = {str(payload[key]) for key in ("userId", "user_id", "uid")
              if payload.get(key) not in (None, "")}
    for key in ("data", "userProfile", "profile", "userInfo"):
        child = payload.get(key)
        if isinstance(child, dict):
            result.update(_ks_profile_user_ids(child))
    return result


async def _ks_profile_matches_context(context, payload):
    cookies = await asyncio.wait_for(context.cookies(), timeout=3)
    live_ids = {str(cookie["value"]) for cookie in cookies
                if cookie.get("name") == "userId" and cookie.get("value")
                and platform_domain_allowed("kuaishou", cookie.get("domain"))}
    return bool(live_ids and live_ids & _ks_profile_user_ids(payload))


def _is_current_user_response(platform, url):
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    if not platform_domain_allowed(platform, parsed.hostname):
        return False
    markers = {
        "douyin": "/aweme/v1/web/user/profile/self",
        "kuaishou": "/rest/v/profile/get",
        "xhs": "/api/sns/web/v2/user/me",
        "shipinhao": "/mmfinderassistant-bin/auth/",
    }
    if platform == "kuaishou" and parsed.hostname != "www.kuaishou.com":
        return False
    return markers[platform] in parsed.path


async def _checkpoint_close_probe_page(page, checkpoint_callback):
    """Save the owned tab while its sessionStorage exists, then always close it."""
    try:
        if checkpoint_callback is not None:
            try:
                await asyncio.wait_for(checkpoint_callback(), timeout=_PROBE_CHECKPOINT_TIMEOUT_SECONDS)
            except Exception:
                pass  # Optional persistence never becomes authentication proof.
    finally:
        try:
            await asyncio.wait_for(page.close(), timeout=3)
        except Exception:
            pass


async def _probe_download_scope(context, account, *, response_timeout=8, checkpoint_callback=None):
    """One bounded web-scope check, independent of creator/publish status."""
    page = await context.new_page()
    observed = asyncio.Event()
    evidence = {"success": False, "conflict": False}
    callbacks = set()

    async def handle(response):
        if not _is_current_user_response(account.platform, response.url):
            return
        try:
            if not 200 <= response.status < 300:
                evidence["conflict"] = True
                return
            payload = await asyncio.wait_for(response.json(), timeout=3)
            if _response_verdict(account.platform, payload):
                if account.platform != "kuaishou" or await _ks_profile_matches_context(context, payload):
                    evidence["success"] = True
                    observed.set()
                else:
                    # profile/get can return a public profile; only the live
                    # account's userId makes it evidence of our own login.
                    evidence["conflict"] = True
            elif not _business_response_succeeded(account.platform, payload):
                evidence["conflict"] = True
            # A successful auth bootstrap may deliberately contain no user
            # profile. It is neutral: wait for the later get_auth_info reply,
            # rather than ending observation or declaring a contradiction.
        except Exception:
            evidence["conflict"] = True

    def received(response):
        task = asyncio.create_task(handle(response))
        callbacks.add(task)
        task.add_done_callback(callbacks.discard)

    page.on("response", received)
    try:
        await page.goto(_HOME[account.platform], wait_until="domcontentloaded", timeout=30000)
        try:
            await asyncio.wait_for(observed.wait(), timeout=response_timeout)
        except asyncio.TimeoutError:
            pass
        if callbacks:
            await asyncio.wait_for(asyncio.gather(*list(callbacks), return_exceptions=True), timeout=4)
        final = urlsplit(page.url or "")
        login_url = "passport" in (final.hostname or "") or "login" in final.path.lower()
        if evidence["success"] and not evidence["conflict"] and not login_url:
            cookies = await context.cookies()
            if _has_auth_cookies(account.platform, cookies):
                return "ready"
        if login_url and not evidence["success"]:
            return "login_required"
        try:
            locator = page.get_by_text("登录", exact=True).first
            if await locator.is_visible(timeout=1200) and not evidence["success"]:
                return "login_required"
        except Exception:
            pass
        return "unconfirmed"
    except asyncio.CancelledError:
        raise
    except Exception:
        return "network_error"
    finally:
        try:
            for task in list(callbacks):
                task.cancel()
            if callbacks:
                await asyncio.gather(*list(callbacks), return_exceptions=True)
        finally:
            await _checkpoint_close_probe_page(page, checkpoint_callback)


_DOUYIN_CREATOR_CONTROLS = r"""() => {
    const visible = node => Boolean(node && node.getClientRects().length &&
        getComputedStyle(node).visibility !== 'hidden');
    const enabled = node => !node.disabled && node.getAttribute('aria-disabled') !== 'true';
    const videoInput = [...document.querySelectorAll('input[type="file"]')].some(node =>
        enabled(node) && /(?:video\/|\.(?:mp4|mov|avi|mkv|webm)(?:,|$))/i.test(node.accept || ''));
    const uploadControl = [...document.querySelectorAll('button, [role="button"], label')].some(node =>
        visible(node) && enabled(node) && /^(?:上传视频|选择视频|上传文件|选择文件|点击上传|开始上传)$/.test(
            (node.innerText || node.textContent || '').trim()));
    const editorControl = [...document.querySelectorAll(
        'input[placeholder*="填写作品标题"], input[placeholder*="作品标题"], ' +
        '.editor-kit-editor-container [contenteditable="true"]')].some(node => visible(node) && enabled(node));
    return {videoInput, uploadControl, editorControl};
}"""


async def _probe_douyin_publish_scope(context, *, response_timeout=8, checkpoint_callback=None):
    """Read the creator upload form without selecting files or submitting anything.

    A creator URL or generic page text is never positive authentication evidence.
    The video file input must coexist with an actionable uploader/editor control.
    """
    from .platforms.douyin import publish as pub

    page = None
    try:
        page = await asyncio.wait_for(context.new_page(), timeout=2)
        deadline = time.monotonic() + max(0, response_timeout)
        response = await page.goto(pub.UPLOAD_URL, wait_until="domcontentloaded", timeout=8000)
        while True:
            if await pub._logged_out(page):
                return "login_required"
            if response is not None and not 200 <= response.status < 400:
                return "network_error"
            final = urlsplit(page.url)
            if final.hostname != "creator.douyin.com" or not final.path.startswith("/creator-micro/content/"):
                return "unconfirmed"
            controls = await asyncio.wait_for(page.evaluate(_DOUYIN_CREATOR_CONTROLS), timeout=1)
            if (isinstance(controls, dict) and controls.get("videoInput") is True
                    and (controls.get("uploadControl") is True or controls.get("editorControl") is True)):
                return "ready"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "unconfirmed"
            await asyncio.sleep(min(0.25, remaining))
    except asyncio.CancelledError:
        raise
    except Exception:
        return "network_error"
    finally:
        if page is not None:
            await _checkpoint_close_probe_page(page, checkpoint_callback)


async def _probe_kuaishou_publish_scope(context, *, response_timeout=8, checkpoint_callback=None):
    """Read CP account info only; no upload, publish or login clicks."""
    try:
        page = await context.new_page()
    except Exception:
        return False
    observed = asyncio.Event()
    evidence = {"success": False, "conflict": False}
    callbacks = set()

    async def handle(response):
        try:
            parsed = urlsplit(response.url)
        except ValueError:
            return
        if parsed.hostname != "cp.kuaishou.com" or parsed.path not in {
                "/rest/cp/creator/pc/home/info", "/rest/cp/creator/pc/home/infoV2"}:
            return
        try:
            if not 200 <= response.status < 300:
                evidence["conflict"] = True
                return
            payload = await asyncio.wait_for(response.json(), timeout=3)
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(payload, dict) or payload.get("result") not in (1, "1"):
                evidence["conflict"] = True
            elif isinstance(data, dict) and (data.get("userName") or data.get("user_name")):
                if await _ks_profile_matches_context(context, data):
                    evidence["success"] = True
                    observed.set()
                else:
                    evidence["conflict"] = True
        except Exception:
            evidence["conflict"] = True

    def received(response):
        task = asyncio.create_task(handle(response))
        callbacks.add(task)
        task.add_done_callback(callbacks.discard)

    page.on("response", received)
    try:
        await page.goto("https://cp.kuaishou.com/", wait_until="domcontentloaded", timeout=8000)
        try:
            await asyncio.wait_for(observed.wait(), timeout=response_timeout)
        except asyncio.TimeoutError:
            pass
        if callbacks:
            await asyncio.wait_for(asyncio.gather(*list(callbacks), return_exceptions=True), timeout=3)
        final = urlsplit(page.url)
        return bool(evidence["success"] and not evidence["conflict"]
                    and final.hostname == "cp.kuaishou.com"
                    and "login" not in final.path.lower() and "passport" not in final.path.lower())
    except asyncio.CancelledError:
        raise
    except Exception:
        return False
    finally:
        try:
            for task in list(callbacks):
                task.cancel()
            if callbacks:
                await asyncio.gather(*list(callbacks), return_exceptions=True)
        finally:
            await _checkpoint_close_probe_page(page, checkpoint_callback)


@asynccontextmanager
async def _download_context(account, identity):
    runtime = _runtime()
    lease = runtime.open_browsers.get(account.id)
    if lease is not None and lease.active:
        # The existing lease already reserves this account's Profile. Taking
        # that same non-reentrant guard again would deadlock the Check button.
        yield lease.context
        return
    if runtime.engine is not None:
        from .risk import OperationKind
        async with runtime.engine.operation_guard(
                account.id, OperationKind.READ_LIGHT,
                fallback_key=f"download-session:{account.id}", operation_target=identity):
            yield await runtime.browser.context_for(identity)
        return
    async with runtime.browser.lock_for(f"acc:{account.id}"):
        yield await runtime.browser.context_for(identity)


async def refresh_download_session(account_id):
    """Verify the download scope and persist the current owned browser session.

    Native pages checkpoint rotated state before closing;
    persistence is separate from login proof and does not change account status,
    inject cookies, extend their lifetime, or copy a browser Profile.
    """
    runtime = _runtime()
    if runtime.browser is None:
        raise HTTPException(503, "账号浏览器尚未启动，请启动发布服务")
    account = _account(account_id)
    lock = _CHECK_LOCKS.setdefault(account.id, asyncio.Lock())
    operation_started = time.monotonic()

    async def run():
        async with lock:
            identity = runtime.browser.identity_for(account)
            async with _download_context(account, identity) as context:
                probe_options = {}
                snapshotter = getattr(runtime.browser, "snapshot_session", None)
                if account.platform in {"kuaishou", "shipinhao"} and callable(snapshotter):
                    async def checkpoint():
                        return await snapshotter(identity, context)
                    probe_options["checkpoint_callback"] = checkpoint
                status = await _probe_download_scope(context, account, **probe_options)
                from .session_observability import record_scope_check
                record_scope_check(account, "download", status)
                if account.platform == "shipinhao":
                    # Channels uses the same creator authentication response for both scopes.
                    record_scope_check(account, "publish", status)
                if status == "ready":
                    publish_status = "ready" if account.platform == "shipinhao" else "unconfirmed"
                    if account.platform in {"douyin", "kuaishou"}:
                        cp_budget = min(10, max(0, 48 - (time.monotonic() - operation_started)))
                        if cp_budget > 0:
                            try:
                                if account.platform == "douyin":
                                    douyin_options = {}
                                    if callable(getattr(context, "storage_state", None)):
                                        async def checkpoint_douyin():
                                            state = await context.storage_state()
                                            return capture_enabled_download_snapshot(identity, state)
                                        douyin_options["checkpoint_callback"] = checkpoint_douyin
                                    publish_status = await asyncio.wait_for(
                                        _probe_douyin_publish_scope(context, **douyin_options), timeout=cp_budget)
                                else:
                                    publish_verified = await asyncio.wait_for(
                                        _probe_kuaishou_publish_scope(context, **probe_options), timeout=cp_budget)
                                    publish_status = "ready" if publish_verified else "unconfirmed"
                            except asyncio.TimeoutError:
                                publish_status = "network_error" if account.platform == "douyin" else "unconfirmed"
                            record_scope_check(account, "publish", publish_status)
                    cookies = await asyncio.wait_for(context.cookies(), timeout=5)
                    credential_store().save(
                        account.platform, account.id, cookies,
                        user_agent=identity.ua, proxy=identity.proxy,
                        verified=True, profile_dir=identity.profile_dir)
                    if account.platform in {"douyin", "shipinhao", "kuaishou"}:
                        _PUBLISH_EVIDENCE[account.id] = {
                            "platform": account.platform, "verified": publish_status == "ready",
                            "status": publish_status,
                            "expires": time.monotonic() + 300,
                            "profile": profile_identity(identity.profile_dir),
                            "cookies": _cookie_evidence(credential_store().read_cookies(
                                account.platform, account.id, profile_dir=identity.profile_dir)),
                            "checked_at": credential_store().metadata(
                                account.platform, account.id)["last_checked_at"]}
                else:
                    _PUBLISH_EVIDENCE.pop(account.id, None)
                    credential_store().update_status(account.platform, account.id, status,
                                                     profile_dir=identity.profile_dir)
            return download_session_metadata(account.id)
    try:
        return await asyncio.wait_for(run(), timeout=55)
    except asyncio.TimeoutError:
        raise HTTPException(409, "账号正被其他操作占用或检查超时，请稍后重试") from None
    except DownloadCredentialError as error:
        raise HTTPException(400, str(error)) from None


async def open_download_login(account_id):
    account = _account(account_id)
    runtime = _runtime()
    # The ordinary account window preserves current cookies and allows the
    # account owner to log in. Saving/verification is a separate Check action.
    result = await runtime.open_account_browser(
        account.id, url=_HOME[account.platform], preserve_publish_status=True)
    return {**result, "account_id": account.id,
            "message": "请在账号窗口完成登录，再点击检查并保存下载登录"}


def select_download_session(account_id):
    account = _account(account_id)
    store = credential_store()
    store.read_record(account.platform, account.id, profile_dir=account.profile_dir)
    store.select(account.platform, account.id)
    return download_session_metadata(account.id)


def capture_enabled_download_snapshot(identity, state):
    """Update only opted-in same-profile download sessions; never mark them live."""
    if not identity.account_id or identity.platform not in PLATFORM_DOMAINS:
        return False
    try:
        account = _account(identity.account_id)
        store = credential_store()
        if account.platform != identity.platform or profile_identity(account.profile_dir) != profile_identity(identity.profile_dir):
            return False
        cookies = state.get("cookies", []) if isinstance(state, dict) else []
        if not _has_auth_cookies(identity.platform, cookies):
            return False
        return store.refresh_snapshot(identity.platform, identity.account_id, cookies,
                                      user_agent=identity.ua, proxy=identity.proxy,
                                      profile_dir=identity.profile_dir)
    except Exception:
        return False
