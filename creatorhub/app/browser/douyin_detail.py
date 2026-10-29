"""Read one video's evidence from an owned page's normal network responses."""
from __future__ import annotations

import asyncio
import re
from urllib.parse import parse_qs, urlsplit


_DETAIL_PATH = "/aweme/v1/web/aweme/detail/"
_FEED_PATHS = {"/aweme/v1/web/tab/feed/", "/aweme/v1/web/aweme/feed/"}


class DetailReadError(str):
    """Keep a safe result code while preserving the guard's risk categories."""
    def __new__(cls, code):
        result = super().__new__(cls, code)
        result.category, result.signal = {
            "verification_required": ("risk", "captcha"),
            "login_required": ("auth", "auth_required"),
            "network_error": ("network", "network_failure"),
        }.get(code, ("business", "detail_unconfirmed"))
        result.status_code = None
        if re.fullmatch(r"http_[1-5][0-9]{2}", code):
            result.status_code = int(code[5:])
            result.signal = code
            result.category = ("auth" if result.status_code == 401 else
                               "risk" if result.status_code in {403, 429} else "network")
        return result


_GATE_JS = """() => {
  const visible = el => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const challenges = [...document.querySelectorAll(
    '[id*="captcha"],[class*="captcha_verify"],iframe[src*="captcha"]')].some(visible);
  const labels = [...document.querySelectorAll(
    '[role="dialog"],[class*="login"],[data-e2e*="login"],h1,h2')]
    .filter(visible).map(el => (el.innerText || '').slice(0, 2000));
  return {
    challenge: challenges || labels.some(t => /安全验证|拖动滑块完成验证|请完成下列验证/.test(t)),
    login: labels.some(t => /扫码登录|二维码登录|登录后查看|登录后即可观看|登录后即可访问/.test(t))
  };
}"""


def _response_kind(url, target_id):
    try:
        parsed = urlsplit(str(url))
        if (parsed.scheme != "https" or parsed.hostname != "www.douyin.com"
                or parsed.port not in (None, 443) or parsed.username or parsed.password):
            return ""
        if parsed.path == _DETAIL_PATH:
            ids = parse_qs(parsed.query).get("aweme_id", [])
            return "detail" if ids == [target_id] else ""
        return "feed" if parsed.path in _FEED_PATHS else ""
    except (ValueError, TypeError):
        return ""


def _target_video(payload, kind, target_id):
    if not isinstance(payload, dict):
        return None
    code = payload.get("status_code")
    if not ((type(code) is int and code == 0) or (type(code) is str and code == "0")):
        return None
    nested = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if kind == "detail":
        candidates = [payload.get("aweme_detail"), nested.get("aweme_detail")]
    else:
        candidates = payload.get("aweme_list") or nested.get("aweme_list") or []
        if not isinstance(candidates, list):
            return None
    for candidate in candidates:
        if (isinstance(candidate, dict) and str(candidate.get("aweme_id")) == target_id
                and isinstance(candidate.get("video"), dict) and candidate["video"]
                and not candidate.get("images")):
            return candidate
    return None


def _payload_gate(payload):
    if not isinstance(payload, dict):
        return ""
    message = " ".join(str(payload.get(key) or "") for key in
                       ("status_msg", "message", "msg")).casefold()
    if (payload.get("verify_info") or payload.get("captcha")
            or any(token in message for token in ("captcha", "verify", "验证", "访问频繁", "环境异常"))):
        return "verification_required"
    if any(token in message for token in ("未登录", "请登录", "login required", "login_required")):
        return "login_required"
    return ""


