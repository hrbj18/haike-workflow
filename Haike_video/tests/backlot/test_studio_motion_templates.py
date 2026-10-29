"""Session revisions, paid-stage boundaries, and shared queue routing."""
from copy import deepcopy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot import studio_motion_templates as m, studio_motion_templates_api as web
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError
from backlot.production_queue import ProductionQueue


@pytest.fixture
def env(tmp_path, monkeypatch):
    media = tmp_path/'media'; media.mkdir()
    for name in ['portrait.jpg', 'a.jpg', 'b.jpg', 'c.jpg', 'd.jpg']:
        Image.new('RGB', (720, 720), '#3D6188').save(media/name)
    voice = media/'voice.wav'
    with wave.open(str(voice), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000); f.writeframes(b'\0'*24000*2)
    for name in ['avatar.mp4', 'lens.mp4', 'package.motion']: (media/name).write_bytes(b'local-fake-'+name.encode())
    atomic_private(media/'caps.json', [{'zh': '你好'}])
    profile = json.loads(m.PROFILE.read_text(encoding='utf-8'))
    seed = {'template_id': m.TEMPLATE_ID, 'title': '亲子体验', 'short_title': '一起探索', 'brand': '海客', 'presenter_label': '店长',
      'layout': 'portrait45', 'voice': m.binding(voice), 'captions': {**m.binding(media/'caps.json')},
      'avatar': {**m.binding(media/'avatar.mp4'), 'badge': m.binding(media/'portrait.jpg')}, 'tools': {'package': m.binding(media/'package.motion')},
      'media': {'wall': [{'id': 'w'+str(i), 'source': m.binding(media/n), 'at': 0} for i,n in enumerate(['a.jpg', 'b.jpg', 'c.jpg', 'd.jpg'])],
                'categories': [{'id': 'c'+str(i), 'source': m.binding(media/n), 'at': 0} for i,n in enumerate(['a.jpg', 'b.jpg', 'c.jpg', 'd.jpg'])],
                'lens': {'id': 'lens', 'source': m.binding(media/'lens.mp4'), 'offset': 0}},
      'content': {g['id']: {f['inputPath']: 3 if f['type'] == 'number' else '海客' for f in g['fields']} for g in profile['groups']}}
    monkeypatch.setattr(m, 'seed_input', lambda: deepcopy(seed))
    store = m.Sessions(tmp_path/'projects', tmp_path/'cache')
    q = ProductionQueue(tmp_path/'queue.sqlite3', tmp_path/'projects')
    app = FastAPI(); app.include_router(web.router); app.state.motion_template_sessions = store
    monkeypatch.setattr(web, 'queue', lambda request: q)
    return store, q, TestClient(app), seed


def test_owned_session_public_contract_and_cas(env):
    s, q, client, _ = env
    d = client.post('/api/studio/motion-templates/sessions', json={'template_id': m.TEMPLATE_ID}).json()
    assert d['layout'] == 'landscape' and d['reuse_matches_script']
    assert 'path' not in json.dumps(d) and 'tools' not in d
    url = '/api/studio/motion-templates/sessions/'+d['id']
    update = client.post(url, json={'revision': 1, 'patch': {'script': '新的口播'}})
    assert update.status_code == 200 and not update.json()['reuse_matches_script']
    assert client.post(url, json={'revision': 1, 'patch': {'title': '冲突'}}).status_code == 409
    assert client.post(url, json={'revision': 2, 'patch': {'tools': {}}}).status_code == 422
    assert client.post(url+'/submit', json={'revision': 2}).status_code == 422
    assert not q.list()['tasks']


def test_import_does_not_grant_execution_or_accept_arbitrary_paths(env):
    _, q, client, _ = env
    assert client.post('/api/studio/motion-templates/sessions', json={'template_id': 'mg-unknown'}).status_code == 503
    assert client.post('/api/studio/motion-templates/sessions', json={'template_id': m.TEMPLATE_ID, 'input': {'path': 'C:/private'}}).status_code == 422
    assert client.post('/api/studio/motion-templates/sessions', json={'template_id': m.TEMPLATE_ID}, headers={'Origin': 'https://foreign.example'}).status_code == 403
    assert not q.list()['tasks']


