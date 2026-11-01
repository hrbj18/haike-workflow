"""Isolated native protocol contracts; fixtures do not certify rendered graphics."""
import json
from pathlib import Path
import struct
import wave

import pytest

from backlot import studio_motiongit as motion
from backlot import studio_motiongit_render as render
from backlot import studio_motion_knowledge as native
from backlot.production_queue import ProductionQueue
from backlot.work_catalog import WorkError, sha


@pytest.fixture
def period(tmp_path, monkeypatch):
    monkeypatch.setattr(motion, 'STORE', tmp_path / 'private')
    monkeypatch.setattr('backlot.studio_render.media_probe', lambda _: {'duration': 8})
    tools = []
    for name in ['ffmpeg', 'ffprobe', 'helper', 'original.motion']:
        file = tmp_path / name; file.write_bytes(('isolated-' + name).encode()); tools.append(file)
    monkeypatch.setattr('lib.ffmpeg_locator.resolve_ffmpeg_pair', lambda: tuple(map(str, tools[:2])))
    monkeypatch.setattr(native.shutil, 'which', lambda _: str(tools[2]))
    monkeypatch.setattr(motion, 'helper_identity', lambda _: {'sha256': sha(tools[2])})
    package = {'id':'mg-native-fixture','template_id':'knowledge-explainer-sketchnote','version':'2.7.3',
               'verification':'verified','support':'official-helper','sha256':sha(tools[3]),
               'path':str(tools[3]),'helper':str(tools[2]), 'workflows':{'native':{'schema':{'type':'object'}}}}
    # Keep this test focused on the native boundary, without runtime path rebinding.
    original_get = motion._get
    monkeypatch.setattr(motion, '_get', lambda table, identity: package if table == 'packages' else original_get(table, identity))
    paths = {}
    for name, amplitude in [('voice.wav', 1000), ('music.wav', 1500)]:
        path = tmp_path / name
        with wave.open(str(path), 'wb') as stream:
            stream.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            stream.writeframes(struct.pack('<h', amplitude) * (8 * 24000))
        paths[name] = path
    captions = [{'id':'c1','start':.1,'end':7.8,'text':'Isolated contract fixture, not real ASR.'}]
    evidence = {'audioSha256':sha(paths['voice.wav']), 'method':'measured', 'captions':captions}
    path = tmp_path / 'sentence.json';path.write_text(json.dumps(evidence), encoding='utf-8');paths[path.name] = path
    params = {'creationProfile':'knowledge-story/1','durationSeconds':8,'fps':60,'layout':'portrait',
              'script':captions[0]['text'],'captions':captions,
              'audio':{'narration':{'mode':'file','path':'voice.wav'},'music':{'mode':'file','path':'music.wav'}},
              'presenter':{'mode':'none'}, 'sentenceEvidence':{'path':'sentence.json','sha256':sha(path),
              'method':'measured','audioSha256':sha(paths['voice.wav'])}}
    draft = motion.save_draft(package['id'], 'native', params, title='隔离协议测试')
    for name, path in paths.items():motion.save_asset(draft['id'], name, path.read_bytes())
    queue = ProductionQueue(tmp_path / 'queue.sqlite3', tmp_path / 'projects')
    return package, draft, queue, paths


def test_native_freeze_and_submit_use_existing_queue_without_executing_package(period, monkeypatch):
    _, draft, queue, _ = period
    monkeypatch.setattr(motion.subprocess, 'run', lambda *a, **kw: pytest.fail('freeze executed a tool'))
    request = render.freeze(queue, draft['id'])
    assert request == render.freeze(queue, draft['id'])
    assert request['native_protocol'] == native.PROTOCOL and request['paid_calls'] == 0
    job = render.submit(queue, request, phase='preview')
    assert job['kind'] == render.KIND and job['status'] == 'paused'
    assert job['title'] == draft['title']
    native.validate(queue, request)
    project = queue.projects_root / request['project_id']
    (project / 'assets/motiongit/voice.wav').write_bytes(b'changed')
    with pytest.raises(WorkError, match='冻结素材已变化'):
        native.validate(queue, request)


def test_native_version_is_exact_and_unknown_package_does_not_execute(period):
    package, draft, queue, _ = period
    package['version'] = 'future'
    with pytest.raises(WorkError, match='尚未接入'):
        render.freeze(queue, draft['id'])


@pytest.mark.parametrize('change, message', [
    (lambda p: p['audio']['narration'].update(path='../voice.wav'), '平面绑定名'),
    (lambda p: p.update(durationSeconds=7), '整片时钟'),
    (lambda p: p['captions'][0].update(text='Unmatched text'), '同源句级证据'),
])
def test_native_source_and_caption_bindings_cannot_be_guessed(period, change, message):
    _, draft, queue, _ = period
    change(draft['parameters'])
    updated = motion.save_draft(draft['package_id'], 'native', draft['parameters'], draft_id=draft['id'], revision=draft['revision'])
    with pytest.raises(WorkError, match=message):
        render.freeze(queue, updated['id'])
