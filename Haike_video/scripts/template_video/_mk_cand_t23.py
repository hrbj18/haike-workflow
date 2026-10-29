# -*- coding: utf-8 -*-
"""从采集交付的 00-素材目录.json 生成 _make_spec.py 可用的 candidates json。

用法: python _mk_cand_t23.py <t_key> <素材目录文件夹名>
"""
from __future__ import annotations

import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 路径收口：不硬编码盘符/工作区绝对路径，统一由 _paths 推导（见同目录 _paths.py）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import WORK_DIR, COPY_SKILL_OUT as DELIV  # noqa: E402

WORK = str(WORK_DIR)
SHEETS = os.path.join(WORK, "sheets929")

t_key, folder = sys.argv[1], sys.argv[2]
src = os.path.join(DELIV, folder, "00-素材目录.json")
j = json.load(open(src, encoding="utf-8"))

out = []
for e in j["entries"]:
    abs_path = os.path.join(DELIV, folder, e["file_path"].replace("/", os.sep))
    assert os.path.isfile(abs_path), abs_path
    out.append({
        "material_id": e["material_id"],
        "file_path": e["file_path"],
        "abs_path": abs_path.replace("\\", "/"),
        "role": e["role"],
        "recommended_usage": e.get("recommended_usage", ""),
        "video_id": e.get("video_id", ""),
        "source_url": e.get("source_url", ""),
        "title": e.get("title", ""),
        "author": e.get("author", ""),
        "duration_seconds": e.get("duration_seconds"),
        "face_class": e.get("face_class", ""),
        "suggested_use": e.get("suggested_use", ""),
        "relevance_score": e.get("relevance_score"),
        "sample_timestamps": [],
    })

dst = os.path.join(SHEETS, f"{t_key}_claude_candidates.json")
json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("WROTE", dst, "items:", len(out))
for i, o in enumerate(out, 1):
    print(f"  {i:2d} {o['material_id']:<10} {o['file_path'].split('/')[-1]}  {o['duration_seconds']:.0f}s")
