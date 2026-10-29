"""Download scope checks use current owned sessions without changing publishing."""
import asyncio
import json
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.db as db
from app import download_sessions as service
from app import download_session_api as api
from app.browser.identity import Identity
from app.download_credentials import DownloadCredentialStore
from app.models import DouyinAccount


def _cookie(value="new-live-token"):
    return {"name": "sessionid", "value": value, "domain": ".douyin.com",
            "path": "/", "expires": -1, "httpOnly": True, "secure": True}


class DownloadSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.previous_engine = db._engine
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        db.init_db(str(self.root / "fixture.db"))
        self.profile = str(self.root / "profile")
        with db.get_session() as session:
            account = DouyinAccount(platform="douyin", nickname="fixture account",
                profile_dir=self.profile, ua="fixture-UA", status="active",
                storage_state=json.dumps({"cookies": [_cookie("old-DB-token")]}),
                creator_storage_state="fixture-publish-snapshot")
            session.add(account)
            session.commit()
            session.refresh(account)
            self.account_id = account.id
        self.context = SimpleNamespace(cookies=AsyncMock(return_value=[_cookie()]))
        context, root = self.context, self.root
        self.guard_events = []
        guard_events = self.guard_events

        class Browser:
            def identity_for(self, account):
                return Identity.from_account(account, str(root / "profiles"), "fixture-UA")

            @asynccontextmanager
            async def lock_for(self, key):
                guard_events.append(("enter", key))
                try:
                    yield
                finally:
                    guard_events.append(("exit", key))

            async def context_for(self, _identity):
                return context

        self.runtime = SimpleNamespace(cfg=SimpleNamespace(db_path=str(self.root / "fixture.db")),
            browser=Browser(), engine=None, open_browsers={}, login_tasks={})
        self.runtime_patch = patch.object(service, "_runtime", return_value=self.runtime)
        self.runtime_patch.start()
        self.douyin_probe_patch = patch.object(service, "_probe_douyin_publish_scope",
                                               AsyncMock(return_value="unconfirmed"))
        self.douyin_probe_patch.start()
        self.environment_patch = patch.dict("os.environ", {"HAIKE_DOWNLOAD_CREDENTIALS_DIR": ""})
        self.environment_patch.start()

    async def asyncTearDown(self):
        service._PUBLISH_EVIDENCE.pop(self.account_id, None)
        self.runtime_patch.stop()
        self.douyin_probe_patch.stop()
        self.environment_patch.stop()
        db._engine.dispose()
        db._engine = self.previous_engine
        self.temp.cleanup()

    def assert_publish_unchanged(self):
        with db.get_session() as session:
            account = session.get(DouyinAccount, self.account_id)
            self.assertEqual(account.status, "active")
            self.assertEqual(account.creator_storage_state, "fixture-publish-snapshot")
            self.assertEqual(json.loads(account.storage_state)["cookies"][0]["value"], "old-DB-token")

    async def test_check_saves_live_cookie_and_leaves_both_publish_snapshots_unchanged(self):
        with patch.object(service, "_probe_download_scope", AsyncMock(return_value="ready")):
            result = await service.refresh_download_session(self.account_id)
        self.assertEqual(result["download_status"], "ready")
        self.assertEqual(result["publish_status"], "unconfirmed")
        self.assertFalse(result["publish_available"])
        self.assertEqual(service.credential_store().read_cookies("douyin", self.account_id)[0]["value"],
                         "new-live-token")
        self.assertNotIn("new-live-token", json.dumps(result))
        self.assertEqual(self.guard_events, [("enter", f"acc:{self.account_id}"),
                                             ("exit", f"acc:{self.account_id}")])
        self.assert_publish_unchanged()

    async def test_existing_owned_window_is_reused_without_reentering_its_guard(self):
        self.runtime.open_browsers[self.account_id] = SimpleNamespace(active=True, context=self.context)
        with patch.object(service, "_probe_download_scope", AsyncMock(return_value="ready")):
            result = await service.refresh_download_session(self.account_id)
        self.assertEqual(result["download_status"], "ready")
        self.assertEqual(self.guard_events, [])

    async def test_download_login_failure_does_not_invalidate_publishing(self):
        with patch.object(service, "_probe_download_scope", AsyncMock(return_value="login_required")):
            result = await service.refresh_download_session(self.account_id)
        self.assertEqual(result["download_status"], "login_required")
        self.assert_publish_unchanged()

    async def test_cancellation_releases_account_guard_without_saving(self):
        with patch.object(service, "_probe_download_scope", AsyncMock(side_effect=asyncio.CancelledError())):
            with self.assertRaises(asyncio.CancelledError):
                await service.refresh_download_session(self.account_id)
        self.assertEqual(self.guard_events[-1][0], "exit")
        self.assertEqual(service.credential_store().metadata("douyin", self.account_id)["status"], "not_saved")

    async def test_open_download_login_preserves_publish_status(self):
        self.runtime.open_account_browser = AsyncMock(return_value={"ok": True})
        await service.open_download_login(self.account_id)
        self.runtime.open_account_browser.assert_awaited_once_with(self.account_id,
            url="https://www.douyin.com/user/self", preserve_publish_status=True)

    async def test_state_callback_updates_only_opted_in_owned_profile_and_keeps_check_time(self):
        identity = self.runtime.browser.identity_for(service._account(self.account_id))
        self.assertFalse(service.capture_enabled_download_snapshot(identity, {"cookies": [_cookie()]}))
        store = service.credential_store()
        store.save("douyin", self.account_id, [_cookie("previous")], verified=True, profile_dir=self.profile)
        before = store.metadata("douyin", self.account_id)["last_checked_at"]
        self.assertTrue(service.capture_enabled_download_snapshot(identity, {"cookies": [_cookie()]}))
        self.assertEqual(store.metadata("douyin", self.account_id)["last_checked_at"], before)
        identity.profile_dir = str(self.root / "other")
        self.assertFalse(service.capture_enabled_download_snapshot(identity, {"cookies": [_cookie("foreign")]}))
        self.assertEqual(store.read_cookies("douyin", self.account_id)[0]["value"], "new-live-token")

    async def test_list_never_exports_saved_transport_or_cookie_values(self):
        store = service.credential_store()
        store.save("douyin", self.account_id, [_cookie()], proxy="http://secret:password@proxy.test",
                   verified=True, profile_dir=self.profile)
        result = service.list_download_sessions()
        self.assertEqual(result["items"][0]["id"], self.account_id)
        for secret in ("new-live-token", "password", "fixture-publish-snapshot", "old-DB-token"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(len(result["service_fingerprint"]), 64)

    async def test_channels_real_scope_evidence_expires_and_cookie_rotation_invalidates_it(self):
        with db.get_session() as session:
            account = session.get(DouyinAccount, self.account_id)
            account.platform = "shipinhao"
            session.add(account)
            session.commit()
        channel_cookie = {**_cookie(), "domain": "channels.weixin.qq.com"}
        self.context.cookies.return_value = [channel_cookie]
        with patch.object(service, "_probe_download_scope", AsyncMock(return_value="ready")):
            ready = await service.refresh_download_session(self.account_id)
        self.assertTrue(ready["publish_verified"])
        self.assertEqual(ready["publish_status"], "active")
        service._PUBLISH_EVIDENCE[self.account_id]["expires"] = 0
        self.assertFalse(service.download_session_metadata(self.account_id)["publish_verified"])
        with patch.object(service, "_probe_download_scope", AsyncMock(return_value="ready")):
            await service.refresh_download_session(self.account_id)
        service.credential_store().refresh_snapshot("shipinhao", self.account_id,
            [{**channel_cookie, "value": "rotated-fixture"}], profile_dir=self.profile)
        self.assertFalse(service.download_session_metadata(self.account_id)["publish_verified"])

    async def test_kuaishou_cp_failure_keeps_download_ready_without_claiming_publish_verified(self):
        with db.get_session() as session:
            account = session.get(DouyinAccount, self.account_id)
            account.platform = "kuaishou"
            session.add(account)
            session.commit()
        self.context.cookies.return_value = [{**_cookie(), "domain": ".kuaishou.com"}]
        with patch.object(service, "_probe_download_scope", AsyncMock(return_value="ready")), \
                patch.object(service, "_probe_kuaishou_publish_scope", AsyncMock(return_value=False)):
            result = await service.refresh_download_session(self.account_id)
        self.assertEqual(result["download_status"], "ready")
        self.assertEqual(result["publish_status"], "unconfirmed")
        self.assertFalse(result["publish_verified"])
        with patch.object(service, "_probe_download_scope", AsyncMock(return_value="ready")), \
                patch.object(service, "_probe_kuaishou_publish_scope", AsyncMock(return_value=True)):
            result = await service.refresh_download_session(self.account_id)
        self.assertTrue(result["publish_verified"])
        self.assertEqual(result["publish_status"], "active")


class DownloadScopeEvidenceTests(unittest.TestCase):
    def test_creator_scope_does_not_count_as_kuaishou_download_scope(self):
        self.assertFalse(service._is_current_user_response("kuaishou",
                         "https://cp.kuaishou.com/rest/v/profile/get"))
        self.assertTrue(service._is_current_user_response("kuaishou",
                        "https://www.kuaishou.com/rest/v/profile/get"))

    def test_only_platform_business_success_authenticates(self):
        self.assertTrue(service._response_verdict("douyin", {"status_code": 0, "user": {"uid": "fixture"}}))
        self.assertFalse(service._response_verdict("douyin", {"status_code": 8, "user": {"uid": "fixture"}}))
        self.assertTrue(service._response_verdict("kuaishou", {"result": 1, "userName": "fixture"}))
        self.assertFalse(service._response_verdict("kuaishou", {"result": 50, "userName": "fixture"}))
        self.assertTrue(service._response_verdict("xhs", {"success": True, "data": {"user_id": "fixture"}}))
        self.assertFalse(service._response_verdict("xhs", {"success": True, "data": {"guest": True, "user_id": "fixture"}}))
        self.assertTrue(service._response_verdict("shipinhao", {"errCode": 0, "data": {"nickname": "fixture"}}))
        self.assertFalse(service._response_verdict("shipinhao", {"errCode": 300334, "data": {"nickname": "fixture"}}))

    def test_missing_or_conflicting_success_fields_are_unconfirmed(self):
        self.assertFalse(service._response_verdict("douyin", {"user": {"uid": "fixture"}}))
        self.assertFalse(service._response_verdict("xhs", {"success": True, "code": -100,
                                                        "data": {"user_id": "fixture"}}))

    def test_current_kuaishou_cookie_names_need_web_identity_not_creator_cookie(self):
        cookies = [{"name": name, "value": "fixture", "domain": ".kuaishou.com"}
                   for name in ("userId", "kuaishou.server.webday7_st")]
        self.assertTrue(service._has_auth_cookies("kuaishou", cookies))
        self.assertFalse(service._has_auth_cookies("kuaishou", [
            {"name": "kuaishou.web.cp.api_st", "value": "fixture", "domain": ".kuaishou.com"}]))


class DownloadPageProbeTests(unittest.IsolatedAsyncioTestCase):
    async def probe(self, payload, *, http_status=200, final_url=None,
                    login_visible=False, cancel=False):
        class Response:
            url = "https://www.douyin.com/aweme/v1/web/user/profile/self/"
            status = http_status

            async def json(self):
                return payload

        class Page:
            closed = False
            url = final_url or "https://www.douyin.com/user/self"

            def on(self, _event, callback):
                self.callback = callback

            async def goto(self, *_args, **_kwargs):
                if cancel:
                    raise asyncio.CancelledError()
                self.callback(Response())
                await asyncio.sleep(0)

            def get_by_text(self, *_args, **_kwargs):
                async def visible(**_options):
                    return login_visible
                return SimpleNamespace(first=SimpleNamespace(is_visible=visible))

            async def close(self):
                self.closed = True

        page = Page()
        context = SimpleNamespace(new_page=AsyncMock(return_value=page),
                                  cookies=AsyncMock(return_value=[_cookie()]),
                                  close=AsyncMock(), add_cookies=AsyncMock(), clear_cookies=AsyncMock())
        account = SimpleNamespace(platform="douyin")
        try:
            return await service._probe_download_scope(context, account, response_timeout=0.03)
        finally:
            self.assertTrue(page.closed)
            context.close.assert_not_awaited()
            context.add_cookies.assert_not_awaited()
            context.clear_cookies.assert_not_awaited()

    async def test_positive_business_and_current_auth_cookie_are_ready(self):
        self.assertEqual(await self.probe({"status_code": 0, "user": {"uid": "fixture"}}), "ready")

    async def test_http_failure_or_missing_business_success_is_not_ready(self):
        self.assertEqual(await self.probe({"status_code": 0, "user": {"uid": "fixture"}},
                                         http_status=500), "unconfirmed")
        self.assertEqual(await self.probe({"user": {"uid": "fixture"}}), "unconfirmed")

    async def test_login_redirect_requires_relogin_without_changing_any_cookie(self):
        self.assertEqual(await self.probe({"status_code": 8},
                         final_url="https://www.douyin.com/login"), "login_required")

    async def test_cancelled_probe_closes_only_its_page(self):
        with self.assertRaises(asyncio.CancelledError):
            await self.probe({}, cancel=True)

    async def test_channels_bootstrap_success_waits_for_later_profile_instead_of_conflicting(self):
        class Response:
            status = 200

            def __init__(self, path, payload):
                self.url = "https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/auth/" + path
                self.payload = payload

            async def json(self):
                return self.payload

        class Page:
            url = "https://channels.weixin.qq.com/platform"

            def on(self, _event, callback):
                self.callback = callback

            async def goto(self, *_args, **_kwargs):
                self.callback(Response("auth_data", {"errCode": 0, "data": {}}))
                await asyncio.sleep(0.01)
                self.callback(Response("get_auth_info", {"errCode": 0,
                    "data": {"finderUser": {"nickname": "fixture"}}}))

            async def close(self):
                pass

        context = SimpleNamespace(new_page=AsyncMock(return_value=Page()), cookies=AsyncMock(
            return_value=[{**_cookie(), "domain": "channels.weixin.qq.com"}]))
        result = await service._probe_download_scope(context, SimpleNamespace(platform="shipinhao"),
                                                     response_timeout=0.2)
        self.assertEqual(result, "ready")


class DownloadLoginPollingTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_download_login_is_checked_once_without_consuming_original_task(self):
        task_id = "fixture-download-login"
        runtime = SimpleNamespace(login_browser_start=AsyncMock(return_value={"task_id": task_id, "status": "opening"}),
                                 login_ks_start=None, login_channels_start=None, login_xhs_start=None,
                                 login_tasks={task_id: {"status": "confirmed", "platform": "douyin", "account_id": 3}})
        account = {"id": 3, "platform": "douyin", "download_status": "ready"}
        refresh = AsyncMock(return_value=account)
        try:
            with patch.object(service, "_runtime", return_value=runtime), \
                    patch.object(service, "refresh_download_session", refresh), \
                    patch.object(service, "credential_store", return_value=SimpleNamespace(selected_account=lambda _p: 3)):
                await api.add_download_account(api.DownloadLoginInput(platform="douyin"))
                first = await api.login_task(task_id)
                runtime.login_tasks.pop(task_id)
                second = await api.login_task(task_id)
            refresh.assert_awaited_once_with(3)
            self.assertEqual(first, second)
            self.assertEqual(first["account"]["download_status"], "ready")
        finally:
            api._LOGIN_TASKS.pop(task_id, None)
            api._LOGIN_LOCKS.pop(task_id, None)

    async def test_login_ui_does_not_expose_original_exception_detail(self):
        public = api._public_login({"status": "error", "hint": "cookie=fixture-secret",
                                    "error": "fixture-secret"}, "task")
        self.assertNotIn("fixture-secret", json.dumps(public))


class DownloadSessionApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(api.router)
        self.client = TestClient(app)

    def test_metadata_surface_is_available_without_starting_a_browser(self):
        expected = {"items": [{"id": 1, "platform": "douyin", "download_status": "not_saved"}],
                    "available": False}
        with patch.object(service, "list_download_sessions", return_value=expected):
            response = self.client.get("/api/download-sessions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)

    def test_backend_capture_exception_does_not_leak_cookie_into_response(self):
        with patch.object(service, "refresh_download_session",
                          AsyncMock(side_effect=RuntimeError("Cookie: fixture-secret"))):
            response = self.client.post("/api/download-sessions/1/check")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("fixture-secret", response.text)

    def test_login_rejects_unsupported_platform_before_starting_a_task(self):
        response = self.client.post("/api/download-sessions/login", json={"platform": "unknown"})
        self.assertEqual(response.status_code, 422)
