"""v5 frozen real local audio, native queue and old-contract regression seams."""
from copy import deepcopy
import math
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from backlot import studio_investment_audio_v5 as sound
from backlot import studio_investment_source_art_v5 as art
from backlot.production_queue import ProductionQueue, ProductionQueueConflict
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import Studio, atomic_private
from backlot.studio_composition import compose_avatar as native_compose_avatar
from backlot.work_catalog import WorkCatalog, WorkError, read_json, sha


def tone(path, duration, *, rate=48000, channels=2, amplitude=.12, frequency=220):
    import array
    samples = array.array("h")
    for i in range(round(duration * rate)):
        value = round(32767 * amplitude * math.sin(2 * math.pi * frequency * i / rate))
        samples.extend([value] * channels)
    with wave.open(str(path), "wb") as output:
        output.setparams((channels, 2, rate, 0, "NONE", "not compressed")); output.writeframes(samples.tobytes())


@pytest.fixture
def source(tmp_path, monkeypatch):
    video = tmp_path / "original.mp4"; video.write_bytes(b"original-source-and-AAC")
    music, hit = tmp_path / "music.wav", tmp_path / "dong.wav"
    tone(music, 4, frequency=330); tone(hit, .25, amplitude=.4, frequency=90)
    cue_file, word_file, config_file, audio_file = [tmp_path / (name + ".json") for name in ("cues", "words", "art", "audio")]
    cues = [{"text": "今天收现金", "startMs": 200, "endMs": 1400, "source_video_sha256": sha(video)},
            {"text": "点击下方链接", "startMs": 1800, "endMs": 2900, "source_video_sha256": sha(video)}]
    words = [{"text": text, "startMs": first, "endMs": last, "source_video_sha256": sha(video)}
             for text, first, last in (("今天", 200, 600), ("收现金", 650, 1400), ("点击", 1800, 2000), ("下方链接", 2100, 2900))]
    config = {"variant": "art-v5", "direction": "red-manifesto", "background_path": None, "background_sha256": None,
              "portrait_framing": "medium-9x16", "highlights": ["现金"], "scenes": [],
              "chapters": [{"kind": "hook", "fromCue": 0, "toCue": 0, "heading": ["今天收现金"], "deck": "", "points": []},
                           {"kind": "cta", "fromCue": 1, "toCue": 1, "heading": ["点击下方链接"], "deck": "", "points": []}]}
    audio = {"version": "sound-motion-v1", "mix_profile": "speech-led-v1",
             "music": {"path": str(music), "sha256": sha(music), "source_label": "isolated test tone", "offset": 0,
                       "loop": False, "gain_db": -8, "fade_in": .05, "fade_out": .2},
             "assets": [{"id": "dong", "role": "dong", "path": str(hit), "sha256": sha(hit), "source_label": "isolated test tone"}],
             "events": [{"id": "cash", "asset_id": "dong", "anchor": {"type": "word", "index": 1, "boundary": "start"},
                         "pattern": "triple-hit", "gain_db": -9}]}
    for path, value in ((cue_file, cues), (word_file, words), (config_file, config), (audio_file, audio)): atomic_private(path, value)
    q = ProductionQueue(tmp_path / ".backlot/queue.sqlite3", tmp_path / "projects")
    monkeypatch.setattr(art, "_runtime", lambda: {str(Path(sound.__file__).resolve()): sha(sound.__file__), "isolated-runtime": "v5"})
    monkeypatch.setattr(art, "media_probe", lambda p: {"duration": 3, "video": {"width": 864, "height": 1536}, "audio": {"codec_name": "aac"}})
    extracts, calls = [], []
    def extract(video, target):
        extracts.append(1); tone(target, 3, rate=24000, channels=1, amplitude=.22, frequency=180)
    monkeypatch.setattr(art.base, "_extract_audio", extract)
    monkeypatch.setattr("backlot.work_catalog.probe", lambda p: {"duration": 3, "width": 1080, "height": 1920, "has_audio": True})
    def forbidden(*a, **kw): pytest.fail("source soundtrack contract must never construct provider SDK")
    monkeypatch.setattr(Studio, "client", forbidden); monkeypatch.setattr("backlot.studio.sdk_type", forbidden)
    def compose(folder, draft, video, voice, duration, cues, *, art_direction, render_profile=None):
        calls.append(art_direction)
        assert sha(voice) == sha(Path(art_direction["audio_master"]["path"]).parent / "source-audio.wav")
        atomic_private(folder / "props.json", {"duration": duration, "avatarSrc": "avatar.mp4", "audioSrc": "mixed-master.wav",
                       "brand": draft["input"]["investment"]["brand"], "captions": cues, "art": art.props_art(art_direction)})
        output = folder / "avatar-preview.mp4"; output.write_bytes(b"fake-v5-final")
        atomic_private(folder / "audio-final-check.json", {"master": art_direction["audio_master"], "output_sha256": sha(output),
                       "additional_mux_gain_db": 0, "final": {"true_peak_dbtp": -3.0}})
        if render_profile is not None:
            public = folder / "public"; public.mkdir(exist_ok=True)
            (public / "avatar.mp4").write_bytes(Path(video).read_bytes())
            atomic_private(folder / "render-quality-receipt.json", {"profile": render_profile,
                "avatar": {"public_sha256": sha(video)}})
        return output
    monkeypatch.setattr("backlot.studio_composition.compose_avatar", compose)
    return dict(queue=q, video=video, music=music, hit=hit, cues=cue_file, words=word_file,
                config_file=config_file, audio_file=audio_file, config=config, audio=audio, calls=calls, extracts=extracts)


