"""Domain contracts: temporary media/database and fake publication gateway only."""
import json
from pathlib import Path

import pytest
from PIL import Image

from backlot.work_catalog import WorkCatalog, WorkError
from backlot import work_publish, work_storage, work_ingest


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "projects"; project = root / "film"; project.mkdir(parents=True)
    (project / "project.json").write_text(json.dumps({"title": "测试作品"}), encoding="utf-8")
    monkeypatch.setattr("backlot.work_catalog.probe", lambda p: {"duration": 10, "width": 1080, "height": 1920, "has_audio": True})
    c = WorkCatalog(root)
    return c, project


def version(c, project, name="v1", mode="manual", key="main", passed=False):
    p = project / (name + ".mp4"); p.write_bytes((name * 1000).encode())
    return c.register("film", p, work_key=key, mode=mode, event_id=name, quality_passed=passed)


def confirm(c, w):
    return c.change(w["work_id"], "confirm", {"revision": w["revision"],
        "version_id": w["versions"][-1]["version_id"], "evidence": "用户明确选择"})


def prepare_work(c, p):
    w = confirm(c, version(c, p))
    image = p / "cover.jpg"; Image.new("RGB", (600,800), "navy").save(image)
    w = c.change(w["work_id"], "materials", {"revision": w["revision"], "data": {
        "title": "测试", "desc": "测试详情", "cover_path": str(image),
        "source_rights_status": "owned", "request_evidence": "用户指定文案"}})
    w = c.change(w["work_id"], "targets", {"revision": w["revision"], "targets": [
        {"platform": "douyin", "account_id": 1}, {"platform": "douyin", "account_id": 2}]})
    return w


class FakeGateway:
    def __init__(self): self.rows=[]; self.calls=[]; self.fail=False
    def submit(self, payload, key):
        self.calls.append(key)
        prior = next((t for t in self.rows if t["key"] == key), None)
        if prior: return prior
        t={"id": len(self.rows)+1, "status": "pending", "key": key, "acceptance_status": "not_checked",
           "platform": payload["expected_platform"], "account_id": payload["account_id"], "video_sha256": payload["video_sha256"]}
        self.rows.append(t)
        if self.fail: self.fail=False; raise WorkError("响应丢失", "unavailable")
        return t
    def tasks(self): return self.rows


def publish(c, w, gateway=None):
    g=gateway or FakeGateway()
    plan=work_publish.prepare(c,w["work_id"],w["revision"])
    return work_publish.submit(c,plan["plan_id"],True,g),g,plan


def verified(c, w, g):
    for t in g.rows: t.update(status="done",acceptance_status="verified",acceptance_evidence={"work_id": str(t["id"]),"unique_work":True,"video_matches":True,"title_matches":True,"cover_matches":True})
    return work_publish.sync(c,w["work_id"],g)


def asset(c,w,p,ownership="exclusive"):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b"asset data")
    return c.change(w["work_id"],"asset",{"revision":w["revision"],"path":str(p),
        "ownership":ownership,"ownership_evidence":"此生产任务生成的专用文件"})


def test_manual_final_does_not_follow_newest_and_survives_restart(env):
    c,p=env;w=confirm(c,version(c,p));final=w["final_version_id"]
    w=version(c,p,"v2");assert w["final_version_id"]==final
    assert WorkCatalog(c.projects_root).get(w["work_id"])["final_version_id"]==final
    assert len(w["versions"])==2
    with pytest.raises(WorkError,match="记录已更新"):c.change(w["work_id"],"handoff",{"revision":0})


def test_automatic_qa_and_work_unit(env):
    c,p=env;w=version(c,p,mode="automatic",passed=False)
    assert not w["final_version_id"] and not c.list()
    w=version(c,p,mode="automatic",passed=True)
    assert w["confirmations"][-1]["mode"]=="automatic"
    again=version(c,p,mode="automatic",passed=True)
    assert len(again["versions"])==1 and len(again["confirmations"])==1
    short=version(c,p,"short",mode="automatic",key="short",passed=True)
    assert short["work_id"]!=w["work_id"] and len(c.list())==2


def test_metadata_requires_manual_instruction_and_source_confirmation(env):
    c,p=env;w=confirm(c,version(c,p))
    with pytest.raises(WorkError,match="用户要求"):c.change(w["work_id"],"materials",{"revision":w["revision"],"data":{}})
    with pytest.raises(WorkError):work_publish.prepare(c,w["work_id"],w["revision"])


