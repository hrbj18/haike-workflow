"""Versioned local v4 contract: real queue, fake extraction/composition."""
from copy import deepcopy
import json
from pathlib import Path
import wave

import pytest
from PIL import Image

from backlot import studio_investment_source_art_v4 as art
from backlot.production_queue import ProductionQueue, ProductionQueueConflict
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import Studio, atomic_private
from backlot.work_catalog import WorkCatalog, WorkError, sha
from backlot.studio_composition import compose_avatar as native_compose_avatar


@pytest.fixture
def source(tmp_path, monkeypatch):
    video = tmp_path / "original.mp4"; video.write_bytes(b"original-video-and-AAC")
    scene = tmp_path / "company-interaction.mp4"; scene.write_bytes(b"authorized-company-interaction")
    background = tmp_path / "background.png"; Image.new("RGB", (32, 48), "ivory").save(background)
    cue_file, word_file, config_file = (tmp_path / name for name in ("cues.json", "words.json", "config.json"))
    cues = [{"text": "今天收现金", "startMs": 200, "endMs": 1400, "source_video_sha256": sha(video)},
            {"text": "点击下方链接", "startMs": 1800, "endMs": 2900, "source_video_sha256": sha(video)}]
    words = [{"text": text, "startMs": start, "endMs": end, "source_video_sha256": sha(video), "raw_word_indices": [i]}
             for i, (text, start, end) in enumerate((("今天", 200, 600), ("收现金", 650, 1400), ("点击", 1800, 2000), ("下方链接", 2100, 2900)))]
    config = {"variant": "art-v4", "direction": "documentary", "background_path": None, "background_sha256": None,
        "portrait_framing": "medium-9x16", "highlights": ["现金"],
        "chapters": [{"kind": "hook", "fromCue": 0, "toCue": 0, "heading": ["今天收现金"], "deck": "", "points": []},
                     {"kind": "cta", "fromCue": 1, "toCue": 1, "heading": ["了解合作方案"], "deck": "社区AI服务", "points": []}],
        "phrase_highlights": [{"text": "收现金", "fromWord": 1, "toWord": 1}],
        "scenes": [{"id": "company-interaction", "path": str(scene.resolve()), "sha256": sha(scene), "kind": "video",
                    "fromCue": 0, "toCue": 0, "offset": .5, "fit": "contain", "source_label": "公司产品互动素材"}]}
    for path, value in ((cue_file, cues), (word_file, words), (config_file, config)): atomic_private(path, value)
    queue = ProductionQueue(tmp_path / ".backlot/queue.sqlite3", tmp_path / "projects")
    monkeypatch.setattr(art, "_runtime", lambda: {"test-v4-runtime": "v1"})
    monkeypatch.setattr(art, "media_probe", lambda path: {"duration": 3, "video": {"width": 864, "height": 1536, "duration": "3"}, "audio": {"codec_name": "aac"}})
    extracts = []
    def extract(video, target):
        extracts.append(1)
        with wave.open(str(target), "wb") as stream:
            stream.setparams((1, 2, 24000, 0, "NONE", "not compressed")); stream.writeframes(b"\xd0\x07" * 72000)
    monkeypatch.setattr(art.base, "_extract_audio", extract)
    monkeypatch.setattr("backlot.work_catalog.probe", lambda path: {"duration": 3, "width": 1080, "height": 1920, "has_audio": True})
    def forbidden(*args, **kwargs): pytest.fail("v4 original-source contract must never construct an SDK")
    monkeypatch.setattr(Studio, "client", forbidden); monkeypatch.setattr("backlot.studio.sdk_type", forbidden)
    calls = []
    def compose(folder, draft, video, audio, duration, actual_cues, *, art_direction):
        calls.append(deepcopy(art_direction))
        with wave.open(str(audio), "rb") as stream: assert stream.readframes(1) == b"\xd0\x07"
        atomic_private(folder / "props.json", {"duration": duration, "avatarSrc": "avatar.mp4", "audioSrc": "narration.wav",
            "brand": draft["input"]["investment"]["brand"], "captions": actual_cues, "art": art.props_art(art_direction)})
        output = folder / "avatar-preview.mp4"; output.write_bytes(b"v4-fake-complete-output"); return output
    monkeypatch.setattr("backlot.studio_composition.compose_avatar", compose)
    return {"queue": queue, "video": video, "scene": scene, "background": background, "cues": cue_file,
            "words": word_file, "config_file": config_file, "config": config, "calls": calls, "extracts": extracts}


def freeze(source):
    return art.prepare(source["queue"], source["video"], source["cues"], source["words"], source["config_file"], title="v4艺术测试", brand="海客AI社区服务站")


def resign(request):
    core = {k: v for k, v in request.items() if k not in {"request_sha256", "render_id"}}
    request["request_sha256"] = art.fingerprint(core); request["render_id"] = art.PREFIX + request["request_sha256"][:20]
    return request


