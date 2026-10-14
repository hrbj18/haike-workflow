import io
import json
import wave

import pytest
from test_commerce import enable, fund, real_quote
from test_platform import key, submit

from platform_app import adapters, domain, gateway, voices
from platform_app.store import Problem, now


def wav(seconds=10):
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(24000)
        stream.writeframes(b'\x10\x00' * int(seconds * 24000))
    return output.getvalue()


def rig(env):
    store, _, client, outsider, _, user, other_user = env
    vault = enable(store)
    client.app.state.vault.public_origin = 'https://samples.example.test'
    vault.public_origin = 'https://samples.example.test'
    headers, _ = key(client)
    other, _ = key(outsider)
    return store, client, outsider, user, other_user, vault, headers, other


def clone_quote(client, headers, name='我的声音'):
    uploaded = client.post('/v2/files?kind=audio', headers=headers, content=wav())
    assert uploaded.status_code == 200
    result = client.post('/v2/quotes', headers=headers, json={'model': voices.CLONE_MODEL,
        'input': {'audio_file': uploaded.json()['id'], 'name': name, 'consent': True}, 'project_ref': 'voice-library'})
    assert result.status_code == 200, result.text
    return result.json()


class Clone:
    def __init__(self): self.calls = 0
    def execute(self, model, inputs, checkpoint, upstream_id):
        self.calls += 1
        identity = upstream_id or 'cosyvoice-v3.5-flash-' + inputs['_clone_prefix'] + '-saved'
        checkpoint(identity)
        return {'usage': {'requests': 1}, 'result': {'provider_voice_id': identity}, 'upstream_id': identity}


def test_clone_is_free_idempotent_private_and_usable_for_its_owner(env):
    store, client, outsider, user, _, _vault, headers, other = rig(env)
    q = clone_quote(client, headers)
    assert q['max_charge_micros'] == '0'
    accepted = submit(client, headers, q)
    assert accepted.status_code == 200, accepted.text
    assert submit(client, headers, q).json()['id'] == accepted.json()['id']
    adapter = Clone()
    assert gateway.execute_one(store, adapter)
    assert not gateway.execute_one(store, adapter)
    job = gateway.get_job(store, user, accepted.json()['id'])
    identity = job['result']['voice_id']
    assert job['charged_micros'] == '0' and job['upstream_id'] is None and adapter.calls == 1
    mine = client.get('/v2/voices', headers=headers).json()
    assert any(v['id'] == identity and v['scope'] == 'personal' for v in mine['items'])
    assert all(v['id'] != identity for v in outsider.get('/v2/voices', headers=other).json()['items'])
    denied = outsider.post('/v2/quotes', headers=other, json={'model': voices.TTS_MODEL, 'input': {'text': '你好', 'voice_id': identity}})
    assert denied.status_code == 404
    assert outsider.get(f'/v2/voices/{identity}/sample', headers=other).status_code == 404
    assert outsider.post(f'/v2/voices/{identity}/rename', headers=other, json={'name': '越权'}).status_code == 404
    q2 = real_quote(client, headers, inputs={'text': '你好', 'voice_id': identity})
    with store.read() as db:
        value = db.execute('SELECT input_json,snapshot FROM gateway_quotes WHERE id=?', (q2['id'],)).fetchone()
        assert json.loads(value['snapshot'])['provider_config']['voice'].endswith('-saved')
    assert domain.verify_ledger(store)['ok']


def test_voice_samples_and_consent_cannot_cross_accounts(env):
    store, client, outsider, _, _, _, headers, other = rig(env)
    sample = client.post('/v2/files?kind=audio', headers=other, content=wav()).json()['id']
    body = {'model': voices.CLONE_MODEL, 'input': {'audio_file': sample, 'name': '我的音色', 'consent': True}}
    assert client.post('/v2/quotes', headers=headers, json=body).status_code == 422
    body['input']['consent'] = False
    assert outsider.post('/v2/quotes', headers=other, json=body).status_code == 422
    sample = client.post('/v2/files?kind=audio', headers=headers, content=wav(4.8)).json()['id']
    body['input'].update(audio_file=sample, consent=True)
    assert client.post('/v2/quotes', headers=headers, json=body).status_code == 422
    with store.read() as db:
        assert db.execute('SELECT count(*) FROM gateway_jobs').fetchone()[0] == 0


