"""Editable, speech-free store films with immutable inputs and queue execution."""
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

CONTRACT = "store-motion-showcase-v1"
ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / CONTRACT
FPS = 30
WIDTH, HEIGHT = 1440, 1800
PROFILE = {"codec": "h264", "crf": 1, "image_format": "png", "x264_preset": "fast", "pixel_format": "yuv444p", "scale": 1}
EXPORT = {"video_bitrate": 20500000, "minimum_measured_bitrate": 20000000, "audio_bitrate": 192000, "pixel_format": "yuv420p"}
RECEIPTS = {"master.wav", "audio-receipt.json", "asset-review.json"}
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


def validate_props(props):
    _require(isinstance(props, dict), "模板参数必须是对象")
    _require(not set(props) - {"durationFrames", "audio", "brand", "location", "palette", "shots", "chapters", "motion", "fontAssets"}, "不支持的模板字段；本模板不接受口播、数字人或可执行代码")
    duration = props.get("durationFrames")
    _require(_integer(duration, 60, 1800), "无口播展示片须为2至60秒的整数帧")
    _require(props.get("audio") == "master.wav", "音频必须绑定同一无口播master.wav母带")
    _require(_text(props.get("brand"), 24) and _text(props.get("location"), 48), "品牌或地点文字为空、超长或含控制符")
    palette = props.get("palette")
    _require(isinstance(palette, dict) and set(palette) == {"paper", "ink", "muted", "blue", "orange", "line"}
             and all(isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in palette.values()), "配色须完整使用六个#RRGGBB颜色槽")
    motion = props.get("motion", {})
    _require(isinstance(motion, dict) and not set(motion) - {"enterFrames", "exitFrames", "lineFrames"}, "动效参数无效")
    for key, default, low, high in (("enterFrames", 16, 8, 24), ("exitFrames", 10, 4, 16), ("lineFrames", 22, 12, 30)):
        _require(_integer(motion.get(key, default), low, high), "入场须8至24帧、退场4至16帧、线条12至30帧")
    if "fontAssets" in props:
        _require(props["fontAssets"] == {"display": "display.ttf", "body": "body.ttf"}, "字体须使用display.ttf和body.ttf平面资源")
    shots = props.get("shots")
    _require(isinstance(shots, list) and 1 <= len(shots) <= 60 and all(isinstance(s, dict) for s in shots), "须提供1至60个实拍镜头")
    cursor, ids, previous, same_source_frames = 0, set(), None, 0
    allowed = {"id", "src", "from", "frames", "offset", "fit", "objectPosition", "layout", "title", "subtitle", "kicker", "chapter"}
    for shot in shots:
        _require(not set(shot) - allowed, "镜头含未开放字段，原片音轨始终静音")
        _require(_text(shot.get("id"), 80) and shot["id"] not in ids, "镜头编号为空或重复")
        ids.add(shot["id"])
        _require(_name(shot.get("src")) and Path(shot["src"]).suffix.lower() in {".mp4", ".mov"}, "镜头来源须为安全平面视频文件名")
        _require(_integer(shot.get("from"), 0, duration - 1) and shot["from"] == cursor
                 and _integer(shot.get("frames"), 30, 120) and cursor + shot["frames"] <= duration, "镜头须连续覆盖且单镜1至4秒，不可重叠或留空")
        _require(_number(shot.get("offset")) and shot["offset"] >= 0, "原片入点必须是非负有限秒数")
        _require(shot.get("fit") in {"contain", "cover"} and shot.get("layout") in {"wide", "portrait-left", "portrait-right", "portrait-center"}, "素材适配方式或布局无效")
        position = shot.get("objectPosition", "50% 50%")
        match = re.fullmatch(r"(\d+(?:\.\d+)?)%[ \t]+(\d+(?:\.\d+)?)%", position) if isinstance(position, str) else None
        _require(match is not None and all(0 <= float(v) <= 100 for v in match.groups()), "裁切位置须为两组0至100%的数值")
        _require(_text(shot.get("title"), 36, lines=3) and all(len(line) <= 14 for line in shot["title"].split("\n")), "标题须为最多三行的短句，每行最多14字")
        _require(_text(shot.get("subtitle", ""), 48, lines=2, empty=True)
                 and _text(shot.get("kicker", ""), 24, empty=True) and _text(shot.get("chapter", ""), 24, empty=True), "镜头说明、标签或章节超长")
        reading = shot["frames"] - motion.get("enterFrames", 16) - motion.get("exitFrames", 10)
        _require(reading >= 18 and (shot["frames"] >= 60 or len(shot["title"].replace("\n", "")) <= 8), "短镜头没有足够稳定阅读时间，请缩短标题或延长真实源区间")
        same_source_frames = same_source_frames + shot["frames"] if previous == shot["src"] else shot["frames"]
        _require(same_source_frames <= 120, "连续同源镜头超过4秒，不能拆分绕过")
        previous, cursor = shot["src"], cursor + shot["frames"]
    _require(cursor == duration, "主实拍轨未覆盖完整音乐时钟")
    chapters = props.get("chapters")
    _require(isinstance(chapters, list) and chapters and all(isinstance(c, dict) for c in chapters), "章节清单为空")
    last, chapter_ids = -1, set()
    for c in chapters:
        _require(set(c) == {"id", "from", "label"} and _text(c.get("id"), 60) and c["id"] not in chapter_ids
                 and _integer(c.get("from"), 0, duration - 1) and c["from"] > last and (last >= 0 or c["from"] == 0)
                 and _text(c.get("label"), 16), "章节须从0帧递增、编号唯一且标签可读")
        last = c["from"]
        chapter_ids.add(c["id"])
    _require(all(not s.get("chapter") or s["chapter"] in chapter_ids for s in shots), "镜头引用了不存在的章节编号")


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
    fonts = set((props.get("fontAssets") or {}).values())
    return RECEIPTS | {s["src"] for s in props["shots"]} | fonts


