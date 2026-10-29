"""Share downloads must use the just-verified scope, never publishing cookies."""
import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import app.db as db
import app.main as main
from app import download_sessions
from app.config import Config
from app.download_credentials import DownloadCredentialStore, profile_identity
from app.engine.monitor import MonitorEngine
from app.models import AccountRiskState, DouyinAccount


def cookie(value, domain=".douyin.com"):
    return {"name": "sessionid", "value": value, "domain": domain,
            "path": "/", "expires": -1, "httpOnly": True, "secure": True}


class NativeDownloadCredentialsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.previous_engine = db._engine
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        db.init_db(str(self.root / "isolated.db"))
        self.profile = str(self.root / "profile")
        with db.get_session() as session:
            account = DouyinAccount(platform="douyin", nickname="fixture",
                profile_dir=self.profile, cookie="sessionid=OLD_RAW_COOKIE",
                storage_state=json.dumps({"cookies": [cookie("OLD_PUBLISH_COOKIE")]}))
            session.add(account)
            session.commit()
            session.refresh(account)
            self.account_id = account.id
        self.store = DownloadCredentialStore(self.root / "credentials")
        self.store.save("douyin", self.account_id, [cookie("NEW_DOWNLOAD_COOKIE")],
                        verified=True, user_agent="fixture-UA", profile_dir=self.profile)
        self.seen = []
        seen = self.seen

        class Client:
            def __init__(self, supplied_cookie, user_agent, **kwargs):
                seen.append(supplied_cookie)

            async def fetch_video_detail(self, aweme_id):
                return {"aweme_id": aweme_id}

        self.patches = [
            patch.object(download_sessions, "refresh_download_session", AsyncMock(return_value={"download_status": "ready"})),
            patch.object(download_sessions, "credential_store", return_value=self.store),
            patch.object(main, "resolve_aweme_id", AsyncMock(return_value="7686317511540821299")),
            patch.object(main, "DouyinClient", Client),
            patch.object(main, "parse_aweme", return_value=SimpleNamespace(media_type="video")),
            patch.object(main, "_native_aweme_metadata", return_value={"id": "fixture"}),
        ]
        for item in self.patches:
            item.start()

    async def asyncTearDown(self):
        for item in reversed(self.patches):
            item.stop()
        if db._engine is not None:
            db._engine.dispose()
        db._engine = self.previous_engine
        self.temp.cleanup()

    def body(self):
        return main.ShareDownloadIn(share_text="https://www.douyin.com/video/7686317511540821299",
            account_id=self.account_id, output_dir=str(self.root / "out"), download=False)

    def native_args(self):
        return {"account_id": self.account_id, "output_root": self.root,
                "quality": "highest", "should_download": False,
                "save_metadata": False, "save_thumbnail": False,
                "proxy": "", "user_agent": "fixture-UA"}

    async def test_real_share_boundary_passes_fresh_verified_cookie_to_native_client(self):
        result = await main.share_download(self.body())
        self.assertTrue(result["ok"])
        self.assertEqual(self.seen, ["sessionid=NEW_DOWNLOAD_COOKIE"])
        self.assertEqual(list(self.store.root.glob(".download-*.cookies.txt")), [])

    async def test_share_exception_still_removes_temporary_cookie_export(self):
        with patch.object(main, "_douyin_native_share", AsyncMock(side_effect=RuntimeError("synthetic failure"))):
            with self.assertRaises(RuntimeError):
                await main.share_download(self.body())
        self.assertEqual(list(self.store.root.glob(".download-*.cookies.txt")), [])

    async def test_native_tls_failure_is_a_safe_download_result_without_invalidating_login(self):
        from curl_cffi.requests.exceptions import SSLError
        client = SimpleNamespace(fetch_video_detail=AsyncMock(side_effect=SSLError(
            "Cookie=PRIVATE_COOKIE https://cdn.example/v?signature=PRIVATE_SIGNED_URL", code=77)))
        with patch.object(main, "DouyinClient", return_value=client):
            result = await main.share_download(self.body())
        self.assertFalse(result["ok"])
        error = result["results"][0]["error"]
        self.assertIn("证书文件", error)
        self.assertIn("curl 77", error)
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertEqual(self.store.metadata("douyin", self.account_id)["status"], "ready")
        self.assertEqual(list(self.store.root.glob(".download-*.cookies.txt")), [])
        with db.get_session() as session:
            self.assertEqual(session.get(DouyinAccount, self.account_id).status, "active")

    async def test_native_ca_preparation_failure_is_safe_and_never_falls_back(self):
        from app.tls_runtime import CertificateBundleError
        with patch.object(main, "DouyinClient", side_effect=CertificateBundleError("PRIVATE_CA_PATH")):
            result = await main.share_download(self.body())
        self.assertFalse(result["ok"])
        self.assertIn("证书文件准备失败", result["results"][0]["error"])
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertEqual(self.store.metadata("douyin", self.account_id)["status"], "ready")
        self.assertEqual(list(self.store.root.glob(".download-*.cookies.txt")), [])

    def browser_runtime(self):
        from app.browser.identity import Identity
        locks = {}
        browser = SimpleNamespace(
            identity_for=lambda account: Identity.from_account(account, str(self.root), "fixture-UA"),
            lock_for=lambda key: locks.setdefault(key, asyncio.Lock()),
        )
        return browser, MonitorEngine(Config(), browser)

    async def test_native_http403_reads_same_account_browser_through_real_guard(self):
        from app.browser import douyin_detail
        browser, engine = self.browser_runtime()
        raw = {"aweme_id": "7686317511540821299", "video": {"duration": 30000}}
        fetch = AsyncMock(return_value=(raw, ""))
        client = SimpleNamespace(fetch_video_detail=AsyncMock(return_value=None), last_error="http_403")
        with patch.object(main, "browser", browser), patch.object(main, "engine", engine), \
                patch.object(main, "DouyinClient", return_value=client), \
                patch.object(douyin_detail, "fetch_douyin_video_detail", fetch):
            result = await main.share_download(self.body())
        self.assertTrue(result["ok"])
        self.assertEqual(result["results"][0]["metadata"]["detail_source"], "browser_network")
        fetch.assert_awaited_once()
        manager, identity, target = fetch.await_args.args
        self.assertIs(manager, browser)
        self.assertEqual((identity.account_id, identity.profile_dir, identity.platform, identity.ua),
                         (self.account_id, self.profile, "douyin", "fixture-UA"))
        self.assertEqual(target, "7686317511540821299")
        self.assertEqual(json.loads(identity.bridge_states[0])["cookies"][0]["value"], "NEW_DOWNLOAD_COOKIE")
        self.assertEqual(list(self.store.root.glob(".download-*.cookies.txt")), [])

    async def test_non_403_transport_results_never_start_a_browser_fallback(self):
        for error in ("http_401", "http_429", "http_503", "empty_body", ""):
            with self.subTest(error=error):
                client = SimpleNamespace(fetch_video_detail=AsyncMock(return_value=None), last_error=error)
                fallback = AsyncMock()
                with patch.object(main, "DouyinClient", return_value=client), \
                        patch.object(main, "_douyin_browser_share_detail", fallback):
                    result = await main.share_download(self.body())
                self.assertFalse(result["ok"])
                fallback.assert_not_awaited()
                self.assertNotIn("更换", result["results"][0]["error"])

    async def test_browser_fallback_honors_manual_hold_before_opening_any_page(self):
        from app.browser import douyin_detail
        browser, engine = self.browser_runtime()
        with db.get_session() as session:
            session.add(AccountRiskState(account_id=self.account_id, manual_review_required=True))
            session.commit()
        fetch = AsyncMock()
        record = self.store.read_record("douyin", self.account_id)
        with patch.object(main, "browser", browser), patch.object(main, "engine", engine), \
                patch.object(douyin_detail, "fetch_douyin_video_detail", fetch):
            with self.assertRaisesRegex(main.ShareDownloadError, "冷却"):
                await main._douyin_browser_share_detail(self.account_id, "7686317511540821299", record, "")
        fetch.assert_not_awaited()

    async def test_browser_fallback_rejects_changed_user_agent_before_page_open(self):
        from app.browser import douyin_detail
        browser, engine = self.browser_runtime()
        fetch = AsyncMock()
        record = self.store.read_record("douyin", self.account_id)
        record["user_agent"] = "changed-UA"
        with patch.object(main, "browser", browser), patch.object(main, "engine", engine), \
                patch.object(douyin_detail, "fetch_douyin_video_detail", fetch):
            with self.assertRaisesRegex(main.ShareDownloadError, "浏览器环境已变化"):
                await main._douyin_browser_share_detail(self.account_id, "7686317511540821299", record, "")
        fetch.assert_not_awaited()

    async def test_observed_browser_challenge_records_real_risk_without_expiring_account(self):
        from app.browser import douyin_detail
        browser, engine = self.browser_runtime()
        record = self.store.read_record("douyin", self.account_id)
        fetch = AsyncMock(return_value=(None, "verification_required"))
        with patch.object(main, "browser", browser), patch.object(main, "engine", engine), \
                patch.object(douyin_detail, "fetch_douyin_video_detail", fetch):
            with self.assertRaisesRegex(main.ShareDownloadError, "人工完成安全验证"):
                await main._douyin_browser_share_detail(self.account_id, "7686317511540821299", record, "")
        with db.get_session() as session:
            self.assertEqual(session.get(DouyinAccount, self.account_id).status, "active")
            state = session.get(AccountRiskState, self.account_id)
            self.assertTrue(state.manual_review_required)

    async def test_native_without_verified_record_cannot_fallback_to_publish_cookie(self):
        with self.assertRaises(main.ShareDownloadError):
            await main._douyin_native_share("https://www.douyin.com/video/7686317511540821299", **self.native_args())
        self.assertEqual(self.seen, [])

    async def test_foreign_record_or_changed_profile_never_reaches_native_client(self):
        record = self.store.read_record("douyin", self.account_id)
        for patch_value in ({"account_id": self.account_id + 1}, {"platform": "kuaishou"},
                            {"status": "unconfirmed"}, {"profile_identity": profile_identity(self.profile + "-other")}):
            with self.subTest(patch_value=patch_value):
                with self.assertRaises(main.ShareDownloadError):
                    await main._douyin_native_share("https://www.douyin.com/video/7686317511540821299",
                        download_record={**copy.deepcopy(record), **patch_value}, **self.native_args())
        self.assertEqual(self.seen, [])

    async def test_native_header_excludes_other_douyin_group_domains(self):
        record = self.store.read_record("douyin", self.account_id)
        record["cookies"] += [cookie("OTHER_DOMAIN_COOKIE", ".amemv.com")]
        await main._douyin_native_share("https://www.douyin.com/video/7686317511540821299",
            download_record=record, **self.native_args())
        self.assertEqual(self.seen, ["sessionid=NEW_DOWNLOAD_COOKIE"])

    async def test_xhs_browser_cold_bridge_uses_verified_download_record(self):
        from app.browser.identity import Identity
        with db.get_session() as session:
            account = session.get(DouyinAccount, self.account_id)
            account.platform = "xhs"
            account.storage_state = json.dumps({"cookies": [cookie("OLD_PUBLISH_COOKIE", ".xiaohongshu.com")]})
            session.add(account)
            session.commit()
        xhs_cookie = {**cookie("NEW_XHS_DOWNLOAD_COOKIE", ".xiaohongshu.com"), "name": "web_session"}
        self.store.save("xhs", self.account_id, [xhs_cookie], verified=True,
                        user_agent="fixture-UA", profile_dir=self.profile)
        record = self.store.read_record("xhs", self.account_id)
        observed = []

        def identity_for(account):
            return Identity.from_account(account, str(self.root), "fixture-UA")

        async def guarded(_account_id, _kind, _key, operation, **kwargs):
            return await operation()

        async def fetch(browser, identity, *args, **kwargs):
            observed.extend(json.loads(identity.bridge_states[-1])["cookies"])
            return {"note_id": "fixture"}, ""

        work = SimpleNamespace(media_type="images", medias=[object()])
        reference = SimpleNamespace(note_id="fixture", xsec_token="", xsec_source="pc_feed")
        with patch.object(main, "browser", SimpleNamespace(identity_for=identity_for)), \
                patch.object(main, "_xhs_browser_reads_enabled", return_value=True), \
                patch.object(main, "_run_account_read", guarded), \
                patch.object(main, "xhs_resolve_note", AsyncMock(return_value=reference)), \
                patch.object(main, "fetch_xhs_note_detail", fetch), \
                patch("app.platforms.xhs.parse_note_detail", return_value=work):
            args = self.native_args()
            args.pop("user_agent")
            result = await main._xhs_native_share("https://www.xiaohongshu.com/explore/fixture",
                download_record=record, **args)
        self.assertTrue(result["ok"])
        self.assertEqual([item["value"] for item in observed], ["NEW_XHS_DOWNLOAD_COOKIE"])

    async def test_xhs_ready_download_scope_bypasses_only_invalid_publish_status(self):
        from app.browser.identity import Identity
        with db.get_session() as session:
            account = session.get(DouyinAccount, self.account_id)
            account.platform = "xhs"
            account.status = "invalid"
            session.add(account)
            session.commit()
        self.store.save("xhs", self.account_id,
                        [{**cookie("NEW_XHS_DOWNLOAD_COOKIE", ".xiaohongshu.com"),
                          "name": "web_session"}], verified=True,
                        user_agent="fixture-UA", profile_dir=self.profile)
        record = self.store.read_record("xhs", self.account_id)
        locks = {}
        browser = SimpleNamespace(
            identity_for=lambda account: Identity.from_account(
                account, str(self.root), "fixture-UA"),
            lock_for=lambda key: locks.setdefault(key, asyncio.Lock()),
        )
        engine = MonitorEngine(Config(), browser)
        fetch = AsyncMock(return_value=({"note_id": "fixture"}, ""))
        reference = SimpleNamespace(note_id="fixture", xsec_token="", xsec_source="pc_feed")
        work = SimpleNamespace(media_type="images", medias=[object()])
        args = self.native_args()
        args.pop("user_agent")
        source_url = "https://www.xiaohongshu.com/explore/fixture"
        with patch.object(main, "browser", browser), \
                patch.object(main, "engine", engine), \
                patch.object(main, "_xhs_browser_reads_enabled", return_value=True), \
                patch.object(main, "xhs_resolve_note", AsyncMock(return_value=reference)), \
                patch.object(main, "fetch_xhs_note_detail", fetch), \
                patch("app.platforms.xhs.parse_note_detail", return_value=work):
            # Exercise the real engine and risk controller, without a scope bypass.
            with self.assertRaisesRegex(main.ShareDownloadError, "登录态已失效"):
                await main._xhs_native_share(source_url, **args)
            fetch.assert_not_awaited()

            with self.assertRaisesRegex(main.ShareDownloadError, "重新检查下载登录"):
                await main._xhs_native_share(source_url,
                    download_record={**record, "status": "unconfirmed"}, **args)
            fetch.assert_not_awaited()

            result = await main._xhs_native_share(source_url,
                download_record=record, **args)
            self.assertTrue(result["ok"])
            fetch.assert_awaited_once()

            # A verified download scope must not override a platform safety hold.
            with db.get_session() as session:
                state = session.get(AccountRiskState, self.account_id)
                state.manual_review_required = True
                session.add(state)
                session.commit()
            with self.assertRaisesRegex(main.ShareDownloadError, "人工验证"):
                await main._xhs_native_share(source_url,
                    download_record=record, **args)
            fetch.assert_awaited_once()
        with db.get_session() as session:
            self.assertEqual(session.get(DouyinAccount, self.account_id).status, "invalid")
