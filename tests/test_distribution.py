import importlib.util
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
sys.path.insert(0, str(ROOT / 'copy_skill/copy_skill-main/src'))
from douyin_intelligence import config

class DistributionTests(unittest.TestCase):
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
