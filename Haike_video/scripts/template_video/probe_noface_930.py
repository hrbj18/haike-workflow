# -*- coding: utf-8 -*-
"""快速探针：只跑 YuNet 人脸，统计每条素材的「无脸窗口」有多少。

与 auto_pick_0930.py 同口径（2fps、中央带 y650-1280、YuNet score>=0.6、
脸宽 >= 带宽 22% 记为大脸），但**不跑 OCR**——OCR 才是瓶颈（1.5s/帧），
所以本探针比 auto_pick 快一两个数量级，用来快速判断"这个目录到底有没有
能用的无脸画面"。

用法: python probe_noface_930.py <folderA> <folderB> ...
输出: 每条素材一行 + 末尾 候选无脸窗口清单
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import COPY_SKILL_OUT as DELIV, FFMPEG, FFPROBE, FACE_MODEL  # noqa: E402
import onnxruntime    # noqa: F401,E402  ★ 顺序敏感：必须早于 cv2/rapidocr
import cv2            # noqa: E402

W, H = 1080, 1920
VIS_TOP, VIS_BOT = 650, 1280
BAND_H = VIS_BOT - VIS_TOP
FPS = 2.0
CLIP = 3.0
FACE_SCORE = 0.6
FACE_BIG_RATIO = 0.22

SCALE = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
         f"crop={W}:{BAND_H}:0:{VIS_TOP}")

DET = cv2.FaceDetectorYN_create(str(FACE_MODEL), "", (W, BAND_H),
                                score_threshold=FACE_SCORE)


def dur_of(p):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", p],
                       capture_output=True, text=True, timeout=60)
    try:
        return float((r.stdout or "").strip())
    except Exception:
        return 0.0


def scan(path):
    with tempfile.TemporaryDirectory(prefix="pn930_") as td:
        pat = os.path.join(td, "f_%05d.jpg")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", path, "-vf",
                        f"fps={FPS},{SCALE}", "-q:v", "3",
                        "-start_number", "0", pat],
                       capture_output=True, text=True, timeout=3600)
        import glob
        files = sorted(glob.glob(os.path.join(td, "f_*.jpg")))
        big, wmax = [], []
        for i, fp in enumerate(files):
            img = cv2.imread(fp)
            if img is None:
                continue
            DET.setInputSize((img.shape[1], img.shape[0]))
            _, res = DET.detect(img)
            fb, fw = False, 0.0
            if res is not None:
                for f in res:
                    if f is None or f[14] < FACE_SCORE:
                        continue
                    fw = max(fw, float(f[2]))
                    if f[2] >= img.shape[1] * FACE_BIG_RATIO:
                        fb = True
            big.append(fb)
            wmax.append(round(fw, 1))
        n = len(big)
        if not n:
            return None
        # 无脸 3s 窗口（起点对齐 0.5s 网格，6 帧全无脸）
        wins = []
        seen = set()
        for i in range(n):
            w = round(round((i / FPS) * 2) / 2, 2)
            if w in seen or w + CLIP > n / FPS:
                continue
            seen.add(w)
            idx = [int(round((w + k * 0.5) * FPS)) for k in range(6)]
            if max(idx) >= n:
                continue
            if all(not big[j] for j in idx):
                wins.append(w)
        kept = []
        for w in wins:
            if all(abs(w - k) >= 1.5 for k in kept):
                kept.append(w)
        return {"n": n, "free": sum(1 for x in big if not x),
                "big": sum(1 for x in big if x), "wins": kept,
                "wmax": round(max(wmax), 1) if wmax else 0.0}


def main():
    folders = sys.argv[1:]
    if not folders:
        print(__doc__)
        return 2
    total_wins = []
    for folder in folders:
        idx = os.path.join(DELIV, folder, "00-素材目录.json")
        if not os.path.isfile(idx):
            print(f"MISS {folder}")
            continue
        print("=" * 10, folder)
        for e in json.load(open(idx, encoding="utf-8")).get("entries", []):
            rel = e.get("file_path", "")
            p = os.path.join(DELIV, folder, rel.replace("/", os.sep))
            if not os.path.isfile(p):
                continue
            r = scan(p)
            if not r:
                print(f"  {os.path.basename(rel)[:40]:<40} EMPTY")
                continue
            print(f"  {os.path.basename(rel)[:40]:<40} dup={r['n']:4d} "
                  f"无脸={r['free']:4d} 大脸={r['big']:4d} maxFaceW={r['wmax']:5.1f} "
                  f"无脸窗口={len(r['wins']):3d} {r['wins'][:8]}")
            for w in r["wins"][:4]:
                total_wins.append((folder, rel, w, r["wmax"]))
    print("\n=== 可用无脸窗口合计", len(total_wins), "个 ===")
    for f, rel, w, fw in total_wins[:20]:
        print(f"  @{w:6.1f}s  {f[:14]}/{os.path.basename(rel)[:34]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
