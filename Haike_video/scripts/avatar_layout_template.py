"""Versioned avatar layout sample/background compiler; no project state writes.

Official full-preview/final production stays on the workbench queue. This CLI
renders an isolated sample or a background asset consumed by that pipeline.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import html
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw, ImageFont
from lib.ffmpeg_locator import resolve_ffmpeg_pair


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_preset(name):
    if Path(name).name != name:
        raise ValueError("preset 必须是 config/avatar-layouts 中的名称")
    path = ROOT / "config" / "avatar-layouts" / f"{name}.json"
    preset = read_json(path)
    if preset["frame"] != {"width": 1080, "height": 1920, "fps": 30}:
        raise ValueError("V1 仅验证了 1080×1920 / 30fps；其他画幅需新版本")
    return preset, path


def font_path(preset, explicit=None):
    path = Path(explicit) if explicit else Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / preset["font"]["windows_file"]
    if not path.is_file():
        raise ValueError("未找到模板字体，请用 --font 指定中文粗体字体并重新视觉核验")
    return path.resolve()


def finite(value, name, positive=False):
    number = float(value)
    if not math.isfinite(number) or number < 0 or (positive and number <= 0):
        raise ValueError(f"{name} 必须是有限的{'正' if positive else '非负'}数")
    return number


def pixel_geometry(preset):
    frame, g = preset["frame"], preset["presenter"]["geometry"]
    return {"x": round(frame["width"] * g["x"]), "y": round(frame["height"] * g["y"]),
            "width": int(frame["width"] * g["width"]) // 2 * 2,
            "height": int(frame["width"] * g["width"]) // 2 * 2}


def text_positions(preset, spec, font, sample=True):
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    result = []
    for key, content in [("title", spec["title"]), ("test_subtitle", spec.get("test_subtitle", "") if sample else "")]:
        if not content or "\n" in content:
            if key == "title" or sample:
                raise ValueError(f"{key} 必须是非空单行文本；长字幕请按实际口播拆成短句")
            continue
        style = preset[key]
        face = ImageFont.truetype(str(font), style["font_size"])
        stroke = style.get("stroke_width", 0)
        box = draw.textbbox((0, 0), content, font=face, stroke_width=stroke)
        width = box[2] - box[0]
        x = style.get("x", (preset["frame"]["width"] - width) // 2)
        actual = draw.textbbox((x, style["y"]), content, font=face, stroke_width=stroke)
        if width > style["max_width"] or actual[3] > style["max_bottom"]:
            raise ValueError(f"{key} 超出模板文字安全框；缩短文案，不自动裁字或放大/缩小字号")
        result.append((key, content, (x, style["y"]), face, actual))
    return result


def make_base(preset, spec, font, path, sample=True):
    frame, bg = preset["frame"], preset["background"]
    image = Image.new("RGB", (frame["width"], frame["height"]))
    pixels = image.load()
    for y in range(image.height):
        glow = max(0.0, 1.0 - abs(y - bg["glow_y"]) / bg["glow_span"])
        for x in range(image.width):
            side = max(0.0, 1.0 - abs(x - bg["side_x"]) / bg["side_span"])
            pixels[x, y] = tuple(int(bg["base_rgb"][i] + bg["glow_rgb"][i] * glow + bg["side_rgb"][i] * side * glow) for i in range(3))
    draw = ImageDraw.Draw(image)
    for arc in bg["arcs"]:
        draw.arc(tuple(arc["box"]), arc["start"], arc["end"], fill=tuple(arc["color"]), width=arc["width"])
    c = preset["card"]
    for offset, radius, color in [(8, c["outer_radius"], c["outer_color"]), (4, c["inner_radius"], c["inner_color"])]:
        draw.rounded_rectangle((c["x"]-offset, c["y"]-offset, c["x"]+c["width"]+offset, c["y"]+c["height"]+offset), radius=radius, fill=tuple(color))
    p, ring = pixel_geometry(preset), preset["presenter"]["ring_width"]
    draw.ellipse((p["x"]-ring, p["y"]-ring, p["x"]+p["width"]+ring, p["y"]+p["height"]+ring), fill=tuple(preset["presenter"]["ring_color"]))
    for key, content, position, face, _ in text_positions(preset, spec, font, sample):
        style = preset[key]
        draw.text(position, content, font=face, fill=tuple(style.get("color", [255, 255, 255])),
                  stroke_width=style.get("stroke_width", 0), stroke_fill=tuple(style.get("stroke_color", [0, 0, 0])))
    image.save(path)


def probe(path, ffprobe):
    return json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], encoding="utf-8"))


def validate(spec, project, preset, font, ffprobe, sample=True):
    duration = finite(spec["duration_seconds"], "duration_seconds", True)
    if sample and duration > 10:
        raise ValueError("render-test 仅允许不超过 10 秒的独立样板；全片走工作台队列")
    segments = spec.get("segments", [])
    if not segments or abs(sum(finite(s["duration_seconds"], "segment duration", True) for s in segments) - duration) > 0.0001:
        raise ValueError("素材区间必须完整覆盖本段时长")
    resolved = []
    media = segments + ([spec["avatar"], spec["audio"]] if sample else [])
    for index, item in enumerate(media):
        path = (project / item["path"]).resolve()
        if not path.is_file():
            raise ValueError(f"素材不存在：{path}")
        if index < len(segments):
            if item.get("kind") not in {"image", "video"} or not item.get("asset_id") or not item.get("source_url") or not item.get("rights_status"):
                raise ValueError("每段必须有 kind、asset_id、source_url、rights_status")
            if item.get("fit", "cover") not in {"cover", "contain"}:
                raise ValueError("素材适配方式只能为 cover 或 contain")
        start = finite(item.get("source_in_seconds", item.get("start_seconds", 0)), "source start")
        needed = finite(item.get("duration_seconds", duration), "duration", True)
        if item.get("kind") == "image":
            with Image.open(path) as source:
                source.verify()
        else:
            info = probe(path, ffprobe)
            stream_type = "audio" if sample and index == len(media)-1 else "video"
            stream = next((s for s in info["streams"] if s.get("codec_type") == stream_type), None)
            if not stream:
                raise ValueError(f"缺少 {stream_type} 流：{path}")
            available = float(stream.get("duration") or info.get("format", {}).get("duration") or 0)
            if start + needed > available + 0.04:
                raise ValueError(f"源区间超出媒体时长：{path}")
        resolved.append(path)
    if sample and spec["audio"].get("already_mixed") is not True:
        raise ValueError("样板须传入本期已确认混音；本工具不会自行修改 BGM 或人声增益")
    text_positions(preset, spec, font, sample)
    return resolved


def presenter_filter(project, spec, preset, source):
    from backlot import workbench as w
    state = deepcopy(read_json(project / "artifacts" / "workbench.json"))
    scene = next(s for s in state["scenes"] if s["id"] == spec["scene_id"])
    presenter = scene["presenter"]
    resolved = w._presenter_layout(state, presenter)
    presenter.update(layout_override=preset["presenter"]["geometry"], shape="circle",
                     face_crop=spec["avatar"].get("face_crop", resolved["face_crop"]),
                     crop_bottom=spec["avatar"].get("crop_bottom", resolved["crop_bottom"]))
    geometry = w._avatar_pip_geometry(project, state, scene, source)
    if any(geometry[key] != pixel_geometry(preset)[key] for key in ("x", "y", "width", "height")):
        raise ValueError("工作台几何与模板不一致；先核对渲染配置")
    return geometry, w._avatar_pip_filter(geometry, fps=preset["frame"]["fps"], duration=spec["duration_seconds"])


def render(spec, project, preset, preset_path, font, output, sample, overwrite=False):
    pair = resolve_ffmpeg_pair()
    if not pair:
        raise ValueError("未找到已安装的 FFmpeg/ffprobe")
    ffmpeg, ffprobe = pair
    inputs = validate(spec, project, preset, font, ffprobe, sample)
    allowed = project / ("renders" if sample else "assets")
    if not output.is_relative_to(allowed.resolve()):
        raise ValueError(f"输出必须位于 {allowed}")
    if output in inputs or output == preset_path.resolve():
        raise ValueError("输出不能覆盖输入")
    if output.exists() and not overwrite:
        raise ValueError("输出已存在，请使用新版本文件名或显式 --overwrite")
    output.parent.mkdir(parents=True, exist_ok=True)
    duration, fps, c = spec["duration_seconds"], preset["frame"]["fps"], preset["card"]
    with tempfile.TemporaryDirectory(prefix="avatar-layout-", dir=output.parent) as temporary:
        base = Path(temporary) / "base.png"
        staged = Path(temporary) / "output.mp4"
        make_base(preset, spec, font, base, sample)
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-framerate", str(fps), "-t", str(duration), "-i", str(base)]
        graph = [f"[0:v]fps={fps},trim=duration={duration},setpts=PTS-STARTPTS[base]"]
        labels = []
        for i, segment in enumerate(spec["segments"], 1):
            if segment["kind"] == "image":
                command += ["-loop", "1", "-framerate", str(fps)]
            else:
                command += ["-ss", str(segment.get("source_in_seconds", 0))]
            command += ["-t", str(segment["duration_seconds"]), "-i", str(inputs[i-1])]
            label = f"card{i}"
            if segment.get("fit") == "contain":
                fitting = (f"scale={c['width']}:{c['height']}:force_original_aspect_ratio=decrease,"
                           f"pad={c['width']}:{c['height']}:(ow-iw)/2:(oh-ih)/2:color=white")
            else:
                fitting = (f"scale={c['width']}:{c['height']}:force_original_aspect_ratio=increase,"
                           f"crop={c['width']}:{c['height']}")
            graph.append(f"[{i}:v]{fitting},setsar=1,fps={fps},trim=duration={segment['duration_seconds']},setpts=PTS-STARTPTS[{label}]")
            labels.append(f"[{label}]")
        graph.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[card]")
        graph.append(f"[base][card]overlay={c['x']}:{c['y']}:shortest=1[withcard]")
        geometry = pixel_geometry(preset)
        if sample:
            avatar_index = len(labels) + 1
            for item, path in zip([spec["avatar"], spec["audio"]], inputs[-2:]):
                command += ["-ss", str(item.get("start_seconds", 0)), "-t", str(duration), "-i", str(path)]
            geometry, filter_string = presenter_filter(project, spec, preset, inputs[-2])
            graph.append(f"[{avatar_index}:v]{filter_string}[presenter]")
            graph.append(f"[withcard][presenter]overlay={geometry['x']}:{geometry['y']}:shortest=1,format=yuv420p[v]")
        else:
            graph.append("[withcard]format=yuv420p[v]")
        command += ["-filter_complex", ";".join(graph), "-map", "[v]"]
        if sample:
            command += ["-map", f"{avatar_index+1}:a:0", "-c:a", "aac", "-b:a", "192k"]
        else:
            command += ["-an"]
        command += ["-t", str(duration), "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-movflags", "+faststart", str(staged)]
        subprocess.run(command, check=True)
        info = probe(staged, ffprobe)
        if abs(float(info["format"]["duration"]) - duration) > 0.08:
            raise ValueError("输出时长与计划不一致")
        staged.replace(output)
    receipt = {"preset_id": preset["id"], "preset_sha256": digest(preset_path), "font_sha256": digest(font),
               "mode": "isolated_test" if sample else "background_asset", "spec": spec,
               "presenter_geometry": geometry, "source_sha256": {str(p): digest(p) for p in inputs},
               "output": str(output), "output_sha256": digest(output), "probe": info,
               "platform_ui_verified": False, "project_state_modified": False}
    output.with_suffix(".manifest.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output": str(output), "manifest": str(output.with_suffix(".manifest.json"))}


def diagram(preset, output):
    p, c, t, s = pixel_geometry(preset), preset["card"], preset["title"], preset["test_subtitle"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920" width="540" height="960">
<rect width="1080" height="1920" fill="#081b32"/>
<g font-family="Microsoft YaHei, sans-serif" fill="white" font-size="28">
<rect width="1080" height="288" fill="#782f45" opacity=".55"/><text x="50" y="140">顶部 15%：仅背景，避开导航 / 搜索</text>
<rect x="{t['x']}" y="{t['y']}" width="{t['max_width']}" height="100" fill="#254664"/><text x="135" y="480">本期标题（68 px，测量宽度）</text>
<circle cx="{p['x']+p['width']/2}" cy="{p['y']+p['height']/2}" r="{p['width']/2}" fill="#218fae"/><text x="{p['x']+38}" y="{p['y']+130}">数字人</text>
<rect x="{c['x']}" y="{c['y']}" width="{c['width']}" height="{c['height']}" rx="36" fill="#e9f1f8"/>
<text x="180" y="850" fill="#123">主体素材：690 × 620</text><text x="180" y="900" fill="#123">左上角 (110, 625)</text><text x="180" y="950" fill="#123">动态片段 / 官方产品标识</text>
<rect x="915" y="750" width="165" height="850" fill="#782f45" opacity=".55"/><text x="932" y="1100" font-size="24">操作栏</text>
<rect x="190" y="{s['y']}" width="700" height="100" fill="#254664"/><text x="230" y="1405">逐句字幕：48 px；超宽先拆句</text>
<rect y="1536" width="1080" height="384" fill="#782f45" opacity=".55"/><text x="50" y="1740">底部预留：作者、描述、导航</text>
<text x="45" y="1870" font-size="22">{html.escape(preset['id'])} · 参数示意；不是平台官方安全区</text></g></svg>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inspect", "render-test", "render-background", "diagram"])
    parser.add_argument("--preset", default="douyin-safe-circle-v1")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--font", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        preset, preset_path = load_preset(args.preset)
        if args.command == "diagram":
            if not args.output:
                parser.error("diagram 需要 --output")
            diagram(preset, args.output.resolve())
            print(args.output.resolve())
            return
        if not args.project or not args.spec:
            parser.error("需要 --project 和 --spec")
        project, spec = args.project.resolve(), read_json(args.spec)
        if spec.get("preset") != preset["id"]:
            raise ValueError("spec 与 --preset 版本不一致")
        font = font_path(preset, args.font)
        if args.command == "inspect":
            pair = resolve_ffmpeg_pair()
            if not pair:
                raise ValueError("缺少 FFmpeg/ffprobe")
            validate(spec, project, preset, font, pair[1], sample="avatar" in spec)
            result = {"valid": True, "preset": preset["id"], "presenter_pixels": pixel_geometry(preset), "project_state_modified": False}
        else:
            if not args.output:
                parser.error("渲染需要 --output")
            result = render(spec, project, preset, preset_path, font, args.output.resolve(), args.command == "render-test", args.overwrite)
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, KeyError, StopIteration, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"模板处理失败：{exc}\n")


if __name__ == "__main__":
    main()
