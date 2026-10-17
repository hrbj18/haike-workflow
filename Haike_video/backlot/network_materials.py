"""Local account-session bridge and durable network-material acquisition jobs."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request as http
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, HTTPException, Request, Response

from backlot import material_library as library
from backlot.studio import atomic_private, timestamp
from backlot.studio_api import mutation, studio
from backlot.work_publish import CreatorGateway

router = APIRouter()
_INSTANCE = uuid4().hex
_ACTIVE_TASKS = set()
_STATES = {"ready": "available", "active": "available",
           "login_required": "login_required", "invalid": "login_required",
           "network_error": "network_error"}
# History is an eight-hour display hint; execution still verifies live login.
_SEARCH_CHECK_MAX_AGE_SECONDS = 8 * 60 * 60


def creator_call(path, data=None, *, timeout=25):
    gateway = CreatorGateway()
    base = urlsplit(gateway.base_url)
    if (base.scheme != "http" or base.hostname not in {"127.0.0.1", "localhost", "::1"}
            or base.username or base.password):
        raise HTTPException(503, "账号服务需使用本机回环地址")
    req = http.Request(gateway.base_url + path, data=None if data is None else json.dumps(data).encode(),
                       headers={"Content-Type": "application/json"})
    try:
        with gateway.opener.open(req, timeout=timeout) as response:
            return json.load(response)
    except error.HTTPError as exc:
        detail = "账号操作暂时无法完成，请检查登录状态"
        try:
            value = json.load(exc).get("detail")
            if isinstance(value, str) and not re.search(r"cookie|token|hk_|sk-", value, re.I):
                detail = value[:240]
        except (ValueError, AttributeError):
            pass
        raise HTTPException(exc.code if exc.code < 500 else 503, detail) from None
    except (error.URLError, ValueError, TimeoutError, OSError):
        raise HTTPException(503, "账号服务暂时不可连接，请启动本副本的账号服务后重试") from None


def _session_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def _session_observability(value):
    value = value if isinstance(value, dict) else {}
    result = {key: _session_timestamp(value.get(key)) for key in (
        "checkpoint_at", "background_health_checked_at", "account_last_active_at")}
    for key, allowed in (("background_health_outcome", {"verified", "login_required", "unconfirmed"}),
                         ("background_health_trigger", {"keepalive", "auth_recheck"})):
        result[key] = value.get(key) if isinstance(value.get(key), str) and value[key] in allowed else None
    policy = value.get("keepalive") if isinstance(value.get("keepalive"), dict) else {}
    clean = {key: policy.get(key) if isinstance(policy.get(key), bool) else None for key in ("configured", "engine_running")}
    for key in ("idle_hours", "check_interval_seconds", "jitter_ratio"):
        number = policy.get(key)
        clean[key] = number if type(number) in (float, int) and math.isfinite(number) else None
    clean["mode"] = policy.get("mode") if isinstance(policy.get("mode"), str) and policy["mode"] in {"keepalive", "auth_recheck"} else None
    clean["schedule_status"] = policy.get("schedule_status") if isinstance(policy.get("schedule_status"), str) and policy["schedule_status"] in {
        "unknown", "disabled", "engine_stopped", "no_saved_session", "waiting", "due"} else "unknown"
    clean["next_eligible_at"] = _session_timestamp(policy.get("next_eligible_at"))
    result["keepalive"] = clean
    return result


def _search_session(value):
    """Project existing login evidence, without probing accounts or reading cookies."""
    supported = value.get("platform") == "douyin"
    checked_at = _session_timestamp(value.get("download_checked_at") or value.get("last_checked_at")) if supported else None
    raw_status = value.get("download_check_status")
    if raw_status is None:
        raw_status = value.get("download_status")
    status = "unknown"
    if not supported:
        status = "unsupported"
    elif raw_status == "ready":
        # A recent successful check may be displayed after restart/rotation;
        # it never replaces the execution-time account check.
        age = ((datetime.now(timezone.utc) - datetime.fromisoformat(
            checked_at.replace("Z", "+00:00"))).total_seconds() if checked_at else None)
        status = "available" if age is not None and 0 <= age <= _SEARCH_CHECK_MAX_AGE_SECONDS else "unconfirmed"
    elif isinstance(raw_status, str):
        status = {"not_saved": "login_required", "login_required": "login_required",
                  "invalid": "login_required", "network_error": "network_error",
                  "stored_unverified": "unconfirmed", "unconfirmed": "unconfirmed",
                  "profile_changed": "unconfirmed"}.get(raw_status, "unknown")
    return {"search_supported": supported, "search_status": status, "search_checked_at": checked_at}


def _scope_check(value, scope, live_status):
    raw = value.get(f"{scope}_check_status")
    status = live_status if raw is None else (_STATES.get(raw, "unconfirmed") if isinstance(raw, str) else "unconfirmed")
    checked_at = value.get(f"{scope}_checked_at")
    if scope == "download" and not checked_at:
        checked_at = value.get("last_checked_at")
    return {f"{scope}_check_status": status,
            f"{scope}_checked_at": _session_timestamp(checked_at)}


def session_view(value):
    download_status = value.get("download_status")
    publish_status = value.get("publish_status")
    download_status = download_status if isinstance(download_status, str) else None
    publish_status = publish_status if isinstance(publish_status, str) else None
    live_download = _STATES.get(download_status, "unconfirmed")
    # Historical checks are deliberately separate from current execution proof.
    live_publish = (_STATES.get(publish_status, "unconfirmed") if value.get("publish_verified") else (
        "login_required" if publish_status in {"invalid", "login_required"} else
        "network_error" if publish_status == "network_error" else "unconfirmed"))
    return {"id": value["id"], "platform": value.get("platform", ""),
            "name": value.get("name") or "未命名账号",
            "download_status": live_download, "publish_status": live_publish,
            **_scope_check(value, "download", live_download),
            **_scope_check(value, "publish", live_publish),
            **_search_session(value),
            "saved_at": value.get("saved_at"), "last_checked_at": value.get("last_checked_at"),
            "login_record_saved": value.get("login_record_saved") is True,
            "download_saved": value.get("download_saved") is True,
            "publish_saved": value.get("publish_saved") is True,
            "observability": _session_observability(value.get("observability")),
            "message": value.get("message") or "", "selected": value.get("selected") is True}


@router.get("/api/studio/download-sessions")
async def sessions():
    result = await asyncio.to_thread(creator_call, "/api/download-sessions")
    if (not isinstance(result, dict) or not isinstance(result.get("items"), list)
            or any(not isinstance(item, dict) or type(item.get("id")) is not int or item["id"] <= 0
                   for item in result["items"])):
        return {"items": [], "available": False, "status": "unknown"}
    return {"items": [session_view(item) for item in result["items"]],
            "available": result.get("available", False)}


@router.post("/api/studio/download-sessions/login")
async def login(req: Request, data: dict = Body(...)):
    mutation(req)
    if set(data) != {"platform"} or data["platform"] not in {"douyin", "kuaishou", "shipinhao", "xhs"}:
        raise HTTPException(422, "请选择支持的登录平台")
    result = await asyncio.to_thread(creator_call, "/api/download-sessions/login", data)
    if result.get("preview_url") and re.fullmatch(r"[0-9a-f]{32}", result.get("task_id", "")):
        result["preview_url"] = f"/api/studio/download-sessions/login/{result['task_id']}/preview.png"
    return result


@router.get("/api/studio/download-sessions/login/{task_id}")
async def login_status(task_id: str):
    if not re.fullmatch(r"[0-9a-f]{32}", task_id):
        raise HTTPException(422, "登录任务编号无效")
    result = await asyncio.to_thread(creator_call, "/api/download-sessions/login/" + task_id, timeout=65)
    if result.get("preview_url"):
        result["preview_url"] = f"/api/studio/download-sessions/login/{task_id}/preview.png"
    if isinstance(result.get("account"), dict):
        result["account"] = session_view(result["account"])
    return result


@router.get("/api/studio/download-sessions/login/{task_id}/preview.png")
async def login_preview(task_id: str, req: Request):
    origin = req.headers.get("origin")
    if (origin and origin != str(req.base_url).rstrip("/")) or req.headers.get("sec-fetch-site") in {"cross-site", "same-site"}:
        raise HTTPException(403, "请从海客工作台查看扫码页面")
    if not re.fullmatch(r"[0-9a-f]{32}", task_id):
        raise HTTPException(422, "登录任务编号无效")
    def capture():
        gateway = CreatorGateway()
        parsed = urlsplit(gateway.base_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password):
            raise HTTPException(503, "账号服务需使用本机回环地址")
        try:
            with gateway.opener.open(gateway.base_url +
                    f"/api/download-sessions/login/{task_id}/preview.png", timeout=12) as response:
                if "image/png" not in response.headers.get("Content-Type", ""):
                    raise HTTPException(409, "扫码页面尚未就绪")
                content = response.read(5 * 1024 * 1024 + 1)
                if len(content) > 5 * 1024 * 1024:
                    raise HTTPException(409, "扫码页面预览过大，请使用账号窗口")
                return content
        except error.HTTPError as exc:
            raise HTTPException(exc.code if exc.code in {404, 409, 410} else 503,
                                "扫码页面尚未就绪或登录已结束") from None
        except (error.URLError, TimeoutError, OSError):
            raise HTTPException(503, "账号服务暂时无法提供扫码页面") from None
    return Response(await asyncio.to_thread(capture), media_type="image/png",
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/api/studio/download-sessions/{account_id}/{action}")
async def account_action(account_id: int, action: str, req: Request, data: dict = Body(...)):
    mutation(req)
    if account_id <= 0 or action not in {"check", "open-login", "select"} or data:
        raise HTTPException(422, "账号操作无效")
    result = await asyncio.to_thread(creator_call,
        f"/api/download-sessions/{account_id}/{action}", {}, timeout=65)
    if isinstance(result.get("account"), dict):
        result = {key: result[key] for key in ("ok", "account", "task_id", "status", "message", "preview_url")
                  if key in result}
        result["ok"] = bool(result.get("ok"))
        result["account"] = session_view(result["account"])
    if result.get("preview_url") and re.fullmatch(r"[0-9a-f]{32}", result.get("task_id", "")):
        result["preview_url"] = f"/api/studio/download-sessions/login/{result['task_id']}/preview.png"
    return result


def job_id(value):
    try:
        parsed = UUID(str(value))
        if str(parsed) != str(value).lower():
            raise ValueError()
        return str(parsed)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "下载任务编号无效") from None


def job_path(service, ident):
    return service.private / "network-download" / job_id(ident) / "job.json"


def read_job(service, ident):
    path = job_path(service, ident)
    if not path.is_file():
        raise HTTPException(404, "尚未查到这个下载任务，请保留原编号后重试查询")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value["status"] in {"queued", "running"} and value.get("instance") != _INSTANCE:
        value.update(status="submission_unknown", message="服务曾重启，原下载结果待核对，请勿重复创建任务")
        atomic_private(path, value)
    return value


def public_job(value):
    return {key: value[key] for key in ("id", "status", "message", "result", "created_at", "updated_at")
            if key in value}


def input_request(data):
    if set(data) - {"url", "account_id", "rights_confirmed", "quality", "client_request_id", "platform", "usage_purpose"}:
        raise HTTPException(422, "下载参数无效")
    if data.get("rights_confirmed") is not True:
        raise HTTPException(422, "请确认有权下载和使用这份素材")
    url = data.get("url")
    if not isinstance(url, str) or len(url) > 5000:
        raise HTTPException(422, "请粘贴有效分享链接")
    try:
        parsed = urlsplit(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "请使用不含账号密码的完整分享链接") from None
    host = parsed.hostname.lower()
    platforms = {"douyin": ("douyin.com", "iesdouyin.com", "amemv.com"),
                 "kuaishou": ("kuaishou.com",), "xhs": ("xiaohongshu.com", "xhslink.com"),
                 "shipinhao": ("channels.weixin.qq.com", "finder.video.qq.com")}
    platform = next((name for name, domains in platforms.items()
                     if any(host == domain or host.endswith("." + domain) for domain in domains)), None)
    if platform is None:
        raise HTTPException(422, "请使用支持的平台分享链接，不支持本机地址或其他站点")
    if data.get("platform", platform) != platform:
        raise HTTPException(422, "链接平台与下载参数不一致")
    account_id, quality = data.get("account_id"), data.get("quality", "highest")
    if type(account_id) is not int or account_id <= 0 or quality not in {"highest", "1080p", "720p"}:
        raise HTTPException(422, "请选择下载账号和支持的清晰度")
    payload = {"url": url.strip(), "platform": platform, "account_id": account_id, "quality": quality,
               "rights_confirmed": True}
    if "usage_purpose" in data:
        if data["usage_purpose"] != "local_learning_test":
            raise HTTPException(422, "下载用途无效")
        payload["usage_purpose"] = "local_learning_test"
    return payload


def register_result(service, job, response):
    root = (job_path(service, job["id"]).parent / "media").resolve()
    ids, items, prepared = [], [], []
    results = response.get("results") or []
    if not results or not any(item.get("ok") for item in results):
        raise HTTPException(422, "平台未返回可下载素材，请检查账号登录、链接及页面验证")
    for result in results:
        if not result.get("ok"):
            continue
        metadata = result.get("metadata") or {}
        for file in result.get("files") or []:
            if file.get("role") != "media":
                continue
            path = Path(str(file.get("path") or "")).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise HTTPException(422, "下载文件位置不符，已保留原下载供检查")
            if path.suffix.lower() not in library.SUFFIXES:
                continue
            prepared.append((path, {
                "platform": result.get("input_platform") or "network",
                "source_url": job["input"]["url"],
                "video_id": str(metadata.get("id") or ""),
                "title": str(metadata.get("title") or path.stem),
                "rights_status": "local_learning_only" if job["input"].get("usage_purpose") == "local_learning_test"
                                 else "confirmed"}))
    # Validate the complete remote file list before writing any registry entry.
    for path, metadata in prepared:
        registered = library.register_file(path, metadata)
        for ident in registered["media_ids"]:
            if ident not in ids:
                ids.append(ident)
                items.append({"id": ident, "title": metadata["title"]})
    if not ids:
        raise HTTPException(422, "已处理下载，但没有取得素材库支持的视频文件；原文件已保留")
    return {"media_count": len(ids), "items": items}


def validate_session(payload, listing):
    account = next((item for item in listing.get("items", [])
                    if item.get("id") == payload["account_id"]), None)
    if not account or account.get("platform") != payload["platform"]:
        raise HTTPException(422, "分享链接与下载账号的平台不一致，请选择对应平台账号")
    if account.get("download_status") not in {"ready", "available"}:
        raise HTTPException(409, "下载登录未确认可用，请先检查登录，再发起下载")


async def run_job(service, job):
    path = job_path(service, job["id"])
    try:
        job.update(status="running", message="正在检查登录并下载素材", updated_at=timestamp())
        atomic_private(path, job)
        listing = await asyncio.to_thread(creator_call, "/api/download-sessions")
        validate_session(job["input"], listing)
        output = path.parent / "media"
        result = await asyncio.to_thread(creator_call, "/api/share-download", {
            "share_text": job["input"]["url"], "account_id": job["input"]["account_id"],
            "quality": job["input"]["quality"], "output_dir": str(output),
            "save_thumbnail": False, "save_metadata": True, "save_subtitles": False}, timeout=300)
        registered = await asyncio.to_thread(register_result, service, job, result)
        job.update(status="completed", message="下载完成，已加入素材库", result=registered)
    except HTTPException as exc:
        job.update(status="login_required" if exc.status_code in {401, 409} else (
            "submission_unknown" if exc.status_code == 503 else "failed"), message=str(exc.detail))
    except asyncio.CancelledError:
        job.update(status="submission_unknown", message="下载进程已中断，请保留原编号核对结果")
        raise
    except Exception:
        job.update(status="failed", message="素材下载或入库失败，已保留原任务和文件供检查")
    finally:
        job["updated_at"] = timestamp()
        atomic_private(path, job)


@router.post("/api/studio/network-download")
async def download(req: Request, data: dict = Body(...)):
    mutation(req)
    service, payload = studio(req), input_request(data)
    ident = job_id(data.get("client_request_id"))
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    path = job_path(service, ident)
    if path.exists():
        previous = read_job(service, ident)
        if previous["fingerprint"] != fingerprint:
            raise HTTPException(409, "此任务编号已绑定另一份输入，请查询原任务")
        return public_job(previous)
    listing = await asyncio.to_thread(creator_call, "/api/download-sessions")
    validate_session(payload, listing)
    # A concurrent request may have submitted this id during preflight.
    if path.exists():
        previous = read_job(service, ident)
        if previous["fingerprint"] != fingerprint:
            raise HTTPException(409, "此任务编号已绑定另一份输入，请查询原任务")
        return public_job(previous)
    # No await between checking the id and saving its durable submission.
    value = {"id": ident, "status": "queued", "message": "下载已排队", "input": payload,
             "fingerprint": fingerprint, "instance": _INSTANCE,
             "created_at": timestamp(), "updated_at": timestamp()}
    atomic_private(path, value)
    task = asyncio.create_task(run_job(service, value))
    _ACTIVE_TASKS.add(task)
    task.add_done_callback(_ACTIVE_TASKS.discard)
    return public_job(value)


@router.get("/api/studio/network-download/{ident}")
def download_status(ident: str, req: Request):
    return public_job(read_job(studio(req), ident))
