import base64
import io

import pytest
from backlot.studio import Studio, sdk_type
from backlot.studio_refinement import PROMPT, RefinementCenter
from backlot.studio_refinement_api import router
from backlot.work_catalog import WorkError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image


def png(color='navy'):
    out=io.BytesIO(); Image.new('RGB',(640,800),color).save(out,'PNG'); return out.getvalue()


@pytest.fixture
def setup(tmp_path,monkeypatch):
    studio=Studio(tmp_path/'projects')
    d=studio.save_draft({'template_id':'avatar-safe-circle-v1','text':'测试','input':{}})
    asset=studio.save_asset(d['id'],'source.png','image',png())
    d=studio.save_draft({**d,'input':{'portrait':asset}})
    state={'account':'a','jobs':{},'posts':0,'quotes':0,'uploads':0,'missing_response':False,'available':True}
    Base=sdk_type()
    class Missing(ValueError): status=404
    class Client(Base):
        def request(self,path,body=None,idem=None,raw=None,**kwargs):
            if path=='/account/summary':return {'account_id':state['account']}
            if path=='/capabilities':return {'items':[{'model':'haike/image-refinement','status':'available'}] if state['available'] else []}
            if path.startswith('/files?'):
                state['uploads']+=1;return {'id':'file_test'}
            if path=='/quotes':
                state['quotes']+=1;assert body['input']['prompt']==PROMPT
                return {'id':'gquote_'+str(state['quotes']),'model':body['model'],'max_charge_micros':'150000'}
            if path.startswith('/quotes/') and path.endswith('/renew'):
                return {'id':path.split('/')[2], 'model':'haike/image-refinement', 'max_charge_micros':'150000', 'expires_at':'2099-01-01T00:00:00Z'}
            if path=='/jobs':
                state['posts']+=1
                value={'id':'gj_test','status':'succeeded','charged_micros':'150000',
                       'result':{'image_base64':base64.b64encode(png('teal')).decode()}}
                state['jobs'].setdefault(idem,value)
                if state['missing_response']:raise TimeoutError()
                return state['jobs'][idem]
            if path.startswith('/requests/'):
                value=state['jobs'].get(path.rsplit('/',1)[1])
                if value is None:raise Missing()
                return value
            if path.startswith('/jobs/'):return next(iter(state['jobs'].values()))
            raise AssertionError(path)
    monkeypatch.setattr(studio,'client',lambda config=None:Client('http://127.0.0.1:17894/v2','fake-only',tmp_path/'unused'))
    return studio,d,asset,state


def test_upload_quote_confirm_compare_adopt_and_preserve_original(setup):
    studio,d,asset,state=setup
    center=RefinementCenter(studio)
    task=center.prepare(d['id'],asset['id'])
    assert state['posts']==0 and task['status']=='quoted'
    assert center.prepare(d['id'],asset['id'])['id']==task['id'] and state['quotes']==1
    result=center.start(task['id'],{'confirmed':True,'max_charge_micros':'150000'})
    assert result['status']=='succeeded' and studio.draft(d['id'])['input']['portrait']['id']==asset['id']
    with Image.open(center.image(task['quote']['operation_id'])) as image:assert image.size==(1024,1280)
    adopted=center.decide(task['id'],True)
    portrait=adopted['draft']['input']['portrait']
    assert portrait['refined'] and portrait['original_id']==asset['id']
    assert studio.asset(asset['id'],d['id']).read_bytes()==png()
    assert center.decide(task['id'],True)['draft']['input']['portrait']['id']==portrait['id']
    assert state['posts']==1


def test_lost_response_get_queries_original_intent_without_post(setup):
    studio,d,asset,state=setup
    center=RefinementCenter(studio);task=center.prepare(d['id'],asset['id'])
    state['missing_response']=True
    assert center.start(task['id'],{'confirmed':True,'max_charge_micros':'150000'})['status']=='submission_unknown'
    assert center.get(task['id'])['status']=='succeeded' and state['posts']==1


def test_confirmation_and_budget_required(setup):
    studio,d,asset,state=setup
    center=RefinementCenter(studio);task=center.prepare(d['id'],asset['id'])
    for body in ({'confirmed':False,'max_charge_micros':'150000'},{'confirmed':True,'max_charge_micros':'1'}):
        with pytest.raises(WorkError):center.start(task['id'],body)
    assert state['posts']==0


def test_replacement_and_account_switch_cannot_adopt_old_candidate(setup):
    studio,d,asset,state=setup
    center=RefinementCenter(studio);task=center.prepare(d['id'],asset['id'])
    center.start(task['id'],{'confirmed':True,'max_charge_micros':'150000'})
    other=studio.save_asset(d['id'],'new.png','image',png('red'))
    studio.save_draft({**studio.draft(d['id']),'input':{'portrait':other}})
    with pytest.raises(WorkError,match='图片已经更换'):center.decide(task['id'],True)
    state['account']='b'
    with pytest.raises(WorkError,match='不属于当前账号'):RefinementCenter(studio).get(task['id'])


def test_unavailable_does_not_upload_or_submit_and_original_choice_is_final(setup):
    studio,d,asset,state=setup
    center=RefinementCenter(studio);state['available']=False
    with pytest.raises(WorkError,match='尚未开通'):center.prepare(d['id'],asset['id'])
    assert state['uploads']==0 and state['posts']==0
    state['available']=True;task=center.prepare(d['id'],asset['id'])
    center.decide(task['id'],False)
    with pytest.raises(WorkError,match='已确认采用'):center.start(task['id'],{'confirmed':True,'max_charge_micros':'150000'})


def test_cross_origin_and_path_escape_rejected(setup):
    studio,_,_,_=setup
    app=FastAPI();app.state.studio=studio;app.include_router(router)
    client=TestClient(app)
    assert client.post('/api/studio/refinement/prepare',headers={'Origin':'https://other.invalid'},json={}).status_code==403
    with pytest.raises(WorkError):RefinementCenter(studio).get('../../escape')


def test_quote_renewal_and_interruption_before_journal_do_not_submit(setup):
    from backlot.studio import atomic_private
    studio,d,asset,state=setup
    center=RefinementCenter(studio);task=center.prepare(d['id'],asset['id'])
    renewed=center.renew(task['id'])
    assert renewed['quote']['id']==task['quote']['id'] and state['quotes']==1 and state['posts']==0
    atomic_private(center.task_path(task['id']),{**renewed,'status':'submitting'})
    assert center.get(task['id'])['status']=='submission_unknown' and state['posts']==0
    assert center.start(task['id'],{'confirmed':True,'max_charge_micros':'150000'})['status']=='succeeded'
    assert state['posts']==1
