from __future__ import annotations

import json
from pathlib import Path
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot import published_clip_index as clips
from backlot import published_clip_api as clip_api


@pytest.fixture
def archive(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    db = tmp_path / "index.sqlite3"
    probe = tmp_path / "ffprobe"
    probe.write_text("stub")
    monkeypatch.setattr(clips, "probe_media", lambda *_: {"duration_seconds": 60.0,
        "streams": [{"codec_type": "video", "width": 720, "height": 1520}, {"codec_type": "audio"}]})
    return source, db, probe


def test_scan_rename_content_change_and_media_boundary(archive):
    source, db, probe = archive
    first = source / "first.mp4"
    first.write_bytes(b"old" * 100)
    assert clips.scan(source, db_path=db, ffprobe=str(probe))["new"] == 1
    identity = clips.list_videos(db_path=db)[0]["id"]
    clips.save_event(identity, {"start_seconds": 3, "end_seconds": 8,
                                      "summary": "真实比心", "tags": ["heart_gesture"],
                                      "review_note": "逐帧核对画面"}, db_path=db)
    assert clips.scan(source, db_path=db, ffprobe=str(probe))["cached"] == 1
    first.rename(source / "renamed.mp4")
    assert clips.scan(source, db_path=db, ffprobe=str(probe))["renamed_or_duplicate"] == 1
    assert clips.get_video(identity, db_path=db)["events"][0]["summary"] == "真实比心"
    assert clips.media_path(identity, source_root=source, db_path=db).name == "renamed.mp4"
    (source / "renamed.mp4").write_bytes(b"new" * 100)
    assert clips.scan(source, db_path=db, ffprobe=str(probe))["new"] == 1
    assert clips.list_videos(db_path=db)[0]["id"] != identity
    with pytest.raises(clips.ClipIndexError):
        clips.get_video(identity, db_path=db)
    with pytest.raises(clips.ClipIndexError):
        clips.media_path(clips.list_videos(db_path=db)[0]["id"], source_root=tmp_path_other(source), db_path=db)


def tmp_path_other(source: Path) -> Path:
    other = source.parent / "other"
    other.mkdir(exist_ok=True)
    return other


def test_candidates_are_not_confirmed_and_editor_changes_survive_refresh(archive):
    source, db, probe = archive
    (source / "粤仔唱歌.mp4").write_bytes(b"video")
    clips.scan(source, db_path=db, ffprobe=str(probe))
    identity = clips.list_videos(db_path=db)[0]["id"]
    transcript = [{"start_seconds": 12, "end_seconds": 17, "text": "等下我唱歌给你听"},
                  {"start_seconds": 19, "end_seconds": 21, "text": "哈哈，好厉害"}]
    clips.store_transcript(identity, transcript, "test-model", db_path=db)
    matches = clips.search("唱歌", db_path=db)
    assert any(row["match_source"] == "candidate_tag" for row in matches)
    assert not clips.search("唱歌", confirmed_only=True, db_path=db)
    candidate = next(row for row in clips.get_video(identity, db_path=db)["events"]
                     if "singing_mentioned" in row["tags"])
    with pytest.raises(clips.ClipIndexError, match="核对依据"):
        clips.save_event(identity, {"review_status": "confirmed"}, event_id=candidate["id"], db_path=db)
    clips.save_event(identity, {"start_seconds": 12.5, "end_seconds": 16.5,
                                "summary": "仅提到唱歌，未开始唱", "tags": ["singing_mentioned"],
                                "review_status": "confirmed", "review_note": "回听确认仅说了这句话"},
                                event_id=candidate["id"], db_path=db)
    clips.store_transcript(identity, transcript, "test-model", db_path=db)
    assert clips.get_video(identity, db_path=db)["events"][0]["review_status"] == "confirmed"
    confirmed = clips.search("唱歌", confirmed_only=True, db_path=db)
    assert len(confirmed) == 1 and confirmed[0]["start_seconds"] == 12.5
    assert len(clips.search(db_path=db)) == 1 and clips.search(db_path=db)[0]["kind"] == "video"
    clips.save_description(identity, "粤仔与游客聊唱歌，之后对方演唱", db_path=db)
    assert clips.search("游客", db_path=db)[-1]["match_source"] == "description"
    assert all(row["kind"] == "video" for row in clips.search("粤仔唱歌", db_path=db))
    with pytest.raises(clips.ClipIndexError):
        clips.save_event(identity, {"start_seconds": 25, "end_seconds": 20,
                                    "summary": "bad", "tags": ["dancing"]}, db_path=db)


def test_import_interaction_stays_candidate(archive, tmp_path: Path):
    source, db, probe = archive
    (source / "one.mp4").write_bytes(b"bytes")
    clips.scan(source, db_path=db, ffprobe=str(probe))
    identity = clips.list_videos(db_path=db)[0]["id"]
    index = {"status": "completed", "source": {"fingerprint": identity}, "duration": 60,
             "signature": "run-1", "events": [{"event_id": "E1", "start": 9, "end": 16,
             "summary": "粤仔邀请大家比心", "confidence": .8,
             "highlights": [{"label": "比心", "time": 14}]}]}
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    assert clips.import_interaction_index(index_path, db_path=db)["imported"] == 1
    assert clips.import_interaction_index(index_path, db_path=db)["imported"] == 0
    item = clips.search("比心", db_path=db)[0]
    assert item["review_status"] == "candidate" and item["start_seconds"] == 9


def test_api_search_edit_and_restricted_media(archive, monkeypatch):
    source, db, probe = archive
    (source / "机器狗比心.mp4").write_bytes(b"video")
    clips.scan(source, db_path=db, ffprobe=str(probe))
    monkeypatch.setattr(clips, "DB_PATH", db)
    monkeypatch.setattr(clip_api, "configured_source", lambda: source)
    app = FastAPI()
    app.include_router(clip_api.router)
    client = TestClient(app)
    identity = client.get("/api/published-clips/videos").json()[0]["id"]
    response = client.post(f"/api/published-clips/videos/{identity}/events", json={
        "start_seconds": 14, "end_seconds": 20, "summary": "现场比心", "tags": ["heart_gesture"],
        "review_note": "核对连续画面"})
    assert response.status_code == 200
    event_id = response.json()["id"]
    assert client.get(f"/api/published-clips/videos/{identity}").json()["confirmed_count"] == 1
    assert client.get("/api/published-clips/search", params={"tag": "heart_gesture", "confirmed_only": True}).json()[0]["start_seconds"] == 14
    response = client.patch(f"/api/published-clips/videos/{identity}/events/{event_id}", json={"start_seconds": -1})
    assert response.status_code == 422
    assert client.get(f"/api/published-clips/videos/{identity}/media").status_code == 200
    assert client.get(f"/api/published-clips/videos/{identity}/media",
                      headers={"Range": "bytes=0-1"}).status_code == 206
    assert client.get("/api/published-clips/videos/unknown/media").status_code == 404


def test_invalid_file_does_not_block_valid_file(archive, monkeypatch):
    source, db, probe = archive
    (source / "bad.mp4").write_bytes(b"bad")
    (source / "good.mp4").write_bytes(b"good")
    original = clips.probe_media
    def probe_one(path, binary):
        if path.name == "bad.mp4":
            raise ValueError("cannot probe")
        return original(path, binary)
    monkeypatch.setattr(clips, "probe_media", probe_one)
    result = clips.scan(source, db_path=db, ffprobe=str(probe))
    assert result["active"] == 1 and result["failed"] == 1
    assert clips.summary(db_path=db)["scan_failed"] == 1


def test_duplicate_content_tracks_both_paths_without_reprobing(archive):
    source, db, probe = archive
    (source / "a.mp4").write_bytes(b"same video")
    (source / "b.mp4").write_bytes(b"same video")
    first = clips.scan(source, db_path=db, ffprobe=str(probe))
    assert first["new"] == 1 and first["renamed_or_duplicate"] == 1
    assert clips.scan(source, db_path=db, ffprobe=str(probe))["cached"] == 2
    identity = clips.list_videos(db_path=db)[0]["id"]
    (source / "b.mp4").unlink()
    assert clips.scan(source, db_path=db, ffprobe=str(probe))["cached"] == 1
    assert clips.media_path(identity, source_root=source, db_path=db).name == "a.mp4"
    with clips.connect(db) as connection:
        locations = connection.execute("SELECT path,active FROM video_locations WHERE video_id=?", (identity,)).fetchall()
    assert len(locations) == 2 and sum(row["active"] for row in locations) == 1


def test_invalid_event_boundaries_are_rejected_but_overlap_is_allowed(archive):
    source, db, probe = archive
    (source / "limits.mp4").write_bytes(b"video")
    clips.scan(source, db_path=db, ffprobe=str(probe))
    identity = clips.list_videos(db_path=db)[0]["id"]
    for start, end in [(-1, 2), (3, 3), (59, 61)]:
        with pytest.raises(clips.ClipIndexError):
            clips.save_event(identity, {"start_seconds": start, "end_seconds": end,
                "summary": "test", "tags": ["other"], "review_note": "已核对"}, db_path=db)
    first = clips.save_event(identity, {"start_seconds": 10, "end_seconds": 15,
        "summary": "first", "tags": ["other"], "review_note": "已核对"}, db_path=db)
    second = clips.save_event(identity, {"start_seconds": 12, "end_seconds": 18,
        "summary": "second", "tags": ["other"], "review_note": "已核对"}, db_path=db)
    assert first["id"] != second["id"]


def test_transcript_small_timestamp_overshoot_is_clamped(archive):
    source, db, probe = archive
    (source / "song.mp4").write_bytes(b"video")
    clips.scan(source, db_path=db, ffprobe=str(probe))
    identity = clips.list_videos(db_path=db)[0]["id"]
    assert clips.store_transcript(identity, [{"start_seconds": 56, "end_seconds": 60.6,
        "text": "唱歌"}, {"start_seconds": 60.2, "end_seconds": 60.4, "text": "尾部幻觉"}],
        "model", db_path=db)["spans"] == 1
    assert clips.get_video(identity, db_path=db)["transcript"][0]["end_seconds"] == 60
    assert clips.store_transcript(identity, [{"start_seconds": 50, "end_seconds": 63, "text": "invalid"}],
                                  "model", db_path=db)["dropped_spans"] == 1
    with pytest.raises(clips.ClipIndexError):
        clips.store_transcript(identity, [{"start_seconds": -1, "end_seconds": 3, "text": "invalid"}],
                               "model", db_path=db)


def test_visual_overview_import_is_reviewable_and_idempotent(archive, tmp_path: Path):
    source, db, probe = archive
    (source / "overview.mp4").write_bytes(b"video")
    clips.scan(source, db_path=db, ffprobe=str(probe))
    identity = clips.list_videos(db_path=db)[0]["id"]
    analysis = {"status": "overview_completed", "task": {"source": {"fingerprint": identity},
        "task_fingerprint": "t1"}, "chapters": [{"chapter_id": "C1", "end_seconds": 60,
        "usable_ranges": [{"label": "合影姿势候选", "start_seconds": 21.2,
                           "end_seconds": 21.2, "confidence": .95,
                           "evidence_cell_ids": ["S1:R1C1"]}]}]}
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    assert clips.import_visual_overview(path, db_path=db)["imported"] == 1
    assert clips.import_visual_overview(path, db_path=db)["imported"] == 0
    event = clips.get_video(identity, db_path=db)["events"][0]
    assert event["review_status"] == "candidate" and event["tags"] == ["photo"]
    assert event["start_seconds"] < 21.2 < event["end_seconds"]


def test_main_workbench_mounts_archive_page(monkeypatch):
    from backlot.server import create_app

    archived = [{"id": "archive-fixture", "name": "fixture.mp4"}]
    monkeypatch.setattr(clip_api, "list_videos", lambda: archived)
    client = TestClient(create_app())
    legacy = client.get("/published-clips", follow_redirects=False)
    assert legacy.status_code == 307
    assert legacy.headers["location"] == "/projects"
    response = client.get(legacy.headers["location"])
    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text
    assets = re.findall(r'(?:src|href)="(/ui/avatar-generator/assets/[^\"]+)"', response.text)
    assert any(path.endswith(".js") for path in assets)
    assert any(path.endswith(".css") for path in assets)
    scripts = []
    for path in assets:
        asset = client.get(path)
        assert asset.status_code == 200
        if path.endswith(".js"):
            scripts.append(asset.text)
    bundle = "\n".join(scripts)
    assert "我的作品" in bundle
    assert "/api/works?candidates=true" in bundle
    # Removing the old standalone page must preserve its internal archive API.
    assert client.get("/api/published-clips/videos").json() == archived
