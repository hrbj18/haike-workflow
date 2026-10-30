"""Portable delivery boundaries, using only synthetic archives and local files."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('portable_package', ROOT / 'scripts/package-portable.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PortablePackageTests(unittest.TestCase):
    def test_disposable_composer_cache_is_not_an_offline_dependency(self):
        self.assertFalse(package.clean_runtime('Haike_video/remotion-composer/node_modules/.cache/webpack/renderer/0.pack'))
        self.assertTrue(package.clean_runtime('Haike_video/remotion-composer/node_modules/@remotion/cli/index.js'))
        self.assertTrue(package.clean_runtime('Haike_video/remotion-composer/node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell.exe'))

    def test_original_template_sounds_require_matching_provenance(self):
        relative = Path('Haike_video/templates/avatar-investment-a-v6-art-v5/assets/sound')
        with tempfile.TemporaryDirectory() as folder:
            source, delivery = Path(folder) / 'source', Path(folder) / 'delivery'
            sound = self.write(source, str(relative / 'dong.wav'), b'original synthetic fixture')
            catalog = {'external_samples': [], 'contains_user_portrait_or_voice': False,
                       'assets': [{'relative_path': 'dong.wav', 'sha256': package.sha256(sound)}]}
            self.write(delivery, str(relative / 'PROVENANCE.json'), json.dumps(catalog).encode())
            with patch.object(package, 'ROOT', source):
                self.assertEqual(package.copy_template_sounds(delivery), 1)
                self.assertEqual((delivery / relative / 'dong.wav').read_bytes(), sound.read_bytes())
                sound.write_bytes(b'changed media')
                with self.assertRaisesRegex(ValueError, 'mismatched'):
                    package.copy_template_sounds(delivery)

    def write(self, root, name, content=b'synthetic fixture'):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def make_stage(self, root):
        self.write(root, 'RELEASE.json', b'{"source_commit":"fixture-committed-revision"}')
        self.write(root, 'docs/API_KEY_SETUP.md', '配置自己的 Key。\n'.encode('utf-8'))
        self.write(root, 'Haike_video/backlot/example.py', b'VALUE = "committed"\n')
        package.manifest(root)

    def test_legacy_archive_only_contributes_selected_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'legacy.zip'
            prefix = 'Legacy/'
            approved = {'runtime/python/python.exe', 'runtime/node/node.exe',
                        'runtime/ffmpeg/ffmpeg.exe',
                        'Haike_video/remotion-composer/node_modules/react/index.js'}
            rejected = {'Haike_video/backlot/studio.py', 'creatorhub/app/main.py',
                        'creatorhub/config.yaml', 'creatorhub/data/creatorhub.db',
                        'Haike_video/.env.secrets.local', 'Haike_video/.backlot/client-config.json',
                        'runtime/not-approved/tool.exe', 'runtime/browser/Default/Cookies',
                        'runtime/browser/cookies.txt', 'runtime/browser/storage_state.json',
                        'runtime/browser/Profiles/account/profile.json',
                        'runtime/python/account.sqlite3'}
            with zipfile.ZipFile(archive, 'w') as handle:
                for name in approved | rejected:
                    handle.writestr(prefix + name, b'synthetic legacy content')
            destination = root / 'stage'
            package.extract_archive(archive, destination, package.clean_runtime, prefix)
            actual = {path.relative_to(destination).as_posix()
                      for path in destination.rglob('*') if path.is_file()}
            self.assertEqual(actual, approved)

    def test_archive_path_traversal_is_rejected_without_writing_outside(self):
        attacks = ('runtime/python/../../../../escaped.txt', '/escaped.txt',
                   'C:/escaped.txt', 'runtime\\python\\escaped.txt')
        for name in attacks:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = root / 'legacy.zip'
                raw_name = 'Legacy/' + name
                with zipfile.ZipFile(archive, 'w') as handle:
                    # ZipInfo normalizes Windows separators in its constructor.
                    # Assign afterward so the archive really contains the attack.
                    entry = zipfile.ZipInfo('fixture')
                    entry.filename = raw_name
                    handle.writestr(entry, b'not written')
                self.assertIn(raw_name.encode('ascii'), archive.read_bytes())
                with self.assertRaises(ValueError):
                    package.extract_archive(archive, root / 'stage', package.clean_runtime, 'Legacy/')
                self.assertFalse((root / 'escaped.txt').exists())

    def test_selected_archive_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'legacy.zip'
            entry = zipfile.ZipInfo('Legacy/runtime/python/linked.txt')
            entry.create_system = 3
            entry.external_attr = 0o120777 << 16
            with zipfile.ZipFile(archive, 'w') as handle:
                handle.writestr(entry, '../../outside.txt')
            with self.assertRaises(ValueError):
                package.extract_archive(archive, root / 'stage', package.clean_runtime, 'Legacy/')
            self.assertFalse((root / 'stage/runtime/python/linked.txt').exists())

    def test_environment_copy_relocates_editable_package_without_old_install_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, destination = root / 'source', root / 'stage'
            module = 'copy_skill/copy_skill-main'
            environment = source / module / '.venv'
            for name in ('Scripts/python.exe', 'Scripts/pythonw.exe', 'Scripts/activate.ps1',
                         'Lib/site-packages/example/__init__.py',
                         'Lib/site-packages/example/__pycache__/private.pyc',
                         'Lib/site-packages/example.dist-info/direct_url.json'):
                self.write(environment, name)
            editable = 'Lib/site-packages/__editable__.douyin_content_intelligence-0.1.0.pth'
            self.write(environment, editable, b'C:/old-install/copy_skill/src\n')
            with patch.object(package.subprocess, 'check_output',
                              return_value='{"python":"3.12 fixture","packages":[]}'):
                result = package.copy_environment(source, destination, module)
            target = destination / module / '.venv'
            self.assertEqual((target / editable).read_text(encoding='utf-8'), '../../../src\n')
            self.assertTrue((target / 'Lib/site-packages/example/__init__.py').is_file())
            self.assertFalse((target / 'Scripts/activate.ps1').exists())
            self.assertFalse((target / 'Lib/site-packages/example/__pycache__').exists())
            self.assertFalse((target / 'Lib/site-packages/example.dist-info/direct_url.json').exists())
            self.assertIn('RUNTIME_PREPARE_REQUIRED', (target / 'pyvenv.cfg').read_text(encoding='utf-8'))
            self.assertEqual(result['module'], module)

    def test_environment_rejects_unreviewed_absolute_import_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            environment = source / 'Haike_video/.venv'
            for name in ('Scripts/python.exe', 'Scripts/pythonw.exe'):
                self.write(environment, name)
            self.write(environment, 'Lib/site-packages/unreviewed.pth', b'C:/other-install/private-src\n')
            with patch.object(package.subprocess, 'check_output') as probe:
                with self.assertRaises(ValueError):
                    package.copy_environment(source, root / 'stage', 'Haike_video')
                probe.assert_not_called()

    def test_delivery_rejects_credentials_state_and_private_presenters(self):
        names = ('cookies.txt', 'runtime/browser/Default/Cookies',
                 'runtime/browser/storage_state.json', 'runtime/browser/Profiles/account/state.json',
                 'creatorhub/config.yaml', 'creatorhub/data/creatorhub.sqlite3',
                 'Haike_video/.backlot/haike-api/client-config.json',
                 'Haike_video/.env.secrets.local',
                 'copy_skill/copy_skill-main/config/content_intelligence.local.json',
                 'prototypes/haike-avatar-generator/public/assets/presenter.png',
                 'Haike_video/backlot/ui/avatar-generator/assets/n1-sample.mp4')
        for name in names:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.write(root, name)
                with self.assertRaises(ValueError):
                    package.clean_delivery(root)

    def test_delivery_allows_public_templates_and_dependency_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('README.md', 'Haike_video/.env.example', 'creatorhub/config.example.yaml',
                         'Haike_video/backlot/ui/avatar-generator/assets/n1-public-presenter.png',
                         'runtime/models/whisper/config.json',
                         'Haike_video/remotion-composer/node_modules/react/package.json'):
                self.write(root, name)
            package.clean_delivery(root)

    def test_delivery_rejects_a_file_link_to_outside_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = self.write(root, 'outside.txt', b'private outside fixture')
            stage = root / 'stage'
            stage.mkdir()
            link = stage / 'innocent.txt'
            try:
                link.symlink_to(outside)
            except OSError as error:
                self.skipTest('File symlinks unavailable: ' + str(error.winerror))
            with self.assertRaises(ValueError):
                package.clean_delivery(stage)

    def test_manifest_hashes_bytes_and_marks_only_relocation_inputs_mutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contents = {
                'Haike_video/backlot/example.py': b'print("synthetic")\n',
                'Haike_video/.venv/pyvenv.cfg': b'home = RUNTIME_PREPARE_REQUIRED\n',
                'copy_skill/copy_skill-main/.venv/Lib/site-packages/__editable__.douyin_content_intelligence-0.1.0.pth': b'../../../src\n',
                'Haike_video/.venv/Lib/site-packages/package-init.pth': b'import fixture_module\n',
                'runtime/python/Lib/fixture.pth': b'library\n',
                'runtime/models/config.json': '{"语言":"中文"}\n'.encode('utf-8'),
            }
            for name, content in contents.items():
                self.write(root, name, content)
            package.manifest(root)
            manifest = json.loads((root / 'PACKAGE-MANIFEST.json').read_text(encoding='utf-8'))
            entries = {item['path']: item for item in manifest['files']}
            self.assertEqual(set(entries), set(contents))
            for name, content in contents.items():
                self.assertEqual(entries[name]['size'], len(content), name)
                self.assertEqual(entries[name]['sha256'], hashlib.sha256(content).hexdigest(), name)
            self.assertEqual({name for name, item in entries.items() if item['mutable']}, {
                'Haike_video/.venv/pyvenv.cfg',
                'copy_skill/copy_skill-main/.venv/Lib/site-packages/__editable__.douyin_content_intelligence-0.1.0.pth',
            })

    def test_manifest_covers_nested_file_with_manifest_basename(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            name = 'runtime/models/PACKAGE-MANIFEST.json'
            self.write(root, name, b'{"synthetic":"dependency metadata"}')
            package.manifest(root)
            data = json.loads((root / 'PACKAGE-MANIFEST.json').read_text(encoding='utf-8'))
            self.assertEqual([entry['path'] for entry in data['files']], [name])

    def test_dirty_source_is_rejected_before_export_or_dependency_copy(self):
        for status in (b' M scripts/example.py\n', b'?? new-source.py\n', b'M  README.md\n'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                stage = Path(temporary) / 'new-stage'
                args = SimpleNamespace(stage=stage, runtime_archive=Path(temporary) / 'unused.zip',
                                       include_crawler=False)
                with patch.object(package, 'git', return_value=status), \
                     patch.object(package.subprocess, 'run') as process, \
                     patch.object(package, 'extract_archive') as extract, \
                     patch.object(package, 'copy_environment') as environment:
                    with self.assertRaisesRegex(ValueError, 'Commit source changes'):
                        package.stage(args)
                process.assert_not_called()
                extract.assert_not_called()
                environment.assert_not_called()
                self.assertFalse(stage.exists())

    def test_source_stage_must_be_a_new_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            sentinel = self.write(stage, 'user-file.txt', b'keep existing data')
            with patch.object(package, 'git') as git:
                with self.assertRaises(ValueError):
                    package.stage(SimpleNamespace(stage=stage))
                git.assert_not_called()
            self.assertEqual(sentinel.read_bytes(), b'keep existing data')

    def test_archive_rejects_changed_missing_or_added_staged_content(self):
        for mutation in ('changed', 'missing', 'added'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                stage = root / 'stage'
                self.make_stage(stage)
                source = stage / 'Haike_video/backlot/example.py'
                if mutation == 'changed':
                    source.write_bytes(b'VALUE = "uncommitted alteration"\n')
                elif mutation == 'missing':
                    source.unlink()
                else:
                    self.write(stage, 'Haike_video/backlot/uncommitted.py', b'UNCOMMITTED = True\n')
                with self.assertRaises(ValueError):
                    package.archive(SimpleNamespace(stage=stage, destination=root / 'delivery'))
                self.assertFalse((root / 'delivery/Haike_videoflow.zip').exists())

    def test_archive_preserves_manifest_hashes_and_writes_separate_setup_document(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / 'stage'
            self.make_stage(stage)
            before = (stage / 'PACKAGE-MANIFEST.json').read_bytes()
            output = root / 'delivery'
            package.archive(SimpleNamespace(stage=stage, destination=output))
            archive = output / 'Haike_videoflow.zip'
            with zipfile.ZipFile(archive) as handle:
                manifest = json.loads(handle.read('Haike_videoflow/PACKAGE-MANIFEST.json'))
                for entry in manifest['files']:
                    content = handle.read('Haike_videoflow/' + entry['path'])
                    self.assertEqual(entry['size'], len(content))
                    self.assertEqual(entry['sha256'], hashlib.sha256(content).hexdigest())
                self.assertEqual(handle.read('Haike_videoflow/PACKAGE-MANIFEST.json'), before)
            document = (output / 'API_Key配置说明.md').read_text(encoding='utf-8-sig')
            self.assertIn('配置自己的 Key。', document)
            self.assertIn(hashlib.sha256(archive.read_bytes()).hexdigest(), document)
            self.assertIn('fixture-committed-revision', document)

    def test_archive_refuses_to_overwrite_a_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / 'stage'
            self.make_stage(stage)
            output = root / 'delivery'
            sentinel = self.write(output, 'Haike_videoflow.zip', b'existing user delivery')
            with self.assertRaises(ValueError):
                package.archive(SimpleNamespace(stage=stage, destination=output))
            self.assertEqual(sentinel.read_bytes(), b'existing user delivery')

    def test_private_multi_key_document_is_only_written_beside_zip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / 'stage'
            self.make_stage(stage)
            payload = {'schema_version': 1, 'providers': {
                'bailian': {'api_key': 'synthetic-bailian-credential'},
                'pexels': {'api_key': 'synthetic-pexels-credential'}}}
            document = self.write(root, 'private.md', ('```haike-config\n' + json.dumps(payload) + '\n```\n').encode())
            output = root / 'delivery'
            package.archive(SimpleNamespace(stage=stage, destination=output, config_document=document))
            delivered = (output / 'API_Key配置说明.md').read_text(encoding='utf-8-sig')
            self.assertIn('synthetic-bailian-credential', delivered)
            self.assertIn('synthetic-pexels-credential', delivered)
            with zipfile.ZipFile(output / 'Haike_videoflow.zip') as handle:
                for name in handle.namelist():
                    content = handle.read(name)
                    self.assertNotIn(b'synthetic-bailian-credential', content)
                    self.assertNotIn(b'synthetic-pexels-credential', content)

    def test_private_document_inside_stage_is_rejected_before_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / 'stage'
            self.make_stage(stage)
            document = self.write(stage, 'private.md', b'```haike-config\n{"schema_version":1}\n```')
            package.manifest(stage)
            output = root / 'delivery'
            with self.assertRaisesRegex(ValueError, 'outside'):
                package.archive(SimpleNamespace(stage=stage, destination=output, config_document=document))
            self.assertFalse((output / 'Haike_videoflow.zip').exists())


if __name__ == '__main__':
    unittest.main()
