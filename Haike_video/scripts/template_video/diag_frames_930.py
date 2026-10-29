# -*- coding: utf-8 -*-
"""诊断：某个素材逐秒帧的 dirty / luma / std / face 分布，定位 windows=0 的原因。

用法: python diag_frames_930.py <视频绝对路径> [秒数] [起始秒]
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

import onnxruntime  # noqa: F401  顺序敏感
from rapidocr import RapidOCR  # noqa: E402
import cv2  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import FFMPEG, FACE_MODEL  # noqa: E402

W, H = 1080, 1920
VIS_TOP, VIS_BOT = 650, 1280
CJK = re.compile(r"[\u4e00-\u9fff]")
SCALE = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"


def main() -> int:
    path = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    t0 = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    ocr = RapidOCR()
    det = cv2.FaceDetectorYN_create(str(FACE_MODEL), "",
                                    (W, VIS_BOT - VIS_TOP), score_threshold=0.6)
    print("t      dirty    luma     std   faceW  txts")
    with tempfile.TemporaryDirectory(prefix="diag930_") as td:
        for i in range(n):
            t = t0 + i
            out = os.path.join(td, "f.png")
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
                            "-i", path, "-frames:v", "1", "-vf", SCALE, out],
                           capture_output=True, timeout=120)
            img = cv2.imread(out)
            if img is None:
                print("%6.1f  (no frame)" % t)
                continue
            cen = img[VIS_TOP:VIS_BOT, :]
            g = cv2.cvtColor(cen, cv2.COLOR_BGR2GRAY)
            luma, std = float(g.mean()), float(g.std())
            txts = []
            res = ocr(cen)
            if res is not None and getattr(res, "txts", None):
                for txt, score in zip(res.txts, res.scores):
                    if float(score) >= 0.6 and CJK.search(str(txt)):
                        txts.append(str(txt))
            det.setInputSize((cen.shape[1], cen.shape[0]))
            _, fres = det.detect(cen)
            fw = 0.0
            if fres is not None:
                for f in fres:
                    if f is not None and f[14] >= 0.6:
                        fw = max(fw, float(f[2]))
            print("%6.1f %6s %7.1f %7.1f %7.1f  %s"
                  % (t, bool(txts), luma, std, fw, txts[:3]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
