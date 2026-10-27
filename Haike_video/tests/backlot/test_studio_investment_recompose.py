"""Real queue/worker contract with fake composition; never contact providers."""
from copy import deepcopy
import json

import pytest

from backlot.production_queue import ProductionQueue, ProductionQueueConflict
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import Studio, atomic_private
from backlot.studio_investment import render_props
from backlot import studio_investment_recompose as recompose
from backlot.studio_investment_recompose import KIND, fingerprint, prepare, submit, validate
from backlot.work_catalog import WorkCatalog, WorkError, sha


@pytest.fixture
def source(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    project = projects / ("studio-" + "a" * 16)
    folder = project / "renders/studio-2"
    folder.mkdir(parents=True)
    atomic_private(project / "project.json", {"id": project.name, "title": "原稿"})
    audio, avatar, output = (folder / name for name in ("narration.wav", "avatar-source.mp4", "avatar-preview.mp4"))
    for path in (audio, avatar, output): path.write_bytes(path.name.encode())
    d = {"id": project.name, "revision": 2, "template_id": "avatar-investment-a-v6", "title": "招商A", "text": "今天收现金。",
         "layout": {}, "input": {"soundMode": "audio", "subtitles": True, "ai": {"enabled": False},
            "investment": {"emphasis": [{"match": "收现金", "text": "现金生意", "kind": "card", "footnote": "制作说明"}]}}}
    cues = [{"text": "今天收现金", "startMs": 0, "endMs": 3000, "timestampMs": None, "confidence": None}]
    props, _ = render_props(d, 3, cues)
    atomic_private(folder / "props.json", props)
    atomic_private(folder / "qa.json", {"template_id": d["template_id"], "caption_timing": "ASR word-level"})
    prepared = {"duration": 3, "audio_path": str(audio)}
    atomic_private(folder / "gateway-state.json", {"prepared": prepared, "stages": {"asr": {"job": {
        "id": "original-asr", "status": "succeeded", "result": {"segments": [{"text": "今天收现金", "start": 0, "end": 3,
            "words": [{"text": "今天收现金", "start": 0, "end": 3}]}]}}}}})
    monkeypatch.setattr("backlot.work_catalog.probe", lambda path: {"duration": 3, "width": 1080, "height": 1920, "has_audio": True})
    catalog = WorkCatalog(projects)
    original_work = catalog.register(project.name, output)
    queue = ProductionQueue(tmp_path / ".backlot/production-queue.sqlite3", projects)
    original = queue.submit(project_id=project.name, kind="studio_avatar", source="codex", priority="normal", parent_job_id="studio-2",
                            frozen_request={"draft": d, "prepared": prepared, "render_id": "studio-2"})
    claimed = queue.claim_next("source-worker")
    queue.finish(claimed["job_id"], "source-worker", status="completed", stage="原片完成", result={"work_id": original_work["work_id"]})
    def forbidden(*args, **kwargs): pytest.fail("Local recompose must never construct or invoke an SDK")
    monkeypatch.setattr(Studio, "client", forbidden)
    monkeypatch.setattr("backlot.studio.sdk_type", forbidden)
    calls = []
    def compose(target, draft, source_avatar, source_audio, duration, actual_cues):
        calls.append((deepcopy(draft), source_avatar, source_audio, duration, deepcopy(actual_cues)))
        final = target / "avatar-preview.mp4"
        final.write_bytes(b"local-corrected-video")
        return final
    monkeypatch.setattr("backlot.studio_composition.compose_avatar", compose)
    return queue, project, original, original_work, calls, audio, avatar, cues


def freeze(source):
    return prepare(source[0], source[2]["job_id"], {"emphasis_index": 0, "footnote": ""})


def caption_freeze(source, monkeypatch):
    monkeypatch.setattr(recompose, "_require_caption_style", lambda: None)
    return prepare(source[0], source[2]["job_id"], caption_style="clear-v2")


def resign(request):
    core = {k: v for k, v in request.items() if k not in {"request_sha256", "render_id"}}
    request["request_sha256"] = fingerprint(core)
    request["render_id"] = recompose._prefix(request["contract"]) + request["request_sha256"][:20]
    return request


def test_original_inputs_only_allow_footnote_and_same_patch_is_idempotent(source):
    q, project, original, work, calls, audio, avatar, cues = source
    frozen = freeze(source)
    assert frozen["contract"] == "investment-footnote-local-v1"
    assert frozen["render_id"].startswith("local-footnote-")
    assert prepare(q, original["job_id"], {"emphasis_index": 0, "footnote": ""}) == frozen
    first, second = submit(q, frozen), submit(q, frozen)
    assert first["job_id"] == second["job_id"] and first["status"] == "paused"
    assert q.claim_next("old-worker") is None
    before = {path: sha(path) for path in (audio, avatar, project / "renders/studio-2/props.json")}
    result = ProductionQueueWorker(q, q.projects_root, worker_id="local", lease_seconds=7200).run_local_recompose(first["job_id"])
    assert result["status"] == "completed" and result["result"]["work_id"] == work["work_id"]
    assert result["result"]["cloud_calls"] == 0 and len(calls) == 1
    d, a, wav, duration, seen_cues = calls[0]
    assert d["input"]["investment"]["emphasis"][0]["footnote"] == ""
    assert (a, wav, duration, seen_cues) == (avatar, audio, 3, cues)
    assert all(sha(path) == digest for path, digest in before.items())
    assert len(WorkCatalog(q.projects_root).get(work["work_id"])["versions"]) == 2
    assert q.get(original["job_id"])["status"] == "completed"
    with pytest.raises(WorkError): prepare(q, original["job_id"], {"emphasis_index": 0, "text": "改稿"})


def test_local_claim_cannot_bypass_global_lane_other_kind_or_duplicate_owner(source):
    q, project, *_ = source
    local = submit(q, freeze(source))
    unrelated = q.submit(project_id=project.name, kind="review_preview", source="codex", priority="normal", parent_job_id="other", frozen_request={})
    q.claim_next("normal")
    with pytest.raises(ProductionQueueConflict, match="已有执行"):
        q.claim_local_recompose(local["job_id"], "local")
    with pytest.raises(ProductionQueueConflict, match="只能领取"):
        q.claim_local_recompose(unrelated["job_id"], "local")
    q.finish(unrelated["job_id"], "normal", status="completed", stage="done")
    q.claim_local_recompose(local["job_id"], "one")
    with pytest.raises(ProductionQueueConflict, match="不能重复"):
        q.claim_local_recompose(local["job_id"], "two")


def test_source_change_is_rejected_before_local_composition(source):
    q, project, original, work, calls, audio, *_ = source
    frozen = freeze(source)
    job = submit(q, frozen)
    audio.write_bytes(b"changed")
    result = ProductionQueueWorker(q, q.projects_root, worker_id="local").run_local_recompose(job["job_id"])
    assert result["status"] == "failed" and "SHA" in result["stage"] and not calls


@pytest.mark.parametrize("change", ["cues", "audio", "duration", "avatar"])
def test_recomputed_request_fingerprint_cannot_replace_actual_sources(source, change):
    q = source[0]
    frozen = freeze(source)
    if change == "cues": frozen["cues"][0]["startMs"] = 1
    elif change == "audio": frozen["prepared"]["audio_path"] = str(source[6])
    elif change == "duration": frozen["prepared"]["duration"] = 2
    else: frozen["avatar_path"] = str(source[5])
    core = {k: v for k, v in frozen.items() if k not in {"request_sha256", "render_id"}}
    frozen["request_sha256"] = fingerprint(core)
    frozen["render_id"] = "local-footnote-" + frozen["request_sha256"][:20]
    with pytest.raises(WorkError, match="不能改换音频"): validate(q, frozen)


def test_registration_failure_recovers_original_local_render_without_recomposing(source, monkeypatch):
    q, _, _, work, calls, *_ = source
    job = submit(q, freeze(source))
    register = WorkCatalog.register
    attempts = []
    def once(self, *args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1: raise WorkError("临时登记失败", "unavailable")
        return register(self, *args, **kwargs)
    monkeypatch.setattr(WorkCatalog, "register", once)
    worker = ProductionQueueWorker(q, q.projects_root, worker_id="local")
    failed = worker.run_local_recompose(job["job_id"])
    assert failed["status"] == "failed" and failed["retryable"] and len(calls) == 1
    with pytest.raises(ProductionQueueConflict): q.retry(job["job_id"])
    result = worker.run_local_recompose(job["job_id"])
    assert result["status"] == "completed" and len(calls) == 1
    assert len(WorkCatalog(q.projects_root).get(work["work_id"])["versions"]) == 2


def test_caption_refresh_preserves_all_source_props_and_clock_in_same_work_without_sdk(source, monkeypatch):
    q, project, original, work, calls, audio, avatar, cues = source
    original_draft = q.get(original["job_id"], include_private=True)["frozen_request"]["draft"]
    frozen = caption_freeze(source, monkeypatch)
    assert frozen == prepare(q, original["job_id"], caption_style="clear-v2")
    assert frozen["contract"] == "investment-caption-style-local-v2"
    assert frozen["patch"] == {"caption_style": "clear-v2"}
    assert frozen["render_id"].startswith("local-caption-clear-")
    assert frozen["draft"] == original_draft
    assert frozen["request_sha256"] != freeze(source)["request_sha256"]
    before_props = json.loads((project / "renders/studio-2/props.json").read_text(encoding="utf-8"))
    job = submit(q, frozen)
    assert submit(q, frozen)["job_id"] == job["job_id"]
    result = ProductionQueueWorker(q, q.projects_root, worker_id="local").run_local_recompose(job["job_id"])
    assert result["status"] == "completed" and result["result"]["cloud_calls"] == 0
    assert result["result"]["work_id"] == work["work_id"] and len(calls) == 1
    draft, seen_avatar, seen_audio, duration, seen_cues = calls[0]
    assert draft == original_draft
    assert (seen_avatar, seen_audio, duration, seen_cues) == (avatar, audio, 3, cues)
    after_props, _ = render_props(draft, duration, seen_cues)
    assert after_props == before_props
    assert draft["input"]["investment"]["emphasis"][0]["footnote"] == "制作说明"
    receipt = json.loads((project / "renders" / frozen["render_id"] / "local-recompose-result.json").read_text(encoding="utf-8"))
    assert receipt["contract"] == frozen["contract"] and receipt["request_sha256"] == frozen["request_sha256"]
    assert receipt["provider_jobs"] == [] and receipt["cloud_calls"] == 0
    assert len(WorkCatalog(q.projects_root).get(work["work_id"])["versions"]) == 2


@pytest.mark.parametrize("style,patch", [("arbitrary-css", None), ("clear-v2", {"emphasis_index": 0, "footnote": ""})])
def test_caption_style_is_fixed_and_cannot_be_combined_with_footnote(source, style, patch):
    with pytest.raises(WorkError, match="仅支持clear-v2"):
        prepare(source[0], source[2]["job_id"], patch, caption_style=style)


def test_caption_style_requires_layout_marker_before_prepare(source, monkeypatch):
    monkeypatch.setattr(recompose, "read_json", lambda path: {"caption": {"styleId": "other"}})
    with pytest.raises(WorkError, match="尚未冻结clear-v2"):
        prepare(source[0], source[2]["job_id"], caption_style="clear-v2")


@pytest.mark.parametrize("change", ["patch", "draft", "cues", "duration"])
def test_caption_request_cannot_self_sign_changes_to_text_clock_or_extra_style(source, monkeypatch, change):
    frozen = caption_freeze(source, monkeypatch)
    if change == "patch": frozen["patch"]["css"] = {"fontSize": 90}
    elif change == "draft": frozen["draft"]["text"] = "改稿"
    elif change == "cues": frozen["cues"][0]["startMs"] = 10
    else: frozen["prepared"]["duration"] = 2
    with pytest.raises(WorkError): validate(source[0], resign(frozen))


@pytest.mark.parametrize("caption", [False, True])
def test_pending_request_never_switches_frozen_renderer(source, monkeypatch, caption):
    frozen = caption_freeze(source, monkeypatch) if caption else freeze(source)
    monkeypatch.setattr(recompose, "_runtime", lambda: {"changed-renderer": "new-sha"})
    with pytest.raises(WorkError, match="模板源码已变化"): submit(source[0], frozen)
    assert source[4] == []


def test_legacy_success_receipt_recovers_registration_after_runtime_change_without_render(source, monkeypatch):
    q, project, _, work, calls, *_ = source
    frozen = freeze(source)
    job = submit(q, frozen)
    register = WorkCatalog.register
    monkeypatch.setattr(WorkCatalog, "register", lambda *a, **k: (_ for _ in ()).throw(WorkError("登记暂不可用", "unavailable")))
    worker = ProductionQueueWorker(q, q.projects_root, worker_id="local")
    assert worker.run_local_recompose(job["job_id"])["status"] == "failed"
    receipt_path = project / "renders" / frozen["render_id"] / "local-recompose-result.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("contract")  # Previously issued v1 receipts had no contract field.
    atomic_private(receipt_path, receipt)
    monkeypatch.setattr(WorkCatalog, "register", register)
    monkeypatch.setattr(recompose, "_runtime", lambda: {"changed-renderer": "new-sha"})
    assert validate(q, frozen) == project
    recovered = worker.run_local_recompose(job["job_id"])
    assert recovered["status"] == "completed" and len(calls) == 1
    assert recovered["result"]["work_id"] == work["work_id"]
    assert submit(q, frozen)["job_id"] == job["job_id"]
    (project / "renders" / frozen["render_id"] / "avatar-preview.mp4").write_bytes(b"tampered")
    with pytest.raises(WorkError, match="已有本地修正版发生变化"): validate(q, frozen)
