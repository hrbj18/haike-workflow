"""Queue-owned investment films with one source-AV EDL and real evidence.

The fixed 12s style-lab and older source-art contracts remain independent.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import wave

from backlot.studio import atomic_private
from backlot.studio_investment_recompose import KIND, fingerprint
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkCatalog, WorkError, read_json, regular_path, sha

CONTRACT = "investment-full-v1"
COMPOSITION_ID = "HaikeInvestmentFull"
TEMPLATE_FOLDER = "investment-full-v1"
PREFIX = "local-investment-full-"
FPS, FRAMES, DURATION, RATE = 30, 900, 30, 24000
SAMPLES_PER_FRAME = RATE // FPS
PALETTES = {7: "blue-beige", 8: "cyan-charcoal", 9: "black-pink"}
INPUTS = ("source.mp4", "source-cues.json", "source-edits.json", "storyboard.json", "audio-plan.json")
DERIVED = {"source-audio.wav", "source-audio-receipt.json", "edited-voice.wav", "voice-edit-receipt.json",
           "mixed-master.wav", "audio-mix-plan.json", "audio-mix-receipt.json", "music-pre-duck.wav", "music-post-duck.wav"}
EXECUTABLE_SUFFIXES = {".tsx", ".ts", ".css", ".ttf", ".ttc", ".otf", ".woff", ".woff2",
                       ".png", ".jpg", ".jpeg", ".webp", ".svg", ".wav"}


def _timeline_frames(value):
    if type(value) is not int or value not in {FRAMES, 1350}:
        raise WorkError("完整招商支持900帧；08青炭可显式扩展为1350帧，禁止隐式改钟")
    return value


def _edit_frames(edit):
    return _timeline_frames(edit["content_end_frame"] + edit["tail_hold_frames"])


def render_profile(frames=FRAMES):
    frames = _timeline_frames(frames)
    return {"id": "investment-full-4x5-20mbps-v1", "ratio": "4x5", "width": 1440, "height": 1800,
            "fps": FPS, "duration_in_frames": frames, "avatar_preparation": "source-byte-copy-edl",
            "codec": "h264", "video_bitrate": "22M" if frames == 1350 else "20M", "rate_control": "cbr-hrd" if frames == 1350 else "abr", "crf": None,
            "image_format": "png", "x264_preset": "slow", "pixel_format": "yuv420p", "scale": 1,
            "final_video": "stream-copy"}


def _root():
    return Path(__file__).resolve().parents[1]


def _template():
    return _root() / "templates" / TEMPLATE_FOLDER


def _template_files():
    folder = _template()
    if not (folder / "index.tsx").is_file() or not (folder / "layout.json").is_file():
        raise WorkError("完整招商模板尚未冻结index.tsx与layout.json")
    return sorted(p for p in folder.rglob("*") if p.is_file()
                  and (p.suffix.lower() in EXECUTABLE_SUFFIXES or p.name == "layout.json"))


def _runtime():
    from backlot import studio_composition, studio_investment_audio_v5
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg, probe = resolve_ffmpeg_pair()
    root = _root()
    paths = set(_template_files()) | {Path(__file__), Path(studio_composition.__file__),
        Path(studio_investment_audio_v5.__file__), root / "backlot/production_queue_worker.py",
        root / "tools/video/video_compose.py", root / "tools/base_tool.py", Path(ffmpeg), Path(probe)}
    paths |= {p for name in ("msyh.ttc", "msyhbd.ttc", "simsun.ttc", "consola.ttf")
              if (p := Path("C:/Windows/Fonts") / name).is_file()}
    return {str(p.resolve()): sha(p) for p in sorted(paths)}


def _number(value):
    return type(value) in {int, float} and math.isfinite(value)


def _text(value, maximum, label, *, empty=False, lines=1):
    if (not isinstance(value, str) or not (0 if empty else 1) <= len(value.strip()) <= maximum
            or len(value.split("\n")) > lines or any(ord(c) < 32 and c != "\n" for c in value)):
        raise WorkError(label + "文字、换行或长度无效")
    return value.strip()


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", value):
        raise WorkError("素材或章节id需1至48个字母、数字、短横线或下划线")
    return value


def _evidence(value):
    if isinstance(value, str):
        return _text(value, 2048, "素材审看证据")
    if isinstance(value, dict) and isinstance(value.get("scope"), str):
        _text(value["scope"], 2048, "素材审看范围")
        try:
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError):
            raise WorkError("素材证据须为有限JSON对象") from None
        if len(encoded.encode("utf-8")) <= 12000:
            return deepcopy(value)
    raise WorkError("素材审看证据须为文字或含scope的来源JSON对象")


def _source(value, suffixes):
    path = Path(value).expanduser()
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or path.suffix.lower() not in suffixes:
        raise WorkError("输入须为存在的本机绝对文件路径，格式匹配且非符号链接")
    return path.resolve()


def _copy(source, target):
    source, target = Path(source), Path(target)
    if target.exists():
        if sha(source) != sha(target):
            raise WorkError("已有冻结文件内容不同，禁止覆盖；请新prepare")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _frames(start, end, limit=FRAMES):
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= limit:
        raise WorkError("编辑帧区间必须是合法整数、左闭右开且位于时间线内")


def _choice(number, palette, ratio):
    if type(number) is not int or PALETTES.get(number) != palette or ratio != "4x5":
        raise WorkError("本合同仅支持4x5及07蓝米、08青炭、09黑粉的固定对应配色")


def _source_clock(info):
    video, audio = info.get("video") or {}, info.get("audio") or {}
    try:
        duration = float(video.get("duration") or info["duration"])
    except (TypeError, KeyError, ValueError):
        raise WorkError("无法核对完整原片视频时钟") from None
    if not video or audio.get("codec_name") != "aac" or not math.isfinite(duration) or not 0 < duration <= 120:
        raise WorkError("需120秒内带AAC原声、可核对视频流时钟的完整原MP4")
    return duration


def normalize_cues(value, source_sha, duration):
    if (not isinstance(value, dict) or value.get("source_video_sha256") != source_sha
            or value.get("timing_basis") not in {"cached_asr", "manual_reviewed"}
            or not isinstance(value.get("evidence"), str) or not value["evidence"].strip()):
        raise WorkError("源字幕须绑定原视频SHA、真实时钟类型和证据")
    raw = value.get("cues")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 2000:
        raise WorkError("完整原片需1至2000条真实字幕")
    cues, previous = [], 0
    for cue in raw:
        if not isinstance(cue, dict) or set(cue) != {"start", "end", "text"}:
            raise WorkError("源字幕条目只接受start/end秒数与text")
        start, end, text = cue["start"], cue["end"], cue["text"]
        if (not _number(start) or not _number(end) or not previous <= start < end <= duration + .001
                or not isinstance(text, str) or not 1 <= len(text.split("\n")) <= 2
                or any(not 1 <= len(line) <= 18 for line in text.split("\n"))
                or any(ord(c) < 32 and c != "\n" for c in text)):
            raise WorkError("字幕须按真实源钟有序、无重叠且至多两行每行18字")
        cues.append({"start": start, "end": end, "text": text})
        previous = end
    return cues


def normalize_edits(value, cues, source_sha, cues_sha, video_duration):
    fields = {"version", "source_video_sha256", "source_cues_sha256", "fps", "target_duration_in_frames",
              "tail_hold_frames", "segments"}
    if (not isinstance(value, dict) or set(value) != fields or value["version"] != "source-edits-v1"
            or value["source_video_sha256"] != source_sha or value["source_cues_sha256"] != cues_sha
            or value["fps"] != FPS
            or type(value["tail_hold_frames"]) is not int or not 0 <= value["tail_hold_frames"] <= 60):
        raise WorkError("EDL须绑定源片和源cue SHA、30fps及显式0至60帧尾卡")
    frames = _timeline_frames(value["target_duration_in_frames"])
    raw = value["segments"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 80:
        raise WorkError("EDL需1至80个有来源的连续剪接段")
    segments, target_cues, cue_map, masks = [], [], [], []
    identifiers, previous_source, previous_cue, target = set(), 0, -1, 0
    source_limit = math.ceil(video_duration * FPS - 1e-9)
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"id", "source_start_frame", "source_end_frame", "fromCue", "toCue", "reason"}:
            raise WorkError("EDL段仅支持id、源编辑帧、源cue索引及真实剪接理由")
        identifier = _id(item["id"])
        if identifier in identifiers:
            raise WorkError("EDL段id不能重复")
        identifiers.add(identifier)
        start, end, first, last = (item[k] for k in ("source_start_frame", "source_end_frame", "fromCue", "toCue"))
        _frames(start, end, source_limit)
        if (start < previous_source or (end - 1) / FPS >= video_duration
                or type(first) is not int or type(last) is not int or not previous_cue < first <= last < len(cues)):
            raise WorkError("EDL源区间或cue索引须递增且每个画面时间戳在原片内")
        reason = _text(item["reason"], 1000, "剪接理由")
        begin, finish = start / FPS, end / FPS
        segment = {"id": identifier, "sourceStartFrame": start, "sourceEndFrame": end,
                   "startFrame": target, "endFrame": target + end - start,
                   "fromCue": first, "toCue": last, "reason": reason}
        for index, cue in enumerate(cues):
            if first <= index <= last:
                if cue["start"] < begin - 1e-9 or cue["end"] > finish + 1e-9:
                    raise WorkError("所选真实cue必须完整保留，不可裁词或拉伸")
                mapped = {"start": target / FPS + cue["start"] - begin,
                          "end": target / FPS + cue["end"] - begin, "text": cue["text"]}
                target_cues.append(mapped)
                cue_map.append({"sourceCueIndex": index, "targetCueIndex": len(target_cues) - 1,
                    "segmentId": identifier, "sourceStartMs": cue["start"] * 1000, "sourceEndMs": cue["end"] * 1000,
                    "targetStartMs": mapped["start"] * 1000, "targetEndMs": mapped["end"] * 1000})
            else:
                left, right = max(begin, cue["start"]), min(finish, cue["end"])
                if right <= left + 1e-9:
                    continue
                prefix = index < first and cue["start"] < begin and right <= cues[first]["start"]
                suffix = index > last and cue["end"] > finish and left >= cues[last]["end"]
                if not (prefix or suffix) or right - left >= 1 / FPS - 1e-9:
                    raise WorkError("被删cue只允许首尾不足一帧的量化余量静音，禁止内部漏句或大段mask")
                masks.append({"segmentId": identifier, "sourceCueIndex": index,
                    "sourceStartMs": left * 1000, "sourceEndMs": right * 1000,
                    "targetStartMs": (target / FPS + left - begin) * 1000,
                    "targetEndMs": (target / FPS + right - begin) * 1000,
                    "sourceStartSample": math.ceil(left * RATE - 1e-9),
                    "sourceEndSample": math.ceil(right * RATE - 1e-9),
                    "reason": "excluded adjacent cue quantization remainder at " + ("segment start" if prefix else "segment end")})
        segments.append(segment)
        target += end - start
        previous_source, previous_cue = end, last
    if target + value["tail_hold_frames"] != frames or not target_cues:
        raise WorkError("EDL内容帧加显式尾卡必须覆盖声明的全部帧，且须保留真实口播")
    return {"segments": segments, "content_end_frame": target, "tail_hold_frames": value["tail_hold_frames"],
            "cues": target_cues, "cue_map": cue_map, "edge_masks": masks}


def _scene_name(index, item):
    return f"scene-{index:02d}-{item['id']}" + Path(item["path"]).suffix.lower()


def _presenter_video(value, chapters, *, imported=None):
    if not isinstance(value, dict) or set(value) != {"path", "sha256", "sourceLabel", "evidence", "segments"}:
        raise WorkError("人物替换轨须提供源视频、SHA、来源、证据和精确分段")
    name = "presenter-override.mp4"
    source = _source(value["path"], {".mp4"}) if imported is None else regular_path(imported / name, imported)
    if not re.fullmatch(r"[a-f0-9]{64}", str(value["sha256"])) or sha(source) != value["sha256"]:
        raise WorkError("人物替换源SHA不匹配")
    info = media_probe(source)
    available = float((info.get("video") or {}).get("duration") or info.get("duration") or 0)
    if not info.get("video") or not math.isfinite(available) or available <= 0:
        raise WorkError("人物替换源视频时钟无效")
    windows = []
    for chapter in chapters:
        if chapter["kind"] == "presenter":
            if windows and windows[-1][1] == chapter["startFrame"]:
                windows[-1][1] = chapter["endFrame"]
            else:
                windows.append([chapter["startFrame"], chapter["endFrame"]])
    segments = value["segments"]
    if not isinstance(segments, list) or len(segments) != len(windows) or not windows:
        raise WorkError("人物替换轨必须精确覆盖全部实际出镜区间")
    ids, previous_source = set(), 0
    for item, (start, end) in zip(segments, windows):
        if not isinstance(item, dict) or set(item) != {"id", "startFrame", "endFrame", "sourceOffsetFrames"}:
            raise WorkError("人物替换分段字段无效")
        identifier = _id(item["id"])
        if (identifier in ids or type(item["startFrame"]) is not int or type(item["endFrame"]) is not int
                or item["startFrame"] != start or item["endFrame"] != end
                or type(item["sourceOffsetFrames"]) is not int or item["sourceOffsetFrames"] < previous_source):
            raise WorkError("人物替换不能漏段、跨入图文素材或重复源画面")
        ids.add(identifier)
        finish = item["sourceOffsetFrames"] + end - start
        if (finish - 1) / FPS >= available:
            raise WorkError("人物替换源长度不足，禁止循环、冻结或变速补帧")
        previous_source = finish
    return {**deepcopy(value), "path": str(source.resolve()), "source_name": name,
        "sourceLabel": _text(value["sourceLabel"], 160, "人物替换来源"), "evidence": _evidence(value["evidence"])}


def normalize_storyboard(value, edit, *, imported=None):
    frames = _edit_frames(edit)
    if (not isinstance(value, dict) or set(value) not in ({"version", "chapters", "shots", "graphics"},
            {"version", "chapters", "shots", "graphics", "presenterVideo"})
            or value["version"] != "investment-full-storyboard-v1"):
        raise WorkError("图文分镜须使用investment-full-storyboard-v1固定字段")
    raw = value["chapters"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 30:
        raise WorkError("图文分镜需1至30个章节")
    chapters, ids, previous = [], set(), 0
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"id", "startFrame", "endFrame", "kind", "heading", "deck", "points"}:
            raise WorkError("章节字段不完整或含未声明参数")
        identifier = _id(item["id"])
        _frames(item["startFrame"], item["endFrame"], frames)
        if identifier in ids or item["startFrame"] != previous or item["kind"] not in {"presenter", "media", "graphic"}:
            raise WorkError("章节id须唯一且连续覆盖时间线，kind固定")
        ids.add(identifier)
        if not isinstance(item["heading"], list) or not 1 <= len(item["heading"]) <= 2:
            raise WorkError("章节标题须1至2行")
        if not isinstance(item["points"], list) or len(item["points"]) > 4:
            raise WorkError("章节要点最多4项")
        chapters.append({**deepcopy(item), "heading": [_text(t, 18, "章节标题") for t in item["heading"]],
                         "deck": _text(item["deck"], 80, "章节说明", empty=True, lines=2),
                         "points": [_text(t, 32, "章节要点") for t in item["points"]]})
        previous = item["endFrame"]
    if previous != frames:
        raise WorkError("章节必须完整覆盖声明的时间线")
    shots, ids, previous = [], set(), 0
    if not isinstance(value["shots"], list) or len(value["shots"]) > 80:
        raise WorkError("实拍轨最多80段")
    for index, item in enumerate(value["shots"]):
        if not isinstance(item, dict) or set(item) != {"id", "path", "sha256", "kind", "startFrame", "endFrame", "sourceOffsetFrames", "fit", "sourceLabel", "evidence"}:
            raise WorkError("实拍素材字段不完整或含未声明参数")
        identifier = _id(item["id"])
        _frames(item["startFrame"], item["endFrame"], edit["content_end_frame"])
        if (identifier in ids or item["startFrame"] < previous or item["endFrame"] - item["startFrame"] > 120
                or type(item["sourceOffsetFrames"]) is not int or item["sourceOffsetFrames"] < 0
                or item["fit"] not in {"contain", "cover"} or item["kind"] not in {"image", "video"}
                or not re.fullmatch(r"[a-f0-9]{64}", str(item["sha256"]))):
            raise WorkError("实拍须唯一有序、单次不超过4秒、适配方式及源偏移合法")
        ids.add(identifier)
        original = _source(item["path"], {".mp4", ".mov", ".png", ".jpg", ".jpeg", ".webp"}) if imported is None else None
        name = _scene_name(index, item)
        source = original if imported is None else regular_path(imported / name, imported)
        if sha(source) != item["sha256"]:
            raise WorkError("实拍或图片源SHA变化")
        if item["kind"] == "video":
            if source.suffix.lower() not in {".mp4", ".mov"}:
                raise WorkError("video素材扩展名不匹配")
            info = media_probe(source)
            try:
                available = float((info.get("video") or {}).get("duration") or info["duration"])
            except (TypeError, ValueError, KeyError):
                raise WorkError("实拍视频时钟无效") from None
            count = item["endFrame"] - item["startFrame"]
            if not info.get("video") or not math.isfinite(available) or (item["sourceOffsetFrames"] + count - 1) / FPS >= available:
                raise WorkError("实拍长度不足，禁止循环、补帧或变速")
        else:
            if item["sourceOffsetFrames"] != 0 or source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                raise WorkError("图片offset须为0且格式匹配")
            try:
                from PIL import Image
                with Image.open(source) as image:
                    image.verify()
            except Exception:
                raise WorkError("实拍图片不能读取") from None
        shots.append({**deepcopy(item), "path": str(source.resolve()), "source_name": name,
                      "sourceLabel": _text(item["sourceLabel"], 160, "素材来源"),
                      "evidence": _evidence(item["evidence"])})
        previous = item["endFrame"]
    if not shots:
        raise WorkError("完整招商本期必须包含实际门店素材，不能以人物替代实拍")
    graphics, ids = [], set()
    if not isinstance(value["graphics"], list) or not 1 <= len(value["graphics"]) <= 40:
        raise WorkError("完整招商需1至40个有源cue支持的图文信息对象")
    by_chapter = {c["id"]: c for c in chapters}
    by_source = {c["sourceCueIndex"]: c for c in edit["cue_map"]}
    for item in value["graphics"]:
        if not isinstance(item, dict) or set(item) != {"id", "chapterId", "kind", "heading", "items", "sourceCueIndices"}:
            raise WorkError("图形信息字段不完整或含未声明参数")
        identifier = _id(item["id"])
        if identifier in ids or item["chapterId"] not in by_chapter or item["kind"] not in {"metric", "list", "process", "offer"}:
            raise WorkError("图形id、关联章节或种类无效")
        ids.add(identifier)
        indices = item["sourceCueIndices"]
        if (not isinstance(indices, list) or not indices or any(type(i) is not int or i not in by_source for i in indices)
                or indices != sorted(set(indices)) or not isinstance(item["items"], list) or not 1 <= len(item["items"]) <= 6):
            raise WorkError("图形须引用已保留的源cue索引并提供1至6项信息")
        chapter = by_chapter[item["chapterId"]]
        # An explicit final offer can quote the spoken CTA immediately before a
        # deliberate silent end-card hold; other graphics overlap their cue.
        for index in indices:
            cue = by_source[index]
            overlaps = cue["targetStartMs"] < chapter["endFrame"] / FPS * 1000 and cue["targetEndMs"] > chapter["startFrame"] / FPS * 1000
            tail_offer = (item["kind"] == "offer" and chapter is chapters[-1]
                          and chapter["startFrame"] <= edit["content_end_frame"] and indices[-1] == max(by_source))
            if not overlaps and not tail_offer:
                raise WorkError("图形源cue须对应所在章节；尾卡只可复述本片真实末尾CTA")
        graphics.append({**deepcopy(item), "heading": _text(item["heading"], 32, "图形标题", lines=2),
                         "items": [_text(t, 48, "图形条目", lines=2) for t in item["items"]]})
    if edit["tail_hold_frames"]:
        final = chapters[-1]
        if (final["kind"] != "graphic" or final["startFrame"] > edit["content_end_frame"]
                or not any(g["chapterId"] == final["id"] and g["kind"] == "offer" for g in graphics)):
            raise WorkError("显式尾卡必须由覆盖内容末端至900帧的graphic/offer章节承载")
    for chapter in chapters:
        chapter_shots = [s for s in shots if s["startFrame"] < chapter["endFrame"] and s["endFrame"] > chapter["startFrame"]]
        chapter_graphics = [g for g in graphics if g["chapterId"] == chapter["id"]]
        if chapter["kind"] == "media":
            cursor = chapter["startFrame"]
            for shot in chapter_shots:
                if shot["startFrame"] != cursor or shot["endFrame"] > chapter["endFrame"]:
                    raise WorkError("media章节实拍须连续覆盖，不能空白或跨章节")
                cursor = shot["endFrame"]
            if cursor != chapter["endFrame"] or chapter_graphics:
                raise WorkError("media章节须由完整实拍轨覆盖，不混用graphic槽")
        elif chapter_shots:
            raise WorkError("实拍仅出现在media章节，禁止跨入人物或图文页")
        if chapter["kind"] == "graphic" and len(chapter_graphics) != 1:
            raise WorkError("graphic章节必须且只能关联一个图形对象")
        if chapter["kind"] == "presenter" and chapter_graphics:
            raise WorkError("presenter章节不接受未显示的graphic槽")
    result = {"version": value["version"], "chapters": chapters, "shots": shots, "graphics": graphics}
    if "presenterVideo" in value:
        result["presenterVideo"] = _presenter_video(value["presenterVideo"], chapters, imported=imported)
    return result


def _command(args, timeout=240):
    from lib.subprocess_window import no_window_kwargs
    result = subprocess.run([str(a) for a in args], capture_output=True, timeout=timeout, **no_window_kwargs())
    if result.returncode:
        raise WorkError("完整招商本地媒体处理失败，原始输入和检查点已保留", "unavailable")
    return result


def _pcm(path):
    try:
        with wave.open(str(path), "rb") as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, RATE, "NONE"):
                raise ValueError()
            samples = stream.getnframes()
            data = stream.readframes(samples)
            if not 0 < samples <= 121 * RATE or len(data) != samples * 2:
                raise ValueError()
    except (wave.Error, OSError, EOFError, ValueError):
        raise WorkError("原声须为完整24kHz PCM16单声道音轨，不能增益或变速") from None
    return data, samples


def _write_pcm(path, data):
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        stream.writeframes(data)


def _extract_audio(video, target):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg, _ = resolve_ffmpeg_pair()
    receipt_path = target.parent / "source-audio-receipt.json"
    if not target.exists():
        pending = target.with_name("source-audio.pending.wav")
        command = [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", video, "-map", "0:a:0", "-vn",
                   "-ar", RATE, "-ac", 1, "-c:a", "pcm_s16le", pending]
        _command(command)
        _, samples = _pcm(pending)
        pending.replace(target)
        atomic_private(receipt_path, {"version": "source-audio-pcm-v1", "source_video_sha256": sha(video),
            "pcm_sha256": sha(target), "samples": samples, "sample_rate": RATE, "gain_db": 0, "speed": 1,
            "command": [str(a) for a in command], "cloud_calls": 0})
    data, samples = _pcm(target)
    receipt = read_json(receipt_path)
    if (receipt.get("version") != "source-audio-pcm-v1" or receipt.get("source_video_sha256") != sha(video)
            or receipt.get("pcm_sha256") != sha(target) or receipt.get("samples") != samples
            or receipt.get("sample_rate") != RATE or receipt.get("gain_db") != 0 or receipt.get("speed") != 1
            or receipt.get("cloud_calls") != 0):
        raise WorkError("完整原声PCM来源回执不匹配")
    return data, samples


def edited_pcm(data, edit):
    """Retain source sample bytes; zero only declared excluded edge fragments/tail."""
    parts, intervals = [], []
    available = len(data) // 2
    for segment in edit["segments"]:
        first, last = segment["sourceStartFrame"] * SAMPLES_PER_FRAME, segment["sourceEndFrame"] * SAMPLES_PER_FRAME
        if last > available:
            raise WorkError("EDL源PCM末端不足，请将源端选在floor完整帧；不隐式补零")
        part = bytearray(data[first * 2:last * 2])
        for mask in edit["edge_masks"]:
            if mask["segmentId"] != segment["id"]:
                continue
            left, right = mask["sourceStartSample"] - first, mask["sourceEndSample"] - first
            if not 0 <= left < right <= last - first or right - left >= SAMPLES_PER_FRAME:
                raise WorkError("边界余量静音样本越界或超过一帧")
            part[left * 2:right * 2] = b"\0" * ((right - left) * 2)
            intervals.append({**deepcopy(mask), "targetStartSample": segment["startFrame"] * SAMPLES_PER_FRAME + left,
                              "targetEndSample": segment["startFrame"] * SAMPLES_PER_FRAME + right,
                              "zeroedSamples": right - left})
        parts.append(bytes(part))
    tail_samples = edit["tail_hold_frames"] * SAMPLES_PER_FRAME
    output = b"".join(parts) + b"\0" * (tail_samples * 2)
    frames = _edit_frames(edit)
    if len(output) != frames * SAMPLES_PER_FRAME * 2:
        raise WorkError("EDL PCM输出必须与声明帧钟逐样本一致，不自动拉伸")
    return output, {"version": "source-edl-pcm-v1", "sample_rate": RATE, "channels": 1,
        "sample_width": 2, "samples_per_edit_frame": SAMPLES_PER_FRAME, "edited_samples": frames * SAMPLES_PER_FRAME,
        "content_end_frame": edit["content_end_frame"], "tail_hold_frames": edit["tail_hold_frames"],
        "tail_zero_samples": tail_samples, "source_cap_zero_samples": 0, "edge_zero_intervals": intervals,
        "edge_zero_samples": sum(i["zeroedSamples"] for i in intervals), "segments": deepcopy(edit["segments"]),
        "selected_cue_samples_unchanged": True, "gain_db": 0, "speed": 1, "cloud_calls": 0}


def _edit_voice(folder, edit, *, write=False):
    data, _ = _pcm(folder / "source-audio.wav")
    output, receipt = edited_pcm(data, edit)
    target, path = folder / "edited-voice.wav", folder / "voice-edit-receipt.json"
    receipt.update(source_video_sha256=sha(folder / "source.mp4"), source_audio_sha256=sha(folder / "source-audio.wav"),
                   source_edits_sha256=sha(folder / "source-edits.json"), edited_pcm_sha256=hashlib.sha256(output).hexdigest())
    if write and not target.exists():
        pending = target.with_name("edited-voice.pending.wav")
        _write_pcm(pending, output)
        pending.replace(target)
        receipt["edited_voice_sha256"] = sha(target)
        atomic_private(path, receipt)
    actual, _ = _pcm(target)
    receipt["edited_voice_sha256"] = sha(target)
    if actual != output or read_json(path) != receipt:
        raise WorkError("EDL音频、所选原句或逐项静音证据与冻结来源不一致")
    return receipt


def _captions(cues):
    return [{**c, "startMs": c["start"] * 1000, "endMs": c["end"] * 1000,
             "timestampMs": None, "confidence": None} for c in cues]


def _sound_plan(raw, edit, storyboard, *, imported=None):
    from backlot.studio_investment_audio_v5 import normalize_plan
    chapters = [{"start": c["startFrame"] / FPS, "end": c["endFrame"] / FPS} for c in storyboard["chapters"]]
    return normalize_plan(raw, _captions(edit["cues"]), [], chapters, _edit_frames(edit) / FPS, imported=imported)


def _verify_audio(folder, plan, runtime):
    from backlot import studio_investment_audio_v5 as sound
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg, _ = resolve_ffmpeg_pair()
    receipt, mix = read_json(folder / "audio-mix-receipt.json"), read_json(folder / "audio-mix-plan.json")
    duration = plan["duration"]
    _timeline_frames(round(duration * FPS))
    identity = fingerprint({"voice_sha256": sha(folder / "edited-voice.wav"), "plan": plan, "duration": duration,
        "mixer_sha256": runtime.get(str(Path(sound.__file__).resolve())), "ffmpeg_sha256": runtime.get(str(Path(ffmpeg).resolve()))})
    if (mix.get("identity") != identity or receipt.get("identity") != identity or mix.get("plan") != plan
            or receipt.get("input_voice_sha256") != sha(folder / "edited-voice.wav")
            or receipt.get("audio_mix_plan_sha256") != sha(folder / "audio-mix-plan.json")
            or receipt.get("master_sha256") != sha(folder / "mixed-master.wav")
            or receipt.get("duration") != duration or receipt.get("voice_gain_db") != -2.5
            or receipt.get("profile") != sound.PROFILE or receipt.get("cloud_calls") != 0
            or receipt.get("aac_check", {}).get("true_peak_dbtp", 99) > -1.5):
        raise WorkError("完整招商原声EDL、真实混音计划、母带或峰值证据不匹配")
    sound.verify_master(folder / "mixed-master.wav", receipt["master_sha256"], duration)
    return receipt


def _props(request):
    from backlot.studio_investment_audio_v5 import sound_events
    storyboard, edit = request["storyboard"], request["source_edits"]
    frames = _edit_frames(edit)
    props = {"templateNumber": request["template_number"], "paletteVariant": request["palette_variant"],
        "ratio": "4x5", "width": 1440, "height": 1800, "fps": FPS, "duration": frames / FPS,
        "durationInFrames": frames, "contentEndFrame": edit["content_end_frame"], "tailHoldFrames": edit["tail_hold_frames"],
        "avatarSrc": "source.mp4", "audioSrc": "mixed-master.wav", "brand": request["brand"],
        "sourceEdits": [{k: s[k] for k in ("id", "sourceStartFrame", "sourceEndFrame", "startFrame", "endFrame")}
                        for s in edit["segments"]], "cues": _captions(request["cues"]),
        "chapters": deepcopy(storyboard["chapters"]),
        "shots": [{**{k: s[k] for k in ("id", "kind", "startFrame", "endFrame", "sourceOffsetFrames", "fit", "sourceLabel")},
                   "src": s["source_name"]} for s in storyboard["shots"]],
        "graphics": deepcopy(storyboard["graphics"]), "soundEvents": sound_events(request["audio_plan"])}
    if "presenterVideo" in storyboard:
        track = storyboard["presenterVideo"]
        props["presenterVideo"] = {"src": track["source_name"], "segments": deepcopy(track["segments"])}
    return props


def prepare(queue, source_video, source_cues_json, edits_json, storyboard_json, audio_plan_json, *,
            template_number, palette_variant, ratio="4x5", title, brand="海客AI社区服务站"):
    _choice(template_number, palette_variant, ratio)
    title, brand = _text(title, 120, "作品标题"), _text(brand, 24, "品牌")
    paths = [_source(p, {".mp4"} if i == 0 else {".json"}) for i, p in enumerate(
        (source_video, source_cues_json, edits_json, storyboard_json, audio_plan_json))]
    originals = dict(zip(INPUTS, paths))
    video, cue_file, edl_file, board_file, plan_file = paths
    info = media_probe(video)
    video_duration = _source_clock(info)
    source_cues = normalize_cues(read_json(cue_file), sha(video), max(video_duration, float(info.get("duration") or 0)))
    edit = normalize_edits(read_json(edl_file), source_cues, sha(video), sha(cue_file), video_duration)
    frames = _edit_frames(edit)
    if frames != FRAMES and template_number != 8:
        raise WorkError("45秒扩展仅适用于08青炭；其他模板保持30秒")
    storyboard = normalize_storyboard(read_json(board_file), edit)
    for scene in storyboard["shots"]:
        originals[scene["source_name"]] = Path(scene["path"])
    if "presenterVideo" in storyboard:
        track = storyboard["presenterVideo"]
        originals[track["source_name"]] = Path(track["path"])
    plan = _sound_plan(read_json(plan_file), edit, storyboard)
    for item in [plan["music"], *plan["assets"]]:
        originals[item["source_name"]] = Path(item["path"])
    origins = {name: {"path": str(path), "sha256": sha(path)} for name, path in originals.items()}
    runtime = _runtime()
    identity = fingerprint({"contract": CONTRACT, "origins": origins, "runtime": runtime,
        "template_number": template_number, "palette_variant": palette_variant, "ratio": ratio, "title": title, "brand": brand})
    project_id = "studio-" + identity[:16]
    project = queue.projects_root / project_id
    frozen = project / "artifacts/investment-full-request.json"
    if frozen.exists():
        request = read_json(frozen)
        validate(queue, request)
        return request
    from lib.checkpoint import init_project
    from backlot.studio_investment_audio_v5 import build_audio_master
    init_project(project_id, title=title, pipeline_type="animated-explainer", pipeline_dir=queue.projects_root)
    folder = project / "assets/investment-full"
    folder.mkdir(parents=True, exist_ok=True)
    for name, path in originals.items():
        _copy(path, folder / name)
    _, samples = _extract_audio(folder / "source.mp4", folder / "source-audio.wav")
    normalize_cues(read_json(folder / "source-cues.json"), sha(folder / "source.mp4"), samples / RATE)
    _edit_voice(folder, edit, write=True)
    storyboard = normalize_storyboard(read_json(folder / "storyboard.json"), edit, imported=folder)
    plan = _sound_plan(read_json(folder / "audio-plan.json"), edit, storyboard, imported=folder)
    build_audio_master(folder, folder / "edited-voice.wav", frames / FPS, plan)
    _verify_audio(folder, plan, runtime)
    sources = {str((folder / name).relative_to(project)): sha(folder / name) for name in set(originals) | DERIVED}
    specs = {str(p.relative_to(_root())): sha(p) for p in _template().rglob("*.json") if "spec" in p.name and p.name != "layout.json"}
    core = {"contract": CONTRACT, "project_id": project_id,
        "template_id": f"investment-full-{template_number:02d}-{palette_variant}", "template_number": template_number,
        "palette_variant": palette_variant, "ratio": ratio, "title": title, "brand": brand,
        "render_profile": render_profile(frames), "source_media": info, "source_edits": edit, "cues": edit["cues"],
        "cue_map": edit["cue_map"], "caption_provenance": {k: read_json(cue_file)[k] for k in ("timing_basis", "evidence")},
        "storyboard": storyboard, "audio_plan": plan, "origins": origins, "sources": sources, "runtime": runtime,
        "audio_mode": "source-edl-sound-plan", "audio_policy": {"voice_gain_db": -2.5, "speed": 1, "additional_mux_gain_db": 0},
        "specification_snapshot": {"files": specs, "role": "prepare-time documentation only; post-render evidence may change"},
        "development_test": True, "publication": False, "cloud_calls": 0}
    digest = fingerprint(core)
    request = {**core, "request_sha256": digest, "render_id": PREFIX + digest[:20]}
    atomic_private(frozen, request)
    validate(queue, request)
    return request


def validate(queue, request):
    core = {k: v for k, v in request.items() if k not in {"request_sha256", "render_id"}}
    digest = fingerprint(core)
    if (request.get("contract") != CONTRACT or request.get("request_sha256") != digest
            or request.get("render_id") != PREFIX + digest[:20]
            or not re.fullmatch(r"studio-[a-f0-9]{16}", str(request.get("project_id", "")))):
        raise WorkError("完整招商冻结合同或请求指纹无效")
    _choice(request.get("template_number"), request.get("palette_variant"), request.get("ratio"))
    frames = _edit_frames(request["source_edits"])
    if frames != FRAMES and request["template_number"] != 8:
        raise WorkError("45秒扩展仅适用于08青炭")
    if (request.get("template_id") != f"investment-full-{request['template_number']:02d}-{request['palette_variant']}"
            or request.get("render_profile") != render_profile(frames) or request.get("development_test") is not True
            or request.get("publication") is not False or request.get("cloud_calls") != 0
            or request.get("audio_mode") != "source-edl-sound-plan"
            or request.get("audio_policy") != {"voice_gain_db": -2.5, "speed": 1, "additional_mux_gain_db": 0}):
        raise WorkError("完整招商身份、画质、原声或零云不发布范围不可改")
    project = WorkCatalog(queue.projects_root).project(request["project_id"])
    if read_json(project / "artifacts/investment-full-request.json") != request:
        raise WorkError("原生项目与原冻结请求不一致，请新prepare而非重签修改")
    folder = project / "assets/investment-full"
    expected = set(request["origins"]) | DERIVED
    if not set(INPUTS) <= set(request["origins"]) or set(request["sources"]) != {str((folder / name).relative_to(project)) for name in expected}:
        raise WorkError("不能增删冻结来源或派生音频绑定")
    for name, value in request["sources"].items():
        if sha(regular_path(project / name, project)) != value:
            raise WorkError("完整招商冻结素材、音频或证据SHA已变化")
    for name, item in request["origins"].items():
        if sha(regular_path(folder / name, project)) != item["sha256"]:
            raise WorkError("导入素材与原始来源身份不一致")
    actual_info = media_probe(folder / "source.mp4")
    if any(actual_info.get(k) != request["source_media"].get(k) for k in ("video", "audio", "duration")):
        raise WorkError("原片真实媒体时钟与冻结快照不一致")
    video_duration = _source_clock(actual_info)
    _, samples = _extract_audio(folder / "source.mp4", folder / "source-audio.wav")
    raw_cues = read_json(folder / "source-cues.json")
    source_cues = normalize_cues(raw_cues, sha(folder / "source.mp4"), samples / RATE)
    edit = normalize_edits(read_json(folder / "source-edits.json"), source_cues,
        sha(folder / "source.mp4"), sha(folder / "source-cues.json"), video_duration)
    if (request["source_edits"] != edit or request["cues"] != edit["cues"] or request["cue_map"] != edit["cue_map"]
            or request["caption_provenance"] != {k: raw_cues[k] for k in ("timing_basis", "evidence")}):
        raise WorkError("源EDL、完整原句、目标时钟或边缘静音映射不一致")
    _edit_voice(folder, edit)
    storyboard = normalize_storyboard(read_json(folder / "storyboard.json"), edit, imported=folder)
    plan = _sound_plan(read_json(folder / "audio-plan.json"), edit, storyboard, imported=folder)
    expected_origins = set(INPUTS) | {s["source_name"] for s in storyboard["shots"]} | {a["source_name"] for a in [plan["music"], *plan["assets"]]}
    if "presenterVideo" in storyboard:
        expected_origins.add(storyboard["presenterVideo"]["source_name"])
    if request["storyboard"] != storyboard or request["audio_plan"] != plan or set(request["origins"]) != expected_origins:
        raise WorkError("实际图文、实拍、声音计划或输入列表与冻结合同不一致")
    _verify_audio(folder, plan, request["runtime"])
    render = project / "renders" / request["render_id"]
    receipt = read_json(render / "investment-full-result.json")
    if receipt:
        if receipt.get("request_sha256") != digest or receipt.get("render_profile") != request["render_profile"]:
            raise WorkError("已有完整招商结果与本次合同身份不一致")
        for name, key in (("avatar-preview.mp4", "output_sha256"), ("props.json", "props_sha256"),
                          ("render-quality-receipt.json", "quality_receipt_sha256")):
            if sha(regular_path(render / name, project)) != receipt.get(key):
                raise WorkError("已有完整招商成片、props或画质证据SHA变化")
        if read_json(render / "props.json") != _props(request):
            raise WorkError("已有预览与冻结EDL、字幕或素材props不同")
    elif request["runtime"] != _runtime():
        raise WorkError("完整招商可执行模板或工具变化，请新prepare保留原请求")
    return project


def _queue_shape_changes(original, sanitized, path=""):
    """Describe loss without echoing any credential value removed by the queue."""
    if isinstance(original, dict) and isinstance(sanitized, dict):
        changes = []
        for key in sorted(original.keys() | sanitized.keys()):
            child = path + "/" + str(key).replace("~", "~0").replace("/", "~1")
            if key not in sanitized:
                changes.append("删除 " + child)
            elif key not in original:
                changes.append("新增 " + child)
            else:
                changes.extend(_queue_shape_changes(original[key], sanitized[key], child))
        return changes
    if isinstance(original, list) and isinstance(sanitized, list):
        changes = [] if len(original) == len(sanitized) else ["数组长度变化 " + path]
        for index, (first, second) in enumerate(zip(original, sanitized)):
            changes.extend(_queue_shape_changes(first, second, path + "/" + str(index)))
        return changes
    return [] if original == sanitized else ["值变化 " + path]


def submit(queue, request):
    from backlot.production_queue import _sanitize
    changes = _queue_shape_changes(request, _sanitize(request, redact_local_paths=False))
    if changes:
        details = "；".join(changes[:8]) + ("；另有更多变更" if len(changes) > 8 else "")
        raise WorkError("队列安全脱敏将改变冻结请求：" + details
                        + "。请重命名冲突的资源或移除不必要敏感字段后新prepare；不修改旧指纹或放宽安全策略")
    validate(queue, request)
    return queue.submit(project_id=request["project_id"], kind=KIND, source="codex", priority="normal",
        parent_job_id=request["render_id"], frozen_request=request,
        idempotency_key=CONTRACT + ":" + request["request_sha256"], start_paused=True)


def _render(project, request):
    from backlot.studio_composition import mux_avatar_audio
    from backlot.studio_investment_audio_v5 import measure_audio
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    from tools.video.video_compose import VideoCompose
    ffmpeg, _ = resolve_ffmpeg_pair()
    duration = _edit_frames(request["source_edits"]) / FPS
    folder = project / "renders" / request["render_id"]
    public = folder / "public"
    public.mkdir(parents=True, exist_ok=True)
    imported = project / "assets/investment-full"
    for name in ("source.mp4", "mixed-master.wav", *[s["source_name"] for s in request["storyboard"]["shots"]]):
        _copy(imported / name, public / name)
    track = request["storyboard"].get("presenterVideo")
    if track:
        _copy(imported / track["source_name"], public / track["source_name"])
    for source in _template_files():
        relative = source.relative_to(_template())
        _copy(source, folder / relative)
        if source.suffix.lower() not in {".tsx", ".ts", ".css"} and source.name != "layout.json":
            _copy(source, public / relative)
    props = _props(request)
    atomic_private(folder / "props.json", props)
    profile = request["render_profile"]
    bespoke = {"entry": str(folder / "index.tsx"), "composition_id": COMPOSITION_ID,
        "art_direction": str(_template() / "README.md"), "props_path": str(folder / "props.json"),
        "public_dir": str(public), "concurrency": 2,
        **{k: profile[k] for k in ("codec", "video_bitrate", "crf", "image_format", "x264_preset", "pixel_format", "scale")}}
    if profile["rate_control"] == "cbr-hrd":
        bespoke["h264_cbr"] = True
    edits = {"render_runtime": "remotion", "composition_mode": "atelier", "renderer_family": "bespoke",
             "bespoke": bespoke, "timeline": {"duration_seconds": duration}}
    raw, output = folder / "avatar-render.mp4", folder / "avatar-preview.mp4"
    result = VideoCompose().execute({"operation": "render", "output_path": str(raw), "edit_decisions": edits,
        "asset_manifest": {"assets": []}, "script_text": "".join(c["text"] for c in request["cues"])})
    if not result.success:
        raise WorkError("完整招商本地合成未通过，原输入及队列恢复点已保留", "unavailable")
    mux = mux_avatar_audio(ffmpeg, raw, public / "mixed-master.wav", output, duration, prepared_master=True)
    info, measured = media_probe(output), measure_audio(output)
    video, audio = info.get("video") or {}, info.get("audio") or {}
    try:
        rate = str(video.get("avg_frame_rate") or video.get("r_frame_rate"))
        actual_fps = float(rate.split("/")[0]) / float(rate.split("/")[1]) if "/" in rate else float(rate)
    except (ValueError, ZeroDivisionError, TypeError):
        actual_fps = 0
    if (video.get("width") != 1440 or video.get("height") != 1800 or video.get("codec_name") != "h264"
            or video.get("pix_fmt") != "yuv420p" or abs(actual_fps - FPS) > .001
            or (_edit_frames(request["source_edits"]) == 1350 and int(video.get("bit_rate") or 0) < 20_000_000)
            or abs(info.get("duration", 0) - duration) > .05 or str(audio.get("sample_rate")) != "48000"
            or audio.get("channels") != 2 or measured["true_peak_dbtp"] > -1.5):
        raise WorkError("完整招商成片尺寸、声明时钟、编码或最终音轨峰值不合格", "unavailable")
    _command([ffmpeg, "-nostdin", "-v", "error", "-i", output, "-f", "null", "-"])
    if sha(public / "source.mp4") != sha(imported / "source.mp4"):
        raise WorkError("人物原片必须按字节保留，不能经中间低清编码")
    if track and sha(public / track["source_name"]) != track["sha256"]:
        raise WorkError("人物替换源必须按字节保留，不能经中间低清编码")
    for shot in request["storyboard"]["shots"]:
        if sha(public / shot["source_name"]) != shot["sha256"]:
            raise WorkError("实际实拍资源字节与原始来源不同")
    atomic_private(folder / "render-quality-receipt.json", {"profile": profile,
        "source_video_sha256": sha(imported / "source.mp4"), "public_source_sha256": sha(public / "source.mp4"),
        "source_preparation": "source-byte-copy-edl", "alignment_command": None,
        "presenter_video_sha256": track["sha256"] if track else None,
        "source_edits_sha256": sha(imported / "source-edits.json"), "voice_edit_receipt_sha256": sha(imported / "voice-edit-receipt.json"),
        "remotion_command": (getattr(result, "data", None) or {}).get("render_command"), "mux_command": mux,
        "master_sha256": sha(public / "mixed-master.wav"), "additional_mux_gain_db": 0,
        "media": info, "final_audio": measured, "technical_decode": "passed",
        "output_sha256": sha(output), "human_review": "pending"})
    return output


def run(queue, job):
    request = job["frozen_request"]
    try:
        if job["kind"] != KIND or job["project_id"] != request["project_id"]:
            raise WorkError("统一队列与完整招商项目身份不匹配")
        project = validate(queue, request)
        folder = project / "renders" / request["render_id"]
        receipt_path = folder / "investment-full-result.json"
        receipt = read_json(receipt_path)
        output = folder / "avatar-preview.mp4" if receipt else _render(project, request)
        if not receipt:
            if read_json(folder / "props.json") != _props(request):
                raise WorkError("完整招商实际props与冻结人物EDL、字幕、图文或实拍不同")
            validate(queue, request)
            receipt = {"contract": CONTRACT, "request_sha256": request["request_sha256"],
                "output_sha256": sha(output), "props_sha256": sha(folder / "props.json"),
                "quality_receipt_sha256": sha(folder / "render-quality-receipt.json"),
                "template_id": request["template_id"], "render_profile": request["render_profile"],
                "development_test": True, "publication": False, "cloud_calls": 0, "human_review": "pending"}
            atomic_private(receipt_path, receipt)
        work = WorkCatalog(queue.projects_root).register(request["project_id"], output, work_key="main", mode="manual",
            event_id=job["job_id"], quality_passed=False, actor="local-investment-full", title=request["title"],
            summary=f"完整招商模板{request['template_number']} {request['palette_variant']}；{_edit_frames(request['source_edits']) // FPS}秒4x5；20Mbps目标码率")
        version = next(v for v in work["versions"] if v["sha256"] == sha(output))
        receipt.update(work_id=work["work_id"], version_id=version["version_id"])
        atomic_private(receipt_path, receipt)
        return {"status": "completed", "stage": "完整招商样片已合成，待实际审看", "result": {
            "output_path": str(output), "output_sha256": sha(output), "work_id": work["work_id"], "version_id": version["version_id"],
            "qa_status": "pending", "cloud_calls": 0, "development_test": True, "template_id": request["template_id"], "ratio": "4x5"}}
    except WorkError as error:
        return {"status": "failed", "stage": str(error), "error": {"type": "InvestmentFull", "message": str(error)},
                "retryable": error.code == "unavailable", "safe_resume_point": "local_investment_full"}
