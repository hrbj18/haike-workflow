"""Agent-authored visual targets before footage search or selection.

The target ledger separates *what the episode needs to show* from footage
already available. It is pure: no model calls, downloads, or timeline writes.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
from typing import Any

from backlot.local_material_orchestration import script_fingerprint


VERSION = 1
PROMPT_VERSION = "visual-needs-v1"
MODES = {"material", "preserve", "presenter"}
MATCH_POLICIES = {"exact", "topic", "atmosphere"}
MIN_TARGET_SECONDS = .4


class VisualNeedError(ValueError):
    """A visual requirement is stale, incomplete, or cannot be rendered."""


def _digest(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _seconds(value: Any) -> float:
    if isinstance(value, bool):
        raise VisualNeedError("画面目标时间不能是布尔值")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise VisualNeedError("画面目标时间无效") from exc
    if not math.isfinite(number):
        raise VisualNeedError("画面目标时间必须为有限数字")
    return round(number, 3)


def _complete_timeline(scene: dict[str, Any], assets: dict[str, dict[str, Any]]) -> bool:
    duration = _seconds(scene.get("end_seconds")) - _seconds(scene.get("start_seconds"))
    blocks = sorted(
        (block for block in ((scene.get("visual_timeline") or {}).get("blocks") or []) if isinstance(block, dict)),
        key=lambda block: _seconds(block.get("start_seconds")),
    )
    if not blocks or not all(
        assets.get(str(block.get("asset_id") or ""), {}).get("path")
        and block.get("status", "ready") == "ready" for block in blocks
    ):
        return False
    cursor = 0.0
    for block in blocks:
        start, end = _seconds(block.get("start_seconds")), _seconds(block.get("end_seconds"))
        if abs(start - cursor) > .02 or end <= start:
            return False
        cursor = end
    return abs(cursor - duration) <= .02


def prepare_visual_need_task(state: dict[str, Any], *, model: str) -> dict[str, Any]:
    """Expose dialogue, clock and legitimate non-footage bases to the agent."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", model or ""):
        raise VisualNeedError("请记录有效的当前 agent 模型")
    scenes = sorted(
        (scene for scene in state.get("scenes") or [] if isinstance(scene, dict)),
        key=lambda scene: (_seconds(scene.get("start_seconds")), str(scene.get("id") or "")),
    )
    if not scenes:
        raise VisualNeedError("请先建立场景与时间线")
    avatar_project = str((state.get("project") or {}).get("pipeline_type") or "") == "avatar-spokesperson"
    assets = {str(asset.get("id") or ""): asset for asset in state.get("assets") or [] if isinstance(asset, dict)}
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for scene in scenes:
        scene_id = str(scene.get("id") or "")
        if not scene_id or scene_id in seen:
            raise VisualNeedError("场景 ID 缺失或重复")
        seen.add(scene_id)
        start, end = _seconds(scene.get("start_seconds")), _seconds(scene.get("end_seconds"))
        if start < 0 or end - start < .04:
            raise VisualNeedError("场景时间范围无效")
        presenter = scene.get("presenter") if isinstance(scene.get("presenter"), dict) else {}
        narration = scene.get("narration") if isinstance(scene.get("narration"), dict) else {}
        treatment = str(presenter.get("treatment") or "hidden")
        presenter_ready = bool(avatar_project and treatment == "fullscreen" and str(presenter.get("source_path") or "").strip())
        has_existing = _complete_timeline(scene, assets)
        summaries.append({
            "scene_id": scene_id,
            "duration_seconds": round(end - start, 3),
            "title": str(scene.get("title") or "")[:160],
            "spoken_text": str(narration.get("text") or scene.get("description") or "")[:3000],
            "visual_intent": str(scene.get("shot_intent") or "")[:1000],
            "presenter_fullscreen_ready": presenter_ready,
            "existing_visual_timeline_ready": has_existing,
            "existing_visual_intervals": [
                {"start_seconds": block.get("start_seconds"), "end_seconds": block.get("end_seconds")}
                for block in ((scene.get("visual_timeline") or {}).get("blocks") or []) if isinstance(block, dict)
            ] if has_existing else [],
            "presenter_treatment": treatment if avatar_project else "none",
            "visual_timeline_fingerprint": _digest((scene.get("visual_timeline") or {}).get("blocks") or []),
        })
    task = {
        "version": VERSION, "execution_mode": "agent", "model": model,
        "prompt_version": PROMPT_VERSION,
        "script_fingerprint": script_fingerprint(state), "scenes": summaries,
    }
    task["task_fingerprint"] = _digest(task)
    return task


