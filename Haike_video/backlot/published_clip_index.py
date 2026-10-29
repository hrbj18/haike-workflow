"""Local, read-only-source index for previously published video files.

The database is intentionally separate from project production state. Automatic
text cues are candidates; only an editor can confirm an observed action.
"""

from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from backlot.media_index import media_content_fingerprint, probe_media
from lib.ffmpeg_locator import resolve_ffmpeg_pair


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / ".backlot" / "published-clips"
DB_PATH = DATA_DIR / "index.sqlite3"
CONFIG_PATH = DATA_DIR / "config.json"
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
TAGS = {
    "activity_candidate": "声画活动候选",
    "singing": "实际唱歌", "singing_mentioned": "提到唱歌", "dancing": "实际跳舞",
    "dancing_mentioned": "提到跳舞", "background_music": "背景音乐", "high_reaction": "热烈反应",
    "emotion_candidate": "情绪词候选", "laughing": "大笑", "applause": "鼓掌",
    "heart_gesture": "比心", "hug": "拥抱", "photo": "合影", "performance": "才艺表演",
    "language_exchange": "语言交流", "other": "其他",
}
ACTORS = {"unknown": "待辨认", "robot": "粤仔", "visitor": "游客", "group": "多人"}
TAG_ALIASES = {
    "唱歌": ("singing", "singing_mentioned"), "跳舞": ("dancing", "dancing_mentioned"),
    "音乐": ("background_music",), "大笑": ("laughing",), "鼓掌": ("applause",),
    "比心": ("heart_gesture",), "合影": ("photo",), "拥抱": ("hug",),
    "高情绪": ("high_reaction", "emotion_candidate"), "才艺": ("performance",),
}
CUE_TERMS = {
    "singing_mentioned": ("唱歌", "唱一首", "唱一下", "合唱", "sing", "song"),
    "dancing_mentioned": ("跳舞", "跳个舞", "跳一下", "dance"),
    "emotion_candidate": ("哇", "天呐", "好厉害", "太酷", "哈哈", "wow", "oh my god"),
}


