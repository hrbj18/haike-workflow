from __future__ import annotations

"""Runtime adapter for MediaCrawler.

This file is executed by MediaCrawler's isolated Python.  It changes runtime
configuration only; the vendored upstream checkout remains untouched.
"""

import argparse
import asyncio
import json
import os
import runpy
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit


def _douyin_origin(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in {"www.douyin.com", "douyin.com"}
                and parsed.port in (None, 443) and not parsed.username and not parsed.password)
    except (TypeError, ValueError):
        return False


def _self_profile_url(url: str) -> bool:
    return _douyin_origin(url) and urlsplit(url).path.rstrip("/") == "/aweme/v1/web/user/profile/self"


def _authenticated_self(payload: Any) -> bool:
    if not isinstance(payload, dict) or isinstance(payload.get("status_code"), bool):
        return False
    if payload.get("status_code") not in (0, "0"):
        return False
    data = payload.get("data")
    user = payload.get("user") or (data.get("user") if isinstance(data, dict) else None)
    if not isinstance(user, dict) or not isinstance(user.get("nickname"), str) or not user["nickname"].strip():
        return False
    for field in ("uid", "sec_uid"):
        value = user.get(field)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value > 0:
            return True
        if isinstance(value, str) and value.strip() not in {"", "0", "null", "undefined", "None"}:
            return True
    return False


