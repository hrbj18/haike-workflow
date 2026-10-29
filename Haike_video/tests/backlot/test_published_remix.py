from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot import published_clip_index as clips
from backlot import published_remix as remix
from backlot import published_remix_api as api
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from lib.ffmpeg_locator import resolve_ffmpeg_pair


@pytest.fixture
def archive(tmp_path, monkeypatch):
    source, projects = tmp_path / "sources", tmp_path / "projects"
    source.mkdir(); projects.mkdir()
    db = tmp_path / "index.sqlite3"
    monkeypatch.setattr(clips, "DB_PATH", db)
    monkeypatch.setattr(clips, "configured_source", lambda: source)
    monkeypatch.setattr(clips, "probe_media", lambda *_: {"duration_seconds": 50,
        "streams": [{"codec_type": "video", "width": 320, "height": 180}, {"codec_type": "audio"}]})
    probe = tmp_path / "probe"; probe.write_text("stub")
    for n in range(2): (source / f"source-{n}.mp4").write_bytes(f"source-{n}".encode())
    clips.scan(source, db_path=db, ffprobe=str(probe))
    videos = clips.list_videos(db_path=db)
    draft = remix.create("测试二剪", projects_root=projects, db_path=db)
    queue = ProductionQueue(tmp_path / "queue.sqlite3", projects)
    monkeypatch.setattr(api, "_runtime", lambda _: (projects, queue))
    return source, projects, db, videos, draft, queue


def segments(videos):
    return [{"id": f"clip-{i}", "video_id": videos[i % 2]["id"], "start_seconds": 1 + i,
             "end_seconds": 3 + i, "audio_mode": mode, "role": "body", "note": "核对原片切口"}
            for i, mode in enumerate(["original", "lowered", "mute"])]


def save(draft, rows, db):
    return remix.save(draft["id"], {"revision": draft["revision"], "title": draft["title"], "segments": rows}, db_path=db)


def test_draft_order_audio_reopen_noop_and_cas(archive):
    _, _, db, videos, draft, _ = archive
    rows = list(reversed(segments(videos)))
    saved = save(draft, rows, db)
    reopened = remix.read(draft["id"], db_path=db)
    assert reopened == saved and [r["id"] for r in reopened["payload"]["segments"]] == ["clip-2", "clip-1", "clip-0"]
    assert reopened["payload"]["segments"][0]["audio_mode"] == "mute"
    assert save(saved, rows, db)["revision"] == saved["revision"]
    with pytest.raises(remix.RemixConflict): save(draft, rows, db)
    assert remix.read(draft["id"], db_path=db) == reopened


@pytest.mark.parametrize("field,value", [("start_seconds", -1), ("end_seconds", 51), ("end_seconds", 1),
    ("end_seconds", float("nan")), ("start_seconds", True), ("start_seconds", None), ("audio_mode", "bad"), ("role", "bad"), ("video_id", "../../outside")])
def test_rejects_invalid_edit(archive, field, value):
    _, _, db, videos, draft, _ = archive
    rows = segments(videos); rows[0][field] = value
    with pytest.raises(clips.ClipIndexError): save(draft, rows, db)
    assert remix.read(draft["id"], db_path=db)["revision"] == 1


def test_duplicate_ids_and_limits(archive):
    _, _, db, videos, draft, _ = archive
    rows = segments(videos)
    with pytest.raises(clips.ClipIndexError): save(draft, [rows[0], rows[0]], db)
    with pytest.raises(clips.ClipIndexError): save(draft, rows * 11, db)
    with pytest.raises(clips.ClipIndexError):
        save(draft, [{**rows[0], "id": str(i), "start_seconds": 0, "end_seconds": 40} for i in range(20)], db)


def test_frozen_versions_and_idempotent_queue(archive):
    source, projects, db, videos, draft, queue = archive
    first = save(draft, segments(videos), db)
    task = remix.submit(first["id"], first["revision"], queue, projects_root=projects, db_path=db)
    assert remix.submit(first["id"], first["revision"], queue, projects_root=projects, db_path=db)["job_id"] == task["job_id"]
    second = save(first, list(reversed(segments(videos))), db)
    path = remix.version_dir(first["id"], task["parent_job_id"], projects_root=projects) / "request.json"
    assert json.loads(path.read_text(encoding="utf-8"))["segments"][0]["id"] == "clip-0"
    with pytest.raises(remix.RemixConflict): remix.prepare(first["id"], first["revision"], projects_root=projects, db_path=db)
    (source / videos[0]["name"]).write_bytes(b"replaced")
    with pytest.raises(clips.ClipIndexError, match="变化"):
        remix.prepare(second["id"], second["revision"], projects_root=projects, db_path=db)


def test_api_save_conflict_submit_and_output_boundary(archive):
    _, _, db, videos, draft, _ = archive
    app = FastAPI(); app.include_router(api.router); client = TestClient(app)
    base = "/api/published-remixes/" + draft["id"]
    data = {"title": "API项目", "revision": 1, "segments": segments(videos)}
    response = client.put(base, json=data)
    assert response.status_code == 200 and response.json()["revision"] == 2
    assert client.put(base, json=data).status_code == 409
    task = client.post(base + "/render", json={"revision": 2})
    assert task.status_code == 200 and task.json()["status"] == "queued"
    assert len(client.get(base).json()["versions"]) == 1
    assert client.get(base + "/versions/" + "a" * 64 + "/media").status_code == 422
    assert client.get(base + "/versions/invalid/media").status_code == 422


def test_worker_restores_incomplete_local_job_from_frozen_version(archive):
    _, projects, db, videos, draft, queue = archive
    draft = save(draft, segments(videos), db)
    job = remix.submit(draft["id"], draft["revision"], queue, projects_root=projects, db_path=db)
    worker = ProductionQueueWorker(queue, projects)
    assert "published_remix" in worker.handlers
    assert worker.inspect_parent(job)["status"] == "queued"


