"""Isolated dynamic-wall input/identity checks; no private media or provider calls."""
from copy import deepcopy
import json
from pathlib import Path
import wave

import pytest
from PIL import Image

from backlot import studio_store_material_wall as wall
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, sha


@pytest.fixture
def props():
    example = Path(__file__).resolve().parents[2] / "templates/store-material-wall-v1/props.example.json"
    return json.loads(example.read_text(encoding="utf-8"))


@pytest.fixture
def sample(props, tmp_path, monkeypatch):
    template = tmp_path / "template"
    template.mkdir()
    (template / "index.tsx").write_text("export const fixture=true;", encoding="utf-8")
    monkeypatch.setattr(wall, "TEMPLATE", template)
    monkeypatch.setattr(wall, "runtime", lambda: {str(template / "index.tsx"): sha(template / "index.tsx")})
    monkeypatch.setattr(wall, "media_probe", lambda path: {
        "duration": 20, "video": {"width": 1920, "height": 1080}, "audio": {"codec_name": "aac"}})
    queue = ProductionQueue(tmp_path / "queue.sqlite3", tmp_path / "projects")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    paths = {name: inputs / name for name in ["master.wav", "audio-receipt.json", "asset-review.json"]}
    for card in props["cards"]:
        paths[card["src"]] = inputs / card["src"]
        paths[card["src"]].write_bytes(("unrendered-isolated-video-" + card["id"]).encode())
        paths[card["thumbnail"]] = inputs / card["thumbnail"]
        Image.new("RGB", (640, 360), "#C2CCD1").save(paths[card["thumbnail"]])
    with wave.open(str(paths["master.wav"]), "wb") as stream:
        stream.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0" * (props["durationFrames"] * 1600 * 4))
    audio = {"master_audio_sha256": sha(paths["master.wav"]), "narration": "none", "source_audio": "muted", "cloud_calls": 0,
             "music_provenance": {"source_sha256": "a" * 64, "evidence": "isolated fixture; not a music-rights claim"}}
    review = {"version": wall.CONTRACT, "review_method": "isolated fixtures only", "reviewed_by": "test-fixture", "cards": [
        {"card_id": c["id"], "src": c["src"], "source_sha256": sha(paths[c["src"]]), "thumbnail": c["thumbnail"],
         "thumbnail_sha256": sha(paths[c["thumbnail"]]), "thumbnail_timestamp": c["offset"],
         "source_start_seconds": c["offset"], "source_end_seconds": c["offset"] + 4,
         "observed_frames": [c["offset"]], "description": "isolated fixture, not actual media viewing", "relevant": True}
        for c in props["cards"]]}
    for name, value in (("audio-receipt.json", audio), ("asset-review.json", review)):
        atomic_private(paths[name], value)
    return {"queue": queue, "props": props, "paths": paths, "audio": audio, "review": review, "template": template}


def prepare(sample):
    return wall.prepare(sample["queue"], sample["props"], sample["paths"], "隔离素材墙短样")


def test_declared_wall_keeps_eight_cards_and_three_same_card_playback_moments(props):
    wall.validate_props(props)
    assert len(props["cards"]) == 8 and len(props["moments"]) == 3
    cards = {card["id"]: card for card in props["cards"]}
    tabs = {tab["id"]: tab for tab in props["tabs"]}
    for moment in props["moments"]:
        assert moment["cardId"] in tabs[moment["tabId"]]["order"]
        assert cards[moment["cardId"]]["fit"] == "contain"
        assert (moment["end"] - moment["expandFrom"]) / 30 == pytest.approx(3.8)


@pytest.mark.parametrize("mutation", [
    "unsafe_video", "unsafe_thumbnail", "duplicate_card", "unknown_tab_card", "duplicate_tab_card",
    "unknown_moment_card", "wrong_category", "phase_order", "overlap", "negative_offset",
    "voiceover", "source_audio", "card_identity_swap", "initial_tab_missing", "tab_order", "preview",
])
def test_invalid_card_category_timeline_or_speech_contract_is_rejected(props, mutation):
    if mutation == "unsafe_video": props["cards"][0]["src"] = "../private.mp4"
    elif mutation == "unsafe_thumbnail": props["cards"][0]["thumbnail"] = "C:\\private\\poster.jpg"
    elif mutation == "duplicate_card": props["cards"][1]["id"] = props["cards"][0]["id"]
    elif mutation == "unknown_tab_card": props["tabs"][0]["order"][0] = "missing-card"
    elif mutation == "duplicate_tab_card": props["tabs"][0]["order"][1] = props["tabs"][0]["order"][0]
    elif mutation == "unknown_moment_card": props["moments"][0]["cardId"] = "missing-card"
    elif mutation == "wrong_category": props["moments"][0]["tabId"] = "robot"
    elif mutation == "phase_order": props["moments"][0]["holdFrom"] = props["moments"][0]["expandFrom"] - 1
    elif mutation == "overlap": props["moments"][1]["cursorFrom"] = props["moments"][0]["end"] - 1
    elif mutation == "negative_offset": props["moments"][0]["sourceOffset"] = -1
    elif mutation == "voiceover": props["voiceover"] = "speech.wav"
    elif mutation == "source_audio": props["cards"][0]["muted"] = False
    elif mutation == "card_identity_swap": props["moments"][0]["expandedCardId"] = "a08"
    elif mutation == "initial_tab_missing": props["tabChanges"][0]["from"] = 1
    elif mutation == "tab_order": props["tabChanges"][1]["from"] = -1
    else: props["cards"][0]["preview"] = {"from": 0, "frames": 30, "offset": 0}
    with pytest.raises(WorkError):
        wall.validate_props(props)


