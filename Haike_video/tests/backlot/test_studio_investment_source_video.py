"""Real durable queue/worker with fake media import and fake composition."""
from copy import deepcopy
import json
import wave

import pytest
from PIL import Image

from backlot import studio_investment_source_video as art
from backlot.production_queue import ProductionQueue, ProductionQueueConflict
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import Studio, atomic_private
from backlot.work_catalog import WorkCatalog, WorkError, sha
from backlot.studio_composition import compose_avatar as native_compose_avatar


@pytest.fixture
def local_source(tmp_path, monkeypatch):
    original = tmp_path / "original.mp4"
    original.write_bytes(b"original-avatar-and-AAC")
    background = tmp_path / "art.png"
    Image.new("RGB", (32, 48), "ivory").save(background)
    cues = tmp_path / "cues.json"
    atomic_private(cues, [{"text": "今天收现金", "startMs": 200, "endMs": 1400,
        "source_video_sha256": sha(original), "confidence": .99},
        {"text": "点击下方链接", "startMs": 1800, "endMs": 2900,
         "source_video_sha256": sha(original)}])
    config = {"direction": "community-showcase", "background_path": str(background.resolve()),
        "background_sha256": sha(background), "portrait_framing": "medium-9x16", "highlights": ["现金"],
        "chapters": [{"kind": "hook", "fromCue": 0, "toCue": 0, "heading": ["今天收现金"], "deck": "", "points": []},
                     {"kind": "cta", "fromCue": 1, "toCue": 1, "heading": ["了解合作方案"], "deck": "社区AI服务", "points": ["服务社区"]}]}
    config_file = tmp_path / "art-config.json"
    atomic_private(config_file, config)
    queue = ProductionQueue(tmp_path / ".backlot/queue.sqlite3", tmp_path / "projects")
    monkeypatch.setattr(art, "_runtime", lambda: {"test-runtime": "v1"})
    monkeypatch.setattr(art, "media_probe", lambda path: {"duration": 3, "video": {"width": 864, "height": 1536},
                                                          "audio": {"codec_name": "aac"}})
    extracts = []
    def extract(video, target):
        extracts.append((video, target))
        with wave.open(str(target), "wb") as stream:
            stream.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            stream.writeframes(b"\xd0\x07" * 72000)
    monkeypatch.setattr(art, "_extract_audio", extract)
    monkeypatch.setattr("backlot.work_catalog.probe", lambda path: {"duration": 3, "width": 1080, "height": 1920, "has_audio": True})
    def forbidden(*args, **kwargs): pytest.fail("Original-source art tests must not construct an SDK")
    monkeypatch.setattr(Studio, "client", forbidden)
    monkeypatch.setattr("backlot.studio.sdk_type", forbidden)
    calls = []
    def compose(folder, draft, video, audio, duration, actual_cues, *, art_direction):
        calls.append((deepcopy(draft), video, audio, duration, deepcopy(actual_cues), deepcopy(art_direction)))
        # Extraction has not applied the final -2.5 dB gain.
        with wave.open(str(audio), "rb") as stream: assert stream.readframes(1) == b"\xd0\x07"
        atomic_private(folder / "props.json", {"duration": duration, "avatarSrc": "avatar.mp4", "audioSrc": "narration.wav",
            "brand": draft["input"]["investment"]["brand"], "captions": actual_cues,
            "art": {"direction": art_direction["direction"], "backgroundSrc": "art-background.png",
                    "chapters": art_direction["chapters"], "highlights": art_direction["highlights"],
                    "portraitFraming": art_direction["portrait_framing"]}})
        output = folder / "avatar-preview.mp4"
        output.write_bytes(b"new-art-test-mp4")
        return output
    monkeypatch.setattr("backlot.studio_composition.compose_avatar", compose)
    return queue, original, cues, config_file, config, calls, extracts


def prepare(local_source):
    queue, video, cues, config, *_ = local_source
    return art.prepare(queue, video, cues, config, title="社区AI招商 · 艺术测试", brand="海客AI社区服务站")


