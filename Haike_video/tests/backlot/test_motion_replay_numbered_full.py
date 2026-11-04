"""New full-production gates. Synthetic media probes never claim video acceptance."""
import hashlib,json,tempfile,unittest,wave
from pathlib import Path
from unittest.mock import patch
from backlot import motion_replay
from backlot import motion_replay_numbered_02_05_full as adapter
from backlot import motion_replay_numbered_02_05_production as producer


class FullNumberedTests(unittest.TestCase):
    def test_new_registry_precise_versions_real_bindings_and_unmodified_old_identity(self):
        document=producer.read(producer.ROOT/'Haike_video/config/motion-replay/numbered-02-05-production.json')
        motion_replay.validate_registry(document)
        self.assertEqual([(r['template_id'],r['version'],len(r['actions'])) for r in document['templates']],[(name,'2.0.0',len(spec[3])) for name,spec in producer.SPECS.items()])
        for row in document['templates']:motion_replay.verify_sources(row)
        old=motion_replay.resolve('kinetic-field-v1','1.0.0')
        self.assertEqual(old['renderer']['adapter'],'backlot.motion_replay_numbered_02_05:prepare')

    def test_incomplete_actions_and_unknown_fields_stop_before_media_or_queue(self):
        t=motion_replay.resolve('field-notes-v1','2.0.0');ids=producer.actions('field-notes-v1')
        with patch.object(producer,'validate',side_effect=AssertionError('must not read media')):
            for values in [ids[:-1],ids[::-1],[],['unknown']]:
                with self.assertRaisesRegex(ValueError,'动作子集'):adapter.prepare(t,{'action_ids':values},workspace=producer.ROOT)
            with self.assertRaisesRegex(ValueError,'仅接受'):adapter.prepare(t,{'run':'anything'},workspace=producer.ROOT)
            self.assertEqual(adapter.prepare(t,{},workspace=producer.ROOT)['status'],'blocked')

    def test_paid_phase_cannot_be_admitted_by_local_reuse_producer(self):
        with self.assertRaisesRegex(ValueError,'不执行付费'):producer.admit(producer.ROOT,producer.ROOT/'.local/fixture',phase='avatar')

    def test_source_change_stops_before_renderer(self):
        relative=Path(producer.__file__).resolve().relative_to(producer.ROOT).as_posix()
        request={'contract':producer.CONTRACT,'template_id':'field-notes-v1','template_version':'2.0.0','action_ids':producer.actions('field-notes-v1'),
            'source_identity':{relative:'0'*64},'data':'unused'}
        with patch.object(producer.subprocess,'run',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(ValueError,'源码变化'):producer.run(None,{'frozen_request':request})

    def fixture(self,data):
        public=data/'public';public.mkdir()
        for name in ['font.ttf','video.mp4','presenter.mp4']:(public/name).write_bytes(name.encode())
        for name in ['voice.wav','asr.json','avatar.mp4','ledger.json']:(data/name).write_bytes(name.encode())
        text='完整原稿。';digest=hashlib.sha256(text.encode()).hexdigest();captions=[{'text':text,'startMs':0,'endMs':16000}]
        producer.write(data/'audio.json',{'sha256':producer.sha(data/'voice.wav'),'time_stretched':False,'full_text_sha256':digest})
        producer.write(data/'timing.json',{'source_audio_sha256':producer.sha(data/'voice.wav'),'script_sha256':digest,'captions':captions,'asr_sha256':producer.sha(data/'asr.json'),'complete_canonical_text_covered':True})
        producer.write(data/'avatar.json',{'workflow_id':'2112180419025260546','sha256':producer.sha(data/'avatar.mp4')})
        fields={'narration':'voice.wav','audio_receipt':'audio.json','asr':'asr.json','timing':'timing.json','avatar_receipt':'avatar.json','avatar_master':'avatar.mp4','original_payment_ledger':'ledger.json'}
        reuse={name:{'path':str(data/file),'sha256':producer.sha(data/file)} for name,file in fields.items()}
        reuse.update(new_paid_calls=0,presenter_clips=[{'sha256':producer.sha(public/'presenter.mp4'),'source_start_seconds':0,'duration_seconds':4.48}])
        producer.write(data/'reuse-source.json',reuse)
        producer.write(data/'materials.json',[{'path':str(public/'video.mp4'),'sha256':producer.sha(public/'video.mp4'),'prepared_file':'video.mp4','prepared_sha256':producer.sha(public/'video.mp4')}])
        with wave.open(str(public/'master.wav'),'wb') as stream:stream.setnchannels(2);stream.setsampwidth(2);stream.setframerate(48000);stream.writeframes(b'\0'*(16*48000*4))
        stages=[{'id':name,'from':i*120,'to':(i+1)*120,'text':{'label':'场景','note':'摘要'},'timing':{'mediaFrom':18,'noteFrom':66}} for i,name in enumerate(producer.FIELD_NAMES)]
        media={str(i):[{'file':'video.mp4','from':0,'to':480,'sourceStartFrame':0}] for i in range(5)}
        episode={'schema':'haike.numbered-full-motion-episode/1','template_id':'field-notes-v1','version':'2.0.0','fps':30,'durationFrames':480,'sourceText':text,'captions':captions,
            'stages':stages,'actions':{name:{'from':i*120+18,'to':i*120+84} for i,name in enumerate(producer.actions('field-notes-v1'))},'media':media,
            'presenters':[{'file':'presenter.mp4','from':0,'to':120,'sourceStartFrame':0}],
            'content':{'segments':stages,'stages':stages,'durationInFrames':480,'photos':list(media)}}
        def save():
            producer.write(public/'episode.json',episode)
            producer.write(data/'preparation.json',{'schema':'haike.numbered-full-motion-preparation/1',
                'files':[{'path':p.name,'sha256':producer.sha(p)} for p in sorted(public.iterdir())],
                'evidence':[{'path':name,'sha256':producer.sha(data/name)} for name in ['reuse-source.json','materials.json']]})
        save();return episode,save

    def test_complete_input_and_actual_native_timing_consumption(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);episode,save=self.fixture(data)
            with patch.object(producer,'probe',return_value={'streams':[{'codec_type':'video','duration':'100','width':1080,'height':1920}],'format':{'duration':'100'}}):
                self.assertEqual(producer.validate(data)[0]['durationFrames'],480)
                episode['actions'][producer.actions('field-notes-v1')[1]]['to']-=1;save()
                with self.assertRaisesRegex(ValueError,'原动作历时'):producer.validate(data)

    def test_content_slot_cannot_replace_original_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);episode,save=self.fixture(data);episode['stages'][0]['text']['layout']='another';save()
            with self.assertRaisesRegex(ValueError,'原布局'):producer.validate(data)

    def test_missing_word_and_short_real_stream_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);episode,save=self.fixture(data);episode['sourceText']+='漏字';save()
            with self.assertRaisesRegex(ValueError,'逐字完整'):producer.validate(data)
            episode['sourceText']='完整原稿。';save()
            with patch.object(producer,'probe',return_value={'streams':[{'codec_type':'video','duration':'1','width':1080,'height':1920}],'format':{'duration':'1'}}):
                with self.assertRaisesRegex(ValueError,'源视频不足'):producer.validate(data)

    def test_event_receipt_reads_native_controls_and_ignores_caller_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            episode,_=self.fixture(Path(temp));episode['critical_internal_events']=[{'id':'fake-selected-effect','frame':1}]
            before={r['id']:r for r in producer.resolve_events(episode)}
            self.assertNotIn('fake-selected-effect',before)
            episode['stages'][1]['timing']['noteFrom']+=8
            after={r['id']:r for r in producer.resolve_events(episode)}
            self.assertEqual(after['compare.note.start']['frame'],before['compare.note.start']['frame']+8)
            self.assertEqual(after['arrive.note.start'],before['arrive.note.start'])

    def test_kinetic_cannot_stretch_all_original_motion_durations(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);episode,save=self.fixture(data)
            episode.update(template_id='kinetic-field-v1',fps=24)
            starts=[0,20,40,60,89,110,130,170,210,278,310,330,350,400,414,440,455]
            durations=[12,20,16,11,11,11,16,11,10,22,13,13,12,13,12,13,11]
            episode['actions']={name:{'from':a,'to':a+d} for name,a,d in zip(producer.actions('kinetic-field-v1'),starts,durations)}
            episode['stages']=[{'id':name,'from':a,'to':b} for name,a,b in [('duo',0,100),('hands',89,200),('collage',200,300),('location',278,400),('invitation',400,480)]]
            episode['actions'][producer.actions('kinetic-field-v1')[0]]['to']+=50;save()
            with self.assertRaisesRegex(ValueError,'物理历时'):producer.validate(data)


if __name__=='__main__':unittest.main()
