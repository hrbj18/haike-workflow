from __future__ import annotations

import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot import published_clip_index as clips
from backlot import published_clip_analysis as analysis
from backlot import published_clip_api as api


@pytest.fixture
def indexed(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "video.mp4").write_bytes(b"unchanged original")
    db = tmp_path / "index.sqlite3"
    monkeypatch.setattr(clips, "DB_PATH", db)
    monkeypatch.setattr(clips, "probe_media", lambda *_: {"duration_seconds": 30,
        "streams": [{"codec_type": "video", "width": 720, "height": 1520}, {"codec_type": "audio"}]})
    probe = tmp_path / "ffprobe"
    probe.write_text("stub")
    clips.scan(source, db_path=db, ffprobe=str(probe))
    identity = clips.list_videos(db_path=db)[0]["id"]
    clips.store_transcript(identity, [{"start_seconds": 3, "end_seconds": 5, "text": "我想唱歌"}], "test", db_path=db)
    points = [{"time": i * .5, "audio_db": -10 if 8 <= i <= 14 else -25,
               "motion": .12 if 8 <= i <= 14 else .01} for i in range(60)]
    monkeypatch.setattr(analysis, "decode_signals", lambda *_: points)
    monkeypatch.setattr(api, "configured_source", lambda: source)
    return source, db, identity


def event_payload(**changes):
    return {"start_seconds": 4, "end_seconds": 8, "summary": "游客鼓掌", "tags": ["applause"],
            "review_note": "连续画面核对", "annotation": {"actor": "visitor", "action": "鼓掌", "reaction": "大笑",
                "channels": ["video"], "context_start": 2, "context_end": 10}, **changes}


def test_structured_search_and_bounds(indexed):
    _, db, identity = indexed
    saved = clips.save_event(identity, event_payload(), db_path=db)
    assert clips.search("鼓掌", actor="visitor", reaction="大笑", confirmed_only=True, db_path=db)[0]["id"] == saved["id"]
    assert not clips.search(actor="robot", db_path=db)
    with pytest.raises(clips.ClipIndexError, match="上下文"):
        clips.save_event(identity, {"start_seconds": 1}, event_id=saved["id"], db_path=db)
    with pytest.raises(clips.ClipIndexError):
        clips.save_event(identity, {"annotation": {"context_end": float("nan")}}, event_id=saved["id"], db_path=db)
    for tags in [["singing"], ["dancing"]]:
        with pytest.raises(clips.ClipIndexError, match="需要"):
            clips.save_event(identity, event_payload(tags=tags, annotation={}), db_path=db)


def test_analysis_idempotence_and_review_preserved(indexed):
    source, db, identity = indexed
    before = (source / "video.mp4").stat()
    first = analysis.analyze(identity, source_root=source, db_path=db)
    assert first["status"] == "completed" and first["result"]["candidate_count"] >= 1
    candidates = [e for e in clips.get_video(identity, db_path=db)["events"] if e["source_kind"] == "joint_signals"]
    assert not any("singing" in e["tags"] or "dancing" in e["tags"] for e in candidates)
    row = candidates[0]
    clips.save_event(identity, {"review_status": "rejected", "review_note": "只有提及，没有开始唱"}, event_id=row["id"], db_path=db)
    assert analysis.analyze(identity, source_root=source, db_path=db)["cached"]
    analysis.analyze(identity, source_root=source, db_path=db, force=True)
    after = clips.get_video(identity, db_path=db)["events"]
    assert len([e for e in after if e["source_kind"] == "joint_signals"]) == len(candidates)
    assert next(e for e in after if e["id"] == row["id"])["review_status"] == "rejected"
    assert (source / "video.mp4").stat().st_mtime_ns == before.st_mtime_ns


def test_changed_source_is_rejected_before_cached_result(indexed):
    source, db, identity = indexed
    analysis.analyze(identity, source_root=source, db_path=db)
    (source / "video.mp4").write_bytes(b"replacement")
    with pytest.raises(clips.ClipIndexError, match="变化"):
        analysis.analyze(identity, source_root=source, db_path=db)


def test_failure_and_live_lease(indexed, monkeypatch):
    source, db, identity = indexed
    def broken(*_):
        raise RuntimeError("解码失败")
    monkeypatch.setattr(analysis, "decode_signals", broken)
    with pytest.raises(RuntimeError):
        analysis.analyze(identity, source_root=source, db_path=db)
    assert analysis.analysis_status(identity, db_path=db)["status"] == "failed"
    with clips.connect(db) as c:
        c.execute("UPDATE clip_analysis SET status='running',started=?", (time.time(),))
    assert analysis.analyze(identity, source_root=source, db_path=db)["status"] == "running"


