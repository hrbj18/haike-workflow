"""Deepblue N1 input contract. Layout values live only in the template JSON."""
from __future__ import annotations

import math
import re

from backlot.work_catalog import WorkError

TEMPLATE_ID = "avatar-deepblue-n1-v1"


def _text(value, maximum, label, *, empty=False):
    if not isinstance(value, str) or len(value.strip()) > maximum or (not empty and not value.strip()):
        raise WorkError(f"N1{label}需要{'0' if empty else '1'}至{maximum}字")
    if any(ord(c) < 32 and c not in "\n\t" for c in value): raise WorkError(f"N1{label}包含无效字符")
    return value.strip()


def _number(value, minimum, maximum, label):
    if type(value) not in {int, float} or not math.isfinite(value) or not minimum <= value <= maximum:
        raise WorkError(f"N1{label}超出有效范围")
    return value


def _local_agent(draft, studio):
    ai = draft.get("input", {}).get("ai") or {}
    if studio is None or not isinstance(ai, dict) or ai.get("enabled") is not True:
        return False
    from backlot.studio_storyboard import analysis_mode
    return analysis_mode(studio) == "agent"


def settings(draft, duration=None, studio=None):
    """Validate before charging; a known audio duration additionally checks scene ends."""
    raw = draft.get("input", {}).get("n1", {})
    if not isinstance(raw, dict) or set(raw) - {"titleLines", "sourceLabel", "brand", "englishLabel", "scenes", "emphasis"}:
        raise WorkError("N1版式配置包含不支持的字段")
    title = draft["title"].strip()
    lines = raw.get("titleLines")
    if lines is None or lines == [] or lines == ["", "", ""]:
        # New drafts use their own title; no sample headline enters ordinary production.
        parts = [s.strip() for s in re.split(r"[\n|｜]", title) if s.strip()]
        if len(parts) == 3:
            lines = parts
        elif len(title) <= 16:
            lines = [title, "", ""]
        else:
            lines = [title[:16], title[16:36], title[36:56]]
            if len(title) > 56: raise WorkError("N1标题最多56字，或另填三行标题")
    if not isinstance(lines, list) or len(lines) != 3:
        raise WorkError("N1标题需要三行")
    lines = [_text(line, limit, "标题", empty=i > 0) for i, (line, limit) in enumerate(zip(lines, (16, 20, 20)))]
    out = {"titleLines": lines, "sourceLabel": _text(raw.get("sourceLabel", "素材来源于网络"), 40, "来源", empty=True),
           "brand": _text(raw.get("brand", "海客科技"), 8, "品牌"),
           "englishLabel": _text(raw.get("englishLabel", "HAIKE"), 40, "英文标识", empty=True)}
    emphasis = raw.get("emphasis", [])
    if not isinstance(emphasis, list) or len(emphasis) > 12: raise WorkError("N1字幕最多设置12个重点词")
    out["emphasis"] = [_text(s, 12, "重点词") for s in emphasis]
    scenes = raw.get("scenes", [])
    if not isinstance(scenes, list) or len(scenes) > 24: raise WorkError("N1最多安排24段画面")
    ai = draft.get("input", {}).get("ai") or {}
    if not isinstance(ai, dict): raise WorkError("AI制作设置无效")
    from backlot.studio_network_materials import enabled
    if (ai.get("enabled") and not enabled(draft) and not _local_agent(draft, studio)
            or draft.get("input", {}).get("motion")):
        raise WorkError("N1首版请使用手工画面配置，暂不支持AI分镜或其他动效模板")
    previous = 0
    out["scenes"] = []
    for scene in scenes:
        if not isinstance(scene, dict) or set(scene) - {"kind", "start", "end", "assetId", "asset", "fit", "offset", "dataTitle", "dataLabel", "rows", "highlights"}:
            raise WorkError("N1画面配置包含不支持的字段")
        kind = scene.get("kind")
        if kind not in {"presenter", "material", "screenshot", "data"}: raise WorkError("N1主窗模式无效")
        start = _number(scene.get("start"), 0, 120, "画面起点")
        end = _number(scene.get("end"), 0, 120, "画面终点")
        if end <= start or start < previous - .001: raise WorkError("N1画面需按时间顺序排列且不能重叠")
        if duration is not None and end > duration + .05: raise WorkError("N1画面超出实际配音时长，请调整结束秒数")
        previous = end
        item = {"kind": kind, "start": start, "end": end}
        asset = scene.get("asset")
        if asset is not None:
            if not isinstance(asset, dict) or set(asset) - {"id", "name", "kind", "url"}: raise WorkError("N1素材资料无效")
            if any(not isinstance(v, str) or len(v) > 300 for v in asset.values()): raise WorkError("N1素材资料无效")
        if kind in {"material", "screenshot"}:
            asset_id = scene.get("assetId") or (asset or {}).get("id")
            if not isinstance(asset_id, str) or not re.fullmatch(r"[a-f0-9]{32}", asset_id): raise WorkError("N1此模式需要项目内图片或视频素材")
            if asset and asset.get("id") != asset_id: raise WorkError("N1素材编号不一致")
            item["assetId"] = asset_id
            item["offset"] = _number(scene.get("offset", 0), 0, 600, "素材起点")
            if studio is not None:
                path = studio.asset(asset_id, draft["id"])
                if path.suffix.lower() not in ({".png", ".jpg", ".jpeg"} if kind == "screenshot" else {".png", ".jpg", ".jpeg", ".mp4", ".mov"}):
                    raise WorkError("N1截图模式需要图片，素材模式需要图片或视频")
                if path.suffix.lower() in {".mp4", ".mov"}:
                    from backlot.studio_render import media_probe
                    if item["offset"] + end - start > media_probe(path)["duration"] + .05:
                        raise WorkError("N1素材视频时长不足，请补充片段或调整起止时间")
            fit = scene.get("fit", "contain" if kind == "screenshot" else "blur")
            if fit not in {"contain", "cover", "blur"} or kind == "screenshot" and fit != "contain":
                raise WorkError("N1截图需完整展示；素材适配支持留边、铺满或同源模糊")
            item["fit"] = fit
        elif scene.get("assetId") or asset:
            raise WorkError("N1主持人或数据模式不需要素材")
        if kind == "data":
            item["dataLabel"] = _text(scene.get("dataLabel", "信息摘要"), 12, "数据标签")
            item["dataTitle"] = _text(scene.get("dataTitle", ""), 16, "数据标题")
            rows = scene.get("rows")
            if not isinstance(rows, list) or not 1 <= len(rows) <= 4: raise WorkError("N1数据板需要1至4行")
            item["rows"] = [_text(row, 17, "数据行") for row in rows]
        elif any(scene.get(k) for k in ("dataLabel", "dataTitle", "rows")):
            raise WorkError("N1数据文字只能用于数据模式")
        highlights = scene.get("highlights", [])
        if not isinstance(highlights, list) or len(highlights) > 4: raise WorkError("N1截图最多四条高亮")
        if highlights and kind != "screenshot": raise WorkError("N1红线高亮只能用于截图模式")
        item["highlights"] = []
        for line in highlights:
            if not isinstance(line, dict) or set(line) - {"x", "y", "width", "start", "duration"}: raise WorkError("N1截图高亮配置无效")
            h = {k: _number(line.get(k), 0, 1, "高亮坐标") for k in ("x", "y", "width")}
            if h["width"] <= 0 or h["x"] + h["width"] > 1: raise WorkError("N1截图高亮超出图片")
            h["start"] = _number(line.get("start", 0), 0, end - start, "高亮起点")
            h["duration"] = _number(line.get("duration", .45), .05, end - start, "高亮时长")
            if h["start"] + h["duration"] > end - start: raise WorkError("N1截图高亮超出画面时长")
            item["highlights"].append(h)
        out["scenes"].append(item)
    return out


