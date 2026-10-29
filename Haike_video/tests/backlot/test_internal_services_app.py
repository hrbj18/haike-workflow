"""The internal configuration app is separate, loopback-only and same-origin."""
from fastapi.testclient import TestClient

from backlot.internal_services import create_app


def test_internal_mode_update_has_no_customer_endpoint_and_rejects_cross_origin(tmp_path):
    app = create_app(tmp_path / 'projects')
    client = TestClient(app, base_url='http://127.0.0.1:14757')
    response = client.put('/api/internal/mode', json={'mode': 'internal'}, headers={'Origin': 'https://foreign.example'})
    assert response.status_code == 403
    assert not (tmp_path / '.backlot/service-mode.json').exists()
    assert client.put('/api/internal/mode', json={'mode': 'internal'}, headers={'Origin': 'http://127.0.0.1:14757'}).status_code == 200
    assert (tmp_path / '.backlot/service-mode.json').is_file()
    assert client.get('/api/health').json()['app'] == 'haike-internal-services'
    assert client.get('/api/studio/drafts').status_code == 404
    assert client.get('/', headers={'Host': 'foreign.example'}).status_code == 400


def test_internal_management_exposes_blank_secret_fields_and_no_production_workers(tmp_path, monkeypatch):
    import backlot.studio_services as services
    calls = []
    monkeypatch.setattr(services, 'settings', lambda studio: {'service_mode': 'internal', 'providers': [
        {'id': 'fake', 'name': '测试供应商', 'configured': True, 'fields': [{'name': 'api_key', 'secret': True, 'configured': True}]}]})
    monkeypatch.setattr(services, 'update_provider', lambda studio, provider, data: calls.append((provider, data)) or {'configured': True})
    app = create_app(tmp_path / 'projects')
    client = TestClient(app, base_url='http://127.0.0.1:14757')
    settings = client.get('/api/internal/services').json()
    assert 'value' not in settings['providers'][0]['fields'][0]
    assert client.put('/api/internal/services/fake', json={'api_key': 'fake-test-only'}, headers={'Origin': 'http://127.0.0.1:14757'}).json() == {'configured': True}
    assert calls == [('fake', {'api_key': 'fake-test-only'})]
    assert not hasattr(app.state, 'production_queue')
