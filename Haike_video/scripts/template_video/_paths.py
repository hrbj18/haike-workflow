# -*- coding: utf-8 -*-
"""模板图文视频流水线 · 路径收口点（single source of truth）。

设计约束
--------
1. **不硬编码任何绝对路径** —— 一律从本文件位置推导，或由环境变量覆盖。
   对齐 ``Haike-Videohub/contracts/layout.json`` 的硬约束：
   「任何自动化脚本都必须按本文件解析路径，不得硬编码」。
2. 与本仓 ``lib/paths.py`` 的 ``REPO_ROOT + 环境变量覆盖`` 模式保持一致。
3. 本目录 ``scripts/template_video/`` 是这条流水线的**正式位置**；原先寄居在
   ``.backlot/_diag/923-batch/``（该目录整体被 ``.gitignore`` 第 109 行忽略
   ⇒ 不入版本控制、跨机丢失、也不受上游同步保护）。

目录推导
--------
    _paths.py                          (本文件)
    parents[0]  scripts/template_video/
    parents[1]  scripts/
    parents[2]  Haike_video/                        -> HAIKE_ROOT
    parents[3]  四仓根 haike-workflow/              -> VIDEOHUB_ROOT（三仓的父目录）

环境变量（全部可选，给了就优先）
--------------------------------
    VIDEOHUB_ROOT              四仓根目录（默认＝Haike_video 的父目录；standalone 检出时用）
    OPENMONTAGE_PROJECTS_DIR   工程库目录（默认 ``Haike_video/projects``）
    OPENMONTAGE_MUSIC_DIR      BGM 曲库（默认 ``Haike_video/song``）
    OPENMONTAGE_MODELS_DIR     模型目录（默认 ``Haike_video/models``）
    VRF929_FACE_MODEL          人脸门禁模型（默认 ``models/yunet.onnx``）
    TEMPLATE_VIDEO_WORK        本流水线工作数据目录（默认 ``.backlot/_diag/923-batch``）
    FFMPEG_BINARY              ffmpeg 可执行文件

用法
----
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _paths import WORK_DIR, MUSIC_DIR, FACE_MODEL, FFMPEG
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# --- 仓库根（从本文件位置推导，不写盘符） ------------------------------------

_HERE = Path(__file__).resolve()
SCRIPT_DIR = _HERE.parent                       # scripts/template_video/
SCRIPTS_DIR = SCRIPT_DIR.parent                 # scripts/
HAIKE_ROOT = SCRIPTS_DIR.parent                 # Haike_video/
# 四仓根（三仓的父目录）：默认由本文件位置推导；可用 ``VIDEOHUB_ROOT`` 覆盖
# —— 对齐 contracts/layout.json 的 root_definition.env_var（standalone 检出时无兄弟仓，
#    可显式给根目录）。仅影响跨仓数据路径（COPY_SKILL_OUT），不影响本仓内的脚本/资源。
VIDEOHUB_ROOT = Path(os.environ.get("VIDEOHUB_ROOT") or HAIKE_ROOT.parent)

# --- 目录（环境变量优先，与 lib/paths.py 同款模式） --------------------------

PROJECTS_DIR = Path(os.environ.get("OPENMONTAGE_PROJECTS_DIR") or (HAIKE_ROOT / "projects"))
MUSIC_DIR = Path(os.environ.get("OPENMONTAGE_MUSIC_DIR") or (HAIKE_ROOT / "song"))
MODELS_DIR = Path(os.environ.get("OPENMONTAGE_MODELS_DIR") or (HAIKE_ROOT / "models"))
def _ascii_safe(path: Path) -> Path:
    """把模型路径解析成 cv2 一定能打开的形式。

    cv2 5.0 的 ONNX 读取器打不开含非 ASCII 字符的路径 —— 2026-09-29 实测：
    ``cv2.FaceDetectorYN_create("<...>\\示例用户\\...\\yunet.onnx")`` 报
    ``Can't read ONNX file``；同一文件换纯 ASCII 路径即正常。

    模型仍以**项目内路径为准**（可入库、可审计、跨机自带），只在运行时镜像一份到
    本机 ASCII 缓存目录（``%LOCALAPPDATA%\\videohub-models``）再交给 cv2。
    """
    try:
        str(path).encode("ascii")
        return path
    except UnicodeEncodeError:
        pass
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    cache = Path(base) / "videohub-models"
    cache.mkdir(parents=True, exist_ok=True)
    mirror = cache / path.name
    try:
        if not mirror.is_file() or mirror.stat().st_size != path.stat().st_size:
            shutil.copy2(path, mirror)
    except OSError:
        return path  # 镜像失败就原样返回，让调用方拿到真实报错
    return mirror


FACE_MODEL = _ascii_safe(Path(os.environ.get("VRF929_FACE_MODEL") or (MODELS_DIR / "yunet.onnx")))

# 采集端交付目录（copy_skill 输出）。★ 这是**数据来源**，不是解释器/代码依赖：
# 按 layout.json 的兄弟布局解析（copy_skill/copy_skill-main 必须是两层），不写死盘符。
COPY_SKILL_OUT = VIDEOHUB_ROOT / "copy_skill" / "copy_skill-main" / "output" / "复刻视频"

# 本流水线的工作数据目录：中间产物（raw923/）、成片（short_out/）、交付归档（final_929/）、
# 候选表（sheets929/）。默认沿用既有目录以便平滑迁移；新批次可设 TEMPLATE_VIDEO_WORK 另起。
WORK_DIR = Path(
    os.environ.get("TEMPLATE_VIDEO_WORK") or (HAIKE_ROOT / ".backlot" / "_diag" / "923-batch")
)


# --- ffmpeg ------------------------------------------------------------------

def ffmpeg() -> str:
    """解析 ffmpeg 路径：``FFMPEG_BINARY`` → PATH → 本仓 ``lib.ffmpeg_locator``。

    永不返回 ``None``（调用方广泛依赖它是可用的字符串）。前面所有命令实测 PATH 里有
    ffmpeg，所以正常路径是第 1、2 步；第 3 步只为跨机兜底。
    """
    override = os.environ.get("FFMPEG_BINARY")
    if override and Path(override).is_file():
        return override
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import sys

        if str(HAIKE_ROOT) not in sys.path:
            sys.path.insert(0, str(HAIKE_ROOT))
        from lib.ffmpeg_locator import resolve_ffmpeg  # type: ignore

        found = resolve_ffmpeg()
        if found:
            return found
    except Exception:
        pass
    return "ffmpeg"


FFMPEG = ffmpeg()


def ffprobe() -> str:
    """与 :func:`ffmpeg` 配套的 ffprobe：优先 PATH，再取与 ffmpeg 同目录。"""
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    ff = Path(FFMPEG)
    sibling = ff.with_name("ffprobe.exe" if ff.suffix.lower() == ".exe" else "ffprobe")
    return str(sibling) if sibling.is_file() else "ffprobe"


FFPROBE = ffprobe()

__all__ = [
    "SCRIPT_DIR",
    "SCRIPTS_DIR",
    "HAIKE_ROOT",
    "VIDEOHUB_ROOT",
    "PROJECTS_DIR",
    "MUSIC_DIR",
    "MODELS_DIR",
    "FACE_MODEL",
    "COPY_SKILL_OUT",
    "WORK_DIR",
    "FFMPEG",
    "ffmpeg",
    "FFPROBE",
    "ffprobe",
]
