"""Versioned edit decisions for the published-clip workbench."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from uuid import uuid4

from backlot import published_clip_index as clips
from lib.checkpoint import init_project

WORKFLOW = "published-remix"
VERSION = "published-remix-v1"
PROFILE = {"width": 720, "height": 1280, "fps": 30, "audio_rate": 48000, "fit": "contain"}


class RemixConflict(clips.ClipIndexError):
    pass


def _tables(c):
    c.executescript("""
        CREATE TABLE IF NOT EXISTS remix_drafts (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, revision INTEGER NOT NULL,
            payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS remix_versions (
            project_id TEXT NOT NULL REFERENCES remix_drafts(id), signature TEXT NOT NULL,
            revision INTEGER NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(project_id,signature));
    """)


def _directory(project_id, root):
    if not re.fullmatch(r"remix-[a-f0-9]{16}", str(project_id)):
        raise clips.ClipIndexError("二剪项目编号无效")
    root = Path(root).resolve()
    target = (root / project_id).resolve()
    if not target.is_relative_to(root):
        raise clips.ClipIndexError("项目目录越界")
    return target


def _atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name("." + uuid4().hex[:12] + ".tmp")
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _title(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 120:
        raise clips.ClipIndexError("项目名称须为一至一百二十字")
    return value.strip()


def _load(row):
    if row is None:
        raise clips.ClipIndexError("二剪项目不存在")
    return {**dict(row), "payload": json.loads(row["payload"])}


def create(title, *, projects_root, db_path=None):
    title = _title(title)
    identity = "remix-" + uuid4().hex[:16]
    directory = _directory(identity, projects_root)
    init_project(identity, title=title, pipeline_type=WORKFLOW, pipeline_dir=Path(projects_root))
    payload = {"version": VERSION, "profile": PROFILE, "segments": []}
    with clips.connect(db_path) as c:
        _tables(c)
        c.execute("INSERT INTO remix_drafts VALUES(?,?,1,?,?,?)",
                  (identity, title, json.dumps(payload), clips._now(), clips._now()))
    _atomic(directory / "artifacts" / "remix-workflow.json", {
        "workflow": WORKFLOW, "executor": "published_remix", "provider": "local-ffmpeg",
        "external_cost_cny": 0, "profile": PROFILE, "music": "source-only",
        "review_gate": "human-review-before-publication", "automatic_publication": False})
    return read(identity, db_path=db_path)


def read(identity, *, db_path=None):
    with clips.connect(db_path) as c:
        _tables(c)
        return _load(c.execute("SELECT * FROM remix_drafts WHERE id=?", (identity,)).fetchone())


def list_drafts(*, db_path=None):
    with clips.connect(db_path) as c:
        _tables(c)
        return [_load(r) for r in c.execute("SELECT * FROM remix_drafts ORDER BY updated_at DESC,id DESC LIMIT 200")]


def normalize_segments(segments, *, db_path=None):
    if not isinstance(segments, list) or len(segments) > 30:
        raise clips.ClipIndexError("选材篮最多三十段")
    output, identities, total_frames = [], set(), 0
    for row in segments:
        if not isinstance(row, dict):
            raise clips.ClipIndexError("片段格式无效")
        identity = row.get("id")
        if not isinstance(identity, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", identity) or identity in identities:
            raise clips.ClipIndexError("片段编号无效或重复")
        identities.add(identity)
        video = clips.get_video(str(row.get("video_id", "")), db_path=db_path)
        if any(isinstance(row.get(key), bool) for key in ("start_seconds", "end_seconds")):
            raise clips.ClipIndexError("片段时间必须是数值")
        start, end, _ = clips._validate_range(row.get("start_seconds"), row.get("end_seconds"), video["duration_seconds"])
        frame_count = int(math.floor((end - start) * PROFILE["fps"] + .5))
        if frame_count < 3:
            raise clips.ClipIndexError("片段至少保留0.1秒")
        audio = row.get("audio_mode", "original")
        role = row.get("role", "body")
        if audio not in ("original", "lowered", "mute") or role not in ("opening", "body", "ending"):
            raise clips.ClipIndexError("片段原声或用途选项无效")
        note = row.get("note", "")
        if not isinstance(note, str) or len(note) > 500:
            raise clips.ClipIndexError("片段备注不能超过五百字")
        event_id = row.get("event_id")
        event = next((e for e in video["events"] if e["id"] == event_id), None)
        if event_id is not None and event is None:
            raise clips.ClipIndexError("来源事件不属于该视频")
        total_frames += frame_count
        output.append({"id": identity, "video_id": video["id"], "source_name": video["name"],
            "start_seconds": start, "end_seconds": end, "frame_count": frame_count,
            "output_seconds": frame_count / PROFILE["fps"], "has_audio": bool(video["has_audio"]),
            "audio_mode": audio, "role": role, "note": note.strip(), "event_id": event_id,
            "source_review_status": event["review_status"] if event else "unreviewed"})
    if total_frames > 600 * PROFILE["fps"]:
        raise clips.ClipIndexError("本版二剪总时长最多十分钟")
    return output


def save(identity, payload, *, db_path=None):
    title = _title(payload.get("title"))
    segments = normalize_segments(payload.get("segments"), db_path=db_path)
    normalized = {"version": VERSION, "profile": PROFILE, "segments": segments}
    with clips.connect(db_path) as c:
        _tables(c)
        c.execute("BEGIN IMMEDIATE")
        current = _load(c.execute("SELECT * FROM remix_drafts WHERE id=?", (identity,)).fetchone())
        if type(payload.get("revision")) is not int or payload["revision"] != current["revision"]:
            raise RemixConflict("草稿已在其他页面更新，请重新打开后再编辑；本页内容尚未覆盖")
        if title != current["title"] or normalized != current["payload"]:
            c.execute("UPDATE remix_drafts SET title=?,payload=?,revision=revision+1,updated_at=? WHERE id=?",
                      (title, json.dumps(normalized, ensure_ascii=False), clips._now(), identity))
    return read(identity, db_path=db_path)


def version_dir(identity, signature, *, projects_root):
    if not re.fullmatch(r"[a-f0-9]{64}", str(signature)):
        raise clips.ClipIndexError("渲染版本编号无效")
    base = _directory(identity, projects_root)
    path = (base / "artifacts" / "remix" / signature[:24]).resolve()
    if not path.is_relative_to(base):
        raise clips.ClipIndexError("渲染目录越界")
    return path


def prepare(identity, revision, *, projects_root, db_path=None):
    draft = read(identity, db_path=db_path)
    if type(revision) is not int or draft["revision"] != revision:
        raise RemixConflict("草稿版本已变化，请保存并重新提交")
    segments = normalize_segments(draft["payload"]["segments"], db_path=db_path)
    if not segments:
        raise clips.ClipIndexError("请先加入至少一个片段")
    source_root = clips.configured_source()
    if source_root is None:
        raise clips.ClipIndexError("原片目录尚未配置")
    for video_id in {s["video_id"] for s in segments}:
        clips.media_path(video_id, source_root=source_root, db_path=db_path)
    frozen = {"version": VERSION, "project_id": identity, "revision": revision, "title": draft["title"],
              "profile": PROFILE, "source_root": str(source_root), "segments": segments}
    signature = hashlib.sha256(json.dumps(frozen, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    directory = version_dir(identity, signature, projects_root=projects_root)
    request_path = directory / "request.json"
    if not request_path.exists():
        _atomic(request_path, frozen)
    elif json.loads(request_path.read_text(encoding="utf-8")) != frozen:
        raise clips.ClipIndexError("版本目录已有不匹配清单，拒绝覆盖")
    with clips.connect(db_path) as c:
        _tables(c)
        c.execute("INSERT OR IGNORE INTO remix_versions VALUES(?,?,?,?)", (identity, signature, revision, clips._now()))
    return {"signature": signature, "revision": revision}


def submit(identity, revision, queue, *, projects_root, db_path=None):
    frozen = prepare(identity, revision, projects_root=projects_root, db_path=db_path)
    return queue.submit(project_id=identity, kind="published_remix", source="workbench", priority="normal",
        parent_job_id=frozen["signature"], frozen_request=frozen, revive=True,
        idempotency_key=f"published_remix:{identity}:{frozen['signature']}")


def versions(identity, *, projects_root, db_path=None):
    read(identity, db_path=db_path)
    with clips.connect(db_path) as c:
        rows = c.execute("SELECT * FROM remix_versions WHERE project_id=? ORDER BY revision DESC,created_at DESC", (identity,)).fetchall()
    result = []
    for row in rows:
        directory = version_dir(identity, row["signature"], projects_root=projects_root)
        status = {"status": "queued"}
        path = directory / "result.json"
        if path.exists():
            status = json.loads(path.read_text(encoding="utf-8"))
        result.append({**dict(row), **status})
    return result


def output_path(identity, signature, *, projects_root, db_path=None):
    read(identity, db_path=db_path)
    with clips.connect(db_path) as c:
        if not c.execute("SELECT 1 FROM remix_versions WHERE project_id=? AND signature=?", (identity, signature)).fetchone():
            raise clips.ClipIndexError("渲染版本未登记")
    directory = version_dir(identity, signature, projects_root=projects_root)
    result_path = directory / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
    path = (directory / "preview.mp4").resolve()
    if not path.is_relative_to(directory) or result.get("status") != "completed" or not path.is_file():
        raise clips.ClipIndexError("该版本尚未通过技术检查，请等待或重试")
    return path
