"""Deterministic commentary executor. Called by the unified production queue only."""
from __future__ import annotations

import math
import os
from pathlib import Path
from uuid import uuid4

from backlot import material_commentary as workflow
from backlot import commentary_library_bridge as bridge
from backlot import commentary_captions as captions
from backlot import commentary_presenter as presenter
from backlot.commentary_common import (
    CommentaryError, FPS, RATE, SAMPLES_PER_FRAME, VERSION, atomic, crop_filter,
    digest, file_sha256, media_tools, probe, read_json, run, verified,
)

RENDER_VERSION = 4


def inspect(project_dir, signature):
    project_dir = Path(project_dir)
    directory = workflow.version_dir(project_dir.name, signature, projects_root=project_dir.parent)
    path = directory / "result.json"
    if path.is_file():
        result = read_json(path)
        if result.get("status") == "completed":
            try:
                for name, sha in result["files"].items(): verified(directory / name, sha)
                return {"status": "completed", "stage": "素材解说已生成，等待人工审核", "result": result}
            except (ValueError, KeyError):
                pass
    return {"status": "queued", "stage": "从冻结清单和已完成段落恢复", "retryable": True,
            "safe_resume_point": "material_commentary"}


def _timestamp(seconds, *, ass=False):
    scale = 100 if ass else 1000
    units = round(seconds * scale)
    secs, fraction = divmod(units, scale)
    mins, secs = divmod(secs, 60)
    hours, mins = divmod(mins, 60)
    return (f"{hours}:{mins:02}:{secs:02}.{fraction:02}" if ass else f"{hours:02}:{mins:02}:{secs:02},{fraction:03}")


def _ass(path, segment, profile, font_path, style=None):
    width, height = profile["width"], profile["height"]
    size = style["font_size"] if style else (36 if height >= width else 32)
    font = captions.validate_layout(segment, profile, font_path, style)
    family = font.getname()[0]
    top = segment["subtitle_position"] == "top"
    x, y = captions.anchor(segment, profile)
    primary = captions.ass_color(style["text_color"]) if style else "&H00FFFFFF"
    outline = style["outline_size"] if style else 2
    shadow = style["shadow"] if style else 0
    outline_color = "&H00000000" if style else "&H00101820"
    header = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{family},{size},{primary},&H00FFFFFF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,40,40,40,1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lines = []
    for cue in segment.get("render_cues", segment["cues"]):
        if "subtitle_layout" in cue:
            x,y=captions.anchor({**segment,"subtitle_layout":cue["subtitle_layout"]},profile)
        value = captions.ass_text(cue["text"], style)
        lines.append(f"Dialogue: 0,{_timestamp(cue['start'], ass=True)},{_timestamp(cue['end'], ass=True)},Default,,0,0,0,,"
                     + "{\\an2\\pos(" + f"{x},{y}" + ")}" + value + "\n")
    path.write_text(header + "".join(lines), encoding="utf-8-sig")


def _concat(ffmpeg, paths, listing, output):
    # Only generated ASCII basenames enter the concat grammar.
    listing.write_text("".join(f"file '{p.name}'\n" for p in paths), encoding="utf-8")
    run([ffmpeg, "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "1", "-i", listing,
         "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", output])


