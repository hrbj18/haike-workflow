# -*- coding: utf-8 -*-
"""裁出成片「中央可见带」(canvas y650..1280) 原尺寸图，用于逐像素核对
是否有烧录字幕/水印落入该带。

用法: python _band_crop.py <out.jpg> <video:t> [video:t ...]
每格 = 1080x630，纵向堆叠，格间 6px 分隔。
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 路径收口：ffmpeg 由 _paths 解析（见同目录 _paths.py）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import FFMPEG  # noqa: E402

FONT = os.environ.get("TEMPLATE_VIDEO_FONT_SANS") or r"C:\Windows\Fonts\msyh.ttc"
W, H = 1080, 1920
TOP, BOT = 650, 1280
BAND_H = BOT - TOP
SCALE = ("scale=1080:1920:force_original_aspect_ratio=increase,"
         "crop=1080:1920,setsar=1")

out_path = sys.argv[1]
items = []
for a in sys.argv[2:]:
    v, t = a.rsplit(":", 1)
    items.append((v, float(t), os.path.basename(v)[:28]))

font = ImageFont.truetype(FONT, 20)
sheet = Image.new("RGB", (W + 8, len(items) * (BAND_H + 30 + 6) + 6), (14, 14, 18))
d = ImageDraw.Draw(sheet)

with tempfile.TemporaryDirectory(prefix="band_") as td:
    for i, (v, t, name) in enumerate(items):
        tmp = os.path.join(td, "f.png")
        r = subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-ss", str(t), "-i", v,
             "-frames:v", "1", "-vf", SCALE, tmp],
            capture_output=True, text=True, timeout=60)
        y = i * (BAND_H + 30 + 6) + 6
        if r.returncode != 0 or not os.path.isfile(tmp):
            d.text((8, y), "FAIL " + name, font=font, fill=(255, 90, 90))
            continue
        img = Image.open(tmp).convert("RGB")
        band = img.crop((0, TOP, W, BOT))
        sheet.paste(band, (4, y + 30))
        d.text((8, y + 4), f"{name} @{t:.1f}s   [canvas y{TOP}-{BOT}]",
               font=font, fill=(255, 205, 60))
        img.close(); band.close()

sheet.save(out_path, quality=92)
print("SAVED", out_path, sheet.size)
