"""Only synthetic writes: never start account engines or use live databases."""
import importlib.util
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location('publisher_update_guard', Path(__file__).resolve().parents[3] / 'creatorhub/app/update_guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_update_closes_new_writes_but_retains_reads_and_inflight_count(tmp_path):
    app = FastAPI()
    app.add_middleware(guard.SourceUpdateMiddleware, root=tmp_path)
    writes = []

    @app.post('/synthetic-write')
    def write():
        writes.append(app.state.haike_update_inflight)
        return {'ok': True}

    @app.get('/synthetic-read')
    def read():
        return {'ok': True}

    client = TestClient(app)
    assert client.post('/synthetic-write').status_code == 200
    assert writes == [1] and app.state.haike_update_inflight == 0
    state = tmp_path / '.local/app-updates/state.json'
    state.parent.mkdir(parents=True)
    for status in ('waiting', 'installing', 'restarting'):
        state.write_text(json.dumps({'operation': {'status': status}}))
        assert client.post('/synthetic-write').status_code == 503
        assert client.get('/synthetic-read').status_code == 200
    assert writes == [1]
    state.write_text('{broken')
    assert client.post('/synthetic-write').status_code == 503
    state.write_text(json.dumps({'operation': {'status': 'cancelled'}}))
    assert client.post('/synthetic-write').status_code == 200


def test_interrupted_transaction_remains_closed_until_receipt_is_recovered(tmp_path):
    folder = tmp_path / '.local/app-updates'
    transaction = folder / ('a' * 24)
    transaction.mkdir(parents=True)
    (folder / 'state.json').write_text(json.dumps({'operation': {'id': 'a'*24, 'status': 'failed'}}))
    receipt = transaction / 'receipt.json'
    receipt.write_text(json.dumps({'status': 'applying'}))
    middleware = guard.SourceUpdateMiddleware(None, tmp_path)
    assert middleware.blocked()
    receipt.write_text(json.dumps({'status': 'rolled_back'}))
    assert not middleware.blocked()
