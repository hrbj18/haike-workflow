"""Private snapshots retain WIP, SQLite WAL data and external assets accurately."""
import hashlib
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('development_transfer', ROOT / 'scripts/package-development-transfer.py')
transfer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transfer)


class DevelopmentTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'workspace'
        self.root.mkdir()
        self.output = self.base / 'transfer.zip'

    def tearDown(self):
        self.temp.cleanup()

    def put(self, name, data=b'data'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def directory_link(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
            return
        except OSError:
            if os.name == 'nt':
                result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(target)],
                                        capture_output=True, timeout=10)
                if result.returncode == 0:
                    return
        self.skipTest('Creating directory symlinks/junctions unavailable')

    def test_wip_private_files_git_and_native_cache_survive_with_hashes(self):
        expected = {'.git/HEAD': b'ref: refs/heads/work\n', '.local/ms/native/a.json': b'{"local":true}',
                    'untracked.py': b'work in progress', 'Haike_video/.backlot/private.yaml': b'fake-secret: test',
                    'Haike_video/projects/p/original.motion': b'opaque native package'}
        for name, value in expected.items():
            self.put(name, value)
        for name in ['.venv/skip', 'nested/node_modules/skip', 'dist/old.zip', 'deliverables/old.zip',
                     'migration/.staging/skip', '.pytest_cache/skip']:
            self.put(name)
        report = transfer.build(self.root, self.output)
        self.assertEqual(report['status'], 'verified')
        with zipfile.ZipFile(self.output) as package:
            hashes = {row['path']: row for row in map(json.loads, package.read('workspace/migration/FILE_HASHES.jsonl').splitlines())}
            for name, value in expected.items():
                self.assertEqual(package.read('workspace/' + name), value)
                self.assertEqual(hashes[name]['sha256'], hashlib.sha256(value).hexdigest())
            self.assertEqual(set(hashes), set(expected))
        self.assertTrue(Path(str(self.output) + '.sha256').exists())

    def test_sqlite_backup_includes_uncheckpointed_wal_and_omits_sidecars(self):
        source = self.put('Haike_video/.backlot/jobs.sqlite3', b'')
        connection = sqlite3.connect(source)
        try:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA wal_autocheckpoint=0')
            connection.execute('CREATE TABLE jobs(id TEXT, result TEXT)')
            connection.execute('INSERT INTO jobs VALUES (?,?)', ('original-job', 'complete'))
            connection.commit()
            self.assertTrue(Path(str(source) + '-wal').exists())
            report = transfer.build(self.root, self.output)
            self.assertEqual(len(report['sqlite_snapshots']), 1)
            with zipfile.ZipFile(self.output) as package:
                names = package.namelist()
                self.assertFalse(any(name.endswith(('-wal', '-shm')) for name in names))
                restored = self.base / 'restored.sqlite3'
                restored.write_bytes(package.read('workspace/Haike_video/.backlot/jobs.sqlite3'))
            with closing(sqlite3.connect(restored)) as check:
                self.assertEqual(check.execute('SELECT * FROM jobs').fetchall(), [('original-job', 'complete')])
                self.assertEqual(check.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        finally:
            connection.close()

    def test_external_directory_is_packaged_and_overlap_deduplicates(self):
        ext = self.base / 'external'
        ext.mkdir()
        (ext / 'file.motion').write_bytes(b'motion')
        mapping = [{'source': str(ext), 'relative': '_migration_external/cache'},
                   {'source': str(ext / 'file.motion'), 'relative': '_migration_external/cache/file.motion'}]
        report = transfer.build(self.root, self.output, mapping)
        self.assertEqual(report['deduplicated_entries'], 1)
        with zipfile.ZipFile(self.output) as package:
            self.assertEqual(package.read('workspace/_migration_external/cache/file.motion'), b'motion')

    def test_duplicate_destination_and_unsafe_mapping_rejected(self):
        self.put('conflict.txt', b'original')
        external = self.base / 'external.txt'
        external.write_bytes(b'different')
        with self.assertRaisesRegex(transfer.TransferError, 'Duplicate'):
            transfer.build(self.root, self.output, [{'source': str(external), 'relative': 'conflict.txt'}])
        for value in ['../escape', '/absolute', 'C:/drive', 'one/./file']:
            with self.assertRaises(transfer.TransferError):
                transfer.safe_relative(value)

    def test_recovery_manifest_required_files_checked(self):
        self.put('migration/RECOVERY_MANIFEST.json', json.dumps({'reading_records': [{'path': 'missing.md', 'sha256': '0' * 64}]}).encode())
        with self.assertRaisesRegex(transfer.TransferError, 'Required recovery file missing'):
            transfer.build(self.root, self.output)

    def test_selection_restricts_state_without_discarding_source(self):
        for name in ['source/module.py', '.local/chosen/request.json', '.local/chosen/nested/item',
                     '.local/other/large.mp4', 'Haike_video/projects/keep/asset.mp4',
                     'Haike_video/projects/omit/large.mp4', '.local/single.json']:
            self.put(name)
        selection = {'restrict_roots': ['.local', 'Haike_video/projects'],
                     'include_roots': ['.local/chosen', 'Haike_video/projects/keep'],
                     'include_files': ['.local/single.json']}
        report = transfer.build(self.root, self.output, selection=selection)
        with zipfile.ZipFile(self.output) as package:
            files = set(package.namelist())
            self.assertIn('workspace/source/module.py', files)
            self.assertIn('workspace/.local/chosen/nested/item', files)
            self.assertIn('workspace/.local/single.json', files)
            self.assertIn('workspace/Haike_video/projects/keep/asset.mp4', files)
            self.assertNotIn('workspace/.local/other/large.mp4', files)
            self.assertNotIn('workspace/Haike_video/projects/omit/large.mp4', files)
        self.assertEqual(sum(row['reason'] == 'outside declared development selection' for row in report['excluded_paths']), 2)

    def test_repeated_media_is_hydratable_and_all_logical_hashes_remain(self):
        media = b'a verified media byte pattern' * 50000
        self.put('.local/media/first.mp4', media)
        self.put('.local/media/second.mp4', media)
        self.put('.local/media/record.json', media)
        report = transfer.build(self.root, self.output, deduplicate_files=True)
        self.assertEqual(report['content_duplicate_files'], 1)
        self.assertEqual(report['content_deduplicated_bytes'], len(media))
        with zipfile.ZipFile(self.output) as package:
            duplicates = json.loads(package.read('workspace/migration/DUPLICATE_FILES.json'))['duplicates']
            self.assertEqual(duplicates, [{'path': '.local/media/second.mp4', 'target': '.local/media/first.mp4',
                                          'bytes': len(media), 'sha256': hashlib.sha256(media).hexdigest()}])
            self.assertNotIn('workspace/.local/media/second.mp4', package.namelist())
            self.assertEqual(package.read('workspace/.local/media/first.mp4'), media)
            self.assertEqual(package.read('workspace/.local/media/record.json'), media)
            hashes = {row['path']: row for row in map(json.loads, package.read('workspace/migration/FILE_HASHES.jsonl').splitlines())}
            self.assertEqual(len(hashes), 3)
            self.assertEqual(hashes['.local/media/second.mp4']['duplicate_of'], '.local/media/first.mp4')

    def test_large_selection_compiles_and_preserves_exact_file_membership(self):
        selection = transfer.compile_selection({'restrict_roots': ['.local'],
                                               'include_files': [f'.local/a/{index}/result.json' for index in range(20000)]})
        self.assertTrue(transfer.selected('.local/a/19999/result.json', False, selection))
        self.assertTrue(transfer.selected('.local/a/19999', True, selection))
        self.assertFalse(transfer.selected('.local/a/20000/result.json', False, selection))
        self.assertFalse(transfer.selected('.local/a/20000', True, selection))
        self.assertTrue(transfer.selected('source/module.py', False, selection))

    def test_duplicate_sub_megabyte_images_always_reference_physical_files(self):
        image = b'small native JPEG frame bytes' * 1200
        self.assertLess(len(image), 1024 * 1024)
        self.put('.local/native/frame-001.jpg', image)
        self.put('.local/native/frame-002.jpg', image)
        self.put('.local/native/frame-003.jpg', image)
        report = transfer.build(self.root, self.output, deduplicate_files=True)
        self.assertEqual(report['content_duplicate_files'], 2)
        with zipfile.ZipFile(self.output) as package:
            rows = json.loads(package.read('workspace/migration/DUPLICATE_FILES.json'))['duplicates']
            self.assertEqual({row['target'] for row in rows}, {'.local/native/frame-001.jpg'})
            self.assertTrue(all('workspace/' + row['target'] in package.namelist() for row in rows))
            self.assertFalse(any(row['target'] in {item['path'] for item in rows} for row in rows))

    def test_windows_long_source_paths_are_readable(self):
        branch = transfer.extended_path(self.root / 'long')
        folder = branch
        for index in range(6):
            folder = folder / (str(index) + '-' + 'a' * 48)
        try:
            folder.mkdir(parents=True)
            (folder / 'state.json').write_bytes(b'{"deep":true}')
            report = transfer.build(self.root, self.output)
            self.assertEqual(report['payload_files'], 1)
            with zipfile.ZipFile(self.output) as package:
                self.assertTrue(any(name.endswith('/state.json') for name in package.namelist()))
        finally:
            self.assertTrue(branch.is_relative_to(transfer.extended_path(self.root)))
            if branch.exists():
                shutil.rmtree(branch)

    def test_external_link_is_rejected_when_symlinks_available(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'private.txt').write_bytes(b'external')
        link = self.root / 'external-link'
        self.directory_link(link, outside)
        with self.assertRaisesRegex(transfer.TransferError, 'Link leaves'):
            transfer.build(self.root, self.output)
        report = json.loads(Path(str(self.output) + '.build-report.json').read_text(encoding='utf-8'))
        self.assertEqual(len(report['rejected_links']), 1)

    def test_explicit_external_mapping_allows_materializing_a_junction(self):
        outside = self.base / 'external-declared'
        outside.mkdir()
        (outside / 'preserved.motion').write_bytes(b'declared original package')
        link = self.root / 'external-declared-link'
        self.directory_link(link, outside)
        report = transfer.build(self.root, self.output,
                                [{'source': str(outside), 'relative': '_migration_external/cache'}])
        self.assertEqual(report['rejected_links'], [])
        self.assertEqual(len(report['internal_links']), 1)
        with zipfile.ZipFile(self.output) as package:
            self.assertEqual(package.read('workspace/external-declared-link/preserved.motion'),
                             b'declared original package')
            self.assertEqual(package.read('workspace/_migration_external/cache/preserved.motion'),
                             b'declared original package')

    def test_external_exclusion_prunes_before_acl_protected_path_inspection(self):
        external = self.base / 'external-cache'
        denied = external / 'denied'
        denied.mkdir(parents=True)
        (denied / 'test-temporary.txt').write_bytes(b'excluded test fixture')
        (external / 'needed.motion').write_bytes(b'preserve')
        original_is_dir = Path.is_dir
        original_resolve = Path.resolve

        def guarded_is_dir(path):
            if path.name == 'denied':
                raise PermissionError('ACL prevents inspection of excluded directory')
            return original_is_dir(path)

        def guarded_resolve(path, *args, **kwargs):
            if path.name == 'denied':
                raise PermissionError('ACL prevents inspection of excluded directory')
            return original_resolve(path, *args, **kwargs)

        with mock.patch.object(Path, 'is_dir', guarded_is_dir), mock.patch.object(Path, 'resolve', guarded_resolve):
            report = transfer.build(self.root, self.output,
                                    [{'source': str(external), 'relative': '_migration_external/cache'}],
                                    selection={'exclude_roots': ['_migration_external/cache/denied']})
        self.assertEqual(report['payload_files'], 1)
        with zipfile.ZipFile(self.output) as package:
            self.assertEqual(package.read('workspace/_migration_external/cache/needed.motion'), b'preserve')
            self.assertFalse(any('denied' in name for name in package.namelist()))


if __name__ == '__main__':
    unittest.main()