def test_selected_voice_is_frozen_and_provider_changes_block_unconfirmed_quotes(env):
    store, client, _, _, _, vault, headers, _ = rig(env)
    original = 'cosyvoice-v3.5-flash-original-saved'
    voice = voices.import_system(store, vault, '系统口播', original, verify=False)
    q = real_quote(client, headers, inputs={'text': '你好', 'voice_id': voice['id']})
    fund(env)
    vault.update('bailian', {'voice': 'cosyvoice-v3.5-flash-other-saved'})
    assert submit(client, headers, q).status_code == 200
    seen = []
    class Tts:
        def execute(self, model, inputs, checkpoint, upstream_id):
            seen.append(inputs['_provider_config']['voice'])
            return {'usage': {'characters': 4}, 'result': {'audio_url': 'https://example.test/a.wav'}}
    gateway.execute_one(store, Tts())
    assert seen == [original]
    q = real_quote(client, headers, inputs={'text': '你好', 'voice_id': voice['id']})
    vault.update('bailian', {'api_key': 'another-test-provider-secret'})
    assert submit(client, headers, q, idem='changed-provider', intent='changed-provider').status_code == 409


def test_changing_default_never_retargets_an_existing_library_identity(env):
    store, client, _, _, _, vault, headers, _ = rig(env)
    old = client.get('/v2/voices', headers=headers).json()['default_voice_id']
    vault.update('bailian', {'voice': 'cosyvoice-v3.5-flash-new-default'})
    changed = client.get('/v2/voices', headers=headers).json()
    assert changed['default_voice_id'] != old
    q = real_quote(client, headers, inputs={'text': '你好', 'voice_id': old})
    with store.read() as db:
        row = db.execute('SELECT snapshot FROM gateway_quotes WHERE id=?', (q['id'],)).fetchone()
        assert json.loads(row['snapshot'])['provider_config']['voice'] == 'test-cloned-voice'
    vault.update('bailian', {'voice': 'test-cloned-voice'})
    restored = client.get('/v2/voices', headers=headers).json()
    assert restored['default_voice_id'] == old and len(restored['items']) == 2


def test_existing_system_audition_import_creates_no_bill_or_new_job(env):
    store, client, outsider, _, _, vault, headers, other = rig(env)
    tone = voices.import_system(store, vault, '原有音色', 'cosyvoice-v3.5-flash-existing', verify=False)
    voices.import_sample(store, tone['id'], wav())
    for account_headers, account in [(headers, client), (other, outsider)]:
        assert account.get(f"/v2/voices/{tone['id']}/sample", headers=account_headers).content == wav()
        assert account.post(f"/v2/voices/{tone['id']}/preview-quote", headers=account_headers).json()['cached']
    fund(env)
    bypass = client.post('/v2/quotes', headers=headers, json={'model': voices.TTS_MODEL,
        'input': {'text': voices.SAMPLE_TEXT, 'voice_id': tone['id']}, 'project_ref': 'voice-preview:' + tone['id']}).json()
    assert submit(client, headers, bypass).status_code == 409
    with store.read() as db:
        assert db.execute('SELECT count(*) FROM gateway_jobs').fetchone()[0] == 0
    assert domain.verify_ledger(store)['ok']


def test_private_manifest_migration_queries_original_voice_and_reuses_cache(env, tmp_path, monkeypatch):
    from import_voices import import_manifest
    store, _, _, _, _, vault, _, _ = rig(env)
    (tmp_path / 'audition.wav').write_bytes(wav())
    manifest = tmp_path / 'voices.json'
    manifest.write_text(json.dumps({'voices': [{'name': '原有口播', 'provider_voice_id': 'cosyvoice-v3.5-flash-existing',
        'sample_file': 'audition.wav'}]}))
    actions = []
    def query(url, headers, body):
        actions.append(body['input']['action'])
        return {'output': {'status': 'OK', 'target_model': 'cosyvoice-v3.5-flash'}}
    monkeypatch.setattr(adapters, 'http', query)
    first = import_manifest(store, vault, manifest)
    second = import_manifest(store, vault, manifest)
    assert first == second and actions == ['query_voice', 'query_voice']
    with store.read() as db:
        assert db.execute('SELECT count(*) FROM gateway_jobs').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM gateway_voices').fetchone()[0] == 1
    assert len(list((store.path.parent / 'voice-samples').glob('*.wav'))) == 1
    manifest.write_text(json.dumps({'voices': [{'name': 'invalid', 'provider_voice_id': 'unused', 'sample_file': '../outside.wav'}]}))
    with pytest.raises(Problem): import_manifest(store, vault, manifest)
    assert actions == ['query_voice', 'query_voice']


def test_real_clone_adapter_checkpoints_once_then_only_queries(env, monkeypatch):
    store, _, _, _, _, vault, _, _ = rig(env)
    adapter = adapters.Adapter(vault, store.path.parent / 'files')
    actions, saved = [], []
    identity = 'cosyvoice-v3.5-flash-habcdef12-saved'
    def response(url, headers, body):
        action = body['input']['action']; actions.append(action)
        return {'output': {'voice_id': identity}} if action == 'create_voice' else {'output': {'status': 'OK'}}
    monkeypatch.setattr(adapters, 'http', response)
    inputs = {'_reference_url': 'https://samples.example.test/reference.wav', '_clone_prefix': 'habcdef12',
              '_provider_scope': voices.scope(vault.load()['bailian'])}
    first = adapter.execute(voices.CLONE_MODEL, inputs, saved.append, None)
    second = adapter.execute(voices.CLONE_MODEL, inputs, saved.append, identity)
    assert first['result'] == second['result'] == {'provider_voice_id': identity}
    assert saved == [identity] and actions == ['create_voice', 'query_voice', 'query_voice']


