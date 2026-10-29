# -*- coding: utf-8 -*-
"""最终窗口挑选：无脸（fw < 阈值）+ 中央带无中文（OCR 全干净）。

输入 face_timeline 结果 + 若干 ocr_frames 结果，输出可用窗口清单，
并可一键写出 spec JSON。

用法:
  python finalize_windows_t25.py <face_tl.json> <max_fw> <ocr1.json> [ocr2.json ...]
  python finalize_windows_t25.py ... --spec <out_spec.json> --pick "素材关键字@起点,素材关键字@起点,..."
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

FPS = 2.0
CLIP = 3.0


def load_ocr(paths):
    out = {}
    for p in paths:
        r = json.load(open(p, encoding="utf-8"))
        out[os.path.basename(r["video"])] = r
    return out


def windows(rec, ocr_rec, max_fw):
    fw = rec["fw"]
    hit = ocr_rec["hit"] if ocr_rec and len(ocr_rec["hit"]) >= len(fw) else None
    n = len(fw)
    dur = rec["t"][-1] + 1 / FPS if rec["t"] else 0.0
    out, seen = [], set()
    for i in range(n):
        w = round(round(rec["t"][i] * 2) / 2, 2)
        if w in seen or w + CLIP > dur + 1e-6:
            continue
        seen.add(w)
        idx = [int(round((w + k * 0.5) * FPS)) for k in range(6)]
        if max(idx) >= n:
            continue
        fvals = [fw[j] for j in idx]
        if max(fvals) >= max_fw:
            continue
        if hit is not None and sum(hit[j] for j in idx) > 0:
            continue
        out.append({"start": w, "fw_max": round(max(fvals), 1),
                    "fw": fvals,
                    "ocr": None if hit is None else [hit[j] for j in idx]})
    out.sort(key=lambda x: x["start"])
    # 相邻去重：间隔 <8s 的只保留第一个（避免三刀画面雷同）
    kept = []
    for w in out:
        if all(abs(w["start"] - k["start"]) >= 8.0 for k in kept):
            kept.append(w)
    return out, kept


def main() -> int:
    args = sys.argv[1:]
    face_tl = args[0]
    max_fw = float(args[1])
    spec_out = None
    pick_spec = None
    if "--spec" in args:
        spec_out = args[args.index("--spec") + 1]
    if "--pick" in args:
        pick_spec = args[args.index("--pick") + 1]
    ocr_args = [a for a in args[2:] if a.endswith(".json")]
    ocrs = load_ocr(ocr_args)

    tl = json.load(open(face_tl, encoding="utf-8"))
    print(f"max_fw={max_fw}px  已加载 OCR: {list(ocrs)}\n")
    allw = {}
    for key, rec in tl.items():
        base = os.path.basename(key)
        ow = ocrs.get(base)
        allw[key] = windows(rec, ow, max_fw)
        o, kept = allw[key]
        tag = "" if ow else "   [无 OCR 数据]"
        print(f"{base[:42]:<42} 候选={len(o):3d} 稀疏后={len(kept):3d}{tag}")
        for w in kept[:12]:
            print(f"      @{w['start']:7.2f}s  fw={w['fw']}"
                  + (f"  ocr={w['ocr']}" if w["ocr"] else ""))

    if not pick_spec:
        return 0

    # 依据 --pick 写 spec："素材关键字@起点" 逗号分隔，顺序即镜头顺序
    picks = []
    for item in pick_spec.split(","):
        kw, st = item.rsplit("@", 1)
        start = float(st)
        hit = None
        for key, rec in tl.items():
            if kw in key:
                hit = (key, rec)
                break
        if not hit:
            print(f"PICK MISS {item}")
            return 1
        key, rec = hit
        j = rec["t"].index(min(rec["t"], key=lambda x: abs(x - start)))
        picks.append({"key": key, "start": rec["t"][j],
                      "fw": rec["fw"][j]})
    json.dump(picks, open("_picks_t25.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\nPICKS ->", json.dumps(picks, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
