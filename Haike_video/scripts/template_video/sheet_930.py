# -*- coding: utf-8 -*-
"""给候选素材生成联系表（contact sheet），用于人眼确认画面内容。

用法: python sheet_930.py <out_dir> <folder> <每?秒一帧> <tile> [关键词过滤...]
"""
import io
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import COPY_SKILL_OUT as DELIV, FFMPEG  # noqa: E402

out_dir, folder, step, tile = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
kws = sys.argv[5:]
os.makedirs(out_dir, exist_ok=True)

import json  # noqa: E402
idx = os.path.join(DELIV, folder, "00-素材目录.json")
for e in json.load(open(idx, encoding="utf-8")).get("entries", []):
    rel = e.get("file_path", "")
    base = os.path.basename(rel)
    if kws and not any(k in base for k in kws):
        continue
    src = os.path.join(DELIV, folder, rel.replace("/", os.sep))
    if not os.path.isfile(src):
        continue
    tag = os.path.splitext(base)[0]
    out = os.path.join(out_dir, f"{folder[:6]}_{tag}.jpg")
    if os.path.isfile(out):
        print("skip(exists)", os.path.basename(out))
        continue
    vf = f"fps=1/{step},scale=200:-2,tile={tile}"
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", src,
                        "-vf", vf, "-frames:v", "1", out],
                       capture_output=True, text=True, timeout=900)
    print("OK " if r.returncode == 0 else "FAIL", os.path.basename(out),
          os.path.getsize(out) if os.path.isfile(out) else 0)
