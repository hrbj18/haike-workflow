"""Local image-edit bridge. Supplier credentials stay in the gateway."""
import asyncio
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse

from backlot.studio_refinement import RefinementCenter
from backlot.work_api import call

router = APIRouter(prefix="/api/studio/refinement")


async def invoke(request, method, *args):
    from backlot.studio_api import studio
    return await asyncio.to_thread(call, lambda: getattr(RefinementCenter(studio(request)), method)(*args))


@router.post("/prepare")
async def prepare(request: Request, data: Annotated[dict, Body()]):
    from backlot.studio_api import mutation
    mutation(request)
    return await invoke(request, "prepare", data.get("draft_id"), data.get("asset_id"))


@router.get("/tasks/{task_id}")
async def get(task_id: str, request: Request):
    return await invoke(request, "get", task_id)


@router.post("/tasks/{task_id}/submit")
async def submit(task_id: str, request: Request, data: Annotated[dict, Body()]):
    from backlot.studio_api import mutation
    mutation(request)
    return await invoke(request, "start", task_id, data)


@router.post("/tasks/{task_id}/renew")
async def renew(task_id: str, request: Request, data: Annotated[dict, Body()]):
    from backlot.studio_api import mutation
    mutation(request)
    if data != {"confirmed": True}:
        raise HTTPException(422, "请确认延长原报价")
    return await invoke(request, "renew", task_id)


@router.post("/tasks/{task_id}/decision")
async def decide(task_id: str, request: Request, data: Annotated[dict, Body()]):
    from backlot.studio_api import mutation
    mutation(request)
    if set(data) != {"use_refined"} or type(data["use_refined"]) is not bool:
        raise HTTPException(422, "请选择精修图或原图")
    return await invoke(request, "decide", task_id, data["use_refined"])


@router.get("/media/{operation}")
async def image(operation: str, request: Request):
    path = await invoke(request, "image", operation)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, no-store"})
