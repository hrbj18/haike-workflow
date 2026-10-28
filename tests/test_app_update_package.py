"""Application patches contain only compatible public program changes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('app_update_package', ROOT / 'scripts/package-app-update.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def json_file(root, name, value):
    return write(root, name, json.dumps(value).encode('utf-8'))


def manifest(root):
    entries = []
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name != 'PACKAGE-MANIFEST.json':
            entries.append({'path': path.relative_to(root).as_posix(), 'size': path.stat().st_size,
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'mutable': False})
    json_file(root, 'PACKAGE-MANIFEST.json', {'schema': 1, 'files': entries})


class ApplicationUpdatePackageTests(unittest.TestCase):
    def test_real_staging_inventory_and_authoring_build_are_compatible(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            old, new = self.stages(folder)
            for root, commit in ((old, 'a' * 40), (new, 'b' * 40)):
                json_file(root, 'RUNTIME-INVENTORY.json', {'source_commit': commit, 'runtime_source_sha256': 'c' * 64,
                                                         'environments': {'python': 'same-approved-runtime'}})
                write(root, 'prototypes/haike-avatar-generator/dist/client/index.html', ('<html>' + commit + '</html>').encode())
                write(root, 'Haike_video/tests/backlot/test_synthetic.py', ('# test ' + commit).encode())
                manifest(root)
            result = self.build(folder, old, new)
            with zipfile.ZipFile(result['package']) as archive:
                self.assertNotIn('payload/RUNTIME-INVENTORY.json', archive.namelist())
                self.assertIn('payload/prototypes/haike-avatar-generator/dist/client/index.html', archive.namelist())
                self.assertIn('payload/Haike_video/tests/backlot/test_synthetic.py', archive.namelist())
            # Runtime provenance changes other than application source commit
            # remain a full-upgrade requirement.
            inventory = package.read_json(new / 'RUNTIME-INVENTORY.json')
            inventory['runtime_source_sha256'] = 'd' * 64
            json_file(new, 'RUNTIME-INVENTORY.json', inventory)
            manifest(new)
            with self.assertRaisesRegex(ValueError, '运行环境来源'):
                package.build(old, new, folder / 'other-release/update.zip', 'https://example.test/update.zip')

    def stages(self, folder):
        old, new = folder / 'old', folder / 'new'
        for root, version, commit, body in ((old, '1.0.0', 'a' * 40, b'# old program\n'),
                                            (new, '1.0.1', 'b' * 40, b'# new program\n')):
            release = {'edition': 'haike-workflow-2', 'version': version, 'channel': 'stable',
                       'runtime_id': 'haike-windows-x64-v1', 'data_schema': 1,
                       'platform': 'windows-x64', 'source_commit': commit}
            json_file(root, 'RELEASE.json', release)
            json_file(root, 'VERSION.json', {k: v for k, v in release.items() if k != 'source_commit'})
            write(root, 'Haike_video/backlot/server.py', body)
            write(root, 'Haike_video/requirements.txt', b'fixed-dependency==1\n')
            write(root, 'Haike_video/remotion-composer/package-lock.json', b'{}\n')
            write(root, 'runtime/python/python.exe', b'fixture-runtime')
            # Existing local-only media must never enter a public application patch.
            write(root, 'Haike_video/templates/library-covers/local.jpg', b'private local cover')
            manifest(root)
        return old, new

    def build(self, folder, old, new):
        return package.build(old, new, folder / 'release' / 'haike-1.0.1.zip',
                             'https://example.test/releases/haike-1.0.1.zip',
                             '修复进度显示', '2026-10-28T00:00:00+00:00')

    def test_public_patch_metadata_hashes_and_install_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            old, new = self.stages(folder)
            # User records exist after initialization and do not belong to the stage manifest.
            sentinels = {'Haike_video/.env.local': b'fixture-private-config',
                         'creatorhub/data/accounts.sqlite3': b'fixture-accounts',
                         'Haike_video/.backlot/works/project.mp4': b'fixture-work'}
            for name, content in sentinels.items():
                write(old, name, content)
            result = self.build(folder, old, new)
            archive = Path(result['package'])
            with zipfile.ZipFile(archive) as content:
                self.assertEqual(set(content.namelist()),
                                 {'UPDATE-MANIFEST.json', 'payload/Haike_video/backlot/server.py'})
                plan = json.loads(content.read('UPDATE-MANIFEST.json'))
            self.assertEqual(plan['base_version'], '1.0.0')
            self.assertEqual(plan['source_commit'], 'b' * 40)
            self.assertEqual(len(plan['required_locks']), 2)
            self.assertTrue(plan['files'][0]['before_sha256'])
            feed = json.loads(Path(result['feed']).read_text(encoding='utf-8'))
            self.assertEqual(feed['version'], '1.0.1')
            self.assertEqual(feed['package']['sha256'], hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual(feed['package']['size'], archive.stat().st_size)
            self.assertEqual(feed['notes'], '修复进度显示')
            update = package.installer()
            bundle = folder / 'unpacked'
            update.extract_bundle(archive, bundle)
            receipt = update.apply_update(bundle, old, health_check=lambda *_: True)
            self.assertTrue(receipt['ok'])
            self.assertEqual(update.read_release(old)['version'], '1.0.1')
            for name, content in sentinels.items():
                self.assertEqual((old / name).read_bytes(), content)
            update.rollback(old, Path(receipt['backup']))
            self.assertEqual(update.read_release(old)['version'], '1.0.0')
            self.assertEqual((old / 'Haike_video/backlot/server.py').read_bytes(), b'# old program\n')

    def test_rejects_runtime_dependency_private_resource_or_schema_changes(self):
        for name in ('runtime/python/python.exe', 'Haike_video/requirements.txt',
                     'Haike_video/templates/library-covers/local.jpg',
                     'creatorhub/config.yaml', 'Haike_video/.env.local',
                     'creatorhub/app/main.py', 'copy_skill/copy_skill-main/src/example.py',
                     'api-platform/app/main.py'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                old, new = self.stages(folder)
                write(new, name, b'unapproved change')
                manifest(new)
                with self.assertRaises(ValueError):
                    self.build(folder, old, new)
                self.assertFalse((folder / 'release').exists())
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            old, new = self.stages(folder)
            release = package.read_json(new / 'RELEASE.json')
            release['data_schema'] = 2
            json_file(new, 'RELEASE.json', release)
            manifest(new)
            with self.assertRaisesRegex(ValueError, '数据结构'):
                self.build(folder, old, new)

    def test_corrupt_stage_or_missing_runtime_is_rejected_before_artifacts(self):
        for failure in ('corrupt', 'deleted'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                old, new = self.stages(folder)
                path = new / 'Haike_video/backlot/server.py'
                if failure == 'corrupt':
                    path.write_bytes(b'changed after audit')
                else:
                    path = new / 'runtime/python/python.exe'
                    path.unlink()
                    manifest(new)
                with self.assertRaises(ValueError):
                    self.build(folder, old, new)
                self.assertFalse((folder / 'release').exists())

    def test_content_hashed_frontend_rebuild_installs_and_retains_old_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            old, new = self.stages(folder)
            prefix = 'Haike_video/backlot/ui/avatar-generator/'
            old_files = {'assets/index-old123.js': b'console.log("old")',
                         'assets/index-old123.css': b'body{color:orange}',
                         'index.html': b'<script src="assets/index-old123.js"></script>'}
            new_files = {'assets/index-new456.js': b'console.log("new")',
                         'assets/index-new456.css': b'body{color:black}',
                         'index.html': b'<script src="assets/index-new456.js"></script>'}
            for root, files in ((old, old_files), (new, new_files)):
                for name, content in files.items():
                    write(root, prefix + name, content)
                manifest(root)
            result = self.build(folder, old, new)
            update = package.installer()
            bundle = folder / 'unpacked'
            update.extract_bundle(Path(result['package']), bundle)
            receipt = update.apply_update(bundle, old, health_check=lambda *_: True)
            self.assertTrue(receipt['ok'])
            entries = {item['path']: item for item in package.read_json(old / 'PACKAGE-MANIFEST.json')['files']}
            for name, content in new_files.items():
                self.assertEqual((old / (prefix + name)).read_bytes(), content)
                self.assertIn(prefix + name, entries)
            for name, content in old_files.items():
                if name != 'index.html':
                    self.assertEqual((old / (prefix + name)).read_bytes(), content)
                    self.assertIn(prefix + name, entries)
            update.rollback(old, Path(receipt['backup']))
            for name, content in old_files.items():
                self.assertEqual((old / (prefix + name)).read_bytes(), content)
            self.assertFalse((old / (prefix + 'assets/index-new456.js')).exists())
            self.assertFalse((old / (prefix + 'assets/index-new456.css')).exists())

    def test_rejects_unidentified_legacy_version_source_checkout_and_unsafe_url(self):
        for failure in ('legacy', 'source', 'url'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                old, new = self.stages(folder)
                if failure == 'legacy':
                    release = package.read_json(old / 'RELEASE.json')
                    release.pop('version')
                    json_file(old, 'RELEASE.json', release)
                    manifest(old)
                elif failure == 'source':
                    (old / '.git').mkdir()
                with self.assertRaises(ValueError):
                    if failure == 'url':
                        package.build(old, new, folder / 'release/app.zip', 'http://example.test/app.zip')
                    else:
                        self.build(folder, old, new)
                self.assertFalse((folder / 'release').exists())

    def test_existing_release_artifacts_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            old, new = self.stages(folder)
            existing = write(folder, 'release/haike-update.json', b'keep existing release')
            with self.assertRaisesRegex(ValueError, '输出已存在'):
                self.build(folder, old, new)
            self.assertEqual(existing.read_bytes(), b'keep existing release')
            self.assertFalse((folder / 'release/haike-1.0.1.zip').exists())


if __name__ == '__main__':
    unittest.main()
