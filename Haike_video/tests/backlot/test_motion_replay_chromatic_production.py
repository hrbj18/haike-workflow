from copy import deepcopy
import hashlib
import pytest
from backlot.motion_replay_chromatic_production import EVENTS,OVERLAY,VERSION,validate_props,resolve_event,freeze_safe
from backlot.work_catalog import WorkError


def fixture():
    words=[{'text':c,'start':1+i*10,'end':2+i*10} for i,c in enumerate('甲乙丙丁')]
    asr={'metadata':{'words':words},'segments':words,'audio_sha256':'voice','approved_script_sha256':hashlib.sha256('甲乙丙丁'.encode()).hexdigest()}
    scenes=[]
    for i,action in enumerate(EVENTS):
        events={}
        keys=sorted(EVENTS[action])
        for k,key in enumerate(keys):
            events[key]={'from':30+i*300+k*20,'to':40+i*300+k*20,
                'anchor':{'kind':'word','index':i,'boundary':'start'},'offsetFrames':k*20,'meaning':key}
        if action.endswith('push-near'):
            for key,offset in [('push',0),('crossfade',20),('settle',20)]:
                events[key].update(from_=30+i*300+offset)
                events[key]['from']=events[key].pop('from_');events[key]['to']=events[key]['from']+10;events[key]['offsetFrames']=offset
        scenes.append({'id':str(i),'actionId':action,'from':i*300,'to':(i+1)*300,'title':'短标题','note':'说明','label':'现场','events':events})
    p={'templateId':'chromatic-06','version':VERSION,'durationInFrames':1200,'fps':30,'scenes':scenes,
       'shots':[{'id':'v','src':'hd.mp4','from':0,'to':1200,'sourceFrom':0,'objectPosition':'50% 50%','description':'fixture'}],
       'captions':[{'from':i*300,'to':i*300+100,'text':c} for i,c in enumerate('甲乙丙丁')],
       'presenters':[{'src':'hq.mp4','from':0,'to':60,'sourceFrom':0},{'src':'hq.mp4','from':1140,'to':1200,'sourceFrom':60}],
       'font':'font.ttf','brand':'海客','medicalOverlay':OVERLAY}
    receipts={'script':{'text':'甲乙丙丁'},'audio':{'script_sha256':asr['approved_script_sha256'],'audio_sha256':'voice'},'asr':asr,
      'avatar':{'workflow_id':'2112180419025260546','instance_type':'plus','api_type':'NORMAL','status':'verified','task_id':'fixture','original_audio_sha256':'voice'}}
    return p,receipts


def test_complete_new_semantic_contract():
    p,r=fixture();check=validate_props(p,r)
    assert check['complete_text_coverage'] and check['events']==13


def test_queue_receipts_are_sanitized_before_identity_is_frozen():
    core={'title':'完整视频','props':{'text':'原文'},'origins':{},'runtime':{},'contract_consumption':{},
          'receipts':{'usage':{'input_tokens':15,'output_tokens':12},'request_id':'accepted'}}
    safe=freeze_safe(core)
    assert safe['receipts']['usage']=={}
    assert safe['receipts']['request_id']=='accepted'
    assert safe['props']==core['props']
    core['props']['api_key']='not-an-actual-key'
    with pytest.raises(WorkError):freeze_safe(core)


def test_individual_internal_anchor_must_be_consumed():
    p,r=fixture();s=p['scenes'][1];event=s['events']['crossfade']
    old=event['from'];r['asr']['metadata']['words'][1]['start']+=1
    with pytest.raises(WorkError,match='未实际消费ASR锚点'):validate_props(p,r)
    # Resolving the changed word moves each affected internal event, while
    # unrelated events and outer scene windows remain untouched.
    for event in s['events'].values():event['from']+=30;event['to']+=30
    assert s['events']['crossfade']['from']==old+30
    assert p['scenes'][0]['events']['aperture']['from']==30
    assert validate_props(p,r)['complete_text_coverage']


@pytest.mark.parametrize('mutate',[
 lambda p,r:p.update(version='1.1.0'),
 lambda p,r:p['scenes'][0].update(actionId='fake'),
 lambda p,r:p['scenes'][0]['events'].pop('aperture'),
 lambda p,r:p['scenes'][0]['events']['aperture']['anchor'].update(index=100),
 lambda p,r:p['scenes'][0]['events']['aperture'].update(from_=22),
 lambda p,r:p['scenes'][1].update({'from':301}),
 lambda p,r:p['captions'].pop(),
 lambda p,r:p['shots'][0].update(to=1199),
 lambda p,r:r['avatar'].update(workflow_id='2094449979141218305'),
 lambda p,r:r['avatar'].update(api_type='SHARED'),
 lambda p,r:r['avatar'].update(original_audio_sha256='other-voice'),
 lambda p,r:p.update(medicalOverlay='无提示'),
])
def test_unknown_or_incomplete_production_blocked(mutate):
    p,r=fixture();mutate(p,r)
    with pytest.raises((WorkError,KeyError)):validate_props(p,r)
