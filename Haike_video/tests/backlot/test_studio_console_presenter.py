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
    assert (opening['startFrame'],opening['endFrame'])==(0,215)
    assert (ending['startFrame'],ending['endFrame'])==(1524,1824)
    assert presenter.policy(inputs('hidden'),1824)['endFrame']==0
    with pytest.raises(WorkError):presenter.policy({**inputs('opening'),'layout':'landscape'},1824)
    with pytest.raises(WorkError):presenter.policy(inputs('random'),1824)


def test_extension_is_idempotent_bound_and_does_not_edit_native_scenes(tmp_path):
    folder=tmp_path/'project';folder.mkdir()
    index=folder/'index.html';index.write_bytes(b'<html><body>native</body></html>')
    scene=folder/'scenes.js';scene.write_bytes(b'native-scene')
    presenter.install(tmp_path,inputs('opening'),1824)
    before=index.read_bytes()
    presenter.install(tmp_path,inputs('opening'),1824)
    assert index.read_bytes()==before and scene.read_bytes()==b'native-scene'
    assert before.count(b'haike-presenter.js')==1
    receipt=json.loads((tmp_path/'haike-presenter.json').read_bytes())
    assert receipt['original_index_sha256']!=receipt['index_sha256']
    with pytest.raises(WorkError):presenter.install(tmp_path,inputs('closing'),1824)
    (folder/'haike-presenter.js').write_bytes(b'changed')
    with pytest.raises(WorkError):presenter.install(tmp_path,inputs('opening'),1824)


def test_never_changes_already_previewed_project(tmp_path):
    (tmp_path/'project').mkdir()
    (tmp_path/'project/index.html').write_bytes(b'<body></body>')
    (tmp_path/'preview.json').write_bytes(b'{}')
    with pytest.raises(WorkError):presenter.install(tmp_path,inputs('opening'),1824)
    assert (tmp_path/'project/index.html').read_bytes()==b'<body></body>'
