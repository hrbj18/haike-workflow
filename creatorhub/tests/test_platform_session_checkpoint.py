"""Direct platform context closures checkpoint rotated login state first."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import app.main  # noqa: F401 - initialize package graph
from app.browser.identity import Identity
from app.browser import channels_fetcher, ks_fetcher
from app.platforms.channels import publish as channels
from app.platforms.kuaishou import publish as kuaishou


class _NavigationStopsHere:
    def on(self, *_args):
        pass

    async def goto(self, *_args, **_kwargs):
        raise RuntimeError("offline navigation fixture")


class PlatformSessionCheckpointTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, operation, mode):
        events = []
        page = _NavigationStopsHere()

        class Context:
            async def new_page(self):
                return page

            async def close(self):
                events.append("close")

        context = Context()

        async def open_context(_identity):
            return context

        async def stop_hold(_identity):
            events.append("stop_hold")

        manager = SimpleNamespace(open_background=open_context,
                                  open_headed=open_context,
                                  stop_minimize_hold=stop_hold)
        identity = Identity(account_id=42, profile_dir="fixture",
                            platform="kuaishou" if operation.startswith("ks") else "shipinhao")

        async def snapshot(given_identity, given_context):
            self.assertIs(given_identity, identity)
            self.assertIs(given_context, context)
            events.append("snapshot")
            if mode == "raises":
                raise RuntimeError("fixture snapshot failure")
            if mode == "cancelled":
                raise asyncio.CancelledError()
            return True

        if mode != "legacy":
            manager.snapshot_session = snapshot
        cancelled = False
        try:
            if operation.endswith("publish"):
                module = kuaishou if operation == "ks_publish" else channels
                publisher = module.publish_kuaishou if operation == "ks_publish" else module.publish_channels
                with tempfile.TemporaryDirectory() as temporary:
                    media = Path(temporary) / "fixture.mp4"
                    media.write_bytes(b"fixture; never uploaded")
                    with patch.object(module, "_dump", AsyncMock(return_value="")):
                        result = await publisher(manager, identity, "", "video", "", "", [str(media)])
            else:
                commenter = ks_fetcher.post_ks_comment if operation == "ks_comment" else channels_fetcher.post_channels_comment
                result = await commenter(manager, identity, "fixture-work", "fixture comment")
        except asyncio.CancelledError:
            cancelled = True
        self.assertEqual(cancelled, mode == "cancelled")
        if not cancelled:
            self.assertFalse(result[0])
            self.assertIn("offline navigation fixture", result[-1])
        expected = ([] if mode == "legacy" else ["snapshot"]) + ["close"]
        if operation.endswith("publish"):
            expected.append("stop_hold")
        self.assertEqual(events, expected)

    async def test_direct_publish_and_comment_close_checkpoint_first(self):
        for operation in ("ks_publish", "channels_publish", "ks_comment", "channels_comment"):
            with self.subTest(operation=operation):
                await self._run(operation, "available")

    async def test_snapshot_failure_still_closes_each_platform_context(self):
        for operation in ("ks_publish", "channels_publish", "ks_comment", "channels_comment"):
            with self.subTest(operation=operation):
                await self._run(operation, "raises")

    async def test_legacy_manager_without_snapshot_api_remains_compatible(self):
        for operation in ("ks_publish", "channels_publish", "ks_comment", "channels_comment"):
            with self.subTest(operation=operation):
                await self._run(operation, "legacy")

    async def test_snapshot_cancellation_closes_context_before_propagating(self):
        for operation in ("ks_publish", "channels_publish", "ks_comment", "channels_comment"):
            with self.subTest(operation=operation):
                await self._run(operation, "cancelled")


if __name__ == "__main__":
    unittest.main()
