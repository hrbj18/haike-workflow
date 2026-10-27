"""Queue-only, zero-provider Template 6 art tests from an existing source video.

This contract imports original local media. It does not impersonate a successful
Studio avatar/ASR job or the separate silent layout-sample contract.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import wave

from backlot.studio import Studio, atomic_private
from backlot.studio_investment import TEMPLATE_ID
from backlot.studio_investment_recompose import KIND, fingerprint
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkCatalog, WorkError, read_json, regular_path, sha

CONTRACT = "investment-source-video-art-v1"
DIRECTIONS = {"blue-editorial", "community-showcase", "optical-cinema"}
FRAMING = {"close-4x5", "medium-9x16"}
PREFIX = "local-source-art-"
IMPORT_FILES = {"video": "source.mp4", "audio": "source-audio.wav", "cues": "cues.json",
                "art_config": "art-config.json", "background": "art-background.png"}
AUDIO_POLICY = {"source": "original_video_AAC_track_0:a:0", "extraction_gain_db": 0,
                "sample_rate": 24000, "channels": 1, "sample_format": "PCM16",
                "final_gain_db": -2.5, "gain_stage": "final_mux_once", "speed": 1}


def _runtime():
    root = Path(__file__).resolve().parents[1]
    template = root / "templates/avatar-investment-a-v6-art-v3"
    required = [template / "index.tsx", template / "layout.json", root / "backlot/studio_composition.py",
                root / "backlot/studio_investment.py", root / "backlot/production_queue_worker.py", Path(__file__).resolve()]
    if not all(p.is_file() for p in required):
        raise WorkError("艺术模板源码尚未冻结，请完成实现后准备本地测试")
    # Fonts and other distributable template dependencies are frozen too.
    paths = set(required) | {p for p in template.rglob("*") if p.is_file()}
    return {str(p.resolve()): sha(p) for p in sorted(paths)}


def _number(value):
    return type(value) in {int, float} and math.isfinite(value)


def _text(value, maximum, label, minimum=1):
    if (not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum
            or any(ord(c) < 32 for c in value)):
        raise WorkError(f"{label}需{minimum}至{maximum}字，且不能包含控制字符")
    return value.strip()


def normalize_cues(value, duration, *, source_sha=None):
    raw = value if isinstance(value, list) else value.get("cues") if isinstance(value, dict) else None
    if not isinstance(raw, list) or not 1 <= len(raw) <= 2000:
        raise WorkError("本地测试需要缓存真实字幕数组，或顶层cues数组")
    binding = value.get("source_video_sha256") if isinstance(value, dict) else None
    if source_sha is not None and binding is not None and binding != source_sha:
        raise WorkError("字幕缓存绑定的原视频SHA不一致")
    result, previous = [], 0
    for cue in raw:
        if not isinstance(cue, dict): raise WorkError("真实字幕条目无效")
        cue_binding = cue.get("source_video_sha256", binding)
        if source_sha is not None and cue_binding != source_sha:
            raise WorkError("每条真实字幕需绑定本次原视频SHA，不能改用其他缓存")
        text = cue.get("text")
        if (not isinstance(text, str) or any(ord(c) < 32 and c != "\n" for c in text)
                or not 1 <= len(text.split("\n")) <= 2
                or any(not 1 <= len(line) <= 14 for line in text.split("\n"))):
            raise WorkError("真实字幕需保留语义换行，最多两行、每行14字")
        start, end = cue.get("startMs"), cue.get("endMs")
        if (not _number(start) or not _number(end) or not previous <= start < end <= duration * 1000 + .001):
            raise WorkError("真实字幕时钟需有序且位于原音轨内，不能猜测或拉伸")
        confidence = cue.get("confidence")
        if confidence is not None and (not _number(confidence) or not 0 <= confidence <= 1):
            raise WorkError("字幕置信度无效")
        previous = end
        result.append({"text": text, "startMs": start, "endMs": end,
                       "timestampMs": None, "confidence": confidence})
    return result


def normalize_art(value, cues, duration):
    fields = {"direction", "background_path", "background_sha256", "chapters", "highlights", "portrait_framing"}
    if not isinstance(value, dict) or set(value) != fields:
        raise WorkError("艺术配置仅支持固定方向、背景、章节、重点词与人物景别字段")
    if value["direction"] not in DIRECTIONS or value["portrait_framing"] not in FRAMING:
        raise WorkError("艺术方向或人物景别不在固定枚举中")
    if (not isinstance(value["background_path"], str) or not Path(value["background_path"]).is_absolute()
            or not re.fullmatch(r"[a-f0-9]{64}", str(value["background_sha256"]))):
        raise WorkError("背景图需冻结PNG绝对路径与SHA256")
    highlights = value["highlights"]
    if not isinstance(highlights, list) or len(highlights) > 24:
        raise WorkError("最多24个字幕重点词")
    highlights = [_text(item, 10, "字幕重点词", minimum=2) for item in highlights]
    raw = value["chapters"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 40:
        raise WorkError("艺术章节需1至40项")
    chapters, next_cue = [], 0
    for chapter in raw:
        if not isinstance(chapter, dict) or set(chapter) != {"kind", "fromCue", "toCue", "heading", "deck", "points"}:
            raise WorkError("章节仅接受类型、cue索引、标题、说明与要点")
        first, last = chapter["fromCue"], chapter["toCue"]
        if (chapter["kind"] not in {"hook", "story", "ai", "offer", "cta"}
                or type(first) is not int or type(last) is not int
                or first != next_cue or not first <= last < len(cues)):
            raise WorkError("章节cue索引需连续覆盖真实字幕，不可漏句、重叠或伪造秒数")
        heading, points = chapter["heading"], chapter["points"]
        if not isinstance(heading, list) or not 1 <= len(heading) <= 2:
            raise WorkError("章节标题需1至2行")
        if not isinstance(points, list) or len(points) > 3: raise WorkError("章节要点最多3项")
        normalized = {"kind": chapter["kind"], "fromCue": first, "toCue": last,
                      "heading": [_text(line, 12, "章节标题每行") for line in heading],
                      "deck": _text(chapter["deck"], 40, "章节说明", minimum=0),
                      "points": [_text(point, 12, "章节要点") for point in points],
                      "start": 0 if first == 0 else cues[first]["startMs"] / 1000,
                      "cueStartMs": cues[first]["startMs"], "cueEndMs": cues[last]["endMs"]}
        chapters.append(normalized)
        next_cue = last + 1
    if next_cue != len(cues): raise WorkError("章节必须覆盖末条真实字幕")
    for i, chapter in enumerate(chapters):
        chapter["end"] = chapters[i + 1]["start"] if i + 1 < len(chapters) else duration
        if chapter["end"] <= chapter["start"]: raise WorkError("章节时间范围为空")
    return {"direction": value["direction"], "background_path": value["background_path"],
            "background_sha256": value["background_sha256"], "chapters": chapters,
            "highlights": highlights, "portrait_framing": value["portrait_framing"]}


def _source(raw, suffixes):
    path = Path(raw).expanduser()
    if path.is_symlink() or not path.is_file() or path.suffix.lower() not in suffixes:
        raise WorkError("导入来源需为存在的本机原文件，不能使用符号链接")
    return path.resolve()


def _extract_audio(video, target):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    from lib.subprocess_window import no_window_kwargs
    ffmpeg, _ = resolve_ffmpeg_pair()
    pending = target.with_name("source-audio.pending.wav")
    result = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(video),
                             "-map", "0:a:0", "-vn", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(pending)],
                            capture_output=True, timeout=180, **no_window_kwargs())
    if result.returncode: raise WorkError("原视频音轨提取失败；保留源文件，不提交云识别", "unavailable")
    _audio_duration(pending)
    pending.replace(target)


def _audio_duration(path):
    try:
        with wave.open(str(path), "rb") as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, 24000, "NONE"):
                raise ValueError()
            duration = stream.getnframes() / 24000
    except (wave.Error, ValueError, EOFError, OSError):
        raise WorkError("导入音轨必须为未增益的24kHz PCM16单声道WAV") from None
    if not 0 < duration <= 120: raise WorkError("艺术测试单条原音轨需在120秒内")
    return duration


def prepare(queue, source_video, cues_json, art_config_json, *, title, brand):
    """Import local sources and freeze a request; no queue admission or SDK."""
    title, brand = _text(title, 120, "测试标题"), _text(brand, 14, "项目品牌")
    video = _source(source_video, {".mp4"})
    cue_file, config_file = _source(cues_json, {".json"}), _source(art_config_json, {".json"})
    raw_art = read_json(config_file)
    if not isinstance(raw_art, dict): raise WorkError("艺术配置需要JSON对象")
    background = _source(raw_art.get("background_path", ""), {".png"})
    if sha(background) != raw_art.get("background_sha256"): raise WorkError("背景图SHA已变化")
    try:
        from PIL import Image
        with Image.open(background) as image:
            if image.format != "PNG": raise ValueError()
            image.verify()
    except Exception:
        raise WorkError("艺术背景不是可读取的PNG原图") from None
    runtime = _runtime()
    origins = {key: {"path": str(path), "sha256": sha(path)} for key, path in (
        ("video", video), ("cues", cue_file), ("art_config", config_file), ("background", background))}
    identity = fingerprint({"contract": CONTRACT, "origins": origins, "runtime": runtime, "title": title, "brand": brand})
    project_id = "studio-" + identity[:16]
    project = queue.projects_root / project_id
    frozen = project / "artifacts/source-video-art-request.json"
    if frozen.is_file():
        request = read_json(frozen)
        validate(queue, request)
        return request
    info = media_probe(video)
    if (not info.get("video") or (info.get("audio") or {}).get("codec_name") != "aac"
            or not 0 < info.get("duration", 0) <= 121):
        raise WorkError("原素材需含完整视频和AAC原音轨，且长度在本合同范围内")
    from lib.checkpoint import init_project
    init_project(project_id, title=title, pipeline_type="animated-explainer", pipeline_dir=queue.projects_root)
    imported = project / "assets/source-video-art"
    imported.mkdir(parents=True, exist_ok=True)
    for key, source in (("video", video), ("cues", cue_file), ("art_config", config_file), ("background", background)):
        target = imported / IMPORT_FILES[key]
        if target.exists() and sha(target) != origins[key]["sha256"]: raise WorkError("已有导入文件SHA冲突，保留原项目")
        if not target.exists(): shutil.copy2(source, target)
    audio = imported / IMPORT_FILES["audio"]
    if not audio.exists(): _extract_audio(imported / IMPORT_FILES["video"], audio)
    duration = _audio_duration(audio)
    if abs(info["duration"] - duration) > 1: raise WorkError("原视频与提取音轨长度不一致，未拉伸或截断")
    cues = normalize_cues(read_json(imported / IMPORT_FILES["cues"]), duration, source_sha=origins["video"]["sha256"])
    art = normalize_art(raw_art, cues, duration)
    art["background_path"] = str((imported / IMPORT_FILES["background"]).resolve())
    studio = Studio(queue.projects_root)
    draft_file = imported / "draft.json"
    if draft_file.is_file():
        draft = read_json(draft_file)
        if studio.draft(project_id) != draft: raise WorkError("导入草稿已被修改，不能覆盖")
    else:
        draft = studio.save_draft({"id": project_id, "template_id": TEMPLATE_ID, "title": title,
            "text": "".join(c["text"] for c in cues), "input": {"soundMode": "audio", "subtitles": True,
            "ai": {"enabled": False}, "network_materials_enabled": False,
            "investment": {"brand": brand, "headline": "\n".join(art["chapters"][0]["heading"]),
                           "cta": "\n".join(art["chapters"][-1]["heading"]), "opening": True, "closing": True, "emphasis": []}}})
        atomic_private(draft_file, draft)
    paths = [imported / name for name in IMPORT_FILES.values()] + [draft_file]
    core = {"contract": CONTRACT, "project_id": project_id, "draft": draft, "origins": origins,
            "avatar_path": str((imported / IMPORT_FILES["video"]).resolve()),
            "prepared": {"duration": duration, "audio_path": str(audio.resolve())},
            "cues": cues, "art_direction": art, "audio_policy": deepcopy(AUDIO_POLICY),
            "sources": {str(p.relative_to(project)): sha(p) for p in paths}, "runtime": runtime,
            "development_test": True, "publication": False, "cloud_calls": 0}
    request_sha = fingerprint(core)
    request = {**core, "request_sha256": request_sha, "render_id": PREFIX + request_sha[:20]}
    atomic_private(imported / "import-manifest.json", {"origins": origins, "sources": core["sources"],
                   "audio_policy": deepcopy(AUDIO_POLICY), "source_media": info})
    atomic_private(frozen, request)
    validate(queue, request)
    return request


def validate(queue, request):
    core = {k: v for k, v in request.items() if k not in {"request_sha256", "render_id"}}
    identity = fingerprint(core)
    if (request.get("contract") != CONTRACT or request.get("request_sha256") != identity
            or request.get("render_id") != PREFIX + identity[:20]
            or not re.fullmatch(r"studio-[a-f0-9]{16}", str(request.get("project_id", "")))):
        raise WorkError("原视频艺术测试冻结合同或指纹无效")
    project = WorkCatalog(queue.projects_root).project(request["project_id"])
    imported = project / "assets/source-video-art"
    expected_paths = [imported / name for name in IMPORT_FILES.values()] + [imported / "draft.json"]
    if set(request["sources"]) != {str(p.relative_to(project)) for p in expected_paths}:
        raise WorkError("不能删改导入来源绑定")
    for relative, digest in request["sources"].items():
        if sha(regular_path(project / relative, project)) != digest: raise WorkError("导入来源SHA已变化")
    manifest = read_json(regular_path(imported / "import-manifest.json", project))
    if manifest.get("sources") != request["sources"] or manifest.get("origins") != request["origins"]:
        raise WorkError("冻结来源与原导入清单不一致")
    if (request.get("development_test") is not True or request.get("publication") is not False
            or request.get("cloud_calls") != 0 or request.get("audio_policy") != AUDIO_POLICY
            or manifest.get("audio_policy") != AUDIO_POLICY):
        raise WorkError("原视频艺术测试必须零云、原速、单次固定增益且不可发布")
    draft = read_json(imported / "draft.json")
    if (request["draft"] != draft or draft != Studio(queue.projects_root).draft(request["project_id"])
            or draft.get("id") != request["project_id"] or draft.get("template_id") != TEMPLATE_ID):
        raise WorkError("不能改换已冻结的导入草稿")
    duration = _audio_duration(imported / IMPORT_FILES["audio"])
    cues = normalize_cues(read_json(imported / IMPORT_FILES["cues"]), duration, source_sha=request["origins"]["video"]["sha256"])
    art = normalize_art(read_json(imported / IMPORT_FILES["art_config"]), cues, duration)
    art["background_path"] = str((imported / IMPORT_FILES["background"]).resolve())
    if (request["avatar_path"] != str((imported / IMPORT_FILES["video"]).resolve())
            or request["prepared"] != {"duration": duration, "audio_path": str((imported / IMPORT_FILES["audio"]).resolve())}
            or request["cues"] != cues or request["art_direction"] != art
            or art["background_sha256"] != sha(imported / IMPORT_FILES["background"])):
        raise WorkError("不能改换原视频、音轨、真实cue或艺术方案")
    folder = project / "renders" / request["render_id"]
    receipt = read_json(folder / "source-video-art-result.json")
    if receipt:
        output = regular_path(folder / "avatar-preview.mp4", project)
        if receipt.get("request_sha256") != identity or receipt.get("output_sha256") != sha(output):
            raise WorkError("已有艺术测试成片SHA发生变化，保留产物待核对")
        for name, key in (("props.json", "props_sha256"), ("art-scene-plan.json", "scene_plan_sha256")):
            if sha(regular_path(folder / name, project)) != receipt.get(key):
                raise WorkError("已有艺术测试的props或分镜计划SHA发生变化")
    elif request["runtime"] != _runtime():
        raise WorkError("艺术模板源码已变化，请为新版本重新准备，不重渲染原冻结任务")
    return project


def submit(queue, request):
    validate(queue, request)
    return queue.submit(project_id=request["project_id"], kind=KIND, source="codex", priority="normal",
        parent_job_id=request["render_id"], frozen_request=request,
        idempotency_key=CONTRACT + ":" + request["request_sha256"], start_paused=True)


def run(queue, job):
    """Registered worker handler; callers must claim the existing native queue."""
    request = job["frozen_request"]
    try:
        if job["project_id"] != request["project_id"] or job["kind"] != KIND:
            raise WorkError("艺术测试任务与项目绑定不一致")
        project = validate(queue, request)
        folder = project / "renders" / request["render_id"]
        folder.mkdir(parents=True, exist_ok=True)
        receipt = folder / "source-video-art-result.json"
        previous = read_json(receipt)
        output = folder / "avatar-preview.mp4"
        if not previous:
            atomic_private(folder / "art-scene-plan.json", {"request_sha256": request["request_sha256"],
                           "clock": "cached_real_source_cues", "duration": request["prepared"]["duration"],
                           "art": request["art_direction"], "cues": request["cues"]})
            from backlot.studio_composition import compose_avatar
            output = compose_avatar(folder, request["draft"], Path(request["avatar_path"]),
                Path(request["prepared"]["audio_path"]), request["prepared"]["duration"], request["cues"],
                art_direction=deepcopy(request["art_direction"]))
            validate(queue, request)
            if Path(output).resolve() != (folder / "avatar-preview.mp4").resolve():
                raise WorkError("艺术合成产物不属于原冻结渲染目录")
            props = read_json(regular_path(folder / "props.json", project))
            art = request["art_direction"]
            expected_art = {"direction": art["direction"], "backgroundSrc": "art-background.png",
                            "chapters": art["chapters"], "highlights": art["highlights"],
                            "portraitFraming": art["portrait_framing"]}
            expected_props = {"duration": request["prepared"]["duration"], "avatarSrc": "avatar.mp4",
                              "audioSrc": "narration.wav", "brand": request["draft"]["input"]["investment"]["brand"],
                              "captions": request["cues"], "art": expected_art}
            if props != expected_props:
                raise WorkError("实际渲染props与冻结品牌、音轨、字幕或艺术分镜不一致")
            previous = {"contract": CONTRACT, "request_sha256": request["request_sha256"],
                "output_sha256": sha(output), "cloud_calls": 0, "provider_jobs": [],
                "props_sha256": sha(folder / "props.json"), "scene_plan_sha256": sha(folder / "art-scene-plan.json"),
                "source_video_sha256": request["origins"]["video"]["sha256"], "sources_unchanged": True,
                "audio_policy": deepcopy(AUDIO_POLICY), "development_test": True, "publication": False,
                "human_review": "pending"}
            atomic_private(receipt, previous)
        work = WorkCatalog(queue.projects_root).register(request["project_id"], output,
            work_key="main", mode="manual", event_id=job["job_id"], quality_passed=False,
            actor="local-source-video-art", title=request["draft"]["title"],
            summary="模板6艺术开发测试；复用原视频、原音轨和缓存真实字幕；" + request["art_direction"]["direction"])
        version = next(v for v in work["versions"] if v["sha256"] == sha(output))
        previous.update(work_id=work["work_id"], version_id=version["version_id"])
        atomic_private(receipt, previous)
        atomic_private(folder / "qa.json", {"template_id": TEMPLATE_ID, "caption_timing": "cached_real_source_cues",
            "cloud_calls": 0, "provider_jobs": [], "development_test": True, "publication": False,
            "audio_policy": deepcopy(AUDIO_POLICY), "human_review": "pending"})
        return {"status": "completed", "stage": "模板6原视频艺术测试已合成，等待审核", "result": {
            "output_path": str(output), "output_sha256": sha(output), "qa_status": "pending", "cloud_calls": 0,
            "development_test": True, "work_id": work["work_id"], "version_id": version["version_id"]}}
    except WorkError as error:
        return {"status": "failed", "stage": str(error), "error": {"type": "LocalSourceVideoArt", "message": str(error)},
                "retryable": error.code == "unavailable", "safe_resume_point": "local_source_video_art"}
