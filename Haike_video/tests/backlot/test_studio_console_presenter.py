import json
from pathlib import Path

import pytest

from backlot import studio_console_presenter as presenter
from backlot.work_catalog import WorkError


def inputs(mode):
    return {'layout':'portrait', 'presenterMode':mode,
            'segments':[{'durationFrames':215},{'durationFrames':1609}]}


def test_appearance_uses_complete_scene_and_output_frames():
    opening=presenter.policy(inputs('opening'),1824)
    ending=presenter.policy(inputs('closing'),1824)
    assert (opening['startFrame'],opening['endFrame'])==(0,180)
    assert (ending['startFrame'],ending['endFrame'])==(1524,1824)
    assert presenter.policy(inputs('hidden'),1824)['endFrame']==0
    with pytest.raises(WorkError):presenter.policy({**inputs('opening'),'layout':'landscape'},1824)
    with pytest.raises(WorkError):presenter.policy(inputs('random'),1824)


def test_extension_is_idempotent_bound_and_does_not_edit_native_scenes(tmp_path):
    folder=tmp_path/'project';folder.mkdir()
    index=folder/'index.html';index.write_bytes(b'<html><body>native</body></html>')
    scene=folder/'scenes.js';scene.write_bytes(b'native-scene')
    original={p.name:p.read_bytes() for p in folder.iterdir()}
    presenter.install(tmp_path,inputs('opening'),1824)
    before=index.read_bytes()
    presenter.install(tmp_path,inputs('opening'),1824)
    assert index.read_bytes()==before and scene.read_bytes()==b'native-scene'
    assert before==b'<html><body>native</body></html>'
    assert {p.name:p.read_bytes() for p in folder.iterdir()}==original
    receipt=json.loads((tmp_path/'haike-presenter.json').read_bytes())
    assert receipt['original_index_sha256']==receipt['index_sha256']
    with pytest.raises(WorkError):presenter.install(tmp_path,inputs('closing'),1824)
    (tmp_path/'haike-composition/haike-presenter.js').write_bytes(b'changed')
    with pytest.raises(WorkError):presenter.install(tmp_path,inputs('opening'),1824)


def test_preserves_official_preview_and_native_html(tmp_path):
    (tmp_path/'project').mkdir()
    (tmp_path/'project/index.html').write_bytes(b'<body></body>')
    (tmp_path/'preview.json').write_bytes(b'{}')
    presenter.install(tmp_path,inputs('opening'),1824)
    assert (tmp_path/'project/index.html').read_bytes()==b'<body></body>'
    assert (tmp_path/'preview.json').read_bytes()==b'{}'


def test_script_change_invalidates_prepared_compiler_receipt(tmp_path, monkeypatch):
    from backlot import studio_motion_console as compiler
    script=tmp_path/'presenter.js';script.write_bytes(b'version-one')
    monkeypatch.setattr(presenter,'SCRIPT',script)
    before=presenter.identity()
    receipt=tmp_path/'build.json'
    receipt.write_text(json.dumps({'schema':compiler.SCHEMA,
        'compiler_sha256':compiler.sha(compiler.__file__),
        'contract_sha256':compiler.sha(compiler.PROFILE),
        'presenter_identity':before}),encoding='utf-8')
    script.write_bytes(b'version-two')
    assert presenter.identity()!=before
    with pytest.raises(WorkError,match='重新准备'):
        compiler.load(receipt)
