"""Host-authenticated routes for the framework-neutral browser widget.

resolve_scope(request) is a synchronous host callback: validate session, project
ownership and CSRF, then return an account/project namespace. Reject with an
HTTPException on failure. Pass it explicitly; no anonymous default is provided.
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import Response

from image_refinement.provider import RefinementError
from image_refinement.service import MAX_BYTES


def public_job(job):
    return {
        key: job[key]
        for key in ("id", "status", "error", "error_code", "metadata", "can_retry")
    } | {
        "config": {
            key: job["config"][key]
            for key in (
                "preset_version",
                "prompt",
                "width",
                "height",
                "image_model",
                "text_model",
            )
        }
    }


def make_router(service, resolve_scope):
    router = APIRouter(prefix="/refinement")

    def scope(request):
        namespace = resolve_scope(request)
        if not isinstance(namespace, str) or not namespace:
            raise HTTPException(403, "请先登录并选择有权限的项目")
        return namespace

    async def invoke(method, *args, **kwargs):
        try:
            return await asyncio.to_thread(method, *args, **kwargs)
        except RefinementError as error:
            status = (
                404
                if error.code == "not_found"
                else 409
                if error.code in {"confirmation_required", "conflict"}
                else 422
            )
            raise HTTPException(status, str(error)) from None

    @router.post("/jobs")
    async def submit(request: Request, confirmed: bool = False):
        namespace = scope(request)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BYTES:
                raise HTTPException(413, "图片最多25MB")
        job = await invoke(service.submit, bytes(raw), namespace, confirmed=confirmed)
        return public_job(job)

    @router.get("/jobs/{job_id}")
    async def get(job_id: str, request: Request):
        return public_job(await invoke(service.get, job_id, scope(request)))

    @router.get("/jobs/{job_id}/files/{kind}")
    async def file(job_id: str, kind: str, request: Request):
        raw = await invoke(service.file, job_id, scope(request), kind)
        return Response(
            raw,
            media_type="image/png" if kind == "result" else "application/octet-stream",
            headers={"Cache-Control": "private, no-store"},
        )

    @router.post("/jobs/{job_id}/retry")
    async def retry(job_id: str, request: Request, data: Annotated[dict, Body()]):
        namespace = scope(request)
        source = await invoke(service.file, job_id, namespace, "source")
        return public_job(
            await invoke(
                service.submit,
                source,
                namespace,
                retry_of=job_id,
                confirmed=data.get("confirmed") is True,
                acknowledge_uncertain=data.get("acknowledge_uncertain") is True,
            )
        )

    return router


# Host integration:
# service = RefinementService(host_private_path, settings=Settings.from_env())
# app.include_router(make_router(service, your_existing_auth_and_project_check))
# In the host lifespan: service.start(); yield; service.close()
# In mounted subapps, explicitly manage lifespan from the parent application.