def test_publish_subsets_multi_account_and_lost_response(env):
    c,p=env;w=prepare_work(c,p);g=FakeGateway();g.fail=True
    plan=work_publish.prepare(c,w["work_id"],w["revision"])
    assert not g.calls
    with pytest.raises(WorkError):work_publish.submit(c,plan["plan_id"],False,g)
    with pytest.raises(WorkError):work_publish.submit(c,plan["plan_id"],True,g)
    result=work_publish.submit(c,plan["plan_id"],True,g)
    assert len(g.rows)==2 and len(result["attempts"])==2
    work_publish.submit(c,plan["plan_id"],True,g)
    assert len(g.rows)==2


def test_all_accounts_need_actual_acceptance_and_final_binding(env):
    c,p=env;w,g,_=publish(c,prepare_work(c,p))
    g.rows[0].update(status="done",acceptance_status="verified")
    g.rows[1].update(status="done",acceptance_status="not_checked")
    w=work_publish.sync(c,w["work_id"],g)
    assert not work_storage.eligible(w)
    w=verified(c,w,g);assert work_storage.eligible(w)
    w=confirm(c,version(c,p,"new"));assert not work_storage.eligible(w)
    assert w["attempts"][0]["version_id"]!=w["final_version_id"]


def test_cleanup_releases_only_exclusive_files_and_keeps_records(env):
    c,p=env;w,g,_=publish(c,prepare_work(c,p));w=verified(c,w,g)
    private=p/"assets/private.wav";shared=p/"assets/shared.mp4"
    w=asset(c,w,private);w=asset(c,w,shared,"shared")
    plan=work_storage.plan(c,[w["work_id"]]);assert plan["estimated_bytes"]==len(b"asset data")
    with pytest.raises(WorkError):work_storage.execute(c,plan["plan_id"],plan["digest"],False)
    result=work_storage.execute(c,plan["plan_id"],plan["digest"],True)
    assert result["state"]=="completed" and not private.exists() and shared.exists()
    assert c.media_path(w["work_id"]).exists() and (p/"cover.jpg").exists()
    assert c.get(w["work_id"])["attempts"]==w["attempts"]
    assert c.get(w["work_id"])["archive"]=="archived"
    assert work_storage.execute(c,plan["plan_id"],plan["digest"],True)==result


def test_cleanup_plan_invalidates_changed_file_and_revision(env):
    c,p=env;w,g,_=publish(c,prepare_work(c,p));w=verified(c,w,g);private=p/"private.wav";w=asset(c,w,private)
    plan=work_storage.plan(c,[w["work_id"]]);private.write_bytes(b"changed")
    with pytest.raises(WorkError,match="变化"):work_storage.execute(c,plan["plan_id"],plan["digest"],True)
    assert private.exists()
    c.change(w["work_id"],"handoff",{"revision":w["revision"],"data":{"next_step":"修改"}})
    with pytest.raises(WorkError,match="更新"):work_storage.execute(c,plan["plan_id"],plan["digest"],True)


def test_cross_work_and_activity_protect_assets(env):
    c,p=env;w,g,_=publish(c,prepare_work(c,p));w=verified(c,w,g)
    shared=p/"shared.wav";w=asset(c,w,shared)
    short=version(c,p,"short",key="short");short=asset(c,short,shared)
    plan=work_storage.plan(c,[w["work_id"]]);assert not any(r["delete"] for r in plan["entries"] if r["path"]==str(shared))
    c.activity("film","job-test",True)
    with pytest.raises(WorkError,match="活动任务"):work_storage.plan(c,[w["work_id"]])
    c.activity("film","job-test",False)


def test_project_external_files_are_explicit_and_controls_never_assets(env,tmp_path):
    c,p=env;w=confirm(c,version(c,p))
    outside=tmp_path/"source.wav";outside.write_bytes(b"source")
    with pytest.raises(WorkError):asset(c,w,outside)
    db=p/"control.sqlite";db.write_bytes(b"db")
    with pytest.raises(WorkError,match="数据库"):asset(c,w,db)
    own=c.projects_root.parent/".backlot/test-render/audio.wav";w=asset(c,w,own)
    assert w["assets"][-1]["path"]==str(own)


