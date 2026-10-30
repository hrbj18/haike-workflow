"""Private migration recovery must preserve frozen evidence and paid task history."""
from __future__ import annotations

from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    'restore_development', Path(__file__).resolve().parents[1] / 'scripts' / 'restore-development.py')
RECOVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECOVERY)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'new-project'
        self.root.mkdir()
        self.root = self.root.resolve()
        self.old = 'D:\\old\\haike'
        self.record = self.write('migration/01-history.md', 'Full development history.\n')
        self.manifest = {
            'schema': 1, 'snapshot_id': 'unit-private-snapshot', 'focus': '.motion',
            'source_root': self.old,
            'path_mappings': [{'old': self.old, 'new_relative': '.'},
                              {'old': 'C:\\HaikeCache', 'new_relative': '_migration_external/HaikeCache'}],
            'reading_records': [{'path': 'migration/01-history.md',
                                 'sha256': hashlib.sha256(self.record.read_bytes()).hexdigest()}],
            'relocation_configs': ['.local/motion-console/defaults.json', 'creatorhub/config.yaml'],
        }
        self.write('migration/RECOVERY_MANIFEST.json', json.dumps(self.manifest))

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def duplicates(self, entries):
        return self.write('migration/DUPLICATE_FILES.json',
                          json.dumps({'schema': 1, 'duplicates': entries}))

    def duplicate_entry(self, source='media/original.bin', destination='projects/copied.bin'):
        content = b'independent migration bytes\x00' * 100
        path = self.root / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {'path': destination, 'target': source, 'bytes': len(content),
                'sha256': hashlib.sha256(content).hexdigest()}

    def test_verify_attests_integrity_only_and_detects_missing_or_changed_records(self):
        report = RECOVERY.verify(self.root, RECOVERY.load_manifest(self.root))
        self.assertTrue(report['ok'])
        self.assertTrue(report['integrity_only'])
        self.assertEqual(report['agent_reading_or_understanding'], 'not_attested')
        self.record.write_text('changed', encoding='utf-8')
        self.assertFalse(RECOVERY.verify(self.root, self.manifest)['ok'])
        self.record.unlink()
        report = RECOVERY.verify(self.root, self.manifest)
        self.assertFalse(report['ok'])
        self.assertFalse(report['records'][0]['exists'])

    def test_relocation_updates_only_defaults_with_backups_and_is_idempotent(self):
        old_config = json.dumps({'image': self.old + '\\projects\\image.png',
                                 'external': 'C:/HaikeCache/avatar.mp4',
                                 'unrelated': 'D:/old/haike-copy/keep.png'})
        config = self.write('.local/motion-console/defaults.json', old_config)
        yaml = self.write('creatorhub/config.yaml', 'media_root: D:/old/haike/media\n')
        original_yaml = yaml.read_bytes()
        frozen = self.write('.local/motiongit/drafts/job/request.json', old_config)
        frozen_before = frozen.read_bytes()
        dry = RECOVERY.relocate(self.root, self.manifest)
        self.assertEqual(len(dry['configs_to_update']), 2)
        self.assertEqual(config.read_text(encoding='utf-8'), old_config)
        self.assertFalse((self.root / RECOVERY.REPORT_ROOT).exists())
        report = RECOVERY.relocate(self.root, self.manifest, apply=True)
        value = json.loads(config.read_text(encoding='utf-8'))
        self.assertTrue(value['image'].startswith(self.root.as_posix()))
        self.assertTrue(value['external'].startswith((self.root / '_migration_external/HaikeCache').as_posix()))
        self.assertEqual(value['unrelated'], 'D:/old/haike-copy/keep.png')
        self.assertEqual(frozen.read_bytes(), frozen_before)
        self.assertEqual(report['historical_files_modified'], 0)
        self.assertEqual(len(report['historical_references']), 1)
        backup = self.root / report['backup'] / 'files'
        self.assertEqual((backup / '.local/motion-console/defaults.json').read_text(encoding='utf-8'), old_config)
        self.assertEqual((backup / 'creatorhub/config.yaml').read_bytes(), original_yaml)
        again = RECOVERY.relocate(self.root, self.manifest, apply=True)
        self.assertEqual(again['configs_updated'], [])
        self.assertIsNone(again['backup'])

    def test_sqlite_json_references_are_reported_without_mutation(self):
        database = self.root / 'Haike_video/.backlot/production-queue.sqlite3'
        database.parent.mkdir(parents=True)
        with closing(sqlite3.connect(database)) as connection:
            connection.execute('CREATE TABLE "task history" ("input json" TEXT, phase TEXT)')
            connection.execute('INSERT INTO "task history" VALUES (?, ?)',
                               (json.dumps({'path': self.old + '\\projects\\paid.mp4'}), 'submission_unknown'))
            connection.execute('CREATE VIRTUAL TABLE search USING fts5(content)')
            connection.commit()
        original = database.read_bytes()
        report = RECOVERY.relocate(self.root, self.manifest, apply=True)
        self.assertEqual(database.read_bytes(), original)
        references = report['historical_references'][0]
        self.assertEqual(references['kind'], 'sqlite')
        self.assertEqual(references['references'], 1)
        self.assertFalse(references['modified'])
        with closing(sqlite3.connect(database)) as connection:
            self.assertEqual(connection.execute('SELECT phase FROM "task history"').fetchone()[0], 'submission_unknown')

    def test_live_wal_is_reported_without_creating_sidecars(self):
        database = self.root / 'Haike_video/.backlot/production-queue.sqlite3'
        database.parent.mkdir(parents=True)
        with closing(sqlite3.connect(database)) as connection:
            connection.execute('CREATE TABLE tasks (path TEXT)')
            connection.commit()
        wal = database.with_name(database.name + '-wal')
        wal.write_bytes(b'pending live WAL snapshot')
        report = RECOVERY.relocate(self.root, self.manifest)
        self.assertIn({'path': 'Haike_video/.backlot/production-queue.sqlite3',
                       'reason': 'sqlite_wal_requires_consistent_snapshot'}, report['skipped'])
        self.assertEqual(wal.read_bytes(), b'pending live WAL snapshot')
        self.assertFalse(database.with_name(database.name + '-shm').exists())

    def test_rewriter_supports_case_slashes_and_exact_path_boundaries(self):
        rewrite = RECOVERY.PathRewriter(self.root, self.manifest)
        values = ['d:/OLD/HAIKE/projects/input.json', self.old + '\\projects\\input.json',
                  json.dumps(self.old + '\\projects\\input.json')]
        for value in values:
            result, changes = rewrite.replace(value)
            self.assertEqual(changes, 1, value)
            self.assertIn(self.root.as_posix(), result)
        for value in ['D:/old/haike-other/input.json', 'D:/old/haikex/input.json',
                      'prefixD:/old/haike/input.json']:
            self.assertEqual(rewrite.replace(value), (value, 0))

    def test_rewriter_does_not_cascade_or_repeat_into_target_inside_old_root(self):
        old = self.root.parent.as_posix()
        manifest = {**self.manifest, 'source_root': old,
                    'path_mappings': [{'old': old, 'new_relative': '.'},
                                      {'old': 'C:/HaikeCache', 'new_relative': '_migration_external/HaikeCache'}]}
        rewrite = RECOVERY.PathRewriter(self.root, manifest)
        value = 'C:/HaikeCache/image.png'
        expected = (self.root / '_migration_external/HaikeCache/image.png').as_posix()
        self.assertEqual(rewrite.replace(value), (expected, 1))
        self.assertEqual(rewrite.replace(expected), (expected, 0))

    def test_manifest_rejects_arbitrary_history_write_path_or_escape(self):
        self.manifest['relocation_configs'] = ['Haike_video/projects/frozen/request.json']
        self.write('migration/RECOVERY_MANIFEST.json', json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, 'allowlist'):
            RECOVERY.load_manifest(self.root)
        self.manifest['relocation_configs'] = []
        self.manifest['path_mappings'][0]['new_relative'] = '../outside'
        self.write('migration/RECOVERY_MANIFEST.json', json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            RECOVERY.load_manifest(self.root)

    def test_linked_config_is_rejected_before_mutation(self):
        outside = Path(self.temporary.name) / 'outside'
        outside.mkdir()
        config = outside / 'defaults.json'
        config.write_text(json.dumps({'path': self.old + '\\private'}), encoding='utf-8')
        link = self.root / '.local/motion-console'
        link.parent.mkdir()
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                self.skipTest('Host does not permit creation of directory symlinks')
            result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(outside)],
                                    capture_output=True, check=False)
            if result.returncode:
                self.skipTest('Host does not permit directory symlinks or junctions')
        before = config.read_bytes()
        with self.assertRaisesRegex(ValueError, 'link'):
            RECOVERY.relocate(self.root, self.manifest, apply=True)
        self.assertEqual(config.read_bytes(), before)

    def test_linked_reading_record_is_rejected(self):
        outside = Path(self.temporary.name) / 'outside-record.md'
        outside.write_text('outside', encoding='utf-8')
        self.record.unlink()
        try:
            self.record.symlink_to(outside)
        except OSError:
            self.skipTest('Host does not permit creation of symlinks')
        with self.assertRaisesRegex(ValueError, 'link'):
            RECOVERY.verify(self.root, self.manifest)

    def test_linked_ancestor_inside_root_with_missing_leaf_is_rejected(self):
        actual = self.root / 'actual'
        actual.mkdir()
        link = self.root / 'alias'
        try:
            link.symlink_to(actual, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                self.skipTest('Host does not permit directory links')
            result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(actual)],
                                    capture_output=True, check=False)
            if result.returncode:
                self.skipTest('Host does not permit directory junctions')
        with self.assertRaisesRegex(ValueError, 'link'):
            RECOVERY.safe(self.root, 'alias/missing/file.bin')

    def test_overlarge_text_is_reported_not_silently_ignored(self):
        self.write('.local/motion-console/defaults.json', json.dumps({'p': self.old + '\\image'}))
        with patch.object(RECOVERY, 'MAX_TEXT_BYTES', 2):
            report = RECOVERY.relocate(self.root, self.manifest, apply=True)
        self.assertIn({'path': '.local/motion-console/defaults.json',
                       'reason': 'text_exceeds_64_mib'}, report['skipped'])
        self.assertEqual(report['configs_updated'], [])

    def test_duplicate_index_has_separate_budget_from_history_text(self):
        entry = self.duplicate_entry()
        self.duplicates([entry])
        with patch.object(RECOVERY, 'MAX_TEXT_BYTES', 2):
            report = RECOVERY.hydrate(self.root)
        self.assertEqual(report['files_copied'], 1)

    def test_overlarge_duplicate_index_is_rejected_before_any_copy(self):
        entry = self.duplicate_entry()
        self.duplicates([entry])
        with patch.object(RECOVERY, 'MAX_DUPLICATE_MANIFEST_BYTES', 2):
            with self.assertRaisesRegex(ValueError, 'Duplicate file manifest exceeds'):
                RECOVERY.hydrate(self.root)
        self.assertFalse((self.root / entry['path']).exists())

    def test_hydrate_copies_independent_files_and_is_idempotent(self):
        entry = self.duplicate_entry()
        self.duplicates([entry])
        preview = RECOVERY.hydrate(self.root, dry_run=True)
        self.assertEqual(preview['files_pending'], 1)
        self.assertEqual(preview['bytes_to_copy'], entry['bytes'])
        self.assertFalse((self.root / entry['path']).exists())
        report = RECOVERY.hydrate(self.root)
        self.assertEqual(report['files_copied'], 1)
        self.assertEqual(report['bytes_copied'], entry['bytes'])
        self.assertTrue(report['logical_snapshot_complete'])
        self.assertNotIn('records', report)
        source, destination = self.root / entry['target'], self.root / entry['path']
        self.assertEqual(source.read_bytes(), destination.read_bytes())
        self.assertNotEqual(source.stat().st_ino, destination.stat().st_ino)
        again = RECOVERY.hydrate(self.root)
        self.assertEqual(again['files_copied'], 0)
        self.assertEqual(again['files_already_present'], 1)
        receipt = json.loads(Path(again['report_path']).read_text(encoding='utf-8'))
        self.assertEqual(receipt['records'][0]['status'], 'already_present')
        destination.write_bytes(b'new local development')
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), entry['sha256'])

    @unittest.skipUnless(os.name == 'nt', 'Windows file-lock recovery')
    def test_copy_retries_a_transient_windows_replace_lock(self):
        entry = self.duplicate_entry()
        replace = RECOVERY.os.replace
        attempts = []

        def locked_once(source, destination):
            attempts.append((source, destination))
            if len(attempts) == 1:
                error = PermissionError(13, 'Access is denied')
                error.winerror = 5
                raise error
            return replace(source, destination)

        with patch.object(RECOVERY.os, 'replace', side_effect=locked_once):
            RECOVERY.copy_independently(self.root, entry)
        self.assertEqual(len(attempts), 2)
        self.assertEqual((self.root / entry['path']).read_bytes(), (self.root / entry['target']).read_bytes())

    @unittest.skipUnless(os.name == 'nt', 'Windows file-lock recovery')
    def test_copy_lock_retry_never_overwrites_a_changed_reservation(self):
        entry = self.duplicate_entry()

        def changed_reservation(source, destination):
            destination.write_bytes(b'new user content')
            error = PermissionError(13, 'Access is denied')
            error.winerror = 5
            raise error

        with patch.object(RECOVERY.os, 'replace', side_effect=changed_reservation):
            with self.assertRaisesRegex(ValueError, 'destination changed'):
                RECOVERY.copy_independently(self.root, entry)
        self.assertEqual((self.root / entry['path']).read_bytes(), b'new user content')

    @unittest.skipUnless(os.name == 'nt', 'Windows file-lock recovery')
    def test_copy_stops_retrying_a_persistent_windows_lock(self):
        entry = self.duplicate_entry()
        error = PermissionError(13, 'Access is denied')
        error.winerror = 32
        with patch.object(RECOVERY.os, 'replace', side_effect=error) as replace, patch.object(RECOVERY.time, 'sleep'):
            with self.assertRaises(PermissionError):
                RECOVERY.copy_independently(self.root, entry)
        self.assertEqual(replace.call_count, 4)
        self.assertFalse((self.root / entry['path']).exists())
        self.assertFalse(list((self.root / entry['path']).parent.glob('.hydrate-*')))

    def test_hydrate_rejects_tampered_source_before_any_copy(self):
        first = self.duplicate_entry()
        second = self.duplicate_entry('media/second.bin', 'projects/second.bin')
        self.duplicates([first, second])
        source = self.root / second['target']
        source.write_bytes(b'x' * second['bytes'])
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            RECOVERY.hydrate(self.root)
        self.assertFalse((self.root / first['path']).exists())

    def test_hydrate_refuses_existing_different_destination_and_preserves_it(self):
        entry = self.duplicate_entry()
        self.duplicates([entry])
        destination = self.root / entry['path']
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b'x' * entry['bytes'])
        before = destination.read_bytes()
        with self.assertRaisesRegex(ValueError, 'refuses to overwrite'):
            RECOVERY.hydrate(self.root)
        self.assertEqual(destination.read_bytes(), before)

    def test_hydrate_rejects_escape_duplicate_destinations_and_missing_targets(self):
        entry = self.duplicate_entry()
        self.duplicates([{**entry, 'path': '../outside.bin'}])
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            RECOVERY.hydrate(self.root)
        self.duplicates([entry, entry])
        with self.assertRaisesRegex(ValueError, 'Duplicate destination'):
            RECOVERY.hydrate(self.root)
        self.duplicates([{**entry, 'target': 'missing/physical.bin'}])
        with self.assertRaisesRegex(ValueError, 'physically exist'):
            RECOVERY.hydrate(self.root)

    def test_hydrate_reports_needed_space_in_doctor_and_checks_disk_space(self):
        entry = self.duplicate_entry()
        self.duplicates([entry])
        with patch.object(RECOVERY, 'executable_version',
                          return_value={'available': True, 'version': 'v22.0.0'}):
            report = RECOVERY.doctor(self.root, self.manifest)
        self.assertEqual(report['hydration']['files_pending'], 1)
        self.assertEqual(report['hydration']['bytes_needed'], entry['bytes'])
        disk_usage = shutil.disk_usage(self.root)
        with patch.object(RECOVERY.shutil, 'disk_usage',
                          return_value=type(disk_usage)(disk_usage.total, disk_usage.used, 0)):
            with self.assertRaisesRegex(ValueError, 'Insufficient free space'):
                RECOVERY.hydrate(self.root)
        self.assertFalse((self.root / entry['path']).exists())

    @unittest.skipUnless(os.name == 'nt', 'Exercises actual Windows extended-length filenames')
    def test_windows_long_paths_hydrate_verify_and_relocate_without_prefix_in_business_json(self):
        # The actual source, destination and same-directory temporary names all
        # exceed MAX_PATH, including the original failing temporary-file case.
        long_root = self.root.joinpath(*('deep-' + 'x' * 45 for _index in range(5)))
        fs_root = RECOVERY.filesystem_path(long_root)
        fs_root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, RECOVERY.filesystem_path(self.root))
        migration = fs_root / 'migration'
        migration.mkdir()
        (migration / '01-history.md').write_bytes(self.record.read_bytes())
        (migration / 'RECOVERY_MANIFEST.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        source_relative = 'media/original-frame/f_0001.jpg'
        destination_relative = 'projects/review-frames/f_0001.jpg'
        content = b'long-path-frame-data' * 100
        source = fs_root / source_relative
        source.parent.mkdir(parents=True)
        source.write_bytes(content)
        self.assertGreater(len(str(RECOVERY.standard_path(source))), 300)
        duplicate = {'path': destination_relative, 'target': source_relative,
                     'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
        (migration / 'DUPLICATE_FILES.json').write_text(
            json.dumps({'schema': 1, 'duplicates': [duplicate]}), encoding='utf-8')
        manifest = RECOVERY.load_manifest(long_root)
        self.assertTrue(RECOVERY.verify(long_root, manifest)['ok'])
        report = RECOVERY.hydrate(long_root)
        self.assertEqual(report['files_copied'], 1)
        destination = fs_root / destination_relative
        self.assertEqual(destination.read_bytes(), content)
        self.assertFalse(list(destination.parent.glob('.hydrate-*')))
        self.assertEqual(RECOVERY.hydrate(long_root)['files_already_present'], 1)
        defaults = fs_root / '.local/motion-console/defaults.json'
        defaults.parent.mkdir(parents=True)
        defaults.write_text(json.dumps({'image': self.old + '\\projects\\image.png'}), encoding='utf-8')
        database = fs_root / 'Haike_video/.backlot/production-queue.sqlite3'
        database.parent.mkdir(parents=True)
        with closing(sqlite3.connect(str(database))) as connection:
            connection.execute('CREATE TABLE tasks (path TEXT)')
            connection.execute('INSERT INTO tasks VALUES (?)', (self.old + '\\projects\\paid.mp4',))
            connection.commit()
        frozen_database = database.read_bytes()
        relocation = RECOVERY.relocate(long_root, manifest, apply=True)
        self.assertEqual(len(relocation['configs_updated']), 1)
        self.assertEqual(relocation['historical_references'][0]['references'], 1)
        self.assertEqual(database.read_bytes(), frozen_database)
        value = json.loads(defaults.read_text(encoding='utf-8'))['image']
        self.assertTrue(value.startswith(long_root.as_posix()))
        self.assertNotIn('//?/', value)
        self.assertNotIn('\\\\?\\', value)
        self.assertNotIn('\\\\?\\', relocation['report_path'])


if __name__ == '__main__':
    unittest.main()
