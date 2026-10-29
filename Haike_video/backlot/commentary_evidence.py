"""Genre-neutral, immutable source-window evidence; no three-shot selection rule."""
from __future__ import annotations

import math
from pathlib import Path

from backlot import material_library as library
from backlot import commentary_library_bridge as bridge
from backlot.commentary_common import (
    CommentaryError, crop_filter, crop_value, digest, identifier, immutable,
    media_tools, number, read_json, run, text, verified, file_sha256,
)


def directory(project, identity):
    identifier(identity, "EV-")
    return Path(project) / "artifacts/commentary/evidence" / identity[:27]


def prepare(project, payload, *, db_path=None):
    media = bridge.ensure_available(str(payload.get("media_id") or ""), db_path=db_path)
    source = library.resolve_media(media["id"], db_path=db_path)
    start = number(payload.get("start"), "证据起点", 0, media["duration"])
    end = number(payload.get("end"), "证据终点", start + .1, media["duration"])
    if end - start > 120:
        raise CommentaryError("单次精查最多120秒；长电影/直播请先概览与章节定位，再分窗口取证")
    crop = crop_value(payload.get("crop"))
    request = {"version": 1, "media_id": media["id"], "sha256": media["sha256"],
               "start": start, "end": end, "crop": crop}
    revision = text(payload.get("review_revision", ""), "证据复核版本", 80, empty=True)
    if revision:
        request["review_revision"] = revision
    identity = "EV-" + digest(request)
    target = directory(project, identity)
    if (target / "evidence.json").is_file():
        return read(project, identity)
    target.mkdir(parents=True, exist_ok=True)
    # Local excerpt is for continuous playback/listening, not just still-frame inference.
    ffmpeg, _ = media_tools()
    preview = target / "source.mp4"
    run([ffmpeg, "-v", "error", "-nostdin", "-y", "-ss", start, "-i", source,
         "-t", end - start, "-vf", crop_filter(crop) + ",scale=640:640:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
         "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "fast", "-crf", "25",
         "-threads", "2", "-c:a", "aac", "-movflags", "+faststart", preview])
    count = min(12, max(3, math.ceil(end - start)))
    samples = [start + (end - start) * (i + .5) / count for i in range(count)]
    from PIL import Image, ImageDraw
    sheet = Image.new("RGB", (960, math.ceil(count / 3) * 205), "#111827")
    draw = ImageDraw.Draw(sheet)
    for i, stamp in enumerate(samples):
        frame = target / f"frame-{i:02d}.png"
        run([ffmpeg, "-v", "error", "-nostdin", "-y", "-ss", stamp, "-i", source,
             "-frames:v", "1", "-vf", crop_filter(crop) + ",scale=320:180:force_original_aspect_ratio=decrease", frame], timeout=90)
        with Image.open(frame) as pic:
            x, y = (i % 3) * 320, (i // 3) * 205
            sheet.paste(pic, (x + (320 - pic.width) // 2, y))
            draw.text((x + 8, y + 183), f"{stamp:.3f}s", fill="white")
        frame.unlink()
    sheet.save(target / "sheet.jpg", quality=90)
    data = {**request, "id": identity, "samples": samples, "title": media["title"],
            "origins": media["origins"], "source_path": str(source),
            "files": {name: file_sha256(target / name) for name in ("source.mp4", "sheet.jpg")}}
    immutable(target / "evidence.json", data)
    return read(project, identity)


def read(project, identity):
    target = directory(project, identity)
    evidence = read_json(target / "evidence.json")
    if evidence.get("id") != identity:
        raise CommentaryError("证据身份不匹配")
    return {**evidence, "review": read_json(target / "review.json") if (target / "review.json").is_file() else None}


def review(project, identity, payload, *, db_path=None):
    current = read(project, identity)
    for name, sha in current["files"].items():
        verified(directory(project, identity) / name, sha)
    bridge.resolve_source(current["media_id"], current["sha256"], db_path=db_path)
    if payload.get("viewed") is not True or type(payload.get("usable")) is not bool:
        raise CommentaryError("实际查看证据后填写 viewed 和 usable；不能把抽帧当成完整回听")
    data = {"reviewer": text(payload.get("reviewer"), "审核者", 160),
            "observation": text(payload.get("observation"), "画面观察"),
            "context": text(payload.get("context"), "前后文及人物关系"),
            "transcript": text(payload.get("transcript", ""), "听辨台词", 10000, empty=True),
            "unknowns": text(payload.get("unknowns", ""), "未确认内容", empty=True),
            "viewed": True, "usable": payload["usable"],
            "audio_reviewed": payload.get("audio_reviewed") is True,
            "source_subtitles": payload.get("source_subtitles", "unknown"),
            "source_music": payload.get("source_music", "unknown")}
    if data["source_subtitles"] not in {"none", "present", "unknown"} or data["source_music"] not in {"none", "present", "unknown"}:
        raise CommentaryError("原字幕/配乐状态须为 none、present 或 unknown")
    immutable(directory(project, identity) / "review.json", data)
    return read(project, identity)


def confirmed(project, identity, *, check_files=False, db_path=None):
    value = read(project, identity)
    if not value["review"] or not value["review"].get("usable"):
        raise CommentaryError("镜头尚未完成可用性确认，请先查看素材并提交观察")
    if check_files:
        bridge.resolve_source(value["media_id"], value["sha256"], db_path=db_path)
        for name, sha in value["files"].items():
            verified(directory(project, identity) / name, sha)
    return value


def list_evidence(project):
    base = Path(project) / "artifacts/commentary/evidence"
    return [read(project, read_json(p)["id"]) for p in sorted(base.glob("EV-*/evidence.json"))]