def test_historical_evidence_and_unknown_versions(env):
    c,p=env;v=p/"renders/old.mp4";v.parent.mkdir();v.write_bytes(b"media")
    report=work_ingest.import_preview(c);assert report["candidates"][0]["decision"]=="needs_confirmation"
    art=p/"artifacts";art.mkdir();(art/"old-handoff.json").write_text(json.dumps({"status":"approved_final","selected_final_path":str(v)}))
    plan=work_ingest.import_preview(c);result=work_ingest.import_apply(c,plan["plan_id"])
    assert len(result["imported"])==1 and c.list()[0]["final_version_id"]
    work_ingest.import_apply(c,plan["plan_id"]);assert len(c.list())==1


def test_symlink_never_crosses_managed_boundary(env,tmp_path):
    c,p=env;w=confirm(c,version(c,p));outside=tmp_path/"elsewhere.wav";outside.write_bytes(b"private")
    link=p/"link.wav"
    try:link.symlink_to(outside)
    except OSError:pytest.skip("此 Windows 账户没有创建符号链接权限")
    with pytest.raises(WorkError):asset(c,w,link)
    assert outside.exists()


def test_publish_wrong_account_or_hash_never_counts_as_verified(env):
    c,p=env;w,g,_=publish(c,prepare_work(c,p));w=verified(c,w,g)
    g.rows[0]["video_sha256"]="0"*64
    w=work_publish.sync(c,w["work_id"],g)
    assert not work_storage.eligible(w) and not w["attempts"][0]["identity_verified"]
    assert w["attempts"][0]["acceptance_status"]=="not_checked"


def test_published_old_version_and_current_final_survive_cleanup(env):
    c,p=env;w,g,_=publish(c,prepare_work(c,p));w=verified(c,w,g)
    old=c.media_path(w["work_id"]);w=confirm(c,version(c,p,"v6"));new=c.media_path(w["work_id"])
    w=c.change(w["work_id"],"materials",{"revision":w["revision"],"data":w["materials"][-1]["data"]})
    w,g,_=publish(c,w,g);w=verified(c,w,g)
    w=version(c,p,"unused");unused=p/"unused.mp4"
    plan=work_storage.plan(c,[w["work_id"]]);work_storage.execute(c,plan["plan_id"],plan["digest"],True)
    assert old.exists() and new.exists() and not unused.exists()


def test_partial_cleanup_resumes_without_double_count_and_blocks_queue(env,monkeypatch):
    c,p=env;w,g,_=publish(c,prepare_work(c,p));w=verified(c,w,g)
    first=p/"first.wav";last=p/"last.wav";w=asset(c,w,first);w=asset(c,w,last)
    plan=work_storage.plan(c,[w["work_id"]]);unlink=Path.unlink
    def locked(path,*a,**kw):
        if path==last:raise PermissionError("模拟文件占用")
        return unlink(path,*a,**kw)
    monkeypatch.setattr(Path,"unlink",locked)
    r=work_storage.execute(c,plan["plan_id"],plan["digest"],True)
    assert r["state"]=="partial" and not first.exists() and last.exists()
    from backlot.production_queue import ProductionQueue,ProductionQueueConflict
    queue=ProductionQueue(c.projects_root.parent/".backlot/production-queue.sqlite3",c.projects_root)
    with pytest.raises(ProductionQueueConflict,match="归档"):
        queue.submit(project_id="film",kind="full_preview",source="codex",priority="normal",parent_job_id="new",frozen_request={})
    monkeypatch.setattr(Path,"unlink",unlink)
    r=work_storage.execute(c,plan["plan_id"],plan["digest"],True)
    assert r["state"]=="completed" and r["deleted_bytes"]==2*len(b"asset data")
    assert "observed_free_change" in r


def test_cancel_partial_releases_activity_without_fake_archive(env,monkeypatch):
    c,p=env;w,g,_=publish(c,prepare_work(c,p));w=verified(c,w,g);w=asset(c,w,p/"locked.wav")
    plan=work_storage.plan(c,[w["work_id"]])
    monkeypatch.setattr(Path,"unlink",lambda *a,**k:(_ for _ in ()).throw(PermissionError("locked")))
    assert work_storage.execute(c,plan["plan_id"],plan["digest"],True)["state"]=="partial"
    work_storage.cancel(c,plan["plan_id"])
    assert c.get(w["work_id"])["archive"]!="archived"
    c.activity("film","newjob",True);c.activity("film","newjob",False)
    with pytest.raises(WorkError,match="结束"):work_storage.execute(c,plan["plan_id"],plan["digest"],True)


