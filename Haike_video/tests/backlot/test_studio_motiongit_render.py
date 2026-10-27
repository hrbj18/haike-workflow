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
