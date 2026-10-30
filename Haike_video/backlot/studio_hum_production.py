"""Reusable speech-clock Hum motion composition, frozen and owned by the queue.

This is a separate contract from the historical twenty-second pilot.  Nothing in
that pilot's source/approval gates is relaxed by accepting a new narration here.
The adapter only renders local resources; provider calls belong to upstream jobs.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import wave

from backlot.studio import atomic_private
from backlot.production_queue import _sanitize as _queue_sanitize
from backlot.studio_investment_recompose import KIND, fingerprint
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkCatalog, WorkError, read_json, regular_path, sha

CONTRACT = "hum-production-v1"
COMPOSITION_ID = "HumProduction"
ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / CONTRACT
FPS, WIDTH, HEIGHT, RATE = 30, 1440, 1800, 48000
PROFILE = {"codec": "h264", "crf": 1, "image_format": "png", "x264_preset": "fast", "pixel_format": "yuv444p", "scale": 1}
EXPORT = {"video_bitrate": 20500000, "minimum_measured_bitrate": 20000000, "audio_bitrate": 192000, "pixel_format": "yuv420p"}
MIX = {"version": "speech-clock-v1", "sample_rate": RATE, "channels": 2, "voice_speed": 1, "voice_offset": 0,
       "target_lufs": -16, "target_true_peak": -2.5, "source_video_audio": "muted"}
REQUEST_FILE = CONTRACT + "-request.json"
OUTPUT_FILE = "hum-production.mp4"
NOMUSIC_FILE = "hum-production-nomusic.mp4"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def _require(ok, message):
    if not ok:
        raise WorkError(message)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _int(value, low, high):
    return type(value) is int and low <= value <= high


def _name(value):
    return (isinstance(value, str) and value not in {"", ".", ".."}
            and Path(value).name == value and not any(c in value for c in '/\\:')
            and not any(ord(c) < 32 for c in value))


def _text(value, limit, *, lines=1, empty=False):
    return (isinstance(value, str) and (empty or bool(value.strip())) and len(value) <= limit
            and len(value.split("\n")) <= lines and not any(ord(c) < 32 and c != "\n" for c in value))


def _position(value):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)%[ \t]+(\d+(?:\.\d+)?)%", value) if isinstance(value, str) else None
    return match is not None and all(0 <= float(v) <= 100 for v in match.groups())


def _clock(path):
    """Use the narration sample count, never container rounding, as the clock."""
    try:
        with wave.open(str(path), "rb") as stream:
            _require(stream.getcomptype() == "NONE" and stream.getnchannels() in {1, 2}
                     and stream.getsampwidth() in {2, 3, 4} and 16000 <= stream.getframerate() <= 96000,
                     "口播须为16至96kHz、单/双声道PCM WAV")
            samples, rate = stream.getnframes(), stream.getframerate()
            duration = samples / rate
            _require(2 <= duration <= 600, "正式模板支持2至600秒完整口播，不能截断或伸缩填时长")
            nonzero = False
            while chunk := stream.readframes(65536):
                nonzero = nonzero or any(chunk)
            _require(nonzero, "口播WAV为空白静音")
            return {"samples": samples, "sample_rate": rate, "channels": stream.getnchannels(),
                    "sample_width": stream.getsampwidth(), "duration_seconds": duration}
    except (OSError, wave.Error, EOFError) as exc:
        raise WorkError("无法读取完整口播PCM WAV") from exc


def _template_files():
    return sorted(p for p in TEMPLATE.rglob("*") if p.is_file() and p.suffix in {".tsx", ".ts", ".css", ".json"}
                  and p.name not in {"video-template-spec.json", "props.example.json"})


def runtime():
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    files = [Path(__file__), ROOT / "backlot/production_queue_worker.py", ROOT / "backlot/production_queue.py", ROOT / "tools/video/video_compose.py",
             ROOT / "remotion-composer/package-lock.json", *_template_files(), *map(Path, resolve_ffmpeg_pair())]
    _require((TEMPLATE / "index.tsx").is_file() and (ROOT / "remotion-composer/node_modules").is_dir(), "正式模板或Remotion依赖未就绪")
    _require(all(p.is_file() for p in files), "本地渲染器或编码器缺失")
    return {str(p.resolve()): sha(p) for p in files}


def plan_scenes(shot_plan, duration_frames):
    """Allocate reusable shot weights to one exact, contiguous narration clock."""
    _require(isinstance(shot_plan, list) and 1 <= len(shot_plan) <= 100 and all(isinstance(s, dict) for s in shot_plan), "shotPlan须有1至100个场景")
    weights = [s.get("weight", 1) for s in shot_plan]
    _require(all(_number(w) and 0 < w <= 100 for w in weights), "shotPlan场景权重须大于0且不超过100")
    minimums = [180 if s.get('module') == 'wall' and s.get('motion') == 'card-stack' else 108 if s.get("module") == "wall"
                else {'cloth': 50, 'parallax': 60, 'mondrian': 80, 'gl-film': 54, 'gl-circle': 54, 'pixi-shock': 60}.get(s.get('motion'), 30) for s in shot_plan]
    dynamic_minimums = read_json(TEMPLATE / 'dynamic/layout.json')['minimumFrames'] if any(s.get('module') == 'dynamic' for s in shot_plan) else {}
    minimums = [dynamic_minimums.get(s.get('motion'), 30) if s.get('module') == 'dynamic' else old
                for s, old in zip(shot_plan, minimums)]
    remaining = duration_frames - sum(minimums)
    _require(remaining >= 0, "口播太短，无法容纳shotPlan的级联、展开和阅读时窗；请减少场景")
    floats = [remaining * w / sum(weights) for w in weights]
    extra = [int(v) for v in floats]
    for index in sorted(range(len(extra)), key=lambda i: floats[i] - extra[i], reverse=True)[:remaining - sum(extra)]:
        extra[index] += 1
    cursor, result = 0, []
    for index, (raw, minimum, addition) in enumerate(zip(shot_plan, minimums, extra)):
        _require(not {"from", "frames", "selection"} & set(raw), "shotPlan不接受固定时码；需要固定时码时请使用props.scenes")
        scene = {k: deepcopy(v) for k, v in raw.items() if k != "weight"}
        frames = minimum + addition
        scene.update(id=scene.get("id", "shot-" + str(index + 1)), **{"from": cursor, "frames": frames})
        if scene.get("module") == "wall":
            # The selected card itself expands. Other cards remain posters.
            expand = 142 if scene.get('motion') == 'card-stack' else max(30, min(60, round(frames * .36)))
            scene["selection"] = {"cursorFrom": max(12, expand - 24), "selectFrom": expand - 10,
                                  "expandFrom": expand, "holdFrom": expand + 18}
        result.append(scene)
        cursor += frames
    return result


def validate_props(props, voice_seconds):
    _require(isinstance(props, dict), "正式模板参数须为对象")
    allowed = {"width", "height", "fps", "durationFrames", "audio", "brand", "footer", "palette", "visualStyle", "media", "scenes",
               "captions", "fontAssets", "wallCategories", "presenterClips", "presenterModes"}
    _require(not set(props) - allowed, "正式模板包含未开放参数")
    total = props.get("durationFrames")
    _require(_int(total, 60, 18060) and (props.get("width"), props.get("height"), props.get("fps"), props.get("audio"))
             == (WIDTH, HEIGHT, FPS, "master.wav"), "正式模板须绑定自动口播时钟、4:5和master.wav")
    _require(_text(props.get("brand"), 24) and _text(props.get("footer", ""), 50, empty=True), "品牌或页脚文字无效")
    _require(props.get("visualStyle") in {"hum", "coral", "darkroom", "carnival", "archive", "playroom"}, "视觉风格须为已适配的模板风格")
    if "palette" in props:
        _require(isinstance(props["palette"], dict) and all(isinstance(v, str) and re.fullmatch(r"#[a-fA-F0-9]{6}", v) for v in props["palette"].values()), "颜色须为十六进制色值")
    _require(props.get("fontAssets") == {"display": "display.ttf", "body": "body.ttf"}, "正式模板须绑定display.ttf和body.ttf字体文件")
    if "wallCategories" in props:
        cats = props["wallCategories"]
        _require(isinstance(cats, list) and 1 <= len(cats) <= 6 and all(_text(c, 8) for c in cats)
                 and len(cats) == len(set(cats)) and sum(len(c) * 25 + 46 for c in cats) + 14 * (len(cats) - 1) <= 1264, "素材墙分类超过单行容量或无效")
    media = props.get("media")
    _require(isinstance(media, list) and 1 <= len(media) <= 24 and all(isinstance(m, dict) for m in media), "须有1至24项素材")
    ids = set()
    for item in media:
        _require(not set(item) - {"id", "src", "thumbnail", "kind", "offset", "fit", "objectPosition", "orientation", "label"}
                 and _text(item.get("id"), 60) and item["id"] not in ids, "素材ID重复或包含未开放参数")
        ids.add(item["id"])
        _require(_name(item.get("src")) and _name(item.get("thumbnail")) and Path(item["thumbnail"]).suffix.lower() in IMAGE_EXT, "素材或封面须为安全平面文件名")
        kind = item.get("kind", "image" if Path(item["src"]).suffix.lower() in IMAGE_EXT else "video")
        _require(kind in {"image", "video"} and Path(item["src"]).suffix.lower() in (IMAGE_EXT if kind == "image" else VIDEO_EXT), "素材类型与扩展名不一致")
        _require(_number(item.get("offset", 0)) and item.get("offset", 0) >= 0 and item.get("fit") == "contain"
                 and _position(item.get("objectPosition", "50% 50%")) and _text(item.get("label", ""), 16, empty=True)
                 and item.get("orientation", "landscape") in {"landscape", "portrait"}, "素材须原速全幅且入点、标签和方向有效")
    scenes = props.get("scenes")
    _require(isinstance(scenes, list) and scenes and all(isinstance(s, dict) for s in scenes), "场景清单为空")
    cursor, seen, used = 0, set(), set()
    for scene in scenes:
        _require(not set(scene) - {"id", "from", "frames", "module", "theme", "title", "subtitle", "mediaId", "selection", "wallMediaIds", "motion"}, "场景包含未开放参数")
        _require(_text(scene.get("id"), 60) and scene["id"] not in seen and scene.get("from") == cursor
                 and _int(scene.get("from"), 0, total - 1) and _int(scene.get("frames"), 30, total)
                 and cursor + scene["frames"] <= total, "场景须连续覆盖全片、不重叠且编号唯一")
        seen.add(scene["id"])
        _require(scene.get("module") in {"statement", "wall", "focus", "dynamic"} and scene.get("theme", "paper") in {"paper", "dark"}, "尚未适配的场景模块或主题")
        motion = scene.get('motion')
        dynamic = scene['module'] == 'dynamic'
        if props['visualStyle'] in {'archive', 'playroom'}:
            _require(scene['module'] in {'dynamic', 'statement'}, '动态素材模板使用dynamic或statement场景')
        if dynamic:
            rules = read_json(TEMPLATE / 'dynamic/layout.json')['minimumFrames']
            _require(props['visualStyle'] in {'archive', 'playroom'} and motion in rules
                     and scene['frames'] >= rules[motion], '动态场景尚未适配或时长不足以完成动作')
            wall = scene.get('wallMediaIds')
            _require(isinstance(wall, list) and 3 <= len(wall) <= 9 and len(set(wall)) == len(wall)
                     and all(i in ids for i in wall) and scene.get('mediaId') in wall, '动态场景须绑定3至9项真实素材并包含主素材')
            _require('selection' not in scene, '动态场景动作节点由当前模块与时长决定，不接受旧素材墙selection')
            _require('\n' not in scene.get('subtitle', '') and len(scene.get('subtitle', '')) <= 38, '动态场景说明须为最多38字的单行')
            used.update(wall)
        if props['visualStyle'] in {'darkroom', 'carnival'}:
            _require(scene['module'] in {'focus', 'statement'}, '开源新风格须使用focus/statement镜头安排；旧wall时间窗不能直接套用')
            _require(motion is None or motion in {'cloth', 'parallax', 'mondrian', 'gl-film', 'gl-circle', 'pixi-shock'}, '新风格不使用旧鼠标卡片动效')
            _require(motion not in {'gl-film', 'gl-circle', 'pixi-shock'} or scene['module'] == 'focus', 'GL/Pixi实拍效果须绑定focus素材')
            _require(scene['frames'] >= {'cloth': 50, 'parallax': 60, 'mondrian': 80, 'gl-film': 54, 'gl-circle': 54, 'pixi-shock': 60}.get(motion, 30), '场景太短，无法完成开源动效及稳定阅读')
        _require(motion is None or dynamic or (scene['module'] == 'wall' and motion in {'cascade', 'card-stack'})
                 or (scene['module'] == 'focus' and motion == 'paper-reveal')
                 or (props['visualStyle'] in {'darkroom', 'carnival'} and scene['module'] in {'focus', 'statement'}
                     and motion in {'cloth', 'parallax', 'mondrian', 'gl-film', 'gl-circle', 'pixi-shock'}), '动效与场景模块不匹配或尚未适配')
        _require(_text(scene.get("title"), 42, lines=2) and all(len(line) <= 16 for line in scene["title"].split("\n"))
                 and _text(scene.get("subtitle", ""), 50, lines=2, empty=True), "场景标题最多2行、每行16字；说明最多2行，须适合实际阅读字框")
        if scene["module"] in {"wall", "focus", "dynamic"}:
            _require(scene.get("mediaId") in ids, "场景引用不存在的主素材")
            used.add(scene["mediaId"])
            if scene["module"] == "wall":
                wall = scene.get("wallMediaIds")
                _require(isinstance(wall, list) and (len(wall) in {3, 5} if motion == 'card-stack' else 4 <= len(wall) <= 6) and len(set(wall)) == len(wall)
                         and all(i in ids for i in wall) and scene["mediaId"] in wall, "素材墙须有4至6张级联卡或3/5张卡堆，且包含选中卡")
                used.update(wall)
                keys = ("cursorFrom", "selectFrom", "expandFrom", "holdFrom")
                selection = scene.get("selection")
                _require(isinstance(selection, dict) and set(selection) == set(keys)
                         and all(_int(selection.get(k), 0, scene["frames"] - 1) for k in keys)
                         and all(selection[a] < selection[b] for a, b in zip(keys, keys[1:]))
                         and 8 <= selection["holdFrom"] - selection["expandFrom"] <= 30
                         and scene["frames"] - selection["holdFrom"] >= (20 if motion == 'card-stack' else 30), "级联、点击、展开和稳定阅读时窗无效")
                if motion == 'card-stack':
                    _require(scene['frames'] >= 180 and selection['expandFrom'] >= 142, '卡堆场景至少180帧并保留142帧分发/选择时窗')
            elif scene['module'] == 'focus':
                _require(not {"selection", "wallMediaIds"} & set(scene), "聚焦模块不接受素材墙选择参数")
        else:
            _require(not {"mediaId", "selection", "wallMediaIds"} & set(scene), "陈述模块不接受实拍参数")
        cursor += scene["frames"]
    _require(cursor == total and used == ids, "场景未覆盖完整口播时钟或有未使用素材")
    captions = props.get("captions")
    _require(isinstance(captions, list) and captions and all(isinstance(c, dict) for c in captions), "须提供实际口播字幕")
    end_ms = 0
    for cue in captions:
        _require(set(cue) == {"text", "startMs", "endMs"} and _text(cue.get("text"), 22)
                 and _number(cue.get("startMs")) and _number(cue.get("endMs")) and cue["startMs"] >= end_ms
                 and cue["endMs"] > cue["startMs"] and cue["endMs"] <= voice_seconds * 1000 + 25, "字幕须绑定实际口播，不能越界、重叠或超长")
        end_ms = cue["endMs"]
    clips, modes = props.get("presenterClips", []), props.get("presenterModes", [])
    _require(isinstance(clips, list) and isinstance(modes, list) and all(isinstance(c, dict) for c in clips)
             and all(isinstance(m, dict) for m in modes), "人物片段及大小窗模式须为数组")
    clip_ids = set()
    for clip in clips:
        _require(not set(clip) - {"id", "src", "from", "frames", "offset", "fit", "objectPosition"}
                 and _text(clip.get("id"), 60) and clip["id"] not in clip_ids and _name(clip.get("src"))
                 and Path(clip["src"]).suffix.lower() in VIDEO_EXT and _int(clip.get("from"), 0, total - 1)
                 and _int(clip.get("frames"), 1, total) and clip["from"] + clip["frames"] <= total
                 and _number(clip.get("offset")) and clip["offset"] >= 0 and clip.get("fit", "contain") == "contain"
                 and _position(clip.get("objectPosition", "50% 50%")), "人物片段须绑定真实同源窗口及原速入点")
        clip_ids.add(clip["id"])
    indexed, previous = {c["id"]: c for c in clips}, 0
    for mode in modes:
        _require(set(mode) == {"clipId", "from", "frames", "mode"} and mode.get("clipId") in indexed
                 and mode.get("mode") in {"large", "small", "hidden"} and _int(mode.get("from"), 0, total - 1)
                 and _int(mode.get("frames"), 1, total) and mode["from"] >= previous, "人物大小/隐藏模式重叠或引用无效")
        clip = indexed[mode["clipId"]]
        _require(clip["from"] <= mode["from"] and mode["from"] + mode["frames"] <= clip["from"] + clip["frames"], "人物模式越过同源出镜窗口")
        previous = mode["from"] + mode["frames"]
    _require(set(indexed) == {m["clipId"] for m in modes}, "人物来源须有大小窗或隐藏模式；不出镜可不提供人物来源")


def _audio_plan(value, paths, clock):
    _require(isinstance(value, dict) and not set(value) - {"voice", "music", "musicGainDb", "musicOffsetSeconds", "loopMusic", "sfx", "tailSeconds"}, "声音计划包含未开放参数")
    _require(_name(value.get("voice")) and value["voice"] in paths and Path(value["voice"]).suffix.lower() == ".wav", "声音计划须有完整口播WAV")
    tail = value.get("tailSeconds", .25)
    _require(_number(tail) and 0 <= tail <= 2, "尾部只能补0至2秒非语音")
    frames = math.ceil((Fraction(clock["samples"], clock["sample_rate"]) + Fraction(str(tail))) * FPS)
    plan = {"voice": value["voice"], "tailSeconds": tail, "sfx": deepcopy(value.get("sfx", [])),
            "durationFrames": frames, "voice_clock": clock, "mix_profile": MIX}
    if value.get("music"):
        music, offset, gain, loop = value["music"], value.get("musicOffsetSeconds", 0), value.get("musicGainDb", -16), value.get("loopMusic", False)
        _require(_name(music) and music in paths and Path(music).suffix.lower() in {".wav", ".mp3", ".m4a"}
                 and _number(offset) and offset >= 0 and _number(gain) and -40 <= gain <= -3 and type(loop) is bool, "配乐来源、入点、增益或循环声明无效")
        info = media_probe(paths[music])
        _require(info.get("audio") and offset < info["duration"] and (loop or offset + frames / FPS <= info["duration"] + .001), "配乐长度不足；请提供完整配乐或显式loopMusic")
        plan.update(music=music, musicOffsetSeconds=offset, musicGainDb=gain, loopMusic=loop)
    _require(isinstance(plan["sfx"], list) and len(plan["sfx"]) <= 200 and all(isinstance(s, dict) for s in plan["sfx"]), "音效须为0至200个真实时间事件")
    for sound in plan["sfx"]:
        _require(not set(sound) - {"src", "atSeconds", "gainDb"} and _name(sound.get("src")) and sound["src"] in paths
                 and Path(sound["src"]).suffix.lower() in {".wav", ".mp3", ".m4a"} and _number(sound.get("atSeconds"))
                 and 0 <= sound["atSeconds"] < frames / FPS and _number(sound.get("gainDb", -10)) and -40 <= sound.get("gainDb", -10) <= 0, "音效来源、全局时码或增益无效")
        info = media_probe(paths[sound["src"]])
        _require(info.get("audio") and 0 < info["duration"] <= 10 and sound["atSeconds"] + info["duration"] <= frames / FPS + .025, "音效长度超过10秒或越过成片尾部")
    return plan


def _required_names(props, audio):
    names = {audio["voice"], *props["fontAssets"].values()}
    names.update(m[k] for m in props["media"] for k in ("src", "thumbnail"))
    names.update(p["src"] for p in props.get("presenterClips", []))
    names.update(s["src"] for s in audio.get("sfx", []))
    if audio.get("music"):
        names.add(audio["music"])
    return names


def _sources(sources):
    _require(isinstance(sources, dict) and sources and all(_name(n) for n in sources), "sources须为安全文件名到绝对本地路径映射")
    paths = {}
    for name, raw in sources.items():
        _require(isinstance(raw, (str, Path)) and Path(raw).is_absolute() and not Path(raw).is_symlink(), "来源必须为真实绝对文件，不能使用链接")
        path = Path(raw).resolve()
        _require(path.is_file() and path.stat().st_size > 0, "来源文件缺失或为空：" + name)
        paths[name] = path
    _require("master.wav" not in paths, "master.wav由引擎生成，请使用voice.wav等输入名")
    return paths


def _validate_sources(props, audio, paths, provenance, *, check_fonts=True):
    _require(set(paths) == _required_names(props, audio), "sources与声明的素材、声音、字体槽不一致")
    _require(isinstance(provenance, dict), "须提供声音、字幕与素材真实来源记录")
    voice_sha = sha(paths[audio["voice"]])
    voice, captions = provenance.get("voice", {}), provenance.get("captions", {})
    _require(voice.get("sha256") == voice_sha and voice.get("source") and voice.get("authorized") is True, "口播来源SHA或本次使用授权声明不匹配")
    _require(captions.get("voice_sha256") == voice_sha and captions.get("method"), "字幕缺少同一口播的真实时码来源")
    audio_rows = provenance.get("audio", {})
    audio_names = {s["src"] for s in audio.get("sfx", [])} | ({audio["music"]} if audio.get("music") else set())
    _require(isinstance(audio_rows, dict) and set(audio_rows) == audio_names, "配乐/音效来源记录不完整")
    for name in audio_names:
        _require(isinstance(audio_rows[name], dict) and audio_rows[name].get("sha256") == sha(paths[name])
                 and audio_rows[name].get("source"), "配乐/音效身份或来源不匹配：" + name)
    rows = provenance.get("media")
    _require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), "须有实际素材看帧记录")
    reviews = {r.get("id"): r for r in rows}
    _require(len(reviews) == len(rows) and set(reviews) == {m["id"] for m in props["media"]}, "看帧记录须逐项覆盖素材ID")
    from PIL import Image, ImageFont
    probed = {}
    for item in props["media"]:
        review = reviews[item["id"]]
        _require(review.get("reviewed") is True and review.get("description")
                 and review.get("source_sha256") == sha(paths[item["src"]])
                 and review.get("thumbnail_sha256") == sha(paths[item["thumbnail"]]), "素材或封面未看帧/身份已改变")
        with Image.open(paths[item["thumbnail"]]) as image:
            _require(min(image.size) >= 240, "素材封面须至少240像素")
            if "orientation" in item:
                _require((image.height > image.width) == (item["orientation"] == "portrait"), "封面方向与声明不一致")
            image.verify()
        kind = item.get("kind", "image" if Path(item["src"]).suffix.lower() in IMAGE_EXT else "video")
        if kind == "image":
            with Image.open(paths[item["src"]]) as image:
                _require(min(image.size) >= 240, "图片素材像素不足")
                image.verify()
            continue
        info = media_probe(paths[item["src"]])
        probed[item["src"]] = info
        _require(info.get("video") and min(int(info["video"].get(k, 0)) for k in ("width", "height")) >= 720, "视频素材低于720p或不可解码")
        start, stop = review.get("source_start_seconds"), review.get("source_end_seconds")
        observed = review.get("observed_frames")
        _require(_number(start) and _number(stop) and 0 <= start <= item.get("offset", 0) < stop <= info["duration"] + .025
                 and isinstance(observed, list) and observed and all(_number(t) and start <= t <= stop for t in observed), "视频素材须声明实际看帧区间，不能循环或冻结补长")
    by_id = {m["id"]: m for m in props["media"]}
    for scene in props["scenes"]:
        if scene["module"] == "statement":
            continue
        item = by_id[scene["mediaId"]]
        if item.get("kind", "image" if Path(item["src"]).suffix.lower() in IMAGE_EXT else "video") == "image":
            continue
        playback_from = scene["selection"]["expandFrom"] if scene["module"] == "wall" else 0
        stop = item.get("offset", 0) + (scene["frames"] - playback_from) / FPS
        _require(stop <= reviews[item["id"]]["source_end_seconds"] + .025
                 and stop <= probed[item["src"]]["duration"] + .025, "实际播放长度超出素材或已看帧区间；须换更长素材或增加镜头，不能冻结/循环")
    clips = props.get("presenterClips", [])
    sync_rows = provenance.get("presenterClips", [])
    _require(isinstance(sync_rows, list) and all(isinstance(r, dict) for r in sync_rows), "人物同源记录无效")
    sync = {r.get("id"): r for r in sync_rows}
    _require(len(sync) == len(sync_rows) and set(sync) == {c["id"] for c in clips}, "人物同源记录须覆盖全部出镜片段")
    for clip in clips:
        row, info = sync[clip["id"]], media_probe(paths[clip["src"]])
        probed[clip["src"]] = info
        _require(row.get("source_sha256") == sha(paths[clip["src"]]) and row.get("voice_sha256") == voice_sha
                 and row.get("reviewed") is True and row.get("globalFrom") == clip["from"] and row.get("sourceOffset") == clip["offset"]
                 and row.get("frames") == clip["frames"], "人物片段须绑定实际完整口播和全局时钟，不能在大小窗切换时重启")
        _require(info.get("video") and clip["offset"] + clip["frames"] / FPS <= info["duration"] + .025, "人物原片长度不足，禁止拉伸语音或循环口型")
    # Use actual bundled font metrics; tests may replace this helper with fixtures.
    if check_fonts:
        _validate_fonts(props, paths, ImageFont)
    return probed


def _validate_fonts(props, paths, image_font):
    try:
        geometry = read_json(TEMPLATE / "layout.json")
        caption_width = (geometry.get("captions") or [88, 1570, 1264, 116])[2]
        is_dynamic = props.get('visualStyle') in {'archive', 'playroom'}
        caption_font = image_font.truetype(str(paths["body.ttf"]), 76 if is_dynamic else geometry.get("captionSize", 60))
        _require(all(caption_font.getlength(c["text"]) <= caption_width for c in props["captions"]), "字幕超出实际字体字框，请按语义分句")
        for scene in props["scenes"]:
            role = geometry.get("statement" if scene["module"] == "statement" else "sceneHeader", {})
            size = role.get("titleSize", 112 if scene["module"] == "statement" else 88)
            box = role.get("title", [88, 160, 1264, 400])
            if is_dynamic:
                size, box = (112, [88, 400, 1264, 300]) if scene['module'] == 'statement' else (88, [88, 200, 1264, 210])
            font = image_font.truetype(str(paths["display.ttf"]), size)
            lines = scene["title"].split("\n")
            measured_height = len(lines) * size * (1.25 if scene['module'] == 'statement' else 1.12) if is_dynamic else len(lines) * (size * 1.16 + 3)
            _require(all(font.getlength(line) <= box[2] for line in lines) and measured_height <= box[3], "标题超出字体字框，请按语义换行")
            if is_dynamic and scene.get('subtitle'):
                sub_font = image_font.truetype(str(paths['body.ttf']), 44 if scene['module'] == 'statement' else 30)
                _require(all(sub_font.getlength(line) <= 1250 for line in scene['subtitle'].split('\n')), '说明超出实际字体字框')
    except OSError as exc:
        raise WorkError("安全字体无法加载") from exc


def preflight(value):
    """Read-only full input validation used by the CLI and prepare()."""
    _require(isinstance(value, dict) and not set(value) - {"title", "props", "sources", "audio", "provenance", "shotPlan"}, "制作输入字段无效")
    _require(_text(value.get("title"), 100), "作品标题无效")
    paths = _sources(value.get("sources"))
    raw_audio = value.get("audio", {})
    _require(isinstance(raw_audio, dict) and raw_audio.get("voice") in paths, "完整口播来源未声明")
    clock = _clock(paths[raw_audio["voice"]])
    audio = _audio_plan(raw_audio, paths, clock)
    props = deepcopy(value.get("props"))
    _require(isinstance(props, dict), "须有模板props")
    for key, expected in {"width": WIDTH, "height": HEIGHT, "fps": FPS, "durationFrames": audio["durationFrames"], "audio": "master.wav"}.items():
        _require(key not in props or props[key] == expected, "尺寸或时长由完整口播自动生成，不能手工覆盖：" + key)
        props[key] = expected
    if "shotPlan" in value:
        _require("scenes" not in props, "shotPlan与props.scenes只能选择一种")
        props["scenes"] = plan_scenes(value["shotPlan"], audio["durationFrames"])
    validate_props(props, clock["duration_seconds"])
    provenance = canonical_provenance(value.get("provenance"))
    probes = _validate_sources(props, audio, paths, provenance)
    return {"title": value["title"], "props": props, "audio": audio, "paths": paths, "provenance": provenance, "media": probes}


def canonical_provenance(value):
    """Freeze the same credential-free lineage the real queue can retain.

    Keys such as authorization_basis/reuse_authorization are removed by the
    queue, whereas authorized and source SHA fields survive. Validate the
    surviving required lineage before assigning any immutable identity.
    """
    return _queue_sanitize(deepcopy(value), redact_local_paths=False)


def prepare(queue, value):
    normalized = preflight(value)
    core = {"contract": CONTRACT, "title": normalized["title"], "props": normalized["props"], "audio": normalized["audio"],
            "provenance": normalized["provenance"], "origins": {n: {"path": str(p), "sha256": sha(p)} for n, p in normalized["paths"].items()},
            "media": normalized["media"], "runtime": runtime(), "profile": PROFILE, "export": EXPORT, "cloud_calls": 0, "publication": False}
    clean = _queue_sanitize(core, redact_local_paths=False)
    # Optional probe metadata can be scrubbed; execution semantics cannot be
    # silently changed (e.g. a credential-looking caption or source slot).
    _require(all(clean.get(key) == core[key] for key in ("title", "props", "audio", "origins", "runtime")),
             "制作参数或来源绑定含队列保留凭据字段，请移除或重命名后冻结；不会静默改写口播字幕或素材")
    core = clean
    core["project_id"] = "studio-" + fingerprint(core)[:16]
    digest = fingerprint(core)
    request = {**core, "request_sha256": digest, "render_id": CONTRACT + "-" + digest[:20]}
    project = queue.projects_root / request["project_id"]
    frozen = project / "artifacts" / REQUEST_FILE
    if frozen.exists():
        existing = read_json(frozen)
        validate(queue, existing)
        return existing
    from lib.checkpoint import init_project
    init_project(request["project_id"], title=request["title"], pipeline_type="animated-explainer", pipeline_dir=queue.projects_root)
    assets = project / "assets" / CONTRACT
    assets.mkdir(parents=True, exist_ok=True)
    for name, path in normalized["paths"].items():
        shutil.copy2(path, assets / name)
        _require(sha(assets / name) == request["origins"][name]["sha256"], "冻结素材复制SHA校验失败")
    atomic_private(frozen, request)
    validate(queue, request)
    return request


def validate(queue, request, *, check_runtime=True):
    r = request
    _require(isinstance(r, dict), "冻结请求无效")
    digest = fingerprint({k: v for k, v in r.items() if k not in {"request_sha256", "render_id"}})
    _require(r.get("contract") == CONTRACT and r.get("request_sha256") == digest and r.get("render_id") == CONTRACT + "-" + digest[:20]
             and r.get("profile") == PROFILE and r.get("export") == EXPORT and r.get("publication") is False and r.get("cloud_calls") == 0, "正式模板冻结身份或本地调用边界已变化")
    project = WorkCatalog(queue.projects_root).project(r["project_id"])
    _require(read_json(project / "artifacts" / REQUEST_FILE) == r, "正式模板冻结请求已改变")
    paths = {n: regular_path(project / "assets" / CONTRACT / n, project) for n in r["origins"]}
    _require(all(_name(n) and sha(paths[n]) == row["sha256"] for n, row in r["origins"].items()), "冻结来源文件已改变")
    clock = _clock(paths[r["audio"]["voice"]])
    _require(clock == r["audio"]["voice_clock"], "完整口播样本时钟已变化")
    audio = _audio_plan({k: v for k, v in r["audio"].items() if k not in {"durationFrames", "voice_clock", "mix_profile"}}, paths, clock)
    _require(audio == r["audio"] and r["props"]["durationFrames"] == audio["durationFrames"], "冻结声音计划或口播总帧数已改变")
    validate_props(r["props"], clock["duration_seconds"])
    folder = project / "renders" / r["render_id"]
    receipt = read_json(folder / "result.json")
    _validate_sources(r["props"], audio, paths, r["provenance"], check_fonts=not bool(receipt))
    if receipt:
        _require(receipt.get("request_sha256") == digest and sha(folder / OUTPUT_FILE) == receipt.get("output_sha256")
                 and sha(folder / "quality.json") == receipt.get("quality_sha256"), "已完成成片或质量记录SHA已变化")
        if receipt.get("nomusic_output_sha256"):
            _require(sha(folder / NOMUSIC_FILE) == receipt["nomusic_output_sha256"] and sha(folder / "nomusic.wav") == receipt.get("nomusic_wav_sha256"), "无配乐备选成片或音轨已变化")
        quality = read_json(folder / "quality.json")
        if quality.get("audio_receipt_sha256"):
            _require(sha(folder / "audio-receipt.json") == quality["audio_receipt_sha256"]
                     and sha(folder / "public/master.wav") == read_json(folder / "audio-receipt.json").get("master_sha256"), "声音母带或制作记录已变化")
    elif check_runtime:
        _require(runtime() == r["runtime"], "模板源码或渲染器已变化，请冻结新请求")
    return project


def submit(queue, request):
    validate(queue, request)
    _require(_queue_sanitize(request, redact_local_paths=False) == request, "冻结请求与队列无凭据表示不一致，须从原输入重新冻结")
    return queue.submit(project_id=request["project_id"], kind=KIND, source="codex", priority="normal", parent_job_id=request["render_id"],
                        frozen_request=request, idempotency_key=CONTRACT + ":" + request["request_sha256"], start_paused=True)


def mix_master(audio, paths, output):
    """Build one exact frame-aligned master. Narration is never sped or cut."""
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg, _ = resolve_ffmpeg_pair()
    duration = audio["durationFrames"] / FPS
    samples = audio["durationFrames"] * (RATE // FPS)
    command = [ffmpeg, "-nostdin", "-y", "-v", "error", "-i", str(paths[audio["voice"]])]
    filters = [f"[0:a]aresample={RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={duration},asetpts=PTS-STARTPTS" + (",asplit=2[voice][duck]" if audio.get("music") else "[voice]")]
    labels, input_index = ["[voice]"], 1
    if audio.get("music"):
        if audio["loopMusic"]:
            command += ["-stream_loop", "-1"]
        command += ["-ss", str(audio["musicOffsetSeconds"]), "-i", str(paths[audio["music"]])]
        gain = 10 ** (audio["musicGainDb"] / 20)
        filters += [f"[{input_index}:a]aresample={RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS,volume={gain},apad,atrim=duration={duration},afade=t=in:d=0.15,afade=t=out:st={max(0, duration - .6)}:d=0.6[music]",
                    "[music][duck]sidechaincompress=threshold=0.025:ratio=5:attack=12:release=220[bed]"]
        labels.append("[bed]")
        input_index += 1
    for index, sound in enumerate(audio["sfx"]):
        command += ["-i", str(paths[sound["src"]])]
        delay = round(sound["atSeconds"] * RATE)
        filters.append(f"[{input_index}:a]aresample={RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS,volume={10 ** (sound.get('gainDb', -10) / 20)},adelay={delay}S:all=1[sfx{index}]")
        labels.append(f"[sfx{index}]")
        input_index += 1
    # End by sample count after loudnorm's internal oversampling. Timestamp-based
    # atrim after that resample can otherwise lose a processing block at EOF.
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0:dropout_transition=0,loudnorm=I=-16:TP=-2.5:LRA=11,aresample={RATE},apad=whole_len={samples},atrim=end_sample={samples},asetpts=N/SR/TB[out]")
    command += ["-filter_complex", ";".join(filters), "-map", "[out]", "-ar", str(RATE), "-ac", "2", "-c:a", "pcm_s16le", str(output)]
    subprocess.run(command, check=True, capture_output=True, creationflags=NO_WINDOW)
    with wave.open(str(output), "rb") as stream:
        _require((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes()) == (2, 2, RATE, audio["durationFrames"] * (RATE // FPS)), "声音母带未精确对齐成片帧时钟")
    return {"command": command, "master_sha256": sha(output), "voice_sha256": sha(paths[audio["voice"]]), "profile": MIX,
            "duration_frames": audio["durationFrames"], "voice_clock": audio["voice_clock"], "speech_stretched": False, "speech_reordered": False,
            "source_video_audio": "muted", "frame_padding_seconds": duration - audio["voice_clock"]["duration_seconds"]}


def run(queue, job):
    r = job["frozen_request"]
    try:
        _require(job["kind"] == KIND and job["project_id"] == r["project_id"], "正式模板队列身份不一致")
        project = validate(queue, r)
        folder = project / "renders" / r["render_id"]
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / OUTPUT_FILE
        if not read_json(folder / "result.json"):
            from tools.video.video_compose import VideoCompose
            from backlot.studio_investment_audio_v5 import measure_audio
            from lib.ffmpeg_locator import resolve_ffmpeg_pair
            ffmpeg, _ = resolve_ffmpeg_pair()
            public = folder / "public"
            public.mkdir(exist_ok=True)
            paths = {n: project / "assets" / CONTRACT / n for n in r["origins"]}
            browser_names = {m[k] for m in r["props"]["media"] for k in ("src", "thumbnail")} | set(r["props"]["fontAssets"].values()) | {p["src"] for p in r["props"].get("presenterClips", [])}
            for name in browser_names:
                shutil.copy2(paths[name], public / name)
            audio_receipt = mix_master(r["audio"], paths, public / "master.wav")
            no_music_plan = {k: deepcopy(v) for k, v in r["audio"].items() if k not in {"music", "musicGainDb", "musicOffsetSeconds", "loopMusic"}}
            no_music_receipt = mix_master(no_music_plan, paths, folder / "nomusic.wav")
            audio_receipt["nomusic"] = no_music_receipt
            atomic_private(folder / "audio-receipt.json", audio_receipt)
            for path in _template_files():
                target = folder / "template" / path.relative_to(TEMPLATE)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            atomic_private(folder / "props.json", r["props"])
            duration = r["props"]["durationFrames"] / FPS
            from tools.analysis.composition_validator import CompositionValidator
            composition = {"render_runtime": "remotion", "cuts": [{"id": s["id"], "in_seconds": s["from"] / FPS,
                           "out_seconds": (s["from"] + s["frames"]) / FPS} for s in r["props"]["scenes"]], "audio": {"narration": {"src": "master.wav"}}}
            atomic_private(folder / "composition-preflight.json", composition)
            preflight_result = CompositionValidator().execute({"composition_path": str(folder / "composition-preflight.json"), "assets_root": str(public)})
            atomic_private(folder / "preflight-result.json", preflight_result.data or {})
            _require(preflight_result.success and (preflight_result.data or {}).get("valid"), "正式模板素材或母带预检未通过")
            edits = {"render_runtime": "remotion", "composition_mode": "atelier", "renderer_family": "bespoke", "timeline": {"duration_seconds": duration},
                     "bespoke": {"entry": str(folder / "template/index.tsx"), "composition_id": COMPOSITION_ID,
                                 "art_direction": str(TEMPLATE / "VISUAL-DIRECTION.md"), "props_path": str(folder / "props.json"),
                                 "public_dir": str(public), "concurrency": 2, **PROFILE}}
            atomic_private(folder / "edit-decisions.json", edits)
            raw = folder / "mezzanine-crf1.mp4"
            result = VideoCompose().execute({"operation": "render", "output_path": str(raw), "edit_decisions": edits, "asset_manifest": {"assets": []}, "script_text": ""})
            atomic_private(folder / "render-report.json", {"success": result.success, "data": result.data, "error": str(result.error) if result.error else None})
            _require(result.success, "本地正式模板渲染失败：" + str(result.error))
            command = [ffmpeg, "-nostdin", "-y", "-v", "error", "-i", str(raw), "-i", str(public / "master.wav"), "-map", "0:v:0", "-map", "1:a:0", "-t", str(duration),
                       "-c:v", "libx264", "-preset", "slow", "-b:v", "20500k", "-minrate", "20500k", "-maxrate", "20500k", "-bufsize", "2000k", "-x264-params", "nal-hrd=cbr:force-cfr=1:filler=1",
                       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", str(RATE), "-ac", "2", "-movflags", "+faststart", str(output)]
            subprocess.run(command, check=True, capture_output=True, creationflags=NO_WINDOW)
            info, measured = media_probe(output), measure_audio(output)
            video, audio = info.get("video") or {}, info.get("audio") or {}
            _require(video.get("width") == WIDTH and video.get("height") == HEIGHT and video.get("codec_name") == "h264" and video.get("pix_fmt") == "yuv420p"
                     and abs(float(Fraction(video.get("avg_frame_rate", "0/1"))) - FPS) < .001 and int(video.get("nb_frames", 0)) == r["props"]["durationFrames"]
                     and abs(info["duration"] - duration) <= .08 and int(video.get("bit_rate", 0)) >= EXPORT["minimum_measured_bitrate"]
                     and str(audio.get("sample_rate")) == str(RATE) and audio.get("channels") == 2 and measured["true_peak_dbtp"] <= -1.5, "成片帧数、码率、尺寸、声道或峰值未通过")
            subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(output), "-f", "null", "-"], check=True, capture_output=True, creationflags=NO_WINDOW)
            no_music_output = folder / NOMUSIC_FILE
            no_music_command = [ffmpeg, "-nostdin", "-y", "-v", "error", "-i", str(output), "-i", str(folder / "nomusic.wav"), "-map", "0:v:0", "-map", "1:a:0",
                                "-t", str(duration), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", str(RATE), "-ac", "2", "-movflags", "+faststart", str(no_music_output)]
            subprocess.run(no_music_command, check=True, capture_output=True, creationflags=NO_WINDOW)
            no_music_audio = measure_audio(no_music_output)
            _require(no_music_audio["true_peak_dbtp"] <= -1.5, "无配乐备选音轨峰值未通过")
            subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(no_music_output), "-f", "null", "-"], check=True, capture_output=True, creationflags=NO_WINDOW)
            atomic_private(folder / "quality.json", {"media": info, "video_stream": video, "audio": measured, "full_decode": "passed", "render_command": (result.data or {}).get("render_command"),
                           "export_command": command, "audio_receipt_sha256": sha(folder / "audio-receipt.json"), "source_audio": "muted", "voice_clock": r["audio"]["voice_clock"],
                           "nomusic": {"audio": no_music_audio, "full_decode": "passed", "export_command": no_music_command, "video": "stream-copy-from-primary"},
                           "original_assets_sha_verified": True, "visual_review": "pending", "continuous_watching": "pending", "device_listening": "pending", "avatar_lip_sync": "pending" if r["props"].get("presenterClips") else "not-applicable"})
            validate(queue, r)
            atomic_private(folder / "result.json", {"request_sha256": r["request_sha256"], "output_sha256": sha(output), "nomusic_output_sha256": sha(no_music_output),
                           "nomusic_wav_sha256": sha(folder / "nomusic.wav"), "quality_sha256": sha(folder / "quality.json"), "cloud_calls": 0, "publication": False})
        work = WorkCatalog(queue.projects_root).register(r["project_id"], output, work_key="main", mode="manual", event_id=job["job_id"], quality_passed=False, actor=CONTRACT,
                title=r["title"], summary="口播主钟4:5可复用动效模板；本地渲染；实测≥20Mbps；视听复核待完成；未发布")
        version = next(v for v in work["versions"] if v["sha256"] == sha(output))
        return {"status": "completed", "stage": "可复用口播动效成片已合成，等待观看", "result": {"output_path": str(output), "output_sha256": sha(output),
                "work_id": work["work_id"], "version_id": version["version_id"], "qa_status": "pending", "cloud_calls": 0}}
    except (WorkError, subprocess.SubprocessError, OSError, ValueError, KeyError) as exc:
        return {"status": "failed", "stage": str(exc)[:1200], "error": {"type": "HumProduction", "message": str(exc)[:1200]}, "retryable": True, "safe_resume_point": "hum_production"}
