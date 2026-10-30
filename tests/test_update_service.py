"""Discovery, durable admission and real detached restart using fake services."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import URLError
import zipfile

from portable import app_update as core, update_service as service, update_worker as worker

spec = importlib.util.spec_from_file_location("app_update_fixture", Path(__file__).with_name("test_app_update.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)

SERVER = '''import http.server,json,os,sys,uuid
from pathlib import Path
root=Path.cwd().parent.resolve(); instance=uuid.uuid4().hex
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  release=json.loads((root/'RELEASE.json').read_text(encoding='utf-8-sig'))
  if self.path=='/api/health': value={'ok':True,'edition':'haike-workflow-2','workspace':str(root),'pid':os.getpid(),'instance_id':instance,'version':release['version']}
  elif self.path=='/api/studio/app-update/readiness': value={'ready':True}
  elif self.path=='/api/studio/templates': value={'templates':[]}
  else:
   self.send_response(200);self.end_headers();self.wfile.write(b'<html>synthetic UI</html>');return
  self.send_response(200);self.end_headers();self.wfile.write(json.dumps(value).encode())
http.server.HTTPServer(('127.0.0.1',int(sys.argv[-1])),Handler).serve_forever()
'''


class UpdateServiceTests(unittest.TestCase):
    def test_full_release_discovers_current_version_and_never_enters_patch_install(self):
        with tempfile.TemporaryDirectory() as folder:
            root, bundle, plan = self.fixture(folder)
            candidate = self.candidate(plan)
            candidate.update(version="1.0.0", base_version="0.0.0")
            candidate["package"].update(kind="full", size=1024 ** 3)
            updater = service.UpdateService(root)
            with patch.object(service, "remote_open", return_value=io.BytesIO(json.dumps(candidate).encode())):
                self.assertEqual(updater.check()["update"]["status"], "current")
            candidate["version"] = "1.0.1"
            with patch.object(service, "remote_open", return_value=io.BytesIO(json.dumps(candidate).encode())):
                snapshot = updater.check()
            self.assertEqual(snapshot["update"]["status"], "incompatible")
            self.assertFalse(snapshot["update"]["can_install"])

    def fixture(self, folder):
        root, bundle, original, plan = fixtures.AppUpdateTests().fixture(Path(folder))
        return root, bundle, plan

    def candidate(self, plan, payload=b"synthetic zip"):
        return {**{key: plan[key] for key in ("version", "base_version", "edition", "platform", "runtime_id", "data_schema")},
                "schema": 1, "channel": "stable", "notes": "修复进度显示", "published_at": "2026-10-28T00:00:00Z",
                "package": {"url": "https://example.test/update.zip", "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}}

    def test_check_and_install_binds_cached_candidate_and_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            root, bundle, plan = self.fixture(folder)
            updater = service.UpdateService(root)
            candidate = self.candidate(plan)
            with patch.object(service, "remote_open", return_value=io.BytesIO(json.dumps(candidate).encode())):
                result = updater.check()
            self.assertEqual(result["update"]["status"], "available")
            self.assertNotIn("candidate", result["update"])
            for version, confirmed in (("9.0.0", True), ("1.0.1", False)):
                with self.assertRaises(core.UpdateError):
                    updater.install(version, "http://127.0.0.1:1234", "instance", 1234, confirmed, launch=False)
            result = updater.install("1.0.1", "http://127.0.0.1:1234", "instance", 1234, True, launch=False)
            again = updater.install("1.0.1", "http://127.0.0.1:1234", "instance", 1234, True, launch=False)
            self.assertEqual(result["operation"]["id"], again["operation"]["id"])
            self.assertNotIn("token", json.dumps(result))

    def test_offline_and_invalid_manifest_never_report_latest(self):
        with tempfile.TemporaryDirectory() as folder:
            root, bundle, plan = self.fixture(folder)
            updater = service.UpdateService(root)
            for failure in (URLError("synthetic offline"),):
                with patch.object(service, "remote_open", side_effect=failure):
                    self.assertEqual(updater.check()["update"]["status"], "unavailable")
            invalid = self.candidate(plan)
            invalid["package"]["url"] = "http://untrusted.test/update.zip"
            with patch.object(service, "remote_open", return_value=io.BytesIO(json.dumps(invalid).encode())):
                self.assertEqual(updater.check()["update"]["status"], "unavailable")

    def test_application_patch_has_a_decimal_300mb_download_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            root, _, plan = self.fixture(folder)
            candidate = self.candidate(plan)
            candidate['package']['size'] = 300_000_000
            service.UpdateService.validate_candidate(candidate, core.read_release(root))
            candidate['package']['size'] += 1
            with self.assertRaisesRegex(core.UpdateError, '大小'):
                service.UpdateService.validate_candidate(candidate, core.read_release(root))

    def test_imported_patch_is_private_pinned_and_never_needs_a_download(self):
        with tempfile.TemporaryDirectory() as folder:
            root, bundle, plan = self.fixture(folder)
            archive = service.private_path(root, 'import-'+'b'*24+'/package.zip')
            with zipfile.ZipFile(archive, 'w') as output:
                for file in bundle.rglob('*'):
                    if file.is_file(): output.write(file, file.relative_to(bundle).as_posix())
            updater = service.UpdateService(root)
            with patch.object(service, 'remote_open', side_effect=AssertionError('offline import must not use network')):
                snapshot = updater.import_archive(archive)
                self.assertEqual(snapshot['update']['source'], 'local')
                self.assertNotIn('local_archive', json.dumps(snapshot))
                result = updater.install(plan['version'], 'http://127.0.0.1:1234', 'instance', 1234, True, launch=False)
            command = service.read_json(service.private_path(root, result['operation']['id']+'/operation.json'))
            self.assertTrue(command['local_package'])
            self.assertEqual(core.digest(service.private_path(root, result['operation']['id']+'/package.zip')), core.digest(archive))
            service.set_operation(root, 'cancelled', 'test cancelled')
            archive.write_bytes(b'changed after inspection')
            with self.assertRaisesRegex(core.UpdateError, '已变化'):
                updater.install(plan['version'], 'http://127.0.0.1:1234', 'instance', 1234, True, launch=False)

    def test_incompatible_and_source_never_install(self):
        with tempfile.TemporaryDirectory() as folder:
            root, bundle, plan = self.fixture(folder)
            updater = service.UpdateService(root)
            candidate = self.candidate(plan)
            candidate["runtime_id"] = "other-runtime"
            with patch.object(service, "remote_open", return_value=io.BytesIO(json.dumps(candidate).encode())):
                self.assertEqual(updater.check()["update"]["status"], "incompatible")
            (root / ".git").mkdir()
            self.assertFalse(updater.snapshot()["capability"]["can_install"])

    def test_digest_mismatch_never_touches_program(self):
        with tempfile.TemporaryDirectory() as folder:
            root, bundle, plan = self.fixture(folder)
            original = (root / "RELEASE.json").read_bytes()
            with patch.object(service, "remote_open", return_value=io.BytesIO(b"damaged zip!!")):
                with self.assertRaises(core.UpdateError):
                    service.download_package(root, self.candidate(plan), root / "download.zip")
            self.assertEqual((root / "RELEASE.json").read_bytes(), original)

    def test_cancel_is_safe_and_old_helper_cannot_modify_new_operation(self):
        with tempfile.TemporaryDirectory() as folder:
            root, bundle, plan = self.fixture(folder)
            updater = service.UpdateService(root)
            service.set_operation(root, "waiting", "等待", id="a" * 24)
            self.assertEqual(updater.cancel()["operation"]["status"], "cancelled")
            self.assertFalse(service.maintenance(root))
            with self.assertRaises(service.UpdateCancelled):
                service.set_operation(root, "installing", "旧助手", expected_id="a" * 24)
            service.set_operation(root, "installing", "正在安装", id="b" * 24)
            with self.assertRaises(core.UpdateError):
                updater.cancel()

    def test_restart_after_committed_update_recovers_accurate_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            root, bundle, plan = self.fixture(folder)
            release = service.read_json(root / "RELEASE.json")
            release["version"] = "1.0.1"
            service.write_json(root / "RELEASE.json", release)
            identity = "a" * 24
            service.set_operation(root, "restarting", "等待", id=identity, target_version="1.0.1")
            state = service.read_json(service.private_path(root))
            state["operation"]["updated_at"] = "2000-01-01T00:00:00+00:00"
            service.write_json(service.private_path(root), state)
            service.write_json(service.private_path(root, identity + "/operation.json"), {"worker_pid": 0})
            service.write_json(service.private_path(root, "backup/receipt.json"), {"status": "complete", "version": "1.0.1"})
            self.assertEqual(service.UpdateService(root).snapshot()["operation"]["status"], "complete")

    def test_real_restart_and_failed_start_rollback_preserve_data(self):
        # The helper actually stops/restarts only these temporary stdlib HTTP
        # servers. No installed Backlot, account service or supplier is used.
        for broken in (False, True):
            with self.subTest(broken=broken), tempfile.TemporaryDirectory() as folder:
                root, bundle, plan = self.fixture(folder)
                program = "Haike_video/backlot/__main__.py"
                # A regular package keeps an inherited development PYTHONPATH
                # from overriding this deliberately synthetic test server.
                (root / "Haike_video/backlot/__init__.py").write_text("", encoding="utf-8")
                (root / program).write_text(SERVER, encoding="utf-8")
                manifest_path = root / "PACKAGE-MANIFEST.json"
                installed = json.loads(manifest_path.read_text(encoding="utf-8"))
                installed["files"].append({"path": program, "size": (root / program).stat().st_size, "sha256": core.digest(root / program), "mutable": False})
                manifest_path.write_bytes(core.json_bytes(installed))
                payload = b"raise RuntimeError('synthetic startup failure')\n" if broken else (SERVER + "\n# compatible new program\n").encode()
                (bundle / "payload" / program).write_bytes(payload)
                plan["files"].append({"path": program, "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "before_sha256": core.digest(root / program)})
                (bundle / "UPDATE-MANIFEST.json").write_bytes(core.json_bytes(plan))
                archive = Path(folder) / "update.zip"
                with zipfile.ZipFile(archive, "w") as output:
                    for file in bundle.rglob("*"):
                        if file.is_file(): output.write(file, file.relative_to(bundle).as_posix())
                package = archive.read_bytes()
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
                base = f"http://127.0.0.1:{port}"
                child = worker.start_server(root, port)
                children = [child]
                real_start = worker.start_server
                def tracked_start(*args):
                    process = real_start(*args)
                    children.append(process)
                    return process
                try:
                    health = worker.wait_server(base, root, child, "1.0.0", timeout=15)
                    updater = service.UpdateService(root)
                    candidate = self.candidate(plan, package)
                    with patch.object(service, "remote_open", return_value=io.BytesIO(json.dumps(candidate).encode())):
                        updater.check()
                    result = updater.install("1.0.1", base, health["instance_id"], health["pid"], True, launch=False)
                    original_data = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file() and ("data" in p.parts or "projects" in p.parts or p.name == ".env.local")}
                    with patch.object(service, "remote_open", return_value=io.BytesIO(package)), patch.object(worker, "start_server", side_effect=tracked_start):
                        worker.run_update(root, result["operation"]["id"])
                    final = updater.snapshot()
                    self.assertEqual(final["operation"]["status"], "rolled_back" if broken else "complete")
                    self.assertEqual(final["current"]["version"], "1.0.0" if broken else "1.0.1")
                    for name, content in original_data.items():
                        self.assertEqual((root / name).read_bytes(), content)
                finally:
                    try:
                        current = worker.local_get(base, "/api/health")
                        worker.stop_verified(base, root, current["instance_id"], current["pid"])
                    except (OSError, ValueError):
                        pass
                    if child.poll() is None: child.terminate()
                    for process in children:
                        if process.poll() is None: process.terminate()
                        process.wait(timeout=15)


if __name__ == "__main__":
    unittest.main()
