"""Native contract/clock regression; fake previews are not actual video QA."""
from copy import deepcopy
import json
import math
from pathlib import Path
import struct
import wave

import pytest

from backlot import studio_dark_native as native
from backlot.production_queue import ProductionQueue
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, read_json, sha


def write_pcm(path,seconds,rate=24000,tone=None):
    samples=round(seconds*rate)
    if tone is None:
        block=b'\x10\x01'*samples
    else:
        block=b''.join(struct.pack('<h',round(3000*math.sin(i*2*math.pi*tone/rate))) for i in range(samples))
    with wave.open(str(path),'wb') as stream:
        stream.setparams((1,2,rate,0,'NONE',''));stream.writeframes(block)


@pytest.fixture
def sample(tmp_path):
    instance=tmp_path/'instance';project=instance/'prepared';project.mkdir(parents=True)
    preview=project/'preview.json';atomic_private(preview,{'reviewed':True,'schema':'fixture-not-real-review'})
    review=tmp_path/'visual.json';atomic_private(review,{'status':'pass','preview_sha256':sha(preview),
        'actual_images_viewed':[{'name':'isolated-test-fixture','sha256':'a'*64}]})
    plan=tmp_path/'plan.json'
    groups=['03-A:s01','03-A:s04','03-A:s08']
    atomic_private(plan,{'frames':1836,'seconds':30.6,'completeGroups':groups,
                         'completeGroupFrames':dict(zip(groups,[564,642,630]))})
    paths={}
    for key,filename in [('helper','motion.mjs'),('package','template.motion'),('node','node.exe'),('ffmpeg','ffmpeg.exe'),('ffprobe','ffprobe.exe')]:
        path=tmp_path/filename;path.write_bytes((key+' isolated fixture').encode());paths[key]=str(path.resolve())
    voice=tmp_path/'voice.wav';write_pcm(voice,727930/24000)
    music=tmp_path/'music.wav';write_pcm(music,35,rate=48000)
    value={'title':'isolated native contract','projectDirectory':str(project.resolve()),'instanceDirectory':str(instance.resolve()),
           **paths,'audio':str(voice.resolve()),'previewReceipt':str(preview.resolve()),'visualReview':str(review.resolve()),
           'planReview':str(plan.resolve()),'outputRoot':str((instance/'native-renders').resolve()),
           'expected':{'width':1920,'height':1080,'fps':60,'frames':1836,'seconds':30.6},
           'audio_mode':'native_plus_music','music':{'path':str(music.resolve()),'gainDb':-5,'offsetSeconds':0,'loop':False}}
    return value,ProductionQueue(tmp_path/'queue.sqlite3',tmp_path/'projects')


def test_short_native_freezes_exact_clock_music_and_single_queue(sample):
    value,queue=sample;r=native.prepare(queue,value)
    assert r['expected']==value['expected'] and r['voice_clock']['samples']==727930
    assert r['audio_mode']=='native_plus_music' and r['music']['gainDb']==-5
    assert r['files']['music']['sha256']==sha(value['music']['path'])
    assert native.prepare(queue,value)==r
    job=native.submit(queue,r)
    assert job['status']=='paused' and native.submit(queue,r)['job_id']==job['job_id']
    assert native.validate(queue,r).is_dir()


def test_console_profile_keeps_complete_native_recipes_and_real_voice_clock(sample):
    value,_=sample
    profile=read_json(native.ROOT/'templates/motiongit-console-v1/source-contract.json')
    groups=['keyword-slam','statement-orb','works-fan','result-inspector','next-update-follow']
    plan={'native_profile':'console04-v1','frames':1836,'seconds':30.6,'completeGroups':groups,
          'completeGroupFrames':dict(zip(groups,[288,312,204,570,462]))}
    clock=native.speech._clock(value['audio'])
    assert native._expected(value,plan,clock,profile)==value['expected']
    plan['completeGroupFrames']['keyword-slam']+=10
    plan['completeGroupFrames']['statement-orb']-=10
    with pytest.raises(WorkError,match='停留容量'):native._expected(value,plan,clock,profile)


