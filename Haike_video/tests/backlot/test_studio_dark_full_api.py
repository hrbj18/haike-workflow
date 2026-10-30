"""Browser boundaries, CAS and recovery use local fakes, never provider calls."""
from copy import deepcopy
import io
import json
from pathlib import Path
import wave
import math
from array import array
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backlot import studio_dark_full_api as web
from backlot.production_queue import ProductionQueue,ProductionQueueConflict
from backlot.studio import atomic_private
from backlot.work_catalog import sha


def wav_bytes():
    out=io.BytesIO()
    tone=array('h',(round(6000*math.sin(i*2*math.pi*440/48000)) for i in range(96000)))
    with wave.open(out,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000);f.writeframes(tone.tobytes())
    return out.getvalue()


@pytest.fixture
def env(tmp_path,monkeypatch):
    task=tmp_path/'task';task.mkdir();monkeypatch.setattr(web,'TASK_ROOT',task)
    app=FastAPI();app.include_router(web.router)
    store=web.DraftStore(tmp_path/'projects');app.state.dark_full_drafts=store
    queue=ProductionQueue(tmp_path/'queue.sqlite3',tmp_path/'projects')
    monkeypatch.setattr(web,'queue',lambda request:queue)
    return TestClient(app),store,queue,task


def blank(client,**patch):
    data={'title':'亲子体验','theme':'child','script':'你好','recipe':{'props':{'variant':'cobalt','media':[],'captions':[]},'audio':{'voice':'voice.wav'},'provenance':{},'shotPlan':[]}}
    data.update(patch)
    response=client.post('/api/studio/dark-full/drafts',json=data);assert response.status_code==200,response.text
    return response.json()


def body(draft,**patch):
    data={k:deepcopy(draft[k]) for k in ['id','revision','title','theme','script','recipe']};data.update(patch);return data


def test_durable_revision_conflict_and_independent_clone(env):
    client,store,_,_=env;d=blank(client)
    v=client.post('/api/studio/dark-full/drafts',json=body(d,title='新标题')).json();assert v['revision']==2
    assert client.post('/api/studio/dark-full/drafts',json=body(d,title='冲突')).status_code==409
    cloned=client.post(f"/api/studio/dark-full/drafts/{v['id']}/clone",json={'revision':2}).json()
    assert cloned['id']!=d['id'] and cloned['revision']==1
    restored=web.DraftStore(store.studio.projects_root).get(d['id']);assert restored['title']=='新标题'


def test_noop_save_preserves_revision_timestamp_and_still_rejects_stale_cas(env):
    client,_,_,_=env;d=blank(client)
    same=client.post('/api/studio/dark-full/drafts',json=body(d));assert same.status_code==200 and same.json()==d
    changed=client.post('/api/studio/dark-full/drafts',json=body(d,title='真实新标题')).json()
    assert changed['revision']==2
    stale=body(changed);stale['revision']=1
    assert client.post('/api/studio/dark-full/drafts',json=stale).status_code==409
    assert client.post('/api/studio/dark-full/drafts',json=body(changed)).json()==changed


def test_paths_secrets_and_cross_origin_never_enter_browser_contract(env):
    client,_,_,_=env
    assert client.post('/api/studio/dark-full/drafts',json={'recipe':{'sources':{'x':'C:/secret.wav'}}}).status_code==422
    assert client.post('/api/studio/dark-full/drafts',json={'recipe':{'props':{'api_key':'secret'}}}).status_code==422
    assert client.post('/api/studio/dark-full/drafts',json={},headers={'Origin':'https://other.invalid'}).status_code==403
    assert client.post('/api/studio/dark-full/drafts',content=b'raw').status_code in {415,422}
    assert web.safe({'sources':{},'path':'/private/file','source':'C:/Users/private.wav','api_key':'secret','url':'/api/test'})=={'source':'[LOCAL_PATH]','url':'/api/test'}


def test_missing_recipe_is_truthful_and_catalog_has_ten_scored_groups(env):
    client,_,_,_=env
    catalog=client.get('/api/studio/dark-full/catalog').json()
    assert len(catalog['groups'])==10 and all(0<g['score']<=100 for g in catalog['groups'])
    assert not any(r['available'] for r in catalog['recipes'])
    assert client.post('/api/studio/dark-full/recipes/elder/copy',json={}).status_code==404


