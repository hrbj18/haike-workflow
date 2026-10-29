"""Voice-bound, project-owned presenters for optional commentary segments.

The source video stays the main frame. Presenter audio is never mixed: the
registered narration remains the single clock and single audible voice.
"""
from pathlib import Path
import shutil

from backlot import commentary_audio as audio
from backlot.commentary_common import (
    CommentaryError, FPS, digest, file_sha256, identifier, immutable, number,
    probe, read_json, text, verified, crop_value, crop_filter,
)


def directory(project, identity):
    identifier(identity, "CP-")
    return Path(project) / "assets/video/commentary-presenters" / identity[:27]


def read(project, identity):
    target = directory(project, identity)
    asset = read_json(target / "presenter.json")
    if asset.get("id") != identity:
        raise CommentaryError("出镜素材身份不匹配")
    verified(target / "presenter.mp4", asset["sha256"])
    return asset


def list_presenters(project):
    root = Path(project) / "assets/video/commentary-presenters"
    return [read(project, read_json(p)["id"]) for p in sorted(root.glob("CP-*/presenter.json"))]


def import_presenter(project, payload):
    if not isinstance(payload, dict):
        raise CommentaryError("出镜素材配置无效")
    take = audio.read(project, payload.get("audio_id"))
    if take["kind"] != "narration":
        raise CommentaryError("出镜素材须绑定旁白音轨")
    name = text(payload.get("name"), "出镜角色名称", 120)
    provenance = text(payload.get("provenance"), "嘴型与配音对应的来源说明", 2000)
    source = Path(str(payload.get("path") or "")).resolve()
    if not source.is_file() or source.suffix.lower() != ".mp4":
        raise CommentaryError("出镜素材须为已有 MP4 视频")
    sha = file_sha256(source)
    info = probe(source)
    video = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
    if not video:
        raise CommentaryError("出镜素材没有视频轨")
    duration = number(video.get("duration", info["format"].get("duration")), "出镜素材时长", .1, 3600)
    identity = "CP-" + digest({"sha256": sha, "audio_id": take["id"], "name": name, "provenance": provenance})
    target = directory(project, identity)
    if (target / "presenter.json").is_file():
        return read(project, identity)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target / "presenter.mp4")
    verified(source, sha)
    verified(target / "presenter.mp4", sha)
    asset = {"id": identity, "name": name, "provenance": provenance,
        "audio_id": take["id"], "audio_sha256": take["sha256"], "text_sha256": take["text_sha256"],
        "sha256": sha, "duration": duration, "width": video["width"], "height": video["height"],
        "path": str(target / "presenter.mp4")}
    immutable(target / "presenter.json", asset)
    return asset


def normalize(project, payload, audio_id):
    if not isinstance(payload, dict) or set(payload) - {"asset_id", "x", "y", "diameter", "layout_review", "crop"}:
        raise CommentaryError("出镜配置只接受素材、圆形位置、直径和避让说明")
    asset = read(project, payload.get("asset_id"))
    if not audio_id or asset["audio_id"] != audio_id:
        raise CommentaryError("出镜嘴型与本段配音不匹配，请选用对应配音的出镜素材")
    result = {"asset_id": asset["id"], "x": number(payload.get("x", .74), "出镜横坐标", 0, 1),
        "y": number(payload.get("y", .12), "出镜纵坐标", 0, 1),
        "diameter": number(payload.get("diameter", .20), "出镜直径（画面宽度比例）", .1, .35),
        "layout_review": text(payload.get("layout_review"), "字幕和素材人物避让说明", 2000)}
    if "crop" in payload:
        result["crop"] = crop_value(payload["crop"])
    return result


def freeze(project, layer, take, profile, frames):
    asset = read(project, layer["asset_id"])
    if asset["audio_id"] != take["id"] or asset["audio_sha256"] != take["sha256"]:
        raise CommentaryError("出镜素材绑定的配音已变化")
    width, height = profile["width"], profile["height"]
    size = round(layer["diameter"] * width / 2) * 2
    x, y = round(layer["x"] * width), round(layer["y"] * height)
    if x + size > width or y + size > height:
        raise CommentaryError("出镜圆形超出画面，请调整位置或直径")
    start = take.get("playback_start_sample", 0) / take["sample_rate"]
    if start + frames/FPS > asset["duration"] + .001:
        raise CommentaryError("出镜素材无法覆盖本段实际配音，禁止循环或定格补齐")
    return {**layer, "asset": asset, "start": start, "geometry": {"x": x, "y": y, "size": size}}


def overlay_filter(layer, placements=None):
    box = layer["geometry"]
    size = box["size"]
    # Alpha is computed after a centred square crop, retaining the main image
    # outside the circle. The provider's video/audio streams are never looped.
    crop = crop_filter(layer["crop"]) + "," if "crop" in layer else ""
    overlay=f"x={box['x']}:y={box['y']}"
    if placements is not None:
        visible=[p for p in placements if p['geometry']]
        x,y='0','0'; enabled=[]
        for placement in reversed(visible):
            condition=f"gte(t,{placement['start_frame']/FPS:.9f})*lt(t,{placement['end_frame']/FPS:.9f})"
            geometry=placement['geometry']
            x=f"if({condition},{geometry['x']},{x})"; y=f"if({condition},{geometry['y']},{y})"; enabled.append(condition)
        overlay=f"x='{x}':y='{y}':enable='{'+'.join(enabled) or '0'}'"
    return (f"[1:v]trim=start={layer['start']:.9f},setpts=PTS-STARTPTS,fps={FPS},{crop}"
        f"scale={size}:{size}:force_original_aspect_ratio=increase,crop={size}:{size},setsar=1,format=rgba,"
        f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(pow(X-{size/2},2)+pow(Y-{size/2},2),pow({size/2-1},2)),255,0)'[p];"
        f"[0:v][p]overlay={overlay}:eof_action=pass:repeatlast=0:shortest=1,format=yuv420p[v]")