def test_unknown_native_profile_is_not_an_executable_plugin(sample):
    value,_=sample;value['profile_id']='downloaded-untrusted-profile'
    with pytest.raises(WorkError,match='未登记'):native.prepare(sample[1],value)


def test_native_portrait_requires_matching_original_plan_and_reviewed_output_window(sample):
    from backlot.studio_motion_native_viewport import CONSOLE_45
    value,_=sample;profile=read_json(native.ROOT/'templates/motiongit-console-v1/source-contract.json')
    groups=['keyword-slam','statement-orb','works-fan','result-inspector','next-update-follow']
    plan={'native_profile':'console04-v1','frames':1836,'seconds':30.6,'completeGroups':groups,
          'completeGroupFrames':dict(zip(groups,[288,312,204,570,462]))}
    value['expected'].update(width=1080,height=1920);clock=native.speech._clock(value['audio'])
    with pytest.raises(WorkError,match='竖屏计划'):native._expected(value,plan,clock,profile)
    value['output_layout']=CONSOLE_45;plan['nativeLayout']='portrait'
    assert native._expected(value,plan,clock,profile)==value['expected']
    with pytest.raises(WorkError,match='1920'):native._expected(value,plan,clock,None)
    value['expected'].update(width=1440,height=1800)
    with pytest.raises(WorkError,match='1920'):native._expected(value,plan,clock,profile)


def test_console_native_profile_requires_exact_source_template_and_version(sample,monkeypatch):
    from backlot import studio_motiongit
    value,queue=sample;value['profile_id']='console04-v1'
    monkeypatch.setattr(studio_motiongit,'inspect_package',lambda _:{'template_id':'template-04-dark-console','version':'future-version','support':'official-helper'})
    with pytest.raises(WorkError,match='不匹配'):native.prepare(queue,value)


def test_legacy_full_manifest_stays_legacy_and_completed_history_survives_adapter_change(sample,monkeypatch):
    value,queue=sample
    for key in ['expected','audio_mode','music']:value.pop(key)
    write_pcm(Path(value['audio']),122.4)
    atomic_private(Path(value['planReview']),{'frames':7344,'seconds':122.4,'completeGroups':list(native.GROUP_MIN_FRAMES)})
    r=native.prepare(queue,value)
    assert r['expected']==native.REFERENCE_EXPECTED and 'audio_mode' not in r and 'music' not in r
    assert r['audio_policy']=='normalize original complete mixed track once; no extra music or effects'
    folder=queue.projects_root/r['project_id']/'renders'/r['render_id'];folder.mkdir(parents=True)
    (folder/native.OUTPUT_FILE).write_bytes(b'fixture-completed-mp4-not-real-video')
    atomic_private(folder/'quality.json',{'fixture':True})
    atomic_private(folder/'result.json',{'request_sha256':r['request_sha256'],'output_sha256':sha(folder/native.OUTPUT_FILE),'quality_sha256':sha(folder/'quality.json')})
    original_sha=native.sha
    monkeypatch.setattr(native,'sha',lambda path:'0'*64 if Path(path)==Path(native.__file__) else original_sha(path))
    assert native.validate(queue,r)==queue.projects_root/r['project_id']


@pytest.mark.parametrize('change,message',[
    (lambda v:v.update(audio_mode='guess'), '未知原生混音模式'),
    (lambda v:v.update(audio_mode={}), '未知原生混音模式'),
    (lambda v:v.pop('music'), '唯一外部配乐'),
    (lambda v:v['expected'].update(seconds=30.5),'精确帧时钟'),
    (lambda v:v['expected'].update(width=1440,height=1800),'1920'),
    (lambda v:v['music'].update(gainDb=-1),'增益'),
    (lambda v:v['music'].update(offsetSeconds=34),'长度不足'),
    (lambda v:v['music'].update(path='relative.wav'),'配乐文件'),
    (lambda v:v['music'].update(path=v['audio'],loop=True),'同一口播'),
])
def test_invalid_explicit_contract_is_rejected(sample,change,message):
    value,queue=sample;change(value)
    with pytest.raises(WorkError,match=message):native.prepare(queue,value)


