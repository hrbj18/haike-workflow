"""Small deterministic production contract: grades first, quality second."""
from __future__ import annotations

import json
from bisect import bisect_right
from pathlib import Path
import re

from backlot.material_crop import template_filter
from backlot.material_library import (MaterialLibraryError, clip_row, connect, digest, get_media,
                                     now, number, resolve_media, words)
from backlot.material_library_evidence import check_task, read_task

GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "unknown": 4, "conflict": 5}


def normalize_plan(raw):
    if not isinstance(raw, dict):
        raise MaterialLibraryError("选材需求须为JSON对象")
    topic = str(raw.get("topic") or "").strip()
    if not topic or len(topic) > 160:
        raise MaterialLibraryError("选材需求缺少主题")
    plan = {"version": 1, "topic": topic}
    for key in ("entities", "series", "brands", "domains"):
        plan[key] = words(raw.get(key, []), key)
    if not plan["entities"]:
        raise MaterialLibraryError("请明确目标实体及经过确认的别名")
    if not isinstance(raw.get("single_source", True), bool):
        raise MaterialLibraryError("单原片策略必须是布尔值")
    plan.update({"single_source": raw.get("single_source", True), "profile": "template-band-v1",
                 "clip_seconds": 3, "clip_count": 3,
                 "min_related_seconds": number(raw.get("min_related_seconds", 3), "相关画面覆盖", 3, 9),
                 "max_acquisition_rounds": int(number(raw.get("max_acquisition_rounds", 2), "补采上限", 0, 3))})
    plan["id"] = "PLAN-" + digest(plan)[:24]
    return plan


def default_plan(topic):
    # A tiny explicit starter profile, not a universal inference model.
    if re.search(r"昇腾\s*950|ascend\s*950", topic, re.I):
        return normalize_plan({"topic": topic, "entities": ["昇腾950", "Atlas 950", "Ascend 950"],
                               "series": ["昇腾", "Atlas", "Ascend"], "brands": ["华为", "Huawei"],
                               "domains": ["算力", "芯片", "数据中心"]})
    return normalize_plan({"topic": topic, "entities": [topic]})


def _norm(value):
    return re.sub(r"\s+", "", value).casefold()


def _overlap(left, right):
    return bool({_norm(v) for v in left} & {_norm(v) for v in right})


def grade(clip, plan):
    meta = clip["metadata"]
    if clip["review_status"] != "confirmed" or not meta.get("usable"):
        return "unknown", "区间尚未确认或裁切后不可用"
    if plan["brands"] and meta.get("brands") and not _overlap(meta["brands"], plan["brands"]):
        return "conflict", "实际画面品牌与目标冲突"
    if _overlap(meta.get("entities", []), plan["entities"]):
        return "A", "已确认目标实体：" + meta["identity_basis"]
    if _overlap(meta.get("series", []), plan["series"]):
        return "B", "同产品系列，不能冒充目标型号"
    domain = _overlap(meta.get("domains", []), plan["domains"])
    if _overlap(meta.get("brands", []), plan["brands"]) and (domain or "brand_logo" in meta.get("tags", [])):
        return "C", "同品牌相关画面，作为品牌补充"
    if domain:
        return "D", "行业氛围画面，身份不等于目标产品"
    return "unknown", "画面领域或实体匹配尚未确认"


