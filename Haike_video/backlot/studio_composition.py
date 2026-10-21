"""Parameterised Remotion adapters; original confirmed template3 TSX remains immutable."""
from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path
from backlot.studio import atomic_private
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkError


def mux_avatar_audio(ffmpeg, raw, audio, output, duration, *, linear_gain_db=None, prepared_master=False):
    """Materialize finite PCM before AAC; keep the driving waveform immutable."""
    if prepared_master and linear_gain_db is not None:
        raise WorkError("冻结混音不能再次施加人声增益")
    mastered = Path(audio) if prepared_master else Path(output).with_name("narration-mastered.wav")
    if not prepared_master:
        audio_filter = "loudnorm=I=-14:TP=-2:LRA=11" if linear_gain_db is None else f"volume={float(linear_gain_db):g}dB"
        r = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(audio),
                            "-af", audio_filter,
                            "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(mastered)],
                           capture_output=True, timeout=60)
        if r.returncode:
            raise WorkError("本地音量整理失败，原配音已保留", "unavailable")
    command = [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(raw),
                        "-i", str(mastered), "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-aac_coder", "fast", "-b:a", "192k", "-t", str(duration),
                        "-movflags", "+faststart", str(output)]
    r = subprocess.run(command,
                       capture_output=True, timeout=60)
    if r.returncode:
        raise WorkError("最终音视频封装失败，渲染和整理后的音轨已保留", "unavailable")
    return command


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


