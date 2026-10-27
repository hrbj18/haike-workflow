"""Queue-owned, local-only multi-ratio investment template development tests.

This is independent of every completed Template 6 contract.  The executable
template and media are frozen; later specification/review documents are not
render dependencies and cannot invalidate an already prepared request.
"""
from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import re
import shutil
import subprocess
import wave

from backlot.studio import atomic_private
from backlot.studio_investment_recompose import KIND, fingerprint
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkCatalog, WorkError, read_json, regular_path, sha

CONTRACT = "investment-style-lab-v1"
COMPOSITION_ID = "HaikeInvestmentStyleLab"
TEMPLATE_FOLDER = "investment-style-lab-v1"
PREFIX = "local-investment-style-lab-"
FPS, FRAMES, DURATION = 30, 360, 12
DIMENSIONS = {"9x16": (1080, 1920), "4x5": (1440, 1800),
              "1x1": (1536, 1536), "16x9": (1920, 1080)}
PALETTE_VARIANTS = {"blue-beige": 7, "cyan-charcoal": 8, "black-pink": 9}
EXECUTABLE_SUFFIXES = {".tsx", ".ts", ".css", ".ttf", ".ttc", ".otf", ".woff", ".woff2",
                       ".png", ".jpg", ".jpeg", ".webp", ".svg", ".wav"}


def render_profile(ratio):
    if ratio not in DIMENSIONS:
        raise WorkError("测试画幅仅支持9x16、4x5、1x1、16x9")
    width, height = DIMENSIONS[ratio]
    return {"id": "style-lab-20mbps-" + ratio + "-v1", "ratio": ratio,
            "width": width, "height": height, "fps": FPS, "duration_in_frames": FRAMES,
            "avatar_preparation": "source-byte-copy", "codec": "h264", "video_bitrate": "20M",
            "rate_control": "abr", "crf": None, "image_format": "png", "x264_preset": "slow",
            "pixel_format": "yuv420p", "scale": 1, "final_video": "stream-copy"}


def normalize_palette_variant(value, template_number, ratio):
    """Absence/default preserves the legacy request and props byte contract."""
    if value is None or value == "default":
        return None
    if (not isinstance(value, str) or value not in PALETTE_VARIANTS
            or PALETTE_VARIANTS[value] != template_number or ratio != "4x5"):
        raise WorkError("新配色仅支持4x5：模板07蓝米、08青炭、09黑粉，且编号必须匹配")
    return value


def _root():
    return Path(__file__).resolve().parents[1]


def _template():
    return _root() / "templates" / TEMPLATE_FOLDER


def _template_files():
    folder = _template()
    if not (folder / "index.tsx").is_file() or not (folder / "layout.json").is_file():
        raise WorkError("招商风格测试模板尚未完成，请先冻结index.tsx与layout.json")
    return sorted(path for path in folder.rglob("*") if path.is_file()
                  and (path.suffix.lower() in EXECUTABLE_SUFFIXES or path.name == "layout.json"))


def _runtime():
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    from backlot import studio_composition, studio_investment_audio_v5
    root = _root()
    ffmpeg, probe = resolve_ffmpeg_pair()
    paths = set(_template_files()) | {Path(__file__), Path(studio_composition.__file__),
        Path(studio_investment_audio_v5.__file__), root / "backlot/production_queue_worker.py",
        root / "tools/video/video_compose.py", root / "tools/base_tool.py", Path(ffmpeg), Path(probe)}
    # Browser font fallback is an executable dependency on this machine.  Bind
    # the files without copying/distributing the Windows system fonts.
    paths |= {path for name in ("msyh.ttc", "msyhbd.ttc", "simsun.ttc", "consola.ttf")
              if (path := Path("C:/Windows/Fonts") / name).is_file()}
    return {str(path.resolve()): sha(path) for path in sorted(paths)}


def _number(value):
    return type(value) in {int, float} and math.isfinite(value)


