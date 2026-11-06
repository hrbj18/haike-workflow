"""The small install resolves local browsers and never obtains a browser archive."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from portable import system_browser

ROOT = Path(__file__).resolve().parents[1]


class SystemBrowserTests(unittest.TestCase):
    def test_explicit_local_browser_has_priority_without_launching(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / 'Chrome with spaces/chrome.exe'
            executable.parent.mkdir()
            executable.write_bytes(b'existing browser')
            with patch.object(system_browser.shutil, 'which', return_value=None):
                result = system_browser.environment({'HAIKE_BROWSER_PATH': str(executable), 'PATH': ''})
            self.assertEqual(result['REMOTION_BROWSER_EXECUTABLE'], str(executable.resolve()))
            self.assertEqual(result['PUPPETEER_SKIP_DOWNLOAD'], 'true')

    def test_missing_browser_is_an_actionable_error_without_download(self):
        with patch.object(system_browser, 'candidates', return_value=iter([])):
            with self.assertRaisesRegex(ValueError, '不会自动下载'):
                system_browser.resolve({})

    def test_existing_explicit_remotion_binding_is_preserved_and_missing_binding_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / 'legacy-browser.exe'
            executable.write_bytes(b'existing bound browser')
            env = {'REMOTION_BROWSER_EXECUTABLE': str(executable)}
            self.assertEqual(system_browser.resolve(env), executable.resolve())
            executable.unlink()
            with self.assertRaisesRegex(ValueError, '本地浏览器不存在'):
                system_browser.resolve(env)

    def test_windows_setup_reuses_browser_and_downloads_only_missing_ffmpeg(self):
        spec = importlib.util.spec_from_file_location('media_setup_test', ROOT / 'scripts/setup-windows-media.py')
        setup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'portable').mkdir()
            (root / 'portable/dependency-downloads.json').write_text(json.dumps({'ffmpeg': {}, 'browser': {}}))
            tools = root / 'runtime/ffmpeg'
            tools.mkdir(parents=True)
            for name in ('ffmpeg.exe', 'ffprobe.exe'):
                (tools / name).write_bytes(b'existing tool')
            browser = root / 'installed-chrome.exe'
            browser.write_bytes(b'existing browser')
            with patch.object(setup.os, 'name', 'nt'), patch.object(setup, 'resolve_browser', return_value=browser), \
                 patch.object(setup, 'version', side_effect=lambda p: 'working' if p.is_file() else ''), \
                 patch.object(setup, 'obtain', side_effect=AssertionError('must not download')):
                setup.install(root)
            receipt = json.loads((root / '.local/windows-media-runtime.json').read_text())
            self.assertEqual(receipt['tools']['browser']['source'], 'existing-local-browser')
            self.assertFalse((root / 'runtime/browser').exists())

    def test_mac_default_runtime_loop_omits_both_browser_archives(self):
        spec = importlib.util.spec_from_file_location('mac_setup_test', ROOT / 'scripts/mac-deploy.py')
        setup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup)
        rows = [{'id': name, 'arch': 'arm64'} for name in ('browser', 'login_browser')]
        with patch.object(setup, 'read', return_value={'assets': rows}), \
             patch.object(setup, 'obtain', side_effect=AssertionError('browser download forbidden')):
            setup.install_runtimes('arm64', False)


if __name__ == '__main__':
    unittest.main()
