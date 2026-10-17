"""Loopback-only task ledger API. No media/provider/publish execution endpoints."""
import ipaddress
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from backlot.automation_task_center import LocalSources, TaskCenter
from backlot.work_api import call


def _loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def local_request(request: Request, response: Response):
    """Protect private reads and writes from remote access and DNS rebinding.

    Forwarded headers do not grant permission. A JSON mutation can also be
    made by a local CLI without Origin, but browser origins must match exactly.
    """
    try:
        host = urlsplit("//" + request.headers.get("host", "")).hostname
    except ValueError:
        host = None
    if not request.client or not _loopback(request.client.host) or not _loopback(host):
        raise HTTPException(403, "任务总账仅限本机工作台访问")
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "请从当前本机工作台访问任务总账")
    if request.method not in {"GET", "HEAD"}:
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise HTTPException(415, "任务操作需要JSON格式")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"


router = APIRouter(prefix="/api/task-center", dependencies=[Depends(local_request)])


def center(request):
    value = getattr(request.app.state, "task_center", None)
    if value is None:
        from backlot.studio_api import studio
        from backlot.studio import TEMPLATES
        s = studio(request)
        queue = getattr(request.app.state, "production_queue", None)
        works = getattr(request.app.state, "work_catalog", None)
        value = TaskCenter(s.private / "task-center.sqlite3", sources=LocalSources(s.projects_root,
            queue_path=getattr(queue, "db_path", None), works_path=getattr(works, "db_path", None)),
            template_ids=[item["id"] for item in TEMPLATES])
        request.app.state.task_center = value
    return value


@router.get("/summary")
def summary(request: Request, cursor: int = 0, limit: int = 100):
    return call(center(request).summary, cursor=cursor, limit=limit)


@router.get("/tasks")
def tasks(request: Request, limit: int = 100):
    return call(center(request).list, limit=limit)


@router.post("/tasks")
def create(request: Request, data: dict = Body(...)):
    return call(center(request).create, data)


@router.get("/tasks/{task_id}")
def detail(task_id: str, request: Request):
    return call(center(request).detail, task_id)


@router.patch("/tasks/{task_id}")
def update(task_id: str, request: Request, data: dict = Body(...)):
    return call(center(request).update, task_id, data)


@router.get("/tasks/{task_id}/events")
def events(task_id: str, request: Request, cursor: int = 0, limit: int = 50):
    return call(center(request).events, task_id, cursor=cursor, limit=limit)


@router.post("/tasks/{task_id}/events")
def append_event(task_id: str, request: Request, data: dict = Body(...)):
    return call(center(request).append_event, task_id, data)


@router.post("/tasks/{task_id}/commands")
def request_command(task_id: str, request: Request, data: dict = Body(...)):
    return call(center(request).request_command, task_id, data)


@router.post("/commands/{command_id}/ack")
def acknowledge(command_id: str, request: Request, data: dict = Body(...)):
    return call(center(request).acknowledge, command_id, data)


@router.get("/commands")
def commands(request: Request, cursor: int = 0, limit: int = 100, status: str = "requested"):
    return call(center(request).commands, cursor=cursor, limit=limit, status=status)


@router.get("/plan")
def plan(request: Request):
    return call(center(request).plan)


@router.put("/plan")
def save_plan(request: Request, data: dict = Body(...)):
    return call(center(request).save_plan, data)
