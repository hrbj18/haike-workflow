from copy import deepcopy
from pathlib import Path
import subprocess

import pytest

from backlot import paper_continuous as paper, paper_evidence
from backlot.studio_motion_presets import check_binding
from backlot.work_catalog import WorkError


@pytest.fixture
def parameters():
    return {'workflow': 'motion-kit', 'timeline': {'layout': 'portrait', 'styleProfile': 'paper', 'duration': 2,
        'voiceover': 'voice.wav', 'hud': False, 'captionSafeArea': 'frame', 'captionPosition': dict(paper.CAPTION_POSITION),
        'segments': [{'shotId': 'first', 't0': 0, 't1': 2, 'area': dict(paper.ACTION_AREA), 'presenter': 'hide'}],
        'captions': [{'s': 0, 'e': 1, 'text': '第一句'}, {'s': 1, 'e': 2, 'text': '第二句'}]},
        'paperSupport': {'profile': paper.PROFILE, 'title': '亲手体验AI', 'font': 'title-font.ttf',
            'shots': [{'shotId': 'first', 'heading': '身边的真实体验', 'clips': [
                {'src': 'a.mp4', 'sourceStart': 0, 'start': 0, 'end': 1, 'captionIndices': [0],
                 'meaning': '第一句话对应的真实体验', 'kind': 'media'},
                {'src': 'b.mp4', 'sourceStart': 1, 'start': 1, 'end': 2, 'captionIndices': [1],
                 'meaning': '第二句话对应的现场实拍', 'kind': 'media'}]}]}}


@pytest.mark.parametrize('change', ['opening', 'middle-gap', 'overlap', 'ending', 'shot-gap', 'title', 'heading',
                                  'font', 'area', 'captions', 'semantic', 'native-presenter'])
def test_empty_or_occluded_subject_and_missing_titles_are_rejected(parameters, change):
    s = parameters['paperSupport']; clips = s['shots'][0]['clips']; t = parameters['timeline']
    if change == 'opening': clips[0]['start'] = .01
    if change == 'middle-gap': clips[1]['start'] = 1.01
    if change == 'overlap': clips[1]['start'] = .99
    if change == 'ending': clips[1]['end'] = 1.99
    if change == 'shot-gap': t['segments'][0]['t0'] = .01
    if change == 'title': s['title'] = ''
    if change == 'heading': s['shots'][0]['heading'] = ' '
    if change == 'font': s['font'] = '../font.ttf'
    if change == 'area': t['segments'][0]['area']['y'] = 500
    if change == 'captions': t['captionPosition']['bottomRatio'] = .2
    if change == 'semantic': clips[1]['captionIndices'] = [0]
    if change == 'native-presenter': t['presenter'] = {'src': 'old.mp4'}
    with pytest.raises(WorkError): paper_evidence.validate(parameters)


def test_presets_require_their_saved_profile_not_latest_profile(parameters):
    value = {'workflow': 'motion-kit', 'parameters': parameters,
             'preset_source': {'id': 'paper-approved-portrait-v1', 'version': '1.2.0'}}
    parameters['timeline']['narrationMap'] = [{}]
    check_binding(value)
    value['preset_source']['version'] = '1.1.0'
    with pytest.raises(WorkError): check_binding(value)
    parameters['paperSupport']['profile'] = 'paper-evidence/1'
    check_binding(value)


def test_sources_and_same_voice_presenter_are_checked(parameters):
    clip = parameters['paperSupport']['shots'][0]['clips'][0]
    clip.update(kind='presenter', voiceSha256='a'*64, videoSha256='b'*64)
    assets = {'a.mp4': {'path': 'a.mp4', 'sha256': 'b'*64}, 'b.mp4': {'path': 'b.mp4', 'sha256': 'c'*64},
              'voice.wav': {'sha256': 'd'*64}}
    probe = lambda _: {'video': {'width': 1080}, 'duration': 2}
    with pytest.raises(WorkError, match='不匹配'): paper.validate(parameters, assets, probe)
    assets['voice.wav']['sha256'] = 'a'*64
    with pytest.raises(WorkError, match='区间不足'):
        paper.validate(parameters, assets, lambda _: {'video': {}, 'duration': .5})
    clip['sourceStart'] = .1
    with pytest.raises(WorkError, match='连续原声时钟'): paper.validate(parameters)


def test_measured_captions_cannot_overlap_the_continuous_main(parameters):
    receipt = {'renderer': {'captionSamples': [{'items': [{'left': 80, 'right': 1000, 'top': 1750, 'bottom': 1880}]}]}}
    paper_evidence.check_preview(receipt, parameters)
    receipt['renderer']['captionSamples'][0]['items'][0]['top'] = 1710
    with pytest.raises(WorkError, match='重叠'): paper_evidence.check_preview(receipt, parameters)


def test_preview_and_export_have_identical_full_sized_subject_and_titles(parameters, tmp_path):
    assets = {n: {'path': n} for n in ['a.mp4', 'b.mp4']}
    plates = ('theme.png', ['chapter.png'])
    before = deepcopy(parameters)
    for at in [None, 0, .999, 1, 1.999]:
        command = paper.command('ffmpeg', 'native', 'out', parameters, assets, plates, at=at)
        graph = command[command.index('-filter_complex')+1]
        assert 'scale=960:1200:force_original_aspect_ratio=decrease' in graph
        assert 'overlay=60:500' in graph and 'overlay=0:0' in graph and 'overlay=60:136' in graph
        assert '-loop' not in command and '-stream_loop' not in command
        if at is None:
            assert command[command.index('-c:a')+1] == 'copy'
    assert parameters == before
    assert {0., 1., 1-1/60, 1+1/60, 2-1/60} <= paper.preview_times(parameters)


def test_real_output_keeps_subject_and_title_on_every_cut_frame(parameters, tmp_path):
    from PIL import Image
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ff, _ = resolve_ffmpeg_pair()
    def run(args):
        subprocess.run([str(ff), '-nostdin', '-v', 'error', '-y', *args], check=True, capture_output=True, timeout=60)
    source = tmp_path/'footage.mp4'
    native = tmp_path/'native.mp4'
    run(['-f', 'lavfi', '-i', 'testsrc2=s=180x320:r=25', '-t', '2.1', '-c:v', 'libx264', str(source)])
    run(['-f', 'lavfi', '-i', 'color=white:s=1080x1920:r=60', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo',
         '-t', '2', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(native)])
    fontpath = Path(__file__).resolve().parents[2]/'remotion-composer/a2e/public/fonts/NotoSansSC.ttf'
    assets = {n: {'path': str(source), 'sha256': 'a'*64} for n in ['a.mp4', 'b.mp4']}
    assets['title-font.ttf'] = {'path': str(fontpath), 'sha256': 'f'*64}
    output = tmp_path/'full.mp4'
    paper.compose(ff, native, output, parameters, assets)
    result = paper.check_output(ff, output, 120)
    assert result['checked_frames'] == 120 and result['empty_frames'] == 0
    # A native-only white frame must fail this exact per-frame gate.
    with pytest.raises(WorkError, match='空帧'): paper.check_output(ff, native, 120)
    parameters['paperSupport']['title'] = '字'*28
    with pytest.raises(WorkError, match='过长'):
        paper.validate(parameters, assets, lambda _: {'video': {'width': 180}, 'duration': 3})