def _text(value, maximum, label, *, newlines=False):
    if (not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum
            or any(ord(char) < 32 and not (newlines and char == "\n") for char in value)):
        raise WorkError(label + "字数无效或包含控制字符")
    return value.strip()


def _source(value, suffixes):
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file() or path.is_symlink() or path.suffix.lower() not in suffixes:
        raise WorkError("输入必须是存在的本机绝对文件路径，且格式匹配")
    return path.resolve()


def _copy(source, target):
    source, target = Path(source), Path(target)
    if target.exists():
        if sha(target) != sha(source):
            raise WorkError("已冻结导入文件内容不同，保留原文件；新版本请使用新请求")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def normalize_cues(value, source_sha):
    if (not isinstance(value, dict) or value.get("source_video_sha256") != source_sha
            or value.get("timing_basis") not in {"cached_asr", "manual_reviewed"}
            or not isinstance(value.get("evidence"), str) or not value["evidence"].strip()):
        raise WorkError("字幕需绑定本次源视频SHA、真实缓存/人工核验时钟类型和证据定位")
    raw = value.get("cues")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 120:
        raise WorkError("12秒测试需1至120条有来源的字幕")
    cues, previous = [], 0
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"start", "end", "text"}:
            raise WorkError("字幕条目仅接受start/end秒数与text")
        start, end, text = item["start"], item["end"], item["text"]
        if (not _number(start) or not _number(end) or not previous <= start < end <= DURATION
                or not isinstance(text, str) or not 1 <= len(text.strip()) <= 96
                or len(text.split("\n")) > 3 or any(ord(c) < 32 and c != "\n" for c in text)):
            raise WorkError("字幕必须有序、非重叠、位于12秒内且文字长度有效")
        cues.append({"start": start, "end": end, "text": text})
        previous = end
    return cues


def normalize_beat_titles(value):
    titles = value.get("beat_titles") if isinstance(value, dict) else None
    if not isinstance(titles, list) or len(titles) != 4:
        raise WorkError("本期字幕输入需提供四个可替换beat_titles，不能在模板内写死文案")
    return [_text(title, 30, "分拍标题", newlines=True) for title in titles]


def _source_clock(info):
    video, audio = info.get("video") or {}, info.get("audio") or {}
    try:
        duration = float(video.get("duration") or info["duration"])
    except (TypeError, ValueError, KeyError):
        raise WorkError("原片视频时钟无法核对") from None
    if (not video or audio.get("codec_name") != "aac" or duration <= (FRAMES - 1) / FPS
            or abs(float(info["duration"]) - DURATION) > .1):
        raise WorkError("本合同只接受覆盖12秒末帧、带AAC原声的历史短测MP4；不拉伸或补帧")


def _command(args, timeout=180):
    from lib.subprocess_window import no_window_kwargs
    result = subprocess.run([str(arg) for arg in args], capture_output=True, timeout=timeout, **no_window_kwargs())
    if result.returncode:
        raise WorkError("本地媒体处理失败，原文件与检查点已保留", "unavailable")
    return result


def _voice(video, target):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg, _ = resolve_ffmpeg_pair()
    if not target.exists():
        pending = target.with_name("source-audio.pending.wav")
        _command([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", video, "-map", "0:a:0",
                  "-t", DURATION, "-vn", "-ar", 24000, "-ac", 1, "-c:a", "pcm_s16le", pending])
        pending.replace(target)
    with wave.open(str(target), "rb") as stream:
        if ((stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, 24000)
                or stream.getnframes() != DURATION * 24000):
            raise WorkError("原声PCM必须覆盖完整12秒且不变速")