def test_edits_invalidate_source_frames_and_clones_keep_paid_job_independent(env):
    s, _, _, _ = env; d = s.create(m.TEMPLATE_ID)
    d.update(source_review='old', source_frames={'token': 'old'}, plan={'token': 'old'}, generation={'job_id': 'old-paid', 'quote': {'id': 'old-quote'}, 'asset_draft_id': 'owner'})
    d = s.put(d, d['revision'])
    v = s.patch(d['id'], d['revision'], {'layout': 'portrait45'})
    assert not v['source_review'] and 'source_frames' not in v and 'plan' not in v
    clone = s.clone(v['id'], v['revision'])
    assert clone['generation'] == {'asset_draft_id': 'owner'}
    assert s.get(d['id'])['generation']['job_id'] == 'old-paid'


def test_native_and_adapted_presenter_capability_enforced(env):
    s, _, _, _ = env; d = s.create(m.TEMPLATE_ID); d['source_review'] = 'review'
    d['presenter_mode'] = 'hidden'
    with pytest.raises(WorkError, match='原生横版'): s.input(d)
    d['layout'] = 'portrait45'
    assert s.input(d)['layout'] == 'portrait45'


def test_console_uses_same_http_sessions_with_its_real_field_limits(env,monkeypatch):
    from backlot import studio_motion_console_session as console
    s,_,client,seed=env
    seed=deepcopy(seed);seed['template_id']=console.ID
    seed['content']={g['id']:{f['key']:(0 if f['type']=='number' else '内容' if f['required'] else '')
                             for f in g['fields']} for g in console.fields()}
    seed['content']['readme-terminal']['body']='陈家林路63号\n未来汇一楼'
    monkeypatch.setattr(console,'seed',lambda:deepcopy(seed))
    monkeypatch.setattr(console,'slots',lambda value:[])
    d=client.post('/api/studio/motion-templates/sessions',json={'template_id':console.ID}).json()
    assert d['template_id']==console.ID and 'tools' not in d and not d['sources']
    url='/api/studio/motion-templates/sessions/'+d['id']
    accepted=client.post(url,json={'revision':d['revision'],'patch':{'content':seed['content']}})
    assert accepted.status_code==200
    revision=accepted.json()['revision']
    assert client.post(url,json={'revision':revision,'patch':{'layout':'portrait-square'}}).status_code==422
    assert client.post(url,json={'revision':revision,'patch':{'presenter_mode':'hidden'}}).status_code==422
    invalid=deepcopy(seed['content']);invalid['versus-panels']['winner']=3
    assert client.post(url,json={'revision':revision,'patch':{'content':invalid}}).status_code==422
    invalid=deepcopy(seed['content']);invalid['keyword-slam']['keyword']='超过六个字符长度'
    assert client.post(url,json={'revision':revision,'patch':{'content':invalid}}).status_code==422
    assert s.get(d['id'])['revision']==revision


def test_console_content_round_trip_keeps_native_paths_outside_editable_fields():
    from backlot import studio_motion_console_session as console
    segments=[]
    for group in console.fields():
        inputs={}
        for field in group['fields']:
            if '.' not in field['key']:inputs[field['key']]=0 if field['type']=='number' else '内容'
        if group['id']=='statement-orb':inputs['lines']=['上句','下句']
        if group['id']=='works-fan':inputs.update(works=[{'name':'素材','kind':'实拍'} for i in range(6)],media={'w0':'private.mp4'})
        if group['id']=='versus-panels':
            for side in ['left','right']:inputs[side]={'head':'标题','tag':'标签','points':['一点','二点']}
        if group['id']=='readme-terminal':inputs['window']={'title':'窗口'}
        segments.append({'recipe':group['id'],'inputs':inputs})
    values=console.content(segments)
    assert values['versus-panels']['left.points.2']==''
    values['versus-panels']['right.points.2']='新增第三点'
    values['readme-terminal']['body']='多行\n正文'
    result=console.apply_content(segments,values)
    assert result[2]['inputs']['media']=={'w0':'private.mp4'}
    assert result[3]['inputs']['left']['points']==['一点','二点']
    assert result[3]['inputs']['right']['points']==['一点','二点','新增第三点']
    assert 'media' not in values['works-fan']


