# -*- coding: utf-8 -*-
"""从 candidates json 生成 spec_<t_key>.json.
用法: python _make_spec.py <t_key> <cand_json> idx1:in1 idx2:in2 idx3:in3
idx 为 1-based 候选序号; in 为 source_in 秒。
"""
import json
import os
import sys

# 路径收口：工作目录由 _paths 推导（见同目录 _paths.py）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import WORK_DIR  # noqa: E402

WORK = str(WORK_DIR)
SHEETS = os.path.join(WORK, "sheets929")

t_key = sys.argv[1]
cand_path = os.path.join(SHEETS, sys.argv[2])
picks = []
for a in sys.argv[3:]:
    i, s = a.split(":")
    picks.append((int(i), float(s)))

j = json.load(open(cand_path, encoding="utf-8"))
items = j if isinstance(j, list) else list(j.values())[0]

out = []
for n, (idx, src_in) in enumerate(picks, start=1):
    c = items[idx - 1]
    out.append(
        {
            "cue": "cue-%03d" % n,
            "t_key": t_key,
            "index": n,
            "file": (c.get("abs_path") or c.get("file_path")).replace("\\", "/"),
            "source_in": src_in,
            "source_video_id": str(c.get("video_id") or ""),
            "source_url": c.get("source_url") or "",
            "source_title": c.get("title") or "",
            "creator": c.get("author") or "",
            "material_role": c.get("role") or "support",
            "original_delivery_path": c.get("file_path") or "",
        }
    )

dst = os.path.join(WORK, "spec_%s.json" % t_key)
with open(dst, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("WROTE", dst)
for o in out:
    print(" ", o["cue"], os.path.basename(o["file"]), "@", o["source_in"], o["material_role"])
