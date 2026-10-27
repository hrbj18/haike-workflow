from __future__ import annotations

import copy
import json
import math
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot import material_library as library
from backlot import material_commentary as flow
from backlot import commentary_evidence as evidence, commentary_audio as audio, commentary_api as api
from backlot.commentary_common import (
    CommentaryError, CommentaryConflict, atomic, digest, file_sha256, immutable, project_dir, read_json,
)
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from lib.ffmpeg_locator import resolve_ffmpeg_pair


def wav(path, seconds=1.2, frequency=830):
    samples = (np.sin(np.arange(round(seconds * 48000)) / 48000 * 2 * np.pi * frequency) * 6000).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, 48000, 0, "NONE", "not compressed")); out.writeframes(samples.tobytes())


def mock_evidence(project, source, *, start=0, end=20, subtitles="none", audio_reviewed=False):
    sha=file_sha256(source)
    request={"version":1,"media_id":"MAT-"+sha,"sha256":sha,"start":start,"end":end,
             "crop":{"x":0,"y":0,"w":1,"h":1}}
    identity="EV-"+digest(request)
    target=evidence.directory(project,identity);target.mkdir(parents=True,exist_ok=True)
    for name in ("source.mp4","sheet.jpg"): (target/name).write_bytes(b"test evidence fixture")
    immutable(target/"evidence.json",{**request,"id":identity,"title":"测试源片","source_path":str(source),
        "origins":[{"source_url":"local-test","rights_status":"test-fixture"}],"samples":[start,end],
        "files":{name:file_sha256(target/name) for name in ("source.mp4","sheet.jpg")}})
    evidence.review(project,identity,{"reviewer":"test-fixture","viewed":True,"usable":True,
        "observation":"测试夹具：人物回看门外","context":"测试夹具：此前有人敲门；没有确认敲门者身份",
        "source_subtitles":subtitles,"source_music":"none","audio_reviewed":audio_reviewed})
    return evidence.read(project,identity)


@pytest.fixture
def setup(tmp_path,monkeypatch):
    projects=tmp_path/"projects"; projects.mkdir()
    db=tmp_path/"library.sqlite3"
    monkeypatch.setenv("OPENMONTAGE_MATERIAL_LIBRARY_DIR",str(tmp_path))
    draft=flow.create("素材解说测试",projects_root=projects,db_path=db)
    project=project_dir(draft["id"],projects)
    source=tmp_path/"source.mp4";source.write_bytes(b"fixture-video")
    stat=source.stat();sha=file_sha256(source)
    library.register_prepared([{"id":"MAT-"+sha,"sha256":sha,"path":str(source),"bytes":stat.st_size,
        "mtime_ns":stat.st_mtime_ns,"title":"测试源片","duration":20,"width":320,"height":180,
        "origin":{"platform":"local","source_url":"","video_id":"","rights_status":"test-fixture","catalog":""}}],db_path=db)
    ev=mock_evidence(project,source)
    monkeypatch.setattr(flow,"probe",lambda _: {"streams":[{"codec_type":"video"},{"codec_type":"audio"}]})
    queue=ProductionQueue(tmp_path/"queue.sqlite3",projects)
    monkeypatch.setattr(api,"runtime",lambda _: (projects,queue))
    return projects,db,draft,project,ev,source,queue


def segment(ev,identity="first",*,start=1,end=3):
    return {"id":identity,"mode":"original","text":"","purpose":"保留有依据的情节",
            "basis":"观察到动作在此区间完整发生；未推断人物动机", "subtitle_mode":"none",
            "shots":[{"evidence_id":ev["id"],"start":start,"end":end}]}


@pytest.mark.parametrize("token", ["7:14", "48%", "v1.2.3"])
def test_caption_keeps_time_percentage_and_version_tokens(token):
    cues = flow.estimated_cues("甲" * 14 + token + "结束", 3, "portrait")
    assert sum(token in cue["text"] for cue in cues) == 1


def save(setup,rows,**changes):
    projects,db,draft,*_=setup
    payload={**draft["payload"],"intent":"解释素材中的事件","structure":"根据观察选择叙事顺序，保留前后文",
             "segments":rows,**changes}
    return flow.save(draft["id"],{"title":draft["title"],"revision":draft["revision"],"payload":payload},projects_root=projects,db_path=db)