def test_console_create_and_clone_measure_again_without_losing_paid_source(env,monkeypatch):
    s,_,_,seed=env;seed=deepcopy(seed);seed['template_id']=m.console_session.ID
    seed['console']={'presenterCrop':{'cx':.2,'cy':.3,'h':.2},
                     'presenterFraming':{'path':'old-framing'},'cropCalibration':{'path':'old-circle'}}
    monkeypatch.setattr(m.console_session,'seed',lambda:deepcopy(seed))
    d=s.create(m.console_session.ID);c=d['input']['console'];digest=seed['avatar']['sha256']
    assert c['presenterFramingRequired']==c['cropCalibrationRequired']==digest
    assert 'presenterFraming' not in c and 'cropCalibration' not in c
    c.update(presenterFraming={'path':'period-one-framing'},cropCalibration={'path':'period-one-circle'})
    d.update(source_review='period-one-reviewed',generation={'job_id':'settled-paid-source','asset_draft_id':'source-owner'})
    d=s.put(d,d['revision']);clone=s.clone(d['id'],d['revision'])
    assert clone['input']['voice']==seed['voice'] and clone['input']['avatar']==seed['avatar']
    assert 'presenterFraming' not in clone['input']['console'] and 'cropCalibration' not in clone['input']['console']
    assert 'source_review' not in clone and clone['generation']=={'asset_draft_id':'source-owner'}
    assert s.get(d['id'])['input']['console']['cropCalibration']=={'path':'period-one-circle'}


def test_console_legacy_crop_flag_cannot_skip_source_framing(env):
    s,_,_,seed=env;d=s.create(m.TEMPLATE_ID);d['template_id']=m.console_session.ID
    d['input']['console']={'cropCalibrationRequired':seed['avatar']['sha256'],
                           'cropCalibration':{'path':'old-unframed-circle'}}
    m.console_presenter(d)
    assert d['input']['console']['presenterFramingRequired']==seed['avatar']['sha256']
    assert 'cropCalibration' not in d['input']['console']


def test_poster_shared_session_exposes_only_supported_controls_and_resets_clone(env,monkeypatch):
    from backlot import studio_motion_poster_session as poster
    s,_,client,seed=env;seed=deepcopy(seed);seed['template_id']=poster.ID
    seed['content']={g['id']:{f['key']:'海客' for f in g['fields']} for g in poster.fields()}
    monkeypatch.setattr(poster,'seed',lambda:deepcopy(seed));monkeypatch.setattr(poster,'slots',lambda value:[])
    d=client.post('/api/studio/motion-templates/sessions',json={'template_id':poster.ID}).json()
    assert d['presenter_mode']=='hidden' and d['reuse_matches_script']
    url='/api/studio/motion-templates/sessions/'+d['id']
    assert client.post(url,json={'revision':d['revision'],'patch':{'presenter_mode':'small'}}).status_code==422
    portrait=client.post(url,json={'revision':d['revision'],'patch':{'layout':'portrait45'}}).json()
    assert portrait['layout']=='portrait45'
    d=portrait
    invalid=deepcopy(seed['content']);invalid['polaroid-film']['items.0.caption']='十一字文案超过十字的限制'
    assert client.post(url,json={'revision':d['revision'],'patch':{'content':invalid}}).status_code==422
    accepted=client.post(url,json={'revision':d['revision'],'patch':{'presenter_mode':'auto'}}).json()
    assert accepted['presenter_mode']=='auto'
    private=s.get(d['id']);private['component_run']={'request':'old'};private['source_review']='old'
    private=s.put(private,private['revision']);clone=s.clone(d['id'],private['revision'])
    assert 'component_run' not in clone and 'source_review' not in clone


def test_unplanned_poster_remains_editable_without_approving_its_timing(env,monkeypatch):
    from backlot import studio_motion_poster_session as poster
    s,q,client,seed=env;seed=deepcopy(seed)
    seed['content']={g['id']:{f['key']:'海客' for f in g['fields']} for g in poster.fields()}
    for i,row in enumerate(seed['media']['wall']):row['label']=f'素材{i+1}'
    seed['media']['wall'][0]['source']=seed['avatar'];seed['media']['wall'][0]['label']='待编排实拍'
    monkeypatch.setattr(poster,'seed',lambda:deepcopy(seed))
    def blocked(value):raise WorkError('完整口播和素材需要重新编排')
    monkeypatch.setattr(poster,'slots',blocked)
    response=client.post('/api/studio/motion-templates/sessions',json={'template_id':poster.ID})
    assert response.status_code==200,response.text
    d=response.json();assert d['configuration_error']=='完整口播和素材需要重新编排'
    assert d['sources'][0]['kind']=='video' and d['sources'][0]['seconds'] is None and d['sources'][0]['timing_pending']
    assert client.get('/api/studio/motion-templates/sessions/'+d['id']).status_code==200
    with pytest.raises(WorkError,match='重新编排'):
        s.prepare_source_review(d['id'],d['revision'],q)
    assert not s.get(d['id']).get('source_review') and not q.list()['tasks']


