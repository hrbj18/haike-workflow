"""Offline transcription for the published-clip index."""

from __future__ import annotations

import os
import ctypes
from pathlib import Path
from typing import Any, Callable

from backlot.published_clip_index import ClipIndexError, _now, connect, media_path, store_transcript


def cached_small_model() -> Path:
    cache = Path(os.environ.get("HF_HUB_CACHE") or Path.home() / ".cache" / "huggingface" / "hub")
    snapshots = cache / "models--Systran--faster-whisper-small" / "snapshots"
    choices = sorted((p for p in snapshots.glob("*") if (p / "model.bin").is_file()), reverse=True)
    if not choices:
        raise ClipIndexError("未找到本地 faster-whisper-small 模型；本流程不会自动下载")
    return choices[0]


def load_model(path: Path | None = None, *, device: str = "auto") -> tuple[Any, str]:
    from faster_whisper import WhisperModel

    local = Path(path).resolve() if path else cached_small_model()
    if not (local / "model.bin").is_file():
        raise ClipIndexError("本地语音模型缺少 model.bin")
    if device not in {"auto", "cuda", "cpu"}:
        raise ClipIndexError("设备只能是 auto/cuda/cpu")
    selected = device
    if device == "auto" and os.name == "nt":
        try:
            ctypes.WinDLL("cublas64_12.dll")
            ctypes.WinDLL("cudnn64_9.dll")
            selected = "cuda"
        except OSError:
            selected = "cpu"
    try:
        model = WhisperModel(str(local), device=selected, compute_type="float16" if selected != "cpu" else "int8",
                             local_files_only=True)
        actual_device = selected
    except Exception:
        if device != "auto":
            raise
        model = WhisperModel(str(local), device="cpu", compute_type="int8", local_files_only=True)
        actual_device = "cpu"
    return model, f"faster-whisper-small:{local.name}:{actual_device}"


def transcribe_batch(*, source_root: Path, db_path: Path | None = None,
                     model_path: Path | None = None, device: str = "auto",
                     video_id: str | None = None, limit: int | None = None,
                     force: bool = False, progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    if limit is not None and limit < 1:
        raise ClipIndexError("limit 必须大于零")
    with connect(db_path) as connection:
        rows = connection.execute("SELECT id,name,has_audio,transcript_status,transcript_model FROM videos WHERE active=1 ORDER BY name").fetchall()
        targets = [dict(row) for row in rows if (video_id is None or row["id"] == video_id)]
    if video_id and not targets:
        raise ClipIndexError("指定视频不存在")
    if limit:
        targets = targets[:limit]
    if not targets:
        return {"total": 0, "processed": 0, "cached": 0, "failed": []}
    model = None
    model_identity = None
    processed = cached = 0
    failures = []
    for target in targets:
        if target["has_audio"]:
            if model is None:
                model, model_identity = load_model(model_path, device=device)
            identity = str(model_identity)
        else:
            identity = "no-audio"
        if not force and target["transcript_status"] == "completed" and target["transcript_model"] == identity:
            cached += 1
            if progress:
                progress({"name": target["name"], "status": "cached"})
            continue
        try:
            source = media_path(target["id"], source_root=source_root, db_path=db_path)
            with connect(db_path) as connection:
                connection.execute("UPDATE videos SET transcript_status='running',error=NULL,updated_at=? WHERE id=?",
                                   (_now(), target["id"]))
            if model is None or not target["has_audio"]:
                spans = []
            else:
                def run_current():
                    segments, info = model.transcribe(str(source), beam_size=3,
                        condition_on_previous_text=False, vad_filter=False, word_timestamps=False)
                    language = str(info.language or "")
                    return [{"start_seconds": float(seg.start), "end_seconds": float(seg.end),
                             "text": str(seg.text).strip(), "language": language}
                            for seg in segments if str(seg.text).strip() and float(seg.end) > float(seg.start)]
                try:
                    spans = run_current()
                except (RuntimeError, OSError) as exc:
                    problem = str(exc).lower()
                    if device != "auto" or not any(word in problem for word in ("cublas", "cudnn", "cuda")):
                        raise
                    model, model_identity = load_model(model_path, device="cpu")
                    identity = str(model_identity)
                    spans = run_current()
            stored = store_transcript(target["id"], spans, identity, db_path=db_path)
            processed += 1
            if progress:
                progress({"name": target["name"], "status": "completed", **stored})
        except Exception as exc:
            message = str(exc)[:500]
            failures.append({"name": target["name"], "error": message})
            with connect(db_path) as connection:
                connection.execute("UPDATE videos SET transcript_status='failed',error=?,updated_at=? WHERE id=?",
                                   (message, _now(), target["id"]))
            if progress:
                progress({"name": target["name"], "status": "failed", "error": message})
    return {"total": len(targets), "processed": processed, "cached": cached, "failed": failures}
