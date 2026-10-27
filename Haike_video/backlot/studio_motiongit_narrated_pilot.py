"""Queue-owned, editable 4:5 narrated motion-design pilot using existing assets."""
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
from backlot.studio_investment_recompose import KIND, fingerprint
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkCatalog, WorkError, read_json, regular_path, sha

CONTRACT = "motiongit-narrated-pilot-v1"
ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / CONTRACT
FPS = 30
WIDTH, HEIGHT = 1440, 1800
PROFILE = {"codec": "h264", "crf": 1, "image_format": "png", "x264_preset": "fast", "pixel_format": "yuv444p", "scale": 1}
EXPORT = {"video_bitrate": 20500000, "minimum_measured_bitrate": 20000000, "audio_bitrate": 192000, "pixel_format": "yuv420p"}
RECEIPTS = {"master.wav", "narration.wav", "voiceover-source.wav", "audio-receipt.json", "asset-review.json", "source-audit.json", "source-asr.json", "prior-receipt.json"}
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _require(ok, message):
    if not ok:
        raise WorkError(message)


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _name(value):
    return isinstance(value, str) and value not in {"", ".", ".."} and Path(value).name == value and not any(c in value for c in ("/", "\\", ":"))


def _text(value, limit, *, lines=1, empty=False):
    return (isinstance(value, str) and (empty or bool(value.strip())) and len(value) <= limit
            and len(value.split("\n")) <= lines and not any(ord(c) < 32 and c != "\n" for c in value))


def _position(value):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)%[ \t]+(\d+(?:\.\d+)?)%", value) if isinstance(value, str) else None
    return match is not None and all(0 <= float(v) <= 100 for v in match.groups())


