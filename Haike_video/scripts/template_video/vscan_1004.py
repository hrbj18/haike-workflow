# -*- coding: utf-8 -*-
"""vscan_1004.py — 源片中央带亮度扫描（QC 同口径 V=HSV V 通道均值）
用法: python vscan_1004.py <crop_json> <step> <video>
crop_json: {"x":..,"y":..,"w":..,"h":..} 归一化 source_crop
输出: 每步一行 t,V；并给出所有「连续3秒全V>=45」的窗口起点。
"""
import json, subprocess, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HAIKE_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, HAIKE_ROOT)
import cv2, numpy as np
from _paths import FFMPEG
from backlot.material_crop import crop_filter


def main():
    crop = json.load(open(sys.argv[1], encoding="utf-8"))
    step = float(sys.argv[2])
    video = sys.argv[3]
    filt = (crop_filter(crop)
            + ",scale=1080:630:force_original_aspect_ratio=decrease:force_divisible_by=2,"
              "pad=1080:630:(ow-iw)/2:(oh-ih)/2:black")
    out = os.path.join(os.environ.get("TEMPLATE_VIDEO_WORK", "."), "_vscan_tmp.mp4")
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", video,
                        "-vf", filt + ",fps=1/%s" % step, "-an", "-c:v", "libx264", "-crf", "28", out],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print("FFMPEG_FAIL", r.stderr[-300:]); return 1
    cap = cv2.VideoCapture(out)
    vals = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        v = float(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[:, :, 2].mean())
        vals.append((round(i * step, 2), round(v, 1)))
        i += 1
    cap.release()
    os.remove(out)
    for t, v in vals:
        print(f"{t:>7.2f}s V={v}")
    # 连续 3 秒窗口（步长内全 >=45）
    need = int(round(3.0 / step))
    starts = []
    for j in range(len(vals) - need + 1):
        seg = vals[j:j + need]
        if all(v >= 45.0 for _, v in seg):
            starts.append(seg[0][0])
    # 合并相邻
    merged = []
    for s in starts:
        if merged and s - merged[-1][1] <= step + 1e-6:
            merged[-1] = (merged[-1][0], s)
        else:
            merged.append((s, s))
    print("WINDOWS_3S_OK:", ["%.2f-%.2f" % (a, b + 3.0) for a, b in merged])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