def candidates(raw_plan, *, db_path=None, limit=12):
    plan = normalize_plan(raw_plan)
    limit = int(number(limit, "候选上限", 1, 12))
    # Read full confirmed clip pool in deterministic order. Titles are not used
    # for adoption; they are only shown to the reviewer for provenance.
    with connect(db_path) as db:
        rows = [clip_row(row) for row in db.execute("SELECT * FROM clips WHERE review_status='confirmed' ORDER BY id")]
    output, rejected, checked_tasks, checked_media = [], [], set(), {}
    for clip in rows:
        level, reason = grade(clip, plan)
        if level in {"unknown", "conflict"} or clip["end"] - clip["start"] < 3 - 1e-6:
            rejected.append({"clip_id": clip["id"], "grade": level, "reason": reason})
            continue
        try:
            if clip["media_id"] not in checked_media:
                checked_media[clip["media_id"]] = resolve_media(clip["media_id"], db_path=db_path)
            if clip["task_id"] not in checked_tasks:
                check_task(read_task(clip["task_id"], db_path=db_path), db_path=db_path)
                checked_tasks.add(clip["task_id"])
        except MaterialLibraryError as exc:
            rejected.append({"clip_id": clip["id"], "grade": "unknown", "reason": str(exc)})
            continue
        output.append({"clip_id": clip["id"], "media_id": clip["media_id"], "start": clip["start"],
                       "end": clip["end"], "grade": level, "reason": reason, "observation": clip["observation"],
                       "quality": clip["metadata"]["quality"], "crop": clip["metadata"]["crop"],
                       "visible_text": clip["metadata"].get("visible_text", []), "task_id": clip["task_id"],
                       "reviewed_at": clip["updated_at"]})
        output[-1]["product_text_regions"] = clip["metadata"].get("product_text_regions", [])
    output.sort(key=lambda c: (c["reviewed_at"], c["clip_id"]), reverse=True)
    output.sort(key=lambda c: (GRADE_ORDER[c["grade"]], -c["quality"], c["media_id"], c["start"]))
    # Keep historical crop versions, but do not let them crowd the bounded
    # candidate list. Prefer the best grade/quality; ties use the latest review.
    unique, seen = [], set()
    for item in output:
        key = (item["media_id"], item["start"], item["end"])
        if key not in seen:
            unique.append(item)
            seen.add(key)
    output = unique
    return {"plan": plan, "candidates": output[:limit], "available_count": len(output),
            "rejected": rejected[:20], "all_candidates": output}


def compact_candidates(raw_plan, *, db_path=None, limit=12):
    result = candidates(raw_plan, db_path=db_path, limit=limit)
    result.pop("all_candidates")
    result["instruction"] = "仅选择候选 clip_id。等级优先，同级看质量；其他型号与品牌画面不能表述为目标产品实拍。"
    return result


def _pick(pool):
    # A greedy early window can block two later windows and incorrectly report
    # a shortage. Find up to three non-overlapping windows in bounded DP states.
    def score(items):
        return (*[sum(c["grade"] == g for c in items) for g in ("A", "B", "C")],
                sum(c["quality"] for c in items))
    groups = {}
    for candidate in pool:
        groups.setdefault(candidate["media_id"], []).append(candidate)
    combined = {0: []}
    for group in groups.values():
        ordered = sorted(group, key=lambda c: (c["start"] + 3, c["clip_id"]))
        ends = [c["start"] + 3 for c in ordered]
        states = [{0: []}]
        for index, candidate in enumerate(ordered):
            current = dict(states[-1])
            previous = states[bisect_right(ends, candidate["start"] + 1e-6, 0, index)]
            for count, items in previous.items():
                if count == 3:
                    continue
                proposal = items + [candidate]
                if count + 1 not in current or score(proposal) > score(current[count + 1]):
                    current[count + 1] = proposal
            states.append(current)
        updated = dict(combined)
        for count, items in combined.items():
            for extra, group_items in states[-1].items():
                if count + extra > 3:
                    continue
                proposal = items + group_items
                if count + extra not in updated or score(proposal) > score(updated[count + extra]):
                    updated[count + extra] = proposal
        combined = updated
    return sorted(combined[max(combined)], key=lambda c: (GRADE_ORDER[c["grade"]], -c["quality"], c["start"]))