def test_unknown_files_visible_but_never_deleted(env):
    c,p=env;w=confirm(c,version(c,p));unknown=p/"unregistered.wav";unknown.write_bytes(b"unknown")
    report=work_storage.report(c,w["work_id"])
    row=next(r for r in report["entries"] if r["path"]==str(unknown))
    assert not row["delete"] and row["fingerprint"]["size"]==7


def test_duplicate_video_copy_removed_and_hardlink_space_not_overcounted(env):
    import os
    c,p=env;w,g,_=publish(c,prepare_work(c,p));w=verified(c,w,g)
    duplicate=p/"renders/preview/copy.mp4";duplicate.parent.mkdir(parents=True);duplicate.write_bytes(c.media_path(w["work_id"]).read_bytes())
    w=c.register("film",duplicate,event_id="copy")
    hard=p/"hard.wav";w=asset(c,w,hard);os.link(hard,p/"keep-hard.wav")
    plan=work_storage.plan(c,[w["work_id"]])
    assert plan["estimated_bytes"]==duplicate.stat().st_size
    r=work_storage.execute(c,plan["plan_id"],plan["digest"],True)
    assert not duplicate.exists() and (p/"keep-hard.wav").exists()
    assert r["deleted_bytes"]==len(("v1"*1000).encode())


def test_history_manual_confirmation_selects_exact_candidate(env):
    c,p=env;v=p/"renders/old.mp4";v.parent.mkdir();v.write_bytes(b"old")
    plan=work_ingest.import_preview(c)
    with pytest.raises(WorkError):work_ingest.import_apply(c,plan["plan_id"],confirmed_indices=[0])
    result=work_ingest.import_apply(c,plan["plan_id"],confirmed_indices=[0],evidence="用户选择旧片")
    assert result["imported"] and c.media_path(result["imported"][0])==v


def test_automatic_material_failure_keeps_valid_work(env,monkeypatch):
    c,p=env;(p/"final.mp4").write_bytes(b"video")
    monkeypatch.setattr(work_ingest,"automatic_materials",lambda *a:(_ for _ in ()).throw(RuntimeError("cover fail")))
    w=work_ingest.completed(c,"film","final.mp4","job-1",mode="automatic")
    assert w["final_version_id"] and not w["materials"] and w["handoff"]["next_step"]=="补齐自动发布资料"


