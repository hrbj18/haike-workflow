"""Bounded local evidence tasks; no remote inference or hidden model calls."""
from __future__ import annotations

import json
from copy import deepcopy
import math
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw

from backlot.material_crop import normalize_crop, template_filter
from backlot.material_catalog_import import file_sha256
from backlot.material_library import (MaterialLibraryError, connect, data_dir, digest, get_media,
                                     now, number, resolve_media, words)
from lib.ffmpeg_locator import resolve_ffmpeg_pair


def task_directory(task_id, db_path=None):
    root = Path(db_path).parent if db_path else data_dir()
    return root / "evidence" / task_id


def read_task(task_id, *, db_path=None):
    with connect(db_path) as db:
        row = db.execute("SELECT payload,submission FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise MaterialLibraryError("分析任务不存在")
    task = json.loads(row["payload"])
    task["completed"] = row["submission"] is not None
    task["review_result"] = json.loads(row["submission"]) if row["submission"] else None
    return task


def check_task(task, *, db_path=None):
    for media_id in dict.fromkeys(window["media_id"] for window in task["windows"]):
        resolve_media(media_id, db_path=db_path)
    directory = task_directory(task["id"], db_path)
    for window in task["windows"]:
        for sheet in window["sheets"]:
            path = (directory / sheet["file"]).resolve()
            if not path.is_relative_to(directory.resolve()) or not path.is_file() or file_sha256(path) != sheet["sha256"]:
                raise MaterialLibraryError("分析证据缺失或被修改，请重新准备任务")


def prepare_task(request, *, db_path=None):
    if not isinstance(request, dict) or not isinstance(request.get("windows"), list) or not 1 <= len(request["windows"]) <= 12:
        raise MaterialLibraryError("每次分析需1—12个候选区间")
    model = str(request.get("model") or "").strip()
    if not model or len(model) > 100:
        raise MaterialLibraryError("请填写实际执行读图的模型名称")
    windows = []
    for index, raw in enumerate(request["windows"], 1):
        if not isinstance(raw, dict):
            raise MaterialLibraryError("候选区间格式无效")
        media = get_media(str(raw.get("media_id") or ""), db_path=db_path)
        start = number(raw.get("start"), "区间开始", 0, media["duration"])
        end = number(raw.get("end"), "区间结束", 0, media["duration"])
        if not .4 <= end - start <= 12:
            raise MaterialLibraryError("单次候选区间需0.4—12秒，长素材先用已有概览定位")
        windows.append({"id": f"W-{index:02d}", "media_id": media["id"], "source_sha256": media["sha256"],
                        "start": round(start, 6), "end": round(end, 6), "crop": normalize_crop(raw.get("crop"))})
    identity = {"version": 2, "sampling_fps": 3, "profile": "template-band-v1", "model": model, "windows": deepcopy(windows)}
    revision = request.get("review_revision", "")
    if not isinstance(revision, str) or len(revision) > 80:
        raise MaterialLibraryError("确认修订标识须为不超过80字的文字")
    if revision.strip():
        identity["review_revision"] = revision.strip()
    task_id = "EV-" + digest(identity)[:24]
    with connect(db_path) as db:
        exists = db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone()
    if exists:
        task = read_task(task_id, db_path=db_path)
        check_task(task, db_path=db_path)
        return {**task, "cached": True}
    pair = resolve_ffmpeg_pair()
    if not pair:
        raise MaterialLibraryError("未找到 FFmpeg")
    directory = task_directory(task_id, db_path)
    directory.mkdir(parents=True, exist_ok=True)
    for window in windows:
        source = resolve_media(window["media_id"], db_path=db_path)
        with tempfile.TemporaryDirectory(prefix="frames-", dir=directory) as temporary:
            temporary = Path(temporary)
            duration = window["end"] - window["start"]
            for kind, transform in (("source", "scale=384:384:force_original_aspect_ratio=decrease"),
                                    ("crop", template_filter(window["crop"]).removesuffix(",fps=30") + ",crop=1080:630:0:650,scale=384:224")):
                command = [pair[0], "-v", "error", "-y", "-ss", str(window["start"]), "-i", str(source),
                           "-t", str(duration), "-an", "-vf", "fps=3," + transform, "-q:v", "2",
                           str(temporary / f"{kind}-%03d.jpg")]
                try:
                    run = subprocess.run(command, capture_output=True, timeout=90)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise MaterialLibraryError("抽帧失败或超时") from exc
                frames = sorted(temporary.glob(kind + "-*.jpg"))
                if run.returncode or not max(1, math.floor(duration * 3) - 1) <= len(frames) <= math.ceil(duration * 3) + 1:
                    raise MaterialLibraryError("实际视频不能覆盖候选区间")
            cropped, sources = sorted(temporary.glob("crop-*.jpg")), sorted(temporary.glob("source-*.jpg"))
            sheets = []
            for page, offset in enumerate(range(0, len(cropped), 6), 1):
                sheet = Image.new("RGB", (768, 790), "#111111")
                draw = ImageDraw.Draw(sheet)
                for tile, frame in enumerate(cropped[offset:offset + 6]):
                    x, y = (tile % 2) * 384, (tile // 2) * 260
                    with Image.open(frame) as img:
                        sheet.paste(img, (x, y + 30))
                    draw.text((x + 8, y + 6), f"{window['id']} crop @{window['start'] + (offset + tile) / 3:.3f}s", fill="white")
                filename = f"{window['id']}-crop-{page}.jpg"
                sheet.save(directory / filename, quality=94)
                sheets.append({"file": filename, "sha256": file_sha256(directory / filename), "kind": "crop"})
            # Source context lets the reviewer separate captions from on-set signage.
            source_sheet = Image.new("RGB", (1152, 420), "#111111")
            draw = ImageDraw.Draw(source_sheet)
            for tile, index in enumerate(sorted(set([0, len(sources) // 2, len(sources) - 1]))):
                with Image.open(sources[index]) as img:
                    source_sheet.paste(img, (tile * 384, 30))
                draw.text((tile * 384 + 8, 6), f"source @{window['start'] + index / 3:.3f}s", fill="white")
            filename = f"{window['id']}-source.jpg"
            source_sheet.save(directory / filename, quality=94)
            sheets.append({"file": filename, "sha256": file_sha256(directory / filename), "kind": "source"})
            window["sheets"] = sheets
    task = {"id": task_id, "identity": identity, "model": model, "windows": windows,
            "instruction": "看完原片上下文及全部裁切图。仅填写实际可辨认的主体/品牌/型号/系列/领域；标题不能证明画面身份。"
                           "裁掉底字幕可用，产品/品牌/展台文字允许保留。只在主体完整、画面清晰、无残留烧录字幕压住主体时usable=true。"
                           "不确定身份保留空列表，不把曙光/NVIDIA等写成华为；看不清需补证据。",
            "submission_template": {"task_id": task_id, "model": model, "reviews": [
                {"window_id": window["id"], "reviewed_sheets": [s["file"] for s in window["sheets"]],
                 "observation": "", "brands": [], "entities": [], "series": [], "domains": [], "tags": [],
                 "usable": False, "subject_retained": False, "captions_obscure_subject": True,
                 "identity_basis": "", "quality": 0, "visible_text": [], "product_text_regions": []} for window in windows]}}
    # Verify sources again after extraction before committing evidence.
    for media_id in dict.fromkeys(window["media_id"] for window in windows):
        resolve_media(media_id, db_path=db_path)
    with connect(db_path) as db:
        db.execute("INSERT OR IGNORE INTO tasks VALUES(?,?,NULL)", (task_id, json.dumps(task, ensure_ascii=False)))
    (directory / "task.json").write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**task, "cached": False}


def submit_task(submission, *, db_path=None):
    if not isinstance(submission, dict):
        raise MaterialLibraryError("分析提交格式无效")
    task = read_task(str(submission.get("task_id") or ""), db_path=db_path)
    if submission.get("model") != task["model"]:
        raise MaterialLibraryError("执行模型与分析任务不一致")
    check_task(task, db_path=db_path)
    reviews = submission.get("reviews")
    if not isinstance(reviews, list) or len(reviews) != len(task["windows"]) or not all(isinstance(r, dict) for r in reviews):
        raise MaterialLibraryError("必须逐一提交所有候选区间")
    by_id = {r.get("window_id"): r for r in reviews}
    if len(by_id) != len(reviews) or set(by_id) != {w["id"] for w in task["windows"]}:
        raise MaterialLibraryError("区间ID重复、未知或遗漏")
    prepared = []
    for window in task["windows"]:
        raw = by_id[window["id"]]
        reviewed = words(raw.get("reviewed_sheets"), "已查看图片", limit=20)
        if set(reviewed) != {s["file"] for s in window["sheets"]}:
            raise MaterialLibraryError("须实际查看原片上下文及所有裁切图")
        observation = str(raw.get("observation") or "").strip()
        basis = str(raw.get("identity_basis") or "").strip()
        if not observation or len(observation) > 800 or len(basis) > 800:
            raise MaterialLibraryError("缺少有效画面描述")
        meta = {key: words(raw.get(key, []), key) for key in ("brands", "entities", "series", "domains", "tags", "visible_text")}
        regions = raw.get("product_text_regions", [])
        if not isinstance(regions, list) or len(regions) > 8:
            raise MaterialLibraryError("实体标识区域最多8个")
        approved_regions = []
        for region in regions:
            if not isinstance(region, dict):
                raise MaterialLibraryError("实体标识区域格式无效")
            rectangle = normalize_crop({key: region.get(key) for key in ("x", "y", "w", "h")})
            if rectangle["w"] * rectangle["h"] > .4:
                raise MaterialLibraryError("单个实体标识区域不能覆盖超过40%的中央画面")
            start = number(region.get("start"), "标识起始时间", 0, window["end"] - window["start"])
            end = number(region.get("end"), "标识结束时间", 0, window["end"] - window["start"])
            reason = str(region.get("reason") or "").strip()
            if end <= start or not reason or len(reason) > 160:
                raise MaterialLibraryError("标识区域需有效相对时间及实体文字依据")
            approved_regions.append({**rectangle, "start": start, "end": end, "reason": reason})
        meta["product_text_regions"] = approved_regions
        for field in ("usable", "subject_retained", "captions_obscure_subject"):
            if not isinstance(raw.get(field), bool):
                raise MaterialLibraryError(f"{field}必须为布尔值")
        if raw["usable"] and (not raw["subject_retained"] or raw["captions_obscure_subject"]):
            raise MaterialLibraryError("主体缺失或字幕仍遮挡，不能标为可用")
        if any(meta[key] for key in ("brands", "entities", "series")) and not basis:
            raise MaterialLibraryError("品牌/型号/系列判断缺少画面身份依据")
        meta.update({key: raw[key] for key in ("usable", "subject_retained", "captions_obscure_subject")})
        meta.update({"quality": number(raw.get("quality"), "质量分", 0, 100), "identity_basis": basis,
                     "crop": window["crop"], "evidence_files": reviewed, "evidence_task_id": task["id"]})
        clip_id = "CLIP-" + digest([task["id"], window["id"]])[:24]
        prepared.append((clip_id, window["media_id"], window["start"], window["end"], observation,
                         "confirmed", json.dumps(meta, ensure_ascii=False), task["id"], now()))
    serialized = json.dumps(submission, ensure_ascii=False, sort_keys=True)
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT submission FROM tasks WHERE id=?", (task["id"],)).fetchone()[0]
        if previous and previous != serialized:
            raise MaterialLibraryError("已完成分析不可覆盖，请建立新模型或新的候选裁切任务")
        for clip in prepared:
            db.execute("INSERT OR IGNORE INTO clips VALUES(?,?,?,?,?,?,?,?,?)", clip)
        db.execute("UPDATE tasks SET submission=? WHERE id=?", (serialized, task["id"]))
    return {"status": "confirmed", "clip_ids": [clip[0] for clip in prepared], "task_id": task["id"]}
