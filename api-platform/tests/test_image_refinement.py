import base64

import pytest
from test_commerce import fund
from test_platform import key, submit

from platform_app import adapters, gateway, providers
from platform_app.store import Problem

PNG = b'\x89PNG\r\n\x1a\nfixture-only'


def enable(env):
    store, _, _, _, admin, _, _ = env
    vault = providers.Vault(store.path.parent)
    vault.update('openai', {'api_key':'fake-only', 'enabled':True,
                           'refinement_text_model':'gpt-5.6', 'refinement_image_model':'gpt-image-2'})
    providers.publish(store, admin['id'], 'haike/image-refinement',
                      {'costs':{'tasks':'100000'}, 'multiplier':'1.5', 'fee_micros':'0',
                       'source':'test', 'cost_basis':'all-in per completed edit fixture', 'confirmed':True}, vault)
    return vault


def response():
    return {'id':'resp-test', 'status':'completed', 'usage':{'input_tokens':80,'output_tokens':20},
            'output':[{'id':'tool-test','type':'image_generation_call','status':'completed',
                       'result':base64.b64encode(PNG).decode()}]}


def test_reference_upload_ownership_frozen_responses_and_billing(env, monkeypatch):
    store, _, client, _, _, user, other = env
    vault = enable(env)
    fund(env)
    headers, _ = key(client)
    image = gateway.upload(store, user['id'], 'image', PNG)
    with store.read() as db, pytest.raises(Problem, match='图片不存在'):
        gateway.clean_input(db, other['id'], 'haike/image-refinement', {'prompt':'修图','image_file':image['id']})
    quoted = client.post('/v2/quotes', headers=headers, json={
        'model':'haike/image-refinement','input':{'prompt':'保持身份，自然坐姿','image_file':image['id']}})
    assert quoted.status_code == 200, quoted.text
    q = quoted.json()
    assert q['max_charge_micros'] == '150000'
    job = submit(client, headers, q).json()
    vault.update('openai', {'refinement_text_model':'different-driver','refinement_image_model':'different-image'})
    calls=[]
    def fake(url, headers, body=None, **kwargs):
        calls.append((url, body))
        return response()
    monkeypatch.setattr(adapters, 'http', fake)
    gateway.execute_one(store, adapters.Adapter(vault, store.path.parent/'files'))
    bill = gateway.get_job(store, user, job['id'])
    assert bill['status'] == 'succeeded' and bill['charged_micros'] == '150000'
    assert bill['usage'] == {'tasks':1}
    url, body = calls[0]
    assert url.endswith('/responses') and body['model']=='gpt-5.6'
    assert body['tools'][0]['model']=='gpt-image-2'
    assert body['input'][0]['content'][1]['image_url'].startswith('data:image/png;base64,')
    assert body['input'][0]['content'][0]['text'].endswith('保持身份，自然坐姿')
    assert not gateway.execute_one(store, adapters.Adapter(vault, store.path.parent/'files'))
    assert len(calls)==1


@pytest.mark.parametrize('mode',['multiple','incomplete','missing','transport'])
def test_unknown_edit_preserves_hold_and_never_resubmits(env, monkeypatch, mode):
    store, _, client, _, _, user, _ = env
    vault=enable(env); fund(env)
    headers,_=key(client)
    image=gateway.upload(store,user['id'],'image',PNG)
    q=gateway.create_quote(store,vault,user,'haike/image-refinement',{'prompt':'修图','image_file':image['id']},'test')
    job=submit(client,headers,q).json()
    calls=[]
    def fake(*args,**kwargs):
        calls.append(1)
        value=response()
        if mode=='transport': raise adapters.Uncertain()
        if mode=='multiple': value['output']*=2
        if mode=='incomplete': value['status']='incomplete'
        if mode=='missing': value['output']=[]
        return value
    monkeypatch.setattr(adapters,'http',fake)
    adapter=adapters.Adapter(vault,store.path.parent/'files')
    gateway.execute_one(store,adapter)
    bill=gateway.get_job(store,user,job['id'])
    assert bill['status']=='submission_unknown' and bill['reserved_micros']=='150000'
    assert not gateway.execute_one(store,adapter)
    assert len(calls)==1


def test_unpriced_refinement_remains_blocked(env):
    store,_,_,_,_,user,_=env
    vault=providers.Vault(store.path.parent)
    vault.update('openai',{'api_key':'fake-only','enabled':True})
    with pytest.raises(Problem,match='模型尚未开通'):
        gateway.create_quote(store,vault,user,'haike/image-refinement',{'prompt':'修图','image_file':'file_test'},'test')
