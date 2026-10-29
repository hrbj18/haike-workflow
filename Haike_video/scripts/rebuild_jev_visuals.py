from __future__ import annotations

import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backlot import workbench as wb

PROJECT = ROOT / "projects" / "jev-remake-1"
STOCK = ROOT / ".backlot" / "9.14-remake-8" / "jev" / "stock"

# One source clip per scene where possible. The three remaining scenes retain
# verified Jev/RLCD material as the factual anchor points.
PLAN = [
    ("T001", "software-automation", "7534244.mp4"),
    ("T002", "", "K1-.mp4"),
    ("T003", "code-screen", "18382358.mp4"),
    ("T004", "software-automation", "854086.mp4"),
    ("T005", "server-data", "7140931.mp4"),
    ("T006", "workflow", "36328529.mp4"),
    ("T007", "server-data", "1085656.mp4"),
    ("T008", "code-screen", "854053.mp4"),
    ("T009", "", "K1-.mp4"),
    ("T010", "server-data", "5028622.mp4"),
    ("T011", "workflow", "7448473.mp4"),
    ("T012", "", "K1-.mp4"),
]


def main() -> None:
    state = wb._load_for_write(PROJECT)
    assets = {str(a.get("path")): a for a in state.get("assets", [])}
    asset_by_path = {str(a.get("path")): a for a in state.get("assets", [])}
    registered: dict[tuple[str, str], str] = {}

    for scene_id, slug, filename in PLAN:
        if slug:
            source = STOCK / slug / filename
            target_rel = f"assets/video/pexels/jev-{scene_id}-{filename}"
            target = PROJECT / target_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(source, target)
            key = (slug, filename)
            if key not in registered:
                existing = asset_by_path.get(target_rel)
                if existing:
                    asset_id = str(existing["id"])
                else:
                    probe = wb._probe_video(target, wb._ffmpeg_available())
                    asset = wb.add_asset(PROJECT, {
                        "name": f"Jev Pexels {filename}",
                        "type": "video",
                        "source_type": "web_download",
                        "path": target_rel,
                        "duration_seconds": probe.get("duration_seconds"),
                        "resolution": probe.get("resolution"),
                        "provider": "Pexels",
                        "source_tool": "pexels_video",
                        "license": "Pexels License (free, no attribution required)",
                        "source_url": f"https://www.pexels.com/video/{filename.removesuffix('.mp4')}/",
                        "generation": {"video_id": filename.removesuffix('.mp4')},
                    })
                    latest = wb._load_for_write(PROJECT)
                    asset = next(a for a in latest.get("assets", []) if str(a.get("path")) == target_rel)
                    asset_id = str(asset["id"])
                    asset_by_path[target_rel] = asset
                    state = latest
                registered[key] = asset_id
        else:
            asset_id = "S-001"
            target_rel = "assets/video/clean-master/K1-.mp4"

        scene = next(s for s in state["scenes"] if str(s.get("id")) == scene_id)
        start = 0.0
        scene_start = float(scene.get("start_seconds") or 0.0)
        scene_end = float(scene.get("end_seconds") or scene_start)
        duration = max(0.1, scene_end - scene_start)
        if slug:
            source_path = PROJECT / target_rel
            probe = wb._probe_video(source_path, wb._ffmpeg_available()) or {}
            source_duration = float(((probe.get("format") or {}).get("duration")) or 0.0)
            source_in = 0.0
            source_out = min(source_duration, duration)
        else:
            source_in = {"T002": 22.05, "T009": 94.67, "T012": 2.53}[scene_id]
            source_out = source_in + duration
        wb.update_scene_visual_timeline(PROJECT, scene_id, {"blocks": [{
            "id": f"VB-{scene_id[1:]}",
            "start_seconds": start,
            "end_seconds": duration,
            "story_id": "",
            "source_mode": "web_download",
            "asset_id": asset_id,
            "label": f"Jev visual refresh · {filename}",
            "status": "ready",
            "locked": False,
            "query": "Pexels technology B-roll" if slug else "Jev/RLCD factual anchor",
            "context_text": scene.get("description", ""),
            "attempt": 0,
            "error": "",
            "source_in_seconds": source_in,
            "source_out_seconds": source_out,
        }]})

    print("updated", len(PLAN), "scenes")
    print("pexels_assets", len(registered))
    print("review statuses reset by timeline updates; preview must be regenerated")


if __name__ == "__main__":
    main()
