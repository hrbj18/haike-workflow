"""Content-clock/provenance gates; no provider, native renderer or queue calls."""
from copy import deepcopy
from pathlib import Path
import json
import wave

import pytest
from PIL import Image

from backlot import studio_dark_native_content as subject


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return {'path': str(path), 'sha256': subject.sha(path)}


def ref(path, data=b'fixture'):
    path.write_bytes(data)
    return {'path': str(path), 'sha256': subject.sha(path)}


@pytest.fixture
def episode(tmp_path, monkeypatch):
    voice_path = tmp_path / 'voice.wav'
    with wave.open(str(voice_path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b'\0\0' * 727930)
    voice = {'path': str(voice_path), 'sha256': subject.sha(voice_path)}
    words = [{'text': text, 'start': at, 'end': at + .5}
             for text, at in [('第一句', 1.), ('第二句', 10.), ('第三句', 20.)]]
    word_proof = save(tmp_path / 'words.json', {'voice_sha256': voice['sha256'], 'words': words})
    captions = [{'t0': w['start'], 't1': w['end'], 'zh': w['text'], 'en': 'Measured fixture.',
                 'highlight': {'source': 'asr-word-boundaries', 'language': 'zh', 'units': [w]}} for w in words]
    caption_ref = save(tmp_path / 'captions.json', captions)
    avatar = ref(tmp_path / 'avatar.mp4', b'avatar-fixture')
    avatar_proof = save(tmp_path / 'avatar-proof.json', {
        'original_full_voice_sha256': voice['sha256'], 'video_sha256': avatar['sha256'],
        'full_decode': 'passed', 'actual_view_status': 'pass-six-representative-frames', 'frames': 765, 'fps': 25})
    badge_path = tmp_path / 'badge.png'
    Image.new('RGB', (12, 12), 'red').save(badge_path)
    badge = {'path': str(badge_path), 'sha256': subject.sha(badge_path)}
    footage = ref(tmp_path / 'footage.mp4', b'footage-fixture')
    source_review = save(tmp_path / 'source-review.json', {
        'schema': 'haike.motion-native-source-review/1', 'status': 'pass', 'materials': [{
            'source_sha256': footage['sha256'], 'source_start_seconds': 0., 'source_end_seconds': 30.,
            'observed_frames': [1., 10., 20.], 'description': 'Synthetic source-review fixture.',
            'actual_images_viewed': [badge]}]})
    profile = subject.read(subject.PROFILE)
    content = {g['id']: {f['inputPath']: 3 if f['type'] == 'number' else '测试' for f in g['fields']}
               for g in profile['groups']}
    value = {'schema': subject.SCHEMA, 'template_id': profile['template_id'], 'title': '测试节目',
             'brand': '测试品牌', 'short_title': '本期真实内容', 'presenter_label': '测试人物', 'layout': 'landscape',
             'voice': voice, 'captions': {**caption_ref, 'voice_sha256': voice['sha256'], 'provenance': word_proof},
             'avatar': {**avatar, 'voice_sha256': voice['sha256'], 'same_voice_verified': True,
                        'evidence': avatar_proof, 'badge': badge},
             'provenance': {'source': 'Explicit synthetic test input', 'authorized': True},
             'source_review': source_review,
             'media': {'wall': [{'id': f'wall{i}', 'source': footage, 'at': i + 1.} for i in range(4)],
                       'categories': [{'id': f'category{i}', 'source': footage, 'at': i + 1.} for i in range(4)],
                       'lens': {'id': 'lens', 'source': footage, 'offset': .8}},
             'content': content,
             'music': {**ref(tmp_path / 'music.wav', b'music-fixture'), 'gainDb': -3, 'offsetSeconds': 0, 'loop': True},
             'tools': {k: ref(tmp_path / (k + '.exe'), k.encode()) for k in subject.TOOLS},
             'fonts': {k: ref(tmp_path / (k + '.ttf'), k.encode()) for k in ['body', 'display']},
             'sfx': {k: ref(tmp_path / (k + '.wav'), k.encode()) for k in ['tick', 'whoosh', 'dong']}}
    input_path = tmp_path / 'input.json'
    save(input_path, value)
    def probe(tool, path):
        name = Path(path).name
        if name == 'avatar.mp4':
            return {'seconds': 30.6, 'video': {'width': 1228, 'height': 1536}, 'audio': {'channels': 1}}
        if name == 'music.wav':
            return {'seconds': 60., 'video': None, 'audio': {'channels': 2}}
        return {'seconds': 30., 'video': {'width': 1920, 'height': 1080}, 'audio': {'channels': 2}}
    monkeypatch.setattr(subject, '_probe', probe)
    return input_path, value, profile


def test_check_is_read_only_and_same_clock(episode):
    path, _, _ = episode
    before = {p.relative_to(path.parent): subject.sha(p) for p in path.parent.rglob('*') if p.is_file()}
    built, rows = subject.check(path)
    after = {p.relative_to(path.parent): subject.sha(p) for p in path.parent.rglob('*') if p.is_file()}
    assert before == after
    assert built['timeline']['frames'] == 1836
    assert [g['frames'] for g in built['timeline']['groups']] == [348, 695, 793]
    assert len(rows) == 3
    assert built['avatar']['validated_evidence']['source_voice_sha256'] == built['voice']['sha256']
    assert built['media']['lens']['review']['source_end_seconds'] == 30.


def test_native_instance_short_root_is_explicit_and_bounded(episode, tmp_path):
    path, value, _ = episode
    # A short declared location is a public output path, not a change to core.
    root = Path(path.anchor)/'hk-mn-test-fixture'
    value['native_instance_root'] = str(root)
    save(path, value)
    built, _ = subject.check(path)
    assert built['native_instance_root'] == str(root.resolve()) and not root.exists()
    value['native_instance_root'] = str(root/('a'*200)); save(path, value)
    with pytest.raises(ValueError, match='短缓存'): subject.check(path)


@pytest.mark.parametrize('seconds', [30.3304167, 31., 34., 40., 45., 55.])
def test_voice_following_holds_preserve_protected_actions(seconds):
    profile = subject.read(subject.PROFILE)
    result = subject.timeline(profile, seconds, {}, 'landscape')
    assert result['frames'] % 12 == 0
    assert 0 <= result['seconds'] - seconds <= 2
    assert sum(g['frames'] for g in result['groups']) == result['frames']
    for g in result['groups']:
        for part in g['clock_parts']:
            if part['kind'] == 'protected':
                assert part['frames'] == part['to'] - part['from']
            else:
                assert part['baseline_frames'] <= part['frames'] <= 180


def test_baseline_anchors_match_checked_source_clock(episode):
    path, _, _ = episode
    built, rows = subject.check(path)
    params = subject._native_params(built, rows)
    assert params['brief']['segments'][0]['anchors']['wall_handoff'] == {'frame': 229}
    assert params['brief']['segments'][1]['anchors']['category_4'] == {'frame': 264}
    assert params['brief']['segments'][2]['anchors']['comments'] == {'frame': 624}
    assert ''.join(s['text'] for s in params['brief']['segments']) == ''.join(c['zh'] for c in rows)
    assert params['brief']['music']['mode'] == 'none'


@pytest.mark.parametrize('seconds,layout', [(20., 'landscape'), (20., 'portrait45'), (100., 'landscape')])
def test_incompatible_complete_group_duration_fails_explicitly(seconds, layout):
    with pytest.raises(ValueError):
        subject.timeline(subject.read(subject.PROFILE), seconds, {}, layout)


def test_portrait_uses_voice_clock_and_never_native_contain(episode):
    path, value, _ = episode
    value['layout'] = 'portrait45'
    save(path, value)
    built, rows = subject.check(path)
    assert built['timeline']['frames'] == 1836
    assert built['timeline']['native_clock_available'] is False
    assert built['timeline']['timing_authority'] == 'studio_native_story_portrait'
    with pytest.raises(ValueError, match='真4:5'):
        subject._native_params(built, rows)
    with pytest.raises(ValueError, match='真4:5'):
        subject._official(built, 'preview')


@pytest.mark.parametrize('change', [
    lambda v: v['captions'].update(voice_sha256='f' * 64),
    lambda v: v['avatar'].update(voice_sha256='f' * 64),
    lambda v: v['avatar'].update(same_voice_verified=False),
    lambda v: v['provenance'].update(authorized=False),
    lambda v: v['media']['categories'].pop(),
    lambda v: v['media']['wall'][0].update(at=45.),
    lambda v: v['media']['lens'].update(offset=20.),
    lambda v: v['content']['s01'].update({'claim.subject': '过长' * 10}),
    lambda v: v['content']['s01'].update({'claim.subject': '<b>标题</b>'}),
    lambda v: v.update(layout='contain'),
    lambda v: v['tools'].update(shell={'path': 'bad', 'sha256': '0' * 64}),
    lambda v: v.update(layout='portrait45', fonts={}),
])
def test_missing_mismatched_or_unsupported_inputs_cannot_build(episode, change):
    path, value, _ = episode
    change(value)
    save(path, value)
    with pytest.raises(ValueError):
        subject.check(path)


def test_measured_word_record_cannot_be_replaced_with_guessed_times(episode):
    path, value, _ = episode
    captions = subject.read(value['captions']['path'])
    captions[0]['highlight']['units'][0]['start'] += .01
    newref = save(Path(value['captions']['path']), captions)
    value['captions'].update(newref)
    save(path, value)
    with pytest.raises(ValueError, match='原始ASR'):
        subject.check(path)


def test_source_review_must_cover_selected_continuous_interval(episode):
    path, value, _ = episode
    proof_path = Path(value['source_review']['path'])
    proof = subject.read(proof_path)
    proof['materials'][0]['source_end_seconds'] = 13.
    proof['materials'][0]['observed_frames'] = [1., 10.]
    value['source_review'] = save(proof_path, proof)
    # Keep all wall covers inside reviewed time so the lens interval is decisive.
    save(path, value)
    with pytest.raises(ValueError, match='连续镜头'):
        subject.check(path)


def test_float_boundary_tolerance_does_not_accept_missing_source_time(episode):
    path, value, _ = episode
    proof_path = Path(value['source_review']['path'])
    proof = subject.read(proof_path)
    proof['materials'][0]['source_end_seconds'] = 13.1
    proof['materials'][0]['observed_frames'] = [1., 10.]
    value['source_review'] = save(proof_path, proof)
    save(path, value)
    result, _ = subject.check(path)
    assert result['media']['lens']['offset'] + result['media']['lens']['seconds'] > 13.1
    proof['materials'][0]['source_end_seconds'] = 13.099
    value['source_review'] = save(proof_path, proof)
    save(path, value)
    with pytest.raises(ValueError):
        subject.check(path)


def test_native_entry_cannot_execute_a_full_render():
    with pytest.raises(ValueError, match='整片必须'):
        subject._official({'layout': 'landscape'}, 'render', ['ignored.mp4'])


def test_first_native_setup_has_an_explicit_new_dependency_cache(episode, monkeypatch):
    from types import SimpleNamespace
    path, _, _ = episode
    built, _ = subject.check(path)
    built.update(directory=str(path.parent), native={'instance': str(path.parent / 'new-instance')})
    commands = []
    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
    monkeypatch.setattr(subject.subprocess, 'run', fake_run)
    subject._official(built, 'setup', ['--language', 'zh'])
    command = commands[0]
    assert command[command.index('--cache') + 1] == str(path.parent / 'native-dependencies')
    assert command.index('--cache') < command.index('setup')


def test_existing_dependency_cache_is_bound_but_still_validated_by_official_setup(episode, monkeypatch):
    from types import SimpleNamespace
    path, value, _ = episode
    cache = path.parent / 'existing-dependencies'
    cache.mkdir()
    save(cache / 'dependencies.json', {'schema': 'motiongit-dependencies/1', 'runtimeLockSha256': 'a' * 64,
                                     'npmLockSha256': 'b' * 64, 'pythonRequirementsSha256': 'c' * 64})
    value['native_dependency_cache'] = str(cache)
    save(path, value)
    built, _ = subject.check(path)
    assert built['native_dependency_cache']['receipt_sha256'] == subject.sha(cache / 'dependencies.json')
    built.update(directory=str(path.parent), native={'instance': str(path.parent / 'new-instance')})
    commands = []
    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
    monkeypatch.setattr(subject.subprocess, 'run', fake_run)
    subject._official(built, 'setup', ['--language', 'zh'])
    assert commands[0][commands[0].index('--cache') + 1] == str(cache)
    assert 'setup' in commands[0]
    (cache / 'dependencies.json').write_text('{}', encoding='utf8')
    with pytest.raises(ValueError, match='签收'):
        subject.check(path)


def test_explicit_group_clock_cannot_truncate_voice_or_speed_actions():
    p = subject.read(subject.PROFILE)
    with pytest.raises(ValueError):
        subject.timeline(p, 31., {'group_frames': [348, 695, 793]}, 'landscape')
    with pytest.raises(ValueError):
        subject.timeline(p, 30., {'group_frames': [200, 695, 793]}, 'landscape')
    with pytest.raises(ValueError):
        subject.timeline(p, 30., {'group_frames': [348, 695, 793]}, 'portrait45')


def test_build_loader_checks_original_assets_even_after_derivatives_exist(episode):
    path, value, _ = episode
    built, _ = subject.check(path)
    built.update(status='built', directory=str(path.parent), prepared_files={})
    build_path = path.parent / 'content-build.json'
    save(build_path, built)
    assert subject.load_build(build_path)['input_sha256'] == built['input_sha256']
    Path(value['voice']['path']).write_bytes(b'changed source')
    with pytest.raises(ValueError, match='原声'):
        subject.load_build(build_path)
