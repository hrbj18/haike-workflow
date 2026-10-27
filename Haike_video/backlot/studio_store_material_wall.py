"""Editable material-wall films with immutable inputs and queue execution."""
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

CONTRACT = "store-material-wall-v1"
ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / CONTRACT
FPS = 30
WIDTH, HEIGHT = 1920, 1080
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


def _position(value):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)%[ \t]+(\d+(?:\.\d+)?)%", value) if isinstance(value, str) else None
    return match is not None and all(0 <= float(v) <= 100 for v in match.groups())


def validate_props(props):
    _require(isinstance(props, dict), "Wall props must be an object")
    allowed = {"durationFrames", "audio", "brand", "title", "closingTitle", "footer", "palette", "tabs", "cards", "moments", "tabChanges", "fontAssets"}
    _require(not set(props) - allowed, "Unsupported wall fields; narration and executable code are not accepted")
    duration = props.get("durationFrames")
    _require(_integer(duration, 180, 1800), "Duration must be 6 to 60 seconds in integer frames")
    _require(props.get("audio") == "master.wav", "Audio must bind the speech-free master.wav")
    for key, limit in (("brand", 24), ("title", 25), ("closingTitle", 20)):
        _require(_text(props.get(key), limit), "Missing or overlong " + key)
    _require(_text(props.get("footer", ""), 40, empty=True), "Invalid footer")
    palette = props.get("palette")
    _require(isinstance(palette, dict) and set(palette) == {"paper", "ink", "muted", "blue", "orange", "line"}
             and all(isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in palette.values()), "Six #RRGGBB palette slots are required")
    if "fontAssets" in props:
        _require(props["fontAssets"] == {"display": "display.ttf", "body": "body.ttf"}, "Fonts must use flat display.ttf/body.ttf resources")
    cards = props.get("cards")
    _require(isinstance(cards, list) and 1 <= len(cards) <= 8 and all(isinstance(c, dict) for c in cards), "Wall needs 1 to 8 cards")
    card_ids = set()
    allowed_card = {"id", "title", "category", "badge", "thumbnail", "src", "offset", "fit", "objectPosition", "imageFit", "imagePosition"}
    for c in cards:
        _require(not set(c) - allowed_card, "Unsupported card field; preview playback is not exposed in this contract")
        _require(_text(c.get("id"), 60) and c["id"] not in card_ids, "Missing or duplicate card id")
        card_ids.add(c["id"])
        _require(_name(c.get("src")) and Path(c["src"]).suffix.lower() in {".mp4", ".mov"}, "Card source must be a safe flat video filename")
        _require(_name(c.get("thumbnail")) and Path(c["thumbnail"]).suffix.lower() in {".jpg", ".jpeg", ".png"}, "Thumbnail must be a safe flat image filename")
        _require(_number(c.get("offset")) and c["offset"] >= 0 and c.get("fit") == "contain", "Expanded real footage must preserve the full frame at a valid source offset")
        _require(c.get("imageFit", "cover") in {"cover", "contain"} and _position(c.get("objectPosition", "50% 50%"))
                 and _position(c.get("imagePosition", "50% 50%")), "Invalid card fitting or position")
        _require(_text(c.get("title"), 16) and _text(c.get("category"), 12) and _text(c.get("badge"), 12), "Card title/category/badge is empty or too long")
    tabs = props.get("tabs")
    _require(isinstance(tabs, list) and 1 <= len(tabs) <= 6 and all(isinstance(t, dict) for t in tabs), "Wall needs 1 to 6 tabs")
    tab_by_id = {}
    for t in tabs:
        _require(set(t) == {"id", "label", "order"} and _text(t.get("id"), 60) and t["id"] not in tab_by_id and _text(t.get("label"), 12), "Invalid or duplicate tab")
        order = t.get("order")
        _require(isinstance(order, list) and 1 <= len(order) <= len(cards) and all(isinstance(i, str) for i in order)
                 and len(set(order)) == len(order) and set(order) <= card_ids, "Tab order must contain unique existing card ids")
        tab_by_id[t["id"]] = t
    changes = props.get("tabChanges")
    _require(isinstance(changes, list) and changes and all(isinstance(t, dict) for t in changes), "Missing tab clock")
    last = -24
    for t in changes:
        _require(set(t) == {"from", "tabId"} and _integer(t.get("from"), 0, duration - 1)
                 and t["from"] >= last + 24 and (last != -24 or t["from"] == 0)
                 and t.get("tabId") in tab_by_id, "Tab changes must begin at 0, reference existing tabs, and leave 24 frames for reorder")
        last = t["from"]
    _require(set(tab_by_id[changes[0]["tabId"]]["order"]) == card_ids, "Initial tab must display all cards")
    moments = props.get("moments")
    _require(isinstance(moments, list) and 1 <= len(moments) <= 12 and all(isinstance(m, dict) for m in moments), "Missing selected-card moments")
    ids, last_end = set(), 0
    clock = ("cursorFrom", "selectFrom", "expandFrom", "holdFrom", "collapseFrom", "end")
    for m in moments:
        _require(set(m) == {"id", "cardId", "tabId", "sourceOffset", *clock} and _text(m.get("id"), 60)
                 and m["id"] not in ids and m.get("cardId") in card_ids and m.get("tabId") in tab_by_id, "Invalid selected-card identity")
        ids.add(m["id"])
        values = [m.get(k) for k in clock]
        _require(all(_integer(v, 0, duration) for v in values) and all(a < b for a, b in zip(values, values[1:]))
                 and m["cursorFrom"] >= max(54, last_end) and m["end"] <= duration - 90, "Moment clocks must be ordered, non-overlapping, after cascade and before closing")
        _require(8 <= m["holdFrom"] - m["expandFrom"] <= 30 and 8 <= m["end"] - m["collapseFrom"] <= 30
                 and m["collapseFrom"] - m["holdFrom"] >= 60 and 30 <= m["end"] - m["expandFrom"] <= 120, "Real selected playback needs 2 seconds stable view and at most 4 seconds total")
        _require(_number(m.get("sourceOffset")) and m["sourceOffset"] >= 0, "Source offset must be a finite nonnegative second")
        active = next(c for c in reversed(changes) if c["from"] <= m["cursorFrom"])
        _require(active["tabId"] == m["tabId"] and m["cardId"] in tab_by_id[m["tabId"]]["order"]
                 and not any(m["cursorFrom"] < c["from"] < m["end"] for c in changes), "Selected card must be visible in the active tab throughout its moment")
        last_end = m["end"]


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
    return RECEIPTS | {c[k] for c in props["cards"] for k in ("src", "thumbnail")} | set((props.get("fontAssets") or {}).values())


