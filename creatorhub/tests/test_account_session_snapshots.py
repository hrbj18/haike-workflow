"""Latest account sessions must survive routine window closure without relogin."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import app.db as db
import app.main as main
from app.browser.identity import Identity
from app.models import DouyinAccount


class AccountSessionSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.previous_engine = db._engine
        self.temp = tempfile.TemporaryDirectory()
        db.init_db(str(Path(self.temp.name) / "fixture.db"))
        self.profile = str(Path(self.temp.name) / "account-profile")
        with db.get_session() as session:
            account = DouyinAccount(platform="kuaishou", profile_dir=self.profile,
                                    storage_state='{"cookies":[]}', status="invalid")
            session.add(account)
            session.commit()
            session.refresh(account)
            self.account_id = account.id
        self.identity = Identity(account_id=self.account_id, profile_dir=self.profile,
                                 platform="kuaishou")
        self.state = {"cookies": [{"name": "session", "value": "fixture-new",
                                  "domain": ".kuaishou.com", "path": "/"}],
                      "origins": []}

    def tearDown(self):
        db._engine.dispose()
        db._engine = self.previous_engine
        self.temp.cleanup()

    def test_rotated_session_updates_both_kuaishou_snapshots_without_claiming_login(self):
        self.assertTrue(main._persist_account_session_state(self.identity, self.state))
        with db.get_session() as session:
            account = session.get(DouyinAccount, self.account_id)
            self.assertEqual(json.loads(account.storage_state), self.state)
            self.assertEqual(account.creator_storage_state, account.storage_state)
            self.assertEqual(account.status, "invalid")

    def test_other_profile_cannot_overwrite_account_snapshot(self):
        self.identity.profile_dir = str(Path(self.temp.name) / "other-profile")
        self.assertFalse(main._persist_account_session_state(self.identity, self.state))
        with db.get_session() as session:
            account = session.get(DouyinAccount, self.account_id)
            self.assertEqual(account.storage_state, '{"cookies":[]}')

    def test_empty_snapshot_does_not_erase_saved_state(self):
        self.assertFalse(main._persist_account_session_state(
            self.identity, {"cookies": [], "origins": []}))


class BrowserLeaseSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_window_close_checkpoints_before_context_is_destroyed(self):
        order = []

        class Context:
            async def close(self):
                order.append("close")

        async def save():
            order.append("save")

        lease = main._OpenBrowserLease(Context(), AsyncMock(), snapshot_callback=save)
        await lease.close()
        await lease.close()
        self.assertEqual(order, ["save", "close"])

    async def test_snapshot_error_still_closes_window_and_releases_guard(self):
        context, guard = AsyncMock(), AsyncMock()
        lease = main._OpenBrowserLease(
            context, guard, snapshot_callback=AsyncMock(side_effect=RuntimeError("fixture")))
        await lease.close()
        context.close.assert_awaited_once()
        guard.__aexit__.assert_awaited_once()

    async def test_cancelled_snapshot_closes_before_releasing_profile(self):
        context, guard = AsyncMock(), AsyncMock()
        lease = main._OpenBrowserLease(context, guard,
            snapshot_callback=AsyncMock(side_effect=asyncio.CancelledError()))
        with self.assertRaises(asyncio.CancelledError):
            await lease.close()
        context.close.assert_awaited_once()
        guard.__aexit__.assert_awaited_once()