def test_missing_source_fails_retryably_without_exposing_partial_output(archive):
    source, projects, db, videos, draft, queue = archive
    draft = save(draft, segments(videos), db)
    job = remix.submit(draft["id"], draft["revision"], queue, projects_root=projects, db_path=db)
    (source / videos[0]["name"]).unlink()
    outcome = ProductionQueueWorker(queue, projects).run_once()
    assert outcome["status"] == "failed" and outcome["retryable"]
    assert remix.versions(draft["id"], projects_root=projects, db_path=db)[0]["status"] == "failed"
    with pytest.raises(clips.ClipIndexError):
        remix.output_path(draft["id"], job["parent_job_id"], projects_root=projects, db_path=db)
    assert queue.retry(job["job_id"])["status"] == "queued"


@pytest.mark.parametrize("frame_counts", [[30, 30, 30, 30], [33, 23, 13, 51]])
def test_real_ffmpeg_two_sources_audio_and_qa(tmp_path, monkeypatch, frame_counts):
    pair = resolve_ffmpeg_pair()
    if not pair: pytest.skip("FFmpeg not installed")
    ffmpeg, ffprobe = pair
    source, projects = tmp_path / "sources", tmp_path / "projects"
    source.mkdir(); projects.mkdir()
    for name, color, size, audio in [("red.mp4", "red", "160x90", True), ("blue.mp4", "blue", "90x160", False)]:
        cmd = [ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", f"color={color}:size={size}:rate=25:duration=5"]
        if audio: cmd += ["-f", "lavfi", "-i", "sine=frequency=600:sample_rate=48000:duration=5"]
        subprocess.run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "5", str(source / name)], check=True, capture_output=True)
    db = tmp_path / "index.sqlite3"
    monkeypatch.setattr(clips, "DB_PATH", db); monkeypatch.setattr(clips, "configured_source", lambda: source)
    clips.scan(source, db_path=db, ffprobe=ffprobe)
    videos = {v["name"]: v for v in clips.list_videos(db_path=db)}
    draft = remix.create("真实编码测试", projects_root=projects, db_path=db)
    # Include lowered, muted, original audio AND an audio-less clip.
    rows = [{"id": str(n), "video_id": videos[name]["id"], "start_seconds": .2, "end_seconds": .2 + frame_counts[n] / 30,
             "audio_mode": mode} for n, (name, mode) in enumerate([
                 ("red.mp4", "original"), ("red.mp4", "lowered"), ("blue.mp4", "original"), ("red.mp4", "mute")])]
    draft = save(draft, rows, db)
    queue = ProductionQueue(tmp_path / "queue.sqlite3", projects)
    job = remix.submit(draft["id"], draft["revision"], queue, projects_root=projects, db_path=db)
    worker = ProductionQueueWorker(queue, projects)
    outcome = worker.run_once()
    assert outcome["status"] == "completed", outcome
    path = remix.output_path(draft["id"], job["parent_job_id"], projects_root=projects, db_path=db)
    result = remix.versions(draft["id"], projects_root=projects, db_path=db)[0]
    assert result["qa"]["status"] == "passed" and result["duration_seconds"] == 4
    decoded = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-vn", "-ar", "48000", "-ac", "1", "-f", "f32le", "-"], capture_output=True, check=True)
    audio = np.frombuffer(decoded.stdout, dtype="<f4")
    boundaries = np.concatenate(([0], np.cumsum(frame_counts))) / 30
    rms = [float(np.sqrt(np.mean(audio[int((boundaries[n] + .2 * frame_counts[n] / 30) * 48000):int((boundaries[n] + .8 * frame_counts[n] / 30) * 48000)] ** 2))) for n in range(4)]
    assert -13 < 20 * np.log10(rms[1] / rms[0]) < -11
    assert rms[2] < .00001 and rms[3] < .00001
    # Decode every frame, including exact cut frames; timestamp seeking rounds to frames.
    raw = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-vf", "crop=20:20:(iw-20)/2:(ih-20)/2", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    colors = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 20 * 20, 3).mean(axis=1)
    assert len(colors) == 120
    for n, pixels in enumerate(colors):
        assert pixels[2 if sum(frame_counts[:2]) <= n < sum(frame_counts[:3]) else 0] > 180, (n, pixels)
    app = FastAPI(); app.include_router(api.router)
    monkeypatch.setattr(api, "_runtime", lambda _: (projects, queue))
    response = TestClient(app).get(f"/api/published-remixes/{draft['id']}/versions/{job['parent_job_id']}/media?download=true", headers={"Range": "bytes=0-127"})
    assert response.status_code == 206 and len(response.content) == 128 and "attachment" in response.headers["content-disposition"]
    # A failed new version must neither replace the playable old file nor expose a partial new file.
    from backlot import published_remix_render as renderer
    old_bytes = path.read_bytes()
    rows[0]["note"] = "new frozen version"
    draft = save(draft, rows, db)
    new_job = remix.submit(draft["id"], draft["revision"], queue, projects_root=projects, db_path=db)
    with monkeypatch.context() as patch:
        def fail(*args, **kwargs):
            raise clips.ClipIndexError("injected local encoder failure")
        patch.setattr(renderer, "_run", fail)
        assert worker.run_once()["status"] == "failed"
    assert path.read_bytes() == old_bytes
    with pytest.raises(clips.ClipIndexError):
        remix.output_path(draft["id"], new_job["parent_job_id"], projects_root=projects, db_path=db)
    assert queue.retry(new_job["job_id"])["status"] == "queued"
    assert worker.run_once()["status"] == "completed"
    assert path.read_bytes() == old_bytes