def test_poster_render_uses_existing_component_queue_and_is_idempotent(env,monkeypatch):
    from backlot import studio_motiongit_render as component
    s,q,_,_=env;d=s.create(m.TEMPLATE_ID)
    frozen={'project_id':'studio-'+'a'*16,'render_id':'motiongit-component-fixture','request_sha256':'fixture',
            'contract':component.CONTRACT,'draft':{'workflow':'poster-kit','parameters':{'duration':30}}}
    from lib.checkpoint import init_project
    init_project(frozen['project_id'],title='海报',pipeline_type='animated-explainer',pipeline_dir=q.projects_root)
    path=s.folder(d['id'])/'component.json';atomic_private(path,frozen)
    d.update(status='ready_to_render',run={k:frozen[k] for k in ['project_id','render_id','request_sha256','contract']},
             frozen={'request':str(path),'engine':'component'});d=s.put(d,d['revision']);calls=[]
    def submit(queue,request,*,phase):
        calls.append(phase)
        return queue.submit(project_id=request['project_id'],kind=component.KIND,source='workbench',priority='normal',
                            parent_job_id=request['render_id'],idempotency_key='poster-final',frozen_request=request,start_paused=True)
    monkeypatch.setattr(component,'submit',submit)
    d=s.submit(d['id'],d['revision'],q);same=s.submit(d['id'],d['revision'],q)
    assert calls==['render'] and same['run']['job_id']==d['run']['job_id'] and len(q.list()['tasks'])==1


def test_poster_portrait_reflows_controls_without_changing_content_or_motion():
    from backlot import studio_motion_poster_session as poster
    params={'duration':30,'voiceover':'inputs/voice.wav','segments':[
        {'control':name,'variant':variant,'t0':i*6,'t1':(i+1)*6,'cues':[i*6+.5],
         'props':{'title':'实际内容'}} for i,(name,variant) in enumerate([
             ('kinetic','stack'),('polaroid','film'),('media','scan'),('gallery','carousel'),('cta','arrow')])]}
    original=deepcopy(params)
    poster.apply_layout(params,'portrait45')
    assert params['layout']=='portrait'
    assert params['duration']==original['duration'] and params['voiceover']==original['voiceover']
    for before,after in zip(original['segments'],params['segments']):
        assert {k:v for k,v in after.items() if k!='area'}==before
        area=after['area']
        assert 0<=area['x']<area['x']+area['w']<=1080
        assert 0<=area['y']<area['y']+area['h']<=1350
    poster.apply_layout(params,'landscape')
    assert params=={**original,'layout':'landscape'}


def test_poster_reading_hold_reselects_real_cues_and_keeps_whole_speech():
    from backlot import studio_motion_poster_session as poster
    segments=[{'control':'polaroid','variant':'film','t0':0,'t1':6.4,'cues':[0,1,2]}]
    caps=[{'t0':i,'t1':i+.8,'zh':f'句{i}'} for i in range(6)]
    selected,maps=poster.fit_segments(segments,caps,6.4,{'polaroid':{'minDur':3}},
                                     cue_holds={0:[2,2,2]})
    assert selected[0]['cues']==[0,2,4]
    assert selected[0]['t1']==6.4 and maps[0]['captionIndices']==list(range(6))
    assert [(b['at'],b['until']) for b in maps[0]['beats']]==[(c['t0'],c['t1']) for c in caps]
    with pytest.raises(WorkError,match='不会截句或加速'):
        poster.fit_segments(segments,caps[:5],5,{'polaroid':{'minDur':3}},cue_holds={0:[2,2,2]})


def test_native_input_uses_new_instance_when_renderer_changes(env,monkeypatch,tmp_path):
    from backlot import studio_dark_native
    s,_,_,_=env;d=s.create(m.TEMPLATE_ID);d['source_review']='review'
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    before=s.input(d)['native_instance_root']
    original_sha=m.sha
    monkeypatch.setattr(m,'sha',lambda path:'f'*64 if Path(path)==Path(studio_dark_native.__file__) else original_sha(path))
    after=s.input(d)['native_instance_root']
    assert Path(before).parent==Path(after).parent and before!=after
    assert 'native_instance_root' not in d['input']


