"""Offline QR-login transactions must not publish tentative guest sessions."""
import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from app.browser.identity import Identity
from app.browser.login import (
    interactive_channels_login, interactive_ks_creator_login, interactive_ks_login,
)
from app.browser.manager import BrowserManager


class _EmptyLocator:
    async def count(self):
        return 0


class _Response:
    status = 200
    url = "https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/auth/get_auth_info"

    async def json(self):
        return {"errCode": 0, "data": {"finderUser": {"nickname": "fixture owner"}}}


class _Page:
    def __init__(self, context):
        self.context = context
        self.url = "about:blank"
        self.closed = False
        self.handlers = []
        self.frames = [self]

    async def bring_to_front(self):
        pass

    def on(self, event, callback):
        if event == "response":
            self.handlers.append(callback)

    def is_closed(self):
        return self.closed

    def locator(self, _selector):
        return _EmptyLocator()

    async def goto(self, url, **_kwargs):
        self.url = url
        self.context.install("new-auth" if self.context.scenario == "success" else "guest")
        # A regular checkpoint can arrive while the QR page is awaiting the
        # business acknowledgement. The real manager/snapshot saver decides
        # whether it is admissible; this fake only supplies browser IO.
        await self.context.manager.snapshot_session(self.context.identity, self.context)
        if self.context.scenario == "navigation_error":
            raise RuntimeError("offline QR navigation failure")
        if self.context.scenario == "cancel":
            self.closed = True
            return
        self.url = "https://channels.weixin.qq.com/platform" if self.context.identity.platform == "shipinhao" else url
        for handler in self.handlers:
            await handler(_Response())

    async def wait_for_timeout(self, _milliseconds):
        await self.context.manager.snapshot_session(self.context.identity, self.context)

    async def evaluate(self, script, *_args):
        if "Object.entries(sessionStorage)" in script:
            return {"origin": self.context.origin, "items": [
                {"name": "fixture-tab-auth", "value": self.context.value},
            ]}
        return "fixture owner"


class _Context:
    def __init__(self, identity, scenario):
        self.identity, self.scenario = identity, scenario
        self.origin = "https://channels.weixin.qq.com" if identity.platform == "shipinhao" else "https://www.kuaishou.com"
        self.manager = None
        self.handlers = []
        self.pages = []
        self.closed = False
        self.closed_cookies = None
        self.value = "old-auth"
        self.install(self.value)

    def install(self, value):
        self.value = value
        domain = ".weixin.qq.com" if self.identity.platform == "shipinhao" else ".kuaishou.com"
        names = ["_finder_auth"] if self.identity.platform == "shipinhao" else ["userId", "passToken", "kuaishou.web.cp.api_st"]
        if value == "guest":
            names = ["fixture_guest"]
        self.cookie_values = [{"name": name, "value": value, "domain": domain, "path": "/", "expires": -1} for name in names]

    def on(self, event, callback):
        if event == "close":
            self.handlers.append(callback)

    async def new_page(self):
        page = _Page(self)
        self.pages.append(page)
        return page

    async def cookies(self):
        return copy.deepcopy(self.cookie_values)

    async def clear_cookies(self):
        self.cookie_values = []

    async def add_cookies(self, cookies):
        self.cookie_values = copy.deepcopy(cookies)

    async def set_extra_http_headers(self, _headers):
        pass

    async def storage_state(self, *, indexed_db=False):
        origin = {"origin": self.origin, "localStorage": []}
        if indexed_db:
            origin["indexedDB"] = [{"name": "fixture-db", "version": 1, "stores": []}]
        return {"cookies": await self.cookies(), "origins": [origin]}

    async def close(self):
        if self.closed:
            return
        self.closed_cookies = await self.cookies()
        self.closed = True
        for handler in self.handlers:
            handler(self)


class _OfflineManager(BrowserManager):
    """Use the real manager except native browser launch/window presentation."""
    async def open_headed(self, identity):
        return await self.context_for(identity)

    async def open_environment_check(self, *_args, **_kwargs):
        return None


class LoginSnapshotTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.managers = []

    async def asyncTearDown(self):
        for manager in self.managers:
            await manager.stop()
        self.temp.cleanup()

    def fixture(self, operation, scenario, *, anonymous=False):
        platform = "shipinhao" if operation == "channels" else "kuaishou"
        identity = Identity(account_id=None if anonymous else 7, platform=platform,
            profile_dir=str(Path(self.temp.name) / (operation + scenario)), identity_mode="legacy", ua="fixture-UA")
        context = _Context(identity, scenario)
        if operation == "ks_creator":
            context.origin = "https://cp.kuaishou.com"
        saved = []
        manager = _OfflineManager("fixture-UA", self.temp.name,
            session_state_callback=lambda _identity, state: saved.append(copy.deepcopy(state)),
            session_snapshot_interval_seconds=3600)
        context.manager = manager

        class Chromium:
            async def launch_persistent_context(self, **_kwargs):
                return context

        async def stop():
            pass

        manager._pw = SimpleNamespace(chromium=Chromium(), stop=stop)
        self.managers.append(manager)
        run = {"channels": interactive_channels_login, "ks_web": interactive_ks_login,
               "ks_creator": interactive_ks_creator_login}[operation]
        return run, manager, identity, context, saved

    async def test_cancelled_reauth_never_persists_guest_and_restores_old_cookies(self):
        for operation in ("channels", "ks_web", "ks_creator"):
            with self.subTest(operation=operation):
                run, manager, identity, context, saved = self.fixture(operation, "cancel")
                old = await context.cookies()
                ok, state, _nickname = await run(manager, identity, timeout_seconds=1, force_reauth=True)
                self.assertFalse(ok)
                self.assertEqual(state, "")
                self.assertEqual(saved, [], "uncommitted guest state reached persistent account snapshots")
                self.assertEqual(context.closed_cookies, old)
                self.assertTrue(context.closed)

    async def test_confirmed_login_returns_complete_final_state_without_tentative_persistence(self):
        for operation in ("channels", "ks_web", "ks_creator"):
            with self.subTest(operation=operation):
                run, manager, identity, context, saved = self.fixture(operation, "success")
                ok, raw, _nickname = await run(manager, identity, timeout_seconds=1, force_reauth=True)
                self.assertTrue(ok)
                self.assertEqual(saved, [], "only the confirmed return value may be committed by the login owner")
                state = json.loads(raw)
                self.assertEqual({cookie["value"] for cookie in state["cookies"]}, {"new-auth"})
                self.assertEqual(state["sessionStorage"][0]["items"][0]["value"], "new-auth")
                self.assertEqual(state["origins"][0]["indexedDB"][0]["name"], "fixture-db")
                self.assertTrue(context.closed)

    async def test_first_account_login_also_captures_tab_state_before_unbound_context_closes(self):
        run, manager, identity, context, saved = self.fixture("channels", "success", anonymous=True)
        ok, raw, _nickname = await run(manager, identity, timeout_seconds=1, force_reauth=True)
        self.assertTrue(ok)
        self.assertIsNone(identity.account_id)
        self.assertEqual(saved, [])
        self.assertEqual(json.loads(raw)["sessionStorage"][0]["items"][0]["value"], "new-auth")
        self.assertTrue(context.closed)

    async def test_navigation_exception_rolls_back_closes_and_does_not_suspend_next_context(self):
        for operation in ("channels", "ks_web", "ks_creator"):
            with self.subTest(operation=operation):
                run, manager, identity, context, saved = self.fixture(operation, "navigation_error")
                old = await context.cookies()
                with self.assertRaisesRegex(RuntimeError, "offline QR navigation failure"):
                    await run(manager, identity, timeout_seconds=1, force_reauth=True)
                self.assertEqual(saved, [])
                self.assertEqual(context.closed_cookies, old)
                self.assertTrue(context.closed)
                # A failed QR transaction must not leave account-wide saving
                # suspended for the next ordinary browser operation.
                next_context = _Context(identity, "success")
                next_context.manager = manager
                self.assertTrue(await manager.snapshot_session(identity, next_context))
                self.assertEqual(saved[-1]["cookies"], old)

    async def test_successful_reauth_replaces_old_cached_checkpoint_before_cold_handoff(self):
        run, manager, identity, context, saved = self.fixture("channels", "success")
        previous = _Context(identity, "success")
        previous.manager = manager
        self.assertTrue(await manager.snapshot_session(identity, previous))
        self.assertEqual(saved[-1]["cookies"][0]["value"], "old-auth")

        ok, raw, _nickname = await run(manager, identity, timeout_seconds=1, force_reauth=True)
        self.assertTrue(ok)
        self.assertEqual(json.loads(raw)["cookies"][0]["value"], "new-auth")
        await manager.close_context(identity.key)
        cold = _Context(identity, "success")
        cold.manager = manager
        cold.cookie_values = []  # Chromium drops session cookies on close.

        class Chromium:
            async def launch_persistent_context(self, **_kwargs):
                return cold

        manager._pw.chromium = Chromium()
        fresh_identity = replace(identity, bridge_states=(raw,))  # Caller reloaded the newly committed account.
        await manager.context_for(fresh_identity)
        self.assertEqual({cookie["value"] for cookie in await cold.cookies()}, {"new-auth"})


if __name__ == "__main__":
    unittest.main()
