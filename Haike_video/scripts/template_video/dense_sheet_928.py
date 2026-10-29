# -*- coding: utf-8 -*-
"""密集抽帧联系表: 全片按固定间隔抽帧, 网格拼图并标注时间戳, 用于精确定位
连续产品特写区间.

用法:
  python dense_sheet_928.py <out_prefix> <step_sec> <cols> <视频1> [视频2 ...]

输出: <out_prefix>_<basename>.jpg  (每个视频一张)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

# 路径收口：ffmpeg/ffprobe 由 _paths 解析（见同目录 _paths.py）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import FFMPEG, FFPROBE  # noqa: E402

TW, TH = 174, 310
FONT = os.environ.get("TEMPLATE_VIDEO_FONT_SANS") or r"C:\Windows\Fonts\msyh.ttc"


def probe_dur(path: str) -> float:
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True, text=True, timeout=30)
    return float(json.loads(r.stdout)["format"]["duration"])


def sheet_one(out_prefix: str, step: float, cols: int, path: str) -> None:
    dur = probe_dur(path)
    tmp = tempfile.mkdtemp(prefix="dense928_")
    try:
        r = subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-i", path,
             "-vf", f"fps=1/{step},scale={TW}:{TH}:force_original_aspect_ratio=increase,crop={TW}:{TH}",
             "-q:v", "3", os.path.join(tmp, "f_%04d.jpg")],
            capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            print("FFMPEG_FAIL", path, r.stderr[-200:])
            return
        frames = sorted(f for f in os.listdir(tmp) if f.endswith(".jpg"))
        if not frames:
            print("NO_FRAMES", path)
            return
        font = ImageFont.truetype(FONT, 13)
        lab_h = 18
        cols = min(cols, len(frames))
        rows_n = (len(frames) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (TW + 4) + 4, rows_n * (TH + lab_h + 4) + 4), (20, 20, 24))
        d = ImageDraw.Draw(sheet)
        for i, fn in enumerate(frames):
            t = i * step  # fps filter 第 i+1 张 ≈ (i)*step 秒
            img = Image.open(os.path.join(tmp, fn))
            img.load()
            cx = (i % cols) * (TW + 4) + 4
            cy = (i // cols) * (TH + lab_h + 4) + 4
            d.text((cx, cy), f"{t:.0f}s", font=font, fill=(255, 210, 80))
            sheet.paste(img, (cx, cy + lab_h))
            img.close()
        base = os.path.splitext(os.path.basename(path))[0]
        out = f"{out_prefix}_{base}.jpg"
        sheet.save(out, quality=80)
        print("SHEET:", out, f"dur={dur:.0f}s frames={len(frames)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    out_prefix = sys.argv[1]
    step = float(sys.argv[2])
    cols = int(sys.argv[3])
    files = sys.argv[4:]
    os.makedirs(os.path.dirname(out_prefix), exist_ok=True)
    for p in files:
        if os.path.isfile(p):
            sheet_one(out_prefix, step, cols, p)
        else:
            print("MISSING", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
