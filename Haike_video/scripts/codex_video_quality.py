"""Local media evidence for a Codex batch; never generates or publishes media."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot.studio import atomic_private
from lib.ffmpeg_locator import resolve_ffmpeg_pair


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def platform_preview(frames, output):
    """Conservative UI-zone simulation; never claims an actual platform capture."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 30)
    views = []
    for entry in (frames[1], frames[4], frames[7]):
        with Image.open(entry["path"]) as source:
            picture = source.convert("RGBA")
        picture.thumbnail((1080, 1920))
        canvas = Image.new("RGBA", (1080, 1920), "black")
        canvas.alpha_composite(picture, ((1080-picture.width)//2, (1920-picture.height)//2))
        ui = Image.new("RGBA", canvas.size)
        draw = ImageDraw.Draw(ui)
        for rect in ((0,0,1080,160), (930,800,1080,1540), (0,1580,1080,1920)):
            draw.rectangle(rect, fill=(15,15,15,150), outline=(255,110,65,220), width=4)
        draw.text((35,40), "模拟顶部导航 / 搜索", font=font, fill="white")
        for y, label in ((880,"赞"),(1040,"评"),(1200,"藏"),(1360,"分享")):
            draw.text((945,y), label, font=font, fill="white")
        draw.text((35,1620), "模拟作者 / 简介 / 话题", font=font, fill="white")
        draw.text((35,1825), "仅检查遮挡；不是平台真机截图", font=font, fill="white")
        canvas = Image.alpha_composite(canvas, ui).convert("RGB")
        canvas.thumbnail((360,640))
        views.append(canvas)
    result = Image.new("RGB", (1080,640), "black")
    for index, view in enumerate(views):
        result.paste(view,(index*360,0))
    path = output / "platform-ui-simulation.jpg"
    result.save(path, quality=92)
    return str(path)


def inspect(project, video, template, audio=None):
    project, video = Path(project).resolve(), Path(video).resolve()
    if not video.is_relative_to(project) or not video.is_file():
        raise ValueError("成片必须是本项目内已有文件")
    output = project / "artifacts/automation/quality" / video.parent.name
    output.mkdir(parents=True, exist_ok=True)
    ffmpeg, ffprobe = resolve_ffmpeg_pair()
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "video_path": str(video),
              "video_sha256": sha(video), "checks": {}, "frames": [],
              "visual_review": "pending", "platform_ui_review": "pending"}
    report["video"] = {"path": str(video), "sha256_before": report["video_sha256"]}

    def run(arguments, timeout=120):
        result = subprocess.run([str(a) for a in arguments], capture_output=True, timeout=timeout)
        if result.returncode:
            raise ValueError("本地媒体检查失败：" + result.stderr.decode("utf-8", "replace")[-1600:])
        return result

    probe = json.loads(run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", video]).stdout)
    atomic_private(output / "ffprobe.json", probe)
    videos = [s for s in probe["streams"] if s["codec_type"] == "video"]
    audios = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    stream = videos[0] if videos else {}
    duration = float(probe["format"]["duration"])
    height = 1440 if template.startswith("avatar-template3") else 1920
    checks = report["checks"]
    checks["one_video_and_audio"] = len(videos) == 1 and len(audios) == 1
    checks["template_dimensions"] = (stream.get("width"), stream.get("height")) == (1080, height)
    checks["fps_30"] = abs(float(Fraction(stream.get("avg_frame_rate", "0/1"))) - 30) < .001
    checks["positive_duration"] = 0 < duration <= 120
    run([ffmpeg, "-v", "error", "-xerror", "-i", video, "-f", "null", "-"])
    checks["full_decode"] = True
    if audio:
        audio = Path(audio).resolve()
        if not audio.is_relative_to(project):
            raise ValueError("驱动音轨必须属于本项目")
        audio_info = json.loads(run([ffprobe, "-v", "error", "-show_format", "-of", "json", audio]).stdout)
        report["audio_sha256"] = sha(audio)
        report["audio_duration_seconds"] = float(audio_info["format"]["duration"])
        checks["audio_master_clock"] = abs(duration - report["audio_duration_seconds"]) < .12
    measurement = run([ffmpeg, "-hide_banner", "-i", video, "-vn", "-af",
                       "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    chunks = re.findall(r'\{\s*"input_i"\s*:.*?\}', measurement.stderr.decode("utf-8", "replace"), re.S)
    metrics = json.loads(chunks[-1]) if chunks else {}
    report["loudness"] = metrics
    integrated = float(metrics.get("input_i", "-inf"))
    checks["non_silent_audio"] = -45 < integrated < 0
    checks["true_peak_margin"] = float(metrics.get("input_tp", "inf")) <= -1
    report["media"] = {"duration_seconds": duration, "width": stream.get("width"), "height": stream.get("height"), "fps": 30}
    times = [min(duration - .1, max(.1, duration * i / 8)) for i in range(9)]
    for index, seconds in enumerate(times):
        frame = output / f"frame-{index:02d}.jpg"
        run([ffmpeg, "-v", "error", "-y", "-ss", seconds, "-i", video, "-frames:v", "1", "-q:v", "2", frame])
        report["frames"].append({"seconds": seconds, "path": str(frame), "sha256": sha(frame)})
    sheet = output / "contact-sheet.jpg"
    run([ffmpeg, "-v", "error", "-y", "-framerate", "1", "-i", output / "frame-%02d.jpg",
         "-vf", f"scale=360:{height // 3},tile=3x3", "-frames:v", "1", "-q:v", "2", sheet])
    report["contact_sheet"] = str(sheet)
    report["platform_ui_simulation"] = platform_preview(report["frames"], output)
    cover = project / "artifacts/publishing" / f"{video.parent.name}-cover.jpg"
    cover.parent.mkdir(parents=True, exist_ok=True)
    crop = "crop=1080:1440:0:120," if height == 1920 else ""
    run([ffmpeg, "-v", "error", "-y", "-ss", min(.8, duration / 2), "-i", video,
         "-frames:v", "1", "-vf", crop + "scale=720:960:flags=lanczos,setsar=1", "-q:v", "2", cover])
    report.update(cover_path=str(cover), cover_sha256=sha(cover), cover_origin="approved_video_frame")
    checks["video_unchanged"] = report["video_sha256"] == sha(video)
    report["video"]["sha256_after"] = sha(video)
    report["technical_checks_passed"] = all(checks.values())
    report["status"] = "technical_checks_passed" if report["technical_checks_passed"] else "needs_review"
    report["quality_report"] = str(output / "quality.json")
    atomic_private(report["quality_report"], report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--template", required=True)
    parser.add_argument("--audio", type=Path)
    args = parser.parse_args()
    result = inspect(args.project, args.video, args.template, args.audio)
    print(json.dumps({k: result[k] for k in ("status", "video_sha256", "media", "quality_report", "contact_sheet", "cover_path")}, ensure_ascii=False))
    return 0 if result["technical_checks_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
