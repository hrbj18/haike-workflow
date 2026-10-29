"""Native adapters must reject missing, escaped and too-short actual sources."""
from pathlib import Path
import json
from types import SimpleNamespace

import pytest

from backlot import studio_motiongit_render as render
from backlot import studio_motiongit as motion
from backlot.work_catalog import WorkError


@pytest.mark.parametrize('name',['C:/private/video.mp4','../../private.mp4','https://example.com/v.mp4','inputs/nested/v.mp4'])
def test_media_cannot_escape_owned_inputs(name):
    with pytest.raises(WorkError): render._check_bindings({'segments':[{'props':{'src':name}}]}, {})


def test_nested_owned_bindings_and_empty_presenter_are_supported():
    render._check_bindings({'presenter':{'src':''},'segments':[{'props':{'items':[{'src':'inputs/photo.jpg'}]}}]}, {'photo.jpg':{}})


def test_short_footage_is_rejected_before_render(monkeypatch):
    from backlot import studio_render
    monkeypatch.setattr(studio_render,'media_probe',lambda p:{'duration':14.375 if p.name=='video.mp4' else 20})
    p={'duration':20,'voiceover':'narration.wav','music':'music.wav','subtitles':'captions.srt',
       'segments':[{'t0':9,'t1':15.4,'props':{'src':'video.mp4','sourceStart':8.3}}]}
    assets={n:{'path':n} for n in ['narration.wav','music.wav','captions.srt','video.mp4']}
    with pytest.raises(WorkError,match='实拍区间不足'): render._check_source_windows(p,assets)
    p['segments'][0]['props']['sourceStart']=7.5
    render._check_source_windows(p,assets)


def test_full_speech_clock_and_music_coverage_are_required(monkeypatch):
    from backlot import studio_render
    p={'duration':20,'voiceover':'voice.wav','music':'music.wav','subtitles':'captions.srt','segments':[]}
    assets={n:{'path':n} for n in ['voice.wav','music.wav','captions.srt']}
    monkeypatch.setattr(studio_render,'media_probe',lambda p:{'duration':31.7 if p.name=='voice.wav' else 20})
    with pytest.raises(WorkError,match='完整本期口播'): render._check_source_windows(p,assets)


def test_motion_kit_cannot_hide_remote_media_inside_wrapper():
    value={'workflow':'motion-kit','parameters':{'workflow':'motion-kit','timeline':{
        'duration':20,'segments':[{'props':{'src':'https://example.com/private.mp4'}}]}}}
    assert render.component_timeline(value)['duration']==20
    with pytest.raises(WorkError,match='已导入素材'):
        render._check_bindings(value['parameters'],{})
    value['parameters']['workflow']='poster-kit'
    with pytest.raises(WorkError,match='封装'):render.component_timeline(value)


def test_official_component_commands_keep_frozen_workflow(monkeypatch):
    calls=[]
    monkeypatch.setattr(motion,'helper_command',lambda package,*args,**kwargs:calls.append((args,kwargs)))
    state={'instanceDirectory':'owned-instance','cache':'owned-cache','workflow':'motion-kit'}
    render._execute({},state,'preview','prepared-project','--times','1,2,3')
    assert '--workflow' not in calls[0][0] and 'prepared-project' in calls[0][0]
    state['workflow']='poster-kit'
    render._execute({},state,'preview','--timeline','@vault')
    assert calls[1][0][calls[1][0].index('--workflow')+1]=='poster-kit'
    state['workflow']='unknown'
    with pytest.raises(WorkError,match='未登记'):render._execute({},state,'render')


def test_new_entry_normalizes_media_bindings_without_rewriting_copy():
    value={'workflow':'motion-kit','parameters':{'workflow':'motion-kit','timeline':{
        'voiceover':'inputs/voice.wav','music':'inputs/music.wav',
        'segments':[{'props':{'src':'inputs/elder.mp4','title':'inputs/ is literal text'}}],
        'mediaPolicies':{'inputs/elder.mp4':{'role':'evidence','fit':'contain'}}}}}
    normalized=render.entry_parameters(value)['timeline']
    assert normalized['voiceover']=='voice.wav' and normalized['segments'][0]['props']['src']=='elder.mp4'
    assert normalized['segments'][0]['props']['title']=='inputs/ is literal text'
    assert 'elder.mp4' in normalized['mediaPolicies']
    assert value['parameters']['timeline']['voiceover']=='inputs/voice.wav'


