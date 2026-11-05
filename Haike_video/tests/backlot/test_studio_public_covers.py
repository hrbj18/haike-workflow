"""Source updates must carry actual styles, independent of private bindings."""
import hashlib
import io
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from backlot import studio_template_library as library
from backlot import studio_motion_preferred as preferred
from backlot.studio_api import router


def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_clean_source_gallery_serves_eighteen_distinct_verified_style_covers(tmp_path, monkeypatch):
    monkeypatch.setattr(library, 'BINDINGS', tmp_path / 'absent.json')
    monkeypatch.setattr(library, 'COVERS', tmp_path / 'absent-private-covers')
    http = client()
    cards = http.get('/api/studio/template-library').json()['templates']
    selected = [row for row in cards if row.get('preferred_production')]
    assert len(selected) == 18
    manifest = json.loads((library.PUBLIC_COVERS / 'manifest.json').read_text(encoding='utf-8'))
    assert {row['gallery_id'] for row in preferred.preferences()} <= set(manifest['covers'])
    hashes = set()
    for card in selected:
        assert card['poster'] and card['poster_source'] == 'public-style'
        expected = manifest['covers'][card['id']]
        assert expected['template_id'] == card['preferred_production']['template_id']
        assert expected['version'] == card['preferred_production']['version']
        assert expected['source']['kind'] == 'completed-video-cover'
        assert expected['source']['template_id'] == expected['template_id']
        assert len(expected['source']['video_sha256']) == 64
        assert card['cover_note'].startswith('上次成片画面')
        assert card['guide'] and http.get(card['guide']).status_code == 200
        response = http.get(card['poster'])
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('image/')
        assert hashlib.sha256(response.content).hexdigest() == expected['sha256']
        with Image.open(io.BytesIO(response.content)) as picture:
            assert picture.size == (expected['width'], expected['height'])
            picture.verify()
        hashes.add(expected['sha256'])
    assert len(hashes) == 18


def test_fixed_original_covers_also_ship_with_source_and_keep_local_override(tmp_path, monkeypatch):
    monkeypatch.setattr(library, 'BINDINGS', tmp_path / 'absent.json')
    monkeypatch.setattr(library, 'COVERS', tmp_path / 'absent-private-covers')
    http = client()
    cards = [row for row in http.get('/api/studio/template-library').json()['templates']
             if row['category'] == '固定模板']
    assert len(cards) == 43
    manifest = json.loads((library.PUBLIC_COVERS / 'manifest.json').read_text(encoding='utf-8'))
    for card in cards:
        expected = manifest['covers'][card['id']]
        assert expected['source']['kind'] == 'existing-fixed-template-cover'
        assert card['poster']
        response = http.get(card['poster'])
        assert response.status_code == 200
        assert hashlib.sha256(response.content).hexdigest() == expected['sha256']
        with Image.open(io.BytesIO(response.content)) as picture:
            picture.verify()
    original = tmp_path / 'my-fixed-cover.png'
    original.write_bytes(b'original-user-fixed-cover')
    library.BINDINGS.write_text(json.dumps({'store-footage-18': {'poster': str(original)}}), encoding='utf-8')
    assert library.media('store-footage-18', 'poster') == original


def test_packaged_style_wins_over_generic_local_cover_and_preserves_original(tmp_path, monkeypatch):
    original = tmp_path / 'old-local.jpg'
    original.write_bytes(b'original-user-cover-kept-without-conversion')
    bindings = tmp_path / 'bindings.json'
    value = json.dumps({'chromatic-07': {'poster': str(original)}})
    bindings.write_text(value, encoding='utf-8')
    monkeypatch.setattr(library, 'BINDINGS', bindings)
    http = client()
    card = next(row for row in http.get('/api/studio/template-library').json()['templates']
                if row['id'] == 'chromatic-07')
    assert card['poster_source'] == 'public-style'
    assert http.get(card['poster']).content != original.read_bytes()
    assert http.get(card['original_poster']).content == original.read_bytes()
    assert bindings.read_text(encoding='utf-8') == value
    assert original.read_bytes() == b'original-user-cover-kept-without-conversion'


def test_changed_public_cover_or_escaping_manifest_cannot_be_served(tmp_path, monkeypatch):
    monkeypatch.setattr(library, 'PUBLIC_COVERS', tmp_path / 'public')
    monkeypatch.setattr(library, 'BINDINGS', tmp_path / 'absent.json')
    monkeypatch.setattr(library, 'COVERS', tmp_path / 'absent')
    library.PUBLIC_COVERS.mkdir()
    cover = library.PUBLIC_COVERS / 'chromatic-07.png'
    cover.write_bytes(b'wrong-cover')
    manifest = {'schema': 'haike.template-public-covers/1', 'covers': {
        'chromatic-07': {'file': 'chromatic-07.png', 'template_id': 'chromatic-07',
                         'version': next(row['version'] for row in preferred.preferences() if row['gallery_id'] == 'chromatic-07'),
                         'sha256': '0' * 64, 'size': cover.stat().st_size}}}
    document = library.PUBLIC_COVERS / 'manifest.json'
    document.write_text(json.dumps(manifest), encoding='utf-8')
    assert library.media('chromatic-07', 'poster') is None
    outside = tmp_path / 'outside.png'
    outside.write_bytes(b'private')
    manifest['covers']['chromatic-07'].update(file='../outside.png', size=7,
                                            sha256=hashlib.sha256(b'private').hexdigest())
    document.write_text(json.dumps(manifest), encoding='utf-8')
    assert library.media('chromatic-07', 'poster') is None