def test_trusted_recipe_copy_hides_sources_and_clone_keeps_owned_blobs(env):
    client,store,_,task=env;folder=task/'elder';folder.mkdir();source=task/'private-voice.wav';source.write_bytes(wav_bytes())
    atomic_private(folder/'input.json',{'title':'长者','props':{'variant':'hedgerow','captions':[{'text':'你好','startMs':0,'endMs':1000}]},'audio':{'voice':'voice.wav'},'provenance':{'voice':{'source':str(source)}},'sources':{'voice.wav':str(source)}})
    response=client.post('/api/studio/dark-full/recipes/elder/copy',json={});assert response.status_code==200,response.text
    d=response.json();assert str(task) not in response.text and 'sources' not in d
    assert d['bindings'][0]['slot']=='voice.wav' and d['script']=='你好'
    clone=store.clone(d['id'],d['revision']);assert store.material_path(d['id'],'voice.wav')==store.material_path(clone['id'],'voice.wav')


def test_upload_uses_owned_asset_validation_and_invalidates_voice_clock(env):
    client,store,_,_=env;d=blank(client);url=f"/api/studio/dark-full/drafts/{d['id']}/assets"
    params={'revision':1,'slot':'voice.wav','kind':'audio','filename':'voice.wav','rights_confirmed':'true'}
    response=client.post(url,params=params,content=wav_bytes(),headers={'Content-Type':'application/octet-stream'})
    assert response.status_code==200,response.text
    saved=response.json();assert saved['revision']==2 and saved['needs_alignment'] and 'path' not in response.text
    assert client.post(url,params=params,content=wav_bytes(),headers={'Content-Type':'application/octet-stream'}).status_code==409
    assert client.get(f"/api/studio/dark-full/drafts/{d['id']}/next-stage").json()['status']=='needs_alignment'
    captions=[{'text':'你好','startMs':0,'endMs':1200}]
    result=client.post(f"/api/studio/dark-full/drafts/{d['id']}/captions",json={'revision':2,'captions':captions})
    assert result.status_code==200 and not result.json()['needs_alignment']
    private=store.get(d['id']);assert private['recipe']['provenance']['captions']['voice_sha256']==private['sources']['voice.wav']['sha256']


def test_script_only_is_pending_voice_without_any_cloud_call(env,monkeypatch):
    client,store,_,_=env;d=blank(client)
    monkeypatch.setattr(store.studio,'client',lambda *a:pytest.fail('Unexpected cloud call'))
    r=client.get(f"/api/studio/dark-full/drafts/{d['id']}/next-stage").json()
    assert r['status']=='needs_voice' and r['cloud_calls']==0
    assert '/api/studio/audio-center/quotes' in [a['endpoint'] for a in r['actions']]


def test_repeated_prepare_submit_recovers_single_existing_queue_job(env,monkeypatch):
    client,store,queue,_=env;d=blank(client);prefix=f"/api/studio/dark-full/drafts/{d['id']}"
    monkeypatch.setattr(store,'input',lambda identity,revision:{'title':'测试'})
    frozen={'project_id':'studio-0000000000000000','render_id':'dark-abc','request_sha256':'a'*64,'props':{'durationFrames':900,'fps':30},'contract':web.adapter.CONTRACT}
    def prepare(q,value):
        atomic_private(q.projects_root/frozen['project_id']/'project.json',{'title':'测试'})
        atomic_private(q.projects_root/frozen['project_id']/'artifacts'/web.adapter.REQUEST_FILE,frozen);return frozen
    monkeypatch.setattr(web.adapter,'prepare',prepare)
    monkeypatch.setattr(web,'dispatch',lambda request,job:None)
    monkeypatch.setattr(web.adapter,'submit',lambda q,r:q.submit(project_id=r['project_id'],kind='studio_investment_recompose',source='workbench',priority='normal',parent_job_id=r['render_id'],frozen_request=r,idempotency_key=web.adapter.CONTRACT+':'+r['request_sha256'],start_paused=True))
    prepared=client.post(prefix+'/prepare',json={'revision':1});assert prepared.status_code==200,prepared.text
    assert str(queue.projects_root) not in prepared.text
    first=client.post(prefix+'/submit',json={'revision':1,'request_sha256':'a'*64});second=client.post(prefix+'/submit',json={'revision':1,'request_sha256':'a'*64})
    assert first.status_code==second.status_code==200,(first.text,second.text)
    assert first.json()['job']['job_id']==second.json()['job']['job_id'] and first.json()['job']['status']=='paused'
    history=client.get(prefix+'/productions').json()['productions'];assert len(history)==1 and history[0]['job']['job_id']==first.json()['job']['job_id']
    client.post('/api/studio/dark-full/drafts',json=body(d,title='已修改'))
    assert client.post(prefix+'/submit',json={'revision':1,'request_sha256':'a'*64}).status_code==409