def resign(request):
    core = {k: v for k, v in request.items() if k not in {"request_sha256", "render_id"}}
    request["request_sha256"] = art.fingerprint(core)
    request["render_id"] = art.PREFIX + request["request_sha256"][:20]
    return request


def test_import_is_idempotent_and_chapters_cover_original_clock_without_sdk(local_source):
    q, original, _, _, _, calls, extracts = local_source
    request = prepare(local_source)
    assert prepare(local_source) == request and len(extracts) == 1 and not calls
    assert request["development_test"] and request["publication"] is False and request["cloud_calls"] == 0
    assert sha(request["avatar_path"]) == sha(original)
    assert request["audio_policy"] == art.AUDIO_POLICY
    assert all(set(c) == {"text", "startMs", "endMs", "timestampMs", "confidence"} for c in request["cues"])
    chapters = request["art_direction"]["chapters"]
    assert (chapters[0]["start"], chapters[0]["end"], chapters[1]["start"], chapters[1]["end"]) == (0, 1.8, 1.8, 3)
    assert chapters[0]["fromCue"] == chapters[0]["toCue"] == 0
    assert chapters[0]["cueStartMs"] == 200 and chapters[1]["cueEndMs"] == 2900


def test_registered_worker_composes_only_once_and_registers_unapproved_test(local_source):
    q, _, _, _, _, calls, _ = local_source
    request = prepare(local_source)
    first = art.submit(q, request)
    assert first["status"] == "paused" and art.submit(q, request)["job_id"] == first["job_id"]
    assert q.claim_next("legacy-worker") is None
    worker = ProductionQueueWorker(q, q.projects_root, worker_id="art-test-worker")
    result = worker.run_local_recompose(first["job_id"])
    assert result["status"] == "completed" and result["result"]["cloud_calls"] == 0 and len(calls) == 1
    work = WorkCatalog(q.projects_root).get(result["result"]["work_id"])
    assert work["final_version_id"] is None and work["targets"] == [] and work["confirmations"] == []
    project = q.projects_root / request["project_id"]
    receipt = json.loads((project / "renders" / request["render_id"] / "source-video-art-result.json").read_text(encoding="utf-8"))
    assert receipt["scene_plan_sha256"] and receipt["props_sha256"] and receipt["sources_unchanged"]
    art.validate(q, request)


def test_source_art_worker_respects_existing_global_lane(local_source):
    q = local_source[0]
    request = prepare(local_source)
    task = art.submit(q, request)
    unrelated = q.submit(project_id=request["project_id"], kind="review_preview", source="codex", priority="normal",
                         parent_job_id="unrelated", frozen_request={})
    assert q.claim_next("other")["job_id"] == unrelated["job_id"]
    with pytest.raises(ProductionQueueConflict, match="已有执行"):
        ProductionQueueWorker(q, q.projects_root).run_local_recompose(task["job_id"])
    assert q.get(task["job_id"])["status"] == "paused" and q.get(task["job_id"])["attempt_count"] == 0


def test_imported_source_change_stops_before_composition(local_source):
    q, _, _, _, _, calls, _ = local_source
    request = prepare(local_source)
    task = art.submit(q, request)
    from pathlib import Path
    Path(request["avatar_path"]).write_bytes(b"changed")
    result = ProductionQueueWorker(q, q.projects_root).run_local_recompose(task["job_id"])
    assert result["status"] == "failed" and "SHA" in result["stage"] and not calls


@pytest.mark.parametrize("change", ["cues", "duration", "art", "audio", "publication", "gain"])
def test_resigned_request_cannot_swap_frozen_sources_or_contract(local_source, change):
    q = local_source[0]
    request = prepare(local_source)
    if change == "cues": request["cues"][0]["startMs"] = 300
    elif change == "duration": request["prepared"]["duration"] = 2
    elif change == "art": request["art_direction"]["chapters"][0]["heading"] = ["捏造标题"]
    elif change == "audio": request["prepared"]["audio_path"] = request["avatar_path"]
    elif change == "publication": request["publication"] = True
    else: request["audio_policy"]["final_gain_db"] = -5
    with pytest.raises(WorkError): art.validate(q, resign(request))


