"""Offline launcher contracts. All services and child processes are fakes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("haike_portable", Path(__file__).resolve().parents[1] / "portable/portable.py")
portable = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portable)


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.root_patch = patch.object(portable, "ROOT", self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temporary.cleanup()

    def file(self, relative, content="fixture"):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def prepared_fixture(self, crawler=False):
        self.file("runtime/python/python.exe")
        for repo in portable.REPOS + ((portable.CRAWLER,) if crawler else ()):
            self.file(repo + "/.venv/Scripts/python.exe")
        self.file("Haike_video/.env.example", "example-only")
        self.file("creatorhub/config.example.yaml", "example: only")
        self.file("copy_skill/copy_skill-main/config/content_intelligence.json", '{"factory":true}')
        self.file("copy_skill/copy_skill-main/.venv/Lib/site-packages/__editable__.douyin_content_intelligence-0.3.0.pth", "old-absolute-reference")

    def test_prepare_relocates_without_changing_factory_config(self):
        self.prepared_fixture(crawler=True)
        self.file("runtime/playwright/chromium-1228/chrome-win64/chrome.exe")
        factory = self.root / "copy_skill/copy_skill-main/config/content_intelligence.json"
        before = factory.read_bytes()
        with patch.dict(os.environ, {"PROGRAMFILES": "", "PROGRAMFILES(X86)": "", "LOCALAPPDATA": ""}):
            result = portable.prepare()
        self.assertEqual(factory.read_bytes(), before)
        self.assertIn(portable.CRAWLER, result["venvs"])
        for repo in result["venvs"]:
            self.assertIn(str((self.root / "runtime/python").resolve()), (self.root / repo / ".venv/pyvenv.cfg").read_text())
        override = portable.read_json("copy_skill/copy_skill-main/config/content_intelligence.local.json")
        self.assertEqual(override["media_tools"]["ffmpeg"], "../../runtime/ffmpeg/bin/ffmpeg.exe")
        self.assertEqual(override["media_crawler"]["chrome_path"], str((self.root / "runtime/playwright/chromium-1228/chrome-win64/chrome.exe").resolve()))
        self.assertNotIn("douyin_commercial_authorized", override)
        self.assertFalse((self.root / "Haike_video/.backlot/studio-asr/policy.json").exists())
        pth = next((self.root / "copy_skill/copy_skill-main/.venv/Lib/site-packages").glob("*.pth"))
        self.assertEqual(pth.read_text(), "../../../src\n")

    def test_prepare_preserves_user_settings_and_is_idempotent(self):
        self.prepared_fixture()
        self.file("Haike_video/.env.local", "user-owned")
        self.file("creatorhub/config.yaml", "user-owned")
        self.file("copy_skill/copy_skill-main/config/content_intelligence.local.json", '{"media_tools":{"ffmpeg":"custom-tool"},"user":true}')
        portable.prepare()
        portable.prepare()
        self.assertEqual((self.root / "Haike_video/.env.local").read_text(), "user-owned")
        self.assertEqual((self.root / "creatorhub/config.yaml").read_text(), "user-owned")
        override = portable.read_json("copy_skill/copy_skill-main/config/content_intelligence.local.json")
        self.assertTrue(override["user"])
        self.assertEqual(override["media_tools"]["ffmpeg"], "custom-tool")

    def test_prepare_relocates_owned_console_cache_without_installing(self):
        self.prepared_fixture()
        self.file('.local/md/console-v1/.venv/Scripts/python.exe')
        self.file('.local/md/console-v1/.venv/pyvenv.cfg','home = old-machine')
        self.file('.local/motion-console/defaults.json',json.dumps({'native_dependency_cache':'.local/md/console-v1'}))
        with patch.object(portable.subprocess,'run') as run:
            result=portable.prepare()
        run.assert_not_called()
        self.assertIn('.local/md/console-v1',result['venvs'])
        cfg=(self.root/'.local/md/console-v1/.venv/pyvenv.cfg').read_text()
        self.assertIn(str((self.root/'runtime/python').resolve()),cfg)
        self.assertNotIn('old-machine',cfg)

    def test_invalid_user_override_fails_and_preserves_file(self):
        self.prepared_fixture()
        path = self.file("copy_skill/copy_skill-main/config/content_intelligence.local.json", "[]")
        with self.assertRaises(ValueError):
            portable.prepare()
        self.assertEqual(path.read_text(), "[]")

    def test_missing_runtime_does_not_install_anything(self):
        with patch.object(portable.subprocess, "run") as run:
            with self.assertRaises(RuntimeError):
                portable.prepare()
        run.assert_not_called()

    def test_system_chrome_precedes_bundled_chromium(self):
        browser = self.file("system/Google/Chrome/Application/chrome.exe")
        self.file("runtime/playwright/chromium-1228/chrome-win64/chrome.exe")
        with patch.dict(os.environ, {"PROGRAMFILES": str(self.root / "system")}):
            self.assertEqual(portable.login_browser(), browser)

    def test_integrity_checks_immutable_files_and_accepts_changed_mutable(self):
        self.file("code.py", "shipped")
        self.file("user.txt", "changed")
        portable.write_json("PACKAGE-MANIFEST.json", {"files": [
            {"path": "code.py", "sha256": hashlib.sha256(b"shipped").hexdigest()},
            {"path": "user.txt", "mutable": True, "sha256": "0" * 64}]})
        self.assertEqual(portable.integrity(), 1)
        self.file("code.py", "tampered")
        with self.assertRaises(RuntimeError):
            portable.integrity()

    def test_manifest_rejects_escape_and_duplicate_paths(self):
        for entries in ([{"path": "../outside", "mutable": True}],
                        [{"path": "user", "mutable": True}] * 2):
            portable.write_json("PACKAGE-MANIFEST.json", {"files": entries})
            with self.assertRaises(ValueError):
                portable.integrity()

    def test_renderer_can_replace_or_remove_webpack_cache_without_invalidating_install(self):
        code = 'Haike_video/remotion-composer/node_modules/@remotion/cli/index.js'
        cache = 'Haike_video/remotion-composer/node_modules/.cache/webpack/renderer/0.pack'
        self.file(code, 'real dependency')
        generated = self.file(cache, 'old generated cache')
        portable.write_json('PACKAGE-MANIFEST.json', {'files': [
            {'path': code, 'sha256': hashlib.sha256(b'real dependency').hexdigest()},
            {'path': cache, 'sha256': hashlib.sha256(b'old generated cache').hexdigest()}]})
        generated.unlink()
        self.assertEqual(portable.integrity(), 1)
        self.file(cache, 'regenerated by the renderer')
        self.assertEqual(portable.integrity(), 1)
        self.file(code, 'corrupted real dependency')
        with self.assertRaisesRegex(RuntimeError, '发行文件校验失败'):
            portable.integrity()

    def test_prepare_rejects_symlinked_local_config(self):
        self.prepared_fixture()
        target = self.file("retained.txt", "preserve")
        override = self.root / "copy_skill/copy_skill-main/config/content_intelligence.local.json"
        try:
            override.symlink_to(target)
        except OSError as error:
            self.skipTest("Symlink creation unavailable: " + str(error))
        with self.assertRaises(ValueError):
            portable.prepare()
        self.assertEqual(target.read_text(), "preserve")

    def test_environment_disables_installers_and_uses_bundle_tools(self):
        with patch.dict(os.environ, {"PYTHONHOME": "external", "PYTHONPATH": "external"}):
            env = portable.environment()
        self.assertNotIn("PYTHONHOME", env)
        self.assertEqual(env["PYTHONPATH"], "")
        for name in ("PIP_NO_INDEX", "UV_OFFLINE", "HF_HUB_OFFLINE", "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"):
            self.assertEqual(env[name], "1")
        self.assertEqual(env["FFMPEG_BINARY"], str(self.root / "runtime/ffmpeg/bin/ffmpeg.exe"))
        self.assertEqual(env["CHROME_PATH"], str(self.root / portable.BROWSER))

    def test_explicit_optional_components_do_not_hide_missing_required_runtime(self):
        self.prepared_fixture()
        for name in ["runtime/python/pythonw.exe", "runtime/node/node.exe",
                     "runtime/ffmpeg/bin/ffmpeg.exe", "runtime/ffmpeg/bin/ffprobe.exe", portable.BROWSER,
                     "Haike_video/backlot/server.py", "Haike_video/backlot/ui/avatar-generator/index.html",
                     "Haike_video/remotion-composer/node_modules/@remotion/cli/package.json"]:
            self.file(name)
        for name in portable.DLLS: self.file("runtime/msvc/"+name)
        for repo in portable.REPOS: self.file(repo+"/.venv/Scripts/pythonw.exe")
        portable.write_json("RUNTIME-INVENTORY.json", {"optional_components": {"hyperframes":False,"whisper_small":False}})
        with patch.object(portable, "run_probe", side_effect=lambda name,*a,**k: {"name":name,"ok":True}) as probe:
            result=portable.diagnose()
        self.assertEqual(result["models"]["whisper_small"], "not_installed")
        self.assertNotIn("whisper-small", [call.args[0] for call in probe.call_args_list])
        self.assertIn("(3,12)", probe.call_args_list[0].args[1][-1])
        (self.root/"runtime/ffmpeg/bin/ffmpeg.exe").unlink()
        with self.assertRaisesRegex(RuntimeError, "ffmpeg"):
            portable.diagnose()

    def test_legacy_full_bundle_keeps_optional_components_required(self):
        self.prepared_fixture()
        with self.assertRaisesRegex(RuntimeError, "缺少必要文件"):
            portable.diagnose()
        portable.write_json("RUNTIME-INVENTORY.json", {"optional_components":{"whisper_small":"false"}})
        with self.assertRaisesRegex(ValueError, "组件清单"):
            portable.diagnose()

    def test_existing_windows_npm_setting_does_not_create_case_duplicate(self):
        with patch.dict(os.environ, {"NPM_CONFIG_OFFLINE": "false"}):
            env = portable.environment()
        names = [name for name in env if name.casefold() == "npm_config_offline"]
        self.assertEqual(names, ["NPM_CONFIG_OFFLINE"])
        self.assertEqual(env["NPM_CONFIG_OFFLINE"], "true")

    def test_identity_requires_current_workspace(self):
        with patch.object(portable, "http_json", return_value={"ok": True, "app": "backlot", "edition": "haike-workflow-2", "workspace": str(self.root.parent)}):
            self.assertFalse(portable.own_service(14756, "backlot"))
        fingerprint = hashlib.sha256(str((self.root / "creatorhub").resolve()).replace("\\", "/").casefold().encode()).hexdigest()
        with patch.object(portable, "http_json", return_value={"service_fingerprint": fingerprint}):
            self.assertTrue(portable.own_service(8000, "creatorhub"))

    def test_ports_skip_other_services_and_reuse_only_owned(self):
        class BusySocket:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def setsockopt(self, *args): pass
            def bind(self, address): raise OSError("occupied")
        with patch.object(portable, "own_service", side_effect=lambda port, kind: port == 14757), patch.object(portable.socket, "socket", return_value=BusySocket()):
            self.assertEqual(portable.choose_port(14756, "backlot"), (14757, True))

    def test_start_passes_chosen_account_port_to_existing_launcher(self):
        with patch.object(portable, "prepare"), patch.object(portable, "diagnose"), patch.object(portable, "choose_port", side_effect=[(14760, False), (8010, False)]), patch.object(portable, "run_launcher") as run, patch.object(portable, "own_service", return_value=True):
            result = portable.start(no_browser=True)
        self.assertEqual(run.call_args.kwargs["env"]["HAIKE_CREATORHUB_URL"], "http://127.0.0.1:8010")
        self.assertIn(str(self.root / "start-workbench.ps1"), run.call_args.args[0])
        self.assertEqual(result["services"][0]["url"], "http://127.0.0.1:14760/avatar")

    def test_start_never_reports_ready_for_another_workspace(self):
        with patch.object(portable, "prepare"), patch.object(portable, "diagnose"), patch.object(portable, "choose_port", side_effect=[(14760, False), (8010, False)]), patch.object(portable, "run_launcher"), patch.object(portable, "own_service", return_value=False):
            with self.assertRaises(RuntimeError):
                portable.start(no_browser=True)
        self.assertFalse((self.root / ".portable/services.json").exists())

    def test_missing_desktop_browser_does_not_turn_ready_services_into_failure(self):
        with patch.object(portable, "prepare"), patch.object(portable, "diagnose"), patch.object(portable, "choose_port", side_effect=[(14760, False), (8010, False)]), patch.object(portable, "run_launcher"), patch.object(portable, "own_service", return_value=True), patch.object(portable.webbrowser, "open", side_effect=portable.webbrowser.Error("no association")):
            result = portable.start()
        self.assertTrue(result["ok"])
        self.assertFalse(result["browser_opened"])

    def test_launcher_uses_files_instead_of_capture_pipes(self):
        def launched(command, **kwargs):
            self.assertNotIn("capture_output", kwargs)
            self.assertNotEqual(kwargs["stdout"], portable.subprocess.PIPE)
            self.assertNotEqual(kwargs["stderr"], portable.subprocess.PIPE)
            self.assertEqual(Path(kwargs["stdout"].name).name, "launcher.out.log")
            self.assertEqual(Path(kwargs["stderr"].name).name, "launcher.err.log")
            kwargs["stdout"].write(b"ready")
            kwargs["stderr"].write(b"diagnostic")
            return portable.subprocess.CompletedProcess(command, 0)
        with patch.object(portable.subprocess, "run", side_effect=launched):
            portable.run_launcher(["fake-launcher"], env={})
        self.assertEqual((self.root / ".portable/logs/launcher.out.log").read_bytes(), b"ready")
        self.assertEqual((self.root / ".portable/logs/launcher.err.log").read_bytes(), b"diagnostic")

    def test_launcher_nonzero_exit_has_visible_code_and_log_locations(self):
        with patch.object(portable.subprocess, "run", return_value=portable.subprocess.CompletedProcess([], 7)):
            with self.assertRaisesRegex(RuntimeError, "退出码 7") as error:
                portable.run_launcher(["fake-launcher"], env={})
        self.assertIn("launcher.out.log", str(error.exception))
        self.assertIn("launcher.err.log", str(error.exception))


if __name__ == "__main__":
    unittest.main()