def _validate_title_widths(props, paths):
    """Measure supplied font outlines against the same editable layout boxes."""
    if not props.get("fontAssets"):
        return
    from PIL import ImageFont
    layout = read_json(TEMPLATE / "layout.json")
    try:
        for shot in props["shots"]:
            geometry = layout["layouts"][shot["layout"]]
            font = ImageFont.truetype(str(paths[props["fontAssets"]["display"]]), geometry["titleSize"])
            width = geometry["title"][2] - 4
            _require(all(font.getlength(line) - max(0, len(line) - 1) * 3 <= width for line in shot["title"].split("\n")),
                     "标题超出本布局实际字宽，请按语义换行或修改版式后重新验收")
    except (OSError, KeyError, TypeError) as exc:
        raise WorkError("字体或布局无法测量，请恢复声明的有效资源") from exc


def _validate_receipts(props, paths, media=None):
    _validate_title_widths(props, paths)
    duration = props["durationFrames"] / FPS
    try:
        with wave.open(str(paths["master.wav"]), "rb") as w:
            _require((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getcomptype()) == (2, 2, 48000, "NONE"), "母带须为48kHz立体声PCM16")
            _require(w.getnframes() == props["durationFrames"] * 1600, "音乐母带样本数与帧时钟不一致")
    except (wave.Error, OSError) as exc:
        raise WorkError("母带无法读取") from exc
    audio = read_json(paths["audio-receipt.json"])
    _require(audio.get("master_audio_sha256") == sha(paths["master.wav"]) and audio.get("narration") == "none"
             and audio.get("source_audio") == "muted" and audio.get("cloud_calls") == 0, "音频回执须绑定本期母带且明确无口播、原片静音及零云调用")
    _require(isinstance(audio.get("music_provenance"), dict) and audio["music_provenance"].get("source_sha256")
             and audio["music_provenance"].get("evidence"), "配乐缺少真实来源与使用依据")
    review = read_json(paths["asset-review.json"])
    _require(review.get("version") == CONTRACT and review.get("review_method") and review.get("reviewed_by"), "素材缺少本次实际观看记录")
    reviews = review.get("shots")
    _require(isinstance(reviews, list) and all(isinstance(s, dict) for s in reviews), "素材审核记录无效")
    indexed = {s.get("id"): s for s in reviews}
    _require(len(indexed) == len(reviews) and set(indexed) == {s["id"] for s in props["shots"]}, "素材审核未完整覆盖全部镜头")
    videos = {}
    for s in props["shots"]:
        path = paths[s["src"]]
        if s["src"] not in videos:
            info = media[s["src"]] if media is not None else media_probe(path)
            _require(min(int((info.get("video") or {}).get(k, 0)) for k in ("width", "height")) >= 720, "原始实拍低于720p")
            videos[s["src"]] = info
        _require(s["offset"] + s["frames"] / FPS <= videos[s["src"]]["duration"] + .025, "镜头取段超出原片长度")
        r = indexed[s["id"]]
        _require(r.get("src") == s["src"] and r.get("source_sha256") == sha(path), "素材审核与原片SHA不匹配")
        start, end = r.get("source_start_seconds"), r.get("source_end_seconds")
        _require(_number(start) and _number(end) and abs(start - s["offset"]) < .025
                 and abs(end - s["offset"] - s["frames"] / FPS) < .025, "素材审核区间不是本次实际采用区间")
        times = r.get("observed_frames")
        _require(isinstance(times, list) and times and all(_number(t) and start - .05 <= t <= end + .05 for t in times)
                 and r.get("description") and r.get("relevant") is True, "素材缺少区间内实际看帧及相关性判断")
    return videos


