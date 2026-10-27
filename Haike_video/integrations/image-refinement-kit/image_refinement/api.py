"""Standalone shared HTTP surface; trusted internal clients use one bearer token."""

from __future__ import annotations

import asyncio
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

from .presets import HEIGHT, WIDTH
from .provider import RefinementError
from .service import MAX_BYTES, RefinementService


def create_app(service: RefinementService | None = None, *, token: str | None = None):
    service = service or RefinementService(
        Path(os.getenv("IMAGE_REFINEMENT_DATA_DIR", ".image-refinement"))
    )
    token = (
        token if token is not None else os.getenv("IMAGE_REFINEMENT_SERVICE_TOKEN", "")
    )
    if not token:
        raise ValueError("共享HTTP服务必须设置 IMAGE_REFINEMENT_SERVICE_TOKEN")

    @asynccontextmanager
    async def lifespan(app):
        service.start()
        try:
            yield
        finally:
            service.close()

    app = FastAPI(title="图片精修服务", lifespan=lifespan)
    app.state.refinement_service = service

    async def authorize(authorization: str = Header(default="")):
        if not token or not hmac.compare_digest(authorization, "Bearer " + token):
            raise HTTPException(401, "需要有效的服务访问令牌。")

    @app.exception_handler(RefinementError)
    async def refinement_error(request, exc):
        from fastapi.responses import JSONResponse

        status = (
            404
            if exc.code == "not_found"
            else 409
            if exc.code in {"conflict", "confirmation_required"}
            else 422
        )
        return JSONResponse({"detail": str(exc), "code": exc.code}, status_code=status)

    @app.get("/health")
    async def health():
        return {"ok": True, "service": "image-refinement"}

    @app.get("/v1/config", dependencies=[Depends(authorize)])
    async def config():
        return service.settings.public() | {
            "preset_version": service.preset_version,
            "width": WIDTH,
            "height": HEIGHT,
        }

    @app.post("/v1/jobs", dependencies=[Depends(authorize)])
    async def submit(request: Request, namespace: str, confirmed: bool = False):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BYTES:
                raise HTTPException(413, "图片不能超过25MB。")
        return await asyncio.to_thread(
            service.submit, bytes(raw), namespace, confirmed=confirmed
        )

    @app.get("/v1/jobs/{job_id}", dependencies=[Depends(authorize)])
    async def get(job_id: str, namespace: str):
        return await asyncio.to_thread(service.get, job_id, namespace)

    @app.post("/v1/jobs/{job_id}/retry", dependencies=[Depends(authorize)])
    async def retry(job_id: str, namespace: str, payload: dict = Body(default={})):
        raw = await asyncio.to_thread(service.file, job_id, namespace, "source")
        return await asyncio.to_thread(
            service.submit,
            raw,
            namespace,
            retry_of=job_id,
            confirmed=payload.get("confirmed") is True,
            acknowledge_uncertain=payload.get("acknowledge_uncertain") is True,
        )

    @app.get("/v1/jobs/{job_id}/files/{kind}", dependencies=[Depends(authorize)])
    async def file(job_id: str, kind: str, namespace: str):
        raw = await asyncio.to_thread(service.file, job_id, namespace, kind)
        # Result is always PNG; source and raw are decoded by the client.
        return Response(
            raw,
            media_type="image/png" if kind == "result" else "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{job_id}-{kind}'
                + ('.png"' if kind == "result" else '.bin"'),
                "Cache-Control": "private, no-store",
            },
        )

    return app