def test_busy_existing_lane_keeps_original_paused_job_and_explains_recovery(env,monkeypatch):
    client,store,queue,_=env
    project=queue.projects_root/'studio-0000000000000001';atomic_private(project/'project.json',{'title':'原任务'})
    job=queue.submit(project_id=project.name,kind='studio_investment_recompose',source='workbench',priority='normal',parent_job_id='same-render',frozen_request={},idempotency_key='same-request',start_paused=True)
    class Immediate:
        def __init__(self,target,**kwargs):self.target=target
        def start(self):self.target()
    class Busy:
        def __init__(self,*args,**kwargs):pass
        def run_local_recompose(self,identity):assert identity==job['job_id'];raise ProductionQueueConflict('busy')
    from backlot import production_queue_worker
    monkeypatch.setattr(production_queue_worker,'ProductionQueueWorker',Busy)
    monkeypatch.setattr(web.threading,'Thread',Immediate)
    web.dispatch(SimpleNamespace(app=client.app),job)
    assert queue.get(job['job_id'])['status']=='paused'
    with store.studio.db() as db:record=json.loads(db.execute('SELECT data FROM dark_full_dispatch WHERE job_id=?',(job['job_id'],)).fetchone()[0])
    assert record['status']=='busy' and '保留原任务' in record['message']


def test_larger_video_allowance_is_scoped_to_this_owner_and_keeps_probe(env,monkeypatch):
    client,store,_,_=env;d=blank(client);owner=web.OwnedAssets(store)
    from backlot import studio_render
    from backlot.studio import Studio
    from backlot.work_catalog import WorkError
    observed=[]
    monkeypatch.setattr(studio_render,'media_probe',lambda path:observed.append(path) or {'video':{'width':1920,'height':1080},'duration':3})
    content=b'0'*(80*1024*1024+1)
    with pytest.raises(WorkError):Studio.save_asset(owner,d['id'],'large.mp4','video',content)
    asset=owner.save_asset(d['id'],'large.mp4','video',content)
    assert observed and owner.asset(asset['id'],d['id']).stat().st_size==len(content)
    monkeypatch.setattr(web,'MAX_UPLOAD',16)
    response=client.post(f"/api/studio/dark-full/drafts/{d['id']}/assets",params={'revision':1,'slot':'video.mp4','kind':'video','filename':'video.mp4','rights_confirmed':'true'},content=b'0'*17,headers={'Content-Type':'application/octet-stream'})
    assert response.status_code==413


