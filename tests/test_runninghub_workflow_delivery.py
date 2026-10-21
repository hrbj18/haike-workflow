"""Public dual-workflow delivery and explicit preference changes, without cloud calls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


selection = load('workflow_selection', ROOT / 'scripts/runninghub-workflow.py')
kit = load('high_quality_delivery', ROOT / 'Haike_video/workflows/runninghub-high-quality/agent_cli.py')


class WorkflowDeliveryTests(unittest.TestCase):
    def test_default_is_economy_and_show_does_not_write(self):
        with tempfile.TemporaryDirectory() as folder:
            preference = Path(folder) / 'default.json'
            self.assertEqual(selection.selected(preference), 'economy')
            self.assertFalse(preference.exists())
            with self.assertRaises(ValueError):
                selection.select('high-quality', False, preference)
            self.assertFalse(preference.exists())
            selection.select('high-quality', True, preference)
            self.assertEqual(selection.selected(preference), 'high-quality')
            selection.select('economy', True, preference)
            self.assertEqual(selection.selected(preference), 'economy')

    def test_high_quality_uses_its_graph_without_changing_economy(self):
        with patch.dict('os.environ', {'RUNNINGHUB_API_KEY': 'synthetic-local-key',
                                       'RUNNINGHUB_WORKFLOW_ID': '2094449979141218305'}):
            self.assertEqual(kit.credentials(kit.config())[1], '2112180419025260546')
        self.assertEqual(selection.WORKFLOWS['economy']['workflow_id'], '2094449979141218305')
        self.assertEqual(kit.config()['voice']['id'], '')
        self.assertTrue(all(not r['image'] for r in kit.config()['ratios'].values()))
        kit.verify_package()

    def test_long_audio_keeps_exact_clock_and_45_second_segments(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / 'audio.wav'
            with wave.open(str(audio), 'wb') as out:
                out.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                out.writeframes(b'\0\0' * (46 * 24000 + 1))
            plan = kit.make_plan(audio, '4x5')
            self.assertEqual(plan['frames'], 1151)
            self.assertEqual(len(plan['segments']), 2)
            self.assertTrue(all(s['frames'] <= 1125 for s in plan['segments']))
            self.assertEqual(sum(s['frames'] for s in plan['segments']), plan['frames'])
            self.assertEqual(plan['segments'][-1]['end_sample'], 46 * 24000 + 1)
            for ratio in kit.config()['ratios']:
                local = kit.make_plan(audio, ratio)
                graph = kit.graph_for(local, local['segments'][0], 'input-image', 'input-audio')
                self.assertEqual(graph['36']['inputs']['image'], 'input-image')
                self.assertEqual(graph['14']['inputs']['colormatch'], 'disabled')

    def test_missing_private_inputs_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, '--audio'):
            kit.assets(SimpleNamespace(audio=None, image=None, ratio='4x5'))


if __name__ == '__main__':
    unittest.main()