class ClipIndexError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db_path(path: Path | None) -> Path:
    return Path(path or DB_PATH).resolve()


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = _db_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    had_locations = connection.execute("""SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='video_locations'""").fetchone() is not None
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY, path TEXT NOT NULL, name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
            duration_seconds REAL NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
            has_audio INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            transcript_status TEXT NOT NULL DEFAULT 'pending', transcript_model TEXT,
            error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS videos_active_name ON videos(active, name);
        CREATE TABLE IF NOT EXISTS video_locations (
            path TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES videos(id),
            size_bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS video_locations_video ON video_locations(video_id, active);
        CREATE TABLE IF NOT EXISTS transcript_spans (
            video_id TEXT NOT NULL REFERENCES videos(id), span_index INTEGER NOT NULL,
            start_seconds REAL NOT NULL, end_seconds REAL NOT NULL,
            text TEXT NOT NULL, language TEXT,
            PRIMARY KEY(video_id, span_index)
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL REFERENCES videos(id),
            start_seconds REAL NOT NULL, end_seconds REAL NOT NULL,
            peak_seconds REAL, summary TEXT NOT NULL,
            source_kind TEXT NOT NULL, source_ref TEXT,
            confidence REAL, review_status TEXT NOT NULL,
            evidence TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(video_id, source_kind, source_ref)
        );
        CREATE INDEX IF NOT EXISTS events_video_time ON events(video_id, start_seconds);
        CREATE INDEX IF NOT EXISTS events_status ON events(review_status);
        CREATE TABLE IF NOT EXISTS event_tags (
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            tag TEXT NOT NULL, PRIMARY KEY(event_id, tag)
        );
        CREATE INDEX IF NOT EXISTS event_tags_tag ON event_tags(tag, event_id);
        CREATE TABLE IF NOT EXISTS scan_failures (
            path TEXT PRIMARY KEY, reason TEXT NOT NULL, updated_at TEXT NOT NULL
        );
    """)
    if "description" not in {row[1] for row in connection.execute("PRAGMA table_info(videos)")}:
        connection.execute("ALTER TABLE videos ADD COLUMN description TEXT NOT NULL DEFAULT ''")
    if not had_locations:
        connection.execute("""INSERT OR IGNORE INTO video_locations(path,video_id,size_bytes,mtime_ns,active,updated_at)
            SELECT path,id,size_bytes,mtime_ns,active,updated_at FROM videos""")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def configure_source(root: Path, *, config_path: Path = CONFIG_PATH) -> Path:
    source = Path(root).resolve()
    if not source.is_dir():
        raise ClipIndexError("成片目录不存在")
    target = Path(config_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps({"source_root": str(source)}, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return source


def configured_source(*, config_path: Path = CONFIG_PATH) -> Path | None:
    if not Path(config_path).is_file():
        return None
    data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    source = Path(str(data.get("source_root") or "")).resolve()
    return source if source.is_dir() else None


def _within(source: Path, root: Path) -> bool:
    try:
        source.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def scan(root: Path, *, db_path: Path | None = None, ffprobe: str | None = None,
         config_path: Path | None = None) -> dict[str, Any]:
    source_root = Path(root).resolve()
    if not source_root.is_dir():
        raise ClipIndexError("成片目录不存在")
    if config_path is not None:
        configure_source(source_root, config_path=config_path)
    elif db_path is None:
        configure_source(source_root)
    pair = resolve_ffmpeg_pair() if not ffprobe else None
    probe_binary = ffprobe or (pair[1] if pair else None)
    if not probe_binary or not Path(probe_binary).is_file():
        raise ClipIndexError("缺少本机 FFprobe")
    files = sorted((p for p in source_root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES), key=lambda p: str(p).casefold())
    counts = {"found": len(files), "new": 0, "cached": 0, "renamed_or_duplicate": 0, "failed": 0}
    failures: list[dict[str, str]] = []
    with connect(db_path) as connection:
        seen: set[str] = set()
        for path in files:
            resolved = path.resolve()
            if not _within(resolved, source_root):
                counts["failed"] += 1
                failures.append({"name": path.name, "reason": "文件越出成片目录"})
                connection.execute("INSERT OR REPLACE INTO scan_failures(path,reason,updated_at) VALUES(?,?,?)",
                                   (str(resolved), "文件越出成片目录", _now()))
                continue
            stat = resolved.stat()
            existing = connection.execute("""SELECT v.id FROM video_locations l JOIN videos v ON v.id=l.video_id
                WHERE l.path=? AND l.size_bytes=? AND l.mtime_ns=? AND v.active=1""",
                (str(resolved), stat.st_size, stat.st_mtime_ns)).fetchone()
            if existing:
                seen.add(existing["id"])
                connection.execute("UPDATE video_locations SET active=1,updated_at=? WHERE path=?", (_now(), str(resolved)))
                counts["cached"] += 1
                continue
            try:
                identity = media_content_fingerprint(resolved)
                probe = probe_media(resolved, probe_binary)
                duration = float(probe["duration_seconds"])
                video = next((row for row in probe.get("streams", []) if row.get("codec_type") == "video"), None)
                if video is None:
                    raise ClipIndexError("文件没有视频流")
                has_audio = int(any(row.get("codec_type") == "audio" for row in probe.get("streams", [])))
            except Exception as exc:
                counts["failed"] += 1
                failures.append({"name": path.name, "reason": str(exc)[:250]})
                connection.execute("INSERT OR REPLACE INTO scan_failures(path,reason,updated_at) VALUES(?,?,?)",
                                   (str(resolved), str(exc)[:250], _now()))
                continue
            connection.execute("DELETE FROM scan_failures WHERE path=?", (str(resolved),))
            seen.add(identity)
            previous = connection.execute("SELECT id FROM videos WHERE id=?", (identity,)).fetchone()
            if previous:
                connection.execute("""UPDATE videos SET path=?, name=?, size_bytes=?, mtime_ns=?,
                    duration_seconds=?, width=?, height=?, has_audio=?, active=1, updated_at=?, error=NULL
                    WHERE id=?""", (str(resolved), resolved.name, stat.st_size, stat.st_mtime_ns,
                    duration, int(video.get("width") or 0), int(video.get("height") or 0),
                    has_audio, _now(), identity))
                counts["renamed_or_duplicate"] += 1
            else:
                connection.execute("""INSERT INTO videos
                    (id,path,name,size_bytes,mtime_ns,duration_seconds,width,height,has_audio,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (identity, str(resolved), resolved.name,
                    stat.st_size, stat.st_mtime_ns, duration, int(video.get("width") or 0),
                    int(video.get("height") or 0), has_audio, _now(), _now()))
                counts["new"] += 1
            connection.execute("""INSERT INTO video_locations(path,video_id,size_bytes,mtime_ns,active,updated_at)
                VALUES(?,?,?,?,1,?) ON CONFLICT(path) DO UPDATE SET video_id=excluded.video_id,
                size_bytes=excluded.size_bytes,mtime_ns=excluded.mtime_ns,active=1,updated_at=excluded.updated_at""",
                (str(resolved), identity, stat.st_size, stat.st_mtime_ns, _now()))
            connection.commit()  # Each video survives a later probe failure or interruption.
        present = {str(path.resolve()) for path in files}
        for row in connection.execute("SELECT path FROM video_locations WHERE active=1").fetchall():
            if row["path"] not in present:
                connection.execute("UPDATE video_locations SET active=0,updated_at=? WHERE path=?", (_now(), row["path"]))
        for row in connection.execute("SELECT id FROM videos WHERE active=1").fetchall():
            if row["id"] not in seen:
                connection.execute("UPDATE videos SET active=0, updated_at=? WHERE id=?", (_now(), row["id"]))
            else:
                locations = connection.execute("""SELECT path,size_bytes,mtime_ns FROM video_locations
                    WHERE video_id=? AND active=1 ORDER BY path""", (row["id"],)).fetchall()
                canonical = connection.execute("SELECT path FROM videos WHERE id=?", (row["id"],)).fetchone()[0]
                if locations and canonical not in {location["path"] for location in locations}:
                    chosen = locations[0]
                    connection.execute("""UPDATE videos SET path=?,name=?,size_bytes=?,mtime_ns=?,updated_at=?
                        WHERE id=?""", (chosen["path"], Path(chosen["path"]).name,
                        chosen["size_bytes"], chosen["mtime_ns"], _now(), row["id"]))
        for row in connection.execute("SELECT path FROM scan_failures").fetchall():
            if row["path"] not in present:
                connection.execute("DELETE FROM scan_failures WHERE path=?", (row["path"],))
        counts["active"] = connection.execute("SELECT COUNT(*) FROM videos WHERE active=1").fetchone()[0]
    return {**counts, "failures": failures}


def _seconds(value: Any, *, duration: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ClipIndexError("时间必须是数值") from exc
    if not math.isfinite(number) or number < 0 or number > duration:
        raise ClipIndexError("时间超出视频范围")
    return round(number, 3)


def _validate_range(start: Any, end: Any, duration: float, peak: Any = None) -> tuple[float, float, float | None]:
    low, high = _seconds(start, duration=duration), _seconds(end, duration=duration)
    if low >= high:
        raise ClipIndexError("片段结束时间必须晚于开始时间")
    at = None if peak is None else _seconds(peak, duration=duration)
    if at is not None and not low <= at <= high:
        raise ClipIndexError("精彩点必须位于片段内")
    return low, high, at


def _tags(value: Any) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > 12:
        raise ClipIndexError("至少选择一个标签，最多十二个")
    tags = sorted(set(str(tag) for tag in value))
    if any(tag not in TAGS for tag in tags):
        raise ClipIndexError("存在未定义的标签")
    return tags


def _event_row(connection: sqlite3.Connection, event_id: int) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        raise ClipIndexError("事件不存在")
    result = dict(row)
    result["tags"] = [item[0] for item in connection.execute("SELECT tag FROM event_tags WHERE event_id=? ORDER BY tag", (event_id,))]
    result["evidence"] = json.loads(result["evidence"])
    result["annotation"] = result["evidence"].get("annotation", {})
    return result


def save_event(video_id: str, payload: dict[str, Any], *, event_id: int | None = None,
               db_path: Path | None = None) -> dict[str, Any]:
    with connect(db_path) as connection:
        video = connection.execute("SELECT * FROM videos WHERE id=? AND active=1", (video_id,)).fetchone()
        if not video:
            raise ClipIndexError("视频未登记或已失效")
        old = _event_row(connection, event_id) if event_id is not None else None
        if old and old["video_id"] != video_id:
            raise ClipIndexError("事件不属于该视频")
        start, end, peak = _validate_range(payload.get("start_seconds", old["start_seconds"] if old else None),
            payload.get("end_seconds", old["end_seconds"] if old else None), float(video["duration_seconds"]),
            payload.get("peak_seconds", old["peak_seconds"] if old else None))
        summary = str(payload.get("summary", old["summary"] if old else "")).strip()
        if not summary or len(summary) > 500:
            raise ClipIndexError("事件摘要须为一至五百字")
        tags = _tags(payload.get("tags", old["tags"] if old else None))
        status = str(payload.get("review_status", old["review_status"] if old else "confirmed"))
        if status not in {"candidate", "confirmed", "rejected"}:
            raise ClipIndexError("审核状态无效")
        evidence = dict(old["evidence"] if old else {})
        annotation = dict(evidence.get("annotation") or {})
        if "annotation" in payload:
            if not isinstance(payload["annotation"], dict):
                raise ClipIndexError("事件详情必须是对象")
            annotation.update(payload["annotation"])
        if annotation:
            actor = annotation.get("actor", "unknown")
            if not isinstance(actor, str) or actor not in ACTORS:
                raise ClipIndexError("主体选项无效")
            annotation["actor"] = actor
            for field in ("action", "reaction"):
                value = str(annotation.get(field) or "").strip()
                if len(value) > 120:
                    raise ClipIndexError("动作或反应不能超过一百二十字")
                annotation[field] = value
            channels = annotation.get("channels", [])
            if not isinstance(channels, list) or any(not isinstance(c, str) or c not in {"audio", "video", "transcript"} for c in channels):
                raise ClipIndexError("核对渠道无效")
            annotation["channels"] = sorted(set(channels))
            context_start, context_end, _ = _validate_range(
                annotation.get("context_start", start), annotation.get("context_end", end),
                float(video["duration_seconds"]))
            if context_start > start or context_end < end:
                raise ClipIndexError("上下文区间必须包含整个事件")
            annotation.update(context_start=context_start, context_end=context_end)
            evidence["annotation"] = annotation
        if status == "confirmed":
            channels = annotation.get("channels", [])
            if "singing" in tags and "audio" not in channels:
                raise ClipIndexError("确认实际唱歌需要回听原声并勾选声音核对")
            if "dancing" in tags and "video" not in channels:
                raise ClipIndexError("确认实际跳舞需要连续观看并勾选画面核对")
        review_note = str(payload.get("review_note", evidence.get("review_note") or "")).strip()
        if len(review_note) > 1000:
            raise ClipIndexError("核对依据不能超过一千字")
        if status == "confirmed" and not review_note:
            raise ClipIndexError("确认事件前请填写画面或原声核对依据")
        if review_note:
            evidence["review_note"] = review_note
            evidence["reviewed_at"] = _now()
        if old:
            evidence["editor_modified_at"] = _now()
            connection.execute("""UPDATE events SET start_seconds=?,end_seconds=?,peak_seconds=?,
                summary=?,review_status=?,evidence=?,updated_at=? WHERE id=?""",
                (start, end, peak, summary, status, json.dumps(evidence, ensure_ascii=False), _now(), event_id))
            connection.execute("DELETE FROM event_tags WHERE event_id=?", (event_id,))
        else:
            cursor = connection.execute("""INSERT INTO events
                (video_id,start_seconds,end_seconds,peak_seconds,summary,source_kind,confidence,
                 review_status,evidence,created_at,updated_at)
                VALUES(?,?,?,?,?,'manual',1,?,?,?,?)""",
                (video_id, start, end, peak, summary, status,
                 json.dumps(evidence, ensure_ascii=False), _now(), _now()))
            event_id = int(cursor.lastrowid)
        connection.executemany("INSERT INTO event_tags(event_id,tag) VALUES(?,?)", [(event_id, tag) for tag in tags])
        return _event_row(connection, event_id)


def _add_candidate(connection: sqlite3.Connection, video_id: str, *, source_kind: str,
                   source_ref: str, start: float, end: float, summary: str,
                   tags: list[str], confidence: float, evidence: dict[str, Any]) -> None:
    existing = connection.execute("SELECT id FROM events WHERE video_id=? AND source_kind=? AND source_ref=?",
                                  (video_id, source_kind, source_ref)).fetchone()
    if existing:
        return  # Preserve editor changes and rejected suggestions.
    video = connection.execute("SELECT duration_seconds FROM videos WHERE id=?", (video_id,)).fetchone()
    if not video:
        raise ClipIndexError("视频未登记")
    low, high, peak = _validate_range(start, end, float(video[0]),
                                    evidence.get("peak_seconds") if source_kind == "joint_signals" else None)
    cursor = connection.execute("""INSERT INTO events
        (video_id,start_seconds,end_seconds,peak_seconds,summary,source_kind,source_ref,confidence,
         review_status,evidence,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,'candidate',?,?,?)""",
        (video_id, low, high, peak, summary[:500], source_kind, source_ref, confidence,
         json.dumps(evidence, ensure_ascii=False), _now(), _now()))
    connection.executemany("INSERT INTO event_tags(event_id,tag) VALUES(?,?)",
                           [(cursor.lastrowid, tag) for tag in tags])


def store_transcript(video_id: str, spans: list[dict[str, Any]], model: str, *,
                     db_path: Path | None = None) -> dict[str, int]:
    with connect(db_path) as connection:
        video = connection.execute("SELECT duration_seconds FROM videos WHERE id=? AND active=1", (video_id,)).fetchone()
        if not video:
            raise ClipIndexError("视频未登记或已失效")
        duration = float(video[0])
        normalized = []
        dropped = 0
        for index, row in enumerate(spans):
            # ASR can put the last token a few frames past the container duration.
            # Discard a wildly overshooting segment instead of losing this file's
            # otherwise valid transcription. Report dropped rows to the operator.
            start = float(row.get("start_seconds"))
            end = float(row.get("end_seconds"))
            if end > duration and end - duration <= 1.0:
                end = duration
            if start >= duration or end > duration or end - start < 0.001:
                dropped += 1
                continue
            low, high, _ = _validate_range(start, end, duration)
            normalized.append((video_id, index, low, high, str(row.get("text") or "")[:2000],
                               str(row.get("language") or "")[:32]))
        connection.execute("DELETE FROM transcript_spans WHERE video_id=?", (video_id,))
        connection.execute("DELETE FROM events WHERE video_id=? AND source_kind='transcript_cue' AND review_status='candidate'", (video_id,))
        connection.executemany("""INSERT INTO transcript_spans
            (video_id,span_index,start_seconds,end_seconds,text,language) VALUES(?,?,?,?,?,?)""", normalized)
        connection.execute("UPDATE videos SET transcript_status='completed',transcript_model=?,error=NULL,updated_at=? WHERE id=?",
                           (model, _now(), video_id))
        for row in normalized:
            _, index, low, high, text, _ = row
            for tag, terms in CUE_TERMS.items():
                if any(term in text.lower() for term in terms):
                    _add_candidate(connection, video_id, source_kind="transcript_cue",
                                   source_ref=f"{model}:{index}:{tag}", start=low, end=high,
                                   summary=f"台词线索：{text}", tags=[tag], confidence=0.3,
                                   evidence={"kind": "transcript", "span_index": index, "text": text})
        return {"spans": len(normalized), "dropped_spans": dropped, "candidates": connection.execute(
            "SELECT COUNT(*) FROM events WHERE video_id=? AND source_kind='transcript_cue'", (video_id,)).fetchone()[0]}


def import_interaction_index(path: Path, *, db_path: Path | None = None) -> dict[str, int]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    identity = str((data.get("source") or {}).get("fingerprint") or "")
    if data.get("status") != "completed" or not identity:
        raise ClipIndexError("互动索引未完成或缺少来源指纹")
    with connect(db_path) as connection:
        video = connection.execute("SELECT * FROM videos WHERE id=? AND active=1", (identity,)).fetchone()
        if not video or abs(float(video["duration_seconds"]) - float(data.get("duration") or 0)) > 0.5:
            raise ClipIndexError("互动索引与已登记成片不匹配")
        before = connection.execute("SELECT COUNT(*) FROM events WHERE video_id=?", (identity,)).fetchone()[0]
        for event in data.get("events") or []:
            text = " ".join([str(event.get("summary") or ""), *[str(item.get("label") or "") for item in event.get("highlights") or []]])
            tags = ["other"]
            if "比心" in text:
                tags = ["heart_gesture"]
            elif "合影" in text or "合照" in text:
                tags = ["photo"]
            elif "鼓掌" in text:
                tags = ["applause"]
            peak = next((item.get("time") for item in event.get("highlights") or [] if item.get("time") is not None), None)
            _add_candidate(connection, identity, source_kind="interaction_import",
                           source_ref=f"{data.get('signature')}:{event.get('event_id')}",
                           start=float(event["start"]), end=float(event["end"]),
                           summary=str(event.get("summary") or "互动候选"), tags=tags,
                           confidence=float(event.get("confidence") or 0),
                           evidence={"kind": "interaction_index", "index_path": str(Path(path).resolve()),
                                     "event_id": event.get("event_id"), "peak_seconds": peak,
                                     "requires_review": event.get("requires_review", True)})
        after = connection.execute("SELECT COUNT(*) FROM events WHERE video_id=?", (identity,)).fetchone()[0]
        return {"imported": after - before}


def import_visual_overview(path: Path, *, db_path: Path | None = None) -> dict[str, int]:
    """Bring earlier sampled-frame observations in as reviewable cues, never facts."""
    source = Path(path).resolve()
    data = json.loads(source.read_text(encoding="utf-8"))
    identity = str(((data.get("task") or {}).get("source") or {}).get("fingerprint") or "")
    if data.get("status") != "overview_completed" or not identity:
        raise ClipIndexError("视觉概览未完成或缺少来源指纹")
    with connect(db_path) as connection:
        video = connection.execute("SELECT duration_seconds FROM videos WHERE id=? AND active=1", (identity,)).fetchone()
        if not video:
            raise ClipIndexError("视觉概览与已登记成片不匹配")
        duration = float(video[0])
        before = connection.execute("SELECT COUNT(*) FROM events WHERE video_id=?", (identity,)).fetchone()[0]
        chapters = data.get("chapters") or []
        if chapters and abs(float(chapters[-1].get("end_seconds") or 0) - duration) > 0.5:
            raise ClipIndexError("视觉概览时长与成片不匹配")
        for chapter in chapters:
            for index, item in enumerate(chapter.get("usable_ranges") or []):
                label = str(item.get("label") or "画面候选")
                start = float(item["start_seconds"])
                end = float(item["end_seconds"])
                if start == end:
                    start, end = max(0, start - 0.5), min(duration, end + 0.5)
                tag = "other"
                if "比心" in label:
                    tag = "heart_gesture"
                elif "合影" in label or "合照" in label:
                    tag = "photo"
                elif "语言" in label or "西班牙语" in label:
                    tag = "language_exchange"
                _add_candidate(connection, identity, source_kind="visual_overview",
                               source_ref=f"{(data.get('task') or {}).get('task_fingerprint')}:{chapter.get('chapter_id')}:{index}",
                               start=start, end=end, summary=f"画面采样线索：{label}", tags=[tag],
                               confidence=min(0.5, float(item.get("confidence") or 0)),
                               evidence={"kind": "sampled_frames", "index_path": str(source),
                                         "cells": item.get("evidence_cell_ids") or [],
                                         "range_is_sampled_not_cutpoint": True})
        after = connection.execute("SELECT COUNT(*) FROM events WHERE video_id=?", (identity,)).fetchone()[0]
        return {"imported": after - before}


def _video_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data.pop("path", None)  # Local paths are never browser input.
    data.pop("mtime_ns", None)
    return data


def _review_counts(connection: sqlite3.Connection, video_id: str) -> dict[str, int]:
    row = connection.execute("""SELECT
        SUM(CASE WHEN review_status='candidate' THEN 1 ELSE 0 END),
        SUM(CASE WHEN review_status='confirmed' THEN 1 ELSE 0 END)
        FROM events WHERE video_id=?""", (video_id,)).fetchone()
    return {"candidate_count": int(row[0] or 0), "confirmed_count": int(row[1] or 0)}


def list_videos(*, db_path: Path | None = None, limit: int = 500) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        return [{**_video_dict(row), **_review_counts(connection, row["id"])} for row in connection.execute(
            "SELECT * FROM videos WHERE active=1 ORDER BY name LIMIT ?", (min(1000, max(1, limit)),)).fetchall()]


def get_video(video_id: str, *, db_path: Path | None = None) -> dict[str, Any]:
    with connect(db_path) as connection:
        row = connection.execute("SELECT * FROM videos WHERE id=? AND active=1", (video_id,)).fetchone()
        if not row:
            raise ClipIndexError("视频未登记或已失效")
        result = _video_dict(row)
        result["events"] = [_event_row(connection, int(item[0])) for item in connection.execute(
            "SELECT id FROM events WHERE video_id=? ORDER BY start_seconds,id", (video_id,))]
        result.update(_review_counts(connection, video_id))
        result["transcript"] = [dict(item) for item in connection.execute(
            "SELECT span_index,start_seconds,end_seconds,text,language FROM transcript_spans WHERE video_id=? ORDER BY span_index", (video_id,))]
        return result


def save_description(video_id: str, description: str, *, db_path: Path | None = None) -> dict[str, Any]:
    value = str(description).strip()
    if len(value) > 1000:
        raise ClipIndexError("视频摘要不能超过一千字")
    with connect(db_path) as connection:
        cursor = connection.execute("UPDATE videos SET description=?,updated_at=? WHERE id=? AND active=1",
                                    (value, _now(), video_id))
        if cursor.rowcount != 1:
            raise ClipIndexError("视频未登记或已失效")
    return get_video(video_id, db_path=db_path)


def media_path(video_id: str, *, source_root: Path, db_path: Path | None = None) -> Path:
    with connect(db_path) as connection:
        row = connection.execute("SELECT path,id FROM videos WHERE id=? AND active=1", (video_id,)).fetchone()
        if not row:
            raise ClipIndexError("视频未登记或已失效")
        path = Path(row["path"]).resolve()
        if not _within(path, Path(source_root)) or not path.is_file():
            raise ClipIndexError("原片已经移动或不在登记目录")
        if media_content_fingerprint(path) != row["id"]:
            raise ClipIndexError("原片内容已变化，请重新扫描")
        return path


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search(query: str = "", *, tag: str = "", confirmed_only: bool = False,
           actor: str = "", reaction: str = "", review_status: str = "",
           db_path: Path | None = None, limit: int = 100) -> list[dict[str, Any]]:
    query = str(query or "").strip()[:120]
    if actor and actor not in ACTORS:
        raise ClipIndexError("主体选项无效")
    if review_status not in {"", "candidate", "confirmed", "rejected"}:
        raise ClipIndexError("审核状态无效")
    structured = bool(actor or reaction or review_status)
    tag = str(tag or "").strip()
    if tag and tag not in TAGS and tag not in TAG_ALIASES:
        raise ClipIndexError("未知标签")
    selected_tags = TAG_ALIASES.get(tag, (tag,)) if tag else ()
    terms = TAG_ALIASES.get(query, ())
    maximum = min(500, max(1, int(limit)))
    results: list[dict[str, Any]] = []
    with connect(db_path) as connection:
        rows = connection.execute("""SELECT e.*,v.name,v.duration_seconds,
            GROUP_CONCAT(t.tag) AS tag_list FROM events e JOIN videos v ON v.id=e.video_id
            JOIN event_tags t ON t.event_id=e.id WHERE v.active=1
            GROUP BY e.id ORDER BY e.start_seconds,e.id""").fetchall()
        for row in rows:
            if not query and not selected_tags and not confirmed_only and not structured:
                break  # The empty search is a video library, not every candidate.
            tags = str(row["tag_list"] or "").split(",")
            if (row["review_status"] == "rejected" and review_status != "rejected") or (confirmed_only and row["review_status"] != "confirmed"):
                continue
            annotation = json.loads(row["evidence"]).get("annotation", {})
            if review_status and row["review_status"] != review_status:
                continue
            if actor and annotation.get("actor", "unknown") != actor:
                continue
            if reaction and reaction.casefold() not in annotation.get("reaction", "").casefold():
                continue
            if selected_tags and not set(selected_tags).intersection(tags):
                continue
            searchable = " ".join([str(row["summary"]), annotation.get("action", ""),
                                   annotation.get("reaction", ""), ACTORS.get(annotation.get("actor"), "")])
            text_match = query.casefold() in searchable.casefold()
            tag_match = bool(set(terms).intersection(tags)) or any(query == TAGS[t] for t in tags)
            if query and not (text_match or tag_match):
                continue
            score = (10 if row["review_status"] == "confirmed" else 3) + (2 if tag_match else 0)
            results.append({"kind": "event", "id": row["id"], "video_id": row["video_id"], "name": row["name"],
                            "start_seconds": row["start_seconds"], "end_seconds": row["end_seconds"],
                            "summary": row["summary"], "tags": tags, "review_status": row["review_status"],
                            "match_source": "confirmed_tag" if tag_match and row["review_status"] == "confirmed"
                            else "candidate_tag" if tag_match else "event_summary", "score": score})
        if not selected_tags and not confirmed_only and not structured:
            if query:
                for row in connection.execute("""SELECT t.*,v.name FROM transcript_spans t
                    JOIN videos v ON v.id=t.video_id WHERE v.active=1 AND t.text LIKE ? ESCAPE '\\'
                    ORDER BY t.video_id,t.start_seconds LIMIT ?""", (_like(query), maximum * 4)):
                    results.append({"kind": "transcript", "id": row["span_index"], "video_id": row["video_id"],
                                    "name": row["name"], "start_seconds": row["start_seconds"],
                                    "end_seconds": row["end_seconds"], "summary": row["text"],
                                    "tags": [], "review_status": "unreviewed", "match_source": "transcript", "score": 2})
            for row in connection.execute("""SELECT * FROM videos WHERE active=1
                AND (name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\') ORDER BY name LIMIT ?""",
                                          (_like(query), _like(query), maximum)):
                counts = _review_counts(connection, row["id"])
                results.append({"kind": "video", "id": row["id"], "video_id": row["id"], "name": row["name"],
                                "start_seconds": 0, "end_seconds": min(15, row["duration_seconds"]),
                                "summary": row["description"] or "尚未填写作品摘要；打开原片可核对并补充。",
                                "tags": [], "review_status": "unreviewed",
                                "transcript_status": row["transcript_status"], **counts,
                                "match_source": "description" if query and query.casefold() in row["description"].casefold()
                                else "filename", "score": 1})
    results.sort(key=lambda item: (-item["score"], item["name"], item["start_seconds"]))
    return results[:maximum]


def summary(*, db_path: Path | None = None) -> dict[str, Any]:
    with connect(db_path) as connection:
        counts = {key: connection.execute(sql).fetchone()[0] for key, sql in {
            "videos": "SELECT COUNT(*) FROM videos WHERE active=1",
            "transcribed": "SELECT COUNT(*) FROM videos WHERE active=1 AND transcript_status='completed'",
            "transcription_failed": "SELECT COUNT(*) FROM videos WHERE active=1 AND transcript_status='failed'",
            "scan_failed": "SELECT COUNT(*) FROM scan_failures",
            "candidates": "SELECT COUNT(*) FROM events e JOIN videos v ON v.id=e.video_id WHERE v.active=1 AND e.review_status='candidate'",
            "confirmed": "SELECT COUNT(*) FROM events e JOIN videos v ON v.id=e.video_id WHERE v.active=1 AND e.review_status='confirmed'",
        }.items()}
    return {**counts, "source_root": str(configured_source() or ""), "tags": TAGS, "actors": ACTORS}
