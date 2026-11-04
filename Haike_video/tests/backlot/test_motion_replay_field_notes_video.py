"""Meaningful negative gates; fake episodes never claim rendered acceptance."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import os

from backlot import motion_replay
from backlot import motion_replay_field_notes_render as render
from backlot import motion_replay_field_notes_video as production
from backlot import motion_replay_numbered_02_05 as adapter


class FieldNotesProductionTests(unittest.TestCase):
    def episode(self):
        scenes=[]
        for i,name in enumerate(('arrive','compare','connect','converge')):
            start=i*300;end=start+300
            event_names=list(sorted(render.EVENTS[i]))
            # Use causal order, independent from alphabetical order.
            causal=(['titleDemoteStart','titleDemoteEnd','mediaEnterStart','mediaEnterEnd','noteStart'],
                    ['focusStart','focusEnd','returnStart','returnEnd','noteStart'],
                    ['lineStart','lineEnd','mediaEnterStart','mediaEnterEnd','noteStart'],
                    ['pathStart','travelStart','travelEnd','conclusionStart','conclusionEnd','noteStart'])[i]
            scenes.append({'id':name,'actionId':render.ACTIONS[i],'from':start,'to':end,'headline':'本期标题','note':'摘要','kicker':'现场',
                'events':{n:start+10+j*15 for j,n in enumerate(causal)},
                'media':[[{'file':'real.mp4','from':start,'to':end,'sourceStartFrame':0}] for _ in range((1,4,1,4)[i])]})
        return {'template_id':'field-notes-v2','version':'2.1.0','fps':30,'durationFrames':1200,'brand':'海客','title':'测试','scenes':scenes,
            'captions':[{'text':'完整原稿。','startMs':0,'endMs':39900}],
            'presenters':[{'file':'presenter.mp4','from':0,'to':90,'sourceStartFrame':0}],
            'audio':'master.wav','font':'font.ttf','requiredOverlay':'AI体质检测：非医疗诊断。不看病不卖药，给您个参考。','address':'地址','sourceText':'完整原稿。'}

    def test_candidate_exact_version_uses_new_real_adapter_without_old_release(self):
        template=motion_replay.resolve('field-notes-v2','2.1.0')
        with patch.object(adapter,'verify_release',side_effect=AssertionError('old release not candidate')):
            value=adapter.prepare(template,{},workspace=production.ROOT)
        self.assertEqual(value['status'],'blocked')
        self.assertFalse(value['submitted'])
        self.assertEqual([a['id'] for a in template['actions']],render.ACTIONS)
        self.assertEqual(len(template['timeline']['events']),21)

    def test_complete_scene_and_caption_coverage_are_required(self):
        episode=self.episode();self.assertEqual(len(render.validate_episode(episode)),11)
        episode['sourceText']+='不能遗漏'
        with self.assertRaisesRegex(ValueError,'逐字完整'):render.validate_episode(episode)
        episode=self.episode();episode['scenes'][2]['from']+=1
        with self.assertRaisesRegex(ValueError,'连续覆盖'):render.validate_episode(episode)

    def test_event_causality_and_reading_budget_cannot_be_hidden_in_outer_scene(self):
        episode=self.episode();episode['scenes'][1]['events']['focusEnd']=episode['scenes'][1]['events']['focusStart']
        with self.assertRaisesRegex(ValueError,'因果'):render.validate_episode(episode)
        episode=self.episode();episode['scenes'][3]['events']['noteStart']=1180
        with self.assertRaisesRegex(ValueError,'36帧'):render.validate_episode(episode)

    def test_video_gaps_unknown_actions_and_missing_presenter_are_rejected(self):
        episode=self.episode();episode['scenes'][0]['media'][0][0]['to']-=1
        with self.assertRaisesRegex(ValueError,'连续覆盖'):render.validate_episode(episode)
        episode=self.episode();episode['scenes'][1]['actionId']='catalogue.unknown'
        with self.assertRaisesRegex(ValueError,'精确动作'):render.validate_episode(episode)
        episode=self.episode();episode['presenters']=[]
        with self.assertRaisesRegex(ValueError,'人物窗'):render.validate_episode(episode)

    def test_unfunded_and_negative_reservations_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)
            for entries,error in [([{'reserved_micros':11}],'超过'),([{'reserved_micros':-1}],'非负')]:
                production.write(data/'payment-ledger.json',{'limit_micros':10,'entries':entries})
                with self.assertRaisesRegex(ValueError,error):production._ledger(data)

    def test_source_changes_stop_before_any_paid_or_render_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);production.write(data/'input.json',{'text':'first'})
            request={'contract':production.CONTRACT,'template_id':production.TEMPLATE_ID,'template_version':production.VERSION,
                'action_ids':list(production.ACTION_IDS),'source_identity':{},'input_identity':{'input.json':'0'*64},'data':str(data),'phase':'avatar'}
            with patch.object(production,'_avatar',side_effect=AssertionError('must never dispatch')):
                with self.assertRaisesRegex(ValueError,'冻结输入变化'):production.run(None,{'frozen_request':request})

    def test_runtime_default_belongs_to_current_workspace_and_explicit_invalid_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);data=root/'private';data.mkdir()
            production.write(data/'production.json',{})
            node=root/'runtime/node/node.exe';browser=root/'runtime/browser/chrome-headless-shell.exe'
            for path in (node,browser):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture only')
            with patch.object(render,'ROOT',root),patch.dict(os.environ,{},clear=True),patch('lib.ffmpeg_locator.resolve_ffmpeg_pair',return_value=('fixture-ffmpeg','fixture-ffprobe')):
                resolved=render.runtime(data)
                self.assertEqual(Path(resolved['node']),node)
                self.assertEqual(Path(resolved['browser']),browser)
                production.write(data/'production.json',{'browser_executable':str(root/'missing.exe')})
                with self.assertRaisesRegex(ValueError,'明确指定'):render.runtime(data)


if __name__=='__main__':unittest.main()
