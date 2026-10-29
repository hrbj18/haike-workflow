# -*- coding: utf-8 -*-
"""候选窗口验证：抽 6 帧 → 跑 OCR（中央带中文=不合格）+ 落一张首帧图供人眼确认。

用法: python verify_windows_t25.py <face_tl.json> <out_dir> <max_fw>
输出: <out_dir>/首帧 jpg + 终端 OCR 结论
"""
import glob
import io
import json
import os
import subprocess
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import COPY_SKILL_OUT as DELIV, FFMPEG  # noqa: E402

import re  # noqa: E402
import onnxruntime  # noqa: F401,E402  ★ 必须早于 cv2/rapidocr
import cv2  # noqa: E402
from rapidocr import RapidOCR  # noqa: E402

W, H = 1080, 1920
VIS_TOP, VIS_BOT = 650, 1280
BAND_H = VIS_BOT - VIS_TOP
FPS = 2.0
CLIP = 3.0
CJK = re.compile(r"[\u4e00-\u9fff]")
OCR_SCORE = 0.6
SCALE = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
         f"crop={W}:{BAND_H}:0:{VIS_TOP}")

# 手工指定的优先候选（素材名关键字 → 窗口起点列表）
CANDIDATES = [
    ("昇腾950-辅助素材-05-补充画面", [3.5, 11.0, 14.5, 16.5, 25.0, 40.0]),
    ("昇腾950-主素材-02-要点画面", [31.0, 33.0, 40.0, 45.0]),
    ("昇腾950-辅助素材-02-要点画面", [3.0, 7.0, 11.0]),
    ("华为昇腾950智算集群-辅助素材-03-演示对比", [6.5, 8.5, 10.5]),
    ("昇腾950-辅助素材-04-结论画面", [0.0, 4.0]),
]


def main() -> int:
    tl_path, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    tl = json.load(open(tl_path, encoding="utf-8"))
    by_name = {os.path.basename(k): (k, v) for k, v in tl.items()}

    ocr = RapidOCR()
    for kw, starts in CANDIDATES:
        hit = next((v for k, v in by_name.items() if kw in k), None)
        if hit is None:
            print(f"MISS {kw}")
            continue
        key, rec = hit
        src = os.path.join(DELIV, key.split("/", 1)[0],
                           key.split("/", 1)[1].replace("/", os.sep))
        print(f"\n=== {kw}  (maxW={max(rec['fw'] or [0])})")
        for st in starts:
            with tempfile.TemporaryDirectory(prefix="vw930_") as td:
                pat = os.path.join(td, "f_%02d.jpg")
                subprocess.run([FFMPEG, "-y", "-loglevel", "error",
                                "-ss", str(st), "-i", src, "-t", "3",
                                "-vf", f"fps={FPS},{SCALE}", "-q:v", "3",
                                "-start_number", "0", pat],
                               capture_output=True, text=True, timeout=600)
                files = sorted(glob.glob(os.path.join(td, "f_*.jpg")))
                hits, fws = [], []
                for i, fp in enumerate(files):
                    img = cv2.imread(fp)
                    if img is None:
                        continue
                    try:
                        res = ocr(img)
                    except Exception:
                        res = None
                    if res is not None and getattr(res, "txts", None):
                        for txt, sc in zip(res.txts, res.scores):
                            if float(sc) >= OCR_SCORE and CJK.search(str(txt)):
                                hits.append(str(txt)[:16])
                    if i == 0 and files:
                        shutil_safe = os.path.join(
                            out_dir, f"{kw[:24]}_{int(st*10):04d}.jpg")
                        cv2.imwrite(shutil_safe, cv2.resize(img, (270, 158)))
                print(f"  @{st:6.1f}s  OCR中文={hits if hits else '无'}  "
                      f"首帧图已存")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