def test_v4_import_real_clock_scene_and_code_background_is_idempotent(source):
    request = freeze(source)
    assert freeze(source) == request and len(source["extracts"]) == 1
    assert request["contract"] == "investment-source-video-art-v4" and request["render_id"].startswith("local-source-art-v4-")
    art_config = request["art_direction"]
    assert art_config["background_path"] is None and "background" not in request["origins"]
    assert not any("art-background.png" in path for path in request["sources"])
    assert art_config["phrase_highlights"] == [{"text": "收现金", "fromWord": 1, "toWord": 1, "startMs": 650, "endMs": 1400}]
    assert art_config["scenes"][0]["start"] == .2 and art_config["scenes"][0]["end"] == 1.4
    assert sha(art_config["scenes"][0]["path"]) == sha(source["scene"])
    assert all(set(w) == {"text", "startMs", "endMs", "timestampMs", "confidence"} for w in art_config["word_cues"])
    props = art.props_art(art_config)
    assert set(props) == {"direction", "backgroundSrc", "chapters", "highlights", "portraitFraming", "wordCues", "phraseHighlights", "scenes"}
    assert props["backgroundSrc"] is None and set(props["scenes"][0]) == {"id", "src", "kind", "start", "end", "offset", "fit", "sourceLabel"}


def test_v4_registered_worker_is_paused_zero_sdk_unapproved_and_respects_lane(source):
    q = source["queue"]; request = freeze(source); job = art.submit(q, request)
    assert job["status"] == "paused" and art.submit(q, request)["job_id"] == job["job_id"] and q.claim_next("legacy") is None
    other = q.submit(project_id=request["project_id"], kind="review_preview", source="codex", priority="normal", parent_job_id="other", frozen_request={})
    q.claim_next("other")
    with pytest.raises(ProductionQueueConflict, match="已有执行"): ProductionQueueWorker(q, q.projects_root).run_local_recompose(job["job_id"])
    q.finish(other["job_id"], "other", status="completed", stage="done")
    result = ProductionQueueWorker(q, q.projects_root).run_local_recompose(job["job_id"])
    assert result["status"] == "completed" and result["result"]["cloud_calls"] == 0 and len(source["calls"]) == 1
    work = WorkCatalog(q.projects_root).get(result["result"]["work_id"])
    assert work["final_version_id"] is None and work["targets"] == [] and work["confirmations"] == []


def test_optional_scenes_and_explicit_phrase_groups_default_to_empty(source):
    config = deepcopy(source["config"])
    config.pop("scenes"); config.pop("phrase_highlights")
    atomic_private(source["config_file"], config)
    request = freeze(source)
    assert request["art_direction"]["scenes"] == [] and request["art_direction"]["phrase_highlights"] == []


@pytest.mark.parametrize("direction", sorted(art.DIRECTIONS))
def test_six_directions_preserve_distinct_background_contract(source, direction):
    config = deepcopy(source["config"]); config["direction"] = direction
    if direction in art.base.DIRECTIONS:
        config.update(background_path=str(source["background"].resolve()), background_sha256=sha(source["background"]))
    atomic_private(source["config_file"], config)
    request = freeze(source)
    assert request["art_direction"]["direction"] == direction
    assert art.props_art(request["art_direction"])["backgroundSrc"] == ("art-background.png" if direction in art.base.DIRECTIONS else None)


@pytest.mark.parametrize("change", ["cue", "offset", "short", "overlap", "fit", "sha", "word_sha", "word_time", "missing_words", "phrase", "old_null", "half_null"])
def test_reject_invalid_scene_word_clock_and_background_contract(source, monkeypatch, change):
    config = deepcopy(source["config"])
    if change == "cue": config["scenes"][0]["toCue"] = 3
    elif change == "offset": config["scenes"][0]["offset"] = -1
    elif change == "short": config["scenes"][0]["offset"] = 2
    elif change == "overlap":
        duplicate = deepcopy(config["scenes"][0]); duplicate["id"] = "duplicate"; config["scenes"].append(duplicate)
    elif change == "fit": config["scenes"][0]["fit"] = "arbitrary-css"
    elif change == "sha": config["scenes"][0]["sha256"] = "f" * 64
    elif change in {"word_sha", "word_time", "missing_words"}:
        words = read(source["words"])
        if change == "word_sha": words[0]["source_video_sha256"] = "a" * 64
        elif change == "word_time": words[1]["startMs"] = 300
        else: words.pop()
        atomic_private(source["words"], words)
    elif change == "phrase": config["phrase_highlights"][0]["text"] = "伪造词组"
    elif change == "old_null": config["direction"] = "blue-editorial"
    else: config["background_sha256"] = "a" * 64
    atomic_private(source["config_file"], config)
    with pytest.raises(WorkError): freeze(source)
    assert not source["calls"]


