"""Public bootstrap contract: no partial writes, safe rollback and offline reuse."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'portable'))
spec = importlib.util.spec_from_file_location('legacy_upgrade', ROOT / 'portable/legacy_upgrade.py')
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


class LegacyUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'old'
        self.bundle = self.root / 'bundle'
        self.target.mkdir(); self.bundle.mkdir()
        self.file('runtime/python/python.exe', b'python')
        self.file('runtime/browser/chrome.exe', b'old browser reused')
        self.file('Haike_video/backlot/legacy_test.py', b'old program')
        self.file('Haike_video/config.local.yaml', b'private-config-sentinel')
        self.file('Haike_video/projects/user-work.txt', b'user work')
        self.file('RELEASE.json', upgrade.json_bytes({'source_commit': 'a' * 40}))
        self.file('PACKAGE-MANIFEST.json', upgrade.json_bytes({'schema': 1, 'files': []}))
        self.file('payload/new.py', b'new program', self.bundle)
        old = upgrade.digest(self.target / 'Haike_video/backlot/legacy_test.py')
        data = b'new cache file'
        self.resource = self.root / 'templates.zip'
        self.resources = {'id': upgrade.ID, 'packages': [], 'files': [
            {'path': '.local/md/shared-1.2/node_modules/test/index.js', 'blob': 'blobs/test',
             'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'before_sha256': None},
            {'path': 'Haike_video/remotion-composer/node_modules/.remotion/chrome.exe',
             'reuse_from': 'runtime/browser/chrome.exe', 'size': len(b'old browser reused'),
             'sha256': upgrade.digest(self.target / 'runtime/browser/chrome.exe'), 'before_sha256': None}]}
        with zipfile.ZipFile(self.resource, 'w') as archive:
            archive.writestr('blobs/test', data)
            archive.writestr('RESOURCES.json', upgrade.json_bytes(self.resources))
        self.plan = {'id': upgrade.ID, 'schema': 1, 'base_source_commit': 'a' * 40,
            'base_manifest_sha256': upgrade.digest(self.target / 'PACKAGE-MANIFEST.json'),
            'resources': {'sha256': upgrade.digest(self.resource)}, 'required_files': [],
            'files': [{'path': 'Haike_video/backlot/legacy_test.py', 'payload': 'payload/new.py',
                       'size': len(b'new program'), 'sha256': hashlib.sha256(b'new program').hexdigest(),
                       'before_sha256': old}],
            'release': {'edition': 'haike-workflow-2', 'version': '1.2.0', 'channel': 'stable',
                        'runtime_id': 'old-runtime', 'data_schema': 1, 'platform': 'windows-x64',
                        'source_commit': 'b' * 40}}
        self.save_plan()
        self.guard = patch.object(upgrade, 'stopped')
        self.guard.start(); self.addCleanup(self.guard.stop)

    def file(self, name, data, root=None):
        path = (root or self.target) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def save_plan(self):
        (self.bundle / 'UPGRADE.json').write_bytes(upgrade.json_bytes(self.plan))

    def install(self, **kwargs):
        return upgrade.apply(self.bundle, self.target, self.resource,
                             health_check=lambda _: {'ok': True, 'templates': []}, **kwargs)

    def test_full_upgrade_reuses_browser_keeps_private_files_and_is_idempotent(self):
        result = self.install()
        self.assertTrue(result['ok'])
        self.assertEqual((self.target / 'runtime/browser/chrome.exe').read_bytes(), b'old browser reused')
        self.assertEqual((self.target / 'Haike_video/config.local.yaml').read_bytes(), b'private-config-sentinel')
        self.assertEqual((self.target / 'Haike_video/projects/user-work.txt').read_bytes(), b'user work')
        self.assertTrue(self.install()['already_current'])
        restored = upgrade.restore(self.target, Path(result['backup']))
        self.assertTrue(restored['ok'])
        self.assertFalse((self.target / 'VERSION.json').exists())
        self.assertEqual((self.target / 'Haike_video/backlot/legacy_test.py').read_bytes(), b'old program')

    def test_read_only_check_does_not_change_program(self):
        self.assertTrue(self.install(check=True)['check_only'])
        self.assertFalse((self.target / 'VERSION.json').exists())

    def test_windows_extract_all_extra_folder_finds_sibling_resource_zip(self):
        nested = self.root / 'extracted' / 'haike-update-1.2'
        self.assertEqual(upgrade.find_resources(nested, self.resource.name), self.resource)
        with self.assertRaises(ValueError):
            upgrade.find_resources(nested, '../templates.zip')

    def test_modified_old_file_rejected_before_any_write(self):
        self.file('Haike_video/backlot/legacy_test.py', b'custom user edit')
        with self.assertRaisesRegex(ValueError, '本地修改'):
            self.install()
        self.assertFalse((self.target / 'VERSION.json').exists())

    def test_bad_resource_archive_rejected_before_any_write(self):
        with self.resource.open('ab') as output:
            output.write(b'corruption')
        with self.assertRaisesRegex(ValueError, '摘要不符'):
            self.install()
        self.assertFalse((self.target / 'VERSION.json').exists())

    def test_reuse_source_tampering_is_rejected(self):
        self.file('runtime/browser/chrome.exe', b'changed old browser')
        with self.assertRaisesRegex(ValueError, '复用依赖损坏'):
            self.install()

    def test_protected_destination_is_rejected(self):
        self.plan['files'][0]['path'] = 'creatorhub/config.yaml'
        self.save_plan()
        with self.assertRaisesRegex(ValueError, '允许范围'):
            self.install()

    def test_probe_failure_rolls_back_all_files(self):
        def failed(_):
            raise ValueError('injected startup failure')
        with self.assertRaisesRegex(ValueError, 'startup failure'):
            upgrade.apply(self.bundle, self.target, self.resource, health_check=failed)
        self.assertFalse((self.target / 'VERSION.json').exists())
        self.assertEqual((self.target / 'Haike_video/backlot/legacy_test.py').read_bytes(), b'old program')
        self.assertFalse((self.target / '.local/md/shared-1.2/node_modules/test/index.js').exists())

    def test_rollback_refuses_later_edits_without_partial_restore(self):
        result = self.install()
        self.file('Haike_video/backlot/legacy_test.py', b'later edit')
        with self.assertRaisesRegex(ValueError, '又被修改'):
            upgrade.restore(self.target, Path(result['backup']))
        self.assertTrue((self.target / 'VERSION.json').exists())


if __name__ == '__main__':
    unittest.main()
