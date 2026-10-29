# -*- coding: utf-8 -*-
"""对单条素材的**全部帧**跑 OCR，把"中央带是否检出中文"逐帧落盘。

为什么要全帧：窗口是任意起点，逐窗口验证会重复跑同一帧。全帧跑一遍（~7 分钟
/150s 素材）后可以离线任意组合窗口，不重复计算。

用法: python ocr_frames_930.py <video_path> <out.json>
"""
import glob
import io
import json
import os
import re
import subprocess
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import FFMPEG  # noqa: E402

import onnxruntime  # noqa: F401,E402
import cv2  # noqa: E402
from rapidocr import RapidOCR  # noqa: E402

W, H = 1080, 1920
VIS_TOP, VIS_BOT = 650, 1280
BAND_H = VIS_BOT - VIS_TOP
FPS = 2.0
CJK = re.compile(r"[\u4e00-\u9fff]")
OCR_SCORE = 0.6
SCALE = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
         f"crop={W}:{BAND_H}:0:{VIS_TOP}")


def main() -> int:
    video, out_path = sys.argv[1], sys.argv[2]
    ocr = RapidOCR()
    rec = {"video": video, "t": [], "hit": [], "txt": []}
    with tempfile.TemporaryDirectory(prefix="ocr930_") as td:
        pat = os.path.join(td, "f_%05d.jpg")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", video, "-vf",
                        f"fps={FPS},{SCALE}", "-q:v", "3",
                        "-start_number", "0", pat],
                       capture_output=True, text=True, timeout=3600)
        files = sorted(glob.glob(os.path.join(td, "f_*.jpg")))
        for i, fp in enumerate(files):
            img = cv2.imread(fp)
            hits = []
            if img is not None:
                try:
                    res = ocr(img)
                except Exception:
                    res = None
                if res is not None and getattr(res, "txts", None):
                    for txt, sc in zip(res.txts, res.scores):
                        if float(sc) >= OCR_SCORE and CJK.search(str(txt)):
                            hits.append(str(txt)[:14])
            rec["t"].append(round(i / FPS, 2))
            rec["hit"].append(len(hits))
            rec["txt"].append(hits[:3])
            if i % 25 == 0:
                print(f"  {i}/{len(files)} ...", flush=True)
    json.dump(rec, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    clean = sum(1 for x in rec["hit"] if x == 0)
    print(f"DONE {len(rec['hit'])} frames, clean={clean}, -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
