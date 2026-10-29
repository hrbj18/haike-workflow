# -*- coding: utf-8 -*-
"""按 spec 抽帧做「成片视角」检查图（版式 v2 参考线 650/1280）。

用法: python _frame_check.py <spec_json> <out.jpg> [每格宽]

输出：每个 cue 一行，每行 3 格（source_in+0.5/1.5/2.5），
      顶板带(0..650)与底字板带(1280..1920)压半透明遮罩，只留中央可见带高亮，
      便于一眼看出「中央可见区是否有烧录字幕/水印、主体是否落在带内」。
"""
from __future__ import annotations

import io
import json
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
PLATE_TOP, PLATE_BOT = 650, 1280
SCALE = ("scale=1080:1920:force_original_aspect_ratio=increase,"
         "crop=1080:1920,setsar=1")

spec_path, out_path = sys.argv[1], sys.argv[2]
CW = int(sys.argv[3]) if len(sys.argv) > 3 else 330
CH = int(round(CW * H / W))
LAB = 18

cues = json.load(open(spec_path, encoding="utf-8"))
if len(sys.argv) > 4 and sys.argv[4] != "-":
    lo, hi = sys.argv[4].split("-")
    cues = cues[int(lo) - 1:int(hi)]
font = ImageFont.truetype(FONT, 14)

rows = len(cues)
sheet = Image.new("RGB", (3 * (CW + 4) + 4, rows * (CH + LAB + 4) + 4), (16, 16, 20))
d = ImageDraw.Draw(sheet)

with tempfile.TemporaryDirectory(prefix="fchk_") as td:
    for r, cue in enumerate(cues):
        fin = float(cue["source_in"])
        for c, off in enumerate((0.5, 1.5, 2.5)):
            tmp = os.path.join(td, "f.png")
            res = subprocess.run(
                [FFMPEG, "-y", "-loglevel", "error", "-ss", str(fin + off), "-i", cue["file"],
                 "-frames:v", "1", "-vf", SCALE, tmp],
                capture_output=True, text=True, timeout=60)
            x = c * (CW + 4) + 4
            y = r * (CH + LAB + 4) + 4
            if res.returncode != 0 or not os.path.isfile(tmp):
                d.text((x, y), "FAIL", font=font, fill=(255, 90, 90))
                continue
            img = Image.open(tmp).convert("RGB")
            # 成片视角：顶/底字板压暗
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            od.rectangle((0, 0, W, PLATE_TOP), fill=(0, 0, 0, 235))
            od.rectangle((0, PLATE_BOT, W, H), fill=(0, 0, 0, 235))
            img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
            dd = ImageDraw.Draw(img)
            dd.rectangle((0, PLATE_TOP, W, PLATE_TOP + 5), fill=(255, 205, 60))
            dd.rectangle((0, PLATE_BOT - 5, W, PLATE_BOT), fill=(255, 205, 60))
            dd.text((8, PLATE_TOP + 10), "VISIBLE 650-1280", font=font, fill=(255, 205, 60))
            img = img.resize((CW, CH))
            sheet.paste(img, (x, y + LAB))
            d.text((x, y), f"{cue['cue']}  @{fin + off:.1f}s", font=font, fill=(235, 235, 235))
            img.close()

sheet.save(out_path, quality=88)
print("SAVED", out_path, sheet.size)