def _voice_master(folder, voice):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    from backlot.studio_investment_audio_v5 import measure_audio, verify_master
    ffmpeg, _ = resolve_ffmpeg_pair()
    master, receipt = folder / "mixed-master.wav", folder / "audio-mix-receipt.json"
    if not receipt.exists():
        _command([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", voice, "-af", "volume=-2.5dB",
                  "-ar", 48000, "-ac", 2, "-c:a", "pcm_s16le", master])
        encoded = folder / "aac-peak-check.m4a"
        _command([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", master,
                  "-c:a", "aac", "-aac_coder", "fast", "-b:a", "192k", encoded])
        measured = measure_audio(encoded)
        if measured["true_peak_dbtp"] > -1.5:
            raise WorkError("原声安全余量不足，请提供经核验的声音计划，不自动改变冻结增益")
        atomic_private(receipt, {"version": "style-lab-voice-only-v1", "input_voice_sha256": sha(voice),
            "master_sha256": sha(master), "duration": DURATION, "voice_gain_db": -2.5, "speed": 1,
            "original_voice_unchanged": True, "aac_check": measured, "cloud_calls": 0})
    value = read_json(receipt)
    if (value.get("version") != "style-lab-voice-only-v1" or value.get("input_voice_sha256") != sha(voice)
            or value.get("duration") != DURATION or value.get("master_sha256") != sha(master)
            or value.get("speed") != 1 or value.get("voice_gain_db") != -2.5
            or value.get("aac_check", {}).get("true_peak_dbtp", 99) > -1.5):
        raise WorkError("原声母带回执与本次输入不匹配")
    verify_master(master, value["master_sha256"], DURATION)
    return [master, receipt]


def _verify_mix(folder, voice):
    """Verify the existing mixer's receipt; do not invent a reuse/remix result."""
    from backlot import studio_investment_audio_v5 as sound
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg, _ = resolve_ffmpeg_pair()
    master, receipt_path, plan_path = (folder / name for name in
        ("mixed-master.wav", "audio-mix-receipt.json", "audio-mix-plan.json"))
    receipt, plan = read_json(receipt_path), read_json(plan_path)
    expected = fingerprint({"voice_sha256": sha(voice), "plan": plan.get("plan"), "duration": DURATION,
                            "mixer_sha256": sha(sound.__file__), "ffmpeg_sha256": sha(ffmpeg)})
    if (plan.get("identity") != expected or receipt.get("identity") != expected
            or plan.get("voice_sha256") != sha(voice) or receipt.get("input_voice_sha256") != sha(voice)
            or receipt.get("duration") != DURATION or receipt.get("master_sha256") != sha(master)
            or receipt.get("audio_mix_plan_sha256") != sha(plan_path)
            or receipt.get("original_voice_unchanged") is not True or receipt.get("cloud_calls") != 0
            or receipt.get("profile") != sound.PROFILE
            or receipt.get("aac_check", {}).get("true_peak_dbtp", 99) > -1.5):
        raise WorkError("混音来源、原声、真实计划、混音器或峰值回执不匹配")
    sound.verify_master(master, receipt["master_sha256"], DURATION)
    return [master, receipt_path, plan_path]


def _plan_master(folder, voice, cues):
    from backlot import studio_investment_audio_v5 as sound
    raw = read_json(folder / "audio-plan.json")
    clock = [{"startMs": c["start"] * 1000, "endMs": c["end"] * 1000, "text": c["text"]} for c in cues]
    plan = sound.normalize_plan(raw, clock, [], [], DURATION)
    paths = [folder / "audio-plan.json"]
    for item in [plan["music"], *plan["assets"]]:
        target = folder / item["source_name"]
        _copy(item["path"], target)
        paths.append(target)
    plan = sound.normalize_plan(raw, clock, [], [], DURATION, imported=folder)
    sound.build_audio_master(folder, voice, DURATION, plan)
    return paths + _verify_mix(folder, voice) + [folder / "music-pre-duck.wav", folder / "music-post-duck.wav"]