def test_new_plan_is_not_automatically_accepted_as_semantic_review(tmp_path,monkeypatch):
    from backlot.studio import atomic_private
    from backlot.work_catalog import sha,read_json
    inst=tmp_path/'instance';plan=inst/'plan';plan.mkdir(parents=True)
    request={'project_id':'studio-fixture','render_id':'render-fixture','request_sha256':'bound',
             'draft':{'workflow':'motion-kit','parameters':{'workflow':'motion-kit','timeline':{'duration':32}}}}
    request['entry_parameters']=render.entry_parameters(request['draft']);request['phase']='preview'
    atomic_private(inst/'timeline.json',request['entry_parameters'])
    atomic_private(plan/'report.json',{'ready':True,'workflow':'motion-kit','duration':32})
    atomic_private(plan/'inputs.json',{'paramsSha256':sha(inst/'timeline.json')})
    atomic_private(plan/'review.json',{'reviewed':False,'inputsSha256':sha(plan/'inputs.json'),'otherBinding':'preserve'})
    folder=tmp_path/'projects/studio-fixture/renders/render-fixture';folder.mkdir(parents=True)
    state={'instanceDirectory':str(inst)};q=SimpleNamespace(projects_root=tmp_path/'projects')
    monkeypatch.setattr(render,'_execute',lambda *a,**kw:pytest.fail('Must not prepare/preview before actual plan review'))
    result=render._kit_prepare({},request,state,folder,{'duration':32})
    assert result['result']['review_stage']=='plan' and not read_json(plan/'review.json')['reviewed']
    with pytest.raises(WorkError,match='实际核对'):render.review_plan(q,request,{})
    review={'report_sha256':sha(plan/'report.json'),'inputs_sha256':sha(plan/'inputs.json'),
            'inspected_plan':True,'reviewer':'fixture-reviewer','description':'Isolated fixture, not real artistic review'}
    assert render.review_plan(q,request,review)['scope']=='plan-only'
    assert read_json(plan/'review.json')['otherBinding']=='preserve'
    atomic_private(plan/'inputs.json',{'changed':'source'})
    with pytest.raises(WorkError,match='实际核对'):render.review_plan(q,request,review)


def test_component_preview_dictionary_binds_pixels_parameters_and_source(tmp_path):
    from backlot.studio import atomic_private
    from backlot.work_catalog import sha
    (tmp_path/'frame.png').write_bytes(b'fixture pixels')
    atomic_private(tmp_path/'params.json',{'fixture':'parameters'})
    atomic_private(tmp_path/'motiongit-origin.json',{'workflow':'motion-kit','sourceBinding':{'sourceLockSha256':'fixture'},
                   'preparedParamsSha256':sha(tmp_path/'params.json')})
    receipt={'schema':'motiongit-preview/1','sourceBinding':{'sourceLockSha256':'fixture'},
        'projectHashes':{n:sha(tmp_path/n) for n in ['params.json','motiongit-origin.json']},
        'stills':{'frame.png':sha(tmp_path/'frame.png')}}
    assert len(render.kit_images(receipt,tmp_path))==1
    receipt['sourceBinding']={'sourceLockSha256':'another'}
    with pytest.raises(WorkError,match='来源与准备'):render.kit_images(receipt,tmp_path)
    receipt['sourceBinding']={'sourceLockSha256':'fixture'}
    receipt['stills']={'../escape.png':'anything'}
    with pytest.raises(WorkError,match='路径无效'):render.kit_images(receipt,tmp_path)


def test_portrait_crop_cannot_drop_real_measured_subtitles():
    sample={'renderer':{'captionSamples':[{'time':18.45,'items':[{'left':50,'right':1030,'top':1722.8,'bottom':1800}]}]}}
    with pytest.raises(WorkError,match='字幕超出4:5'):render.check_portrait_captions(sample)
    sample['renderer']['captionSamples'][0]['items'][0].update(top=1110,bottom=1200)
    render.check_portrait_captions(sample)
    with pytest.raises(WorkError,match='未覆盖'):render.check_portrait_captions({'renderer':{'captionSamples':[]}})


def test_unknown_full_range_matrix_is_not_silently_retagged():
    with pytest.raises(WorkError,match='色彩矩阵未识别'):
        render.encoding_layout({'color_range':'pc','pix_fmt':'yuvj420p','color_space':'unknown'},False)