@pytest.mark.parametrize("kind,windows",[("电影解说",[(12,14),(1,5),(8,10)]),
    ("直播切片解说",[(2,16)]),("产品演示",[(1,2),(3,4),(5,7),(9,11),(13,18)])])
def test_source_decides_order_count_and_duration(setup,kind,windows):
    projects,db,_,project,ev,_,queue=setup
    rows=[segment(ev,f"s{i}",start=a,end=b) for i,(a,b) in enumerate(windows)]
    draft=save(setup,rows,content_kind=kind,format="landscape" if kind=="电影解说" else "portrait")
    frozen=flow.compile_timeline(project,draft["payload"])
    assert len(frozen["segments"])==len(windows)
    assert [s["shots"][0]["start"] for s in frozen["segments"]]==[a for a,b in windows]
    assert frozen["duration"]==sum(b-a for a,b in windows)
    first=flow.submit(draft["id"],draft["revision"],queue,projects_root=projects,db_path=db)
    again=flow.submit(draft["id"],draft["revision"],queue,projects_root=projects,db_path=db)
    assert first["job_id"]==again["job_id"]
    assert ProductionQueueWorker(queue,projects).inspect_parent(first)["status"]=="queued"


def test_cas_noop_frozen_and_old_versions(setup):
    projects,db,_,_,ev,_,queue=setup
    draft=save(setup,[segment(ev)])
    identical=flow.save(draft["id"],draft,projects_root=projects,db_path=db)
    assert identical["revision"]==draft["revision"]
    job=flow.submit(draft["id"],draft["revision"],queue,projects_root=projects,db_path=db)
    changed=copy.deepcopy(draft);changed["payload"]["segments"][0]["shots"][0]["start"]=1.5
    saved=flow.save(draft["id"],changed,projects_root=projects,db_path=db)
    assert saved["revision"]==draft["revision"]+1
    with pytest.raises(CommentaryConflict): flow.save(draft["id"],changed,projects_root=projects,db_path=db)
    frozen=read_json(flow.version_dir(draft["id"],job["parent_job_id"],projects_root=projects)/"request.json")
    assert frozen["segments"][0]["shots"][0]["start"]==1


@pytest.mark.parametrize("field,value",[("start",True),("start",float("nan")),("start",-1),("end",25),("end",1),("end",float("inf"))])
def test_rejects_invalid_source_windows(setup,field,value):
    ev=setup[4]; row=segment(ev);row["shots"][0][field]=value
    with pytest.raises(ValueError): save(setup,[row])


def test_no_unknown_evidence_no_arbitrary_crop_no_duplicate_ids(setup):
    ev=setup[4]; row=segment(ev)
    with pytest.raises(CommentaryError): save(setup,[row,row])
    row["shots"][0]["crop"]={"x":0,"y":0,"w":1,"h":.5}
    with pytest.raises(CommentaryError,match="裁切"): save(setup,[row])
    row=segment(ev);row["shots"][0]["evidence_id"]="../../outside"
    with pytest.raises(CommentaryError): save(setup,[row])
    (evidence.directory(setup[3],ev["id"])/"review.json").unlink()
    with pytest.raises(CommentaryError,match="确认"): save(setup,[segment(ev)])


def test_source_replacement_and_evidence_tampering_fail_closed(setup):
    projects,db,_,project,ev,source,queue=setup
    draft=save(setup,[segment(ev)])
    original=source.read_bytes();source.write_bytes(b"changed")
    with pytest.raises(CommentaryError,match="变化"): flow.prepare(draft["id"],draft["revision"],projects_root=projects,db_path=db)
    source.write_bytes(original)
    (evidence.directory(project,ev["id"])/"sheet.jpg").write_bytes(b"changed")
    with pytest.raises(CommentaryError,match="变化"): flow.prepare(draft["id"],draft["revision"],projects_root=projects,db_path=db)