def freeze(source, **kwargs):
    return art.prepare(source["queue"], source["video"], source["cues"], source["words"], source["config_file"], source["audio_file"],
                       title="v5 sound motion test", brand="海客AI社区服务站", **kwargs)


def resign(request):
    core = {k: v for k, v in request.items() if k not in {"request_sha256", "render_id"}}
    request["request_sha256"] = art.fingerprint(core); request["render_id"] = art.PREFIX + request["request_sha256"][:20]
    return request


def test_real_mix_is_frozen_once_stereo_and_anchors_are_not_fabricated(source):
    request = freeze(source)
    assert freeze(source) == request and len(source["extracts"]) == 1
    master = request["art_direction"]["audio_master"]
    report = read_json(master["receipt_path"])
    assert report["aac_check"]["true_peak_dbtp"] <= -1.5
    assert report["voice_gain_db"] == -2.5 and report["effective_voice_gain_db"] == -2.5 + report["master_gain_db"]
    assert 3 <= report["music_ducking"]["active_speech_reduction_db"] <= 6
    assert 2.95 <= report["music_ducking"]["active_seconds"] <= 3
    sound.verify_master(master["path"], master["sha256"], 3)
    hits = art.props_art(request["art_direction"])["soundEvents"]
    assert [h["timeMs"] for h in hits] == pytest.approx([650, 770, 890])
    assert [h["startFrame"] for h in hits] == [20, 24, 27]
    assert all(set(h) == {"id", "role", "timeMs", "startFrame", "endFrame", "strength"} for h in hits)
    assert len(art.props_art(request["art_direction"])) == 9
    mix_plan = read_json(Path(master["path"]).with_name("audio-mix-plan.json"))
    assert "attack=15:release=180" in mix_plan["filter_graph"] and "normalize=0" in mix_plan["filter_graph"]
    assert "threshold=0.05:ratio=2.5" in mix_plan["filter_graph"]
    assert mix_plan["filter_graph"].count("volume=-2.5dB") == 1
    assert request["prepared"]["mixed_audio_sha256"] == sha(master["path"])