def test_ui_display_data_is_not_a_source_path_or_executable_slot(props):
    changed = deepcopy(props)
    changed["cards"][0]["imagePosition"] = "50% 50%;filter:blur(10px)"
    with pytest.raises(WorkError):
        wall.validate_props(changed)
    changed = deepcopy(props)
    changed["tabs"][0]["order"] = []
    with pytest.raises(WorkError):
        wall.validate_props(changed)


def test_sources_and_posters_are_copied_without_mutating_originals_and_submit_is_idempotent(sample):
    before = {name: sha(path) for name, path in sample["paths"].items()}
    request = prepare(sample)
    assert prepare(sample) == request
    project = wall.validate(sample["queue"], request)
    assert all(sha(path) == before[name] for name, path in sample["paths"].items())
    assert request["narration"] == "none" and request["cloud_calls"] == 0 and request["publication"] is False
    first = wall.submit(sample["queue"], request)
    assert first["job_id"] == wall.submit(sample["queue"], request)["job_id"]
    assert first["status"] == "paused"
    assert project.is_dir()


@pytest.mark.parametrize("mutation", ["poster_sha", "poster_card", "poster_time", "source_sha", "missing_card", "no_frames", "play_window", "narration", "master_sha", "source_audio", "cloud_calls"])
def test_current_poster_source_window_and_speech_free_master_must_match(sample, mutation):
    review, audio = sample["review"], sample["audio"]
    if mutation == "poster_sha": review["cards"][0]["thumbnail_sha256"] = "f" * 64
    elif mutation == "poster_card": review["cards"][0]["thumbnail"] = review["cards"][1]["thumbnail"]
    elif mutation == "poster_time": review["cards"][0]["thumbnail_timestamp"] = 200
    elif mutation == "source_sha": review["cards"][0]["source_sha256"] = "f" * 64
    elif mutation == "missing_card": review["cards"].pop()
    elif mutation == "no_frames": review["cards"][0]["observed_frames"] = []
    elif mutation == "play_window": review["cards"][1]["source_end_seconds"] = 7
    elif mutation == "narration": audio["narration"] = "user"
    elif mutation == "master_sha": audio["master_audio_sha256"] = "f" * 64
    elif mutation == "source_audio": audio["source_audio"] = "mixed"
    else: audio["cloud_calls"] = 1
    for name, value in (("audio-receipt.json", audio), ("asset-review.json", review)):
        atomic_private(sample["paths"][name], value)
    with pytest.raises(WorkError):
        prepare(sample)


def test_audio_samples_follow_output_frame_clock(sample):
    with wave.open(str(sample["paths"]["master.wav"]), "wb") as stream:
        stream.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0" * (sample["props"]["durationFrames"] * 1600 * 4 - 4))
    with pytest.raises(WorkError):
        prepare(sample)


@pytest.mark.parametrize("asset", ["a01.jpg", "a01.mp4", "master.wav"])
def test_frozen_assets_and_runtime_cannot_be_changed_under_existing_request(sample, asset):
    request = prepare(sample)
    changed = deepcopy(request)
    changed["props"]["moments"][0]["cardId"] = "a08"
    with pytest.raises(WorkError):
        wall.validate(sample["queue"], changed)
    (sample["template"] / "index.tsx").write_text("changed", encoding="utf-8")
    with pytest.raises(WorkError):
        wall.validate(sample["queue"], request)
    (sample["template"] / "index.tsx").write_text("export const fixture=true;", encoding="utf-8")
    project = wall.validate(sample["queue"], request)
    frozen_asset = next(p for p in project.rglob(asset))
    frozen_asset.write_bytes(b"changed frozen asset")
    with pytest.raises(WorkError):
        wall.validate(sample["queue"], request)


def test_tab_cannot_change_while_its_selected_card_is_expanding_or_playing(props):
    props["tabChanges"].insert(1, {"from": 150, "tabId": "robot"})
    with pytest.raises(WorkError):
        wall.validate_props(props)


def test_worker_dispatches_wall_contract_through_existing_local_queue(sample, monkeypatch):
    expected = {"status": "completed", "result": {"isolated": True}}
    monkeypatch.setattr(wall, "run", lambda queue, job: expected)
    worker = ProductionQueueWorker(sample["queue"], sample["queue"].projects_root)
    assert worker._run_investment_recompose({"frozen_request": {"contract": wall.CONTRACT}}) == expected
