"""Small local material library UI/API; source paths are never URL parameters."""
from pathlib import Path
from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from backlot import material_library as library
from backlot import material_library_evidence as evidence
from backlot import material_library_selection as selection

router = APIRouter()


def call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/material-library", response_class=HTMLResponse)
def page():
    return HTMLResponse((Path(__file__).parent / "ui/avatar-generator/index.html").read_text(encoding="utf-8"), headers={'Cache-Control': 'no-cache'})


@router.get("/api/material-library/status")
def status(): return call(library.summary)


@router.get("/api/material-library/search")
def search(query: str = "", limit: int = Query(100, ge=1, le=500)):
    return {"media": call(library.list_media, query, limit=limit), "clips": call(library.list_clips, query, limit=limit)}


@router.post("/api/material-library/import")
def ingest(payload: dict = Body(...)):
    path = Path(str(payload.get("path") or ""))
    if payload.get("kind") == "catalog": return call(library.ingest_catalog, path)
    if payload.get("kind") == "folder": return call(library.scan_folder, path)
    if payload.get("kind") == "file": return call(library.register_file, path)
    raise HTTPException(422, "请选择素材文件、文件夹或标准交付清单")


@router.post("/api/material-library/sync-published")
def sync(): return call(library.sync_published)


@router.get("/api/material-library/media/{media_id}")
def media(media_id: str): return call(library.get_media, media_id)


@router.get("/api/material-library/media/{media_id}/video")
def video(media_id: str): return FileResponse(call(library.resolve_media, media_id))


@router.post("/api/material-library/evidence")
def prepare(payload: dict = Body(...)): return call(evidence.prepare_task, payload)


@router.get("/api/material-library/evidence/{task_id}")
def task(task_id: str): return call(evidence.read_task, task_id)


@router.get("/api/material-library/evidence/{task_id}/images/{filename}")
def task_image(task_id: str, filename: str):
    task = call(evidence.read_task, task_id)
    allowed = {sheet["file"] for w in task["windows"] for sheet in w["sheets"]}
    if filename not in allowed: raise HTTPException(404, "证据图片不存在")
    call(evidence.check_task, task)
    return FileResponse(evidence.task_directory(task_id) / filename)


@router.post("/api/material-library/evidence/submit")
def submit(payload: dict = Body(...)): return call(evidence.submit_task, payload)


@router.post("/api/material-library/plan")
def plan(payload: dict = Body(...)):
    return call(selection.normalize_plan, payload) if "entities" in payload else call(selection.default_plan, str(payload.get("topic") or ""))


@router.post("/api/material-library/candidates")
def candidates(payload: dict = Body(...)): return call(selection.compact_candidates, payload)


@router.post("/api/material-library/select")
def select(payload: dict = Body(...)):
    return call(selection.select, payload.get("plan", {}), clip_ids=payload.get("clip_ids"))


@router.get("/api/material-library/selections")
def selections(plan_id: str = ""): return call(selection.selection_history, plan_id)


@router.post("/api/material-library/acquisition")
def acquire(payload: dict = Body(...)): return call(selection.acquisition_request, payload)


@router.post("/api/material-library/acquisition/{request_id}/finish")
def finish(request_id: str, payload: dict = Body(...)): return call(selection.finish_acquisition, request_id, payload)


# Additive management routes; preserve all V1 selection and evidence contracts.
from backlot.material_library_manage_api import router as management_router
router.include_router(management_router)