def test_http_and_cli_share_catalog_revision_and_handoff(env,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backlot.work_api import router
    c,p=env;w=confirm(c,version(c,p));app=FastAPI();app.state.work_catalog=c;app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/works").status_code==200
        assert client.get("/api/works").json()[0]["work_id"]==w["work_id"]
        response=client.post(f"/api/works/{w['work_id']}/handoff",json={"revision":w["revision"],"data":{"next_step":"WorkBuddy读此记录"}})
        assert response.status_code==200
        assert WorkCatalog(c.projects_root).handoff(w["work_id"])["handoff"]["next_step"]=="WorkBuddy读此记录"
        assert client.post(f"/api/works/{w['work_id']}/handoff",json={"revision":w["revision"]}).status_code==409
        assert client.get(f"/api/works/{w['work_id']}/media").content==(p/"v1.mp4").read_bytes()


def test_real_media_probe_and_automatic_cover(tmp_path):
    import subprocess
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    root=tmp_path/"projects";p=root/"auto";p.mkdir(parents=True)
    (p/"project.json").write_text(json.dumps({"title":"自动测试","intake":{"created_from":"daily_automation"}}))
    ff,_=resolve_ffmpeg_pair();video=p/"final.mp4"
    subprocess.run([ff,"-y","-v","error","-f","lavfi","-i","color=c=blue:s=180x240:d=1", "-f","lavfi","-i","sine=frequency=440:duration=1","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-shortest",str(video)],check=True,timeout=30)
    c=WorkCatalog(root);w=work_ingest.completed(c,"auto",video,"real-video")
    assert w["final_version_id"] and w["versions"][0]["media"]["has_audio"]
    assert w["materials"][0]["data"]["title"]=="自动测试"
    with Image.open(w["materials"][0]["data"]["cover_path"]) as image:assert image.size==(720,960)


def test_shared_library_location_is_protected_even_when_declared_exclusive(env):
    import sqlite3
    c,p=env;w,g,_=publish(c,prepare_work(c,p));w=verified(c,w,g);shared=p/"shared-library.mp4";w=asset(c,w,shared)
    path=c.projects_root.parent/".backlot/material-library/library.sqlite3";path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE locations(path TEXT)");db.execute("INSERT INTO locations VALUES(?)",(str(shared),))
    plan=work_storage.plan(c,[w["work_id"]])
    assert not next(r for r in plan["entries"] if r["path"]==str(shared))["delete"]


def test_historical_receipt_readonly_and_unknown_hash_not_verified(env,monkeypatch):
    import sqlite3
    from backlot.work_catalog import sha
    c,p=env;video=p/"renders/final.mp4";video.parent.mkdir();video.write_bytes(b"history")
    legacy=p.parent.parent/"legacy.db"
    with sqlite3.connect(legacy) as db:
        db.execute("CREATE TABLE publishtask(id INTEGER,platform TEXT,account_id INTEGER,title TEXT,status TEXT,media_json TEXT,video_sha256 TEXT,acceptance_status TEXT,acceptance_evidence_json TEXT)")
        db.execute("INSERT INTO publishtask VALUES(1,'douyin',5,'old','done',?,?,'verified',?)",(json.dumps([str(video)]),sha(video).upper(),json.dumps({"work_id":"platform-1","unique_work":True,"video_matches":True,"title_matches":True,"cover_matches":True})))
    before=sha(legacy);monkeypatch.setenv("HAIKE_CREATORHUB_DB",str(legacy))
    plan=work_ingest.import_preview(c);result=work_ingest.import_apply(c,plan["plan_id"])
    w=c.get(result["imported"][0]);assert w["attempts"][0]["acceptance_status"]=="verified"
    assert w["targets"]==[] and not work_storage.eligible(w)
    assert sha(legacy)==before


def test_multiple_history_choices_cannot_silently_pick_last(env):
    c,p=env;folder=p/"renders";folder.mkdir();(folder/"one.mp4").write_bytes(b"one");(folder/"two.mp4").write_bytes(b"two")
    plan=work_ingest.import_preview(c)
    with pytest.raises(WorkError,match="只能勾选"):work_ingest.import_apply(c,plan["plan_id"],confirmed_indices=[0,1],evidence="用户选择")
    assert not c.list(include_candidates=True)


def test_scheduled_beijing_next_day_preserves_timezone(env):
    from datetime import datetime,timedelta,timezone
    c,p=env;w=prepare_work(c,p);when=(datetime.now(timezone(timedelta(hours=8)))+timedelta(days=5)).replace(hour=0,minute=5,second=0,microsecond=0).isoformat()
    w=c.change(w["work_id"],"targets",{"revision":w["revision"],"targets":[{"platform":"douyin","account_id":1,"scheduled_at":when}]})
    plan=work_publish.prepare(c,w["work_id"],w["revision"])
    assert datetime.fromisoformat(plan["entries"][0]["payload"]["scheduled_at"])==datetime.fromisoformat(when)


def test_cover_changed_after_preflight_causes_zero_publish_calls(env):
    c,p=env;w=prepare_work(c,p);plan=work_publish.prepare(c,w["work_id"],w["revision"])
    Image.new("RGB",(600,800),"red").save(p/"cover.jpg");gateway=FakeGateway()
    with pytest.raises(WorkError,match="冻结"):work_publish.submit(c,plan["plan_id"],True,gateway)
    assert not gateway.calls


def test_broken_database_is_preserved_and_reports_unavailable(tmp_path):
    db=tmp_path/"broken.sqlite3";db.write_bytes(b"invalid sqlite data")
    with pytest.raises(WorkError,match="数据库不可读取"):WorkCatalog(tmp_path/"projects",db)
    assert db.read_bytes()==b"invalid sqlite data"


def test_production_event_and_confirmation_replay_keep_revision(env):
    c,p=env;w=confirm(c,version(c,p));revision=w["revision"]
    replay=c.register("film",p/"v1.mp4",event_id="v1")
    assert replay["revision"]==revision
    again=c.change(w["work_id"],"confirm",{"revision":revision,"version_id":w["final_version_id"],"evidence":"重复确认同版"})
    assert again["revision"]==revision


def test_simultaneous_agents_cannot_overwrite_same_revision(env):
    from concurrent.futures import ThreadPoolExecutor
    c,p=env;w=confirm(c,version(c,p))
    def update(actor):
        try:
            c.change(w["work_id"],"handoff",{"revision":w["revision"],"data":{"actor":actor}},actor=actor)
            return "saved"
        except WorkError as exc:return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(update,["Codex","WorkBuddy"]))
    assert sorted(results)==["conflict","saved"]


