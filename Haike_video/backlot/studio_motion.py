"""Version-pinned ADu integration. Planning is local; production uses the parent queue.

HTTP inputs contain owned asset IDs and plain values, never executable code or paths.
Upstream plans are immutable and rechecked before building. Original speech is the
master clock. A retry creates a new engineering attempt, keeping previous artifacts.
"""
from __future__ import annotations

import functools
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from uuid import uuid4

from backlot.studio import Studio, atomic_private
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkError, WorkCatalog, sha

COMMIT = "f52490bd1ec37370091982d853990725b340f3f5"
VERSION = "3.14.0-rc.1"
TEMPLATE_ID = "avatar-motion-adu-v1"
QUICK = [
    ("hero", "标题开场"), ("point", "观点要点"), ("number", "数字强调"),
    ("compare", "两侧对比"), ("steps", "步骤流程"), ("quote", "金句结论"),
    ("demo", "产品演示"), ("checklist", "清单盘点"), ("outro", "片尾邀请"),
]


def runtime():
    root = Path(os.environ.get("HAIKE_ADU_ROOT") or Path(__file__).resolve().parents[3] / "adu-motion-video").resolve()
    if not (root / "scripts/pipeline.py").is_file():
        raise WorkError("动效引擎尚未安装，请按部署说明安装 ADu 3.14.0-rc.1")
    p = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    if p.returncode or p.stdout.strip() != COMMIT:
        raise WorkError("动效引擎版本与模板目录不一致，请恢复固定版本；旧工程仍保留")
    changed = subprocess.run(["git", "-C", str(root), "diff", "--name-only", "HEAD", "--", "scripts", "packs", "template", "adaptation-profiles", "references/template-catalog.json"], capture_output=True, text=True, timeout=10)
    if changed.returncode or changed.stdout.strip():
        raise WorkError("动效引擎源码已变化，请恢复固定版本后重新检查，不沿用旧计划")
    return root