def select(raw_plan, *, db_path=None, clip_ids=None):
    found = candidates(raw_plan, db_path=db_path)
    plan, pool = found["plan"], found["all_candidates"]
    if clip_ids is not None:
        clip_ids = words(clip_ids, "选择的片段ID", limit=3)
        if len(clip_ids) != 3:
            raise MaterialLibraryError("模板必须选择三个不同片段ID")
        by_id = {item["clip_id"]: item for item in found["candidates"]}
        if any(clip_id not in by_id for clip_id in clip_ids):
            raise MaterialLibraryError("只能从本次最多12个有效候选中选择")
        picked = [by_id[clip_id] for clip_id in clip_ids]
        if len(_pick(picked)) != 3:
            raise MaterialLibraryError("同原片区间不能重叠")
    else:
        if plan["single_source"]:
            groups = {}
            for candidate in pool:
                groups.setdefault(candidate["media_id"], []).append(candidate)
            sets = [_pick(group) for group in groups.values()]
        else:
            sets = [_pick(pool)]
        def score(group):
            return (len(group) == 3, sum(c["grade"] != "D" for c in group) * 3 >= plan["min_related_seconds"],
                    *[sum(c["grade"] == grade for c in group) for grade in ("A", "B", "C")],
                    sum(c["quality"] for c in group))
        picked = max(sets, key=score) if sets else []
    if plan["single_source"] and len({c["media_id"] for c in picked}) > 1:
        raise MaterialLibraryError("本次要求同一原片；请明确放宽后重新选材")
    related = sum(c["grade"] != "D" for c in picked) * 3
    status = "ready" if len(picked) == 3 and related >= plan["min_related_seconds"] else "needs_material"
    result = {"version": 1, "plan_id": plan["id"], "plan": plan, "status": status,
              "related_seconds": related, "clips": picked if status == "ready" else [],
              "gaps": [] if status == "ready" else [
                  {"reason": "缺少三个不重叠可用镜头" if len(picked) < 3 else "相关画面不足",
                   "missing_related_seconds": max(0, plan["min_related_seconds"] - related),
                   "analysis_required": True, "note": "请先分析已有候选，再按有限补采词族获取；不代表全网无素材"}],
              "rejected": found["rejected"]}
    result["id"] = "SEL-" + digest(result)[:24]
    with connect(db_path) as db:
        db.execute("INSERT OR IGNORE INTO selections VALUES(?,?,?,?)",
                   (result["id"], plan["id"], json.dumps(result, ensure_ascii=False), now()))
    return result


def search_layers(raw_plan):
    plan = normalize_plan(raw_plan)
    layers = [
        {"grade": "A", "queries": [f"{entity} {scene}" for entity in plan["entities"][:2] for scene in ("真机", "展台", "机柜")]},
        {"grade": "B", "queries": [f"{series} {scene}" for series in plan["series"][:2] for scene in ("设备 实拍", "芯片 特写")]},
        {"grade": "C", "queries": [f"{brand} {scene}" for brand in plan["brands"][:2] for scene in ("logo", "芯片 特写", "算力 机房")]},
        {"grade": "D", "queries": [f"{domain} 实拍" for domain in plan["domains"][:2]]},
    ]
    return [layer for layer in layers if layer["queries"]]


def acquisition_request(raw_plan, *, db_path=None):
    plan = normalize_plan(raw_plan)
    selected = select(plan, db_path=db_path)
    if selected["status"] == "ready":
        return {"status": "not_required", "selection_id": selected["id"]}
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute("SELECT * FROM acquisition WHERE plan_id=? ORDER BY round", (plan["id"],)).fetchall()
        open_row = next((row for row in rows if row["status"] == "requested"), None)
        if open_row:
            return {**json.loads(open_row["payload"]), "cached": True}
        next_round = len(rows) + 1
        if next_round > plan["max_acquisition_rounds"]:
            return {"status": "budget_exhausted", "plan_id": plan["id"], "rounds": len(rows),
                    "reason": "有限补采已用完；请调整需求、检查已有素材或人工选材，不能推断全网没有"}
        layers = search_layers(plan)
        active = layers[:1] if next_round == 1 else layers[1:3] or layers[:1]
        request = {"id": "ACQ-" + digest([plan["id"], next_round])[:24], "plan_id": plan["id"],
                   "status": "requested", "round": next_round, "layers": active,
                   "max_keywords": 10, "max_download_bytes": 180 * 1024 * 1024, "max_seconds": 600,
                   "reason": selected["gaps"], "note": "保留品牌/型号锚点；实际搜索词必须落账。先查本地库，来源标题只用于召回。"}
        db.execute("INSERT INTO acquisition VALUES(?,?,?,?,?)", (request["id"], plan["id"], next_round,
                   json.dumps(request, ensure_ascii=False), "requested"))
    return request