def test_changed_script_cannot_reuse_voice_or_review(env):
    s, _, _, _ = env; d = s.create(m.TEMPLATE_ID); d['source_review'] = 'review'; d['script'] = '别的声音'
    with pytest.raises(WorkError, match='不一致'): s.input(d)
    with pytest.raises(WorkError): s.review_sources(d['id'], 1, 'invented', [0], '素材合适')


@pytest.mark.parametrize('patch', [{'layout': '4:5'}, {'content': []}, {'content': {'s01': {}}}, {'sound': {'mode': 'voice'}}, {'selections': {'wall-0': float('nan')}}])
def test_invalid_edits_are_blocked_without_writes(env, patch):
    s, q, _, _ = env; d = s.create(m.TEMPLATE_ID)
    with pytest.raises(WorkError): s.patch(d['id'], 1, patch)
    assert s.get(d['id'])['revision'] == 1 and not q.list()['tasks']


def test_source_stage_quotes_once_and_uses_current_text(env, monkeypatch):
    s, _, _, _ = env; d = s.create(m.TEMPLATE_ID)
    d = s.patch(d['id'], 1, {'sound': {'mode': 'voice', 'modelId': 'haike/cosyvoice', 'voiceId': 'voice-a', 'rate': 1}})
    calls = []
    def quote(studio, draft, **kw):
        calls.append((draft, kw)); return {'id': 'quote-one', 'known_max_micros': 100, 'items': []}
    monkeypatch.setattr('backlot.studio_avatar.quote', quote)
    d = s.quote_source(d['id'], d['revision']); again = s.quote_source(d['id'], d['revision'])
    assert len(calls) == 1 and calls[0][1] == {'source_consumer': 'motion-template-source-v1'}
    assert calls[0][0]['input']['ai']['enabled'] is False and again['generation']['quote']['id'] == 'quote-one'
    d = s.patch(d['id'], again['revision'], {'script': '新的文案'})
    d = s.source_draft(d['id'], d['revision'])
    assert 'quote' not in d['generation'] and s.studio.draft(d['generation']['draft_id'])['text'] == '新的文案'


def test_paid_submit_is_explicit_frozen_and_idempotent(env, monkeypatch):
    s, q, _, _ = env; d = s.create(m.TEMPLATE_ID)
    d = s.patch(d['id'], 1, {'sound': {'mode': 'voice', 'modelId': 'haike/cosyvoice', 'voiceId': 'voice-a', 'rate': 1}})
    monkeypatch.setattr('backlot.studio_avatar.quote', lambda *a, **kw: {'id': 'quote', 'items': [], 'known_max_micros': 100})
    d = s.quote_source(d['id'], d['revision'])
    with pytest.raises(WorkError): s.submit_source(d['id'], d['revision'], q, 100, False)
    captured = []
    def frozen(studio, draft, identity, maximum):
        captured.append(maximum)
        return {'draft': draft, 'render_id': 'studio-'+str(draft['revision']), 'source_consumer': 'motion-template-source-v1'}
    monkeypatch.setattr('backlot.studio_avatar.frozen_request', frozen)
    d = s.submit_source(d['id'], d['revision'], q, 100, True)
    assert len(q.list()['tasks']) == 1
    again = s.submit_source(d['id'], d['revision'], q, 100, True)
    assert again['generation']['job_id'] == d['generation']['job_id'] and captured == [100]


def test_changed_text_cannot_submit_old_quote(env, monkeypatch):
    s, q, _, _ = env; d = s.create(m.TEMPLATE_ID)
    d = s.patch(d['id'], 1, {'sound': {'mode': 'voice', 'modelId': 'haike/cosyvoice', 'voiceId': 'v', 'rate': 1}})
    monkeypatch.setattr('backlot.studio_avatar.quote', lambda *a, **kw: {'id': 'old', 'items': []})
    d = s.quote_source(d['id'], d['revision']); d = s.patch(d['id'], d['revision'], {'script': '换了文案'})
    monkeypatch.setattr('backlot.studio_avatar.frozen_request', lambda *a: pytest.fail('must not submit old quote'))
    with pytest.raises(WorkError, match='报价'): s.submit_source(d['id'], d['revision'], q, 100, True)
    assert not q.list()['tasks']


