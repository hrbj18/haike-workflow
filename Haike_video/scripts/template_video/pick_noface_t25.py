# -*- coding: utf-8 -*-
"""基于 face_timeline 结果的离线选窗口（不重扫、不跑 OCR）。

判据从宽到严：
  max_fw = 大脸阈值（默认 60px，即 1080 宽的 5.5%）——窗口内 6 帧的脸宽都必须 <
  这个值。60px 在成片里几乎看不出是人脸；用 0 就是"绝对无人脸"。

用法: python pick_noface_t25.py face_tl.json [max_fw] [--top N]
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

FPS = 2.0
CLIP = 3.0


def windows_for(rec: dict, max_fw: float) -> list[dict]:
    t, fw = rec["t"], rec["fw"]
    n = len(fw)
    dur = t[-1] + 1 / FPS if t else 0.0
    out, seen = [], set()
    for i in range(n):
        w = round(round(t[i] * 2) / 2, 2)
        if w in seen or w + CLIP > dur + 1e-6:
            continue
        seen.add(w)
        idx = [int(round((w + k * 0.5) * FPS)) for k in range(6)]
        if max(idx) >= n:
            continue
        vals = [fw[j] for j in idx]
        if max(vals) < max_fw:
            out.append({"start": w, "fw_max": round(max(vals), 1),
                        "fw": vals})
    # 相邻窗口去重：间隔 < 2s 的只留 fw_max 最小的
    out.sort(key=lambda x: (x["fw_max"], x["start"]))
    kept = []
    for w in out:
        if all(abs(w["start"] - k["start"]) >= 2.0 for k in kept):
            kept.append(w)
    kept.sort(key=lambda x: x["start"])
    return kept


def main() -> int:
    path = sys.argv[1]
    max_fw = float(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 60.0
    top = 8
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])

    data = json.load(open(path, encoding="utf-8"))
    rows = []
    for key, rec in data.items():
        ws = windows_for(rec, max_fw)
        rows.append((key, rec, ws))
    rows.sort(key=lambda r: (-len(r[2]), r[0]))

    print(f"max_fw(脸宽上限) = {max_fw}px   素材数={len(rows)}\n")
    for key, rec, ws in rows:
        n = len(rec["fw"])
        nz = sum(1 for x in rec["fw"] if x > 0)
        print(f"{os.path.basename(key)[:40]:<40} 帧={n:4d} 有脸帧={nz:4d} "
              f"无脸窗口={len(ws):4d}  maxW={max(rec['fw'] or [0]):6.1f}")
        for w in ws[:top]:
            print(f"      @{w['start']:7.2f}s  fw={w['fw']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
