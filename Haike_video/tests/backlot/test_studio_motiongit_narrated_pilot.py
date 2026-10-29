"""Narrated pilot contract checks with isolated files and no paid media calls."""
from copy import deepcopy
import json
from pathlib import Path
import wave

import pytest
from PIL import Image

from backlot import studio_motiongit_narrated_pilot as pilot
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, sha


@pytest.fixture
def props():
    path = Path(__file__).resolve().parents[2] / "templates/motiongit-narrated-pilot-v1/props.example.json"
    return json.loads(path.read_text(encoding="utf-8"))


def write_pcm(path, frames=960000, *, tail_signal=False):
    content = bytearray(frames * 4)
    if tail_signal:
        content[-4:] = b"\1\0\1\0"
    with wave.open(str(path), "wb") as stream:
        stream.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        stream.writeframes(content)


def test_wall_is_editable_without_changing_source_clock(props):
    for s in props['scenes']:
        if s['module']=='select':
            s['module']='wall';s.pop('secondaryMediaId');s['wallMediaIds']=[m['id'] for m in props['media']]
    pilot.validate_props(props)
    assert props['presenter']['from']==462 and props['durationFrames']==600
    props['scenes'][0]['wallMediaIds'][1]=props['scenes'][0]['wallMediaIds'][0]
    with pytest.raises(WorkError,match='素材墙'):pilot.validate_props(props)


def test_wall_category_row_capacity_is_checked(props):
    props['wallCategories']=['全部素材','亲子体验','机器人现场']
    pilot.validate_props(props)
    props['wallCategories']=[str(i)+'分类名称过长了' for i in range(6)]
    with pytest.raises(WorkError,match='单行阅读容量'):pilot.validate_props(props)


def test_hum_is_an_explicit_variant_and_preserves_all_timing(props):
    for scene in props['scenes']:
        if scene['module']=='select':
            scene['module']='wall';scene.pop('secondaryMediaId');scene['wallMediaIds']=[m['id'] for m in props['media']]
    original=deepcopy(props)
    props['visualStyle']='hum'
    pilot.validate_props(props)
    assert {k:v for k,v in props.items() if k!='visualStyle'}==original
    for invalid in ('unknown',{},True):
        props['visualStyle']=invalid
        with pytest.raises(WorkError,match='视觉风格'):pilot.validate_props(props)


def test_hum_does_not_claim_unadapted_two_card_module(props):
    props['visualStyle']='hum'
    with pytest.raises(WorkError,match='两卡select'):pilot.validate_props(props)


