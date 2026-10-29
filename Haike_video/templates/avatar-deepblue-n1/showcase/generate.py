"""Reproduce the distributable N1 silent showcase, using only authored SVGs.

This is an offline development render, not a production-queue submission.
No account, private project, supplier, voice, or cloud API is accessed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent
ROOT = HERE.parents[3]
COMPOSER = ROOT / "Haike_video/remotion-composer"
PUBLIC = ROOT / "prototypes/haike-avatar-generator/public/assets"
WORK = COMPOSER / ".local/n1-public-showcase-v1"
VIDEO = "n1-public-sample-v1.mp4"
MANIFEST = "n1-public-provenance.json"
FRAMES = (("presenter", 2), ("material", 5.5), ("screenshot", 9.5), ("data", 13.5))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(args, timeout=60):
    environment = {key: value for key, value in os.environ.items()
                   if not any(marker in key.upper() for marker in ("API_KEY", "API_SECRET", "ACCESS_TOKEN"))}
    result = subprocess.run([str(value) for value in args], cwd=COMPOSER,
                            env=environment, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout,
                            creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
                            if os.name == "nt" else 0)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-1400:])
    return result.stdout


def tools():
    suffix = ".exe" if os.name == "nt" else ""
    values = []
    for name in ("ffmpeg", "ffprobe"):
        bundled = ROOT / "runtime/ffmpeg" / (name + suffix)
        value = str(bundled) if bundled.is_file() else shutil.which(name)
        if not value:
            raise RuntimeError("Install the local FFmpeg runtime before rendering.")
        values.append(value)
    return values


def verify(video, ffmpeg, ffprobe):
    info = json.loads(run([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", video]))
    stream = next(item for item in info["streams"] if item["codec_type"] == "video")
    assert (stream["width"], stream["height"], stream["avg_frame_rate"], stream["nb_frames"]) == (1080, 1920, "30/1", "450")
    assert abs(float(info["format"]["duration"]) - 15) < .01
    assert not any(item["codec_type"] == "audio" for item in info["streams"])
    run([ffmpeg, "-v", "error", "-xerror", "-i", video, "-f", "null", "-"], timeout=90)
    return {"width": 1080, "height": 1920, "fps": 30, "frames": 450,
            "duration_seconds": 15, "audio_streams": 0, "full_decode": "pass"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true", help="Explicitly run an offline local development render.")
    parser.add_argument("--replace", action="store_true", help="Replace only this recipe's known public preview files.")
    args = parser.parse_args()
    ffmpeg, ffprobe = tools()
    if not args.render:
        manifest = json.loads((PUBLIC / MANIFEST).read_text(encoding="utf-8"))
        for item in [manifest["video"], *manifest["frames"]]:
            assert digest(PUBLIC / item["file"]) == item["sha256"]
        assert digest(TEMPLATE / "layout.json") == manifest["layout_sha256"]
        assert digest(TEMPLATE / "index.tsx") == manifest["implementation_sha256"]
        verify(PUBLIC / VIDEO, ffmpeg, ffprobe)
        print("Public N1 showcase hashes and media verification passed.")
        return
    assert WORK.resolve().is_relative_to((COMPOSER / ".local").resolve())
    WORK.mkdir(parents=True, exist_ok=True)
    public = WORK / "public"
    public.mkdir(exist_ok=True)
    for name in ("material.svg", "source-card.svg"):
        shutil.copy2(HERE / name, public / name)
    for name in ("index.tsx", "layout.json"):
        shutil.copy2(TEMPLATE / name, WORK / name)
    shutil.copy2(HERE / "props.json", WORK / "props.json")
    run([ffmpeg, "-v", "error", "-y", "-i", HERE / "avatar-geometric.svg", "-frames:v", "1", WORK / "avatar.png"])
    run([ffmpeg, "-v", "error", "-y", "-loop", "1", "-framerate", "30", "-i", WORK / "avatar.png",
         "-t", "15", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
         "-threads", "2", "-movflags", "+faststart", public / "avatar-geometric.mp4"])
    node = shutil.which("node")
    cli = COMPOSER / "node_modules/@remotion/cli/remotion-cli.js"
    if not node or not cli.is_file():
        raise RuntimeError("Install the locked Remotion composer dependencies first.")
    raw = WORK / "render-raw.mp4"
    command = [node, cli, "render", WORK / "index.tsx", "HaikeDeepblueN1", raw,
               f"--props={WORK / 'props.json'}", f"--public-dir={public}", "--codec=h264", "--crf=18", "--concurrency=2"]
    output = run(command, timeout=300)
    (WORK / "render.stdout.log").write_text(output, encoding="utf-8")
    # Remotion may mux a silent AAC track for muted Video components. Preserve
    # the rendered image stream and explicitly produce a video-only showcase.
    run([ffmpeg, "-v", "error", "-y", "-i", raw, "-map", "0:v:0", "-c:v", "copy", "-an",
         "-movflags", "+faststart", WORK / VIDEO])
    checks = verify(WORK / VIDEO, ffmpeg, ffprobe)
    for mode, seconds in FRAMES:
        run([ffmpeg, "-v", "error", "-y", "-ss", str(seconds), "-i", WORK / VIDEO,
             "-frames:v", "1", WORK / f"n1-public-{mode}.png"])
    PUBLIC.mkdir(parents=True, exist_ok=True)
    names = [VIDEO, *(f"n1-public-{mode}.png" for mode, _ in FRAMES)]
    for name in names:
        destination = PUBLIC / name
        assert not destination.is_symlink() and destination.resolve().is_relative_to(PUBLIC.resolve())
        if destination.exists() and digest(destination) != digest(WORK / name) and not args.replace:
            raise RuntimeError("A public example already exists; use --replace only after reviewing the new version.")
    for name in names:
        shutil.copy2(WORK / name, PUBLIC / name)
    def identity(path):
        return {"file": path.name, "sha256": digest(path), "bytes": path.stat().st_size}
    manifest = {
        "version": 1, "template_id": "avatar-deepblue-n1-v1", "render_kind": "offline_development_showcase",
        "description": "通用几何人物与源码合成内容的15秒四模式无声版式演示；不是口型、有声同步或新闻事实验收。",
        "private_media_used": False, "cloud_calls": 0, "queue_used": False, "caption_clock": "illustrative_manual",
        "source_notice": "All SVG inputs and text are authored for this project; no personal image, recording or external media is used.",
        "reproduce": "python Haike_video/templates/avatar-deepblue-n1/showcase/generate.py --render",
        "layout_sha256": digest(TEMPLATE / "layout.json"), "implementation_sha256": digest(TEMPLATE / "index.tsx"),
        "inputs": [{"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}
                   for path in (HERE / "avatar-geometric.svg", HERE / "material.svg", HERE / "source-card.svg", HERE / "props.json", HERE / "generate.py")],
        "tools": {"node": run([node, "--version"]).strip(),
                  "remotion": json.loads((COMPOSER / "node_modules/remotion/package.json").read_text())["version"],
                  "ffmpeg": run([ffmpeg, "-version"]).splitlines()[0]},
        "video": identity(PUBLIC / VIDEO), "verification": checks,
        "frames": [{**identity(PUBLIC / f"n1-public-{mode}.png"), "mode": mode, "time_seconds": seconds} for mode, seconds in FRAMES],
        "visual_review": "pending", "platform_review": "pending", "user_review": "pending",
    }
    (PUBLIC / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"video": manifest["video"], "verification": checks, "cloud_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