def test_crash_after_unlink_recovers_durable_intent_without_inventing_bytes(env,monkeypatch):
    c,p=env;w,g,_=publish(c,prepare_work(c,p));w=verified(c,w,g);file=p/"crash.wav";w=asset(c,w,file)
    plan=work_storage.plan(c,[w["work_id"]]);original=Path.unlink
    class SimulatedPowerLoss(BaseException):pass
    def interrupted(path,*args,**kwargs):original(path,*args,**kwargs);raise SimulatedPowerLoss()
    monkeypatch.setattr(Path,"unlink",interrupted)
    with pytest.raises(SimulatedPowerLoss):work_storage.execute(c,plan["plan_id"],plan["digest"],True)
    assert not file.exists()
    monkeypatch.setattr(Path,"unlink",original)
    result=work_storage.execute(WorkCatalog(c.projects_root),plan["plan_id"],plan["digest"],True)
    assert result["state"]=="completed" and result["deleted_bytes"]==0
    assert c.media_path(w["work_id"]).exists()


def test_batch_two_works_same_project_cleans_each_exclusive_asset(env):
    c,p=env;first,g,_=publish(c,prepare_work(c,p));first=verified(c,first,g)
    second=confirm(c,version(c,p,"short",key="short"))
    second=c.change(second["work_id"],"materials",{"revision":second["revision"],"data":first["materials"][-1]["data"]})
    second=c.change(second["work_id"],"targets",{"revision":second["revision"],"targets":first["targets"]})
    second,g,_=publish(c,second,g);second=verified(c,second,g)
    a=p/"long-only.wav";b=p/"short-only.wav";first=asset(c,first,a);second=asset(c,second,b)
    plan=work_storage.plan(c,[first["work_id"],second["work_id"]])
    assert plan["estimated_bytes"]==2*len(b"asset data")
    result=work_storage.execute(c,plan["plan_id"],plan["digest"],True)
    assert result["state"]=="completed" and not a.exists() and not b.exists()
    assert c.media_path(first["work_id"]).exists() and c.media_path(second["work_id"]).exists()


def handoff_materials(c, w, **overrides):
    data = {**w["materials"][-1]["data"], "topics": "AI,公司管理", **overrides}
    return c.change(w["work_id"], "materials", {"revision": w["revision"], "data": data})


def test_handoff_prepared_materials_are_separate_from_publication_authorization(env):
    c, p = env; w = handoff_materials(c, prepare_work(c, p), source_rights_status="unknown")
    w = c.change(w["work_id"], "targets", {"revision": w["revision"], "targets": []})
    w = c.change(w["work_id"], "handoff", {"revision": w["revision"], "data": {
        "candidate_accounts": [{"platform": "douyin", "account_id": 1, "name": "现有账号", "cookie": "never export"}],
        "publish_authorized": True}})
    before = w["revision"]; result = c.handoff(w["work_id"])["publish_handoff"]
    assert result["materials_ready"] and result["title"] == "测试" and result["description"] == "测试详情"
    assert result["targets"] == [] and result["candidate_accounts"][0]["account_id"] == 1
    assert "cookie" not in result["candidate_accounts"][0]
    assert not result["publish_authorized"] and not result["ready_for_publication"]
    assert len(result["publication_blockers"]) == 3 and c.get(w["work_id"])["revision"] == before


