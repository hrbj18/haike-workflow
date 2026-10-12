"""Project dates and version-bound publication ledger; CreatorHub is read-only."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

PLATFORMS = {"douyin": "抖音", "kuaishou": "快手", "shipinhao": "视频号", "xhs": "小红书"}
STATUSES = {"pending": "待发布", "uploading": "上传中", "uploaded": "已上传", "reviewing": "审核中",
            "published": "已发布", "failed": "发布失败", "uncertain": "待核实", "canceled": "已取消"}
_LOCK = threading.RLock()
FILENAME = "artifacts/library-index.json"


class IndexConflict(ValueError):
    pass


def _read(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (OSError, ValueError) as exc:
        raise ValueError("项目索引无法读取，请先检查原始记录") from exc


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".library-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


def _date(value, *, naive_utc=False):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            if not naive_utc:
                return None
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _now():
    return datetime.now(timezone.utc).isoformat()


def creatorhub_snapshot():
    """Read only the publication table, never import its app or call publish APIs."""
    root = Path(__file__).resolve().parents[2] / "creatorhub"
    path = Path(os.environ.get("HAIKE_CREATORHUB_DB", str(root / "data" / "creatorhub.db")))
    cache_path = Path(__file__).resolve().parents[1] / ".backlot" / "library-publish-cache.json"
    source_key = sha256(str(path.resolve()).encode()).hexdigest()
    def unavailable(message):
        try:
            cached = _read(cache_path)
        except ValueError:
            cached = {}
        if cached.get("source_key") == source_key:
            return {**cached, "status": "stale", "message": message + "；保留上次同步结果"}
        return {"status": "unavailable", "message": message, "records": []}
    if not path.is_file():
        return unavailable("发布系统未连接，显示本机记录")
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as connection:
            connection.row_factory = sqlite3.Row
            columns = {r[1] for r in connection.execute("PRAGMA table_info(publishtask)")}
            done = "done_at" if "done_at" in columns else "NULL AS done_at"
            rows = connection.execute(f"SELECT id, platform, account_id, title, status, media_json, result_url, created_at, {done} FROM publishtask ORDER BY id").fetchall()
        records = []
        for raw in rows:
            row = dict(raw)
            try:
                media = json.loads(row.pop("media_json") or "[]")
            except ValueError:
                continue
            if isinstance(media, list):
                row["media_paths"] = [p for p in media if isinstance(p, str)]
                records.append(row)
        snapshot = {"status": "connected", "checked_at": _now(), "records": records, "source_key": source_key}
        try:
            with _LOCK:
                _write(cache_path, snapshot)
        except OSError:
            pass
        return snapshot
    except (sqlite3.Error, OSError):
        return unavailable("发布记录暂时无法读取，稍后刷新重试")


def _inside(project_dir, raw):
    path = Path(raw)
    if not path.is_absolute():
        path = project_dir / path
    try:
        resolved = path.resolve()
        resolved.relative_to(project_dir.resolve())
        return resolved
    except (ValueError, OSError):
        return None


def _version(project_dir, raw):
    path = _inside(project_dir, raw)
    if not path or path.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv"} or not path.is_file():
        return None
    stat = path.stat()
    if not stat.st_size:
        return None
    relative = path.relative_to(project_dir.resolve()).as_posix()
    identity = sha256(f"{relative}:{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()
    return {"id": identity, "path": relative, "size": stat.st_size, "mtime": stat.st_mtime,
            "label": relative, "signature_kind": "path-size-mtime_ns"}


def _source_records(project_dir, snapshot):
    result = []
    # One snapshot is shared by the project-list request. Resolve each source
    # once and group by actual ancestor directories, preserving symlink safety.
    # Keep this request-local; file moves must be visible on the next refresh.
    if "_records_by_directory" not in snapshot:
        grouped = {}
        for row in snapshot["records"]:
            for raw in row["media_paths"]:
                path = Path(raw)
                if not path.is_absolute():
                    continue
                try:
                    path = path.resolve()
                except OSError:
                    continue
                for parent in path.parents:
                    grouped.setdefault(parent, []).append((row, path))
        snapshot["_records_by_directory"] = grouped
    project_root = project_dir.resolve()
    seen = set()
    mapping = {"draft": "pending", "pending": "pending", "publishing": "uploading", "done": "published",
               "uncertain": "uncertain", "failed": "failed", "canceled": "canceled"}
    for row, path in snapshot["_records_by_directory"].get(project_root, []):
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        result.append({"id": f"creatorhub:{row['id']}", "platform": row["platform"],
                "account": str(row["account_id"] or "未知"), "status": mapping.get(row["status"], "uncertain"),
                "source": "creatorhub", "task_id": row["id"], "version_id": None,
                "version_path": path.relative_to(project_root).as_posix(), "version_verified": False,
                "published_at": _date(row["done_at"], naive_utc=True),
                "recorded_at": _date(row["created_at"], naive_utc=True),
                "url": row["result_url"] if str(row["result_url"]).startswith(("https://", "http://")) else "",
                "note": "发布系统记录；文件路径已匹配，历史文件版本仍需核对"})
    return result


def read_index(project_dir, *, board=None, snapshot=None):
    from backlot.state import load_board_state
    project_dir = Path(project_dir)
    board = board if board is not None else load_board_state(project_dir)
    local = _read(project_dir / FILENAME)
    workbench = _read(project_dir / "artifacts/workbench.json")
    snapshot = snapshot if snapshot is not None else creatorhub_snapshot()
    imported = _source_records(project_dir, snapshot)
    records = imported + local.get("records", [])
    records.sort(key=lambda r: r.get("recorded_at") or "", reverse=True)
    paths = [r["path"] for r in (board.get("media") or {}).get("renders", [])]
    preview = (workbench.get("automation") or {}).get("preview_render") or (workbench.get("full_preview") or {}).get("preview") or {}
    if preview.get("output_path"):
        paths.append(preview["output_path"])
    paths += [r["version_path"] for r in records if r.get("version_path")]
    versions = {}
    for path in paths:
        version = _version(project_dir, path)
        if version:
            versions[version["id"]] = version
    versions = sorted(versions.values(), key=lambda v: v["mtime"], reverse=True)
    selected = next((v for v in versions if v["id"] == local.get("selected_version_id")), None)
    current = selected or (versions[0] if versions else None)
    targets = local.get("targets", [])
    latest = {}
    for row in records:
        if current and row.get("version_id") == current["id"] and row.get("platform") not in latest:
            latest[row["platform"]] = row
    published = [p for p in targets if latest.get(p, {}).get("status") == "published"]
    history_count = len({r["platform"] for r in records if r["status"] == "published"})
    history_latest = {}
    for row in records:
        history_latest.setdefault((row["platform"], row.get("account")), row)
    if targets and len(published) == len(targets):
        publication = {"status": "published", "label": f"已发布 {len(published)}/{len(targets)}"}
    elif published:
        publication = {"status": "partial", "label": f"已发布 {len(published)}/{len(targets)}"}
    elif any(r["status"] in {"failed", "uncertain"} for r in latest.values()):
        publication = {"status": "attention", "label": "发布需处理"}
    elif any(r["status"] in {"failed", "uncertain"} for r in history_latest.values()):
        publication = {"status": "attention", "label": "历史发布需核对"}
    elif current and any(r.get("status") == "published" for r in latest.values()):
        publication = {"status": "partial", "label": "已有发布 · 请设置目标平台"}
    elif history_count:
        publication = {"status": "history", "label": f"历史已发 {history_count} 平台 · 当前版本待确认"}
    elif records or targets:
        publication = {"status": "pending", "label": "待发布"}
    else:
        publication = {"status": "none", "label": "暂无发布记录"}
    phase = preview.get("status")
    stages = board.get("stages", [])
    activity_date = _date(workbench.get("updated_at")) or _date(preview.get("started_at"))
    activity = datetime.fromisoformat(activity_date).timestamp() if activity_date else float(board.get("last_activity") or 0)
    if phase in {"generating", "queued", "running"} or any(s.get("status") == "in_progress" for s in stages):
        production = {"status": "producing", "label": "制作中"} if datetime.now(timezone.utc).timestamp() - activity < 900 else {"status": "attention", "label": "制作进度待核实"}
    elif phase == "failed" or any(s.get("status") == "failed" for s in stages):
        production = {"status": "failed", "label": "制作需处理"}
    elif current:
        production = {"status": "review", "label": "有成片 · 待审核"}
    else:
        production = {"status": "draft", "label": "草案"}
    created = _date(local.get("created_at")) or _date(board.get("created_at"))
    updated = max(float(board.get("last_activity") or 0),
        datetime.fromisoformat(_date(workbench.get("updated_at"))).timestamp() if _date(workbench.get("updated_at")) else 0)
    return {"revision": local.get("revision", 0), "created_at": created,
        "created_source": "manual" if local.get("created_at") else "project" if created else "unknown",
        "updated_at": datetime.fromtimestamp(updated, timezone.utc).isoformat() if updated else None,
        "targets": targets, "versions": versions, "current_version": current, "records": records,
        "selected_version_id": local.get("selected_version_id"),
        "newer_version_available": bool(selected and versions and selected["id"] != versions[0]["id"]),
        "version_count": len(versions),
        "publication": {**publication, "platforms": {p: latest.get(p, {}).get("status", "pending") for p in targets},
                        "history_platforms": sorted({r["platform"] for r in records if r["status"] == "published"})},
        "production": production, "sync": {k: v for k, v in snapshot.items() if k not in {"records", "source_key"} and not k.startswith("_")},
        "platform_labels": PLATFORMS, "status_labels": STATUSES}


def summary(project_dir, *, board=None, snapshot=None):
    result = read_index(project_dir, board=board, snapshot=snapshot)
    return {key: result[key] for key in ("created_at", "created_source", "updated_at", "publication", "production", "current_version", "newer_version_available", "version_count", "sync")}


def save_index(project_dir, payload):
    project_dir = Path(project_dir)
    with _LOCK:
        local = _read(project_dir / FILENAME)
        if payload.get("revision") != local.get("revision", 0):
            raise IndexConflict("记录已被其他页面更新，请重新打开后操作")
        kind = payload.get("kind")
        view = read_index(project_dir)
        if kind == "settings":
            targets = payload.get("targets")
            if not isinstance(targets, list) or any(p not in PLATFORMS for p in targets):
                raise ValueError("请选择有效的目标平台")
            local["targets"] = list(dict.fromkeys(targets))
            version = payload.get("version_id")
            if version and version not in {v["id"] for v in view["versions"]}:
                raise ValueError("成片已变化，请重新打开记录面板")
            local["selected_version_id"] = version or None
            created = payload.get("created_at")
            if created:
                if not _date(created):
                    raise ValueError("创建日期必须包含时区")
                local["created_at"] = _date(created)
        elif kind == "record":
            if payload.get("platform") not in PLATFORMS or payload.get("status") not in STATUSES:
                raise ValueError("平台或发布状态无效")
            version = next((v for v in view["versions"] if v["id"] == payload.get("version_id")), None)
            if not version:
                raise ValueError("请选择仍存在的成片版本")
            account = str(payload.get("account") or "").strip()
            if not account or len(account) > 100:
                raise ValueError("请填写发布账号名称或编号（最多 100 字）")
            url, note = str(payload.get("url") or "").strip(), str(payload.get("note") or "").strip()
            if len(url) > 2000 or (url and not url.startswith(("https://", "http://"))) or len(note) > 1000:
                raise ValueError("作品链接应为 HTTP/HTTPS 地址，备注最多 1000 字")
            published_at = _date(payload.get("published_at"))
            if payload["status"] == "published" and not published_at:
                raise ValueError("标记已发布时请填写实际发布时间")
            identifier = str(payload.get("id") or "manual:" + uuid4().hex)
            records = local.setdefault("records", [])
            previous = next((r for r in records if r["id"] == identifier), None)
            if not previous and not identifier.startswith("manual:"):
                raise ValueError("发布系统记录只读，请补录人工核对记录")
            if previous:
                local.setdefault("history", []).append(previous)
            row = {"id": identifier, "platform": payload["platform"], "account": account,
                "status": payload["status"], "source": "manual", "version_id": version["id"],
                "version_path": version["path"], "version_verified": True, "published_at": published_at,
                "recorded_at": _now(), "url": url, "note": note}
            local["records"] = [r for r in records if r["id"] != identifier] + [row]
        else:
            raise ValueError("不支持的记录操作")
        local["revision"] = local.get("revision", 0) + 1
        local["updated_at"] = _now()
        _write(project_dir / FILENAME, local)
        return read_index(project_dir)
