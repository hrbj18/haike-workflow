"""Shared HTTP surface for completed-work management and local agent tooling."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse

from backlot.work_catalog import WorkCatalog, WorkError
from backlot import work_ingest, work_publish, work_storage

router = APIRouter()
UI = Path(__file__).parent / "ui"


def catalog(request):
    value = getattr(request.app.state, "work_catalog", None)
    if value is None:
        from lib.paths import PROJECTS_DIR
        value = call(WorkCatalog, getattr(request.app.state, "works_projects_root", PROJECTS_DIR))
        request.app.state.work_catalog = value
    return value


def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except WorkError as exc:
        raise HTTPException(status_code={"missing": 404, "not_found": 404, "forbidden": 403, "conflict": 409, "unavailable": 503}.get(exc.code, 422), detail=str(exc)) from exc
    except (KeyError, TypeError, OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="输入或文件不可用，请核对后再操作") from exc


@router.get("/works", response_class=HTMLResponse)
def page():
    return RedirectResponse('/projects', status_code=307)


@router.get("/api/works")
def works(request: Request, query: str = "", candidates: bool = False):
    return call(catalog(request).list, query, include_candidates=candidates)


@router.post("/api/works/register")
def register(request: Request, data: dict = Body(...)):
    allowed = {k: data[k] for k in ("work_key", "mode", "event_id", "quality_passed", "title", "actor", "summary") if k in data}
    return call(catalog(request).register, data.get("project_id", ""), data.get("path", ""), **allowed)


@router.get("/api/works/accounts")
def accounts():
    return call(work_publish.CreatorGateway().accounts)


@router.get("/api/works/plans")
def plans(request: Request, kind: str = "cleanup"):
    with catalog(request).transaction() as db:
        return [json.loads(r[0]) for r in db.execute("SELECT data FROM work_plans WHERE kind=? ORDER BY rowid DESC", (kind,))]


@router.post("/api/works/cleanup/{plan_id}/cancel")
def cleanup_cancel(plan_id: str, request: Request):
    return call(work_storage.cancel, catalog(request), plan_id)


@router.post("/api/works/import-preview")
def import_preview(request: Request):
    return call(work_ingest.import_preview, catalog(request))


@router.post("/api/works/import/{plan_id}")
def import_apply(plan_id: str, request: Request, data: dict = Body(default={})):
    return call(work_ingest.import_apply, catalog(request), plan_id,
                confirmed_indices=data.get("confirmed_indices"), evidence=data.get("evidence", ""))


@router.post("/api/works/cleanup-preview")
def cleanup_preview(request: Request, data: dict = Body(...)):
    return call(work_storage.plan, catalog(request), data.get("work_ids", []))


@router.post("/api/works/cleanup/{plan_id}")
def cleanup_execute(plan_id: str, request: Request, data: dict = Body(...)):
    return call(work_storage.execute, catalog(request), plan_id, data.get("digest"), data.get("confirmed"), actor=data.get("actor", "web"))


@router.post("/api/works/publish/{plan_id}")
def publish_submit(plan_id: str, request: Request, data: dict = Body(...)):
    return call(work_publish.submit, catalog(request), plan_id, data.get("confirmed"), actor=data.get("actor", "web"))


@router.get("/api/works/{work_id}")
def detail(work_id: str, request: Request):
    return call(catalog(request).get, work_id)


@router.get("/api/works/{work_id}/handoff")
def handoff(work_id: str, request: Request):
    return call(catalog(request).handoff, work_id)


@router.get("/api/works/{work_id}/media")
def media(work_id: str, request: Request, version: str | None = None):
    return FileResponse(call(catalog(request).media_path, work_id, version), media_type="video/mp4")


@router.get("/api/works/{work_id}/cover")
def cover(work_id: str, request: Request, version: str | None = None):
    c = catalog(request); w = call(c.get, work_id)
    selected = next((m for m in reversed(w["materials"]) if version is None or m.get("version_id") == version), None)
    if not selected or not selected["data"].get("cover_path"):
        raise HTTPException(404, "封面待准备")
    from backlot.work_catalog import regular_path
    return FileResponse(call(regular_path, selected["data"]["cover_path"], c.project(w["project_id"])))


@router.get("/api/works/{work_id}/storage")
def storage(work_id: str, request: Request):
    return call(work_storage.report, catalog(request), work_id)


@router.post("/api/works/{work_id}/preflight")
def preflight(work_id: str, request: Request, data: dict = Body(...)):
    return call(work_publish.prepare, catalog(request), work_id, data.get("revision"))


@router.post("/api/works/{work_id}/sync")
def sync(work_id: str, request: Request):
    return call(work_publish.sync, catalog(request), work_id)


@router.post("/api/works/{work_id}/acceptance/{task_id}")
def acceptance(work_id: str, task_id: int, request: Request, data: dict = Body(...)):
    return call(work_publish.acceptance, catalog(request), work_id, task_id, data)


@router.post("/api/works/{work_id}/{action}")
def change(work_id: str, action: str, request: Request, data: dict = Body(...)):
    return call(catalog(request).change, work_id, action, data, actor=data.get("actor", "web"))
