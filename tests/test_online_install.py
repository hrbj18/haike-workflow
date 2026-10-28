"""Online installer boundaries, using tiny archives and fake HTTPS responses."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('online_portable_runtime', ROOT / 'portable/portable.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
spec = importlib.util.spec_from_file_location('online_installer', ROOT / 'portable/online.py')
online = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'portable': runtime}):
    spec.loader.exec_module(online)


class Response(io.BytesIO):
    def geturl(self):
        return 'https://mirror.example.test/dependency.zip'


class OnlineInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.patch = patch.object(runtime, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def archive(self, entries):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return stream.getvalue()

    def component(self, entries):
        payload = self.archive(entries)
        return payload, {'sha256': hashlib.sha256(payload).hexdigest(),
                         'urls': ['https://mirror.example.test/dependency.zip']}

    def test_verified_download_is_reused_without_network(self):
        payload, spec = self.component({'node.exe': b'executable fixture'})
        with patch.object(online.urllib.request, 'urlopen', return_value=Response(payload)) as request:
            first = online.download('node', spec)
            second = online.download('node', spec)
        self.assertEqual(first, second)
        request.assert_called_once()

    def test_bad_checksum_rejects_html_and_retains_existing_component_and_user_data(self):
        runtime.write_text('runtime/node/node.exe', 'existing executable')
        runtime.write_text('Haike_video/.env.local', 'user key fixture')
        runtime.write_text('creatorhub/data/account.fixture', 'user account fixture')
        _, spec = self.component({'node.exe': b'new fixture'})
        with patch.object(online.urllib.request, 'urlopen', return_value=Response(b'<html>mirror error</html>')):
            with self.assertRaises(RuntimeError):
                online.install_component('node', spec)
        self.assertEqual((self.root / 'runtime/node/node.exe').read_text(), 'existing executable')
        self.assertEqual((self.root / 'Haike_video/.env.local').read_text(), 'user key fixture')
        self.assertEqual((self.root / 'creatorhub/data/account.fixture').read_text(), 'user account fixture')
        self.assertFalse(list((self.root / '.portable/downloads').glob('*.part')))

    def test_component_install_can_repair_and_preserves_old_tree(self):
        runtime.write_text('runtime/node/node.exe', 'old fixture')
        payload, spec = self.component({'node.exe': b'new fixture', 'LICENSE': b'license fixture'})
        with patch.object(online.urllib.request, 'urlopen', return_value=Response(payload)) as request:
            online.install_component('node', spec)
            online.install_component('node', spec)
        request.assert_called_once()
        self.assertEqual((self.root / 'runtime/node/node.exe').read_bytes(), b'new fixture')
        self.assertEqual((self.root / '.portable/dependency-backups/node/node.exe').read_text(), 'old fixture')

    def test_archive_cannot_escape_to_user_configuration(self):
        payload, _ = self.component({'../Haike_video/.env.local': b'must not be written'})
        destination = self.root / 'staging'
        destination.mkdir()
        with self.assertRaises(ValueError):
            online.extract(io.BytesIO(payload), destination)
        self.assertFalse((self.root / 'Haike_video/.env.local').exists())

    def test_online_child_environment_enables_mirrors_and_retains_no_model_downloads(self):
        env = online.install_environment({'npm': 'https://registry.npmmirror.com'})
        for name in ('PIP_NO_INDEX', 'UV_OFFLINE', 'NPM_CONFIG_OFFLINE'):
            self.assertNotIn(name, env)
        self.assertEqual(env['NPM_CONFIG_REPLACE_REGISTRY_HOST'], 'always')
        self.assertEqual(env['HF_HUB_OFFLINE'], '1')
        self.assertEqual(env['PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD'], '1')

    def test_source_checkout_is_not_an_online_installation(self):
        (self.root / '.git').mkdir()
        with self.assertRaisesRegex(RuntimeError, 'extracted online release'):
            online.hydrate()

    def test_npm_cannot_select_an_ancestor_project_and_exact_version_is_reused(self):
        def installing(arguments, env, cwd):
            self.assertEqual(cwd, (self.root / 'runtime/hyperframes').resolve())
            boundary = runtime.read_json('runtime/hyperframes/package.json')
            self.assertTrue(boundary['private'])
            self.assertEqual(boundary['dependencies'], {'hyperframes': '0.8.34'})
            runtime.write_json('runtime/hyperframes/node_modules/hyperframes/package.json', {'version': '0.8.34'})
        with patch.object(online, 'command', side_effect=installing) as install:
            online.install_hyperframes({'hyperframes': '0.8.34'}, {}, 'npm-fixture.cmd')
            online.install_hyperframes({'hyperframes': '0.8.34'}, {}, 'npm-fixture.cmd')
        install.assert_called_once()

    def test_only_online_distribution_can_omit_optional_whisper(self):
        required = ['runtime/python/python.exe', 'runtime/python/pythonw.exe', 'runtime/node/node.exe',
                    'runtime/ffmpeg/bin/ffmpeg.exe', 'runtime/ffmpeg/bin/ffprobe.exe', runtime.BROWSER,
                    'Haike_video/backlot/server.py', 'Haike_video/backlot/ui/avatar-generator/index.html',
                    'Haike_video/remotion-composer/node_modules/@remotion/cli/package.json',
                    'runtime/hyperframes/node_modules/hyperframes/package.json']
        required += ['runtime/msvc/' + name for name in runtime.DLLS]
        required += [repo + '/.venv/Scripts/' + name + '.exe' for repo in runtime.REPOS for name in ('python', 'pythonw')]
        for relative in required:
            runtime.write_text(relative, 'fixture')
        with patch.object(runtime, 'run_probe', return_value={'ok': True}):
            with self.assertRaisesRegex(RuntimeError, 'Whisper'):
                runtime.diagnose()
            runtime.write_json('RELEASE.json', {'distribution': 'online'})
            result = runtime.diagnose()
        self.assertEqual(result['models']['whisper_small'], 'optional_not_installed')
        runtime.write_text('runtime/models/whisper-small/partial/model.bin', 'fixture')
        with self.assertRaisesRegex(RuntimeError, 'Whisper'):
            runtime.diagnose()

    def test_release_download_manifest_has_only_fixed_https_resources(self):
        spec = json.loads((ROOT / 'config/online-downloads.json').read_text())
        for name in ('python', 'uv', 'msvc', 'node', 'browser', 'ffmpeg'):
            self.assertRegex(spec[name]['sha256'], r'^[0-9a-f]{64}$')
            self.assertTrue(all(url.startswith('https://') for url in spec[name]['urls']))


if __name__ == '__main__':
    unittest.main()
