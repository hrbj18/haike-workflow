# -*- coding: utf-8 -*-
"""AI 生图 → 3:4 竖封面（复用 build_923.SPECS 的文案与配色）+ 契约可校验的 proof JSON。

口径（技能 creatorhub-publish §0.17）:
  用户 2026-09-18 原话「我要的封面是 ai 生成的全新图片」——**长期口径、跨批次有效**。
  本脚本只做「AI 原图 → 中心裁 1080x1440 → 顶部渐变压暗 → 叠标题」，
  **绝不用视频抽帧当封面**（抽帧联系表只作次要参考）。

用法:
  # 1) 先出 AI 原图（零积分中转站，单张 40-62s，建议后台跑）
  #    提示词必须显式写 no text, no letters, no words, no logo, no watermark
  #    ★ --out 必须传 Windows 绝对路径（MSYS 的 /d/... 会被脚本按字面落成 C:/d/...）
  python C:/Users/Administrator/.workbuddy/tools/relay-imagegen.py generate "<英文竖构图提示词>" \
      --out "D:\\...\\_covers929\\_ai\\t23-raw.png"

  # 2) 合成封面 + proof
  python make_cover.py t23 --src "...\\_ai\\t23-raw.png" [--out <cover.jpg>] [--check-dir <dir>]

  # 只看文案/配色（dry-run，不写任何文件）
  python make_cover.py t23 --ls

默认路径约定: --src 为 `<covers>/_ai/<ep>-raw.png` 时，
  封面落 `<covers>/<ep>-cover.jpg`，证据落 `<covers>/<ep>-cover-proof.json`。

proof JSON 字段对齐 creatorhub 的 publish_contract.validate_cover_proof:
  kind=ai_generated / model / source_image_path / source_image_sha256 / final_cover_sha256
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
F_REG = r"C:\Windows\Fonts\msyh.ttc"
F_BOLD = (r"C:\Windows\Fonts\msyhbd.ttf"
          if os.path.isfile(r"C:\Windows\Fonts\msyhbd.ttf") else F_REG)

W, H = 1080, 1440          # 主版 3:4（抖音/快手/视频号列表槽位）
MAX_W = 900               # 文字最大绘制宽度（含描边）——视频号列表会做 0.92 中心裁切
                          # （0.92*1080=993），留 ≥45px 单侧余量才不会把主标切边
START_Y = 120              # 首行基线起点
LINE_SIZES = (62, 116, 62, 54)   # 钩子 / 主标 / 副标 / 要点
GAP = 38                   # 行距追加量（实际 advance = 字号 + GAP）
SCRIM_STRENGTH = 0.74      # 顶部压暗强度
SCRIM_END_RATIO = 0.50     # 压暗到 0.50*H 处衰减为 0
SCRIM_PLATEAU = 0.52       # 前 52% 保持满强度（避免末行压在亮部上糊掉）
BAR_FILL = (255, 205, 60)
BAR_STROKE = (20, 20, 20)
CST = timezone(timedelta(hours=8))


def sha256_file(p: str | Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest().upper()


def load_specs() -> dict:
    sys.path.insert(0, str(HERE))
    import build_923  # noqa: PLC0415  同目录的生产脚本，带 __main__ 守卫，可安全 import
    return build_923.SPECS


def ep_lines(sp: dict) -> list[dict]:
    """SPECS 的 top(3 行) + bar(要点行) → 统一的行描述。"""
    out: list[dict] = []
    for item in sp["top"]:
        text, fill, stroke, sw = item[0], tuple(item[1]), tuple(item[2]), item[3]
        out.append({"text": text, "fill": fill[:3], "stroke": stroke[:3], "sw": sw})
    out.append({"text": sp["bar"], "fill": BAR_FILL, "stroke": BAR_STROKE, "sw": 4})
    return out


def fit(draw: ImageDraw.ImageDraw, text: str, max_w: int, base: int,
        font_path: str, stroke_w: int = 0) -> ImageFont.FreeTypeFont:
    """自适应降字号；**必须把描边算进去**，否则视觉宽度会超出 max_w。"""
    size = base
    while size > 32:
        f = ImageFont.truetype(font_path, size)
        box = draw.textbbox((0, 0), text, font=f, stroke_width=stroke_w)
        if box[2] - box[0] <= max_w:
            return f
        size -= 4
    return ImageFont.truetype(font_path, size)


def top_scrim(im: Image.Image, strength: float = SCRIM_STRENGTH,
              end_ratio: float = SCRIM_END_RATIO,
              plateau: float = SCRIM_PLATEAU) -> Image.Image:
    """顶部压暗：先满强度覆盖文字块，再平滑衰减到 0。

    AI 图不一定自带暗场带，白/琥珀字直接压上去会糊（本批 t23 末行正落在引擎亮斑上）。
    平台期保证「文字块范围内」压得够狠，衰减段避免出现生硬的横向分界线。
    """
    w, h = im.size
    end = max(1, int(h * end_ratio))
    flat_until = int(end * plateau)
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in range(end):
        if y <= flat_until:
            a = strength
        else:
            t = (y - flat_until) / max(1, end - flat_until)
            a = strength * (1.0 - t) ** 1.25
        d.line((0, y, w, y), fill=(0, 0, 0, max(0, min(255, int(255 * a)))))
    return Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")


def compose(src: str | Path, lines: list[dict]) -> Image.Image:
    im = Image.open(src).convert("RGB")
    iw, ih = im.size
    scale = max(W / iw, H / ih)
    nw, nh = int(iw * scale + 0.5), int(ih * scale + 0.5)
    im = im.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - W) // 2, (nh - H) // 2
    im = im.crop((left, top, left + W, top + H))       # 中心裁 3:4，零拉伸
    im = top_scrim(im)
    d = ImageDraw.Draw(im)
    y = START_Y
    for ln, base in zip(lines, LINE_SIZES):
        f = fit(d, ln["text"], MAX_W, base, F_BOLD, ln["sw"])
        x0, _, x1, _ = d.textbbox((0, 0), ln["text"], font=f, stroke_width=ln["sw"])
        x = (W - (x1 - x0)) // 2 - x0          # 含描边的真实外框居中
        d.text((x, y), ln["text"], font=f, fill=ln["fill"],
               stroke_fill=ln["stroke"], stroke_width=ln["sw"])
        y += f.size + GAP
    return im


def write_checks(cover: str | Path, out_dir: Path, ep: str) -> list[str]:
    """自检图：9:16 兼容版（模糊补边）+ 视频号 0.92 裁切预览（验文字不被切）。"""
    from PIL import ImageFilter

    out_dir.mkdir(parents=True, exist_ok=True)
    im = Image.open(cover).convert("RGB")
    made: list[str] = []

    nine_h = int(W * 16 / 9)                       # 1080x1920
    bg = im.resize(mode_size(im.size, (W, nine_h)), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(24))
    canvas = Image.new("RGB", (W, nine_h), (0, 0, 0))
    canvas.paste(bg, (0, (nine_h - bg.height) // 2))
    canvas.paste(im, (0, (nine_h - H) // 2))
    p1 = out_dir / f"{ep}-cover-1080x1920.jpg"
    canvas.save(p1, "JPEG", quality=88)
    made.append(str(p1))

    cw = int(W * 0.92)                             # 视频号列表会做约 0.92 中心裁切
    left = (W - cw) // 2
    p2 = out_dir / f"{ep}-cover-crop0.92.jpg"
    im.crop((left, 0, left + cw, H)).save(p2, "JPEG", quality=88)
    made.append(str(p2))
    return made


def mode_size(src: tuple[int, int], target: tuple[int, int]) -> tuple[int, int]:
    """等比放大到刚好覆盖 target（cover 语义）。"""
    tw, th = target
    sw, sh = src
    s = max(tw / sw, th / sh)
    return max(tw, int(sw * s + 0.5)), max(th, int(sh * s + 0.5))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ep", help="期号 key，如 t23")
    ap.add_argument("--src", help="AI 原图路径")
    ap.add_argument("--out", help="封面输出路径（默认 src 同级的 <ep>-cover.jpg）")
    ap.add_argument("--check-dir", help="自检图输出目录（可选）")
    ap.add_argument("--model", default="gpt-image-2", help="出图模型名，写入 proof")
    ap.add_argument("--prompt", default="", help="生图提示词（写入 proof 备查）")
    ap.add_argument("--ls", action="store_true", help="只打印文案与配色，不写文件")
    args = ap.parse_args()

    specs = load_specs()
    if args.ep not in specs:
        print(f"[ERR] SPECS 里没有 {args.ep}；现有: {', '.join(sorted(specs))}")
        return 2
    sp = specs[args.ep]
    lines = ep_lines(sp)

    print(f"=== {args.ep} 封面文案（源: build_923.SPECS）===")
    for i, ln in enumerate(lines):
        print("  行%d  %-24s fill=%s stroke=%s sw=%s"
              % (i + 1, ln["text"], ln["fill"], ln["stroke"], ln["sw"]))
    if args.ls:
        return 0

    if not args.src:
        print("[ERR] 需要 --src（或加 --ls 只看文案）")
        return 2
    src = Path(args.src)
    if not src.is_file():
        print(f"[ERR] AI 原图不存在: {src}")
        return 2

    out = Path(args.out) if args.out else src.parent.parent / f"{args.ep}-cover.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)

    im = compose(src, lines)
    if abs(im.width / im.height - 0.75) > 0.01:
        print("[ERR] 成品不是 3:4")
        return 3
    im.save(out, "JPEG", quality=92)

    proof_path = out.parent / f"{args.ep}-cover-proof.json"
    proof = {
        "kind": "ai_generated",
        "model": args.model,
        "source_image_path": str(src.resolve()),
        "source_image_sha256": sha256_file(src),
        "final_cover_sha256": sha256_file(out),
        "source_image_size": list(Image.open(src).size),
        "final_cover_size": [im.width, im.height],
        "prompt": args.prompt,
        "generated_at": datetime.now(CST).isoformat(timespec="seconds"),
        "note": "AI 生图原图经中心裁切 1080x1440(3:4) + 顶部压暗 + 标题合成，作为视频封面。",
    }
    proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2),
                          encoding="utf-8")

    assert proof["final_cover_sha256"] == sha256_file(out), "封面 sha 不一致"
    assert proof["source_image_sha256"] == sha256_file(src), "原图 sha 不一致"
    print(f"COVER_OK  {out}")
    print(f"PROOF_OK  {proof_path}")
    print(f"  size={im.width}x{im.height}  bytes={out.stat().st_size}")
    print(f"  src_sha={proof['source_image_sha256'][:16]}  cover_sha={proof['final_cover_sha256'][:16]}")

    if args.check_dir:
        for p in write_checks(out, Path(args.check_dir), args.ep):
            print(f"CHECK     {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