class CookieAccountEvidence:
    """One navigation's live self-profile evidence; no Cookie/UI marker cache."""

    def __init__(self, page: Any) -> None:
        self.page = page
        self.generation = 0
        self.requests: dict[int, int] = {}
        self.tasks: set[asyncio.Task] = set()
        self.observed = asyncio.Event()
        self.success = False
        self.conflict = False
        page.on("request", self._requested)
        page.on("response", self._received)

    def start_navigation(self) -> None:
        self.generation += 1
        self.requests.clear()
        self.success = self.conflict = False
        self.observed.clear()
        for task in list(self.tasks):
            task.cancel()

    def _requested(self, request: Any) -> None:
        if (request.method == "GET" and _self_profile_url(request.url)
                and len(self.requests) < 32):
            self.requests[id(request)] = self.generation

    def _received(self, response: Any) -> None:
        generation = self.requests.pop(id(response.request), None)
        if generation != self.generation or not _self_profile_url(response.url):
            return
        task = asyncio.create_task(self._handle(response, generation))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _handle(self, response: Any, generation: int) -> None:
        try:
            if not 200 <= response.status < 300 or getattr(response, "from_service_worker", False):
                verdict = "conflict"
            else:
                payload = await asyncio.wait_for(response.json(), timeout=3)
                if _authenticated_self(payload):
                    verdict = "success"
                elif (not isinstance(payload, dict) or isinstance(payload.get("status_code"), bool)
                      or payload.get("status_code") not in (0, "0")):
                    verdict = "conflict"
                else:
                    verdict = "neutral"
        except asyncio.CancelledError:
            raise
        except Exception:
            verdict = "conflict"
        if generation != self.generation:
            return
        if verdict == "success":
            self.success = True
            self.observed.set()
        elif verdict == "conflict":
            self.conflict = True
            self.observed.set()

    async def wait(self, timeout: float = 8) -> bool:
        deadline = asyncio.get_running_loop().time() + timeout
        try:
            try:
                await asyncio.wait_for(self.observed.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                return False
            if self.tasks:
                remaining = max(0.001, deadline - asyncio.get_running_loop().time())
                await asyncio.wait_for(asyncio.gather(*list(self.tasks), return_exceptions=True),
                                       timeout=min(3, remaining))
            if not self.success or self.conflict or not _douyin_origin(self.page.url):
                return False
            if any(part in urlsplit(self.page.url).path.lower() for part in ("login", "captcha", "verify")):
                return False
            remaining = max(0.001, deadline - asyncio.get_running_loop().time())
            title = await asyncio.wait_for(self.page.title(), timeout=min(1, remaining))
            if "验证码" in title or "安全验证" in title:
                return False
            challenge = self.page.locator(
                "#captcha-verify-image:visible, #captcha_container:visible, "
                ".captcha_verify_container:visible, iframe[src*='captcha']:visible, iframe[src*='verify']:visible"
            ).first
            remaining = max(0.001, deadline - asyncio.get_running_loop().time())
            return not await asyncio.wait_for(challenge.is_visible(timeout=500), timeout=min(1, remaining))
        except asyncio.CancelledError:
            raise
        except Exception:
            return False
        finally:
            self.page.remove_listener("request", self._requested)
            self.page.remove_listener("response", self._received)
            for task in list(self.tasks):
                task.cancel()
            if self.tasks:
                await asyncio.gather(*list(self.tasks), return_exceptions=True)


class HumanVerificationRequired(RuntimeError):
    """The owned runner stops rather than completing a platform challenge."""


def install_human_verification_guard(login_class: Any, *, credential_backed: bool) -> None:
    """Keep normal authentication checks, but never invoke upstream CAPTCHA solvers.

    A credential-backed run has already injected the verified account snapshot.
    If upstream's pong check rejects it, a second automatic login cannot repair
    that observation safely: hand control back to the workbench instead.
    """
    async def require_human_login(self, *args, **kwargs):
        print("COPY_SKILL_STATUS " + json.dumps({
            "status": "needs_human_verification", "platform": "douyin",
            "reason": "login_or_verification_required",
            "message": "抖音登录需要人工确认，请在工作台处理后恢复；未自动处理验证码",
        }, ensure_ascii=False), flush=True)
        raise HumanVerificationRequired("抖音登录需要人工确认，未自动处理验证码")

    # Cover both the high-level check and direct slider calls. These are the
    # only challenge automation entrypoints in the supported upstream Douyin
    # module; ordinary browser-side request signing remains untouched.
    login_class.check_page_display_slider = require_human_login
    login_class.move_slider = require_human_login
    if credential_backed:
        login_class.begin = require_human_login


async def reuse_existing_page(
    context: Any,
    original_new_page: Callable[[Any], Awaitable[Any]],
) -> tuple[Any, dict[str, int | bool]]:
    """Reuse the single project page instead of opening another visible page."""
    pages = [page for page in list(getattr(context, "pages", []) or []) if not page.is_closed()]
    before = len(pages)
    if pages:
        page = pages[0]
        reused = True
    else:
        page = await original_new_page(context)
        reused = False
    after = len([value for value in list(getattr(context, "pages", []) or []) if not value.is_closed()])
    return page, {"pages_before": before, "pages_after": after, "reused_existing_page": reused}


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--crawler-root", required=True)
    parser.add_argument("--cdp-port", type=int, required=True)
    parser.add_argument("--navigation-timeout", type=int, default=90)
    parser.add_argument("--publish-time-type", type=int, choices=(0, 1, 7, 180), default=0)
    parser.add_argument("--download-account-id", type=int)
    known, remainder = parser.parse_known_args()
    if remainder and remainder[0] == "--":
        remainder = remainder[1:]

    root = Path(known.crawler_root).resolve()
    os.chdir(root)
    sys.path.insert(0, str(root))
    # MediaCrawler's CDP discovery uses HTTP clients that may honor the host
    # system proxy.  Local debugging endpoints must never leave this machine.
    local_bypass = "localhost,127.0.0.1"
    os.environ["NO_PROXY"] = local_bypass
    os.environ["no_proxy"] = local_bypass

    import config  # type: ignore
    from playwright.async_api import BrowserContext, Page  # type: ignore
    from media_platform.douyin.client import DouYinClient  # type: ignore
    from media_platform.douyin.login import DouYinLogin  # type: ignore

    install_human_verification_guard(
        DouYinLogin, credential_backed=known.download_account_id is not None,
    )

    # Current upstream still omits clip length from its saved-row whitelist.
    # Preserve the explicitly millisecond video.duration at runtime; never
    # patch the ignored third-party checkout or infer units after downloading.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from douyin_intelligence.mediacrawler_runtime_store import install_duration_bridge
    from store import douyin as douyin_store  # type: ignore
    install_duration_bridge(douyin_store)

    config.ENABLE_CDP_MODE = True
    config.CDP_CONNECT_EXISTING = True
    config.CDP_DEBUG_PORT = known.cdp_port
    config.BROWSER_LAUNCH_TIMEOUT = max(10, known.navigation_timeout)
    config.PUBLISH_TIME_TYPE = known.publish_time_type
    # This adapter collects metadata. The caller downloads only its explicitly
    # selected media through the bounded project downloader.
    config.ENABLE_GET_MEDIA = False
    config.ENABLE_GET_MEIDAS = False  # Compatibility with older upstream spelling.
    download_cookies = None
    download_user_agent = ""
    if known.download_account_id is not None:
        # This script is executed by the isolated upstream Python, which does
        # not necessarily have copy_skill installed as a package.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from douyin_intelligence.download_credentials_adapter import (
            account_record, configure_cookie_login, inject_download_cookies,
            inherit_download_user_agent,
        )
        record = account_record(known.download_account_id)
        download_cookies = record["cookies"]
        download_user_agent = record.get("user_agent", "")
        remainder = configure_cookie_login(config, remainder, download_cookies)
        # Upstream log messages can include request headers. Preserve only the
        # project's bounded status protocol for credential-backed runs.
        import logging
        logging.disable(logging.CRITICAL)
        try:
            from loguru import logger
            logger.remove()
        except ImportError:
            pass

    async def bounded_creator_posts(self, sec_user_id, callback=None):
        """Honor CRAWLER_MAX_NOTES_COUNT, which upstream creator mode ignores."""
        posts_has_more = 1
        max_cursor = ""
        result = []
        limit = max(1, int(config.CRAWLER_MAX_NOTES_COUNT))
        while posts_has_more == 1 and len(result) < limit:
            response = await self.get_user_aweme_posts(sec_user_id, max_cursor)
            posts_has_more = response.get("has_more", 0)
            max_cursor = response.get("max_cursor")
            items = response.get("aweme_list") or []
            remaining = limit - len(result)
            items = items[:remaining]
            if callback and items:
                await callback(items)
            result.extend(items)
        return result

    DouYinClient.get_all_user_aweme_posts = bounded_creator_posts

    original_new_page = BrowserContext.new_page
    injected_contexts = set()
    auth_evidence: dict[int, CookieAccountEvidence] = {}

    if download_cookies is not None:
        async def verified_account_pong(self, browser_context):
            evidence = auth_evidence.get(id(self.playwright_page))
            return await evidence.wait(timeout=8) if evidence is not None else False

        # UI storage flags may be absent from an imported Cookie snapshot. A
        # fresh authenticated self response replaces those flags, not the
        # authentication requirement itself.
        DouYinClient.pong = verified_account_pong

    async def project_owned_new_page(self):
        if download_cookies is not None and id(self) not in injected_contexts:
            await inject_download_cookies(self, download_cookies)
            injected_contexts.add(id(self))
        page, audit = await reuse_existing_page(self, original_new_page)
        if download_cookies is not None:
            await inherit_download_user_agent(self, page, download_user_agent)
            if id(page) not in auth_evidence:
                auth_evidence[id(page)] = CookieAccountEvidence(page)
        print(
            "COPY_SKILL_CDP_AUDIT "
            f"pages_before={audit['pages_before']} pages_after={audit['pages_after']} "
            f"reused_existing_page={int(bool(audit['reused_existing_page']))}"
        )
        return page

    BrowserContext.new_page = project_owned_new_page

    original_goto = Page.goto

    async def resilient_goto(self, url, **kwargs):
        evidence = auth_evidence.get(id(self))
        if evidence is not None:
            evidence.start_navigation()
        kwargs.setdefault("wait_until", "domcontentloaded")
        kwargs.setdefault("timeout", known.navigation_timeout * 1000)
        return await original_goto(self, url, **kwargs)

    Page.goto = resilient_goto
    sys.argv = [str(root / "main.py"), *remainder]
    try:
        runpy.run_path(str(root / "main.py"), run_name="__main__")
    except HumanVerificationRequired:
        # The bounded status above is sufficient; no upstream traceback, page
        # contents, credential values, or signed URLs are needed by the caller.
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