@pytest.mark.parametrize('plan_edit,message',[
    (lambda p:p.update(seconds=29),'计划与预期'),
    (lambda p:p.update(completeGroups=['03-A:s99']),'未知'),
    (lambda p:p.update(completeGroups=[{}]),'未知'),
    (lambda p:p['completeGroupFrames'].update({'03-A:s08':629}),'完整动作时长'),
    (lambda p:p['completeGroupFrames'].update({'03-A:s01':100,'03-A:s04':1106}),'完整动作时长'),
    (lambda p:p.update(completeGroups=['03-A:s02','03-A:s01','03-A:s03'],completeGroupFrames={'03-A:s02':636,'03-A:s01':661,'03-A:s03':539}),'连续相邻'),
])
def test_bad_reviewed_groups_or_clock_is_rejected(sample,plan_edit,message):
    value,queue=sample;path=Path(value['planReview']);plan=read_json(path);plan_edit(plan);atomic_private(path,plan)
    with pytest.raises(WorkError,match=message):native.prepare(queue,value)


def test_voice_cannot_be_cut_or_stretched_to_target(sample):
    value,queue=sample;write_pcm(Path(value['audio']),31)
    with pytest.raises(WorkError,match='不能截断'):native.prepare(queue,value)
    write_pcm(Path(value['audio']),25)
    with pytest.raises(WorkError,match='非语音'):native.prepare(queue,value)


def test_music_source_cannot_change_after_freeze(sample):
    value,queue=sample;r=native.prepare(queue,value)
    with Path(value['music']['path']).open('ab') as stream:stream.write(b'changed')
    with pytest.raises(WorkError,match='已变化'):native.validate(queue,r)


def test_official_runtime_mutations_are_isolated_and_resume_checks_exact_copy(sample):
    value,queue=sample;r=native.prepare(queue,value)
    scratch=Path(r['output_root'])/r['render_id'];scratch.mkdir(parents=True)
    runtime=native._runtime_project(r,scratch)
    assert runtime!=Path(r['native_project']) and native._tree(runtime)==r['project_files']
    (runtime/'mix.wav').write_bytes(b'fixture-runtime-output')
    atomic_private(runtime/'audio_boundary_report.json',{'runtime':'fixture'})
    native._record_runtime_project(r,scratch,runtime,1)
    assert native.validate(queue,r).is_dir()
    assert native._runtime_project(r,scratch)==runtime
    (runtime/'mix.wav').write_bytes(b'changed-after-runtime')
    with pytest.raises(WorkError,match='恢复记录已变化'):native._runtime_project(r,scratch)


def test_explicit_browser_is_bound_and_change_blocks_resume(sample,monkeypatch,tmp_path):
    value,queue=sample;browser=tmp_path/'fixture-browser.exe';browser.write_bytes(b'isolated-fake-browser')
    monkeypatch.setenv('CHROME_PATH',str(browser.resolve()))
    r=native.prepare(queue,value)
    assert r['files']['browser']=={'path':str(browser.resolve()),'sha256':sha(browser)}
    browser.write_bytes(b'changed-version')
    with pytest.raises(WorkError,match='已变化'):native.validate(queue,r)


def test_native_master_adds_only_music_and_exact_pcm_clock(tmp_path):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ff,_=resolve_ffmpeg_pair()
    # Native has its own narration/SFX signal. The different source-voice tone
    # must be a provenance clock only, never another input to the new mix.
    raw=tmp_path/'native.wav';voice=tmp_path/'voice.wav';music=tmp_path/'music.wav'
    write_pcm(raw,6,tone=220);write_pcm(voice,5.75,tone=660);write_pcm(music,7,tone=110)
    r={'expected':{'width':1920,'height':1080,'fps':60,'frames':360,'seconds':6},
       'voice_clock':native.speech._clock(voice),'music':{'gainDb':-5,'offsetSeconds':0,'loop':False}}
    receipt=native._native_music_master(r,{'ffmpeg':Path(ff),'audio':voice,'music':music},raw,tmp_path)
    assert receipt['added_voice'] is False and receipt['additional_sfx'] is False and receipt['additional_music'] is True
    assert str(voice) not in receipt['command']
    assert receipt['command'].count('-i')==2 and 'amix=inputs=2:' in receipt['command'][receipt['command'].index('-filter_complex')+1]
    assert native.speech._clock(tmp_path/'master.wav')['samples']==288000
    assert receipt['native_audio_clock']['samples']==288000


