"""Template updates preserve private data and fail before modifying bad targets."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('template_update', ROOT / 'scripts/install-template-update.py')
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


class TemplateUpdateTests(unittest.TestCase):
    def fixture(self, root):
        bundle, target = root / 'bundle', root / 'old installation'
        def write(folder, name, content):
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            return path
        write(target, 'Haike_video/backlot/server.py', b'# original service\n')
        lock = write(target, 'Haike_video/requirements.txt', b'fixture dependencies')
        write(target, 'Haike_video/backlot/studio_template_library.py', b'# old\n')
        write(target, 'Haike_video/.backlot/config.json', b'keep exact private config')
        write(target, 'RELEASE.json', b'{"source_commit":"old"}')
        files = {
            'Haike_video/backlot/studio_template_library.py': b'# new\n',
            'Haike_video/templates/library.json': b'{"templates":[{"id":"fixture"}]}',
            'Haike_video/templates/library-covers/fixture.jpg': b'fixture screenshot',
        }
        entries = []
        for name, content in files.items():
            path = write(bundle / 'payload', name, content)
            entries.append({'path': name, 'size': len(content), 'sha256': update.digest(path)})
        plan = {'schema': 1, 'id': 'fixture-update', 'source_snapshot': 'snapshot-fixture',
                'covered_template_ids': ['fixture'], 'files': entries,
                'required_locks': [{'path': 'Haike_video/requirements.txt', 'sha256': update.digest(lock)}]}
        write(bundle, 'UPDATE-MANIFEST.json', update.json_bytes(plan))
        write(target, 'PACKAGE-MANIFEST.json', update.json_bytes({'schema': 1, 'files': [
            {'path': 'RELEASE.json', 'size': 23, 'sha256': update.digest(target / 'RELEASE.json'), 'mutable': False}]}))
        return bundle, target

    def test_apply_idempotency_manifest_and_rollback_preserve_private_data(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle, target = self.fixture(Path(folder))
            original = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob('*') if p.is_file()}
            self.assertTrue(update.apply(bundle, target, check=True)['ok'])
            self.assertFalse((target / '.local').exists())
            result = update.apply(bundle, target)
            self.assertEqual(result['covers'], 1)
            manifest = update.read(target / 'PACKAGE-MANIFEST.json')
            for entry in manifest['files']:
                self.assertEqual(entry['sha256'], update.digest(target / entry['path']))
            self.assertEqual(update.read(target / 'RELEASE.json')['source_commit'], 'old')
            self.assertTrue(update.apply(bundle, target)['already_current'])
            update.restore(target, Path(result['backup']))
            for name, content in original.items():
                self.assertEqual((target / name).read_bytes(), content)
            self.assertFalse((target / 'Haike_video/templates/library-covers/fixture.jpg').exists())

    def test_corrupt_payload_and_incompatible_runtime_leave_target_untouched(self):
        for failure in ('corrupt', 'lock'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                bundle, target = self.fixture(Path(folder))
                if failure == 'corrupt':
                    (bundle / 'payload/Haike_video/templates/library-covers/fixture.jpg').write_bytes(b'corrupt')
                else:
                    (target / 'Haike_video/requirements.txt').write_bytes(b'different dependencies')
                with self.assertRaises(ValueError):
                    update.apply(bundle, target)
                self.assertEqual((target / 'Haike_video/backlot/studio_template_library.py').read_bytes(), b'# old\n')
                self.assertFalse((target / '.local').exists())

    def test_path_traversal_and_private_payload_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('../outside', 'C:/outside', 'Haike_video/../../outside',
                         'Haike_video/.backlot/config.json', 'creatorhub/config.yaml'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    update.safe(Path(folder), name, payload=True)

    def test_rollback_refuses_to_overwrite_subsequent_user_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle, target = self.fixture(Path(folder))
            result = update.apply(bundle, target)
            edited = target / 'Haike_video/backlot/studio_template_library.py'
            edited.write_bytes(b'# later user work\n')
            with self.assertRaises(ValueError):
                update.restore(target, Path(result['backup']))
            self.assertEqual(edited.read_bytes(), b'# later user work\n')


if __name__ == '__main__':
    unittest.main()
