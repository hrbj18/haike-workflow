"""Same-origin local bridge; the browser never receives relay credentials."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse, Response

from backlot.studio_audio import AudioCenter
from backlot.work_api import call

router = APIRouter(prefix="/api/studio/audio-center")


def center(request):
    from backlot.studio_api import studio
    from backlot.studio_services import audio_mode, budget_policy, refresh_private_environment
    value = studio(request)
    if audio_mode(value) == 'internal':
        from backlot.studio_audio_internal import InternalAudioCenter
        refresh_private_environment()
        return InternalAudioCenter(value, pricing=budget_policy(value).get('audio_pricing', {}))
    return AudioCenter(value)


def mutation(request, raw=False):
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "请从本地海客工作台提交")
    expected = "application/octet-stream" if raw else "application/json"
    if expected not in request.headers.get("content-type", ""):
        raise HTTPException(415, "上传需要二进制文件" if raw else "请求需要JSON格式")


async def invoke(request, method, *args):
    def run():
        return getattr(center(request), method)(*args)
    return await asyncio.to_thread(call, run)


@router.get("")
async def voices(request: Request):
    return await invoke(request, "voices")


async def invoke_defaults(request, method, *args):
    from backlot.studio_avatar_defaults import AvatarDefaults
    def run():
        return getattr(AvatarDefaults(center(request)), method)(*args)
    return await asyncio.to_thread(call, run)


@router.get("/avatar-defaults")
async def avatar_defaults(request: Request):
    return await invoke_defaults(request, "read")


@router.put("/avatar-defaults")
async def save_avatar_defaults(request: Request, data: dict = Body(...)):
    mutation(request)
    return await invoke_defaults(request, "save", data)


@router.post("/avatar-defaults/resolve")
async def resolve_avatar_defaults(request: Request, data: dict = Body(...)):
    mutation(request)
    return await invoke_defaults(request, "resolve", data)


@router.put("/preferences")
async def preferences(request: Request, data: dict = Body(...)):
    mutation(request)
    return await invoke(request, "preferences", data)


@router.put("/voices/{voice_id}/preferences")
async def voice_preferences(voice_id: str, request: Request, data: dict = Body(...)):
    mutation(request)
    return await invoke(request, "preferences", data, voice_id)


@router.delete("/voices/{voice_id}")
async def delete_voice(voice_id: str, request: Request):
    mutation(request)
    return await invoke(request, "delete", voice_id)


@router.post("/upload")
async def upload(request: Request, kind: str, filename: str):
    mutation(request, raw=True)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(413, "文件最多20MB")
    return await invoke(request, "upload", bytes(content), kind, filename)


@router.post("/quotes")
async def quote(request: Request, data: dict = Body(...)):
    mutation(request)
    return await invoke(request, "quote", data)


@router.post("/jobs")
async def submit(request: Request, data: dict = Body(...)):
    mutation(request)
    return await invoke(request, "submit", data)


@router.get("/jobs/{operation_id}")
async def job(operation_id: str, request: Request):
    return await invoke(request, "job", operation_id)


@router.get("/jobs/{operation_id}/audio")
async def preview(operation_id: str, request: Request):
    path = await invoke(request, "preview", operation_id)
    with path.open('rb') as audio:
        mime = 'audio/wav' if audio.read(4) == b'RIFF' else 'audio/mpeg'
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "no-store"})


@router.get("/media/{file_id}")
async def media(file_id: str, request: Request):
    content, media_type = await invoke(request, "media", file_id)
    return Response(content, media_type=media_type, headers={"Cache-Control": "no-store"})