def _segment(project, segment, frozen, font_path):
    visual = [{"sha256": frozen["sources"][shot["media_id"]]["sha256"],
               **{key: shot[key] for key in ("start", "end", "frames", "crop")}} for shot in segment["shots"]]
    content = {"renderer": RENDER_VERSION, "profile": frozen["profile"], "visual": visual,
               "audio_sha256": (segment["audio"] or {}).get("sha256"),
               **{key: segment[key] for key in ("mode", "source_gain_db", "cues", "subtitle_position", "frames")},
               "font_sha256": file_sha256(font_path)}
    content["independent_source_audio"] = "source_audio" in segment
    content["narration_window"] = {key: (segment["audio"] or {}).get(key) for key in ("playback_start_sample", "playback_samples")}
    if segment["cues"] and "subtitle_style" in frozen:
        content["subtitle_style"] = frozen["subtitle_style"]
    if "presenter" in segment:
        content["presenter"] = segment["presenter"]
    if segment["cues"] and "subtitle_layout" in segment:
        content["subtitle_layout"] = segment["subtitle_layout"]
    if "layout_plan" in segment:
        content["layout_plan"] = segment["layout_plan"]
        content["render_cues"] = segment["render_cues"]
    key = digest(content)
    directory = project / "artifacts/commentary/cache" / key[:24]
    directory.mkdir(parents=True, exist_ok=True)
    output, receipt = directory / "segment.mkv", directory / "receipt.json"
    if receipt.is_file():
        try:
            saved = read_json(receipt)
            if saved.get("key") == key:
                verified(output, saved["sha256"])
                return output, {"segment_id": segment["id"], "key": key, "hit": True, "sha256": saved["sha256"]}
        except (ValueError, KeyError): pass
    ffmpeg, _ = media_tools()
    work = project / "renders" / ("commentary-" + uuid4().hex[:8]); work.mkdir()
    width, height = frozen["profile"]["width"], frozen["profile"]["height"]
    parts = []
    for n, shot in enumerate(segment["shots"]):
        source = frozen["sources"][shot["media_id"]]
        frames, duration = shot["frames"], shot["frames"] / FPS
        part = work / f"shot-{n:03d}.mkv"
        args = [ffmpeg, "-v", "error", "-nostdin", "-y", "-ss", shot["start"], "-i", source["path"]]
        keep = source["has_audio"] and segment["mode"] != "narration" and "source_audio" not in segment
        if not keep: args += ["-f", "lavfi", "-i", f"anullsrc=r={RATE}:cl=stereo"]
        vf = (f"{crop_filter(shot['crop'])},setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
              f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS},trim=end_frame={frames},setpts=N/({FPS}*TB),format=yuv420p")
        # Input seeking rebases BOTH streams to the same cut. Keep the source audio
        # offset here; independently zeroing its PTS moves delayed dialogue early.
        af = (f"[{'0' if keep else '1'}:a:0]aresample={RATE}:async=0:first_pts=0,"
              f"aformat=sample_rates={RATE}:channel_layouts=stereo,apad,atrim=end_sample={frames * SAMPLES_PER_FRAME},"
              f"asetpts=N/SR/TB,volume={segment['source_gain_db'] if keep else 0}dB,afade=t=in:d=0.005,"
              f"afade=t=out:st={max(0,duration-.005):.9f}:d=0.005[a]")
        run(args + ["-filter_complex", f"[0:v:0]{vf}[v];{af}", "-map", "[v]", "-map", "[a]", "-t", f"{duration:.9f}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-threads", "4", "-c:a", "pcm_s16le", part])
        parts.append(part)
    assembled = work / "assembled.mkv"
    _concat(ffmpeg, parts, work / "concat.txt", assembled)
    if segment["audio"]:
        narrated = work / "narrated.mkv"
        samples = segment["frames"] * SAMPLES_PER_FRAME
        first = segment["audio"].get("playback_start_sample", 0)
        length = segment["audio"].get("playback_samples", segment["audio"]["samples"])
        graph = (f"[1:a]atrim=start_sample={first}:end_sample={first+length},asetpts=N/SR/TB,apad,atrim=end_sample={samples},asetpts=N/SR/TB[n];"
                 "[0:a][n]amix=inputs=2:duration=first:normalize=0[a]")
        run([ffmpeg, "-v", "error", "-nostdin", "-y", "-i", assembled, "-i", segment["audio"]["path"],
             "-filter_complex", graph, "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "pcm_s16le", narrated])
        assembled = narrated
    if "presenter" in segment:
        layer = segment["presenter"]
        presented = work / "presented.mkv"
        run([ffmpeg, "-v", "error", "-nostdin", "-y", "-i", assembled, "-i", layer["asset"]["path"],
             "-filter_complex", presenter.overlay_filter(layer,segment.get("layout_plan",{}).get("shots")), "-map", "[v]", "-map", "0:a:0",
             "-frames:v", segment["frames"], "-c:v", "libx264", "-preset", "fast", "-crf", "20",
             "-threads", "4", "-c:a", "copy", presented])
        assembled = presented
    if segment["cues"]:
        import shutil
        shutil.copyfile(font_path, work / ("caption-font" + font_path.suffix))
        _ass(work / "subtitles.ass", segment, frozen["profile"], font_path, frozen.get("subtitle_style"))
        subtitled = work / "subtitled.mkv"
        # cwd + controlled relative filename avoids quoting Windows/user paths in libavfilter.
        run([ffmpeg, "-v", "error", "-nostdin", "-y", "-i", assembled, "-vf", "ass=subtitles.ass:fontsdir=.",
             "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-threads", "4", "-c:a", "copy", subtitled], cwd=work)
        assembled = subtitled
    assembled.replace(output)
    sha = file_sha256(output)
    atomic(receipt, {"key": key, "sha256": sha})
    # Keep failed work for recovery; successful intermediates need no recursive deletion.
    for path in work.iterdir():
        if path.is_file(): path.unlink()
    work.rmdir()
    return output, {"segment_id": segment["id"], "key": key, "hit": False, "sha256": sha}


def render(project_dir, signature):
    project = Path(project_dir)
    directory = workflow.version_dir(project.name, signature, projects_root=project.parent)
    try:
        return _render(project, signature, directory)
    except Exception as exc:
        message = str(exc)[:800]
        atomic(directory / "result.json", {"status": "failed", "signature": signature, "error": message})
        return {"status": "failed", "stage": "素材解说未完成，请修复后重试同一版本",
                "error": {"type": type(exc).__name__, "message": message},
                "retryable": True, "safe_resume_point": "material_commentary"}


def _source_audio(ffmpeg, master, frozen, work):
    clips = [clip for segment in frozen["segments"] for clip in segment.get("source_audio", [])]
    if not clips: return master
    args = [ffmpeg, "-v", "error", "-nostdin", "-y", "-i", master]
    filters, labels = [], ["[0:a]"]
    for i, clip in enumerate(clips, 1):
        duration = clip["end"] - clip["start"]
        args += ["-ss", clip["start"], "-t", duration, "-i", frozen["sources"][clip["media_id"]]["path"]]
        label = f"bed{i}"
        filters.append(f"[{i}:a]aresample={RATE}:async=0:first_pts=0,aformat=channel_layouts=stereo,"
            f"apad,atrim=end_sample={round(duration*RATE)},asetpts=N/SR/TB,volume={clip['gain_db']}dB,"
            f"afade=t=in:d={clip['fade_in']},afade=t=out:st={duration-clip['fade_out']}:d={clip['fade_out']},"
            f"adelay={round(clip['timeline_start']*RATE)}S:all=1[{label}]")
        labels.append(f"[{label}]")
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=first:normalize=0[a]")
    output = work / "source-audio.mkv"
    run(args + ["-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[a]",
        "-c:v", "copy", "-c:a", "pcm_s16le", "-t", frozen["duration"], output])
    return output


def _render(project, signature, directory):
    frozen = read_json(directory / "request.json")
    if digest(frozen) != signature or frozen.get("version") != VERSION or frozen.get("project_id") != project.name:
        raise CommentaryError("冻结清单已变化，拒绝使用不匹配版本")
    previous = inspect(project, signature)
    if previous["status"] == "completed": return previous
    # Verify all inputs even when every segment can be served from cache.
    for source in frozen["sources"].values():
        source["path"] = str(bridge.resolve_source(source["media_id"], source["sha256"]))
    for segment in frozen["segments"]:
        if segment["audio"]: verified(segment["audio"]["path"], segment["audio"]["sha256"])
        if "presenter" in segment:
            verified(segment["presenter"]["asset"]["path"], segment["presenter"]["asset"]["sha256"])
    if frozen["music"]: verified(frozen["music"]["audio"]["path"], frozen["music"]["audio"]["sha256"])
    font_path = verified(frozen["font"]["path"], frozen["font"]["sha256"])
    outputs, cache = [], []
    atomic(directory / "result.json", {"status": "running", "signature": signature, "stage": "逐段编排"})
    work = project / "renders" / ("commentary-" + uuid4().hex[:8]); work.mkdir()
    for n, segment in enumerate(frozen["segments"]):
        path, receipt = _segment(project, segment, frozen, font_path)
        # Hard links avoid copying large caches; fall back for cross-device filesystems.
        local = work / f"segment-{n:03d}.mkv"
        try: os.link(path, local)
        except OSError:
            import shutil
            shutil.copyfile(path, local)
        outputs.append(local); cache.append(receipt)
        atomic(directory / "result.json", {"status": "running", "signature": signature,
               "stage": f"已处理 {n+1}/{len(frozen['segments'])} 段", "cache": cache})
    ffmpeg, _ = media_tools()
    master = work / "master.mkv"
    _concat(ffmpeg, outputs, work / "concat.txt", master)
    master = _source_audio(ffmpeg, master, frozen, work)
    temporary = work / "preview.mp4"
    args = [ffmpeg, "-v", "error", "-nostdin", "-y", "-i", master]
    music = frozen["music"]
    if music:
        args += ["-stream_loop", "-1", "-i", music["audio"]["path"]]
        graph = (f"[1:a]volume={music['gain_db']}dB,atrim=duration={frozen['duration']},"
                 f"afade=t=out:st={max(0,frozen['duration']-1)}:d=1[m];"
                 "[0:a]asplit=2[voice][key];[m][key]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=250[duck];"
                 "[voice][duck]amix=inputs=2:duration=first:normalize=0[a]")
        args += ["-filter_complex", graph, "-map", "0:v:0", "-map", "[a]"]
    else: args += ["-map", "0:v:0", "-map", "0:a:0"]
    run(args + ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", RATE,
                "-t", f"{frozen['duration']:.9f}", "-movflags", "+faststart", temporary])
    # Reuse the project's established normalization + final AAC acceptance gate.
    from backlot.workbench import _normalize_video_loudness
    loudness = _normalize_video_loudness(project, temporary, target_lufs=frozen["target_lufs"])
    info = probe(temporary)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
    checks = {"frames": int(video["nb_frames"]) == frozen["frames"], "fps": video["r_frame_rate"] == f"{FPS}/1",
        "dimensions": (video["width"],video["height"]) == (frozen["profile"]["width"],frozen["profile"]["height"]),
        "codecs": video["codec_name"] == "h264" and audio["codec_name"] == "aac", "pixel_format": video["pix_fmt"] == "yuv420p",
        "audio_format": audio["sample_rate"] == str(RATE) and audio["channels"] == 2,
        "duration": abs(float(video["duration"]) - frozen["duration"]) <= .08,
        "av_sync": abs(float(audio["duration"]) - float(video["duration"])) <= .08}
    decoded = run([ffmpeg, "-v", "error", "-xerror", "-i", temporary, "-f", "null", "-"])
    checks["decode"] = not decoded.stderr.strip()
    if not all(checks.values()): raise CommentaryError("成片技术检查未通过：" + "、".join(k for k,v in checks.items() if not v))
    cues = [{**c, "start": c["start"] + s["start_frame"] / FPS, "end": c["end"] + s["start_frame"] / FPS}
            for s in frozen["segments"] for c in s["cues"]]
    srt = "\n".join(f"{n}\n{_timestamp(c['start'])} --> {_timestamp(c['end'])}\n{captions.display_text(c['text'], frozen.get('subtitle_style'))}\n" for n,c in enumerate(cues,1))
    (directory / "subtitles.srt").write_text(srt, encoding="utf-8-sig")
    temporary.replace(directory / "preview.mp4")
    result = {"status": "completed", "review_status": "pending_review", "signature": signature,
        "revision": frozen["revision"], "duration": frozen["duration"], "frames": frozen["frames"], "cache": cache,
        "qa": {"checks": checks, "loudness": loudness, "status": "passed"}, "warnings": frozen["warnings"],
        "output_path": (directory / "preview.mp4").relative_to(project).as_posix(),
        "files": {name: file_sha256(directory / name) for name in ("preview.mp4", "subtitles.srt")}}
    if any('layout_plan' in s for s in frozen['segments']):
        result['layouts']=[{'segment_id':s['id'],**s['layout_plan']} for s in frozen['segments'] if 'layout_plan' in s]
    atomic(directory / "result.json", result)
    for path in work.iterdir():
        if path.is_file(): path.unlink()
    work.rmdir()
    return {"status": "completed", "stage": "素材解说已生成，等待人工审核", "result": result}