def build_visual_need_plan(task: dict[str, Any], proposal: dict[str, Any], *, model: str) -> dict[str, Any]:
    """Check a full partition of every scene and freeze variable visual targets."""
    if model != task.get("model"):
        raise VisualNeedError("画面目标模型与任务模型不一致")
    supplied = proposal.get("scenes") if isinstance(proposal, dict) else None
    if not isinstance(supplied, list) or len(supplied) != len(task["scenes"]):
        raise VisualNeedError("画面目标必须包含全部场景，且每场景只出现一次")
    by_scene: dict[str, dict[str, Any]] = {}
    for item in supplied:
        if not isinstance(item, dict) or not isinstance(item.get("segments"), list):
            raise VisualNeedError("画面目标场景格式无效")
        scene_id = str(item.get("scene_id") or "")
        if scene_id in by_scene:
            raise VisualNeedError("画面目标重复了同一场景")
        by_scene[scene_id] = item
    if set(by_scene) != {scene["scene_id"] for scene in task["scenes"]}:
        raise VisualNeedError("画面目标存在未知或遗漏的场景")
    plans: list[dict[str, Any]] = []
    for scene_number, scene in enumerate(task["scenes"], 1):
        scene_id = scene["scene_id"]
        duration = scene["duration_seconds"]
        segments = by_scene[scene_id]["segments"]
        if not 1 <= len(segments) <= 120:
            raise VisualNeedError(f"{scene_id} 需要 1—120 个有意义的画面段")
        cursor = 0.0
        targets: list[dict[str, Any]] = []
        for number, raw in enumerate(segments, 1):
            if not isinstance(raw, dict):
                raise VisualNeedError(f"{scene_id} 的画面段格式无效")
            start, end = _seconds(raw.get("start_seconds")), _seconds(raw.get("end_seconds"))
            if abs(start - cursor) > .012 or end > duration + .012 or end - start < min(MIN_TARGET_SECONDS, duration) - .001:
                raise VisualNeedError(f"{scene_id} 的画面段必须无重叠、无空白且不少于最短可剪时长")
            mode = str(raw.get("mode") or "")
            if mode not in MODES:
                raise VisualNeedError(f"{scene_id} 的画面承接方式无效")
            if mode == "presenter" and not scene["presenter_fullscreen_ready"]:
                raise VisualNeedError(f"{scene_id} 没有可单独承接画面的全屏数字人")
            if mode == "preserve" and not scene["existing_visual_timeline_ready"]:
                raise VisualNeedError(f"{scene_id} 没有可保留的完整主体画面时间线")
            if mode == "material" and scene["presenter_fullscreen_ready"]:
                raise VisualNeedError(f"{scene_id} 使用全屏数字人；先调整为可显示主体画面的版式再规划外部素材")
            intent = re.sub(r"\s+", " ", str(raw.get("visual_intent") or "")).strip()[:500]
            if not isinstance(raw.get("query_terms") or [], list) or not isinstance(raw.get("must_show") or [], list):
                raise VisualNeedError(f"{scene_id} 的检索词和必现要素必须是列表")
            terms = [re.sub(r"\s+", " ", str(value)).strip()[:100] for value in raw.get("query_terms") or []]
            terms = list(dict.fromkeys(value for value in terms if value))[:8]
            if mode == "material" and (not intent or not terms):
                raise VisualNeedError(f"{scene_id} 的外部素材目标缺少画面意图或检索词")
            must_show = [str(value).strip()[:100] for value in raw.get("must_show") or [] if str(value).strip()][:8]
            policy = str(raw.get("match_policy") or "topic")
            if mode == "material" and policy not in MATCH_POLICIES:
                raise VisualNeedError(f"{scene_id} 的素材匹配策略无效")
            if mode == "material" and policy == "exact" and not must_show:
                raise VisualNeedError(f"{scene_id} 的精确匹配目标必须说明哪些要素应当可见")
            targets.append({
                "target_id": f"VT-{scene_number:03d}-{number:03d}", "scene_id": scene_id,
                "start_seconds": start, "end_seconds": end,
                "duration_seconds": round(end - start, 3), "mode": mode,
                "visual_intent": intent, "query_terms": terms if mode == "material" else [],
                "must_show": must_show if mode == "material" else [],
                "match_policy": policy if mode == "material" else "not_applicable",
                "reason": str(raw.get("reason") or "")[:300],
            })
            cursor = end
        if abs(cursor - duration) > .012:
            raise VisualNeedError(f"{scene_id} 的画面目标没有覆盖完整场景")
        plans.append({"scene_id": scene_id, "duration_seconds": duration, "targets": targets})
    result = {
        "version": VERSION, "model": model, "execution_mode": "agent",
        "task_fingerprint": task["task_fingerprint"],
        "script_fingerprint": task["script_fingerprint"],
        "scenes": plans,
    }
    result["fingerprint"] = _digest(result)
    return result


def material_targets(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [deepcopy(target) for scene in plan.get("scenes") or [] for target in scene.get("targets") or [] if target.get("mode") == "material"]


def validate_current_visual_need_plan(state: dict[str, Any], plan: dict[str, Any], *, model: str) -> None:
    if not isinstance(plan, dict) or plan.get("version") != VERSION:
        raise VisualNeedError("请先由当前 agent 规划画面目标")
    if plan.get("model") != model or plan.get("task_fingerprint") != prepare_visual_need_task(state, model=model)["task_fingerprint"]:
        raise VisualNeedError("画面目标与当前模型、脚本或版式不一致，请重新规划")
    if plan.get("fingerprint") != _digest({key: value for key, value in plan.items() if key not in {"fingerprint", "created_at"}}):
        raise VisualNeedError("画面目标记录已损坏，请重新规划")