def storyboard_settings(draft, storyboard, duration, studio):
    """Compile verified ASR-bound footage without rewriting the saved manual draft."""
    from backlot.studio_network_materials import enabled
    from backlot.work_catalog import sha
    network = enabled(draft)
    ai = draft.get("input", {}).get("ai") or {}
    local_agent = (studio is not None and isinstance(ai, dict) and ai.get("enabled") is True
                   and storyboard.get("analysis_mode") == "agent")
    if not (network or local_agent) or storyboard.get("status") != "ready":
        raise WorkError("N1联网画面尚未核验完成，请恢复原素材任务")
    source_scenes = storyboard.get("scenes")
    if not isinstance(source_scenes, list) or not source_scenes:
        raise WorkError("N1联网画面为空，请补充合适素材后恢复原任务", "unavailable")
    if network and not any((scene.get("asset") or {}).get("provenance", {}).get("source") in {"douyin", "pexels"}
                           for scene in source_scenes):
        raise WorkError("联网素材已开启，N1尚未采用已核验的网络画面；请补充原素材任务", "unavailable")
    scenes, cursor = [], 0
    for scene in source_scenes:
        start, end = scene.get("start"), scene.get("end")
        _number(start, 0, duration, "联网画面起点")
        _number(end, 0, duration, "联网画面终点")
        if abs(start - cursor) > .001 or end <= start:
            raise WorkError("N1联网画面未连续覆盖真实配音时钟，请核对原分镜")
        asset = scene.get("asset") or {}
        if asset.get("provenance", {}).get("source") not in {"douyin", "pexels", "user"}:
            raise WorkError("N1联网画面来源未通过核验，请核对原素材")
        source = studio.asset(asset.get("id"), draft["id"])
        if sha(source) != scene.get("asset_sha256"):
            raise WorkError("N1联网分镜素材已变化，请恢复原素材")
        scenes.append({"kind": "material", "start": start, "end": end,
                       "assetId": asset["id"], "offset": asset.get("offset", 0), "fit": "blur"})
        cursor = end
    if abs(cursor - duration) > .001:
        raise WorkError("N1联网画面未覆盖真实配音结尾，请核对原分镜")
    raw = {**draft["input"].get("n1", {}), "scenes": scenes}
    compiled = {**draft, "input": {**draft["input"], "n1": raw}}
    if local_agent:
        # The verified plan freezes its analysis route; later account settings do not change it.
        compiled["input"]["ai"] = {**ai, "enabled": False}
    return settings(compiled, duration, studio)
