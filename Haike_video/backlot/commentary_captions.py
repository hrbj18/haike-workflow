"""Project caption presentation, independent of spoken text and its timestamps."""
from __future__ import annotations

import re
import unicodedata

from backlot.commentary_common import CommentaryError, text, number


def normalize_layout(raw):
    if not isinstance(raw, dict) or set(raw) - {"x", "y", "max_width"}:
        raise CommentaryError("字幕避让配置只接受中心横坐标、基线纵坐标和最大宽度")
    return {"x": number(raw.get("x"), "字幕中心横坐标", .1, .9),
        "y": number(raw.get("y"), "字幕基线纵坐标", .1, .9),
        "max_width": number(raw.get("max_width", .84), "字幕最大宽度", .1, .84)}


def anchor(segment, profile):
    layout = segment.get("subtitle_layout", {})
    return (round(profile["width"] * layout.get("x", .5)),
        round(profile["height"] * layout.get("y", .18 if segment["subtitle_position"] == "top" else .75)))


def normalize_style(raw):
    defaults = {"font_size": 64, "text_color": "#FFFFFF", "highlight_color": "#FFD54A",
                "highlight_terms": [], "outline_size": 3, "shadow": 1, "strip_punctuation": False}
    if not isinstance(raw, dict) or set(raw) - set(defaults):
        raise CommentaryError("字幕样式格式或字段无效")
    style = {**defaults, **raw}
    for key, low, high in (("font_size", 20, 96), ("outline_size", 0, 6), ("shadow", 0, 4)):
        if type(style[key]) is not int or not low <= style[key] <= high:
            raise CommentaryError(f"字幕 {key} 须为 {low} 至 {high} 的整数")
    for key in ("text_color", "highlight_color"):
        if not isinstance(style[key], str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", style[key]):
            raise CommentaryError("字幕颜色须为 #RRGGBB")
        style[key] = style[key].upper()
    if type(style["strip_punctuation"]) is not bool:
        raise CommentaryError("字幕去标点须为布尔值")
    if not isinstance(style["highlight_terms"], list) or len(style["highlight_terms"]) > 24:
        raise CommentaryError("字幕强调词须为不超过24项的列表")
    terms = []
    for value in style["highlight_terms"]:
        value = text(value, "字幕强调词", 30)
        if any(c in value for c in "{}\\\n\r\t"):
            raise CommentaryError("字幕强调词请用纯文本")
        value = display_text(value, style)
        if not value:
            raise CommentaryError("字幕强调词去标点后不能为空")
        if value not in terms: terms.append(value)
    style["highlight_terms"] = terms
    return style


def display_text(value, style=None):
    if not style or not style["strip_punctuation"]:
        return value
    result = []
    for index, char in enumerate(value):
        before = value[index-1] if index else ""
        after = value[index+1] if index+1 < len(value) else ""
        lexical = char in ".:'’：-/_" and before.isascii() and before.isalnum() and after.isascii() and after.isalnum()
        percent = char in "%％" and before.isdigit()
        if unicodedata.category(char).startswith("P") and not lexical and not percent:
            # Do not join two English words when removing their separator.
            if before.isascii() and before.isalnum() and after.isascii() and after.isalnum():
                result.append(" ")
        else:
            result.append(char)
    return "".join(result).strip()


def validate_layout(segment, profile, font_path, style=None):
    from PIL import ImageFont
    size = style["font_size"] if style else (36 if profile["height"] >= profile["width"] else 32)
    font = ImageFont.truetype(str(font_path), size)
    margin = (style["outline_size"] + style["shadow"] + 2) if style else 4
    for cue in segment.get("render_cues", segment["cues"]):
        placement = {**segment, "subtitle_layout": cue["subtitle_layout"]} if "subtitle_layout" in cue else segment
        x, y = anchor(placement, profile)
        raw = cue["text"]
        value = display_text(raw, style)
        length = font.getlength(value)
        if not value or any(c in raw for c in "{}\\\n\r") or length > profile["width"] * placement.get("subtitle_layout", {}).get("max_width", .84):
            raise CommentaryError(f"段落 {segment['id']} 的字幕超出安全宽度、去标点后为空或含控制字符，请拆成更短的逐句字幕")
        left, right = x - length/2 - margin, x + length/2 + margin
        top, bottom = y - size - margin, y + margin
        if left < 0 or right > profile["width"] or top < 0 or bottom > profile["height"]:
            raise CommentaryError("字幕超出画面，请调整避让位置或拆句")
        box = cue.get("presenter_geometry") if "presenter_geometry" in cue else segment.get("presenter", {}).get("geometry")
        if box:
            if left < box["x"]+box["size"] and right > box["x"] and top < box["y"]+box["size"] and bottom > box["y"]:
                raise CommentaryError(f"段落 {segment['id']} 的字幕与出镜圆形重叠，请调整字幕避让位置或出镜位置")
    return font


def ass_color(rgb):
    return "&H00" + rgb[5:7] + rgb[3:5] + rgb[1:3] + "&"


def ass_text(value, style=None):
    value = display_text(value, style)
    if not style or not style["highlight_terms"]:
        return value
    pattern = "|".join(re.escape(term) for term in sorted(style["highlight_terms"], key=len, reverse=True))
    return re.sub(pattern, lambda match: "{\\c" + ass_color(style["highlight_color"]) + "}" + match[0]
                  + "{\\c" + ass_color(style["text_color"]) + "}", value)
