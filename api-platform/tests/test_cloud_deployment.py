import pytest
from fastapi.testclient import TestClient

from platform_app.app import create_app
from platform_app.deployment import public_origin

ORIGIN = 'https://8.138.207.71:17894'


def test_cloud_origin_https_cookie_and_admin_boundaries(env):
    store, _, _, _, _, user, _ = env
    app = create_app(store.path, worker_enabled=False, testing=True, public_origin=ORIGIN)
    with TestClient(app, base_url=ORIGIN, headers={'Origin': ORIGIN}) as client:
        assert client.get('/health').json()['mode'] == 'cloud_commercial'
        assert client.get('/portal/v1/setup-status').json()['environment'] == 'cloud'
        login = client.post('/portal/v1/login', json={'username': user['email'], 'password': 'Test-only-password-123'})
        assert login.status_code == 200
        assert 'Secure' in login.headers['set-cookie'] and 'HttpOnly' in login.headers['set-cookie']
        client.headers['X-CSRF-Token'] = login.json()['csrf']
        assert client.get('/portal/v1/me').json()['user']['id'] == user['id']
        assert client.get('/admin/v1/users').status_code == 403
        assert client.post('/portal/v1/setup', json={'username': 'new-admin', 'password': '1'}).status_code == 403
        assert client.post('/portal/v1/register', headers={'Origin': 'https://evil.test'}, json={'username': 'evil', 'password': '1'}).status_code == 403
        assert client.get('/health', headers={'Host': 'evil.test'}).status_code == 403
        assert client.get('http://8.138.207.71:17894/health').status_code == 403


def test_cloud_refuses_public_initialization_without_admin(tmp_path):
    app = create_app(tmp_path / 'empty.sqlite3', worker_enabled=False, public_origin=ORIGIN)
    with pytest.raises(RuntimeError, match='Initialize an administrator'), TestClient(app, base_url=ORIGIN):
        pass


@pytest.mark.parametrize('value', ['http://8.138.207.71:17894', 'https://x.test/path', 'https://u:p@x.test', 'https://x.test?key=x', 'https://x.test:99999', 'https://x.test#fragment', 'https://x .test'])
def test_invalid_cloud_origin_is_rejected(value):
    with pytest.raises(ValueError):
        public_origin(value)