def test_native_worker_claim_and_old_worker_exclusion_no_sdk_no_approval(source):
    q = source["queue"]; request = freeze(source); job = art.submit(q, request)
    assert job["status"] == "paused" and art.submit(q, request)["job_id"] == job["job_id"] and q.claim_next("old") is None
    other = q.submit(project_id=request["project_id"], kind="review_preview", source="codex", priority="normal", parent_job_id="other", frozen_request={})
    q.claim_next("other")
    with pytest.raises(ProductionQueueConflict): ProductionQueueWorker(q, q.projects_root).run_local_recompose(job["job_id"])
    q.finish(other["job_id"], "other", status="completed", stage="done")
    finished = ProductionQueueWorker(q, q.projects_root).run_local_recompose(job["job_id"])
    assert finished["status"] == "completed" and finished["result"]["variant"] == "art-v5" and len(source["calls"]) == 1
    work = WorkCatalog(q.projects_root).get(finished["result"]["work_id"])
    assert work["final_version_id"] is None and work["targets"] == [] and work["confirmations"] == []


@pytest.mark.parametrize("mutation", ["sha", "free_time", "anchor", "gain", "short_music", "crowded", "role", "pattern"])
def test_sound_contract_rejects_bad_provenance_clock_or_unsafe_plan_before_mix(source, mutation):
    config = deepcopy(source["audio"])
    if mutation == "sha": config["music"]["sha256"] = "0" * 64
    elif mutation == "free_time": config["events"][0]["timeMs"] = 500
    elif mutation == "anchor": config["events"][0]["anchor"]["index"] = 200
    elif mutation == "gain": config["events"][0]["gain_db"] = 8
    elif mutation == "short_music": config["music"]["offset"] = 2
    elif mutation == "role": config["assets"][0]["role"] = "arbitrary"
    elif mutation == "pattern": config["events"][0]["pattern"] = "custom-offsets"
    else:
        config["events"] = [{**deepcopy(config["events"][0]), "id": f"event-{i}", "pattern": "single"} for i in range(5)]
    atomic_private(source["audio_file"], config)
    with pytest.raises(WorkError): freeze(source)
    assert not source["calls"]


@pytest.mark.parametrize("mutation", ["master", "plan", "voice_gain", "publication"])
def test_signed_request_cannot_change_frozen_sound_or_policy(source, mutation):
    request = freeze(source)
    if mutation == "master": Path(request["prepared"]["mixed_audio_path"]).write_bytes(b"tampered")
    elif mutation == "plan": request["art_direction"]["audio_plan"]["hits"][0]["start"] = 1
    elif mutation == "voice_gain": request["audio_policy"]["voice_gain_db"] = 8
    else: request["publication"] = True
    with pytest.raises(WorkError): art.validate(source["queue"], resign(request))


def test_frozen_master_mux_has_no_gain_or_loudnorm_or_mono_conversion(tmp_path, monkeypatch):
    from backlot import studio_composition as c
    calls = []
    monkeypatch.setattr(c.subprocess, "run", lambda args, **kw: calls.append(args) or SimpleNamespace(returncode=0))
    c.mux_avatar_audio("ffmpeg", tmp_path / "raw.mp4", tmp_path / "mixed-master.wav", tmp_path / "final.mp4", 3, prepared_master=True)
    assert len(calls) == 1 and "-af" not in calls[0] and "-ac" not in calls[0]
    assert str(tmp_path / "mixed-master.wav") in calls[0] and "1:a:0" in calls[0]
    with pytest.raises(WorkError): c.mux_avatar_audio("ffmpeg", "raw", "audio", "out", 3, prepared_master=True, linear_gain_db=-2.5)


