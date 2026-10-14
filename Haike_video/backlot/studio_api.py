"""Local HTTP interface: templates, draft assets, private Key and publication calendar."""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from backlot.studio import Studio, TEMPLATES
from backlot.work_api import catalog, call
from backlot.work_catalog import WorkError
from backlot import work_publish

router = APIRouter()
REMOVED_ENTRIES = {"/audio": "/avatar", "/automation": "/calendar", "/material-library": "/graphic", "/material-library/manage": "/graphic", "/material-commentary": "/projects", "/published-clips": "/projects", "/works": "/projects", "/legacy/projects": "/projects"}


def studio(request):
    value = getattr(request.app.state, "studio", None)
    if value is None:
        value = Studio(request.app.state.works_projects_root); request.app.state.studio = value
    return value


def mutation(request):
    # A local Key holder is never exposed to cross-origin browser forms.
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "请从本地海客工作台提交")
    content = request.headers.get("content-type", "")
    if "application/json" not in content and request.url.path != "/api/studio/assets" and not request.url.path.endswith("/cover-upload"):
        raise HTTPException(415, "请求需要JSON格式")


@router.get("/graphic", response_class=HTMLResponse)
@router.get("/avatar", response_class=HTMLResponse)
@router.get("/calendar", response_class=HTMLResponse)
@router.get("/settings", response_class=HTMLResponse)
@router.get("/projects", response_class=HTMLResponse)
def page():
    path = Path(__file__).parent / "ui/avatar-generator/index.html"
    return HTMLResponse(path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-cache"})


@router.get("/api/studio/templates")
def templates(): return {"templates": TEMPLATES}


@router.get("/api/studio/motion/catalog")
async def motion_catalog(layout: str = "portrait"):
    from backlot.studio_motion import library
    return await asyncio.to_thread(call, library, layout)


@router.get("/api/studio/motion/media/{name:path}")
def motion_media(name: str):
    from backlot.studio_motion import public_media
    return FileResponse(call(public_media, name))


@router.get("/api/studio/motion/guides/{name}")
def motion_guide(name: str):
    from backlot.studio_motion import guide
    return call(guide, name)


@router.get("/api/studio/motion/sources")
def motion_sources(request: Request):
    from backlot.studio_motion import motion_sources
    return {"items": call(motion_sources, studio(request))}


@router.get("/api/studio/drafts/{draft_id}/motion-source")
async def motion_source(draft_id: str, request: Request):
    from backlot.studio_motion import source_metadata
    s=studio(request)
    return await asyncio.to_thread(call,source_metadata,s,call(s.draft,draft_id))


@router.get("/api/studio/drafts/{draft_id}/motion-source/media")
def motion_source_media(draft_id: str, request: Request):
    from backlot.studio_motion import source_video
    s = studio(request)
    video, _ = call(source_video, s, call(s.draft, draft_id))
    return FileResponse(video)


@router.get("/api/studio/drafts/{draft_id}/motion-job")
async def motion_job(draft_id: str, request: Request):
    call(studio(request).draft, draft_id)
    from backlot.server import _ensure_production_queue
    q = _ensure_production_queue(request.app)
    result = await asyncio.to_thread(q.list, project_id=draft_id, limit=200)
    jobs = [j for j in result['tasks'] if j['kind'] == 'studio_motion']
    return {'job': max(jobs, key=lambda j:j['created_at']) if jobs else None}


@router.post("/api/studio/motion/doctor")
async def motion_doctor(request: Request, data: dict = Body(...)):
    mutation(request)
    from backlot.studio_motion import command, VERSION
    result = await asyncio.to_thread(call, command, "doctor")
    return {"version": VERSION, "ready": True, "report": result.stdout}


@router.post("/api/studio/drafts/{draft_id}/motion-plan")
async def motion_plan(draft_id: str, request: Request, data: dict = Body(...)):
    mutation(request); s = studio(request); d = call(s.draft, draft_id)
    if data.get("revision") != d["revision"]: raise HTTPException(409, "内容已更新，请重新保存后检查")
    from backlot.studio_motion import plan
    return await asyncio.to_thread(call, plan, s, d)


@router.get("/api/studio/drafts/{draft_id}/motion-project/{revision}")
def motion_project(draft_id: str, revision: int, request: Request):
    s = studio(request); call(s.draft, draft_id)
    if revision < 1: raise HTTPException(404, "工程不存在")
    path = s.projects_root / draft_id / "renders" / ("studio-" + str(revision)) / "editable-project.zip"
    if not path.is_file() or path.is_symlink(): raise HTTPException(404, "工程尚未生成")
    return FileResponse(path, filename="海客动效口播-可编辑工程.zip")


@router.get("/api/studio/settings")
def settings(request: Request): return call(studio(request).settings)


@router.get("/api/studio/ai/status")
def ai_status(request: Request):
    from backlot.studio_storyboard import status
    return call(status, studio(request))


@router.post("/api/studio/drafts/{draft_id}/ai-preview")
async def ai_preview(draft_id: str, request: Request, data: dict = Body(...)):
    mutation(request); s = studio(request); d = call(s.draft,draft_id)
    if data != {"revision":d["revision"],"confirmed":True}: raise HTTPException(409,"草稿已改变，请重新保存后确认AI理解")
    from backlot.studio_storyboard import preview
    return await asyncio.to_thread(call,preview,s,d)


@router.get("/api/studio/drafts/{draft_id}/ai-preview")
def ai_preview_saved(draft_id: str, request: Request):
    import json
    s=studio(request); d=call(s.draft,draft_id)
    path=s.projects_root/draft_id/"assets/ai-preview"/str(d["revision"])/"preview.json"
    return {"plan":json.loads(path.read_text()) if path.is_file() else None}


@router.get("/api/studio/drafts/{draft_id}/storyboard")
def storyboard(draft_id: str, request: Request, revision: int | None = None):
    import json
    s = studio(request); d = call(s.draft, draft_id)
    if revision is not None and not 1 <= revision <= d["revision"]: raise HTTPException(422,"分镜版本无效")
    path = s.projects_root / draft_id / "renders" / ("studio-" + str(revision or d["revision"])) / "storyboard.json"
    return {"plan": json.loads(path.read_text()) if path.is_file() else None}


@router.get("/api/studio/drafts/{draft_id}/avatar-job")
def avatar_job(draft_id: str, request: Request):
    call(studio(request).draft, draft_id)
    from backlot.server import _ensure_production_queue
    result = call(_ensure_production_queue(request.app).list, project_id=draft_id, limit=200)
    jobs = [j for j in result["tasks"] if j["kind"] == "studio_avatar"]
    return {"job": max(jobs, key=lambda j:j["created_at"]) if jobs else None}


@router.post("/api/studio/ai/jobs/{job_id}/skip-douyin")
def skip_douyin(job_id: str, request: Request, data: dict = Body(...)):
    mutation(request)
    if data != {"confirmed": True}: raise HTTPException(422, "请明确确认跳过抖音")
    from backlot.server import _ensure_production_queue
    from backlot.studio import atomic_private, timestamp
    q = _ensure_production_queue(request.app); job = call(q.get, job_id, include_private=True)
    if job["kind"] != "studio_avatar" or job["status"] != "failed": raise HTTPException(409, "只能恢复暂停的口播任务")
    d = job["frozen_request"]["draft"]
    path = studio(request).projects_root / d["id"] / "renders" / ("studio-" + str(d["revision"])) / "source-decisions.json"
    atomic_private(path, {"skip_douyin": True, "confirmed_at": timestamp(), "reason": "用户明确跳过抖音，恢复原任务"})
    return call(q.retry, job_id)


@router.post("/api/studio/ai/douyin/login")
async def douyin_login(request: Request, data: dict = Body(...)):
    mutation(request)
    if data != {"confirmed": True}: raise HTTPException(422,"请确认打开抖音登录窗口")
    from backlot.studio_storyboard import login_prepare
    return await asyncio.to_thread(call,login_prepare,studio(request))


@router.post("/api/studio/ai/douyin/login-confirmed")
def douyin_login_confirmed(request: Request, data: dict = Body(...)):
    mutation(request)
    if data != {"confirmed": True}: raise HTTPException(422,"请完成抖音登录后再确认")
    from backlot.studio_storyboard import configuration, status
    from backlot.studio import atomic_private
    s=studio(request); c=configuration(s); c["douyin_login_confirmed"]=True
    atomic_private(s.private / "studio-ai/relay.json",c)
    return call(status,s)


@router.get("/api/studio/ai/jobs/{job_id}/douyin-candidates")
def douyin_candidates(job_id: str, request: Request):
    import json
    from backlot.server import _ensure_production_queue
    q=_ensure_production_queue(request.app); job=call(q.get,job_id,include_private=True)
    if job["kind"]!="studio_avatar": raise HTTPException(422,"请选择口播任务")
    d=job["frozen_request"]["draft"]
    folder=studio(request).projects_root/d["id"]/"renders"/("studio-"+str(d["revision"]))/"ai-requests"
    items=[x for p in folder.glob("scene-*-candidates.json") for x in json.loads(p.read_text()).get("items",[])]
    return {"items":items}


@router.post("/api/studio/ai/jobs/{job_id}/authorize-douyin")
def authorize_douyin(job_id: str, request: Request, data: dict = Body(...)):
    import json
    from backlot.studio import atomic_private, timestamp
    mutation(request)
    if set(data)!={"video_id","rights_confirmed"} or data["rights_confirmed"] is not True: raise HTTPException(422,"请确认拥有此视频的使用权")
    candidates=douyin_candidates(job_id,request)["items"]
    if data["video_id"] not in {c["id"] for c in candidates}: raise HTTPException(422,"视频不在本次候选中")
    from backlot.server import _ensure_production_queue
    q=_ensure_production_queue(request.app);job=call(q.get,job_id,include_private=True)
    if job["status"]!="failed": raise HTTPException(409,"只能恢复暂停的任务")
    d=job["frozen_request"]["draft"];path=studio(request).projects_root/d["id"]/"renders"/("studio-"+str(d["revision"]))/"source-decisions.json"
    value=json.loads(path.read_text()) if path.exists() else {}
    value.update(authorized_video_ids=sorted(set(value.get("authorized_video_ids",[])+[data["video_id"]])),confirmed_at=timestamp())
    atomic_private(path,value)
    return call(q.retry,job_id)


@router.post("/api/studio/settings")
async def connect(request: Request, data: dict = Body(...)):
    mutation(request)
    return await asyncio.to_thread(call, studio(request).connect, data)


@router.get("/api/studio/account")
async def account(request: Request):
    if not studio(request).settings()["configured"]:
        return {"configured": False, "summary": None, "capabilities": {"items": []}}
    def read():
        try:
            sdk = studio(request).client()
            from backlot.studio_asr import status
            return {"summary": sdk.request("/account/summary"), "capabilities": sdk.request("/capabilities"), "local_asr": status(studio(request))}
        except Exception: raise WorkError("无法读取账户，请到API设置检查连接") from None
    return await asyncio.to_thread(call, read)


@router.get("/api/studio/drafts")
def drafts(request: Request): return call(studio(request).drafts)


@router.post("/api/studio/drafts")
def save_draft(request: Request, data: dict = Body(...)):
    mutation(request); return call(studio(request).save_draft, data)


@router.get("/api/studio/drafts/{draft_id}")
def draft(draft_id: str, request: Request): return call(studio(request).draft, draft_id)


@router.post("/api/studio/assets")
async def upload(request: Request, draft_id: str, kind: str, filename: str):
    mutation(request)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 80 * 1024 * 1024: raise HTTPException(413, "文件最多80MB")
    if kind == "sequence":
        from backlot.studio_motion import save_bundle
        return await asyncio.to_thread(call, save_bundle, studio(request), draft_id, filename, bytes(content))
    value=await asyncio.to_thread(call, studio(request).save_asset, draft_id, filename, kind, bytes(content))
    if kind=='video':
        from backlot.studio_motion import narration_clock
        from backlot.studio_render import media_probe
        value.update(await asyncio.to_thread(call,lambda:narration_clock(media_probe(studio(request).asset(value['id'],draft_id)))))
    return value


@router.get("/api/studio/assets/{asset_id}")
def asset(asset_id: str, request: Request): return FileResponse(call(studio(request).asset, asset_id))


@router.post("/api/studio/drafts/{draft_id}/generate")
def generate(draft_id: str, request: Request, data: dict = Body(...)):
    mutation(request)
    s = studio(request); d = call(s.draft, draft_id)
    if data.get("revision") != d["revision"]: raise HTTPException(409, "制作内容已更新，请重新确认")
    template = call(s.template, d["template_id"])
    if data.get("confirmed") is not True: raise HTTPException(422, "请确认本次制作及费用上限")
    kind = template["kind"]
    if template["id"] == "avatar-motion-adu-v1":
        from backlot.studio_motion import freeze
        frozen = call(freeze, s, d, data.get("plan_id"), data.get("confirmed")); kind = "motion"
    elif template["kind"] == "graphic":
        from backlot.studio_render import validate_graphic
        call(validate_graphic, s, d)
        frozen = {"draft": d, "render_id": "studio-" + str(d["revision"])}
    else:
        from backlot.studio_avatar import frozen_request
        frozen = call(frozen_request, s, d, data.get("quote_id"), data.get("max_charge_micros"))
    from backlot.server import _ensure_production_queue
    render_id = "studio-" + str(d["revision"])
    project_dir = s.projects_root / draft_id
    if not (project_dir / "project.json").exists():
        from lib.checkpoint import init_project
        init_project(draft_id, title=d["title"], pipeline_type="animated-explainer", pipeline_dir=s.projects_root)
    return call(_ensure_production_queue(request.app).submit, project_id=draft_id, kind="studio_" + kind, source="workbench", priority="normal",
                parent_job_id=render_id, idempotency_key=f"studio:{draft_id}:{d['revision']}", frozen_request=frozen)


@router.post("/api/studio/drafts/{draft_id}/quote")
async def quote_avatar(draft_id: str, request: Request, data: dict = Body(...)):
    mutation(request)
    s = studio(request); d = call(s.draft, draft_id)
    if data.get("revision") != d["revision"]: raise HTTPException(409, "制作内容已更新，请重新读取报价")
    from backlot.studio_avatar import quote
    def read():
        try: return quote(s, d)
        except WorkError: raise
        except Exception: raise WorkError("无法读取报价：请检查统一Key和管理员模型费率；尚未提交付费任务") from None
    return await asyncio.to_thread(call, read)


@router.post("/api/studio/works/{work_id}/cover-upload")
async def upload_cover(work_id: str, request: Request):
    mutation(request)
    c = catalog(request); w = call(c.get, work_id)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 10 * 1024 * 1024: raise HTTPException(413, "封面最多10MB")
    from PIL import Image, ImageOps
    from io import BytesIO
    try:
        with Image.open(BytesIO(body)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            if image.width < 600 or image.height < 800 or abs(image.width / image.height - .75) > .01: raise ValueError()
            folder = c.project(w["project_id"]) / "assets/publish"; folder.mkdir(parents=True, exist_ok=True)
            path = folder / ("cover-" + uuid4().hex + ".jpg"); image.save(path, quality=95)
        return {"path": str(path), "name": "发布封面", "url": f"/api/works/{work_id}/cover"}
    except Exception: raise HTTPException(422, "请上传至少600×800像素的3:4图片作为封面") from None


@router.post("/api/studio/works/{work_id}/materials")
def materials(work_id: str, request: Request, data: dict = Body(...)):
    mutation(request)
    return call(catalog(request).change, work_id, "materials", {"revision": data.get("revision"), "data": {"title": str(data.get("title") or ""), "desc": str(data.get("desc") or ""), "topics": str(data.get("topics") or ""), "cover_path": str(data.get("cover_path") or ""), "cover_origin": "provided_image", "source_rights_status": "confirmed" if data.get("rights_confirmed") is True else "unknown", "request_evidence": "用户在海客工作台填写并保存发布资料"}}, actor="studio")


@router.get("/api/studio/publishing")
async def publishing(request: Request):
    try:
        accounts = await asyncio.to_thread(work_publish.CreatorGateway().accounts)
        return {"accounts": accounts, "available": True, "message": "按确认排期由发布服务自动执行"}
    except WorkError:
        return {"accounts": [], "available": False, "message": "发布服务暂时不可连接；请启动CreatorHub后刷新，计划仍会保存"}


@router.get("/api/studio/calendar")
def calendar(request: Request): return call(studio(request).calendar)


@router.post("/api/studio/calendar")
def save_calendar(request: Request, data: dict = Body(...)):
    mutation(request); return call(studio(request).save_calendar, data, catalog(request))


@router.post("/api/studio/calendar-batch")
def batch_calendar(request: Request, data: dict = Body(...)):
    mutation(request); return call(studio(request).batch_calendar, data, catalog(request))


@router.post("/api/studio/calendar/{plan_id}/activate")
async def activate(plan_id: str, request: Request, data: dict = Body(...)):
    mutation(request)
    return await asyncio.to_thread(call, studio(request).activate_calendar, plan_id, data.get("confirmed"), catalog(request))


@router.post("/api/studio/calendar/{plan_id}/cancel")
async def cancel(plan_id: str, request: Request, data: dict = Body(...)):
    mutation(request)
    return await asyncio.to_thread(call, studio(request).cancel_calendar, plan_id)


@router.post("/api/studio/calendar/sync")
async def sync_calendar(request: Request, data: dict = Body(...)):
    mutation(request)
    return await asyncio.to_thread(call, studio(request).sync_calendar, catalog(request))