def _validate_title_widths(props, paths):
    if not props.get("fontAssets"):
        return
    from PIL import ImageFont
    layout = read_json(TEMPLATE / "layout.json")
    font = ImageFont.truetype(str(paths[props["fontAssets"]["display"]]), layout["titleSize"])
    _require(all(font.getlength(props[k]) <= layout["title"][2] for k in ("title", "closingTitle")), "Heading exceeds the actual editable title box")
    font = ImageFont.truetype(str(paths[props["fontAssets"]["body"]]), layout["cardTitleSize"])
    _require(all(font.getlength(c["title"]) <= layout["grid"]["width"] - 44 for c in props["cards"]), "Card title exceeds its actual width")


def _validate_receipts(props, paths, media=None):
    _validate_title_widths(props, paths)
    try:
        with wave.open(str(paths["master.wav"]), "rb") as w:
            _require((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getcomptype()) == (2, 2, 48000, "NONE"), "Master must be 48k stereo PCM16")
            _require(w.getnframes() == props["durationFrames"] * 1600, "Master samples must match the output frame clock exactly")
    except (wave.Error, OSError) as exc:
        raise WorkError("Cannot read audio master") from exc
    audio = read_json(paths["audio-receipt.json"])
    _require(audio.get("master_audio_sha256") == sha(paths["master.wav"]) and audio.get("narration") == "none"
             and audio.get("source_audio") == "muted" and audio.get("cloud_calls") == 0, "Audio receipt must bind this master, mute original audio and declare no narration/cloud calls")
    _require(isinstance(audio.get("music_provenance"), dict) and audio["music_provenance"].get("source_sha256")
             and audio["music_provenance"].get("evidence"), "Music needs actual provenance evidence")
    review = read_json(paths["asset-review.json"])
    _require(review.get("version") == CONTRACT and review.get("review_method") and review.get("reviewed_by"), "Missing actual visual review record")
    rows = review.get("cards")
    _require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), "Invalid card review")
    indexed = {r.get("card_id"): r for r in rows}
    _require(len(indexed) == len(rows) and set(indexed) == {c["id"] for c in props["cards"]}, "Review must cover every card exactly once")
    from PIL import Image
    videos = {}
    for c in props["cards"]:
        path = paths[c["src"]]
        if c["src"] not in videos:
            info = media[c["src"]] if media is not None else media_probe(path)
            _require(min(int((info.get("video") or {}).get(k, 0)) for k in ("width", "height")) >= 720, "Original footage must be at least 720p")
            videos[c["src"]] = info
        r = indexed[c["id"]]
        _require(r.get("src") == c["src"] and r.get("source_sha256") == sha(path)
                 and r.get("thumbnail") == c["thumbnail"] and r.get("thumbnail_sha256") == sha(paths[c["thumbnail"]]), "Card source/poster SHA or identity changed")
        start, end, timestamp = r.get("source_start_seconds"), r.get("source_end_seconds"), r.get("thumbnail_timestamp")
        _require(_number(start) and _number(end) and _number(timestamp) and 0 <= start <= timestamp <= end
                 and end <= videos[c["src"]]["duration"] + .025 and start <= c["offset"] < end, "Invalid reviewed source window or poster time")
        times = r.get("observed_frames")
        _require(isinstance(times, list) and times and all(_number(t) and start - .05 <= t <= end + .05 for t in times)
                 and any(abs(timestamp - t) < .05 for t in times) and r.get("description") and r.get("relevant") is True, "Poster/source needs actual observed frames and relevance")
        with Image.open(paths[c["thumbnail"]]) as image:
            _require(min(image.size) >= 240, "Poster resolution is insufficient")
            image.verify()
    by_id = {c["id"]: c for c in props["cards"]}
    for m in props["moments"]:
        r = indexed[m["cardId"]]
        end = m["sourceOffset"] + (m["end"] - m["expandFrom"]) / FPS
        _require(m["sourceOffset"] >= r["source_start_seconds"] - .025 and end <= r["source_end_seconds"] + .025,
                 "Selected continuous source interval exceeds the actually reviewed window")
        _require(end <= videos[by_id[m["cardId"]]["src"]]["duration"] + .025, "Selected interval exceeds original footage")
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
    request = {**core, "request_sha256": digest, "render_id": "store-material-wall-" + digest[:20]}
    project = queue.projects_root / request["project_id"]
    frozen = project / "artifacts/store-material-wall-request.json"
    if frozen.exists():
        existing = read_json(frozen)
        validate(queue, existing)
        return existing
    from lib.checkpoint import init_project
    init_project(request["project_id"], title=title, pipeline_type="animated-explainer", pipeline_dir=queue.projects_root)
    assets = project / "assets/store-material-wall"
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
    _require(r.get("contract") == CONTRACT and r.get("request_sha256") == digest and r.get("render_id") == "store-material-wall-" + digest[:20]
             and r.get("profile") == PROFILE and r.get("export") == EXPORT and r.get("narration") == "none"
             and r.get("publication") is False and r.get("cloud_calls") == 0, "展示模板冻结身份或零云调用边界不一致")
    project = WorkCatalog(queue.projects_root).project(r["project_id"])
    _require(read_json(project / "artifacts/store-material-wall-request.json") == r, "冻结请求已变化")
    validate_props(r["props"])
    paths = {name: regular_path(project / "assets/store-material-wall" / name, project) for name in r["origins"]}
    _require(set(paths) == _required_names(r["props"]) and all(sha(paths[n]) == v["sha256"] for n, v in r["origins"].items()), "冻结素材已变化")
    _validate_receipts(r["props"], paths, media=r["media"])
    folder = project / "renders" / r["render_id"]
    receipt = read_json(folder / "result.json")
    if receipt:
        _require(receipt.get("request_sha256") == digest and sha(folder / "material-wall.mp4") == receipt.get("output_sha256")
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
        output = folder / "material-wall.mp4"
        if not read_json(folder / "result.json"):
            from tools.video.video_compose import VideoCompose
            from backlot.studio_investment_audio_v5 import measure_audio
            from lib.ffmpeg_locator import resolve_ffmpeg_pair
            ffmpeg, _ = resolve_ffmpeg_pair()
            public = folder / "public"
            public.mkdir(exist_ok=True)
            for name in r["origins"]:
                shutil.copy2(project / "assets/store-material-wall" / name, public / name)
            for path in _template_files():
                target = folder / "template" / path.relative_to(TEMPLATE)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            atomic_private(folder / "props.json", r["props"])
            duration = r["props"]["durationFrames"] / FPS
            from tools.analysis.composition_validator import CompositionValidator
            composition = {"render_runtime": "remotion", "cuts": [
                {"id": m["id"], "source": next(c["src"] for c in r["props"]["cards"] if c["id"] == m["cardId"]),
                 "in_seconds": m["expandFrom"] / FPS, "out_seconds": m["end"] / FPS} for m in r["props"]["moments"]],
                "audio": {"music": {"src": "master.wav"}}}
            atomic_private(folder / "composition-preflight.json", composition)
            preflight = CompositionValidator().execute({"composition_path": str(folder / "composition-preflight.json"), "assets_root": str(public)})
            atomic_private(folder / "preflight-result.json", preflight.data or {})
            _require(preflight.success and (preflight.data or {}).get("valid"), "成片素材或母带预检未通过")
            edits = {"render_runtime": "remotion", "composition_mode": "atelier", "renderer_family": "bespoke",
                     "timeline": {"duration_seconds": duration}, "bespoke": {"entry": str(folder / "template/index.tsx"),
                     "composition_id": "StoreMaterialWall", "art_direction": str(TEMPLATE / "VISUAL-DIRECTION.md"), "props_path": str(folder / "props.json"),
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
            quality_passed=False, actor="store-material-wall", title=r["title"], summary="无口播店长实拍开发短样；原片静音、配乐和音效；实测≥20Mbps；未发布")
        version = next(v for v in work["versions"] if v["sha256"] == sha(output))
        return {"status": "completed", "stage": "无口播店长短样已合成，等待观看", "result": {"output_path": str(output),
                "output_sha256": sha(output), "work_id": work["work_id"], "version_id": version["version_id"], "qa_status": "pending", "cloud_calls": 0}}
    except (WorkError, subprocess.SubprocessError) as exc:
        return {"status": "failed", "stage": str(exc)[:1200], "error": {"type": "StoreMaterialWall", "message": str(exc)[:1200]},
                "retryable": True, "safe_resume_point": "store_material_wall"}
