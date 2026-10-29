"""Synthetic KS/Channels state survives cold tabs without mixing old live state."""
import copy
import asyncio
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.browser.session_snapshots import _seed_new_tab

from tests import test_browser_session_snapshots as _fixtures

_Context = _fixtures._Context
_cookie = _fixtures._cookie


ORIGIN = "https://channels.weixin.qq.com"


class _Frame:
    def __init__(self, origin=ORIGIN, value="rotated-fixture"):
        self.url = origin + "/platform"
        self.origin = origin
        self.value = value

    async def evaluate(self, _script):
        return {"origin": self.origin, "items": [] if self.value is None else [
            {"name": "fixture_tab_auth", "value": self.value},
        ]}


class _StorageContext(_Context):
    def __init__(self):
        super().__init__()
        self.indexed_db_requested = False
        self.pages = [SimpleNamespace(frames=[_Frame(), _Frame("https://unrelated.invalid")])]
        self.scripts = []

    async def storage_state(self, *, indexed_db=False):
        state = await super().storage_state()
        self.indexed_db_requested = indexed_db
        if indexed_db:
            state["origins"] = [{"origin": ORIGIN, "localStorage": [], "indexedDB": [
                {"name": "fixture-db", "version": 1, "stores": []},
            ]}]
        return state

    async def add_init_script(self, script):
        self.scripts.append(script)

    async def new_page(self):
        page = SimpleNamespace(url="about:blank", frames=[], close=AsyncMock())
        self.pages.append(page)
        return page


def _state(value):
    return {"cookies": [_cookie()], "origins": [], "sessionStorage": [
        {"origin": ORIGIN, "items": [{"name": "fixture_tab_auth", "value": value}]},
    ]}


class SessionStorageBridgeTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = _fixtures.BrowserSessionSnapshotTests.asyncSetUp
    asyncTearDown = _fixtures.BrowserSessionSnapshotTests.asyncTearDown
    manager = _fixtures.BrowserSessionSnapshotTests.manager
    identity = _fixtures.BrowserSessionSnapshotTests.identity
    launch = _fixtures.BrowserSessionSnapshotTests.launch
    noop = _fixtures.BrowserSessionSnapshotTests.noop

    async def test_checkpoint_captures_indexed_db_and_platform_tab_storage(self):
        saved = []
        manager = self.manager(lambda identity, state: saved.append(copy.deepcopy(state)))
        context = _StorageContext()

        self.assertTrue(await manager.snapshot_session(self.identity(), context))

        self.assertTrue(context.indexed_db_requested)
        self.assertEqual(saved[0]["origins"][0]["indexedDB"][0]["name"], "fixture-db")
        self.assertEqual(saved[0]["sessionStorage"], _state("rotated-fixture")["sessionStorage"])

    async def test_cold_context_registers_tab_restore_for_same_platform_only(self):
        manager = self.manager(lambda identity, state: True)
        state = _state("saved-fixture")
        state["sessionStorage"].append({"origin": "https://unrelated.invalid", "items": [
            {"name": "foreign", "value": "foreign-fixture"},
        ]})
        identity = replace(self.identity(), bridge_states=(json.dumps(state),))
        context = _StorageContext()

        with patch("app.browser.session_snapshots._seed_new_tab", AsyncMock()) as seed:
            await self.launch(manager, identity, context)
            await context.new_page()
        seed.assert_awaited_once()
        self.assertEqual(seed.await_args.args[2]["sessionStorage"], _state("saved-fixture")["sessionStorage"])
        self.assertEqual(context.scripts, [])

    async def test_latest_checkpoint_beats_identity_loaded_before_close(self):
        manager = self.manager(lambda identity, state: True)
        identity = replace(self.identity(), bridge_states=(json.dumps(_state("old-db-fixture")),))
        old = _StorageContext()
        old.pages[0].frames = [_Frame(value="just-saved-fixture")]
        self.assertTrue(await manager.snapshot_session(identity, old))
        context = _StorageContext()

        with patch("app.browser.session_snapshots._seed_new_tab", AsyncMock()) as seed:
            await self.launch(manager, identity, context)
            await context.new_page()
        seed.assert_awaited_once()
        self.assertEqual(seed.await_args.args[2]["sessionStorage"], _state("just-saved-fixture")["sessionStorage"])

    async def test_latest_empty_tab_storage_does_not_resurrect_old_snapshot(self):
        manager = self.manager(lambda identity, state: True)
        identity = replace(self.identity(), bridge_states=(json.dumps(_state("old-db-fixture")),))
        old = _StorageContext()
        old.pages[0].frames = [_Frame(value=None)]
        self.assertTrue(await manager.snapshot_session(identity, old))
        context = _StorageContext()

        with patch("app.browser.session_snapshots._seed_new_tab", AsyncMock()) as seed:
            await self.launch(manager, identity, context)
            await context.new_page()
        seed.assert_not_awaited()
        self.assertEqual(context.scripts, [])

    async def test_new_state_extension_keeps_old_browser_adapter_compatible(self):
        saved = []
        manager = self.manager(lambda identity, state: saved.append(state))
        self.assertTrue(await manager.snapshot_session(self.identity(), _Context()))
        self.assertEqual(saved[0]["cookies"], [_cookie()])

    async def test_latest_cookie_set_does_not_resurrect_a_deleted_old_auth_cookie(self):
        manager = self.manager(lambda identity, state: True)
        device = {**_cookie("device-fixture"), "name": "fixture_device"}
        stale = {"cookies": [_cookie("deleted-auth-fixture"), device], "origins": []}
        identity = replace(self.identity(), bridge_states=(json.dumps(stale),))
        current = _StorageContext()
        current.state["cookies"] = [device]
        self.assertTrue(await manager.snapshot_session(identity, current))
        cold = _StorageContext()
        cold.state["cookies"] = []

        await self.launch(manager, identity, cold)

        self.assertEqual(await cold.cookies(), [device])

    async def test_newer_live_cookie_prevents_incompatible_old_tab_state_restore(self):
        manager = self.manager(lambda identity, state: True)
        identity = replace(self.identity(), bridge_states=(json.dumps(_state("stale-tab-fixture")),))
        current = _StorageContext()
        current.state["cookies"] = [_cookie("newer-live-fixture")]

        with patch("app.browser.session_snapshots._seed_new_tab", AsyncMock()) as seed:
            await self.launch(manager, identity, current)
            await current.new_page()
        seed.assert_not_awaited()
        self.assertEqual(current.scripts, [])
        self.assertEqual(await current.cookies(), [_cookie("newer-live-fixture")])

    async def test_no_live_frame_keeps_last_observed_tab_state_through_final_close(self):
        saved = []
        manager = self.manager(lambda identity, state: saved.append(copy.deepcopy(state)))
        identity = self.identity()
        context = _StorageContext()
        await self.launch(manager, identity, context)
        self.assertTrue(await manager.snapshot_session(identity, context))
        context.pages = []  # The short health tab has now closed.
        self.assertTrue(await manager.snapshot_session(identity, context))
        await manager.close_context(identity.key)

        self.assertGreaterEqual(len(saved), 3)
        self.assertEqual(saved[-1]["sessionStorage"], _state("rotated-fixture")["sessionStorage"])

    async def test_cookie_rotation_without_observed_frame_does_not_mix_old_tab_auth(self):
        saved = []
        manager = self.manager(lambda identity, state: saved.append(copy.deepcopy(state)))
        identity = self.identity()
        context = _StorageContext()
        self.assertTrue(await manager.snapshot_session(identity, context))
        context.pages = []
        context.state["cookies"] = [_cookie("different-session-fixture")]

        self.assertTrue(await manager.snapshot_session(identity, context))

        self.assertNotIn("sessionStorage", saved[-1])

    async def test_transaction_pause_blocks_periodic_and_explicit_saves_until_resumed(self):
        saved = []
        manager = self.manager(lambda identity, state: saved.append(copy.deepcopy(state)))
        identity = self.identity()
        context = _StorageContext()
        await self.launch(manager, identity, context)
        await manager.pause_session_checkpoints(context)
        context.state["cookies"] = [_cookie("guest-not-committed")]
        self.assertFalse(await manager.snapshot_session(identity, context))
        self.assertEqual(saved, [])
        # Unified capture is available for the login transaction's final state,
        # including anonymous accounts; it never invokes the save callback.
        state = await manager.capture_session_state(replace(identity, account_id=None), context)
        self.assertEqual(state["cookies"], [_cookie("guest-not-committed")])
        self.assertEqual(saved, [])
        manager.resume_session_checkpoints(context)
        self.assertTrue(await manager.snapshot_session(identity, context))
        self.assertEqual(len(saved), 1)

    async def test_paused_reauth_does_not_seed_old_tab_auth_after_all_cookies_are_cleared(self):
        manager = self.manager(lambda identity, state: True)
        identity = replace(self.identity(), bridge_states=(json.dumps(_state("old-auth-fixture")),))
        context = _StorageContext()
        await self.launch(manager, identity, context)
        await manager.pause_session_checkpoints(context)
        context.state["cookies"] = []

        with patch("app.browser.session_snapshots._seed_new_tab", AsyncMock()) as seed:
            await context.new_page()

        seed.assert_not_awaited()
        manager.resume_session_checkpoints(context)

    async def test_cancelled_new_page_preparation_closes_only_the_unreturned_page(self):
        manager = self.manager(lambda identity, state: True)
        identity = replace(self.identity(), bridge_states=(json.dumps(_state("saved-fixture")),))
        context = _StorageContext()
        await self.launch(manager, identity, context)

        with patch("app.browser.session_snapshots._seed_new_tab", AsyncMock(
                side_effect=asyncio.CancelledError())):
            with self.assertRaises(asyncio.CancelledError):
                await context.new_page()

        context.pages[-1].close.assert_awaited_once()
        self.assertFalse(context.closed)


class LocalSeedCleanupTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, *, cancel_blank=False, fail_reset=False):
        page = SimpleNamespace(url="about:blank", route=AsyncMock(), unroute=AsyncMock())
        session = SimpleNamespace(send=AsyncMock(), detach=AsyncMock())

        async def goto(url, **_kwargs):
            if url == "about:blank" and cancel_blank:
                raise asyncio.CancelledError()
            page.url = url

        async def evaluate(_script, *_args):
            return {"url": page.url, "token": page.url.rsplit("/", 1)[-1]}

        async def send(method, payload):
            if fail_reset and payload == {"bypass": False}:
                raise RuntimeError("synthetic reset failure")

        page.goto = AsyncMock(side_effect=goto)
        page.evaluate = AsyncMock(side_effect=evaluate)
        session.send.side_effect = send
        context = SimpleNamespace(new_cdp_session=AsyncMock(return_value=session))
        return page, context, session

    async def test_cancel_during_blank_cleanup_still_unroutes_resets_and_detaches(self):
        page, context, session = self.fixture(cancel_blank=True)

        with self.assertRaises(asyncio.CancelledError):
            await _seed_new_tab(page, context, _state("fixture"))

        page.unroute.assert_awaited_once()
        self.assertEqual(session.send.await_args.args, ("Network.setBypassServiceWorker", {"bypass": False}))
        session.detach.assert_awaited_once()

    async def test_failed_bypass_reset_does_not_skip_detach(self):
        page, context, session = self.fixture(fail_reset=True)

        await _seed_new_tab(page, context, _state("fixture"))

        page.unroute.assert_awaited_once()
        session.detach.assert_awaited_once()
