import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

check = load('distribution_check', 'scripts/check.py')
configure = load('distribution_configure', 'scripts/configure.py')
studio_build = load('distribution_studio_build', 'scripts/build-studio.py')
sys.path.insert(0, str(ROOT / 'copy_skill/copy_skill-main/src'))
from douyin_intelligence import config

class DistributionTests(unittest.TestCase):
    def test_public_demo_exception_requires_exact_path_and_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            name = next(iter(check.PUBLIC_MEDIA_SHA256))
            demo = root / name
            demo.parent.mkdir(parents=True)
            content = b'synthetic public geometry fixture'
            demo.write_bytes(content)
            with patch.dict(check.PUBLIC_MEDIA_SHA256, {name: hashlib.sha256(content).hexdigest()}, clear=True):
                self.assertEqual(check.check_paths(root, [name]), [])
                demo.write_bytes(content + b'changed')
                self.assertTrue(any('hash mismatch' in item for item in check.check_paths(root, [name])))
                other = demo.with_name('private-sample.mp4')
                other.write_bytes(content)
                self.assertTrue(any('Private/generated' in item for item in check.check_paths(root, [other.relative_to(root).as_posix()])))

    def test_retired_previews_cleanup_is_exact_and_stays_in_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / 'embedded'
            assets = destination / 'assets'
            assets.mkdir(parents=True)
            for name in studio_build.PRIVATE_PREVIEWS:
                (assets / name).write_bytes(b'private test fixture')
            retained = assets / 'n1-presenter.svg'
            retained.write_text('<svg/>', encoding='utf-8')
            with patch.object(studio_build, 'ROOT', root):
                studio_build.remove_private_previews(destination)
                studio_build.remove_private_previews(destination)
                with self.assertRaises(ValueError):
                    studio_build.remove_private_previews(root.parent / 'outside-checkout')
            self.assertTrue(retained.is_file())
            self.assertFalse(any((assets / name).exists() for name in studio_build.PRIVATE_PREVIEWS))

    def test_build_rejects_private_portrait_before_running_toolchain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            portrait = root / 'prototypes/haike-avatar-generator/public/assets/presenter.png'
            portrait.parent.mkdir(parents=True)
            portrait.write_bytes(b'private portrait fixture')
            with patch.object(studio_build, 'ROOT', root), patch.object(studio_build.subprocess, 'run') as run:
                with self.assertRaisesRegex(SystemExit, 'Private preview found'):
                    studio_build.main()
                run.assert_not_called()
            self.assertEqual(portrait.read_bytes(), b'private portrait fixture')

    def test_retired_previews_cleanup_rejects_directories_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / 'embedded' / 'assets'
            assets.mkdir(parents=True)
            target = assets / studio_build.PRIVATE_PREVIEWS[0]
            target.mkdir()
            with patch.object(studio_build, 'ROOT', root):
                with self.assertRaises(ValueError):
                    studio_build.remove_private_previews(assets.parent)
            target.rmdir()
            retained = root / 'retained.txt'
            retained.write_text('keep', encoding='utf-8')
            try:
                target.symlink_to(retained)
            except OSError as error:
                self.skipTest(f'Symlink creation unavailable: {error.winerror}')
            with patch.object(studio_build, 'ROOT', root):
                with self.assertRaises(ValueError):
                    studio_build.remove_private_previews(assets.parent)
            self.assertEqual(retained.read_text(encoding='utf-8'), 'keep')

    def test_credentials_and_git_state_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ['.env.local','creatorhub/config.yaml','x/.git/config','cookies.txt','clip.mp4']:
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('example', encoding='utf-8')
                self.assertTrue(check.check_paths(root, [name]), name)

    def test_initialization_preserves_existing_user_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ['Haike_video/.env.example','creatorhub/config.example.yaml']:
                file=root/name; file.parent.mkdir(parents=True, exist_ok=True); file.write_text('example')
            (root/'copy_skill/copy_skill-main/config').mkdir(parents=True)
            configure.configure(root)
            original = root/'Haike_video/.env.local'
            original.write_text('user-owned-setting')
            override=root/'copy_skill/copy_skill-main/config/content_intelligence.local.json'
            override.write_text('{"user_owned": true}')
            configure.configure(root)
            self.assertEqual(original.read_text(), 'user-owned-setting')
            self.assertEqual(json.loads(override.read_text()), {'user_owned':True})

    def test_default_override_and_explicit_config_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'config').mkdir()
            shipped=ROOT/'copy_skill/copy_skill-main/config/content_intelligence.json'
            base=root/'config/content_intelligence.json'; base.write_bytes(shipped.read_bytes())
            override=base.with_name('content_intelligence.local.json')
            override.write_text('{"media_tools":{"ffmpeg":"local-ffmpeg"}}')
            with patch.object(config, 'project_root', return_value=root):
                merged=config.load_config()
                self.assertEqual(merged['media_tools']['ffmpeg'],'local-ffmpeg')
                self.assertIn('ffprobe', merged['media_tools'])
                self.assertNotEqual(config.load_config(base)['media_tools']['ffmpeg'],'local-ffmpeg')
                override.write_text('[]')
                with self.assertRaises(config.ConfigurationError): config.load_config()

    def test_source_check_succeeds(self):
        result=subprocess.run([sys.executable, str(ROOT/'scripts/check.py')], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__ == '__main__': unittest.main()
