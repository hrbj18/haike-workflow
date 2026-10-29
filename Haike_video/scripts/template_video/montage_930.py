# -*- coding: utf-8 -*-
"""把指定时间点的画面拼成一张联系表，供人眼复核（补 YuNet 漏检的坑）。

用法:
  python montage_930.py <src.mp4> <out.jpg> <width> <cols> <mode> <t1,t2,...>
    mode: full = 整帧等比缩放; band = 先按成片版式裁出「中央可见带」(1080x630) 再缩放

输出: out.jpg（每格左上角烧一个时间戳，纯 ASCII，不受 cv2 中文乱码影响）
"""
import io
import os
import subprocess
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import FFMPEG  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

W, H = 1080, 1920
VIS_TOP, VIS_BOT = 650, 1280
BAND = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}," \
       f"crop={W}:{VIS_BOT - VIS_TOP}:0:{VIS_TOP}"


def grab(src, t, width, mode, td):
    vf = (f"{BAND},scale={width}:-2" if mode == "band" else f"scale={width}:-2")
    out = os.path.join(td, "g_%08.2f.jpg" % t)
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "%.3f" % t,
                        "-i", src, "-frames:v", "1", "-vf", vf, "-q:v", "2", out],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not os.path.isfile(out):
        return None
    return cv2.imread(out)


def main() -> int:
    src, out, width, cols, mode = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    times = [float(x) for x in sys.argv[6].replace(",", " ").split()]
    tiles = []
    with tempfile.TemporaryDirectory(prefix="mt930_") as td:
        for t in times:
            img = grab(src, t, width, mode, td)
            if img is None:
                print("MISS", t)
                continue
            cv2.rectangle(img, (0, 0), (168, 26), (0, 0, 0), -1)
            cv2.putText(img, "%.1fs" % t, (6, 19), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0, 0, 255), 2, cv2.LINE_AA)
            tiles.append(img)
    if not tiles:
        print("NO TILES")
        return 1
    h = max(t.shape[0] for t in tiles)
    rows = (len(tiles) + cols - 1) // cols
    canvas = np.full((rows * (h + 4), cols * (width + 4), 3), 24, np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        y0, x0 = r * (h + 4) + 2, c * (width + 4) + 2
        canvas[y0:y0 + t.shape[0], x0:x0 + t.shape[1]] = t
    ok, buf = cv2.imencode(".jpg", canvas)
    buf.tofile(out)
    if not ok or not os.path.isfile(out):
        print("WRITE FAIL", out)
        return 1
    print("WROTE", out, canvas.shape)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
