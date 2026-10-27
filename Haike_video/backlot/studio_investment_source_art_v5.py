"""Versioned zero-provider source-video motion/sound tests.

The completed v3 contract and default v002 renderer remain independent.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import shutil

from backlot import studio_investment_source_video as base
from backlot import studio_investment_source_art_v4 as previous
from backlot import studio_investment_audio_v5 as sound
from backlot.studio import Studio, atomic_private
from backlot.studio_investment import TEMPLATE_ID
from backlot.studio_investment_recompose import KIND, fingerprint
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkCatalog, WorkError, read_json, regular_path, sha

CONTRACT = "investment-source-video-art-v5"
VARIANT = "art-v5"
PREFIX = "local-source-art-v5-"
DIRECTIONS = base.DIRECTIONS | {"red-manifesto", "silver-launch", "documentary"}
DEFAULT_RENDER_PROFILE = "high-fidelity-20mbps-v1"
RENDER_PROFILES = {
    "legacy-v1": {"id": "legacy-v1", "avatar_preparation": "fps30-h264-crf23", "codec": "h264",
        "image_format": "jpeg", "jpeg_quality": 80, "crf": 18, "x264_preset": "medium", "pixel_format": "yuv420p",
        "width": 1080, "height": 1920, "fps": 30, "scale": 1, "final_video": "stream-copy"},
    "high-fidelity-v1": {"id": "high-fidelity-v1", "avatar_preparation": "source-byte-copy", "codec": "h264",
        "image_format": "png", "jpeg_quality": None, "crf": 16, "x264_preset": "slow", "pixel_format": "yuv420p",
        "width": 1080, "height": 1920, "fps": 30, "scale": 1, "final_video": "stream-copy"},
    DEFAULT_RENDER_PROFILE: {"id": DEFAULT_RENDER_PROFILE, "avatar_preparation": "source-byte-copy", "codec": "h264",
        "image_format": "png", "jpeg_quality": None, "crf": None, "video_bitrate": "20M", "rate_control": "abr",
        "x264_preset": "slow", "pixel_format": "yuv420p", "width": 1080, "height": 1920, "fps": 30,
        "scale": 1, "final_video": "stream-copy"},
}


def render_profile_spec(value):
    """Only named, immutable encoder profiles may enter a frozen request."""
    name = value.get("id") if isinstance(value, dict) else value
    if not isinstance(name, str) or name not in RENDER_PROFILES:
        raise WorkError("v5导出画质配置无效，请选择已登记的20Mbps、CRF16或legacy配置")
    profile = RENDER_PROFILES[name]
    if isinstance(value, dict) and value != profile:
        raise WorkError("不能修改v5冻结导出画质参数")
    return deepcopy(profile)


def verify_source_clock(info, duration, profile):
    """A direct source must cover every output timestamp; never pad/stretch it silently."""
    if profile["avatar_preparation"] != "source-byte-copy":
        return
    video = info.get("video") or {}
    try:
        source_duration = float(video.get("duration") or info["duration"])
    except (KeyError, TypeError, ValueError):
        raise WorkError("高清导出需要可核对的原片视频时钟") from None
    last_timestamp = (max(1, round(duration * profile["fps"])) - 1) / profile["fps"]
    if not source_duration > last_timestamp:
        raise WorkError("原片视频不足以覆盖高清成片末帧，请提供完整原片；不自动补帧或拉伸")


def _audio_plan_identity(value):
    """Only imported filesystem locations may differ when reusing a sound master."""
    if isinstance(value, dict):
        return {key: _audio_plan_identity(item) for key, item in value.items() if key != "path"}
    if isinstance(value, list):
        return [_audio_plan_identity(item) for item in value]
    return value


def _audio_donor(queue, request_file, lineage=()):
    donor = read_json(request_file)
    if donor.get("request_sha256") in lineage:
        raise WorkError("音频复用来源不能循环引用")
    project = validate(queue, donor, _audio_lineage=lineage)
    job = queue.find_by_idempotency_key(CONTRACT + ":" + donor["request_sha256"])
    result_path = project / "renders" / donor["render_id"] / "source-art-v5-result.json"
    result = read_json(result_path)
    if (not job or job["status"] != "completed" or not result
            or result.get("request_sha256") != donor["request_sha256"]
            or job.get("result", {}).get("output_sha256") != result.get("output_sha256")):
        raise WorkError("音频只能复用来源、回执和原生队列均核验完成的v5请求")
    return donor, result_path


def _reuse_audio(queue, folder, voice, duration, plan, request_file, *, lineage=(), write=False):
    """Copy completed audio bytes and original receipts; never relabel a remix as reuse."""
    donor, result_path = _audio_donor(queue, request_file, lineage)
    donor_folder = Path(donor["prepared"]["audio_path"]).parent
    old_plan = read_json(donor_folder / "audio-mix-plan.json")
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg, _ = resolve_ffmpeg_pair()
    mixer_key = str(Path(sound.__file__).resolve())
    if (sha(voice) != sha(donor_folder / "source-audio.wav") or duration != donor["prepared"]["duration"]
            or _audio_plan_identity(plan) != _audio_plan_identity(donor["art_direction"]["audio_plan"])
            or donor["audio_policy"] != AUDIO_POLICY
            or donor["runtime"].get(mixer_key) != sha(sound.__file__)
            or old_plan.get("ffmpeg_sha256") != sha(ffmpeg)):
        raise WorkError("音频复用要求原声、完整计划、素材SHA、时钟、混音器和FFmpeg保持一致")
    names = ("mixed-master.wav", "audio-mix-receipt.json", "audio-mix-plan.json", "music-pre-duck.wav", "music-post-duck.wav")
    files = {name: {"source": str(donor_folder / name), "sha256": sha(donor_folder / name)} for name in names}
    receipt = {"version": "completed-audio-reuse-v1", "donor_request_sha256": donor["request_sha256"],
        "donor_request_file_sha256": sha(request_file), "donor_project_id": donor["project_id"],
        "donor_render_id": donor["render_id"], "donor_result_path": str(result_path),
        "donor_result_sha256": sha(result_path), "donor_output_sha256": read_json(result_path)["output_sha256"],
        "input_voice_sha256": sha(voice), "duration": duration,
        "canonical_audio_plan_sha256": fingerprint(_audio_plan_identity(plan)),
        "filter_graph_fingerprint": fingerprint(old_plan["filter_graph"]), "files": files,
        "original_mix_receipt_and_plan_preserved_byte_exact": True, "remixed": False, "cloud_calls": 0}
    folder = Path(folder)
    if write:
        for name, item in files.items():
            destination = folder / name
            if destination.exists() and sha(destination) != item["sha256"]:
                raise WorkError("已有音频复用目标不同，不能覆盖冻结产物")
            if not destination.exists(): shutil.copy2(item["source"], destination)
        atomic_private(folder / "audio-reuse-receipt.json", receipt)
    else:
        if read_json(folder / "audio-reuse-receipt.json") != receipt:
            raise WorkError("音频复用来源、原生成回执或复用证明已变化")
        for name, item in files.items():
            if sha(folder / name) != item["sha256"]:
                raise WorkError("复用母带和原始混音证据必须逐字节保持")
    master = {"path": str((folder / "mixed-master.wav").resolve()), "sha256": files["mixed-master.wav"]["sha256"],
        "receipt_path": str((folder / "audio-mix-receipt.json").resolve()),
        "receipt_sha256": files["audio-mix-receipt.json"]["sha256"], "identity": donor["art_direction"]["audio_master"]["identity"]}
    return master, {"version": receipt["version"], "donor_request_sha256": donor["request_sha256"],
        "donor_output_sha256": receipt["donor_output_sha256"], "receipt_sha256": sha(folder / "audio-reuse-receipt.json"),
        "master_sha256": master["sha256"], "remixed": False}
FILES = {"video": "source.mp4", "audio": "source-audio.wav", "cues": "cues.json", "words": "word-clock.json",
         "art_config": "art-config.json", "audio_plan": "audio-plan.json", "background": "art-background.png"}
AUDIO_POLICY = {**deepcopy(base.AUDIO_POLICY), "final_gain_db": 0, "voice_gain_db": -2.5,
                "gain_stage": "frozen_mix_voice_once_plus_reported_master_headroom",
                "master_sample_rate": 48000, "master_channels": 2, "mix_profile": sound.PROFILE}


def import_files(config):
    return {key: name for key, name in FILES.items() if key != "background" or config.get("background_path") is not None}


def _runtime():
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    root = Path(__file__).resolve().parents[1]
    template = root / "templates/avatar-investment-a-v6-art-v5"
    required = [template / "index.tsx", template / "layout.json", root / "backlot/studio_composition.py",
                root / "tools/video/video_compose.py", root / "tools/base_tool.py",
                root / "backlot/production_queue_worker.py", Path(base.__file__).resolve(), Path(previous.__file__).resolve(), Path(sound.__file__).resolve(), Path(__file__).resolve()]
    if not all(path.is_file() for path in required): raise WorkError("v5艺术模板尚未冻结，请先完成实现")
    ffmpeg, probe = resolve_ffmpeg_pair()
    paths = set(required) | {path for path in template.rglob("*") if path.is_file()} | {Path(ffmpeg), Path(probe)}
    return {str(path.resolve()): sha(path) for path in sorted(paths)}


normalize_words = previous.normalize_words
_scene_name = previous._scene_name


def normalize_art(value, cues, words, duration, *, imported=None):
    if not isinstance(value, dict) or value.get("variant") != VARIANT:
        raise WorkError("v5艺术配置需显式art-v5")
    projected = deepcopy(value)
    projected["variant"] = previous.VARIANT
    art = previous.normalize_art(projected, cues, words, duration, imported=imported)
    art["variant"] = VARIANT
    return art


def props_art(art):
    props = previous.props_art(art)
    props["soundEvents"] = sound.sound_events(art["audio_plan"])
    return props


def prepare(queue, source_video, cues_json, word_clock_json, art_config_json, audio_plan_json, *, title, brand,
            render_profile=DEFAULT_RENDER_PROFILE, reuse_audio_request=None):
    quality = render_profile_spec(render_profile)
    title, brand = base._text(title, 120, "测试标题"), base._text(brand, 14, "项目品牌")
    video = base._source(source_video, {".mp4"})
    cue_file, words_file, config_file, audio_file = (base._source(path, {".json"}) for path in (cues_json, word_clock_json, art_config_json, audio_plan_json))
    raw = read_json(config_file)
    if not isinstance(raw, dict): raise WorkError("v5艺术配置需JSON对象")
    background = None
    if raw.get("background_path") is not None:
        background = base._source(raw["background_path"], {".png"})
        if sha(background) != raw.get("background_sha256"): raise WorkError("v5背景SHA已变化")
        try:
            from PIL import Image
            with Image.open(background) as image:
                if image.format != "PNG": raise ValueError()
                image.verify()
        except Exception: raise WorkError("v5艺术背景必须是可读PNG") from None
    runtime = _runtime()
    originals = [("video", video), ("cues", cue_file), ("words", words_file), ("art_config", config_file), ("audio_plan", audio_file)]
    if reuse_audio_request is not None:
        donor_file = base._source(reuse_audio_request, {".json"})
        _audio_donor(queue, donor_file)
        originals.append(("audio_reuse_request", donor_file))
    if background is not None: originals.append(("background", background))
    origins = {key: {"path": str(path), "sha256": sha(path)} for key, path in originals}
    identity = fingerprint({"contract": CONTRACT, "origins": origins, "runtime": runtime, "title": title, "brand": brand,
                            "render_profile": quality})
    project_id = "studio-" + identity[:16]
    project = queue.projects_root / project_id
    frozen = project / "artifacts/source-art-v5-request.json"
    if frozen.is_file():
        request = read_json(frozen)
        validate(queue, request)
        return request
    info = media_probe(video)
    if not info.get("video") or (info.get("audio") or {}).get("codec_name") != "aac" or not 0 < info.get("duration", 0) <= 121:
        raise WorkError("v5需120秒内完整原视频及其AAC原音轨")
    from lib.checkpoint import init_project
    init_project(project_id, title=title, pipeline_type="animated-explainer", pipeline_dir=queue.projects_root)
    imported = project / "assets/source-art-v5"
    imported.mkdir(parents=True, exist_ok=True)
    for key, path in originals:
        target = imported / ("audio-reuse-request.json" if key == "audio_reuse_request" else FILES[key])
        if target.exists() and sha(target) != origins[key]["sha256"]: raise WorkError("已有v5导入来源SHA冲突")
        if not target.exists(): shutil.copy2(path, target)
    audio = imported / FILES["audio"]
    if not audio.exists(): base._extract_audio(imported / FILES["video"], audio)
    duration = base._audio_duration(audio)
    if abs(duration - info["duration"]) > 1: raise WorkError("v5源视频与原音轨时钟不一致")
    verify_source_clock(info, duration, quality)
    cues = base.normalize_cues(read_json(imported / FILES["cues"]), duration, source_sha=origins["video"]["sha256"])
    words = normalize_words(read_json(imported / FILES["words"]), duration, origins["video"]["sha256"])
    art = normalize_art(raw, cues, words, duration)
    for scene in art["scenes"]:
        source, target = Path(scene["path"]), imported / scene["source_name"]
        origins["scene:" + scene["id"]] = {"path": str(source), "sha256": scene["sha256"]}
        if target.exists() and sha(target) != scene["sha256"]: raise WorkError("已有v5素材SHA冲突")
        if not target.exists(): shutil.copy2(source, target)
    art = normalize_art(raw, cues, words, duration, imported=imported)
    if background is not None: art["background_path"] = str((imported / FILES["background"]).resolve())
    raw_audio = read_json(imported / FILES["audio_plan"])
    plan = sound.normalize_plan(raw_audio, cues, words, art["chapters"], duration)
    for item in [plan["music"], *plan["assets"]]:
        source, target = Path(item["path"]), imported / item["source_name"]
        origins["sound:" + item["source_name"]] = {"path": str(source), "sha256": item["sha256"]}
        if target.exists() and sha(target) != item["sha256"]: raise WorkError("已有v5声音来源SHA冲突")
        if not target.exists(): shutil.copy2(source, target)
    plan = sound.normalize_plan(raw_audio, cues, words, art["chapters"], duration, imported=imported)
    reuse = None
    if reuse_audio_request is not None:
        master, reuse = _reuse_audio(queue, imported, audio, duration, plan, imported / "audio-reuse-request.json", write=True)
    else:
        master = sound.build_audio_master(imported, audio, duration, plan)
    art.update(audio_plan=plan, audio_master=master)
    studio = Studio(queue.projects_root)
    draft_path = imported / "draft.json"
    if draft_path.is_file():
        draft = read_json(draft_path)
        if draft != studio.draft(project_id): raise WorkError("已有v5草稿已改变")
    else:
        draft = studio.save_draft({"id": project_id, "template_id": TEMPLATE_ID, "title": title,
            "text": "".join(c["text"] for c in cues), "input": {"soundMode": "audio", "subtitles": True,
            "ai": {"enabled": False}, "network_materials_enabled": False, "investment": {"brand": brand,
            "headline": "\n".join(art["chapters"][0]["heading"]), "cta": "\n".join(art["chapters"][-1]["heading"]),
            "opening": True, "closing": True, "emphasis": []}}})
        atomic_private(draft_path, draft)
    paths = [imported / name for name in import_files(raw).values()] + [draft_path] + [imported / scene["source_name"] for scene in art["scenes"]]
    paths += [imported / item["source_name"] for item in [plan["music"], *plan["assets"]]]
    paths += [imported / name for name in ("mixed-master.wav", "audio-mix-receipt.json", "audio-mix-plan.json", "music-pre-duck.wav", "music-post-duck.wav")]
    if reuse is not None: paths += [imported / "audio-reuse-request.json", imported / "audio-reuse-receipt.json"]
    core = {"contract": CONTRACT, "project_id": project_id, "draft": draft, "origins": origins,
            "avatar_path": str((imported / FILES["video"]).resolve()),
            "prepared": {"duration": duration, "audio_path": str(audio.resolve()),
                         "mixed_audio_path": master["path"], "mixed_audio_sha256": master["sha256"]}, "cues": cues,
            "art_direction": art, "audio_policy": deepcopy(AUDIO_POLICY), "sources": {str(p.relative_to(project)): sha(p) for p in paths},
            "runtime": runtime, "render_profile": quality, "development_test": True, "publication": False, "cloud_calls": 0}
    if reuse is not None: core["audio_reuse"] = reuse
    request_sha = fingerprint(core)
    request = {**core, "request_sha256": request_sha, "render_id": PREFIX + request_sha[:20]}
    atomic_private(imported / "import-manifest.json", {"origins": origins, "sources": core["sources"],
                   "audio_policy": deepcopy(AUDIO_POLICY), "render_profile": quality, "source_media": info})
    atomic_private(frozen, request)
    validate(queue, request)
    return request


def validate(queue, request, *, _audio_lineage=()):
    core = {k: v for k, v in request.items() if k not in {"request_sha256", "render_id"}}
    identity = fingerprint(core)
    if (request.get("contract") != CONTRACT or request.get("request_sha256") != identity
            or request.get("render_id") != PREFIX + identity[:20]
            or not re.fullmatch(r"studio-[a-f0-9]{16}", str(request.get("project_id", "")))):
        raise WorkError("v5冻结合同或指纹无效")
    project = WorkCatalog(queue.projects_root).project(request["project_id"])
    if ("audio_reuse" in request) != ("audio_reuse_request" in request["origins"]):
        raise WorkError("音频复用声明与来源记录必须同时冻结")
    imported = project / "assets/source-art-v5"
    raw = read_json(regular_path(imported / FILES["art_config"], project))
    raw_audio = read_json(regular_path(imported / FILES["audio_plan"], project))
    expected = [imported / name for name in import_files(raw).values()] + [imported / "draft.json"]
    expected += [imported / _scene_name(i, scene) for i, scene in enumerate(raw.get("scenes", []))]
    expected += [imported / "music.wav"] + [imported / ("sound-" + item["id"] + ".wav") for item in raw_audio["assets"]]
    expected += [imported / name for name in ("mixed-master.wav", "audio-mix-receipt.json", "audio-mix-plan.json", "music-pre-duck.wav", "music-post-duck.wav")]
    if "audio_reuse" in request:
        expected += [imported / "audio-reuse-request.json", imported / "audio-reuse-receipt.json"]
    if set(request["sources"]) != {str(p.relative_to(project)) for p in expected}: raise WorkError("不能删改v5来源绑定")
    for relative, digest in request["sources"].items():
        if sha(regular_path(project / relative, project)) != digest: raise WorkError("v5导入来源SHA已变化")
    manifest = read_json(regular_path(imported / "import-manifest.json", project))
    if manifest.get("sources") != request["sources"] or manifest.get("origins") != request["origins"]:
        raise WorkError("v5来源与原导入清单不一致")
    # Missing means a historical request, never the new prepare default.
    quality = render_profile_spec(request["render_profile"]) if "render_profile" in request else None
    if manifest.get("render_profile") != quality:
        raise WorkError("v5导出画质与原导入清单不一致，不能静默迁移历史请求")
    if (request.get("development_test") is not True or request.get("publication") is not False or request.get("cloud_calls") != 0
            or request.get("audio_policy") != AUDIO_POLICY or manifest.get("audio_policy") != AUDIO_POLICY):
        raise WorkError("v5必须零云、原速、单次固定增益且不发布")
    draft = read_json(imported / "draft.json")
    if (request["draft"] != draft or draft != Studio(queue.projects_root).draft(request["project_id"])
            or draft.get("template_id") != TEMPLATE_ID or draft.get("id") != request["project_id"]):
        raise WorkError("不能改换v5冻结草稿")
    duration = base._audio_duration(imported / FILES["audio"])
    if quality is not None:
        verify_source_clock(manifest["source_media"], duration, quality)
    cues = base.normalize_cues(read_json(imported / FILES["cues"]), duration, source_sha=request["origins"]["video"]["sha256"])
    words = normalize_words(read_json(imported / FILES["words"]), duration, request["origins"]["video"]["sha256"])
    art = normalize_art(raw, cues, words, duration, imported=imported)
    if art["background_path"] is not None: art["background_path"] = str((imported / FILES["background"]).resolve())
    plan = sound.normalize_plan(raw_audio, cues, words, art["chapters"], duration, imported=imported)
    mixed = imported / "mixed-master.wav"
    mix_receipt_path = imported / "audio-mix-receipt.json"
    mix_receipt = read_json(mix_receipt_path)
    mix_plan = read_json(imported / "audio-mix-plan.json")
    if "audio_reuse" in request:
        if sha(imported / "audio-reuse-request.json") != request["origins"].get("audio_reuse_request", {}).get("sha256"):
            raise WorkError("音频复用请求来源SHA无效")
        _, reuse = _reuse_audio(queue, imported, imported / FILES["audio"], duration, plan,
            imported / "audio-reuse-request.json", lineage=(*_audio_lineage, identity))
        if request["audio_reuse"] != reuse: raise WorkError("不能改换已冻结音频复用来源")
    mix_identity = fingerprint({"voice_sha256": sha(imported / FILES["audio"]), "plan": mix_plan["plan"] if "audio_reuse" in request else plan, "duration": duration,
                                "mixer_sha256": request["runtime"].get(str(Path(sound.__file__).resolve())),
                                "ffmpeg_sha256": mix_plan.get("ffmpeg_sha256")})
    master = {"path": str(mixed.resolve()), "sha256": sha(mixed), "receipt_path": str(mix_receipt_path.resolve()),
              "receipt_sha256": sha(mix_receipt_path), "identity": mix_identity}
    sound.verify_master(mixed, master["sha256"], duration)
    if (mix_receipt.get("identity") != mix_identity or mix_receipt.get("master_sha256") != master["sha256"]
            or mix_receipt.get("audio_mix_plan_sha256") != sha(imported / "audio-mix-plan.json")
            or mix_receipt.get("input_voice_sha256") != sha(imported / FILES["audio"])
            or mix_receipt.get("profile") != sound.PROFILE or mix_receipt.get("voice_gain_db") != -2.5
            or (mix_plan.get("plan") != plan if "audio_reuse" not in request
                else _audio_plan_identity(mix_plan.get("plan")) != _audio_plan_identity(plan))
            or mix_plan.get("identity") != mix_identity
            or mix_receipt.get("music_ducking", {}).get("pre_bus_sha256") != sha(imported / "music-pre-duck.wav")
            or mix_receipt.get("music_ducking", {}).get("post_bus_sha256") != sha(imported / "music-post-duck.wav")
            or mix_receipt.get("aac_check", {}).get("true_peak_dbtp", 99) > -1.5):
        raise WorkError("v5派生混音、原声、计划或峰值回执绑定无效")
    art.update(audio_plan=plan, audio_master=master)
    if (request["avatar_path"] != str((imported / FILES["video"]).resolve())
            or request["prepared"] != {"duration": duration, "audio_path": str((imported / FILES["audio"]).resolve()),
                                       "mixed_audio_path": master["path"], "mixed_audio_sha256": master["sha256"]}
            or request["cues"] != cues or request["art_direction"] != art
            or art["background_path"] is not None and art["background_sha256"] != sha(imported / FILES["background"])):
        raise WorkError("不能改换v5原视频、音轨、真实词时钟或艺术分镜")
    folder = project / "renders" / request["render_id"]
    receipt = read_json(folder / "source-art-v5-result.json")
    if receipt:
        if receipt.get("audio_reuse") != request.get("audio_reuse"):
            raise WorkError("已有v5结果与冻结音频复用来源不一致")
        for name, key in (("avatar-preview.mp4", "output_sha256"), ("props.json", "props_sha256"), ("art-scene-plan.json", "scene_plan_sha256"),
                          ("audio-final-check.json", "audio_final_check_sha256")):
            if receipt.get("request_sha256") != identity or sha(regular_path(folder / name, project)) != receipt.get(key):
                raise WorkError("已有v5产物、props或分镜SHA已变化")
        if quality is not None:
            quality_path = regular_path(folder / "render-quality-receipt.json", project)
            if receipt.get("render_profile") != quality or receipt.get("render_quality_receipt_sha256") != sha(quality_path):
                raise WorkError("已有v5高清导出参数或回执SHA已变化")
    elif request["runtime"] != _runtime(): raise WorkError("v5源码已变化，请为新版本重新准备")
    return project


def submit(queue, request):
    validate(queue, request)
    return queue.submit(project_id=request["project_id"], kind=KIND, source="codex", priority="normal",
        parent_job_id=request["render_id"], frozen_request=request,
        idempotency_key=CONTRACT + ":" + request["request_sha256"], start_paused=True)


def run(queue, job):
    request = job["frozen_request"]
    try:
        if job["kind"] != KIND or job["project_id"] != request["project_id"]: raise WorkError("v5任务与项目绑定不一致")
        project = validate(queue, request)
        folder = project / "renders" / request["render_id"]
        folder.mkdir(parents=True, exist_ok=True)
        receipt, output = folder / "source-art-v5-result.json", folder / "avatar-preview.mp4"
        previous = read_json(receipt)
        if not previous:
            atomic_private(folder / "art-scene-plan.json", request["art_direction"])
            from backlot.studio_composition import compose_avatar
            quality_args = {"render_profile": deepcopy(request["render_profile"])} if "render_profile" in request else {}
            output = compose_avatar(folder, request["draft"], Path(request["avatar_path"]), Path(request["prepared"]["audio_path"]),
                request["prepared"]["duration"], request["cues"], art_direction=deepcopy(request["art_direction"]), **quality_args)
            validate(queue, request)
            if Path(output).resolve() != (folder / "avatar-preview.mp4").resolve(): raise WorkError("v5输出目录与原请求不一致")
            props = {"duration": request["prepared"]["duration"], "avatarSrc": "avatar.mp4", "audioSrc": "mixed-master.wav",
                     "brand": request["draft"]["input"]["investment"]["brand"], "captions": request["cues"],
                     "art": props_art(request["art_direction"])}
            if read_json(regular_path(folder / "props.json", project)) != props: raise WorkError("实际v5 props与冻结品牌、词时钟或素材分镜不一致")
            final_audio = read_json(regular_path(folder / "audio-final-check.json", project))
            if (final_audio.get("master") != request["art_direction"]["audio_master"]
                    or final_audio.get("output_sha256") != sha(output)
                    or final_audio.get("additional_mux_gain_db") != 0
                    or final_audio.get("final", {}).get("true_peak_dbtp", 99) > -1.5):
                raise WorkError("v5最终AAC需匹配冻结母带且通过true-peak检查")
            previous = {"contract": CONTRACT, "request_sha256": request["request_sha256"], "output_sha256": sha(output),
                "props_sha256": sha(folder / "props.json"), "scene_plan_sha256": sha(folder / "art-scene-plan.json"),
                "audio_final_check_sha256": sha(folder / "audio-final-check.json"), "final_audio": final_audio["final"],
                "source_video_sha256": request["origins"]["video"]["sha256"], "sources_unchanged": True,
                "audio_master": request["art_direction"]["audio_master"],
                "audio_policy": deepcopy(AUDIO_POLICY), "development_test": True, "publication": False,
                "cloud_calls": 0, "provider_jobs": [], "human_review": "pending"}
            if "render_profile" in request:
                quality_receipt = read_json(regular_path(folder / "render-quality-receipt.json", project))
                if quality_receipt.get("profile") != request["render_profile"]:
                    raise WorkError("实际导出画质与冻结参数不一致")
                if request["render_profile"]["avatar_preparation"] == "source-byte-copy":
                    expected_sha = request["origins"]["video"]["sha256"]
                    if (sha(folder / "public/avatar.mp4") != expected_sha
                            or quality_receipt.get("avatar", {}).get("public_sha256") != expected_sha):
                        raise WorkError("高清导出必须逐字节复用原人物视频")
                previous.update(render_profile=deepcopy(request["render_profile"]),
                    render_quality_receipt_sha256=sha(folder / "render-quality-receipt.json"))
            if "audio_reuse" in request: previous["audio_reuse"] = deepcopy(request["audio_reuse"])
            atomic_private(receipt, previous)
        work = WorkCatalog(queue.projects_root).register(request["project_id"], output, work_key="main", mode="manual",
            event_id=job["job_id"], quality_passed=False, actor="local-source-art-v5", title=request["draft"]["title"],
            summary="模板6 v5艺术开发测试；复用原片、原声和真实词时钟；" + request["art_direction"]["direction"])
        version = next(v for v in work["versions"] if v["sha256"] == sha(output))
        previous.update(work_id=work["work_id"], version_id=version["version_id"])
        atomic_private(receipt, previous)
        atomic_private(folder / "qa.json", {"template_id": TEMPLATE_ID, "variant": VARIANT,
            "caption_timing": "cached_real_word_clock", "cloud_calls": 0, "provider_jobs": [],
            "development_test": True, "publication": False, "audio_policy": deepcopy(AUDIO_POLICY), "human_review": "pending"})
        return {"status": "completed", "stage": "模板6 v5原视频艺术测试已合成，等待审核", "result": {
            "output_path": str(output), "output_sha256": sha(output), "work_id": work["work_id"], "version_id": version["version_id"],
            "qa_status": "pending", "cloud_calls": 0, "development_test": True, "variant": VARIANT}}
    except WorkError as error:
        return {"status": "failed", "stage": str(error), "error": {"type": "LocalSourceArtV5", "message": str(error)},
                "retryable": error.code == "unavailable", "safe_resume_point": "local_source_art_v5"}
