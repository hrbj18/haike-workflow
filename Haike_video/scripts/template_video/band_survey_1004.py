# -*- coding: utf-8 -*-
"""band_survey_1004.py — 成片视角中央带扫描联系表（QC 同口径）
用法: python band_survey_1004.py <out.jpg> <step_sec> <cols> <video> [video...]
对 1080x1920 竖屏源: 带内 = 归一化后 crop=1080:630:0:650
对任意源: 先 scale=1080:1920:force_original_aspect_ratio=increase, crop=1080:1920 中央,
          再取 y650-1280 带, 输出每格 384x224。
"""
import json, os, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import FFMPEG, FFPROBE

TW, TH = 384, 224
FONT = os.environ.get("TEMPLATE_VIDEO_FONT_SANS") or r"C:\Windows\Fonts\msyh.ttc"


def probe_size_dur(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-show_entries", "format=duration",
                        "-of", "json", path], capture_output=True, text=True, timeout=30)
    d = json.loads(r.stdout)
    return d["streams"][0]["width"], d["streams"][0]["height"], float(d["format"]["duration"])


def band_crop_expr(w, h):
    # 归一化 1080x1920 的变换系数
    s = max(1080 / w, 1920 / h)
    sw, sh = w * s, h * s
    x0 = (sw - 1080) / 2
    # 先中央裁 1080x1920，再取带 y650-1280
    cw = 1080 / s
    ch = 630 / s
    cx = x0 / s
    cy = 650 / s
    return f"crop={cw:.2f}:{ch:.2f}:{cx:.2f}:{cy:.2f}"


def sheet_one(out, step, cols, path):
    w, h, dur = probe_size_dur(path)
    expr = band_crop_expr(w, h)
    tmp = tempfile.mkdtemp(prefix="band1004_")
    try:
        r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", path,
                            "-vf", f"fps=1/{step},{expr},scale={TW}:{TH}",
                            "-q:v", "3", os.path.join(tmp, "f_%04d.jpg")],
                           capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            print("FFMPEG_FAIL", path, r.stderr[-300:]); return
        frames = sorted(f for f in os.listdir(tmp) if f.endswith(".jpg"))
        if not frames:
            print("NO_FRAMES", path); return
        font = ImageFont.truetype(FONT, 14)
        lab = 20
        cols = min(cols, len(frames))
        rows_n = (len(frames) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (TW + 4) + 4, rows_n * (TH + lab + 4) + 4), (18, 18, 22))
        d = ImageDraw.Draw(sheet)
        for i, fn in enumerate(frames):
            t = i * step
            img = Image.open(os.path.join(tmp, fn)); img.load()
            cx = (i % cols) * (TW + 4) + 4
            cy = (i // cols) * (TH + lab + 4) + 4
            d.text((cx, cy), f"{t:.1f}s", font=font, fill=(255, 210, 80))
            sheet.paste(img, (cx, cy + lab)); img.close()
        base = os.path.splitext(os.path.basename(path))[0]
        sheet.save(out.replace("<BASE>", base), quality=82)
        print("SHEET:", out.replace("<BASE>", base), f"dur={dur:.1f}s frames={len(frames)} src={w}x{h}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    out, step, cols = sys.argv[1], float(sys.argv[2]), int(sys.argv[3])
    for p in sys.argv[4:]:
        if os.path.isfile(p):
            sheet_one(out, step, cols, p)
        else:
            print("MISSING", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
