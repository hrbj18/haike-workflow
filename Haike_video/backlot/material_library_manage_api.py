"""Additive asset-management contract, independent of production workflows."""
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import HTMLResponse

from backlot import material_library_management as management
from backlot import material_library_refs as refs

router = APIRouter()
PREFIX = "/api/material-library/manage"


def call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (management.MaterialConflictError, refs.MaterialReferenceConflictError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/material-library/manage", response_class=HTMLResponse)
def page():
    return HTMLResponse((Path(__file__).parent / "ui/material_library_manage.html").read_text(encoding="utf-8"))


@router.get(PREFIX + "/status")
def status():
    return call(management.summary)


@router.get(PREFIX + "/search")
def search(query: str = "", tag: str = "", collection: str = "", platform: str = "",
           aspect: str = "all", review_status: str = "all", health: str = "all",
           archived: str = "active", min_duration: float | None = None,
           max_duration: float | None = None, page: int = Query(1, ge=1),
           page_size: int = Query(24, ge=1, le=100)):
    payload = dict(query=query, tag=tag, collection=collection, platform=platform,
                   aspect=aspect, review_status=review_status, health=health,
                   archived=archived, page=page, page_size=page_size)
    if min_duration is not None:
        payload["min_duration"] = min_duration
    if max_duration is not None:
        payload["max_duration"] = max_duration
    return call(management.search, payload)


@router.get(PREFIX + "/media/{media_id}")
def detail(media_id: str):
    result = call(management.detail, media_id)
    result["observations"] = call(refs.list_observations, media_id)
    result["usage"] = call(refs.list_usage, media_id=media_id)
    return result


@router.post(PREFIX + "/metadata")
def metadata(payload: dict = Body(...)):
    return call(management.update_metadata, payload)


@router.post(PREFIX + "/media/{media_id}/health")
def health(media_id: str):
    return call(management.check_health, media_id)


@router.post(PREFIX + "/media/{media_id}/relink")
def relink(media_id: str, payload: dict = Body(...)):
    path = payload.get("path")
    if not isinstance(path, str) or not path.strip():
        raise HTTPException(422, "请填写素材的新位置")
    return call(management.relink, media_id, path)


@router.post(PREFIX + "/project-import")
def import_project(payload: dict = Body(...)):
    return call(refs.import_project, payload)


@router.get(PREFIX + "/aliases")
def alias(namespace: str, external_id: str):
    return call(refs.lookup_alias, namespace, external_id)


@router.post(PREFIX + "/observations")
def observation(payload: dict = Body(...)):
    return call(refs.save_observation, payload)


@router.get(PREFIX + "/observations")
def observations(media_id: str):
    return call(refs.list_observations, media_id)


@router.post(PREFIX + "/references")
def reference(payload: dict = Body(...)):
    return call(refs.freeze_reference, payload)


@router.get(PREFIX + "/references/{ref_id}")
def read_reference(ref_id: str):
    return call(refs.get_reference, ref_id)


@router.get(PREFIX + "/references/{ref_id}/resolve")
def resolve(ref_id: str):
    return call(refs.resolve_reference, ref_id)


@router.post(PREFIX + "/usage")
def usage(payload: dict = Body(...)):
    return call(refs.record_usage, payload)


@router.get(PREFIX + "/usage")
def usages(media_id: str = "", project_id: str = ""):
    return call(refs.list_usage, media_id=media_id, project_id=project_id)