def _props(request):
    captions = [{**cue, "startMs": round(cue["start"] * 1000), "endMs": round(cue["end"] * 1000),
                 "timestampMs": None, "confidence": None} for cue in request["cues"]]
    props = {"templateNumber": request["template_number"], "ratio": request["ratio"],
        "width": request["render_profile"]["width"], "height": request["render_profile"]["height"],
        "fps": FPS, "durationInFrames": FRAMES, "avatarSrc": "source.mp4", "audioSrc": "mixed-master.wav",
        "cues": captions, "beatTitles": request["beat_titles"], "brand": request["brand"],
        "headline": request["headline"], "cta": request["cta"]}
    if "palette_variant" in request:
        props["paletteVariant"] = request["palette_variant"]
    return props


def prepare(queue, source_video, cues_json, *, template_number, ratio, title, brand, headline=None, cta="",
            audio_plan=None, mixed_audio=None, audio_receipt=None, palette_variant=None):
    if type(template_number) is not int or template_number not in range(3, 11):
        raise WorkError("招商视频模板编号仅支持3至10")
    quality = render_profile(ratio)
    variant = normalize_palette_variant(palette_variant, template_number, ratio)
    palette = {} if variant is None else {"palette_variant": variant}
    title, brand = _text(title, 120, "标题"), _text(brand, 24, "品牌")
    cta = "" if cta == "" else _text(cta, 60, "咨询引导")
    if bool(mixed_audio) != bool(audio_receipt) or audio_plan and mixed_audio:
        raise WorkError("声音计划与母带复用二选一；母带需同时提供原混音回执")
    video, cue_file = _source(source_video, {".mp4"}), _source(cues_json, {".json"})
    info = media_probe(video)
    _source_clock(info)
    cue_input = read_json(cue_file)
    cues = normalize_cues(cue_input, sha(video))
    beat_titles = normalize_beat_titles(cue_input)
    headline = beat_titles[0] if headline is None else _text(headline, 30, "主标题", newlines=True)
    if headline != beat_titles[0]:
        raise WorkError("主标题必须与本期beat_titles第一拍一致，避免存在无效或相冲突的替换槽")
    originals = {"source.mp4": video, "cues.json": cue_file}
    mode = "voice-only"
    if audio_plan:
        mode = "sound-plan"
        originals["audio-plan.json"] = _source(audio_plan, {".json"})
    elif mixed_audio:
        mode = "completed-mix-reuse"
        master, receipt = _source(mixed_audio, {".wav"}), _source(audio_receipt, {".json"})
        if master.name != "mixed-master.wav" or receipt.name != "audio-mix-receipt.json" or master.parent != receipt.parent:
            raise WorkError("复用需提供原混音器同目录母带和回执，不接受改名拼接的证明")
        originals.update({"mixed-master.wav": master, "audio-mix-receipt.json": receipt,
                          "audio-mix-plan.json": _source(receipt.parent / "audio-mix-plan.json", {".json"})})
    origins = {name: {"path": str(path), "sha256": sha(path)} for name, path in originals.items()}
    if mode == "sound-plan":
        raw_plan = read_json(originals["audio-plan.json"])
        from backlot.studio_investment_audio_v5 import normalize_plan
        clock = [{"startMs": c["start"] * 1000, "endMs": c["end"] * 1000, "text": c["text"]} for c in cues]
        plan = normalize_plan(raw_plan, clock, [], [], DURATION)
        for item in [plan["music"], *plan["assets"]]:
            origins[item["source_name"]] = {"path": item["path"], "sha256": item["sha256"]}
    runtime = _runtime()
    identity = fingerprint({"contract": CONTRACT, "origins": origins, "runtime": runtime,
        "template_number": template_number, "ratio": ratio, "title": title, "brand": brand,
        "headline": headline, "beat_titles": beat_titles, "cta": cta, "render_profile": quality, "audio_mode": mode,
        **palette})
    project_id = "studio-" + identity[:16]
    project = queue.projects_root / project_id
    frozen = project / "artifacts/investment-style-lab-request.json"
    if frozen.exists():
        request = read_json(frozen)
        validate(queue, request)
        return request
    from lib.checkpoint import init_project
    init_project(project_id, title=title, pipeline_type="animated-explainer", pipeline_dir=queue.projects_root)
    folder = project / "assets/investment-style-lab"
    folder.mkdir(parents=True, exist_ok=True)
    for name, path in originals.items():
        _copy(path, folder / name)
    voice = folder / "source-audio.wav"
    _voice(folder / "source.mp4", voice)
    audio_paths = (_plan_master(folder, voice, cues) if mode == "sound-plan" else
                   _verify_mix(folder, voice) if mode == "completed-mix-reuse" else _voice_master(folder, voice))
    sources = {str(path.relative_to(project)): sha(path) for path in
               set([folder / name for name in originals] + [voice] + audio_paths)}
    template = _template()
    specs = {str(path.relative_to(_root())): sha(path) for path in template.rglob("*.json")
             if path.name != "layout.json" and "spec" in path.name}
    template_id = f"investment-template-{template_number:02d}" + ("-" + variant if variant else "")
    core = {"contract": CONTRACT, "project_id": project_id, "template_id": template_id,
        "template_number": template_number, "ratio": ratio, "title": title, "brand": brand,
        "headline": headline, "beat_titles": beat_titles, "cta": cta, "render_profile": quality, "cues": cues,
        "caption_provenance": {key: read_json(cue_file)[key] for key in ("timing_basis", "evidence")},
        "audio_mode": mode, "origins": origins, "sources": sources, "runtime": runtime,
        "specification_snapshot": {"files": specs, "role": "prepare-time documentation only; post-render evidence may change"},
        "development_test": True, "publication": False, "cloud_calls": 0, **palette}
    request_sha = fingerprint(core)
    request = {**core, "request_sha256": request_sha, "render_id": PREFIX + request_sha[:20]}
    atomic_private(frozen, request)
    validate(queue, request)
    return request


