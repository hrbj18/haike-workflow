"""Parameterised native nine-second graphic template. No cloud calls."""
from __future__ import annotations

import json
import hashlib
import os
import subprocess
from pathlib import Path

from backlot.studio import Studio, atomic_private
from backlot.work_catalog import WorkError


def media_probe(path):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    _, probe = resolve_ffmpeg_pair()
    result = subprocess.run([probe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture_output=True, timeout=30)
    try:
        value = json.loads(result.stdout)
        if result.returncode: raise ValueError()
        return {"duration": float(value["format"]["duration"]), "format": value["format"],
                "video": next((s for s in value["streams"] if s["codec_type"] == "video"), None),
                "audio": next((s for s in value["streams"] if s["codec_type"] == "audio"), None)}
    except Exception: raise WorkError("文件无法解码为有效媒体") from None


def template_runtime():
    import importlib.util
    root = Path(__file__).resolve().parents[1]
    candidates = [os.environ.get("TEMPLATE_VIDEO_FONT"), "C:/Windows/Fonts/msyhbd.ttc", "/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
    font = next((f for f in candidates if f and Path(f).is_file()), None)
    if not font: raise WorkError("缺少中文字体，请配置TEMPLATE_VIDEO_FONT")
    os.environ["TEMPLATE_VIDEO_FONT"] = font
    file = root / "scripts/template_video/build_923.py"
    spec = importlib.util.spec_from_file_location("studio_native_graphic", file)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module, font


def draw_plates(folder, draft):
    from PIL import ImageFont, ImageColor, Image, ImageDraw
    module, font = template_runtime()
    layout = draft["layout"]; inputs = draft["input"]
    titles = inputs.get("headlines", [])
    details = inputs.get("details", [])
    if not isinstance(titles, list) or len(titles) != 3 or not isinstance(details, list) or len(details) != 3:
        raise WorkError("图文模板需要三行标题和三段详情")
    if any(not isinstance(t, str) or not t.strip() for t in titles): raise WorkError("请填写三行标题")
    if any(not isinstance(lines, list) or not 1 <= len(lines) <= 3 or any(not isinstance(t, str) or not t.strip() for t in lines) for lines in details):
        raise WorkError("每段详情需要1至3行文字")
    conclusion = str(inputs.get("conclusion") or "").strip()
    if not conclusion: raise WorkError("请填写结论条")
    module.F_TOP = ImageFont.truetype(font, layout.get("title_size", 80))
    module.F_DET = ImageFont.truetype(font, layout.get("detail_size", 52))
    module.YELLOW = ImageColor.getrgb(layout.get("accent", "#ffcd3c")) + (255,)
    module.PLATE_COLOR = ImageColor.getrgb(layout.get("background", "#050c16")) + (255,)
    draw = ImageDraw.Draw(Image.new("RGB", (1080, 1920)))
    for text, face, width in [(t, module.F_TOP, 920) for t in titles] + [(conclusion, module.F_BAR, 900)] + [(t, module.F_DET, 900) for lines in details for t in lines]:
        if draw.textbbox((0, 0), text, font=face)[2] > width: raise WorkError("文案超过模板可见宽度，请缩短文字或降低字号")
    folder.mkdir(parents=True, exist_ok=True)
    top = folder / "top.png"
    module.make_top(str(top), [(t, module.YELLOW if i == 0 else module.WHITE, (0, 0, 0, 255), 2) for i, t in enumerate(titles)], conclusion)
    plates = []
    for i, lines in enumerate(details):
        p = folder / f"detail-{i}.png"
        module.make_detail(str(p), [(t, module.YELLOW if j == 0 else module.WHITE) for j, t in enumerate(lines)])
        plates.append(p)
    return top, plates


def preview_graphic(output):
    """Render the actual template plates to a sample cover, not a fake UI image."""
    from PIL import Image
    sample = {"layout": {"title_size": 80, "detail_size": 52, "accent": "#ffcd3c", "background": "#050c16"},
              "input": {"headlines": ["海客科技", "让创作更简单", "图文视频工作流"], "conclusion": "三个画面 · 一个观点", "details": [["选择模板", "准备文字与素材", "按三景组织内容"]] * 3}}
    output = Path(output)
    top, details = draw_plates(output.parent / ".graphic-preview", sample)
    canvas = Image.new("RGBA", (1080, 1920), "#202c3e")
    canvas.alpha_composite(Image.open(top)); canvas.alpha_composite(Image.open(details[0]))
    canvas.convert("RGB").save(output)


def validate_graphic(studio, draft):
    if draft["template_id"] != "graphic-news-v2": raise WorkError("当前渲染器只支持资讯三景模板")
    materials = draft["input"].get("materials", [])
    if not isinstance(materials, list) or len(materials) != 3: raise WorkError("请为三景分别选择图片或视频素材")
    for item in materials:
        path = studio.asset(item.get("id"), draft["id"])
        if path.suffix.lower() in {".mp4", ".mov"} and media_probe(path)["duration"] < 3:
            raise WorkError("每段视频素材至少需要3秒")
    # Text width and actual font are preflighted before queue submission.
    draw_plates(studio.private / "studio-preflight" / draft["id"], draft)


def run_graphic(project_dir, request):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    project_dir = Path(project_dir)
    studio = Studio(project_dir.parent)
    draft = request["draft"]
    validate_graphic(studio, draft)
    output_dir = project_dir / "renders" / request["render_id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    top, details = draw_plates(output_dir, draft)
    ffmpeg, _ = resolve_ffmpeg_pair()
    parts = []
    sources = []
    for i, material in enumerate(draft["input"]["materials"]):
        path = studio.asset(material["id"], draft["id"])
        sources.append({"id": material["id"], "role": f"scene-{i + 1}", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        part = output_dir / f"scene-{i}.mp4"
        args = [ffmpeg, "-y", "-v", "error"]
        if path.suffix.lower() in {".png", ".jpg", ".jpeg"}: args += ["-loop", "1"]
        args += ["-i", str(path), "-i", str(top), "-i", str(details[i]), "-filter_complex",
                 "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[bg];[bg][1:v]overlay=0:0[a];[a][2:v]overlay=0:0[v]",
                 "-map", "[v]", "-t", "3", "-an", "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", str(part)]
        r = subprocess.run(args, capture_output=True, timeout=180)
        if r.returncode: raise WorkError("图文场景合成失败，已完成素材已保留")
        parts.append(part)
    listing = output_dir / "concat.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    output = output_dir / "graphic-preview.mp4"
    args = [ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing)]
    bgm = draft["input"].get("bgm")
    if bgm:
        music = studio.asset(bgm["id"], draft["id"])
        sources.append({"id": bgm["id"], "role": "music", "sha256": hashlib.sha256(music.read_bytes()).hexdigest()})
        # Leave headroom for AAC reconstruction peaks; verify the encoded file.
        args += ["-stream_loop", "-1", "-i", str(studio.asset(bgm["id"], draft["id"])), "-af", "atrim=0:9,afade=t=out:st=7.8:d=1.2,loudnorm=I=-11:TP=-2.5:LRA=11"]
    else: args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    args += ["-map", "0:v", "-map", "1:a", "-t", "9", "-c:v", "copy", "-c:a", "aac", str(output)]
    result = subprocess.run(args, capture_output=True, timeout=120)
    if result.returncode: raise WorkError("音轨合成失败，场景已保留")
    info = media_probe(output)
    decode = subprocess.run([ffmpeg, "-v", "error", "-i", str(output), "-f", "null", "-"], capture_output=True, timeout=90)
    if decode.returncode or abs(info["duration"] - 9) > .1 or info["video"]["width"] != 1080 or info["video"]["height"] != 1920:
        raise WorkError("成片文件校验未通过，保留输出供检查")
    # User uploads need human rights/content/audio review; never auto-publish.
    report = {"template": draft["template_id"], "template_version": draft["template_version"], "duration": info["duration"],
              "file_decode_passed": True, "content_review": "pending", "rights_review": "pending", "audio_review": "pending",
              "draft_id": draft["id"], "draft_revision": draft["revision"], "layout": draft["layout"], "sources": sources}
    atomic_private(output_dir / "render-request.json", {"draft": draft, "sources": sources})
    atomic_private(output_dir / "qa.json", report)
    return {"status": "completed", "stage": "合成完成，等待观看和来源审核", "result": {"output_path": str(output), "qa_status": "pending", "template_id": draft["template_id"]}}
