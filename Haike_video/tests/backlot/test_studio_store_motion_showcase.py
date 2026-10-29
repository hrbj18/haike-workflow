"""Speech-free editing contracts, using isolated files rather than private media."""
from copy import deepcopy
import wave

import pytest

from backlot import studio_store_motion_showcase as showcase
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, sha


@pytest.fixture
def sample(tmp_path, monkeypatch):
    template = tmp_path / "template"
    template.mkdir()
    (template / "index.tsx").write_text("export const fixture=true;", encoding="utf-8")
    monkeypatch.setattr(showcase, "TEMPLATE", template)
    monkeypatch.setattr(showcase, "runtime", lambda: {str(template / "index.tsx"): sha(template / "index.tsx")})
    monkeypatch.setattr(showcase, "media_probe", lambda path: {
        "duration": 8, "video": {"width": 1920, "height": 1080}, "audio": {"codec_name": "aac"}})
    queue = ProductionQueue(tmp_path / "queue.sqlite3", tmp_path / "projects")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    paths = {name: inputs / name for name in ["master.wav", "audio-receipt.json", "asset-review.json", "a.mp4", "b.mp4"]}
    for name in ("a.mp4", "b.mp4"):
        paths[name].write_bytes(("unrendered-isolated-fixture-" + name).encode())
    with wave.open(str(paths["master.wav"]), "wb") as stream:
        stream.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0" * (6 * 48000 * 4))
    props = {
        "durationFrames": 180, "audio": "master.wav", "brand": "隔离测试门店", "location": "测试地点",
        "palette": {"paper": "#F5F3EC", "ink": "#18212A", "muted": "#59616A", "blue": "#294CEE", "orange": "#FF6B35", "line": "#D3D6D5"},
        "shots": [
            {"id": "door", "src": "a.mp4", "from": 0, "frames": 90, "offset": 1, "fit": "contain", "layout": "wide", "title": "走进门店", "subtitle": "", "kicker": "", "chapter": "arrival"},
            {"id": "experience", "src": "b.mp4", "from": 90, "frames": 90, "offset": 2, "fit": "contain", "layout": "portrait-left", "title": "现场体验", "subtitle": "", "kicker": "", "chapter": "arrival"},
        ],
        "chapters": [{"id": "arrival", "from": 0, "label": "门店现场"}],
    }
    audio = {"master_audio_sha256": sha(paths["master.wav"]), "narration": "none", "source_audio": "muted", "cloud_calls": 0,
             "music_provenance": {"source_sha256": "a" * 64, "evidence": "isolated fixture; not a music-rights claim"}}
    review = {"version": showcase.CONTRACT, "review_method": "isolated fixtures only", "reviewed_by": "test-fixture", "shots": [
        {"id": s["id"], "src": s["src"], "source_sha256": sha(paths[s["src"]]), "source_start_seconds": s["offset"],
         "source_end_seconds": s["offset"] + s["frames"] / 30, "observed_frames": [s["offset"] + .1],
         "description": "isolated fixture; not an actual media review", "relevant": True} for s in props["shots"]]}
    for name, value in (("audio-receipt.json", audio), ("asset-review.json", review)):
        atomic_private(paths[name], value)
    return {"queue": queue, "props": props, "paths": paths, "audio": audio, "review": review, "template": template}


def prepare(sample):
    return showcase.prepare(sample["queue"], sample["props"], sample["paths"], "隔离无口播店长短样")


def test_originals_are_frozen_and_submitting_same_request_is_idempotent(sample):
    before = {name: sha(path) for name, path in sample["paths"].items()}
    request = prepare(sample)
    assert prepare(sample) == request
    assert request["narration"] == "none" and request["publication"] is False and request["cloud_calls"] == 0
    project = showcase.validate(sample["queue"], request)
    assert all(sha(project / "assets/store-motion" / name) == before[name] == sha(path) for name, path in sample["paths"].items())
    first = showcase.submit(sample["queue"], request)
    assert first["job_id"] == showcase.submit(sample["queue"], request)["job_id"]
    assert first["status"] == "paused"


