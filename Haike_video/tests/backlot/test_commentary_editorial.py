"""Editorial behavior exercised through the same HTTP interface as the editor."""
from pathlib import Path
import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot import commentary_api as api, material_library as library
from backlot.production_queue import ProductionQueue
from lib.ffmpeg_locator import resolve_ffmpeg_pair
from backlot import material_commentary as flow, material_library_refs as refs
from backlot.commentary_common import read_json
from backlot.production_queue_worker import ProductionQueueWorker
import numpy as np
import wave
import json


@pytest.fixture
def editor(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENMONTAGE_MATERIAL_LIBRARY_DIR", str(tmp_path / "library"))
    source = tmp_path / "source.mp4"
    subprocess.run([resolve_ffmpeg_pair()[0], "-v", "error", "-y", "-f", "lavfi", "-i",
        "testsrc2=size=320x180:rate=30:duration=12", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=48000:duration=12", "-c:v", "libx264",
        "-threads", "2", "-c:a", "aac", "-t", "12", str(source)], check=True, capture_output=True)
    media_id = library.register_file(source, {"title": "事件测试素材", "rights_status": "generated-test-fixture"})["media_ids"][0]
    projects = tmp_path / "projects"
    queue = ProductionQueue(tmp_path / "queue.sqlite3", projects)
    monkeypatch.setattr(api, "runtime", lambda _: (projects, queue))
    app = FastAPI(); app.include_router(api.router)
    client = TestClient(app)
    draft = client.post(api.BASE, json={"title": "事件编排"}).json()
    base = api.BASE + "/" + draft["id"]
    ev = client.post(base + "/evidence", json={"media_id": media_id, "start": 0, "end": 12}).json()
    response = client.post(base + "/evidence/" + ev["id"] + "/review", json={
        "viewed": True, "usable": True, "reviewer": "test-fixture",
        "observation": "合成移动图案", "context": "测试媒体，非现实叙事",
        "source_subtitles": "none", "source_music": "none"})
    assert response.status_code == 200
    return client, base, draft, ev, media_id, projects, queue


def plan(draft, ev, media_id):
    return {**draft, "payload": {**draft["payload"], "intent": "说明动作的结果", "structure": "依据事件组织",
        "editorial": {"version": 2, "candidate_media_ids": [media_id],
            "coverage": [{"media_id": media_id, "status": "reviewed", "reason": "已检查动作窗口", "evidence_ids": [ev["id"]]}],
            "events": [{"id": "action", "evidence_ids": [ev["id"]], "summary": "图案移动",
                "context": "合成夹具", "setup": "初始图案", "action": "移动", "result": "位置改变",
                "tone": "客观解释", "original_reason": "不采用测试正弦波"}]},
        "segments": [{"id": "answer", "mode": "original", "text": "", "purpose": "展示结果", "basis": "来自事件",
            "event_id": "action", "subtitle_mode": "none", "shots": [{"evidence_id": ev["id"], "start": 2, "end": 4}]}]}}


def test_optional_presenter_survives_public_editor_and_queue_only_changes_opening(editor, tmp_path):
    client, base, draft, ev, media_id, projects, queue = editor
    voice = tmp_path / "voice.wav"
    with wave.open(str(voice), "wb") as out:
        out.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        out.writeframes((np.sin(np.arange(96000)*2*np.pi*220/48000)*5000).astype("<i2").tobytes())
    take = client.post(base + "/audio/import", json={"path": str(voice), "text": "看这个动作"}).json()
    avatar = tmp_path / "presenter.mp4"
    subprocess.run([resolve_ffmpeg_pair()[0], "-v", "error", "-y", "-f", "lavfi", "-i",
        "color=red:size=320x400:rate=25:duration=2", "-c:v", "libx264", "-threads", "2", str(avatar)],
        check=True, capture_output=True)
    response = client.post(base + "/presenters/import", json={"path": str(avatar), "audio_id": take["id"],
        "name": "测试主持人", "provenance": "合成夹具，绑定完整配音"})
    assert response.status_code == 200, response.text
    asset = response.json()
    saved_assets = client.get(base).json()["presenters"]
    assert saved_assets[0]["id"] == asset["id"]
    payload = plan(draft, ev, media_id)
    payload["payload"].pop("editorial")
    row = payload["payload"]["segments"][0]
    row.update(id="opening", mode="narration", text=take["text"], audio_id=take["id"], subtitle_mode="none")
    row.pop("event_id")
    payload["payload"]["segments"].append({"id": "handoff", "mode": "original", "text": "",
        "purpose": "转入素材原声", "basis": "保留连续反应", "subtitle_mode": "none",
        "shots": [{"evidence_id": ev["id"], "start": 6, "end": 8}]})
    saved = client.put(base, json=payload).json()
    off = client.post(base + "/render", json={"revision": saved["revision"]}).json()
    assert ProductionQueueWorker(queue, projects).run_once()["status"] == "completed"
    saved["payload"]["segments"][0]["presenter"] = {"asset_id": asset["id"], "x": .74, "y": .12,
        "diameter": .20, "crop": {"x": 0, "y": 0, "w": 1, "h": .8}, "layout_review": "已核对不遮挡素材主体"}
    saved = client.put(base, json=saved).json()
    assert saved["payload"]["segments"][0]["presenter"]["asset_id"] == asset["id"]
    assert client.put(base, json=saved).json()["revision"] == saved["revision"]
    on = client.post(base + "/render", json={"revision": saved["revision"]}).json()
    outcome = ProductionQueueWorker(queue, projects).run_once()
    assert outcome["status"] == "completed", outcome
    results = client.get(base).json()
    versions = {v["signature"]: v for v in results["versions"]}
    a, b = versions[off["parent_job_id"]], versions[on["parent_job_id"]]
    assert a["frames"] == b["frames"] == 120
    assert b["cache"][0]["hit"] is False and b["cache"][1]["hit"] is True
    frozen = read_json(flow.version_dir(draft["id"], on["parent_job_id"], projects_root=projects)/"request.json")
    assert frozen["segments"][0]["presenter"]["asset"]["audio_sha256"] == take["sha256"]
    assert frozen["segments"][0]["presenter"]["crop"]["h"] == .8
    assert "presenter" not in frozen["segments"][1]
    output = flow.output_path(draft["id"], on["parent_job_id"], projects_root=projects)
    pixels = subprocess.run([resolve_ffmpeg_pair()[0], "-v", "error", "-ss", "0.5", "-i", str(output),
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True)
    frame = np.frombuffer(pixels.stdout, np.uint8).reshape(1280, 720, 3)
    assert frame[220, 600, 0] > 180 and frame[220, 600, 1] < 70


def test_presenter_caption_collision_blocks_public_submission(editor, tmp_path):
    client, base, draft, ev, media_id, projects, queue = editor
    voice = tmp_path / "voice.wav"
    with wave.open(str(voice), "wb") as out:
        out.setparams((1, 2, 48000, 0, "NONE", "not compressed")); out.writeframes(bytes(192000))
    take = client.post(base + "/audio/import", json={"path": str(voice), "text": "动作"}).json()
    asset = client.post(base + "/presenters/import", json={"path": str(tmp_path/"source.mp4"),
        "audio_id": take["id"], "name": "测试", "provenance": "已知配音夹具"}).json()
    payload = plan(draft, ev, media_id); payload["payload"].pop("editorial")
    row = payload["payload"]["segments"][0]
    row.update(mode="narration", text="动作", audio_id=take["id"], subtitle_mode="timed", subtitle_position="top",
        subtitles=[{"start": .1, "end": 1.8, "text": "动作"}],
        presenter={"asset_id": asset["id"], "x": .4, "y": .12, "diameter": .2, "layout_review": "测试重叠"})
    saved = client.put(base, json=payload).json()
    blocked = client.post(base + "/render", json={"revision": saved["revision"]})
    assert blocked.status_code == 422 and "字幕" in blocked.text and "出镜" in blocked.text
    saved["payload"]["segments"][0]["subtitle_layout"] = {"x": .24, "y": .18, "max_width": .3}
    saved = client.put(base, json=saved).json()
    assert saved["payload"]["segments"][0]["subtitle_layout"]["x"] == .24
    assert client.post(base + "/preflight", json={"revision": saved["revision"]}).status_code == 200


@pytest.fixture
def cloud_presenter(editor, tmp_path, monkeypatch):
    from PIL import Image
    from backlot import avatar_roles as roles
    from backlot.daily_pipeline import PRODUCTION_WORKFLOW_ID, PRODUCTION_WORKFLOW_PROFILE
    client, base, draft, ev, media_id, projects, queue = editor
    role_dir = tmp_path / "roles"
    monkeypatch.setattr(roles, "ROLE_DIRECTORY", role_dir)
    monkeypatch.setattr(roles, "ROLE_FILE", role_dir / "roles.json")
    monkeypatch.setattr(roles, "ROLE_ASSET_DIRECTORY", role_dir / "assets")
    role = roles.create_avatar_role({"name": "测试角色"})
    temporary, target = roles.prepare_role_reference_upload(role["role_id"], "front", "face.png")
    Image.new("RGB", (64, 80), "red").save(temporary, format="PNG")
    roles.finalize_role_reference_upload(role["role_id"], "front", temporary, target, "face.png")
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "test-only")
    monkeypatch.setenv("RUNNINGHUB_WORKFLOW_ID", PRODUCTION_WORKFLOW_ID)
    monkeypatch.setenv("RUNNINGHUB_WORKFLOW_PROFILE", PRODUCTION_WORKFLOW_PROFILE)
    voice = tmp_path / "voice.wav"
    with wave.open(str(voice), "wb") as out:
        out.setparams((1, 2, 48000, 0, "NONE", "not compressed")); out.writeframes(bytes(192000))
    take = client.post(base + "/audio/import", json={"path": str(voice), "text": "动作"}).json()
    calls = []
    class Provider:
        def __init__(self, **kwargs): pass
        def upload_file(self, path, *, file_type):
            if file_type == "audio":
                with wave.open(str(path), "rb") as wav:
                    assert wav.getnchannels() == 1 and wav.getnframes() == 97920
            return file_type + ".test"
        def submit(self, **kwargs):
            calls.append(kwargs)
            assert kwargs["instance_type"] == "plus" and kwargs["exact_total_frames"] == 51
            return {"task_id": "external-test-task"}
        def poll(self, identity):
            return {"status": "SUCCEEDED", "video_url": "test://video", "consume_money_cny": .07}
        def download(self, url, target):
            subprocess.run([resolve_ffmpeg_pair()[0], "-v", "error", "-y", "-f", "lavfi", "-i",
                "color=red:size=448x560:rate=25", "-frames:v", "51", "-c:v", "libx264", "-threads", "2", str(target)],
                check=True, capture_output=True)
    monkeypatch.setattr("tools.avatar.runninghub_avatar.RunningHubLongCatClient", Provider)
    request = {"audio_id": take["id"], "role_id": role["role_id"], "budget_limit_cny": 5,
        "prior_cost_cny": .01, "max_runtime_seconds": 900}
    return client, base, draft, projects, queue, request, Provider, calls


def test_presenter_generation_uses_queue_and_reuses_one_paid_task(cloud_presenter):
    client, base, draft, projects, queue, request, Provider, calls = cloud_presenter
    quoted = client.post(base + "/presenters/quote", json=request)
    assert quoted.status_code == 200, quoted.text
    request.update(quote_signature=quoted.json()["signature"], confirmed=True)
    job = client.post(base + "/presenters/generate", json=request).json()
    assert job["kind"] == "commentary_presenter" and not calls
    outcome = ProductionQueueWorker(queue, projects).run_once()
    assert outcome["status"] == "completed", outcome
    assert len(calls) == 1
    again = client.post(base + "/presenters/generate", json=request).json()
    assert again["job_id"] == job["job_id"]
    assets = client.get(base).json()["presenters"]
    assert assets[0]["audio_id"] == request["audio_id"]
    status = client.get(base + "/presenters/jobs/" + quoted.json()["generation_id"]).json()
    assert status["result"]["actual_cost_cny"] == .07


def test_presenter_budget_blocks_before_remote_submission(cloud_presenter):
    client, base, _, _, _, request, _, calls = cloud_presenter
    response = client.post(base + "/presenters/quote", json={**request, "prior_cost_cny": 4})
    assert response.status_code == 422 and "预算" in response.text and calls == []


def test_ambiguous_presenter_submission_never_creates_another_paid_task(cloud_presenter, monkeypatch):
    client, base, _, projects, queue, request, Provider, calls = cloud_presenter
    def uncertain(self, **kwargs):
        calls.append(kwargs)
        raise RuntimeError("provider body containing secret-test-value")
    monkeypatch.setattr(Provider, "submit", uncertain)
    quoted = client.post(base + "/presenters/quote", json=request).json()
    request.update(quote_signature=quoted["signature"], confirmed=True)
    job = client.post(base + "/presenters/generate", json=request).json()
    assert ProductionQueueWorker(queue, projects).run_once()["status"] == "ambiguous"
    repeated = client.post(base + "/presenters/generate", json=request).json()
    assert repeated["job_id"] == job["job_id"] and repeated["status"] == "ambiguous"
    assert ProductionQueueWorker(queue, projects).run_once() is None
    assert len(calls) == 1
    status = client.get(base + "/presenters/jobs/" + quoted["generation_id"])
    assert "secret-test-value" not in status.text


def test_presenter_local_download_retry_reuses_settled_remote_task(cloud_presenter, monkeypatch):
    client, base, _, projects, queue, request, Provider, calls = cloud_presenter
    original = Provider.download
    downloads = []
    def interrupted(self, url, target):
        downloads.append(url)
        if len(downloads) == 1:
            raise OSError("temporary download interruption")
        original(self, url, target)
    monkeypatch.setattr(Provider, "download", interrupted)
    quoted = client.post(base + "/presenters/quote", json=request).json()
    request.update(quote_signature=quoted["signature"], confirmed=True)
    job = client.post(base + "/presenters/generate", json=request).json()
    first = ProductionQueueWorker(queue, projects).run_once()
    assert first["status"] == "failed" and first["retryable"] is True
    assert client.post(base + "/presenters/generate", json=request).json()["job_id"] == job["job_id"]
    assert ProductionQueueWorker(queue, projects).run_once()["status"] == "completed"
    assert len(calls) == 1 and len(downloads) == 2


def test_short_presenter_accepts_only_proven_silent_tail_without_padding(cloud_presenter, monkeypatch):
    client, base, _, projects, queue, request, Provider, calls = cloud_presenter
    def short_result(self, url, target):
        subprocess.run([resolve_ffmpeg_pair()[0], "-v", "error", "-y", "-f", "lavfi", "-i",
            "color=red:size=448x560:rate=25", "-frames:v", "48", "-c:v", "libx264", "-threads", "2", str(target)],
            check=True, capture_output=True)
    monkeypatch.setattr(Provider, "download", short_result)
    quoted = client.post(base + "/presenters/quote", json=request).json()
    request.update(quote_signature=quoted["signature"], confirmed=True)
    client.post(base + "/presenters/generate", json=request)
    outcome = ProductionQueueWorker(queue, projects).run_once()
    assert outcome["status"] == "completed", outcome
    assert outcome["result"]["omitted_silent_frames"] == 3
    assert client.get(base).json()["presenters"][0]["duration"] == 1.92
    assert len(calls) == 1


def test_presenter_budget_includes_other_settled_tasks_in_this_project(cloud_presenter):
    client, base, _, projects, queue, request, _, calls = cloud_presenter
    quoted = client.post(base + "/presenters/quote", json=request).json()
    client.post(base + "/presenters/generate", json={**request,"quote_signature":quoted["signature"],"confirmed":True})
    assert ProductionQueueWorker(queue, projects).run_once()["status"] == "completed"
    voice = client.get(base).json()["audio"][0]
    take = client.post(base + "/audio/import", json={"path":voice["path"],"text":"第二段动作"}).json()
    response = client.post(base + "/presenters/quote", json={**request,"audio_id":take["id"],"prior_cost_cny":3.25})
    assert response.status_code == 422 and "预算" in response.text and len(calls) == 1


def test_presenter_timeout_keeps_uncertain_cancellation_pending(cloud_presenter, monkeypatch):
    from types import SimpleNamespace
    from datetime import datetime, timezone
    from backlot import commentary_presenter_job as jobs
    client, base, _, projects, queue, request, Provider, calls = cloud_presenter
    cancellations = []
    monkeypatch.setattr(Provider, "cancel", lambda self, task_id: cancellations.append(task_id), raising=False)
    monkeypatch.setattr(Provider, "poll", lambda self, task_id: {"status":"RUNNING"})
    monkeypatch.setattr(jobs, "time", SimpleNamespace(time=lambda:datetime.now(timezone.utc).timestamp()+2000, sleep=lambda seconds:None))
    quoted = client.post(base + "/presenters/quote", json=request).json()
    request.update(quote_signature=quoted["signature"],confirmed=True)
    client.post(base + "/presenters/generate", json=request)
    outcome = ProductionQueueWorker(queue, projects).run_once()
    assert outcome["status"] == "ambiguous" and outcome["retryable"] is False
    assert cancellations == ["external-test-task"] and len(calls) == 1


def test_missing_presenter_frames_containing_speech_are_rejected(cloud_presenter, tmp_path, monkeypatch):
    client, base, _, projects, queue, request, Provider, calls = cloud_presenter
    voice = tmp_path/"speech-tail.wav"
    with wave.open(str(voice), "wb") as out:
        out.setparams((1,2,48000,0,"NONE","not compressed")); out.writeframes(np.full(96000,2000,dtype="<i2").tobytes())
    take = client.post(base + "/audio/import",json={"path":str(voice),"text":"动作"}).json()
    request["audio_id"] = take["id"]
    def short_result(self,url,target):
        subprocess.run([resolve_ffmpeg_pair()[0],"-v","error","-y","-f","lavfi","-i",
            "color=red:size=448x560:rate=25","-frames:v","48","-c:v","libx264","-threads","2",str(target)],check=True,capture_output=True)
    monkeypatch.setattr(Provider,"download",short_result)
    quoted = client.post(base + "/presenters/quote",json=request).json()
    client.post(base + "/presenters/generate",json={**request,"quote_signature":quoted["signature"],"confirmed":True})
    outcome = ProductionQueueWorker(queue,projects).run_once()
    assert outcome["status"] == "failed" and outcome["retryable"] is False
    assert "非零语音" in outcome["error"]["message"] and len(calls) == 1
    assert client.get(base).json()["presenters"] == []


def test_caption_groups_retain_real_word_timestamps(editor, tmp_path):
    client, base, *_ = editor
    voice = tmp_path / "words.wav"
    with wave.open(str(voice), "wb") as out:
        out.setparams((1, 2, 48000, 0, "NONE", "not compressed")); out.writeframes(bytes(192000))
    take = client.post(base + "/audio/import", json={"path": str(voice), "text": "粤仔只是想握个手。"}).json()
    words = [{"text": c, "start": i*.15+.05, "end": (i+1)*.15+.05} for i,c in enumerate("粤仔只是想握个手")]
    result = client.post(base + "/audio/alignment", json={"audio_id": take["id"], "words": words,
        "cue_word_ends": [4, 8], "provenance": "已知逐字时间戳，按短意群分组"}).json()
    assert result["cues"] == [{"start": .05, "end": .65, "text": "粤仔只是"},
        {"start": .65, "end": 1.25, "text": "想握个手。"}]


def test_editor_reports_coverage_and_missing_candidates(editor):
    client, base, draft, ev, media_id, *_ = editor
    response = client.put(base, json=plan(draft, ev, media_id))
    assert response.status_code == 200, response.text
    audit = client.get(base + "/editorial").json()
    assert audit["coverage"]["reviewed"] == 1 and audit["coverage"]["pending"] == 0
    assert audit["events"][0]["tone"] == "客观解释"


def test_unprocessed_candidate_blocks_preflight(editor):
    client, base, draft, ev, media_id, *_ = editor
    payload = plan(draft, ev, media_id)
    payload["payload"]["editorial"]["coverage"] = []
    saved = client.put(base, json=payload).json()
    response = client.post(base + "/preflight", json={"revision": saved["revision"]})
    assert response.status_code == 422 and "覆盖" in response.text


def test_j_cut_is_frozen_independently_and_traced(editor):
    client, base, draft, ev, media_id, projects, queue = editor
    payload = plan(draft, ev, media_id)
    first = payload["payload"]["segments"][0]
    first["source_audio"] = []
    second = {**first, "id": "reaction", "shots": [{"evidence_id": ev["id"], "start": 6, "end": 8}],
        "source_audio": [{"evidence_id": ev["id"], "start": 5.5, "end": 7.5, "offset": -.5,
            "gain_db": -6, "fade_in": .05, "fade_out": .1}]}
    payload["payload"]["segments"].append(second)
    saved = client.put(base, json=payload).json()
    assert saved["payload"]["segments"][1]["source_audio"][0]["offset"] == -.5
    job = client.post(base + "/render", json={"revision": saved["revision"]}).json()
    frozen = read_json(flow.version_dir(draft["id"], job["parent_job_id"], projects_root=projects) / "request.json")
    assert frozen["duration"] == 4
    assert frozen["segments"][1]["source_audio"][0]["timeline_start"] == 1.5
    assert any(r["slot_id"] == "audio-001" for r in refs.list_usage(project_id=draft["id"]))
    outcome = ProductionQueueWorker(queue, projects).run_once()
    assert outcome["status"] == "completed", outcome
    output = flow.output_path(draft["id"], job["parent_job_id"], projects_root=projects)
    decoded = subprocess.run([resolve_ffmpeg_pair()[0], "-v", "error", "-i", str(output),
        "-f", "s16le", "-ac", "1", "-ar", "48000", "-"], check=True, capture_output=True)
    samples = np.frombuffer(decoded.stdout, dtype="<i2").astype(float)
    assert np.sqrt(np.mean(samples[12000:48000] ** 2)) < 10
    assert np.sqrt(np.mean(samples[80000:90000] ** 2)) > 200


def test_subtitles_follow_imported_speech_not_character_proportions(editor, tmp_path):
    client, base, draft, ev, media_id, *_ = editor
    path = tmp_path / "voice.wav"
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        out.writeframes(np.zeros(144000, dtype="<i2").tobytes())
    take = client.post(base + "/audio/import", json={"path": str(path), "text": "先看动作。再看结果。"}).json()
    aligned = client.post(base + "/audio/alignment", json={"audio_id": take["id"], "provenance": "测试已知语音时间戳",
        "words": [{"text": "先看动作", "start": .2, "end": .9}, {"text": "再看结果", "start": 2, "end": 2.5}]}).json()
    assert aligned["cues"][1]["start"] == 2
    payload = plan(draft, ev, media_id)
    row = payload["payload"]["segments"][0]
    row.update(mode="narration", text=take["text"], audio_id=take["id"], subtitle_mode="aligned", alignment_id=aligned["id"],
        sentence_links=[{"cue_index": 0, "shot_indexes": [0], "basis": "动作画面"},
                        {"cue_index": 1, "shot_indexes": [0], "basis": "结果画面"}])
    row["shots"][0]["end"] = 5
    saved = client.put(base, json=payload).json()
    response = client.post(base + "/preflight", json={"revision": saved["revision"]})
    assert response.status_code == 200, response.text
    assert not any("估时" in w for w in response.json()["warnings"])
    assert response.json()["duration"] == 2.5  # speech .2..2.5 plus .06/.12 padding, rounded to frame clock


def test_repeated_source_requires_story_reason_but_callback_is_allowed(editor):
    client, base, draft, ev, media_id, *_ = editor
    payload = plan(draft, ev, media_id)
    first = payload["payload"]["segments"][0]
    payload["payload"]["segments"].append({**first, "id": "callback"})
    saved = client.put(base, json=payload).json()
    assert client.post(base + "/preflight", json={"revision": saved["revision"]}).status_code == 422
    saved["payload"]["segments"][1]["shots"][0]["repeat_reason"] = "在解释之后回到开头动作，补足前因"
    saved = client.put(base, json=saved).json()
    assert client.post(base + "/preflight", json={"revision": saved["revision"]}).status_code == 200


def test_out_of_bounds_j_cut_is_rejected_before_queue(editor):
    client, base, draft, ev, media_id, *_ = editor
    payload = plan(draft, ev, media_id)
    payload["payload"]["segments"][0]["source_audio"] = [{"evidence_id": ev["id"], "start": 1, "end": 3, "offset": -.5}]
    saved = client.put(base, json=payload).json()
    response = client.post(base + "/render", json={"revision": saved["revision"]})
    assert response.status_code == 422 and "时间范围" in response.text


def test_alignment_cli_imports_tencent_timestamps_without_paid_call(editor, tmp_path):
    client, base, draft, ev, media_id, projects, queue = editor
    path = tmp_path / "voice.wav"
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, 48000, 0, "NONE", "not compressed")); out.writeframes(bytes(96000))
    take = client.post(base + "/audio/import", json={"path": str(path), "text": "动作"}).json()
    sidecar = tmp_path / "voice.wav.tencent.json"
    sidecar.write_text(json.dumps({"provider": "tencent", "subtitles": [
        {"Text": "动", "BeginTime": 100, "EndTime": 300}, {"Text": "作", "BeginTime": 300, "EndTime": 500}]}), encoding="utf-8")
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"audio_id": take["id"], "tencent_metadata_path": str(sidecar)}), encoding="utf-8")
    output = tmp_path / "alignment.json"
    from scripts.material_commentary_cli import main
    assert main(["--projects-root", str(projects), "--db", str(library.data_dir()/"library.sqlite3"),
        "--output", str(output), "alignment-import", draft["id"], str(request)]) == 0
    assert read_json(output)["cues"] == [{"start": .1, "end": .5, "text": "动作"}]