def compose_avatar(folder, draft, video, audio, duration, cues, storyboard=None, *, art_direction=None, render_profile=None):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    from tools.video.video_compose import VideoCompose
    from backlot.studio_network_materials import enabled
    if enabled(draft) and not storyboard:
        raise WorkError("联网素材已开启，但尚无已核验分镜；请恢复原任务，未改用纯图文", "unavailable")
    folder = Path(folder)
    public = folder / "public"; public.mkdir(exist_ok=True)
    ffmpeg, _ = resolve_ffmpeg_pair()
    quality = None
    if render_profile is not None:
        if not (draft["template_id"] == "avatar-investment-a-v6" and art_direction
                and art_direction.get("variant") == "art-v5"):
            raise WorkError("冻结高清导出配置仅用于模板6 v5原视频合同")
        from backlot.studio_investment_source_art_v5 import render_profile_spec, verify_source_clock
        quality = render_profile_spec(render_profile)
    info = media_probe(video)
    if not info.get("video") or abs(info["duration"] - duration) > 1:
        raise WorkError("数字人片段与驱动音频时长不一致，保留原素材待核对")
    # Historical calls keep their fps/tail alignment. New v5 high-fidelity
    # requests retain every original encoded byte and sample media time in Remotion.
    aligned = public / "avatar.mp4"
    alignment_command = None
    if quality is not None and quality["avatar_preparation"] == "source-byte-copy":
        verify_source_clock(info, duration, quality)
        shutil.copy2(video, aligned)
    else:
        alignment_command = [ffmpeg, "-v", "error", "-y", "-i", str(video), "-vf", "fps=30,tpad=stop_mode=clone:stop_duration=2", "-t", str(duration), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(aligned)]
        r = subprocess.run(alignment_command, capture_output=True, timeout=180)
        if r.returncode: raise WorkError("数字人素材无法解码，请核对原模型任务")
    shutil.copy2(audio, public / "narration.wav")
    shutil.copy2(Path(__file__).parent / "ui/brand/haike-company-logo.png", public / "haike-logo.png")
    props = {"template": draft["template_id"], "duration": duration, "title": draft["title"], "text": draft["text"], "titleSize": draft["layout"].get("title_size", 60), "accent": draft["layout"].get("accent", "#316dd6"), "captions": cues}
    n1 = draft["template_id"] == "avatar-deepblue-n1-v1"
    investment = draft["template_id"] == "avatar-investment-a-v6"
    art = art_direction is not None
    art_v4 = art and art_direction.get("variant") == "art-v4"
    art_v5 = art and art_direction.get("variant") == "art-v5"
    if art and (not investment or storyboard):
        raise WorkError("原视频艺术模板仅用于模板6本地合同，不能混合其他分镜")
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
    if investment and not art:
        from backlot.studio_investment import render_props
        investment_props, trigger_receipt = render_props(draft, duration, cues)
        # Verified optional footage uses the existing storyboard asset path above.
        investment_props["scenes"] = props.get("scenes", [])
        props = investment_props
        # The private development contract supplies explicitly labelled manual
        # captions while its public ASR/subtitle switch remains disabled.
        if draft.get("_illustrative_manual_captions") is True: props["captions"] = cues
        atomic_private(folder / "investment-triggers.json", trigger_receipt)
    if art:
        from backlot.work_catalog import sha
        if art_direction["background_path"] is not None:
            background = Path(art_direction["background_path"])
            if sha(background) != art_direction["background_sha256"]:
                raise WorkError("冻结的艺术背景已变化，保留原素材")
            shutil.copy2(background, public / "art-background.png")
        props = {"duration": duration, "avatarSrc": "avatar.mp4", "audioSrc": "narration.wav",
                 "brand": draft["input"]["investment"]["brand"], "captions": cues,
                 "art": {"direction": art_direction["direction"], "backgroundSrc": "art-background.png",
                         "chapters": art_direction["chapters"], "highlights": art_direction["highlights"],
                         "portraitFraming": art_direction["portrait_framing"]}}
        if art_v4 or art_v5:
            if art_v5:
                from backlot.studio_investment_source_art_v5 import props_art
                from backlot.studio_investment_audio_v5 import verify_master
                master = art_direction["audio_master"]
                verify_master(master["path"], master["sha256"], duration)
                if sha(master["receipt_path"]) != master["receipt_sha256"]:
                    raise WorkError("冻结混音回执SHA已变化")
                shutil.copy2(master["path"], public / "mixed-master.wav")
                props["audioSrc"] = "mixed-master.wav"
            else:
                from backlot.studio_investment_source_art_v4 import props_art
            for scene in art_direction["scenes"]:
                source = Path(scene["path"])
                if sha(source) != scene["sha256"]:
                    raise WorkError("真实素材SHA已变化，保留原请求与原片")
                shutil.copy2(source, public / scene["source_name"])
            props["art"] = props_art(art_direction)
        atomic_private(folder / "art-scene-plan.json", art_direction)
    atomic_private(folder / "props.json", props)
    template_dir = Path(__file__).resolve().parents[1] / "templates" / ("avatar-investment-a-v6-art-v5" if art_v5 else "avatar-investment-a-v6-art-v4" if art_v4 else "avatar-investment-a-v6-art-v3" if art else "avatar-deepblue-n1" if n1 else "avatar-investment-a-v6" if investment else "studio-avatar-v1")
    source = template_dir / "index.tsx"
    shutil.copy2(source, folder / "index.tsx")
    if art_v4 or art_v5:
        for component in template_dir.glob("*.tsx"):
            if component.name != "index.tsx": shutil.copy2(component, folder / component.name)
        shutil.copy2(template_dir / "types.ts", folder / "types.ts")
    if n1 or investment: shutil.copy2(template_dir / "layout.json", folder / "layout.json")
    direction = ("# 深蓝视窗 N1\n适配器avatar-deepblue-n1-v1；layout.json是几何和动效参数真值。主持人、素材、截图和纵向数据四种主窗共用深蓝外壳；人物主窗与圆框互斥，同源模糊延展。截图完整contain，红线绑定原图坐标，字幕静态重点黄字。所有视觉源静音，主音轨独立且不拉伸；留白时间回到主持人，不循环素材。标题/来源/品牌/场景来自本期输入，换人换内容后需观看审核，平台真实视口未自动验收。\n" if n1 else
                 "# 海客数字人口播\n海客科技统一品牌。选择模板决定画幅和人物位置；标题、文案、字号和强调色来自本期输入。模板3保留白卡与章节式讲解视觉，原v001确认基准不变。本适配器版本studio-avatar-v1，复用已有付费人物和声音。句级字幕需人审，素材范围与真实平台遮挡待用户观看。\n")
    if investment:
        direction = "# 数字人口播模板6-招商A\n紫蓝霓虹封面、金色斜条、白青大标题，原图原背景与头肩完整展示，同源模糊延展画布。右上玻璃项目牌、红金闪电贴纸、白字紫粗边字幕；所有重点贴纸与数据卡绑定真实ASR字幕时钟。画面没有手机录屏/平台控件；无外部素材时只用稿件数据卡，不代表实拍。开头与结尾封面叠在原音轨上，不加空白、不改变语速。layout.json为几何和动效参数真值。真人口型、招商事实及平台视口仍需观看审核。\n"
    if art:
        direction = "# 模板6艺术扩展 v003\n三种经关键帧确认的广告方向：锐蓝商业刊物、晴空社区橱窗、曜黑光学科技。真实原视频与原音轨零付费重生成，保持语速；章节完整覆盖真实ASR字幕。关键词色块为静态强调，整句轻量入场，不伪造逐字时间。装饰纸雕建筑/光学材质不是门店实拍。最终封装仅一次-2.5dB线性降幅，无二次动态压缩。layout.json记录版式与动效参数；本地开发测试仍需视觉验收。\n"
    if art_v4:
        direction = "# 模板6六风格扩展 v004\n社区橱窗、锐蓝刊物、曜黑光学、赤红宣言、银白发布、实景纪实。真实词边界驱动语义短句字幕及关键词下划线；合作条件完整保留。真实产品互动素材仅按冻结cue/offset显示并注明来源，不声称为海客门店。原人物与完整同源音轨复用、原速；最终封装仅一次-2.5dB线性降幅。\n"
    if art_v5:
        direction = "# 模板6声画扩展 v005\n原人物、原稿和真实词时钟独立冻结；声音事件仅锚定真实词、字幕或章节，命名三击pattern不冒充词钟。原声24k PCM保持不变，冻结混音对人声一次-2.5dB、音乐侧链ducking、事件音效和主限幅；如需峰值安全衰减，master_gain_db及有效人声增益见音频回执。预览和最终封装共用同一48k立体声mixed-master.wav；最终AAC无额外增益或响度归一化。\n"
    (folder / "art-direction.md").write_text(direction, encoding="utf-8")
    raw = folder / "avatar-render.mp4"
    edits = {"render_runtime": "remotion", "composition_mode": "atelier", "renderer_family": "bespoke", "bespoke": {"entry": str(folder / "index.tsx"), "composition_id": "HaikeInvestmentArtV5" if art_v5 else "HaikeInvestmentArtV4" if art_v4 else "HaikeInvestmentArtV3" if art else "HaikeDeepblueN1" if n1 else "HaikeInvestmentA6" if investment else "HaikeStudioAvatar", "props_path": str(folder / "props.json"), "public_dir": str(public), "crf": 18, "concurrency": 2}, "timeline": {"duration_seconds": duration}}
    if quality is not None:
        edits["bespoke"].update({key: quality[key] for key in ("codec", "image_format", "crf", "x264_preset", "pixel_format", "scale")})
        if quality.get("video_bitrate") is not None:
            edits["bespoke"]["video_bitrate"] = quality["video_bitrate"]
        if quality["jpeg_quality"] is not None:
            edits["bespoke"]["jpeg_quality"] = quality["jpeg_quality"]
    result = VideoCompose().execute({"operation": "render", "output_path": str(raw), "edit_decisions": edits, "asset_manifest": {"assets": []}, "script_text": draft["text"]})
    if not result.success:
        # Keep local renderer diagnostics private. Never copy job/config/props
        # payloads into a public error or silently restart a paid stage.
        import re
        error = str(result.error or "本地渲染未返回错误说明")
        error = re.sub(r"https?://[^\s\"'<>]+", "[已隐藏网络地址]", error)
        error = re.sub(r"(?i)(api[_-]?key|authorization|bearer|token|secret)(\s*[=:]\s*|\s+)[^\s,;]+", r"\1=[已隐藏]", error)
        atomic_private(folder / "render-failure.json", {"template_adapter": draft["template_id"], "error": error[-12000:],
                       "safe_resume_point": "local_composition", "paid_artifacts_preserved": True})
        raise WorkError("本地模板合成未通过，请检查渲染依赖；数字人与音频已保留", "unavailable")
    frames = round(duration * 30)
    output = folder / "avatar-preview.mp4"
    # Align the AAC container tail to the same final frame clock as the image.
    if art_v5:
        mux_command = mux_avatar_audio(ffmpeg, raw, public / "mixed-master.wav", output, frames / 30, prepared_master=True)
        from backlot.studio_investment_audio_v5 import measure_audio
        final_audio = measure_audio(output)
        atomic_private(folder / "audio-final-check.json", {"master": art_direction["audio_master"],
            "final": final_audio, "output_sha256": sha(output), "additional_mux_gain_db": 0})
        if final_audio["true_peak_dbtp"] > -1.5:
            raise WorkError("最终AAC true-peak超过-1.5dBTP，保留冻结混音与原任务", "unavailable")
    elif art:
        mux_avatar_audio(ffmpeg, raw, audio, output, frames / 30, linear_gain_db=-2.5)
    else:
        mux_avatar_audio(ffmpeg, raw, audio, output, frames / 30)
    info = media_probe(output)
    if art_v5 and (str((info.get("audio") or {}).get("sample_rate")) != "48000" or (info.get("audio") or {}).get("channels") != 2):
        raise WorkError("v5最终音轨必须保持48kHz立体声冻结混音", "unavailable")
    expected_height = 1440 if draft["template_id"].startswith("avatar-template3") else 1920
    decode = subprocess.run([ffmpeg, "-v", "error", "-i", str(output), "-f", "null", "-"], capture_output=True, timeout=180)
    if decode.returncode or not info.get("audio") or info["video"]["width"] != 1080 or info["video"]["height"] != expected_height or abs(info["duration"] - frames/30) > .1:
        raise WorkError("成片技术校验未通过，产物保留待核对", "unavailable")
    if quality is not None:
        from backlot.work_catalog import sha
        source_info = media_probe(video)["video"]
        atomic_private(folder / "render-quality-receipt.json", {"profile": quality,
            "avatar": {"mode": quality["avatar_preparation"], "source_path": str(Path(video).resolve()),
                "source_sha256": sha(video), "public_sha256": sha(aligned),
                "source_fps": source_info.get("avg_frame_rate") or source_info.get("r_frame_rate"),
                "source_duration": source_info.get("duration"), "alignment_command": alignment_command},
            "remotion_command": (getattr(result, "data", None) or {}).get("render_command"),
            "remotion_settings": edits["bespoke"], "final_mux_command": mux_command,
            "final_video": "stream-copy", "output_sha256": sha(output),
            "timeline_unchanged": {"duration": duration, "fps": 30, "frames": frames}})
    atomic_private(folder / "render-result.json", {"template_adapter": "avatar-deepblue-n1-v1" if n1 else "avatar-investment-a-v6" if investment else "studio-avatar-v1", "media": info, "native_render": str(raw), "technical_decode": "passed", "human_review": "pending"})
    return output