def test_source_intent_identity_uses_original_portrait_not_later_badge_derivative(env, monkeypatch):
    s, _, _, seed = env; d = s.create(m.TEMPLATE_ID)
    d = s.patch(d['id'], 1, {'sound': {'mode': 'voice', 'modelId': 'haike/cosyvoice', 'voiceId': 'v', 'rate': 1}})
    monkeypatch.setattr('backlot.studio_avatar.quote', lambda *a, **kw: {'id': 'original', 'items': []})
    d = s.quote_source(d['id'], d['revision']); key = d['generation']['source_key']
    d['generation']['job_id'] = 'original-paid-job'
    d['input']['avatar']['badge'] = seed['media']['wall'][0]['source']
    d = s.put(d, d['revision'])
    result = s.source_draft(d['id'], d['revision'])
    assert result['generation']['source_key'] == key and result['generation']['job_id'] == 'original-paid-job'


def completed_source(env, monkeypatch):
    s,q,client,seed=env;source=s.create(m.TEMPLATE_ID)
    from lib.checkpoint import init_project
    project='fixture-source';init_project(project,title='完整源',pipeline_type='animated-explainer',pipeline_dir=q.projects_root)
    job=q.submit(project_id=project,kind='studio_avatar',source='workbench',priority='normal',parent_job_id='studio-1',
                 idempotency_key='completed-source',frozen_request={'source_consumer':'motion-template-source-v1'})
    q.claim_next('source-worker');q.finish(job['job_id'],'source-worker',status='completed',stage='源已完成')
    source['generation']={'job_id':job['job_id'],'draft_id':project,'revision':1,'quote':{'id':'old-fee'},
                          'portrait_source':seed['avatar']['badge'],'source_key':'old-key'}
    source['sound']={'mode':'voice','modelId':'haike/internal-tts','voiceId':'old-voice','rate':1}
    source['source_review']={'old':'approval'};source['run']={'old':'composition'};source=s.put(source,source['revision'])
    folder=q.projects_root/project/'renders/studio-1';folder.mkdir(parents=True)
    atomic_private(folder/'motion-template-source.json',{'contract':'motion-template-source-v1','script':source['script'],
                   'draft_id':project,'revision':1,'voice':seed['voice'],'avatar':seed['avatar'],'asr':{}})
    monkeypatch.setattr(m,'measured_captions',lambda *a:([{'startMs':0,'endMs':900,'text':'你好'}],
                                                      [{'start':0,'end':.9,'text':'你好'}]))
    monkeypatch.setattr(s.studio,'draft',lambda identity:{'input':{'portrait':{'id':'portrait'}}})
    monkeypatch.setattr(s.studio,'asset',lambda *a:m.verified(seed['avatar']['badge']))
    monkeypatch.setattr('backlot.studio_avatar.quote',lambda *a,**k:pytest.fail('reuse must not quote or charge'))
    return source,job


@pytest.mark.parametrize('target',['motiongit-native-story-v1','motiongit-console-story-v1','motiongit-poster-story-v1'])
def test_completed_source_can_enter_another_template_without_copying_fee_or_reviews(env,monkeypatch,target):
    s,q,client,seed=env;source,job=completed_source(env,monkeypatch)
    if target==m.console_session.ID:
        monkeypatch.setattr(m.console_session,'seed',lambda:deepcopy(seed))
        monkeypatch.setattr(m.console_session,'slots',lambda value:[])
    elif target==m.poster_session.ID:
        monkeypatch.setattr(m.poster_session,'seed',lambda:deepcopy(seed))
        monkeypatch.setattr(m.poster_session,'slots',lambda value:[])
    result=client.post('/api/studio/motion-templates/sessions',json={'template_id':target,'source_session_id':source['id']})
    assert result.status_code==200,result.text
    public=result.json();value=s.get(public['id'])
    assert public['source_origin']=={'session_id':source['id'],'title':source['title'],'job_id':job['job_id']}
    assert public['reuse_matches_script'] and public['sound']['mode']=='reuse'
    assert not public['generation']['quote'] and not public['generation']['job_id']
    assert not public['source_review_ready'] and not public['run']['job_id'] and not value.get('plan')
    assert value['input']['voice']==seed['voice'] and value['input']['avatar']['sha256']==seed['avatar']['sha256']
    assert value['source_receipt']==value['source_origin']['receipt']
    assert len(q.list()['tasks'])==1 and q.get(job['job_id'])['status']=='completed'
    if target==m.console_session.ID:
        assert value['input']['console']['cropCalibrationRequired']==seed['avatar']['sha256']


