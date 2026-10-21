"""Offline concurrency contracts for account-owned platform operations."""
import asyncio
import tempfile
import unittest
from pathlib import Path

import app.db as db
from app.config import Config
from app.engine.monitor import MonitorEngine
from app.models import DouyinAccount
from app.risk import OperationKind


class _ObservedLock(asyncio.Lock):
    def __init__(self):
        super().__init__()
        self.waiting = asyncio.Event()
        self.acquired = asyncio.Event()

    async def acquire(self):
        if self.locked():
            self.waiting.set()
        result = await super().acquire()
        self.acquired.set()
        return result


class _BrowserLocks:
    def __init__(self):
        self.locks = {}

    def lock_for(self, key):
        return self.locks.setdefault(key, _ObservedLock())


class OperationGuardConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.previous_engine = db._engine
        self.tmp = tempfile.TemporaryDirectory()
        db.init_db(str(Path(self.tmp.name) / "guard.db"))
        self.cfg = Config()
        self.cfg.engine.media_dir = str(Path(self.tmp.name) / "media")
        self.browser = _BrowserLocks()
        self.accounts = []
        with db.get_session() as session:
            for _ in range(3):
                account = DouyinAccount(nickname="fixture", status="active", proxy="")
                session.add(account)
                session.commit()
                session.refresh(account)
                self.accounts.append(account.id)
        self.engine = MonitorEngine(self.cfg, self.browser)

    def tearDown(self):
        db._engine.dispose()
        db._engine = self.previous_engine
        self.tmp.cleanup()

    async def _operation(self, account_id, *, entered=None, release=None):
        async with self.engine.operation_guard(account_id, OperationKind.READ_LIGHT):
            if entered is not None:
                entered.set()
            if release is not None:
                await release.wait()

    def _set_proxy(self, account_id, proxy):
        with db.get_session() as session:
            account = session.get(DouyinAccount, account_id)
            account.proxy = proxy
            session.add(account)
            session.commit()

    async def _cancel(self, task):
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_manual_account_window_does_not_block_other_account_on_same_exit(self):
        occupied, _, available = self.accounts
        account_lock = self.browser.lock_for(f"acc:{occupied}")
        await account_lock.acquire()  # Same ownership as a manual account window.
        queued = asyncio.create_task(self._operation(occupied))
        try:
            await asyncio.wait_for(account_lock.waiting.wait(), timeout=1)
            await asyncio.wait_for(self._operation(available), timeout=0.25)
        finally:
            queued.cancel()
            await asyncio.gather(queued, return_exceptions=True)
            account_lock.release()

    async def test_cancelling_account_wait_keeps_manual_lock_and_releases_capacity(self):
        self.cfg.engine.active_accounts = 1
        self.engine = MonitorEngine(self.cfg, self.browser)
        occupied, _, available = self.accounts
        account_lock = self.browser.lock_for(f"acc:{occupied}")
        await account_lock.acquire()
        queued = asyncio.create_task(self._operation(occupied))
        try:
            await asyncio.wait_for(account_lock.waiting.wait(), timeout=1)
            await self._cancel(queued)
            self.assertTrue(account_lock.locked())
            await asyncio.wait_for(self._operation(available), timeout=0.25)
        finally:
            queued.cancel()
            await asyncio.gather(queued, return_exceptions=True)
            account_lock.release()
        await asyncio.wait_for(self._operation(occupied), timeout=0.25)

    async def test_cancelling_global_wait_releases_account_reservation(self):
        self.cfg.engine.active_accounts = 1
        self.engine = MonitorEngine(self.cfg, self.browser)
        occupied, waiting, _ = self.accounts
        release = asyncio.Event()
        entered = asyncio.Event()
        holder = asyncio.create_task(self._operation(occupied, entered=entered, release=release))
        queued = None
        try:
            await asyncio.wait_for(entered.wait(), timeout=1)
            queued = asyncio.create_task(self._operation(waiting))
            lock = self.browser.lock_for(f"acc:{waiting}")
            await asyncio.wait_for(lock.acquired.wait(), timeout=1)
            await self._cancel(queued)
            self.assertFalse(lock.locked())
        finally:
            release.set()
            await asyncio.gather(holder, *([queued] if queued else []), return_exceptions=True)
        await asyncio.wait_for(self._operation(waiting), timeout=0.25)
        await asyncio.wait_for(self._operation(occupied), timeout=0.25)

    async def test_cancelling_network_wait_releases_account_and_global_capacity(self):
        self.cfg.engine.active_accounts = 2
        occupied, waiting, different_exit = self.accounts
        self._set_proxy(different_exit, "http://fixture-other-exit.example:8000")
        self.engine = MonitorEngine(self.cfg, self.browser)
        release = asyncio.Event()
        entered = asyncio.Event()
        holder = asyncio.create_task(self._operation(occupied, entered=entered, release=release))
        queued = None
        try:
            await asyncio.wait_for(entered.wait(), timeout=1)
            queued = asyncio.create_task(self._operation(waiting))
            lock = self.browser.lock_for(f"acc:{waiting}")
            await asyncio.wait_for(lock.acquired.wait(), timeout=1)
            await self._cancel(queued)
            self.assertFalse(lock.locked())
            # The first account still owns one global slot and the direct exit.
            # A leaked second global slot would block this unrelated exit.
            await asyncio.wait_for(self._operation(different_exit), timeout=0.25)
        finally:
            release.set()
            await asyncio.gather(holder, *([queued] if queued else []), return_exceptions=True)
        await asyncio.wait_for(self._operation(waiting), timeout=0.25)

    async def test_cancelling_running_operation_releases_all_capacity(self):
        self.cfg.engine.active_accounts = 1
        self.engine = MonitorEngine(self.cfg, self.browser)
        occupied, _, available = self.accounts
        entered = asyncio.Event()
        running = asyncio.create_task(self._operation(
            occupied, entered=entered, release=asyncio.Event()))
        try:
            await asyncio.wait_for(entered.wait(), timeout=1)
            await self._cancel(running)
        finally:
            running.cancel()
            await asyncio.gather(running, return_exceptions=True)
        await asyncio.wait_for(self._operation(occupied), timeout=0.25)
        await asyncio.wait_for(self._operation(available), timeout=0.25)

    async def test_operations_on_same_exit_still_serialize(self):
        active = peak = 0

        async def worker(account_id):
            nonlocal active, peak
            async with self.engine.operation_guard(account_id, OperationKind.READ_LIGHT):
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1

        await asyncio.wait_for(asyncio.gather(*(worker(aid) for aid in self.accounts)), timeout=1)
        self.assertEqual(peak, 1)

    async def test_global_limit_still_bounds_operations_on_distinct_exits(self):
        self.cfg.engine.active_accounts = 2
        for index, account_id in enumerate(self.accounts):
            self._set_proxy(account_id, f"http://fixture-exit-{index}.example:8000")
        self.engine = MonitorEngine(self.cfg, self.browser)
        active = peak = 0
        two_running = asyncio.Event()
        release = asyncio.Event()

        async def worker(account_id):
            nonlocal active, peak
            async with self.engine.operation_guard(account_id, OperationKind.READ_LIGHT):
                active += 1
                peak = max(peak, active)
                if active == 2:
                    two_running.set()
                try:
                    await release.wait()
                finally:
                    active -= 1

        tasks = [asyncio.create_task(worker(aid)) for aid in self.accounts]
        try:
            await asyncio.wait_for(two_running.wait(), timeout=1)
        finally:
            release.set()
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)
        self.assertEqual(peak, 2)


if __name__ == "__main__":
    unittest.main()
