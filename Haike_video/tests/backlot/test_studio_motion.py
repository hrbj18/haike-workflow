"""Motion boundaries: owned assets, exact clock, immutable review and no paid calls."""
import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backlot.studio import Studio
from backlot.studio_api import router
from backlot import studio_motion as m
from backlot.studio_motion_quick import DEFINITIONS, options
from backlot.work_catalog import WorkError


@pytest.fixture
def setup(tmp_path,monkeypatch):
    s=Studio(tmp_path/'projects')
    monkeypatch.setattr(m,'runtime',lambda:tmp_path)
    monkeypatch.setattr(m,'capabilities',lambda layout:{'groups':[]})
    monkeypatch.setattr(m,'media_probe',lambda path:{'duration':6.56,'format':{'start_time':'0'},'video':{'duration':'6.52'},'audio':{'codec_type':'audio'}})
    d=s.save_draft({'template_id':m.TEMPLATE_ID,'text':'本期完整口播','title':'验收'})
    video=s.projects_root/d['id']/'assets/studio/source.mp4';video.parent.mkdir(parents=True);video.write_bytes(b'owned-source')
    with s.db() as db:db.execute('INSERT INTO studio_assets VALUES(?,?,?,?,?)',('owned-video',d['id'],'口播.mp4','video',str(video)))
    values={'source':{'id':'owned-video'},'motionLayout':'landscape','style':'quick','music':{'mode':'none'},'segments':[{'group':'quick:hero','text':d['text'],'end':391/60,'values':{'line1':'本期内容','line2':'完整观点'},'anchors':{'line1':0,'line2':1.2}}]}
    d=s.save_draft({**d,'input':values})
    return s,d,video


def test_real_video_clock_beats_longer_audio_container():
    info={'duration':6.56,'format':{'start_time':'0'},'video':{'duration':'6.52'}}
    assert m.narration_clock(info)['frames']==391
    info['video']['start_time']='.5';info['format']['start_time']='.5'
    assert m.narration_clock(info)['frames']==391
    info['video']['start_time']='.6'
    assert m.narration_clock(info)['frames']==397
    with pytest.raises(WorkError):m.narration_clock({**info,'video':{'duration':'NaN'}})


def test_comparison_preserves_meaning_asset_identity_and_exact_role_names():
    base={'id':'first:group','style':'first','intents':['proof'],'phases':['entry','reading'],'counts':{'items':{'min':3,'max':3}},'cueRoles':{'show':'entry'},'fields':[{'id':'headline','inputPath':'title','type':'text'}]}
    same={**base,'id':'second:group','style':'second','fields':[{'id':'different-id','inputPath':'title','type':'text'}]}
    changed={**same,'id':'third:group','style':'third','counts':{'items':{'min':4,'max':4}}}
    missing={**same,'id':'fourth:group','style':'fourth','fields':[{'id':'image','type':'image','required':True}]}
    result=m.compatible_candidates(base,{g['id']:g for g in [base,same,changed,missing]},{'headline':'本期证据'})
    assert set(result)=={'first:group','second:group'}
    assert result['second:group']['slots']['different-id']=='本期证据'


@pytest.mark.parametrize('patch,message',[
    ({'segments':[{'group':'quick:hero','text':'丢掉原文','end':6}]},'完整覆盖'),
    ({'music':{'mode':''}},'请选择本期配乐'),
    ({'motionLayout':'portrait'},'不支持当前画幅'),
    ({'segments':[{'group':'quick:hero','text':'本期完整口播','end':6}]},'口播结尾'),
])
def test_incomplete_inputs_block_before_renderer(setup,tmp_path,patch,message):
    s,d,_=setup;d={**d,'input':{**d['input'],**patch}}
    with pytest.raises(WorkError,match=message):m.brief(s,d,tmp_path)


def test_review_freezes_content_clock_and_source(setup):
    s,d,video=setup;p=m.plan(s,d)
    assert p['report']['ready'] and p['cost_micros']==0
    frozen=m.freeze(s,d,p['id'],True)
    assert frozen['draft']==d
    with pytest.raises(WorkError,match='确认'):m.freeze(s,d,p['id'],False)
    with pytest.raises(WorkError,match='已改变'):m.freeze(s,{**d,'title':'改标题'},p['id'],True)
    video.write_bytes(b'changed-source')
    with pytest.raises(WorkError,match='来源已改变'):m.freeze(s,d,p['id'],True)


def test_plan_tampering_is_blocked(setup):
    s,d,_=setup;p=m.plan(s,d)
    plan=s.projects_root/d['id']/'assets/motion-plans'/p['id']/'planning/auto_plan.json'
    saved=json.loads(plan.read_text());saved['quickScenes'][0]['options']['lines'][0][0]='tampered'
    plan.write_text(json.dumps(saved))
    with pytest.raises(WorkError,match='计划已改变'):m.freeze(s,d,p['id'],True)


