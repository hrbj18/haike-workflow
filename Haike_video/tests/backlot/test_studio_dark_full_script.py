"""Contract and crash recovery: fake providers, real durable files and PCM."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from backlot.studio_dark_full_script import Budget, ScriptFacade, measured_captions, read
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError,sha


def wav(path):
    with wave.open(str(path),'wb') as out:
        out.setparams((1,2,24000,0,'NONE','not compressed'));out.writeframes(b'\1\0'*72000)


class Center:
    def __init__(self,path):
        self.account='account-a';self.path=path;wav(path)
        self.submits=0;self.quotes=0;self.polls=0;self.ready=True;self.available=True;self.result='succeeded'
    def voices(self):
        return {'preferences':{'voice_id':'selected'},'items':[dict(id='selected',name='已配置音色',model='haike/internal-tts',model_id='existing-model',provider='bailian',available=self.available,preferences={'speech_rate':1.15})]}
    def quote(self,payload):
        self.quotes+=1
        return {'id':'iq_test','operation_id':'call_'+'1'*32,'max_charge_micros':'10000','model':payload['model']}
    def submit(self,data):
        self.submits+=1;return {'status':self.result,'accepted':True,'result':None}
    def job(self,op):
        self.polls+=1;return {'status':self.result,'accepted':True,'result':None}
    def operation(self,op):
        return {'status':'succeeded','request':{'kind':'tts','text':'你好。'}}
    def preview(self,op):return self.path


class SDK:
    def __init__(self):self.confirms=0;self.resumes=0
    def prepare_asr_audio(self,path):return {'id':'existing-upload'}
    def quote(self,model,data,ref):return {'id':'asr-quote','model':model,'max_charge_micros':'1000'}
    def confirm(self,q,maximum,op):self.confirms+=1;return op
    def resume(self,op):
        self.resumes+=1
        return {'status':'succeeded','result':{'segments':[{'start':0,'end':.8,'text':'你好。','words':[{'text':'你好。','start':.1,'end':.8}]}]}}


@pytest.fixture
def setup(tmp_path):
    center=Center(tmp_path/'provider.wav');sdk=SDK();menu=[]
    request={'title':'测试','script':'你好。','recipe':{'title':'测试','props':{'variant':'cobalt','media':[],'fontAssets':{}},'sources':{},'audio':{'voice':'voice.wav','sfx':[]},'provenance':{}}}
    def create(request_arg=None):
        return ScriptFacade(SimpleNamespace(),tmp_path/'project',request_arg,center=center,sdk=sdk,
                            menu=lambda:menu.append('menu') or {'capabilities':[]},
                            asr_status=lambda:{'ready':True},asr_snapshot=lambda:{'provider':'bailian','model':'haike/bailian-asr'},
                            preflight=lambda v:{'props':{'durationFrames':90,'fps':30}})
    return tmp_path,center,sdk,menu,request,create


def test_missing_service_yields_chinese_needs_voice(setup):
    _,c,_,menu,r,create=setup;c.available=False
    f=create(r);state=f.inspect()
    assert menu==['menu'] and state['status']=='needs_voice' and '配音' in state['message']
    with pytest.raises(WorkError,match='needs_voice'):f.quote('tts')
    assert c.submits==0


def test_quote_check_never_submit_and_preconfirm_resume_rejected(setup):
    _,c,_,_,r,create=setup
    f=create(r);f.inspect();q=f.quote('tts');assert q['status']=='quoted' and c.submits==0
    with pytest.raises(WorkError,match='尚未确认'):create().resume('tts')
    assert c.submits==0


def test_unknown_submission_resume_same_operation_no_second_submit(setup):
    path,c,_,_,r,create=setup;c.result='submission_unknown'
    f=create(r);f.quote('tts');state=f.confirm('tts',500000,path/'budget.json',confirmed=True)
    assert state['stages']['tts']['status']=='submission_unknown' and c.submits==1
    create().confirm('tts',500000,path/'budget.json',confirmed=True)
    assert c.submits==1 and c.quotes==1 and c.polls==1
    assert read(path/'budget.json')['reserved_micros']==500000


def test_quote_over_cap_or_scope_change_never_calls_provider(setup):
    path,c,_,_,r,create=setup;f=create(r);f.quote('tts')
    with pytest.raises(WorkError,match='报价超过'):f.confirm('tts',100,path/'budget.json',confirmed=True)
    c.account='different'
    with pytest.raises(WorkError,match='账号已改变'):f.confirm('tts',500000,path/'budget.json',confirmed=True)
    assert c.submits==0


def test_restarted_tts_asr_export_and_duplicate_confirm_are_idempotent(setup):
    path,c,sdk,_,r,create=setup;f=create(r);f.quote('tts')
    state=f.confirm('tts',500000,path/'budget.json',confirmed=True)
    assert state['status']=='needs_alignment'
    create().resume('tts');assert c.submits==1
    a=create();a.quote('asr');a.confirm('asr',100000,path/'budget.json',confirmed=True)
    result=create().export();value=read(result['input'])
    assert value['props']['captions']==[{'text':'你好。','startMs':100.,'endMs':800.}]
    assert result['cloud_render_submitted'] is False and sdk.confirms==1
    create().confirm('asr',100000,path/'budget.json',confirmed=True)
    assert sdk.confirms==1 and c.submits==1


def test_stale_facade_reloads_quote_and_does_not_requote(setup):
    _,c,_,_,r,create=setup;a=create(r);b=create()
    a.quote('tts');b.quote('tts');assert c.quotes==1


def test_request_mutation_rejected_and_existing_pcm_change_rejected(setup):
    path,c,_,_,r,create=setup;f=create(r);changed=deepcopy(r);changed['script']='别的内容'
    with pytest.raises(WorkError,match='已改变'):create(changed)
    f.quote('tts');f.confirm('tts',500000,path/'budget.json',confirmed=True)
    (path/'project/voice.wav').write_bytes(b'tampered')
    with pytest.raises(WorkError,match='已改变'):create().resume('tts')


def test_word_timing_must_be_measured_and_script_complete():
    with pytest.raises(WorkError,match='缺少真实词级'):measured_captions({'segments':[{'text':'你好'}]},1,'你好')
    with pytest.raises(WorkError,match='原文不一致'):
        measured_captions({'segments':[{'words':[{'text':'别的','start':.1,'end':.8}]}]},1,'你好')


def test_measured_caption_keeps_script_phrase_boundaries_without_inventing_word_times():
    words=[{'text':text,'start':i,'end':i+.8} for i,text in enumerate(['甲乙','丙丁','戊己'])]
    cues,observed=measured_captions({'segments':[{'words':words}]},3,'甲乙，丙丁。戊己')
    assert observed==words and [c['text'] for c in cues]==['甲乙','丙丁','戊己']
    assert [(c['startMs'],c['endMs']) for c in cues]==[(0,800),(1000,1800),(2000,2800)]


def test_measured_caption_does_not_cut_inside_a_provider_word():
    words=[{'text':'甲乙','start':0,'end':1},{'text':'丙丁','start':1,'end':2}]
    cues,observed=measured_captions({'segments':[{'words':words}]},2,'甲，乙丙丁')
    assert len(cues)==1 and observed==words and cues[0]['text']=='甲乙丙丁'


def test_measured_caption_does_not_merge_distinct_asr_sentences():
    words=[{'text':'甲乙','start':0,'end':1},{'text':'丙丁','start':1,'end':2}]
    cues,observed=measured_captions({'segments':[{'words':words[:1]},{'words':words[1:]}]},2,'甲乙丙丁')
    assert observed==words and [c['text'] for c in cues]==['甲乙','丙丁']


@pytest.mark.parametrize('container',[False,True])
def test_source_proof_reuse_checks_original_operation_and_provider_pcm(setup,container):
    path,c,_,_,r,create=setup
    script=path/'script.json';info=path/'voice-info.json';caps=path/'captions.json'
    atomic_private(script,{'text':'你好。'})
    atomic_private(info,{'status':'succeeded','operation_id':'call_'+'2'*32,'voice':str(c.path),'sha256':sha(c.path),
                         'samples':72000,'sample_rate':24000,'channels':1,'sample_width':2})
    atomic_private(caps,{'voice_sha256':sha(c.path),'clock':'provider-word-timestamps','captions':[{'text':'你好。','start':.1,'end':.8}]}
                   if container else [{'text':'你好。','startMs':100,'endMs':800}])
    r['recipe']['provenance']={'captions':{'voice_sha256':sha(c.path),'source_sha256':sha(caps)}}
    r['reuse']={'script':str(script),'voice_info':str(info),'captions':str(caps)}
    facade=create(r);state=facade.inspect();assert state['voice']['reused'] and state['cache_proof']['pcm'] and c.submits==0
    assert facade.quote('tts')['status']=='cached' and c.quotes==0
    assert facade.quote('asr')['status']=='cached'
    changed=deepcopy(r);changed['script']='声明的另一句话。';changed['reuse']['script']=str(path/'fake-script.json')
    atomic_private(path/'fake-script.json',{'text':changed['script']})
    # A matching local declaration is insufficient when the actual provider
    # operation text differs.
    g=ScriptFacade(SimpleNamespace(),path/'other',changed,center=c,menu=lambda:{},asr_status=lambda:{})
    with pytest.raises(WorkError,match='原供应商操作'):g.inspect()


def test_budget_keeps_existing_unconfirmed_asr_reservation(tmp_path):
    path=tmp_path/'budget.json'
    atomic_private(path,{'limit_micros':30000000,'known_spend_micros':0,'calls':[{'operation_id':'original-asr','reserved_micros':100000}]})
    budget=Budget(path);budget.reserve('new-tts','tts',500000);budget.record('new-tts',{'status':'succeeded','accepted':True,'charged_micros':None})
    saved=read(path);assert saved['reserved_micros']==600000 and saved['calls'][0]['reserved_micros']==100000


def test_later_material_revision_does_not_create_or_replace_speech_operation(setup):
    path,c,sdk,_,r,create=setup;f=create(r);f.quote('tts');f.confirm('tts',500000,path/'budget.json',confirmed=True)
    f.quote('asr');f.confirm('asr',100000,path/'budget.json',confirmed=True)
    recipe=deepcopy(r['recipe']);recipe['props']['footer']='新的已审素材安排'
    f.bind_recipe(recipe);out=create().export()
    assert read(out['input'])['props']['footer']=='新的已审素材安排'
    assert c.submits==1 and c.quotes==1 and sdk.confirms==1
