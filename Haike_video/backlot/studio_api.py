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
            return {"summary": sdk.request("/account/summary"), "capabilities": sdk.request("/capabilities")}
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
