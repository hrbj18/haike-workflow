"""Isolated native-contract tests; never call a provider, encoder or real queue."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from backlot import studio_investment_style_lab as lab
from backlot.production_queue import ProductionQueue, ProductionQueueConflict
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import Studio, atomic_private
from backlot.work_catalog import WorkCatalog, WorkError, read_json, sha


@pytest.fixture
def sample(tmp_path_factory, monkeypatch):
    # The production folder names are descriptive; keep Windows test roots short
    # enough for atomic_private's UUID temporary suffix as well.
    tmp_path = tmp_path_factory.mktemp("isl")
    root = tmp_path / "runtime"
    template = root / "templates" / lab.TEMPLATE_FOLDER
    template.mkdir(parents=True)
    (template / "index.tsx").write_text("export const fixture = true;", encoding="utf-8")
    atomic_private(template / "layout.json", {"fixture": True})
    atomic_private(template / "video-template-spec.json", {"stage": "specification"})
    monkeypatch.setattr(lab, "_root", lambda: root)
    monkeypatch.setattr(lab, "_runtime", lambda: {str(p): sha(p) for p in lab._template_files()})
    video, cues = tmp_path / "historical.mp4", tmp_path / "cues.json"
    video.write_bytes(b"original-video-and-aac")
    atomic_private(cues, {"source_video_sha256": sha(video), "timing_basis": "manual_reviewed",
        "beat_titles": ["社区AI新生意", "本期第二拍", "本期第三拍", "本期第四拍"],
        "evidence": "isolated fixture only; not an actual transcript", "cues": [
            {"start": .2, "end": 5.2, "text": "社区AI新生意"},
            {"start": 6, "end": 11.9, "text": "了解合作方案"}]})
    queue = ProductionQueue(tmp_path / ".backlot/queue.sqlite3", tmp_path / "projects")
    monkeypatch.setattr(lab, "media_probe", lambda path: {"duration": 12,
        "video": {"duration": "12", "width": 864, "height": 1536}, "audio": {"codec_name": "aac"}})
    calls = []
    def voice(source, target):
        calls.append("extract")
        target.write_bytes(b"unaltered-voice-fixture")
    monkeypatch.setattr(lab, "_voice", voice)
    def master(folder, source):
        target, receipt = folder / "mixed-master.wav", folder / "audio-mix-receipt.json"
        if not target.exists():
            target.write_bytes(b"voice-master-fixture")
            atomic_private(receipt, {"fixture": True})
        return [target, receipt]
    monkeypatch.setattr(lab, "_voice_master", master)
    def no_provider(*args, **kwargs):
        pytest.fail("local source tests must not construct a provider SDK")
    monkeypatch.setattr(Studio, "client", no_provider)
    monkeypatch.setattr("backlot.studio.sdk_type", no_provider)
    monkeypatch.setattr("backlot.work_catalog.probe", lambda p: {
        "duration": 12, "width": 1080, "height": 1920, "has_audio": True})
    return {"root": root, "template": template, "queue": queue, "video": video, "cues": cues, "calls": calls}


def prepare(sample, **kwargs):
    params = dict(template_number=3, ratio="9x16", title="隔离招商测试",
                  brand="海客AI社区服务站", headline="社区AI新生意", cta="了解合作方案")
    params.update(kwargs)
    return lab.prepare(sample["queue"], sample["video"], sample["cues"], **params)


def resign(request):
    request["request_sha256"] = lab.fingerprint({k: v for k, v in request.items() if k not in {"request_sha256", "render_id"}})
    request["render_id"] = lab.PREFIX + request["request_sha256"][:20]
    return request


@pytest.mark.parametrize("ratio,dimensions", list(lab.DIMENSIONS.items()))
def test_four_profiles_and_native_props_are_explicit_20m(sample, ratio, dimensions):
    request = prepare(sample, ratio=ratio, template_number=10)
    props = lab._props(request)
    assert (props["width"], props["height"]) == dimensions
    assert (props["templateNumber"], props["ratio"], props["fps"], props["durationInFrames"]) == (10, ratio, 30, 360)
    assert request["render_profile"]["video_bitrate"] == "20M"
    assert request["render_profile"]["crf"] is None
    assert props["avatarSrc"] == "source.mp4" and props["audioSrc"] == "mixed-master.wav"
    assert props["cues"][0]["start"] == .2 and request["caption_provenance"]["timing_basis"] == "manual_reviewed"
    assert props["cues"][0]["startMs"] == 200 and props["cues"][0]["timestampMs"] is None
    assert props["beatTitles"] == request["beat_titles"]


def test_prepare_is_idempotent_and_postrender_docs_are_not_runtime(sample):
    request = prepare(sample)
    assert prepare(sample) == request and sample["calls"] == ["extract"]
    assert request["cloud_calls"] == 0 and request["publication"] is False
    snapshot = request["specification_snapshot"]
    assert snapshot["files"]
    atomic_private(sample["template"] / "video-template-spec.json", {"stage": "ready", "evidence": "later"})
    assert lab.validate(sample["queue"], request)
    assert not any("spec" in Path(path).name for path in request["runtime"])
    (sample["template"] / "index.tsx").write_text("changed executable", encoding="utf-8")
    with pytest.raises(WorkError, match="可执行模板"):
        lab.validate(sample["queue"], request)


def test_historical_short_test_can_omit_an_unspoken_cta(sample):
    request = prepare(sample, cta="")
    assert lab._props(request)["cta"] == ""


def test_default_palette_omission_keeps_legacy_request_and_props(sample):
    legacy = prepare(sample, template_number=7, ratio="4x5")
    explicit = prepare(sample, template_number=7, ratio="4x5", palette_variant="default")
    assert explicit == legacy
    assert "palette_variant" not in legacy and "paletteVariant" not in lab._props(legacy)
    # A completed result remains readable after executable source changes.
    project = sample["queue"].projects_root / legacy["project_id"]
    render = project / "renders" / legacy["render_id"]
    render.mkdir(parents=True)
    (render / "avatar-preview.mp4").write_bytes(b"legacy-completed-output")
    atomic_private(render / "props.json", lab._props(legacy))
    atomic_private(render / "render-quality-receipt.json", {"fixture": True})
    atomic_private(render / "investment-style-lab-result.json", {
        "request_sha256": legacy["request_sha256"], "output_sha256": sha(render / "avatar-preview.mp4"),
        "props_sha256": sha(render / "props.json"), "quality_receipt_sha256": sha(render / "render-quality-receipt.json")})
    (sample["template"] / "index.tsx").write_text("new palette executable", encoding="utf-8")
    assert lab.validate(sample["queue"], legacy) == project


@pytest.mark.parametrize("variant,number", list(lab.PALETTE_VARIANTS.items()))
def test_optional_palette_is_frozen_and_bound_to_its_template_and_ratio(sample, variant, number):
    legacy = prepare(sample, template_number=number, ratio="4x5")
    revised = prepare(sample, template_number=number, ratio="4x5", palette_variant=variant)
    assert revised["palette_variant"] == variant and lab._props(revised)["paletteVariant"] == variant
    assert revised["template_id"] == f"investment-template-{number:02d}-{variant}"
    assert revised["project_id"] != legacy["project_id"]
    assert revised["request_sha256"] != legacy["request_sha256"]
    assert revised["render_profile"] == legacy["render_profile"]
    assert revised["cues"] == legacy["cues"] and revised["beat_titles"] == legacy["beat_titles"]
    assert lab.validate(sample["queue"], revised)
    removed = deepcopy(revised)
    del removed["palette_variant"]
    removed["template_id"] = legacy["template_id"]
    with pytest.raises(WorkError, match="配色变体"):
        lab.validate(sample["queue"], resign(removed))
    added = deepcopy(legacy)
    added["palette_variant"] = variant
    added["template_id"] = revised["template_id"]
    with pytest.raises(WorkError, match="配色变体"):
        lab.validate(sample["queue"], resign(added))


@pytest.mark.parametrize("variant,number,ratio", [
    ("blue-beige", 8, "4x5"), ("cyan-charcoal", 7, "4x5"), ("black-pink", 10, "4x5"),
    ("blue-beige", 7, "9x16"), ("cyan-charcoal", 8, "1x1"), ("black-pink", 9, "16x9"),
    ("unknown", 7, "4x5"), ("", 7, "4x5"), (True, 7, "4x5"), ({}, 7, "4x5")])
def test_wrong_palette_template_or_ratio_rejected_before_import(sample, variant, number, ratio):
    with pytest.raises(WorkError, match="新配色"):
        prepare(sample, template_number=number, ratio=ratio, palette_variant=variant)
    assert sample["calls"] == []


@pytest.mark.parametrize("value", [None, "default"])
def test_frozen_palette_cannot_add_an_empty_default_field(sample, value):
    request = prepare(sample)
    request["palette_variant"] = value
    with pytest.raises(WorkError, match="默认配色"):
        lab.validate(sample["queue"], resign(request))


def test_four_beat_titles_are_owned_by_current_input_and_headline_is_effective(sample):
    value = read_json(sample["cues"])
    value["beat_titles"] = ["第一拍\n可换文案", "第二拍", "第三拍", "第四拍"]
    atomic_private(sample["cues"], value)
    request = prepare(sample, headline=None)
    assert lab._props(request)["headline"] == "第一拍\n可换文案"
    assert lab._props(request)["beatTitles"] == value["beat_titles"]
    with pytest.raises(WorkError, match="第一拍"):
        prepare(sample, headline="无效的旧标题")


def test_real_isolated_sound_plan_and_completed_master_reuse(sample, monkeypatch):
    """Exercise the existing mixer and proof verification, without video/SDK calls."""
    import array
    import math
    import wave
    def tone(path, duration, rate=48000, channels=2, frequency=180):
        values = array.array("h")
        for index in range(round(duration * rate)):
            values.extend([round(5000 * math.sin(2 * math.pi * frequency * index / rate))] * channels)
        with wave.open(str(path), "wb") as stream:
            stream.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
            stream.writeframes(values.tobytes())
    monkeypatch.setattr(lab, "_voice", lambda source, target: tone(target, 12, 24000, 1))
    # The fixture's fake source probe must not replace sound's real WAV probe.
    music, hit = sample["root"] / "music.wav", sample["root"] / "hit.wav"
    tone(music, 12.5, frequency=330)
    tone(hit, .25, frequency=90)
    plan = sample["root"] / "plan.json"
    atomic_private(plan, {"version": "sound-motion-v1", "mix_profile": "speech-led-v1",
        "music": {"path": str(music), "sha256": sha(music), "source_label": "isolated generated sine",
                  "offset": 0, "loop": False, "gain_db": -12, "fade_in": .05, "fade_out": .2},
        "assets": [{"id": "hit", "role": "impact", "path": str(hit), "sha256": sha(hit), "source_label": "isolated generated sine"}],
        "events": [{"id": "open", "asset_id": "hit", "anchor": {"type": "cue", "index": 0, "boundary": "start"},
                    "pattern": "single", "gain_db": -12}]})
    first = prepare(sample, audio_plan=plan)
    folder = sample["queue"].projects_root / first["project_id"] / "assets/investment-style-lab"
    receipt = read_json(folder / "audio-mix-receipt.json")
    assert receipt["cloud_calls"] == 0 and receipt["aac_check"]["true_peak_dbtp"] <= -1.5
    second = prepare(sample, template_number=4, mixed_audio=folder / "mixed-master.wav",
                     audio_receipt=folder / "audio-mix-receipt.json")
    reused = sample["queue"].projects_root / second["project_id"] / "assets/investment-style-lab"
    assert sha(reused / "mixed-master.wav") == sha(folder / "mixed-master.wav")
    assert sha(reused / "audio-mix-receipt.json") == sha(folder / "audio-mix-receipt.json")
    assert second["audio_mode"] == "completed-mix-reuse" and lab.validate(sample["queue"], second)


@pytest.mark.parametrize("mutation", ["profile", "policy", "template", "source", "cue", "binding"])
def test_frozen_identity_media_and_policy_cannot_change(sample, mutation):
    request = prepare(sample)
    folder = sample["queue"].projects_root / request["project_id"] / "assets/investment-style-lab"
    if mutation == "profile":
        request["render_profile"]["video_bitrate"] = "30M"
    elif mutation == "policy":
        request["publication"] = True
    elif mutation == "template":
        request["template_number"] = 2
    elif mutation == "source":
        (folder / "source.mp4").write_bytes(b"changed")
    elif mutation == "binding":
        del request["sources"][str((folder / "source-audio.wav").relative_to(folder.parents[1]))]
    else:
        request["cues"][0]["start"] = .8
    with pytest.raises(WorkError):
        lab.validate(sample["queue"], resign(request))


@pytest.mark.parametrize("mutation", ["sha", "basis", "overlap", "tail", "duration", "text"])
def test_cue_clock_must_be_sourced_and_cover_valid_nonoverlapping_ranges(sample, mutation):
    value = read_json(sample["cues"])
    if mutation == "sha": value["source_video_sha256"] = "0" * 64
    elif mutation == "basis": value["timing_basis"] = "guessed_asr"
    elif mutation == "overlap": value["cues"][1]["start"] = 5
    elif mutation == "tail": value["cues"][1]["end"] = 12.01
    elif mutation == "duration": value["cues"][0]["start"] = value["cues"][0]["end"]
    else: value["cues"][0]["text"] = ""
    with pytest.raises(WorkError):
        lab.normalize_cues(value, sha(sample["video"]))


def test_paused_native_worker_enforces_single_lane_and_registers_unapproved_work(sample, monkeypatch):
    queue = sample["queue"]
    request = prepare(sample)
    job = lab.submit(queue, request)
    assert job["status"] == "paused" and lab.submit(queue, request)["job_id"] == job["job_id"]
    assert queue.claim_next("legacy-worker") is None
    other = queue.submit(project_id=request["project_id"], kind="review_preview", source="codex", priority="normal",
        parent_job_id="other", frozen_request={})
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
        output.write_bytes(b"isolated-final-video")
        atomic_private(folder / "props.json", lab._props(value))
        atomic_private(folder / "render-quality-receipt.json", {"isolated": True})
        return output
    monkeypatch.setattr(lab, "_render", render)
    result = ProductionQueueWorker(queue, queue.projects_root).run_local_recompose(job["job_id"])
    assert result["status"] == "completed", result
    assert result["result"]["template_id"] == "investment-template-03"
    assert len(renders) == 1
    work = WorkCatalog(queue.projects_root).get(result["result"]["work_id"])
    assert work["final_version_id"] is None and work["confirmations"] == [] and work["targets"] == []
    assert lab.validate(queue, request)
    with pytest.raises(ProductionQueueConflict):
        ProductionQueueWorker(queue, queue.projects_root).run_local_recompose(job["job_id"])


def test_renderer_retains_source_bytes_and_passes20m_without_intermediate_avatar_encode(sample, monkeypatch):
    from backlot import studio_composition, studio_investment_audio_v5
    from tools.video.video_compose import VideoCompose
    request = prepare(sample, ratio="16x9", template_number=8)
    project = sample["queue"].projects_root / request["project_id"]
    renders, muxes, commands = [], [], []
    monkeypatch.setattr("lib.ffmpeg_locator.resolve_ffmpeg_pair", lambda: ("fake-ffmpeg", "fake-probe"))
    def render(self, inputs):
        renders.append(inputs)
        Path(inputs["output_path"]).write_bytes(b"raw-encoded-fixture")
        return SimpleNamespace(success=True, data={"render_command": ["fixture-remotion", "--video-bitrate=20M"]})
    monkeypatch.setattr(VideoCompose, "execute", render)
    def mux(ffmpeg, raw, audio, output, duration, **kwargs):
        muxes.append((raw, audio, duration, kwargs))
        Path(output).write_bytes(b"muxed-fixture")
        return [ffmpeg, "-c:v", "copy"]
    monkeypatch.setattr(studio_composition, "mux_avatar_audio", mux)
    monkeypatch.setattr(studio_investment_audio_v5, "measure_audio", lambda p: {"true_peak_dbtp": -3.2, "integrated_lufs": -17})
    monkeypatch.setattr(lab, "_command", lambda args: commands.append(args))
    monkeypatch.setattr(lab, "media_probe", lambda p: {"duration": 12,
        "video": {"width": 1920, "height": 1080, "codec_name": "h264", "pix_fmt": "yuv420p", "avg_frame_rate": "30/1"},
        "audio": {"sample_rate": "48000", "channels": 2}})
    output = lab._render(project, request)
    folder = output.parent
    assert sha(folder / "public/source.mp4") == sha(sample["video"])
    settings = renders[0]["edit_decisions"]["bespoke"]
    assert settings["composition_id"] == lab.COMPOSITION_ID and settings["video_bitrate"] == "20M"
    assert settings["crf"] is None and settings["image_format"] == "png" and settings["x264_preset"] == "slow"
    assert muxes[0][3] == {"prepared_master": True}
    assert len(commands) == 1 and "null" in commands[0] and "-vf" not in commands[0]
    quality = read_json(folder / "render-quality-receipt.json")
    assert quality["alignment_command"] is None and quality["additional_mux_gain_db"] == 0
    assert "--video-bitrate=20M" in quality["remotion_command"]
    assert quality["profile"]["width"] == 1920 and quality["human_review"] == "pending"
