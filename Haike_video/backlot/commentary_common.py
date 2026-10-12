"""Small shared primitives for the material-led commentary workflow."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from uuid import uuid4

from backlot.material_library import digest, number
from backlot.material_catalog_import import file_sha256
from lib.ffmpeg_locator import resolve_ffmpeg_pair
from lib.subprocess_window import no_window_kwargs

WORKFLOW = "material-commentary"
VERSION = "material-commentary-v1"
FPS = 30
RATE = 48000
SAMPLES_PER_FRAME = RATE // FPS
FORMATS = {"portrait": (720, 1280), "landscape": (1280, 720), "square": (720, 720)}


class CommentaryError(ValueError):
    pass


class CommentaryConflict(CommentaryError):
    pass


def text(value, label, maximum=2000, *, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise CommentaryError(f"{label}须为{'零' if empty else '一'}至{maximum}字的文字")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise CommentaryError(f"{label}含控制字符")
    return value.strip()


def identifier(value, prefix=""):
    pattern = re.escape(prefix) + (r"[a-f0-9]{64}" if prefix else r"[A-Za-z0-9_-]{1,80}")
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise CommentaryError("编号无效")
    return value


def project_dir(identity, root):
    if not isinstance(identity, str) or not re.fullmatch(r"commentary-[a-f0-9]{16}", identity):
        raise CommentaryError("素材解说项目编号无效")
    root = Path(root).resolve()
    path = (root / identity).resolve()
    if not path.is_relative_to(root):
        raise CommentaryError("项目目录越界")
    return path


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + uuid4().hex[:8] + ".tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (OSError, ValueError) as exc:
        raise CommentaryError("制作记录不存在或损坏，请检查项目文件") from exc


def immutable(path, data):
    path = Path(path)
    if path.exists():
        if read_json(path) != data:
            raise CommentaryConflict("已冻结的记录不允许覆盖，请创建新版本")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also prevents a concurrent editor replacing this version.
    try:
        with path.open("x", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2, allow_nan=False)
    except FileExistsError:
        if read_json(path) != data:
            raise CommentaryConflict("制作记录正在更新，请重新读取")


def media_tools():
    pair = resolve_ffmpeg_pair()
    if not pair:
        raise CommentaryError("未找到 FFmpeg/ffprobe，请检查项目媒体依赖")
    return pair


def subtitle_font():
    choices = [os.environ.get("OPENMONTAGE_COMMENTARY_FONT", ""), "C:/Windows/Fonts/msyh.ttc",
               "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    path = next((Path(p).resolve() for p in choices if p and Path(p).is_file()), None)
    if not path:
        raise CommentaryError("缺少中文字幕字体，请配置 OPENMONTAGE_COMMENTARY_FONT")
    return {"path": str(path), "sha256": file_sha256(path)}


def run(argv, *, timeout=900, cwd=None):
    result = subprocess.run([str(v) for v in argv], capture_output=True, timeout=timeout,
                            cwd=cwd, **no_window_kwargs())
    if result.returncode:
        # Do not put provider responses, command lines or local secrets in the UI.
        raise CommentaryError("本地媒体处理失败，请检查源文件、字幕字体和磁盘空间")
    return result


def probe(path):
    return json.loads(run([media_tools()[1], "-v", "error", "-show_streams", "-show_format",
                           "-of", "json", path], timeout=90).stdout)


def verified(path, sha):
    path = Path(path)
    if not path.is_file() or file_sha256(path) != sha:
        raise CommentaryError("素材或缓存内容已变化，旧证据不可沿用；请重新登记或恢复原文件")
    return path


def crop_value(raw):
    raw = raw or {"x": 0, "y": 0, "w": 1, "h": 1}
    if not isinstance(raw, dict) or set(raw) != {"x", "y", "w", "h"}:
        raise CommentaryError("裁切须包含 x、y、w、h")
    value = {k: number(raw[k], "裁切坐标", 0, 1) for k in raw}
    if min(value["w"], value["h"]) < .05 or value["x"] + value["w"] > 1.000001 or value["y"] + value["h"] > 1.000001:
        raise CommentaryError("裁切越界或区域太小")
    return value


def crop_filter(crop):
    return (f"crop=w=trunc(iw*{crop['w']}/2)*2:h=trunc(ih*{crop['h']}/2)*2:"
            f"x=trunc(iw*{crop['x']}/2)*2:y=trunc(ih*{crop['y']}/2)*2")
