"""The first account-window checkpoint must not strand its lifetime guard."""
import asyncio
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import app.db as db
import app.main as main
from app.browser.identity import Identity
from app.models import DouyinAccount


class _Page:
    def on(self, *_args):
        pass

    async def goto(self, *_args, **_kwargs):
        pass

    async def wait_for_timeout(self, *_args):
        pass


class _Context:
    def __init__(self):
        self.closed = False
        self.close_handlers = []

    def on(self, event, handler):
        if event == "close":
            self.close_handlers.append(handler)

    async def new_page(self):
        return _Page()

    async def close(self):
        if self.closed:
            return
        self.closed = True
        for handler in self.close_handlers:
            handler(self)


class AccountOpenCheckpointCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.previous_engine = db._engine
        self.temp = tempfile.TemporaryDirectory(prefix="account-checkpoint-fixture-")
        db.init_db(str(Path(self.temp.name) / "fixture.db"))
        with db.get_session() as session:
            account = DouyinAccount(
                platform="kuaishou",
                profile_dir=str(Path(self.temp.name) / "profile"),
            )
            session.add(account)
            session.commit()
            session.refresh(account)
            self.account_id = account.id
        self.context = _Context()
        self.account_guard = asyncio.Lock()

    async def asyncTearDown(self):
        lease = main.open_browsers.pop(self.account_id, None)
        if lease is not None:
            await lease.close()
        await asyncio.sleep(0)
        db._engine.dispose()
        db._engine = self.previous_engine
        self.temp.cleanup()

    async def open_with_checkpoint(self, checkpoint):
        context = self.context
        account_guard = self.account_guard
        profiles = str(Path(self.temp.name) / "profiles")

        class Browser:
            def identity_for(self, account):
                return Identity.from_account(account, profiles, "fixture-UA")

            @asynccontextmanager
            async def lock_for(self, _key):
                async with account_guard:
                    yield

            async def open_headed(self, _identity):
                return context

            async def snapshot_session(self, identity, live_context):
                self_identity = identity
                assert self_identity.account_id is not None
                assert live_context is context
                return await checkpoint()

        with patch.object(main, "browser", Browser()), patch.object(
                main, "_opened_page_login_state", AsyncMock(return_value="authenticated")):
            return await main.open_account_browser(self.account_id)

    async def test_cancelled_first_checkpoint_closes_context_and_releases_account(self):
        checkpoint = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await self.open_with_checkpoint(checkpoint)
        self.assertTrue(self.context.closed)
        self.assertFalse(self.account_guard.locked())
        self.assertNotIn(self.account_id, main.open_browsers)

    async def test_failed_first_checkpoint_cleans_up_before_propagating(self):
        checkpoint = AsyncMock(side_effect=RuntimeError("fixture checkpoint failure"))
        with self.assertRaisesRegex(RuntimeError, "fixture checkpoint failure"):
            await self.open_with_checkpoint(checkpoint)
        self.assertTrue(self.context.closed)
        self.assertFalse(self.account_guard.locked())
        self.assertNotIn(self.account_id, main.open_browsers)

    async def test_successful_checkpoint_keeps_guard_until_window_is_closed(self):
        checkpoint = AsyncMock(return_value=True)
        result = await self.open_with_checkpoint(checkpoint)
        self.assertTrue(result["ok"])
        self.assertFalse(self.context.closed)
        self.assertTrue(self.account_guard.locked())
        self.assertIn(self.account_id, main.open_browsers)
        checkpoint.assert_awaited_once()

        await main.open_browsers[self.account_id].close()
        await asyncio.sleep(0)
        self.assertTrue(self.context.closed)
        self.assertFalse(self.account_guard.locked())
        self.assertNotIn(self.account_id, main.open_browsers)


if __name__ == "__main__":
    unittest.main()
