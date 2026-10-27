"""交互式扫码登录:打开真实浏览器窗口,用户扫码,落地登录态。
对应原项目 internal/douyin.QRLoginManager(chromedp 版)。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

from .identity import Identity
from .manager import BrowserManager

_LOG = logging.getLogger(__name__)


def _now() -> float:
    """单调时钟(抽成函数便于离线测试注入假时钟)。"""
    return time.monotonic()

# 登录后才会出现的 Cookie(用于判断是否已登录)
_LOGIN_COOKIES = {"sessionid", "sessionid_ss", "sid_tt", "uid_tt", "sid_guard"}


async def _focus(page):
    """把扫码窗口提到前台(否则有头浏览器常开在其它窗口后面)。"""
    try:
        await page.bring_to_front()
    except Exception:
        pass


async def _open_first_environment_check(
        mgr: BrowserManager, identity: Identity, ctx) -> None:
    """Best-effort first-run diagnostic; never block the platform login flow."""
    opener = getattr(mgr, "open_environment_check", None)
    if not callable(opener):
        return
    try:
        await opener(identity, context=ctx)
    except Exception as exc:
        _LOG.warning("Fingerprint environment check page failed to open: %r", exc)


async def _reuse_or_create_login_page(ctx):
    """兼容旧调用：复用持久 Context 的空白页，否则创建一个新页。"""
    for candidate in ctx.pages:
        try:
            if candidate.url == "about:blank" and not candidate.is_closed():
                return candidate
        except Exception:
            continue
    return await ctx.new_page()


async def _pause_login_checkpoints(mgr, ctx):
    """Do not persist guest/intermediate QR state before the login commits."""
    pause = getattr(mgr, "pause_session_checkpoints", None)
    resume = getattr(mgr, "resume_session_checkpoints", None)
    if not callable(pause) or not callable(resume):
        return None  # Compatibility with older browser adapters.
    try:
        await pause(ctx)
    except BaseException:
        # pause sets its guard before draining an already-running capture.
        # Cancellation during that await must release the same guard.
        resume(ctx)
        raise
    return resume


async def _confirmed_login_state_json(mgr, identity, ctx):
    """Freeze confirmed state for DB commit and replace an older handoff cache.

    Called only after the platform's existing login confirmation. Capture stays
    side-effect free; remembering here never invokes the persistence callback.
    """
    capture = getattr(mgr, "capture_session_state", None)
    state = await capture(identity, ctx) if callable(capture) else await ctx.storage_state()
    serialized = json.dumps(state)
    remember = getattr(mgr, "remember_session_state", None)
    if callable(remember):
        remember(identity, state)
    return serialized


async def _restore_login_cookies(ctx, cookies, platform):
    # Exact rollback removes partial credentials written during an abandoned
    # QR flow. A failed add gets one bounded retry after clearing again.
    for attempt in range(2):
        try:
            await ctx.clear_cookies()
            await ctx.add_cookies(cookies)
            return
        except Exception as exc:
            _LOG.warning("[%s-login] 回滚旧 Cookie 失败(第 %d 次): %s",
                         platform, attempt + 1, type(exc).__name__)


async def _close_login_context(ctx, resume):
    try:
        try:
            await ctx.close()
        except Exception:
            pass
    finally:
        if resume is not None:
            resume(ctx)


async def _douyin_login_panel_visible(page) -> bool:
    """发现登录/验证面板后只等待用户，不点击其中的验证或协议控件。"""
    for text in (
        "扫码登录", "二维码登录", "打开抖音扫码登录", "请使用抖音扫码登录",
        "验证码登录", "手机验证码登录", "短信验证码登录", "安全验证",
    ):
        try:
            loc = page.get_by_text(text, exact=True)
            for index in range(min(await loc.count(), 8)):
                if await loc.nth(index).is_visible():
                    return True
        except Exception:
            continue
    return False


async def _expand_douyin_login_panel(page) -> bool:
    """首页水合期间有界重试可见的登录入口，避免严格匹配多个隐藏副本。"""
    deadline = _now() + 8.0
    next_click_round = 0
    for round_index in range(16):
        if page.is_closed() or _now() >= deadline:
            return False
        if await _douyin_login_panel_visible(page):
            return True
        if round_index >= next_click_round:
            # 精确文案优先；逐个检查可见性，不使用可能严格匹配多个节点的 page.click。
            factories = (
                lambda: page.get_by_text("登录", exact=True),
                lambda: page.get_by_role("button", name="登录", exact=True),
                lambda: page.locator('[data-e2e="login-button"]'),
            )
            clicked = False
            for make_locator in factories:
                try:
                    loc = make_locator()
                    for index in range(min(await loc.count(), 8)):
                        if _now() >= deadline:
                            return False
                        candidate = loc.nth(index)
                        if not await candidate.is_visible():
                            continue
                        try:
                            await candidate.click(timeout=600)
                        except Exception:
                            continue
                        clicked = True
                        # 点击已被接受后留出一次水合机会，再判断是否需要重试。
                        next_click_round = round_index + 2
                        break
                except Exception:
                    continue
                if clicked:
                    break
        if round_index < 15:
            await asyncio.sleep(0.5)
    return await _douyin_login_panel_visible(page)


async def interactive_login(mgr: BrowserManager, identity: Identity,
                            timeout_seconds: int = 180,
                            start_url: str = "https://www.douyin.com/",
                            force_reauth: bool = False,
                            ) -> Tuple[bool, str, str]:
    """返回 (是否成功, storage_state_json, nickname)。
    在账号专属持久 profile(独立 UA/视口/时区/代理/指纹)里有头扫码,
    登录态直接落盘到该 profile;同时返回 storage_state 供库内展示/兜底。
    start_url 用 creator.douyin.com 即为创作中心登录(其登录态因 .douyin.com 共享 Cookie,
    同样可用于 www 公开抓取)。"""
    ctx = await mgr.open_headed(identity)
    if force_reauth:
        # “重新登录”必须从干净的认证态开始。持久 profile 和数据库快照里可能
        # 仍保存着已被服务端撤销的 sessionid；若不先清掉，下面仅按 Cookie 名
        # 轮询会在窗口刚打开时把旧 Cookie 误判为扫码成功。
        await ctx.clear_cookies()
    await _open_first_environment_check(mgr, identity, ctx)
    page = await ctx.new_page()
    await _focus(page)
    logged = False
    nickname = ""
    state_json = ""

    try:
        await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
        await _focus(page)
        await _expand_douyin_login_panel(page)

        # 轮询登录态(用户关窗 -> 立即视为未登录,不抛错)
        waited = 0.0
        while waited < timeout_seconds:
            if page.is_closed():
                break
            try:
                cookies = await ctx.cookies()
            except Exception:
                break
            names = {c["name"] for c in cookies}
            if names & _LOGIN_COOKIES:
                # Cookie 写入后再确认页面已离开登录态。扫码弹窗尚在时继续等，
                # 避免平台刚轮换游客/旧 Cookie 就提前结束登录流程。
                try:
                    login_visible = await page.get_by_text(
                        "登录", exact=True).first.is_visible(timeout=500)
                except Exception:
                    login_visible = None
                current_url = str(page.url or "").lower()
                if login_visible is not True and "passport" not in current_url \
                        and "/login" not in current_url:
                    logged = True
                    break
            # 扫码确认后尽快通知主页面；Cookie 查询很轻量，500ms 足够且比原来的
            # 2 秒轮询明显更跟手。
            await asyncio.sleep(0.5)
            waited += 0.5

        if logged:
            await page.wait_for_timeout(800)   # 给登录跳转/localStorage 一次落盘机会
            state = await ctx.storage_state()
            state_json = json.dumps(state)
            nickname = await _read_nickname(page)
    finally:
        try:
            await ctx.close()
        except Exception:
            pass

    return logged, state_json, nickname


async def interactive_creator_login(mgr: BrowserManager, identity: Identity,
                                    timeout_seconds: int = 180,
                                    force_reauth: bool = False):
    """创作中心登录。返回 (ok, storage_state_json, nickname)。"""
    return await interactive_login(
        mgr, identity, timeout_seconds,
        start_url="https://creator.douyin.com/",
        force_reauth=force_reauth,
    )


# 创作服务平台登录后才会写入的 Cookie(发布需要)
_XHS_CREATOR_COOKIES = {"customerClientId", "galaxy_creator_session_id",
                        "access-token-creator.xiaohongshu.com", "customer-sso-sid"}


class XhsSecurityVerificationRequired(RuntimeError):
    """小红书将当前登录导航到了设备安全验证页。"""


def _is_xhs_security_verification_url(url: str) -> bool:
    """识别小红书设备验证页和已知的 IP 风险错误页。"""
    try:
        parsed = urlparse(str(url or ""))
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if host != "xiaohongshu.com" and not host.endswith(".xiaohongshu.com"):
        return False
    if parsed.path.rstrip("/").lower() == "/website-login/captcha":
        return True
    return "300012" in parse_qs(parsed.query).get("error_code", [])


async def _xhs_web_session(ctx) -> str:
    """取当前 web_session cookie 值；游客态也可能存在且发生轮换。"""
    try:
        for c in await ctx.cookies():
            if c["name"] == "web_session":
                return c.get("value", "") or ""
    except Exception:
        pass
    return ""


_XHS_USER_ME_API = "/api/sns/web/v2/user/me"
_XHS_QRCODE_STATUS_API = "/api/sns/web/v1/login/qrcode/status"
_XHS_IDENTITY_RECHECK_DELAY_SECONDS = 2.0
_XHS_PAGE_IDENTITY_POLL_SECONDS = 1.0

_XHS_PAGE_IDENTITY_JS = """() => {
  try {
    const marker = 'window.__INITIAL_STATE__=';
    let state = window.__INITIAL_STATE__;
    if (!state || !Object.keys(state).length) {
      for (const script of document.scripts) {
        const text = script.textContent || '';
        const at = text.indexOf(marker);
        if (at < 0) continue;
        try {
          state = (new Function(
            'return (' + text.slice(at + marker.length) + ')'))();
        } catch (_) { state = null; }
        break;
      }
    }
    const unwrap = (input) => {
      let value = input;
      for (let i = 0; i < 3 && value && typeof value === 'object'; i++) {
        if (value._rawValue !== undefined) value = value._rawValue;
        else if (value._value !== undefined) value = value._value;
        else break;
      }
      return value;
    };
    const root = unwrap((state || {}).user) || {};
    const candidates = [
      root.userInfo, root.loginUser, root.currentUser, root.me,
      root.userPageData, root.info
    ];
    for (let candidate of candidates) {
      candidate = unwrap(candidate);
      if (!candidate || typeof candidate !== 'object') continue;
      const basic = unwrap(candidate.basicInfo || candidate.basic_info) || {};
      const userId = candidate.userId || candidate.user_id ||
        basic.userId || basic.user_id || '';
      const redId = candidate.redId || candidate.red_id ||
        basic.redId || basic.red_id || '';
      if (!userId && !redId) continue;
      return {
        user_id: String(userId || ''),
        red_id: String(redId || ''),
        nickname: String(candidate.nickname || candidate.nickName ||
          basic.nickname || basic.nickName || ''),
        guest: candidate.guest === true
      };
    }
    return null;
  } catch (_) { return null; }
}"""


async def _xhs_page_identity(page) -> dict:
    try:
        value = await page.evaluate(_XHS_PAGE_IDENTITY_JS)
    except Exception:
        return {}
    if not isinstance(value, dict) or value.get("guest") is True:
        return {}
    if not (value.get("user_id") or value.get("red_id")):
        return {}
    return value


def _xhs_login_response_handler(
        authenticated_user: dict, login_signals: dict | None = None):
    async def on_response(response):
        try:
            parsed = urlparse(str(response.url or ""))
            host = (parsed.hostname or "").lower()
            if not (host == "xiaohongshu.com"
                    or host.endswith(".xiaohongshu.com")):
                return
            if int(response.status) != 200:
                return
            payload = await response.json()
            path = parsed.path.rstrip("/").lower()
            if path == _XHS_QRCODE_STATUS_API:
                data = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(data, dict):
                    data = payload if isinstance(payload, dict) else {}
                code_status = data.get("codeStatus", data.get("code_status"))
                try:
                    code_status = int(code_status)
                except (TypeError, ValueError):
                    code_status = -1
                # Current XHS web client maps 0=waiting, 1=scanned,
                # 2=login completed, 3=expired and emits onLogin for status 2.
                if code_status == 2 and login_signals is not None:
                    login_signals["qr_confirmed"] = True
                    _LOG.info("XHS QR login confirmed by qrcode/status")
                return
            if path != _XHS_USER_ME_API:
                return
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict) or data.get("guest") is True:
                return
            if not (data.get("user_id") or data.get("red_id")):
                return
            authenticated_user.update(data)
        except Exception:
            return
    return on_response


async def interactive_xhs_login(mgr: BrowserManager, identity: Identity,
                                timeout_seconds: int = 180,
                                force_reauth: bool = False,
                                status_callback=None,
                                ) -> Tuple[bool, str, str]:
    """小红书扫码登录。打开真实窗口让用户扫码,落地登录态。
    返回 (是否成功, storage_state_json, nickname)。

    判定登录:必须同时观察到有效 web_session，以及主站 user/me 返回非游客用户身份。
    游客态 web_session 和登录弹窗 Cookie 都可能在扫码前生成或轮换，不能单独作为
    成功信号。用户中途关掉窗口则视为未登录。"""
    ctx = await mgr.context_for(identity)
    if force_reauth:
        await ctx.clear_cookies()
    await _open_first_environment_check(mgr, identity, ctx)
    logged = False
    nickname = ""
    state_json = ""
    security_verification_seen = False
    authenticated_user: dict = {}
    login_signals: dict = {}
    on_response = _xhs_login_response_handler(
        authenticated_user, login_signals)
    observed_pages: set[int] = set()

    def observe(candidate) -> None:
        marker = id(candidate)
        if marker in observed_pages:
            return
        observed_pages.add(marker)
        try:
            candidate.on("response", on_response)
        except Exception:
            pass

    def context_pages(fallback) -> list:
        pages = getattr(ctx, "pages", ())
        if not isinstance(pages, (list, tuple)):
            pages = ()
        result = [candidate for candidate in pages if candidate is not None]
        if fallback is not None and fallback not in result:
            result.append(fallback)
        return result

    def usable_page(fallback):
        # A user may open the homepage manually in a second tab after the first
        # clean-Profile navigation receives device verification.  Follow that
        # real tab instead of keeping the login task pinned to the captcha tab.
        for candidate in reversed(context_pages(fallback)):
            try:
                current = str(candidate.url or "")
                parsed = urlparse(current)
                host = (parsed.hostname or "").lower()
                if host != "xiaohongshu.com" and not host.endswith(
                        ".xiaohongshu.com"):
                    continue
                if _is_xhs_security_verification_url(current):
                    continue
                if "passport" in current.lower():
                    continue
                return candidate
            except Exception:
                continue
        return fallback

    async def report_status(url: str) -> None:
        if not callable(status_callback):
            return
        try:
            result = status_callback(url)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass

    security_notified = False
    security_cleared_notified = False
    last_rechecked_session = ""
    next_identity_recheck_at = 0.0
    next_page_identity_poll_at = 0.0
    async with mgr.visible_page(identity) as page:
        await _focus(page)
        observe(page)
        context_on = getattr(ctx, "on", None)
        if callable(context_on):
            try:
                context_on("page", observe)
            except Exception:
                pass
        # 从官网首页进入登录流程。直接访问 /explore 会让全新隔离 profile
        # 更容易被重定向到 website-login/captcha 的设备安全验证页。
        await page.goto(
            "https://www.xiaohongshu.com/",
            wait_until="domcontentloaded", timeout=30000)
        security_verification_seen = _is_xhs_security_verification_url(page.url)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0, timeout_seconds)
        while loop.time() < deadline:
            if page.is_closed():                  # 没登录就关了窗口 -> 视为未登录
                break
            for candidate in context_pages(page):
                observe(candidate)
            security_verification_seen = (
                security_verification_seen
                or _is_xhs_security_verification_url(page.url)
            )
            if security_verification_seen and not security_notified:
                security_notified = True
                _LOG.info("XHS device verification detected: %s", page.url)
                await report_status(str(page.url or ""))
            active_page = usable_page(page)
            active_url = str(getattr(active_page, "url", "") or "")
            # Device verification is an explicit platform decision.  Keep the
            # visible page available for the account owner, but never navigate
            # around it or issue automated recovery retries.
            if (security_notified and not security_cleared_notified
                    and not _is_xhs_security_verification_url(active_url)
                    and "xiaohongshu.com" in active_url.lower()
                    and "passport" not in active_url.lower()):
                security_cleared_notified = True
                await report_status(active_url)
            ws = await _xhs_web_session(ctx)
            # The QR flow can update web_session without issuing user/me again
            # in the tab that was already on /explore.  Cookie alone is not a
            # success signal because guests also receive web_session.  When
            # its value changes, visibly reload the healthy XHS page once so
            # the site's own startup request supplies an authoritative
            # guest/non-guest user/me response to our existing listener.
            if (ws and len(ws) >= 20 and not authenticated_user
                    and ws != last_rechecked_session
                    and loop.time() >= next_identity_recheck_at
                    and "xiaohongshu.com" in active_url.lower()
                    and "passport" not in active_url.lower()
                    and not _is_xhs_security_verification_url(active_url)):
                last_rechecked_session = ws
                next_identity_recheck_at = (
                    loop.time() + _XHS_IDENTITY_RECHECK_DELAY_SECONDS)
                try:
                    _LOG.info(
                        "XHS web_session changed; reloading page to verify identity")
                    await active_page.reload(
                        wait_until="domcontentloaded", timeout=30000)
                    active_url = str(active_page.url or "")
                except Exception as exc:
                    _LOG.warning("XHS identity recheck reload failed: %r", exc)
            # Some successful QR flows update the page's reactive current-user
            # state but neither rotate web_session nor emit another user/me
            # request.  Read only the dedicated current-user branch from the
            # page state; requiring user_id/red_id avoids treating feed authors
            # or a guest web_session as the logged-in account.
            if (not authenticated_user
                    and loop.time() >= next_page_identity_poll_at
                    and "xiaohongshu.com" in active_url.lower()
                    and "passport" not in active_url.lower()
                    and not _is_xhs_security_verification_url(active_url)):
                next_page_identity_poll_at = (
                    loop.time() + _XHS_PAGE_IDENTITY_POLL_SECONDS)
                page_user = await _xhs_page_identity(active_page)
                if page_user:
                    authenticated_user.update(page_user)
                    _LOG.info(
                        "XHS authenticated identity found in page state: %s",
                        page_user.get("user_id") or page_user.get("red_id"))
            # Cookie 只作必要条件；user/me 的非游客身份才是授权完成证据。
            identity_confirmed = bool(
                authenticated_user or login_signals.get("qr_confirmed"))
            if (ws and len(ws) >= 20 and identity_confirmed
                    and "passport" not in active_url
                    and not _is_xhs_security_verification_url(active_url)):
                try:
                    state_json = json.dumps(await ctx.storage_state())
                    logged = True
                except Exception:
                    pass
                if logged:
                    try:
                        identity.observed_login_profile = dict(
                            authenticated_user or {})
                    except Exception:
                        pass
                    nickname = str(
                        authenticated_user.get("nickname") or "").strip()[:40]
                    if not nickname:
                        try:
                            nickname = await _read_xhs_nickname(active_page)
                        except Exception:
                            pass
                    # 普通登录只保存主站读取态。创作平台是独立登录入口，避免在
                    # 扫码完成后跨站跳转导致 Chromium 周期性拉起临时页签。
                    break
            await mgr.xhs_interaction.pause(0.70, 1.15)
    if not logged and security_verification_seen:
        raise XhsSecurityVerificationRequired(
            "小红书要求完成设备安全验证；请保持当前网络和账号环境稳定，"
            "重新打开登录窗口后按页面提示验证"
        )
    return logged, state_json, nickname


async def interactive_xhs_creator_login(mgr: BrowserManager, identity: Identity,
                                        timeout_seconds: int = 180,
                                        force_reauth: bool = False,
                                        ) -> Tuple[bool, str, str]:
    """小红书「创作服务平台」登录(发布/已发布列表用)。打开 creator.xiaohongshu.com/login
    扫码,落地含创作者会话的登录态。返回 (是否成功, storage_state_json, nickname)。
    与普通登录区分:这里登录的是创作平台,登录态里含 customerClientId / galaxy_creator_session_id 等。"""
    ctx = await mgr.context_for(identity)
    if force_reauth:
        await ctx.clear_cookies()
    await _open_first_environment_check(mgr, identity, ctx)
    logged = False
    nickname = ""
    state_json = ""
    async with mgr.visible_page(identity) as page:
        await _focus(page)
        await page.goto(
            "https://creator.xiaohongshu.com/login",
            wait_until="domcontentloaded", timeout=30000)
        init_ws = await _xhs_web_session(ctx)
        deadline = asyncio.get_running_loop().time() + max(0, timeout_seconds)
        while asyncio.get_running_loop().time() < deadline:
            if page.is_closed():
                break
            cookies = await ctx.cookies()
            names = {c["name"] for c in cookies}
            ws = next((c.get("value", "") for c in cookies if c["name"] == "web_session"), "")
            # 创作平台登录成功:出现创作者专属 Cookie,或离开 /login 且 web_session 变为有效
            on_creator = "creator.xiaohongshu.com" in page.url and "/login" not in page.url
            if (names & _XHS_CREATOR_COOKIES) or \
                    (on_creator and ws and len(ws) >= 20 and ws != init_ws):
                try:
                    state_json = json.dumps(await ctx.storage_state())
                    logged = True
                except Exception:
                    pass
                if logged:
                    try:
                        nickname = await _read_xhs_nickname(page)
                    except Exception:
                        pass
                    break
            await mgr.xhs_interaction.pause(0.70, 1.15)
    return logged, state_json, nickname


# ── 快手登录 ──
# 快手主站根路径在未登录的新浏览器里偶尔只返回一段 ``result=2`` JSON，
# 不会渲染登录入口；新版推荐页才是稳定的 Web 登录落点。
_KS_HOME_URL = "https://www.kuaishou.com/new-reco"
# 登录判定:passToken 是强信号；新版主站也会写 webday7_st，旧版则是 web_st。
_KS_LOGIN_COOKIES = {
    "passToken", "userId", "kuaishou.server.web_st",
    "kuaishou.server.webday7_st",
}
# 创作平台(cp.kuaishou.com)登录后才会写入的 Cookie(发布需要)
_KS_CREATOR_COOKIES = {"kuaishou.web.cp.api_st", "kuaishou.web.cp.api_ph"}

_KS_WEB_LOGIN_BUTTONS = (
    '[role="button"].sidebar-login-button',
    'span[role="button"]:has-text("登录")',
    'button:has-text("登录")',
    '[class*="login-button"]',
)
_KS_CREATOR_LOGIN_BUTTONS = (
    'button:has-text("立即登录")',
    '[role="button"]:has-text("立即登录")',
    'text=立即登录',
    'button:has-text("登录")',
)


def _ks_web_login_ready(cookie_names) -> bool:
    """兼容当前 webday7_st 与旧 web_st 的快手主站登录态。"""
    names = set(cookie_names or ())
    if "passToken" in names:
        return True
    has_web_st = any(
        name in {"web_st", "kuaishou.server.web_st"}
        or name.endswith(".webday7_st")
        for name in names
    )
    return "userId" in names and has_web_st


async def _click_ks_login_button(page, selectors) -> bool:
    """只点击可见的登录按钮，避免旧的 ``[class*=login]`` 点中整块容器。"""
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for index in range(await loc.count()):
                candidate = loc.nth(index)
                if not await candidate.is_visible():
                    continue
                await candidate.click(timeout=3000)
                return True
        except Exception:
            continue
    return False


async def interactive_ks_login(mgr: BrowserManager, identity: Identity,
                               timeout_seconds: int = 180,
                               start_url: str = _KS_HOME_URL,
                               force_reauth: bool = False,
                               ) -> Tuple[bool, str, str]:
    """快手扫码登录。打开真实窗口让用户扫码,落地登录态。
    返回 (是否成功, storage_state_json, nickname)。
    判定登录:出现 userId + web_st/passToken(游客态没有)。用户中途关窗视为未登录。
    ⚠️ 选择器/登录态 Cookie 名随快手改版可能变化,集中在 _KS_LOGIN_COOKIES。"""
    ctx = await mgr.open_headed(identity)
    logged = False
    committed = False
    backup_cookies = []
    resume = None
    nickname = ""
    state_json = ""
    try:
        resume = await _pause_login_checkpoints(mgr, ctx)
        if force_reauth:
            backup_cookies = list(await ctx.cookies())
            await ctx.clear_cookies()
        await _open_first_environment_check(mgr, identity, ctx)
        page = await ctx.new_page()
        await _focus(page)
        await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
        await _focus(page)
        # 新版按钮是 ``span[role=button].sidebar-login-button``，文案被拆成
        # “立即”+“登录”，旧的 text=登录 / [class*=login] 会点不中或点到容器。
        await _click_ks_login_button(page, _KS_WEB_LOGIN_BUTTONS)
        waited = 0
        while waited < timeout_seconds:
            if page.is_closed():
                break
            try:
                cookies = await ctx.cookies()
            except Exception:
                break
            names = {c["name"] for c in cookies}
            if _ks_web_login_ready(names):
                logged = True
                break
            await asyncio.sleep(0.5)
            waited += 0.5
        if logged:
            await page.wait_for_timeout(1500)
            state_json = await _confirmed_login_state_json(mgr, identity, ctx)
            committed = True
            nickname = await _read_ks_nickname(page)
    finally:
        try:
            if force_reauth and backup_cookies and not committed:
                await _restore_login_cookies(ctx, backup_cookies, "ks")
        finally:
            await _close_login_context(ctx, resume)
    return logged, state_json, nickname


async def interactive_ks_creator_login(mgr: BrowserManager, identity: Identity,
                                       timeout_seconds: int = 180,
                                       force_reauth: bool = False,
                                       ) -> Tuple[bool, str, str]:
    """快手「创作者服务平台」登录(cp.kuaishou.com,发布用)。扫码后落地含创作者会话的登录态。
    返回 (是否成功, storage_state_json, nickname)。登录成功标志:出现 cp.api_st/api_ph。"""
    ctx = await mgr.open_headed(identity)
    logged = False
    committed = False
    backup_cookies = []
    resume = None
    nickname = ""
    state_json = ""
    try:
        resume = await _pause_login_checkpoints(mgr, ctx)
        if force_reauth:
            backup_cookies = list(await ctx.cookies())
            await ctx.clear_cookies()
        await _open_first_environment_check(mgr, identity, ctx)
        page = await ctx.new_page()
        await _focus(page)
        await page.goto("https://cp.kuaishou.com/", wait_until="domcontentloaded",
                        timeout=30000)
        await _focus(page)
        await _click_ks_login_button(page, _KS_CREATOR_LOGIN_BUTTONS)
        waited = 0
        while waited < timeout_seconds:
            if page.is_closed():
                break
            try:
                cookies = await ctx.cookies()
            except Exception:
                break
            names = {c["name"] for c in cookies}
            on_cp = "cp.kuaishou.com" in page.url and "/passport" not in page.url
            if (names & _KS_CREATOR_COOKIES) or (
                    on_cp and _ks_web_login_ready(names)):
                await page.wait_for_timeout(1500)
                try:
                    state_json = await _confirmed_login_state_json(mgr, identity, ctx)
                    committed = True
                    logged = True
                    nickname = await _read_ks_nickname(page)
                except Exception:
                    pass
                if logged:
                    break
            await asyncio.sleep(0.5)
            waited += 0.5
    finally:
        try:
            if force_reauth and backup_cookies and not committed:
                await _restore_login_cookies(ctx, backup_cookies, "ks-creator")
        finally:
            await _close_login_context(ctx, resume)
    return logged, state_json, nickname


# ── 视频号(微信视频号 / finder)登录 ──
# 视频号助手登录后写入的 Cookie(挂在 channels.weixin.qq.com / .weixin.qq.com)。
# 唯一可靠的强判据是业务接口 auth/* 返回 errCode==0。sessionid / _finder_auth 只是
# 辅助信号 —— 扫码授权尚未最终完成时它们就可能提前出现（wxuin 更是很早就写入），
# 单看 Cookie 名会把残缺登录态当成成功，出现「刚提示成功又登录失效」。
_CHANNELS_AUX_LOGIN_COOKIES = {"sessionid", "_finder_auth"}
# 辅助信号(仅凭 Cookie)必须「已离开 login 页」且连续稳定这么多轮才可采信，
# 避免授权过程中的瞬时假成功定案。
_CHANNELS_AUX_STABLE_ROUNDS = 3
_CHANNELS_AUTH_APIS = (
    "mmfinderassistant-bin/auth/get_auth_info",
    "mmfinderassistant-bin/auth/auth_data",
)


def channels_auth_err_code(payload) -> object:
    """从视频号 auth/* 响应里取出业务 errCode(取不到返回 None)。

    兼容 ``{errCode: 0, data: {...}}`` 以及包在 ``baseResponse`` 里的旧形态。
    单独抽出来是为了让登录页与资料抓取页共用同一套「200/300334 可区分」的判据。
    """
    if not isinstance(payload, dict):
        return None
    for key in ("errCode", "err_code", "ret", "retCode", "code"):
        if key in payload:
            return payload.get(key)
    base = payload.get("baseResponse") or payload.get("base_response") or {}
    if isinstance(base, dict):
        for key in ("errCode", "err_code", "ret", "retCode", "code"):
            if key in base:
                return base.get(key)
    return None


def channels_auth_code_ok(code) -> bool:
    """业务 errCode 是否表示明确成功(0 / ok / success);取不到一律不算成功。"""
    if code is None:
        return False
    try:
        return int(code) == 0
    except (TypeError, ValueError):
        return str(code).strip().lower() in {"ok", "success"}


def _channels_auth_response_ok(payload: dict) -> bool:
    """判断视频号 auth/* 响应是否明确表示已认证。

    只接受明确的业务成功码，避免 HTTP 200/201 但业务层未登录(errCode=300334)
    的响应被当成登录成功。
    """
    return channels_auth_code_ok(channels_auth_err_code(payload))


def _channels_login_ready(cookie_names, auth_verified: bool, on_platform: bool,
                          stable_rounds: int = 0) -> bool:
    """视频号登录是否已确认。

    唯一强判据是业务层 ``auth/*`` 的 ``errCode == 0``(``auth_verified``)。
    ``sessionid`` / ``_finder_auth`` 仅作辅助：即便出现，也必须同时满足
    「URL 已离开 login 页(``on_platform``)」且 ``stable_rounds`` 连续稳定达到
    ``_CHANNELS_AUX_STABLE_ROUNDS``，才可当作成功；任一条件不满足都不判定为成功。
    """
    if not on_platform:
        return False
    if auth_verified:
        return True
    return bool(
        (_CHANNELS_AUX_LOGIN_COOKIES & set(cookie_names or ()))
        and stable_rounds >= _CHANNELS_AUX_STABLE_ROUNDS
    )


async def _channels_confirm_platform_login(page, auth_verified, *,
                                           budget_seconds: float = 60.0,
                                           attempts: int = 3,
                                           per_attempt_seconds: int = 8) -> bool:
    """抓取快照前把页面导到 ``/platform``，确认 auth/* 返回 errCode==0。

    只认「这一次导航」产生的成功响应(每轮开始先 ``clear``)。所有等待收敛在
    ``budget_seconds`` 这个墙钟预算内(用单调时钟裁剪 attempts / 单轮等待 / 单次
    goto 超时，goto 超时上限 15s)，因此 confirm 阶段总耗时不会超过预算。
    只有拿到业务成功码才算，杜绝抓到只有 sessionid+wxuin 的残缺快照。
    """
    deadline = _now() + max(0.0, float(budget_seconds))
    goto_timeout_ms = 15000
    for _ in range(max(1, attempts)):
        if page.is_closed() or _now() >= deadline:
            break
        auth_verified.clear()
        remaining = deadline - _now()
        if remaining <= 0:
            break
        try:
            await page.goto(
                "https://channels.weixin.qq.com/platform",
                wait_until="domcontentloaded",
                timeout=min(goto_timeout_ms, max(1000, int(remaining * 1000))))
        except Exception:
            continue
        attempt_end = min(deadline, _now() + per_attempt_seconds)
        while _now() < attempt_end:
            if auth_verified.is_set():
                return True
            if page.is_closed():
                return False
            step = min(1.0, attempt_end - _now())
            if step <= 0:
                break
            # 至少等 1ms：避免 step*1000 被取整成 0 导致 wait 不推进、忙等死循环
            # (真机靠真实时钟自愈,但预算的「有界」保证需要进程本身不吃死循环)。
            wait_ms = max(1, int(step * 1000))
            try:
                await page.wait_for_timeout(wait_ms)
            except Exception:
                return False
    return auth_verified.is_set()


def channels_open_auth_response_handler(evidence: dict):
    """采集视频号登录的权威业务证据(供「打开账号浏览器」判活用)。

    与 xhs 的 ``_xhs_open_auth_response_handler`` 同型：只采 auth/* 的**业务 errCode**，
    不把 URL 或页面 UI 当证据。evidence 键：
      - ``seen``          看到过 auth/* 响应；
      - ``authenticated`` 观测到 errCode==0；
      - ``auth_failed``   观测到明确的非 0 业务码。
    """
    async def on_response(resp):
        try:
            if not any(api in str(getattr(resp, "url", "") or "")
                       for api in _CHANNELS_AUTH_APIS):
                return
            evidence["seen"] = True
            if int(getattr(resp, "status", 0)) >= 400:
                return
            payload = await resp.json()
            code = channels_auth_err_code(payload)
            evidence["last_code"] = code
            if channels_auth_code_ok(code):
                evidence["authenticated"] = True
            elif code is not None:
                evidence["auth_failed"] = True
        except Exception:
            return
    return on_response


async def interactive_channels_login(mgr: BrowserManager, identity: Identity,
                                     timeout_seconds: int = 180,
                                     force_reauth: bool = False,
                                     ) -> Tuple[bool, str, str]:
    """视频号扫码登录。打开视频号助手登录页让用户用微信扫码,落地登录态。
    返回 (是否成功, storage_state_json, nickname)。
    视频号只有一套登录态(助手即创作平台),读取/发布共用,故无独立创作登录。
    昵称登录页不易读,返回空串,交由「资料刷新」用 fetch_channels_self_profile 补全。
    ⚠️ 登录判定以业务接口 auth/* 的 errCode==0 为唯一强判据，逻辑集中在
    _channels_login_ready / _channels_confirm_platform_login。force_reauth 采用
    「先备份后提交」语义：只在确认拿到新的有效登录态后才丢弃旧 Cookie，否则回滚。"""
    ctx = await mgr.open_headed(identity)
    started_at = _now()
    backup_cookies: list = []
    logged = False
    nickname = ""
    state_json = ""
    committed = False
    resume = None
    auth_verified = asyncio.Event()
    last_auth: dict = {"code": None, "url": ""}

    async def on_response(resp):
        if not any(api in resp.url for api in _CHANNELS_AUTH_APIS) or resp.status >= 400:
            return
        try:
            payload = await resp.json()
        except Exception:
            return
        # 记住最近一次看到的业务 errCode，供收尾校验与诊断打印使用。
        last_auth["code"] = channels_auth_err_code(payload)
        last_auth["url"] = resp.url
        if channels_auth_code_ok(last_auth["code"]):
            auth_verified.set()

    # F1：try 从 ctx 打开后立即开始 —— backup / clear_cookies /
    # _open_first_environment_check / new_page / _focus / page.on 全部落在同一个
    # try 内，任何一步抛异常都由下面的 finally 兜底(回滚 + 无条件 ctx.close())，
    # 不再出现「cookie 已清空却零回滚 + ctx 泄漏」。
    # ⚠️ 这里刻意不收异常(无 except)：异常继续向上抛，保持原有语义。
    try:
        resume = await _pause_login_checkpoints(mgr, ctx)
        if force_reauth:
            # 「重新登录」先备份当前登录态再清空：本次扫码若关窗/超时/中途取消，
            # 收尾时会把备份回滚回去，避免「一次没完成的扫码」把已经能用的登录态
            # 直接清空 —— 那正是「刚登录又立刻掉登录」的直接诱因。
            try:
                backup_cookies = list(await ctx.cookies())
            except Exception as exc:
                backup_cookies = []
                _LOG.warning("[ch-login] 备份旧 Cookie 失败，本次无法回滚: %r", exc)
            await ctx.clear_cookies()
        await _open_first_environment_check(mgr, identity, ctx)
        page = await ctx.new_page()
        await _focus(page)
        page.on("response", on_response)
        await page.goto("https://channels.weixin.qq.com/login.html",
                        wait_until="domcontentloaded", timeout=30000)
        await _focus(page)
        waited = 0
        stable_rounds = 0
        while waited < timeout_seconds:
            if page.is_closed():
                break
            try:
                cookies = await ctx.cookies()
            except Exception:
                break
            names = {c["name"] for c in cookies}
            on_platform = "channels.weixin.qq.com" in page.url \
                and "login.html" not in page.url
            if auth_verified.is_set():
                # 唯一强判据：auth/* 返回 errCode==0。
                logged = True
                break
            # 辅助信号(仅 Cookie)：必须已离开 login 页、且连续多轮稳定才累计。
            if on_platform and (_CHANNELS_AUX_LOGIN_COOKIES & names):
                stable_rounds += 1
            else:
                stable_rounds = 0
            if _channels_login_ready(names, False, on_platform, stable_rounds):
                logged = True
                break
            await asyncio.sleep(2)
            waited += 2
        if logged:
            # 抓快照前主动导航到 /platform 并等待 auth/* 的 errCode==0，确认确实
            # 处于已登录态，避免抓到只有 sessionid+wxuin 的残缺快照。
            # F5：确认阶段收敛在明确预算内(≤60s)，并保证整个函数墙钟 ≤ timeout+30s。
            elapsed = _now() - started_at
            confirm_budget = max(0.0, min(60.0, timeout_seconds + 30.0 - elapsed))
            confirmed = await _channels_confirm_platform_login(
                page, auth_verified, budget_seconds=confirm_budget)
            names = {c["name"] for c in await ctx.cookies()}
            still_on_platform = "channels.weixin.qq.com" in page.url \
                and "login.html" not in page.url
            logged = bool(confirmed and still_on_platform)
            if logged:
                state_json = await _confirmed_login_state_json(mgr, identity, ctx)
                committed = True
            _LOG.info(
                "[ch-login] confirmed=%s on_platform=%s cookies=%d "
                "has_finder_auth=%s last_errCode=%s url=%s",
                confirmed, still_on_platform, len(names),
                "_finder_auth" in names, last_auth.get("code"), page.url)
    finally:
        # F3：备份回滚是「精确还原」——先 clear 再 add，删掉失败期间新写入的残缺
        # Cookie(例如不完整的 _finder_auth)，避免只合并、还原不干净。
        # 只有确认拿到新的有效登录态(committed)才丢弃旧 Cookie，否则还原。
        # R1b 保险：若 clear 成功而 add 抛异常，旧态已被清空，只留一行 warn 会真正丢
        # 登录态；故对「clear+add」整组再重试一次(仍失败才认栽，交由
        # manager._bridge_identity_cookies 在下次开 context 时兜底)。正常路径依旧
        # 只做一次 clear+add，可观测行为不变。
        try:
            if force_reauth and backup_cookies and not committed:
                await _restore_login_cookies(ctx, backup_cookies, "ch")
        finally:
            # Remain paused through rollback and close. Resuming first would
            # let a periodic checkpoint commit a partial state at teardown.
            await _close_login_context(ctx, resume)
    return logged, state_json, nickname


async def interactive_channels_creator_login(mgr: BrowserManager, identity: Identity,
                                             timeout_seconds: int = 180,
                                             force_reauth: bool = False,
                                             ) -> Tuple[bool, str, str]:
    """视频号无独立创作登录 —— 助手即创作平台,直接复用普通登录。"""
    return await interactive_channels_login(
        mgr, identity, timeout_seconds, force_reauth=force_reauth)


async def _read_ks_nickname(page) -> str:
    for sel in ('.profile-user-name', '[class*="user-name"]', '[class*="userName"]',
                '.user-name', 'span.name'):
        try:
            t = await page.inner_text(sel, timeout=1500)
            if t and t.strip():
                return t.strip()[:40]
        except Exception:
            continue
    return ""


async def _read_xhs_nickname(page) -> str:
    for sel in ('.user .name', '.reds-avatar + * .name', 'span.name'):
        try:
            t = await page.inner_text(sel, timeout=1500)
            if t and t.strip():
                return t.strip()[:40]
        except Exception:
            continue
    return ""


async def _read_nickname(page) -> str:
    # 新版抖音会把登录用户写进 localStorage；优先读它，避免三个 DOM 选择器
    # 逐个超时（旧实现最坏会额外等待 4.5 秒）。
    try:
        nickname = await page.evaluate(
            """() => {
              for (const store of [window.localStorage, window.sessionStorage]) {
                for (const key of ['user_info', 'userInfo', 'user_info_passport']) {
                  try {
                    const raw = store.getItem(key);
                    if (!raw) continue;
                    let value = JSON.parse(raw);
                    if (typeof value === 'string') value = JSON.parse(value);
                    const name = value && (value.nickname || value.name);
                    if (name) return String(name).trim().slice(0, 40);
                  } catch (_) {}
                }
              }
              return '';
            }"""
        )
        if nickname and str(nickname).strip():
            return str(nickname).strip()[:40]
    except Exception:
        pass

    for sel in ('[data-e2e="user-info-nickname"]', 'span.nickname',
                '[data-e2e="live-avatar"] + * span'):
        try:
            t = await page.inner_text(sel, timeout=600)
            if t and t.strip():
                return t.strip()[:40]
        except Exception:
            continue
    return ""