def test_benchmark_does_not_invent_ground_truth_and_freezes_prediction(indexed):
    source, db, identity = indexed
    assert analysis.seed_benchmark(db_path=db)["created"] == 1
    assert analysis.seed_benchmark(db_path=db)["created"] == 0
    report = analysis.evaluate(analysis.benchmark_cases(db_path=db))
    assert report["reviewed"] == 0 and report["precision"] is None and report["recall"] is None
    analysis.analyze(identity, source_root=source, db_path=db)
    with pytest.raises(clips.ClipIndexError, match="完整复核"):
        analysis.save_truth(identity, {"status": "reviewed", "truth": [], "note": "", "channels": []}, db_path=db)
    payload = {"status": "reviewed", "truth": [], "note": "独立完整回听与观看，仅普通交流", "channels": ["audio", "video"]}
    first = analysis.save_truth(identity, payload, db_path=db)
    analysis.save_truth(identity, {**payload, "status": "pending"}, db_path=db)
    with clips.connect(db) as c:
        c.execute("UPDATE clip_analysis SET result=?", (json.dumps({"candidates": []}),))
    second = analysis.save_truth(identity, payload, db_path=db)
    assert first["prediction"] == second["prediction"] and len(first["prediction"]) > 0
    report = analysis.evaluate([second])
    assert report["precision"] == 0 and report["recall"] is None


def test_matching_is_one_to_one_and_label_specific():
    truth = [{"start_seconds": 3, "end_seconds": 8, "tags": ["singing"]}]
    row = {"status": "reviewed", "truth": truth, "prediction": truth * 2}
    report = analysis.evaluate([row])
    assert report["precision"] == .5 and report["recall"] == 1
    assert report["mean_boundary_error_seconds"] == 0
    for wrong in ["background_music", "singing_mentioned", "dancing"]:
        row["prediction"] = [{**truth[0], "tags": [wrong]}]
        report = analysis.evaluate([row])
        assert report["true_positive"] == 0 and report["false_positive"] == 1 and report["false_negative"] == 1
    assert analysis.evaluate([{**row, "status": "pending"}])["precision"] is None


def test_cut_spike_and_constant_sound_are_not_reactions():
    points = [{"time": i * .5, "audio_db": -12, "motion": .5 if i == 5 else .001} for i in range(30)]
    assert analysis.propose(points, [], 15) == []
    points[5]["audio_db"] = -1
    assert analysis.propose(points, [], 15) == []


def test_api_analysis_truth_and_combined_search(indexed):
    source, db, identity = indexed
    app = FastAPI(); app.include_router(api.router)
    client = TestClient(app)
    assert client.get(f"/api/published-clips/videos/{identity}/analysis").json()["status"] == "pending"
    assert client.post(f"/api/published-clips/videos/{identity}/analysis").json()["status"] == "completed"
    assert client.post(f"/api/published-clips/videos/{identity}/analysis").json()["cached"]
    assert client.get("/api/published-clips/search", params={"actor": "invalid"}).status_code == 422
    analysis.seed_benchmark(db_path=db)
    assert client.get("/api/published-clips/benchmark").json()["evaluation"]["pending"] == 1
    assert client.patch(f"/api/published-clips/benchmark/{identity}", json={"truth": [{"start_seconds": 20, "end_seconds": 10, "tags": ["dancing"]}]}).status_code == 422


def test_missing_audio_is_explicit():
    points = [{"time": i * .5, "audio_db": None, "motion": .12} for i in range(20)]
    candidates = analysis.propose(points, [{"start_seconds": 1, "end_seconds": 3, "text": "跳舞"}], 10)
    assert candidates[0]["evidence"]["channels"] == ["video_signal", "transcript"]
    assert candidates[0]["tags"] == ["dancing_mentioned"]


def test_transcript_change_replaces_only_untouched_candidates(indexed):
    source, db, identity = indexed
    first = analysis.analyze(identity, source_root=source, db_path=db)
    candidates = [e for e in clips.get_video(identity, db_path=db)["events"] if e["source_kind"] == "joint_signals"]
    changed = candidates[0]
    clips.save_event(identity, {"summary": "编辑补充的候选"}, event_id=changed["id"], db_path=db)
    clips.store_transcript(identity, [{"start_seconds": 15, "end_seconds": 18, "text": "跳舞"}], "test2", db_path=db)
    second = analysis.analyze(identity, source_root=source, db_path=db)
    assert not second["cached"] and first["result"]["signature"] != second["result"]["signature"]
    events = clips.get_video(identity, db_path=db)["events"]
    assert next(e for e in events if e["id"] == changed["id"])["summary"] == "编辑补充的候选"
    assert not any(e["id"] in [r["id"] for r in candidates[1:]] for e in events)