@pytest.fixture
def completed_adoption(env,monkeypatch):
    client,store,queue,task=env
    props={'variant':'cobalt','captions':[{'text':'你好','startMs':0,'endMs':1000}],
           'media':[{'id':'a','offset':0,'src':'voice.wav'}]}
    audio={'voice':'voice.wav','durationFrames':60};provenance={'voice':{'sha256':'voice-proof','source':'本次授权录音','authorized':True}}
    d=blank(client,recipe={'props':props,'audio':audio,'provenance':provenance})
    source=task/'voice.wav';source.write_bytes(wav_bytes())
    frozen={'project_id':'studio-1111111111111111','render_id':'dark-completed',
            'request_sha256':'b'*64,'props':deepcopy(props),'audio':deepcopy(audio),'provenance':deepcopy(provenance),
            'origins':{'voice.wav':{'sha256':sha(source)}},'contract':web.adapter.CONTRACT}
    project=queue.projects_root/frozen['project_id']
    atomic_private(project/'artifacts'/web.adapter.REQUEST_FILE,frozen)
    job={'job_id':'PQ-existing-completed','status':'completed','result':{'work_id':'work-existing','version_id':'version-existing'}}
    monkeypatch.setattr(web.adapter,'validate',lambda q,r:project)
    monkeypatch.setattr(queue,'find_by_idempotency_key',lambda key:job if key==web.adapter.CONTRACT+':'+frozen['request_sha256'] else None)
    def owned_input(identity,revision):
        current=store.get(identity);web.require(current['revision']==revision,'草稿已更新','conflict')
        return deepcopy(current['recipe'])
    monkeypatch.setattr(store,'input',owned_input)
    monkeypatch.setattr(web.adapter,'preflight',lambda value:{'props':value['props'],'audio':value['audio'],'provenance':value['provenance'],'paths':{'voice.wav':source}})
    monkeypatch.setattr(web.adapter,'prepare',lambda *a:pytest.fail('adopt must not prepare or render'))
    monkeypatch.setattr(web.adapter,'submit',lambda *a:pytest.fail('adopt must not enqueue'))
    return client,store,queue,d,frozen,source,job


def test_completed_adoption_is_idempotent_and_uses_existing_work_version(completed_adoption):
    client,_,_,d,frozen,_,_=completed_adoption;prefix=f"/api/studio/dark-full/drafts/{d['id']}"
    request={'revision':1,'project_id':frozen['project_id']}
    first=client.post(prefix+'/adopt',json=request);again=client.post(prefix+'/adopt',json=request)
    assert first.status_code==again.status_code==200,first.text
    assert first.json()==again.json() and first.json()['adopted'] and first.json()['cloud_calls']==0
    history=client.get(prefix+'/productions').json()['productions']
    assert len(history)==1 and history[0]['job']['job_id']=='PQ-existing-completed'
    assert history[0]['work_id']=='work-existing' and history[0]['version_id']=='version-existing' and history[0]['video_url']
    assert client.post(prefix+'/adopt',json={**request,'path':'C:/not-allowed.mp4'}).status_code==422


@pytest.mark.parametrize('changed',['caption','offset','sha'])
def test_adopt_rejects_changed_captions_offset_or_slot_bytes(completed_adoption,changed):
    client,_,_,d,frozen,source,_=completed_adoption;revision=1
    if changed=='sha':source.write_bytes(b'different-voice-bytes')
    else:
        patch=deepcopy(d['recipe'])
        if changed=='caption':patch['props']['captions'][0]['endMs']=1001
        else:patch['props']['media'][0]['offset']=.1
        saved=client.post('/api/studio/dark-full/drafts',json=body(d,recipe=patch)).json();revision=saved['revision']
    response=client.post(f"/api/studio/dark-full/drafts/{d['id']}/adopt",json={'revision':revision,'project_id':frozen['project_id']})
    assert response.status_code==422 and '不同' in response.json()['detail']
    assert client.get(f"/api/studio/dark-full/drafts/{d['id']}/productions").json()['productions']==[]


def test_adopt_cas_guards_both_stale_requests_and_mid_check_edit(completed_adoption,monkeypatch):
    client,store,_,d,frozen,_,_=completed_adoption;prefix=f"/api/studio/dark-full/drafts/{d['id']}"
    updated=client.post('/api/studio/dark-full/drafts',json=body(d,title='新标题')).json()
    assert client.post(prefix+'/adopt',json={'revision':1,'project_id':frozen['project_id']}).status_code==409
    base=web.adapter.preflight
    def concurrent(value):
        result=base(value);store.save(body(updated,title='检查期间更新'));return result
    monkeypatch.setattr(web.adapter,'preflight',concurrent)
    assert client.post(prefix+'/adopt',json={'revision':2,'project_id':frozen['project_id']}).status_code==409
    assert client.get(prefix+'/productions').json()['productions']==[]


def test_adopt_requires_completed_queue_receipt(completed_adoption):
    client,_,_,d,frozen,_,job=completed_adoption;job['status']='running'
    response=client.post(f"/api/studio/dark-full/drafts/{d['id']}/adopt",json={'revision':1,'project_id':frozen['project_id']})
    assert response.status_code==422 and '已完成' in response.json()['detail']

