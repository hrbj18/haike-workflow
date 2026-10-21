"""Versioned zero-provider source-video art tests with real word clocks/media.

The completed v3 contract and default v002 renderer remain independent.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import shutil

from backlot import studio_investment_source_video as base
from backlot.studio import Studio, atomic_private
from backlot.studio_investment import TEMPLATE_ID, normalized
from backlot.studio_investment_recompose import KIND, fingerprint
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkCatalog, WorkError, read_json, regular_path, sha

CONTRACT = "investment-source-video-art-v4"
VARIANT = "art-v4"
PREFIX = "local-source-art-v4-"
DIRECTIONS = base.DIRECTIONS | {"red-manifesto", "silver-launch", "documentary"}
FILES = {"video": "source.mp4", "audio": "source-audio.wav", "cues": "cues.json", "words": "word-clock.json",
         "art_config": "art-config.json", "background": "art-background.png"}
AUDIO_POLICY = deepcopy(base.AUDIO_POLICY)


def import_files(config):
    return {key: name for key, name in FILES.items() if key != "background" or config.get("background_path") is not None}


def _runtime():
    root = Path(__file__).resolve().parents[1]
    template = root / "templates/avatar-investment-a-v6-art-v4"
    required = [template / "index.tsx", template / "layout.json", root / "backlot/studio_composition.py",
                root / "backlot/production_queue_worker.py", Path(base.__file__).resolve(), Path(__file__).resolve()]
    if not all(path.is_file() for path in required): raise WorkError("v4艺术模板尚未冻结，请先完成实现")
    paths = set(required) | {path for path in template.rglob("*") if path.is_file()}
    return {str(path.resolve()): sha(path) for path in sorted(paths)}


def normalize_words(value, duration, source_sha):
    raw = value if isinstance(value, list) else value.get("cues") if isinstance(value, dict) else None
    if not isinstance(raw, list) or not 1 <= len(raw) <= 10000: raise WorkError("v4需要真实word-clock数组")
    binding = value.get("source_video_sha256") if isinstance(value, dict) else None
    out, previous = [], 0
    for word in raw:
        if not isinstance(word, dict) or word.get("source_video_sha256", binding) != source_sha:
            raise WorkError("每条实测word-clock都需绑定本次原视频SHA")
        text = base._text(word.get("text"), 100, "实测词")
        start, end, confidence = word.get("startMs"), word.get("endMs"), word.get("confidence")
        if (not base._number(start) or not base._number(end) or not previous <= start < end <= duration * 1000 + .001
                or confidence is not None and (not base._number(confidence) or not 0 <= confidence <= 1)):
            raise WorkError("实测词时钟需有序且位于原音轨内，不能补造或拉伸")
        out.append({"text": text, "startMs": start, "endMs": end, "timestampMs": None, "confidence": confidence})
        previous = end
    return out


def _scene_name(index, item):
    path = Path(item["path"])
    return f"scene-{index:02d}-{item['id']}" + path.suffix.lower()


def normalize_art(value, cues, words, duration, *, imported=None):
    fields = {"variant", "direction", "background_path", "background_sha256", "portrait_framing", "chapters",
              "highlights", "phrase_highlights", "scenes"}
    required = fields - {"phrase_highlights", "scenes"}
    if (not isinstance(value, dict) or not required <= set(value) or set(value) - fields
            or value["variant"] != VARIANT or value["direction"] not in DIRECTIONS):
        raise WorkError("v4艺术配置需固定variant、六方向及已声明的章节/词时钟/素材字段")
    if normalized("".join(c["text"] for c in cues)) != normalized("".join(w["text"] for w in words)):
        raise WorkError("完整显示字幕与实测word-clock原文不一致，不能用缺失词时钟制作高亮")
    code_background = value["background_path"] is None
    if (code_background != (value["background_sha256"] is None)
            or code_background and value["direction"] in base.DIRECTIONS):
        raise WorkError("仅红色、银色和纪实方向可使用双null的代码背景；旧三方向仍需PNG及SHA")
    common = {key: value[key] for key in ("direction", "background_path", "background_sha256", "portrait_framing", "chapters", "highlights")}
    common["direction"] = "blue-editorial"
    if code_background:
        # The immutable v3 normalizer requires concrete source identity while
        # validating shared chapters/text. This internal code identity is never
        # imported, rendered or persisted as an image; restore null below.
        common.update(background_path=str(Path(__file__).resolve()), background_sha256=sha(Path(__file__).resolve()))
    art = base.normalize_art(common, cues, duration)
    if code_background: art.update(background_path=None, background_sha256=None)
    art.update(variant=VARIANT, direction=value["direction"], word_cues=deepcopy(words))
    groups = value.get("phrase_highlights", [])
    if not isinstance(groups, list) or len(groups) > 80: raise WorkError("实测词组高亮最多80项")
    phrases = []
    for group in groups:
        if not isinstance(group, dict) or set(group) != {"text", "fromWord", "toWord"}:
            raise WorkError("词组高亮只接受原文与实测word索引，不接受自填秒数")
        first, last = group["fromWord"], group["toWord"]
        text = base._text(group["text"], 28, "高亮词组")
        if (type(first) is not int or type(last) is not int or not 0 <= first <= last < len(words)
                or normalized(text) != normalized("".join(w["text"] for w in words[first:last + 1]))):
            raise WorkError("高亮词组必须逐字对应指定实测word片段")
        phrases.append({"text": text, "fromWord": first, "toWord": last,
                        "startMs": words[first]["startMs"], "endMs": words[last]["endMs"]})
    art["phrase_highlights"] = phrases
    raw_scenes = value.get("scenes", [])
    if not isinstance(raw_scenes, list) or len(raw_scenes) > 16: raise WorkError("v4真实素材最多16段")
    scenes, identifiers, previous_end = [], set(), 0
    for index, item in enumerate(raw_scenes):
        if not isinstance(item, dict) or set(item) != {"id", "path", "sha256", "kind", "fromCue", "toCue", "offset", "fit", "source_label"}:
            raise WorkError("真实素材仅支持已声明的来源、cue范围、起点及适配方式")
        identifier = item["id"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", identifier) or identifier in identifiers:
            raise WorkError("真实素材id无效或重复")
        identifiers.add(identifier)
        first, last, offset = item["fromCue"], item["toCue"], item["offset"]
        if (type(first) is not int or type(last) is not int or not 0 <= first <= last < len(cues)
                or not base._number(offset) or offset < 0 or item["fit"] not in {"cover", "contain"}
                or item["kind"] not in {"image", "video"}
                or not isinstance(item["path"], str) or not Path(item["path"]).is_absolute()
                or not re.fullmatch(r"[a-f0-9]{64}", str(item["sha256"]))):
            raise WorkError("真实素材的cue索引、offset、SHA或固定枚举无效")
        start, end = cues[first]["startMs"] / 1000, cues[last]["endMs"] / 1000
        if start < previous_end or end <= start: raise WorkError("同一真实素材轨不能重叠或乱序")
        previous_end = end
        label = base._text(item["source_label"], 100, "素材来源标注")
        name = _scene_name(index, item)
        path = regular_path(imported / name, imported) if imported else base._source(item["path"], {".mp4", ".mov", ".png", ".jpg", ".jpeg", ".webp"})
        if sha(path) != item["sha256"]: raise WorkError("真实素材源SHA已变化")
        if item["kind"] == "video":
            if path.suffix.lower() not in {".mp4", ".mov"}: raise WorkError("视频素材格式与kind不一致")
            info = media_probe(path)
            if not info.get("video"): raise WorkError("真实素材缺少视频流")
            available = info["duration"]
            try: available = min(available, float(info["video"].get("duration", available)))
            except (TypeError, ValueError): raise WorkError("真实素材的视频流时长无效") from None
            if not base._number(available) or available <= 0 or offset + end - start > available + .05:
                raise WorkError("真实素材长度不足；不得循环或拉伸补足")
        else:
            if offset != 0 or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                raise WorkError("图片素材offset必须为0且格式与kind一致")
            try:
                from PIL import Image
                with Image.open(path) as image: image.verify()
            except Exception: raise WorkError("真实图片无法读取") from None
        scenes.append({**deepcopy(item), "path": str(path.resolve()), "start": start, "end": end,
                       "source_name": name, "cueStartMs": cues[first]["startMs"], "cueEndMs": cues[last]["endMs"]})
    art["scenes"] = scenes
    return art


def props_art(art):
    """Only renderer-facing fields; provenance stays in request/scene plan."""
    return {"direction": art["direction"], "backgroundSrc": "art-background.png" if art["background_path"] is not None else None, "chapters": art["chapters"],
            "highlights": art["highlights"], "portraitFraming": art["portrait_framing"],
            "wordCues": art["word_cues"], "phraseHighlights": art["phrase_highlights"],
            "scenes": [{"id": s["id"], "src": s["source_name"], "kind": s["kind"], "start": s["start"],
                        "end": s["end"], "offset": s["offset"], "fit": s["fit"], "sourceLabel": s["source_label"]} for s in art["scenes"]]}


def prepare(queue, source_video, cues_json, word_clock_json, art_config_json, *, title, brand):
    title, brand = base._text(title, 120, "测试标题"), base._text(brand, 14, "项目品牌")
    video = base._source(source_video, {".mp4"})
    cue_file, words_file, config_file = (base._source(path, {".json"}) for path in (cues_json, word_clock_json, art_config_json))
    raw = read_json(config_file)
    if not isinstance(raw, dict): raise WorkError("v4艺术配置需JSON对象")
    background = None
    if raw.get("background_path") is not None:
        background = base._source(raw["background_path"], {".png"})
        if sha(background) != raw.get("background_sha256"): raise WorkError("v4背景SHA已变化")
        try:
            from PIL import Image
            with Image.open(background) as image:
                if image.format != "PNG": raise ValueError()
                image.verify()
        except Exception: raise WorkError("v4艺术背景必须是可读PNG") from None
    runtime = _runtime()
    originals = [("video", video), ("cues", cue_file), ("words", words_file), ("art_config", config_file)]
    if background is not None: originals.append(("background", background))
    origins = {key: {"path": str(path), "sha256": sha(path)} for key, path in originals}
    identity = fingerprint({"contract": CONTRACT, "origins": origins, "runtime": runtime, "title": title, "brand": brand})
    project_id = "studio-" + identity[:16]
    project = queue.projects_root / project_id
    frozen = project / "artifacts/source-art-v4-request.json"
    if frozen.is_file():
        request = read_json(frozen)
        validate(queue, request)
        return request
    info = media_probe(video)
    if not info.get("video") or (info.get("audio") or {}).get("codec_name") != "aac" or not 0 < info.get("duration", 0) <= 121:
        raise WorkError("v4需120秒内完整原视频及其AAC原音轨")
    from lib.checkpoint import init_project
    init_project(project_id, title=title, pipeline_type="animated-explainer", pipeline_dir=queue.projects_root)
    imported = project / "assets/source-art-v4"
    imported.mkdir(parents=True, exist_ok=True)
    for key, path in originals:
        target = imported / FILES[key]
        if target.exists() and sha(target) != origins[key]["sha256"]: raise WorkError("已有v4导入来源SHA冲突")
        if not target.exists(): shutil.copy2(path, target)
    audio = imported / FILES["audio"]
    if not audio.exists(): base._extract_audio(imported / FILES["video"], audio)
    duration = base._audio_duration(audio)
    if abs(duration - info["duration"]) > 1: raise WorkError("v4源视频与原音轨时钟不一致")
    cues = base.normalize_cues(read_json(imported / FILES["cues"]), duration, source_sha=origins["video"]["sha256"])
    words = normalize_words(read_json(imported / FILES["words"]), duration, origins["video"]["sha256"])
    art = normalize_art(raw, cues, words, duration)
    for scene in art["scenes"]:
        source, target = Path(scene["path"]), imported / scene["source_name"]
        origins["scene:" + scene["id"]] = {"path": str(source), "sha256": scene["sha256"]}
        if target.exists() and sha(target) != scene["sha256"]: raise WorkError("已有v4素材SHA冲突")
        if not target.exists(): shutil.copy2(source, target)
    art = normalize_art(raw, cues, words, duration, imported=imported)
    if background is not None: art["background_path"] = str((imported / FILES["background"]).resolve())
    studio = Studio(queue.projects_root)
    draft_path = imported / "draft.json"
    if draft_path.is_file():
        draft = read_json(draft_path)
        if draft != studio.draft(project_id): raise WorkError("已有v4草稿已改变")
    else:
        draft = studio.save_draft({"id": project_id, "template_id": TEMPLATE_ID, "title": title,
            "text": "".join(c["text"] for c in cues), "input": {"soundMode": "audio", "subtitles": True,
            "ai": {"enabled": False}, "network_materials_enabled": False, "investment": {"brand": brand,
            "headline": "\n".join(art["chapters"][0]["heading"]), "cta": "\n".join(art["chapters"][-1]["heading"]),
            "opening": True, "closing": True, "emphasis": []}}})
        atomic_private(draft_path, draft)
    paths = [imported / name for name in import_files(raw).values()] + [draft_path] + [imported / scene["source_name"] for scene in art["scenes"]]
    core = {"contract": CONTRACT, "project_id": project_id, "draft": draft, "origins": origins,
            "avatar_path": str((imported / FILES["video"]).resolve()),
            "prepared": {"duration": duration, "audio_path": str(audio.resolve())}, "cues": cues,
            "art_direction": art, "audio_policy": deepcopy(AUDIO_POLICY), "sources": {str(p.relative_to(project)): sha(p) for p in paths},
            "runtime": runtime, "development_test": True, "publication": False, "cloud_calls": 0}
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
        raise WorkError("v4冻结合同或指纹无效")
    project = WorkCatalog(queue.projects_root).project(request["project_id"])
    imported = project / "assets/source-art-v4"
    raw = read_json(regular_path(imported / FILES["art_config"], project))
    expected = [imported / name for name in import_files(raw).values()] + [imported / "draft.json"]
    expected += [imported / _scene_name(i, scene) for i, scene in enumerate(raw.get("scenes", []))]
    if set(request["sources"]) != {str(p.relative_to(project)) for p in expected}: raise WorkError("不能删改v4来源绑定")
    for relative, digest in request["sources"].items():
        if sha(regular_path(project / relative, project)) != digest: raise WorkError("v4导入来源SHA已变化")
    manifest = read_json(regular_path(imported / "import-manifest.json", project))
    if manifest.get("sources") != request["sources"] or manifest.get("origins") != request["origins"]:
        raise WorkError("v4来源与原导入清单不一致")
    if (request.get("development_test") is not True or request.get("publication") is not False or request.get("cloud_calls") != 0
            or request.get("audio_policy") != AUDIO_POLICY or manifest.get("audio_policy") != AUDIO_POLICY):
        raise WorkError("v4必须零云、原速、单次固定增益且不发布")
    draft = read_json(imported / "draft.json")
    if (request["draft"] != draft or draft != Studio(queue.projects_root).draft(request["project_id"])
            or draft.get("template_id") != TEMPLATE_ID or draft.get("id") != request["project_id"]):
        raise WorkError("不能改换v4冻结草稿")
    duration = base._audio_duration(imported / FILES["audio"])
    cues = base.normalize_cues(read_json(imported / FILES["cues"]), duration, source_sha=request["origins"]["video"]["sha256"])
    words = normalize_words(read_json(imported / FILES["words"]), duration, request["origins"]["video"]["sha256"])
    art = normalize_art(raw, cues, words, duration, imported=imported)
    if art["background_path"] is not None: art["background_path"] = str((imported / FILES["background"]).resolve())
    if (request["avatar_path"] != str((imported / FILES["video"]).resolve())
            or request["prepared"] != {"duration": duration, "audio_path": str((imported / FILES["audio"]).resolve())}
            or request["cues"] != cues or request["art_direction"] != art
            or art["background_path"] is not None and art["background_sha256"] != sha(imported / FILES["background"])):
        raise WorkError("不能改换v4原视频、音轨、真实词时钟或艺术分镜")
    folder = project / "renders" / request["render_id"]
    receipt = read_json(folder / "source-art-v4-result.json")
    if receipt:
        for name, key in (("avatar-preview.mp4", "output_sha256"), ("props.json", "props_sha256"), ("art-scene-plan.json", "scene_plan_sha256")):
            if receipt.get("request_sha256") != identity or sha(regular_path(folder / name, project)) != receipt.get(key):
                raise WorkError("已有v4产物、props或分镜SHA已变化")
    elif request["runtime"] != _runtime(): raise WorkError("v4源码已变化，请为新版本重新准备")
    return project


def submit(queue, request):
    validate(queue, request)
    return queue.submit(project_id=request["project_id"], kind=KIND, source="codex", priority="normal",
        parent_job_id=request["render_id"], frozen_request=request,
        idempotency_key=CONTRACT + ":" + request["request_sha256"], start_paused=True)


def run(queue, job):
    request = job["frozen_request"]
    try:
        if job["kind"] != KIND or job["project_id"] != request["project_id"]: raise WorkError("v4任务与项目绑定不一致")
        project = validate(queue, request)
        folder = project / "renders" / request["render_id"]
        folder.mkdir(parents=True, exist_ok=True)
        receipt, output = folder / "source-art-v4-result.json", folder / "avatar-preview.mp4"
        previous = read_json(receipt)
        if not previous:
            atomic_private(folder / "art-scene-plan.json", request["art_direction"])
            from backlot.studio_composition import compose_avatar
            output = compose_avatar(folder, request["draft"], Path(request["avatar_path"]), Path(request["prepared"]["audio_path"]),
                request["prepared"]["duration"], request["cues"], art_direction=deepcopy(request["art_direction"]))
            validate(queue, request)
            if Path(output).resolve() != (folder / "avatar-preview.mp4").resolve(): raise WorkError("v4输出目录与原请求不一致")
            props = {"duration": request["prepared"]["duration"], "avatarSrc": "avatar.mp4", "audioSrc": "narration.wav",
                     "brand": request["draft"]["input"]["investment"]["brand"], "captions": request["cues"],
                     "art": props_art(request["art_direction"])}
            if read_json(regular_path(folder / "props.json", project)) != props: raise WorkError("实际v4 props与冻结品牌、词时钟或素材分镜不一致")
            previous = {"contract": CONTRACT, "request_sha256": request["request_sha256"], "output_sha256": sha(output),
                "props_sha256": sha(folder / "props.json"), "scene_plan_sha256": sha(folder / "art-scene-plan.json"),
                "source_video_sha256": request["origins"]["video"]["sha256"], "sources_unchanged": True,
                "audio_policy": deepcopy(AUDIO_POLICY), "development_test": True, "publication": False,
                "cloud_calls": 0, "provider_jobs": [], "human_review": "pending"}
            atomic_private(receipt, previous)
        work = WorkCatalog(queue.projects_root).register(request["project_id"], output, work_key="main", mode="manual",
            event_id=job["job_id"], quality_passed=False, actor="local-source-art-v4", title=request["draft"]["title"],
            summary="模板6 v4艺术开发测试；复用原片、原声和真实词时钟；" + request["art_direction"]["direction"])
        version = next(v for v in work["versions"] if v["sha256"] == sha(output))
        previous.update(work_id=work["work_id"], version_id=version["version_id"])
        atomic_private(receipt, previous)
        atomic_private(folder / "qa.json", {"template_id": TEMPLATE_ID, "variant": VARIANT,
            "caption_timing": "cached_real_word_clock", "cloud_calls": 0, "provider_jobs": [],
            "development_test": True, "publication": False, "audio_policy": deepcopy(AUDIO_POLICY), "human_review": "pending"})
        return {"status": "completed", "stage": "模板6 v4原视频艺术测试已合成，等待审核", "result": {
            "output_path": str(output), "output_sha256": sha(output), "work_id": work["work_id"], "version_id": version["version_id"],
            "qa_status": "pending", "cloud_calls": 0, "development_test": True, "variant": VARIANT}}
    except WorkError as error:
        return {"status": "failed", "stage": str(error), "error": {"type": "LocalSourceArtV4", "message": str(error)},
                "retryable": error.code == "unavailable", "safe_resume_point": "local_source_art_v4"}