def validate_props(props):
    _require(isinstance(props, dict), "模板参数必须是对象")
    allowed = {"durationFrames", "audio", "brand", "footer", "palette", "presenter", "presenterModes", "media", "scenes", "captions", "fontAssets", "wallCategories", "visualStyle"}
    _require(not set(props) - allowed, "模板包含未开放参数")
    _require(isinstance(props.get('visualStyle', 'original'), str) and props.get('visualStyle', 'original') in {'original', 'hum'}, '视觉风格只支持original或hum')
    _require(props.get("durationFrames") == 600 and props.get("audio") == "master.wav", "本次测试固定600帧、20秒，音频须绑定master.wav")
    _require(_text(props.get("brand"), 24) and _text(props.get("footer", ""), 40, empty=True), "品牌或页脚文字无效")
    if "wallCategories" in props:
        _require(isinstance(props["wallCategories"],list) and 1 <= len(props["wallCategories"]) <= 6
                 and all(_text(v,8) for v in props["wallCategories"]) and len(set(props["wallCategories"]))==len(props["wallCategories"]),
                 "素材墙分类须为1至6个不重复的短标签")
        _require(sum(len(v)*25+46 for v in props["wallCategories"])+14*(len(props["wallCategories"])-1)<=1264,
                 "素材墙分类超过单行阅读容量，请减少标签或缩短文字")
    palette = props.get("palette")
    _require(isinstance(palette, dict) and set(palette) == {"paper", "ink", "muted", "blue", "orange", "line", "dark", "light"}
             and all(isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in palette.values()), "须完整设置八个十六进制颜色槽")
    if "fontAssets" in props:
        _require(props["fontAssets"] == {"display": "display.ttf", "body": "body.ttf"}, "字体须使用display.ttf和body.ttf")
    media = props.get("media")
    _require(isinstance(media, list) and 1 <= len(media) <= 12 and all(isinstance(m, dict) for m in media), "须提供1至12项实拍素材")
    ids = set()
    for m in media:
        _require(not set(m) - {"id", "src", "thumbnail", "offset", "fit", "objectPosition", "label", "orientation"} and _text(m.get("id"), 60) and m["id"] not in ids, "素材编号无效、重复或含未开放参数")
        _require(_text(m.get("label", ""), 12, empty=True), "素材标签过长")
        _require(m.get("orientation", "landscape") in {"portrait", "landscape"}, "素材方向只支持portrait或landscape")
        ids.add(m["id"])
        _require(_name(m.get("src")) and Path(m["src"]).suffix.lower() in {".mp4", ".mov"} and _name(m.get("thumbnail"))
                 and Path(m["thumbnail"]).suffix.lower() in {".png", ".jpg", ".jpeg"}, "素材须为安全平面视频及封面文件名")
        _require(_number(m.get("offset")) and m["offset"] >= 0 and m.get("fit") == "contain"
                 and _position(m.get("objectPosition", "50% 50%")), "实拍须原速保留全幅并指定有效源入点")
    scenes = props.get("scenes")
    _require(isinstance(scenes, list) and scenes and all(isinstance(s, dict) for s in scenes), "场景清单为空")
    cursor, scene_ids, used = 0, set(), set()
    for s in scenes:
        _require(not set(s) - {"id", "from", "frames", "module", "theme", "title", "subtitle", "mediaId", "secondaryMediaId", "selection", "wallMediaIds"}, "场景包含未开放参数")
        _require(_text(s.get("id"), 60) and s["id"] not in scene_ids and _integer(s.get("from"), 0, 599)
                 and s["from"] == cursor and _integer(s.get("frames"), 30, 600) and cursor + s["frames"] <= 600, "场景须连续覆盖、不重叠且编号唯一")
        scene_ids.add(s["id"])
        _require(s.get("module") in {"statement", "select", "focus", "wall"} and s.get("theme") in {"paper", "dark"}, "模块或主题无效")
        _require(props.get('visualStyle') != 'hum' or s['module'] != 'select', 'Hum当前支持素材墙、聚焦和人物陈述；两卡select尚未适配')
        _require(_text(s.get("title"), 36, lines=3) and all(len(line) <= 16 for line in s["title"].split("\n"))
                 and _text(s.get("subtitle", ""), 36, lines=2, empty=True), "场景标题或说明过长")
        if s["module"] in {"select", "focus", "wall"}:
            _require(s.get("mediaId") in ids, "场景引用了不存在的主素材")
            used.add(s["mediaId"])
            playback = s["frames"]
            if s["module"] in {"select", "wall"}:
                if s["module"] == "select":
                    _require("wallMediaIds" not in s and s.get("secondaryMediaId") in ids and s["secondaryMediaId"] != s["mediaId"], "选择模块须提供另一张不同素材卡")
                    used.add(s["secondaryMediaId"])
                else:
                    wall = s.get("wallMediaIds")
                    _require(isinstance(wall, list) and 4 <= len(wall) <= 6 and all(isinstance(i, str) and i in ids for i in wall)
                             and len(set(wall)) == len(wall) and s["mediaId"] in wall and "secondaryMediaId" not in s,
                             "素材墙须有4至6个不重复有效素材及其中一张选中卡")
                    used.update(wall)
                sel = s.get("selection")
                keys = ("cursorFrom", "selectFrom", "expandFrom", "holdFrom")
                _require(isinstance(sel, dict) and set(sel) == set(keys) and all(_integer(sel[k], 0, s["frames"] - 1) for k in keys)
                         and all(sel[a] < sel[b] for a, b in zip(keys, keys[1:]))
                         and 8 <= sel["holdFrom"] - sel["expandFrom"] <= 30 and s["frames"] - sel["holdFrom"] >= 30, "选择、展开与稳定阅读时窗无效")
                playback -= sel["expandFrom"]
            else:
                _require("selection" not in s and "secondaryMediaId" not in s and "wallMediaIds" not in s, "聚焦模块不接受选择卡片参数")
            _require(15 <= playback <= 120, "单段连续实拍须0.5至4秒，不能冻结、循环或变速填充")
        else:
            _require(not {"mediaId", "secondaryMediaId", "selection", "wallMediaIds"} & set(s), "陈述模块不接受实拍卡片参数")
        cursor += s["frames"]
    _require(cursor == 600 and used == ids, "场景未覆盖20秒或存在未使用素材")
    presenter = props.get("presenter")
    modes = props.get("presenterModes", [])
    _require(isinstance(modes, list) and all(isinstance(m, dict) for m in modes), "人物模式须为数组")
    if presenter is None:
        _require(not modes, "无人物来源时不能声明出镜模式")
    else:
        _require(isinstance(presenter, dict) and not set(presenter) - {"src", "from", "frames", "offset", "fit", "objectPosition"}
                 and _name(presenter.get("src")) and Path(presenter["src"]).suffix.lower() in {".mp4", ".mov"}, "人物视频来源无效")
        _require(_integer(presenter.get("from"), 0, 599) and _integer(presenter.get("frames"), 1, 600)
                 and presenter["from"] + presenter["frames"] <= 600 and _number(presenter.get("offset")) and presenter["offset"] >= 0
                 and presenter.get("fit") == "contain" and _position(presenter.get("objectPosition", "50% 50%")), "人物真实出镜区间或适配方式无效")
        previous = presenter["from"]
        _require(bool(modes), "人物来源须有实际出镜时窗")
        for m in modes:
            _require(set(m) == {"from", "frames", "mode"} and _integer(m.get("from"), presenter["from"], 599)
                     and _integer(m.get("frames"), 1, presenter["frames"]) and m["from"] >= previous
                     and m["from"] + m["frames"] <= presenter["from"] + presenter["frames"] and m.get("mode") in {"large", "small"}, "人物模式重叠、越过同源窗口或无效")
            previous = m["from"] + m["frames"]
    captions = props.get("captions")
    _require(isinstance(captions, list) and captions and all(isinstance(c, dict) for c in captions), "口播字幕不能为空")
    end_ms = 0
    for c in captions:
        _require(not set(c) - {"text", "startMs", "endMs"} and _text(c.get("text"), 18) and _number(c.get("startMs")) and _number(c.get("endMs"))
                 and c["startMs"] >= end_ms and c["endMs"] > c["startMs"] and c["endMs"] <= 19800, "字幕须为原口播短句时钟，不可越界或重叠")
        end_ms = c["endMs"]