def test_handoff_does_not_take_project_or_legacy_title_as_publication_materials(env):
    c, p = env; w = confirm(c, version(c, p)); folder = p / "artifacts/publishing"; folder.mkdir(parents=True)
    (folder / "待发布交接.json").write_text(json.dumps({"title": "old", "publish_authorized": True}))
    summary = c.handoff(w["work_id"])["publish_handoff"]
    assert summary["title"] is None and not summary["materials_ready"] and not summary["publish_authorized"]
    assert set(summary["missing_materials"]) == {"发布标题", "详情文案", "话题", "封面"}


def test_handoff_checks_changed_and_missing_media_files(env):
    c, p = env; w = handoff_materials(c, prepare_work(c, p))
    assert c.handoff(w["work_id"])["publish_handoff"]["materials_ready"]
    Image.new("RGB", (600, 800), "red").save(p / "cover.jpg")
    summary = c.handoff(w["work_id"])["publish_handoff"]
    assert not summary["materials_ready"] and summary["cover_path"] is None
    assert any("封面" in v for v in summary["invalid_materials"])
    (p / "v1.mp4").unlink()
    assert c.handoff(w["work_id"])["publish_handoff"]["video_path"] is None


def test_handoff_new_final_invalidates_old_materials_and_bound_authorization(env):
    c, p = env; w = handoff_materials(c, prepare_work(c, p))
    auth = {"authorized": True, "evidence": "用户授权本版发布", "version_id": w["final_version_id"],
            "material_revision": w["materials"][-1]["number"], "targets": w["targets"]}
    w = c.change(w["work_id"], "handoff", {"revision": w["revision"], "data": {"publication_authorization": auth}})
    assert c.handoff(w["work_id"])["publish_handoff"]["ready_for_publication"]
    w = confirm(c, version(c, p, "new-final"))
    summary = c.handoff(w["work_id"])["publish_handoff"]
    assert not summary["materials_ready"] and not summary["publish_authorized"]
    assert any("旧版本" in v for v in summary["invalid_materials"])


def test_handoff_target_or_schedule_change_invalidates_specific_authorization(env):
    c, p = env; w = handoff_materials(c, prepare_work(c, p))
    auth = {"authorized": True, "evidence": "用户授权当前目标", "version_id": w["final_version_id"],
            "material_revision": w["materials"][-1]["number"], "targets": w["targets"]}
    w = c.change(w["work_id"], "handoff", {"revision": w["revision"], "data": {"publication_authorization": auth}})
    assert c.handoff(w["work_id"])["publish_handoff"]["publish_authorized"]
    w = c.change(w["work_id"], "targets", {"revision": w["revision"], "targets": [{"platform": "douyin", "account_id": 4}]})
    assert not c.handoff(w["work_id"])["publish_handoff"]["publish_authorized"]


def test_handoff_ai_proof_checks_original_image_content(env):
    from backlot.work_catalog import sha
    c, p = env; w = prepare_work(c, p); original = p / "source.png"
    Image.new("RGB", (800, 1200), "blue").save(original)
    proof = p / "proof.json"; proof.write_text(json.dumps({"kind": "ai_generated", "model": "image-model",
        "source_image_path": str(original), "source_image_sha256": sha(original), "final_cover_sha256": sha(p / "cover.jpg")}))
    w = handoff_materials(c, w, cover_origin="generated_ai", cover_proof_path=str(proof))
    assert c.handoff(w["work_id"])["publish_handoff"]["materials_ready"]
    Image.new("RGB", (800, 1200), "red").save(original)
    assert not c.handoff(w["work_id"])["publish_handoff"]["materials_ready"]


def test_handoff_compatibility_export_and_http_share_authoritative_materials(env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backlot.work_api import router
    from backlot.work_handoff import export
    c, p = env; w = handoff_materials(c, prepare_work(c, p))
    result = export(c, w["work_id"]); snapshot = json.loads(Path(result["paths"][0]).read_text(encoding="utf-8"))
    assert snapshot["read_only_snapshot"] and snapshot["description"] == "测试详情"
    assert snapshot["status"] == "materials_prepared_pending_confirmation" and not snapshot["publish_authorized"]
    assert c.get(w["work_id"])["revision"] == w["revision"]
    app = FastAPI(); app.state.work_catalog = c; app.include_router(router)
    with TestClient(app) as client:
        response = client.get(f"/api/works/{w['work_id']}/handoff")
        assert response.status_code == 200 and response.json()["publish_handoff"] == result["publish_handoff"]