def test_cached_result_survives_runtime_maintenance_without_new_render(local_source, monkeypatch):
    q, _, _, _, _, calls, _ = local_source
    request = prepare(local_source)
    task = art.submit(q, request)
    result = ProductionQueueWorker(q, q.projects_root).run_local_recompose(task["job_id"])
    assert result["status"] == "completed"
    monkeypatch.setattr(art, "_runtime", lambda: {"test-runtime": "v2"})
    art.validate(q, request)
    assert len(calls) == 1


def test_pending_result_rejects_runtime_change(local_source, monkeypatch):
    q = local_source[0]
    request = prepare(local_source)
    monkeypatch.setattr(art, "_runtime", lambda: {"test-runtime": "v2"})
    with pytest.raises(WorkError, match="源码已变化"): art.validate(q, request)


def test_registration_failure_recovers_same_render_without_recompose(local_source, monkeypatch):
    q, _, _, _, _, calls, _ = local_source
    request = prepare(local_source)
    task = art.submit(q, request)
    register, attempts = WorkCatalog.register, []
    def once(self, *args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1: raise WorkError("临时登记失败", "unavailable")
        return register(self, *args, **kwargs)
    monkeypatch.setattr(WorkCatalog, "register", once)
    worker = ProductionQueueWorker(q, q.projects_root)
    first = worker.run_local_recompose(task["job_id"])
    assert first["status"] == "failed" and first["retryable"] and len(calls) == 1
    final = worker.run_local_recompose(task["job_id"])
    assert final["status"] == "completed" and len(calls) == 1


def test_cue_cache_requires_matching_source_video_sha(local_source):
    q, video, cue_file, config_file, *_ = local_source
    cue_value = json.loads(cue_file.read_text(encoding="utf-8"))
    cue_value[1]["source_video_sha256"] = "a" * 64
    atomic_private(cue_file, cue_value)
    with pytest.raises(WorkError, match="原视频SHA"):
        art.prepare(q, video, cue_file, config_file, title="测试", brand="海客")


def test_semantic_caption_newlines_are_preserved_and_bounded():
    value = [{"text": "每个小区\n只放一个名额", "startMs": 200, "endMs": 1400}]
    assert art.normalize_cues(value, 3)[0]["text"] == value[0]["text"]
    for invalid in ("一\n二\n三", "单行字幕超出十四个汉字就应当拒绝", "不能\t有制表符"):
        value[0]["text"] = invalid
        with pytest.raises(WorkError, match="语义换行"): art.normalize_cues(value, 3)


def test_cached_result_rejects_changed_render_props(local_source):
    q = local_source[0]
    request = prepare(local_source)
    task = art.submit(q, request)
    assert ProductionQueueWorker(q, q.projects_root).run_local_recompose(task["job_id"])["status"] == "completed"
    folder = q.projects_root / request["project_id"] / "renders" / request["render_id"]
    props = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    props["captions"][0]["text"] = "伪造字幕"
    atomic_private(folder / "props.json", props)
    with pytest.raises(WorkError, match="props或分镜"): art.validate(q, request)


def test_worker_rejects_composer_brand_drift_before_registering(local_source, monkeypatch):
    from backlot import studio_composition as composition
    q = local_source[0]
    request = prepare(local_source)
    task = art.submit(q, request)
    compose = composition.compose_avatar
    def wrong_brand(folder, *args, **kwargs):
        output = compose(folder, *args, **kwargs)
        props = json.loads((folder / "props.json").read_text(encoding="utf-8"))
        props["brand"] = "另一品牌"
        atomic_private(folder / "props.json", props)
        return output
    monkeypatch.setattr(composition, "compose_avatar", wrong_brand)
    result = ProductionQueueWorker(q, q.projects_root).run_local_recompose(task["job_id"])
    assert result["status"] == "failed" and "冻结品牌" in result["stage"]
    assert WorkCatalog(q.projects_root).list(include_candidates=True) == []


@pytest.mark.parametrize("use_art", [True, False])
def test_actual_composer_routes_art_props_brand_and_gain_without_old_trigger_mix(local_source, monkeypatch, use_art):
    from pathlib import Path
    from types import SimpleNamespace
    from backlot import studio_composition as composition
    from tools.video.video_compose import VideoCompose
    request = prepare(local_source)
    q = local_source[0]
    folder = q.projects_root / request["project_id"] / "renders" / ("native-art-test" if use_art else "legacy-test")
    folder.mkdir(parents=True)
    rendered, mastered = [], []
    def render(self, value):
        rendered.append(deepcopy(value))
        Path(value["output_path"]).write_bytes(b"fake-render")
        return SimpleNamespace(success=True)
    def mux(ffmpeg, raw, audio, output, duration, **kwargs):
        mastered.append((duration, kwargs))
        Path(output).write_bytes(b"fake-mux")
    monkeypatch.setattr(VideoCompose, "execute", render)
    monkeypatch.setattr("lib.ffmpeg_locator.resolve_ffmpeg_pair", lambda: ("fake-ffmpeg", "fake-probe"))
    monkeypatch.setattr(composition.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(composition, "media_probe", lambda path: {"duration": 3, "video": {"width": 1080, "height": 1920}, "audio": {"codec_name": "aac"}})
    monkeypatch.setattr(composition, "mux_avatar_audio", mux)
    if use_art:
        def forbidden(*args, **kwargs): pytest.fail("Art composition must not call legacy semantic render_props")
        monkeypatch.setattr("backlot.studio_investment.render_props", forbidden)
    native_compose_avatar(folder, request["draft"], Path(request["avatar_path"]),
                          Path(request["prepared"]["audio_path"]), 3, request["cues"],
                          art_direction=request["art_direction"] if use_art else None)
    props = json.loads((folder / "props.json").read_text(encoding="utf-8"))
    renderer = rendered[0]["edit_decisions"]["bespoke"]
    if use_art:
        assert props["brand"] == request["draft"]["input"]["investment"]["brand"] == "海客AI社区服务站"
        assert props["art"]["direction"] == "community-showcase"
        assert props["art"]["chapters"] == request["art_direction"]["chapters"]
        assert props["art"]["portraitFraming"] == "medium-9x16"
        assert not {"investment", "events", "scenes"} & props.keys()
        assert renderer["composition_id"] == "HaikeInvestmentArtV3" and (folder / "art-scene-plan.json").is_file()
        assert sha(folder / "public/art-background.png") == request["art_direction"]["background_sha256"]
        assert mastered == [(3, {"linear_gain_db": -2.5})]
        assert not (folder / "investment-triggers.json").exists()
    else:
        assert "art" not in props and "investment" in props and (folder / "investment-triggers.json").is_file()
        assert renderer["composition_id"] == "HaikeInvestmentA6" and mastered == [(3, {})]
    assert props["captions"] == request["cues"]


@pytest.mark.parametrize("change", ["direction", "css", "overlap", "gap", "last", "heading", "points", "framing"])
def test_art_config_rejects_uncontrolled_layout_and_invalid_coverage(local_source, change):
    _, _, cue_file, _, value, *_ = local_source
    cues = art.normalize_cues(json.loads(cue_file.read_text(encoding="utf-8")), 3)
    value = deepcopy(value)
    if change == "direction": value["direction"] = "arbitrary"
    elif change == "css": value["css"] = {"position": "absolute"}
    elif change == "overlap": value["chapters"][1]["fromCue"] = 0
    elif change == "gap": value["chapters"][0]["fromCue"] = 1
    elif change == "last": value["chapters"] = value["chapters"][:1]
    elif change == "heading": value["chapters"][0]["heading"] = ["超长标题" * 5]
    elif change == "points": value["chapters"][0]["points"] = ["一", "二", "三", "四"]
    else: value["portrait_framing"] = "arbitrary"
    with pytest.raises(WorkError): art.normalize_art(value, cues, 3)