def test_audio_clock_coverage_text_and_project_binding(setup,tmp_path):
    projects,db,_,project,ev,_,_=setup
    path=tmp_path/"voice.wav";wav(path,1.213)
    take=audio.import_audio(project,path,narration_text="只有素材能说明发生了什么")
    assert take["samples"]==58224
    row={**segment(ev),"mode":"narration","text":take["text"],"audio_id":take["id"],"subtitle_mode":"estimated"}
    draft=save(setup,[row]);frozen=flow.compile_timeline(project,draft["payload"])
    assert frozen["frames"]==37 and frozen["segments"][0]["audio"]["samples"]==58224
    assert frozen["segments"][0]["shots"][0]["end"]<=3
    assert frozen["warnings"]
    short=copy.deepcopy(draft["payload"]);short["segments"][0]["shots"][0]["end"]=1.5
    with pytest.raises(flow.MaterialGap) as caught: flow.compile_timeline(project,short)
    assert caught.value.detail["missing_seconds"]==22/30
    mismatch=copy.deepcopy(draft["payload"]);mismatch["segments"][0]["text"]="新文案"
    with pytest.raises(CommentaryError,match="不一致"): flow.normalize(project,mismatch)
    foreign=flow.create("其他项目",projects_root=projects,db_path=db)
    with pytest.raises(CommentaryError): flow.normalize(project_dir(foreign["id"],projects),draft["payload"])


def test_original_subtitles_preserved_and_new_cues_separated(setup,tmp_path):
    project,source=setup[3],setup[5]
    ev=mock_evidence(project,source,start=1,end=10,subtitles="present")
    row=segment(ev,start=2,end=4);row.update(subtitle_mode="timed",subtitles=[{"start":0,"end":1,"text":"观察说明"}])
    draft=save(setup,[row])
    with pytest.raises(CommentaryError,match="原字幕"): flow.compile_timeline(project,draft["payload"])
    row.update(subtitle_position="top",source_subtitle_note="保留原片现场翻译，新说明放上方")
    draft=copy.deepcopy(draft);draft["payload"]["segments"][0].update(row)
    result=flow.compile_timeline(project,draft["payload"])
    assert result["segments"][0]["cues"][0]["text"]=="观察说明"
    draft["payload"]["segments"][0]["subtitles"][0]["end"]=10
    with pytest.raises(ValueError): flow.compile_timeline(project,draft["payload"])


def test_api_contract_and_cli_roundtrip(setup,tmp_path,capsys):
    projects,db,draft,_,ev,_,_=setup
    app=FastAPI();app.include_router(api.router);client=TestClient(app)
    # The standalone legacy page was retired; the retained API and CLI below
    # still enforce revision, evidence, rendering, and export contracts.
    assert client.get("/material-commentary").status_code==404
    base="/api/material-commentaries/"+draft["id"]
    changed={**draft,"payload":{**draft["payload"],"intent":"问答","structure":"保留问题再给回答","segments":[segment(ev)]}}
    response=client.put(base,json=changed);assert response.status_code==200,response.text
    assert client.put(base,json=changed).status_code==409
    assert client.post(base+"/preflight",json={"revision":2}).json()["status"]=="ready"
    job=client.post(base+"/render",json={"revision":2});assert job.status_code==200,job.text
    assert client.get(base+"/versions/"+job.json()["parent_job_id"]+"/preview.mp4").status_code==422
    assert client.get(base+"/evidence/invalid/source.mp4").status_code==422
    from scripts.material_commentary_cli import main
    dest=tmp_path/"brief.json"
    assert main(["--projects-root",str(projects),"--db",str(db),"--output",str(dest),"brief",draft["id"]])==0
    assert read_json(dest)["draft"]["revision"]==2