def command(*args, timeout=180, pending=False, log=None):
    root = runtime()
    wrapper = root / "adu-local.sh"
    if os.name != "nt" and wrapper.is_file():
        entry = ["bash", str(wrapper)]
    else:
        python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        entry = [str(python if python.is_file() else sys.executable), "-X", "utf8", str(root / "scripts/pipeline.py")]
    env = os.environ.copy()
    # No credentials are needed by the local renderer.
    for name in list(env):
        if any(x in name.upper() for x in ("API_KEY", "API_SECRET", "ACCESS_TOKEN")): env.pop(name)
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    try:
        result = subprocess.run(entry + [str(a) for a in args], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise WorkError("本地动效步骤超时，已保留检查报告和工程；请恢复原任务", "unavailable") from None
    if log:
        Path(log).write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode not in ({0, 2} if pending else {0}):
        tail = (result.stderr or result.stdout).strip()[-2400:]
        raise WorkError("动效步骤未通过，请检查报告并调整素材或分镜：" + tail)
    return result


@functools.lru_cache(maxsize=2)
def capabilities(layout):
    if layout not in {"portrait", "landscape"}: raise WorkError("请选择横屏或竖屏")
    return json.loads(command("auto-capabilities", "--layout", layout).stdout)


def library(layout="portrait"):
    root = runtime()
    catalog = json.loads((root / "references/template-catalog.json").read_text(encoding="utf-8"))
    caps = capabilities(layout)
    styles = []
    for family in catalog["templates"]:
        for item in family["styles"]:
            group = [g for g in caps["groups"] if g["style"] == item["id"] and layout in g["layouts"]]
            preview = item.get("portraitPreview", item.get("preview")) if layout == "portrait" else item.get("preview")
            demo = item.get("portraitDemo", item.get("demo")) if layout == "portrait" else item.get("demo")
            styles.append({"id": item["id"], "name": item["title"], "family": family["title"], "family_id": family["id"],
                           "supported": bool(group), "selection": group[0]["selection"] if group else None,
                           "status": group[0]["status"] if group else "unsupported", "scope": item.get("scope", "完整镜头组"),
                           "preview": "/api/studio/motion/media/" + preview if preview else None,
                           "demo": "/api/studio/motion/media/" + demo if demo else None,
                           "preview_basis": item.get("previewBasis", "上游风格示例，不能作为本期人物或证据素材"),
                           "requirements": item.get("requires", []), "groups": group})
    from backlot.studio_motion_quick import groups as quick_groups
    styles.append({"id":"quick", "name":"轻量动画组合", "family":"基础动画", "family_id":"07", "supported":layout=="landscape",
                   "selection":"TPL", "status":"quick-start", "scope":"9个轻量组件；不代表完整工程的全部动作", "preview":"/api/studio/motion/media/assets/tutorials/templates.png",
                   "demo":None, "preview_basis":"上游9个基础动画组件说明图，不是完整工程样片", "requirements":["已有口播与原文","实际动作落点"], "groups":quick_groups(QUICK) if layout=="landscape" else []})
    return {"version": VERSION, "commit": COMMIT, "styles": styles, "layout": layout,
            "available_styles": caps["availableStyles"], "available_groups": caps["availableGroups"],
            "quick": [{"id": a, "name": b, "layout": "landscape", "status": "quick-start"} for a, b in QUICK],
            "tools": ["自动比较可用组", "内容与动作时钟检查", "当前分镜素材替换", "横竖屏排版", "准确字幕与双语字幕", "人脸构图", "背景音乐与动作音效", "工程与视频导出", "版本保留"],
            "methods": [{"id": "handdrawn-animation", "name": "手绘续接", "status": "method-only"}, {"id": "template-intake", "name": "新模板接入", "status": "method-only"}, {"id": "quality-upgrade", "name": "保护式口播修剪", "status": "explicit-review-required"}],
            "historical": [{k: v for k,v in p.items() if k != "path"} for p in json.loads(command("packs").stdout)]}


def public_media(name):
    if not re.fullmatch(r"assets/demos/[0-9A-Za-z_-]+\.(gif|mp4)", name) and name != "assets/tutorials/templates.png": raise WorkError("示例不存在", "missing")
    root = runtime(); path = root / name
    if not path.is_file() or path.is_symlink(): raise WorkError("示例不存在", "missing")
    return path


def guide(name):
    if name not in {"handdrawn-animation", "template-intake", "quality-upgrade", "compatibility", "automatic-selection", "local-rematch", "templates"}:
        raise WorkError("制作说明不存在", "missing")
    return {"name": name, "text": (runtime() / "references" / (name + ".md")).read_text(encoding="utf-8")}


def save_bundle(studio, draft_id, filename, content):
    """Frame sequences/attributed sprite walls: immutable ZIP with bounded extraction."""
    studio.draft(draft_id)
    if Path(filename).suffix.lower() != ".zip" or not 0 < len(content) <= 80 * 1024 * 1024: raise WorkError("序列素材请上传80MB以内的ZIP")
    folder = studio.projects_root / draft_id / "assets/studio" / uuid4().hex
    folder.mkdir(parents=True)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = [i for i in archive.infolist() if not i.is_dir()]
            if len(entries) > 5000 or sum(i.file_size for i in entries) > 250 * 1024 * 1024: raise WorkError("ZIP展开后最多250MB、5,000个文件")
            for info in entries:
                name = info.filename.replace("\\", "/"); target = folder / name
                if name.startswith("/") or ".." in Path(name).parts or ":" in name or ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    raise WorkError("ZIP包含不安全路径或链接")
                if target.suffix.lower() not in {".jpg", ".jpeg", ".png", ".json"}: raise WorkError("序列ZIP只包含JPG/PNG帧和来源清单JSON")
                if not target.resolve().is_relative_to(folder.resolve()): raise WorkError("ZIP路径越界")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, target.open("xb") as out: shutil.copyfileobj(src, out)
        images = list(folder.rglob("*.jpg")) + list(folder.rglob("*.png")) + list(folder.rglob("*.jpeg"))
        if not images: raise WorkError("ZIP没有图片帧")
        from PIL import Image
        for path in images:
            with Image.open(path) as image: image.verify()
        # Frames must share one directory; nested source paths do not reach the API.
        directories = {p.parent for p in images}
        if len(directories) != 1: raise WorkError("请把全部序列帧放在ZIP的同一文件夹")
        path = next(iter(directories))
        marker = folder / "bundle.json"; atomic_private(marker, {"directory": str(path), "files": len(images)})
        identity = folder.name
        with studio.db() as db: db.execute("INSERT INTO studio_assets VALUES(?,?,?,?,?)", (identity, draft_id, Path(filename).name[:160], "sequence", str(marker)))
        return {"id": identity, "name": Path(filename).name[:160], "kind": "sequence", "files": len(images)}
    except Exception:
        shutil.rmtree(folder)
        raise


def number(value, label, minimum=0, maximum=600):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise WorkError(label + "需要在有效范围内")
    return value


def owned_value(studio, draft, value, kind):
    if not isinstance(value, dict) or set(value) - {"asset", "offset", "entityId"}: raise WorkError("素材绑定格式无效，不能提交文件路径")
    path = studio.asset((value.get("asset") or {}).get("id"), draft["id"])
    if kind in {"sequence", "wall-sprites"}:
        if path.name != "bundle.json": raise WorkError("该镜头需要上传序列帧ZIP")
        path = Path(json.loads(path.read_text(encoding="utf-8"))["directory"])
        if not path.resolve().is_relative_to((studio.projects_root / draft["id"] / "assets/studio").resolve()): raise WorkError("序列素材路径越界")
    elif kind == "image" and path.suffix.lower() not in {".jpg", ".png", ".jpeg"}: raise WorkError("请为图片槽上传图片")
    elif kind == "video" and path.suffix.lower() not in {".mp4", ".mov"}: raise WorkError("请为视频槽上传视频")
    out = {"path": str(path)}
    if value.get("entityId"): out["entityId"] = str(value["entityId"])[:120]
    if kind == "video": out["offset"] = number(value.get("offset", 0), "素材开始时间")
    return out


def source_video(studio, draft):
    source = draft["input"].get("source") or {}
    if source.get("work_id"):
        catalog = WorkCatalog(studio.projects_root)
        work = catalog.get(source["work_id"])
        path = catalog.media_path_from_work(work, source.get("version_id"))
        # Prefer the real speech mother clip from a completed Haike avatar job.
        if source.get("raw") is True:
            raw = path.parent / "avatar-source.mp4"
            if not raw.is_file() or raw.is_symlink(): raise WorkError("此作品没有可复用的口播母版，请上传口播视频")
            if not raw.resolve().is_relative_to(studio.projects_root.resolve()): raise WorkError("口播来源越界")
            audio = path.parent / "narration.wav"
            if not audio.is_file():
                state = path.parent / "gateway-state.json"
                if state.is_file(): audio = Path(json.loads(state.read_text(encoding="utf-8"))["prepared"]["audio_path"])
            return raw, audio if audio.is_file() and audio.resolve().is_relative_to(studio.projects_root.resolve()) else None
        return path, None
    return studio.asset(source.get("id"), draft["id"]), None


def narration_clock(info):
    """Match upstream import_talk.input_timing, including non-zero stream starts."""
    video=info.get('video')
    if not video: raise WorkError('口播素材没有视频画面')
    origin=float(info.get('format',{}).get('start_time') or 0)
    offset=max(0.,float(video.get('start_time') or origin)-origin)
    duration=float(video.get('duration') or (info['duration']-offset))
    end=offset+duration
    if not math.isfinite(end) or not 0 < end <= 600: raise WorkError('口播真实视频时长需要在10分钟内')
    frames=math.floor(end*60+.5)
    return {'duration':frames/60,'frames':frames,'fps':60,'container_duration':info['duration'], 'clock':'video-end-on-output-grid'}


def source_metadata(studio,draft):
    video,audio=source_video(studio,draft); info=media_probe(video)
    if not info.get('audio') and not audio: raise WorkError('口播视频没有音轨，请上传含口播音轨的视频')
    return {**narration_clock(info),'width':info['video']['width'],'height':info['video']['height']}


def motion_sources(studio):
    c = WorkCatalog(studio.projects_root)
    return [{"work_id": w["work_id"], "name": w["title"], "versions": [{"id": v["version_id"], "raw": any((Path(p).parent / "avatar-source.mp4").is_file() for p in v["paths"])} for v in w["versions"]]} for w in c.list(include_candidates=True)]


def compatible_candidates(primary, groups, slots):
    """Compare explicit contracts, without guessing a new meaning or action time."""
    candidates={primary['id']:{'slots':slots}}
    bindings={(f.get('inputPath') or f['id'],f['type']):slots[f['id']] for f in primary['fields'] if f['id'] in slots}
    for g in groups.values():
        if g['id']==primary['id'] or g['style']==primary['style']:continue
        if g['intents'][0]!=primary['intents'][0] or g['phases']!=primary['phases'] or g['counts']!=primary['counts'] or set(g['cueRoles'].values())!=set(primary['cueRoles'].values()):continue
        values={};available=True
        for f in g['fields']:
            if f['type']=='talk':continue
            item=bindings.get((f.get('inputPath') or f['id'],f['type']))
            if item is not None:values[f['id']]=item
            elif f.get('required',True):available=False;break
        if available:candidates[g['id']]={'slots':values}
    return candidates


def brief(studio, draft, directory):
    value = draft["input"]
    layout = value.get("motionLayout", "portrait")
    caps = capabilities(layout); groups = {g["id"]: g for g in caps["groups"] if layout in g["layouts"]}
    if layout=="landscape":
        from backlot.studio_motion_quick import groups as quick_groups
        groups.update({g["id"]:g for g in quick_groups(QUICK)})
    video, audio = source_video(studio, draft); info = media_probe(video)
    if not info["video"] or not (info["audio"] or audio): raise WorkError("请上传同时有画面和口播音轨的视频")
    clock=narration_clock(info);frames=clock['frames']
    music = value.get("music") or {}
    if music.get("mode") == "none": music = {"mode": "none"}
    elif music.get("mode") == "track":
        music = {"mode": "track", "path": str(studio.asset((music.get("asset") or {}).get("id"), draft["id"])), "offset": number(music.get("offset", 0), "配乐起点")}
    else: raise WorkError("请选择本期配乐，或明确选择不使用背景音乐")
    segments = value.get("segments", [])
    if not isinstance(segments, list) or not 1 <= len(segments) <= 40: raise WorkError("请配置1至40个完整分镜")
    if "".join(s.get("text", "") for s in segments) != draft["text"] or not draft["text"].strip():
        raise WorkError("分镜原文须按顺序完整覆盖口播文案，不能丢句、重复或重写原文")
    timeline = []; units = []; cursor = 0; text_cursor = 0; hashes = []
    identity = hashlib.sha256(draft["text"].encode()).hexdigest()
    for i, segment in enumerate(segments):
        group = groups.get(segment.get("group"))
        if not group: raise WorkError(f"分镜{i+1}的模板不支持当前画幅")
        end = round(number(segment.get("end"), f"分镜{i+1}结束时间") * 60)
        if not cursor < end <= frames: raise WorkError(f"分镜{i+1}的结束时间必须递增且不超过实际口播时长")
        ref = f"{identity[:16]}:{text_cursor}:{text_cursor+len(segment['text'])}"
        units.append({"id": ref, "start": text_cursor, "end": text_cursor + len(segment["text"]), "text": segment["text"]})
        fields = {f["id"]: f for f in group["fields"]}; values = segment.get("values", {})
        if not isinstance(values, dict) or set(values) - fields.keys(): raise WorkError("分镜包含不支持的配置字段")
        slots = {}
        for k, f in fields.items():
            item = values.get(k)
            if f["type"] == "talk": continue  # Upstream binds the imported, exact-clock talk.
            if item is None or item == "": continue  # Native planner explains missing inputs.
            if f["type"] in {"text", "dynamicText"}:
                if not isinstance(item, str): raise WorkError("分镜文字格式无效")
                slots[k] = item
            elif f["type"] == "number": slots[k] = number(item, "镜头数值", -10000000, 10000000)
            else:
                slots[k] = owned_value(studio, draft, item, f["type"])
                path = Path(slots[k]["path"])
                if path.is_file(): hashes.append({"path": str(path), "sha256": sha(path)})
        anchors = {}
        if set(segment.get("anchors", {})) - set(group["cueRoles"].values()): raise WorkError("分镜动作落点不支持")
        for role, at in segment.get("anchors", {}).items():
            if at is not None and at != "": anchors[role] = {"at": number(at, "动作落点", 0, (end - cursor) / 60)}
        candidates=compatible_candidates(group,groups,slots) if value.get('selectionMode')=='compatible' and not group['id'].startswith('quick:') else {group['id']:{'slots':slots}}
        text_fields={f['id'] for candidate in candidates for f in groups[candidate]['fields'] if f['type'] in {'text','dynamicText','number'} and f['id'] in candidates[candidate]['slots']}
        timeline.append({"id": "segment-" + str(i+1), "text": segment["text"], "durationFrames": end-cursor,
                         "intent": group["intents"][0], "phases": group["phases"], "counts": {k: v["min"] for k,v in group["counts"].items()},
                         "anchors": anchors, "candidates": candidates, "ownershipRefs": [ref],
                         "supportingRefs": {k:[ref] for k in text_fields}})
        cursor = end; text_cursor += len(segment["text"])
    if cursor != frames: raise WorkError("最后一个分镜须覆盖口播结尾，时间以实际视频为准")
    evidence = {"schema": "adu-content-evidence/1", "text": draft["text"], "textSha256": identity, "sourceKind": "user-confirmed-transcript", "units": units,
                "assets": [{"id": "narration", "path": str(video), "sha256": sha(video)}] + hashes}
    cues = value.get("captions", [])
    if not isinstance(cues, list) or len(cues) > 3000: raise WorkError("字幕格式无效")
    normalized = []; previous_end = 0
    for cue in cues:
        if not isinstance(cue, dict) or set(cue) - {"start", "end", "text", "en"}: raise WorkError("字幕只支持时间、原文与可选英文")
        a = number(cue.get("start"), "字幕起点"); b = number(cue.get("end"), "字幕终点")
        if not a < b <= frames/60 + .02 or not isinstance(cue.get("text"), str) or not cue['text'].strip(): raise WorkError("字幕原文为空或时间超出实际口播")
        if a < previous_end: raise WorkError("字幕时间不能重叠或倒序，请按实际口播调整")
        if not isinstance(cue.get('en',''),str): raise WorkError('英文字幕需要文字格式')
        normalized.append({"t0": a, "t1": min(b, frames/60), "zh": cue["text"], "en": cue.get('en','')})
        previous_end = b
    subtitle_file = directory / "subs.js"; subtitle_file.write_text("const SUBS=" + json.dumps(normalized, ensure_ascii=False) + ";\n", encoding="utf-8")
    result = {"schema": "adu-auto-brief/1", "brand": "海客科技", "fps": 60, "layout": layout,
              "narrationDuration": frames/60, "music": music, "fontPolicy": "preferred", "segments": timeline, "contentEvidence": evidence,
              "stylePolicy": "coherent-first", "allowedStyles": sorted({id.split(':')[0] for s in timeline for id in s['candidates']}), "repairPolicy": {"mode": "off"},
              "subtitlePreset": "standard", "subtitlePosition": {"bottomRatio": number(value.get("subtitleBottom", .18), "字幕底边", .05, .4), "leftRatio": .15, "rightRatio": .15}}
    if value.get("texture"):
        result["grainTexture"] = str(studio.asset(value["texture"]["id"], draft["id"]))
    face = value.get("face") or {"mode": "auto"}
    if face.get("mode") == "fixed": result["faceTracking"] = {"mode": "fixed", **{k: number(face.get(k), "人物构图", .01, 1) for k in ("cx", "cy", "h")}}
    if any(s['group'].startswith('quick:') for s in segments):
        if not all(s['group'].startswith('quick:') for s in segments): raise WorkError('轻量动画与完整工程分别制作，不能混用两种时钟合同')
        from backlot.studio_motion_quick import options
        cursor=0; compiled=[]
        for source,segment in zip(segments,timeline):
            end=cursor+segment['durationFrames']/60
            compiled.append(options({'group':source['group'],'slots':segment['candidates'][source['group']]['slots'],'anchors':segment['anchors']},cursor,end));cursor=end
        result['quickScenes']=compiled
    atomic_private(directory / "brief.json", result)
    return video, audio, result


def plan(studio, draft):
    runtime()
    if draft["template_id"] != TEMPLATE_ID: raise WorkError("请选择动效口播")
    folder = (studio.projects_root / draft["id"] / "assets/motion-plans" / uuid4().hex).resolve()
    folder.mkdir(parents=True)
    video, audio, value = brief(studio, draft, folder)
    if value.get('quickScenes'):
        folder.joinpath('planning').mkdir()
        saved={'schema':'haike-adu-quick-plan/1','brief':value,'quickScenes':value['quickScenes'],
               'report':{'ready':True,'status':'ready','durationFrames':sum(s['durationFrames'] for s in value['segments']),'selectedStyle':'quick','missing':[],'blocking':[]}}
        atomic_private(folder/'planning/auto_plan.json',saved)
    else:
        command("auto-plan", folder / "brief.json", folder / "planning", pending=True, log=folder / "plan.log")
        saved = json.loads((folder / "planning/auto_plan.json").read_text(encoding="utf-8"))
    snapshot = {"id": folder.name, "revision": draft["revision"], "draft": draft, "video": str(video), "audio": str(audio) if audio else None,
                "video_sha256": sha(video), "audio_sha256": sha(audio) if audio else None, "commit": COMMIT, "plan_sha256": sha(folder / "planning/auto_plan.json"), "human_review": "pending"}
    atomic_private(folder / "snapshot.json", snapshot)
    return {"id": folder.name, "revision": draft["revision"], "report": saved["report"], "cost_micros": 0, "commit": COMMIT}


def freeze(studio, draft, plan_id, confirmed):
    if confirmed is not True: raise WorkError("请先确认文案、素材和分镜含义")
    if not isinstance(plan_id, str) or not re.fullmatch(r"[a-f0-9]{32}", plan_id): raise WorkError("请先运行生成前检查")
    folder = studio.projects_root / draft["id"] / "assets/motion-plans" / plan_id
    if not (folder / "snapshot.json").is_file(): raise WorkError("检查计划不存在，请重新检查")
    snapshot = json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
    if snapshot["draft"] != draft or sha(folder / "planning/auto_plan.json") != snapshot["plan_sha256"]: raise WorkError("制作内容或计划已改变，请重新检查")
    saved = json.loads((folder / "planning/auto_plan.json").read_text(encoding="utf-8"))
    if not saved["report"]["ready"]: raise WorkError("分镜仍缺少绑定或受阻，请补齐后重新检查")
    if sha(Path(snapshot["video"])) != snapshot["video_sha256"] or (snapshot["audio"] and sha(Path(snapshot["audio"])) != snapshot["audio_sha256"]): raise WorkError("口播来源已改变，请重新检查")
    return {"draft": draft, "plan_id": plan_id, "plan_folder": str(folder), "snapshot": snapshot, "render_id": "studio-" + str(draft["revision"])}


def run_motion(project_dir, request):
    project_dir = Path(project_dir); studio = Studio(project_dir.parent)
    output = project_dir / "renders" / request["render_id"]
    output.mkdir(parents=True, exist_ok=True)
    try:
        # Freeze is authoritative; a newer editor draft does not change a queued render.
        checked = freeze(studio, request["draft"], request["plan_id"], True)
        if checked != request: raise WorkError("队列内容与冻结计划不一致，请重新提交")
        if (output / "motion-preview.mp4").is_file() and (output / "qa.json").is_file():
            return {"status": "completed", "stage": "动效口播已合成，等待审核", "result": {"output_path": str(output / "motion-preview.mp4"), "qa_status": "pending"}}
        attempt = output / ("attempt-" + uuid4().hex[:10]); attempt.mkdir()
        folder = Path(request["plan_folder"]); video = Path(checked["snapshot"]["video"])
        if checked["snapshot"]["audio"]:
            from lib.ffmpeg_locator import resolve_ffmpeg_pair
            ffmpeg, _ = resolve_ffmpeg_pair(); aligned = attempt / "narration-source.mp4"
            args = [ffmpeg, "-v", "error", "-i", str(video), "-i", checked["snapshot"]["audio"], "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", str(aligned)]
            subprocess.run(args, check=True, capture_output=True, timeout=90); video = aligned
        engineering = attempt / "engineering"
        saved=json.loads((folder / "planning/auto_plan.json").read_text(encoding="utf-8"))
        if saved['schema']=='haike-adu-quick-plan/1':
            from backlot.studio_motion_quick import build
            # Recompute adapter output, so flags in an edited plan are never authority.
            verification=attempt/'recheck';verification.mkdir()
            _,_,fresh=brief(studio,request['draft'],verification)
            if fresh!=saved['brief']: raise WorkError('轻量编排已变化，请重新检查')
            build(saved,video,engineering,folder/'subs.js',command,runtime)
        else:
            command("auto-build", folder / "planning/auto_plan.json", video, engineering, "--subs-js", folder / "subs.js", timeout=900, log=attempt / "build.log")
        command("audio", engineering, timeout=600, log=attempt / "audio.log")
        command("mix", engineering, timeout=300, log=attempt / "mix.log")
        candidate = attempt / "motion-preview.mp4"
        command("render", engineering, candidate, "2", timeout=3600, log=attempt / "render.log")
        command("check", candidate, timeout=300, log=attempt / "check.log")
        info = media_probe(candidate); desired = json.loads((folder / "planning/auto_plan.json").read_text(encoding="utf-8"))["report"]["durationFrames"] / 60
        if not info["video"] or not info["audio"] or abs(info["duration"] - desired) > .05: raise WorkError("导出视频与口播时钟不一致，保留工程待处理")
        command("preview", engineering, candidate, attempt / "delivery-preview", timeout=90, log=attempt / "preview.log")
        # A complete editable project: no private Key, queue database or supplier configuration.
        archive = output / "editable-project.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in engineering.rglob("*"):
                if p.is_file() and not p.is_symlink(): z.write(p, "engineering/" + p.relative_to(engineering).as_posix())
            for name in ("LICENSE", "THIRD_PARTY.md"):
                z.write(runtime() / name, name)
            z.write(folder / "planning/auto_plan.json", "planning/auto_plan.json")
            z.write(folder / "brief.json", "planning/brief.json")
        shutil.copy2(candidate, output / "motion-preview.mp4")
        atomic_private(output / "qa.json", {"engine": VERSION, "commit": COMMIT, "source": checked["snapshot"], "source_clock": "unmodified-narration", "output": info,
                       "frames": round(desired*60), "caption_timing": "provided exact cues", "checks": ["upstream-plan-build-revalidation", "full-decode", "duration", "audio", "version-bound-preview"],
                       "human_review": "pending", "engineering": str(engineering), "archive": str(archive), "no_paid_calls": True})
        return {"status": "completed", "stage": "动效口播已合成，等待观看与审核", "result": {"output_path": str(output / "motion-preview.mp4"), "qa_status": "pending", "engineering_archive": str(archive)}}
    except WorkError as exc:
        return {"status": "failed", "stage": str(exc), "error": {"message": str(exc), "type": "StudioMotion"}, "retryable": exc.code == "unavailable", "safe_resume_point": "studio_motion"}
    except Exception:
        return {"status": "failed", "stage": "本地动效制作中断，原口播与工程已保留，请查看制作报告", "error": {"message": "可恢复原任务；不会产生新付费调用", "type": "StudioMotion"}, "retryable": True, "safe_resume_point": "studio_motion"}