def test_real_ffmpeg_conversion_preserves_frames_and_changes_luma_range(tmp_path):
    """Three synthetic diagnostic frames, never a claim of film visual review."""
    import subprocess
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    from backlot.studio_render import media_probe
    try:ff,_=resolve_ffmpeg_pair()
    except Exception:pytest.skip('Local FFmpeg is unavailable')
    help_result=subprocess.run([ff,'-hide_banner','-h','filter=scale'],capture_output=True,text=True)
    help_text=help_result.stdout+help_result.stderr
    if 'in_transfer' not in help_text or 'in_primaries' not in help_text:
        pytest.skip('This local FFmpeg lacks the tested libswscale transfer/primaries capabilities')
    def run(*args):
        result=subprocess.run([ff,'-nostdin','-v','error','-y',*map(str,args)],capture_output=True)
        assert result.returncode==0,result.stderr.decode(errors='replace')
        return result.stdout
    source=tmp_path/'browser.mp4';output=tmp_path/'limited.mp4'
    run('-f','lavfi','-i','testsrc=size=320x400:rate=25','-frames:v',3,
        '-vf','scale=out_range=full,format=yuvj420p','-c:v','libx264','-crf',0,
        '-color_range','pc','-colorspace','bt470bg',source)
    before=media_probe(source)['video'];conversion=render.encoding_layout(before,False)
    run('-i',source,'-vf',conversion['filter'],'-c:v','libx264','-crf',0,'-pix_fmt','yuv420p',*conversion['options'],output)
    after=media_probe(output)['video']
    assert (after['width'],after['height'],after['nb_frames'])==(320,400,'3')
    assert after['pix_fmt']=='yuv420p' and after['color_range']=='tv' and after['color_space']=='bt709'
    original=run('-i',source,'-frames:v',1,'-pix_fmt','yuvj420p','-f','rawvideo','pipe:1')[:320*400]
    converted=run('-i',output,'-frames:v',1,'-pix_fmt','yuv420p','-f','rawvideo','pipe:1')[:320*400]
    assert min(original)<8 and max(original)>247
    assert min(converted)>=12 and max(converted)<=240


def test_preview_covers_late_reveal_before_exit():
    p={'duration':30.33,'segments':[{'t0':0,'t1':5.9,'cues':[.76,3.64]},
                                  {'t0':23,'t1':30.33,'cues':[23.88,26.92]}]}
    times=render.preview_times(p)
    assert any(abs(t-4.29)<.001 for t in times)
    assert any(abs(t-27.57)<.001 for t in times)
    assert all(0<=t<p['duration'] for t in times)


def test_preview_includes_each_actual_spoken_sentence_midpoint():
    p={'duration':6, 'segments':[{'t0':0,'t1':6,'cues':[.5]}],
       'narrationMap':[{'beats':[{'at':.2,'until':1.4}, {'at':2,'until':3}, {'at':4,'until':5.8}]}]}
    times=render.preview_times(p)
    assert all(any(abs(actual-expected)<.000001 for actual in times) for expected in [.8,2.5,4.9])


def test_saved_production_restores_only_same_draft_and_asset_bindings(tmp_path,monkeypatch):
    monkeypatch.setattr(motion,'STORE',tmp_path/'private')
    package={'id':'mg-fixture','sha256':'package-sha','workflows':{'poster-kit':{'schema':{},'controls':{}}}}
    motion._put_package(package)
    value=motion.save_draft(package['id'],'poster-kit',{'segments':[]})
    motion.save_asset(value['id'],'photo.jpg',b'original-owned-photo')
    request={'contract':render.CONTRACT,'draft':value,'assets':render._assets(value),'project_id':'studio-fixture',
             'render_id':'motiongit-component-fixture','request_sha256':'fixture-only'}
    queue=SimpleNamespace(projects_root=tmp_path/'projects')
    folder=queue.projects_root/request['project_id']/'artifacts';folder.mkdir(parents=True)
    (folder/'motiongit-component-request.json').write_text(json.dumps(request),encoding='utf-8')
    motion.track_production(value,request)
    assert render.recorded_request(queue,value['id'],request['render_id'])==request
    motion.save_asset(value['id'],'photo.jpg',b'changed-owned-photo')
    with pytest.raises(WorkError,match='素材绑定已变更'):render.recorded_request(queue,value['id'],request['render_id'])
