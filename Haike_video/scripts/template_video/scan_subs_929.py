# -*- coding: utf-8 -*-
"""扫描源视频中央可见区的烧录字幕时间线, 找干净的3秒窗口。
用法: python scan_subs_929.py <video> <start> <end> [step] [vis_top]
输出: 每行 "t<TAB>dirty/clean<TAB>前40字文本"
dirty = 中央区 OCR 到含 CJK 的文本(对白字幕/中文水印); 纯拉丁(品牌字/图表标签)不算。

vis_top 默认 650（版式 v2 顶板下沿）；v1 批次为 570。
"""
import os
import re
import subprocess
import sys
import tempfile

import onnxruntime  # noqa: F401  顺序敏感: 先于 rapidocr/cv2
from rapidocr import RapidOCR

import cv2

# 路径收口：ffmpeg 由 _paths 解析（见同目录 _paths.py）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import FFMPEG  # noqa: E402

W, H = 1080, 1920
VIS_TOP = int(sys.argv[5]) if len(sys.argv) > 5 else 650
VIS_BOT = 1280
CJK = re.compile(r"[\u4e00-\u9fff]")

ocr = RapidOCR()
video = sys.argv[1]
start = float(sys.argv[2])
end = float(sys.argv[3])
step = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0

with tempfile.TemporaryDirectory(prefix="scan929_") as td:
    out = os.path.join(td, "f.png")
    t = start
    while t < end:
        r = subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-ss", str(t), "-i", video,
             "-frames:v", "1", "-vf",
             f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
             out], capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or not os.path.isfile(out):
            print(f"{t:.1f}\tGRAB_FAIL")
            t += step
            continue
        img = cv2.imread(out)
        cen = img[VIS_TOP:VIS_BOT, :]
        res = ocr(cen)
        txts = []
        if res is not None and getattr(res, "txts", None):
            for txt, score in zip(res.txts, res.scores):
                if float(score) >= 0.6 and CJK.search(str(txt)):
                    txts.append(str(txt))
        dirty = bool(txts)
        joined = " | ".join(txts)[:60]
        print(f"{t:.1f}\t{'DIRTY' if dirty else 'clean'}\t{joined}", flush=True)
        t += step
