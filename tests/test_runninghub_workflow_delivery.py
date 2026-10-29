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

    def test_conditional_default_uses_full_video_clock_and_preserves_long_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'default.json'
            selection.select('high-quality', True, path, max_video_seconds=120)
            self.assertEqual(selection.selected(path, duration_seconds=45), 'high-quality')
            self.assertEqual(selection.selected(path, duration_seconds=120), 'high-quality')
            self.assertEqual(selection.selected(path, duration_seconds=120.001), 'economy')
            self.assertEqual(selection.selected(path), 'economy')
            self.assertEqual(selection.preference(path)['duration_rule']['max_video_seconds'], 120)
            for invalid in (True, 0, -1, float('nan'), float('inf')):
                with self.assertRaises(ValueError):
                    selection.selected(path, duration_seconds=invalid)
            selection.select('economy', True, path)
            self.assertNotIn('duration_rule', selection.preference(path))

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

    def test_coin_workflow_rejects_shared_key_before_upload_or_submit(self):
        with patch.object(kit, 'account', return_value={'apiType':'SHARED','remainCoins':'9999'}):
            with self.assertRaisesRegex(RuntimeError, 'NORMAL'):
                kit.consumer_account('synthetic-key')
        with patch.object(kit, 'account', return_value={'apiType':'NORMAL','remainCoins':'9999'}):
            self.assertEqual(kit.consumer_account('synthetic-key')['apiType'], 'NORMAL')

    def test_provider_rejection_retains_response_without_secret(self):
        from unittest.mock import Mock
        response=Mock(status_code=200)
        response.json.return_value={'code':605,'msg':'NOT_ENOUGH_BALANCE','apiKey':'synthetic-private-key'}
        kit.SECRETS.add('synthetic-private-key')
        with patch('requests.request', return_value=response):
            with self.assertRaises(kit.ProviderReplyError) as caught:
                kit.request('POST','/task/openapi/create','synthetic-private-key',{})
        self.assertEqual(caught.exception.code,605)
        self.assertNotIn('synthetic-private-key',json.dumps(caught.exception.response))

    def test_actual_run_stops_shared_route_before_reading_or_uploading_inputs(self):
        with patch.object(kit,'credentials',return_value=('synthetic-key','2112180419025260546')), \
             patch.object(kit,'account',return_value={'apiType':'SHARED','remainCoins':'9999'}), \
             patch.object(kit,'assets',side_effect=AssertionError('inputs must not be touched')), \
             patch.object(kit,'upload',side_effect=AssertionError('upload must not be called')):
            with self.assertRaisesRegex(RuntimeError,'NORMAL'):
                kit.run(SimpleNamespace(),('ffmpeg','ffprobe'))

    def test_alternate_cdn_requires_same_node_and_storage_path(self):
        result={'nodeId':'93','url':'https://origin.example/user/output.mp4'}
        rows=[{'nodeId':'93','fileUrl':'https://cdn.example/user/output.mp4'}]
        self.assertEqual(kit.matching_artifact_url(result,rows),rows[0]['fileUrl'])
        for wrong in ({'nodeId':'92','fileUrl':rows[0]['fileUrl']},
                      {'nodeId':'93','fileUrl':'https://cdn.example/user/other.mp4'},
                      {'nodeId':'93','fileUrl':'http://cdn.example/user/output.mp4'}):
            self.assertEqual(kit.matching_artifact_url(result,[wrong]),result['url'])

    def test_download_recovery_queries_same_task_without_generating(self):
        with tempfile.TemporaryDirectory() as folder:
            case=Path(folder)
            target=case/'video.mp4'
            result={'nodeId':'93','url':'https://origin.example/output.mp4'}
            reply={'code':0,'data':[{'nodeId':'93','fileUrl':'https://cdn.example/output.mp4'}]}
            def fetched(url,path):path.write_bytes(b'original-artifact')
            with patch.object(kit,'request',return_value=reply) as request, \
                 patch.object(kit.shutil,'which',return_value=None), \
                 patch.object(kit,'download',side_effect=fetched):
                kit.download_existing_artifact(result,target,'synthetic-key','existing-task',case)
                request.assert_called_once_with('POST','/task/openapi/outputs','synthetic-key',
                    {'apiKey':'synthetic-key','taskId':'existing-task'})
            self.assertEqual(target.read_bytes(),b'original-artifact')
            self.assertTrue(kit.read(case/'video.mp4.download.json')['alternate_cdn'])


if __name__ == '__main__':
    unittest.main()
