"""Compatibility adapter for the existing three-shot template pipeline."""
from __future__ import annotations
import json
from pathlib import Path
import re

from backlot.material_library import MaterialLibraryError, connect, get_media, ingest_catalog, list_media, resolve_media
from backlot.material_library_evidence import check_task, read_task
from backlot.material_library_selection import acquisition_request, default_plan, normalize_plan, select, to_template_spec


def indexed_pick(theme_key, topic, catalogs, output_dir, *, raw_plan=None, db_path=None):
    if not re.fullmatch(r"t\d{1,5}", theme_key):
        raise MaterialLibraryError("模板条目代号无效")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    registered = []
    for path in catalogs:
        registered.extend(ingest_catalog(Path(path), db_path=db_path)["media_ids"])
    plan = normalize_plan(raw_plan) if raw_plan else default_plan(topic)
    selected = select(plan, db_path=db_path)
    if selected["status"] != "ready":
        result = {**selected, "acquisition": acquisition_request(plan, db_path=db_path),
                  "analysis_candidates": [
                      {"media_id": media_id, "title": get_media(media_id, db_path=db_path)["title"],
                       "duration": get_media(media_id, db_path=db_path)["duration"],
                       "next_step": "用已有概览找主体时段，再提交最多12个区间的原片/裁切读图任务"}
                      for media_id in list(dict.fromkeys(registered))[:12]],
                  "next_command": "scripts/material_library_cli.py prepare <区间请求.json>；submit <确认.json>；然后重跑本次选材"}
        (output_dir / f"material_gap_{theme_key}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    spec = to_template_spec(selected, theme_key, db_path=db_path)
    destination = output_dir / f"spec_{theme_key}.json"
    versions = output_dir / "material-selection-versions"
    versions.mkdir(exist_ok=True)
    if destination.is_file():
        from backlot.material_library import digest
        old = json.loads(destination.read_text(encoding="utf-8"))
        (versions / f"{theme_key}-previous-{digest(old)[:16]}.json").write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
    serialized = json.dumps(spec, ensure_ascii=False, indent=2)
    frozen = versions / f"{theme_key}-{selected['id']}.json"
    frozen.write_text(serialized, encoding="utf-8")
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(destination)
    return {**selected, "spec_path": str(destination), "frozen_spec": str(frozen)}


def validate_spec(cues, *, db_path=None):
    """Old specs retain legacy transforms; indexed specs must match frozen rows."""
    if not isinstance(cues, list) or len(cues) != 3 or not all(isinstance(c, dict) for c in cues):
        raise MaterialLibraryError("模板选段表必须包含三个镜头")
    indexed = [bool(cue.get("selection_id")) for cue in cues]
    if not any(indexed):
        return False
    if not all(indexed) or len({cue["selection_id"] for cue in cues}) != 1:
        raise MaterialLibraryError("不能混用历史与分级选材镜头")
    with connect(db_path) as db:
        row = db.execute("SELECT payload FROM selections WHERE id=?", (cues[0]["selection_id"],)).fetchone()
    if not row:
        raise MaterialLibraryError("冻结选材版本不存在")
    frozen = json.loads(row[0])
    expected = to_template_spec(frozen, cues[0]["t_key"], db_path=db_path)
    for cue, original in zip(cues, expected):
        if any(cue.get(key) != original[key] for key in ("cue", "index", "t_key", "source_in", "media_id", "clip_id", "source_crop",
                                                         "grade", "render_transform", "evidence_task_id", "visible_text")):
            raise MaterialLibraryError("选段或裁切已偏离冻结版本，请重新选材")
        if cue.get("product_text_regions", []) != original["product_text_regions"]:
            raise MaterialLibraryError("实体文字区域已偏离冻结版本，请重新选材")
        path = Path(cue["file"])
        from backlot.material_catalog_import import file_sha256
        if not path.is_file() or file_sha256(path) != get_media(cue["media_id"], db_path=db_path)["sha256"]:
            raise MaterialLibraryError("冻结镜头源文件已变化")
        check_task(read_task(cue["evidence_task_id"], db_path=db_path), db_path=db_path)
    return True


def text_is_approved(text, approved):
    def normalize(value):
        # OCR commonly reads the on-set 昇腾 identifier as 升腾. This narrow
        # spelling correction does not grant a clip product identity.
        return re.sub(r"\s+", "", value).casefold().replace("升腾", "昇腾")
    normalized = normalize(text)
    return bool(normalized) and any(
        normalized == normalize(item) or (len(normalized) >= 6 and normalized in normalize(item))
        for item in approved)


def product_region_is_approved(box, regions, seconds, width, height):
    """Only whole OCR boxes inside reviewed, time-scoped on-set label regions."""
    if box is None or not len(box):
        return False
    for region in regions:
        if region["start"] <= seconds < region["end"] and all(
            region["x"] * width <= float(point[0]) <= (region["x"] + region["w"]) * width and
            region["y"] * height <= float(point[1]) <= (region["y"] + region["h"]) * height for point in box):
            return True
    return False
