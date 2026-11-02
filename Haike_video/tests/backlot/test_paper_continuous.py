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
    probe = lambda _: {'video': {'width': 1080, 'duration': '2'}, 'duration': 2}
    with pytest.raises(WorkError, match='不匹配'): paper.validate(parameters, assets, probe)
    assets['voice.wav']['sha256'] = 'a'*64
    with pytest.raises(WorkError, match='区间不足'):
        paper.validate(parameters, assets, lambda _: {'video': {'duration': '.5'}, 'duration': .5})
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
    # The last frame covers its display interval even after its exact PTS.
    # ffmpeg -ss beyond that PTS alone would produce an empty still.
    parameters['paperSupport']['shots'][0]['clips'][1]['sourceStart'] = 1.1
    still = tmp_path/'last-frame.png'
    native_still = tmp_path/'native.png'
    run(['-i', str(native), '-frames:v', '1', str(native_still)])
    paper.compose(ff, native_still, still, parameters, assets, at=1.999)
    assert still.is_file()
    # A native-only white frame must fail this exact per-frame gate.
    with pytest.raises(WorkError, match='空帧'): paper.check_output(ff, native, 120)
    parameters['paperSupport']['title'] = '字'*28
    with pytest.raises(WorkError, match='过长'):
        paper.validate(parameters, assets, lambda _: {'video': {'width': 180, 'duration': '3'}, 'duration': 3})


def test_long_audio_does_not_extend_short_video(parameters):
    assets = {n: {'path': n, 'sha256': 'a'*64} for n in ['a.mp4', 'b.mp4']}
    with pytest.raises(WorkError, match='区间不足'):
        paper.validate(parameters, assets, lambda _: {'duration': 2, 'video': {'duration': '.4', 'start_time': '0'}})
    assert paper.video_window({'video': {'duration_ts': 10, 'time_base': '1/25', 'start_time': '.2'}}, 'unused') == pytest.approx((.2, .6))


def test_title_cache_recovers_partial_and_decodable_wrong_content(parameters, tmp_path):
    from PIL import Image
    fontpath = Path(__file__).resolve().parents[2]/'remotion-composer/a2e/public/fonts/NotoSansSC.ttf'
    assets = {'title-font.ttf': {'path': str(fontpath), 'sha256': 'f'*64}}
    support = parameters['paperSupport']
    title, chapters = paper.title_images(tmp_path, support, assets)
    expected = [p.read_bytes() for p in [title, *chapters]]
    title.write_bytes(b'partial PNG')
    Image.new('RGB', (960, 70), 'black').save(chapters[0])
    same_title, same_chapters = paper.title_images(tmp_path, support, assets)
    assert [p.read_bytes() for p in [same_title, *same_chapters]] == expected
    assert not list(tmp_path.glob('*pending*'))


def test_actual_short_video_with_long_audio_is_rejected(parameters, tmp_path):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    from backlot.studio_render import media_probe
    ff, _ = resolve_ffmpeg_pair()
    source = tmp_path/'short-video-long-audio.mp4'
    subprocess.run([str(ff), '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-t', '0.4', '-i',
        'testsrc2=s=180x320:r=25', '-f', 'lavfi', '-t', '2', '-i', 'anullsrc=r=48000:cl=stereo',
        '-c:v', 'libx264', '-c:a', 'aac', str(source)], check=True, capture_output=True, timeout=30)
    info = media_probe(source)
    assert info['duration'] >= 2 and float(info['video']['duration']) < .5
    assets = {n: {'path': str(source), 'sha256': 'a'*64} for n in ['a.mp4', 'b.mp4']}
    with pytest.raises(WorkError, match='区间不足'):
        paper.validate(parameters, assets, media_probe)


def test_non_frame_aligned_low_fps_preview_matches_encoded_cut_frames(parameters, tmp_path):
    from PIL import Image
    import numpy as np
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ff, _ = resolve_ffmpeg_pair()
    def run(args):
        subprocess.run([str(ff), '-nostdin', '-v', 'error', '-y', *args], check=True, capture_output=True, timeout=60)
    footage, native = tmp_path/'slow.mp4', tmp_path/'native.mp4'
    run(['-f', 'lavfi', '-i', 'testsrc2=s=180x320:r=1', '-t', '3', '-c:v', 'libx264', str(footage)])
    run(['-f', 'lavfi', '-i', 'color=white:s=1080x1920:r=60', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo',
         '-t', '2', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(native)])
    fontpath = Path(__file__).resolve().parents[2]/'remotion-composer/a2e/public/fonts/NotoSansSC.ttf'
    assets = {n: {'path': str(footage), 'sha256': 'a'*64} for n in ['a.mp4', 'b.mp4']}
    assets['title-font.ttf'] = {'path': str(fontpath), 'sha256': 'f'*64}
    first, second = parameters['paperSupport']['shots'][0]['clips']
    first['sourceStart'], second['sourceStart'] = .5, 1.25
    output = tmp_path/'full.mp4'
    paper.compose(ff, native, output, parameters, assets)
    blank = tmp_path/'native.png'
    run(['-i', str(native), '-frames:v', '1', str(blank)])
    x, y, w, h = paper.MAIN
    def pixels(path):
        with Image.open(path) as im:
            return np.asarray(im.convert('RGB').crop((x, y, x+w, y+h)).resize((96, 120))).astype(float)
    for at in [0, .5, 1, 1.75, 119/60]:
        still, encoded = tmp_path/f'preview-{at}.png', tmp_path/f'encoded-{at}.png'
        paper.compose(ff, blank, still, parameters, assets, at=at)
        run(['-i', str(output), '-vf', f'select=eq(n\\,{round(at*60)})', '-frames:v', '1', str(encoded)])
        assert abs(pixels(still)-pixels(encoded)).mean() < 5, f'preview/export differ at {at}'
