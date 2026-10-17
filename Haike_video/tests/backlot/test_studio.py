"""Studio regressions: real local ownership, fake external gateways, no paid calls."""
import io
import os
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backlot.studio import Studio, atomic_private
from backlot.studio_api import router
from backlot.studio_avatar import captions, frozen_request, key_identity, public_quote
from backlot.work_catalog import WorkCatalog, WorkError


@pytest.fixture
def studio(tmp_path): return Studio(tmp_path / "projects")


def make_draft(s): return s.save_draft({"template_id":"graphic-news-v2","title":"测试","text":"测试","input":{}})


def test_draft_revision_and_asset_ownership(studio):
    d = make_draft(studio); other = make_draft(studio)
    with pytest.raises(WorkError, match="已更新"): studio.save_draft({**d,"revision":0})
    b = io.BytesIO(); Image.new('RGB',(300,400),'navy').save(b,format='PNG')
    a = studio.save_asset(d['id'],'../../源图.png','image',b.getvalue())
    assert studio.asset(a['id'],d['id']).is_relative_to(studio.projects_root)
    with pytest.raises(WorkError): studio.asset(a['id'],other['id'])
    with pytest.raises(WorkError): studio.save_asset(d['id'],'image.png','image',b'invalid')
    with pytest.raises(WorkError,match='API Key'): studio.save_draft({**d,'input':{'api_key':'do-not-save'}})


def test_key_is_masked_private_and_never_sent_to_changed_host(studio):
    atomic_private(studio.config_path,{'base_url':'http://127.0.0.1:17894/v2','api_key':'test-secret-12345'})
    assert studio.settings()['key_hint']=='••••2345'
    assert 'test-secret' not in json.dumps(studio.settings())
    original=key_identity(studio)
    with pytest.raises(WorkError,match='更换'): studio.connect({'base_url':'https://example.com/v2'})
    with patch.object(studio,'client',side_effect=ValueError('test-secret-12345')):
        with pytest.raises(WorkError) as err:studio.connect({'base_url':'http://127.0.0.1:17894/v2'})
    assert 'test-secret' not in str(err.value)
    c=studio.configuration();c['checked_at']='new-time';atomic_private(studio.config_path,c)
    assert key_identity(studio)==original
    if os.name != 'nt':
        assert studio.config_path.stat().st_mode & 0o777 == 0o600
    else:
        assert studio.config_path.is_file()  # POSIX mode bits are not Windows ACLs.


@pytest.fixture
def work(studio,monkeypatch):
    p=studio.projects_root/'film';p.mkdir(parents=True)
    (p/'project.json').write_text('{"title":"测试成片"}', encoding='utf-8')
    (p/'video.mp4').write_bytes(b'unit-test-media')
    monkeypatch.setattr('backlot.work_catalog.probe',lambda p:{'duration':9,'width':1080,'height':1920,'has_audio':True})
    c=WorkCatalog(studio.projects_root);w=c.register('film',p/'video.mp4',title='测试成片')
    w=c.change(w['work_id'],'confirm',{'revision':w['revision'],'version_id':w['versions'][-1]['version_id'],'evidence':'test approval'})
    Image.new('RGB',(600,800),'navy').save(p/'cover.jpg')
    w=c.change(w['work_id'],'materials',{'revision':w['revision'],'data':{'title':'测试','desc':'测试详情','cover_path':str(p/'cover.jpg'),'source_rights_status':'confirmed','request_evidence':'test'}})
    return c,w


