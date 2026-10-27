"""Reference selection persists without becoming an unsupported render parameter."""
import json
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backlot import studio_art_direction as art
from backlot import studio_motiongit as motion
from backlot.studio_motiongit_api import router
from backlot.work_catalog import WorkError


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(motion, 'STORE', tmp_path / 'private')
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def package(tmp_path):
    path = tmp_path / 'reference.motion'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('motion.json', json.dumps({'format': 'motiongit-template',
            'template': {'id': 'test', 'name': '测试'}, 'runtime': {'profile': 'html-canvas/1'}}))
        archive.writestr('params.schema.json', json.dumps({'type': 'object',
            'properties': {'title': {'type': 'string'}}, 'additionalProperties': False}))
    return motion.import_package(path)


def test_pinned_catalog_and_all_reference_digests():
    receipt = art.verify_references()
    assert receipt['valid'] and receipt['theme_count'] == 48 and receipt['checked_files'] == 99
    values = art.catalog()['themes']
    assert len({t['slug'] for t in values}) == 48
    assert all(t['name_zh'] and t['summary_zh'] and t['video_use_zh'] for t in values)


def test_reference_endpoints_and_planning_status(client):
    catalog = client.get('/api/studio/motiongit/art-directions').json()
    assert len(catalog['themes']) == 48
    selected = next(t for t in catalog['themes'] if t['slug'] == 'hum')
    image = client.get(selected['image_url'])
    assert image.status_code == 200 and image.headers['content-type'] == 'image/jpeg'
    assert image.content[:2] == b'\xff\xd8'
    assert '# Hum' in client.get(selected['reference_url']).text
    brief = client.get('/api/studio/motiongit/art-directions/hum/video-brief').json()
    assert brief['status'] == 'planning'
    assert set(brief['review'].values()) == {'pending'}
    assert client.get('/api/studio/motiongit/art-directions/unknown/image').status_code == 422


def test_selection_roundtrip_clone_clear_and_legacy_save(client, tmp_path):
    p = package(tmp_path)
    parameters = {'title': '同一套素材'}
    request = {'package_id': p['id'], 'workflow': 'native', 'parameters': parameters,
               'art_direction': {'theme_slug': 'hum', 'implementation_status': 'passed'}}
    d = client.post('/api/studio/motiongit/drafts', json=request).json()
    assert d['art_direction']['implementation_status'] == 'reference_selected'
    assert d['parameters'] == parameters and motion.validate_draft(d['id'])['valid']
    assert client.get('/api/studio/motiongit/drafts/' + d['id']).json()['art_direction'] == d['art_direction']
    copied = client.post('/api/studio/motiongit/drafts/' + d['id'] + '/clone').json()
    assert copied['art_direction'] == d['art_direction'] and copied['id'] != d['id']
    legacy = dict(d)
    legacy.pop('art_direction')
    updated = client.post('/api/studio/motiongit/drafts', json=legacy).json()
    assert updated['art_direction'] == d['art_direction']
    stale = client.post('/api/studio/motiongit/drafts', json={**d, 'art_direction': {}})
    assert stale.status_code == 422
    cleared = client.post('/api/studio/motiongit/drafts', json={**updated, 'art_direction': {}}).json()
    assert cleared['art_direction'] is None
    assert motion.draft(copied['id'])['art_direction'] == d['art_direction']


@pytest.mark.parametrize('value', [{'theme_slug': '../SKILL'}, {'theme_slug': 'unknown'},
                                  {'theme_slug': 'hum', 'source_commit': 'changed'}, 'hum'])
def test_invalid_selection_rejected(value):
    with pytest.raises(WorkError):
        art.normalize_selection(value)


def test_changed_image_is_not_served(tmp_path, monkeypatch):
    source = art.ROOT
    (tmp_path / 'themes').mkdir()
    for name in ('catalog.json', 'UPSTREAM.json'):
        (tmp_path / name).write_bytes((source / name).read_bytes())
    (tmp_path / 'themes/hum.jpg').write_bytes(b'changed')
    monkeypatch.setattr(art, 'ROOT', tmp_path)
    with pytest.raises(WorkError, match='已改变'):
        art.theme_asset('hum', 'jpg')