@pytest.fixture
def sample(props, tmp_path, monkeypatch):
    # These fixtures exercise lineage/clock/queue contracts, not font loading or
    # rendering. Keep them independent of private or platform-installed fonts.
    props = deepcopy(props)
    props.pop("fontAssets", None)
    template = tmp_path / "template"
    template.mkdir()
    (template / "index.tsx").write_text("export const isolated=true;", encoding="utf-8")
    monkeypatch.setattr(pilot, "TEMPLATE", template)
    monkeypatch.setattr(pilot, "runtime", lambda: {str(template / "index.tsx"): sha(template / "index.tsx")})
    monkeypatch.setattr(pilot, "media_probe", lambda path: {
        "duration": 40, "video": {"width": 1440, "height": 1800}, "audio": {"codec_name": "aac"}})
    queue = ProductionQueue(tmp_path / "queue.sqlite3", tmp_path / "projects")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    paths = {name: inputs / name for name in pilot.RECEIPTS}
    for media in props["media"]:
        paths[media["src"]] = inputs / media["src"]
        paths[media["src"]].write_bytes(("isolated-unrendered-video-" + media["id"]).encode())
        paths[media["thumbnail"]] = inputs / media["thumbnail"]
        poster_size = (640, 800) if media.get("orientation") == "portrait" else (800, 640)
        Image.new("RGB", poster_size, "#CBD0D4").save(paths[media["thumbnail"]])
    presenter = props["presenter"]
    paths[presenter["src"]] = inputs / presenter["src"]
    paths[presenter["src"]].write_bytes(b"isolated-unrendered-presenter")
    paths["voiceover-source.wav"].write_bytes(b"isolated-approved-source-voiceover")
    write_pcm(paths["master.wav"])
    write_pcm(paths["narration.wav"])
    captions = [dict(c, source_cue_index=i) for i, c in enumerate(props["captions"])]
    source_asr = {"cues": deepcopy(props["captions"])}
    prior = {"approved_audio": {"sha256": sha(paths["voiceover-source.wav"]), "user_approved": True}}
    atomic_private(paths["source-asr.json"], source_asr)
    atomic_private(paths["prior-receipt.json"], prior)
    audit = {
        "source_audio": {"sha256": sha(paths["voiceover-source.wav"])},
        "source_avatar": {"sha256": sha(paths[presenter["src"]])},
        "source_audio_receipt_sha256": sha(paths["prior-receipt.json"]),
        "source_asr_sha256": sha(paths["source-asr.json"]), "source_audio_prior_approved": True,
        "captions": captions,
        "avatar_sync": {"global_output_from_frame": presenter["from"], "global_output_frames": presenter["frames"],
                        "source_video_start_seconds": presenter["offset"],
                        "embedded_audio_vs_dry_voice_zero_lag_correlation_active": .9996},
    }
    atomic_private(paths["source-audit.json"], audit)
    audio = {
        "master_audio_sha256": sha(paths["master.wav"]), "narration": "existing-voiceover", "source_audio": "muted",
        "cloud_calls": 0, "paid_calls": 0, "publication": False, "playback_rate": 1, "reordered": False,
        "narration_offset_seconds": 0, "narration_duration_seconds": 19.8,
        "narration_source_sha256": sha(paths["voiceover-source.wav"]),
        "source_selection_sha256": sha(paths["source-audit.json"]), "source_asr_sha256": sha(paths["source-asr.json"]),
        "music_provenance": {"source_sha256": "a" * 64, "evidence": "isolated fixture, no rights claim"},
        "captions": deepcopy(captions),
    }
    review = {"version": pilot.CONTRACT, "review_method": "isolated fixtures", "reviewed_by": "test-fixture", "media": [
        {"media_id": m["id"], "src": m["src"], "source_sha256": sha(paths[m["src"]]), "thumbnail": m["thumbnail"],
         "thumbnail_sha256": sha(paths[m["thumbnail"]]), "thumbnail_timestamp": m["offset"],
         "source_start_seconds": m["offset"], "source_end_seconds": m["offset"] + 4,
         "observed_frames": [m["offset"]], "description": "isolated fixture; not an actual media review", "relevant": True}
        for m in props["media"]]}
    for name, value in (("audio-receipt.json", audio), ("asset-review.json", review)):
        atomic_private(paths[name], value)
    return {"queue": queue, "props": props, "paths": paths, "audio": audio, "review": review,
            "audit": audit, "source_asr": source_asr, "prior": prior, "template": template}


def prepare(sample):
    return pilot.prepare(sample["queue"], sample["props"], sample["paths"], "隔离口播动效测试片")


def test_orientation_rejects_unknown_value(props):
    props["media"][0]["orientation"] = "diagonal"
    with pytest.raises(WorkError):
        pilot.validate_props(props)


def test_orientation_must_match_the_reviewed_original_poster(sample):
    sample["props"]["media"][0]["orientation"] = "portrait"
    with pytest.raises(WorkError):
        prepare(sample)


def test_example_covers_modules_and_has_complete_original_clock_captions(props):
    pilot.validate_props(props)
    assert props["durationFrames"] == 600 and len(props["captions"]) == 11
    assert {scene["module"] for scene in props["scenes"]} == {"statement", "select", "focus"}
    assert all(len(caption["text"]) <= 18 for caption in props["captions"])
    assert props["captions"][-1]["endMs"] == 19720
    assert props["presenter"]["from"] == 462 and props["presenter"]["frames"] == 102
    assert {mode["mode"] for mode in props["presenterModes"]} == {"large", "small"}


