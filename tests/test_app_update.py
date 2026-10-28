"""Real temporary-install transactions; no production data, services, or network."""
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("haike_app_update_test", ROOT / "portable/app_update.py")
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


class AppUpdateTests(unittest.TestCase):
    def test_large_portable_inventory_does_not_use_small_update_manifest_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, bundle, original, plan = self.fixture(Path(temporary))
            manifest = root / "PACKAGE-MANIFEST.json"
            manifest.write_bytes(manifest.read_bytes() + b" " * (update.MAX_MANIFEST_BYTES + 1))
            self.assertEqual(update.preflight(bundle, root)["version"], "1.0.1")

    def write(self, root, name, content):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def fixture(self, folder):
        folder = folder.resolve()
        root, bundle = folder / "旧海客 installation", folder / "bundle"
        release = {"edition": update.EDITION, "version": "1.0.0", "channel": "stable",
                   "platform": update.PLATFORM, "runtime_id": update.RUNTIME_ID, "data_schema": 1,
                   "source_commit": "old-commit", "template_update": {"id": "local-template-patch"}}
        self.write(root, "VERSION.json", update.json_bytes({**release, "source_commit": "default-commit"}))
        self.write(root, "RELEASE.json", update.json_bytes(release))
        self.write(root, "Haike_video/backlot/server.py", b"# original program\n")
        self.write(root, "Haike_video/backlot/ui/avatar-generator/index.html", b"<html>old</html>")
        self.write(root, "Haike_video/requirements.txt", b"synthetic-approved-dependency==1\n")
        self.write(root, "creatorhub/package-lock.json", b'{"lockfileVersion":3}')
        shipped = [path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()]
        self.write(root, "PACKAGE-MANIFEST.json", update.json_bytes({"schema": 1, "files": [
            {"path": name, "size": (root / name).stat().st_size, "sha256": update.digest(root / name), "mutable": False}
            for name in shipped]}))
        for name, content in {
            "Haike_video/.env.local": b"SYNTHETIC_PRIVATE_CONFIGURATION",
            "creatorhub/config.yaml": b"SYNTHETIC_ACCOUNT_CONFIG",
            "creatorhub/data/account.sqlite3": b"SYNTHETIC_ACCOUNT_DATABASE",
            "creatorhub/browser_data/Default/Cookies": b"SYNTHETIC_COOKIE_DATABASE",
            "Haike_video/.backlot/queue.sqlite3": b"SYNTHETIC_TASKS",
            "Haike_video/projects/synthetic/renders/final.mp4": b"SYNTHETIC_VIDEO",
            "copy_skill/copy_skill-main/config/content_intelligence.local.json": b"SYNTHETIC_PERSONAL_PREFS",
        }.items():
            self.write(root, name, content)
        original = {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}
        payloads = {"Haike_video/backlot/server.py": b"# new compatible program\n",
                    "Haike_video/backlot/new_component.py": b"# newly shipped component\n",
                    "Haike_video/backlot/ui/avatar-generator/index.html": b"<html>new</html>"}
        files = []
        for name, content in payloads.items():
            self.write(bundle / "payload", name, content)
            files.append({"path": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                          "before_sha256": hashlib.sha256(original[name]).hexdigest() if name in original else None})
        plan = {"schema": 1, "edition": update.EDITION, "platform": update.PLATFORM, "version": "1.0.1",
                "base_version": "1.0.0", "runtime_id": update.RUNTIME_ID, "data_schema": 1,
                "source_commit": "b" * 40, "files": files,
                "required_locks": [{"path": name, "sha256": update.digest(root / name)}
                                   for name in shipped if update.is_dependency_path(name)]}
        self.write(bundle, "UPDATE-MANIFEST.json", update.json_bytes(plan))
        return root, bundle, original, plan

    def assert_original(self, root, original):
        for name, content in original.items():
            self.assertEqual((root / name).read_bytes(), content, name)
        self.assertFalse((root / "Haike_video/backlot/new_component.py").exists())

    def rewrite_plan(self, bundle, plan):
        self.write(bundle, "UPDATE-MANIFEST.json", update.json_bytes(plan))

    def zip_bundle(self, folder, bundle, extras=None):
        path = folder / "patch.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in bundle.rglob("*"):
                if item.is_file():
                    archive.write(item, item.relative_to(bundle).as_posix())
            for name, content in (extras or {}).items():
                archive.writestr(name, content)
        return path

    def test_success_is_idempotent_and_manifest_and_private_data_survive_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            root, bundle, original, plan = self.fixture(Path(folder))
            self.assertEqual(update.read_release(root)["source_commit"], "old-commit")
            self.assertEqual(update.preflight(bundle, root), plan)
            self.assertFalse((root / ".local").exists())
            calls = []
            def healthy(target, manifest):
                calls.append((target, manifest["version"]))
                self.assertEqual(update.read_release(target)["version"], "1.0.1")
                return True
            result = update.apply_update(bundle, root, healthy)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(len(calls), 1)
            self.assertEqual(update.read_release(root)["template_update"], {"id": "local-template-patch"})
            installed = json.loads((root / "PACKAGE-MANIFEST.json").read_bytes())
            for item in installed["files"]:
                self.assertEqual(item["sha256"], update.digest(root / item["path"]))
                self.assertEqual(item["size"], (root / item["path"]).stat().st_size)
            for name, content in original.items():
                if name not in {"RELEASE.json", "PACKAGE-MANIFEST.json", *(f["path"] for f in plan["files"])}:
                    self.assertEqual((root / name).read_bytes(), content, name)
            self.assertTrue(update.apply_update(bundle, root)["already_current"])
            self.assertEqual(update.pending_receipts(root), [])
            self.assertEqual(update.rollback(root, result["backup"])["status"], "rolled_back")
            self.assert_original(root, original)
            self.assertTrue(update.rollback(root, result["backup"])["ok"])
            self.assert_original(root, original)

    def test_bad_restart_and_raised_restart_both_restore_original_program_and_data(self):
        for raises in (False, True):
            with self.subTest(raises=raises), tempfile.TemporaryDirectory() as folder:
                root, bundle, original, _ = self.fixture(Path(folder))
                def bad_health(target, manifest):
                    if raises:
                        raise OSError("synthetic startup failure")
                    return False
                with self.assertRaisesRegex(update.UpdateError, "已回退"):
                    update.apply_update(bundle, root, bad_health)
                self.assert_original(root, original)
                receipts = list((root / ".local/app-updates").glob("*/receipt.json"))
                self.assertEqual(len(receipts), 1)
                self.assertEqual(json.loads(receipts[0].read_bytes())["status"], "rolled_back")
                self.assertEqual(update.pending_receipts(root), [])

    def test_corruption_incompatible_environment_and_local_changes_fail_before_backup(self):
        scenarios = ("payload", "dependency", "missing-lock", "runtime", "data-schema", "baseline",
                     "source", "unknown-version", "program-edit", "user-created-new-path", "before-hash")
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as folder:
                root, bundle, original, plan = self.fixture(Path(folder))
                if scenario == "payload":
                    (bundle / "payload/Haike_video/backlot/server.py").write_bytes(b"damaged")
                elif scenario == "dependency":
                    (root / "Haike_video/requirements.txt").write_bytes(b"different")
                elif scenario == "missing-lock":
                    plan["required_locks"] = []
                elif scenario in {"runtime", "data-schema", "baseline"}:
                    key, value = {"runtime": ("runtime_id", "other-environment"), "data-schema": ("data_schema", 2),
                                  "baseline": ("base_version", "0.9.0")}[scenario]
                    plan[key] = value
                elif scenario == "source":
                    (root / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
                elif scenario == "unknown-version":
                    release = json.loads((root / "RELEASE.json").read_bytes())
                    del release["version"]
                    (root / "RELEASE.json").write_bytes(update.json_bytes(release))
                elif scenario == "program-edit":
                    (root / "Haike_video/backlot/server.py").write_bytes(b"# user edited program\n")
                elif scenario == "user-created-new-path":
                    self.write(root, "Haike_video/backlot/new_component.py", b"# user-authored private script\n")
                elif scenario == "before-hash":
                    plan["files"][0]["before_sha256"] = "f" * 64
                self.rewrite_plan(bundle, plan)
                snapshot = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
                with self.assertRaises(update.UpdateError):
                    update.apply_update(bundle, root)
                self.assertFalse((root / ".local").exists())
                for name, content in snapshot.items():
                    self.assertEqual((root / name).read_bytes(), content)

    def test_private_service_runtime_metadata_and_malicious_paths_are_not_programs(self):
        rejected = ("../server.py", "/outside.py", "C:/outside.py", "Haike_video/backlot/../../private.py",
                    "Haike_video/backlot/aux.py", "Haike_video/backlot/server.py.", "Haike_video/backlot/server.py ",
                    "Haike_video\\backlot\\server.py", "Haike_video/backlot/a.py:stream",
                    "Haike_video/.env.local", "Haike_video/.backlot/config.json", "Haike_video/projects/test/render.py",
                    "Haike_video/backlot/config/private.json", "Haike_video/requirements.txt",
                    "Haike_video/templates/library-covers/private.jpg", "Haike_video/templates/a/assets/portrait.png",
                    "creatorhub/app/main.py", "creatorhub/config.yaml", "creatorhub/data/creatorhub.sqlite3",
                    "copy_skill/copy_skill-main/src/main.py", "api-platform/app/main.py", "runtime/python/tool.py",
                    "RELEASE.json", "VERSION.json", "PACKAGE-MANIFEST.json")
        for name in rejected:
            with self.subTest(name=name):
                self.assertFalse(update.is_program_path(name))
        self.assertTrue(update.is_program_path("Haike_video/backlot/server.py"))
        self.assertTrue(update.is_program_path("Haike_video/backlot/ui/avatar-generator/assets/index-hashed.js"))
        self.assertTrue(update.is_program_path("portable/update_worker.py"))

    def test_manifest_protected_paths_case_collision_and_duplicate_fields_are_rejected(self):
        for scenario in ("private", "case", "duplicate-json", "migration", "delete"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as folder:
                root, bundle, original, plan = self.fixture(Path(folder))
                if scenario == "private":
                    plan["files"][0]["path"] = "creatorhub/config.yaml"
                elif scenario == "case":
                    # Windows would alias this name to the first payload.
                    plan["files"].append({**plan["files"][0], "path": "Haike_video/backlot/SERVER.py"})
                elif scenario == "migration":
                    plan["migrations"] = ["unsafe-migration.py"]
                elif scenario == "delete":
                    plan["deletes"] = ["Haike_video/backlot/server.py"]
                self.rewrite_plan(bundle, plan)
                if scenario == "duplicate-json":
                    path = bundle / "UPDATE-MANIFEST.json"
                    path.write_bytes(path.read_bytes().replace(b'"schema": 1', b'"schema": 0, "schema": 1'))
                with self.assertRaises(update.UpdateError):
                    update.apply_update(bundle, root)
                self.assert_original(root, original)

    def test_interrupted_partial_replacement_is_detected_and_recoverable(self):
        for crash_before in ("Haike_video/backlot/new_component.py", "RELEASE.json"):
            with self.subTest(crash_before=crash_before), tempfile.TemporaryDirectory() as folder:
                root, bundle, original, _ = self.fixture(Path(folder))
                real_atomic = update._atomic_write
                def power_failure(path, content):
                    if Path(path) == root / crash_before:
                        raise KeyboardInterrupt("synthetic process death")
                    real_atomic(path, content)
                with patch.object(update, "_atomic_write", side_effect=power_failure):
                    with self.assertRaises(KeyboardInterrupt):
                        update.apply_update(bundle, root)
                pending = update.pending_receipts(root)
                self.assertEqual(len(pending), 1)
                self.assertEqual(pending[0]["status"], "applying")
                with self.assertRaisesRegex(update.UpdateError, "上次更新被中断"):
                    update.apply_update(bundle, root)
                self.assertTrue(update.rollback(root, pending[0]["backup"])["ok"])
                self.assert_original(root, original)
                self.assertEqual(update.pending_receipts(root), [])

    def test_write_failure_automatically_rolls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            root, bundle, original, _ = self.fixture(Path(folder))
            real_atomic = update._atomic_write
            failed = False
            def disk_failure(path, content):
                nonlocal failed
                if Path(path) == root / "RELEASE.json" and not failed:
                    failed = True
                    raise OSError("synthetic filesystem failure")
                real_atomic(path, content)
            with patch.object(update, "_atomic_write", side_effect=disk_failure):
                with self.assertRaisesRegex(update.UpdateError, "已回退"):
                    update.apply_update(bundle, root)
            self.assert_original(root, original)

    def test_later_user_edit_and_damaged_backup_block_entire_rollback(self):
        for scenario in ("user-edit", "damaged-backup"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as folder:
                root, bundle, _, _ = self.fixture(Path(folder))
                result = update.apply_update(bundle, root)
                if scenario == "user-edit":
                    (root / "Haike_video/backlot/server.py").write_bytes(b"# subsequent user work\n")
                else:
                    (Path(result["backup"]) / "files/Haike_video/backlot/server.py").write_bytes(b"damaged")
                snapshot = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
                with self.assertRaises(update.UpdateError):
                    update.rollback(root, result["backup"])
                for name, content in snapshot.items():
                    self.assertEqual((root / name).read_bytes(), content)

    def test_installation_identity_and_rollback_receipt_cannot_reach_user_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root, bundle, _, _ = self.fixture(Path(folder))
            result = update.apply_update(bundle, root)
            directory = Path(result["backup"])
            receipt = json.loads((directory / "receipt.json").read_bytes())
            receipt["files"][0]["path"] = "creatorhub/config.yaml"
            (directory / "receipt.json").write_bytes(update.json_bytes(receipt))
            with self.assertRaisesRegex(update.UpdateError, "受保护"):
                update.rollback(root, directory)
            with self.assertRaises(update.UpdateError):
                update.rollback(root, Path(folder))

    def test_archive_roundtrip_rejects_extra_members_traversal_symlinks_and_bad_hash(self):
        scenarios = ("valid", "extra", "traversal", "symlink", "bad-hash", "duplicate")
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                root, bundle, _, _ = self.fixture(folder)
                extras = {"extra": {"launch.exe": b"unknown executable"},
                          "traversal": {"../outside.py": b"escape"}}.get(scenario)
                if scenario == "bad-hash":
                    (bundle / "payload/Haike_video/backlot/server.py").write_bytes(b"damaged payload")
                path = self.zip_bundle(folder, bundle, extras)
                if scenario in {"symlink", "duplicate"}:
                    with zipfile.ZipFile(path, "a") as archive:
                        if scenario == "symlink":
                            item = zipfile.ZipInfo("payload/Haike_video/backlot/link.py")
                            item.create_system = 3
                            item.external_attr = (stat.S_IFLNK | 0o777) << 16
                            archive.writestr(item, b"/outside")
                        else:
                            archive.writestr("payload/Haike_video/backlot/SERVER.py", b"duplicate")
                destination = folder / "unpacked"
                if scenario == "valid":
                    update.extract_bundle(path, destination)
                    self.assertTrue(update.preflight(destination, root))
                else:
                    with self.assertRaises(update.UpdateError):
                        update.extract_bundle(path, destination)
                self.assertFalse((folder / "outside.py").exists())

    def test_archive_expansion_and_existing_destination_are_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            _, bundle, _, _ = self.fixture(folder)
            path = self.zip_bundle(folder, bundle)
            with patch.object(update, "MAX_ARCHIVE_BYTES", 4):
                with self.assertRaisesRegex(update.UpdateError, "大小限制"):
                    update.extract_bundle(path, folder / "unpacked")
            with patch.object(update, "MAX_FILE_BYTES", 4):
                with self.assertRaises(update.UpdateError):
                    update.extract_bundle(path, folder / "unpacked")
            self.write(folder, "occupied/precious.txt", b"keep")
            with self.assertRaises(update.UpdateError):
                update.extract_bundle(path, folder / "occupied")
            self.assertEqual((folder / "occupied/precious.txt").read_bytes(), b"keep")

    def test_lock_is_exclusive_and_reusable_after_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with update._install_lock(root):
                with self.assertRaises(update.UpdateError):
                    with update._install_lock(root):
                        self.fail("second installer acquired the same lock")
            with update._install_lock(root):
                pass

    def test_target_link_is_rejected_when_platform_supports_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            outside = folder / "outside"
            outside.mkdir()
            root = folder / "installation"
            root.mkdir()
            try:
                (root / "Haike_video").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Windows symlink creation requires developer mode or privilege")
            with self.assertRaises(update.UpdateError):
                update.safe_path(root, "Haike_video/backlot/server.py")


if __name__ == "__main__":
    unittest.main()
