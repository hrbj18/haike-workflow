import pytest

from platform_app import adapters, gateway, providers
from platform_app.store import Problem


def test_image_input_upper_quote_is_bounded_and_no_external_url():
    info=providers.MODELS['haike/illustration']
    value,usage=gateway.clean_input(None,'user','haike/illustration',{'prompt':'示意插画'},info)
    assert usage['output_tokens']==32768 and value=={'prompt':'示意插画'}
    for v in [{'prompt':'','url':'https://external'}, {'prompt':'ok','n':20}]:
        with pytest.raises(Problem):gateway.clean_input(None,'user','haike/illustration',v,info)


@pytest.mark.parametrize('model',['gpt-image-2','gpt-image-1.5','gpt-image-1'])
def test_image_adapter_uses_actual_token_receipt(monkeypatch,tmp_path,model):
    vault=providers.Vault(tmp_path);vault.update('openai',{'api_key':'test-private-key','enabled':True,'image_model':model})
    calls=[]
    def fake(url,headers,body):
        calls.append((url,body))
        return {'data':[{'b64_json':'eA=='}],'usage':{'input_tokens':10,'output_tokens':20},'created':123}
    monkeypatch.setattr(adapters,'http',fake)
    result=adapters.Adapter(vault,tmp_path).execute('haike/illustration',{'prompt':'test'},lambda _:None)
    assert calls[0][0].endswith('/images/generations') and calls[0][1]['n']==1
    assert calls[0][1]['model']==model and result['result']['source']==model
    assert result['usage']=={'input_tokens':10,'output_tokens':20}
    assert result['result']['generated'] is True and 'test-private-key' not in str(result)


def test_missing_image_usage_retains_media_and_does_not_invent_cost(monkeypatch,tmp_path):
    vault=providers.Vault(tmp_path);vault.update('openai',{'api_key':'test-private-key','enabled':True})
    monkeypatch.setattr(adapters,'http',lambda *_:{'data':[{'b64_json':'eA=='}],'created':123})
    with pytest.raises(adapters.ReceiptMissing) as e:
        adapters.Adapter(vault,tmp_path).execute('haike/illustration',{'prompt':'test'},lambda _:None)
    assert e.value.result['image_base64']=='eA=='
