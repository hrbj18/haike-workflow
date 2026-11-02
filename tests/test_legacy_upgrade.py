"""Public bootstrap contract: no partial writes, safe rollback and offline reuse."""
import hashlib
from contextlib import closing
import importlib.util
import json
import sqlite3
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
core_spec = importlib.util.spec_from_file_location('release_core', ROOT / 'portable/app_update.py')
core = importlib.util.module_from_spec(core_spec)
core_spec.loader.exec_module(core)
spec = importlib.util.spec_from_file_location('legacy_upgrade', ROOT / 'portable/legacy_upgrade.py')
upgrade = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'release_core': core}):
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
        with patch.object(upgrade, 'reconcile_audio') as reconcile:
            self.assertTrue(self.install(check=True)['check_only'])
            reconcile.assert_not_called()
        self.assertFalse((self.target / 'VERSION.json').exists())

    def test_install_and_rollback_preserve_seven_held_unknown_records(self):
        queue = self.target / 'Haike_video/.backlot/production-queue.sqlite3'
        queue.parent.mkdir(parents=True)
        with closing(sqlite3.connect(queue)) as db:
            db.execute('CREATE TABLE production_jobs(job_id TEXT,status TEXT,worker_id TEXT,lease_expires_at TEXT,frozen_request TEXT)')
            db.executemany('INSERT INTO production_jobs VALUES (?,?,?,?,?)',
                [(f'PQ-{i}', 'ambiguous', None, None, '{"synthetic":"preserve"}') for i in range(7)])
            db.commit()
        before = queue.read_bytes()
        result = self.install()
        self.assertEqual(result['held_jobs_preserved'], 7)
        receipt = upgrade.read(Path(result['backup']) / 'receipt.json')
        copy = Path(result['backup']) / receipt['preserved_queue']['filename']
        self.assertEqual(len(upgrade.queue_module().inspect(copy)['held']), 7)
        self.assertEqual(queue.read_bytes(), before)
        upgrade.restore(self.target, Path(result['backup']))
        self.assertEqual(queue.read_bytes(), before)

    def modern_base(self):
        identity = 'base-1-2-1-' + 'c' * 12
        release = {**self.plan['release'], 'version': '1.2.1', 'source_commit': 'c' * 40}
        self.file('RELEASE.json', upgrade.json_bytes(release))
        self.plan['release']['version'] = '1.2.2'
        self.plan['modern_bases'] = [{'id': identity, 'version': '1.2.1', 'source_commit': 'c' * 40, 'required_files': []}]
        for row in self.plan['files'] + self.resources['files']:
            row['before_by_base'] = {identity: row.get('before_sha256')}
        with zipfile.ZipFile(self.resource, 'w') as archive:
            archive.writestr('blobs/test', b'new cache file')
            archive.writestr('RESOURCES.json', upgrade.json_bytes(self.resources))
        self.plan['resources']['sha256'] = upgrade.digest(self.resource)
        self.save_plan()
        return release

    def test_explicit_modern_migration_preserves_data_and_rolls_back(self):
        previous = self.modern_base()
        before = (self.target / 'RELEASE.json').read_bytes()
        result = self.install()
        self.assertEqual(upgrade.read(self.target / 'RELEASE.json')['upgraded_from'], '1.2.1')
        self.assertEqual((self.target / 'Haike_video/config.local.yaml').read_bytes(), b'private-config-sentinel')
        upgrade.restore(self.target, Path(result['backup']))
        self.assertEqual((self.target / 'RELEASE.json').read_bytes(), before)

    def project_base(self):
        self.modern_base()
        release = {**self.plan['release'], 'version': '1.1.0',
                   'source_commit': '594980e14d722e5c98ac4296a1a5279080f7f8d1'}
        self.file('RELEASE.json', upgrade.json_bytes(release))
        self.file('START_HERE.md', b'# Haike Workflow Agent entry\n')
        self.file('Haike_video/backlot/server.py', b'# haike-workflow-2 server\n')
        self.plan['project_compatibility'] = {'schema': 1, 'edition': 'haike-workflow-2',
            'platform': 'windows-x64', 'data_schema': 1}
        self.save_plan()

    def test_project_identity_accepts_reported_594980e_build_without_commit_allowlist(self):
        self.project_base()
        before = (self.target / 'RELEASE.json').read_bytes()
        result = self.install()
        self.assertTrue(result['ok'])
        self.assertEqual((self.target / 'Haike_video/config.local.yaml').read_bytes(), b'private-config-sentinel')
        upgrade.restore(self.target, Path(result['backup']))
        self.assertEqual((self.target / 'RELEASE.json').read_bytes(), before)

    def test_project_update_backs_up_modified_program_and_preserves_private_data(self):
        self.project_base()
        self.file('Haike_video/backlot/legacy_test.py', b'other Haike build program')
        result = self.install()
        self.assertEqual((self.target / 'Haike_video/backlot/legacy_test.py').read_bytes(), b'new program')
        upgrade.restore(self.target, Path(result['backup']))
        self.assertEqual((self.target / 'Haike_video/backlot/legacy_test.py').read_bytes(), b'other Haike build program')

    def test_project_update_rejects_other_product_and_incompatible_data(self):
        self.project_base()
        original = upgrade.read(self.target / 'RELEASE.json')
        for change in [{'edition': 'other-product'}, {'platform': 'darwin-arm64'}, {'data_schema': 99}]:
            self.file('RELEASE.json', upgrade.json_bytes({**original, **change}))
            with self.assertRaisesRegex(ValueError, '不是兼容'):
                self.install()

    def test_same_version_missing_program_is_repaired_through_project_transaction(self):
        self.project_base()
        self.install()
        (self.target / 'Haike_video/backlot/legacy_test.py').unlink()
        self.assertTrue(self.install()['ok'])
        self.assertEqual((self.target / 'Haike_video/backlot/legacy_test.py').read_bytes(), b'new program')

    def test_project_resource_archive_supplies_fallback_for_missing_reuse_file(self):
        self.project_base()
        self.resources['files'][1]['blob'] = 'blobs/browser'
        with zipfile.ZipFile(self.resource, 'w') as archive:
            archive.writestr('blobs/test', b'new cache file')
            archive.writestr('blobs/browser', b'old browser reused')
            archive.writestr('RESOURCES.json', upgrade.json_bytes(self.resources))
        self.plan['resources']['sha256'] = upgrade.digest(self.resource); self.save_plan()
        (self.target / 'runtime/browser/chrome.exe').unlink()
        self.assertTrue(self.install()['ok'])
        self.assertEqual((self.target / 'Haike_video/remotion-composer/node_modules/.remotion/chrome.exe').read_bytes(), b'old browser reused')

    def test_unknown_modern_build_and_missing_per_file_baseline_are_rejected(self):
        release = self.modern_base()
        self.file('RELEASE.json', upgrade.json_bytes({**release, 'source_commit': 'd' * 40}))
        with self.assertRaisesRegex(ValueError, '未支持当前构建'):
            self.install()
        self.file('RELEASE.json', upgrade.json_bytes(release))
        self.plan['files'][0].pop('before_by_base'); self.save_plan()
        with self.assertRaisesRegex(ValueError, '基线校验'):
            self.install()

    def test_rollback_accepts_same_installation_through_canonical_path_alias(self):
        (self.root / 'alias-parent').mkdir()
        alias = self.root / 'alias-parent/../old'
        result = upgrade.apply(self.bundle, alias, self.resource,
                               health_check=lambda _: {'ok': True, 'templates': []})
        restored = upgrade.restore(self.target.resolve(), Path(result['backup']))
        self.assertTrue(restored['ok'])
        self.assertFalse((self.target / 'VERSION.json').exists())
        self.assertEqual((self.target / 'Haike_video/backlot/legacy_test.py').read_bytes(), b'old program')

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


class LegacyPendingWorkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        inspection = patch.object(upgrade.subprocess, 'run', return_value=type('ProcessList', (), {
            'returncode': 0, 'stdout': '[]'})())
        inspection.start()
        self.addCleanup(inspection.stop)

    def test_every_nonterminal_queue_state_blocks_offline_installer(self):
        path = self.root / 'Haike_video/.backlot/production-queue.sqlite3'
        path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE production_jobs(status TEXT)')
            db.execute('INSERT INTO production_jobs VALUES (?)', ('queued',))
            db.commit()
            for status in ['queued', 'running', 'paused', 'awaiting_human', 'ambiguous', None]:
                with self.subTest(status=status):
                    db.execute('UPDATE production_jobs SET status=?', (status,)); db.commit()
                    with self.assertRaisesRegex(ValueError, '制作任务'):
                        upgrade.stopped(self.root)
            for status in ['completed', 'failed', 'cancelled']:
                db.execute('UPDATE production_jobs SET status=?', (status,)); db.commit()
                upgrade.stopped(self.root)

    def test_unknown_audio_file_blocks_without_modifying_its_record(self):
        path = self.root / 'Haike_video/.backlot/audio-center-internal/voice/operations/test/operation.json'
        path.parent.mkdir(parents=True)
        for status in ['submitting', 'processing', 'submission_unknown', None]:
            with self.subTest(status=status):
                original = upgrade.json_bytes({'status': status, 'synthetic': True})
                path.write_bytes(original)
                with self.assertRaisesRegex(ValueError, '音色操作'):
                    upgrade.stopped(self.root)
                self.assertEqual(path.read_bytes(), original)
        for status in ['succeeded', 'failed']:
            path.write_bytes(upgrade.json_bytes({'status': status}))
            upgrade.stopped(self.root)

    def test_unresolved_audio_database_intent_blocks_offline_installer(self):
        path = self.root / 'Haike_video/.backlot/studio.sqlite3'
        path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE studio_audio_operations(attempts INTEGER, outcome TEXT)')
            db.execute('INSERT INTO studio_audio_operations VALUES(1,NULL)'); db.commit()
            with self.assertRaisesRegex(ValueError, '音色操作'):
                upgrade.stopped(self.root)
            db.execute("UPDATE studio_audio_operations SET outcome='failed'"); db.commit()
            upgrade.stopped(self.root)
            db.execute('UPDATE studio_audio_operations SET attempts=0,outcome=NULL'); db.commit()
            upgrade.stopped(self.root)

    def test_corrupt_audio_record_fails_closed(self):
        path = self.root / 'Haike_video/.backlot/audio-center-internal/voice/operations/test/operation.json'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'{invalid')
        with self.assertRaises(ValueError):
            upgrade.stopped(self.root)


if __name__ == '__main__':
    unittest.main()