def finish_acquisition(request_id, report, *, db_path=None):
    if not isinstance(report, dict):
        raise MaterialLibraryError("补采结果格式无效")
    if report.get("status") not in {"imported", "search_no_results", "download_limited", "crop_unusable", "identity_unconfirmed", "failed"}:
        raise MaterialLibraryError("请区分搜索、下载、裁切、身份确认阶段的结果")
    queries = words(report.get("queries_used"), "实际搜索词", limit=10)
    if not queries:
        raise MaterialLibraryError("补采结果须记录实际搜索词")
    detail = str(report.get("detail") or "").strip()
    if not detail or len(detail) > 2000:
        raise MaterialLibraryError("补采结果须记录具体原因")
    normalized = {"status": report["status"], "queries_used": queries, "detail": detail,
                  "catalog_path": str(report.get("catalog_path") or "")}
    with connect(db_path) as db:
        row = db.execute("SELECT * FROM acquisition WHERE id=?", (request_id,)).fetchone()
    if not row:
        raise MaterialLibraryError("补采请求不存在")
    previous = json.loads(row["payload"])
    if row["status"] != "requested":
        if all((previous.get("result") or {}).get(key) == value for key, value in normalized.items()):
            return previous
        raise MaterialLibraryError("已完成补采不可覆盖")
    if normalized["status"] == "imported":
        from backlot.material_library import ingest_catalog
        if not normalized["catalog_path"]:
            raise MaterialLibraryError("补采导入须提供标准交付清单")
        normalized["registered"] = ingest_catalog(Path(normalized["catalog_path"]), db_path=db_path)
    previous.update({"status": normalized["status"], "result": normalized})
    with connect(db_path) as db:
        updated = db.execute("UPDATE acquisition SET payload=?,status=? WHERE id=? AND status='requested'",
                             (json.dumps(previous, ensure_ascii=False), normalized["status"], request_id))
        if not updated.rowcount:
            concurrent = json.loads(db.execute("SELECT payload FROM acquisition WHERE id=?", (request_id,)).fetchone()[0])
            if all((concurrent.get("result") or {}).get(key) == value for key, value in normalized.items() if key != "registered"):
                return concurrent
            raise MaterialLibraryError("补采请求已由另一操作完成，请读取现有结果")
    return previous


def selection_history(plan_id="", *, db_path=None):
    with connect(db_path) as db:
        rows = db.execute("SELECT payload FROM selections WHERE plan_id=? OR ?='' ORDER BY created_at DESC LIMIT 30",
                          (plan_id, plan_id)).fetchall()
    return [json.loads(row[0]) for row in rows]


def to_template_spec(selection, theme_key, *, db_path=None):
    if selection.get("status") != "ready":
        raise MaterialLibraryError("选材仍有缺口，不能生成模板选段表")
    spec = []
    for index, clip in enumerate(selection["clips"], 1):
        media = get_media(clip["media_id"], db_path=db_path)
        source = resolve_media(clip["media_id"], db_path=db_path)
        origin = next((o for o in media["origins"] if o["source_url"]), media["origins"][0])
        spec.append({"cue": f"cue-{index:03d}", "index": index, "t_key": theme_key,
                     "file": str(source), "source_in": clip["start"], "source_video_id": origin["video_id"],
                     "source_url": origin["source_url"], "source_title": origin["title"], "creator": "",
                     "material_role": "main" if clip["grade"] == "A" else "support",
                     "original_delivery_path": str(source), "media_id": clip["media_id"], "clip_id": clip["clip_id"],
                     "selection_id": selection["id"], "grade": clip["grade"], "source_crop": clip["crop"],
                     "evidence_task_id": clip["task_id"], "visible_text": clip["visible_text"],
                     "product_text_regions": clip.get("product_text_regions", []),
                     "render_transform": template_filter(clip["crop"]), "pick_reason": clip["reason"]})
    return spec
