"""Account-window previews and checkpoint close retain exact manager ownership."""
import asyncio
import copy
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

import app.db as db
import app.main as main
from app import download_sessions as service
from app import download_session_api as api
from app.browser.identity import Identity
from app.browser.manager import BrowserManager
from app.models import DouyinAccount, PublishTask


class _Context:
    def __init__(self):
        self.closed = False
        self.handlers = []
        self.events = []
        self.state = {"cookies": [{"name": "passToken", "value": "fixture-rotated",
            "domain": ".kuaishou.com", "path": "/", "expires": -1}], "origins": []}

    def on(self, event, callback):
        if event == "close":
            self.handlers.append(callback)

    async def storage_state(self):
        self.events.append("save")
        return copy.deepcopy(self.state)

    async def cookies(self):
        return copy.deepcopy(self.state["cookies"])

    async def set_extra_http_headers(self, *_args):
        pass

    async def add_init_script(self, *_args):
        pass

    async def add_cookies(self, *_args):
        pass

    async def close(self):
        self.events.append("close")
        self.closed = True
        for callback in self.handlers:
            callback(self)


class DownloadAccountLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.previous_engine = db._engine
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        db.init_db(str(self.root / "test.db"))
        with db.get_session() as session:
            account = DouyinAccount(platform="kuaishou", nickname="fixture", status="active",
                profile_dir=str(self.root / "profile"), identity_mode="legacy")
            session.add(account)
            session.commit()
            session.refresh(account)
            self.account_id = account.id
        self.saved = []
        self.context = _Context()
        self.manager = BrowserManager("fixture-UA", str(self.root / "profiles"),
            session_state_callback=lambda identity, state: self.saved.append(state))
        self.manager._pw = SimpleNamespace(chromium=SimpleNamespace(
            launch_persistent_context=AsyncMock(return_value=self.context)), stop=AsyncMock())
        self.runtime = SimpleNamespace(cfg=SimpleNamespace(db_path=str(self.root / "test.db")),
            browser=self.manager, engine=None, open_browsers={}, login_tasks={},
            _release_open_browser=main._release_open_browser)
        self.patches = [patch.object(service, "_runtime", return_value=self.runtime),
                        patch.object(main, "open_browsers", self.runtime.open_browsers),
                        patch.dict("os.environ", {"HAIKE_DOWNLOAD_CREDENTIALS_DIR": ""})]
        for item in self.patches:
            item.start()
        self.identity = self.manager.identity_for(service._account(self.account_id))

    async def asyncTearDown(self):
        lease = self.runtime.open_browsers.get(self.account_id)
        if lease is not None:
            await self.runtime._release_open_browser(self.account_id, lease)
        await self.manager.stop()
        if not self.context.closed:
            await self.context.close()
        for task_id, own in list(api._LOGIN_TASKS.items()):
            if own.get("kind") == "account-window" and own.get("account_id") == self.account_id:
                api._LOGIN_TASKS.pop(task_id, None)
                api._LOGIN_LOCKS.pop(task_id, None)
        for item in reversed(self.patches):
            item.stop()
        db._engine.dispose()
        db._engine = self.previous_engine
        self.temp.cleanup()

    async def make_lease(self):
        await self.manager._launch_persistent(self.identity, headless=False)
        self.manager._register_interactive_context(self.identity, self.context)
        guard = self.manager.lock_for(f"acc:{self.account_id}")
        await guard.acquire()

        class Guard:
            async def __aexit__(self, *_args):
                guard.release()

        lease = main._OpenBrowserLease(self.context, Guard())
        self.runtime.open_browsers[self.account_id] = lease
        return lease

    async def test_existing_window_preview_has_uuid_and_never_starts_forced_relogin(self):
        await self.make_lease()
        with patch.object(service, "open_download_login", AsyncMock(return_value={"ok": True})):
            result = await api.open_login(self.account_id)
        self.assertTrue(re.fullmatch("[0-9a-f]{32}", result["task_id"]))
        self.assertIn("preview.png", result["preview_url"])
        self.assertEqual(self.runtime.login_tasks, {})
        self.assertEqual(api._pending_preview_task(result["task_id"])["preview_context_id"], id(self.context))
        with patch.object(service, "refresh_download_session", AsyncMock(return_value={
                "id": self.account_id, "platform": "kuaishou", "download_status": "ready"})):
            await api.check_session(self.account_id)
        with self.assertRaises(HTTPException) as error:
            api._pending_preview_task(result["task_id"])
        self.assertEqual(error.exception.status_code, 410)

    async def test_checkpoint_closes_background_manager_context_and_preserves_account_and_profile(self):
        await self.manager.context_for(self.identity)
        result = await service.checkpoint_close_download_account(self.account_id)
        self.assertTrue(result["closed"])
        self.assertTrue(self.context.closed)
        self.assertTrue(self.saved)
        self.assertLess(self.context.events.index("save"), self.context.events.index("close"))
        self.assertNotIn(self.account_id, self.manager._contexts)
        self.assertNotIn(self.account_id, self.manager._profile_process_locks)
        self.assertTrue(Path(self.identity.profile_dir).is_dir())
        with db.get_session() as session:
            self.assertEqual(session.get(DouyinAccount, self.account_id).status, "active")

    async def test_checkpoint_closes_exact_owned_lease_and_releases_its_guard(self):
        await self.make_lease()
        result = await service.checkpoint_close_download_account(self.account_id)
        self.assertTrue(result["closed"])
        self.assertNotIn(self.account_id, self.runtime.open_browsers)
        self.assertFalse(self.manager.lock_for(f"acc:{self.account_id}").locked())

    async def test_empty_publish_queue_does_not_allow_a_foreign_lease_context(self):
        lease = await self.make_lease()
        original = lease.context
        lease.context = _Context()
        with self.assertRaises(HTTPException) as error:
            await service.checkpoint_close_download_account(self.account_id)
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(original.closed)
        self.assertFalse(lease.context.closed)

    async def test_account_profile_change_cannot_save_old_window_as_new_profile(self):
        await self.make_lease()
        with db.get_session() as session:
            account = session.get(DouyinAccount, self.account_id)
            account.profile_dir = str(self.root / "different")
            session.add(account)
            session.commit()
        with self.assertRaises(HTTPException) as error:
            await service.checkpoint_close_download_account(self.account_id)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.saved, [])

    async def test_pending_qr_or_publishing_or_busy_guard_prevents_close(self):
        await self.manager.context_for(self.identity)
        self.runtime.login_tasks["fixture"] = {"status": "waiting", "platform": "kuaishou", "account_id": self.account_id}
        with self.assertRaises(HTTPException):
            await service.checkpoint_close_download_account(self.account_id)
        self.runtime.login_tasks.clear()
        with db.get_session() as session:
            task = PublishTask(account_id=self.account_id, platform="kuaishou", status="publishing")
            session.add(task)
            session.commit()
            session.refresh(task)
            task_id = task.id
        with self.assertRaises(HTTPException):
            await service.checkpoint_close_download_account(self.account_id)
        with db.get_session() as session:
            session.delete(session.get(PublishTask, task_id))
            session.commit()
        guard = self.manager.lock_for(f"acc:{self.account_id}")
        await guard.acquire()
        try:
            with self.assertRaises(HTTPException):
                await service.checkpoint_close_download_account(self.account_id)
        finally:
            guard.release()
        self.assertFalse(self.context.closed)

    async def test_failed_checkpoint_retains_owned_context_for_retry(self):
        await self.manager.context_for(self.identity)
        self.manager._session_snapshots.callback = lambda *_args: False
        with self.assertRaises(HTTPException):
            await service.checkpoint_close_download_account(self.account_id)
        self.assertFalse(self.context.closed)
        self.assertIs(self.manager._contexts[self.account_id], self.context)
