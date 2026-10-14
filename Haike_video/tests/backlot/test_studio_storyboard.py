import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from backlot.studio import Studio, atomic_private
from backlot.studio_storyboard import TrialRelay, options, resolve_scene, status, validate_plan, produce, verify_spoken_script, motion_clock_segments, image_identity
from backlot.work_catalog import WorkError


@pytest.fixture
def data(tmp_path):
    s = Studio(tmp_path / 'projects')
    config={'base_url':'https://supplier.example/v1','api_key':'test-private-value','image_verified':True}
    config['image_verified_for']=image_identity(config)
    atomic_private(s.private / 'studio-ai/relay.json', config)
    d = s.save_draft({'template_id':'avatar-safe-circle-v1','title':'测试','text':'第一句。第二句。','input':{'ai':{'enabled':True,'materials':[],'allow_images':True,'max_images':2}}})
    cues = [{'text':'第一句。','startMs':20,'endMs':1500},{'text':'第二句。','startMs':1700,'endMs':3100}]
    raw = {'scenes':[{'from_cue':0,'to_cue':0,'script_start':0,'script_end':4,'label':'第一镜','asset_id':'','query':'technology','illustration_prompt':'示意插画','reason':'缺少可用用户素材'},
                     {'from_cue':1,'to_cue':1,'script_start':4,'script_end':8,'label':'第二镜','asset_id':'','query':'computer','illustration_prompt':'示意插画','reason':'缺少可用用户素材'}]}
    return s,d,cues,raw


def test_server_binds_contiguous_real_clock(data):
    s,d,cues,body = data
    scenes = validate_plan(body,d,cues,3.2)
    assert [(x['start'],x['end']) for x in scenes] == [(0,1.7),(1.7,3.2)]
    assert ''.join(x['text'] for x in scenes) == d['text']
    assert status(s)['customer_charge_micros'] == '0' and status(s)['procurement_price'] is None
    assert 'test-private-value' not in json.dumps(status(s))


def test_storyboard_uses_asr_sentence_clock_not_caption_wrap_interpolation():
    from backlot.studio_avatar import captions
    result={'segments':[{'start':.25,'end':4.9,'text':'这是一句超过十八个字的长口播用于确认真实句级时钟没有被按字数拆开。'}]}
    assert len(captions(result,5))>1
    exact=captions(result,5,split=False)
    assert len(exact)==1 and exact[0]['startMs']==250 and exact[0]['endMs']==4900


def test_real_audio_and_script_must_describe_same_speech():
    verify_spoken_script('海客科技，让创作更简单。',[{'text':'海客科技让创作更简单'}])
    with pytest.raises(WorkError,match='不一致'):
        verify_spoken_script('今天讲工业生产流程',[{'text':'用户素材优先缺少素材再补充示意插画'}])


def test_25fps_drive_is_mapped_to_observed_60fps_tail():
    segments=[{'text':'一','end':1.73},{'text':'二','end':5.12}]
    result=motion_clock_segments(segments,308)
    assert result[0]['end']==104/60 and result[-1]['end']==308/60
    assert ''.join(s['text'] for s in result)=='一二'
    with pytest.raises(WorkError,match='过短'):motion_clock_segments([{'end':.001},{'end':5.12}],308)


@pytest.mark.parametrize('change',[{'from_cue':1},{'to_cue':9},{'script_start':2},{'asset_id':'foreign'},{'path':'../../etc/passwd'},{'from_cue':False}])
def test_invalid_plan_never_reaches_renderer(data,change):
    _,d,cues,body=data; body['scenes'][0].update(change)
    with pytest.raises(WorkError): validate_plan(body,d,cues,3.2)


def test_must_and_reference_materials_are_enforced(data):
    _,d,cues,body=data
    d['input']['ai']['materials']=[{'id':'local','mode':'must'}]
    with pytest.raises(WorkError,match='遗漏'): validate_plan(body,d,cues,3.2)
    body['scenes'][0]['asset_id']='local'
    assert validate_plan(body,d,cues,3.2)[0]['asset_id']=='local'
    d['input']['ai']['materials'][0]['mode']='reference'
    with pytest.raises(WorkError,match='仅供参考'): validate_plan(body,d,cues,3.2)


