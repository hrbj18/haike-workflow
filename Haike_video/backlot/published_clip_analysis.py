"""Local signal evidence, deliberately not a semantic song/dance classifier."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
import uuid
from pathlib import Path

import numpy as np

from backlot import published_clip_index as index
from backlot.material_audio_envelope import decode_envelope, envelope_identity
from backlot.material_motion_timeline import build_motion_timeline, motion_identity
from lib.ffmpeg_locator import resolve_ffmpeg_pair
from lib.subprocess_window import no_window_kwargs

VERSION = "published-signals-v2.1"
STEP = .5
LIMITATION = "声音变响可能是配乐，画面变化可能是运镜或切镜；需回听和连续观看，不能据此确认歌舞或热烈反应。"


def ensure_tables(connection):
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS clip_analysis (
            video_id TEXT PRIMARY KEY REFERENCES videos(id), signature TEXT NOT NULL,
            status TEXT NOT NULL, token TEXT NOT NULL, started REAL NOT NULL,
            result TEXT, error TEXT, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS clip_benchmark (
            video_id TEXT PRIMARY KEY REFERENCES videos(id), stratum TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', truth TEXT NOT NULL DEFAULT '[]',
            note TEXT NOT NULL DEFAULT '', channels TEXT NOT NULL DEFAULT '[]',
            prediction TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL
        );
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(clip_benchmark)")}
    if "prediction_frozen" not in columns:
        connection.execute("ALTER TABLE clip_benchmark ADD COLUMN prediction_frozen INTEGER NOT NULL DEFAULT 0")
        connection.execute("UPDATE clip_benchmark SET prediction_frozen=1 WHERE status='reviewed'")
        connection.commit()


def analysis_status(video_id, *, db_path=None):
    index.get_video(video_id, db_path=db_path)
    with index.connect(db_path) as connection:
        ensure_tables(connection)
        row = connection.execute("SELECT * FROM clip_analysis WHERE video_id=?", (video_id,)).fetchone()
    if not row:
        return {"status": "pending", "result": None}
    return {"status": row["status"], "error": row["error"], "updated_at": row["updated_at"],
            "result": json.loads(row["result"]) if row["result"] else None}


def _run(*args, **kwargs):
    return subprocess.run(*args, **kwargs, **no_window_kwargs())


def decode_signals(path: Path, duration: float, has_audio: bool):
    if duration > 1800:
        raise index.ClipIndexError("单条成片超过三十分钟，请先分段建立分析")
    pair = resolve_ffmpeg_pair()
    if not pair:
        raise index.ClipIndexError("缺少本地 FFmpeg，请检查工作台媒体依赖")
    ffmpeg, _ = pair
    motion = build_motion_timeline(path, ffmpeg=str(ffmpeg), duration=duration, timeout=300, runner=_run)
    envelope = decode_envelope(path, ffmpeg=str(ffmpeg), duration=duration, timeout=300, runner=_run) if has_audio else None
    bins = int(math.ceil(duration / STEP))
    points = []
    for n in range(bins):
        audio = None
        if envelope is not None:
            hop = envelope["hop_ms"] / 1000
            values = envelope["rms_db"][int(n * STEP / hop):int((n + 1) * STEP / hop)]
            if len(values):
                audio = round(float(np.mean(values)) / 100, 2)
        scores = motion["scores"][int(n * STEP * motion["fps"]):int((n + 1) * STEP * motion["fps"])]
        points.append({"time": round(n * STEP, 3), "audio_db": audio,
                       "motion": round(float(np.mean(scores)), 5) if len(scores) else None})
    return points


def propose(points, transcript, duration):
    """Generate ranked windows without promoting lexical cues to actions."""
    audio_values = [p["audio_db"] for p in points if p["audio_db"] is not None]
    motion_values = [p["motion"] for p in points if p["motion"] is not None]
    baseline = float(np.median(audio_values)) if audio_values else -120
    motion_threshold = max(.035, float(np.percentile(motion_values, 75))) if motion_values else .035
    seeds = []
    for span in transcript:
        text = span["text"].lower()
        for tag, terms in index.CUE_TERMS.items():
            if any(term in text for term in terms):
                start, end = max(0, span["start_seconds"] - 1), min(duration, span["end_seconds"] + 5)
                seeds.append((start, end, tag, "台词及后续声画待核对：" + span["text"]))
    # Require sustained activity; an isolated cut must not be called a reaction.
    active = []
    for p in points:
        audio_rise = p["audio_db"] is not None and p["audio_db"] > max(-40, baseline + 4)
        movement = p["motion"] is not None and motion_threshold <= p["motion"] < .35
        if audio_rise and movement:
            active.append(p["time"])
    groups = []
    for at in active:
        if groups and at - groups[-1][-1] <= 1:
            groups[-1].append(at)
        else:
            groups.append([at])
    for group in groups:
        if len(group) >= 2:
            seeds.append((max(0, group[0] - 1), min(duration, group[-1] + 2),
                          "activity_candidate", "声音增强并伴随画面变化，待核对互动"))
    output = []
    for start, end, tag, summary in seeds:
        subset = [p for p in points if start <= p["time"] < end]
        if not subset or end <= start:
            continue
        def score(p):
            return min(1, max(0, (p["audio_db"] - baseline) / 12)) if p["audio_db"] is not None else 0
        peak = max(subset, key=lambda p: score(p) + min(1, (p["motion"] or 0) / .15))
        priority = round(min(1, .2 + score(peak) * .35 + min(1, (peak["motion"] or 0) / .15) * .35), 3)
        channels = ["video_signal"] + (["audio_signal"] if any(p["audio_db"] is not None for p in subset) else [])
        if tag != "activity_candidate":
            channels.append("transcript")
        output.append({"start_seconds": round(start, 3), "end_seconds": round(end, 3),
                       "peak_seconds": peak["time"], "tags": [tag], "summary": summary[:500],
                       "evidence": {"channels": channels, "priority": priority, "limitation": LIMITATION,
                                    "audio_baseline_db": round(baseline, 2), "motion_threshold": round(motion_threshold, 5),
                                    "peak_seconds": peak["time"], "version": VERSION,
                                    "annotation": {"actor": "unknown", "action": "", "reaction": "", "channels": [],
                                                   "context_start": round(max(0, start - 3), 3),
                                                   "context_end": round(min(duration, end + 3), 3)}}})
    # Merge near-identical same-tag windows, retain separate semantic labels.
    selected = []
    for row in sorted(output, key=lambda r: -r["evidence"]["priority"]):
        if any(row["tags"] == old["tags"] and interval_iou(row, old) > .5 for old in selected):
            continue
        selected.append(row)
        if len(selected) == 30:
            break
    return sorted(selected, key=lambda r: r["start_seconds"])


def interval_iou(a, b):
    overlap = max(0, min(a["end_seconds"], b["end_seconds"]) - max(a["start_seconds"], b["start_seconds"]))
    union = max(a["end_seconds"], b["end_seconds"]) - min(a["start_seconds"], b["start_seconds"])
    return overlap / union if union else 0


def analyze(video_id, *, source_root, db_path=None, force=False):
    video = index.get_video(video_id, db_path=db_path)
    path = index.media_path(video_id, source_root=source_root, db_path=db_path)
    signature = hashlib.sha256(json.dumps([VERSION, video_id, video["transcript_model"], video["transcript"],
        STEP, envelope_identity(), motion_identity()], sort_keys=True).encode()).hexdigest()
    token, started = uuid.uuid4().hex, time.time()
    with index.connect(db_path) as connection:
        ensure_tables(connection)
        connection.execute("BEGIN IMMEDIATE")
        old = connection.execute("SELECT * FROM clip_analysis WHERE video_id=?", (video_id,)).fetchone()
        if old and old["status"] == "running" and started - old["started"] < 900:
            return {"status": "running", "cached": False}
        if old and old["signature"] == signature and old["status"] == "completed" and not force:
            return {"status": "completed", "cached": True, "result": json.loads(old["result"])}
        connection.execute("""INSERT INTO clip_analysis VALUES(?,?,'running',?,?,NULL,NULL,?)
            ON CONFLICT(video_id) DO UPDATE SET signature=excluded.signature,status='running',token=excluded.token,
            started=excluded.started,result=NULL,error=NULL,updated_at=excluded.updated_at""",
                           (video_id, signature, token, started, index._now()))
    try:
        points = decode_signals(path, video["duration_seconds"], bool(video["has_audio"]))
        candidates = propose(points, video["transcript"], video["duration_seconds"])
        # Verify the source again after decoding, before attaching observations.
        index.media_path(video_id, source_root=source_root, db_path=db_path)
        result = {"version": VERSION, "signature": signature, "step_seconds": STEP,
                  "duration_seconds": video["duration_seconds"], "points": points,
                  "candidate_count": len(candidates), "candidates": candidates, "limitation": LIMITATION,
                  "channels": ["video_signal"] + (["audio_signal"] if video["has_audio"] else []),
                  "elapsed_seconds": round(time.time() - started, 3)}
        with index.connect(db_path) as connection:
            owner = connection.execute("SELECT token FROM clip_analysis WHERE video_id=?", (video_id,)).fetchone()
            if not owner or owner[0] != token:
                raise index.ClipIndexError("分析已由新的任务接管，请刷新状态")
            for previous in connection.execute("SELECT id,source_ref,evidence FROM events WHERE video_id=? AND source_kind='joint_signals' AND review_status='candidate'", (video_id,)).fetchall():
                if not previous["source_ref"].startswith(signature + ":") and not json.loads(previous["evidence"]).get("editor_modified_at"):
                    connection.execute("DELETE FROM events WHERE id=?", (previous["id"],))
            for row in candidates:
                ref = f"{signature}:{row['tags'][0]}:{row['start_seconds']}"
                index._add_candidate(connection, video_id, source_kind="joint_signals", source_ref=ref,
                    start=row["start_seconds"], end=row["end_seconds"], summary=row["summary"],
                    tags=row["tags"], confidence=0, evidence=row["evidence"])
            connection.execute("UPDATE clip_analysis SET status='completed',result=?,updated_at=? WHERE video_id=? AND token=?",
                               (json.dumps(result, ensure_ascii=False), index._now(), video_id, token))
        return {"status": "completed", "cached": False, "result": result}
    except Exception as exc:
        with index.connect(db_path) as connection:
            connection.execute("UPDATE clip_analysis SET status='failed',error=?,updated_at=? WHERE video_id=? AND token=?",
                               (str(exc)[:500], index._now(), video_id, token))
        raise


def seed_benchmark(*, db_path=None, count=10):
    """Freeze a deterministic, stratified *review set*, never auto-ground-truth."""
    with index.connect(db_path) as connection:
        ensure_tables(connection)
        existing = connection.execute("SELECT COUNT(*) FROM clip_benchmark").fetchone()[0]
        if existing:
            return {"created": 0, "total": existing}
        videos = index.list_videos(db_path=db_path)
        buckets = {"歌唱线索（需区分演唱/仅提及/配乐）": [], "舞蹈线索（需区分动作/仅提及）": [],
                   "热烈互动线索": [], "普通交流与负例核对": []}
        for video in videos:
            detail = index.get_video(video["id"], db_path=db_path)
            text = video["name"] + " ".join(s["text"] for s in detail["transcript"])
            bucket = (0 if any(t in text for t in ("唱", "sing", "song")) else
                      1 if any(t in text for t in ("舞", "dance")) else
                      2 if any(t in text for t in ("哈哈", "比心", "合影", "wow")) else 3)
            list(buckets.values())[bucket].append(video["id"])
        chosen = []
        while len(chosen) < count and any(buckets.values()):
            for stratum, identities in buckets.items():
                if identities and len(chosen) < count:
                    chosen.append((identities.pop(0), stratum))
        connection.executemany("INSERT INTO clip_benchmark(video_id,stratum,updated_at) VALUES(?,?,?)",
                               [(vid, stratum, index._now()) for vid, stratum in chosen])
    return {"created": len(chosen), "total": len(chosen)}


def benchmark_cases(*, db_path=None):
    with index.connect(db_path) as connection:
        ensure_tables(connection)
        rows = connection.execute("SELECT b.*,v.name,v.active FROM clip_benchmark b JOIN videos v ON v.id=b.video_id ORDER BY b.stratum,v.name").fetchall()
    return [{**dict(row), "truth": json.loads(row["truth"]), "channels": json.loads(row["channels"]),
             "prediction": json.loads(row["prediction"])} for row in rows]


def save_truth(video_id, payload, *, db_path=None):
    video = index.get_video(video_id, db_path=db_path)
    status = payload.get("status", "pending")
    if status not in {"pending", "reviewed"}:
        raise index.ClipIndexError("评估状态无效")
    channels = payload.get("channels", [])
    if not isinstance(channels, list) or any(not isinstance(c, str) or c not in {"audio", "video"} for c in channels):
        raise index.ClipIndexError("真值核对渠道无效")
    note = str(payload.get("note", "")).strip()
    if len(note) > 1000:
        raise index.ClipIndexError("真值说明不能超过一千字")
    if status == "reviewed" and (not note or "video" not in channels or (video["has_audio"] and "audio" not in channels)):
        raise index.ClipIndexError("完整复核需全片观看及原声回听，并填写依据；未完成请保存草稿")
    truth = payload.get("truth", [])
    if not isinstance(truth, list) or len(truth) > 200:
        raise index.ClipIndexError("真值应为不超过两百条的列表")
    normalized = []
    for row in truth:
        if not isinstance(row, dict):
            raise index.ClipIndexError("真值片段格式无效")
        start, end, _ = index._validate_range(row.get("start_seconds"), row.get("end_seconds"), video["duration_seconds"])
        tags = index._tags(row.get("tags"))
        if set(tags) & {"activity_candidate", "emotion_candidate"}:
            raise index.ClipIndexError("真值必须标记真实事件，不能使用未核实候选标签")
        normalized.append({"start_seconds": start, "end_seconds": end, "tags": tags})
    analysis = analysis_status(video_id, db_path=db_path)
    if status == "reviewed" and analysis["status"] != "completed":
        raise index.ClipIndexError("请先完成声画分析，才能冻结评估预测")
    with index.connect(db_path) as connection:
        ensure_tables(connection)
        previous = connection.execute("SELECT * FROM clip_benchmark WHERE video_id=?", (video_id,)).fetchone()
        if not previous:
            raise index.ClipIndexError("视频不属于固定评估集")
        # Freeze machine predictions on first full review; later editor actions cannot improve the score.
        predictions = previous["prediction"] if previous["prediction_frozen"] else json.dumps(
            (analysis.get("result") or {}).get("candidates", []), ensure_ascii=False)
        frozen = bool(previous["prediction_frozen"] or status == "reviewed")
        connection.execute("UPDATE clip_benchmark SET status=?,truth=?,note=?,channels=?,prediction=?,prediction_frozen=?,updated_at=? WHERE video_id=?",
                           (status, json.dumps(normalized), note, json.dumps(channels), predictions, int(frozen), index._now(), video_id))
    return next(c for c in benchmark_cases(db_path=db_path) if c["video_id"] == video_id)


def evaluate(cases):
    complete = [c for c in cases if c["status"] == "reviewed" and c.get("active", True)]
    tp = fp = fn = 0
    errors, overlaps = [], []
    for case in complete:
        truth, prediction = case["truth"], case["prediction"]
        pairs = sorted([(interval_iou(p, t), i, j) for i, p in enumerate(prediction) for j, t in enumerate(truth)
                        if set(p["tags"]) & set(t["tags"])], reverse=True)
        used_p, used_t = set(), set()
        for overlap, i, j in pairs:
            if overlap < .5 or i in used_p or j in used_t:
                continue
            used_p.add(i); used_t.add(j)
            overlaps.append(overlap)
            errors.extend([abs(prediction[i][k] - truth[j][k]) for k in ("start_seconds", "end_seconds")])
        tp += len(used_p); fp += len(prediction) - len(used_p); fn += len(truth) - len(used_t)
    tags = sorted({t for c in complete for row in c["truth"] for t in row["tags"]})
    return {"total": len(cases), "reviewed": len(complete), "pending": len(cases) - len(complete),
            "precision": tp / (tp + fp) if complete and tp + fp else None,
            "recall": tp / (tp + fn) if complete and tp + fn else None,
            "true_positive": tp, "false_positive": fp, "false_negative": fn,
            "mean_iou": sum(overlaps) / len(overlaps) if overlaps else None,
            "mean_boundary_error_seconds": sum(errors) / len(errors) if errors else None,
            "truth_tags": tags, "semantic_classifier": False,
            "quality_gate": "待完整复核及类别覆盖" if len(complete) < 10 else "需人工检查类别正负例覆盖后决定扩量"}
