"""Prepare/render an isolated Template 7 development sample with existing media.

No provider, ASR, workbench, registered preview runner or publication calls.
Formal parent-video production still requires its own queue integration.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

HAIKE = Path(__file__).resolve().parents[1]
WORKSPACE = HAIKE.parent
TEMPLATE = HAIKE / "templates" / "avatar-interview-v7"
SOURCE_FILES = ("index.tsx", "Root.tsx", "Composition.tsx", "Captions.tsx", "layout.json")
TEMPLATE_ID = "avatar-interview-v7"
COMPOSITION_ID = "AvatarTemplate7Sample"
sys.path.insert(0, str(HAIKE))
os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def number(value, field, minimum=0):
    if isinstance(value, bool):
        raise ValueError(f"{field} 必须是有限数值")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"{field} 必须是大于等于 {minimum} 的有限数值")
    return result


def text(value, field, optional=False):
    if optional and value in (None, ""):
        return ""
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise ValueError(f"{field} 必须是非空单行文字")
    return value.strip()


def private_project(path):
    result = Path(path).expanduser().resolve()
    allowed = (WORKSPACE / ".local", HAIKE / "projects", HAIKE / ".backlot")
    if not any(result != root and result.is_relative_to(root.resolve()) for root in allowed):
        raise ValueError("样片项目必须位于本checkout的.local/、Haike_video/projects/或.backlot/子目录")
    return result


def run(command, timeout=180):
    from lib.subprocess_window import no_window_kwargs
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=timeout, **no_window_kwargs())
    if result.returncode:
        raise ValueError("本地媒体处理失败：" + result.stderr[-1600:])
    return result.stdout


def probe(path, ffprobe):
    return json.loads(run([str(ffprobe), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]))


def stream_duration(info, kind):
    stream = next((item for item in info.get("streams", []) if item.get("codec_type") == kind), None)
    if stream is None:
        raise ValueError(f"媒体缺少{kind}流")
    return number(stream.get("duration") or info.get("format", {}).get("duration"), "媒体时长", .001)


def check_interval(info, kind, start, duration, label):
    if start + duration > stream_duration(info, kind) + .045:
        raise ValueError(f"{label} 所需源区间{start:.3f}..{start + duration:.3f}秒超出素材时长")


def fit_text(value, style, field, font_path, max_key="font_size", min_key="min_font_size", width=None):
    from PIL import ImageFont
    maximum, minimum = int(style[max_key]), int(style[min_key])
    available = width or style["width"]
    for size in range(maximum, minimum - 1, -1):
        face = ImageFont.truetype(str(font_path), size)
        if face.getlength(value) <= available:
            return size
    raise ValueError(f"{field} 在最小字号{minimum}px仍超出安全框；请缩短文字或明确拆句")


def prepare(manifest_path, project, force=False):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    pair = resolve_ffmpeg_pair()
    if not pair:
        raise ValueError("未找到项目FFmpeg/ffprobe；不自动下载或安装")
    _, ffprobe = pair
    source = read_json(manifest_path)
    layout = read_json(TEMPLATE / "layout.json")
    duration = number(source.get("duration_seconds"), "duration_seconds", 15)
    if duration > 25:
        raise ValueError("本CLI只允许15至25秒独立开发短样；正式全片需要工作台与统一队列适配")
    fps = layout["canvas"]["fps"]
    if abs(duration * fps - round(duration * fps)) > 1e-6:
        raise ValueError("总时长必须对齐30fps帧时钟")
    font_path = Path(source.get("font_path") or (Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / layout["fonts"]["windows_file"]))
    if not font_path.is_file():
        raise ValueError("未找到微软雅黑粗体字体；先提供font_path并确认匹配layout字体，再做视觉核验")

    props = {"duration_seconds": duration, "media": {}, "scenes": [], "cues": []}
    title_lines = source.get("title_lines")
    if not isinstance(title_lines, list) or not 1 <= len(title_lines) <= layout["title"]["max_lines"]:
        raise ValueError("title_lines 必须是1至2行标题数组")
    props["title_lines"] = [text(line, "title_lines") for line in title_lines]
    props["title_emphasis"] = [text(word, "title_emphasis") for word in source.get("title_emphasis", [])]
    props["brand"] = text(source.get("brand"), "brand")
    props["context_pill"] = text(source.get("context_pill", "视觉结构测试"), "context_pill")
    props["source_pill"] = text(source.get("source_pill"), "source_pill")
    props["footer_note"] = text(source.get("footer_note", "数字人模板7 · 本地结构验证"), "footer_note")
    props["development_label"] = text(source.get("development_label", "结构开发样片 · 引用原片音画"), "development_label")
    tagline = source.get("tagline", [])
    if isinstance(tagline, str):
        tagline = [tagline]
    if not isinstance(tagline, list) or not 1 <= len(tagline) <= layout["tagline"]["max_lines"]:
        raise ValueError("tagline 必须是1至2行副说明数组")
    props["tagline"] = [text(line, "tagline") for line in tagline]
    for line in props["title_lines"]:
        fit_text(line, layout["title"], "标题", font_path)
    for line in props["tagline"]:
        fit_text(line, layout["tagline"], "副说明", font_path)
    for name in ("brand", "context_pill", "source_pill", "footer_note"):
        fit_text(props[name], layout[name], name, font_path, width=layout[name]["width"] - 32)
    label_style = layout["development_label"]
    fit_text(props["development_label"], {**label_style, "min_font_size": label_style["font_size"]}, "开发标识", font_path)

    media = source.get("media") or {}
    source_media, probes = {}, {}
    for name in ("avatar", "avatar_pip", "broll", "audio"):
        raw = media.get(name)
        if not raw:
            if name in {"avatar", "audio"}:
                raise ValueError(f"media.{name} 必须提供本地已完成媒体")
            continue
        if not isinstance(raw, str) or "://" in raw:
            raise ValueError("本地开发短样只接受现有本地文件，不接受URL或供应商任务")
        candidate = Path(raw).expanduser()
        path = (manifest_path.parent / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        if not path.is_file():
            raise ValueError(f"media.{name} 文件不存在")
        fingerprint = digest(path)
        props["media"][name] = name + "-" + fingerprint[:12] + path.suffix.lower()
        probes[name] = probe(path, ffprobe)
        stream_duration(probes[name], "audio" if name == "audio" else "video")
        source_media[name] = {"path": str(path), "sha256": fingerprint, "staged_name": props["media"][name]}
    check_interval(probes["audio"], "audio", 0, duration, "独立音轨")
    if abs(stream_duration(probes["audio"], "audio") - duration) > .1:
        raise ValueError("独立音轨须已按同一时钟裁成短样时长；CLI不会截断讲话或拉伸音频")

    scenes = source.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("scenes 必须完整描述短样全部区间")
    cursor, ids = 0., set()
    for index, scene in enumerate(scenes):
        sid = text(scene.get("id"), f"scenes[{index}].id")
        if sid in ids:
            raise ValueError("scene.id 必须唯一")
        ids.add(sid)
        start = number(scene.get("start"), "scene.start")
        end = number(scene.get("end"), "scene.end")
        if abs(start - cursor) > 1e-6 or end <= start or end > duration + 1e-6:
            raise ValueError("scenes 必须顺序无缝覆盖0至总时长，不能空缺、重叠或越界")
        if any(abs(point * fps - round(point * fps)) > 1e-6 for point in (start, end)):
            raise ValueError("场景边界必须对齐30fps帧时钟")
        mode = scene.get("mode")
        if mode not in {"presenter", "broll"}:
            raise ValueError("scene.mode 只允许presenter或broll")
        fit = scene.get("fit", "contain" if mode == "broll" else "cover")
        if fit not in {"contain", "cover"}:
            raise ValueError("scene.fit 只允许contain或cover，禁止拉伸")
        source_in = number(scene.get("source_in", start if mode == "presenter" else 0), "source_in")
        avatar_in = number(scene.get("avatar_in", source_in if mode == "presenter" else start), "avatar_in")
        pip_in = number(scene.get("pip_in", avatar_in), "pip_in")
        item = {"id": sid, "start": start, "end": end, "mode": mode, "fit": fit,
                "source_in": source_in, "avatar_in": avatar_in, "pip_in": pip_in}
        if mode == "broll":
            if "broll" not in probes:
                raise ValueError("broll场景必须提供media.broll")
            check_interval(probes["broll"], "video", source_in, end - start, sid + "素材")
            check_interval(probes.get("avatar_pip", probes["avatar"]), "video", pip_in, end - start, sid + "圆人物")
        else:
            check_interval(probes["avatar"], "video", avatar_in, end - start, sid + "人物")
        for name, fields in (("summary", ("title",)), ("focus", ("value", "label"))):
            if scene.get(name):
                data = dict(scene[name])
                for field in fields:
                    data[field] = text(data.get(field), f"{name}.{field}")
                for field in (("kicker", "body") if name == "summary" else ()):
                    if data.get(field):
                        data[field] = text(data[field], f"{name}.{field}")
                if name == "focus" and data.get("color", "yellow") not in {"yellow", "red"}:
                    raise ValueError("focus.color只允许yellow或red")
                item[name] = data
        if "summary" in item:
            sty = layout["summary"]
            for field, max_key, min_key in (("title", "title_size", "title_min_size"), ("body", "body_size", "body_min_size")):
                if item["summary"].get(field):
                    fit_text(item["summary"][field], sty, "summary." + field, font_path, max_key, min_key, sty["width"] - 2 * sty["padding"])
        if "focus" in item:
            sty = layout["focus"]
            for field in ("value", "label"):
                fit_text(item["focus"][field], sty, "focus." + field, font_path, field + "_size", field + "_min_size", sty["width"] - 2 * sty["stroke_width"])
        props["scenes"].append(item)
        cursor = end
    if abs(cursor - duration) > 1e-6:
        raise ValueError("最后场景必须到短样总时长")

    previous_end = 0
    for cue in source.get("cues", []):
        start_ms = number(cue["startMs"], "cue.startMs") if "startMs" in cue else number(cue.get("start"), "cue.start") * 1000
        end_ms = number(cue["endMs"], "cue.endMs") if "endMs" in cue else number(cue.get("end"), "cue.end") * 1000
        if end_ms <= start_ms or start_ms < previous_end or end_ms > duration * 1000 + 1:
            raise ValueError("字幕区间必须顺序、无重叠并位于全片时钟内")
        content = text(cue.get("text"), "cue.text")
        fit_text(content, layout["captions"], "字幕", font_path, width=layout["captions"]["width"] - 2 * layout["captions"]["stroke_width"])
        props["cues"].append({"startMs": start_ms, "endMs": end_ms, "text": content,
                              "timestampMs": None, "confidence": None})
        previous_end = end_ms

    source_hashes = {name: digest(TEMPLATE / name) for name in SOURCE_FILES}
    identity = {"template_id": TEMPLATE_ID, "props": props,
                "media_sha256": {name: value["sha256"] for name, value in source_media.items()}, "source_sha256": source_hashes}
    fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    state_path = project / "artifacts" / "sample-state.json"
    old = read_json(state_path) if state_path.is_file() else {}
    if old and old.get("fingerprint") != fingerprint and not force:
        raise ValueError("此项目已有不同冻结输入；使用新项目目录，或明确--force只更新此开发样片")
    project.mkdir(parents=True, exist_ok=True)
    public_dir = project / "public"
    public_dir.mkdir(exist_ok=True)
    for name in SOURCE_FILES:
        shutil.copy2(TEMPLATE / name, project / name)
    for item in source_media.values():
        destination = public_dir / item["staged_name"]
        if not destination.is_file() or digest(destination) != item["sha256"]:
            shutil.copy2(item["path"], destination)
    write_json(project / "artifacts" / "props.json", props)
    composition = {"render_runtime": "remotion", "cuts": [{"id": "complete-sample", "source": props["media"]["avatar"],
                    "in_seconds": 0, "out_seconds": duration}], "audio": {"narration": {"src": props["media"]["audio"]}}}
    write_json(project / "artifacts" / "composition-preflight.json", composition)
    from tools.analysis.composition_validator import CompositionValidator
    preflight = CompositionValidator().execute({"composition_path": str(project / "artifacts" / "composition-preflight.json"), "assets_root": str(public_dir)})
    if not preflight.success or not preflight.data.get("valid"):
        raise ValueError("项目原生composition预检失败：" + str(preflight.error or preflight.data))
    write_json(project / "artifacts" / "composition-preflight-result.json", preflight.data)
    output = project / "renders" / ("template7-sample-" + fingerprint[:12] + ".mp4")
    edit = {"render_runtime": "remotion", "composition_mode": "atelier", "total_duration_seconds": duration,
            "metadata": {"proposal_render_runtime": "remotion", "development_sample": True},
            "bespoke": {"entry": str(project / "index.tsx"), "composition_id": COMPOSITION_ID,
                        "props_path": str(project / "artifacts" / "props.json"), "public_dir": str(public_dir),
                        "art_direction": "用户指定参考复刻：黑色星点双行标题、蓝青分割、中窗素材/独立圆人物、紫黑品牌底、白描黑斜字幕；开发短样只复用原片音画。",
                        "crf": 18, "concurrency": 2}}
    write_json(project / "artifacts" / "edit_decisions.json", edit)
    scene_plan = {"scenes": [{"id": scene["id"], "start_seconds": scene["start"], "end_seconds": scene["end"]} for scene in props["scenes"]]}
    write_json(project / "artifacts" / "scene_plan.json", scene_plan)
    state = {"template_id": TEMPLATE_ID, "fingerprint": fingerprint, "manifest_path": str(manifest_path),
             "manifest_sha256": digest(manifest_path), "project": str(project), "output": str(output),
             "duration_seconds": duration, "source_media": source_media, "source_sha256": source_hashes,
             "font_path": str(font_path.resolve()), "font_sha256": digest(font_path), "cloud_calls": 0, "publication": False,
             "development_sample": True, "production_integration": False,
             "caption_timing": source.get("caption_timing", "manual_reference_clock"), "provenance": source.get("provenance", {}),
             "technical_preflight": "passed", "frame_review": "pending", "listening_review": "pending"}
    if old.get("fingerprint") == fingerprint:
        for key in ("output_sha256", "render_completed", "native_render_completed", "evidence_path",
                    "audio_clock_mux", "audio_clock_audio_sha256"):
            if key in old:
                state[key] = old[key]
    write_json(state_path, state)
    return state, props, edit, pair


def mux_master_audio(state, pair):
    """Replace renderer audio with the same-clock master, keeping video bytes.

    The original output remains readable until FFmpeg has completed the sibling
    temporary MP4. Re-entering this operation never renders video or calls a
    provider; the frozen master identity must still match.
    """
    ffmpeg, _ = pair
    output = Path(state["output"])
    master = state["source_media"]["audio"]
    audio = Path(master["path"])
    if not output.is_file() or not audio.is_file() or digest(audio) != master["sha256"]:
        raise ValueError("主音轨封装需要现有成片及哈希一致的冻结音轨")
    temporary = output.with_name(output.stem + ".master-audio-v1.tmp.mp4")
    run([str(ffmpeg), "-nostdin", "-hide_banner", "-v", "error", "-y", "-i", str(output), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-t", str(state["duration_seconds"]), "-movflags", "+faststart", str(temporary)], timeout=300)
    if not temporary.is_file():
        raise ValueError("主音轨封装未返回临时MP4；保留原成片")
    temporary.replace(output)
    state["audio_clock_mux"] = "master_wav_v1"
    state["audio_clock_audio_sha256"] = master["sha256"]


def render(state, props, edit, pair, concurrency):
    project, output = Path(state["project"]), Path(state["output"])
    cached = ((state.get("render_completed") or state.get("native_render_completed"))
              and output.is_file() and digest(output) == state.get("output_sha256"))
    if cached and state.get("render_completed") and state.get("audio_clock_mux") == "master_wav_v1":
        return {"status": "existing_render_reused", **state}
    edit["bespoke"]["concurrency"] = concurrency
    write_json(project / "artifacts" / "edit_decisions.json", edit)
    if not cached:
        from tools.video.video_compose import VideoCompose
        result = VideoCompose().execute({"operation": "render", "project_dir": str(project),
                                         "output_path": str(output), "edit_decisions": edit})
        write_json(project / "artifacts" / "native-render-result.json", {"success": result.success, "error": result.error, "data": result.data})
        if not result.success or not output.is_file():
            raise ValueError("原生Atelier渲染失败；保留现有产物，从native-render-result.json诊断：" + str(result.error))
        state.update(native_render_completed=True, render_completed=False, output_sha256=digest(output))
        state.pop("audio_clock_mux", None)
        state.pop("audio_clock_audio_sha256", None)
        write_json(project / "artifacts" / "sample-state.json", state)
    if state.get("audio_clock_mux") != "master_wav_v1":
        mux_master_audio(state, pair)
        state.update(native_render_completed=True, render_completed=False, output_sha256=digest(output))
        write_json(project / "artifacts" / "sample-state.json", state)
    ffmpeg, ffprobe = pair
    info = probe(output, ffprobe)
    video = next(stream for stream in info["streams"] if stream.get("codec_type") == "video")
    layout = read_json(TEMPLATE / "layout.json")
    if (video.get("width"), video.get("height")) != (layout["canvas"]["width"], layout["canvas"]["height"]):
        raise ValueError("输出画幅未通过检查")
    if Fraction(video.get("avg_frame_rate", "0/1")) != layout["canvas"]["fps"]:
        raise ValueError("输出帧率未通过检查")
    if abs(stream_duration(info, "video") - state["duration_seconds"]) > .05 or abs(stream_duration(info, "audio") - state["duration_seconds"]) > .1:
        raise ValueError("输出声画时长未通过检查")
    run([str(ffmpeg), "-nostdin", "-v", "error", "-i", str(output), "-f", "null", "-"], timeout=300)
    snapshots = project / "snapshots"
    snapshots.mkdir(exist_ok=True)
    times = sorted({.25, max(0, state["duration_seconds"] - .1), *[(scene["start"] + scene["end"]) / 2 for scene in props["scenes"]]})
    frames = []
    for index, time in enumerate(times):
        path = snapshots / f"review-{index + 1:02d}.jpg"
        run([str(ffmpeg), "-nostdin", "-v", "error", "-y", "-ss", str(time), "-i", str(output), "-frames:v", "1", "-q:v", "2", str(path)])
        frames.append({"time_seconds": time, "path": str(path), "sha256": digest(path)})
    evidence = {"development_sample": True, "template_id": TEMPLATE_ID, "fingerprint": state["fingerprint"],
                "video": str(output), "video_sha256": digest(output), "media_probe": info,
                "full_decode": "passed", "cloud_calls": 0, "provider_jobs": [], "publication": False,
                "technical_validation": "pass", "visual_validation": "pending_actual_frame_view", "continuous_listening": "pending",
                "source_clock": "independent same-clock audio; every video muted; no speech speed change",
                "audio_clock_mux": state["audio_clock_mux"], "audio_clock_audio_sha256": state["audio_clock_audio_sha256"],
                "caption_timing": state["caption_timing"], "frames": frames}
    evidence_path = project / "artifacts" / "sample-evidence.json"
    write_json(evidence_path, evidence)
    state.update(render_completed=True, output_sha256=evidence["video_sha256"], evidence_path=str(evidence_path))
    write_json(project / "artifacts" / "sample-state.json", state)
    return {"status": "rendered_technical_checks_passed", "output": str(output), "evidence": str(evidence_path),
            "cloud_calls": 0, "publication": False, "audio_clock_mux": state["audio_clock_mux"],
            "frame_review": "pending_actual_view", "frames": frames}


def main(argv=None):
    parser = argparse.ArgumentParser(description="数字人模板7：现有媒体15至25秒本地开发短样，默认只准备和预检")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--render", action="store_true", help="通过项目原生VideoCompose Atelier渲染短样")
    parser.add_argument("--force", action="store_true", help="只更新指定开发项目内冻结输入，不影响生产状态")
    parser.add_argument("--concurrency", type=int, default=2, choices=range(1, 9))
    args = parser.parse_args(argv)
    try:
        manifest = args.manifest.expanduser().resolve(strict=True)
        project = private_project(args.project)
        state, props, edit, pair = prepare(manifest, project, args.force)
        result = render(state, props, edit, pair, args.concurrency) if args.render else {
            "status": "prepared", "project": str(project), "output": state["output"], "fingerprint": state["fingerprint"],
            "technical_preflight": "passed", "cloud_calls": 0, "publication": False}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error), "cloud_calls": 0, "publication": False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