async def _page_gate(page, target_id):
    try:
        parsed = urlsplit(str(page.url))
        if parsed.scheme != "https" or parsed.port not in (None, 443) or parsed.username or parsed.password:
            return "page_unconfirmed"
        if parsed.hostname in {"passport.douyin.com", "sso.douyin.com", "login.douyin.com"}:
            return "login_required"
        if parsed.hostname != "www.douyin.com":
            return "page_unconfirmed"
        if "captcha" in parsed.path.casefold() or "verify" in parsed.path.casefold():
            return "verification_required"
        if parsed.path.startswith(("/passport/", "/login")):
            return "login_required"
        canonical = parsed.path.rstrip("/") == "/video/" + target_id
        modal = parsed.path in {"/", "/jingxuan"} and parse_qs(parsed.query).get("modal_id") == [target_id]
        if not canonical and not modal:
            return "page_unconfirmed"
        gate = await asyncio.wait_for(page.evaluate(_GATE_JS), timeout=2)
        if not isinstance(gate, dict) or any(type(gate.get(key)) is not bool for key in ("challenge", "login")):
            return "page_unconfirmed"
        if gate["challenge"]:
            return "verification_required"
        return "login_required" if gate["login"] else ""
    except Exception:
        return "page_unconfirmed"


async def fetch_douyin_video_detail(mgr, identity, target_id, *, wait_seconds=12):
    """Return (raw video, error); no API replay, page clicks or browser discovery.

    The caller holds the engine's account/network guard and validates a current
    download record. BrowserManager opens only that identity's owned profile.
    """
    target_id = str(target_id)
    if (not re.fullmatch(r"[0-9]{15,22}", target_id) or identity.platform != "douyin"
            or type(identity.account_id) is not int or identity.account_id <= 0 or not identity.profile_dir):
        return None, "detail_unconfirmed"
    page = None
    pending = set()
    observed = None
    response_error = ""
    active = True
    accepted = 0
    changed = asyncio.Event()

    async def inspect_response(response, kind):
        nonlocal observed, response_error
        try:
            if response.status != 200:
                response_error = response_error or f"http_{int(response.status)}"
                changed.set()
                return
            payload = await asyncio.wait_for(response.json(), timeout=3)
            gate = _payload_gate(payload)
            if gate:
                response_error = gate
            elif active:
                observed = _target_video(payload, kind, target_id) or observed
            changed.set()
        except Exception:
            response_error = response_error or "network_error"
            changed.set()

    def on_response(response):
        nonlocal accepted
        if not active or accepted >= 12:
            return
        kind = _response_kind(response.url, target_id)
        if not kind:
            return
        try:
            # Page events are already scoped; also reject any synthetic/cross-page
            # response whose actual request frame belongs to a different page.
            if response.request.frame.page is not page or response.request.method != "GET":
                return
        except Exception:
            return
        accepted += 1
        task = asyncio.create_task(inspect_response(response, kind))
        pending.add(task)
        task.add_done_callback(pending.discard)

    try:
        page = await asyncio.wait_for(mgr.new_page(identity, block_media=True), timeout=35)
        page.on("response", on_response)
        navigation = await page.goto("https://www.douyin.com/video/" + target_id,
                                     wait_until="domcontentloaded", timeout=30000)
        if navigation is not None and navigation.status >= 400:
            return None, f"http_{int(navigation.status)}"
        deadline = asyncio.get_running_loop().time() + max(0.01, min(float(wait_seconds), 20))
        gate = "page_unconfirmed"
        while asyncio.get_running_loop().time() < deadline:
            if page.is_closed():
                return None, "network_error"
            gate = await _page_gate(page, target_id)
            if gate in {"verification_required", "login_required"}:
                return None, gate
            if response_error in {"verification_required", "login_required"}:
                return None, response_error
            if observed is not None and not gate:
                return observed, ""
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(changed.wait(), timeout=min(0.5, remaining))
            except asyncio.TimeoutError:
                pass
            changed.clear()
        return None, response_error or "detail_unconfirmed"
    except Exception:
        return None, "network_error"
    finally:
        active = False
        if page is not None:
            try:
                page.remove_listener("response", on_response)
            except Exception:
                pass
        for task in list(pending):
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if page is not None:
            try:
                await asyncio.wait_for(page.close(), timeout=3)
            except Exception:
                pass