def validate(queue, request):
    core = {key: value for key, value in request.items() if key not in {"request_sha256", "render_id"}}
    identity = fingerprint(core)
    if (request.get("contract") != CONTRACT or request.get("request_sha256") != identity
            or request.get("render_id") != PREFIX + identity[:20]
            or not re.fullmatch(r"studio-[a-f0-9]{16}", str(request.get("project_id", "")))):
        raise WorkError("招商模板测试冻结合同或指纹无效")
    number = request.get("template_number")
    variant = normalize_palette_variant(request.get("palette_variant"), number, request.get("ratio"))
    template_id = f"investment-template-{number:02d}" + ("-" + variant if variant else "") if type(number) is int else None
    if (type(number) is not int or number not in range(3, 11)
            or request.get("template_id") != template_id
            or request.get("render_profile") != render_profile(request.get("ratio"))
            or request.get("development_test") is not True or request.get("publication") is not False
            or request.get("cloud_calls") != 0):
        raise WorkError("模板身份、20Mbps配置或零云不发布范围不可修改")
    if "palette_variant" in request and variant is None:
        raise WorkError("默认配色沿用原合同，不得在冻结请求中新增空或default配色字段")
    project = WorkCatalog(queue.projects_root).project(request["project_id"])
    # A re-signed JSON must not silently remove/add a color revision on an
    # existing native project. Completed legacy requests have no such field.
    frozen = read_json(project / "artifacts/investment-style-lab-request.json")
    if (("palette_variant" in frozen) != ("palette_variant" in request)
            or frozen.get("palette_variant") != request.get("palette_variant")):
        raise WorkError("配色变体与项目原冻结请求不一致，请使用新prepare目录")
    folder = project / "assets/investment-style-lab"
    expected = set(request["origins"]) | {"source-audio.wav", "mixed-master.wav", "audio-mix-receipt.json"}
    if request["audio_mode"] != "voice-only":
        expected.add("audio-mix-plan.json")
    if request["audio_mode"] == "sound-plan":
        expected |= {"music-pre-duck.wav", "music-post-duck.wav"}
    if set(request["sources"]) != {str((folder / name).relative_to(project)) for name in expected}:
        raise WorkError("不能增删冻结来源绑定")
    for name, digest in request["sources"].items():
        if sha(regular_path(project / name, project)) != digest:
            raise WorkError("冻结素材、母带或回执SHA已变化")
    for name, item in request["origins"].items():
        if sha(regular_path(folder / name, project)) != item["sha256"]:
            raise WorkError("导入素材与原来源身份不一致")
    source = regular_path(folder / "source.mp4", project)
    raw_cues = read_json(regular_path(folder / "cues.json", project))
    if (normalize_cues(raw_cues, sha(source)) != request["cues"]
            or normalize_beat_titles(raw_cues) != request["beat_titles"] or request["headline"] != request["beat_titles"][0]
            or request["caption_provenance"] != {key: raw_cues[key] for key in ("timing_basis", "evidence")}):
        raise WorkError("冻结字幕与来源时钟不一致")
    if request["audio_mode"] == "voice-only":
        _voice_master(folder, regular_path(folder / "source-audio.wav", project))
    elif request["audio_mode"] in {"sound-plan", "completed-mix-reuse"}:
        _verify_mix(folder, regular_path(folder / "source-audio.wav", project))
    else:
        raise WorkError("声音模式无效")
    render = project / "renders" / request["render_id"]
    receipt = read_json(render / "investment-style-lab-result.json")
    if receipt:
        for name, key in (("avatar-preview.mp4", "output_sha256"), ("props.json", "props_sha256"),
                          ("render-quality-receipt.json", "quality_receipt_sha256")):
            if receipt.get("request_sha256") != identity or sha(regular_path(render / name, project)) != receipt.get(key):
                raise WorkError("已有成片或渲染回执SHA已变化")
    elif request["runtime"] != _runtime():
        raise WorkError("可执行模板或工具已变化，新版本请重新prepare；已有原片保留")
    return project