def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("change", ["words", "scenes", "gain", "publication"])
def test_resigned_request_cannot_replace_frozen_v4_inputs(source, change):
    request = freeze(source)
    if change == "words": request["art_direction"]["word_cues"][0]["startMs"] += 10
    elif change == "scenes": request["art_direction"]["scenes"][0]["offset"] += .1
    elif change == "gain": request["audio_policy"]["final_gain_db"] = -5
    else: request["publication"] = True
    with pytest.raises(WorkError): art.validate(source["queue"], resign(request))


def test_v4_registration_retry_preserves_output_after_runtime_maintenance(source, monkeypatch):
    q = source["queue"]; request = freeze(source); job = art.submit(q, request)
    register, calls = WorkCatalog.register, []
    def once(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1: raise WorkError("登记暂时失败", "unavailable")
        return register(self, *args, **kwargs)
    monkeypatch.setattr(WorkCatalog, "register", once)
    worker = ProductionQueueWorker(q, q.projects_root)
    assert worker.run_local_recompose(job["job_id"])["retryable"]
    monkeypatch.setattr(art, "_runtime", lambda: {"test-v4-runtime": "v2"})
    assert worker.run_local_recompose(job["job_id"])["status"] == "completed" and len(source["calls"]) == 1


def test_pending_v4_runtime_change_blocks_and_source_file_change_stops_before_render(source, monkeypatch):
    request = freeze(source); q = source["queue"]
    monkeypatch.setattr(art, "_runtime", lambda: {"test-v4-runtime": "v2"})
    with pytest.raises(WorkError, match="源码已变化"): art.validate(q, request)


@pytest.mark.parametrize("code_background", [True, False])
def test_native_v4_composer_freezes_props_scene_components_and_single_gain(source, monkeypatch, code_background):
    from types import SimpleNamespace
    from backlot import studio_composition as composition
    from tools.video.video_compose import VideoCompose
    if not code_background:
        config = deepcopy(source["config"])
        config.update(direction="blue-editorial", background_path=str(source["background"].resolve()),
                      background_sha256=sha(source["background"]))
        atomic_private(source["config_file"], config)
    request = freeze(source)
    folder = source["queue"].projects_root / request["project_id"] / "renders/native-v4-test"
    folder.mkdir(parents=True)
    renders, gains = [], []
    def render(self, value):
        renders.append(deepcopy(value))
        Path(value["output_path"]).write_bytes(b"native-fake-v4-render")
        return SimpleNamespace(success=True)
    def mux(ffmpeg, raw, audio, output, duration, **kwargs):
        gains.append((duration, kwargs)); Path(output).write_bytes(b"native-fake-v4-mux")
    def forbidden(*args, **kwargs): pytest.fail("v4 composition must not use legacy investment render_props")
    monkeypatch.setattr(VideoCompose, "execute", render)
    monkeypatch.setattr("lib.ffmpeg_locator.resolve_ffmpeg_pair", lambda: ("fake-ffmpeg", "fake-probe"))
    monkeypatch.setattr(composition.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(composition, "media_probe", lambda path: {"duration": 3, "video": {"width": 1080, "height": 1920}, "audio": {"codec_name": "aac"}})
    monkeypatch.setattr(composition, "mux_avatar_audio", mux)
    monkeypatch.setattr("backlot.studio_investment.render_props", forbidden)
    output = native_compose_avatar(folder, request["draft"], Path(request["avatar_path"]),
        Path(request["prepared"]["audio_path"]), 3, request["cues"], art_direction=request["art_direction"])
    assert output == folder / "avatar-preview.mp4" and output.is_file()
    actual = read(folder / "props.json")
    assert set(actual) == {"duration", "avatarSrc", "audioSrc", "brand", "captions", "art"}
    assert actual["art"] == art.props_art(request["art_direction"]) and len(actual["art"]) == 8
    assert actual["brand"] == "海客AI社区服务站" and actual["captions"] == request["cues"]
    assert actual["art"]["wordCues"] == request["art_direction"]["word_cues"]
    assert actual["art"]["backgroundSrc"] == (None if code_background else "art-background.png")
    assert (folder / "public/art-background.png").exists() is not code_background
    if not code_background: assert sha(folder / "public/art-background.png") == sha(source["background"])
    scene = request["art_direction"]["scenes"][0]
    assert sha(folder / "public" / scene["source_name"]) == scene["sha256"] == sha(source["scene"])
    assert actual["art"]["scenes"][0]["sourceLabel"] == "公司产品互动素材"
    assert "sha256" not in actual["art"]["scenes"][0] and "path" not in actual["art"]["scenes"][0]
    template = Path(art.__file__).resolve().parents[1] / "templates/avatar-investment-a-v6-art-v4"
    for path in [*template.glob("*.tsx"), template / "types.ts", template / "layout.json"]:
        assert sha(folder / path.name) == sha(path)
    assert read(folder / "art-scene-plan.json") == request["art_direction"]
    assert renders[0]["edit_decisions"]["bespoke"]["composition_id"] == "HaikeInvestmentArtV4"
    assert gains == [(3, {"linear_gain_db": -2.5})] and not (folder / "investment-triggers.json").exists()