def test_subtitles_preserve_half_open_clock_and_reject_overlap(setup,tmp_path):
    s,d,_=setup
    cues=[{'start':0,'end':1.4,'text':'本期','en':'This episode'},{'start':1.4,'end':391/60,'text':'完整口播','en':''}]
    m.brief(s,{**d,'input':{**d['input'],'captions':cues}},tmp_path)
    assert 'This episode' in (tmp_path/'subs.js').read_text()
    cues[1]['start']=1.3
    with pytest.raises(WorkError,match='不能重叠'):
        m.brief(s,{**d,'input':{**d['input'],'captions':cues}},tmp_path)


def bundle(entries):
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as z:
        for name,value in entries:z.writestr(name,value)
    return data.getvalue()


def test_sequence_unpack_and_owned_access(setup):
    s,d,_=setup;png=io.BytesIO();Image.new('RGB',(32,32),'navy').save(png,'PNG')
    asset=m.save_bundle(s,d['id'],'frames.zip',bundle([('frames/f_00001.png',png.getvalue()),('frames/f_00002.png',png.getvalue())]))
    assert asset['files']==2
    bound=m.owned_value(s,d,{'asset':asset,'entityId':'same-product'},'sequence')
    assert Path(bound['path']).is_dir() and bound['entityId']=='same-product'
    other=s.save_draft({'template_id':m.TEMPLATE_ID})
    with pytest.raises(WorkError):m.owned_value(s,other,{'asset':asset},'sequence')
    with pytest.raises(WorkError):m.owned_value(s,d,{'path':'/private/file'},'sequence')
    with pytest.raises(WorkError,match='不安全'):m.save_bundle(s,d['id'],'bad.zip',bundle([('../escape.png',png.getvalue())]))
    link=zipfile.ZipInfo('link.png');link.external_attr=(0o120777<<16)
    with pytest.raises(WorkError,match='链接'):m.save_bundle(s,d['id'],'bad.zip',bundle([(link,b'target')]))


@pytest.mark.parametrize('kind',list(DEFINITIONS))
def test_all_nine_tpl_bind_actual_values_and_cues(kind):
    fields,roles=DEFINITIONS[kind];values={}
    for f in fields:
        values[f['id']]=3 if f['type']=='number' else {'path':'/owned/product.png'} if f['type']=='image' else '本期内容'
    for key in ('cards','leftItems','rightItems','steps','lines','features','items'):
        if key in values:values[key]='第一项\n第二项'
    scene={'group':'quick:'+kind,'slots':values,'anchors':{r:{'at':.8+i*.3} for i,r in enumerate(roles)}}
    result=options(scene,10,18)
    assert result['kind']==kind and result['options']['t0']==10
    if roles:
        scene['anchors']={}
        with pytest.raises(WorkError,match='落点'):options(scene,10,18)


def test_tpl_never_executes_plain_content_markup():
    scene={'group':'quick:hero','slots':{'line1':'<svg/onload=x>','line2':'本期内容'},'anchors':{'line1':{'at':0},'line2':{'at':1}}}
    result=options(scene,0,6)
    assert '<svg' not in result['options']['lines'][0][0] and '&lt;svg' in result['options']['lines'][0][0]


def test_long_list_copy_is_blocked_without_rewriting_narration():
    scene={'group':'quick:checklist','slots':{'title':'本期清单','items':'字'*17},'anchors':{'item1':{'at':0}}}
    with pytest.raises(WorkError,match='每行最多16字'):
        options(scene,0,6)


def test_outro_textcontent_preserves_literal_symbols():
    scene={'group':'quick:outro','slots':{'title':'本期','lines':'本期内容','prompt':'A & B < C'},'anchors':{}}
    assert options(scene,0,6)['options']['prompt']=='A & B < C'


def test_http_mutation_and_stale_revision_do_not_run_engine(setup,monkeypatch):
    s,d,_=setup;app=FastAPI();app.state.studio=s;app.state.works_projects_root=s.projects_root;app.include_router(router)
    client=TestClient(app)
    monkeypatch.setattr(m,'command',lambda *a,**k:pytest.fail('must not invoke engine'))
    assert client.post('/api/studio/motion/doctor',json={},headers={'Origin':'https://foreign.test'}).status_code==403
    assert client.post(f"/api/studio/drafts/{d['id']}/motion-plan",json={'revision':0}).status_code==409
    assert client.get(f"/api/studio/drafts/{d['id']}/motion-project/999").status_code==404


def test_empty_saved_draft_restores_no_job_without_a_project_folder(setup,monkeypatch,tmp_path):
    from backlot.production_queue import ProductionQueue
    from backlot import server
    s,d,_=setup;empty=s.save_draft({'template_id':m.TEMPLATE_ID})
    queue=ProductionQueue(tmp_path/'queue.sqlite',s.projects_root)
    monkeypatch.setattr(server,'_ensure_production_queue',lambda app:queue)
    app=FastAPI();app.state.studio=s;app.include_router(router)
    response=TestClient(app).get(f"/api/studio/drafts/{empty['id']}/motion-job")
    assert response.status_code==200 and response.json()=={'job':None}
