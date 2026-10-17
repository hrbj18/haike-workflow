"""Account-window regressions: live sessions win over older login snapshots."""
import asyncio
import json
import tempfile
import time
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app.db as db
import app.main as main
from app.browser import ks_fetcher
from app.browser.identity import Identity
from app.models import DouyinAccount


def _cookie(name, value, platform="kuaishou", **extra):
    domains = {"kuaishou": ".kuaishou.com", "shipinhao": ".weixin.qq.com",
               "douyin": ".douyin.com"}
    return {"name": name, "value": value, "domain": domains[platform],
            "path": "/", **extra}


class _Page:
    url = "about:blank"

    def on(self, *_args):
        pass

    async def goto(self, url, **_kwargs):
        self.url = url

    async def wait_for_timeout(self, *_args):
        pass


class _CookieContext:
    def __init__(self, cookies):
        self.current = {(item["name"], item["domain"], item["path"]): item.copy()
                        for item in cookies}

    async def cookies(self):
        return list(self.current.values())

    async def add_cookies(self, cookies):
        for item in cookies:
            self.current[item["name"], item["domain"], item["path"]] = item.copy()

    async def new_page(self):
        return _Page()

    async def close(self):
        pass

    def on(self, *_args):
        pass


class AccountBrowserCookieRefreshTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.previous_engine = db._engine
        self.temp = tempfile.TemporaryDirectory()
        db.init_db(str(Path(self.temp.name) / "fixture.db"))

    def tearDown(self):
        db._engine.dispose()
        db._engine = self.previous_engine
        self.temp.cleanup()

    async def _open(self, platform, snapshot, live):
        context = _CookieContext(live)
        profiles = str(Path(self.temp.name) / "profiles")

        class Browser:
            def identity_for(self, account):
                return Identity.from_account(account, profiles, "fixture-UA")

            @asynccontextmanager
            async def lock_for(self, _key):
                yield

            async def open_headed(self, _identity):
                return context

        async def classify(*_args):
            return "authenticated"

        with db.get_session() as session:
            account = DouyinAccount(
                platform=platform, nickname="fixture",
                storage_state=json.dumps({"cookies": snapshot}),
                profile_dir=str(Path(profiles) / platform),
            )
            session.add(account)
            session.commit()
            session.refresh(account)
            account_id = account.id
        try:
            with patch.object(main, "browser", Browser()), \
                    patch.object(main, "_opened_page_login_state", classify):
                result = await main.open_account_browser(account_id)
                self.assertTrue(result["ok"])
                await main.open_browsers[account_id].close()
        finally:
            main.open_browsers.pop(account_id, None)
        return await context.cookies()

    async def test_open_window_preserves_newer_live_session(self):
        for platform in ("kuaishou", "shipinhao", "douyin"):
            with self.subTest(platform=platform):
                cookies = await self._open(
                    platform, [_cookie("session", "old-snapshot", platform)],
                    [_cookie("session", "new-live", platform)])
                self.assertEqual(cookies, [_cookie("session", "new-live", platform)])

    async def test_open_window_restores_only_missing_session_cookie(self):
        live = _cookie("device", "live-device")
        missing = _cookie("session", "saved-session", expires=-1)
        cookies = await self._open("kuaishou", [missing], [live])
        self.assertEqual(cookies, [live, missing])

    async def test_open_window_does_not_restore_expired_snapshot(self):
        expired = _cookie("session", "expired", expires=time.time() - 60)
        self.assertEqual(await self._open("kuaishou", [expired], []), [])


class _LoginLocator:
    @property
    def first(self):
        return self

    async def is_visible(self, **_kwargs):
        return True


class _CreatorResponse:
    url = "https://cp.kuaishou.com/rest/cp/creator/pc/home/infoV2"
    request = SimpleNamespace(resource_type="fetch")

    async def json(self):
        return {"result": 1, "data": {"userName": "fixture", "userId": "fixture-id"}}

    async def text(self):
        return json.dumps(await self.json())


class _ScopePage:
    def __init__(self, creator_ok):
        self.creator_ok = creator_ok
        self.url = "about:blank"
        self.context = self
        self.callbacks = []

    async def cookies(self):
        # No web userId/passToken: only the creator-center session remains.
        return [_cookie("kuaishou.web.cp.api_st", "fixture-creator-session")]

    def on(self, event, callback):
        if event == "response":
            self.callbacks.append(callback)

    def locator(self, *_args):
        return _LoginLocator()

    async def goto(self, url, **_kwargs):
        self.url = url
        if "cp.kuaishou.com" in url:
            if self.creator_ok:
                for callback in self.callbacks:
                    await callback(_CreatorResponse())
            else:
                self.url = "https://cp.kuaishou.com/passport/login"

    async def wait_for_timeout(self, *_args):
        pass

    async def evaluate(self, *_args):
        return ""

    async def inner_text(self, *_args):
        return "发布作品 内容管理" if self.creator_ok else "立即登录"

    async def close(self):
        pass


async def _instant_timeout(awaitable, **_kwargs):
    awaitable.close()
    raise asyncio.TimeoutError()


class KuaishouSessionScopeTests(unittest.IsolatedAsyncioTestCase):
    async def _fetch(self, creator_ok):
        page = _ScopePage(creator_ok)

        class Manager:
            async def new_page(self, *_args):
                return page

        with patch.object(ks_fetcher.asyncio, "wait_for", _instant_timeout):
            return await ks_fetcher.fetch_ks_self_profile(
                Manager(), Identity(account_id=1, profile_dir="fixture", platform="kuaishou"))

    async def test_expired_web_scope_keeps_valid_creator_scope_authenticated(self):
        profile, error = await self._fetch(True)
        self.assertEqual(error, "")
        self.assertEqual(profile["_source"], "ks_creator")

    async def test_explicitly_logged_out_web_and_creator_scopes_are_invalid(self):
        profile, error = await self._fetch(False)
        self.assertEqual(profile, {})
        self.assertEqual(error, "logged_out")


if __name__ == "__main__":
    unittest.main()
