"""Review the exact source windows that a material proposal will put on screen.

The contact sheets use the same center crop as the full-bleed renderer.  They
are evidence for the current agent, not a substitute for its visual judgment.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from PIL import Image, ImageDraw

class MaterialWindowQAError(ValueError):
    """The proposed source window lacks current visual QA."""


VERSION = 1
FPS = 3
TILE_WIDTH, TILE_HEIGHT = 360, 640
PAGE_FRAMES = 8
MAX_WINDOW_SECONDS = 300


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source(project_dir: Path, asset: dict[str, Any]) -> Path:
    path = Path(str(asset.get("path") or ""))
    resolved = path if path.is_absolute() else project_dir / path
    if not resolved.is_file():
        raise MaterialWindowQAError(f"{asset.get('id')} 的源视频文件不存在")
    return resolved


def _windows(state: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    windows = list(plan.get("sequences") or [])
    scenes = {str(item.get("id") or ""): item for item in state.get("scenes") or [] if isinstance(item, dict)}
    preserved_count = 0
    for target in plan.get("target_plans") or []:
        if target.get("mode") != "preserve":
            continue
        scene = scenes.get(str(target.get("scene_id") or ""), {})
        start, end = float(target["start_seconds"]), float(target["end_seconds"])
        covered = 0.0
        for block in ((scene.get("visual_timeline") or {}).get("blocks") or []):
            if not isinstance(block, dict):
                continue
            block_start, block_end = float(block.get("start_seconds") or 0), float(block.get("end_seconds") or 0)
            overlap_start, overlap_end = max(start, block_start), min(end, block_end)
            if overlap_end - overlap_start <= .001:
                continue
            source_in = float(block.get("source_in_seconds") or 0) + overlap_start - block_start
            preserved_count += 1
            covered += overlap_end - overlap_start
            windows.append({
                "sequence_id": f"LMP-{preserved_count:03d}", "asset_id": block.get("asset_id"),
                "scene_id": target["scene_id"], "target_id": target["target_id"],
                "source_in_seconds": round(source_in, 3),
                "source_out_seconds": round(source_in + overlap_end - overlap_start, 3),
                "match_reason": "保留已有主体画面",
            })
        if abs(covered - (end - start)) > .02:
            raise MaterialWindowQAError(f"{target['target_id']} 的已有画面无法完整审核")
    return windows


def prepare_window_qa_task(
    project_dir: Path, state: dict[str, Any], request: dict[str, Any], proposal: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Make paged, full-window contact sheets for every selected new shot."""
    if plan.get("status") != "ready":
        raise MaterialWindowQAError("选材尚有缺口，请先补齐或记录采集需求")
    assets = {str(item.get("id") or ""): item for item in state.get("assets") or [] if isinstance(item, dict)}
    windows = _windows(state, plan)
    sources = []
    for sequence in windows:
        asset = assets.get(str(sequence.get("asset_id") or ""))
        if asset is None:
            raise MaterialWindowQAError("选材源视频已被移除")
        path = _source(project_dir, asset)
        sources.append({
            "sequence_id": sequence["sequence_id"], "asset_id": sequence["asset_id"],
            "source_in_seconds": sequence["source_in_seconds"],
            "source_out_seconds": sequence["source_out_seconds"],
            "source_fingerprint": _file_hash(path),
            "asset_type": str(asset.get("type") or "video").lower(),
        })
    identity = {
        "version": VERSION, "model": plan["model"],
        "request_fingerprint": request["request_fingerprint"],
        "proposal_fingerprint": _hash(proposal), "sources": sources,
    }
    directory = project_dir / "artifacts" / "material-window-qa" / _hash(identity)[:24]
    manifest = directory / "task.json"
    if manifest.is_file():
        try:
            cached = json.loads(manifest.read_text(encoding="utf-8"))
            if (cached.get("identity") == identity
                and cached.get("task_fingerprint") == _hash({key: value for key, value in cached.items() if key != "task_fingerprint"})
                and all(
                (project_dir / sheet["path"]).resolve().is_relative_to(directory.resolve())
                and (project_dir / sheet["path"]).is_file()
                and _file_hash(project_dir / sheet["path"]) == sheet["sha256"]
                for item in cached.get("sequences") or [] for sheet in item.get("sheets") or []
            )):
                return cached
        except (OSError, ValueError, KeyError):
            pass
    if sources and not (ffmpeg := shutil.which("ffmpeg")):
        raise MaterialWindowQAError("需要 FFmpeg 生成实际使用区间的审核宫格")
    directory.mkdir(parents=True, exist_ok=True)
    output = []
    for sequence, source_info in zip(windows, sources):
        path = _source(project_dir, assets[source_info["asset_id"]])
        duration = float(source_info["source_out_seconds"]) - float(source_info["source_in_seconds"])
        if duration <= 0 or duration > MAX_WINDOW_SECONDS:
            raise MaterialWindowQAError("单个源区间必须在 0—300 秒内；更长连续段请按镜头切分")
        with tempfile.TemporaryDirectory(prefix="frames-", dir=directory) as temporary:
            frames_dir = Path(temporary)
            input_args = (["-loop", "1", "-i", str(path)] if source_info["asset_type"] == "image"
                          else ["-ss", f"{source_info['source_in_seconds']:.3f}", "-i", str(path)])
            command = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *input_args,
                "-t", f"{min(duration, 1 / FPS) if source_info['asset_type'] == 'image' else duration:.3f}", "-an",
                "-vf", f"fps={FPS},scale={TILE_WIDTH}:{TILE_HEIGHT}:force_original_aspect_ratio=increase,"
                       f"crop={TILE_WIDTH}:{TILE_HEIGHT},setsar=1",
                "-q:v", "3", str(frames_dir / "%05d.jpg"),
            ]
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=max(60, int(duration * 5)))
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise MaterialWindowQAError(f"{sequence['sequence_id']} 审核帧提取失败") from exc
            frames = sorted(frames_dir.glob("*.jpg"))
            if completed.returncode or not frames:
                raise MaterialWindowQAError(f"{sequence['sequence_id']} 审核帧提取失败：{completed.stderr[-300:]}")
            if source_info["asset_type"] != "image" and len(frames) < max(1, int(duration * FPS) - 1):
                raise MaterialWindowQAError(f"{sequence['sequence_id']} 的实际源视频不足以覆盖所选时间段")
            sheets = []
            for page, offset in enumerate(range(0, len(frames), PAGE_FRAMES), 1):
                subset = frames[offset:offset + PAGE_FRAMES]
                canvas = Image.new("RGB", (TILE_WIDTH * 2, (TILE_HEIGHT + 30) * 4), "#101010")
                draw = ImageDraw.Draw(canvas)
                for position, frame in enumerate(subset):
                    x, y = (position % 2) * TILE_WIDTH, (position // 2) * (TILE_HEIGHT + 30)
                    with Image.open(frame) as item:
                        canvas.paste(item.convert("RGB"), (x, y + 30))
                    approximate = float(source_info["source_in_seconds"]) + (offset + position) / FPS
                    draw.text((x + 8, y + 7), f"{sequence['sequence_id']}  source {approximate:.2f}s", fill="white")
                sheet_path = directory / f"{sequence['sequence_id']}-{page:03d}.jpg"
                canvas.save(sheet_path, quality=88)
                sheets.append({"path": str(sheet_path.relative_to(project_dir)).replace("\\", "/"),
                               "sha256": _file_hash(sheet_path), "frame_count": len(subset)})
        output.append({**source_info, "target_id": sequence.get("target_id"),
                       "scene_id": sequence["scene_id"], "match_reason": sequence.get("match_reason"),
                       "sheets": sheets})
    task = {
        "identity": identity, "sequences": output,
        "instruction": "逐页查看全部宫格：检查实际成片中心裁切区域的原字幕、水印、贴纸、文字遮挡与题材匹配；全部合格后逐镜头提交 clean 和 relevant。",
    }
    task["task_fingerprint"] = _hash(task)
    manifest.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    return task


def validate_window_qa(
    project_dir: Path, state: dict[str, Any], request: dict[str, Any], proposal: dict[str, Any],
    plan: dict[str, Any], verdict: Any,
) -> dict[str, Any]:
    """Reject stale or partial attestations before the timeline can be changed."""
    if not plan.get("visual_need_fingerprint") or not _windows(state, plan):
        return {"status": "not_required", "sequences": []}
    if not isinstance(verdict, dict) or not isinstance(verdict.get("checks"), list):
        raise MaterialWindowQAError("请先生成并查看实际源区间宫格，再提交逐镜头审核结果")
    task = prepare_window_qa_task(project_dir, state, request, proposal, plan)
    if verdict.get("task_fingerprint") != task["task_fingerprint"]:
        raise MaterialWindowQAError("源视频或选材已变化，请重新查看实际源区间宫格")
    checks = verdict["checks"]
    by_id = {str(item.get("sequence_id") or ""): item for item in checks if isinstance(item, dict)}
    expected = {item["sequence_id"] for item in task["sequences"]}
    if len(checks) != len(expected) or set(by_id) != expected:
        raise MaterialWindowQAError("实际源区间审核须逐镜头完整提交")
    for sequence_id, item in by_id.items():
        if item.get("clean") is not True or item.get("relevant") is not True:
            raise MaterialWindowQAError(f"{sequence_id} 的实际画面不干净或题材不匹配，请改选镜头")
        observation = str(item.get("observation") or "").strip()
        if len(observation) < 8 or len(observation) > 500:
            raise MaterialWindowQAError(f"{sequence_id} 缺少具体的画面审核观察")
    return {"status": "passed", "task_fingerprint": task["task_fingerprint"],
            "sequences": [{"sequence_id": item["sequence_id"], "observation": by_id[item["sequence_id"]]["observation"]}
                          for item in task["sequences"]]}