def test_tts_unknown_never_resubmits_and_success_reuses(setup,monkeypatch,tmp_path):
    project=setup[3]
    from backlot import tts_runtime
    from tools.base_tool import ToolResult
    request={"text":"测试旁白","profile":{"id":"test","name":"测试","provider_id":"tencent"},
             "estimated_cost_usd":.001,"characters":4,"signature":"a"*64}
    monkeypatch.setattr(audio,"quote",lambda _:request)
    calls=[]
    def fail(**kwargs): calls.append(kwargs);raise TimeoutError("provider timed out")
    monkeypatch.setattr(tts_runtime,"generate_voice_audio",fail)
    payload={"confirmed":True,"quote_signature":"a"*64,"max_characters":4,"max_estimated_cost_usd":.001}
    for _ in range(2):
        with pytest.raises(CommentaryConflict):audio.synthesize(project,payload)
    assert len(calls)==1
    request={**request,"signature":"b"*64};payload["quote_signature"]="b"*64
    def success(**kwargs):calls.append(kwargs);wav(kwargs["output_path"]);return ToolResult(success=True)
    monkeypatch.setattr(tts_runtime,"generate_voice_audio",success)
    first=audio.synthesize(project,payload);second=audio.synthesize(project,payload)
    assert first==second and len(calls)==2


@pytest.mark.parametrize("kind,shape,modes",[("电影式倒叙","landscape",["narration","original","mixed"]),
    ("直播问答","portrait",["original","narration"]),("多镜头演示","square",["narration"])])
def test_real_queue_render_audio_subtitles_reuse_recovery(tmp_path,monkeypatch,kind,shape,modes):
    pair=resolve_ffmpeg_pair()
    if not pair:pytest.skip("FFmpeg unavailable")
    ffmpeg,_=pair
    monkeypatch.setenv("OPENMONTAGE_MATERIAL_LIBRARY_DIR",str(tmp_path/"library"))
    projects=tmp_path/"projects";projects.mkdir()
    source=tmp_path/"source.mp4"
    subprocess.run([ffmpeg,"-v","error","-y","-f","lavfi","-i","testsrc2=size=320x180:rate=25:duration=8",
        "-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=8","-c:v","libx264","-threads","2",
        "-c:a","aac","-t","8",str(source)],check=True,capture_output=True)
    media_id=library.register_file(source,{"title":kind,"rights_status":"generated-test-fixture"})["media_ids"][0]
    draft=flow.create(kind,projects_root=projects);project=project_dir(draft["id"],projects)
    ev=evidence.prepare(project,{"media_id":media_id,"start":0,"end":7})
    evidence.review(project,ev["id"],{"reviewer":"test-fixture","viewed":True,"usable":True,
        "observation":"合成的移动测试图案","context":"非电影或直播实片，只验证媒体合同",
        "source_subtitles":"none","source_music":"none","audio_reviewed":False})
    if len(modes)==1:
        revised=evidence.prepare(project,{"media_id":media_id,"start":0,"end":7,"review_revision":"更正观察"})
        assert revised["id"]!=ev["id"] and revised["review"] is None
        assert evidence.read(project,ev["id"])["review"]["usable"]
    voice=tmp_path/"voice.wav";wav(voice,1.213)
    take=audio.import_audio(project,voice,narration_text="素材决定叙事结构。")
    rows=[]
    for i,mode in enumerate(modes):
        row=segment(ev,f"s{i}",start=4-i,end=6-i)
        row.update(mode=mode)
        if mode!="original":row.update(text=take["text"],audio_id=take["id"],subtitle_mode="estimated")
        rows.append(row)
    if len(rows)==1:rows[0]["shots"]=[{"evidence_id":ev["id"],"start":0,"end":.7},{"evidence_id":ev["id"],"start":4,"end":5}]
    draft=flow.save(draft["id"],{**draft,"payload":{**draft["payload"],"content_kind":kind,"format":shape,
        "intent":"验证不同素材组织方式","structure":"按素材观察组织；不使用固定开头正文结尾","segments":rows}},projects_root=projects)
    queue=ProductionQueue(tmp_path/"queue.sqlite3",projects)
    job=flow.submit(draft["id"],draft["revision"],queue,projects_root=projects)
    worker=ProductionQueueWorker(queue,projects)
    outcome=worker.run_once();assert outcome["status"]=="completed",outcome
    path=flow.output_path(draft["id"],job["parent_job_id"],projects_root=projects)
    original_hash=file_sha256(path)
    result=flow.versions(draft["id"],projects_root=projects)[0]
    assert all(result["qa"]["checks"].values()) and result["qa"]["loudness"]["acceptance_status"]=="passed"
    assert result["review_status"]=="pending_review"
    if modes[0]=="narration":
        raw=subprocess.run([ffmpeg,"-v","error","-i",str(path),"-t","0.8","-vn","-ac","1","-ar","48000","-f","f32le","-"],capture_output=True,check=True).stdout
        signal=np.frombuffer(raw,dtype="<f4");spectrum=np.abs(np.fft.rfft(signal));freq=np.fft.rfftfreq(len(signal),1/48000)
        assert spectrum[np.argmin(abs(freq-830))] > 20*spectrum[np.argmin(abs(freq-440))]
    app=FastAPI();app.include_router(api.router);monkeypatch.setattr(api,"runtime",lambda _: (projects,queue))
    response=TestClient(app).get(f"/api/material-commentaries/{draft['id']}/versions/{job['parent_job_id']}/preview.mp4",headers={"Range":"bytes=0-127"})
    assert response.status_code==206 and len(response.content)==128
    changed=copy.deepcopy(draft);changed["payload"]["segments"][0]["shots"][0]["start"]+=.1
    changed=flow.save(draft["id"],changed,projects_root=projects)
    new=flow.submit(draft["id"],changed["revision"],queue,projects_root=projects)
    from backlot import commentary_render as renderer
    with monkeypatch.context() as patch:
        patch.setattr(renderer,"_segment",lambda *a,**kw: (_ for _ in ()).throw(CommentaryError("注入的编码失败")))
        assert worker.run_once()["status"]=="failed"
    with pytest.raises(CommentaryError):flow.output_path(draft["id"],new["parent_job_id"],projects_root=projects)
    queue.retry(new["job_id"])
    assert worker.run_once()["status"]=="completed"
    latest=flow.versions(draft["id"],projects_root=projects)[0]
    assert not latest["cache"][0]["hit"]
    assert all(row["hit"] for row in latest["cache"][1:])
    assert file_sha256(path)==original_hash


