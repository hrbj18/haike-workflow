# -*- coding: utf-8 -*-
"""924 rework: preview windows as-rendered, then cut selections into raw923.

Usage:
  # preview: simulate build_923 plates (top 0-570, bottom 1280-1920 blacked out)
  #          and dump 3 frames per clip spec, tiled side by side.
  python select_cut_923.py preview <out_prefix> <spec_json>

  # cut: for each cue, cut 3s window -> raw923/t{n}_{i}.mp4 + project assets/video
  python select_cut_923.py cut <theme_key> <project_id> <spec_json>

spec_json: list of 3 cues:
  [{"cue":"cue-001","t_key":"t5","index":1,"file":"<abs mp4>","source_in":12.0,
    "source_video_id":"...","source_url":"...","source_title":"...",
    "creator":"...","material_role":"main",
    "original_delivery_path":"output/复刻视频/<folder>/02-主素材/x.mp4"}]

cut also writes <WORK>/selection_<t_key>.json with full manifest fields.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backlot.material_crop import template_filter
from backlot.material_library_template import validate_spec

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
RAW = os.path.join(WORK, "raw923")
PROJECTS = str(PROJECTS_DIR)

SCALE = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"
# 版式 v2: 顶板下沿 570 -> 650（见 build_923.py 头注）。此处仅用于 preview 参考线绘制。
PLATE_TOP, PLATE_BOT = 650, 1280


def preview(out_prefix: str, spec_path: str) -> int:
    cues = json.load(open(spec_path, encoding="utf-8"))
    validate_spec(cues)
    from PIL import Image, ImageDraw
    tiles = []
    for cue in cues:
        fin = cue["source_in"]
        for off in (0.5, 1.5, 2.5):
            tmp = out_prefix + "_ptmp.png"
            r = subprocess.run(
                [FFMPEG, "-y", "-loglevel", "error", "-ss", str(fin + off), "-i", cue["file"],
                 "-frames:v", "1", "-vf", template_filter(cue["source_crop"]) if "source_crop" in cue else SCALE, tmp],
                capture_output=True, text=True, timeout=60)
            if r.returncode != 0 or not os.path.isfile(tmp):
                print("PREVIEW_FAIL", cue["cue"], off, r.stderr[-200:])
                tiles.append(None)
                continue
            img = Image.open(tmp)
            img.load()
            d = ImageDraw.Draw(img)
            d.rectangle((0, 0, 1080, PLATE_TOP), fill=(10, 10, 10))
            d.rectangle((0, PLATE_BOT, 1080, 1920), fill=(10, 10, 10))
            d.rectangle((0, PLATE_TOP, 1080, PLATE_TOP + 6), fill=(255, 205, 60))
            d.rectangle((0, PLATE_BOT - 6, 1080, PLATE_BOT), fill=(255, 205, 60))
            img = img.resize((324, 576))
            tiles.append((cue["cue"] + f" @{fin + off:.1f}s", img.copy()))
            img.close()
            if os.path.isfile(tmp):
                os.remove(tmp)
    from PIL import ImageFont
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 15)
    sheet = Image.new("RGB", (336 * len(tiles) + 8, 620), (18, 18, 18))
    d = ImageDraw.Draw(sheet)
    x = 8
    for t in tiles:
        if t:
            label, img = t
            sheet.paste(img, (x, 34))
            d.text((x, 8), label, font=font, fill=(240, 240, 240))
        else:
            d.text((x, 8), "FAIL", font=font, fill=(255, 80, 80))
        x += 336
    out = out_prefix + "_preview.jpg"
    sheet.save(out, quality=85)
    print("PREVIEW:", out)
    return 0


def cut(theme_key: str, project_id: str, spec_path: str) -> int:
    cues = json.load(open(spec_path, encoding="utf-8"))
    validate_spec(cues)
    if not __import__("re").fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", project_id):
        raise ValueError("项目ID无效")
    os.makedirs(RAW, exist_ok=True)
    project = os.path.join(PROJECTS, project_id)
    assets_dir = os.path.join(project, "assets", "video")
    os.makedirs(assets_dir, exist_ok=True)

    # theme short label for asset filenames, e.g. douyin-grok47-cue-001
    label = {"t1": "v900", "t2": "qcom2nm", "t3": "memprice", "t4": "mac",
             "t5": "grok47", "t6": "mi-oss", "t7": "robotpark", "t8": "qyrobot",
             "t9": "nvidia-glass", "t10": "deepseek", "t11": "d35",
             "t12": "claude55", "t13": "spacecomp", "t14": "agentbreach",
             "t15": "qweneva", "t16": "glorym9", "t17": "metamuse",
             "t18": "optimus", "t19": "gpt6drive", "t20": "colossus2",
             "t21": "embodiedbot", "t22": "devday500",
             "t23": "sonnet55",
             # 0930 批次（t24-t29）
             "t24": "gpt61stop", "t25": "ascend950", "t26": "vast10m",
             "t27": "nvagentsec", "t28": "nvchipcn", "t29": "sharpahand",
             "t30": "gpt61sol", "t31": "openaidots", "t32": "pro500",
             "t33": "chatgpt-users-review",
             "t34": "gemini4argon",
             # 2026-10-04 每日自动化批次（t35-t40）
             "t35": "dgxspark64g", "t36": "macosfdagent", "t37": "gpttryon",
             "t38": "musegadget", "t39": "frontieracad", "t40": "sunovoice",
             # 2026-10-05 每日自动化批次（t41-t46）
             "t41": "gtpuspace", "t42": "oaijalap", "t43": "reflopen",
             "t44": "whistlestt", "t45": "dstilelang", "t46": "astribott1",
             # 2026-10-08 每日自动化批次（t47-t52）
             "t47": "gtpu8t8i", "t48": "sierrapap", "t49": "applej450",
             "t50": "cwatermark", "t51": "solmath722", "t52": "gimgprice",
             "t54": "terafab",
             "t55": "nvidia-genesis",
             "t56": "oneplus-display",
             "t58": "tsmc-revenue",
             }[theme_key]

    records = []
    for cue in cues:
        i = cue["index"]
        fin, fout = float(cue["source_in"]), float(cue["source_in"]) + 3.0
        raw_out = os.path.join(RAW, f"{theme_key}_{i}.mp4")
        platform = str(cue.get("source_platform") or "douyin")
        asset_prefix = str(cue.get("asset_prefix") or platform)
        asset_out = os.path.join(assets_dir, f"{asset_prefix}-{label}-cue-{i:03d}.mp4")
        for target in (raw_out, asset_out):
            r = subprocess.run(
                [FFMPEG, "-y", "-loglevel", "error", "-ss", str(fin), "-t", "3.0",
                 "-i", cue["file"], "-vf", template_filter(cue["source_crop"]) if "source_crop" in cue else SCALE, "-an",
                 "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
                 target], capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                print("CUT_FAIL", target, r.stderr[-300:])
                return 1
            print("CUT_OK:", target)
        records.append({
            "scene_id": f"cue-{i:03d}",
            "platform": platform,
            "source_video_id": cue["source_video_id"],
            "source_url": cue["source_url"],
            "source_title": cue["source_title"],
            "creator": cue.get("creator", ""),
            "material_role": cue.get("material_role", "support"),
            "original_delivery_path": cue["original_delivery_path"],
            "asset_path": f"assets/video/{asset_prefix}-{label}-cue-{i:03d}.mp4",
            "raw923_path": f"raw923/{theme_key}_{i}.mp4",
            "source_in_seconds": fin,
            "source_out_seconds": fout,
            "duration_seconds": 3.0,
            "render_transform": template_filter(cue["source_crop"]) if "source_crop" in cue else SCALE,
            "media_id": cue.get("media_id"), "clip_id": cue.get("clip_id"),
            "selection_id": cue.get("selection_id"), "source_crop": cue.get("source_crop"), "grade": cue.get("grade"),
            "caption_policy": "不叠用原视频顶/底字幕；成片顶区和底区使用我方不透明字板，只显示中央素材画面。",
            "rights_status": cue.get("rights_status", "unknown"),
            "rights_note": cue.get("rights_note", ""),
        })

    platforms = sorted({record["platform"] for record in records})
    sel = {
        "version": "1.1",
        "theme_key": theme_key,
        "project_id": project_id,
        "render_duration_seconds": 9.0,
        "render_path": "renders/final.mp4",
        "source_platform": platforms[0] if len(platforms) == 1 else "mixed",
        "selection_policy": "3 个 3 秒短片段；主题相关并经 agent 抽帧目检中段画面干净；顶部/底部原字幕由不透明自有字板完全覆盖，中央保留素材画面。",
        "rights_note": "Douyin 原素材授权状态未核实，发布前需确认可用范围。",
        "visual_review": "agent 逐帧目检（contact sheet + 成片视角预览），无烧录字幕/水印进入中央可见区。",
        "clips": records,
    }
    sel_path = os.path.join(WORK, f"selection_{theme_key}.json")
    json.dump(sel, open(sel_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("SELECTION:", sel_path)
    return 0


def main() -> int:
    mode = sys.argv[1]
    if mode == "preview":
        return preview(sys.argv[2], sys.argv[3])
    if mode == "cut":
        return cut(sys.argv[2], sys.argv[3], sys.argv[4])
    print("unknown mode", mode)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
