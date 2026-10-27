"""The read-only gallery must not expose arbitrary files or become a draft template."""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot import studio_template_library as library
from backlot.studio_api import router


def test_inventory_has_unique_ids_and_existing_guides():
    items = library.entries()
    assert len(items) >= 37
    assert len({i['id'] for i in items}) == len(items)
    for item in items:
        assert library.document(item['id']).is_file(), item['id']
    for number in range(18, 22):
        item = library.entry(f'store-footage-{number}')
        assert item['status'] == '完整版'
        guide = library.document(item['id']).read_text(encoding='utf-8')
        assert 'BGM' in guide and '20Mbps' in guide
        if number >= 20:
            assert '只替换left主窗' in guide and '0.2秒网格' in guide


def test_private_media_is_explicit_read_only_and_range_capable(tmp_path, monkeypatch):
    monkeypatch.setattr(library, 'COVERS', tmp_path / 'no-distributed-covers')
    media = tmp_path / 'sample.mp4'
    media.write_bytes(b'0123456789')
    secret = tmp_path / 'secret.txt'
    secret.write_text('do-not-expose')
    bindings = tmp_path / 'bindings.json'
    bindings.write_text(json.dumps({'store-footage-20': {'sample': str(media), 'poster': str(secret)}}))
    monkeypatch.setattr(library, 'BINDINGS', bindings)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    result = client.get('/api/studio/template-library')
    assert result.status_code == 200
    assert str(tmp_path) not in result.text
    assert 'secret.txt' not in result.text
    assert client.get('/api/studio/template-library/store-footage-20/media/poster').status_code == 404
    assert client.get('/api/studio/template-library/unknown/media/sample').status_code == 404
    assert client.get('/api/studio/template-library/store-footage-20/media/secret.txt').status_code == 404
    response = client.get('/api/studio/template-library/store-footage-20/media/sample', headers={'Range': 'bytes=2-5'})
    assert response.status_code == 206 and response.content == b'2345'
    assert client.get('/api/studio/template-library/store-footage-20/guide').json()['text'].startswith('# 店长')
    assert client.get('/api/studio/template-library/unknown/guide').status_code == 404


def test_document_stays_in_template_or_runbook_roots(monkeypatch):
    monkeypatch.setattr(library, 'entry', lambda _: {'runbook': '.local/private.md'})
    assert library.document('anything') is None


def test_portable_covers_work_without_private_bindings(tmp_path, monkeypatch):
    covers = tmp_path / 'relocated-package' / 'covers'
    covers.mkdir(parents=True)
    poster = covers / 'store-footage-20.jpg'
    poster.write_bytes(b'portable screenshot fixture')
    monkeypatch.setattr(library, 'COVERS', covers)
    monkeypatch.setattr(library, 'BINDINGS', tmp_path / 'missing-private-map.json')
    assert library.media('store-footage-20', 'poster') == poster
    assert library.media('store-footage-20', 'sample') is None
    assert library.media('../store-footage-20', 'poster') is None
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    listing = client.get('/api/studio/template-library').json()['templates']
    item = next(t for t in listing if t['id'] == 'store-footage-20')
    assert item['poster'] and item['sample'] is None
    assert client.get(item['poster']).content == poster.read_bytes()


def test_stale_or_malformed_private_binding_falls_back_to_portable_cover(tmp_path, monkeypatch):
    monkeypatch.setattr(library, 'COVERS', tmp_path)
    poster = tmp_path / 'store-footage-20.jpg'
    poster.write_bytes(b'fixture')
    bindings = tmp_path / 'bindings.json'
    monkeypatch.setattr(library, 'BINDINGS', bindings)
    for content in ('invalid JSON', '[]', '{"store-footage-20": null}',
                    json.dumps({'store-footage-20': {'poster': 'missing.jpg'}})):
        bindings.write_text(content)
        assert library.media('store-footage-20', 'poster') == poster
