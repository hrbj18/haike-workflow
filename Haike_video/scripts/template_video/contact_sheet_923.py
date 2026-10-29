# -*- coding: utf-8 -*-
"""924 rework: list candidates & build contact sheets for visual review.

Usage:
  python contact_sheet_923.py <theme_dir> <out_prefix> [--limit N]

- Reads 00-素材目录.json entries, matches actual files in 02-主素材/03-辅助素材.
- For each candidate: probe duration, extract 4 frames at 15%/40%/65%/90% of
  duration (min 1.0s from start, avoid last 0.5s), tile into one row.
- Writes <out_prefix>_sheet.jpg (rows = candidates) and <out_prefix>_candidates.json
  (metadata + sampled timestamps for the selection step).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

# 路径收口：不硬编码盘符/工作区绝对路径，统一由 _paths 推导（见同目录 _paths.py）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import COPY_SKILL_OUT as COPY_OUT, WORK_DIR, FFMPEG, FFPROBE  # noqa: E402

WORK = str(WORK_DIR)
TH_W, TH_H = 200, 356  # tile size (9:16-ish)
SAMPLES = [0.15, 0.40, 0.65, 0.90]


def probe_dur(path: str) -> float | None:
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path], capture_output=True, text=True, timeout=30)
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return None


def main() -> int:
    theme_dir = sys.argv[1]
    out_prefix = sys.argv[2]
    limit = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[3] == "--limit" else 14

    manifest = json.load(open(os.path.join(theme_dir, "00-素材目录.json"), encoding="utf-8"))
    entries = manifest["entries"]

    candidates = []
    for e in entries:
        fp = os.path.join(theme_dir, e["file_path"])
        if not os.path.isfile(fp):
            continue
        dur = probe_dur(fp)
        if not dur or dur < 4.0:
            continue
        ts = [round(max(1.0, min(d * dur, dur - 0.6)), 2) for d in SAMPLES]
        candidates.append({
            "material_id": e["material_id"],
            "file_path": e["file_path"],
            "abs_path": fp,
            "role": e.get("role"),
            "recommended_usage": e.get("recommended_usage"),
            "video_id": e.get("video_id"),
            "source_url": e.get("source_url"),
            "title": e.get("title"),
            "author": e.get("author"),
            "duration_seconds": dur,
            "face_class": e.get("face_class"),
            "suggested_use": e.get("suggested_use"),
            "relevance_score": e.get("relevance_score"),
            "sample_timestamps": ts,
        })
        if len(candidates) >= limit:
            break

    if not candidates:
        print("NO_CANDIDATES")
        return 1

    os.makedirs(os.path.dirname(out_prefix), exist_ok=True)
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 16)

    row_h = TH_H + 26
    sheet = Image.new("RGB", (TH_W * len(SAMPLES) * len(candidates[0:0] or [0]) or 1, 1), (18, 18, 18))
    # build rows one by one
    rows = []
    for c in candidates:
        tiles = []
        for t in c["sample_timestamps"]:
            tmp = out_prefix + "_tmp.png"
            r = subprocess.run(
                [FFMPEG, "-y", "-loglevel", "error", "-ss", str(t), "-i", c["abs_path"],
                 "-frames:v", "1", "-vf", f"scale={TH_W}:{TH_H}:force_original_aspect_ratio=increase,crop={TH_W}:{TH_H}", tmp],
                capture_output=True, text=True, timeout=60)
            if r.returncode == 0 and os.path.isfile(tmp):
                img = Image.open(tmp)
                img.load()
                tiles.append(img.copy())
                img.close()
            else:
                tiles.append(Image.new("RGB", (TH_W, TH_H), (80, 0, 0)))
            if os.path.isfile(tmp):
                os.remove(tmp)
        row = Image.new("RGB", (TH_W * len(tiles) + (len(tiles) + 1) * 6, row_h), (24, 24, 28))
        x = 6
        d = ImageDraw.Draw(row)
        d.text((x, 3), f'{c["material_id"]} [{c["role"]}] face={c["face_class"]} dur={c["duration_seconds"]:.0f}s rel={c["relevance_score"]} | {(c["title"] or "")[:34]}', font=font, fill=(230, 230, 230))
        for img in tiles:
            row.paste(img, (x, 22))
            x += TH_W + 6
        rows.append(row)

    W = max(r.width for r in rows)
    sheet = Image.new("RGB", (W, sum(r.height for r in rows) + 8), (18, 18, 18))
    y = 4
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    out_jpg = out_prefix + "_sheet.jpg"
    sheet.save(out_jpg, quality=82)

    meta_path = out_prefix + "_candidates.json"
    json.dump(candidates, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("SHEET:", out_jpg)
    print("META :", meta_path)
    print("CANDS:", len(candidates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
