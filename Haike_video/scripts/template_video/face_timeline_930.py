# -*- coding: utf-8 -*-
"""人脸时间线扫描（只跑 YuNet，不跑 OCR）。

为什么要它：0930 批次原先只按「脸宽 >= 带宽 22%」判大脸，但 2026-09-30 老大
返工 t25 时指出「开头就是一个大脸，素材肯定是不通过的」——实测那个脸
脸宽 220px、阈值线 237.6px，**差 17px 没触发**，于是三条镜头其实都有脸、
QC 也没拦。结论：22% 这条线对「画面里不该出现人脸主导」太松。

本脚本把每条素材的**逐帧最大脸宽**全部落盘成 JSON，之后可以在**任意阈值**
下离线重算窗口，不必反复重扫（扫一遍 ~3 分钟，OCR 版要 16 分钟）。

用法: python face_timeline_930.py <out.json> <folderA> [folderB ...]
"""
from __future__ import annotations

import glob
import io
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import COPY_SKILL_OUT as DELIV, FFMPEG, FFPROBE, FACE_MODEL  # noqa: E402

W, H = 1080, 1920
VIS_TOP, VIS_BOT = 650, 1280
BAND_H = VIS_BOT - VIS_TOP
FPS = 2.0
FACE_SCORE = 0.6
SCALE = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
         f"crop={W}:{BAND_H}:0:{VIS_TOP}")


def dur_of(p: str) -> float:
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                            "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", p],
                           capture_output=True, text=True, timeout=60)
        return float((r.stdout or "").strip())
    except Exception:
        return 0.0


def scan(job: dict) -> dict:
    import cv2
    det = cv2.FaceDetectorYN_create(str(FACE_MODEL), "", (W, BAND_H),
                                   score_threshold=FACE_SCORE)
    out = {"key": job["key"], "dur": job["dur"], "t": [], "fw": [], "nface": [],
           "wmax_sec": None}
    with tempfile.TemporaryDirectory(prefix="ftl930_") as td:
        pat = os.path.join(td, "f_%05d.jpg")
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", job["abs"],
                        "-vf", f"fps={FPS},{SCALE}", "-q:v", "3",
                        "-start_number", "0", pat],
                       capture_output=True, text=True, timeout=3600)
        files = sorted(glob.glob(os.path.join(td, "f_*.jpg")))
        for i, fp in enumerate(files):
            img = cv2.imread(fp)
            if img is None:
                continue
            det.setInputSize((img.shape[1], img.shape[0]))
            _, res = det.detect(img)
            fw, cnt = 0.0, 0
            if res is not None:
                for f in res:
                    if f is None or f[14] < FACE_SCORE:
                        continue
                    cnt += 1
                    fw = max(fw, float(f[2]))
            out["t"].append(round(i / FPS, 2))
            out["fw"].append(round(fw, 1))
            out["nface"].append(cnt)
    if out["fw"]:
        j = max(range(len(out["fw"])), key=lambda k: out["fw"][k])
        out["wmax_sec"] = out["t"][j]
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    out_path, folders = sys.argv[1], sys.argv[2:]
    jobs_list = []
    for folder in folders:
        idx = os.path.join(DELIV, folder, "00-素材目录.json")
        if not os.path.isfile(idx):
            print(f"MISS {folder}")
            continue
        for e in json.load(open(idx, encoding="utf-8")).get("entries", []):
            rel = e.get("file_path", "")
            p = os.path.join(DELIV, folder, rel.replace("/", os.sep))
            if not os.path.isfile(p):
                continue
            jobs_list.append({"key": f"{folder}/{rel}", "abs": p,
                              "dur": dur_of(p)})
    print(f"scan {len(jobs_list)} videos ...", flush=True)
    res = {}
    with ProcessPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(scan, j) for j in jobs_list]
        for fu in as_completed(futs):
            r = fu.result()
            res[r["key"]] = r
            n = len(r["fw"])
            big = sum(1 for x in r["fw"] if x >= W * 0.22)
            any_f = sum(1 for x in r["fw"] if x > 0)
            print(f"  {os.path.basename(r['key'])[:44]:<44} dup={n:4d} "
                  f"任何脸={any_f:4d} 大脸22%={big:4d} maxW={max(r['fw'] or [0]):6.1f} "
                  f"@{r['wmax_sec']}", flush=True)
    json.dump(res, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"WROTE {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