def test_completed_source_rejects_another_script_and_an_unfinished_source(env,monkeypatch):
    s,q,client,seed=env;source,job=completed_source(env,monkeypatch)
    url='/api/studio/motion-templates/sessions'
    assert client.post(url,json={'template_id':m.TEMPLATE_ID,'source_session_id':source['id'],'script':'另一条稿子'}).status_code==422
    unfinished=s.create(m.TEMPLATE_ID)
    assert client.post(url,json={'template_id':m.TEMPLATE_ID,'source_session_id':unfinished['id']}).status_code==422
    assert client.post(url,json={'template_id':m.TEMPLATE_ID,'source_session_id':'../../outside'}).status_code==422
    assert len(q.list()['tasks'])==1


@pytest.mark.parametrize('problem',['unfinished_job','receipt_script','tampered_voice'])
def test_completed_source_rechecks_job_receipt_and_asset_identity(env,monkeypatch,problem):
    s,q,client,seed=env;source,job=completed_source(env,monkeypatch)
    if problem=='unfinished_job':
        original=q.get
        monkeypatch.setattr(q,'get',lambda identity:{**original(identity),'status':'running'})
    elif problem=='receipt_script':
        path=q.projects_root/'fixture-source/renders/studio-1/motion-template-source.json'
        receipt=json.loads(path.read_text(encoding='utf-8'));receipt['script']='另一个源';atomic_private(path,receipt)
    else:Path(seed['voice']['path']).write_bytes(b'changed after source completion')
    response=client.post('/api/studio/motion-templates/sessions',json={'template_id':m.TEMPLATE_ID,'source_session_id':source['id']})
    assert response.status_code==422 and len(q.list()['tasks'])==1
    assert s.get(source['id'])==source


def test_consuming_console_source_never_reuses_old_person_crop(env,monkeypatch):
    s,_,_,seed=env;d=s.create(m.TEMPLATE_ID)
    d['template_id']=m.console_session.ID
    d['input']['console']={'presenterCrop':{'cx':.2,'cy':.3,'h':.2},'cropCalibration':{'path':'old-person'},
                         'presenterFraming':{'path':'old-framing'}}
    d['generation']={'job_id':'completed-fixture','draft_id':'fixture-source','revision':1}
    folder=s.studio.projects_root/'fixture-source/renders/studio-1';folder.mkdir(parents=True)
    atomic_private(folder/'motion-template-source.json',{'contract':'motion-template-source-v1',
        'script':d['script'],'draft_id':'fixture-source','revision':1,
        'voice':seed['voice'],'avatar':seed['avatar'],'asr':{}})
    monkeypatch.setattr(m,'measured_captions',lambda *a:([{'startMs':0,'endMs':900,'text':'你好'}],
                                                      [{'start':0,'end':.9,'text':'你好'}]))
    monkeypatch.setattr(s.studio,'draft',lambda identity:{'input':{'portrait':{'id':'portrait'}}})
    monkeypatch.setattr(s.studio,'asset',lambda *a:m.verified(seed['avatar']['badge']))
    q=SimpleNamespace(get=lambda identity:{'status':'completed'})
    result=s.consume_source(d,q);console=result['input']['console']
    assert console['cropCalibrationRequired']==seed['avatar']['sha256']
    assert 'cropCalibration' not in console and console['presenterCrop']=={'cx':.5,'cy':.5,'h':.4}
    assert console['presenterFramingRequired']==seed['avatar']['sha256'] and 'presenterFraming' not in console
    # Re-reading the identical completed paid source preserves later calibration.
    console.update(presenterCrop={'cx':.51,'cy':.4,'h':.38},cropCalibration={'path':'current-proof'})
    assert s.consume_source(result,q)['input']['console']['cropCalibration']=={'path':'current-proof'}


