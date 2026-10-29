# -*- coding: utf-8 -*-
"""逐帧扫描素材池，找出每条视频里「中央带无脸且无中文」的**连续窗口**。

相比 7 帧采样，本脚本不漏掉局部干净段（例：某条只有尾巴 2s 有英文字幕）。
代价是要跑全帧 —— 故做两遍法：YuNet 先筛，只有「无脸帧」才跑 OCR（OCR 慢 10 倍）。

用法: python scan_windows_930.py <目录或若干mp4> [fps=2]
输出: 每条一行结论 + 干净窗口列表；同时把逐帧明细落 JSON（供后续离线复用）。
"""
from __future__ import annotations

import glob
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import FFMPEG, FFPROBE, FACE_MODEL  # noqa: E402

import onnxruntime  # noqa: F401,E402  (必须先于 rapidocr 载入)
import cv2  # noqa: E402
from rapidocr import RapidOCR  # noqa: E402

W, H = 1080, 1920
VIS_TOP, VIS_BOT = 650, 1280
BAND_H = VIS_BOT - VIS_TOP
CJK = re.compile(r"[\u4e00-\u9fff]")
SCALE = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
         f"crop={W}:{BAND_H}:0:{VIS_TOP}")

FACE_HIT = 60.0   # >= 这宽度算「画面里真有脸」
OCR_SCORE = 0.6
MIN_WIN = 3.0     # 干净窗口短于 3s 不予采纳
DETAIL_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_scan_windows_930.json")


def duration(src: str) -> float:
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", src], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def merge_windows(states: list[tuple[float, bool]], fps: float) -> list[tuple[float, float, float]]:
    """states = [(t, ok)]；把连续 ok 帧合并成窗口，返回 [(t0, t1, dur)]。"""
    wins, cur = [], None
    step = 1.0 / fps
    for t, ok in states:
        if ok:
            cur = [t, t] if cur is None else [cur[0], t]
        elif cur is not None:
            d = (cur[1] - cur[0]) + step
            if d >= MIN_WIN:
                wins.append((cur[0], cur[1] + step, d))
            cur = None
    if cur is not None:
        d = (cur[1] - cur[0]) + step
        if d >= MIN_WIN:
            wins.append((cur[0], cur[1] + step, d))
    return wins


def main() -> int:
    args = sys.argv[1:]
    fps = 2.0
    if args and re.fullmatch(r"\d+(\.\d+)?", args[-1]):
        fps = float(args[-1])
        args = args[:-1]
    files: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            files.extend(sorted(p.glob("*.mp4")))
        elif p.is_file():
            files.append(p)
    if not files:
        print("没有找到 mp4")
        return 1
    files.sort(key=lambda f: -duration(str(f)))   # 长的先跑

    ocr = RapidOCR()
    det = cv2.FaceDetectorYN_create(str(FACE_MODEL), "", (W, BAND_H), score_threshold=0.6)
    detail: dict[str, dict] = {}

    print("=" * 100)
    for idx, f in enumerate(files, 1):
        dur = duration(str(f))
        if dur <= 0:
            print("[%2d/%d] %s  时长读取失败" % (idx, len(files), f.name[:60]))
            continue
        states: list[tuple[float, bool]] = []
        fws: list[float] = []
        txt_hits: list[list[str]] = []
        with tempfile.TemporaryDirectory(prefix="sw930_") as td:
            pat = os.path.join(td, "f_%05d.jpg")
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(f),
                            "-vf", f"fps={fps},{SCALE}", "-q:v", "3",
                            "-start_number", "0", pat],
                           capture_output=True, text=True, timeout=3600)
            frames = sorted(glob.glob(os.path.join(td, "f_*.jpg")))
            for i, fp in enumerate(frames):
                t = i / fps
                img = cv2.imread(fp)
                if img is None:
                    continue
                det.setInputSize((img.shape[1], img.shape[0]))
                _, fres = det.detect(img)
                fw = 0.0
                if fres is not None:
                    for face in fres:
                        if face is not None and face[14] >= 0.6:
                            fw = max(fw, float(face[2]))
                fws.append(fw)
                hits: list[str] = []
                if fw < FACE_HIT:               # 只对无脸帧跑 OCR（省时间）
                    try:
                        res = ocr(img)
                    except Exception:
                        res = None
                    if res is not None and getattr(res, "txts", None):
                        for txt, sc in zip(res.txts, res.scores):
                            if float(sc) >= OCR_SCORE and CJK.search(str(txt)):
                                hits.append(str(txt)[:16])
                txt_hits.append(hits)
                states.append((t, fw < FACE_HIT and not hits))
        wins = merge_windows(states, fps)
        total_clean = sum(w[2] for w in wins)
        n_face = sum(1 for x in fws if x >= FACE_HIT)
        n_txt = sum(1 for x in txt_hits if x)
        print("[%2d/%d] %-52s %6.1fs  脸帧%4d/%-4d  字帧%4d  干净窗口 %2d 个 / %5.1fs"
              % (idx, len(files), f.name[:52], dur, n_face, len(fws), n_txt, len(wins), total_clean))
        for t0, t1, d in wins:
            print("        窗口 %6.1f - %6.1f s  (%.1fs)" % (t0, t1, d))
        if not wins:
            print("        无 ≥%.0fs 的干净窗口" % MIN_WIN)
        detail[f.name] = {"duration": dur, "fps": fps, "n_face": n_face,
                          "n_txt": n_txt, "windows": wins}

    print("=" * 100)
    json.dump(detail, open(DETAIL_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tot = sum(sum(w[2] for w in d["windows"]) for d in detail.values())
    usable = [k for k, d in detail.items() if d["windows"]]
    print("汇总: %d/%d 条含干净窗口；可用总时长 %.1fs" % (len(usable), len(detail), tot))
    for k in usable:
        ws = detail[k]["windows"]
        print("   %-52s %s" % (k[:52], " | ".join("%.0f-%.0fs(%.1fs)" % w for w in ws)))
    print("明细 -> %s" % DETAIL_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
