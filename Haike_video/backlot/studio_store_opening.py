"""Frozen, queue-owned opening films with reviewed original footage and short avatars."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import wave

from backlot.studio import atomic_private
from backlot.studio_investment_recompose import KIND, fingerprint
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkCatalog, WorkError, read_json, regular_path, sha

CONTRACT = "store-opening-v1"
ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/store-opening-v1"
FPS = 30
PROFILE = {"codec": "h264", "crf": 1, "image_format": "png", "x264_preset": "fast", "pixel_format": "yuv444p", "scale": 1}
EXPORT = {"video_bitrate": 20500000, "minimum_measured_bitrate": 20000000, "audio_bitrate": 192000, "pixel_format": "yuv420p"}
RECEIPTS = {"master.wav", "audio-receipt.json", "asr.json", "asset-review.json"}
FONT_ASSETS = {"display": "display.ttf", "body": "body.ttf", "latin": "latin.ttf"}
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def _name(value):
    return isinstance(value, str) and value not in {"", ".", ".."} and Path(value).name == value and not any(c in value for c in ("/", "\\", ":"))


def _require(ok, message):
    if not ok:
        raise WorkError(message)


def _font_names(props):
    if "fontAssets" not in props:
        return set()
    _require(isinstance(props["fontAssets"], dict) and props["fontAssets"] == FONT_ASSETS,
             "字体槽必须完整使用display.ttf、body.ttf、latin.ttf三个安全平面文件名")
    return set(FONT_ASSETS.values())


def _required_names(props):
    return (RECEIPTS | {s["src"] for s in props["shots"]}
            | {a["src"] for a in props.get("avatarSegments", [])} | _font_names(props))


def _validate_font_file(path):
    """Reject missing, oversized or non-sfnt assets before browser font loading."""
    try:
        size = path.stat().st_size
        _require(1024 <= size <= 32 * 1024 * 1024, "字体文件大小须在1KB至32MB之间")
        with path.open("rb") as stream:
            header = stream.read(12)
            _require(len(header) == 12 and header[:4] in {b"\x00\x01\x00\x00", b"OTTO"},
                     "字体文件不是有效的TrueType/OpenType字体头")
            count = struct.unpack_from(">H", header, 4)[0]
            _require(4 <= count <= 128 and 12 + count * 16 <= size, "字体表目录无效")
            directory = stream.read(count * 16)
            _require(len(directory) == count * 16, "字体表目录不完整")
            tables = {}
            for index in range(count):
                tag, _, offset, length = struct.unpack_from(">4sIII", directory, index * 16)
                _require(tag not in tables and offset >= 12 + count * 16
                         and length > 0 and offset + length <= size, "字体表目录越界或重复")
                tables[tag] = (offset, length)
            _require({b"head", b"name", b"cmap", b"maxp"} <= set(tables), "字体缺少必要字形或名称表")
    except (OSError, struct.error) as exc:
        raise WorkError("字体文件无法安全读取") from exc


def _template_files():
    return sorted(p for p in TEMPLATE.rglob("*") if p.is_file() and (p.suffix in {".tsx", ".ts", ".css", ".ttf", ".otf", ".woff2"} or p.name == "layout.json"))


def runtime():
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    files = [Path(__file__), ROOT / "backlot/production_queue_worker.py", ROOT / "tools/video/video_compose.py",
             Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/msyhbd.ttc"), Path("C:/Windows/Fonts/simhei.ttf")]
    files += _template_files() + [Path(p) for p in resolve_ffmpeg_pair()]
    _require((TEMPLATE / "index.tsx").is_file(), "开业模板实现入口缺失")
    return {str(p.resolve()): sha(p) for p in files}


def validate_props(props):
    """Validate edit geometry before copying media or submitting any queue work."""
    _require(isinstance(props, dict), "开业模板参数必须是对象")
    _font_names(props)
    duration = props.get("durationFrames")
    content_mode = props.get("contentMode", "opening")
    _require(content_mode in {"opening", "community-cend"}, "门店内容模式无效")
    _require(type(props.get("style")) is int and props["style"] in range(22, 27) and _integer(duration, 30, 1800), "开业模板仅支持22–26及1至60秒")
    _require(props.get("audio") == "master.wav", "开业模板音频必须使用同一master.wav母带")
    store_name = "海客AI社区服务店" if content_mode == "community-cend" else "海客AI社区服务站"
    _require(isinstance(props.get("location"), str) and "新塘未来汇" in props["location"] and store_name in props["location"], "模板地址必须明确新塘未来汇及本期门店名称")
    shots = props.get("shots")
    _require(isinstance(shots, list) and bool(shots) and all(isinstance(s, dict) for s in shots), "开业模板需要实拍镜头")
    identifiers = []
    for s in shots:
        _require(isinstance(s.get("id"), str) and s["id"], "实拍镜头缺少编号")
        identifiers.append(s["id"])
        _require(s.get("lane") in {"main", "detail"} and _name(s.get("src")) and s.get("fit", "contain") in {"contain", "cover"}, "实拍轨、文件名或适配方式无效")
        position = s.get("objectPosition", "50% 50%")
        match = re.fullmatch(r"(\d+(?:\.\d+)?)%[ \t]+(\d+(?:\.\d+)?)%", position) if isinstance(position, str) else None
        _require(match is not None and all(0 <= float(value) <= 100 for value in match.groups()), "素材裁切位置必须是两组0至100%的数值")
        _require(_integer(s.get("from"), 0, duration - 1) and _integer(s.get("frames"), 1, 120)
                 and s["from"] + s["frames"] <= duration and _number(s.get("offset")) and s["offset"] >= 0,
                 "实拍镜头时长或入出点无效；单镜最多4秒")
    _require(len(identifiers) == len(set(identifiers)), "实拍镜头编号重复")
    for lane in ("main", "detail"):
        end, last, consecutive = 0, None, 0
        items = sorted((s for s in shots if s["lane"] == lane), key=lambda s: s["from"])
        if lane == "main":
            _require(bool(items), "主实拍轨为空")
        for s in items:
            _require(s["from"] >= end and (lane != "main" or s["from"] == end), "实拍轨存在空隙或重叠")
            consecutive = consecutive + s["frames"] if last and last["src"] == s["src"] and s["from"] == end else s["frames"]
            _require(consecutive <= 120, "连续同源镜头合计超过4秒，不能靠拆分绕过")
            end, last = s["from"] + s["frames"], s
        if lane == "main":
            _require(end == duration, "主实拍轨未覆盖完整配音")
    avatars = props.get("avatarSegments", [])
    _require(isinstance(avatars, list) and all(isinstance(a, dict) for a in avatars), "数字人短段必须是数组")
    for a in avatars:
        _require(_name(a.get("src")) and _integer(a.get("from"), 0, duration - 1) and _integer(a.get("frames"), 1, 300 if content_mode == "community-cend" else 240)
                 and a["from"] + a["frames"] <= duration, "数字人短段越界或超过8秒")
    end = 0
    for a in sorted(avatars, key=lambda a: a["from"]):
        _require(a["from"] >= end, "数字人短段重叠")
        end = a["from"] + a["frames"]
    _require(sum(a["frames"] for a in avatars) <= 300, "数字人总出镜超过10秒")
    captions = props.get("captions")
    _require(isinstance(captions, list) and bool(captions) and all(isinstance(c, dict) for c in captions), "字幕为空或格式错误")
    end_ms = 0
    for c in captions:
        _require(isinstance(c.get("text"), str) and 0 < len(c["text"]) <= 21 and "\n" not in c["text"], "字幕超宽、为空或含未审换行")
        _require(_number(c.get("startMs")) and _number(c.get("endMs")) and c["startMs"] >= max(0, end_ms - 1)
                 and c["endMs"] > c["startMs"] and c["endMs"] <= duration / FPS * 1000 + 1, "字幕时钟越界或重叠")
        end_ms = c["endMs"]
    chapters = props.get("chapters")
    _require(isinstance(chapters, list) and bool(chapters) and all(isinstance(c, dict) for c in chapters), "缺少章节标题")
    previous = -1
    for c in chapters:
        _require(_integer(c.get("from"), 0, duration - 1) and c["from"] > previous and (previous >= 0 or c["from"] == 0), "章节起点必须从0递增且不越界")
        _require(isinstance(c.get("title"), str) and bool(c["title"].strip()) and isinstance(c.get("sub", ""), str), "章节标题或副文案无效")
        previous = c["from"]


def _pcm_duration(path):
    try:
        with wave.open(str(path), "rb") as w:
            _require((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getcomptype()) == (2, 2, 48000, "NONE"), "母带须为48kHz立体声PCM16 WAV")
            return w.getnframes() / w.getframerate()
    except (OSError, wave.Error) as exc:
        raise WorkError("母带无法读取为PCM WAV") from exc


def _validate_receipts(props, paths, media=None):
    duration = props["durationFrames"] / FPS
    for name in _font_names(props):
        _require(name in paths, "本期字体来源槽缺失")
        _validate_font_file(paths[name])
    master_sha = sha(paths["master.wav"])
    _require(abs(_pcm_duration(paths["master.wav"]) - duration) <= 1 / FPS + .001, "母带长度与完整主时钟不一致")
    audio = read_json(paths["audio-receipt.json"])
    approved = audio.get("approved_audio", {})
    authorization = audio.get("authorization", {})
    _require(approved.get("user_approved") is True and authorization.get("user_approved_audio") is True
             and authorization.get("publication") is False, "缺少本期配音确认或发布边界")
    _require(isinstance(approved.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", approved["sha256"]), "已确认干声缺少SHA256")
    _require(audio.get("master_audio_sha256") == master_sha and audio.get("audio_sha256") == master_sha, "母带与音频回执SHA不符")
    asr = read_json(paths["asr.json"])
    _require(asr.get("audio_sha256") in {master_sha, approved["sha256"]} and isinstance(asr.get("text"), str) and asr["text"], "ASR未绑定本期已确认音频")
    _require(asr.get("cues") == props["captions"], "字幕不是本期ASR冻结词时钟")
    _require(isinstance(asr.get("approved_script_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", asr["approved_script_sha256"]), "ASR缺少已确认文案指纹")
    review = read_json(paths["asset-review.json"])
    _require(review.get("version") == "store-opening-asset-review-v1" and review.get("review_method") and review.get("reviewed_by"), "素材缺少本期实际观看说明")
    reviews = review.get("shots")
    _require(isinstance(reviews, list) and all(isinstance(r, dict) for r in reviews), "素材审核清单无效")
    indexed = {r.get("id"): r for r in reviews}
    _require(len(indexed) == len(reviews) and set(indexed) == {s["id"] for s in props["shots"]}, "镜头审核范围不完整或重复")
    videos = {}
    for s in props["shots"]:
        path = paths[s["src"]]
        if s["src"] not in videos:
            info = media[s["src"]] if media is not None else media_probe(path)
            v = info.get("video") or {}
            _require(min(int(v.get("width", 0)), int(v.get("height", 0))) >= 720, "正式素材低于720p，不能提高导出码率冒充清晰原片")
            videos[s["src"]] = info
        _require(s["offset"] + s["frames"] / FPS <= videos[s["src"]]["duration"] + .04, "实拍取段超出原片长度")
        r = indexed[s["id"]]
        start, stop = r.get("source_start_seconds"), r.get("source_end_seconds")
        _require(r.get("src") == s["src"] and r.get("source_sha256") == sha(path), "素材审核来源SHA或文件名不符")
        _require(_number(start) and _number(stop) and abs(start - s["offset"]) <= .05
                 and abs(stop - s["offset"] - s["frames"] / FPS) <= .05, "素材审核并非本次实际取段")
        frames = r.get("observed_frames")
        _require(isinstance(frames, list) and bool(frames) and all(_number(t) and start - .05 <= t <= stop + .05 for t in frames), "镜头缺少区间内实际观看帧")
        _require(r.get("clean") is True and r.get("relevant") is True and r.get("description") and r.get("category"), "镜头清洁度或相关性未通过")
    avatar_reviews = audio.get("avatar_review", [])
    _require(isinstance(avatar_reviews, list) and len(avatar_reviews) == len(props.get("avatarSegments", [])), "数字人审核短段缺失")
    for a in props.get("avatarSegments", []):
        _require(authorization.get("high_quality_avatar") is True and authorization.get("workflow_id") == "2112180419025260546"
                 and isinstance(authorization.get("portrait_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", authorization["portrait_sha256"]), "数字人缺少已授权高质量工作流与人物图指纹")
        matched = [r for r in avatar_reviews if (r.get("src"), r.get("from"), r.get("frames")) == (a["src"], a["from"], a["frames"])]
        _require(len(matched) == 1, "数字人审核区间与实际出镜不符")
        r = matched[0]
        community = props.get("contentMode") == "community-cend"
        _require(r.get("source_sha256") == sha(paths[a["src"]]), "数字人来源SHA不符")
        if not community:
            _require("店长" in str(r.get("source_text", "")) and r.get("reason") == "店长介绍", "数字人未绑定本期店长介绍原句")
        indices = r.get("asr_cue_indices")
        _require(isinstance(indices, list) and bool(indices) and all(_integer(i, 0, len(props["captions"]) - 1) for i in indices), "数字人缺少真实ASR句索引")
        cues = [props["captions"][i] for i in indices]
        if community:
            canonical = lambda text: re.sub(r"[^\w\u4e00-\u9fff]", "", text)
            _require(r.get("reason") == "开场钩子" and a["from"] == 0
                     and indices == list(range(len(indices)))
                     and authorization.get("presenter_script_sha256") == asr["approved_script_sha256"]
                     and canonical(str(r.get("source_text", ""))) == canonical("".join(c["text"] for c in cues)),
                     "C端人物必须绑定已授权文案的连续开场真实字幕")
        else:
            _require(any("店长" in c["text"] for c in cues), "数字人出镜时段没有提及店长")
        start, stop = a["from"] / FPS, (a["from"] + a["frames"]) / FPS
        _require(start >= (0 if community else min(c["startMs"] for c in cues) / 1000 - .5)
                 and stop <= max(c["endMs"] for c in cues) / 1000 + .5, "数字人超出已审核句范围")
        info = media[a["src"]] if media is not None else media_probe(paths[a["src"]])
        _require(bool(info.get("video")) and info["duration"] + .08 >= a["frames"] / FPS, "数字人视频长度不足")
        videos[a["src"]] = info
    return videos


def prepare(queue, props, sources, title):
    validate_props(props)
    required = _required_names(props)
    _require(isinstance(sources, dict) and set(sources) == required and all(_name(n) for n in sources), "开业素材槽不完整、含未使用素材或文件名无效")
    paths = {name: Path(path).resolve() for name, path in sources.items()}
    _require(all(p.is_file() and p.stat().st_size for p in paths.values()), "素材文件缺失或为空")
    media = _validate_receipts(props, paths)
    origins = {name: {"path": str(path), "sha256": sha(path)} for name, path in paths.items()}
    core = {"contract": CONTRACT, "title": title, "props": deepcopy(props), "origins": origins, "media": media,
            "runtime": runtime(), "profile": PROFILE, "export": EXPORT, "cloud_calls": 0, "publication": False}
    core["project_id"] = "studio-" + fingerprint(core)[:16]
    digest = fingerprint(core)
    request = {**core, "request_sha256": digest, "render_id": "store-opening-" + digest[:20]}
    project = queue.projects_root / request["project_id"]
    frozen = project / "artifacts/store-manager-request.json"
    if frozen.exists():
        existing = read_json(frozen)
        validate(queue, existing)
        return existing
    from lib.checkpoint import init_project
    init_project(request["project_id"], title=title, pipeline_type="animated-explainer", pipeline_dir=queue.projects_root)
    assets = project / "assets/store-manager"
    assets.mkdir(parents=True, exist_ok=True)
    for name, path in paths.items():
        shutil.copy2(path, assets / name)
        _require(sha(assets / name) == origins[name]["sha256"], "原素材复制校验失败")
    atomic_private(frozen, request)
    validate(queue, request)
    return request


def validate(queue, request, *, check_runtime=True):
    r = request
    digest = fingerprint({k: v for k, v in r.items() if k not in {"request_sha256", "render_id"}})
    _require(r.get("contract") == CONTRACT and r.get("request_sha256") == digest and r.get("render_id") == "store-opening-" + digest[:20]
             and r.get("profile") == PROFILE and r.get("export") == EXPORT, "开业模板冻结身份无效")
    project = WorkCatalog(queue.projects_root).project(r["project_id"])
    _require(read_json(project / "artifacts/store-manager-request.json") == r, "开业模板冻结请求不一致")
    paths = {name: regular_path(project / "assets/store-manager" / name, project) for name in r["origins"]}
    _require(all(sha(paths[name]) == value["sha256"] for name, value in r["origins"].items()), "冻结素材内容已变化")
    validate_props(r["props"])
    _require(set(paths) == _required_names(r["props"]), "冻结素材槽与本期字体或实拍声明不一致")
    _validate_receipts(r["props"], paths, media=r["media"])
    folder = project / "renders" / r["render_id"]
    receipt = read_json(folder / "result.json")
    if receipt:
        _require(receipt.get("request_sha256") == digest and sha(folder / "avatar-preview.mp4") == receipt.get("output_sha256")
                 and sha(folder / "quality.json") == receipt.get("quality_sha256"), "已完成开业成片身份不一致")
    elif check_runtime:
        _require(runtime() == r["runtime"], "开业模板实现已变化，需新建冻结请求")
    return project


def submit(queue, request):
    validate(queue, request)
    return queue.submit(project_id=request["project_id"], kind=KIND, source="codex", priority="normal", parent_job_id=request["render_id"],
                        frozen_request=request, idempotency_key=CONTRACT + ":" + request["request_sha256"], start_paused=True)


def run(queue, job):
    r = job["frozen_request"]
    try:
        _require(job["kind"] == KIND and job["project_id"] == r["project_id"], "开业模板队列身份不匹配")
        project = validate(queue, r)
        folder = project / "renders" / r["render_id"]
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / "avatar-preview.mp4"
        if not read_json(folder / "result.json"):
            from tools.video.video_compose import VideoCompose
            from backlot.studio_investment_audio_v5 import measure_audio
            from lib.ffmpeg_locator import resolve_ffmpeg_pair
            ffmpeg, _ = resolve_ffmpeg_pair()
            public = folder / "public"
            public.mkdir(exist_ok=True)
            for name in r["origins"]:
                shutil.copy2(project / "assets/store-manager" / name, public / name)
            for path in _template_files():
                target = folder / "template" / path.relative_to(TEMPLATE)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            atomic_private(folder / "props.json", r["props"])
            duration = r["props"]["durationFrames"] / FPS
            edits = {"render_runtime": "remotion", "composition_mode": "atelier", "renderer_family": "bespoke",
                     "timeline": {"duration_seconds": duration}, "bespoke": {"entry": str(folder / "template/index.tsx"),
                     "composition_id": "HaikeStoreOpening", "art_direction": str(TEMPLATE / "README.md"), "props_path": str(folder / "props.json"),
                     "public_dir": str(public), "concurrency": 2, **PROFILE}}
            raw = folder / "mezzanine-crf1.mp4"
            result = VideoCompose().execute({"operation": "render", "output_path": str(raw), "edit_decisions": edits,
                                            "asset_manifest": {"assets": []}, "script_text": read_json(public / "asr.json")["text"]})
            if not result.success:
                raise WorkError(str(result.error), "unavailable")
            command = [ffmpeg, "-nostdin", "-y", "-v", "error", "-i", str(raw), "-i", str(public / "master.wav"),
                       "-map", "0:v:0", "-map", "1:a:0", "-t", str(duration), "-c:v", "libx264", "-preset", "slow",
                       "-b:v", "20500k", "-minrate", "20500k", "-maxrate", "20500k", "-bufsize", "2000k",
                       "-x264-params", "nal-hrd=cbr:force-cfr=1:filler=1", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                       "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(output)]
            subprocess.run(command, check=True, capture_output=True, creationflags=CREATE_NO_WINDOW)
            info = media_probe(output)
            video = info.get("video") or {}
            audio = measure_audio(output)
            _require(video.get("width") == 1440 and video.get("height") == 1800 and video.get("codec_name") == "h264"
                     and video.get("pix_fmt") == "yuv420p" and abs(float(Fraction(video.get("avg_frame_rate", "0/1"))) - FPS) < .001
                     and int(video.get("nb_frames", 0)) == r["props"]["durationFrames"]
                     and abs(info["duration"] - duration) <= .08 and int(video.get("bit_rate", 0)) >= EXPORT["minimum_measured_bitrate"]
                     and audio["true_peak_dbtp"] <= -1.5, "开业成片尺寸、码率、时长或声音峰值未通过")
            subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(output), "-f", "null", "-"],
                           check=True, capture_output=True, creationflags=CREATE_NO_WINDOW)
            atomic_private(folder / "quality.json", {"media": info, "video_stream": video, "audio": audio,
                "render_command": (result.data or {}).get("render_command"), "export_command": command,
                "full_decode": "passed", "source_copy_sha_verified": True, "visual_review": "pending", "listening": "pending"})
            validate(queue, r)
            atomic_private(folder / "result.json", {"request_sha256": r["request_sha256"], "output_sha256": sha(output),
                "quality_sha256": sha(folder / "quality.json"), "cloud_calls": 0, "publication": False})
        community = r["props"].get("contentMode") == "community-cend"
        work = WorkCatalog(queue.projects_root).register(r["project_id"], output, work_key="main", mode="manual", event_id=job["job_id"],
            quality_passed=False, actor="store-opening", title=r["title"], summary=("新塘未来汇C端门店视频" if community else "新塘未来汇开业店长账号") + "；原片与同钟短数字人；实测≥20Mbps；待视听审阅，未发布")
        return {"status": "completed", "stage": "新塘未来汇C端视频完成，待审阅" if community else "新塘未来汇开业成片完成，待审阅", "result": {"output_path": str(output),
                "output_sha256": sha(output), "work_id": work["work_id"], "cloud_calls": 0}}
    except WorkError as exc:
        return {"status": "failed", "stage": str(exc), "error": {"type": "StoreOpening", "message": str(exc)},
                "retryable": exc.code == "unavailable", "safe_resume_point": "store_opening"}