@pytest.mark.parametrize("profile_id", ["high-fidelity-v1", "high-fidelity-20mbps-v1"])
def test_native_v5_composer_uses_identical_public_master_and_ninth_sound_field(source, monkeypatch, profile_id):
    from backlot import studio_composition as c
    from tools.video.video_compose import VideoCompose
    request = freeze(source, render_profile=profile_id)
    folder = source["queue"].projects_root / request["project_id"] / "renders/native-v5-test"
    folder.mkdir(parents=True)
    renders, muxes, commands = [], [], []
    def render(self, value):
        renders.append(value); Path(value["output_path"]).write_bytes(b"raw-v5"); return SimpleNamespace(success=True)
    def mux(ffmpeg, raw, audio, output, duration, **kwargs):
        muxes.append((Path(audio), kwargs)); Path(output).write_bytes(b"native-v5-final")
    monkeypatch.setattr(VideoCompose, "execute", render)
    monkeypatch.setattr("lib.ffmpeg_locator.resolve_ffmpeg_pair", lambda: ("fake-ffmpeg", "fake-probe"))
    monkeypatch.setattr(c.subprocess, "run", lambda args, **kw: commands.append(args) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(c, "media_probe", lambda p: {"duration": 3, "video": {"width": 1080, "height": 1920, "duration": "3", "avg_frame_rate": "25/1"}, "audio": {"sample_rate": "48000", "channels": 2}})
    monkeypatch.setattr(c, "mux_avatar_audio", mux)
    monkeypatch.setattr(sound, "measure_audio", lambda p: {"true_peak_dbtp": -2.8, "integrated_lufs": -19, "loudness_range_lu": 2})
    out = native_compose_avatar(folder, request["draft"], source["video"], request["prepared"]["audio_path"], 3, request["cues"],
        art_direction=request["art_direction"], render_profile=request["render_profile"])
    props = read_json(folder / "props.json")
    assert props["audioSrc"] == "mixed-master.wav" and props["art"] == art.props_art(request["art_direction"])
    assert sha(folder / "public/mixed-master.wav") == request["prepared"]["mixed_audio_sha256"]
    assert sha(folder / "public/narration.wav") == sha(request["prepared"]["audio_path"])
    assert muxes == [(folder / "public/mixed-master.wav", {"prepared_master": True})]
    assert renders[0]["edit_decisions"]["bespoke"]["composition_id"] == "HaikeInvestmentArtV5"
    quality = read_json(folder / "render-quality-receipt.json")
    assert quality["profile"] == request["render_profile"] and quality["profile"]["id"] == profile_id
    assert sha(folder / "public/avatar.mp4") == sha(source["video"])
    assert quality["avatar"]["source_fps"] == "25/1" and quality["avatar"]["alignment_command"] is None
    assert all("-vf" not in command and "libx264" not in command for command in commands)
    settings = renders[0]["edit_decisions"]["bespoke"]
    assert (settings["image_format"], settings["x264_preset"], settings["scale"]) == ("png", "slow", 1)
    if profile_id == "high-fidelity-v1":
        assert settings["crf"] == 16 and "video_bitrate" not in settings
    else:
        assert settings["crf"] is None and settings["video_bitrate"] == "20M"
    assert "jpeg_quality" not in settings
    template = Path(art.__file__).resolve().parents[1] / "templates/avatar-investment-a-v6-art-v5"
    for component in [*template.glob("*.tsx"), template / "types.ts", template / "layout.json"]:
        assert sha(folder / component.name) == sha(component)
    final = read_json(folder / "audio-final-check.json")
    assert final["output_sha256"] == sha(out) and final["additional_mux_gain_db"] == 0


def test_peak_safety_fallback_reports_effective_voice_gain(source, monkeypatch):
    reports = iter([{"integrated_lufs": -12, "true_peak_dbtp": 0, "loudness_range_lu": 2},
                    {"integrated_lufs": -14, "true_peak_dbtp": -1.8, "loudness_range_lu": 2},
                    {"integrated_lufs": -14, "true_peak_dbtp": -2.0, "loudness_range_lu": 2}])
    monkeypatch.setattr(sound, "measure_audio", lambda p: next(reports))
    request = freeze(source)
    receipt = read_json(request["art_direction"]["audio_master"]["receipt_path"])
    assert receipt["master_gain_db"] == -1.75 and receipt["effective_voice_gain_db"] == -4.25
    assert len(receipt["safety_passes"]) == 2 and receipt["original_voice_unchanged"]


def test_music_loop_is_explicit_and_cue_chapter_anchors_derive_original_clock(source):
    audio = deepcopy(source["audio"])
    audio["music"].update(offset=2, loop=True)
    audio["events"] = [{**audio["events"][0], "id": "chapter", "pattern": "single", "anchor": {"type": "chapter", "index": 1, "boundary": "start"}},
                       {**audio["events"][0], "id": "cue", "pattern": "single", "anchor": {"type": "cue", "index": 1, "boundary": "end"}}]
    atomic_private(source["audio_file"], audio)
    request = freeze(source)
    hits = art.props_art(request["art_direction"])["soundEvents"]
    assert [h["timeMs"] for h in hits] == pytest.approx([1800, 2900])
    assert hits[-1]["endFrame"] == 90


def test_asset_sync_point_prerolls_actual_audio_and_trims_negative_start_without_moving_words(source):
    audio = deepcopy(source["audio"])
    audio["assets"][0].update(role="whoosh", sync_ms=230)
    audio["events"] = [{**audio["events"][0], "pattern": "single", "anchor": {"type": "word", "index": 0, "boundary": "start"}}]
    atomic_private(source["audio_file"], audio)
    request = freeze(source)
    hit = request["art_direction"]["audio_plan"]["hits"][0]
    assert hit["timeMs"] == 200 and hit["startFrame"] == 6
    assert hit["sync_ms"] == 230 and hit["playback_start_ms"] == 0 and hit["trim_start_ms"] == 30
    assert request["art_direction"]["word_cues"][0]["startMs"] == 200
    graph = read_json(Path(request["prepared"]["mixed_audio_path"]).with_name("audio-mix-plan.json"))["filter_graph"]
    assert "atrim=start_sample=1440:end_sample=12000" in graph and "adelay=0S:all=1[s2]" in graph
    assert read_json(request["art_direction"]["audio_master"]["receipt_path"])["aac_check"]["true_peak_dbtp"] <= -1.5
    audio["assets"][0]["sync_ms"] = 250
    atomic_private(source["audio_file"], audio)
    with pytest.raises(WorkError, match="同步点"): freeze(source)


def test_quality_profile_is_default_frozen_idempotent_and_part_of_request_identity(source):
    request = freeze(source)
    assert request["render_profile"] == art.render_profile_spec("high-fidelity-20mbps-v1")
    manifest = read_json(Path(request["prepared"]["audio_path"]).with_name("import-manifest.json"))
    assert manifest["render_profile"] == request["render_profile"]
    assert freeze(source) == request
    legacy = freeze(source, render_profile="legacy-v1")
    assert legacy["request_sha256"] != request["request_sha256"] and legacy["project_id"] != request["project_id"]
    assert legacy["cues"] == request["cues"] and legacy["audio_policy"] == request["audio_policy"]
    assert legacy["art_direction"]["word_cues"] == request["art_direction"]["word_cues"]
    changed = deepcopy(request); changed["render_profile"]["crf"] = 23
    with pytest.raises(WorkError, match="冻结导出画质"): art.validate(source["queue"], resign(changed))


def test_missing_historical_profile_is_not_upgraded_and_pending_runtime_change_still_blocks(source, monkeypatch):
    request = freeze(source, render_profile="legacy-v1")
    request.pop("render_profile"); resign(request)
    manifest_path = Path(request["prepared"]["audio_path"]).with_name("import-manifest.json")
    manifest = read_json(manifest_path); manifest.pop("render_profile"); atomic_private(manifest_path, manifest)
    assert art.validate(source["queue"], request).name == request["project_id"]
    assert "render_profile" not in request
    monkeypatch.setattr(art, "_runtime", lambda: {"changed": "runtime"})
    with pytest.raises(WorkError, match="源码已变化"): art.validate(source["queue"], request)


def test_direct_source_covers_last_output_timestamp_without_padding_or_speed_change():
    profile = art.render_profile_spec("high-fidelity-v1")
    art.verify_source_clock({"duration": 33.2, "video": {"duration": "33.2", "avg_frame_rate": "25/1"}}, 33.18258333333333, profile)
    with pytest.raises(WorkError, match="末帧"):
        art.verify_source_clock({"duration": 33.0, "video": {"duration": "33.0"}}, 33.18258333333333, profile)


@pytest.mark.parametrize("invalid", ["unknown", {"id": "high-fidelity-v1", "crf": 0}])
def test_unrecognized_quality_rejected_before_extraction_or_mix(source, invalid):
    with pytest.raises(WorkError): freeze(source, render_profile=invalid)
    assert source["extracts"] == [] and source["calls"] == []


def completed_audio_donor(source):
    donor = freeze(source, render_profile="high-fidelity-v1")
    job = art.submit(source["queue"], donor)
    assert ProductionQueueWorker(source["queue"], source["queue"].projects_root).run_local_recompose(job["job_id"])["status"] == "completed"
    path = source["video"].with_name("completed-audio-request.json")
    atomic_private(path, donor)
    return donor, path


def test_reuse_completed_master_and_original_receipts_byte_exact_without_any_new_mix(source, monkeypatch):
    donor, donor_path = completed_audio_donor(source)
    original = Path(donor["prepared"]["audio_path"]).parent
    names = ("mixed-master.wav", "audio-mix-plan.json", "audio-mix-receipt.json", "music-pre-duck.wav", "music-post-duck.wav")
    before = {name: sha(original / name) for name in names}
    def no_mix(*a, **kw): pytest.fail("A completed master must be copied, never remixed")
    monkeypatch.setattr(sound, "build_audio_master", no_mix)
    request = freeze(source, reuse_audio_request=donor_path)
    assert request["project_id"] != donor["project_id"]
    assert request["render_profile"]["id"] == "high-fidelity-20mbps-v1"
    assert request["prepared"]["mixed_audio_sha256"] == donor["prepared"]["mixed_audio_sha256"]
    assert request["audio_reuse"]["donor_request_sha256"] == donor["request_sha256"]
    assert request["audio_reuse"]["remixed"] is False
    imported = Path(request["prepared"]["audio_path"]).parent
    for name, digest in before.items(): assert sha(imported / name) == digest == sha(original / name)
    assert request["art_direction"]["audio_master"]["identity"] == donor["art_direction"]["audio_master"]["identity"]
    assert art.validate(source["queue"], request).name == request["project_id"]
    assert freeze(source, reuse_audio_request=donor_path) == request
    result = ProductionQueueWorker(source["queue"], source["queue"].projects_root).run_local_recompose(art.submit(source["queue"], request)["job_id"])
    assert result["status"] == "completed"


@pytest.mark.parametrize("change", ["unfinished", "plan", "voice", "tampered_master"])
def test_audio_reuse_refuses_unfinished_or_different_provenance_without_remix(source, monkeypatch, change):
    if change == "unfinished":
        donor = freeze(source, render_profile="high-fidelity-v1")
        donor_path = source["video"].with_name("unfinished-request.json"); atomic_private(donor_path, donor)
    else:
        donor, donor_path = completed_audio_donor(source)
    if change == "plan":
        audio = deepcopy(source["audio"]); audio["music"]["gain_db"] -= 1; atomic_private(source["audio_file"], audio)
    elif change == "voice":
        monkeypatch.setattr(art.base, "_extract_audio", lambda video, target: tone(target, 3, rate=24000, channels=1, amplitude=.15))
    elif change == "tampered_master":
        Path(donor["prepared"]["mixed_audio_path"]).write_bytes(b"changed-donor-master")
    monkeypatch.setattr(sound, "build_audio_master", lambda *a, **kw: pytest.fail("Rejected reuse must not silently remix"))
    with pytest.raises(WorkError): freeze(source, reuse_audio_request=donor_path)


def test_prior_crf16_profile_parameters_remain_unchanged():
    assert art.render_profile_spec("high-fidelity-v1") == {
        "id": "high-fidelity-v1", "avatar_preparation": "source-byte-copy", "codec": "h264", "image_format": "png",
        "jpeg_quality": None, "crf": 16, "x264_preset": "slow", "pixel_format": "yuv420p", "width": 1080,
        "height": 1920, "fps": 30, "scale": 1, "final_video": "stream-copy"}
