# -*- coding: utf-8 -*-
"""单期版式预览器：把某一期的字板叠在真实素材帧上，出「洁净版式图 + 实机预览图」。

字板一律由渲染器本体 build_923 生成，保证与成片同源。
背景优先取该期自己的素材 raw923/<t>_1.mp4；缺素材时回退 t16_1.mp4（仅占位）。

用法: python _preview_ep.py t23 [背景时刻秒, 默认 0.5]
"""
from __future__ import annotations
import os
import sys
import io
import subprocess

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageDraw, ImageFont
import build_923 as B
from _paths import WORK_DIR

W, H = B.W, B.H
WORK = str(WORK_DIR)
CHK = os.path.join(WORK, "_chk929")
S, OX, OY = 1.364, -96.5, 5.0
# 实机截图：用于把成片贴进抖音界面、目视确认安全区。这是**外部测试输入**，不是生产依赖
# 用 TEMPLATE_VIDEO_SHOT 指定；缺失时只出版式图、跳过实机预览。
SHOT = os.environ.get("TEMPLATE_VIDEO_SHOT", "").strip()


def grab(src: str, t: float, dst: str) -> str:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", src,
                    "-frames:v", "1", "-vf",
                    "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                    dst], check=True)
    return dst


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "t23"
    t = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    spec = B.SPECS[key]

    src = os.path.join(B.RAW, "%s_1.mp4" % key)
    placeholder = False
    if not os.path.isfile(src):
        src, placeholder = os.path.join(B.RAW, "t16_1.mp4"), True
    print("[bg] %s @%.1fs%s" % (os.path.basename(src), t, "  （占位素材）" if placeholder else ""))

    os.makedirs(CHK, exist_ok=True)
    bg = grab(src, t, os.path.join(CHK, "_pv_%s_bg.png" % key))
    top_png = os.path.join(CHK, "_pv_%s_top.png" % key)
    det_pngs = []
    B.make_top(top_png, spec["top"], spec["bar"])
    for i, lines in enumerate(spec["details"], 1):
        p = os.path.join(CHK, "_pv_%s_det%d.png" % (key, i))
        B.make_detail(p, lines)
        det_pngs.append(p)

    frame = Image.open(bg).convert("RGBA")
    frame.alpha_composite(Image.open(top_png).convert("RGBA"))
    frame.alpha_composite(Image.open(det_pngs[0]).convert("RGBA"))
    clean = frame.convert("RGB")
    p_clean = os.path.join(CHK, "%s_版式图.png" % key)
    clean.save(p_clean)
    print("SAVED", p_clean)

    if SHOT and os.path.isfile(SHOT):
        shot = Image.open(SHOT).convert("RGB")
        SW, SH = shot.size
        ph = Image.new("RGB", (SW, SH), (0, 0, 0))
        scaled = clean.resize((int(W * S), int(H * S)), Image.LANCZOS)
        cx0 = (scaled.width - SW) // 2
        ph.paste(scaled.crop((cx0, 0, cx0 + SW, scaled.height)), (0, int(OY)))
        ph.paste(shot.crop((0, 0, SW, 118)), (0, 0))
        ph.paste(shot.crop((36, 140, 140, 250)), (36, 140))
        ph.paste(shot.crop((1100, 140, 1240, 250)), (1100, 140))
        d = ImageDraw.Draw(ph, "RGBA")
        d.rectangle((0, 0, SW, int(OY + S * B.TOP_SAFE)), fill=(255, 60, 60, 46))
        d.line((0, int(OY + S * B.TOP_SAFE), SW, int(OY + S * B.TOP_SAFE)),
               fill=(60, 255, 120, 255), width=3)
        fl = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 30)
        d.text((20, int(OY + S * B.TOP_SAFE) + 8),
               "绿线 = 新版式首行起排线（抖音功能区已在线上方）",
               font=fl, fill=(120, 255, 160))
        p_prev = os.path.join(CHK, "%s_实机预览.png" % key)
        ph.save(p_prev)
        print("SAVED", p_prev)
    else:
        print("[实机预览] 未设置有效的 TEMPLATE_VIDEO_SHOT，已跳过；版式图已保存。")

    print("\n文案：")
    for tx, _f, _s, _w in spec["top"]:
        print("  ", tx)
    print("  [%s]" % spec["bar"])
    for line in spec["details"][0]:
        print("  ", line[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
