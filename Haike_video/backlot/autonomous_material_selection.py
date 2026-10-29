"""Model-directed, evidence-bounded material selection for whole projects.

The model ranks verified shots and proposes variable durations. This module
owns all source, timing, quality and completeness decisions. It has no IO.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from backlot.local_material_orchestration import (
    build_material_capability_map,
    material_indexes_fingerprint,
    script_fingerprint,
)
from backlot.visual_need_plan import VisualNeedError, validate_current_visual_need_plan


class MaterialSelectionError(ValueError):
    """Invalid or unsafe model selection."""


VERSION = 1
MIN_CLIP_SECONDS = 0.4  # The existing visual timeline's technical minimum.


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return -1.0
    try:
        number = float(value)
        return number if math.isfinite(number) else -1.0
    except (TypeError, ValueError):
        return -1.0


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _platform(asset: dict[str, Any]) -> str:
    provenance = asset.get("provenance") if isinstance(asset.get("provenance"), dict) else {}
    text = " ".join(str(provenance.get(key) or "") for key in ("provider", "source_tool", "source_url")).lower()
    if "douyin" in text or "抖音" in text:
        return "douyin"
    if "pexels" in text:
        return "pexels"
    if "bilibili" in text or "b23.tv" in text or "哔哩" in text:
        return "bilibili"
    return "unknown"


def material_source_keys(item: dict[str, Any]) -> set[str]:
    """Identify one original despite copies, renames, or different asset IDs."""
    provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    generation = item.get("generation") if isinstance(item.get("generation"), dict) else {}
    platform = str(item.get("platform") or _platform(item)).lower()
    video_id = str(item.get("source_video_id") or generation.get("video_id") or provenance.get("source_video_id") or "").strip()
    source_url = str(item.get("source_url") or provenance.get("source_url") or "").strip()
    content_sha = str(item.get("content_sha256") or generation.get("content_sha256") or "").lower().strip()
    keys = set()
    if video_id:
        keys.add(f"video:{platform}:{video_id}")
    if re.match(r"^https?://", source_url, re.I):
        parsed = urlsplit(source_url)
        normalized = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))
        keys.add(f"url:{normalized}")
    if re.fullmatch(r"[0-9a-f]{64}", content_sha):
        keys.add(f"sha256:{content_sha}")
    keys.add(f"asset:{item.get('asset_id') or item.get('id') or ''}")
    return keys


def _quality_reasons(capability: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if capability.get("evidence_level") != "vision_v2" or capability.get("requires_source_preview"):
        reasons.append("仅有多宫格概览，缺少已验证的连续镜头")
    evidence = capability.get("evidence") if isinstance(capability.get("evidence"), dict) else {}
    if not re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("index_fingerprint") or "")):
        reasons.append("视觉索引指纹无效")
    if not evidence.get("frame_ids"):
        reasons.append("镜头没有可追溯的抽帧证据")
    quality = capability.get("quality") if isinstance(capability.get("quality"), dict) else {}
    if str(quality.get("blur") or "").lower() not in {"low", "none"}:
        reasons.append("画面模糊等级未通过")
    # Visible on-screen text is a review signal, not an automatic rejection:
    # factual title cards and charts are often the intended visual evidence.
    # The mandatory actual-window QA checks whether embedded captions collide
    # with the final subtitle placement. Watermarks and severe obstruction stay
    # hard quality failures below.
    notes = " ".join(str(quality.get(key) or "") for key in ("notes", "occlusion")).lower()
    watermark_notes = re.sub(
        r"无(?:明显|可见)?(?:创作者(?:账号)?)?水印|未(?:观察到|发现|见)(?:明显|可见)?(?:创作者(?:账号)?)?水印|不含(?:明显|可见)?(?:创作者(?:账号)?)?水印|没有(?:明显|可见)?(?:创作者(?:账号)?)?水印|no\s+(?:visible\s+)?(?:creator\s+)?watermark",
        "", notes,
    )
    if any(term in watermark_notes for term in ("水印", "logo", "watermark", "重度遮挡", "严重遮挡")):
        reasons.append("画面质量说明含水印或严重遮挡")
    if _number(capability.get("duration_seconds")) < MIN_CLIP_SECONDS:
        reasons.append("镜头短于时间线最小区间")
    return reasons


def prepare_selection_request(
    state: dict[str, Any], indexes: dict[str, dict[str, Any]], *, required_platform: str = "any", model: str = "",
    execution_mode: str = "relay",
) -> dict[str, Any]:
    """Return only safe, traceable candidates for the configured model."""
    if required_platform not in {"any", "douyin", "pexels", "bilibili"}:
        raise MaterialSelectionError("素材来源策略无效")
    if model and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", model):
        raise MaterialSelectionError("本次选择的模型名称无效")
    if execution_mode not in {"agent", "relay"}:
        raise MaterialSelectionError("模型执行方式无效")
    scenes = sorted(
        (scene for scene in state.get("scenes") or [] if isinstance(scene, dict)),
        key=lambda scene: (_number(scene.get("start_seconds")), str(scene.get("id") or "")),
    )
    if not scenes:
        raise MaterialSelectionError("项目没有可选材的场景")
    assets = {str(asset.get("id") or ""): asset for asset in state.get("assets") or [] if isinstance(asset, dict)}
    unindexed_asset_ids = [
        asset_id for asset_id, asset in sorted(assets.items())
        if str(asset.get("type") or "").lower() == "video"
        and str((asset.get("provenance") or {}).get("source_tool") or "") == "copy_skill_material_catalog_v1"
        and asset_id not in indexes
    ]
    capabilities, warnings = build_material_capability_map(state, indexes, {})
    allowed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for capability in capabilities:
        asset = assets.get(str(capability.get("asset_id") or ""), {})
        index = indexes.get(str(capability.get("asset_id") or ""), {})
        overview_gate = index.get("overview_gate") if isinstance(index.get("overview_gate"), dict) else {}
        platform = _platform(asset)
        reasons = _quality_reasons(capability)
        if model:
            if str((index.get("vision") or {}).get("model") or "") != model:
                reasons.append("镜头级视觉分析模型与本次选定模型不一致")
            if str(overview_gate.get("model") or "") != model:
                reasons.append("多宫格视觉分析模型与本次选定模型不一致")
        if execution_mode == "agent":
            if str((index.get("vision") or {}).get("provider") or "") != "agent":
                reasons.append("镜头级视觉证据不是本次 agent 生成")
            if str(overview_gate.get("provider") or "") != "agent":
                reasons.append("多宫格视觉证据不是本次 agent 生成")
        windows = []
        for item in overview_gate.get("ranges") or []:
            if not isinstance(item, dict) or not item.get("cell_ids"):
                continue
            start = max(_number(item.get("start_seconds")), _number(capability.get("source_in_seconds")))
            end = min(_number(item.get("end_seconds")), _number(capability.get("source_out_seconds")))
            if end - start >= MIN_CLIP_SECONDS - .001:
                if capability.get("cut_policy") == "atomic" and (
                    abs(start - _number(capability.get("source_in_seconds"))) > .001
                    or abs(end - _number(capability.get("source_out_seconds"))) > .001
                ):
                    continue
                windows.append((round(start, 3), round(end, 3), item))
        if not windows:
            reasons.append("镜头不在已完成多宫格概览的可用区间内")
        if required_platform != "any" and platform != required_platform:
            reasons.append(f"来源 {platform} 不符合 {required_platform} 策略")
        source_url = str((asset.get("provenance") or {}).get("source_url") or "")
        rights_status = str((asset.get("generation") or {}).get("rights_status") or (asset.get("provenance") or {}).get("license") or "unknown").lower()
        if rights_status == "reference_only":
            reasons.append("素材仅可参考，不能进入待审成片")
        if required_platform == "douyin" and not re.search(r"^https://(?:[\w-]+\.)*(?:douyin\.com|iesdouyin\.com)/", source_url, re.I):
            reasons.append("抖音来源缺少可核验的原视频链接")
        if reasons:
            rejected.append({"capability_id": capability["capability_id"], "asset_id": capability["asset_id"], "reasons": reasons})
        else:
            for number, (start, end, item) in enumerate(windows, 1):
                row = {
                    **deepcopy(capability),
                    "capability_id": (f"{capability['capability_id']}:R{number:02d}" if len(windows) > 1 else capability["capability_id"]),
                    "source_in_seconds": start,
                    "source_out_seconds": end,
                    "duration_seconds": round(end - start, 3),
                    "overview_evidence": {"signature": overview_gate.get("signature"), "cell_ids": item["cell_ids"]},
                    "platform": platform,
                    "source_url": source_url,
                    "source_video_id": str((asset.get("generation") or {}).get("video_id") or (asset.get("provenance") or {}).get("source_video_id") or ""),
                    "content_sha256": str((asset.get("generation") or {}).get("content_sha256") or ""),
                    "license": str((asset.get("provenance") or {}).get("license") or ""),
                    "rights_status": rights_status,
                }
                allowed.append(row)
    scene_briefs = []
    for scene in scenes:
        start, end = _number(scene.get("start_seconds")), _number(scene.get("end_seconds"))
        if start < 0 or end - start < .04:
            raise MaterialSelectionError("场景时间范围无效")
        scene_briefs.append({
            "scene_id": str(scene.get("id") or ""),
            "duration_seconds": round(end - start, 3),
            "title": str(scene.get("title") or "")[:160],
            "description": str(scene.get("description") or "")[:1200],
            "shot_intent": str(scene.get("shot_intent") or "")[:500],
        })
    visual_need_plan = state.get("visual_need_plan") if isinstance(state.get("visual_need_plan"), dict) else None
    if visual_need_plan:
        try:
            validate_current_visual_need_plan(state, visual_need_plan, model=model)
        except VisualNeedError as exc:
            raise MaterialSelectionError(str(exc)) from exc
        targets = [deepcopy(target) for item in visual_need_plan["scenes"] for target in item["targets"]]
    else:
        targets = []
    request = {
        "version": VERSION,
        "required_platform": required_platform,
        "execution_mode": execution_mode,
        "model": model,
        "script_fingerprint": script_fingerprint(state),
        "asset_index_fingerprint": material_indexes_fingerprint(indexes),
        "scenes": scene_briefs,
        "visual_need_fingerprint": visual_need_plan.get("fingerprint") if visual_need_plan else None,
        "targets": targets,
        "candidates": allowed,
        "unindexed_asset_ids": unindexed_asset_ids,
        "rejected_candidates": rejected,
        "warnings": warnings,
    }
    request["request_fingerprint"] = _digest(request)
    return request


def build_selection_plan(request: dict[str, Any], proposal: dict[str, Any], *, model: str) -> dict[str, Any]:
    """Validate model IDs/timecodes and produce full scene coverage or a diagnosis."""
    if request.get("visual_need_fingerprint"):
        return _build_target_selection_plan(request, proposal, model=model)
    if not isinstance(proposal, dict) or not isinstance(proposal.get("scenes"), list):
        raise MaterialSelectionError("模型没有返回场景选材列表")
    if not model or len(model) > 160:
        raise MaterialSelectionError("模型身份缺失")
    if request.get("model") and model != request["model"]:
        raise MaterialSelectionError("返回结果的模型与排队时冻结的模型不一致")
    candidates = {str(item["capability_id"]): item for item in request.get("candidates") or []}
    proposal_scenes = proposal["scenes"]
    if len(proposal_scenes) != len(request.get("scenes") or []):
        raise MaterialSelectionError("模型返回的场景数与项目不一致")
    by_scene: dict[str, dict[str, Any]] = {}
    for raw in proposal_scenes:
        if not isinstance(raw, dict) or not isinstance(raw.get("clips"), list):
            raise MaterialSelectionError("模型场景选材格式无效")
        scene_id = str(raw.get("scene_id") or "")
        if scene_id in by_scene:
            raise MaterialSelectionError("模型重复返回场景")
        by_scene[scene_id] = raw
    if set(by_scene) != {scene["scene_id"] for scene in request["scenes"]}:
        raise MaterialSelectionError("模型返回了未知场景或遗漏场景")
    used: set[str] = set()
    sequences: list[dict[str, Any]] = []
    scene_plans: list[dict[str, Any]] = []
    for scene in request["scenes"]:
        scene_id = scene["scene_id"]
        scene_duration = float(scene["duration_seconds"])
        position = 0.0
        scene_sequences: list[str] = []
        for raw in by_scene[scene_id]["clips"]:
            if not isinstance(raw, dict):
                raise MaterialSelectionError("模型镜头选择格式无效")
            capability_id = str(raw.get("capability_id") or "")
            capability = candidates.get(capability_id)
            if capability is None:
                raise MaterialSelectionError(f"{scene_id} 引用了未通过证据或来源检查的镜头 {capability_id}")
            if capability_id in used:
                raise MaterialSelectionError(f"镜头 {capability_id} 被重复使用")
            source_in = _number(raw.get("source_in_seconds", capability["source_in_seconds"]))
            requested = _number(raw.get("duration_seconds"))
            source_start = float(capability["source_in_seconds"])
            source_end = float(capability["source_out_seconds"])
            remaining = round(scene_duration - position, 3)
            if source_in < source_start - .001 or source_in >= source_end or requested <= 0:
                raise MaterialSelectionError(f"{capability_id} 的源入点或用时无效")
            if requested > remaining + .001 or source_in + requested > source_end + .001:
                raise MaterialSelectionError(f"{capability_id} 超出场景或已验证的源时间范围")
            if requested < min(MIN_CLIP_SECONDS, scene_duration) - .001:
                raise MaterialSelectionError(f"{capability_id} 的镜头太短")
            if capability.get("cut_policy") == "atomic" and (
                abs(source_in - source_start) > .001 or abs(requested - (source_end - source_start)) > .001
            ):
                raise MaterialSelectionError(f"{capability_id} 是完整动作，不允许截断")
            used.add(capability_id)
            sequence_id = f"LMS-{len(sequences) + 1:03d}"
            display_end = round(position + requested, 3)
            evidence = capability["evidence"]
            evidence = {**evidence, "overview": deepcopy(capability["overview_evidence"])}
            sequences.append({
                "sequence_id": sequence_id,
                "scene_id": scene_id,
                "capability_id": capability_id,
                "asset_id": capability["asset_id"],
                "platform": capability["platform"],
                "source_url": capability["source_url"],
                "license": capability["license"],
                "rights_status": capability["rights_status"],
                "source_in_seconds": round(source_in, 3),
                "source_out_seconds": round(source_in + requested, 3),
                "display_start_seconds": round(position, 3),
                "display_end_seconds": display_end,
                "visual_role": "local_full_bleed",
                "cut_policy": capability["cut_policy"],
                "muted": True,
                "playback_rate": 1.0,
                "evidence": deepcopy(evidence),
            })
            scene_sequences.append(sequence_id)
            position = display_end
        covered = abs(scene_duration - position) <= .001
        scene_plans.append({
            "scene_id": scene_id,
            "status": "ready" if covered else "needs_more_material",
            "duration_seconds": scene_duration,
            "covered_seconds": position,
            "missing_seconds": round(max(0.0, scene_duration - position), 3),
            "sequence_ids": scene_sequences,
            "reason": str(by_scene[scene_id].get("reason") or "")[:240],
        })
    result = {
        "version": VERSION,
        "status": "ready" if all(item["status"] == "ready" for item in scene_plans) else "needs_more_material",
        "provider": "default",
        "model": model,
        "required_platform": request["required_platform"],
        "request_fingerprint": request["request_fingerprint"],
        "script_fingerprint": request["script_fingerprint"],
        "asset_index_fingerprint": request["asset_index_fingerprint"],
        "scene_plans": scene_plans,
        "sequences": sequences,
        "rejected_candidates": deepcopy(request.get("rejected_candidates") or []),
        "publish_rights_status": (
            "review_required" if (
                any(item["status"] != "ready" for item in scene_plans)
                or any(item["rights_status"] not in {"renderable_with_attribution", "project_generated"} for item in sequences)
            )
            else "cleared_by_catalog"
        ),
        "acquisition_requests": [
            {
                "scene_id": scene["scene_id"],
                "required_platform": request["required_platform"],
                "missing_seconds": next(item["missing_seconds"] for item in scene_plans if item["scene_id"] == scene["scene_id"]),
                "query_context": " ".join(str(scene.get(key) or "") for key in ("title", "description", "shot_intent")).strip()[:800],
            }
            for scene in request["scenes"]
            if next(item for item in scene_plans if item["scene_id"] == scene["scene_id"])["status"] != "ready"
        ],
    }
    result["fingerprint"] = _digest(result)
    return result


def _build_target_selection_plan(request: dict[str, Any], proposal: dict[str, Any], *, model: str) -> dict[str, Any]:
    """Fill only planned material targets; other spans retain their render base."""
    if model != request.get("model"):
        raise MaterialSelectionError("选材模型与画面目标模型不一致")
    rows = proposal.get("targets") if isinstance(proposal, dict) else None
    expected = [target for target in request.get("targets") or [] if target.get("mode") == "material"]
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise MaterialSelectionError("选材方案必须逐一返回全部外部素材目标")
    by_target: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("clips"), list):
            raise MaterialSelectionError("素材目标选材格式无效")
        target_id = str(row.get("target_id") or "")
        if target_id in by_target:
            raise MaterialSelectionError("同一画面目标被重复返回")
        by_target[target_id] = row
    if set(by_target) != {item["target_id"] for item in expected}:
        raise MaterialSelectionError("选材方案包含未知目标或遗漏目标")
    candidates = {str(item["capability_id"]): item for item in request.get("candidates") or []}
    used_assets: set[str] = set()
    used_source_keys: set[str] = set()
    sequences: list[dict[str, Any]] = []
    target_plans: list[dict[str, Any]] = []
    for target in request["targets"]:
        target_id = target["target_id"]
        target_start = float(target["start_seconds"])
        target_end = float(target["end_seconds"])
        if target["mode"] != "material":
            target_plans.append({
                "target_id": target_id, "scene_id": target["scene_id"], "mode": target["mode"],
                "status": "ready", "start_seconds": target_start, "end_seconds": target_end,
                "covered_seconds": round(target_end - target_start, 3), "missing_seconds": 0.0,
                "sequence_ids": [], "reason": target.get("reason") or "",
            })
            continue
        position = target_start
        sequence_ids: list[str] = []
        for raw in by_target[target_id]["clips"]:
            if not isinstance(raw, dict):
                raise MaterialSelectionError(f"{target_id} 的镜头格式无效")
            capability_id = str(raw.get("capability_id") or "")
            capability = candidates.get(capability_id)
            if capability is None:
                raise MaterialSelectionError(f"{target_id} 使用了未通过来源或质量筛选的镜头 {capability_id}")
            asset_id = str(capability["asset_id"])
            source_keys = material_source_keys(capability)
            if source_keys & used_source_keys:
                raise MaterialSelectionError(f"原视频 {asset_id} 在成片中重复使用")
            source_in = _number(raw.get("source_in_seconds", capability["source_in_seconds"]))
            duration = _number(raw.get("duration_seconds"))
            source_start, source_end = float(capability["source_in_seconds"]), float(capability["source_out_seconds"])
            if source_in < source_start - .001 or source_in >= source_end or duration <= 0:
                raise MaterialSelectionError(f"{target_id} 的源入点或镜头时长无效")
            if position + duration > target_end + .001 or source_in + duration > source_end + .001:
                raise MaterialSelectionError(f"{target_id} 的镜头超出了目标或已验证源范围")
            if duration < min(MIN_CLIP_SECONDS, target_end - target_start) - .001:
                raise MaterialSelectionError(f"{target_id} 的镜头过短")
            if capability.get("cut_policy") == "atomic" and (
                abs(source_in - source_start) > .001 or abs(duration - (source_end - source_start)) > .001
            ):
                raise MaterialSelectionError(f"{capability_id} 必须保留完整动作")
            reason = re.sub(r"\s+", " ", str(raw.get("match_reason") or "")).strip()[:240]
            confidence = _number(raw.get("semantic_confidence"))
            if not reason or confidence < .65 or confidence > 1:
                raise MaterialSelectionError(f"{target_id} 的语义匹配依据或置信度不足")
            if target.get("match_policy") == "exact":
                observed = " ".join(
                    [str(capability.get("summary") or ""), *(str(value) for value in capability.get("entities") or []),
                     *(str(value) for value in capability.get("actions") or []),
                     *(str(value) for value in capability.get("screen_text") or [])]
                ).casefold()
                if not any(str(term).casefold() in observed for term in target.get("must_show") or []):
                    raise MaterialSelectionError(f"{target_id} 的具体对象未出现在镜头视觉证据中")
            used_assets.add(asset_id)
            used_source_keys.update(source_keys)
            sequence_id = f"LMS-{len(sequences) + 1:03d}"
            display_end = round(position + duration, 3)
            evidence = {**deepcopy(capability["evidence"]), "overview": deepcopy(capability["overview_evidence"])}
            sequences.append({
                "sequence_id": sequence_id, "target_id": target_id, "scene_id": target["scene_id"],
                "capability_id": capability_id, "asset_id": asset_id,
                "platform": capability["platform"], "source_url": capability["source_url"],
                "license": capability["license"], "rights_status": capability["rights_status"],
                "source_in_seconds": round(source_in, 3), "source_out_seconds": round(source_in + duration, 3),
                "display_start_seconds": round(position, 3), "display_end_seconds": display_end,
                "visual_role": "local_full_bleed", "cut_policy": capability["cut_policy"],
                "muted": True, "playback_rate": 1.0, "evidence": evidence,
                "match_reason": reason, "semantic_confidence": round(confidence, 3),
            })
            sequence_ids.append(sequence_id)
            position = display_end
        deficit = round(max(0.0, target_end - position), 3)
        target_plans.append({
            "target_id": target_id, "scene_id": target["scene_id"], "mode": "material",
            "status": "ready" if deficit <= .001 else "needs_more_material",
            "start_seconds": target_start, "end_seconds": target_end,
            "covered_seconds": round(position - target_start, 3), "missing_seconds": deficit,
            "sequence_ids": sequence_ids, "reason": str(by_target[target_id].get("reason") or "")[:240],
        })
    scene_plans = []
    for scene in request["scenes"]:
        parts = [item for item in target_plans if item["scene_id"] == scene["scene_id"]]
        scene_plans.append({
            "scene_id": scene["scene_id"],
            "status": "ready" if all(item["status"] == "ready" for item in parts) else "needs_more_material",
            "duration_seconds": scene["duration_seconds"],
            "covered_seconds": round(sum(item["covered_seconds"] for item in parts), 3),
            "missing_seconds": round(sum(item["missing_seconds"] for item in parts), 3),
            "sequence_ids": [sequence_id for item in parts for sequence_id in item["sequence_ids"]],
            "reason": "按事先规划的画面目标匹配",
        })
    needs_more = any(item["status"] != "ready" for item in target_plans)
    result = {
        "version": VERSION, "status": "needs_more_material" if needs_more else "ready",
        "provider": request.get("execution_mode") or "agent", "model": model, "required_platform": request["required_platform"],
        "request_fingerprint": request["request_fingerprint"],
        "script_fingerprint": request["script_fingerprint"],
        "asset_index_fingerprint": request["asset_index_fingerprint"],
        "visual_need_fingerprint": request["visual_need_fingerprint"],
        "target_plans": target_plans, "scene_plans": scene_plans, "sequences": sequences,
        "rejected_candidates": deepcopy(request.get("rejected_candidates") or []),
        "publish_rights_status": (
            "review_required" if needs_more or any(
                item["rights_status"] not in {"renderable_with_attribution", "project_generated"} for item in sequences
            ) else "cleared_by_catalog"
        ),
        "acquisition_requests": [
            {
                "target_id": target["target_id"], "scene_id": target["scene_id"],
                "required_platform": request["required_platform"],
                "missing_seconds": next(item["missing_seconds"] for item in target_plans if item["target_id"] == target["target_id"]),
                "start_seconds": target["start_seconds"], "end_seconds": target["end_seconds"],
                "visual_intent": target["visual_intent"], "query_terms": target["query_terms"],
                "must_show": target["must_show"], "match_policy": target["match_policy"],
                "excluded_asset_ids": sorted(used_assets),
            }
            for target in request["targets"] if target["mode"] == "material"
            and next(item for item in target_plans if item["target_id"] == target["target_id"])["status"] != "ready"
        ],
    }
    result["fingerprint"] = _digest(result)
    return result
