"""Audio-led test variant of the existing graphic template (no presenter).

Explicitly separate from build_923's frozen nine-second contract. Takes a
project episode spec, freezes the selected voice, caches completed takes,
and uses provider timestamps. Only writes a review preview; never publishes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image, ImageDraw, ImageFont, ImageOps
import build_923 as template
from _paths import FFMPEG, FFPROBE, MUSIC_DIR
from backlot.audio_center import _runtime_profiles
from backlot.tts_runtime import generate_voice_audio


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args):
    p = subprocess.run([str(x) for x in args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])
    return p


def duration(path):
    with wave.open(str(path)) as f:
        return f.getnframes() / f.getframerate()


def voice(spec, project):
    profile = next(p for p in _runtime_profiles() if p["id"] == spec["voice_profile_id"])
    if not profile.get("available"):
        raise ValueError("指定音色当前不可用，不替换音色")
    frozen = project / "artifacts/narrated_template/voice_profile.json"
    if frozen.exists() and json.loads(frozen.read_text(encoding="utf-8")) != profile:
        raise ValueError("冻结音色或语速已变化，请另建版本")
    write(frozen, profile)
    cost = 0.0
    for i, scene in enumerate(spec["scenes"], 1):
        path = project / f"assets/audio/narrated-{i:03d}.wav"
        record = path.with_suffix(".take.json")
        identity = {"text": scene["text"], "profile": profile}
        if record.exists():
            old = json.loads(record.read_text(encoding="utf-8"))
            if old["identity"] != identity:
                raise ValueError("配音文案或音色变化，禁止覆盖已生成音频")
            if old["status"] == "completed" and path.exists() and old["sha256"] == sha(path):
                cost += old["estimated_cost_usd"]
                continue
            raise ValueError("配音提交状态未知或音频校验失败，停止自动重新计费")
        write(record, {"identity": identity, "status": "submitting"})
        result = generate_voice_audio(text=scene["text"], profile=profile, output_path=path)
        if not result.success or not path.exists():
            write(record, {"identity": identity, "status": "failed", "error": result.error})
            raise RuntimeError(result.error or "未生成配音文件")
        write(record, {"identity": identity, "status": "completed", "sha256": sha(path),
                       "duration_seconds": duration(path), "estimated_cost_usd": result.cost_usd,
                       "data": result.data})
        cost += result.cost_usd
        print(json.dumps({"voice_scene": i, "duration_seconds": duration(path),
                          "estimated_cost_usd": result.cost_usd}, ensure_ascii=False), flush=True)
    return cost


def font(size):
    return ImageFont.truetype(template.MSYHBD, size)


def center(draw, text, y, size=48, color="#101b27", max_width=820):
    f = font(size)
    box = draw.textbbox((0, 0), text, font=f)
    if box[2] - box[0] > max_width:
        raise ValueError(f"图文超宽：{text}")
    draw.text(((1080 - box[2] + box[0]) / 2, y - box[1]), text, font=f, fill=color)


def card(scene, index, target):
    """Own editorial diagrams, explicitly labelled, never simulated product footage."""
    im = Image.new("RGB", (1080, 1920), (5, 12, 22))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((78, 686, 1002, 1166), radius=28, fill="#e8f7f1")
    d.rounded_rectangle((112, 711, 390, 769), radius=18, fill="#102f29")
    d.text((138, 719), f"0{index}  /  {scene['label']}", font=font(30), fill="#ffffff")
    if index == 1:
        center(d, "12 亿+", 806, 136, "#073f34")
        center(d, "ChatGPT 每周使用人数", 978, 40)
        center(d, "GPT-6 面向免费与付费用户推出", 1052, 37)
    elif index == 2:
        for x, text, accent in [(125, "图表", "#ffb858"), (430, "按钮", "#69c6b0"), (735, "工具", "#a3acfb")]:
            d.rounded_rectangle((x, 804, x + 218, 1008), radius=20, fill="#ffffff")
            if text == "图表":
                for j, h in enumerate([46, 83, 112]):
                    d.rounded_rectangle((x+35+j*51, 936-h, x+67+j*51, 936), radius=5, fill=accent)
            elif text == "按钮":
                d.rounded_rectangle((x+30, 862, x+188, 924), radius=17, fill=accent)
                d.text((x+60, 873), "选择", font=font(32), fill="#073f34")
                d.polygon([(x+160, 907), (x+166, 957), (x+181, 941), (x+199, 939)], fill="#20332e")
            else:
                d.line((x+32, 888, x+185, 888), fill="#d2d9e0", width=13)
                d.ellipse((x+91, 870, x+127, 906), fill=accent)
                d.text((x+40, 932), "改参数", font=font(30), fill="#182b34")
            d.text((x+66, 1017), text, font=font(39), fill="#101b27")
        center(d, "把答案变成可操作的界面", 1095, 35)
    else:
        for y, title, model, subtitle in [(801, "付费用户", "GPT-6 Sol", "Plus / Pro / Business / Enterprise"),
                                        (959, "免费用户", "GPT-6 Luna", "Free / Go")]:
            d.rounded_rectangle((119, y, 961, y+130), radius=18, fill="#ffffff")
            d.text((145, y+18), title, font=font(35), fill="#0c5744")
            d.text((405, y+15), model, font=font(46), fill="#132633")
            d.text((145, y+77), subtitle, font=font(25), fill="#56666d")
    center(d, "据 OpenAI 官方公告整理 · 信息图示意", 1136, 22, "#536970")
    top = target.with_name(f"top-{index}.png")
    detail = target.with_name(f"detail-{index}.png")
    lines = [(t, template.YELLOW if i == 0 else template.RED,
              (20,20,20,255) if i == 0 else template.WHITE, 6 if i == 0 else 8)
             for i, t in enumerate(scene["top"])]
    for t in scene["top"]:
        if ImageDraw.Draw(im).textlength(t, font=template.F_TOP) + 16 > 936:
            raise ValueError(f"标题超宽：{t}")
    template.make_top(str(top), lines, scene["bar"])
    template.make_detail(str(detail), [(t, template.YELLOW if i == 0 else template.WHITE)
                                      for i,t in enumerate(scene["details"])])
    im = im.convert("RGBA")
    im.alpha_composite(Image.open(top))
    im.alpha_composite(Image.open(detail))
    d = ImageDraw.Draw(im)
    d.text((82, 1818), "口播图文模板 · 测试版", font=font(25), fill="#708398")
    im.convert("RGB").save(target)


def downloaded_visual(index, target):
    """Use OpenAI's downloaded launch image and source-preserving crops."""
    source = target.parent / "network/openai-intelligent-ui-art-card.png"
    original = Image.open(source).convert("RGB")
    if index == 1:
        visual = ImageOps.fit(original, (924, 480), method=Image.Resampling.LANCZOS)
    elif index == 2:
        phone_demo = Image.open(target.parent / "network/macrumors-gpt6-intelligent-ui.jpg").convert("RGB")
        visual = ImageOps.fit(phone_demo, (924, 480), method=Image.Resampling.LANCZOS)
    else:
        crop = original.crop((104, 0, 630, 635) if index == 2 else (805, 275, 1580, 660))
        visual = Image.new("RGB", (924, 480), "#f3f4f7")
        fitted = ImageOps.contain(crop, (908, 464), method=Image.Resampling.LANCZOS)
        visual.paste(fitted, ((924-fitted.width)//2, (480-fitted.height)//2))
    canvas = Image.open(target).convert("RGB")
    canvas.paste(visual, (78, 686))
    canvas.save(target)


def caption_groups(subtitles, offset):
    # Tencent provides actual per-token millisecond timestamps; no text-length timing.
    rows = []
    group = []
    for item in subtitles:
        text = str(item.get("Text", ""))
        if not text or "BeginTime" not in item or "EndTime" not in item:
            continue
        group.append(item)
        joined = "".join(str(x["Text"]) for x in group)
        if len(joined) >= 17 or re.search(r"[，。！？；]$", joined):
            rows.append({"text": joined, "start": offset + group[0]["BeginTime"]/1000,
                         "end": offset + group[-1]["EndTime"]/1000})
            group = []
    if group:
        rows.append({"text": "".join(x["Text"] for x in group),
                     "start": offset + group[0]["BeginTime"]/1000,
                     "end": offset + group[-1]["EndTime"]/1000})
    if not rows:
        raise ValueError("未获得真实配音时间戳，停止生成估时字幕")
    merged = []
    for row in rows:
        if re.fullmatch(r"[，。！？；、]+", row["text"]) and merged:
            merged[-1]["text"] += row["text"]
            merged[-1]["end"] = row["end"]
        else:
            merged.append(row)
    return merged


def ass_time(seconds):
    c = round(seconds*100)
    return f"{c//360000}:{c//6000%60:02d}:{c//100%60:02d}.{c%100:02d}"


def render(spec, project):
    art = project / "artifacts/narrated_template"
    frames = project / "assets/images"
    frames.mkdir(parents=True, exist_ok=True)
    scene_plan, captions = [], []
    offset, raw_audio = 0.0, []
    for i, scene in enumerate(spec["scenes"], 1):
        audio = project / f"assets/audio/narrated-{i:03d}.wav"
        dur = duration(audio)
        pad = 0.25 if i < len(spec["scenes"]) else 0.60
        nframes = math.ceil((dur+pad)*30)
        length = nframes/30
        image = frames/f"card-{i:03d}.png"
        card(scene, i, image)
        downloaded_visual(i, image)
        take = json.loads(audio.with_suffix(".take.json").read_text(encoding="utf-8"))
        captions.extend(caption_groups(take["data"]["subtitles"], offset))
        with wave.open(str(audio)) as w:
            if (w.getframerate(),w.getnchannels(),w.getsampwidth()) != (24000,1,2):
                raise ValueError("配音不是24000Hz单声道PCM16")
            raw_audio.append(w.readframes(w.getnframes()))
            raw_audio.append(bytes(round(length*24000-w.getnframes())*2))
        scene_plan.append({"id": f"cue-{i:03d}", "title":scene["label"],
                           "start_seconds":offset, "end_seconds":offset+length,
                           "duration_seconds":length, "script_section_id":f"cue-{i:03d}",
                           "visual_asset":image.relative_to(project).as_posix(),
                           "asset_type":"image", "editorial_graphic":False,
                           "source_media":("assets/images/network/macrumors-gpt6-intelligent-ui.jpg" if i == 2 else
                                           "assets/images/network/openai-intelligent-ui-art-card.png"),
                           "source_url":("https://images.macrumors.com/t/IwxdmqIlkFP4D7v4Fph6mIun5Hc%3D/400x0/article-new/2026/10/gpt-6-intelligent-ui.jpg?lossy=" if i == 2 else
                                         "https://images.ctfassets.net/kftzwdyauwt9/5frqtUAWccstAbVrCFraH6/5ae9b6bfbc3f3dff8001ed249812f97d/Intelligent-UI_Art-Card_16x9.png?w=1600&h=900&fit=fill"),
                           "source_page":("https://www.macrumors.com/2026/10/07/chatgpt-intelligent-ui/" if i == 2 else spec["source_url"]),
                           "source_crop":([0,0,1600,900] if i == 1 else
                                          ([0,0,400,225] if i == 2 else [805,275,1580,660]))})
        offset += length
    voice_path = project/"assets/audio/yaya-master.wav"
    with wave.open(str(voice_path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(b"".join(raw_audio))
    write(art/"caption-timeline.json", captions)
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Microsoft YaHei,60,&H00F7EA49,&H00F7EA49,&H00160C05,&H00160C05,-1,0,0,0,100,100,0,0,1,4,0,5,130,180,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for c in captions:
        text = "".join(ch for ch in c["text"] if not unicodedata.category(ch).startswith("P")).strip()
        if not text:
            continue
        draw = ImageDraw.Draw(Image.new("RGB",(1,1)))
        if draw.textlength(text,font=font(60)) > 780:
            # Wrap within the same provider-timed event, without inventing timestamps.
            valid = [b for b in range(1,len(text)) if
                     max(draw.textlength(text[:b],font=font(60)),
                         draw.textlength(text[b:],font=font(60))) <= 780]
            if not valid:
                raise ValueError(f"字幕超宽：{text}")
            b = min(valid, key=lambda x: abs(draw.textlength(text[:x],font=font(60))-
                                              draw.textlength(text[x:],font=font(60))))
            text = text[:b] + r"\N" + text[b:]
        c["display_text"] = text
        events.append(f"Dialogue: 0,{ass_time(c['start'])},{ass_time(c['end'])},Caption,,0,0,0,,{{\\pos(510,1243)}}{text}")
    write(art/"caption-timeline.json", captions)
    ass = art/"captions.ass"
    ass.write_text(header+"\n".join(events),encoding="utf-8-sig")
    segments = []
    for i, scene in enumerate(scene_plan,1):
        clip = art/f"scene-{i:03d}.mp4"
        # Gentle push-in affects the downloaded middle image only; typography stays locked.
        image = frames/f"card-{i:03d}.png"
        motion = ("[0:v]split=2[base][c];[c]crop=924:480:78:686,scale=1848:960,"
                  "zoompan=z='min(zoom+0.00007,1.025)':x='iw/2-iw/zoom/2':"
                  "y='ih/2-ih/zoom/2':d=1:s=924x480:fps=30[card];"
                  "[base][card]overlay=78:686,format=yuv420p[v]")
        run([FFMPEG,"-y","-v","error","-loop","1","-framerate","30","-i",image,
             "-t",scene["duration_seconds"],"-filter_complex",motion,"-map","[v]",
             "-c:v","libx264","-preset","fast","-crf","19","-threads","4",clip])
        segments.append(clip)
    listing = art/"concat.txt"
    listing.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in segments),encoding="utf-8")
    silent = art/"picture-master.mp4"
    run([FFMPEG,"-y","-v","error","-f","concat","-safe","0","-i",listing,"-c","copy",silent])
    bgm = MUSIC_DIR / spec["bgm"]
    if not bgm.is_file():
        raise ValueError("缺少指定BGM")
    mix = art/"mix.wav"
    mix_filter = (f"[0:a]highpass=f=80,loudnorm=I=-14:TP=-3:LRA=7,aresample=48000[v];"
                  f"[1:a]atrim=0:{offset},asetpts=PTS-STARTPTS,loudnorm=I=-27:TP=-8:LRA=8,"
                  f"afade=t=in:d=0.3,afade=t=out:st={offset-1.2}:d=1.2,aresample=48000[b];"
                  "[v][b]amix=inputs=2:duration=first:normalize=0[m]")
    run([FFMPEG,"-y","-v","error","-i",voice_path,"-stream_loop","-1","-i",bgm,
         "-filter_complex",mix_filter,"-map","[m]","-t",offset,"-c:a","pcm_s16le",mix])
    # This mix has insufficient crest-factor headroom for loudnorm alone.
    # Use the template runbook's gain + limiter mode, then measure final AAC.
    af = "volume=16dB,alimiter=limit=0.79:level=false:attack=5:release=20"
    output = project/"renders/narrated-template-test-v1.mp4"
    output.parent.mkdir(exist_ok=True)
    # Use relative cwd for FFmpeg ASS parser on Windows, avoiding drive/colon escaping.
    ass_name = "artifacts/narrated_template/captions.ass"
    p = subprocess.run([str(FFMPEG),"-y","-v","error","-i",str(silent),"-i",str(mix),
                        "-vf",f"ass='{ass_name}'","-map","0:v","-map","1:a","-t",str(offset),
                        "-af",af,"-ar","48000","-ac","2","-c:v","libx264","-crf","19",
                        "-preset","fast","-threads","4","-c:a","aac","-b:a","192k",
                        "-movflags","+faststart",str(output)],cwd=project,capture_output=True,text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])
    final_measure = run([FFMPEG,"-hide_banner","-i",output,"-af","loudnorm=I=-9:TP=-2:LRA=11:print_format=json","-f","null","-"])
    loudness = json.loads(re.search(r"\{\s*\"input_i\".*?\}",final_measure.stderr,re.S).group(0))
    if abs(float(loudness["input_i"])+9)>1.5 or float(loudness["input_tp"])>-1:
        raise ValueError(f"成片响度未达标：{loudness}")
    run([FFMPEG,"-v","error","-i",output,"-f","null","-"])
    write(art/"loudness.json", {"target_lufs":-9,"mode":"gain_limiter",
          "filter":af,"final_aac":loudness})
    write(project/"artifacts/scene_plan.json",{"version":"1.0","title":spec["title"],
          "total_duration_seconds":offset,"metadata":{"total_duration_seconds":offset},"scenes":scene_plan})
    sections = [{"id":s["id"],"text":spec["scenes"][i]["text"],"start_seconds":s["start_seconds"],
                 "end_seconds":s["end_seconds"],"delivery_cues":spec["scenes"][i]["delivery_cues"]}
                for i,s in enumerate(scene_plan)]
    write(project/"artifacts/script.json", {"title":spec["title"],"sections":sections,
          "voice_performance":spec["voice_performance"]})
    assets = [{"asset_id":f"network-openai-ui-{i:03d}","asset_type":"image","role":"scene_main_visual",
               "scene_id":s["id"],"path":s["visual_asset"],"sha256":sha(project/s["visual_asset"]),
               "source_type":"downloaded_network_asset","source_url":s["source_url"],"source_page":s["source_page"],
               "source_asset_path":s["source_media"],"source_asset_sha256":sha(project/s["source_media"]),
               "source_crop":s["source_crop"],
               "rights_status":"test_only_permission_unverified"} for i,s in enumerate(scene_plan,1)]
    assets.extend([{"asset_id":"yaya-narration","asset_type":"audio","path":"assets/audio/yaya-master.wav",
                    "sha256":sha(voice_path),"provider":"tencent","voice_type":"501001","role":"narration"},
                   {"asset_id":"local-bgm","asset_type":"audio","path":str(bgm),"sha256":sha(bgm),
                    "role":"bgm","rights_status":"existing_local_music_test_only"}])
    write(project/"artifacts/asset_manifest.json",{"version":"1.1","assets":assets})
    snaps = project/"snapshots"
    snaps.mkdir(exist_ok=True)
    for i,s in enumerate(scene_plan,1):
        run([FFMPEG,"-y","-v","error","-ss",s["start_seconds"]+0.8,"-i",output,"-frames:v","1",snaps/f"cue-{i:03d}.jpg"])
    write(project/"artifacts/render_report.json", {"status":"review_ready","editorial_status":"verified",
          "pipeline_type":"animated-explainer","workflow_id":"template-graphic-video",
          "variant":"narrated-test-v1","user_overrides":["audio_driven_duration","narration","downloaded_network_visuals","large_punctuation_free_cyan_subtitles"],
          "output_path":output.relative_to(project).as_posix(),"test_only":True,"published":False,
          "render_profile":{"width":1080,"height":1920,"fps":30,"duration_seconds":offset},
          "loudness":{"integrated_lufs":float(loudness["input_i"]),"true_peak_dbtp":float(loudness["input_tp"])},
          "source_url":spec["source_url"],"sha256":sha(output),"decode_passed":True,
          "visual_review":"pending","audio_listening":"pending"})
    print(json.dumps({"output":str(output),"duration_seconds":offset,"loudness":loudness},ensure_ascii=False),flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p=argparse.ArgumentParser()
    p.add_argument("spec",type=Path)
    p.add_argument("--stage",choices=["voice","render"],required=True)
    a=p.parse_args()
    spec=json.loads(a.spec.read_text(encoding="utf-8-sig"))
    if len(spec["scenes"])!=3 or spec.get("avatar") is not False:
        raise ValueError("本测试变体要求三段且无数字人")
    project=a.spec.resolve().parents[1]
    if a.stage=="voice":
        print(json.dumps({"estimated_total_cost_usd":voice(spec,project)},ensure_ascii=False))
    else:
        render(spec,project)


if __name__=="__main__":
    main()
