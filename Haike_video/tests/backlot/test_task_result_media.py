"""Result previews stay bound to their version; no production/provider calls."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backlot.work_api import router


def test_pinned_result_cover_cannot_silently_switch_to_newer_materials(tmp_path):
    old = tmp_path / 'old.jpg';old.write_bytes(b'old-cover')
    new = tmp_path / 'new.jpg';new.write_bytes(b'new-cover')
    class Catalog:
        def get(self, identity):
            assert identity == 'work-test'
            return {'project_id': 'test', 'materials': [
                {'version_id': 'v1', 'data': {'cover_path': str(old)}},
                {'version_id': 'v2', 'data': {'cover_path': str(new)}}]}
        def project(self, identity):
            return tmp_path
    app = FastAPI();app.include_router(router);app.state.work_catalog = Catalog()
    client = TestClient(app)
    assert client.get('/api/works/work-test/cover?version=v1').content == b'old-cover'
    assert client.get('/api/works/work-test/cover?version=v2').content == b'new-cover'
    assert client.get('/api/works/work-test/cover').content == b'new-cover'
    assert client.get('/api/works/work-test/cover?version=missing').status_code == 404