def test_raw_native_audio_clock_mismatch_blocks_mix(tmp_path):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ff,_=resolve_ffmpeg_pair();raw=tmp_path/'short-native.wav';write_pcm(raw,5,tone=220)
    r={'expected':{'width':1920,'height':1080,'fps':60,'frames':360,'seconds':6},'voice_clock':{'duration_seconds':5.75}}
    with pytest.raises(WorkError,match='原生完整音轨'):native._native_music_master(r,{'ffmpeg':Path(ff)},raw,tmp_path)


def test_premixed_odd_native_frame_has_only_exact_nonvoice_padding(tmp_path):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ff,_=resolve_ffmpeg_pair();voice=tmp_path/'voice.wav';write_pcm(voice,6,tone=220)
    r={'expected':{'width':1920,'height':1080,'fps':60,'frames':361,'seconds':361/60},'audio_mode':'original_mix'}
    receipt=native._premixed_master(r,{'ffmpeg':Path(ff),'audio':voice},tmp_path)
    assert native.speech._clock(tmp_path/'master.wav')['samples']==361*800
    assert receipt['speech_stretched'] is False and receipt['additional_music_or_sfx'] is False


def test_portrait_companion_flag_is_explicit_frozen_and_boolean(sample):
    value,queue=sample
    original=native.prepare(queue,value)
    assert 'portrait_companion' not in original
    value['portrait_companion']=True
    framed=native.prepare(queue,value)
    assert framed['portrait_companion'] is True and framed['request_sha256']!=original['request_sha256']
    value['portrait_companion']='true'
    with pytest.raises(WorkError,match='布尔值'):native.prepare(queue,value)


def test_portrait_export_contains_whole_landscape_and_copies_audio(tmp_path,monkeypatch):
    from backlot import studio_render,studio_investment_audio_v5
    source=tmp_path/'primary.mp4';source.write_bytes(b'fixture-landscape-not-real-video')
    output=tmp_path/'framed.mp4';commands=[]
    def run(command,**_):
        commands.append(command)
        if command[-1]==str(output):output.write_bytes(b'fixture-framed-not-real-video')
    monkeypatch.setattr(native.subprocess,'run',run)
    monkeypatch.setattr(studio_render,'media_probe',lambda _: {'duration':6,'video':{
        'width':1440,'height':1800,'nb_frames':'360','avg_frame_rate':'60/1','codec_name':'h264',
        'pix_fmt':'yuv420p','bit_rate':'20500000'},'audio':{'codec_name':'aac','sample_rate':'48000','channels':2}})
    monkeypatch.setattr(studio_investment_audio_v5,'measure_audio',lambda _:{'true_peak_dbtp':-2.3})
    receipt=native._portrait_companion({'expected':{'frames':360,'seconds':6,'fps':60}},
                                     {'ffmpeg':Path('fixture-ffmpeg.exe')},source,output)
    geometry=receipt['layout'];command=commands[0];filters=command[command.index('-vf')+1]
    assert geometry['contentWidth']/geometry['contentHeight']==1920/1080
    assert (geometry['width'],geometry['height'],geometry['x'],geometry['y'])==(1440,1800,0,495)
    assert geometry['cropped'] is False and 'crop' not in filters and 'pad=1440:1800:0:495' in filters
    assert command[command.index('-c:a')+1]=='copy' and receipt['full_decode']=='passed'
