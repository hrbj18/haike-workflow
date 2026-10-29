# -*- coding: utf-8 -*-
"""把页面截图里的矩形裁出来并放大，用于肉眼复核「列表缩略图到底显示的是什么」。

背景: `backfill_cover.py probe` 会把现场落成一张视口截图，
而列表缩略图在这些平台上是 **background-image**(不是 <img>)，没法用 locator.screenshot，
所以只能用「JS 量 rect → 从视口截图裁」这条路。

★ 坑: 截图分辨率 ≠ CSS 视口像素。抖音账号指纹的 device_scale_factor=1.25，
  视口 1280x800 落盘成 1600x1000 —— 直接按 CSS rect 裁会整体偏左上。
  用 `--viewport 1280x800` 让脚本自动推断 dpr(=png宽/视口宽)，或直接 `--dpr 1.25`。

用法:
  python scripts/crop_thumb.py --png data/debug/cover_dy-verify_xxx.png \
      --viewport 1280x800 --rect 240,209,120,160 \
      --out data/debug/crops/dy_v2.png --scale 4

  # 一次裁多块(rect 之间用 ;; 分隔)；--out 给目录
  python scripts/crop_thumb.py --png a.png --viewport 1600x900 \
      --rect "1,2,3,4;;5,6,7,8" --out crops/ --scale 3
"""
from __future__ import annotations

import argparse
import os

from PIL import Image


def main() -> int:
    ap = argparse.ArgumentParser(description="从截图裁矩形并放大")
    ap.add_argument("--png", required=True)
    ap.add_argument("--rect", required=True, help="CSS 像素 x,y,w,h；多块用 ;; 分隔")
    ap.add_argument("--out", required=True, help="输出 png；多块时当作目录")
    ap.add_argument("--scale", type=float, default=4.0)
    ap.add_argument("--pad", type=int, default=6, help="向外多裁几像素，避免切边(CSS 像素)")
    ap.add_argument("--dpr", type=float, default=0.0, help="设备像素比；0=从 --viewport 推断")
    ap.add_argument("--viewport", default="", help="CSS 视口 WxH，用于自动推断 dpr")
    args = ap.parse_args()

    im = Image.open(args.png)
    dpr = args.dpr
    if not dpr:
        if args.viewport and "x" in args.viewport.lower():
            vw = float(args.viewport.lower().split("x")[0])
            dpr = im.width / vw if vw else 1.0
        else:
            dpr = 1.0
    print(f"[crop] 源图 {im.width}x{im.height}，dpr={dpr:.3f}"
          f"（CSS 矩形将被乘以此系数）")

    rects = [r.strip() for r in args.rect.split(";;") if r.strip()]
    multi = len(rects) > 1
    if multi:
        os.makedirs(args.out, exist_ok=True)

    for i, one in enumerate(rects):
        cx, cy, cw, ch = (float(v) for v in one.split(","))
        p = args.pad
        box = (max(0, int((cx - p) * dpr)), max(0, int((cy - p) * dpr)),
               min(im.width, int((cx + cw + p) * dpr)),
               min(im.height, int((cy + ch + p) * dpr)))
        crop = im.crop(box)
        if args.scale and args.scale != 1:
            crop = crop.resize((int(crop.width * args.scale),
                                int(crop.height * args.scale)), Image.LANCZOS)
        out = os.path.join(args.out, f"crop_{i}.png") if multi else args.out
        crop.save(out)
        print(f"[crop] {one} -> {out}  ({crop.width}x{crop.height}, 截图区 {box})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
