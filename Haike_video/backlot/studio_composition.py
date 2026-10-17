"""Parameterised Remotion adapters; original confirmed template3 TSX remains immutable."""
from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path
from backlot.studio import atomic_private
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkError


def mux_avatar_audio(ffmpeg, raw, audio, output, duration):
    """Materialize finite PCM before AAC; keep the driving waveform immutable."""
    mastered = Path(output).with_name("narration-mastered.wav")
    r = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(audio),
                        "-af", "loudnorm=I=-14:TP=-2:LRA=11",
                        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(mastered)],
                       capture_output=True, timeout=60)
    if r.returncode:
        raise WorkError("本地音量整理失败，原配音已保留", "unavailable")
    r = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(raw),
                        "-i", str(mastered), "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-aac_coder", "fast", "-b:a", "192k", "-t", str(duration),
                        "-movflags", "+faststart", str(output)],
                       capture_output=True, timeout=60)
    if r.returncode:
        raise WorkError("最终音视频封装失败，渲染和整理后的音轨已保留", "unavailable")


def n1_props(folder, draft, duration, cues, storyboard=None):
    """Resolve only draft-owned media into the same renderer used by the sample."""
    from PIL import Image
    from backlot.studio import Studio
    from backlot.studio_n1 import settings, storyboard_settings
    from backlot.studio_network_materials import enabled
    from backlot.work_catalog import sha
    folder = Path(folder)
    studio = Studio(folder.parents[1].parent)
    if enabled(draft) and storyboard is None:
        raise WorkError("联网素材已开启，但尚无已核验分镜；请恢复原任务，未改用纯图文", "unavailable")
    props = storyboard_settings(draft, storyboard, duration, studio) if storyboard is not None else settings(draft, duration, studio)
    sources = []
    for index, scene in enumerate(props["scenes"]):
        if "assetId" not in scene: continue
        source = studio.asset(scene["assetId"], draft["id"])
        name = f"n1-{index}" + source.suffix.lower()
        shutil.copy2(source, folder / "public" / name)
        scene["src"] = name
        scene["mediaKind"] = "video" if source.suffix.lower() in {".mp4", ".mov"} else "image"
        if scene["mediaKind"] == "image":
            with Image.open(source) as image: scene["assetWidth"], scene["assetHeight"] = image.size
        sources.append({"asset_id": scene["assetId"], "sha256": sha(source), "file": name})
    props.update(duration=duration, avatarSrc="avatar.mp4", audioSrc="narration.wav", captions=cues)
    atomic_private(folder / "n1-sources.json", {"sources": sources})
    return props


