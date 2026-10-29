"""Isolated EDL/queue contracts; fixture speech/media are never real reviews."""
from array import array
from copy import deepcopy
import math
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from backlot import studio_investment_full as full
from backlot import studio_investment_audio_v5 as sound
from backlot.production_queue import ProductionQueue, ProductionQueueConflict
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import Studio, atomic_private
from backlot.work_catalog import WorkCatalog, WorkError, read_json, sha


def _tone(path, seconds, rate=48000, channels=2, amplitude=3000):
    # Repeated 1/30-second complete cycles keep fixture generation inexpensive.
    cycle = array("h", [round(amplitude * math.sin(2 * math.pi * 300 * i / rate))
                        for i in range(rate // 30) for _ in range(channels)])
    data = cycle.tobytes() * round(seconds * 30)
    with wave.open(str(path), "wb") as stream:
        stream.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
        stream.writeframes(data)


@pytest.fixture
def sample(tmp_path_factory, monkeypatch):
    from PIL import Image
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    base = tmp_path_factory.mktemp("if")
    root = base / "rt"
    template = root / "templates" / full.TEMPLATE_FOLDER
    template.mkdir(parents=True)
    (template / "index.tsx").write_text("export const fixture=true;", encoding="utf-8")
    atomic_private(template / "layout.json", {"fixture": True})
    atomic_private(template / "video-template-spec.json", {"stage": "specification"})
    ffmpeg, _ = resolve_ffmpeg_pair()
    monkeypatch.setattr(full, "_root", lambda: root)
    monkeypatch.setattr(full, "_runtime", lambda: {**{str(p): sha(p) for p in full._template_files()},
        str(Path(sound.__file__).resolve()): sha(sound.__file__), str(Path(ffmpeg).resolve()): sha(ffmpeg)})
    video = base / "original.mp4"
    video.write_bytes(b"isolated-original-video-with-aac")
    cue_file, edits_file, board_file, plan_file = (base / name for name in ("cues.json", "edits.json", "board.json", "sound.json"))
    atomic_private(cue_file, {"source_video_sha256": sha(video), "timing_basis": "manual_reviewed",
        "evidence": "isolated generated fixtures only, not an actual transcript", "cues": [
            {"start": .5, "end": 3, "text": "社区AI超市"}, {"start": 4, "end": 8, "text": "AI数字员工"},
            {"start": 12, "end": 15, "text": "被删除的完整句"}, {"start": 16.04, "end": 18, "text": "门店体验"},
            {"start": 25, "end": 27, "text": "选品宣传客服"}, {"start": 33, "end": 34.5, "text": "点击咨询合作"}]})
    atomic_private(edits_file, {"version": "source-edits-v1", "source_video_sha256": sha(video),
        "source_cues_sha256": sha(cue_file), "fps": 30, "target_duration_in_frames": 900, "tail_hold_frames": 36,
        "segments": [{"id": "open", "source_start_frame": 0, "source_end_frame": 300, "fromCue": 0, "toCue": 1,
                      "reason": "isolated complete opening cues"},
                     {"id": "close", "source_start_frame": 480, "source_end_frame": 1044, "fromCue": 3, "toCue": 5,
                      "reason": "isolated complete final cues and CTA"}]})
    photos = [base / "photo-a.png", base / "photo-b.png"]
    for i, photo in enumerate(photos):
        Image.new("RGB", (20, 20), (i * 120, 80, 100)).save(photo)
    def chapter(identifier, start, end, kind):
        return {"id": identifier, "startFrame": start, "endFrame": end, "kind": kind,
                "heading": ["隔离测试标题"], "deck": "", "points": []}
    atomic_private(board_file, {"version": "investment-full-storyboard-v1", "chapters": [
        chapter("hook", 0, 240, "presenter"), chapter("proof", 240, 480, "media"),
        chapter("services", 480, 690, "graphic"), chapter("voice", 690, 810, "presenter"),
        chapter("cta", 810, 900, "graphic")], "shots": [
            {"id": f"photo-{i}", "path": str(photo), "sha256": sha(photo), "kind": "image",
             "startFrame": 240 + i * 120, "endFrame": 360 + i * 120, "sourceOffsetFrames": 0,
             "fit": "contain", "sourceLabel": "isolated generated color square",
             "evidence": {"scope": "fixture, no real store proof"}} for i, photo in enumerate(photos)],
        "graphics": [{"id": "service-list", "chapterId": "services", "kind": "list", "heading": "服务",
                      "items": ["选品", "宣传", "客服"], "sourceCueIndices": [4]},
                     {"id": "cta-offer", "chapterId": "cta", "kind": "offer", "heading": "咨询合作",
                      "items": ["点击咨询合作"], "sourceCueIndices": [5]}]})
    music, hit = base / "music.wav", base / "hit.wav"
    _tone(music, 30.2, amplitude=1500)
    _tone(hit, .2, amplitude=2500)
    atomic_private(plan_file, {"version": "sound-motion-v1", "mix_profile": "speech-led-v1",
        "music": {"path": str(music), "sha256": sha(music), "source_label": "isolated generated sine",
                  "offset": 0, "loop": False, "gain_db": -12, "fade_in": .05, "fade_out": .4},
        "assets": [{"id": "hit", "role": "impact", "path": str(hit), "sha256": sha(hit), "source_label": "isolated generated sine"}],
        "events": [{"id": "open", "asset_id": "hit", "anchor": {"type": "cue", "index": 0, "boundary": "start"},
                    "pattern": "single", "gain_db": -15}]})
    monkeypatch.setattr(full, "media_probe", lambda p: {"duration": 35,
        "video": {"duration": "35", "width": 1228, "height": 1536}, "audio": {"codec_name": "aac"}})
    extracts = []
    def extract(source, target):
        if not target.exists():
            extracts.append(source)
            _tone(target, 35, rate=24000, channels=1, amplitude=5000)
            atomic_private(target.parent / "source-audio-receipt.json", {"isolated": True})
        return full._pcm(target)
    monkeypatch.setattr(full, "_extract_audio", extract)
    originals = (full._sound_plan, sound.build_audio_master, full._verify_audio)
    def plan(raw, edit, board, *, imported=None):
        result = deepcopy(raw)
        for asset, name in [(result["music"], "music.wav"), *[(a, "sound-" + a["id"] + ".wav") for a in result["assets"]]]:
            asset.update(source_name=name, path=str(imported / name) if imported else asset["path"])
        result.update(duration=30, hits=[{"id": "open", "role": "impact", "timeMs": 500,
                      "startFrame": 15, "endFrame": 21, "strength": .1}])
        return result
    monkeypatch.setattr(full, "_sound_plan", plan)
    def master(folder, voice, duration, plan):
        output = folder / "mixed-master.wav"
        if not output.exists():
            _tone(output, 30, amplitude=1000)
            for name in ("audio-mix-plan.json", "audio-mix-receipt.json"):
                atomic_private(folder / name, {"isolated": True})
            for name in ("music-pre-duck.wav", "music-post-duck.wav"):
                (folder / name).write_bytes(b"isolated-audio-diagnostic")
        return {"path": str(output)}
    monkeypatch.setattr(sound, "build_audio_master", master)
    monkeypatch.setattr(full, "_verify_audio", lambda *a: {"isolated": True})
    def no_provider(*a, **kw):
        pytest.fail("full local contract must not create a provider SDK")
    monkeypatch.setattr(Studio, "client", no_provider)
    monkeypatch.setattr("backlot.studio.sdk_type", no_provider)
    monkeypatch.setattr("backlot.work_catalog.probe", lambda p: {"duration": 30, "width": 1440, "height": 1800, "has_audio": True})
    return {"root": root, "template": template, "video": video, "cues": cue_file, "edits": edits_file,
            "board": board_file, "plan": plan_file, "extracts": extracts, "originals": originals,
            "queue": ProductionQueue(base / ".backlot/q.sqlite3", base / "projects")}


def prepare(sample, **kwargs):
    options = {"template_number": 7, "palette_variant": "blue-beige", "title": "隔离完整招商"}
    options.update(kwargs)
    return full.prepare(sample["queue"], sample["video"], sample["cues"], sample["edits"], sample["board"], sample["plan"], **options)


def edit(sample):
    return full.normalize_edits(read_json(sample["edits"]), read_json(sample["cues"])["cues"],
        sha(sample["video"]), sha(sample["cues"]), 35)


def _add_presenter_track(sample):
    video = sample["board"].parent / "hq-presenter.mp4"
    video.write_bytes(b"isolated-high-quality-presenter")
    raw = read_json(sample["board"])
    raw["presenterVideo"] = {"path": str(video), "sha256": sha(video),
        "sourceLabel": "isolated separate presenter track", "evidence": "fixture only",
        "segments": [{"id": "hq-open", "startFrame": 0, "endFrame": 240, "sourceOffsetFrames": 0},
                     {"id": "hq-close", "startFrame": 690, "endFrame": 810, "sourceOffsetFrames": 240}]}
    return raw


def test_presenter_replacement_preserves_voice_clock_and_freezes_hq_source(sample):
    original = prepare(sample)
    raw = _add_presenter_track(sample)
    atomic_private(sample["board"], raw)
    updated = prepare(sample)
    assert updated["project_id"] != original["project_id"]
    for key in ("source_edits", "cues", "cue_map", "audio_policy", "render_profile"):
        assert updated[key] == original[key]
    props = full._props(updated)
    assert props["presenterVideo"]["src"] == "presenter-override.mp4"
    assert props["presenterVideo"]["segments"] == raw["presenterVideo"]["segments"]
    assert "path" not in props["presenterVideo"]
    folder = sample["queue"].projects_root / updated["project_id"] / "assets/investment-full"
    assert sha(folder / "presenter-override.mp4") == raw["presenterVideo"]["sha256"]
    first = sample["queue"].projects_root / original["project_id"] / "assets/investment-full"
    assert sha(folder / "edited-voice.wav") == sha(first / "edited-voice.wav")
    full.validate(sample["queue"], updated)
    (folder / "presenter-override.mp4").write_bytes(b"tampered")
    with pytest.raises(WorkError):
        full.validate(sample["queue"], updated)


@pytest.mark.parametrize("fault", ["gap", "cross-media", "missing", "repeat"])
def test_presenter_replacement_rejects_wrong_coverage_or_repeated_source(sample, fault):
    raw = _add_presenter_track(sample)
    segments = raw["presenterVideo"]["segments"]
    if fault == "gap": segments[0]["startFrame"] = 1
    elif fault == "cross-media": segments[0]["endFrame"] = 241
    elif fault == "missing": segments.pop()
    else: segments[1]["sourceOffsetFrames"] = 0
    with pytest.raises(WorkError):
        full.normalize_storyboard(raw, edit(sample))


def test_complete_edl_maps_real_cues_and_only_explicit_tail(sample):
    request = prepare(sample)
    props = full._props(request)
    assert (props["durationInFrames"], props["duration"], props["width"], props["height"]) == (900, 30, 1440, 1800)
    assert props["contentEndFrame"] == 864 and props["tailHoldFrames"] == 36
    assert props["sourceEdits"][1] == {"id": "close", "sourceStartFrame": 480, "sourceEndFrame": 1044, "startFrame": 300, "endFrame": 864}
    assert request["cue_map"][2]["sourceCueIndex"] == 3
    assert props["cues"][2]["start"] == pytest.approx(10.04)
    assert props["cues"][2]["confidence"] is None and props["cues"][2]["timestampMs"] is None
    assert props["shots"][0]["src"] == "scene-00-photo-0.png"
    assert "path" not in props["shots"][0] and "evidence" not in props["shots"][0]
    assert request["render_profile"]["video_bitrate"] == "20M" and request["render_profile"]["crf"] is None
    folder = sample["queue"].projects_root / request["project_id"] / "assets/investment-full"
    pcm, count = full._pcm(folder / "edited-voice.wav")
    assert count == 720000 and pcm[-36 * 800 * 2:] == b"\0" * (36 * 800 * 2)
    assert read_json(folder / "voice-edit-receipt.json")["source_cap_zero_samples"] == 0
    assert prepare(sample) == request and len(sample["extracts"]) == 1
    atomic_private(sample["template"] / "video-template-spec.json", {"stage": "ready", "postrender": True})
    assert full.validate(sample["queue"], request)


def test_edge_masks_preserve_selected_samples_and_record_both_clocks():
    cues = [{"start": .1, "end": 10.04, "text": "保留首句"}, {"start": 10.04, "end": 15.04, "text": "删除完整句"},
            {"start": 15.04, "end": 34.8, "text": "保留末句"}]
    raw = {"version": "source-edits-v1", "source_video_sha256": "a", "source_cues_sha256": "b", "fps": 30,
        "target_duration_in_frames": 900, "tail_hold_frames": 5, "segments": [
            {"id": "first", "source_start_frame": 0, "source_end_frame": 302, "fromCue": 0, "toCue": 0, "reason": "keep selected cue"},
            {"id": "last", "source_start_frame": 451, "source_end_frame": 1044, "fromCue": 2, "toCue": 2, "reason": "keep full CTA"}]}
    mapped = full.normalize_edits(raw, cues, "a", "b", 35)
    data = b"\x34\x12" * (35 * 24000)
    output, receipt = full.edited_pcm(data, mapped)
    assert len(receipt["edge_zero_intervals"]) == 2
    assert receipt["edge_zero_samples"] == 800
    assert mapped["cues"][1]["start"] == pytest.approx(302 / 30 + 15.04 - 451 / 30)
    for mask in receipt["edge_zero_intervals"]:
        a, b = mask["targetStartSample"] * 2, mask["targetEndSample"] * 2
        assert output[a:b] == b"\0" * (b - a)
        assert mask["sourceCueIndex"] == 1 and mask["reason"]
    # Whole selected sample intervals survive unchanged, excluding only the deleted neighbor.
    end_first = math.ceil(10.04 * 24000)
    assert output[2400 * 2:end_first * 2] == data[2400 * 2:end_first * 2]
    begin_last = 302 * 800 + math.ceil((15.04 - 451 / 30) * 24000 - 1e-9)
    assert output[begin_last * 2:895 * 800 * 2] == b"\x34\x12" * (895 * 800 - begin_last)
    assert receipt["tail_zero_samples"] == 4000 and len(output) == 1440000


@pytest.mark.parametrize("mutation", ["cue_cut", "source_overlap", "cue_overlap", "frames", "missing_tail", "internal_omission", "source_end"])
def test_unsafe_edl_is_rejected(sample, mutation):
    value = read_json(sample["edits"])
    if mutation == "cue_cut": value["segments"][1]["source_start_frame"] = 490
    elif mutation == "source_overlap": value["segments"][1]["source_start_frame"] = 299
    elif mutation == "cue_overlap": value["segments"][1]["fromCue"] = 1
    elif mutation == "frames": value["segments"][1]["source_end_frame"] -= 1
    elif mutation == "missing_tail": del value["tail_hold_frames"]
    elif mutation == "internal_omission": value["segments"][0]["source_end_frame"] = 470
    else: value["segments"][1]["source_end_frame"] = 1051
    with pytest.raises(WorkError):
        full.normalize_edits(value, read_json(sample["cues"])["cues"], sha(sample["video"]), sha(sample["cues"]), 35)


def test_source_pcm_shortage_never_silently_pads(sample):
    with pytest.raises(WorkError, match="不隐式补零"):
        full.edited_pcm(b"\1\1" * (34 * 24000), edit(sample))


@pytest.mark.parametrize("mutation", ["gap", "too_long", "offset_image", "wrong_sha", "empty_media", "shot_crosses", "tail_presenter", "missing_graphic", "discarded_cue", "wrong_cue_chapter"])
def test_storyboard_rejects_unsupported_or_unbound_objects(sample, mutation):
    value = read_json(sample["board"])
    if mutation == "gap": value["chapters"][1]["startFrame"] += 1
    elif mutation == "too_long": value["shots"][0]["endFrame"] += 1
    elif mutation == "offset_image": value["shots"][0]["sourceOffsetFrames"] = 1
    elif mutation == "wrong_sha": value["shots"][0]["sha256"] = "0" * 64
    elif mutation == "empty_media": value["shots"] = value["shots"][:1]
    elif mutation == "shot_crosses": value["shots"][0]["startFrame"] -= 1
    elif mutation == "tail_presenter": value["chapters"][-1]["kind"] = "presenter"
    elif mutation == "missing_graphic": value["graphics"] = value["graphics"][:-1]
    elif mutation == "discarded_cue": value["graphics"][0]["sourceCueIndices"] = [2]
    else: value["graphics"][0]["sourceCueIndices"] = [0]
    with pytest.raises(WorkError):
        full.normalize_storyboard(value, edit(sample))


@pytest.mark.parametrize("number,palette,ratio", [(7, "cyan-charcoal", "4x5"), (8, "black-pink", "4x5"),
    (9, "blue-beige", "4x5"), (7, "blue-beige", "9x16"), (6, "blue-beige", "4x5"), (True, "blue-beige", "4x5")])
def test_palette_ratio_number_are_strict_before_media_work(sample, number, palette, ratio):
    with pytest.raises(WorkError):
        prepare(sample, template_number=number, palette_variant=palette, ratio=ratio)
    assert sample["extracts"] == []


def test_actual_v5_mixer_consumes_edl_voice_with_target_cue_clock(sample, monkeypatch):
    plan, build, verify = sample["originals"]
    monkeypatch.setattr(full, "_sound_plan", plan)
    monkeypatch.setattr(sound, "build_audio_master", build)
    monkeypatch.setattr(full, "_verify_audio", verify)
    request = prepare(sample)
    folder = sample["queue"].projects_root / request["project_id"] / "assets/investment-full"
    receipt = read_json(folder / "audio-mix-receipt.json")
    assert receipt["input_voice_sha256"] == sha(folder / "edited-voice.wav")
    assert receipt["voice_gain_db"] == -2.5 and receipt["duration"] == 30
    assert receipt["aac_check"]["true_peak_dbtp"] <= -1.5 and receipt["cloud_calls"] == 0
    assert full.validate(sample["queue"], request)


def test_paused_full_queue_shares_parent_lane_and_registers_unapproved_work(sample, monkeypatch):
    request = prepare(sample)
    queue = sample["queue"]
    job = full.submit(queue, request)
    assert job["status"] == "paused" and full.submit(queue, request)["job_id"] == job["job_id"]
    assert queue.claim_next("ordinary-worker") is None
    other = queue.submit(project_id=request["project_id"], kind="review_preview", source="codex", priority="normal", parent_job_id="other", frozen_request={})
    queue.claim_next("occupied")
    with pytest.raises(ProductionQueueConflict):
        ProductionQueueWorker(queue, queue.projects_root).run_local_recompose(job["job_id"])
    queue.finish(other["job_id"], "occupied", status="completed", stage="done")
    renders = []
    def render(project, value):
        renders.append(value)
        folder = project / "renders" / value["render_id"]
        folder.mkdir(parents=True)
        output = folder / "avatar-preview.mp4"
        output.write_bytes(b"isolated-full-output")
        atomic_private(folder / "props.json", full._props(value))
        atomic_private(folder / "render-quality-receipt.json", {"fixture": True})
        return output
    monkeypatch.setattr(full, "_render", render)
    result = ProductionQueueWorker(queue, queue.projects_root).run_local_recompose(job["job_id"])
    assert result["status"] == "completed" and len(renders) == 1
    work = WorkCatalog(queue.projects_root).get(result["result"]["work_id"])
    assert work["final_version_id"] is None and work["targets"] == [] and work["confirmations"] == []
    (sample["template"] / "index.tsx").write_text("later executable", encoding="utf-8")
    assert full.validate(queue, request)


def test_real_submit_round_trip_preserves_the_entire_frozen_request(sample):
    request = prepare(sample)
    job = full.submit(sample["queue"], request)
    stored = sample["queue"].get(job["job_id"], include_private=True)["frozen_request"]
    assert stored == request
    core = {key: value for key, value in stored.items() if key not in {"request_sha256", "render_id"}}
    assert full.fingerprint(core) == stored["request_sha256"]


@pytest.mark.parametrize("loss", ["resource_name", "evidence_value"])
def test_submit_detects_existing_queue_sanitizer_loss_before_persisting(sample, loss):
    if loss == "resource_name":
        (sample["template"] / "tokens.ts").write_text("export const fixture = 1;", encoding="utf-8")
    else:
        value = read_json(sample["cues"])
        value["evidence"] = "isolated fixture api_key: do-not-echo-this-value"
        atomic_private(sample["cues"], value)
        edl = read_json(sample["edits"])
        edl["source_cues_sha256"] = sha(sample["cues"])
        atomic_private(sample["edits"], edl)
    request = prepare(sample)
    with pytest.raises(WorkError, match="队列安全脱敏") as error:
        full.submit(sample["queue"], request)
    assert "do-not-echo-this-value" not in str(error.value)
    assert "tokens.ts" in str(error.value) if loss == "resource_name" else "/caption_provenance/evidence" in str(error.value)
    assert sample["queue"].find_by_idempotency_key(full.CONTRACT + ":" + request["request_sha256"]) is None


def test_frozen_pcm_or_runtime_tampering_rejects(sample):
    request = prepare(sample)
    (sample["template"] / "index.tsx").write_text("changed executable", encoding="utf-8")
    with pytest.raises(WorkError, match="可执行模板"):
        full.validate(sample["queue"], request)


def test_renderer_uses_original_edl_source20m_and_one_prepared_master(sample, monkeypatch):
    from backlot import studio_composition
    from tools.video.video_compose import VideoCompose
    request = prepare(sample)
    project = sample["queue"].projects_root / request["project_id"]
    renders, muxes, commands = [], [], []
    monkeypatch.setattr("lib.ffmpeg_locator.resolve_ffmpeg_pair", lambda: ("fixture-ffmpeg", "fixture-probe"))
    def render(self, inputs):
        renders.append(inputs)
        Path(inputs["output_path"]).write_bytes(b"isolated-raw")
        return SimpleNamespace(success=True, data={"render_command": ["fixture-remotion", "--video-bitrate=20M"]})
    monkeypatch.setattr(VideoCompose, "execute", render)
    def mux(ffmpeg, raw, audio, output, duration, **kwargs):
        muxes.append((raw, audio, duration, kwargs))
        Path(output).write_bytes(b"isolated-muxed")
        return [ffmpeg, "-c:v", "copy"]
    monkeypatch.setattr(studio_composition, "mux_avatar_audio", mux)
    monkeypatch.setattr(sound, "measure_audio", lambda p: {"true_peak_dbtp": -3, "integrated_lufs": -17})
    monkeypatch.setattr(full, "_command", lambda args: commands.append(args))
    monkeypatch.setattr(full, "media_probe", lambda p: {"duration": 30,
        "video": {"width": 1440, "height": 1800, "codec_name": "h264", "pix_fmt": "yuv420p", "avg_frame_rate": "30/1"},
        "audio": {"sample_rate": "48000", "channels": 2}})
    output = full._render(project, request)
    assert sha(output.parent / "public/source.mp4") == sha(sample["video"])
    assert muxes[0][2:] == (30, {"prepared_master": True})
    settings = renders[0]["edit_decisions"]["bespoke"]
    assert settings["composition_id"] == "HaikeInvestmentFull" and settings["video_bitrate"] == "20M"
    assert settings["crf"] is None and settings["image_format"] == "png"
    assert len(commands) == 1 and "-vf" not in commands[0]
    assert read_json(output.parent / "props.json") == full._props(request)


def test_cyan45_edl_retains_complete_speech_and_explicit_tail():
    cues = [{"start": .1, "end": 44.4, "text": "完整原文口播"}]
    raw = {"version": "source-edits-v1", "source_video_sha256": "a", "source_cues_sha256": "b",
           "fps": 30, "target_duration_in_frames": 1350, "tail_hold_frames": 15,
           "segments": [{"id": "whole", "source_start_frame": 0, "source_end_frame": 1335,
                         "fromCue": 0, "toCue": 0, "reason": "保留完整45秒扩展口播"}]}
    value = full.normalize_edits(raw, cues, "a", "b", 44.5)
    source = b"\x01\x00" * (1335 * 800)
    pcm, receipt = full.edited_pcm(source, value)
    assert pcm[:len(source)] == source
    assert pcm[len(source):] == b"\0" * (15 * 800 * 2)
    assert receipt["edited_samples"] == 1080000
    request = {"template_number": 8, "palette_variant": "cyan-charcoal", "brand": "测试",
               "source_edits": value, "cues": value["cues"], "storyboard": {"chapters": [], "shots": [], "graphics": []},
               "audio_plan": {"hits": []}}
    props = full._props(request)
    assert (props["duration"], props["durationInFrames"], props["contentEndFrame"], props["tailHoldFrames"]) == (45, 1350, 1335, 15)
    assert full.render_profile(1350)["duration_in_frames"] == 1350
    assert full.render_profile(1350)["video_bitrate"] == "22M"
    assert full.render_profile(1350)["rate_control"] == "cbr-hrd"
    raw["segments"][0]["source_end_frame"] = 1334
    with pytest.raises(WorkError, match="覆盖声明"):
        full.normalize_edits(raw, cues, "a", "b", 44.5)


@pytest.mark.parametrize("frames", [True, 900.0, 1349, 1351, 1800])
def test_duration_extension_rejects_implicit_or_unapproved_clocks(frames):
    with pytest.raises(WorkError, match="1350"):
        full.render_profile(frames)
