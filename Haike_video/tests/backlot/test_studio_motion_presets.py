"""Preset identity, private-envelope resolution and existing-draft compatibility."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import runpy
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backlot import studio_motiongit as motion
from backlot import studio_motion_presets as presets
from backlot.studio_motiongit_api import router
from backlot.work_catalog import WorkError, sha


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(motion, 'STORE', tmp_path / 'private')
    monkeypatch.setattr(motion, 'helper_command', lambda *a, **k: pytest.fail('preset invoked a provider/helper'))
    return tmp_path


def fake_package(tmp_path, row, monkeypatch):
    original = tmp_path / (row['id'] + '.motion'); original.write_bytes(b'personal-envelope-for-this-test')
    helper = tmp_path / 'motion.mjs'; helper.write_bytes(b'independently-pinned-test-helper')
    monkeypatch.setitem(motion.HELPER_PINS, '1.0.0-rc.54', (sha(helper), helper.stat().st_size))
    p = {**row['package'], 'id': 'mg-other-users-envelope', 'path': str(original), 'sha256': sha(original),
         'verification': 'verified', 'helper': str(helper), 'support': 'official-helper',
         'workflows': {row['workflow']: {'schema': {'type': 'object'}, 'controls': {}}}}
    motion._put_package(p)
    return p


def test_public_recipe_has_no_episode_bindings_or_fixed_clock(isolated):
    names = set()
    for row in presets.manifest()['presets']:
        entry, recipe = presets.load(row['id']); names.add(entry['id'])
        text = json.dumps(recipe, ensure_ascii=False)
        for forbidden in ['D:\\', 'C:\\', '.local/', 'mgd-', 'work-', '侯总', 'voice_sha256', 'reviewed', '30.6', '22.8']:
            assert forbidden not in text
        assert not recipe['parameters'].get('provenance')
        assert recipe['binding']['clock'] == 'actual-voice-and-caption-events'
    assert len(names) == 3


def test_missing_originals_are_not_ready_or_executable(isolated):
    before = sha(motion.ROOT / 'Haike_video/templates/hum-production-v1/quest/params.example.json')
    rows = presets.catalog()['presets']
    assert rows[0]['can_create'] and rows[0]['status'] == 'needs-inputs'
    assert all(not r['can_create'] and r['status'] == 'needs-package' for r in rows[1:])
    with pytest.raises(WorkError, match='合法原包'):
        presets.create(rows[1]['id'])
    d = presets.create(rows[0]['id'])
    assert d['preset_source']['recipe_sha256'] == rows[0]['sha256']
    assert d['package_sha256'] == before
    assert len(d['parameters']['props']['scenes']) == 7
    assert all('from' not in s and 'frames' not in s for s in d['parameters']['props']['scenes'])
    with pytest.raises(WorkError, match='待绑定'):
        motion.validate_draft(d['id'])


def test_update_and_clone_keep_frozen_preset_identity_and_old_draft(isolated):
    old = motion.save_draft('haike-quest-v1', 'hum-production', {'old-input': True}, title='历史草稿')
    created = presets.create('quest-approved-portrait-v1')
    edited = motion.save_draft(created['package_id'], created['workflow'], created['parameters'],
                              draft_id=created['id'], revision=1, title='本期内容')
    clone = motion.clone_draft(edited['id'])
    assert clone['preset_source'] == edited['preset_source'] == created['preset_source']
    assert motion.draft(old['id']) == old
    assert motion.draft(edited['id'])['preset_source'] == created['preset_source']
    assert sha(motion.ROOT / 'Haike_video/templates/hum-production-v1/quest/params.example.json') == old['package_sha256']


def test_current_users_exact_verified_package_is_resolved(isolated, monkeypatch):
    row, _ = presets.load('paper-approved-portrait-v1')
    p = fake_package(isolated, row, monkeypatch)
    created = presets.create(row['id'])
    assert created['package_id'] == p['id']
    assert created['package_sha256'] == p['sha256']
    p['version'] = '2.7.22'; motion._put_package(p)
    with pytest.raises(WorkError, match='2.7.21-alpha.5'):
        presets.create(row['id'])


def test_tampered_original_or_helper_is_not_usable(isolated, monkeypatch):
    row, _ = presets.load('paper-approved-portrait-v1')
    p = fake_package(isolated, row, monkeypatch)
    Path(p['helper']).write_bytes(b'changed')
    assert not presets.catalog()['presets'][1]['can_create']
    with pytest.raises(WorkError, match='工具'):
        presets.create(row['id'])
    p = fake_package(isolated, row, monkeypatch)
    Path(p['path']).write_bytes(b'changed-original')
    with pytest.raises(WorkError, match='原包已改变'):
        presets.create(row['id'])


def test_recipe_tamper_is_detected_without_executing(isolated, monkeypatch):
    folder = isolated / 'presets'; folder.mkdir()
    for path in presets.FOLDER.glob('*.json'):
        (folder / path.name).write_bytes(path.read_bytes())
    monkeypatch.setattr(presets, 'FOLDER', folder)
    (folder / 'quest-approved-portrait-v1.json').write_text('{}', encoding='utf-8')
    with pytest.raises(WorkError, match='预设文件'):
        presets.create('quest-approved-portrait-v1')


@pytest.mark.parametrize('change', ['kind', 'path', 'transition', 'photos'])
def test_named_preset_rejects_removed_defining_mechanisms(isolated, change):
    _, recipe = presets.load('quest-approved-portrait-v1')
    p = deepcopy(recipe['parameters']); scenes = p['props']['scenes']
    if change == 'kind': scenes[4]['quest']['kind'] = 'media'
    if change == 'path': scenes[5]['quest']['path']['id'] = 'different-graph'
    if change == 'transition': scenes[2]['quest'].pop('transition')
    if change == 'photos': scenes[6]['quest']['photoIds'].pop()
    with pytest.raises(WorkError):
        presets.create('quest-approved-portrait-v1', parameters=p)


def test_api_creation_origins_and_shared_identity(isolated):
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        rows = client.get('/api/studio/motiongit/presets').json()['presets']
        path = '/api/studio/motiongit/presets/' + rows[0]['id'] + '/drafts'
        assert client.post(path, json={}, headers={'Origin': 'https://foreign.invalid'}).status_code == 403
        created = client.post(path, json={}, headers={'Origin': 'http://testserver'})
        assert created.status_code == 200, created.text
        assert created.json()['preset_source']['recipe_sha256'] == rows[0]['sha256']
        capability = client.get('/api/studio/motiongit/preset-capability')
        assert capability.status_code == 200
        assert capability.json()['files'] == presets.delivery_files()
        assert len(capability.json()['availability']) == 3


def test_cli_lists_the_same_public_identity(isolated, monkeypatch, capsys):
    script = motion.ROOT / 'Haike_video/scripts/motiongit.py'
    monkeypatch.setattr(sys, 'argv', [str(script), 'presets'])
    runpy.run_path(str(script), run_name='__main__')
    assert json.loads(capsys.readouterr().out) == presets.catalog()


def test_capability_identity_binds_actual_files(isolated):
    value = presets.capability_identity()
    actual = hashlib.sha256(json.dumps(value['files'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert value['sha256'] == actual
    assert all(sha(presets.ROOT / name) == digest for name, digest in value['files'].items())
