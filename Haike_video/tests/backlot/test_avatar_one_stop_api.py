import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot.avatar_one_stop_api import router
from backlot.work_catalog import WorkError


@pytest.fixture
def client(tmp_path):
    class Flow:
        scope = 'only-this-account'
        advances = 0
        applies = 0
        def create(self, data):
            return {'id': 'os_'+'a'*32, 'status': 'queued'}
        def list(self, draft_id):
            return [self.get('owned')]
        def get(self, identity):
            if identity == 'foreign':
                raise WorkError('不属于本账号', 'missing')
            return {'id': identity, 'status': 'awaiting_agent'}
        def defaults(self):
            return {'template': '模板11', 'configured': True}
        def advance(self, identity):
            self.advances += 1
            return {'id': identity, 'status': 'awaiting_agent'}
        def context(self, identity):
            return {'action': 'refine_portrait'}
        def apply(self, identity, data):
            self.applies += 1
            return {'id': identity, 'status': 'queued'}
        def revise(self, identity, data):
            assert identity=='owned' and data['speech_rate']==1.15
            return {'id':'new-rate-revision','status':'queued'}
        def file(self, identity, kind):
            if identity == 'foreign':
                raise WorkError('不属于本账号', 'missing')
            p = tmp_path/'output.mp4'
            p.write_bytes(b'test-existing-output')
            return p
    app = FastAPI()
    app.state.studio = object()
    instance = Flow()
    app.state.one_stop_factory = lambda studio: instance
    app.include_router(router)
    with TestClient(app) as test:
        yield test, instance


def test_reading_task_and_media_never_launches_production(client):
    http, flow = client
    assert http.get('/api/studio/one-stop/defaults').status_code == 200
    assert http.get('/api/studio/one-stop/jobs').status_code == 200
    assert http.get('/api/studio/one-stop/jobs/owned/context').json()['action'] == 'refine_portrait'
    response = http.get('/api/studio/one-stop/jobs/owned/files/video')
    assert response.content == b'test-existing-output'
    assert response.headers['cache-control'] == 'private, no-store'
    assert http.get('/api/studio/one-stop/jobs/foreign').status_code == 404
    assert http.get('/api/studio/one-stop/jobs/foreign/files/video').status_code == 404
    assert flow.advances == flow.applies == 0


def test_writes_require_same_origin_and_do_not_replace_resume_parameters(client):
    http, flow = client
    assert http.post('/api/studio/one-stop/jobs', json={}, headers={'origin': 'https://unrelated.example'}).status_code == 403
    assert http.post('/api/studio/one-stop/jobs/owned/advance', json={'new_budget': 9000}).status_code == 422
    assert flow.advances == 0
    assert http.post('/api/studio/one-stop/jobs', json={}).status_code == 200
    assert http.post('/api/studio/one-stop/jobs/owned/apply', json={'stage': 'refinement'}).status_code == 200
    assert flow.applies == 1


def test_rate_revision_is_explicit_same_origin_mutation(client):
    http,flow=client
    path='/api/studio/one-stop/jobs/owned/revise'
    body={'speech_rate':1.15,'reason':'用户指出原版语速偏慢'}
    assert http.post(path,json=body,headers={'origin':'https://unrelated.example'}).status_code==403
    assert http.post(path,json=body).json()['id']=='new-rate-revision'
