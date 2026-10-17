"""Download authentication remains local, account-scoped and disposable."""
import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.download_credentials import (
    DownloadCredentialError, DownloadCredentialStore, resolve_store_root,
)


def cookie(value="fixture-secret", domain=".douyin.com", **extra):
    return {"name": "sessionid", "value": value, "domain": domain,
            "path": "/", "expires": -1, "httpOnly": True,
            "secure": True, "sameSite": "None", **extra}


class DownloadCredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.store = DownloadCredentialStore(self.root / "credentials")

    def tearDown(self):
        self.temp.cleanup()

    def save(self, account_id=1, **options):
        return self.store.save("douyin", account_id, [cookie()],
                               profile_dir=str(self.root / str(account_id)), **options)

    def test_module_can_load_without_creatorhub_or_third_party_imports(self):
        path = Path(__file__).resolve().parents[1] / "app/download_credentials.py"
        spec = importlib.util.spec_from_file_location("standalone_download_credentials", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.DownloadCredentialStore(self.store.root).metadata(
            "douyin", 1)["status"], "not_saved")

    def test_missing_or_unverified_credentials_cannot_be_selected(self):
        self.assertEqual(self.store.metadata("douyin", 1)["status"], "not_saved")
        self.assertEqual(self.save()["status"], "stored_unverified")
        with self.assertRaises(DownloadCredentialError):
            self.store.select("douyin", 1)

    def test_metadata_does_not_contain_cookie_transport_or_profile(self):
        metadata = self.save(verified=True, user_agent="fixture-UA",
                             proxy="http://private:password@127.0.0.1:8888")
        text = json.dumps(metadata)
        for secret in ("fixture-secret", "fixture-UA", "password", str(self.root)):
            self.assertNotIn(secret, text)
        self.assertEqual(metadata["status"], "ready")

    def test_other_account_platform_and_profile_cannot_read_snapshot(self):
        self.save(verified=True)
        for platform, account_id in (("douyin", 2), ("kuaishou", 1)):
            with self.assertRaises(DownloadCredentialError):
                self.store.read_cookies(platform, account_id)
        with self.assertRaises(DownloadCredentialError):
            self.store.read_cookies("douyin", 1, profile_dir=str(self.root / "different"))

    def test_domain_allowlist_and_expiry_preserve_only_valid_owned_cookies(self):
        future = time.time() + 500
        self.store.save("douyin", 1, [cookie(expires=future),
            cookie(domain="evildouyin.com"), cookie(domain=".kuaishou.com"),
            cookie(name="expired", expires=time.time()-1)], verified=True)
        saved = self.store.read_cookies("douyin", 1)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["expires"], future)
        self.assertTrue(saved[0]["httpOnly"])
        self.assertTrue(saved[0]["secure"])
        self.assertEqual(saved[0]["sameSite"], "None")

    def test_invalid_cookie_lines_cannot_inject_netscape_fields(self):
        self.store.save("douyin", 1, [cookie(), cookie(name="bad", value="value\nother"),
                                     cookie(name="bad\tname"), cookie(path="/\tother")], verified=True)
        self.assertEqual(len(self.store.read_cookies("douyin", 1)), 1)

    def test_netscape_keeps_httponly_and_session_semantics_then_deletes_file(self):
        self.save(verified=True)
        with self.store.cookie_file("douyin", 1) as filename:
            self.assertTrue(filename.is_file())
            text = filename.read_text(encoding="utf-8")
            self.assertIn("#HttpOnly_.douyin.com\tTRUE\t/\tTRUE\t0\tsessionid\t", text)
        self.assertFalse(filename.exists())
        self.assertEqual(self.store.read_cookies("douyin", 1)[0]["expires"], -1)

    def test_download_failure_and_cancellation_remove_temporary_file(self):
        self.save(verified=True)
        for failure in (RuntimeError("fixture"), KeyboardInterrupt()):
            with self.assertRaises(type(failure)):
                with self.store.cookie_file("douyin", 1) as filename:
                    raise failure
            self.assertFalse(filename.exists())

    def test_partitioned_cookie_is_not_flattened_to_another_cookie_scope(self):
        self.store.save("douyin", 1, [cookie(partitionKey="https://example.test")], verified=True)
        with self.assertRaises(DownloadCredentialError):
            with self.store.cookie_file("douyin", 1):
                self.fail("partitioned cookie was flattened")

    def test_selection_is_per_platform_and_delete_clears_only_that_selection(self):
        self.save(verified=True)
        self.store.save("kuaishou", 2, [cookie(domain=".kuaishou.com")], verified=True)
        self.store.select("douyin", 1)
        self.store.select("kuaishou", 2)
        self.assertEqual(self.store.selected_account("douyin"), 1)
        self.assertEqual(self.store.selected_account("kuaishou"), 2)
        self.store.delete("douyin", 1)
        self.assertIsNone(self.store.selected_account("douyin"))
        self.assertEqual(self.store.selected_account("kuaishou"), 2)

    def test_expired_saved_state_is_not_represented_as_ready(self):
        self.save(verified=True)
        with patch("app.download_credentials.time.time", return_value=time.time()+500):
            record = self.store.read_record("douyin", 1)
            record["cookies"][0]["expires"] = 1
            self.store._write(self.store._path("douyin", 1), record)
        self.assertEqual(self.store.metadata("douyin", 1)["status"], "login_required")

    def test_periodic_rotation_does_not_upgrade_unconfirmed_login(self):
        self.save(verified=True)
        self.store.update_status("douyin", 1, "unconfirmed")
        before = self.store.metadata("douyin", 1)["last_checked_at"]
        self.assertTrue(self.store.refresh_snapshot("douyin", 1, [cookie("rotated")],
                        profile_dir=str(self.root / "1")))
        self.assertEqual(self.store.metadata("douyin", 1)["status"], "unconfirmed")
        self.assertEqual(self.store.metadata("douyin", 1)["last_checked_at"], before)

    def test_environment_and_configuration_root_resolution(self):
        with patch.dict(os.environ, {"HAIKE_DOWNLOAD_CREDENTIALS_DIR": str(self.root / "override")}):
            self.assertEqual(resolve_store_root("unused", db_path="unused"), self.root / "override")
        with patch.dict(os.environ, {"HAIKE_DOWNLOAD_CREDENTIALS_DIR": ""}):
            self.assertEqual(resolve_store_root(db_path=self.root / "db.sqlite"),
                             self.root / "download-credentials")
            self.assertEqual(resolve_store_root(self.root),
                             self.root / "creatorhub/data/download-credentials")

    def test_unsafe_account_or_platform_paths_are_rejected(self):
        for platform, account_id in (("../douyin", 1), ("douyin", "../1"), ("douyin", True)):
            with self.assertRaises(DownloadCredentialError):
                self.store.metadata(platform, account_id)
