"""Only a pending owned QR flow may expose a no-store platform-page preview."""
import asyncio
import base64
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

from app import download_session_api as api
from app import download_sessions as service
from app.browser.identity import Identity
from app.browser.manager import BrowserManager
from app.local_access import LocalAccessMiddleware


PNG = b"\x89PNG\r\n\x1a\nfixture-only"


class _Page:
    def __init__(self, url):
        self.url = url
        self.screenshot = AsyncMock(return_value=PNG)

    def is_closed(self):
        return False


class _Context:
    def __init__(self, pages=()):
        self.pages = list(pages)
        self.handlers = []

    def on(self, event, callback):
        if event == "close":
            self.handlers.append(callback)

    async def close(self):
        for handler in self.handlers:
            handler(self)


class InteractiveContextRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = BrowserManager("fixture-UA", self.temp.name)

    async def asyncTearDown(self):
        await self.manager.stop()
        self.temp.cleanup()

    async def test_anonymous_preview_never_selects_existing_account_or_other_platform(self):
        self.manager._register_interactive_context(Identity(7, self.temp.name, platform="kuaishou"), _Context())
        self.manager._register_interactive_context(Identity(None, self.temp.name, platform="douyin"), _Context())
        self.assertIsNone(self.manager.interactive_login_context("kuaishou", None))
        self.assertIsNone(self.manager.interactive_login_context("shipinhao", None))

    async def test_closed_and_older_contexts_are_not_available(self):
        context = _Context()
        self.manager._register_interactive_context(Identity(None, self.temp.name, platform="kuaishou"), context)
        self.assertIsNone(self.manager.interactive_login_context("kuaishou", created_after=time.monotonic()+1))
        self.assertIs(self.manager.interactive_login_context("kuaishou"), context)
        await context.close()
        self.assertIsNone(self.manager.interactive_login_context("kuaishou"))

    async def test_both_open_headed_paths_register_only_the_returned_context(self):
        from app.browser import manager as manager_module
        for platform in ("kuaishou", "xhs"):
            with self.subTest(platform=platform):
                identity = Identity(None, str(Path(self.temp.name)/platform), platform=platform)
                context = _Context()
                self.manager.context_for = AsyncMock(return_value=context)
                self.manager.close_context = AsyncMock()
                self.manager._launch_persistent = AsyncMock(return_value=context)
                self.manager.stop_minimize_hold = AsyncMock()
                self.manager._first_page = AsyncMock(return_value=None)
                with patch.object(manager_module, "capture_window_snapshot", return_value=[]), \
                        patch.object(manager_module, "bring_window_to_front", return_value=None), \
                        patch.object(manager_module, "bring_new_windows_onscreen", return_value=None):
                    result = await self.manager.open_headed(identity)
                self.assertIs(result, context)
                self.assertIs(self.manager.interactive_login_context(platform), context)
                await context.close()


class DownloadLoginPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.task_id = "fixture-owned-login-preview"
        self.page = _Page("https://channels.weixin.qq.com/login.html")
        self.context = _Context([self.page])
        self.browser = SimpleNamespace(interactive_login_context=lambda *_a, **_kw: self.context)
        self.runtime = SimpleNamespace(browser=self.browser, login_tasks={self.task_id: {
            "status": "waiting", "platform": "shipinhao", "account_id": None}})
        api._LOGIN_TASKS[self.task_id] = {"created": time.monotonic(), "platform": "shipinhao",
                                        "account_id": None, "context_created_after": 0}
        self.runtime_patch = patch.object(service, "_runtime", return_value=self.runtime)
        self.runtime_patch.start()
        self.app = FastAPI()
        self.app.add_middleware(LocalAccessMiddleware)
        self.app.include_router(api.router)

    async def asyncTearDown(self):
        self.runtime_patch.stop()
        api._LOGIN_TASKS.pop(self.task_id, None)
        api._LOGIN_LOCKS.pop(self.task_id, None)

    async def request(self, *, peer="127.0.0.1", headers=None):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=(peer, 1234)),
                                     base_url="http://127.0.0.1:8000") as client:
            return await client.get(f"/api/download-sessions/login/{self.task_id}/preview.png",
                                    headers=headers or {})

    async def test_pending_actual_page_is_png_and_cannot_be_cached(self):
        response = await self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, PNG)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.page.screenshot.assert_awaited_once_with(type="png", full_page=False, timeout=5000)

    async def test_confirmed_expired_or_missing_task_never_captures_a_page(self):
        for status in ("confirmed", "expired", "error"):
            self.runtime.login_tasks[self.task_id]["status"] = status
            self.assertEqual((await self.request()).status_code, 410)
        self.runtime.login_tasks.clear()
        self.assertEqual((await self.request()).status_code, 410)
        self.page.screenshot.assert_not_awaited()

    async def test_slow_font_capture_falls_back_to_the_same_owned_chromium_surface(self):
        self.page.screenshot.side_effect = TimeoutError()
        session = SimpleNamespace(send=AsyncMock(return_value={"data": base64.b64encode(PNG).decode()}),
                                  detach=AsyncMock())
        self.context.new_cdp_session = AsyncMock(return_value=session)
        response = await self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, PNG)
        self.context.new_cdp_session.assert_awaited_once_with(self.page)
        session.detach.assert_awaited_once()

    async def test_fallback_rechecks_navigation_and_never_returns_another_site(self):
        self.page.screenshot.side_effect = TimeoutError()
        async def capture(*_args, **_kwargs):
            self.page.url = "https://evil.example/"
            return {"data": base64.b64encode(PNG).decode()}
        session = SimpleNamespace(send=AsyncMock(side_effect=capture), detach=AsyncMock())
        self.context.new_cdp_session = AsyncMock(return_value=session)
        self.assertEqual((await self.request()).status_code, 409)
        session.detach.assert_awaited_once()

    async def test_preview_is_not_available_to_an_unowned_task_or_wrong_platform(self):
        api._LOGIN_TASKS.pop(self.task_id)
        self.assertEqual((await self.request()).status_code, 404)
        api._LOGIN_TASKS[self.task_id] = {"created": time.monotonic(), "platform": "douyin"}
        self.assertEqual((await self.request()).status_code, 409)
        self.page.screenshot.assert_not_awaited()

    async def test_environment_check_or_arbitrary_page_is_never_captured(self):
        for url in ("https://www.browserscan.net/zh", "https://evil.example/login",
                    "https://channels.weixin.qq.com.evil.example/login.html",
                    "https://channels.weixin.qq.com/platform/post/list"):
            self.page.url = url
            self.assertEqual((await self.request()).status_code, 409)
        self.page.screenshot.assert_not_awaited()

    async def test_target_is_rechecked_after_screenshot_navigation(self):
        async def capture(**_kwargs):
            self.page.url = "https://evil.example/"
            return PNG
        self.page.screenshot.side_effect = capture
        response = await self.request()
        self.assertEqual(response.status_code, 409)
        self.assertNotEqual(response.content, PNG)

    async def test_task_finishing_during_capture_cannot_expose_post_login_page(self):
        async def capture(**_kwargs):
            self.runtime.login_tasks[self.task_id]["status"] = "confirmed"
            return PNG
        self.page.screenshot.side_effect = capture
        self.assertEqual((await self.request()).status_code, 410)

    async def test_bound_task_cannot_follow_a_replacement_context(self):
        self.assertEqual((await self.request()).status_code, 200)
        self.context = _Context([_Page("https://channels.weixin.qq.com/login.html")])
        self.assertEqual((await self.request()).status_code, 409)

    async def test_remote_or_cross_origin_requests_are_rejected_before_capture(self):
        self.assertEqual((await self.request(peer="192.0.2.1")).status_code, 403)
        self.assertEqual((await self.request(headers={"Origin": "https://evil.example"})).status_code, 403)
        self.assertEqual((await self.request(headers={"Sec-Fetch-Site": "cross-site"})).status_code, 403)
        self.page.screenshot.assert_not_awaited()

    async def test_login_page_is_preferred_over_home_and_browser_environment_check(self):
        home = _Page("https://channels.weixin.qq.com/platform")
        scan = _Page("https://www.browserscan.net/zh")
        self.context.pages = [self.page, home, scan]
        self.assertEqual((await self.request()).status_code, 200)
        self.page.screenshot.assert_awaited_once()
        home.screenshot.assert_not_awaited()
        scan.screenshot.assert_not_awaited()