@pytest.mark.parametrize("mutation", [
    "gap", "overlap", "uncovered", "unknown_module", "unknown_media", "same_card", "select_phase", "select_hold",
    "unsafe_video", "unsafe_poster", "source_speed", "source_sound", "long_caption", "caption_overlap", "caption_overrun",
    "presenter_before", "presenter_after", "presenter_overlap", "presenter_cover", "mode_without_source",
])
def test_invalid_coverage_media_caption_or_presenter_contract_is_rejected(props, mutation):
    selection = next(s for s in props["scenes"] if s["module"] == "select")
    if mutation == "gap": props["scenes"][1]["from"] += 1
    elif mutation == "overlap": props["scenes"][1]["from"] -= 1
    elif mutation == "uncovered": props["scenes"][-1]["frames"] -= 1
    elif mutation == "unknown_module": props["scenes"][0]["module"] = "unmapped-effect"
    elif mutation == "unknown_media": selection["mediaId"] = "missing"
    elif mutation == "same_card": selection["secondaryMediaId"] = selection["mediaId"]
    elif mutation == "select_phase": selection["selection"]["holdFrom"] = selection["selection"]["expandFrom"] - 1
    elif mutation == "select_hold": selection["selection"]["holdFrom"] = selection["frames"] - 1
    elif mutation == "unsafe_video": props["media"][0]["src"] = "../private.mp4"
    elif mutation == "unsafe_poster": props["media"][0]["thumbnail"] = "C:\\private\\poster.jpg"
    elif mutation == "source_speed": props["media"][0]["playbackRate"] = 1.2
    elif mutation == "source_sound": props["media"][0]["muted"] = False
    elif mutation == "long_caption": props["captions"][0]["text"] = "字" * 19
    elif mutation == "caption_overlap": props["captions"][1]["startMs"] = props["captions"][0]["endMs"] - 1
    elif mutation == "caption_overrun": props["captions"][-1]["endMs"] = 19801
    elif mutation == "presenter_before": props["presenterModes"][0]["from"] = 461
    elif mutation == "presenter_after": props["presenterModes"][-1]["frames"] = 600
    elif mutation == "presenter_overlap": props["presenterModes"][1]["from"] = props["presenterModes"][0]["from"]
    elif mutation == "presenter_cover": props["presenter"]["fit"] = "cover"
    else: del props["presenter"]
    with pytest.raises(WorkError):
        pilot.validate_props(props)


def test_no_presenter_is_valid_when_modes_are_absent(props):
    del props["presenter"]
    del props["presenterModes"]
    pilot.validate_props(props)


def test_prepare_copies_originals_and_submit_reuses_one_queue_intent(sample):
    before = {name: sha(path) for name, path in sample["paths"].items()}
    request = prepare(sample)
    assert prepare(sample) == request
    assert {name: sha(path) for name, path in sample["paths"].items()} == before
    assert request["narration"] == "existing-voiceover" and request["cloud_calls"] == 0 and request["publication"] is False
    first = pilot.submit(sample["queue"], request)
    assert first["job_id"] == pilot.submit(sample["queue"], request)["job_id"]
    assert first["status"] == "paused"


