"""Focused contract gates; synthetic files never claim media/visual acceptance."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backlot import motion_replay
from backlot import motion_replay_numbered_02_05 as adapter

ROOT=Path(__file__).resolve().parents[2]


class NumberedMotionReplayTests(unittest.TestCase):
    def setUp(self):
        self.document=json.loads((ROOT/'config/motion-replay/numbered-02-05.json').read_bytes())

    def template(self, identity):
        return deepcopy(next(t for t in self.document['templates'] if t['template_id']==identity))

    def test_registry_real_schema_and_references(self):
        motion_replay.validate_registry(self.document)
        self.assertEqual([len(t['actions']) for t in self.document['templates']],[17,13,4,4,4])

    def test_unknown_version_or_sources_cannot_enter_direct_adapter(self):
        t=self.template('kinetic-field-v1');t['version']='1.0.1'
        with self.assertRaisesRegex(ValueError,'版本'):
            adapter.verify_release(t,workspace=ROOT.parent)
        t=self.template('kinetic-field-v1');t['sources']=[]
        with self.assertRaisesRegex(ValueError,'来源合同'):
            adapter.verify_release(t,workspace=ROOT.parent)

    def test_action_subset_order_and_unknown_fields_are_rejected(self):
        t=self.template('field-notes-v2')
        with patch.object(adapter,'verify_release',return_value={'status':'pass'}):
            ids=[a['id'] for a in t['actions']]
            for requested in [ids[:1],ids[::-1],[],['talkcraft:source-converge']]:
                with self.subTest(requested=requested),self.assertRaisesRegex(ValueError,'动作顺序'):
                    adapter.prepare(t,{'action_ids':requested},workspace=ROOT.parent)
            with self.assertRaisesRegex(ValueError,'仅接受'):
                adapter.prepare(t,{'data':'x','semantic_events':{}},workspace=ROOT.parent)
            result=adapter.prepare(t,{'action_ids':ids},workspace=ROOT.parent)
            self.assertIsNone(result['props'])
            self.assertEqual(result['status'],'blocked')
            self.assertFalse(result['submitted'])

    def test_real_nana_cues_change_resolved_instants_not_other_scenes(self):
        t=self.template('nana-mint-explainer-v1')
        content={'scenes':[{'id':a['id'].rsplit('.',1)[-1],'start':i*20,'end':(i+1)*20,'cues':{}} for i,a in enumerate(t['actions'])]}
        before={e['id']:e for e in adapter.resolve_events(t,content)}
        content['scenes'][4]['cues']={'prompt':3.1,'steps':8.2,'preview':13.5}
        after={e['id']:e for e in adapter.resolve_events(t,content)}
        self.assertEqual(after['workflow.prompt']['resolved_frame'],2493)
        self.assertEqual(after['workflow.steps']['resolved_frame'],2646)
        self.assertEqual(after['workflow.preview']['resolved_frame'],2805)
        self.assertEqual(before['closing.comment-card'],after['closing.comment-card'])
        self.assertEqual(after['workflow.prompt']['anchor']['consumed_by'],'scene.cues.prompt')

    def test_field_notes_input_digest_clock_and_silence_gates(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);(data/'assets').mkdir()
            names=['presenter.mp4','font.ttf']+[f'photo-{i}.jpg' for i in range(7)]
            for name in names:(data/'assets'/name).write_bytes(name.encode())
            spans=[(0,180),(180,360),(360,540),(540,720)]
            episode={'schema':'haike.chromatic-avatar-episode/2','mode':'visual-preview','previewQuality':'low',
                'fps':30,'durationInFrames':720,'photos':['/assets/'+name for name in names[2:]],
                'presenterClips':[{'src':'/assets/presenter.mp4','from':0,'to':720}],
                'segments':[{'from':a,'to':b} for a,b in spans],
                'captions':[{'from':a,'to':b} for a,b in spans]}
            def save():
                (data/'episode.json').write_text(json.dumps(episode),encoding='utf-8')
                rows=[{'path':p.relative_to(data).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                      for p in [data/'episode.json',*(data/'assets').iterdir()]]
                (data/'preparation.json').write_text(json.dumps({'files':rows}),encoding='utf-8')
            save()
            with patch.object(adapter,'_duration',return_value=24):
                ready,_=adapter._field_notes(data,'field-notes-v1',ROOT.parent)
                self.assertEqual(ready['fontFamily'],'Haike Custom Field Notes')
                (data/'assets/photo-0.jpg').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'身份变化'):
                    adapter._field_notes(data,'field-notes-v1',ROOT.parent)
                save();episode['mode']='narrated-preview';save()
                with self.assertRaisesRegex(ValueError,'静音'):
                    adapter._field_notes(data,'field-notes-v1',ROOT.parent)
                episode['mode']='visual-preview';episode['segments'][0]['to']=181;save()
                with self.assertRaisesRegex(ValueError,'固定四场'):
                    adapter._field_notes(data,'field-notes-v1',ROOT.parent)


if __name__=='__main__':
    unittest.main()