def test_materials_require_ownership_and_rights(data):
    s,d,_,_=data; b=io.BytesIO();Image.new('RGB',(300,300)).save(b,format='PNG')
    a=s.save_asset(d['id'],'test.png','image',b.getvalue())
    d['input']['ai']['materials']=[{**a,'mode':'prefer','rights_confirmed':False}]
    with pytest.raises(WorkError,match='使用权'): options(s,d)
    d['input']['ai']['materials'][0]['rights_confirmed']=True
    assert options(s,d)
    other=s.save_draft({'template_id':'avatar-safe-circle-v1','title':'其他','input':{}})
    other['input']['ai']=d['input']['ai']
    with pytest.raises(WorkError,match='不属于'): options(s,other)


def test_source_order_and_no_paid_fallback_on_login_failure():
    calls=[]
    def source(name,result):
        def run(_):calls.append(name);return result
        return run
    sources=SimpleNamespace(douyin=source('douyin',None),pexels=source('pexels',None),illustration=source('image',{'id':'generated'}))
    scene={'illustration_prompt':'test'}; ai={'allow_images':True,'max_images':2}
    assert resolve_scene(scene,ai,sources)['id']=='generated'; assert calls==['douyin','pexels','image']
    calls.clear()
    def login(_):calls.append('login');raise WorkError('登录失效','unavailable')
    sources.douyin=login
    with pytest.raises(WorkError,match='登录'):resolve_scene(scene,ai,sources)
    assert calls==['login']
    calls.clear(); resolve_scene(scene,{**ai,'skip_douyin':True},sources);assert calls==['pexels','image']


def test_user_asset_bypasses_all_network_sources():
    def bad(_):raise AssertionError('unwanted network')
    sources=SimpleNamespace(douyin=bad,pexels=bad,illustration=bad)
    asset=resolve_scene({'asset_id':'local'},{'materials':[{'id':'local','mode':'must'}]},sources)
    assert asset['id']=='local' and asset['provenance']['source']=='user'


def test_image_cap_and_explicit_opt_in():
    bad=lambda _: (_ for _ in ()).throw(AssertionError('unwanted generation'))
    sources=SimpleNamespace(douyin=lambda _:None,pexels=lambda _:None,illustration=bad)
    for ai,count in [({},0),({'allow_images':True,'max_images':1},1)]:
        with pytest.raises(WorkError,match='未找到'):resolve_scene({'illustration_prompt':'test'},ai,sources,count)


def test_trial_cached_success_and_ambiguous_request_never_repeat(data,tmp_path):
    s,_,_,_=data; calls=[]
    def ok(payload,image):calls.append(payload);return {'choices':[{'message':{'content':'{}'}}],'usage':{'prompt_tokens':2}}
    r=TrialRelay(s,tmp_path/'calls',ok); payload={'model':'gpt-6-luna'}
    assert r.call('one',payload)==r.call('one',payload);assert len(calls)==1
    with pytest.raises(WorkError,match='冻结'): r.call('one',{'model':'changed'})
    def timeout(payload,image):calls.append(payload);raise TimeoutError()
    r.transport=timeout
    with pytest.raises(WorkError,match='待核对'):r.call('unknown',payload)
    with pytest.raises(WorkError,match='未重复'):r.call('unknown',payload)
    assert len(calls)==2


def test_trial_daily_limits_are_durable(data,tmp_path):
    s,_,_,_=data
    from backlot.studio import timestamp
    atomic_private(s.private/'studio-ai/trial-budget.json',{'day':timestamp()[:10],'requests':50,'images':0})
    r=TrialRelay(s,tmp_path/'calls',lambda *_:(_ for _ in ()).throw(AssertionError()))
    with pytest.raises(WorkError,match='今日'):r.call('over-limit',{'model':'gpt-6-luna'})
    assert not list(r.folder.glob('*.json'))


@pytest.mark.parametrize('change',[{'image_model':'gpt-image-1.5'}, {'api_key':'another-private-value'}, {'base_url':'https://another.example/v1'}])
def test_probe_cannot_enable_a_different_model_or_destination(data,change):
    s,d,_,_=data
    assert status(s)['image_verified']
    path=s.private/'studio-ai/relay.json'; c=json.loads(path.read_text()); c.update(change); atomic_private(path,c)
    assert not status(s)['image_verified']
    with pytest.raises(WorkError,match='尚未验收'):options(s,d)


def test_fallback_model_never_resubmits_an_unknown_original_request(data,tmp_path):
    s,_,_,_=data;calls=[]
    def failed(payload,image):calls.append(payload['model']);raise TimeoutError()
    relay=TrialRelay(s,tmp_path/'calls',failed);stage='illustration-scene-1'
    payload={'model':'gpt-image-2','prompt':'test'}
    with pytest.raises(WorkError):relay.call(stage,payload,image=True)
    path=s.private/'studio-ai/relay.json';c=json.loads(path.read_text());c.update(image_model='gpt-image-1.5');atomic_private(path,c)
    assert relay.image_model_for_stage(stage)=='gpt-image-2'
    assert relay.image_model_for_stage('illustration-scene-2')=='gpt-image-2'
    assert TrialRelay(s,tmp_path/'new-job').image_model_for_stage('illustration-scene-1')=='gpt-image-1.5'
    with pytest.raises(WorkError,match='未重复'):relay.call(stage,payload,image=True)
    assert calls==['gpt-image-2']


