"""Private local footnote and fixed caption-style revisions for Investment A."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from backlot.studio import atomic_private
from backlot.studio_investment import TEMPLATE_ID, settings
from backlot.work_catalog import WorkCatalog, WorkError, read_json, regular_path, sha

KIND = "studio_investment_recompose"
FOOTNOTE_CONTRACT = "investment-footnote-local-v1"
CAPTION_CONTRACT = "investment-caption-style-local-v2"
CAPTION_STYLE = "clear-v2"


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _runtime():
    root = Path(__file__).resolve().parents[1]
    return {str(path): sha(path) for path in (root / "templates/avatar-investment-a-v6/index.tsx",
            root / "templates/avatar-investment-a-v6/layout.json", root / "backlot/studio_investment.py",
            root / "backlot/studio_composition.py", Path(__file__).resolve())}


def _task_id(queue, source_id):
    path = queue.projects_root.parent / ".backlot/task-center.sqlite3"
    if not path.is_file(): return None
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT id FROM task_center_tasks WHERE json_extract(data,'$.links.queue_job_id')=?", (source_id,)).fetchall()
    if len(rows) > 1: raise WorkError("原生产队列关联多个任务，请先核对原任务")
    return rows[0][0] if rows else None


def _patch(draft, patch):
    if not isinstance(patch, dict) or set(patch) != {"emphasis_index", "footnote"}:
        raise WorkError("本地修正版仅支持指定重点卡的脚注")
    index, note = patch["emphasis_index"], patch["footnote"]
    if type(index) is not int or not isinstance(note, str) or len(note) > 64:
        raise WorkError("脚注索引或文字无效，最多64字")
    result = deepcopy(draft)
    entries = result.get("input", {}).get("investment", {}).get("emphasis", [])
    if not 0 <= index < len(entries) or not isinstance(entries[index], dict):
        raise WorkError("请指定原模板中已有的重点卡")
    entries[index]["footnote"] = note
    settings(result)
    return result


def _display_draft(draft, patch, contract):
    if contract == FOOTNOTE_CONTRACT:
        return _patch(draft, patch)
    if contract != CAPTION_CONTRACT or patch != {"caption_style": CAPTION_STYLE}:
        raise WorkError("字幕刷新仅支持固定clear-v2样式，不能修改其他展示字段")
    # The source draft, including every title, footnote, cue and layout prop,
    # remains byte-for-byte equivalent. Only the frozen renderer changes.
    return deepcopy(draft)


def _prefix(contract):
    if contract == FOOTNOTE_CONTRACT: return "local-footnote-"
    if contract == CAPTION_CONTRACT: return "local-caption-clear-"
    raise WorkError("本地修正版合同无效")


def _require_caption_style():
    path = Path(__file__).resolve().parents[1] / "templates/avatar-investment-a-v6/layout.json"
    if read_json(path).get("caption", {}).get("styleId") != CAPTION_STYLE:
        raise WorkError("当前模板尚未冻结clear-v2字幕样式，请完成模板更新后重新准备")


def _cached_output(project, request):
    folder = project / "renders" / request["render_id"]
    receipt = read_json(folder / "local-recompose-result.json")
    if not receipt: return False
    output = regular_path(folder / "avatar-preview.mp4", project)
    if receipt.get("request_sha256") != request["request_sha256"] or sha(output) != receipt.get("output_sha256"):
        raise WorkError("已有本地修正版发生变化，保留产物待核对")
    return True


def prepare(queue, source_queue_id, patch=None, *, caption_style=None):
    """Freeze local sources only; never quote, construct an SDK, or enqueue."""
    source = queue.get(source_queue_id, include_private=True)
    original = source.get("frozen_request") or {}
    draft = original.get("draft") or {}
    if source["kind"] != "studio_avatar" or source["status"] != "completed" or draft.get("template_id") != TEMPLATE_ID or "development_sample" in original:
        raise WorkError("请选择已完成的招商A正式口播原队列")
    if draft.get("input", {}).get("ai", {}).get("enabled") or draft.get("input", {}).get("network_materials_enabled") or draft.get("input", {}).get("motion"):
        raise WorkError("本地展示修正版仅支持无外部素材的招商A口播")
    contract = FOOTNOTE_CONTRACT
    if caption_style is not None:
        if caption_style != CAPTION_STYLE or patch is not None:
            raise WorkError("字幕刷新仅支持clear-v2，不能同时修改脚注或其他字段")
        _require_caption_style()
        contract, patch = CAPTION_CONTRACT, {"caption_style": CAPTION_STYLE}
    _display_draft(draft, patch, contract)
    project = WorkCatalog(queue.projects_root).project(source["project_id"])
    render_id = original.get("render_id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", render_id): raise WorkError("原渲染编号无效")
    folder = project / "renders" / render_id
    state_path = regular_path(folder / "gateway-state.json", project)
    state = read_json(state_path)
    prepared = state.get("prepared") or {}
    props_path, qa_path = (regular_path(folder / name, project) for name in ("props.json", "qa.json"))
    props, qa = read_json(props_path), read_json(qa_path)
    if qa.get("caption_timing") in {None, "off", "illustrative_manual"} or qa.get("template_id") != TEMPLATE_ID:
        raise WorkError("原作品缺少真实识别字幕验收记录")
    from backlot.studio_avatar import captions
    stages = state.get("stages", {})
    asr_stage = (state.get("asr_resolution") or {}).get("stage") or "asr"
    asr = (stages.get(asr_stage) or {}).get("job") or {}
    if asr.get("status") != "succeeded": raise WorkError("本地修正版需要原识别任务已成功，不能重新识别")
    cues = captions(asr["result"], prepared["duration"], max_chars=14)
    if cues != props.get("captions") or props.get("duration") != prepared.get("duration"):
        raise WorkError("原字幕或音频时钟不一致，未创建修正版")
    audio = regular_path(prepared["audio_path"], project)
    avatar = regular_path(folder / "avatar-source.mp4", project)
    original_video = regular_path(folder / "avatar-preview.mp4", project)
    sources = {str(path.relative_to(project)): sha(path) for path in (state_path, props_path, qa_path, audio, avatar, original_video)}
    work_id = (source.get("result") or {}).get("work_id")
    if not work_id: raise WorkError("原作品尚未完成登记，请先恢复原作品登记")
    work = WorkCatalog(queue.projects_root).get(work_id)
    if work["project_id"] != source["project_id"] or not any(v["sha256"] == sha(original_video) for v in work["versions"]):
        raise WorkError("原队列与作品版本未绑定")
    core = {"contract": contract, "source_queue_id": source_queue_id,
            "source_task_id": _task_id(queue, source_queue_id), "source_revision": draft["revision"],
            "project_id": source["project_id"], "source_work_id": work_id,
            "source_version_sha256": sha(original_video), "source_request_sha256": fingerprint(original),
            "draft": draft, "prepared": {"duration": prepared["duration"], "audio_path": str(audio)},
            "avatar_path": str(avatar), "cues": cues, "patch": patch, "sources": sources, "runtime": _runtime()}
    identity = fingerprint(core)
    return {**core, "request_sha256": identity, "render_id": _prefix(contract) + identity[:20]}


def validate(queue, request):
    base = {k: v for k, v in request.items() if k not in {"request_sha256", "render_id"}}
    identity = fingerprint(base)
    if request.get("request_sha256") != identity or request.get("render_id") != _prefix(request.get("contract")) + identity[:20]:
        raise WorkError("本地修正版冻结规格已变化")
    source = queue.get(request["source_queue_id"], include_private=True)
    original = source.get("frozen_request") or {}
    original_draft = original.get("draft") or {}
    if (source["status"] != "completed" or source["kind"] != "studio_avatar"
            or original_draft.get("template_id") != TEMPLATE_ID or "development_sample" in original
            or fingerprint(original) != request["source_request_sha256"]):
        raise WorkError("原生产任务已变化，保留原文件待核对")
    project = WorkCatalog(queue.projects_root).project(request["project_id"])
    if source["project_id"] != request["project_id"] or request["draft"] != source["frozen_request"]["draft"]:
        raise WorkError("本地修正版不能改换原稿、人物或声音")
    if request["source_work_id"] != source.get("result", {}).get("work_id") or request["source_revision"] != request["draft"]["revision"]:
        raise WorkError("本地修正版不能更换原作品或版本绑定")
    for relative, digest in request["sources"].items():
        if sha(regular_path(project / relative, project)) != digest: raise WorkError("本地修正版源文件SHA已变化，未重新调用供应商")
    folder = project / "renders" / source["frozen_request"]["render_id"]
    original_state, original_props = read_json(folder / "gateway-state.json"), read_json(folder / "props.json")
    original_prepared = original_state["prepared"]
    if (request["cues"] != original_props.get("captions") or request["prepared"] != {
            "duration": original_prepared["duration"], "audio_path": str(regular_path(original_prepared["audio_path"], project))}
            or request["avatar_path"] != str(regular_path(folder / "avatar-source.mp4", project))):
        raise WorkError("本地修正版不能改换音频、数字人或字幕时钟")
    required_paths = {str(path.relative_to(project)) for path in (folder / "gateway-state.json", folder / "props.json", folder / "qa.json",
        Path(original_prepared["audio_path"]), folder / "avatar-source.mp4", folder / "avatar-preview.mp4")}
    if set(request["sources"]) != required_paths or request["source_version_sha256"] != request["sources"][str((folder / "avatar-preview.mp4").relative_to(project))]:
        raise WorkError("本地修正版不能删改原素材SHA绑定")
    _display_draft(request["draft"], request["patch"], request["contract"])
    # Already-rendered immutable output can still be inspected or registered
    # after renderer maintenance. A pending request may never silently switch
    # its frozen renderer, including a legacy footnote-v1 request.
    if not _cached_output(project, request):
        if request["runtime"] != _runtime(): raise WorkError("模板源码已变化，请重新准备本地修正版")
        if request["contract"] == CAPTION_CONTRACT: _require_caption_style()
    return project


def submit(queue, request):
    validate(queue, request)
    return queue.submit(project_id=request["project_id"], kind=KIND, source="codex", priority="normal",
                        parent_job_id=request["render_id"], frozen_request=request,
                        idempotency_key=KIND + ":" + request["request_sha256"], start_paused=True)


def run(queue, job):
    """Registered queue runner. All inputs are local and SDK access is absent."""
    request = job["frozen_request"]
    try:
        project = validate(queue, request)
        folder = project / "renders" / request["render_id"]
        folder.mkdir(parents=True, exist_ok=True)
        receipt = folder / "local-recompose-result.json"
        previous = read_json(receipt)
        output = folder / "avatar-preview.mp4"
        if previous:
            if previous.get("request_sha256") != request["request_sha256"] or not output.is_file() or sha(output) != previous.get("output_sha256"):
                raise WorkError("已有本地修正版发生变化，保留产物待核对")
        else:
            from backlot.studio_composition import compose_avatar
            output = compose_avatar(folder, _display_draft(request["draft"], request["patch"], request["contract"]), Path(request["avatar_path"]),
                                    Path(request["prepared"]["audio_path"]), request["prepared"]["duration"], request["cues"])
            validate(queue, request)
            previous = {"request_sha256": request["request_sha256"], "source_queue_id": request["source_queue_id"],
                        "source_task_id": request["source_task_id"], "source_revision": request["source_revision"],
                        "source_work_id": request["source_work_id"], "source_version_sha256": request["source_version_sha256"],
                        "patch": request["patch"], "contract": request["contract"], "output_sha256": sha(output), "cloud_calls": 0, "provider_jobs": [],
                        "sources_unchanged": True, "human_review": "pending"}
            atomic_private(receipt, previous)
        catalog = WorkCatalog(queue.projects_root)
        original_work = catalog.get(request["source_work_id"])
        caption_refresh = request["contract"] == CAPTION_CONTRACT
        label = "字幕清晰版clear-v2" if caption_refresh else "脚注修正版"
        work = catalog.register(request["project_id"], output, work_key=original_work["work_key"], mode=original_work["mode"],
                                event_id=job["job_id"], quality_passed=False, actor="local-investment-recompose",
                                summary="招商A本地" + label + "；复用原音轨、数字人与真实字幕；原队列 " + request["source_queue_id"])
        if work["work_id"] != request["source_work_id"]: raise WorkError("修正版未登记到原作品")
        version = next(v for v in work["versions"] if v["sha256"] == sha(output))
        previous.update(work_id=work["work_id"], version_id=version["version_id"])
        atomic_private(receipt, previous)
        atomic_private(folder / "qa.json", {"template_id": TEMPLATE_ID, "caption_timing": "original_asr_reused",
                        "provider_jobs": [], "cloud_calls": 0, "source_queue_id": request["source_queue_id"],
                        "source_revision": request["source_revision"], "display_refresh": label, "human_review": "pending"})
        return {"status": "completed", "stage": "招商A本地" + label + "已合成，等待审核", "result": {
            "output_path": str(output), "qa_status": "pending", "work_id": work["work_id"], "version_id": version["version_id"],
            "source_queue_id": request["source_queue_id"], "source_task_id": request["source_task_id"],
            "source_revision": request["source_revision"], "output_sha256": sha(output), "cloud_calls": 0}}
    except WorkError as error:
        return {"status": "failed", "stage": str(error), "error": {"type": "LocalInvestmentRecompose", "message": str(error)},
                "retryable": error.code == "unavailable", "safe_resume_point": "local_recompose"}