def _template_files():
    return sorted(p for p in TEMPLATE.rglob("*") if p.is_file() and p.suffix in {".tsx", ".ts", ".css", ".json"} and p.name not in {"video-template-spec.json", "props.example.json"})


def runtime():
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    files = [Path(__file__), ROOT / "backlot/production_queue_worker.py", ROOT / "tools/video/video_compose.py",
             ROOT / "remotion-composer/package-lock.json", Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf")]
    files += _template_files() + [Path(p) for p in resolve_ffmpeg_pair()]
    _require((TEMPLATE / "index.tsx").is_file() and (ROOT / "remotion-composer/node_modules").is_dir(), "可编辑模板或Remotion依赖未就绪")
    _require(all(p.is_file() for p in files), "渲染器、字体或编码器文件缺失")
    return {str(p.resolve()): sha(p) for p in files}


def _required_names(props):
    names = RECEIPTS | {m[k] for m in props["media"] for k in ("src", "thumbnail")} | set((props.get("fontAssets") or {}).values())
    if props.get("presenter"):
        names.add(props["presenter"]["src"])
    return names


def _pcm_clock(path):
    try:
        with wave.open(str(path), "rb") as w:
            _require((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getcomptype()) == (2, 2, 48000, "NONE")
                     and w.getnframes() == 960000, "母带和独立人声须为精确20秒、48kHz立体声PCM16")
    except (OSError, wave.Error) as exc:
        raise WorkError("母带或独立人声无法读取") from exc


def _validate_receipts(props, paths, media=None):
    for name in ("master.wav", "narration.wav"):
        _pcm_clock(paths[name])
    audio = read_json(paths["audio-receipt.json"])
    audit = read_json(paths["source-audit.json"])
    prior = read_json(paths["prior-receipt.json"])
    _require(audio.get("master_audio_sha256") == sha(paths["master.wav"]) and audio.get("narration") == "existing-voiceover"
             and audio.get("source_audio") == "muted" and audio.get("cloud_calls") == 0 and audio.get("paid_calls") == 0
             and audio.get("publication") is False, "本期音频须绑定既有口播母带、原片静音及零新付费调用边界")
    _require(audio.get("narration_source_sha256") == sha(paths["voiceover-source.wav"])
             and audio.get("source_selection_sha256") == sha(paths["source-audit.json"])
             and audio.get("source_asr_sha256") == sha(paths["source-asr.json"]), "口播、来源核对或原始ASR身份已变化")
    _require(audio.get("playback_rate") == 1 and audio.get("reordered") is False
             and audio.get("narration_offset_seconds") == 0 and audio.get("narration_duration_seconds") == 19.8, "本期须原速连续采用0至19.8秒口播")
    _require(isinstance(audio.get("music_provenance"), dict) and audio["music_provenance"].get("source_sha256")
             and audio["music_provenance"].get("evidence"), "配乐缺少实际来源依据")
    _require(audit.get("source_audio", {}).get("sha256") == sha(paths["voiceover-source.wav"])
             and audit.get("source_audio_receipt_sha256") == sha(paths["prior-receipt.json"])
             and audit.get("source_audio_prior_approved") is True
             and audit.get("source_asr_sha256") == sha(paths["source-asr.json"]), "既有口播确认和来源链缺失")
    _require(prior.get("approved_audio", {}).get("sha256") == sha(paths["voiceover-source.wav"])
             and prior.get("approved_audio", {}).get("user_approved") is True, "原配音确认回执不匹配")
    normalize = lambda rows: [{k: r[k] for k in ("text", "startMs", "endMs")} for r in rows]
    _require(normalize(audit.get("captions", [])) == props["captions"] == normalize(audio.get("captions", [])), "本期字幕不等于实际口播来源的冻结字幕")
    source_asr = read_json(paths["source-asr.json"])
    source_cues = source_asr.get("cues", [])
    selected = audit.get("captions", [])
    _require(all(type(c.get("source_cue_index")) is int and 0 <= c["source_cue_index"] < len(source_cues)
                 and normalize([source_cues[c["source_cue_index"]]])[0] == normalize([c])[0] for c in selected), "字幕不是原ASR对应的真实cue")
    with wave.open(str(paths["narration.wav"]), "rb") as w:
        w.setpos(950400)
        _require(not any(w.readframes(9600)), "独立人声最后0.2秒必须是无语音尾部")
    review = read_json(paths["asset-review.json"])
    _require(review.get("version") == CONTRACT and review.get("review_method") and review.get("reviewed_by"), "实拍素材缺少本期实际看帧审核")
    rows = review.get("media")
    _require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), "实拍审核记录无效")
    indexed = {r.get("media_id"): r for r in rows}
    _require(len(indexed) == len(rows) and set(indexed) == {m["id"] for m in props["media"]}, "实拍审核须完整覆盖每个素材ID")
    from PIL import Image
    videos = {}
    by_id = {m["id"]: m for m in props["media"]}
    for m in props["media"]:
        r = indexed[m["id"]]
        info = media[m["src"]] if media is not None else media_probe(paths[m["src"]])
        _require(min(int((info.get("video") or {}).get(k, 0)) for k in ("width", "height")) >= 720, "实拍原片低于720p")
        videos[m["src"]] = info
        _require(r.get("src") == m["src"] and r.get("source_sha256") == sha(paths[m["src"]])
                 and r.get("thumbnail") == m["thumbnail"] and r.get("thumbnail_sha256") == sha(paths[m["thumbnail"]]), "实拍或封面身份不一致")
        start, stop, time = r.get("source_start_seconds"), r.get("source_end_seconds"), r.get("thumbnail_timestamp")
        _require(_number(start) and _number(stop) and _number(time) and 0 <= start <= time <= stop
                 and start <= m["offset"] < stop and stop <= info["duration"] + .025, "实拍审核窗口或封面时点无效")
        seen = r.get("observed_frames")
        _require(isinstance(seen, list) and seen and all(_number(t) and start - .05 <= t <= stop + .05 for t in seen)
                 and any(abs(t - time) < .05 for t in seen) and r.get("description") and r.get("relevant") is True, "缺少封面及实拍区间内实际看帧")
        with Image.open(paths[m["thumbnail"]]) as image:
            _require(min(image.size) >= 240, "封面像素不足")
            if "orientation" in m:
                _require((image.height > image.width) == (m["orientation"] == "portrait"), "素材方向与已审核原片封面不一致")
            image.verify()
    for scene in props["scenes"]:
        if scene["module"] == "statement":
            continue
        m, r = by_id[scene["mediaId"]], indexed[scene["mediaId"]]
        start = scene["selection"]["expandFrom"] if scene["module"] in {"select", "wall"} else 0
        stop = m["offset"] + (scene["frames"] - start) / FPS
        _require(stop <= r["source_end_seconds"] + .025, "实际播放取段超出已看帧审核区间")
    if props.get("presenter"):
        p, sync = props["presenter"], audit.get("avatar_sync", {})
        _require(audit.get("source_avatar", {}).get("sha256") == sha(paths[p["src"]])
                 and (p["from"], p["frames"], p["offset"]) == (sync.get("global_output_from_frame"), sync.get("global_output_frames"), sync.get("source_video_start_seconds")), "人物出镜不符合原口播同源窗口")
        info = media[p["src"]] if media is not None else media_probe(paths[p["src"]])
        _require(p["offset"] + p["frames"] / FPS <= info["duration"] + .025, "人物源长度不足")
        _require(sync.get("embedded_audio_vs_dry_voice_zero_lag_correlation_active", 0) > .98, "人物嵌入音轨与本期口播来源未通过同钟核对")
        videos[p["src"]] = info
    if props.get("fontAssets"):
        from PIL import ImageFont
        geometry = read_json(TEMPLATE / "layout.json")
        for scene in props["scenes"]:
            role = geometry["statement" if scene["module"] == "statement" else "sceneHeader"]
            font = ImageFont.truetype(str(paths["display.ttf"]), role["titleSize"])
            lines = scene["title"].split("\n")
            _require(all(font.getlength(line) <= role["title"][2] for line in lines)
                     and len(lines) * (role["titleSize"] * 1.16 + 3) <= role["title"][3], "标题超出实际字框，请按语义换行或调整布局")
        font = ImageFont.truetype(str(paths["body.ttf"]), geometry["captionSize"])
        _require(all(font.getlength(c["text"]) <= geometry["captions"][2] for c in props["captions"]), "字幕超出实际字宽，请重新按语义分句")
    return videos



