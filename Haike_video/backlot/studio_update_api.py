"""Local-only bridge to the portable application's independent updater."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import secrets
import sys
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from portable import update_service as updates

router = APIRouter(prefix="/api/studio/app-update")


def service(app):
    value = getattr(app.state, "app_update_service", None)
    if value is None:
        value = updates.UpdateService(ROOT)
        app.state.app_update_service = value
    return value


def local_request(request):
    from portable.update_worker import local_url
    try:
        local_url(str(request.base_url).rstrip("/"))
    except ValueError:
        raise HTTPException(403, "请从本机海客工作台使用更新功能")
    if request.client and request.client.host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(403, "更新功能仅供本机使用")


def mutation(request):
    from backlot.studio_api import mutation as studio_mutation
    local_request(request)
    studio_mutation(request)
    if request.headers.get("origin") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "请从本机海客工作台确认更新")


@router.get("")
def status(request: Request):
    local_request(request)
    return service(request.app).snapshot()


@router.post("/check")
async def check(request: Request, data: dict = Body(...)):
    mutation(request)
    return await asyncio.to_thread(service(request.app).check)


@router.post("/install")
async def install(request: Request, data: dict = Body(...)):
    mutation(request)
    try:
        return await asyncio.to_thread(service(request.app).install, data.get("version"),
                                       str(request.base_url).rstrip("/"), request.app.state.update_instance_id,
                                       os.getpid(), data.get("confirmed") is True)
    except updates.core.UpdateError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/import')
async def import_package(request: Request):
    mutation(request)
    updater = service(request.app)
    current = updates.current_release(updater.root)
    cap = updates.capability(updater.root, current)
    if not cap['can_install']:
        raise HTTPException(409, cap['reason'])
    if request.headers.get('content-type') != 'application/octet-stream':
        raise HTTPException(415, '请选择程序更新ZIP文件')
    archive = updates.private_path(updater.root, 'import-'+secrets.token_hex(12)+'/package.zip')
    size = 0
    try:
        with archive.open('xb') as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > updates.core.MAX_ARCHIVE_BYTES:
                    raise HTTPException(413, '更新包不能超过300 MB')
                output.write(chunk)
        return await asyncio.to_thread(updater.import_archive, archive)
    except updates.core.UpdateError as exc:
        archive.unlink(missing_ok=True)
        raise HTTPException(409, str(exc)) from exc
    except BaseException:
        archive.unlink(missing_ok=True)
        raise


@router.post("/cancel")
def cancel(request: Request, data: dict = Body(...)):
    mutation(request)
    try:
        return service(request.app).cancel()
    except updates.core.UpdateError as exc:
        raise HTTPException(409, str(exc)) from exc


def publisher_busy(root):
    # Publication/account services retain their code and keep running. Still
    # wait for in-flight work and uncertain external submissions before restart.
    from backlot.work_publish import CreatorGateway
    gateway = CreatorGateway()
    identity = gateway.call("/api/download-sessions")
    expected = hashlib.sha256(str((Path(root) / "creatorhub").resolve()).replace("\\", "/").casefold().encode()).hexdigest()
    if identity.get("service_fingerprint") != expected:
        return "账号服务身份尚未确认，请先检查本副本的账号服务。"
    tasks = gateway.tasks()
    for task in tasks:
        status = task.get("status")
        if status == "pending" and task.get("scheduled_at") and task.get("scheduled_at_is_utc", True):
            try:
                scheduled = datetime.fromisoformat(task["scheduled_at"].replace("Z", "+00:00"))
                if scheduled.tzinfo is None:
                    scheduled = scheduled.replace(tzinfo=timezone.utc)
                if scheduled > datetime.now(timezone.utc) + timedelta(minutes=2):
                    continue
            except (ValueError, TypeError):
                pass
        if status in {"pending", "running", "publishing", "doing", "submitting", "uncertain", "canceling"}:
            return "正在等待发布任务结束；结果待确认的提交请先核对原任务。"
    collections = gateway.call("/api/collections")
    rows = collections if isinstance(collections, list) else collections.get("items", [])
    if any(item.get("status") in {"pending", "running"} for item in rows):
        return "正在等待素材下载与采集任务结束。"
    return ""


def audio_busy(app, root):
    projects = Path(getattr(app.state, "works_projects_root", Path(root) / "Haike_video/projects"))
    private = projects.parent / ".backlot"
    database = private / "studio.sqlite3"
    if database.is_file():
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='studio_audio_operations'").fetchone()
            if exists and db.execute("SELECT 1 FROM studio_audio_operations WHERE attempts>0 AND outcome IS NULL LIMIT 1").fetchone():
                return "音色操作结果尚未确认，请先核对原操作或暂缓更新。"
    for file in (private / "audio-center-internal").glob("*/operations/*/operation.json"):
        record = updates.read_json(file)
        if record.get("status") not in {"succeeded", "failed"}:
            return "正在等待音色操作结束；结果未知时请先核对原操作。"
    return ""


@router.get("/readiness")
async def readiness(request: Request):
    local_request(request)
    root = service(request.app).root
    state = updates.read_json(updates.private_path(root))
    operation = state.get("operation", {})
    identity = operation.get("id", "")
    if not identity or any(c not in "0123456789abcdef" for c in identity) or len(identity) != 24:
        raise HTTPException(403, "没有可恢复的更新任务")
    command = updates.read_json(updates.private_path(root, identity + "/operation.json"))
    token = request.headers.get("x-haike-update-token", "")
    if not token or not hmac.compare_digest(token, command.get("token", "")):
        raise HTTPException(403, "更新助手身份无效")
    busy = ""
    queue_service = getattr(request.app.state, "production_queue", None)
    if queue_service is None:
        from backlot.server import _ensure_production_queue
        queue_service = _ensure_production_queue(request.app)
    queue = await asyncio.to_thread(queue_service.list, limit=200)
    if any(queue.get(k, 0) for k in ("active_count", "queued_count", "waiting_count")):
        busy = "正在等待制作队列结束；结果待确认的任务请先核对，或暂缓本次更新。"
    if getattr(request.app.state, "update_inflight", 0):
        busy = "正在等待已提交的工作台操作结束。"
    from backlot import studio_motion_templates_api
    if studio_motion_templates_api._ACTIVE_PREPARATIONS:
        busy = '正在等待动效模板的素材检查、准备或预览结束。'
    for name in ("recovery_tasks", "media_index_tasks", "media_index_batch_tasks", "interaction_candidate_tasks", "interaction_second_pass_tasks"):
        tasks = getattr(request.app.state, name, {})
        if isinstance(tasks, dict):
            tasks = tasks.values()
        if any(not task.done() for task in tasks):
            busy = "正在等待后台制作或素材任务结束。"
    if not busy:
        try:
            busy = await asyncio.to_thread(audio_busy, request.app, root)
            if not busy:
                busy = await asyncio.to_thread(publisher_busy, root)
        except Exception:
            busy = "暂时无法确认下载与发布状态，请检查本副本账号服务；原程序未修改。"
    return {"ready": not busy, "message": busy}


def attach(app):
    app.state.update_instance_id = secrets.token_hex(16)
    app.state.update_inflight = 0
    app.include_router(router)

    @app.middleware("http")
    async def update_admission(request, call_next):
        path = request.url.path
        managed = path.startswith("/api/") and not path.startswith("/api/studio/app-update") and path != "/api/health"
        is_mutation = managed and request.method not in {"GET", "HEAD", "OPTIONS"}
        if is_mutation and updates.maintenance(service(app).root):
            return JSONResponse({"detail": "工作台正在等待更新或安装更新，暂不接收新操作；现有任务与作品已保留。"}, status_code=503)
        if is_mutation:
            app.state.update_inflight += 1
        try:
            return await call_next(request)
        finally:
            if is_mutation:
                app.state.update_inflight -= 1