@pytest.mark.parametrize("mutation", [
    "master_sha", "source_sha", "source_selection", "asr_sha", "unapproved", "speed", "reordered", "offset",
    "new_paid", "source_audio", "caption_text", "cue_index", "presenter_sha", "presenter_clock", "presenter_sync",
    "poster_sha", "poster_time", "missing_media", "source_window",
])
def test_receipts_bind_existing_narration_asr_presenter_and_reviewed_visual_sources(sample, mutation):
    audio, audit, review, prior = sample["audio"], sample["audit"], sample["review"], sample["prior"]
    if mutation == "master_sha": audio["master_audio_sha256"] = "f" * 64
    elif mutation == "source_sha": audio["narration_source_sha256"] = "f" * 64
    elif mutation == "source_selection": audio["source_selection_sha256"] = "f" * 64
    elif mutation == "asr_sha": audio["source_asr_sha256"] = "f" * 64
    elif mutation == "unapproved": prior["approved_audio"]["user_approved"] = False
    elif mutation == "speed": audio["playback_rate"] = 1.1
    elif mutation == "reordered": audio["reordered"] = True
    elif mutation == "offset": audio["narration_offset_seconds"] = .1
    elif mutation == "new_paid": audio["paid_calls"] = 1
    elif mutation == "source_audio": audio["source_audio"] = "mixed"
    elif mutation == "caption_text": audio["captions"][0]["text"] = "无对应来源的新台词"
    elif mutation == "cue_index": audit["captions"][0]["source_cue_index"] = 999
    elif mutation == "presenter_sha": audit["source_avatar"]["sha256"] = "f" * 64
    elif mutation == "presenter_clock": audit["avatar_sync"]["global_output_from_frame"] = 461
    elif mutation == "presenter_sync": audit["avatar_sync"]["embedded_audio_vs_dry_voice_zero_lag_correlation_active"] = .5
    elif mutation == "poster_sha": review["media"][0]["thumbnail_sha256"] = "f" * 64
    elif mutation == "poster_time": review["media"][0]["thumbnail_timestamp"] = 300
    elif mutation == "missing_media": review["media"].pop()
    else:
        scene = next(s for s in sample["props"]["scenes"] if s["module"] == "focus")
        next(r for r in review["media"] if r["media_id"] == scene["mediaId"])["source_end_seconds"] = .1
    # Rebind the hash of a changed JSON so nested evidence is checked, not just its outer digest.
    atomic_private(sample["paths"]["prior-receipt.json"], prior)
    if mutation == "unapproved": audit["source_audio_receipt_sha256"] = sha(sample["paths"]["prior-receipt.json"])
    atomic_private(sample["paths"]["source-audit.json"], audit)
    if mutation in {"unapproved", "cue_index", "presenter_sha", "presenter_clock", "presenter_sync"}:
        audio["source_selection_sha256"] = sha(sample["paths"]["source-audit.json"])
    for name, value in (("audio-receipt.json", audio), ("asset-review.json", review)):
        atomic_private(sample["paths"][name], value)
    with pytest.raises(WorkError):
        prepare(sample)


@pytest.mark.parametrize("name", ["master.wav", "narration.wav"])
def test_master_and_narration_samples_must_follow_exact_output_clock(sample, name):
    write_pcm(sample["paths"][name], frames=959999)
    with pytest.raises(WorkError):
        prepare(sample)


def test_last_point_two_seconds_of_narration_has_no_speech(sample):
    write_pcm(sample["paths"]["narration.wav"], tail_signal=True)
    with pytest.raises(WorkError):
        prepare(sample)


@pytest.mark.parametrize("asset", ["master.wav", "source-asr.json", "source-audit.json", "prior-receipt.json", "presenter.mp4"])
def test_existing_request_rejects_frozen_media_or_source_lineage_tamper(sample, asset):
    request = prepare(sample)
    project = pilot.validate(sample["queue"], request)
    actual = sample["props"]["presenter"]["src"] if asset == "presenter.mp4" else asset
    (project / "assets/motiongit-narrated-pilot" / actual).write_bytes(b"changed frozen asset")
    with pytest.raises(WorkError):
        pilot.validate(sample["queue"], request)


def test_frozen_props_and_runtime_cannot_change_under_existing_identity(sample):
    request = prepare(sample)
    changed = deepcopy(request)
    changed["props"]["scenes"][0]["title"] = "changed"
    with pytest.raises(WorkError):
        pilot.validate(sample["queue"], changed)
    (sample["template"] / "index.tsx").write_text("changed", encoding="utf-8")
    with pytest.raises(WorkError):
        pilot.validate(sample["queue"], request)


def test_worker_dispatches_narrated_contract_through_existing_queue(sample, monkeypatch):
    expected = {"status": "completed", "result": {"isolated": True}}
    monkeypatch.setattr(pilot, "run", lambda queue, job: expected)
    worker = ProductionQueueWorker(sample["queue"], sample["queue"].projects_root)
    assert worker._run_investment_recompose({"frozen_request": {"contract": pilot.CONTRACT}}) == expected
