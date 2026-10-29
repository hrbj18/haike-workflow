"""Full-group/source/queue regression tests. Fixtures are not real video QA."""
from copy import deepcopy
import math
from pathlib import Path
import shutil
import wave

import pytest
from PIL import Image

from backlot import studio_dark_full as dark
from backlot.production_queue import ProductionQueue
from backlot.work_catalog import WorkError, sha


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(dark,'CACHE_ROOT',tmp_path/'persistent-cache')
    voice=tmp_path/'voice.wav'
    with wave.open(str(voice),'wb') as out:
        out.setparams((1,2,24000,0,'NONE',''));out.writeframes(b'\x10\x01'*840000)
    font=next((p for p in [Path('C:/Windows/Fonts/msyh.ttc'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')] if p.is_file()),None)
    if not font:pytest.skip('No fixture font installed')
    paths={'voice.wav':voice,'body.ttf':font,'display.ttf':font};media=[];reviews=[]
    for i in range(3):
        path=tmp_path/f'm{i}.jpg';Image.new('RGB',(800,450),'#6C7D71').save(path);paths[path.name]=path
        media.append({'id':f'm{i}','src':path.name,'thumbnail':path.name,'kind':'image','offset':0,'fit':'contain'})
        reviews.append({'id':f'm{i}','source_sha256':sha(path),'thumbnail_sha256':sha(path),'reviewed':True,'description':'Isolated fixture; no actual visual claim'})
    value={'title':'isolated full contract','props':{'variant':'hedgerow','brand':'Haike','header':'Test','footer':'Test',
        'fontAssets':{'body':'body.ttf','display':'display.ttf'},'media':media,
        'captions':[{'text':'fixture','startMs':0,'endMs':35000}]},
        'sources':{n:str(p) for n,p in paths.items()},'audio':{'voice':'voice.wav','tailSeconds':.25},
        'shotPlan':[{'id':'a','group':'s01','mediaIds':['m0','m1','m2'],'mainMediaId':'m0','content':{},'weight':1},
                    {'id':'b','group':'s04','mediaIds':['m0','m1','m2'],'mainMediaId':'m0','content':{},'weight':3},
                    {'id':'c','group':'s08','mediaIds':['m0','m1','m2'],'content':{},'weight':2}],
        'provenance':{'voice':{'source':'test generated PCM','authorized':True,'sha256':sha(voice)},
                      'captions':{'voice_sha256':sha(voice),'method':'test fixture only'},'audio':{},'media':reviews}}
    monkeypatch.setattr(dark,'runtime',lambda:{'fixture-source':'a'*64})
    return value,ProductionQueue(tmp_path/'queue.sqlite3',tmp_path/'projects')


def test_real_pcm_full_clock_and_contiguous_atomic_groups(fixture):
    value,_=fixture;n=dark.preflight(value);p=n['props'];scenes=p['scenes']
    assert p['durationFrames']==1058
    assert n['audio']['voice_clock']['samples']==840000
    assert [s['group'] for s in scenes]==['s01','s04','s08']
    assert sum(s['frames'] for s in scenes)==1058
    assert all(a['from']+a['frames']==b['from'] for a,b in zip(scenes,scenes[1:]))
    assert scenes[-1]['cueTimes']['comments']<=scenes[-1]['frames']/30-1.25


def test_native_story_reflows_in_actual_portrait_canvas_at_sixty_fps(fixture):
    value,_=fixture;value['props']['variant']='native-story'
    n=dark.preflight(value);p=n['props']
    assert (p['width'],p['height'],p['fps'])==(1440,1800,60)
    assert p['durationFrames']==2116
    assert p['durationFrames']/60==n['audio']['durationFrames']/30
    assert sum(s['frames'] for s in p['scenes'])==p['durationFrames']
    assert [s['group'] for s in p['scenes']]==['s01','s04','s08']


def test_native_story_blocks_groups_outside_its_actual_layout_scope(fixture):
    value,_=fixture;value['props']['variant']='native-story'
    value['shotPlan']=[{'id':'unsupported','group':'s06','mediaIds':['m0'],'content':{}}]
    with pytest.raises(WorkError,match='只开放已适配'):
        dark.preflight(value)


def test_sixty_fps_presenter_proof_uses_same_seconds_in_shared_checker(fixture,monkeypatch,tmp_path):
    value,_=fixture;value['props']['variant']='native-story'
    n=dark.preflight(value);p=n['props'];video=tmp_path/'presenter.mp4';video.write_bytes(b'fixture-only')
    p['presenter']={'src':video.name,'from':0,'frames':p['durationFrames'],'offset':0,
                    'modes':[{'from':0,'frames':p['durationFrames'],'mode':'small'}]}
    n['paths'][video.name]=video
    n['provenance']['presenterClips']=[{'id':'presenter','globalFrom':0,'frames':p['durationFrames'],'sourceOffset':0}]
    captured={}
    def validate(mapped,audio,paths,provenance,**kwargs):
        captured.update(mapped=mapped,provenance=provenance);return {}
    monkeypatch.setattr(dark.speech,'_validate_sources',validate)
    dark._source_check(p,n['audio'],n['paths'],n['provenance'],fonts=False)
    clip=captured['mapped']['presenterClips'][0];proof=captured['provenance']['presenterClips'][0]
    assert clip['frames']==proof['frames']==1058
    assert clip['frames']/30==p['presenter']['frames']/60
    assert n['provenance']['presenterClips'][0]['frames']==2116


def test_reading_minimum_blocks_forced_thirty_second_ten_group_plan():
    shots=[{'id':g['id'],'group':g['id'],'content':{},'mediaIds':[]} for g in dark.catalog()['groups']]
    with pytest.raises(WorkError,match='完整动作保护时长'):
        dark.plan_shots(shots,900,30)


def test_tail_action_fixed_duration_is_protected():
    for group,key,tail in [('s05','lane_result',1.1),('s06','account_commit',.8),('s07','code_video',.7),('s08','comments',1.25)]:
        definition=next(g for g in dark.catalog()['groups'] if g['id']==group)
        frames=math.ceil(definition['minimumProjectSeconds']*30)
        scene=dark.plan_shots([{'id':'test','group':group,'mediaIds':[],'content':{}}],frames,30)[0]
        assert scene['cueTimes'][key]+tail<=frames/30+.000001


def test_reference_cannot_omit_or_reorder_groups(fixture):
    value,_=fixture;p=dark.preflight(value)['props'];p.update(variant='reference',width=1920,height=1080,fps=60,durationFrames=7344)
    # Even valid individual groups cannot masquerade as the complete reference.
    p['scenes']=dark.plan_shots(value['shotPlan'],7344,60)
    with pytest.raises(WorkError,match='完整原版'):
        dark.validate_props(p,122.4)


def test_s02_s03_are_a_required_continuous_pair(fixture):
    value,_=fixture;value['shotPlan']=[{'id':'s02','group':'s02','mediaIds':['m0'],'mainMediaId':'m0','content':{}}]
    with pytest.raises(WorkError,match='须接同一中央素材'):
        dark.preflight(value)


def test_fake_or_missing_source_review_is_blocked(fixture):
    value,_=fixture;value['provenance']['media'][0]['reviewed']=False
    with pytest.raises(WorkError,match='未看帧'):
        dark.preflight(value)


def test_freeze_copy_idempotent_queue_and_source_change(fixture):
    value,queue=fixture;r=dark.prepare(queue,value);same=dark.prepare(queue,value)
    assert r==same
    job=dark.submit(queue,r);assert dark.submit(queue,r)['job_id']==job['job_id']
    assert job['status']=='paused'
    source=Path(r['asset_directory'])/'m0.jpg'
    Image.new('RGB',(800,450),'red').save(source)
    with pytest.raises(WorkError,match='冻结素材已变化'):
        dark.validate(queue,r)


def test_changed_incomplete_runtime_requires_new_identity(fixture,monkeypatch):
    value,queue=fixture;r=dark.prepare(queue,value)
    monkeypatch.setattr(dark,'runtime',lambda:{'fixture-source':'b'*64})
    with pytest.raises(WorkError,match='模板源码或依赖已改变'):
        dark.validate(queue,r)


def test_completed_artifact_survives_cache_relocation_but_not_tampering(fixture,monkeypatch,tmp_path):
    from backlot.studio import atomic_private
    value,queue=fixture;r=dark.prepare(queue,value)
    folder=queue.projects_root/r['project_id']/'renders'/r['render_id'];folder.mkdir(parents=True)
    for name in [dark.OUTPUT_FILE,'quality.json','audio-receipt.json']:
        (folder/name).write_bytes(b'isolated completed artifact')
    atomic_private(folder/'result.json',{'request_sha256':r['request_sha256'],
        'output_sha256':sha(folder/dark.OUTPUT_FILE),'quality_sha256':sha(folder/'quality.json'),
        'audio_receipt_sha256':sha(folder/'audio-receipt.json')})
    monkeypatch.setattr(dark,'CACHE_ROOT',tmp_path/'new-runtime-cache')
    assert dark.validate(queue,r)==queue.projects_root/r['project_id']
    (folder/dark.OUTPUT_FILE).write_bytes(b'tampered')
    with pytest.raises(WorkError,match='完成产物'):
        dark.validate(queue,r)


def test_caption_actual_font_width_blocks_overflow(fixture):
    value,_=fixture;value['props']['captions'][0]['text']='字'*40
    with pytest.raises(WorkError,match='实际字体字幕超宽'):
        dark.preflight(value)


@pytest.mark.parametrize('group',[g['id'] for g in dark.catalog()['groups']])
def test_each_group_minimum_retains_full_action_state_graph(group):
    definition=next(g for g in dark.catalog()['groups'] if g['id']==group)
    frames=math.ceil(definition['minimumProjectSeconds']*30-.00001)
    scene=dark.plan_shots([{'id':'test','group':group,'mediaIds':[],'content':{}}],frames,30)[0]
    dark.action_gate(scene,30,definition)


@pytest.mark.parametrize('fourth,wall,message',[(5.8,5.3,'节点顺序'),(5.1,5.3,'尚未完成就退场')])
def test_fourth_category_must_finish_before_wall_handoff(fixture,fourth,wall,message):
    value,_=fixture
    value['shotPlan'][1]['cueTimes']={'category_4':fourth,'wall_expand':wall}
    with pytest.raises(WorkError,match=message):dark.preflight(value)


def test_process_primary_binding_cannot_silently_remain_a_poster(fixture):
    value,_=fixture;p=dark.preflight(value)['props'];p['media'][2]['kind']='video'
    p['scenes']=dark.plan_shots([{'id':'process','group':'s07','mediaIds':['m0','m1','m2'],'mainMediaId':'m2','content':{}}],p['durationFrames'],30)
    with pytest.raises(WorkError,match='主素材/接力窗口'):dark.validate_props(p,35)


def test_nine_grid_focus_actual_video_offset_is_continuous(fixture):
    value,_=fixture;p=dark.preflight(value)['props'];p['media'][0]['kind']='video'
    p['scenes']=dark.plan_shots([{'id':g,'group':g,'mediaIds':['m0'],'mainMediaId':'m0','content':{}} for g in ['s02','s03']],p['durationFrames'],30)
    a,b=p['scenes']
    a['videoWindows']=[{'mediaId':'m0','from':0,'frames':a['frames'],'offset':0}]
    b['videoWindows']=[{'mediaId':'m0','from':0,'frames':b['frames'],'offset':0}]
    with pytest.raises(WorkError,match='接力源时钟不连续'):dark.validate_props(p,35)
    b['videoWindows'][0]['offset']=a['frames']/30
    dark.validate_props(p,35)


def test_process_clip_cannot_be_scheduled_after_phone_has_disappeared(fixture):
    value,_=fixture;p=dark.preflight(value)['props'];p['media'][0]['kind']='video'
    p['scenes']=dark.plan_shots([{'id':'process','group':'s07','mediaIds':['m0','m1'],'mainMediaId':'m0','content':{}}],p['durationFrames'],30)
    scene=p['scenes'][0];scene['videoWindows']=[{'mediaId':'m0','from':scene['frames']-1,'frames':1,'offset':0}]
    with pytest.raises(WorkError,match='素材槽可见阶段'):dark.validate_props(p,35)
    scene['videoWindows']=[{'mediaId':'m0','from':math.ceil(scene['cueTimes']['work_video']*30),'frames':45,'offset':0}]
    dark.validate_props(p,35)