def plan_data(w):return {'work_id':w['work_id'],'scheduled_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'accounts':[{'platform':'douyin','account_id':1}]}


def test_calendar_timezone_cas_duplicate_and_atomic_batch(studio,work):
    c,w=work;v=plan_data(w)
    with pytest.raises(WorkError,match='时区'):studio.save_calendar({**v,'scheduled_at':'2027-01-01T18:00:00'},c)
    p=studio.save_calendar(v,c);assert p['scheduled_at'].endswith('+00:00')
    with pytest.raises(WorkError,match='已有排期'):studio.save_calendar(v,c)
    with pytest.raises(WorkError,match='已更新'):studio.save_calendar({**p,'revision':0},c)
    studio.cancel_calendar(p['id'])
    edited=studio.save_calendar(v,c)
    with pytest.raises(WorkError):studio.batch_calendar({**v,'work_ids':[w['work_id'],'missing'],'interval_days':1},c)
    assert len(studio.calendar())==2
    assert edited['status']=='draft'


class Publisher:
    def __init__(self):self.rows=[];self.calls=[];self.drop=True;self.cancel_failed=False
    def submit(self,payload,key):
        self.calls.append(key)
        row=next((r for r in self.rows if r['key']==key),None)
        if not row:row={'id':len(self.rows)+1,'status':'pending','key':key};self.rows.append(row)
        if self.drop:self.drop=False;raise WorkError('response lost','unavailable')
        return row
    def call(self,path,data=None,method=None):
        if self.cancel_failed:raise WorkError('service offline','unavailable')
        return {'status':'canceled'}


def test_unknown_publish_resumes_same_intent_and_cancel_needs_remote_receipt(studio,work):
    c,w=work;p=studio.save_calendar(plan_data(w),c);g=Publisher()
    with pytest.raises(WorkError):studio.activate_calendar(p['id'],False,c,g)
    with pytest.raises(WorkError):studio.activate_calendar(p['id'],True,c,g)
    assert studio.calendar_get(p['id'])['status']=='uncertain'
    with pytest.raises(WorkError):studio.cancel_calendar(p['id'],g)
    resumed=studio.activate_calendar(p['id'],True,c,g)
    assert resumed['status']=='scheduled' and resumed['task_ids']==[1]
    assert len(g.rows)==1 and g.calls[0]==g.calls[1]
    g.cancel_failed=True
    with pytest.raises(WorkError):studio.cancel_calendar(p['id'],g)
    assert studio.calendar_get(p['id'])['status']=='scheduled'
    g.cancel_failed=False;assert studio.cancel_calendar(p['id'],g)['status']=='canceled'


def test_caption_clock_requires_asr_evidence():
    values=captions({'text':'[0:0.020,0:2.380] 海客科技让创作更简单。\n[0:2.500,0:6.500] 一个接口连接工作流。'},6.56)
    assert values[0]['startMs']==20 and values[-1]['endMs']==6500
    with pytest.raises(WorkError):captions({'text':'没有时间轴'},7)


def test_retired_tencent_voice_is_blocked_before_gateway_upload_or_quote(studio, monkeypatch):
    from backlot.studio_avatar import quote
    d = studio.save_draft({"template_id":"avatar-template3-card-3x4-v001","title":"测试","text":"测试",
                           "input":{"soundMode":"voice","voiceId":"haike/tencent-tts"}})
    def unexpected(*args): raise AssertionError("must reject before external calls")
    monkeypatch.setattr(studio, "client", unexpected)
    monkeypatch.setattr(studio, "asset", unexpected)
    with pytest.raises(WorkError, match="腾讯精品配音已移除"):
        quote(studio, d)
    data = {"id":"old-tts-quote","draft":d,"key_identity":key_identity(studio),
            "quotes":{"tts":{"model":"haike/tencent-tts","max_charge_micros":"270"}},"prepared":{}}
    with studio.db() as db:
        db.execute("INSERT INTO studio_quotes VALUES(?,?)", (data["id"], json.dumps(data)))
    with pytest.raises(WorkError, match="腾讯精品配音已移除"):
        frozen_request(studio, d, data["id"], 1000)
    with studio.db() as db:
        assert json.loads(db.execute("SELECT data FROM studio_quotes WHERE id=?",(data["id"],)).fetchone()[0]) == data


def test_calendar_tracks_real_publishing_and_partial_failure(studio,work,monkeypatch):
    c,w=work;p=studio.save_calendar(plan_data(w),c)
    studio.update_calendar(p['id'],{'status':'scheduled','publish_plan_id':'plan1'})
    attempts=[{'plan_id':'plan1','status':'publishing'},{'plan_id':'plan1','status':'done'}]
    monkeypatch.setattr('backlot.work_publish.sync',lambda *args:{'attempts':attempts})
    assert studio.sync_calendar(c)[0]['status']=='running'
    attempts[0]['status']='uncertain'
    assert studio.sync_calendar(c)[0]['status']=='uncertain'
    attempts[0]['status']='canceled'
    assert studio.sync_calendar(c)[0]['status']=='failed'
    studio.update_calendar(p['id'],{'status':'canceling'})
    assert studio.sync_calendar(c)[0]['status']=='canceling'


def test_avatar_lost_confirmation_and_pending_resume_never_create_new_intent(studio, monkeypatch):
    from backlot.studio_avatar import run_avatar
    d=make_draft(studio)
    d['input']={'soundMode':'audio','subtitles':False}
    folder=studio.projects_root/d['id'];folder.mkdir(parents=True,exist_ok=True)
    audio=folder/'drive.wav';audio.write_bytes(b'test-audio')
    request={'id':'quote-one','draft':d,'key_identity':key_identity(studio),'render_id':'retry-one',
             'prepared':{'audio_path':str(audio),'audio_file':'audio1','image_file':'image1','duration':3},
             'quotes':{'avatar':{'model':'haike/avatar','max_charge_micros':150}},'max_charge_micros':150}
    stages=[]
    class Gateway:
        def __init__(self):self.intents={};self.confirm_calls=[];self.polls=0
        def confirm(self,q,maximum,identity):
            self.confirm_calls.append(identity)
            if identity not in self.intents:
                self.intents[identity]={'id':'intent1'}
                raise TimeoutError('response lost after reservation')
            return self.intents[identity]
        def wait(self,intent,timeout):
            assert stages[-1] == '生成数字人口播：等待供应商结果'
            self.polls+=1
            return {'id':'job1','status':'pending' if self.polls==1 else 'succeeded','result':{'video_url':'https://supplier.example/video'}}
    gateway=Gateway()
    monkeypatch.setattr('backlot.studio_avatar.download_result',lambda url,path:path.write_bytes(b'test-video'))
    def compose(out,*args):
        result=out/'avatar-preview.mp4';result.write_bytes(b'test-render');return result
    monkeypatch.setattr('backlot.studio_composition.compose_avatar',compose)
    assert run_avatar(folder,request,gateway,progress=stages.append)['retryable']
    assert run_avatar(folder,request,gateway,progress=stages.append)['retryable']
    result=run_avatar(folder,request,gateway,progress=stages.append)
    assert result['status']=='completed' and len(gateway.intents)==1
    assert len(set(gateway.confirm_calls))==1 and len(gateway.confirm_calls)==2
    # A further local retry reuses the output source and does not touch paid endpoints.
    assert run_avatar(folder,request,gateway,progress=stages.append)['status']=='completed'
    assert gateway.polls==2 and len(gateway.confirm_calls)==2
    assert stages[-1] == '本地合成成片'
    assert json.loads((folder/'renders/retry-one/gateway-state.json').read_text(encoding='utf-8'))['progress']['stage'] == stages[-1]


def test_quote_budget_and_content_are_frozen(studio):
    d=make_draft(studio);data={'id':'q','draft':d,'key_identity':key_identity(studio),'quotes':{'avatar':{'model':'haike/avatar','max_charge_micros':'400000'}},'prepared':{}}
    data['draft']['input']['soundMode']='audio'
    with studio.db() as db:db.execute('INSERT INTO studio_quotes VALUES(?,?)',('q',json.dumps(data)))
    assert public_quote(data)['known_max_micros']==400000
    with pytest.raises(WorkError,match='低于'):frozen_request(studio,d,'q',300000)
    with pytest.raises(WorkError,match='改变'):frozen_request(studio,{**d,'title':'different'},'q',500000)
    assert frozen_request(studio,d,'q',500000)['max_charge_micros']==500000


def test_api_origin_guard_and_persistent_drafts(studio):
    app=FastAPI();app.state.studio=studio;app.state.works_projects_root=studio.projects_root;app.include_router(router)
    client=TestClient(app)
    payload={'template_id':'graphic-news-v2','title':'测试','input':{}}
    assert client.post('/api/studio/drafts',json=payload,headers={'Origin':'https://external.test'}).status_code==403
    d=client.post('/api/studio/drafts',json=payload).json()
    assert client.get('/api/studio/drafts/'+d['id']).json()['title']=='测试'
    assert client.post('/api/studio/drafts',json={**d,'revision':0}).status_code==409


@pytest.fixture
def gbk_checkpoint_reads(monkeypatch):
    """Emulate Windows' legacy default only for this test's checkpoint files."""
    targets = set()
    original = Path.read_text

    def read(path, encoding=None, errors=None):
        if encoding is None and path.resolve() in targets:
            encoding = "gbk"
        return original(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", read)
    return targets


@pytest.mark.parametrize("route,relative", [
    ("ai-preview", "assets/ai-preview/{revision}/preview.json"),
    ("storyboard", "renders/studio-{revision}/storyboard.json"),
])
def test_saved_ai_plan_api_reuses_exact_utf8_checkpoint(studio, monkeypatch, gbk_checkpoint_reads, route, relative):
    draft = make_draft(studio)
    path = studio.projects_root / draft["id"] / relative.format(revision=draft["revision"])
    saved = {"status": "ready", "title": "机器人🤖分镜", "scenes": [{"text": "复用原结果，不再生成🚦"}]}
    atomic_private(path, saved)
    before = path.read_bytes()
    gbk_checkpoint_reads.add(path.resolve())
    monkeypatch.setattr(studio, "client", lambda: pytest.fail("Reading a saved plan must not call a gateway"))
    app = FastAPI(); app.state.studio = studio; app.include_router(router)
    with TestClient(app) as client:
        for _ in range(2):
            response = client.get(f"/api/studio/drafts/{draft['id']}/{route}")
            assert response.status_code == 200
            assert response.json() == {"plan": saved}
    assert path.read_bytes() == before


def test_douyin_candidate_and_skip_authorization_reuse_utf8_checkpoint(studio, monkeypatch, gbk_checkpoint_reads):
    draft = make_draft(studio)
    folder = studio.projects_root / draft["id"] / "renders" / f"studio-{draft['revision']}"
    candidates = folder / "ai-requests/scene-1-candidates.json"
    item = {"id": "fixture-video", "title": "机器人🤖演示", "author": "中文作者🚦", "source_url": "https://www.douyin.com/video/fixture-video"}
    atomic_private(candidates, {"items": [item]})
    before = candidates.read_bytes()
    decision = folder / "source-decisions.json"
    gbk_checkpoint_reads.update({candidates.resolve(), decision.resolve()})
    job = {"id": "original-job", "kind": "studio_avatar", "status": "failed", "frozen_request": {"draft": draft}}
    retries = []

    def get(identity, *, include_private):
        assert identity == job["id"] and include_private is True
        return job

    def retry(identity):
        assert identity == job["id"]
        retries.append(identity)
        job["status"] = "queued"
        return {"id": identity, "status": "queued"}

    monkeypatch.setattr("backlot.server._ensure_production_queue", lambda _app: SimpleNamespace(get=get, retry=retry))
    monkeypatch.setattr(studio, "client", lambda: pytest.fail("Local authorization must not call a gateway"))
    app = FastAPI(); app.state.studio = studio; app.include_router(router)
    base = f"/api/studio/ai/jobs/{job['id']}"
    with TestClient(app) as client:
        for _ in range(2):
            response = client.get(base + "/douyin-candidates")
            assert response.status_code == 200 and response.json() == {"items": [item]}
        assert retries == [] and candidates.read_bytes() == before
        skipped = client.post(base + "/skip-douyin", json={"confirmed": True})
        assert skipped.status_code == 200 and skipped.json() == {"id": job["id"], "status": "queued"}
        saved = json.loads(decision.read_text(encoding="utf-8"))
        assert saved["skip_douyin"] is True and saved["reason"] == "用户明确跳过抖音，恢复原任务"
        # Simulate that the same worker paused again, with a Unicode operator note.
        job["status"] = "failed"
        saved.update(note="保留原决定🤖", authorized_video_ids=["earlier-video"])
        atomic_private(decision, saved)
        unchanged = decision.read_bytes()
        assert client.post(base + "/authorize-douyin", json={"video_id": item["id"], "rights_confirmed": False}).status_code == 422
        assert client.post(base + "/authorize-douyin", json={"video_id": "not-a-candidate", "rights_confirmed": True}).status_code == 422
        assert decision.read_bytes() == unchanged and retries == [job["id"]]
        authorized = client.post(base + "/authorize-douyin", json={"video_id": item["id"], "rights_confirmed": True})
        assert authorized.status_code == 200 and authorized.json() == {"id": job["id"], "status": "queued"}
        updated = json.loads(decision.read_text(encoding="utf-8"))
        assert updated["authorized_video_ids"] == ["earlier-video", item["id"]]
        assert updated["note"] == saved["note"] and updated["reason"] == saved["reason"]
        assert updated["skip_douyin"] is True and updated["confirmed_at"]
        assert client.post(base + "/authorize-douyin", json={"video_id": item["id"], "rights_confirmed": True}).status_code == 409
    assert retries == [job["id"], job["id"]] and candidates.read_bytes() == before
