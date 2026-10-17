"""Legacy pages retain tools while customer supplier controls remain private."""
import pytest

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from backlot.customer_surface import install


def application():
    app = FastAPI()
    install(app)

    @app.get('/legacy/projects')
    def page():
        return HTMLResponse('<html><head><title>项目工作台</title></head><body>原项目能力</body></html>')

    @app.get('/api/tencent/config')
    def supplier():
        return {'configured': True}

    @app.post('/api/bailian/test')
    def supplier_paid_test():
        raise AssertionError('普通页面不能触发旧供应商的无报价连接测试')

    @app.get('/api/studio/audio-center')
    def customer_audio():
        return {'items': []}

    return app


def test_legacy_visual_shell_and_customer_api_boundary(monkeypatch):
    monkeypatch.delenv('HAIKE_INTERNAL_TESTING', raising=False)
    client = TestClient(application())
    page = client.get('/legacy/projects')
    assert page.status_code == 200 and '原项目能力' in page.text
    assert '/ui/legacy-shell.js' in page.text and '/ui/haike-brand.css' in page.text
    assert 'window.__HAIKE_INTERNAL__=false' in page.text
    assert int(page.headers['content-length']) == len(page.content)
    assert client.get('/api/tencent/config').status_code == 403
    assert client.post('/api/bailian/test', json={}).status_code == 403
    assert client.get('/api/studio/audio-center').status_code == 200


def test_internal_supplier_service_is_retained_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv('HAIKE_INTERNAL_TESTING', '1')
    client = TestClient(application())
    assert client.get('/api/tencent/config').json() == {'configured': True}
    assert 'window.__HAIKE_INTERNAL__=true' in client.get('/legacy/projects').text


@pytest.mark.parametrize(('method', 'path'), [
    ('GET', '/api/ai-text/config'),
    ('PUT', '/api/ai-text/config'),
    ('POST', '/api/ai-text/test'),
    ('GET', '/api/ai-text/doubao/config'),
    ('PUT', '/api/ai-text/doubao/config'),
    ('POST', '/api/ai-text/doubao/test'),
    ('GET', '/api/ai-text/providers'),
    ('POST', '/api/audio-center/local-voices'),
    ('GET', '/api/asr/doubao/config'),
])
def test_customer_cannot_reach_retained_internal_supplier_handlers(monkeypatch, method, path):
    monkeypatch.delenv('HAIKE_INTERNAL_TESTING', raising=False)
    app = application()

    def supplier_handler():
        raise AssertionError('普通用户请求不得执行供应商配置、测试或音色创建')

    app.add_api_route(path, supplier_handler, methods=[method])
    response = TestClient(app).request(method, path, json={})
    assert response.status_code == 403
    assert '海客Key' in response.json()['detail']