def test_comparison_uses_frozen_source_identity_and_actual_clock(editor):
    client, base, draft, ev, media_id, projects, queue = editor
    saved = client.put(base, json=plan(draft, ev, media_id)).json()
    client.post(base + "/render", json={"revision": saved["revision"]})
    result = client.post(base + "/compare", json={"baseline_project_id": draft["id"]}).json()
    assert result["same_source_pool"] is True
    assert result["target"]["duration"] == 2 and result["target"]["shot_count"] == 1
    assert result["target"]["original_audio_ratio"] == 1


def test_excluded_candidate_cannot_enter_final_video(editor):
    client, base, draft, ev, media_id, *_ = editor
    payload = plan(draft, ev, media_id)
    payload["payload"]["editorial"]["coverage"][0]["status"] = "excluded"
    saved = client.put(base, json=payload).json()
    response = client.post(base + "/preflight", json={"revision": saved["revision"]})
    assert response.status_code == 422 and "排除" in response.text


def test_malformed_editorial_import_returns_controlled_validation_error(editor):
    client, base, draft, ev, media_id, *_ = editor
    payload = plan(draft, ev, media_id)
    payload["payload"]["editorial"]["coverage"] = [None]
    response = client.put(base, json=payload)
    assert response.status_code == 422


def test_mobile_caption_style_survives_editor_queue_and_srt(editor):
    client, base, draft, ev, media_id, projects, queue = editor
    payload = plan(draft, ev, media_id)
    row = payload["payload"]["segments"][0]
    row.update(subtitle_mode="timed", subtitle_position="top",
               subtitles=[{"start": .1, "end": 1.8, "text": "看，动作！"}],
               sentence_links=[{"cue_index": 0, "shot_indexes": [0], "basis": "移动动作"}])
    payload["payload"]["segments"].append({**row, "id": "original-tail", "subtitle_mode": "none",
        "subtitles": [], "sentence_links": [], "shots": [{"evidence_id": ev["id"], "start": 6, "end": 8}]})
    saved = client.put(base, json=payload).json()
    first = client.post(base + "/render", json={"revision": saved["revision"]}).json()
    assert ProductionQueueWorker(queue, projects).run_once()["status"] == "completed"
    saved["payload"]["subtitle_style"] = {"font_size": 64, "text_color": "#ffffff",
        "highlight_color": "#ffd54a", "highlight_terms": ["动作"], "outline_size": 3,
        "shadow": 1, "strip_punctuation": True}
    saved = client.put(base, json=saved).json()
    assert saved["payload"]["subtitle_style"]["font_size"] == 64
    assert saved["payload"]["subtitle_style"]["highlight_color"] == "#FFD54A"
    assert client.put(base, json=saved).json()["revision"] == saved["revision"]
    assert saved["payload"]["segments"][0]["subtitles"][0]["text"] == "看，动作！"
    second = client.post(base + "/render", json={"revision": saved["revision"]}).json()
    assert first["parent_job_id"] != second["parent_job_id"]
    directory = flow.version_dir(draft["id"], second["parent_job_id"], projects_root=projects)
    frozen = read_json(directory / "request.json")
    assert frozen["subtitle_style"] == saved["payload"]["subtitle_style"]
    assert ProductionQueueWorker(queue, projects).run_once()["status"] == "completed"
    assert "看动作" in (directory / "subtitles.srt").read_text(encoding="utf-8-sig")
    assert "看，动作！" not in (directory / "subtitles.srt").read_text(encoding="utf-8-sig")
    assert read_json(directory / "result.json")["cache"][0]["hit"] is False
    assert read_json(directory / "result.json")["cache"][1]["hit"] is True


