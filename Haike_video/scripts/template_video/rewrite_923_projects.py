# -*- coding: utf-8 -*-
"""924 rework: write re-rendered t2-t8 results back into the project library.

Per theme (reads selection_<t>.json written by select_cut_923.py cut mode):
  1. copy final_923/<file>.mp4 -> projects/<pid>/renders/final.mp4
  2. write artifacts/douyin_broll_manifest.json (schema aligned with t1)
  3. write artifacts/asset_manifest.json
  4. rewrite artifacts/scene_plan.json scenes -> cue-001..003, visual_asset
     -> douyin assets, keep original scene titles/descriptions
  5. write artifacts/render_report.json
  6. re-extract snapshots/cue-00X.jpg from the new final.mp4 at 1.5/4.5/7.5s

Usage:
  python rewrite_923_projects.py t2 t3 t4 t5 t6 t7 t8 t9
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import time

# 路径收口：不硬编码盘符/工作区绝对路径，统一由 _paths 推导（见同目录 _paths.py）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import (  # noqa: E402
    VIDEOHUB_ROOT as ROOT,
    HAIKE_ROOT as HAIKE,
    WORK_DIR,
    PROJECTS_DIR,
    FFMPEG,
)

WORK = str(WORK_DIR)
FINAL = os.path.join(WORK, "final_923")
PROJECTS = str(PROJECTS_DIR)

THEMES = {
    "t2": {"project": "sub3-0923-qualcomm-2nm", "final": "02_高通2nm骁龙_9s.mp4", "label": "qcom2nm", "title": "高通2nm骁龙"},
    "t3": {"project": "sub3-0923-memory-price-hike", "final": "03_内存涨价_9s.mp4", "label": "memprice", "title": "内存涨疯了"},
    "t4": {"project": "sub3-0923-mac-launch", "final": "04_Mac发售_9s.mp4", "label": "mac", "title": "苹果Mac开卖"},
    "t5": {"project": "sub3-0923-grok47-launch", "final": "05_Grok47发布_9s.mp4", "label": "grok47", "title": "Grok4.7发布"},
    "t6": {"project": "sub3-0923-xiaomi-oss-no1", "final": "06_小米开源登顶_9s.mp4", "label": "mi-oss", "title": "小米大模型登顶"},
    "t7": {"project": "sub3-0923-robot-theme-park", "final": "07_机器人进乐园_9s.mp4", "label": "robotpark", "title": "机器人进乐园"},
    "t8": {"project": "sub3-0923-qiyuan-robot-19999", "final": "08_启元机器人19999_9s.mp4", "label": "qyrobot", "title": "19999元机器人"},
    "t9": {"project": "sub3-0924-nvidia-glass-substrate", "final": "01_英伟达玻璃基板_9s.mp4", "label": "nvidia-glass", "title": "英伟达玻璃基板", "source_batch": "924-topic", "final_dir": os.path.join(WORK, "final_924")},
}

SNAP_TS = [1.5, 4.5, 7.5]


def rewrite(t: str) -> None:
    info = THEMES[t]
    source_platform = str(info.get("source_platform") or "douyin")
    provenance_name = info.get("provenance_manifest_name") or (
        "douyin_broll_manifest.json" if source_platform == "douyin" else "source_broll_manifest.json"
    )
    qc = None
    if info.get("qc_file"):
        qc = json.load(open(info["qc_file"], encoding="utf-8"))
        if not isinstance(qc, list) or len(qc) != 1 or qc[0].get("pass") is not True or not qc[0].get("per_frame") or qc[0].get("risks"):
            raise ValueError("成片QC未通过，禁止完成入库")
        frames = qc[0]["per_frame"]
        times = [float(frame.get("frame", -1)) for frame in frames]
        if (qc[0].get("cue") != f"{t}_9s" or times[0] != 0 or times[-1] < 8.5
                or any(not math.isfinite(ts) for ts in times)
                or any(b <= a or b - a > 0.51 for a, b in zip(times, times[1:]))
                or any(frame.get(risk) is not False for frame in frames for risk in ("text_risk", "face_risk", "dark_risk"))):
            raise ValueError("QC主题、密采样覆盖或逐帧结果不合格")
    sel = json.load(open(os.path.join(WORK, f"selection_{t}.json"), encoding="utf-8"))
    project = os.path.join(PROJECTS, info["project"])
    assert os.path.isdir(project), f"missing project {project}"

    src_final = os.path.join(info.get("final_dir", FINAL), info["final"])
    assert os.path.isfile(src_final), f"missing final {src_final}"
    renders = os.path.join(project, "renders")
    os.makedirs(renders, exist_ok=True)
    shutil.copy2(src_final, os.path.join(renders, "final.mp4"))

    artifacts = os.path.join(project, "artifacts")
    os.makedirs(artifacts, exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    broll = {
        "version": "1.1",
        "project_id": info["project"],
        "render_duration_seconds": 9.0,
        "render_path": "renders/final.mp4",
        "source_platform": source_platform,
        "updated_at": now,
        "selection_policy": sel["selection_policy"],
        "rights_note": sel["rights_note"],
        "visual_review": sel["visual_review"],
        "clips": sel["clips"],
    }
    json.dump(broll, open(os.path.join(artifacts, provenance_name), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    assets = []
    for c in sel["clips"]:
        assets.append({
            "asset_id": f"{c.get('platform') or source_platform}-{info['label']}-{c['scene_id']}",
            "asset_type": "video",
            "role": "scene_broll",
            "scene_id": c["scene_id"],
            "path": c["asset_path"],
            "duration_seconds": 3.0,
            "source_platform": c.get("platform") or source_platform,
            "source_video_id": c["source_video_id"],
            "source_url": c["source_url"],
            "source_title": c["source_title"],
            "creator": c.get("creator", ""),
            "source_file": c["original_delivery_path"],
            "source_in_seconds": c["source_in_seconds"],
            "source_out_seconds": c["source_out_seconds"],
            "caption_policy": c["caption_policy"],
            "rights_status": c.get("rights_status", "unknown"),
            **{key: c[key] for key in ("media_id", "clip_id", "selection_id", "grade", "source_crop") if c.get(key) is not None},
        })
    json.dump({"version": "1.1", "updated_at": now, "assets": assets},
              open(os.path.join(artifacts, "asset_manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    sp_path = os.path.join(artifacts, "scene_plan.json")
    old = {}
    if os.path.isfile(sp_path):
        try:
            old = json.load(open(sp_path, encoding="utf-8"))
        except Exception:
            old = {}
    old_scenes = old.get("scenes", []) if isinstance(old, dict) else []
    scenes = []
    for i, c in enumerate(sel["clips"]):
        prev = old_scenes[i] if i < len(old_scenes) else {}
        scenes.append({
            "id": c["scene_id"],
            "title": prev.get("title") or c["scene_id"],
            "description": prev.get("description") or "",
            "start_seconds": (i) * 3.0,
            "end_seconds": (i + 1) * 3.0,
            "script_section_id": c["scene_id"],
            "shot_intent": prev.get("title") or c["scene_id"],
            "hero_moment": False,
            "visual_asset": c["asset_path"],
            "visual_source_platform": c.get("platform") or source_platform,
        })
    scene_plan = {
        "version": "1.0",
        "title": info["title"],
        "total_duration_seconds": 9.0,
        "metadata": {
            "total_duration_seconds": 9.0,
            "origin": info.get("source_batch", "924-rework-douyin-replication"),
        },
        "scenes": scenes,
    }
    json.dump(scene_plan, open(sp_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    report = {
        "status": "fact_pending" if info.get("editorial_status") == "fact_pending" else "completed",
        "editorial_status": info.get("editorial_status", "legacy_unverified"),
        "source_batch": info.get("source_batch", "923-batch"),
        "source_file": info["final"],
        "ingested_at": old.get("ingested_at", now),
        "pipeline_type": "animated-explainer",
        "updated_at": now,
        "output_path": "renders/final.mp4",
        "source_platform": source_platform,
        "replaced_scene_count": 3,
        "provenance_manifest": f"artifacts/{provenance_name}",
        "caption_review": info.get("caption_review", "已检查三张场景快照；不等同于全片密集QC。"),
        "quality_evidence": "artifacts/template_qc.json" if qc else None,
        "render_profile": {
            "width": 1080, "height": 1920, "fps": 30,
            "duration_seconds": 9.0, "video_codec": "h264", "audio_codec": "aac",
        },
    }
    json.dump(report, open(os.path.join(artifacts, "render_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if qc:
        shutil.copy2(info["qc_file"], os.path.join(artifacts, "template_qc.json"))
    for name, source in info.get("evidence_files", {}).items():
        if os.path.basename(name) != name:
            raise ValueError("证据文件名不得包含目录")
        shutil.copy2(source, os.path.join(artifacts, name))

    snaps = os.path.join(project, "snapshots")
    os.makedirs(snaps, exist_ok=True)
    for i, ts in enumerate(SNAP_TS, 1):
        out = os.path.join(snaps, f"cue-{i:03d}.jpg")
        r = subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-ss", str(ts), "-i",
             os.path.join(renders, "final.mp4"), "-frames:v", "1", "-q:v", "3", out],
            capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(f"SNAP_FAIL {t} {i}: {r.stderr[-200:]}")
    # Explicit automatic policy only; a manual template run remains a candidate.
    if str(HAIKE) not in sys.path:
        sys.path.insert(0, str(HAIKE))
    from backlot.work_catalog import WorkCatalog, sha
    from backlot.work_ingest import completed
    if report["status"] == "completed" and qc:
        completed(WorkCatalog(PROJECTS), info["project"], "renders/final.mp4",
                  "template:" + sha(os.path.join(renders, "final.mp4")), mode=info.get("task_mode"))
    print(f"REWRITE_OK {t} -> {info['project']}")


def main() -> int:
    args = sys.argv[1:]
    if "--manifest" in args:
        index = args.index("--manifest")
        manifest = json.load(open(args[index + 1], encoding="utf-8"))
        for key, info in manifest.items():
            if info.get("editorial_status") not in {"verified", "fact_pending"} or not info.get("qc_file"):
                raise ValueError("新批次须提供事实状态与QC证据")
            THEMES[key] = info
        del args[index:index + 2]
    for t in args:
        rewrite(t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