def test_approved_render_uses_existing_native_or_adapted_queue_once(env, monkeypatch):
    s, q, _, _ = env; d = s.create(m.TEMPLATE_ID)
    for engine, adapter in [('native', 'studio_dark_native'), ('adapted', 'studio_dark_full')]:
        frozen = {'project_id': 'studio-'+('1' if engine == 'native' else '2')*16, 'render_id': engine, 'request_sha256': engine*10, 'contract': engine}
        from lib.checkpoint import init_project
        init_project(frozen['project_id'], title='模板', pipeline_type='animated-explainer', pipeline_dir=q.projects_root)
        path = s.folder(d['id'])/(engine+'.json'); atomic_private(path, frozen)
        d.update(status='ready_to_render', run={k:frozen[k] for k in ['project_id','render_id','request_sha256','contract']}, frozen={'request':str(path),'engine':engine})
        d = s.put(d, d['revision'])
        def submit(queue, r):
            return queue.submit(project_id=r['project_id'], kind='studio_investment_recompose', source='workbench', priority='normal', parent_job_id=r['render_id'], idempotency_key=r['contract']+r['request_sha256'], frozen_request=r, start_paused=True)
        monkeypatch.setattr('backlot.'+adapter+'.submit', submit)
        d = s.submit(d['id'], d['revision'], q); again = s.submit(d['id'], d['revision'], q)
        assert again['run']['job_id'] == d['run']['job_id']
    assert len(q.list()['tasks']) == 2


def test_asset_upload_stays_owned_and_clears_old_review(env):
    s, _, _, _ = env; d = s.create(m.TEMPLATE_ID)
    out = io.BytesIO(); Image.new('RGB', (400, 400), '#aabbcc').save(out, 'PNG')
    d['source_frames'] = {'token': 'old'}; d = s.put(d, 1)
    d = s.upload(d['id'], d['revision'], 'wall-0', 'my-source.png', 'image', out.getvalue())
    assert 'source_frames' not in d and Path(d['input']['media']['wall'][0]['source']['path']).is_relative_to(s.studio.projects_root)


def test_png_calibration_and_viewport_reviews_have_correct_media_type(env):
    s,_,client,_=env;d=s.create(m.TEMPLATE_ID)
    path=s.folder(d['id'])/'measured-face.png';Image.new('RGB',(360,640),'#226655').save(path)
    d['plan']={'images':[m.binding(path)]};d['preview_files']=[m.binding(path)];s.put(d,d['revision'])
    for suffix in ['review/plan/0','preview/0']:
        r=client.get(f"/api/studio/motion-templates/sessions/{d['id']}/{suffix}")
        assert r.status_code==200 and r.headers['content-type']=='image/png' and r.content.startswith(b'\x89PNG')


def test_template_preset_is_public_parameters_and_version_bound(env):
    s, _, _, _ = env; d = s.create(m.TEMPLATE_ID)
    with pytest.raises(WorkError): s.save_preset(d['id'], 1, '亲子')
    d['run'] = {'request_sha256': 'reviewed'}; d['layout'] = 'portrait45'; d = s.put(d, 1)
    p = s.save_preset(d['id'], d['revision'], '亲子4:5')
    assert 'input' not in p and 'voice' not in p['parameters']
    reused = s.create(m.TEMPLATE_ID, preset_id=p['id'])
    assert reused['layout'] == 'portrait45' and reused['id'] != d['id']


def test_preparation_claim_survives_process_gap_and_rejects_live_duplicate(env, monkeypatch):
    s, q, _, _ = env; d = s.create(m.TEMPLATE_ID)
    d['operation'] = {'kind': 'prepare', 'status': 'running'}; d = s.put(d, d['revision'])
    launched = []
    monkeypatch.setattr(web.threading, 'Thread', lambda **kw: SimpleNamespace(start=lambda: launched.append(kw)))
    try:
        first = web.start_operation(s, q, d['id'], d['revision'], 'prepare', lambda rev: None)
        assert len(launched) == 1
        with pytest.raises(WorkError, match='正在准备'):
            web.start_operation(s, q, d['id'], first['revision'], 'prepare', lambda rev: None)
    finally: web._ACTIVE_PREPARATIONS.discard(d['id'])


def test_source_audio_alignment_keeps_complete_pcm_and_common_frame_clock(tmp_path):
    from backlot.studio_avatar import prepare_audio
    source = tmp_path/'source.wav'; samples = 24241
    with wave.open(str(source), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000); f.writeframes(b'\x10\x00'*samples)
    original = tmp_path/'regular.wav'; common = tmp_path/'common.wav'
    a = prepare_audio(source, original); b = prepare_audio(source, common, frame_quantum=5)
    assert a >= samples/24000 and b >= a and round(b*25)%5 == 0 and abs(b*60-round(b*60)) < 1e-8
    with wave.open(str(common), 'rb') as f:
        data = f.readframes(f.getnframes())
    assert data[:samples*2] == b'\x10\x00'*samples and not any(data[samples*2:])