def prepare(queue, props, sources, title):
    validate_props(props)
    _require(_text(title, 100), "作品标题无效")
    _require(isinstance(sources, dict) and set(sources) == _required_names(props) and all(_name(n) for n in sources), "素材槽不完整或包含未声明文件")
    paths = {name: Path(path).resolve() for name, path in sources.items()}
    _require(all(p.is_file() and p.stat().st_size and not Path(sources[n]).is_symlink() for n, p in paths.items()), "输入文件缺失、为空或为符号链接")
    media = _validate_receipts(props, paths)
    core = {"contract": CONTRACT, "title": title, "props": deepcopy(props), "origins": {n: {"path": str(p), "sha256": sha(p)} for n, p in paths.items()},
            "media": media, "runtime": runtime(), "profile": PROFILE, "export": EXPORT, "cloud_calls": 0, "publication": False, "narration": "none"}
    core["project_id"] = "studio-" + fingerprint(core)[:16]
    digest = fingerprint(core)
    request = {**core, "request_sha256": digest, "render_id": "store-motion-" + digest[:20]}
    project = queue.projects_root / request["project_id"]
    frozen = project / "artifacts/store-motion-request.json"
    if frozen.exists():
        existing = read_json(frozen)
        validate(queue, existing)
        return existing
    from lib.checkpoint import init_project
    init_project(request["project_id"], title=title, pipeline_type="animated-explainer", pipeline_dir=queue.projects_root)
    assets = project / "assets/store-motion"
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
    _require(r.get("contract") == CONTRACT and r.get("request_sha256") == digest and r.get("render_id") == "store-motion-" + digest[:20]
             and r.get("profile") == PROFILE and r.get("export") == EXPORT and r.get("narration") == "none"
             and r.get("publication") is False and r.get("cloud_calls") == 0, "展示模板冻结身份或零云调用边界不一致")
    project = WorkCatalog(queue.projects_root).project(r["project_id"])
    _require(read_json(project / "artifacts/store-motion-request.json") == r, "冻结请求已变化")
    validate_props(r["props"])
    paths = {name: regular_path(project / "assets/store-motion" / name, project) for name in r["origins"]}
    _require(set(paths) == _required_names(r["props"]) and all(sha(paths[n]) == v["sha256"] for n, v in r["origins"].items()), "冻结素材已变化")
    _validate_receipts(r["props"], paths, media=r["media"])
    folder = project / "renders" / r["render_id"]
    receipt = read_json(folder / "result.json")
    if receipt:
        _require(receipt.get("request_sha256") == digest and sha(folder / "showcase.mp4") == receipt.get("output_sha256")
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
        output = folder / "showcase.mp4"
        if not read_json(folder / "result.json"):
            from tools.video.video_compose import VideoCompose
            from backlot.studio_investment_audio_v5 import measure_audio
            from lib.ffmpeg_locator import resolve_ffmpeg_pair
            ffmpeg, _ = resolve_ffmpeg_pair()
            public = folder / "public"
            public.mkdir(exist_ok=True)
            for name in r["origins"]:
                shutil.copy2(project / "assets/store-motion" / name, public / name)
            for path in _template_files():
                target = folder / "template" / path.relative_to(TEMPLATE)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            atomic_private(folder / "props.json", r["props"])
            duration = r["props"]["durationFrames"] / FPS
            from tools.analysis.composition_validator import CompositionValidator
            composition = {"render_runtime": "remotion", "cuts": [
                {"id": s["id"], "source": s["src"], "in_seconds": s["from"] / FPS,
                 "out_seconds": (s["from"] + s["frames"]) / FPS} for s in r["props"]["shots"]],
                "audio": {"music": {"src": "master.wav"}}}
            atomic_private(folder / "composition-preflight.json", composition)
            preflight = CompositionValidator().execute({"composition_path": str(folder / "composition-preflight.json"), "assets_root": str(public)})
            atomic_private(folder / "preflight-result.json", preflight.data or {})
            _require(preflight.success and (preflight.data or {}).get("valid"), "成片素材或母带预检未通过")
            edits = {"render_runtime": "remotion", "composition_mode": "atelier", "renderer_family": "bespoke",
                     "timeline": {"duration_seconds": duration}, "bespoke": {"entry": str(folder / "template/index.tsx"),
                     "composition_id": "StoreMotionShowcase", "art_direction": str(TEMPLATE / "VISUAL-DIRECTION.md"), "props_path": str(folder / "props.json"),
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
                "render_command": (result.data or {}).get("render_command"), "export_command": command, "narration": "none", "source_audio": "muted",
                "original_assets_sha_verified": True, "visual_review": "pending", "continuous_watching": "pending", "device_listening": "pending"})
            validate(queue, r)
            atomic_private(folder / "result.json", {"request_sha256": r["request_sha256"], "output_sha256": sha(output),
                "quality_sha256": sha(folder / "quality.json"), "cloud_calls": 0, "publication": False})
        work = WorkCatalog(queue.projects_root).register(r["project_id"], output, work_key="main", mode="manual", event_id=job["job_id"],
            quality_passed=False, actor="store-motion-showcase", title=r["title"], summary="无口播店长实拍开发短样；原片静音、配乐和音效；实测≥20Mbps；未发布")
        version = next(v for v in work["versions"] if v["sha256"] == sha(output))
        return {"status": "completed", "stage": "无口播店长短样已合成，等待观看", "result": {"output_path": str(output),
                "output_sha256": sha(output), "work_id": work["work_id"], "version_id": version["version_id"], "qa_status": "pending", "cloud_calls": 0}}
    except (WorkError, subprocess.SubprocessError) as exc:
        return {"status": "failed", "stage": str(exc)[:1200], "error": {"type": "StoreMotionShowcase", "message": str(exc)[:1200]},
                "retryable": True, "safe_resume_point": "store_motion_showcase"}
