"""Frozen local soundtrack for Template 6 v5; no provider or renderer calls.

One PCM master is used by Studio preview and final AAC mux. Voice remains the
original extracted stream; its only track gain is -2.5 dB. Any necessary master
headroom attenuation is separately reported, never disguised as voice gain.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import re
import subprocess
import wave

from backlot import studio_investment_source_video as base
from backlot.studio import atomic_private
from backlot.studio_investment_recompose import fingerprint
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkError, read_json, sha

RATE, FPS = 48000, 30
VERSION = "sound-motion-v1"
PROFILE = {"id": "speech-led-v1", "voice_gain_db": -2.5, "sample_rate": RATE, "channels": 2,
           "sidechain": {"threshold": .05, "ratio": 2.5, "attack_ms": 15, "release_ms": 180},
           "limiter_dbfs": -3.0, "aac_true_peak_ceiling_dbtp": -1.5,
           "amix_normalize": False, "speed": 1}
PATTERNS = {"single": (0,), "triple-hit": (0, .12, .24)}
ROLES = {"dong", "impact", "whoosh", "tick"}


def _id(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", value):
        raise WorkError(label + "需1至48位字母、数字、下划线或连字符")
    return value


def _bounded(value, low, high, label):
    if not base._number(value) or not low <= value <= high: raise WorkError(label + "超出固定范围")
    return value


def _asset(item, name, *, imported=None):
    if (not isinstance(item.get("path"), str) or not Path(item["path"]).is_absolute()
            or not re.fullmatch(r"[a-f0-9]{64}", str(item.get("sha256")))):
        raise WorkError("声音素材需绝对本地路径与SHA256")
    path = base._source(imported / name if imported else item["path"], {".wav"})
    if sha(path) != item["sha256"]: raise WorkError("声音素材SHA已变化")
    info = media_probe(path)
    audio = info.get("audio") or {}
    if (not base._number(info.get("duration")) or not .025 <= info["duration"] <= 180
            or str(audio.get("sample_rate")) != str(RATE) or audio.get("channels") != 2
            or not str(audio.get("codec_name", "")).startswith("pcm_")):
        raise WorkError("声音素材需可解码48kHz立体声PCM WAV，长度0.025至180秒")
    return {**deepcopy(item), "path": str(path), "source_name": name, "duration": info["duration"],
            "source_label": base._text(item["source_label"], 160, "声音来源")}


def normalize_plan(value, cues, words, chapters, duration, *, imported=None):
    if (not isinstance(value, dict) or set(value) != {"version", "mix_profile", "music", "assets", "events"}
            or value["version"] != VERSION or value["mix_profile"] != PROFILE["id"]):
        raise WorkError("v5需固定sound-motion-v1/speech-led-v1声音计划")
    music = value["music"]
    if (not isinstance(music, dict) or set(music) != {"path", "sha256", "source_label", "offset", "loop", "gain_db", "fade_in", "fade_out"}
            or type(music["loop"]) is not bool): raise WorkError("BGM字段不完整或含未声明参数")
    music = _asset(music, "music.wav", imported=imported)
    offset = _bounded(music["offset"], 0, music["duration"] - .001, "BGM起点")
    _bounded(music["gain_db"], -36, -3, "BGM增益")
    _bounded(music["fade_in"], .005, min(3, duration / 2), "BGM淡入")
    _bounded(music["fade_out"], .05, min(5, duration / 2), "BGM淡出")
    if not music["loop"] and offset + duration > music["duration"] + .001:
        raise WorkError("BGM长度不足，必须显式授权loop或提供完整音乐")
    raw_assets, raw_events = value["assets"], value["events"]
    if not isinstance(raw_assets, list) or not 1 <= len(raw_assets) <= 12: raise WorkError("v5需1至12个原创/授权声音素材")
    if not isinstance(raw_events, list) or not 1 <= len(raw_events) <= 80: raise WorkError("v5需1至80个真实时钟音效事件")
    assets, ids = [], set()
    for item in raw_assets:
        required = {"id", "role", "path", "sha256", "source_label"}
        if not isinstance(item, dict) or not required <= set(item) or set(item) - required - {"sync_ms"}:
            raise WorkError("音效来源字段无效")
        ident = _id(item["id"], "声音id")
        if ident in ids or item["role"] not in ROLES: raise WorkError("声音id重复或role无效")
        ids.add(ident)
        asset = _asset(item, "sound-" + ident + ".wav", imported=imported)
        if asset["duration"] > 10: raise WorkError("单条音效不能超过10秒")
        asset["sync_ms"] = _bounded(item.get("sync_ms", 0), 0, asset["duration"] * 1000 - .001, "声音同步点")
        assets.append(asset)
    by_id = {item["id"]: item for item in assets}
    events, hits, ids = [], [], set()
    for event in raw_events:
        if not isinstance(event, dict) or set(event) != {"id", "asset_id", "anchor", "pattern", "gain_db"}:
            raise WorkError("音效只接受真实时钟锚点与命名pattern，不接受自由秒数")
        ident = _id(event["id"], "事件id")
        if ident in ids or event["asset_id"] not in by_id or event["pattern"] not in PATTERNS:
            raise WorkError("音效事件id、asset_id或pattern无效")
        ids.add(ident)
        gain = _bounded(event["gain_db"], -36, -3, "音效增益")
        anchor = event["anchor"]
        if (not isinstance(anchor, dict) or set(anchor) != {"type", "index", "boundary"}
                or anchor["type"] not in {"cue", "word", "chapter"}
                or anchor["boundary"] not in {"start", "end"} or type(anchor["index"]) is not int):
            raise WorkError("音效锚点仅支持cue/word/chapter实测起止边界")
        track = {"cue": cues, "word": words, "chapter": chapters}[anchor["type"]]
        if not 0 <= anchor["index"] < len(track): raise WorkError("音效锚点索引越界")
        item = track[anchor["index"]]
        time_ms = item[anchor["boundary"]] * 1000 if anchor["type"] == "chapter" else item[anchor["boundary"] + "Ms"]
        asset = by_id[event["asset_id"]]
        event_hits = []
        for index, delta in enumerate(PATTERNS[event["pattern"]]):
            start = time_ms / 1000 + delta
            if start < 0 or start >= duration - .005: raise WorkError("音效击打锚点位于片尾外")
            playback = max(0, start * 1000 - asset["sync_ms"])
            trim = max(0, asset["sync_ms"] - start * 1000)
            end = min(duration, start + asset["duration"] - asset["sync_ms"] / 1000)
            hit = {"id": ident if event["pattern"] == "single" else f"{ident}-{index + 1}",
                   "asset_id": asset["id"], "role": asset["role"], "timeMs": start * 1000,
                   "startFrame": math.ceil(start * FPS - 1e-9), "endFrame": math.ceil(end * FPS - 1e-9),
                   "strength": 10 ** (gain / 20), "gain_db": gain, "start": start, "end": end,
                   "sync_ms": asset["sync_ms"], "playback_start_ms": playback, "trim_start_ms": trim,
                   "quantization_delta_ms": math.ceil(start * FPS - 1e-9) / FPS * 1000 - start * 1000}
            event_hits.append(hit); hits.append(hit)
        events.append({**deepcopy(event), "timeMs": time_ms, "hits": event_hits})
    hits.sort(key=lambda item: (item["start"], item["id"]))
    if len(hits) > 120 or len({hit["id"] for hit in hits}) != len(hits): raise WorkError("展开音效击打过多或id冲突")
    for i, hit in enumerate(hits):
        if sum(other["start"] - hit["start"] < .1 for other in hits[i:i + 5]) > 4:
            raise WorkError("100毫秒内最多4次音效，不能叠加噪声墙")
    return {"version": VERSION, "mix_profile": deepcopy(PROFILE), "music": music, "assets": assets,
            "events": events, "hits": hits, "duration": duration}


def sound_events(plan):
    return [{key: hit[key] for key in ("id", "role", "timeMs", "startFrame", "endFrame", "strength")} for hit in plan["hits"]]


def _run(args, *, timeout=180):
    from lib.subprocess_window import no_window_kwargs
    result = subprocess.run([str(arg) for arg in args], capture_output=True, timeout=timeout, **no_window_kwargs())
    if result.returncode:
        raise WorkError("v5本地音频处理失败，保留原声和混音诊断：" + result.stderr.decode("utf-8", errors="replace")[-1200:], "unavailable")
    return result


def measure_audio(path):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg, _ = resolve_ffmpeg_pair()
    result = _run([ffmpeg, "-nostdin", "-hide_banner", "-i", path, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    text = result.stderr.decode("utf-8", errors="replace")
    try:
        report, _ = json.JSONDecoder().raw_decode(text[text.rfind("{"):])
        measured = {"integrated_lufs": float(report["input_i"]), "true_peak_dbtp": float(report["input_tp"]),
                    "loudness_range_lu": float(report["input_lra"])}
        if not all(math.isfinite(value) for value in measured.values()): raise ValueError()
        return measured
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise WorkError("v5混音无法取得有限的响度与true-peak测量") from None


def verify_master(path, digest, duration):
    path = base._source(path, {".wav"})
    if sha(path) != digest: raise WorkError("v5冻结混音SHA已变化")
    try:
        with wave.open(str(path), "rb") as stream:
            if (stream.getframerate() != RATE or stream.getnchannels() != 2 or stream.getsampwidth() != 2
                    or abs(stream.getnframes() / RATE - duration) > 1 / RATE): raise ValueError()
    except (wave.Error, ValueError): raise WorkError("v5混音必须为完整48k立体声PCM16") from None
    return path


def measure_ducking(voice, pre, post):
    """Measure actual music bus RMS during 50 ms windows of active source voice."""
    from array import array
    pre_energy = post_energy = total_pre = total_post = 0
    active_samples = total_samples = active_windows = 0
    def energy(raw):
        values = array("h"); values.frombytes(raw)
        return sum(sample * sample for sample in values), len(values)
    with wave.open(str(voice), "rb") as speech, wave.open(str(pre), "rb") as before, wave.open(str(post), "rb") as after:
        if speech.getsampwidth() != 2 or before.getparams()[:3] != (2, 2, RATE) or after.getparams()[:3] != (2, 2, RATE):
            raise WorkError("ducking测量需要原PCM16及48k立体声诊断母线")
        voice_frames, music_frames = round(speech.getframerate() * .05), round(RATE * .05)
        while True:
            raw_voice, raw_pre, raw_post = speech.readframes(voice_frames), before.readframes(music_frames), after.readframes(music_frames)
            if not raw_voice or not raw_pre or not raw_post: break
            common = min(len(raw_pre), len(raw_post))
            v, vn = energy(raw_voice); a, an = energy(raw_pre[:common]); b, bn = energy(raw_post[:common])
            count = min(an, bn)
            total_pre += a; total_post += b; total_samples += count
            if v / max(1, vn) >= (32768 * 10 ** (-35 / 20)) ** 2:
                pre_energy += a; post_energy += b; active_samples += count; active_windows += 1
    def dbfs(value, count): return 10 * math.log10(max(value / max(1, count), 1e-20) / 32768 ** 2)
    if not active_samples or pre_energy <= 0 or post_energy <= 0:
        raise WorkError("实际人声/音乐能量不足，不能取得ducking实测比值")
    gain = 10 * math.log10(post_energy / pre_energy)
    return {"method": "actual_pre_post_music_bus_rms_over_active_original_voice_windows",
            "window_ms": 50, "voice_activity_threshold_dbfs": -35,
            "active_seconds": active_samples / (RATE * 2), "active_windows": active_windows,
            "active_pre_rms_dbfs": dbfs(pre_energy, active_samples), "active_post_rms_dbfs": dbfs(post_energy, active_samples),
            "active_speech_duck_gain_db": gain, "active_speech_reduction_db": -gain,
            "full_pre_rms_dbfs": dbfs(total_pre, total_samples), "full_post_rms_dbfs": dbfs(total_post, total_samples),
            "pre_bus_sha256": sha(pre), "post_bus_sha256": sha(post)}


def build_audio_master(folder, voice, duration, plan):
    """Prepare the same frozen master consumed by both preview and queue mux."""
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg, _ = resolve_ffmpeg_pair()
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    output, receipt_path = folder / "mixed-master.wav", folder / "audio-mix-receipt.json"
    identity = fingerprint({"voice_sha256": sha(voice), "plan": plan, "duration": duration,
                            "mixer_sha256": sha(Path(__file__)), "ffmpeg_sha256": sha(ffmpeg)})
    previous = read_json(receipt_path)
    if previous:
        if previous.get("identity") != identity: raise WorkError("已有v5混音与当前冻结输入不同")
        verify_master(output, previous["master_sha256"], duration)
        return {"path": str(output.resolve()), "sha256": previous["master_sha256"], "receipt_path": str(receipt_path.resolve()), "receipt_sha256": sha(receipt_path), "identity": identity}
    for asset in [plan["music"], *plan["assets"]]:
        if sha(asset["path"]) != asset["sha256"]: raise WorkError("混音前声音素材SHA不匹配")
    samples = round(duration * RATE)
    args = [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(voice)]
    music = plan["music"]
    if music["loop"]: args += ["-stream_loop", "-1"]
    args += ["-i", music["path"]]
    graph = [f"[0:a:0]aresample={RATE}:async=0:first_pts=0,aformat=channel_layouts=stereo,apad,atrim=end_sample={samples},asetpts=N/SR/TB,volume=-2.5dB,asplit=2[voice][key]",
             f"[1:a:0]atrim=start={music['offset']},asetpts=PTS-STARTPTS,aresample={RATE}:async=0:first_pts=0,aformat=channel_layouts=stereo,apad,atrim=end_sample={samples},asetpts=N/SR/TB,volume={music['gain_db']}dB,afade=t=in:d={music['fade_in']},afade=t=out:st={duration-music['fade_out']}:d={music['fade_out']},asplit=2[music][pre-diagnostic]",
             "[music][key]sidechaincompress=threshold=0.05:ratio=2.5:attack=15:release=180:makeup=1:link=maximum:level_sc=1,asplit=2[ducked][post-diagnostic]"]
    labels = ["[voice]", "[ducked]"]
    assets = {item["id"]: item for item in plan["assets"]}
    for i, hit in enumerate(plan["hits"], 2):
        args += ["-i", assets[hit["asset_id"]]["path"]]
        length = round((hit["end"] - hit["playback_start_ms"] / 1000) * RATE)
        first = round(hit["trim_start_ms"] / 1000 * RATE)
        fade = min(.008, length / RATE / 4)
        graph.append(f"[{i}:a:0]aresample={RATE}:async=0:first_pts=0,aformat=channel_layouts=stereo,atrim=start_sample={first}:end_sample={first+length},asetpts=N/SR/TB,volume={hit['gain_db']}dB,afade=t=in:d=0.002,afade=t=out:st={max(0,length/RATE-fade)}:d={fade},adelay={round(hit['playback_start_ms']/1000*RATE)}S:all=1[s{i}]")
        labels.append(f"[s{i}]")
    graph.append("".join(labels) + f"amix=inputs={len(labels)}:duration=first:normalize=0,aresample=192000,alimiter=limit={10**(PROFILE['limiter_dbfs']/20)}:attack=5:release=50:level=0:latency=1,aresample={RATE},apad,atrim=end_sample={samples},asetpts=N/SR/TB[mix]")
    candidate = folder / "mixed-candidate.wav"
    filter_graph = ";".join(graph)
    atomic_private(folder / "audio-mix-plan.json", {"identity": identity, "profile": PROFILE, "plan": plan,
        "filter_graph": filter_graph, "voice_sha256": sha(voice), "samples": samples, "ffmpeg_sha256": sha(ffmpeg)})
    pre, post = folder / "music-pre-duck.wav", folder / "music-post-duck.wav"
    _run(args + ["-filter_complex", filter_graph, "-map", "[mix]", "-ar", RATE, "-ac", 2, "-c:a", "pcm_s16le", candidate,
                 "-map", "[pre-diagnostic]", "-ar", RATE, "-ac", 2, "-c:a", "pcm_s16le", pre,
                 "-map", "[post-diagnostic]", "-ar", RATE, "-ac", 2, "-c:a", "pcm_s16le", post])
    ducking = measure_ducking(voice, pre, post)
    master_gain, passes = 0.0, []
    for attempt in range(3):
        if master_gain:
            _run([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", candidate, "-af", f"volume={master_gain}dB", "-ar", RATE, "-ac", 2, "-c:a", "pcm_s16le", output])
        else:
            import shutil
            shutil.copy2(candidate, output)
        encoded = folder / "aac-peak-check.m4a"
        _run([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", output, "-c:a", "aac", "-aac_coder", "fast", "-b:a", "192k", "-ar", RATE, "-ac", 2, encoded])
        measured = measure_audio(encoded)
        passes.append({"master_gain_db": master_gain, "aac": measured})
        if measured["true_peak_dbtp"] <= PROFILE["aac_true_peak_ceiling_dbtp"]: break
        master_gain -= measured["true_peak_dbtp"] - PROFILE["aac_true_peak_ceiling_dbtp"] + .25
    else: raise WorkError("v5混音true-peak安全回退仍未通过，保留诊断", "unavailable")
    verify_master(output, sha(output), duration)
    receipt = {"identity": identity, "version": VERSION, "profile": PROFILE, "master_sha256": sha(output),
               "duration": duration, "voice_gain_db": -2.5, "master_gain_db": master_gain,
               "effective_voice_gain_db": -2.5 + master_gain, "master": measure_audio(output),
               "aac_check": passes[-1]["aac"], "safety_passes": passes,
               "music_ducking": ducking,
               "input_voice_sha256": sha(voice), "audio_mix_plan_sha256": sha(folder / "audio-mix-plan.json"),
               "cloud_calls": 0, "original_voice_unchanged": True}
    atomic_private(receipt_path, receipt)
    return {"path": str(output.resolve()), "sha256": receipt["master_sha256"], "receipt_path": str(receipt_path.resolve()), "receipt_sha256": sha(receipt_path), "identity": identity}
