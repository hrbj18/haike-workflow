# -*- coding: utf-8 -*-
"""批量扫描素材池：每条视频按比例抽 N 帧，只看「成片中央可见带」(1080x630 @ y650)。

输出每条一行：时长 / 最大脸宽 / 中文命中 / 平均亮度 / 结论。
★ 只做粗筛 —— YuNet 实测会漏检口播大脸，结论必须人眼抽帧复核（见项目记忆）。

用法: python scan_pool_930.py <目录或若干mp4>  [每条的抽样点数=7]
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import FFMPEG, FFPROBE, FACE_MODEL  # noqa: E402

import onnxruntime  # noqa: F401,E402  (必须先于 rapidocr 载入，否则 Windows 下 DLL 初始化偶发失败)
import cv2  # noqa: E402
from rapidocr import RapidOCR  # noqa: E402

W, H = 1080, 1920
VIS_TOP, VIS_BOT = 650, 1280
BAND_H = VIS_BOT - VIS_TOP
CJK = re.compile(r"[\u4e00-\u9fff]")
SCALE = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
         f"crop={W}:{BAND_H}:0:{VIS_TOP}")

FACE_HIT = 60.0  # >= 这宽度算「画面里真有脸」


def duration(src: str) -> float:
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", src], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def main() -> int:
    args = sys.argv[1:]
    n = 7
    if args and args[-1].isdigit():
        n = int(args[-1])
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

    ocr = RapidOCR()
    det = cv2.FaceDetectorYN_create(str(FACE_MODEL), "", (W, BAND_H), score_threshold=0.6)

    print("%-46s %6s %7s %6s %7s  %s" % ("文件", "时长", "最大脸宽", "中文", "亮度", "结论"))
    print("-" * 108)
    summary = []
    with tempfile.TemporaryDirectory(prefix="scan930_") as td:
        for f in files:
            dur = duration(str(f))
            if dur <= 0:
                print("%-46s  %s" % (f.name[:46], "时长读取失败"))
                continue
            times = [dur * (i + 1) / (n + 1) for i in range(n)]
            max_fw = 0.0
            cjk_hits: list[str] = []
            vs: list[float] = []
            for t in times:
                fp = os.path.join(td, "b.jpg")
                r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "%.3f" % t,
                                    "-i", str(f), "-frames:v", "1", "-vf", SCALE, "-q:v", "2", fp],
                                   capture_output=True, text=True, timeout=300)
                img = cv2.imread(fp)
                if img is None:
                    continue
                det.setInputSize((img.shape[1], img.shape[0]))
                _, fres = det.detect(img)
                if fres is not None:
                    for face in fres:
                        if face is not None and face[14] >= 0.6:
                            max_fw = max(max_fw, float(face[2]))
                vs.append(float(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 2].mean()))
                res = ocr(img)
                if res is not None and getattr(res, "txts", None):
                    for txt, sc in zip(res.txts, res.scores):
                        if float(sc) >= 0.6 and CJK.search(str(txt)):
                            cjk_hits.append("%.0fs:%s" % (t, str(txt)[:12]))
            verdict = []
            if max_fw >= FACE_HIT:
                verdict.append("有人脸")
            if cjk_hits:
                verdict.append("有中文")
            if not verdict:
                verdict.append("干净")
            print("%-46s %6.1f %7.1f %6d %7.1f  %s"
                  % (f.name[:46], dur, max_fw, len(cjk_hits),
                     sum(vs) / len(vs) if vs else -1, "+".join(verdict)))
            if cjk_hits:
                print("      中文样例: %s" % " ; ".join(cjk_hits[:3]))
            summary.append((f.name, dur, max_fw, len(cjk_hits)))

    clean = [s for s in summary if s[2] < FACE_HIT and s[3] == 0]
    print("-" * 108)
    print("干净素材 %d / %d 条：" % (len(clean), len(summary)))
    for name, dur, fw, _ in clean:
        print("   %-50s %5.1fs  fw=%.1f" % (name[:50], dur, fw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