def prepare(queue, props, sources, title):
    validate_props(props)
    _require(_text(title, 100), "作品标题无效")
    _require(isinstance(sources, dict) and set(sources) == _required_names(props) and all(_name(n) for n in sources), "素材槽不完整或包含未声明文件")
    paths = {name: Path(path).resolve() for name, path in sources.items()}
    _require(all(p.is_file() and p.stat().st_size and not Path(sources[n]).is_symlink() for n, p in paths.items()), "输入文件缺失、为空或为符号链接")
    media = _validate_receipts(props, paths)
    core = {"contract": CONTRACT, "title": title, "props": deepcopy(props), "origins": {n: {"path": str(p), "sha256": sha(p)} for n, p in paths.items()},
            "media": media, "runtime": runtime(), "profile": PROFILE, "export": EXPORT, "cloud_calls": 0, "publication": False, "narration": "existing-voiceover"}
    core["project_id"] = "studio-" + fingerprint(core)[:16]
    digest = fingerprint(core)
    request = {**core, "request_sha256": digest, "render_id": "motiongit-narrated-pilot-" + digest[:20]}
    project = queue.projects_root / request["project_id"]
    frozen = project / "artifacts/motiongit-narrated-pilot-request.json"
    if frozen.exists():
        existing = read_json(frozen)
        validate(queue, existing)
        return existing
    from lib.checkpoint import init_project
    init_project(request["project_id"], title=title, pipeline_type="animated-explainer", pipeline_dir=queue.projects_root)
    assets = project / "assets/motiongit-narrated-pilot"
    assets.mkdir(parents=True, exist_ok=True)
    for name, path in paths.items():
        shutil.copy2(path, assets / name)
        _require(sha(assets / name) == request["origins"][name]["sha256"], "原片复制SHA校验失败")
    atomic_private(frozen, request)
    validate(queue, request)
    return request