def submit(queue, request):
    validate(queue, request)
    return queue.submit(project_id=request["project_id"], kind=KIND, source="codex", priority="normal",
        parent_job_id=request["render_id"], frozen_request=request,
        idempotency_key=CONTRACT + ":" + request["request_sha256"], start_paused=True)


def _render(project, request):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    from backlot.studio_composition import mux_avatar_audio
    from backlot.studio_investment_audio_v5 import measure_audio
    from tools.video.video_compose import VideoCompose
    ffmpeg, _ = resolve_ffmpeg_pair()
    folder = project / "renders" / request["render_id"]
    public = folder / "public"
    public.mkdir(parents=True, exist_ok=True)
    imported = project / "assets/investment-style-lab"
    for name in ("source.mp4", "mixed-master.wav"):
        _copy(imported / name, public / name)
    for source in _template_files():
        relative = source.relative_to(_template())
        _copy(source, folder / relative)
        if source.suffix.lower() not in {".tsx", ".ts", ".css"} and source.name != "layout.json":
            _copy(source, public / relative)
    props = _props(request)
    atomic_private(folder / "props.json", props)
    profile = request["render_profile"]
    bespoke = {"entry": str(folder / "index.tsx"), "composition_id": COMPOSITION_ID,
        "art_direction": str(_template() / "README.md"),
        "props_path": str(folder / "props.json"), "public_dir": str(public), "concurrency": 2,
        **{key: profile[key] for key in ("codec", "video_bitrate", "crf", "image_format", "x264_preset", "pixel_format", "scale")}}
    edits = {"render_runtime": "remotion", "composition_mode": "atelier", "renderer_family": "bespoke",
             "bespoke": bespoke, "timeline": {"duration_seconds": DURATION}}
    raw, output = folder / "avatar-render.mp4", folder / "avatar-preview.mp4"
    result = VideoCompose().execute({"operation": "render", "output_path": str(raw),
        "edit_decisions": edits, "asset_manifest": {"assets": []}, "script_text": "".join(c["text"] for c in request["cues"])})
    if not result.success:
        raise WorkError("招商模板本地渲染未通过，保留原输入及原队列恢复点", "unavailable")
    mux_command = mux_avatar_audio(ffmpeg, raw, public / "mixed-master.wav", output, DURATION, prepared_master=True)
    info, measured = media_probe(output), measure_audio(output)
    video, audio = info.get("video") or {}, info.get("audio") or {}
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate")
    try:
        actual_fps = float(rate.split("/")[0]) / float(rate.split("/")[1]) if "/" in str(rate) else float(rate)
    except (ValueError, TypeError, ZeroDivisionError):
        actual_fps = 0
    if (video.get("width") != profile["width"] or video.get("height") != profile["height"]
            or video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p"
            or abs(actual_fps - FPS) > .001 or abs(info.get("duration", 0) - DURATION) > .05
            or str(audio.get("sample_rate")) != "48000" or audio.get("channels") != 2
            or measured["true_peak_dbtp"] > -1.5):
        raise WorkError("成片尺寸、帧时钟、音轨或峰值检查未通过，产物保留", "unavailable")
    _command([ffmpeg, "-nostdin", "-v", "error", "-i", output, "-f", "null", "-"])
    source_sha = sha(imported / "source.mp4")
    if sha(public / "source.mp4") != source_sha:
        raise WorkError("人物源视频必须逐字节保留")
    atomic_private(folder / "render-quality-receipt.json", {"profile": profile,
        "source_video_sha256": source_sha, "public_source_sha256": sha(public / "source.mp4"),
        "source_preparation": "source-byte-copy", "alignment_command": None,
        "remotion_command": (getattr(result, "data", None) or {}).get("render_command"), "mux_command": mux_command,
        "master_sha256": sha(public / "mixed-master.wav"), "additional_mux_gain_db": 0,
        "media": info, "final_audio": measured, "technical_decode": "passed",
        "output_sha256": sha(output), "human_review": "pending"})
    return output


