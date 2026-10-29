"""A repaired DNS path can reopen only the same accepted, budget-bound source job."""
from copy import deepcopy
import json

import pytest

from backlot.production_queue import ProductionQueue, ProductionQueueConflict
from backlot.studio import Studio, atomic_private
from backlot.studio_avatar import key_identity


@pytest.fixture
def case(tmp_path, monkeypatch):
    root=tmp_path/'projects';project=root/'source';project.mkdir(parents=True)
    atomic_private(project/'project.json',{'id':'source','title':'原人物下载'})
    studio=Studio(root);queue=ProductionQueue(tmp_path/'queue.sqlite3',root)
    intent='call_'+'a'*32
    request={'source_consumer':'motion-template-source-v1','key_identity':key_identity(studio),
             'draft':{'id':'source','revision':2},'render_id':'studio-2','max_charge_micros':10_000_000}
    audio=project/'audio.wav';audio.write_bytes(b'existing-complete-audio')
    path=project/'renders/studio-2/gateway-state.json'
    state={'prepared':{'audio_path':str(audio)},'stages':{
        'tts':{'quote':{'max_charge_micros':20000},'job':{'status':'succeeded'}},
        'avatar':{'intent':intent,'quote':{'id':'quote-avatar','model':'haike/avatar','max_charge_micros':3_960_000},
                  'job':{'id':'gj-original','status':'submission_unknown',
                         'result':{'video_url':'https://rh-comfyui01.tos-cn-beijing.volces.com/original.mp4'}}}}}
    atomic_private(path,state)
    journal=studio.private/'haike-api/intents'/f'{intent}.json'
    atomic_private(journal,{'job_id':'gj-original','body':{'call_intent_id':intent,'quote_id':'quote-avatar'}})
    dns=[]
    monkeypatch.setattr('backlot.studio_avatar.public_media_address',lambda host,port:dns.append((host,port)) or '8.8.8.8')
    monkeypatch.setattr(Studio,'client',lambda *a,**k:pytest.fail('rechecking a download must not submit provider calls'))
    def submit(*,message='代理DNS未能核对真实公网媒体地址，请核对代理DNS后恢复原任务',kind='studio_avatar',changes=None):
        frozen={**deepcopy(request),**(changes or {})}
        job=queue.submit(project_id='source',kind=kind,source='workbench',priority='normal',
                         parent_job_id='studio-2',idempotency_key='original',frozen_request=frozen)
        queue.claim_next('worker')
        queue.finish(job['job_id'],'worker',status='failed',stage=message,
                     error={'type':'StudioAvatar','message':message},retryable=False,safe_resume_point='studio_avatar')
        return job['job_id']
    return {'queue':queue,'submit':submit,'request':request,'path':path,'state':state,'journal':journal,'audio':audio,'dns':dns}


def test_original_download_recheck_preserves_request_budget_intent_and_pending_billing(case):
    c=case;q=c['queue'];identity=c['submit']();before=q.get(identity,include_private=True)
    state_bytes=c['path'].read_bytes();journal_bytes=c['journal'].read_bytes()
    result=q.recover_studio_avatar_download(identity)
    assert result['status']=='queued' and result['job_id']==identity
    assert q.get(identity,include_private=True)['frozen_request']==before['frozen_request']
    assert c['path'].read_bytes()==state_bytes and c['journal'].read_bytes()==journal_bytes
    assert c['dns']==[('rh-comfyui01.tos-cn-beijing.volces.com',443)]
    events=[e for e in q.events(identity) if e['event_type']=='source_download_rechecked']
    assert len(events)==1
    with pytest.raises(ProductionQueueConflict):q.recover_studio_avatar_download(identity)


@pytest.mark.parametrize('problem',['other_error','other_kind','other_account','other_consumer','foreign_draft',
                                   'other_render','missing_audio','asr_failed','over_budget','other_job',
                                   'other_quote','missing_intent','private_url','dns_rejected','changed_state'])
def test_download_recheck_cannot_release_unrelated_or_unverified_failures(case,monkeypatch,problem):
    c=case;changes={};kwargs={}
    if problem=='other_error':kwargs['message']='不是下载错误'
    if problem=='other_kind':kwargs['kind']='review_preview'
    if problem=='other_account':changes['key_identity']='foreign'
    if problem=='other_consumer':changes['source_consumer']='other'
    if problem=='foreign_draft':changes['draft']={'id':'foreign','revision':2}
    if problem=='other_render':changes['render_id']='../outside'
    if problem=='missing_audio':c['audio'].unlink()
    if problem=='asr_failed':c['state']['stages']['asr_bailian']={'quote':{'max_charge_micros':100000},'job':{'status':'failed'}}
    if problem=='over_budget':changes['max_charge_micros']=1
    if problem=='other_job':c['state']['stages']['avatar']['job']['id']='gj-other'
    if problem=='other_quote':c['state']['stages']['avatar']['quote']['id']='quote-other'
    if problem=='missing_intent':c['state']['stages']['avatar'].pop('intent')
    if problem=='private_url':c['state']['stages']['avatar']['job']['result']['video_url']='http://127.0.0.1/private'
    if problem=='dns_rejected':
        def reject(*a):raise ValueError('no verified public address')
        monkeypatch.setattr('backlot.studio_avatar.public_media_address',reject)
    if problem=='changed_state':
        def change(*a):c['path'].write_bytes(b'changed during DNS');return '8.8.8.8'
        monkeypatch.setattr('backlot.studio_avatar.public_media_address',change)
    atomic_private(c['path'],c['state'])
    identity=c['submit'](changes=changes,**kwargs);before=c['queue'].get(identity,include_private=True)
    with pytest.raises(ProductionQueueConflict):c['queue'].recover_studio_avatar_download(identity)
    assert c['queue'].get(identity,include_private=True)==before
    assert not any(e['event_type']=='source_download_rechecked' for e in c['queue'].events(identity))
