"""HTTP adapter for the published remix editor, backed by the existing queue."""
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse

from backlot import published_remix as remix
from backlot.production_queue import ProductionQueueConflict, ProductionQueueError

router = APIRouter(prefix="/api/published-remixes")


def _runtime(request):
    from backlot import server
    return server.PROJECTS_DIR, server._ensure_production_queue(request.app)


def _error(exc):
    return HTTPException(409 if isinstance(exc, (remix.RemixConflict, ProductionQueueConflict)) else 422, str(exc))


@router.get("")
def drafts():
    return remix.list_drafts()


@router.post("")
def create(request: Request, payload: dict = Body(...)):
    try:
        root, _ = _runtime(request)
        return remix.create(payload.get("title"), projects_root=root)
    except (ValueError, OSError) as exc:
        raise _error(exc) from exc


@router.get("/{identity}")
def read(identity: str, request: Request):
    try:
        root, queue = _runtime(request)
        draft = remix.read(identity)
        versions = remix.versions(identity, projects_root=root)
        for version in versions:
            job = queue.find_by_idempotency_key(f"published_remix:{identity}:{version['signature']}")
            if job:
                version["queue_job"] = job
                version["status"] = job["status"]
                version["error"] = (job.get("error") or {}).get("message") or version.get("error")
        return {**draft, "versions": versions}
    except (ValueError, OSError) as exc:
        raise _error(exc) from exc


@router.put("/{identity}")
def save(identity: str, payload: dict = Body(...)):
    try:
        return remix.save(identity, payload)
    except (ValueError, OSError) as exc:
        raise _error(exc) from exc


@router.post("/{identity}/render")
def render(identity: str, request: Request, payload: dict = Body(...)):
    try:
        root, queue = _runtime(request)
        return remix.submit(identity, payload.get("revision"), queue, projects_root=root)
    except (ValueError, OSError, ProductionQueueError) as exc:
        raise _error(exc) from exc


@router.get("/{identity}/versions/{signature}/media")
def media(identity: str, signature: str, request: Request, download: bool = False):
    try:
        root, _ = _runtime(request)
        path = remix.output_path(identity, signature, projects_root=root)
        return FileResponse(path, media_type="video/mp4",
            filename=f"{identity}-{signature[:8]}-待审.mp4" if download else None)
    except (ValueError, OSError) as exc:
        raise _error(exc) from exc