@pytest.mark.parametrize("cut_start,expected_delay",[(0,.5),(.2,.3),(.7,0)])
def test_original_audio_preserves_source_stream_offset(tmp_path,monkeypatch,cut_start,expected_delay):
    pair=resolve_ffmpeg_pair()
    if not pair:pytest.skip("FFmpeg unavailable")
    monkeypatch.setenv("OPENMONTAGE_MATERIAL_LIBRARY_DIR",str(tmp_path/"library"))
    projects=tmp_path/"projects";projects.mkdir()
    source=tmp_path/"offset.mkv"
    subprocess.run([pair[0],"-v","error","-y","-f","lavfi","-i","color=blue:size=160x90:rate=30:duration=4",
        "-itsoffset","0.5","-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=3.5",
        "-c:v","libx264","-threads","2","-c:a","pcm_s16le","-t","4",str(source)],capture_output=True,check=True)
    library.register_file(source)
    draft=flow.create("带延迟的原声音轨",projects_root=projects);project=project_dir(draft["id"],projects)
    ev=mock_evidence(project,source,start=0,end=4)
    row=segment(ev,start=cut_start,end=cut_start+3)
    draft=flow.save(draft["id"],{**draft,"payload":{**draft["payload"],"intent":"保留原声同步",
        "structure":"按共同媒体时间保留音轨延迟","format":"landscape","segments":[row]}},projects_root=projects)
    queue=ProductionQueue(tmp_path/"queue.sqlite3",projects)
    job=flow.submit(draft["id"],draft["revision"],queue,projects_root=projects)
    outcome=ProductionQueueWorker(queue,projects).run_once();assert outcome["status"]=="completed",outcome
    path=flow.output_path(draft["id"],job["parent_job_id"],projects_root=projects)
    raw=subprocess.run([pair[0],"-v","error","-i",str(path),"-vn","-ac","1","-ar","48000","-f","f32le","-"],capture_output=True,check=True).stdout
    signal=np.frombuffer(raw,dtype="<f4")
    audible=np.flatnonzero(np.abs(signal)>.02)
    assert len(audible)>0 and abs(audible[0]/48000-expected_delay)<.035
