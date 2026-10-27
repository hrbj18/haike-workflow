"""Investment A v6: validated text and ASR-bound overlays, without paid stages."""
from __future__ import annotations

import math
import re

from backlot.work_catalog import WorkError

TEMPLATE_ID = "avatar-investment-a-v6"


def _text(value, limit, label, *, empty=False):
    if (not isinstance(value, str) or len(value.strip()) > limit
            or (not empty and not value.strip())
            or any(ord(c) < 32 and c not in "\n\t" for c in value)):
        raise WorkError(f"招商A{label}需要{'0' if empty else '1'}至{limit}字")
    return value.strip()


def normalized(value):
    """Match ASR display splits and punctuation without inventing timestamps."""
    digits = {char: index for index, char in enumerate("零一二三四五六七八九")}
    digits.update({"〇": 0, "两": 2})
    def integer(match):
        left, right = match[0].split("十")
        return str(digits.get(left, 1) * 10 + digits.get(right, 0))
    # ASR commonly writes 十四个月 as 14个月. Keep large units and decimals
    # outside this narrow equivalence; they must not acquire guessed values.
    value = re.sub(r"(?<![零〇一二两三四五六七八九十百千万亿\d.点])[一二两三四五六七八九]?十[一二三四五六七八九]?(?![零〇一二两三四五六七八九十百千万亿\d.点])", integer, value)
    return re.sub(r"[^\w\u3400-\u9fff]", "", value, flags=re.UNICODE).lower()


def settings(draft, duration=None):
    raw = draft.get("input", {}).get("investment", {})
    if not isinstance(raw, dict) or set(raw) - {"brand", "headline", "cta", "emphasis", "opening", "closing"}:
        raise WorkError("招商A版式配置包含不支持的字段")
    if draft.get("input", {}).get("motion"):
        raise WorkError("招商A使用固定招商动效，请清空其他动效模板")
    out = {"brand": _text(raw.get("brand", "海客科技"), 14, "项目名称"),
           "headline": _text(raw.get("headline") or draft["title"], 32, "封面标题"),
           "cta": _text(raw.get("cta", "点击视频下方链接\n加入我们"), 32, "结尾引导")}
    if "\n" in out["brand"]: raise WorkError("招商A项目名称请使用一行")
    for key in ("headline", "cta"):
        if len(out[key].splitlines()) > 2 or any(not line.strip() for line in out[key].splitlines()):
            raise WorkError("招商A封面标题和结尾引导最多两行，不能包含空白行")
    for key in ("opening", "closing"):
        out[key] = raw.get(key, True)
        if type(out[key]) is not bool: raise WorkError("招商A开头和结尾开关需要明确开启或关闭")
    entries = raw.get("emphasis", [])
    if not isinstance(entries, list) or len(entries) > 32:
        raise WorkError("招商A最多设置32条重点内容")
    out["emphasis"] = []
    matches = set()
    for entry in entries:
        if isinstance(entry, str): entry = {"match": entry, "text": entry}
        if not isinstance(entry, dict) or set(entry) - {"match", "text", "kind", "detail", "footnote"}:
            raise WorkError("招商A重点内容字段无效")
        match = _text(entry.get("match"), 48, "触发原文")
        if not normalized(match) or normalized(match) in matches:
            raise WorkError("招商A触发原文不能为空或重复")
        matches.add(normalized(match))
        kind = entry.get("kind", "sticker")
        if kind not in {"sticker", "card"}: raise WorkError("招商A重点形式请选择贴纸或信息卡")
        out["emphasis"].append({"match": match, "text": _text(entry.get("text", match), 18, "重点标题"),
                                 "kind": kind, "detail": _text(entry.get("detail", ""), 48, "信息卡说明", empty=True),
                                 "footnote": _text(entry.get("footnote", ""), 64, "信息卡注释", empty=True)})
    if duration is not None and (type(duration) not in {int, float} or not math.isfinite(duration) or not 0 < duration <= 120):
        raise WorkError("招商A单段口播需要在120秒内；长稿请分段复用原音轨")
    return out


def semantic_events(config, cues, duration):
    """Bind each phrase to its first observed ASR span, including split captions.

    An unmatched phrase is reported, never evenly distributed over the script.
    Source cue indices and actual cue bounds remain in the audit receipt.
    """
    spans, combined = [], ""
    for index, cue in enumerate(cues):
        text, start, end = cue.get("text"), cue.get("startMs"), cue.get("endMs")
        if (not isinstance(text, str) or type(start) not in {int, float} or type(end) not in {int, float}
                or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= duration * 1000 + 1):
            raise WorkError("招商A字幕时钟无效，请恢复原识别结果")
        if len(text.replace("\n", "")) > 28:
            raise WorkError("招商A显示字幕每条最多28字、两行；请使用原识别时钟拆分显示字幕")
        part = normalized(text)
        spans.append((len(combined), len(combined) + len(part), index, start / 1000, min(duration, end / 1000)))
        combined += part
    events, unmatched = [], []
    for index, entry in enumerate(config["emphasis"]):
        match = normalized(entry["match"])
        offset = combined.find(match)
        covered = [s for s in spans if s[0] < offset + len(match) and s[1] > offset] if offset >= 0 else []
        if not covered:
            unmatched.append({"emphasis_index": index, "match": entry["match"]})
            continue
        first, last = covered[0], covered[-1]
        events.append({**entry, "id": f"emphasis-{index}", "start": first[3],
                       "end": min(duration, max(last[4] + .35, first[3] + 1.5)),
                       "fromCue": first[2], "toCue": last[2], "asrStart": first[3], "asrEnd": last[4]})
    events.sort(key=lambda event: event["start"])
    # Preserve every selected event. Two phrases in one cue become a multi-card.
    for i, event in enumerate(events[:-1]):
        next_start = next((e["start"] for e in events[i + 1:] if e["start"] > event["start"] + .001), None)
        if next_start is not None: event["end"] = min(event["end"], next_start)
    if any(sum(other["start"] <= event["start"] < other["end"] for other in events) > 3 for event in events):
        raise WorkError("招商A同一字幕最多展示3条重点，请合并该句的重点卡后恢复原任务")
    return events, unmatched


def render_props(draft, duration, cues):
    config = settings(draft, duration)
    events, unmatched = semantic_events(config, cues, duration)
    return {"duration": duration, "investment": config, "captions": cues if draft["input"].get("subtitles", True) else [], "events": events,
            "avatarSrc": "avatar.mp4", "audioSrc": "narration.wav"}, {
                "template_adapter": TEMPLATE_ID, "clock": "supplied_caption_cues",
                "events": events, "unmatched": unmatched,
                "illustration_policy": "只有原稿关键词与数据卡；信息卡不代表实拍或外部事实核验"}