def run(queue, job):
    request = job["frozen_request"]
    try:
        if job["kind"] != KIND or job["project_id"] != request["project_id"]:
            raise WorkError("队列任务与冻结项目身份不一致")
        project = validate(queue, request)
        folder = project / "renders" / request["render_id"]
        receipt_path = folder / "investment-style-lab-result.json"
        receipt = read_json(receipt_path)
        output = folder / "avatar-preview.mp4" if receipt else _render(project, request)
        if not receipt:
            if read_json(folder / "props.json") != _props(request):
                raise WorkError("实际渲染props与冻结请求不一致")
            validate(queue, request)
            receipt = {"contract": CONTRACT, "request_sha256": request["request_sha256"],
                "output_sha256": sha(output), "props_sha256": sha(folder / "props.json"),
                "quality_receipt_sha256": sha(folder / "render-quality-receipt.json"),
                "template_id": request["template_id"], "render_profile": request["render_profile"],
                "development_test": True, "publication": False, "cloud_calls": 0, "human_review": "pending"}
            atomic_private(receipt_path, receipt)
        work = WorkCatalog(queue.projects_root).register(request["project_id"], output, work_key="main", mode="manual",
            event_id=job["job_id"], quality_passed=False, actor="local-investment-style-lab", title=request["title"],
            summary=f"招商视频模板{request['template_number']}；12秒四画幅风格测试；{request['ratio']}；20Mbps目标码率")
        version = next(item for item in work["versions"] if item["sha256"] == sha(output))
        receipt.update(work_id=work["work_id"], version_id=version["version_id"])
        atomic_private(receipt_path, receipt)
        return {"status": "completed", "stage": "招商模板12秒风格测试已完成，待审", "result": {
            "output_path": str(output), "output_sha256": sha(output), "work_id": work["work_id"],
            "version_id": version["version_id"], "qa_status": "pending", "cloud_calls": 0,
            "development_test": True, "template_id": request["template_id"], "ratio": request["ratio"]}}
    except WorkError as error:
        return {"status": "failed", "stage": str(error), "error": {"type": "InvestmentStyleLab", "message": str(error)},
                "retryable": error.code == "unavailable", "safe_resume_point": "local_investment_style_lab"}