def test_oversized_mobile_caption_is_blocked_before_queue(editor):
    client, base, draft, ev, media_id, *_ = editor
    payload = plan(draft, ev, media_id)
    payload["payload"]["subtitle_style"] = {"font_size": 64}
    payload["payload"]["segments"][0].update(subtitle_mode="timed",
        subtitles=[{"start": .1, "end": 1.8, "text": "这是一句明显超出手机安全区的字幕"}],
        sentence_links=[{"cue_index": 0, "shot_indexes": [0], "basis": "动作画面"}])
    saved = client.put(base, json=payload).json()
    response = client.post(base + "/render", json={"revision": saved["revision"]})
    assert response.status_code == 422 and "安全宽度" in response.text


@pytest.mark.parametrize("style", [
    {"font_size": 200}, {"text_color": "{\\c&H00FF00&}"},
    {"highlight_terms": ["{\\pos(0,0)}"]}, {"strip_punctuation": "false"}])
def test_invalid_caption_styles_return_validation_error(editor, style):
    client, base, draft, ev, media_id, *_ = editor
    payload = plan(draft, ev, media_id)
    payload["payload"]["subtitle_style"] = style
    assert client.put(base, json=payload).status_code == 422


def test_caption_punctuation_keeps_meaningful_numeric_and_english_tokens():
    from backlot.commentary_captions import display_text, normalize_style
    style = normalize_style({"strip_punctuation": True})
    assert display_text("用时3.14秒，12:30开始，完成100%！", style) == "用时3.14秒12:30开始完成100%"
    assert display_text("Don't stop,go!", style) == "Don't stop go"
    assert display_text("原字幕，保留。") == "原字幕，保留。"


def test_caption_highlighting_resets_color_and_prefers_complete_terms():
    from backlot.commentary_captions import ass_text, normalize_style
    style = normalize_style({"highlight_terms": ["朋友", "交朋友"], "strip_punctuation": True})
    value = ass_text("一起交朋友！", style)
    assert value == "一起{\\c&H004AD5FF&}交朋友{\\c&H00FFFFFF&}"