def validate(queue, request, *, check_runtime=True):
    r = request
    digest = fingerprint({k: v for k, v in r.items() if k not in {"request_sha256", "render_id"}})
    _require(r.get("contract") == CONTRACT and r.get("request_sha256") == digest and r.get("render_id") == "motiongit-narrated-pilot-" + digest[:20]
             and r.get("profile") == PROFILE and r.get("export") == EXPORT and r.get("narration") == "existing-voiceover"
             and r.get("publication") is False and r.get("cloud_calls") == 0, "展示模板冻结身份或零云调用边界不一致")
    project = WorkCatalog(queue.projects_root).project(r["project_id"])
    _require(read_json(project / "artifacts/motiongit-narrated-pilot-request.json") == r, "冻结请求已变化")
    validate_props(r["props"])
    paths = {name: regular_path(project / "assets/motiongit-narrated-pilot" / name, project) for name in r["origins"]}
    _require(set(paths) == _required_names(r["props"]) and all(sha(paths[n]) == v["sha256"] for n, v in r["origins"].items()), "冻结素材已变化")
    _validate_receipts(r["props"], paths, media=r["media"])
    folder = project / "renders" / r["render_id"]
    receipt = read_json(folder / "result.json")
    if receipt:
        _require(receipt.get("request_sha256") == digest and sha(folder / "narrated-pilot.mp4") == receipt.get("output_sha256")
                 and sha(folder / "quality.json") == receipt.get("quality_sha256"), "已完成产物身份已变化")
    elif check_runtime:
        _require(runtime() == r["runtime"], "模板源码或渲染器已变化，须冻结新请求")
    return project


