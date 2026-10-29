"""Shared, additive media registry. Originals stay in their existing folders."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess

from backlot.material_catalog_import import file_sha256, read_material_catalog
from lib.ffmpeg_locator import resolve_ffmpeg_pair

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


class MaterialLibraryError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def data_dir():
    return Path(os.environ.get("OPENMONTAGE_MATERIAL_LIBRARY_DIR") or ROOT / ".backlot/material-library").resolve()


def number(value, label, minimum=0, maximum=864000):
    if isinstance(value, bool):
        raise MaterialLibraryError(f"{label}不能是布尔值")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise MaterialLibraryError(f"{label}无效") from exc
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise MaterialLibraryError(f"{label}超出范围")
    return result


def words(values, label, limit=16):
    if not isinstance(values, list) or len(values) > limit:
        raise MaterialLibraryError(f"{label}必须为不超过{limit}项的列表")
    if any(not isinstance(v, str) or not v.strip() or len(v) > 160 for v in values):
        raise MaterialLibraryError(f"{label}含无效文字")
    return list(dict.fromkeys(v.strip() for v in values))


@contextmanager
def connect(db_path=None):
    path = Path(db_path or data_dir() / "library.sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=30000")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS library_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
        INSERT OR IGNORE INTO library_meta VALUES('version','1');
        CREATE TABLE IF NOT EXISTS media (
          id TEXT PRIMARY KEY,sha256 TEXT NOT NULL UNIQUE,title TEXT NOT NULL,
          bytes INTEGER NOT NULL,duration REAL NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS locations (
          path TEXT PRIMARY KEY,media_id TEXT NOT NULL REFERENCES media(id),
          bytes INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS locations_media ON locations(media_id);
        CREATE TABLE IF NOT EXISTS origins (
          id TEXT PRIMARY KEY,media_id TEXT NOT NULL REFERENCES media(id),
          platform TEXT NOT NULL,source_url TEXT NOT NULL,video_id TEXT NOT NULL,
          title TEXT NOT NULL,rights_status TEXT NOT NULL,catalog TEXT NOT NULL,imported_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS clips (
          id TEXT PRIMARY KEY,media_id TEXT NOT NULL REFERENCES media(id),start REAL NOT NULL,end REAL NOT NULL,
          observation TEXT NOT NULL,review_status TEXT NOT NULL,metadata TEXT NOT NULL,
          task_id TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS clips_media_time ON clips(media_id,start,end);
        CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY,payload TEXT NOT NULL,submission TEXT);
        CREATE TABLE IF NOT EXISTS selections (
          id TEXT PRIMARY KEY,plan_id TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS selections_plan ON selections(plan_id,created_at);
        CREATE TABLE IF NOT EXISTS acquisition (
          id TEXT PRIMARY KEY,plan_id TEXT NOT NULL,round INTEGER NOT NULL,payload TEXT NOT NULL,
          status TEXT NOT NULL,UNIQUE(plan_id,round));
        CREATE TABLE IF NOT EXISTS failures (path TEXT PRIMARY KEY,reason TEXT NOT NULL,updated_at TEXT NOT NULL);
    """)
    try:
        if db.execute("SELECT value FROM library_meta WHERE key='version'").fetchone()[0] != "1":
            raise MaterialLibraryError("素材库版本不支持，请先迁移")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def probe(path):
    pair = resolve_ffmpeg_pair()
    if not pair:
        raise MaterialLibraryError("未找到项目 FFmpeg/ffprobe")
    try:
        run = subprocess.run([pair[1], "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                             capture_output=True, text=True, encoding="utf-8", timeout=45)
        info = json.loads(run.stdout)
        stream = next(s for s in info["streams"] if s.get("codec_type") == "video")
        duration = number(info.get("format", {}).get("duration", stream.get("duration")), "素材时长", .1)
        width, height = int(stream["width"]), int(stream["height"])
        if run.returncode or min(width, height) < 2:
            raise ValueError()
        # Decode both ends before the file is eligible for registration.
        for stamp in (0, max(0, duration - .15)):
            decoded = subprocess.run([pair[0], "-v", "error", "-ss", str(stamp), "-i", str(path),
                                      "-frames:v", "1", "-an", "-f", "null", "-"],
                                     capture_output=True, timeout=45)
            if decoded.returncode or decoded.stderr:
                raise ValueError()
    except (ValueError, KeyError, StopIteration, OSError, subprocess.TimeoutExpired) as exc:
        raise MaterialLibraryError(f"视频探测或解码失败：{Path(path).name}") from exc
    return {"duration": duration, "width": width, "height": height}


def prepare_media(path, metadata=None, *, db_path=None):
    path = Path(path).resolve()
    if not path.is_file() or path.suffix.lower() not in SUFFIXES:
        raise MaterialLibraryError("素材文件不存在或格式不支持")
    stat = path.stat()
    sha = file_sha256(path)
    with connect(db_path) as db:
        cached = db.execute("SELECT duration,width,height FROM media WHERE sha256=?", (sha,)).fetchone()
    info = dict(cached) if cached else probe(path)
    if path.stat().st_mtime_ns != stat.st_mtime_ns or path.stat().st_size != stat.st_size:
        raise MaterialLibraryError("登记时素材正在变化，请稍后重试")
    meta = metadata or {}
    return {"id": "MAT-" + sha, "sha256": sha, "path": str(path), "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns, "title": str(meta.get("title") or path.stem)[:160],
            **info, "origin": {k: str(meta.get(k) or "")[:2000] for k in
                               ("platform", "source_url", "video_id", "rights_status", "catalog")}}


def register_prepared(items, *, db_path=None):
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        for item in items:
            db.execute("INSERT OR IGNORE INTO media VALUES(?,?,?,?,?,?,?,?)",
                       (item["id"], item["sha256"], item["title"], item["bytes"], item["duration"],
                        item["width"], item["height"], now()))
            db.execute("INSERT INTO locations VALUES(?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
                       "media_id=excluded.media_id,bytes=excluded.bytes,mtime_ns=excluded.mtime_ns,updated_at=excluded.updated_at",
                       (item["path"], item["id"], item["bytes"], item["mtime_ns"], now()))
            origin = {**item["origin"], "media_id": item["id"], "title": item["title"]}
            db.execute("INSERT OR IGNORE INTO origins VALUES(?,?,?,?,?,?,?,?,?)",
                       (digest(origin), item["id"], origin["platform"], origin["source_url"], origin["video_id"],
                        item["title"], origin["rights_status"] or "unknown", origin["catalog"], now()))
            db.execute("DELETE FROM failures WHERE path=?", (item["path"],))
    return {"registered": len(items), "media_ids": list(dict.fromkeys(item["id"] for item in items))}


def ingest_catalog(path, *, workspace_root=None, db_path=None):
    path = Path(path).resolve()
    entries = read_material_catalog(path, workspace_root=Path(workspace_root or ROOT.parent))
    # Whole-batch validation before writing registry rows.
    items = [prepare_media(entry["source"], {**entry, "catalog": str(path)}, db_path=db_path) for entry in entries]
    return register_prepared(items, db_path=db_path)


def register_file(path, metadata=None, *, db_path=None):
    return register_prepared([prepare_media(path, metadata, db_path=db_path)], db_path=db_path)


def scan_folder(path, *, db_path=None, limit=200):
    root = Path(path).resolve()
    if not root.is_dir():
        raise MaterialLibraryError("素材文件夹不存在")
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUFFIXES)
    if len(files) > limit:
        raise MaterialLibraryError(f"本次目录超过{limit}条，请按子目录分批登记")
    registered, failures = [], []
    for path in files:
        try:
            registered.extend(register_file(path, {"platform": "local", "catalog": str(root)}, db_path=db_path)["media_ids"])
        except MaterialLibraryError as exc:
            failures.append({"file": str(path), "reason": str(exc)})
            with connect(db_path) as db:
                db.execute("INSERT OR REPLACE INTO failures VALUES(?,?,?)", (str(path), str(exc), now()))
    return {"registered": len(registered), "media_ids": registered, "failures": failures}


def resolve_media(media_id, *, db_path=None, verify_hash=True):
    with connect(db_path) as db:
        item = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
        paths = db.execute("SELECT * FROM locations WHERE media_id=? ORDER BY updated_at DESC,path", (media_id,)).fetchall()
    if item:
        for location in paths:
            path = Path(location["path"])
            if path.is_file() and path.stat().st_size == item["bytes"]:
                if not verify_hash or file_sha256(path) == item["sha256"]:
                    return path
    raise MaterialLibraryError("素材文件缺失或内容已变化，请重新登记；旧证据不可沿用")


def list_media(query="", *, db_path=None, limit=100):
    limit = int(number(limit, "查询上限", 1, 500))
    with connect(db_path) as db:
        rows = db.execute("SELECT m.*,(SELECT count(*) FROM clips c WHERE c.media_id=m.id) clip_count "
                          "FROM media m WHERE m.title LIKE ? OR EXISTS(SELECT 1 FROM origins o WHERE "
                          "o.media_id=m.id AND o.title LIKE ?) ORDER BY m.created_at DESC LIMIT ?",
                          (f"%{query[:160]}%", f"%{query[:160]}%", limit)).fetchall()
    return [dict(row) for row in rows]


def get_media(media_id, *, db_path=None):
    with connect(db_path) as db:
        row = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
        if not row:
            raise MaterialLibraryError("素材ID不存在")
        result = dict(row)
        result["origins"] = [dict(x) for x in db.execute("SELECT * FROM origins WHERE media_id=?", (media_id,))]
        result["locations"] = [dict(x) for x in db.execute("SELECT * FROM locations WHERE media_id=?", (media_id,))]
        result["clips"] = [clip_row(x) for x in db.execute("SELECT * FROM clips WHERE media_id=? ORDER BY start", (media_id,))]
    return result


def clip_row(row):
    result = dict(row)
    result["metadata"] = json.loads(result["metadata"])
    return result


def list_clips(query="", *, db_path=None, limit=100):
    limit = int(number(limit, "查询上限", 1, 500))
    with connect(db_path) as db:
        rows = db.execute("SELECT c.*,m.title FROM clips c JOIN media m ON m.id=c.media_id "
                          "WHERE c.observation LIKE ? OR c.metadata LIKE ? ORDER BY c.updated_at DESC LIMIT ?",
                          (f"%{query[:160]}%", f"%{query[:160]}%", limit)).fetchall()
    return [clip_row(row) for row in rows]


def summary(*, db_path=None):
    with connect(db_path) as db:
        return {"version": 1, "media": db.execute("SELECT count(*) FROM media").fetchone()[0],
                "locations": db.execute("SELECT count(*) FROM locations").fetchone()[0],
                "clips": db.execute("SELECT count(*) FROM clips").fetchone()[0],
                "confirmed": db.execute("SELECT count(*) FROM clips WHERE review_status='confirmed'").fetchone()[0],
                "failures": [dict(row) for row in db.execute("SELECT * FROM failures LIMIT 20")]}


def sync_published(*, db_path=None, published_db=None):
    """Register existing sources; transfer event *candidates*, never invent visual QA."""
    from backlot.published_clip_index import connect as published_connect
    output = []
    with published_connect(published_db) as old:
        videos = [dict(row) for row in old.execute("SELECT * FROM videos")]
        for video in videos:
            paths = [Path(row[0]) for row in old.execute("SELECT path FROM video_locations WHERE video_id=?", (video["id"],))]
            found = next((path for path in paths if path.is_file()), None)
            if found is None:
                continue
            media_id = register_file(found, {"platform": "local", "title": video["name"],
                                            "catalog": "published-clips:" + video["id"]}, db_path=db_path)["media_ids"][0]
            with connect(db_path) as db:
                for event in old.execute("SELECT * FROM events WHERE video_id=?", (video["id"],)):
                    identity = "PUB-" + digest([video["id"], event["id"]])
                    meta = {"imported_review_status": event["review_status"], "analysis_required": True,
                            "source_ref": event["source_ref"], "tags": [row[0] for row in old.execute(
                                "SELECT tag FROM event_tags WHERE event_id=?", (event["id"],))]}
                    db.execute("INSERT OR IGNORE INTO clips VALUES(?,?,?,?,?,?,?,?,?)",
                               (identity, media_id, event["start_seconds"], event["end_seconds"], event["summary"],
                                "candidate", json.dumps(meta, ensure_ascii=False), "published-index", now()))
            output.append(media_id)
    return {"registered": len(output), "media_ids": output, "note": "事件可检索，裁切后采用前仍需画面确认"}
