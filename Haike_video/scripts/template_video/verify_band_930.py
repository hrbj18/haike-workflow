# -*- coding: utf-8 -*-
"""对指定时间点抽「中央可见带」帧并直接跑 OCR + YuNet，打印真实判定（用于交叉核验）。

用法: python verify_band_930.py <src.mp4> <t1,t2,...>
"""
import io
import os
import subprocess
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import FFMPEG, FACE_MODEL  # noqa: E402

import re  # noqa: E402
import onnxruntime  # noqa: F401,E402
import cv2  # noqa: E402
from rapidocr import RapidOCR  # noqa: E402

W, H = 1080, 1920
VIS_TOP, VIS_BOT = 650, 1280
BAND_H = VIS_BOT - VIS_TOP
CJK = re.compile(r"[\u4e00-\u9fff]")
SCALE = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
         f"crop={W}:{BAND_H}:0:{VIS_TOP}")


def main() -> int:
    src = sys.argv[1]
    times = [float(x) for x in sys.argv[2].replace(",", " ").split()]
    ocr = RapidOCR()
    det = cv2.FaceDetectorYN_create(str(FACE_MODEL), "", (W, BAND_H), score_threshold=0.6)
    with tempfile.TemporaryDirectory(prefix="vband930_") as td:
        for t in times:
            fp = os.path.join(td, "b.jpg")
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "%.3f" % t,
                            "-i", src, "-frames:v", "1", "-vf", SCALE, "-q:v", "2", fp],
                           capture_output=True, text=True, timeout=300)
            img = cv2.imread(fp)
            if img is None:
                print(f"@{t:7.2f}s  FRAME MISS")
                continue
            res = ocr(img)
            hits = []
            if res is not None and getattr(res, "txts", None):
                for txt, sc in zip(res.txts, res.scores):
                    if float(sc) >= 0.6:
                        tag = "CJK" if CJK.search(str(txt)) else "lat"
                        hits.append(f"{tag}:{str(txt)[:18]}({float(sc):.2f})")
            det.setInputSize((img.shape[1], img.shape[0]))
            _, fres = det.detect(img)
            fw = 0.0
            if fres is not None:
                for f in fres:
                    if f is not None and f[14] >= 0.6:
                        fw = max(fw, float(f[2]))
            v = float(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 2].mean())
            print(f"@{t:7.2f}s  fw={fw:6.1f}  V={v:5.1f}  "
                  f"{' | '.join(hits) if hits else 'OCRCLEAN'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
