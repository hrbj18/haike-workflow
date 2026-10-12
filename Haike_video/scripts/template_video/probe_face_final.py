# -*- coding: utf-8 -*-
"""对已成片 mp4 中央可见区做人脸门禁 + 亮度, 不依赖 onnxruntime/rapidocr。
用法: python probe_face_final.py <mp4> <step> [vis_top]
输出: t<TAB>faces<TAB>big<TAB>brightness
vis_top 默认 650（版式 v2 顶板下沿）；v1 批次为 570。
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import tempfile

import cv2

# 路径收口：模型/ffmpeg 统一由 _paths 推导（见同目录 _paths.py）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import FACE_MODEL as _FACE_MODEL, FFMPEG  # noqa: E402

W, H = 1080, 1920
VIS_TOP = int(sys.argv[3]) if len(sys.argv) > 3 else 650
VIS_BOT = 1280
FACE_MODEL = str(_FACE_MODEL)


def main() -> int:
    mp4 = sys.argv[1]
    step = float(sys.argv[2]) if len(sys.argv) > 2 else 0.25
    assert os.path.isfile(FACE_MODEL), "face model missing: " + FACE_MODEL
    det = cv2.FaceDetectorYN_create(FACE_MODEL, "", (W, VIS_BOT - VIS_TOP), score_threshold=0.6)
    with tempfile.TemporaryDirectory(prefix="pff_") as td:
        pat = os.path.join(td, "f_%05d.png")
        subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-i", mp4, "-vf",
             "fps=%f,scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d"
             % (1.0 / step, W, H, W, H), "-start_number", "0", pat],
            check=True, timeout=900)
        frames = sorted(glob.glob(os.path.join(td, "f_*.png")))
        worst = 0
        nbig = 0
        for i, fp in enumerate(frames):
            t = round(i * step, 2)
            img = cv2.imread(fp)
            if img is None:
                print("%.2f\tREAD_FAIL" % t)
                continue
            cen = img[VIS_TOP:VIS_BOT, :]
            det.setInputSize((cen.shape[1], cen.shape[0]))
            _, res = det.detect(cen)
            faces = [] if res is None else [f for f in res if f is not None and f[14] >= 0.6]
            big = [f for f in faces if f[2] >= cen.shape[1] * 0.22]
            hsv = cv2.cvtColor(cen, cv2.COLOR_BGR2HSV)
            v = float(hsv[:, :, 2].mean())
            nbig += len(big)
            if len(big) > worst:
                worst = len(big)
            print("%.2f\t%d\t%d\t%.0f" % (t, len(faces), len(big), v))
        print("----")
        print("FRAMES=%d  BIG_FACE_FRAMES=%d  MAX_BIG_IN_FRAME=%d" % (len(frames), nbig, worst))
    return 2 if nbig else 0


if __name__ == "__main__":
    raise SystemExit(main())