def test_switching_image_model_preserves_successful_receipt_identity(data,tmp_path):
    s,_,_,_=data
    relay=TrialRelay(s,tmp_path/'calls',lambda *_:{'data':[{'b64_json':'fixture'}]})
    stage='illustration-scene-1'
    relay.call(stage,{'model':'gpt-image-1.5'},image=True)
    assert relay.image_model_for_stage(stage)=='gpt-image-1.5'


def test_only_a_valid_probe_can_enable_the_configured_image_model(data,monkeypatch):
    from scripts.configure_studio_ai import verify_image
    s,_,_,_=data;path=s.private/'studio-ai/relay.json';c=json.loads(path.read_text())
    c.update(image_model='gpt-image-1.5',image_verified=False);atomic_private(path,c)
    image=io.BytesIO();Image.new('RGB',(1024,1536)).save(image,format='PNG')
    import base64
    def fake(self,stage,payload,image=False):
        assert payload['model']=='gpt-image-1.5' and image
        return {'data':[{'b64_json':base64.b64encode(image_bytes).decode()}],'usage':{'input_tokens':1,'output_tokens':2}}
    image_bytes=image.getvalue();monkeypatch.setattr(TrialRelay,'call',fake)
    verify_image(s,'one-explicit-test')
    assert status(s)['image_verified'] and status(s)['image_model']=='gpt-image-1.5'
    c=json.loads(path.read_text());c.update(image_model='gpt-image-1');atomic_private(path,c)
    with pytest.raises(ValueError,match='绑定'):verify_image(s,'one-explicit-test')


def test_unified_avatar_motion_result_is_recovered_after_restart(tmp_path):
    from backlot.production_queue_worker import ProductionQueueWorker
    root=tmp_path/'projects';output=root/'demo/renders/studio-1';output.mkdir(parents=True)
    (output/'motion-preview.mp4').write_bytes(b'test-render');(output/'qa.json').write_text('{}')
    worker=ProductionQueueWorker(None,root)
    job={'project_id':'demo','kind':'studio_avatar','frozen_request':{'render_id':'studio-1','draft':{'input':{'motion':{'style':'01-D'}}}}}
    result=worker.inspect_parent(job)
    assert result['status']=='completed' and result['result']['output_path'].endswith('motion-preview.mp4')


def test_expired_quote_renewal_cannot_change_customer_approval():
    from backlot.studio_avatar import renew_if_expired
    q={'id':'original','model':'haike/avatar','price':{'version':1},'quoted_usage':{'tasks':1},'max_charge_micros':'100','expires_at':'2020-01-01T00:00:00+00:00'}
    calls=[]
    def request(path,body):calls.append((path,body));return {**q,'expires_at':'2099-01-01T00:00:00+00:00'}
    sdk=SimpleNamespace(request=request)
    assert renew_if_expired(sdk,q)['id']=='original' and len(calls)==1
    sdk.request=lambda *_:{**q,'max_charge_micros':'101'}
    with pytest.raises(WorkError,match='改变'):renew_if_expired(sdk,q)


def test_pipeline_resumes_completed_scenes_without_researching(data,tmp_path,monkeypatch):
    s,d,cues,body=data
    b=io.BytesIO();Image.new('RGB',(300,300)).save(b,format='PNG')
    a=s.save_asset(d['id'],'test.png','image',b.getvalue())
    plan={'scenes':validate_plan(body,d,cues,3.2),'duration':3.2}
    monkeypatch.setattr('backlot.studio_storyboard.make_plan',lambda *_:plan)
    calls=[]
    def resolve(scene,*_):
        calls.append(scene['id'])
        if len(calls)==2:raise WorkError('需要登录抖音','unavailable')
        return {**a,'provenance':{'source':'user'}}
    monkeypatch.setattr('backlot.studio_storyboard.resolve_scene',resolve)
    with pytest.raises(WorkError):produce(s,d,tmp_path/'render',cues,3.2,None)
    result=produce(s,d,tmp_path/'render',cues,3.2,None)
    assert result['status']=='ready' and calls==['scene-1','scene-2','scene-2']
