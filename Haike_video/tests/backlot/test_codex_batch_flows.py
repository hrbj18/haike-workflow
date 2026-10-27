"""CLI -> real local APIs/SQLite/queue/producer/plans, with fake suppliers only."""
import base64
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import wave

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backlot.codex_batch import BatchError, CodexBatch, file_sha, validate_spec
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import Studio
from backlot.work_catalog import WorkCatalog, WorkError


@pytest.fixture
def flow(tmp_path, monkeypatch, capsys):
    root = tmp_path / "workspace"
    projects = root / "Haike_video/projects"
    projects.mkdir(parents=True)
    portrait = tmp_path / "person.png"
    Image.new("RGB", (600, 800), "navy").save(portrait)
    audio = tmp_path / "complete.wav"
    with wave.open(str(audio), "wb") as out:
        out.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        out.writeframes(b"\0\0" * 77760)  # Exactly 3.24 seconds; no shortened excerpt.
    source_audio = audio.read_bytes()

    class Supplier:
        def __init__(self):
            self.quotes, self.intents, self.confirm_calls = {}, {}, []
        def upload(self, path, kind): return {"id": kind + "-fixture"}
        def prepare_asr_audio(self, path): return {"id": "bailian-audio-fixture"}
        def request(self, path): return {"items": [{"id": i} for i in ("haike/avatar", "haike/tencent-asr")]}
        def quote(self, model, inputs, project):
            identity = "q-" + str(len(self.quotes) + 1)
            value = {"id": identity, "model": model, "max_charge_micros": "10"}
            self.quotes[identity] = value
            return value
        def confirm(self, quote, maximum, identity):
            self.confirm_calls.append((quote['model'], identity))
            self.intents.setdefault(identity, {"id": identity, "model": quote["model"]})
            return self.intents[identity]
        def wait(self, intent, timeout):
            model = intent["model"]
            result = ({"items": [{"id": 123, "url": "https://www.pexels.com/video/computer-123/", "video_files": [
                          {"file_type": "video/mp4", "width": 1080, "link": "https://videos.pexels.com/fake.mp4"}]}]} if model == "haike/assets" else
                      {"segments": [{"start": 0, "end": 3.24, "text": "本期经过核实的测试。", "words": [
                          {"start": 0, "end": 3.24, "text": "本期经过核实的测试。"}]}]} if model == "haike/bailian-asr" else
                      {"video_url": "https://supplier.invalid/video"} if model == "haike/avatar" else
                      {"text": "[0:0.000,0:3.240] 本期经过核实的测试。"} if model == "haike/tencent-asr" else
                      {"audio_base64": base64.b64encode(source_audio).decode()})
            return {"id": "job-" + intent["id"], "status": "succeeded", "result": result}
    supplier = Supplier()

    class Publisher:
        def __init__(self): self.rows, self.payloads = {}, []
        def accounts(self):
            return [{"id": n, "platform": p, "status": "active", "has_creator": True}
                    for n, p in enumerate(("douyin", "kuaishou", "shipinhao"), 1)]
        def submit(self, payload, key):
            self.payloads.append(copy.deepcopy(payload))
            self.rows.setdefault(key, {"id": len(self.rows) + 1, "status": "pending",
                "platform": payload["expected_platform"], "account_id": payload["account_id"],
                "video_sha256": payload["video_sha256"]})
            return self.rows[key]
        def tasks(self): return list(self.rows.values())
    publisher = Publisher()
    monkeypatch.setattr("backlot.work_publish.CreatorGateway", lambda: publisher)
    monkeypatch.setattr(Studio, "client", lambda self: supplier)
    monkeypatch.setattr("backlot.studio_avatar.prepare_audio", lambda src, dst, rate=1: (shutil.copyfile(src, dst), 3.24)[1])
    monkeypatch.setattr("backlot.studio_avatar.download_result", lambda url, path: path.write_bytes(b"fake-avatar-media"))
    compositions = []
    def compose(folder, draft, video, narration, duration, cues, **kw):
        assert duration == 3.24 and Path(narration).read_bytes() == source_audio
        path = folder / "avatar-preview.mp4"
        path.write_bytes(b"fake-local-render-" + draft["id"].encode())
        compositions.append({"draft_id": draft['id'], "storyboard": kw.get('storyboard')})
        return path
    monkeypatch.setattr("backlot.studio_composition.compose_avatar", compose)
    monkeypatch.setattr("backlot.studio_render.media_probe", lambda path: {"duration": 3.24, "audio": {"codec_name": "pcm_s16le"}, "video": {"width": 1080, "height": 1920}})
    monkeypatch.setattr("backlot.studio_avatar.media_probe", lambda path: {"duration": 3.24, "audio": {"codec_name": "pcm_s16le"}})
    monkeypatch.setattr("backlot.work_catalog.probe", lambda path: {"duration": 3.24, "width": 1080, "height": 1920, "has_audio": True})
    studio = Studio(projects)
    catalog = WorkCatalog(projects)
    queue = ProductionQueue(root / "queue.sqlite3", projects)
    app = FastAPI()
    app.state.studio, app.state.work_catalog = studio, catalog
    app.state.works_projects_root, app.state.production_queue = projects, queue
    @app.get("/api/health")
    def health(): return {"edition": "haike-workflow-2", "workspace": str(root)}
    @app.get("/api/studio/audio-center")
    def voices(): return {"items": [{"id": "test-voice", "model": "haike/cosyvoice", "name": "fixture"}]}
    @app.get("/api/production-queue/jobs/{job_id}")
    def job(job_id: str): return queue.get(job_id)
    @app.post("/api/production-queue/jobs/{job_id}/retry")
    def retry(job_id: str): return queue.retry(job_id)
    from backlot.studio_api import router as studio_router
    from backlot.work_api import router as work_router
    from backlot.automation_task_center_api import router as task_router
    app.include_router(studio_router); app.include_router(work_router); app.include_router(task_router)
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 19001))
    class API:
        base = "http://127.0.0.1"
        drop_publish_response = False
        def call(self, path, data=None, *, method=None, raw=None, content_type=None):
            method = method or ("POST" if data is not None or raw is not None else "GET")
            kw = {"content": raw, "headers": {"content-type": content_type}} if raw is not None else {"json": data} if data is not None else {}
            response = client.request(method, path, **kw)
            if response.status_code >= 400:
                raise BatchError(str(response.json()), status=response.status_code)
            if path.startswith("/api/works/publish/") and self.drop_publish_response:
                self.drop_publish_response = False
                raise BatchError("lost original publish response", unknown=True)
            return response.json()
    api = API()
    cli_path = Path(__file__).resolve().parents[2] / "scripts/codex_video_batch.py"
    module_spec = importlib.util.spec_from_file_location("fixture_batch_cli", cli_path)
    cli = importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, "LocalAPI", lambda base: api)
    monkeypatch.setattr(cli, "CodexBatch", lambda spec, api: CodexBatch(spec, root=root, api=api))
    spec_path = tmp_path / "spec.json"
    def command(name, spec=None, evidence=None, *, slot=None, analysis=None):
        if spec is not None: spec_path.write_text(json.dumps(spec), encoding="utf-8")
        arguments = [name, "--spec", str(spec_path)]
        if evidence is not None:
            evidence_path = tmp_path / "evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            arguments += ["--evidence", str(evidence_path)]
        if slot is not None:
            arguments += ['--slot', slot]
        if analysis is not None:
            analysis_path = tmp_path / 'analysis.json'
            analysis_path.write_text(json.dumps(analysis), encoding='utf-8')
            arguments += ['--analysis', str(analysis_path)]
        code = cli.main(arguments)
        output = capsys.readouterr()
        return code, json.loads(output.out or output.err)
    def produce(*, expect_complete=True):
        from backlot.studio_avatar import run_avatar
        worker = ProductionQueueWorker(queue, projects, handlers={"studio_avatar": lambda job: run_avatar(
            projects / job["project_id"], job["frozen_request"], supplier)}, worker_id="offline-fixture")
        results = []
        while value := worker.run_once(): results.append(value)
        if expect_complete:
            assert all(value["status"] == "completed" for value in results), json.dumps(results, ensure_ascii=True)
        return results
    def specification(count=1, upload=True, publish=False):
        items = []
        for n in range(count):
            item = {"slot_id": f"slot{n}", "topic_key": f"event-{n}", "sources": [{"url": f"https://example.com/source{n}"}],
                "title": f"本期主题{n}", "text": "本期经过核实的测试。", "template_id": "avatar-safe-circle-v1",
                "portrait_path": str(portrait), "target_duration_seconds": 25, "max_charge_micros": 100,
                "allow_graphic_fallback": False, "network_materials_enabled": False,
                "publishing": {"desc": "本期说明", "topics": "测试", "source_rights_status": "confirmed", "targets": []}}
            if upload:
                item["audio_path"] = str(audio)
                item["sources"] = [{"kind": "user_provided", "label": "用户提供完整音轨与人物图"}]
            else: item.update(voice_id="test-voice", model_id="haike/cosyvoice", speech_rate=1.15)
            if publish:
                item["publishing"]["targets"] = [{"platform": p, "account_id": k,
                    "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1, minutes=n)).isoformat()}
                    for k, p in enumerate(("douyin", "kuaishou", "shipinhao"), 1)]
            items.append(item)
        return {"batch_id": "offline-core", "limit_micros": count * 100, "items": items}
    def evidence(spec):
        batch = CodexBatch(spec, root=root, api=api)
        rows = []
        for item in spec["items"]:
            task = batch._task(item)
            folder = projects / batch._draft_id(item) / "renders" / f"studio-{task['facts']['execution']['draft_revision']}"
            video = folder / "avatar-preview.mp4"
            cover = folder / "approved-cover.jpg"; Image.new("RGB", (600, 800), "blue").save(cover)
            quality = folder / "technical.json"
            quality.write_text(json.dumps({"status": "technical_checks_passed", "video": {"sha256_after": file_sha(video)}}), encoding="utf-8")
            rows.append({"slot_id": item["slot_id"], "technical_checks_passed": True, "frame_review_passed": True,
                "source_claims_verified": True, "authorized_publication": True, "cover_reviewed": True,
                "quality_report": str(quality), "cover_path": str(cover), "video_sha256": file_sha(video),
                "cover_sha256": file_sha(cover), "source_rights_status": "confirmed"})
        return {"batch_id": spec["batch_id"], "spec_sha256": batch.spec_hash, "items": rows}
    return locals()


def test_single_complete_audio_image_requirement_cli_reaches_real_queue_and_report(flow):
    spec = flow["specification"]()
    code, started = flow["command"]("advance", spec)
    assert code == 0 and len(started["items"]) == 1
    draft = flow["studio"].draft(started["items"][0]["draft_id"])
    assert draft["input"]["soundMode"] == "audio" and "rate" not in draft["input"]
    assert flow["studio"].asset(draft["input"]["audio"]["id"]).read_bytes() == flow["source_audio"]
    results = flow["produce"]()
    assert results[0]["result"]["work_id"]
    code, report = flow["command"]("report")
    assert code == 0 and report["items"][0]["queue"]["status"] == "completed"
    assert report["items"][0]["status"] == "awaiting_human"
    document = Path(report["report_path"]).read_text(encoding="utf-8")
    assert "完整音轨" in document and "仅制作" in document and "未知" in document
    assert file_sha(flow["audio"]) in document
    assert str(flow["portrait"]) not in document and str(flow["audio"]) not in document
    assert not any(q["model"].endswith("tts") for q in flow["supplier"].quotes.values())
    assert not flow["publisher"].rows
    reviewed = flow['evidence'](spec)
    for row in reviewed['items']:
        for field in ('authorized_publication', 'cover_reviewed', 'cover_path', 'cover_sha256', 'source_rights_status'):
            row.pop(field)
    code, completed = flow['command']('advance', evidence=reviewed)
    assert code == 0 and completed['items'][0]['status'] == 'completed'
    assert '仅制作未发布' in completed['items'][0]['stage']
    assert flow['catalog'].get(completed['items'][0]['work_id'])['final_version_id']
    assert flow['command']('approve', evidence=reviewed)[0] == 0
    code, repeated = flow['command']('report')
    assert code == 0 and repeated['items'][0]['status'] == 'completed'
    assert not flow['publisher'].rows and not flow['publisher'].payloads


def test_night_three_cli_production_publish_schedule_report_and_lost_response_resume(flow):
    spec = flow["specification"](3, upload=False, publish=True)
    code, started = flow["command"]("advance", spec)
    assert code == 0, json.dumps(started, ensure_ascii=True)
    assert flow["command"]("advance")[0] == 0  # New invocation reuses original jobs/quotes.
    assert len(flow["queue"].list()["tasks"]) == 3
    flow["produce"]()
    assert flow["command"]("advance")[0] == 0
    assert not flow["publisher"].rows  # Rendering never fabricates human review.
    evidence = flow["evidence"](spec)
    flow["api"].drop_publish_response = True
    code, partial = flow["command"]("advance", evidence=evidence)
    assert code == 2 and partial["errors"] and len(flow["publisher"].rows) == 9
    assert flow["command"]("advance", evidence=evidence)[0] == 0
    assert len(flow["publisher"].rows) == 9
    assert len(flow["publisher"].payloads) == 9
    assert all(p["scheduled_at"] for p in flow["publisher"].payloads)
    for row in flow["publisher"].rows.values():
        row.update(status="done", acceptance_status="verified", acceptance_evidence={"work_id": f"platform-{row['id']}",
            "unique_work": True, "video_matches": True, "title_matches": True, "cover_matches": True})
    code, done = flow["command"]("advance", evidence=evidence)
    assert code == 0 and all(i["status"] == "completed" for i in done["items"])
    assert len(flow["queue"].list()["tasks"]) == 3 and len(flow["publisher"].rows) == 9
    document = Path(done["report_path"]).read_text(encoding="utf-8")
    assert all(f"本期主题{n}" in document for n in range(3))
    assert "已提交并核验" in document and "排期" in document and "未知" in document


def test_audio_hash_change_cannot_replace_a_frozen_track(flow):
    spec = flow["specification"]()
    assert flow["command"]("init", spec)[0] == 0
    flow["audio"].write_bytes(b"different audio")
    assert flow["command"]("prepare")[0] == 2
    assert not flow["supplier"].intents


def test_production_only_approval_cannot_claim_unreviewed_or_changed_video(flow):
    spec = flow['specification']()
    assert flow['command']('advance', spec)[0] == 0
    flow['produce']()
    reviewed = flow['evidence'](spec)
    reviewed['items'][0]['frame_review_passed'] = False
    assert flow['command']('approve', evidence=reviewed)[0] == 2
    reviewed['items'][0]['frame_review_passed'] = True
    reviewed['items'][0]['video_sha256'] = '0' * 64
    assert flow['command']('approve', evidence=reviewed)[0] == 2
    assert flow['command']('report')[1]['items'][0]['status'] == 'awaiting_human'
    assert not flow['publisher'].rows


def test_schedule_requires_explicit_timezone_before_any_api(flow):
    spec = flow["specification"](publish=True)
    spec["items"][0]["publishing"]["targets"][0]["scheduled_at"] = "2026-10-18T08:00:00"
    with pytest.raises(BatchError, match="时区"):
        validate_spec(spec)


@pytest.mark.parametrize('name,slot,analysis', [
    ('material-context', None, None), ('material-apply', 'slot0', None), ('status', None, {})])
def test_material_cli_requires_slot_and_analysis_only_for_apply(flow, name, slot, analysis):
    code, result = flow['command'](name, flow['specification'](), slot=slot, analysis=analysis)
    assert code == 2 and result['ok'] is False
    assert not flow['queue'].list()['tasks'] and not flow['supplier'].intents


def test_agent_cli_plan_candidate_review_resumes_original_bailian_job_without_model_api(flow, monkeypatch):
    from backlot.studio import atomic_private
    from backlot.studio_storyboard import TrialRelay
    studio, supplier = flow['studio'], flow['supplier']
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'offline-fixture-not-a-real-provider-key')
    for name in tuple(os.environ):
        if name.startswith('TENCENT_') or name in {'OPENAI_API_KEY', 'GPT_API_KEY'}:
            monkeypatch.delenv(name)
    atomic_private(studio.private / 'studio-asr/policy.json', {'default_provider': 'bailian', 'bailian_enabled': True, 'verified': False})
    atomic_private(studio.private / 'internal-services/budget-policy.json', {
        'per_call_micros': {'haike/bailian-asr': '10'}, 'daily_limit_micros': '1000'})
    atomic_private(studio.private / 'studio-ai/relay.json', {'analysis_mode': 'agent', 'network_sources': ['pexels']})
    monkeypatch.setattr('backlot.studio_storyboard.download_account', lambda studio: (3, None, {'status': 'ready'}))
    monkeypatch.setattr('backlot.network_materials.creator_call', lambda path, data=None, **kw: {
        'ok': True, 'account': {'id': 3, 'platform': 'douyin', 'download_status': 'ready'}})
    monkeypatch.setattr(supplier, 'request', lambda path: {'items': [{'id': 'haike/avatar'}]})
    monkeypatch.setattr(TrialRelay, 'call', lambda *a, **kw: pytest.fail('Agent visual analysis must never call the relay'))
    monkeypatch.setattr('backlot.studio_storyboard.image_preview', lambda source, frame, at=0: Image.new('RGB', (640, 360), 'blue').save(frame))
    spec = flow['specification'](upload=False)
    spec['items'][0].update(network_materials_enabled=True, template_id='avatar-deepblue-n1-v1')
    code, queued = flow['command']('advance', spec)
    assert code == 0, json.dumps(queued, ensure_ascii=True)
    job_id = queued['items'][0]['queue']['job_id']
    initial_draft = studio.draft(queued['items'][0]['draft_id'])
    stopped = flow['produce'](expect_complete=False)[0]
    assert stopped['status'] == 'failed' and stopped['retryable'] is True
    assert stopped['job_id'] == job_id
    code, context = flow['command']('material-context', slot='slot0')
    assert code == 0 and context['status'] == 'needs_plan' and context['audio_sha256']
    script = context['script']
    analysis = {'draft_revision': context['draft_revision'], 'clock_sha256': context['clock_sha256'], 'materials': [],
        'scenes': [{'from_cue': 0, 'to_cue': len(context['cues']) - 1, 'script_start': 0, 'script_end': len(script),
            'label': '与口播相关的电脑画面', 'asset_id': '', 'query': '电脑画面 | computer', 'illustration_prompt': '', 'reason': '当前Agent按真实字幕安排电脑相关画面'}]}
    code, accepted = flow['command']('material-apply', slot='slot0', analysis=analysis)
    assert code == 0 and accepted['queue_resumed'] is False
    assert flow['queue'].get(job_id)['status'] == 'failed'  # Applying observations never retries paid work.
    assert flow['command']('resume', slot='slot0')[0] == 0
    stopped = flow['produce'](expect_complete=False)[0]
    assert stopped['job_id'] == job_id and stopped['status'] == 'failed' and stopped['retryable']
    code, context = flow['command']('material-context', slot='slot0')
    assert code == 0 and context['status'] == 'needs_review' and context['analysis']['scenes'] == analysis['scenes']
    candidate = context['candidates'][0]
    for frame in candidate['frames']:
        with Image.open(frame['path']) as pixels:
            assert pixels.size == (640, 360)
    decisions = {'draft_revision': context['draft_revision'], 'clock_sha256': context['clock_sha256'],
        'decisions': [{'candidate_id': candidate['candidate_id'], 'sha256': candidate['sha256'], 'suitable': True,
            'observed_frames': [frame['at_seconds'] for frame in candidate['frames']], 'reason': '假素材三个代表帧均为电脑画面，本用例仅验证Agent观察回执合同'}]}
    assert flow['command']('material-apply', slot='slot0', analysis=decisions)[0] == 0
    assert flow['queue'].get(job_id)['status'] == 'failed'
    assert flow['command']('resume', slot='slot0')[0] == 0
    done = flow['produce']()[0]
    assert done['job_id'] == job_id and done['status'] == 'completed' and done['result']['work_id']
    assert flow['command']('material-context', slot='slot0')[1]['status'] == 'ready'
    assert studio.draft(initial_draft['id']) == initial_draft
    assert len(flow['queue'].list()['tasks']) == 1
    models = [model for model, _ in supplier.confirm_calls]
    assert models.count('haike/cosyvoice') == models.count('haike/bailian-asr') == models.count('haike/avatar') == 1
    assert not {'haike/tencent-asr', 'haike/text'} & set(models)
    assert flow['compositions'][0]['storyboard']['model'] == 'current-agent'
    assert flow['compositions'][0]['storyboard']['scenes'][0]['asset_sha256'] == candidate['sha256']


@pytest.mark.parametrize('segments', [None, []])
def test_legacy_timestamp_text_asr_keeps_complete_audio_clock(segments):
    from backlot.studio_avatar import clock_captions
    result = {'text': '[0:0.000,0:3.240] 完整音轨。'}
    if segments is not None:
        result['segments'] = segments
    clock = clock_captions(result, 3.24)
    assert clock[0]['startMs'] == 0 and clock[-1]['endMs'] == 3240
