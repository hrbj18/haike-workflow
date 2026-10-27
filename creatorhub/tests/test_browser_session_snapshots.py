"""Keep rotated sessions before Chromium discards session cookies."""
import asyncio
import contextlib
import copy
import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from app.browser.identity import Identity
from app.browser.manager import BrowserManager


def _cookie(value="rotated", domain=".weixin.qq.com"):
    return {"name": "_finder_auth", "value": value, "domain": domain,
            "path": "/", "expires": -1, "httpOnly": True, "secure": True}


class _Context:
    def __init__(self):
        self.state = {"cookies": [_cookie()], "origins": []}
        self.handlers = []
        self.closed = False
        self.events = []
        self.capture_error = False

    def on(self, event, callback):
        if event == "close":
            self.handlers.append(callback)

    async def storage_state(self):
        self.events.append("snapshot")
        if self.capture_error:
            raise RuntimeError("secret fixture capture error")
        return copy.deepcopy(self.state)

    async def close(self):
        self.events.append("close")
        self.closed = True
        self.state = {"cookies": [], "origins": []}
        for handler in self.handlers:
            handler(self)

    async def set_extra_http_headers(self, _headers):
        pass

    async def cookies(self):
        return copy.deepcopy(self.state["cookies"])

    async def add_cookies(self, cookies):
        current = {(c["name"], c["domain"].lstrip("."), c.get("path", "/")): c
                   for c in self.state["cookies"]}
        for cookie in cookies:
            current[(cookie["name"], cookie["domain"].lstrip("."), cookie.get("path", "/"))] = copy.deepcopy(cookie)
        self.state["cookies"] = list(current.values())


class BrowserSessionSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.managers = []

    async def asyncTearDown(self):
        for manager in self.managers:
            await manager.stop()
        self.scratch.cleanup()

    def manager(self, callback, interval=30):
        manager = BrowserManager(
            "UA", self.scratch.name,
            session_state_callback=callback,
            session_snapshot_interval_seconds=interval,
        )
        self.managers.append(manager)
        return manager

    def identity(self, platform="shipinhao"):
        return Identity(
            account_id=71, platform=platform, ua="UA", identity_mode="legacy",
            profile_dir=str(Path(self.scratch.name) / platform),
        )

    async def launch(self, manager, identity, context):
        class Chromium:
            async def launch_persistent_context(self, **_kwargs):
                return context
        manager._pw = SimpleNamespace(
            chromium=Chromium(), stop=self.noop)
        return await manager.context_for(identity)

    async def noop(self):
        pass

    async def test_actual_manager_close_captures_rotation_before_context_close(self):
        saved = []
        manager = self.manager(lambda identity, state: saved.append(state))
        context = _Context()
        identity = self.identity()
        await self.launch(manager, identity, context)
        context.state["cookies"][0]["value"] = "freshly-rotated"

        await manager.close_context(identity.key)

        self.assertEqual(context.events, ["snapshot", "close"])
        self.assertEqual(saved[-1]["cookies"][0]["value"], "freshly-rotated")
        self.assertEqual(saved[-1]["cookies"][0]["expires"], -1)

    async def test_periodic_checkpoint_captures_rotation_and_close_cancels_it(self):
        observed = asyncio.Event()
        saved = []

        async def save(identity, state):
            saved.append(state)
            observed.set()

        manager = self.manager(save, interval=0.01)
        context = _Context()
        await self.launch(manager, self.identity(), context)
        context.state["cookies"][0]["value"] = "new-periodic-token"
        await asyncio.wait_for(observed.wait(), timeout=1)
        self.assertEqual(saved[-1]["cookies"][0]["value"], "new-periodic-token")

        await context.close()
        count = len(saved)
        await asyncio.sleep(0.04)
        self.assertEqual(len(saved), count)
        self.assertFalse(await manager.snapshot_session(self.identity(), context))

    async def test_snapshot_is_filtered_to_platform_domains(self):
        saved = []
        manager = self.manager(lambda identity, state: saved.append(state))
        context = _Context()
        context.state = {
            "cookies": [_cookie(), _cookie(domain="channels.weixin.qq.com"),
                        _cookie(domain="evilweixin.qq.com"),
                        _cookie(domain=".douyin.com")],
            "origins": [
                {"origin": "https://channels.weixin.qq.com", "localStorage": [{"name": "account", "value": "fixture"}]},
                {"origin": "https://www.douyin.com", "localStorage": []},
            ],
        }
        self.assertTrue(await manager.snapshot_session(self.identity(), context))
        self.assertEqual(len(saved[0]["cookies"]), 2)
        self.assertEqual(len(saved[0]["origins"]), 1)

    async def test_empty_or_failed_capture_never_replaces_saved_state(self):
        saved = []
        manager = self.manager(lambda identity, state: saved.append(state))
        context = _Context()
        self.assertTrue(await manager.snapshot_session(self.identity(), context))
        context.state = {"cookies": [], "origins": []}
        self.assertFalse(await manager.snapshot_session(self.identity(), context))
        context.capture_error = True
        with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertFalse(await manager.snapshot_session(self.identity(), context))
        self.assertEqual(len(saved), 1)
        self.assertNotIn("secret fixture", stdout.getvalue() + stderr.getvalue())

    async def test_callback_failure_does_not_prevent_manager_close(self):
        def fail(identity, state):
            raise RuntimeError("secret fixture callback error")

        manager = self.manager(fail)
        context = _Context()
        identity = self.identity()
        await self.launch(manager, identity, context)
        with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()) as stderr:
            await manager.close_context(identity.key)
        self.assertTrue(context.closed)
        self.assertNotIn("secret fixture", stdout.getvalue() + stderr.getvalue())

    async def test_callback_rejection_is_reported_as_not_saved(self):
        manager = self.manager(lambda identity, state: False)
        self.assertFalse(await manager.snapshot_session(self.identity(), _Context()))

    async def test_cancelled_checkpoint_still_closes_context_then_propagates(self):
        async def cancelled(identity, state):
            raise asyncio.CancelledError()

        manager = self.manager(cancelled)
        context = _Context()
        identity = self.identity()
        await self.launch(manager, identity, context)
        with self.assertRaises(asyncio.CancelledError):
            await manager.close_context(identity.key)
        self.assertTrue(context.closed)
        self.assertEqual(context.events, ["snapshot", "close"])

    async def test_other_platforms_and_anonymous_contexts_are_unchanged(self):
        saved = []
        manager = self.manager(lambda identity, state: saved.append(state))
        context = _Context()
        for platform in ("douyin", "xhs", ""):
            self.assertFalse(await manager.snapshot_session(self.identity(platform), context))
        identity = self.identity()
        identity.account_id = None
        self.assertFalse(await manager.snapshot_session(identity, context))
        self.assertEqual(saved, [])

    async def test_kuaishou_keeps_both_web_and_creator_domain_state(self):
        saved = []
        manager = self.manager(lambda identity, state: saved.append(state))
        context = _Context()
        context.state = {
            "cookies": [_cookie(domain=".kuaishou.com"), _cookie(domain="cp.kuaishou.com")],
            "origins": [{"origin": "https://www.kuaishou.com", "localStorage": []},
                        {"origin": "https://cp.kuaishou.com", "localStorage": []}],
        }
        self.assertTrue(await manager.snapshot_session(self.identity("kuaishou"), context))
        self.assertEqual(len(saved[0]["cookies"]), 2)
        self.assertEqual(len(saved[0]["origins"]), 2)

    async def test_cold_handoff_bridges_just_saved_rotation_over_stale_identity(self):
        import json
        manager = self.manager(lambda identity, state: True)
        identity = replace(self.identity(), bridge_states=(json.dumps({
            "cookies": [_cookie("old-db-token")], "origins": []}),))
        old_context, new_context = _Context(), _Context()
        old_context.state["cookies"][0]["value"] = "fresh-checkpoint-token"
        new_context.state = {"cookies": [], "origins": []}
        contexts = iter([old_context, new_context])

        class Chromium:
            async def launch_persistent_context(self, **_kwargs):
                return next(contexts)

        manager._pw = SimpleNamespace(chromium=Chromium(), stop=self.noop)
        manager._start_minimize_hold = self.noop_identity_context
        await manager.context_for(identity)

        # The caller loaded this identity before close_context updates the DB.
        # Chromium removes session cookies when the old context closes.
        await manager.open_background(identity)

        self.assertEqual(new_context.state["cookies"][0]["value"], "fresh-checkpoint-token")
        await new_context.close()

    async def noop_identity_context(self, *_args):
        pass

    async def test_latest_checkpoint_never_overwrites_newer_live_cookie(self):
        import json
        manager = self.manager(lambda identity, state: True)
        identity = replace(self.identity(), bridge_states=(json.dumps({
            "cookies": [_cookie("old-db-token")], "origins": []}),))
        self.assertTrue(await manager.snapshot_session(identity, _Context()))
        context = _Context()
        context.state["cookies"][0]["value"] = "newest-live-token"
        await self.launch(manager, identity, context)
        self.assertEqual(context.state["cookies"][0]["value"], "newest-live-token")

    async def test_cold_handoff_cannot_use_another_account_or_profile_checkpoint(self):
        import json
        for change in ("account", "profile"):
            with self.subTest(change=change):
                manager = self.manager(lambda identity, state: True)
                identity = replace(self.identity(), bridge_states=(json.dumps({
                    "cookies": [_cookie("foreign-own-db-token")], "origins": []}),))
                self.assertTrue(await manager.snapshot_session(identity, _Context()))
                foreign = replace(identity, account_id=72) if change == "account" else replace(
                    identity, profile_dir=identity.profile_dir + "-other")
                context = _Context()
                context.state = {"cookies": [], "origins": []}
                await self.launch(manager, foreign, context)
                self.assertEqual(context.state["cookies"][0]["value"], "foreign-own-db-token")
                await manager.close_context(foreign.key)

    async def test_shutdown_discards_in_memory_latest_checkpoint(self):
        manager = self.manager(lambda identity, state: True)
        identity = self.identity()
        self.assertTrue(await manager.snapshot_session(identity, _Context()))
        self.assertIsNotNone(manager._session_snapshots.latest_state(identity))
        await manager.stop()
        self.assertIsNone(manager._session_snapshots.latest_state(identity))