def test_audition_cache_does_not_charge_again_and_is_private(env, monkeypatch):
    store, client, outsider, user, _, _, headers, other = rig(env)
    q = clone_quote(client, headers)
    job = submit(client, headers, q).json()
    gateway.execute_one(store, Clone())
    identity = gateway.get_job(store, user, job['id'])['result']['voice_id']
    fund(env)
    preview = client.post(f'/v2/voices/{identity}/preview-quote', headers=headers).json()['quote']
    accepted = submit(client, headers, preview, idem='audition-1', intent='audition-1')
    assert accepted.status_code == 200
    class Tts:
        def execute(self, model, inputs, checkpoint, upstream_id):
            return {'usage': {'characters': 70}, 'result': {'audio_url': 'https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/sample.wav'}}
    gateway.execute_one(store, Tts())
    downloads = []
    monkeypatch.setattr(adapters, 'download_bailian_audio', lambda url: downloads.append(url) or wav())
    before = client.get('/v2/account/summary', headers=headers).json()
    for _ in range(2):
        assert client.get(f'/v2/voices/{identity}/sample', headers=headers).content == wav()
        assert client.post(f'/v2/voices/{identity}/preview-quote', headers=headers).json()['cached']
    assert len(downloads) == 1
    assert client.get('/v2/account/summary', headers=headers).json() == before
    assert outsider.get(f'/v2/voices/{identity}/sample', headers=other).status_code == 404
    assert domain.verify_ledger(store)['ok']


def test_only_one_audition_can_be_accepted_at_a_time(env):
    store, client, _, _, _, _, headers, _ = rig(env)
    fund(env)
    identity = client.get('/v2/voices', headers=headers).json()['items'][0]['id']
    one = client.post(f'/v2/voices/{identity}/preview-quote', headers=headers).json()['quote']
    two = client.post(f'/v2/voices/{identity}/preview-quote', headers=headers).json()['quote']
    assert submit(client, headers, one).status_code == 200
    assert submit(client, headers, two, idem='parallel-audition', intent='parallel-audition').status_code == 409
    with store.read() as db:
        assert db.execute('SELECT count(*) FROM gateway_jobs').fetchone()[0] == 1
    assert domain.verify_ledger(store)['ok']


def test_reference_ticket_is_file_scoped_short_lived_and_does_not_expose_bearer(env):
    store, client, _, user, _, _, headers, _ = rig(env)
    sample = client.post('/v2/files?kind=audio', headers=headers, content=wav()).json()['id']
    url = voices.ticket(store, sample, user['id'], 'https://samples.example.test')
    token = url.rsplit('/', 1)[1].removesuffix('.wav')
    assert headers['Authorization'] not in url and voices.reference(store, token).read_bytes() == wav()
    assert client.get('/voice-reference/' + token + '.wav').content == wav()
    with store.write() as db: db.execute('UPDATE gateway_voice_tickets SET expires_at=?', (now(),))
    with pytest.raises(Problem): voices.reference(store, token)


def test_unknown_clone_recovers_by_query_and_never_recreates_it(env, monkeypatch):
    store, client, _, user, _, vault, headers, _ = rig(env)
    q = clone_quote(client, headers)
    accepted = submit(client, headers, q).json()
    class Lost:
        calls = 0
        def execute(self, *args): self.calls += 1; raise adapters.Uncertain()
    lost = Lost()
    gateway.execute_one(store, lost)
    assert not gateway.execute_one(store, lost) and lost.calls == 1
    prefix = voices.clone_prefix(accepted['id'])
    identity = 'cosyvoice-v3.5-flash-' + prefix + '-saved'
    actions = []
    def query(url, headers, body):
        actions.append(body['input']['action'])
        return {'output': {'voice_list': [{'voice_id': identity, 'target_model': 'cosyvoice-v3.5-flash'}]}}
    monkeypatch.setattr(adapters, 'http', query)
    recovered = voices.query_clone(store, vault, user, accepted['id'])
    assert recovered['status'] == 'running' and actions == ['list_voice']
    adapter = Clone(); gateway.execute_one(store, adapter)
    assert gateway.get_job(store, user, accepted['id'])['status'] == 'succeeded'


@pytest.mark.parametrize('url', ['http://127.0.0.1/a.wav', 'https://127.0.0.1/a.wav', 'https://evil.example/a.wav', 'https://user:secret@dashscope-result-bj.oss-cn-beijing.aliyuncs.com/a.wav'])
def test_audition_download_rejects_non_provider_hosts_and_credentials(url):
    with pytest.raises(Problem): adapters.download_bailian_audio(url)