def submit(queue, request):
    validate(queue, request)
    return queue.submit(project_id=request["project_id"], kind=KIND, source="codex", priority="normal", parent_job_id=request["render_id"],
                        frozen_request=request, idempotency_key=CONTRACT + ":" + request["request_sha256"], start_paused=True)


def run(queue, job):
    r = job["frozen_request"]
    try:
        _require(job["kind"] == KIND and job["project_id"] == r["project_id"], "展示模板队列身份不一致")
        project = validate(queue, r)
        folder = project / "renders" / r["render_id"]
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / "narrated-pilot.mp4"
        if not read_json(folder / "result.json"):
            from tools.video.video_compose import VideoCompose
            from backlot.studio_investment_audio_v5 import measure_audio
            from lib.ffmpeg_locator import resolve_ffmpeg_pair
            ffmpeg, _ = resolve_ffmpeg_pair()
            public = folder / "public"
            public.mkdir(exist_ok=True)
            for name in r["origins"]:
                # Keep source lineage and approval receipts in private assets;
                # the browser only needs the actual composition resources.
                if name in RECEIPTS and name != "master.wav":
                    continue
                shutil.copy2(project / "assets/motiongit-narrated-pilot" / name, public / name)
            for path in _template_files():
                target = folder / "template" / path.relative_to(TEMPLATE)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            atomic_private(folder / "props.json", r["props"])
            duration = r["props"]["durationFrames"] / FPS
            from tools.analysis.composition_validator import CompositionValidator
            composition = {"render_runtime": "remotion", "cuts": [{"id": s["id"], "in_seconds": s["from"] / FPS,
                "out_seconds": (s["from"] + s["frames"]) / FPS} for s in r["props"]["scenes"]],
                "audio": {"narration": {"src": "master.wav"}}}
            atomic_private(folder / "composition-preflight.json", composition)
            preflight = CompositionValidator().execute({"composition_path": str(folder / "composition-preflight.json"), "assets_root": str(public)})
            atomic_private(folder / "preflight-result.json", preflight.data or {})
            _require(preflight.success and (preflight.data or {}).get("valid"), "成片素材或母带预检未通过")
            edits = {"render_runtime": "remotion", "composition_mode": "atelier", "renderer_family": "bespoke",
                     "timeline": {"duration_seconds": duration}, "bespoke": {"entry": str(folder / "template/index.tsx"),
                     "composition_id": "MotionGitNarratedPilot", "art_direction": str(TEMPLATE / "VISUAL-DIRECTION.md"), "props_path": str(folder / "props.json"),
                     "public_dir": str(public), "concurrency": 2, **PROFILE}}
            atomic_private(folder / "edit-decisions.json", edits)
            raw = folder / "mezzanine-crf1.mp4"
            result = VideoCompose().execute({"operation": "render", "output_path": str(raw), "edit_decisions": edits,
                                            "asset_manifest": {"assets": []}, "script_text": ""})
            atomic_private(folder / "render-report.json", {"success": result.success, "data": result.data, "error": str(result.error) if result.error else None})
            _require(result.success, "本地Remotion渲染未通过：" + str(result.error))
            command = [ffmpeg, "-nostdin", "-y", "-v", "error", "-i", str(raw), "-i", str(public / "master.wav"),
                       "-map", "0:v:0", "-map", "1:a:0", "-t", str(duration), "-c:v", "libx264", "-preset", "slow",
                       "-b:v", "20500k", "-minrate", "20500k", "-maxrate", "20500k", "-bufsize", "2000k",
                       "-x264-params", "nal-hrd=cbr:force-cfr=1:filler=1", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                       "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(output)]
            subprocess.run(command, check=True, capture_output=True, creationflags=NO_WINDOW)
            info, measured = media_probe(output), measure_audio(output)
            video = info.get("video") or {}
            _require(video.get("width") == WIDTH and video.get("height") == HEIGHT and video.get("codec_name") == "h264"
                     and video.get("pix_fmt") == "yuv420p" and abs(float(Fraction(video.get("avg_frame_rate", "0/1"))) - FPS) < .001
                     and int(video.get("nb_frames", 0)) == r["props"]["durationFrames"] and abs(info["duration"] - duration) <= .08
                     and int(video.get("bit_rate", 0)) >= EXPORT["minimum_measured_bitrate"]
                     and (info.get("audio") or {}).get("sample_rate") in {48000, "48000"} and measured["true_peak_dbtp"] <= -1.5,
                     "成片尺寸、帧数、码率、音轨或声音峰值未通过")
            subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(output), "-f", "null", "-"], check=True, capture_output=True, creationflags=NO_WINDOW)
            atomic_private(folder / "quality.json", {"media": info, "video_stream": video, "audio": measured, "full_decode": "passed",
                "render_command": (result.data or {}).get("render_command"), "export_command": command, "narration": "existing-voiceover", "source_audio": "muted",
                "original_assets_sha_verified": True, "visual_review": "pending", "continuous_watching": "pending", "device_listening": "pending"})
            validate(queue, r)
            atomic_private(folder / "result.json", {"request_sha256": r["request_sha256"], "output_sha256": sha(output),
                "quality_sha256": sha(folder / "quality.json"), "cloud_calls": 0, "publication": False})
        work = WorkCatalog(queue.projects_root).register(r["project_id"], output, work_key="main", mode="manual", event_id=job["job_id"],
            quality_passed=False, actor="motiongit-narrated-pilot", title=r["title"], summary="20秒4:5口播视觉开发样片；既有配音和人物复用，原片静音；实测≥20Mbps；未发布")
        version = next(v for v in work["versions"] if v["sha256"] == sha(output))
        return {"status": "completed", "stage": "20秒口播视觉测试已合成，等待观看", "result": {"output_path": str(output),
                "output_sha256": sha(output), "work_id": work["work_id"], "version_id": version["version_id"], "qa_status": "pending", "cloud_calls": 0}}
    except (WorkError, subprocess.SubprocessError) as exc:
        return {"status": "failed", "stage": str(exc)[:1200], "error": {"type": "MotionGitNarratedPilot", "message": str(exc)[:1200]},
                "retryable": True, "safe_resume_point": "motiongit_narrated_pilot"}
