"""Platform selection preserves canonical bytes and never grants media approval."""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Haike_video'))
from backlot import motion_platform
from backlot import motion_replay


class NativeMotionTests(unittest.TestCase):
    def test_generated_adapter_matches_reviewable_derivation(self):
        subprocess.run([sys.executable, str(ROOT / 'scripts/build-native-motion.py'), '--check'], check=True)
        self.assertEqual(len(motion_platform.verify()['modules']), 19)

    def test_windows_keeps_original_modules_and_mac_selects_owned_derivation(self):
        original = 'backlot.motion_public_production_v2'
        with patch.object(motion_platform.sys, 'platform', 'win32'):
            self.assertEqual(motion_platform.owned_module(original).__name__, original)
        with patch.object(motion_platform.sys, 'platform', 'darwin'):
            self.assertEqual(motion_platform.owned_module(original).__name__, 'backlot.motion_native_public_production_v2')

    def test_native_derivation_does_not_change_any_preferred_source(self):
        rows = json.loads((ROOT / 'Haike_video/config/motion-preferred-production.json').read_text('utf8'))['templates']
        for row in rows:
            with self.subTest(template=row['template_id']):
                motion_replay.verify_sources(motion_replay.resolve(row['template_id'], row['version']))

    def test_missing_or_changed_native_source_is_rejected_before_import(self):
        with patch.object(motion_platform, '_sha', return_value='0' * 64):
            with self.assertRaisesRegex(ValueError, '实现改变'):
                motion_platform.verify()

    def test_restored_historical_paper_and_quote_sources_keep_their_exact_identity(self):
        for filename in ('imported-public-paper-v3-bound.json', 'imported-public-quote-v3-bound.json'):
            document = json.loads((motion_replay.REGISTRY_DIR / filename).read_text('utf8'))
            for template in document['templates']:
                with self.subTest(template=template['template_id'], version=template['version']):
                    motion_replay.verify_sources(template)

    def test_fixture_set_matches_all_preferred_styles_without_private_identity(self):
        fixtures = ROOT / 'Haike_video/tests/fixtures/native-motion'
        declared = json.loads((fixtures / 'manifest.json').read_text('utf8'))['templates']
        preferred = json.loads((ROOT / 'Haike_video/config/motion-preferred-production.json').read_text('utf8'))['templates']
        self.assertEqual({(r['template_id'], r['version']) for r in declared}, {(r['template_id'], r['version']) for r in preferred})
        for path in fixtures.glob('*.json'):
            content = path.read_text('utf8')
            for name in ('api_key', 'voice_id', 'task_id', 'EDY', 'C:\\\\', 'D:\\\\'):
                self.assertNotIn(name, content)


if __name__ == '__main__':
    unittest.main()
