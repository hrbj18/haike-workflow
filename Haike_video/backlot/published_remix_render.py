"""Local FFmpeg executor; invoked only by the unified production queue."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from uuid import uuid4

from backlot import published_clip_index as clips
from backlot import published_remix as remix
from lib.ffmpeg_locator import resolve_ffmpeg_pair
from lib.subprocess_window import no_window_kwargs


def _run(argv, *, timeout=900):
    result = subprocess.run(argv, capture_output=True, timeout=timeout, **no_window_kwargs())
    if result.returncode:
        raise clips.ClipIndexError("本地媒体处理失败：" + result.stderr.decode("utf-8", errors="replace")[-600:])
    return result


def inspect(project_dir, signature):
    directory = remix.version_dir(project_dir.name, signature, projects_root=project_dir.parent)
    path = directory / "result.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if result.get("status") == "completed" and (directory / "preview.mp4").is_file():
        return {"status": "completed", "stage": "二剪预览完成，等待人工观看", "result": result}
    return {"status": "queued", "stage": "恢复同一冻结版本的本地渲染", "retryable": True,
            "safe_resume_point": "published_remix"}


def render(project_dir, signature, *, db_path=None):
    # Preflight errors also need a durable, retryable result (e.g. a disconnected source disk).
    try:
        return _render(project_dir, signature, db_path=db_path)
    except Exception as exc:
        project_dir = Path(project_dir)
        directory = remix.version_dir(project_dir.name, signature, projects_root=project_dir.parent)
        remix._atomic(directory / "result.json", {"status": "failed", "error": str(exc)[:800], "updated_at": clips._now()})
        return {"status": "failed", "stage": "二剪检查失败，请修复后重试",
                "error": {"type": type(exc).__name__, "message": str(exc)[:800]},
                "retryable": True, "safe_resume_point": "published_remix"}


def _render(project_dir, signature, *, db_path=None):
    project_dir = Path(project_dir)
    directory = remix.version_dir(project_dir.name, signature, projects_root=project_dir.parent)
    frozen = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(json.dumps(frozen, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if digest != signature or frozen.get("version") != remix.VERSION or frozen.get("project_id") != project_dir.name:
        raise clips.ClipIndexError("冻结剪辑清单不匹配，已停止渲染")
    if frozen.get("profile") != remix.PROFILE:
        raise clips.ClipIndexError("渲染规格已变化，请重新提交新版本")
    previous = inspect(project_dir, signature)
    if previous["status"] == "completed":
        return previous
    sources = {s["video_id"]: clips.media_path(s["video_id"], source_root=Path(frozen["source_root"]), db_path=db_path)
               for s in frozen["segments"]}
    pair = resolve_ffmpeg_pair()
    if not pair:
        raise clips.ClipIndexError("本机缺少 FFmpeg/FFprobe，请检查媒体依赖")
    ffmpeg, ffprobe = pair
    result_path = directory / "result.json"
    remix._atomic(result_path, {"status": "running", "revision": frozen["revision"], "stage": "统一片段规格", "updated_at": clips._now()})
    work = directory / ("work-" + uuid4().hex[:12])
    work.mkdir()
    try:
        parts, timeline, at_frame = [], [], 0
        fps, width, height = (remix.PROFILE[k] for k in ("fps", "width", "height"))
        for n, segment in enumerate(frozen["segments"]):
            frames = segment["frame_count"]
            duration = frames / fps
            path = work / f"part-{n:03d}.mkv"
            argv = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-ss", str(segment["start_seconds"]),
                    "-i", str(sources[segment["video_id"]])]
            if not segment["has_audio"]:
                argv += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
            vf = (f"setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                  f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},"
                  f"tpad=stop_mode=clone:stop_duration=0.1,trim=end_frame={frames},setpts=N/({fps}*TB),format=yuv420p")
            gain = {"original": "1", "lowered": "0.2511886432", "mute": "0"}[segment["audio_mode"]]
            audio_stream = "0:a:0" if segment["has_audio"] else "1:a:0"
            af = (f"[{audio_stream}]asetpts=PTS-STARTPTS,aresample=48000:async=0:first_pts=0,"
                  f"aformat=sample_rates=48000:channel_layouts=stereo,apad,atrim=end_sample={frames * 1600},"
                  f"asetpts=N/SR/TB,volume={gain},afade=t=in:d=0.005,"
                  f"afade=t=out:st={max(0, duration - .005):.6f}:d=0.005[a]")
            argv += ["-filter_complex", f"[0:v:0]{vf}[v];{af}", "-map", "[v]", "-map", "[a]",
                     "-t", f"{duration:.9f}", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                     "-threads", "4", "-c:a", "pcm_s16le", str(path)]
            _run(argv)
            parts.append(path)
            timeline.append({**segment, "timeline_start": at_frame / fps, "timeline_end": (at_frame + frames) / fps})
            at_frame += frames
            remix._atomic(result_path, {"status": "running", "revision": frozen["revision"],
                "stage": f"已处理 {n + 1}/{len(frozen['segments'])} 段", "updated_at": clips._now()})
        # PCM intermediate audio avoids AAC encoder padding accumulating at each cut.
        listing = work / "concat.txt"
        listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
        temporary = work / "preview.mp4"
        expected = at_frame / fps
        _run([ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-f", "concat", "-safe", "1",
              "-i", str(listing), "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-c:a", "aac",
              "-b:a", "192k", "-ar", "48000", "-t", f"{expected:.9f}", "-movflags", "+faststart", str(temporary)])
        probe = clips.probe_media(temporary, ffprobe)
        # Stream duration and frame count are not included by the index's compact probe.
        exact = json.loads(_run([ffprobe, "-v", "error", "-show_entries",
            "stream=codec_type,codec_name,width,height,duration,nb_frames,r_frame_rate,sample_rate,channels,pix_fmt",
            "-of", "json", str(temporary)], timeout=120).stdout)
        video = next(s for s in exact["streams"] if s["codec_type"] == "video")
        audio = next(s for s in exact["streams"] if s["codec_type"] == "audio")
        checks = {"video_codec": video["codec_name"] == "h264", "audio_codec": audio["codec_name"] == "aac",
            "dimensions": (video["width"], video["height"]) == (width, height),
            "frame_count": int(video["nb_frames"]) == at_frame,
            "fps": video["r_frame_rate"] == f"{fps}/1", "pixel_format": video["pix_fmt"] == "yuv420p",
            "audio_format": audio["sample_rate"] == "48000" and audio["channels"] == 2,
            "duration": abs(probe["duration_seconds"] - expected) <= .08,
            "av_duration": abs(float(video["duration"]) - float(audio["duration"])) <= .08}
        if not all(checks.values()):
            raise clips.ClipIndexError("二剪技术检查未通过：" + "、".join(k for k,v in checks.items() if not v))
        _run([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-xerror", "-i", str(temporary), "-f", "null", "-"], timeout=900)
        checks["decode"] = True
        for video_id in sources:
            clips.media_path(video_id, source_root=Path(frozen["source_root"]), db_path=db_path)
        temporary.replace(directory / "preview.mp4")
        result = {"status": "completed", "review_status": "pending_review", "revision": frozen["revision"],
            "signature": signature, "title": frozen["title"], "stage": "二剪预览完成，等待人工观看",
            "duration_seconds": expected, "profile": remix.PROFILE, "timeline": timeline,
            "qa": {"status": "passed", "checks": checks}, "updated_at": clips._now(),
            "output_path": (directory / "preview.mp4").relative_to(project_dir).as_posix()}
        remix._atomic(result_path, result)
        return {"status": "completed", "stage": result["stage"], "result": result}
    except Exception as exc:
        remix._atomic(result_path, {"status": "failed", "revision": frozen["revision"], "error": str(exc)[:800], "updated_at": clips._now()})
        return {"status": "failed", "stage": "二剪渲染失败，可重试同一版本",
                "error": {"type": type(exc).__name__, "message": str(exc)[:800]},
                "retryable": True, "safe_resume_point": "published_remix"}
    finally:
        # Delete only this executor's named temporary files, never recursively.
        for path in work.iterdir():
            if path.is_file():
                path.unlink(missing_ok=True)
        work.rmdir()
