"""Native KS/Channels health must keep the same headed mode as login/publish."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from tests import test_browser_session_snapshots as fixtures


class NativeAccountLaunchPolicyTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.BrowserSessionSnapshotTests.asyncSetUp
    asyncTearDown = fixtures.BrowserSessionSnapshotTests.asyncTearDown
    manager = fixtures.BrowserSessionSnapshotTests.manager
    identity = fixtures.BrowserSessionSnapshotTests.identity
    noop = fixtures.BrowserSessionSnapshotTests.noop

    def make_manager(self):
        manager = self.manager(None)
        manager._pw = SimpleNamespace(stop=self.noop)
        manager._uses_xhs_cdp = lambda _identity: False
        context = fixtures._Context()
        manager._launch_persistent = AsyncMock(return_value=context)
        manager._start_minimize_hold = AsyncMock()
        return manager, context

    async def test_native_health_uses_one_offscreen_headed_context_and_reuses_it(self):
        for platform in ("shipinhao", "kuaishou"):
            with self.subTest(platform=platform):
                manager, context = self.make_manager()
                identity = replace(self.identity(platform), identity_mode="native")

                self.assertIs(await manager.context_for(identity), context)
                self.assertIs(await manager.context_for(identity), context)

                manager._launch_persistent.assert_awaited_once_with(
                    identity, headless=False, off_screen=True)
                manager._start_minimize_hold.assert_awaited_once_with(identity, context)

    async def test_legacy_and_other_platform_launch_policy_is_unchanged(self):
        for platform, mode, expected_headless in (
                ("shipinhao", "legacy", True), ("kuaishou", "legacy", True),
                ("douyin", "native", True), ("xhs", "native", False)):
            with self.subTest(platform=platform, mode=mode):
                manager, context = self.make_manager()
                identity = replace(self.identity(platform), identity_mode=mode)

                self.assertIs(await manager.context_for(identity), context)

                manager._launch_persistent.assert_awaited_once_with(identity, headless=expected_headless)
                manager._start_minimize_hold.assert_not_awaited()

    async def test_close_waits_for_owned_window_hold_to_stop_before_context_close(self):
        manager, context = self.make_manager()
        identity = replace(self.identity(), identity_mode="native")
        order = []

        async def hold():
            try:
                await asyncio.Future()
            finally:
                order.append("hold-stopped")

        original_close = context.close

        async def close():
            order.append("context-close")
            await original_close()

        context.close = close
        await manager.context_for(identity)
        task = asyncio.create_task(hold())
        manager._minimize_holds[identity.key] = task
        await asyncio.sleep(0)

        await manager.close_context(identity.key)

        self.assertTrue(task.done())
        self.assertNotIn(identity.key, manager._minimize_holds)
        self.assertEqual(order, ["hold-stopped", "context-close"])