@pytest.mark.parametrize("mutation", ["gap", "overlap", "tail_gap", "long_shot", "repeated_source", "traversal", "absolute_path", "nan_offset", "crop_css", "long_title", "short_reading", "voiceover", "source_audio", "unknown_chapter"])
def test_invalid_edits_fail_before_project_or_media_copy(sample, mutation):
    props = sample["props"]
    if mutation == "gap": props["shots"][1]["from"] = 91
    elif mutation == "overlap": props["shots"][1]["from"] = 89
    elif mutation == "tail_gap": props["durationFrames"] = 181
    elif mutation == "long_shot": props["shots"][0]["frames"] = 121
    elif mutation == "repeated_source": props["shots"][1]["src"] = "a.mp4"
    elif mutation == "traversal": props["shots"][0]["src"] = "../a.mp4"
    elif mutation == "absolute_path": props["shots"][0]["src"] = "C:\\private\\a.mp4"
    elif mutation == "nan_offset": props["shots"][0]["offset"] = float("nan")
    elif mutation == "crop_css": props["shots"][0]["objectPosition"] = "50% 50%;filter:blur(4px)"
    elif mutation == "long_title": props["shots"][0]["title"] = "字" * 15
    elif mutation == "short_reading":
        props["motion"] = {"enterFrames": 24, "exitFrames": 16}
        props["durationFrames"] = 174
        props["shots"][0]["frames"] = 54
        props["shots"][1].update({"from": 54, "frames": 120})
    elif mutation == "voiceover": props["voiceover"] = "speech.wav"
    elif mutation == "source_audio": props["shots"][0]["muted"] = False
    else: props["shots"][0]["chapter"] = "missing-chapter"
    with pytest.raises(WorkError):
        prepare(sample)
    assert not list(sample["queue"].projects_root.glob("studio-*"))


@pytest.mark.parametrize("mutation", ["voice", "source_audio", "cloud", "master_sha", "missing_provenance", "review_sha", "review_range", "unseen", "missing_shot"])
def test_receipts_bind_no_speech_audio_and_reviewed_source_windows(sample, mutation):
    audio, review = sample["audio"], sample["review"]
    if mutation == "voice": audio["narration"] = "user"
    elif mutation == "source_audio": audio["source_audio"] = "mixed"
    elif mutation == "cloud": audio["cloud_calls"] = 1
    elif mutation == "master_sha": audio["master_audio_sha256"] = "b" * 64
    elif mutation == "missing_provenance": audio.pop("music_provenance")
    elif mutation == "review_sha": review["shots"][0]["source_sha256"] = "b" * 64
    elif mutation == "review_range": review["shots"][0]["source_start_seconds"] += .2
    elif mutation == "unseen": review["shots"][0]["observed_frames"] = []
    else: review["shots"].pop()
    for name, value in (("audio-receipt.json", audio), ("asset-review.json", review)):
        atomic_private(sample["paths"][name], value)
    with pytest.raises(WorkError):
        prepare(sample)


def test_clip_must_fit_source_and_master_must_fit_integer_frame_clock(sample, monkeypatch):
    monkeypatch.setattr(showcase, "media_probe", lambda path: {"duration": 3, "video": {"width": 1920, "height": 1080}})
    with pytest.raises(WorkError, match="原片长度"):
        prepare(sample)
    with wave.open(str(sample["paths"]["master.wav"]), "wb") as stream:
        stream.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0" * (6 * 48000 * 4 - 4))
    with pytest.raises(WorkError, match="样本数"):
        prepare(sample)


def test_frozen_sources_runtime_and_request_cannot_be_silently_changed(sample):
    request = prepare(sample)
    altered = deepcopy(request)
    altered["props"]["shots"][0]["title"] = "替换后的标题"
    with pytest.raises(WorkError, match="冻结身份"):
        showcase.validate(sample["queue"], altered)
    (sample["template"] / "index.tsx").write_text("changed", encoding="utf-8")
    with pytest.raises(WorkError, match="模板源码"):
        showcase.validate(sample["queue"], request)
    (sample["template"] / "index.tsx").write_text("export const fixture=true;", encoding="utf-8")
    project = showcase.validate(sample["queue"], request)
    (project / "assets/store-motion/a.mp4").write_bytes(b"changed frozen source")
    with pytest.raises(WorkError, match="冻结素材"):
        showcase.validate(sample["queue"], request)


def test_worker_dispatches_showcase_contract_through_existing_local_queue(sample, monkeypatch):
    expected = {"status": "completed", "result": {"isolated": True}}
    monkeypatch.setattr(showcase, "run", lambda queue, job: expected)
    worker = ProductionQueueWorker(sample["queue"], sample["queue"].projects_root)
    assert worker._run_investment_recompose({"frozen_request": {"contract": showcase.CONTRACT}}) == expected