def compose_avatar(folder, draft, video, audio, duration, cues, storyboard=None):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    from tools.video.video_compose import VideoCompose
    from backlot.studio_network_materials import enabled
    if enabled(draft) and not storyboard:
        raise WorkError("联网素材已开启，但尚无已核验分镜；请恢复原任务，未改用纯图文", "unavailable")
    folder = Path(folder)
    public = folder / "public"; public.mkdir(exist_ok=True)
    ffmpeg, _ = resolve_ffmpeg_pair()
    # Keep the original media, align video tail only; speech is never stretched.
    aligned = public / "avatar.mp4"
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(video), "-vf", "fps=30,tpad=stop_mode=clone:stop_duration=2", "-t", str(duration), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(aligned)], capture_output=True, timeout=180)
    if r.returncode: raise WorkError("数字人素材无法解码，请核对原模型任务")
    info = media_probe(video)
    if not info.get("video") or abs(info["duration"] - duration) > 1: raise WorkError("数字人片段与驱动音频时长不一致，保留原素材待核对")
    shutil.copy2(audio, public / "narration.wav")
    shutil.copy2(Path(__file__).parent / "ui/brand/haike-company-logo.png", public / "haike-logo.png")
    props = {"template": draft["template_id"], "duration": duration, "title": draft["title"], "text": draft["text"], "titleSize": draft["layout"].get("title_size", 60), "accent": draft["layout"].get("accent", "#316dd6"), "captions": cues}
    n1 = draft["template_id"] == "avatar-deepblue-n1-v1"
    if storyboard and not n1:
        from backlot.studio import Studio
        from backlot.work_catalog import sha
        studio = Studio(folder.parents[1].parent)
        scenes = []
        for scene in storyboard["scenes"]:
            source = studio.asset(scene["asset"]["id"], draft["id"])
            if sha(source) != scene["asset_sha256"]: raise WorkError("分镜素材已变化，请恢复原素材")
            offset=scene["asset"].get("offset",0)
            if source.suffix.lower() in {".mp4",".mov"} and offset+scene["end"]-scene["start"]>media_probe(source)["duration"]+.05:
                raise WorkError("分镜视频片段时长不足，请调整素材起点或补充素材；没有循环或拉伸片段")
            name = scene["id"] + source.suffix; shutil.copy2(source, public / name)
            scenes.append({"start": scene["start"], "end": scene["end"], "text": scene["text"], "label": scene["label"], "src": name,
                           "kind": "video" if source.suffix.lower() in {".mp4", ".mov"} else "image", "offset":offset,"generated": scene["asset"].get("provenance", {}).get("generated", False)})
        props["scenes"] = scenes
    if n1:
        props = n1_props(folder, draft, duration, cues, storyboard)
    atomic_private(folder / "props.json", props)
    template_dir = Path(__file__).resolve().parents[1] / "templates" / ("avatar-deepblue-n1" if n1 else "studio-avatar-v1")
    source = template_dir / "index.tsx"
    shutil.copy2(source, folder / "index.tsx")
    if n1: shutil.copy2(template_dir / "layout.json", folder / "layout.json")
    direction = ("# 深蓝视窗 N1\n适配器avatar-deepblue-n1-v1；layout.json是几何和动效参数真值。主持人、素材、截图和纵向数据四种主窗共用深蓝外壳；人物主窗与圆框互斥，同源模糊延展。截图完整contain，红线绑定原图坐标，字幕静态重点黄字。所有视觉源静音，主音轨独立且不拉伸；留白时间回到主持人，不循环素材。标题/来源/品牌/场景来自本期输入，换人换内容后需观看审核，平台真实视口未自动验收。\n" if n1 else
                 "# 海客数字人口播\n海客科技统一品牌。选择模板决定画幅和人物位置；标题、文案、字号和强调色来自本期输入。模板3保留白卡与章节式讲解视觉，原v001确认基准不变。本适配器版本studio-avatar-v1，复用已有付费人物和声音。句级字幕需人审，素材范围与真实平台遮挡待用户观看。\n")
    (folder / "art-direction.md").write_text(direction, encoding="utf-8")
    raw = folder / "avatar-render.mp4"
    edits = {"render_runtime": "remotion", "composition_mode": "atelier", "renderer_family": "bespoke", "bespoke": {"entry": str(folder / "index.tsx"), "composition_id": "HaikeDeepblueN1" if n1 else "HaikeStudioAvatar", "props_path": str(folder / "props.json"), "public_dir": str(public), "crf": 18, "concurrency": 2}, "timeline": {"duration_seconds": duration}}
    result = VideoCompose().execute({"operation": "render", "output_path": str(raw), "edit_decisions": edits, "asset_manifest": {"assets": []}, "script_text": draft["text"]})
    if not result.success: raise WorkError("本地模板合成未通过，请检查渲染依赖；数字人与音频已保留", "unavailable")
    frames = round(duration * 30)
    output = folder / "avatar-preview.mp4"
    # Align the AAC container tail to the same final frame clock as the image.
    mux_avatar_audio(ffmpeg, raw, audio, output, frames / 30)
    info = media_probe(output)
    expected_height = 1440 if draft["template_id"].startswith("avatar-template3") else 1920
    decode = subprocess.run([ffmpeg, "-v", "error", "-i", str(output), "-f", "null", "-"], capture_output=True, timeout=180)
    if decode.returncode or not info.get("audio") or info["video"]["width"] != 1080 or info["video"]["height"] != expected_height or abs(info["duration"] - frames/30) > .1:
        raise WorkError("成片技术校验未通过，产物保留待核对", "unavailable")
    atomic_private(folder / "render-result.json", {"template_adapter": "avatar-deepblue-n1-v1" if n1 else "studio-avatar-v1", "media": info, "native_render": str(raw), "technical_decode": "passed", "human_review": "pending"})
    return output
