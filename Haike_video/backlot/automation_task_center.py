"""Cross-project orchestration ledger. No production/publish execution.

Reported state and read-only local receipts remain distinct. Commands require
an explicit acknowledgement; money uses integer CNY micros, None is unknown.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.parse import quote
from uuid import uuid4

from backlot.production_queue import _safe_public
from backlot.work_catalog import WorkError

STATUSES = {"planned", "queued", "running", "paused", "awaiting_human", "uncertain", "completed", "failed", "cancelled"}
COMMANDS = {"report_now", "pause_requested", "resume_requested"}
EVENT_KINDS = {"stage", "report", "fact", "heartbeat", "note"}
LINK_KEYS = {"project_id", "draft_id", "queue_job_id", "work_id", "calendar_id", "publish_plan_id"}
MONEY_KEYS = {"limit_micros", "actual_micros", "reserved_micros", "estimated_micros"}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}\Z")
_BARE_KEY = re.compile(r"(?i)\b(?:hk_|sk[-_])[A-Za-z0-9_-]{12,}\b")
_PRIVATE_KEY = re.compile(r"(?i)api.?key|secret|token|authorization|cookie|password|credential|private.?key")
_AUTH_TEXT = re.compile(r"(?i)\b(bearer\s+|(?:authorization|cookie|password|secret|access_token)\s*[:=]\s*)[^\r\n,;]+")
_URL_TEXT = re.compile(r"https?://[^\s<>\"']+")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identifier(value, label="编号"):
    if not isinstance(value, str) or not _ID.fullmatch(value) or _BARE_KEY.search(value):
        raise WorkError(f"{label}无效")
    return value


def _shape(value, depth=0):
    if depth > 7:
        raise WorkError("任务资料层级过多")
    if value is None or type(value) in {bool, int}:
        return
    if isinstance(value, str):
        if len(value) > 12000 or "\x00" in value:
            raise WorkError("任务文字过长或包含无效字符")
        return
    if isinstance(value, float):
        # JSON serialization rejects NaN/Infinity below.
        return
    if isinstance(value, dict) and len(value) <= 100:
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 120:
                raise WorkError("任务资料字段无效")
            _shape(item, depth + 1)
        return
    if isinstance(value, list) and len(value) <= 100:
        for item in value:
            _shape(item, depth + 1)
        return
    raise WorkError("任务资料格式无效或项目过多")


def public(value):
    """Sanitize before persistence as well as before HTTP output."""
    _shape(value)
    try:
        size = len(encoded(value).encode("utf-8"))
    except (ValueError, TypeError):
        raise WorkError("任务资料必须是有效JSON") from None
    if size > 64000:
        raise WorkError("任务资料过大，请保存证据引用而非完整原文")

    def clean(item):
        if isinstance(item, dict):
            return {key: clean(child) for key, child in item.items() if not _PRIVATE_KEY.search(key)}
        if isinstance(item, list):
            return [clean(child) for child in item]
        if isinstance(item, str):
            item = _BARE_KEY.sub("[REDACTED]", _AUTH_TEXT.sub(lambda m: m.group(1) + "[REDACTED]", item))
            # Evidence sometimes includes a signed URL. Never store its query,
            # fragment or userinfo in this customer-visible ledger.
            def clean_url(match):
                try:
                    part = urlsplit(match.group(0))
                    host = part.hostname or ""
                    if ":" in host:
                        host = "[" + host + "]"
                    if part.port:
                        host += ":" + str(part.port)
                    return urlunsplit((part.scheme, host, part.path, "", ""))
                except ValueError:
                    return "[INVALID_URL]"
            return _URL_TEXT.sub(clean_url, item)
        return item

    return clean(_safe_public(value))


def text(value, label, maximum, *, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise WorkError(f"{label}无效或过长")
    return public(value.strip())


def budget(value, previous=None):
    if not isinstance(value, dict) or set(value) - (MONEY_KEYS | {"currency"}):
        raise WorkError("预算字段无效；请使用整数微元")
    if value.get("currency", "CNY") != "CNY":
        raise WorkError("任务总账仅支持人民币")
    result = previous.copy() if previous else {key: None for key in MONEY_KEYS}
    result["currency"] = "CNY"
    for key in MONEY_KEYS & value.keys():
        item = value[key]
        if item is not None and (type(item) is not int or not 0 <= item <= 10**15):
            raise WorkError("金额须为非负整数微元；未知金额请保留为空")
        result[key] = item
    return result


def evidence(value):
    if not isinstance(value, list) or len(value) > 50:
        raise WorkError("证据引用须为列表，最多50项")
    result = []
    for item in value:
        if not isinstance(item, dict) or set(item) - {"label", "ref", "kind"}:
            raise WorkError("证据引用格式无效")
        ref = text(item.get("ref"), "证据引用", 2000)
        if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", ref) and not ref.startswith(("http://", "https://", "sha256:")):
            raise WorkError("证据仅支持网页、摘要或相对文件引用")
        if ref.startswith(("/", "\\")) or ".." in ref.split("/"):
            raise WorkError("证据文件请使用工作区内的相对引用")
        result.append({"label": text(item.get("label", "证据"), "证据名称", 160),
                       "ref": ref, "kind": text(item.get("kind", "evidence"), "证据类型", 40)})
    return result


def links(value, previous=None):
    if not isinstance(value, dict) or set(value) - LINK_KEYS:
        raise WorkError("任务关联字段无效")
    result = previous.copy() if previous else {}
    for key, item in value.items():
        if item is None:
            result.pop(key, None)
        else:
            result[key] = identifier(item, "关联编号")
    return result


def _fingerprint(value):
    _shape(value)
    return hashlib.sha256(encoded(value).encode("utf-8")).hexdigest()


class LocalSources:
    """Read existing local databases with SQLite mode=ro. No remote refresh.

    Publishing attempts are the last locally synchronized receipts. In
    particular, status=done and acceptance=verified do not assert public
    visibility. Missing/error snapshots are explicit rather than success.
    """
    def __init__(self, projects_root, *, queue_path=None, works_path=None):
        self.projects_root = Path(projects_root)
        private = Path(projects_root).parent / ".backlot"
        self.queue_path = Path(queue_path or private / "production-queue.sqlite3")
        self.works_path = Path(works_path or private / "works.sqlite3")
        self.studio_path = private / "studio.sqlite3"

    @staticmethod
    def _read(path, sql, identity, fields=None):
        if not path.is_file():
            return {"id": identity, "availability": "missing"}
        try:
            db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
            try:
                db.row_factory = sqlite3.Row
                row = db.execute(sql, (identity,)).fetchone()
            finally:
                db.close()
            if row is None:
                return {"id": identity, "availability": "missing"}
            value = json.loads(row["data"]) if "data" in row.keys() else dict(row)
            if not isinstance(value, dict):
                raise ValueError("source record is not an object")
            if fields:
                value = {key: value[key] for key in fields if key in value}
            return {**value, "id": identity, "availability": "available"}
        except (sqlite3.Error, ValueError, OSError):
            return {"id": identity, "availability": "unavailable", "message": "本机来源记录暂不可读，请保留原任务后重查"}

    @staticmethod
    def _attempts(items):
        fields = {"plan_id", "task_id", "platform", "account_id", "status", "error", "blocked_reason",
                  "next_allowed_at", "acceptance_status", "identity_verified", "result_url", "synced_at", "at"}
        if not isinstance(items, list):
            return []
        result = []
        for item in items[:100]:
            if not isinstance(item, dict):
                continue
            value = {**{key: item[key] for key in fields if key in item}, "public_visible": None}
            acceptance = item.get("acceptance") or {}
            identity = acceptance.get("work_id") if isinstance(acceptance, dict) else None
            if isinstance(identity, str) and re.fullmatch(r"[A-Za-z0-9_/-]{1,180}", identity):
                value["platform_work_id"] = identity
                if item.get("identity_verified") is True and acceptance.get("unique_work") is True:
                    if item.get("platform") == "douyin" and identity.isdecimal():
                        value["work_url"] = "https://www.douyin.com/video/" + identity
                    elif item.get("platform") == "kuaishou" and re.fullmatch(r"[A-Za-z0-9]{5,80}", identity):
                        value["work_url"] = "https://www.kuaishou.com/short-video/" + identity
            result.append(value)
        return result

    def snapshot(self, bound):
        result = {"queue": None, "work": None, "calendar": None}
        work_id = bound.get("work_id")
        if bound.get("queue_job_id"):
            value = self._read(self.queue_path,
                "SELECT job_id,project_id,status,stage,revision,updated_at,started_at,finished_at,result_json,error_json,retryable,safe_resume_point FROM production_jobs WHERE job_id=?",
                bound["queue_job_id"])
            if value["availability"] == "available":
                try:
                    receipt = json.loads(value.pop("result_json") or "{}")
                    value["error"] = json.loads(value.pop("error_json") or "{}")
                    value["work_id"] = receipt.get("work_id")
                    work_id = work_id or value["work_id"]
                except (ValueError, AttributeError):
                    value = {"id": bound["queue_job_id"], "availability": "unavailable", "message": "生产回执不可读，请保留原任务后重查"}
            result["queue"] = value
        if work_id:
            value = self._read(self.works_path, "SELECT data FROM works WHERE id=?", work_id,
                {"work_id", "project_id", "title", "revision", "final_version_id", "updated_at", "attempts", "materials"})
            materials = value.pop("materials", [])
            materials = materials if isinstance(materials, list) else []
            selected = next((m for m in reversed(materials) if isinstance(m, dict)
                             and m.get("version_id") == value.get("final_version_id")), {})
            data = selected.get("data") or {}
            data = data if isinstance(data, dict) else {}
            version = value.get("final_version_id")
            if isinstance(version, str) and _ID.fullmatch(version) and _ID.fullmatch(work_id):
                value["result"] = {"video_url": f"/api/works/{work_id}/media?version={quote(version, safe='')}",
                    "cover_url": f"/api/works/{work_id}/cover?version={quote(version, safe='')}" if data.get("cover_path") else None,
                    **{key: data[key] for key in ("title", "desc", "topics") if isinstance(data.get(key), str)}}
            value["attempts"] = self._attempts(value.get("attempts", []))
            result["work"] = value
        if bound.get("calendar_id"):
            value = self._read(self.studio_path, "SELECT data FROM studio_calendar WHERE id=?", bound["calendar_id"],
                {"status", "revision", "work_id", "scheduled_at", "updated_at", "accounts", "attempts", "message"})
            value["attempts"] = self._attempts(value.get("attempts", []))
            result["calendar"] = value
        if bound.get("draft_id") or bound.get("project_id") or bound.get("queue_job_id"):
            from backlot.task_material_results import task_material_result
            materials = task_material_result(self.projects_root, self.studio_path, self.queue_path, bound)
            if materials is not None:
                result["material_result"] = materials
        return public(result)


class TaskCenter:
    def __init__(self, db_path, *, sources=None, template_ids=()):
        self.db_path = Path(db_path)
        self.sources = sources
        self.template_ids = frozenset(template_ids)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection(write=True) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS task_center_tasks(
                    id TEXT PRIMARY KEY, client_id TEXT NOT NULL UNIQUE,
                    fingerprint TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS task_center_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    client_id TEXT NOT NULL, fingerprint TEXT NOT NULL, data TEXT NOT NULL,
                    UNIQUE(task_id,client_id), FOREIGN KEY(task_id) REFERENCES task_center_tasks(id));
                CREATE TABLE IF NOT EXISTS task_center_changes(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES task_center_tasks(id));
                CREATE INDEX IF NOT EXISTS task_center_changes_task ON task_center_changes(task_id,id);
                CREATE TABLE IF NOT EXISTS task_center_commands(
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL, client_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL,
                    UNIQUE(task_id,client_id), FOREIGN KEY(task_id) REFERENCES task_center_tasks(id));
                CREATE TABLE IF NOT EXISTS task_center_plan(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self, *, write=False):
        try:
            db = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        except sqlite3.Error:
            raise WorkError("任务总账暂不可读取，请保留原数据后重试", "unavailable") from None
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except sqlite3.Error:
            db.rollback()
            raise WorkError("任务总账暂不可写入，请保留原数据后重试", "unavailable") from None
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _task(db, task_id):
        row = db.execute("SELECT data FROM task_center_tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise WorkError("任务不存在", "missing")
        return json.loads(row[0])

    @staticmethod
    def _save(db, task, *, progress=False):
        task["revision"] += 1
        task["updated_at"] = now()
        if progress:
            task["last_progress_at"] = task["updated_at"]
        db.execute("UPDATE task_center_tasks SET data=? WHERE id=?", (encoded(task), task["id"]))
        db.execute("INSERT INTO task_center_changes(task_id) VALUES(?)", (task["id"],))

    @staticmethod
    def _cas(task, expected):
        if type(expected) is not int or expected != task["revision"]:
            raise WorkError("任务已更新，请刷新后重试", "conflict")

    def create(self, data):
        allowed = {"client_id", "title", "batch_id", "kind", "status", "stage", "summary", "budget", "links", "facts", "evidence"}
        if not isinstance(data, dict) or set(data) - allowed:
            raise WorkError("任务创建字段无效")
        client_id = identifier(data.get("client_id"), "客户端幂等编号")
        fingerprint = _fingerprint(data)
        status = data.get("status", "planned")
        if status not in STATUSES or data.get("kind", "production") not in {"production", "collection", "publishing"}:
            raise WorkError("任务状态或类别无效")
        if not isinstance(data.get("facts", {}), dict):
            raise WorkError("事实资料须为对象")
        stamp = now()
        task = {"id": "TC-" + uuid4().hex[:24], "client_id": client_id, "revision": 1,
                "title": text(data.get("title"), "任务名称", 200), "kind": data.get("kind", "production"),
                "batch_id": identifier(data["batch_id"], "批次编号") if data.get("batch_id") else None,
                "status": status, "stage": text(data.get("stage", "待开始"), "当前阶段", 120),
                "summary": text(data.get("summary", ""), "任务摘要", 2000, empty=True),
                "budget": budget(data.get("budget", {})), "links": links(data.get("links", {})),
                "facts": public(data.get("facts", {})), "evidence": evidence(data.get("evidence", [])),
                "created_at": stamp, "updated_at": stamp, "last_progress_at": stamp, "heartbeat_at": None,
                "status_source": "reported", "sources": {"queue": None, "work": None, "calendar": None}}
        with self.connection(write=True) as db:
            old = db.execute("SELECT fingerprint,data FROM task_center_tasks WHERE client_id=?", (client_id,)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise WorkError("客户端编号已有不同任务，请读取原任务后继续", "conflict")
                return self._summary(db, json.loads(old["data"]))
            db.execute("INSERT INTO task_center_tasks VALUES(?,?,?,?)", (task["id"], client_id, fingerprint, encoded(task)))
            db.execute("INSERT INTO task_center_changes(task_id) VALUES(?)", (task["id"],))
            return self._summary(db, task)

    def update(self, task_id, data):
        allowed = {"expected_revision", "title", "status", "stage", "summary", "budget", "links", "facts", "evidence"}
        if not isinstance(data, dict) or set(data) - allowed:
            raise WorkError("任务更新字段无效")
        with self.connection(write=True) as db:
            task = self._task(db, task_id)
            self._cas(task, data.get("expected_revision"))
            before = encoded(task)
            progress_fields = {key: task[key] for key in ("stage", "status", "summary")}
            for key, maximum in (("title", 200), ("stage", 120), ("summary", 2000)):
                if key in data:
                    task[key] = text(data[key], "任务文字", maximum, empty=key == "summary")
            if "status" in data:
                if data["status"] not in STATUSES:
                    raise WorkError("任务状态无效")
                task["status"] = data["status"]
            if "budget" in data:
                task["budget"] = budget(data["budget"], task["budget"])
            if "links" in data:
                task["links"] = links(data["links"], task["links"])
            if "facts" in data:
                if not isinstance(data["facts"], dict):
                    raise WorkError("事实资料须为对象")
                task["facts"] = public(data["facts"])
            if "evidence" in data:
                task["evidence"] = evidence(data["evidence"])
            if encoded(task) == before:
                return self._summary(db, task)
            changed = [key for key, previous in progress_fields.items() if task[key] != previous]
            self._save(db, task, progress=True)
            if changed:
                # Persist the reported snapshot beside its CAS update, never
                # as a later request that can fail while the task still commits.
                item = {"task_id": task_id, "client_id": "update-" + uuid4().hex, "kind": "stage",
                        "stage": task["stage"], "message": task["summary"] or "任务当前阶段或状态已更新。",
                        "facts": {"status": task["status"], "task_revision": task["revision"], "changed_fields": changed},
                        "evidence": [], "created_at": task["updated_at"]}
                db.execute("INSERT INTO task_center_events(task_id,client_id,fingerprint,data) VALUES(?,?,?,?)",
                           (task_id, item["client_id"], _fingerprint(item), encoded(item)))
            return self._summary(db, task)

    @staticmethod
    def _summary(db, task):
        value = {key: item for key, item in task.items() if key not in {"facts", "evidence"}}
        snapshot = task.get("facts", {}).get("snapshot") or {}
        publishing = snapshot.get("publishing") if isinstance(snapshot, dict) else {}
        targets = publishing.get("targets", []) if isinstance(publishing, dict) else []
        targets = targets if isinstance(targets, list) else []
        value["expected_targets"] = [{"platform": item["platform"], "account_id": item["account_id"]}
                                     for item in targets if isinstance(item, dict) and item.get("platform") in {"douyin", "kuaishou", "shipinhao"}
                                     and type(item.get("account_id")) is int]
        value["pending_commands_count"] = db.execute(
            "SELECT COUNT(*) FROM task_center_commands WHERE task_id=? AND status='requested'", (task["id"],)).fetchone()[0]
        return value

    def refresh_sources(self, task_id=None):
        """Materialize local receipts only; GET polling never executes work.

        Source projection changes use their own cursor but do not advance the
        reporter's CAS revision or last-progress clock merely due to polling.
        """
        if self.sources is None:
            return
        with self.connection() as db:
            values = [self._task(db, task_id)] if task_id else [json.loads(row[0]) for row in db.execute("SELECT data FROM task_center_tasks")]
        for original in values:
            snapshot = self.sources.snapshot(original["links"])
            if snapshot == original["sources"]:
                continue
            with self.connection(write=True) as db:
                task = self._task(db, original["id"])
                # A concurrent reporter may rebind the source while it is read.
                if task["links"] != original["links"] or task["sources"] != original["sources"]:
                    continue
                task["sources"] = snapshot
                db.execute("UPDATE task_center_tasks SET data=? WHERE id=?", (encoded(task), task["id"]))
                db.execute("INSERT INTO task_center_changes(task_id) VALUES(?)", (task["id"],))

    def list(self, *, limit=100):
        _page(0, limit)
        self.refresh_sources()
        with self.connection() as db:
            values = [self._summary(db, json.loads(row[0])) for row in db.execute(
                "SELECT data FROM task_center_tasks ORDER BY rowid DESC LIMIT ?", (limit + 1,))]
        return {"items": values[:limit], "has_more": len(values) > limit}

    def summary(self, *, cursor=0, limit=100):
        _page(cursor, limit)
        self.refresh_sources()
        with self.connection() as db:
            rows = db.execute("""SELECT t.data, MAX(c.id) AS seq FROM task_center_tasks t
                JOIN task_center_changes c ON c.task_id=t.id GROUP BY t.id
                HAVING MAX(c.id)>? ORDER BY seq LIMIT ?""", (cursor, limit + 1)).fetchall()
            values = [self._summary(db, json.loads(row["data"])) for row in rows[:limit]]
            pending = db.execute("SELECT COUNT(*) FROM task_center_commands WHERE status='requested'").fetchone()[0]
        return {"changes": values, "next_cursor": rows[min(len(rows), limit)-1]["seq"] if rows else cursor,
                "has_more": len(rows) > limit, "pending_commands_count": pending,
                "worker_available": False, "worker_status": "not_connected"}

    def detail(self, task_id):
        self.refresh_sources(task_id)
        with self.connection() as db:
            task = self._task(db, task_id)
            summary = self._summary(db, task)
            task["pending_commands_count"] = summary["pending_commands_count"]
            task["expected_targets"] = summary["expected_targets"]
            events = db.execute("SELECT id,data FROM task_center_events WHERE task_id=? ORDER BY id DESC LIMIT 51", (task_id,)).fetchall()
            task["events"] = [{**json.loads(row["data"]), "id": row["id"]} for row in reversed(events[:50])]
            task["events_has_more"] = len(events) > 50
            task["commands"] = [json.loads(row[0]) for row in db.execute(
                "SELECT data FROM task_center_commands WHERE task_id=? ORDER BY rowid DESC LIMIT 50", (task_id,))]
        return task

    def append_event(self, task_id, data):
        allowed = {"client_id", "kind", "stage", "message", "facts", "evidence"}
        if not isinstance(data, dict) or set(data) - allowed or data.get("kind") not in EVENT_KINDS:
            raise WorkError("阶段事件格式无效")
        client = identifier(data.get("client_id"), "事件幂等编号")
        fingerprint = _fingerprint(data)
        if not isinstance(data.get("facts", {}), dict):
            raise WorkError("事件事实须为对象")
        item = {"task_id": task_id, "client_id": client, "kind": data["kind"],
                "stage": text(data.get("stage", ""), "阶段", 120, empty=True),
                "message": text(data.get("message", ""), "事件说明", 4000, empty=True),
                "facts": public(data.get("facts", {})), "evidence": evidence(data.get("evidence", [])), "created_at": now()}
        with self.connection(write=True) as db:
            task = self._task(db, task_id)
            old = db.execute("SELECT id,fingerprint,data FROM task_center_events WHERE task_id=? AND client_id=?", (task_id, client)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise WorkError("事件编号已有不同记录", "conflict")
                return {**json.loads(old["data"]), "id": old["id"]}
            cur = db.execute("INSERT INTO task_center_events(task_id,client_id,fingerprint,data) VALUES(?,?,?,?)",
                             (task_id, client, fingerprint, encoded(item)))
            if item["kind"] == "heartbeat":
                task["heartbeat_at"] = item["created_at"]
            self._save(db, task, progress=item["kind"] != "heartbeat")
            return {**item, "id": cur.lastrowid}

    def events(self, task_id, *, cursor=0, limit=50):
        _page(cursor, limit)
        with self.connection() as db:
            self._task(db, task_id)
            rows = db.execute("SELECT id,data FROM task_center_events WHERE task_id=? AND id>? ORDER BY id LIMIT ?", (task_id, cursor, limit + 1)).fetchall()
        return {"items": [{**json.loads(row["data"]), "id": row["id"]} for row in rows[:limit]],
                "next_cursor": rows[min(len(rows), limit)-1]["id"] if rows else cursor, "has_more": len(rows) > limit}

    def request_command(self, task_id, data):
        if not isinstance(data, dict) or set(data) != {"client_id", "kind"} or data["kind"] not in COMMANDS:
            raise WorkError("仅支持请求汇报、暂停请求或恢复请求")
        client = identifier(data["client_id"], "命令幂等编号")
        fingerprint = _fingerprint(data)
        command = {"id": "CMD-" + uuid4().hex[:24], "task_id": task_id, "client_id": client,
                   "kind": data["kind"], "status": "requested", "created_at": now(), "acknowledged_at": None, "result": None}
        with self.connection(write=True) as db:
            task = self._task(db, task_id)
            old = db.execute("SELECT fingerprint,data FROM task_center_commands WHERE task_id=? AND client_id=?", (task_id, client)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise WorkError("命令编号已有不同请求", "conflict")
                return json.loads(old["data"])
            db.execute("INSERT INTO task_center_commands VALUES(?,?,?,?,?,?)",
                       (command["id"], task_id, client, fingerprint, command["status"], encoded(command)))
            self._save(db, task)
        return command

    def acknowledge(self, command_id, data):
        if not isinstance(data, dict) or set(data) != {"status", "result"} or data["status"] not in {"acknowledged", "rejected"}:
            raise WorkError("请明确应答或拒绝，并提供简短说明")
        result = text(data["result"], "应答说明", 4000)
        with self.connection(write=True) as db:
            row = db.execute("SELECT data FROM task_center_commands WHERE id=?", (command_id,)).fetchone()
            if row is None:
                raise WorkError("命令不存在", "missing")
            command = json.loads(row[0])
            if command["status"] != "requested":
                if command["status"] == data["status"] and command["result"] == result:
                    return command
                raise WorkError("命令已有应答，不可覆盖", "conflict")
            command.update(status=data["status"], result=result, acknowledged_at=now())
            db.execute("UPDATE task_center_commands SET status=?,data=? WHERE id=?", (command["status"], encoded(command), command_id))
            self._save(db, self._task(db, command["task_id"]))
        return command

    def commands(self, *, cursor=0, limit=100, status="requested"):
        _page(cursor, limit)
        if status not in {"requested", "acknowledged", "rejected", "all"}:
            raise WorkError("命令状态无效")
        with self.connection() as db:
            rows = db.execute("SELECT rowid AS seq,data FROM task_center_commands WHERE rowid>? "
                "AND (?='all' OR status=?) ORDER BY rowid LIMIT ?", (cursor, status, status, limit + 1)).fetchall()
        return {"items": [json.loads(row["data"]) for row in rows[:limit]],
                "next_cursor": rows[min(len(rows), limit)-1]["seq"] if rows else cursor, "has_more": len(rows) > limit}

    def plan(self):
        with self.connection() as db:
            row = db.execute("SELECT data FROM task_center_plan WHERE id=1").fetchone()
        return json.loads(row[0]) if row else {"revision": 0, "enabled": False, "timezone": "Asia/Shanghai",
            "start_time": "02:00", "slots": [], "worker_available": False, "worker_status": "not_connected"}

    def save_plan(self, data):
        fields = {"expected_revision", "enabled", "timezone", "start_time", "slots"}
        if not isinstance(data, dict) or set(data) != fields:
            raise WorkError("每日方案字段不完整")
        if data["enabled"] is not False:
            raise WorkError("每日执行器尚未接入，目前仅能保存未启用方案", "conflict")
        if data["timezone"] != "Asia/Shanghai" or not isinstance(data["start_time"], str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", data["start_time"]):
            raise WorkError("请使用北京时间和有效的24小时制时间")
        if not isinstance(data["slots"], list) or len(data["slots"]) > 12:
            raise WorkError("每日方案最多12条")
        slots = []
        for slot in data["slots"]:
            if not isinstance(slot, dict) or set(slot) != {"template_id", "accounts", "budget_limit_micros", "topic"}:
                raise WorkError("方案条目字段无效")
            template_id = identifier(slot["template_id"], "模板编号")
            if template_id not in self.template_ids:
                raise WorkError("请选择现有模板")
            amount = budget({"limit_micros": slot["budget_limit_micros"]})["limit_micros"]
            if amount is None or amount <= 0:
                raise WorkError("每条视频需设置正数预算上限")
            if not isinstance(slot["accounts"], list) or len(slot["accounts"]) > 12:
                raise WorkError("每条视频最多12个发布账号")
            accounts = []
            for account in slot["accounts"]:
                if not isinstance(account, dict) or set(account) != {"platform", "account_id"} or account["platform"] not in {"douyin", "kuaishou", "shipinhao"} or type(account["account_id"]) is not int or account["account_id"] < 1 or account in accounts:
                    raise WorkError("发布账号格式无效或重复")
                accounts.append(dict(account))
            slots.append({"template_id": template_id, "accounts": accounts, "budget_limit_micros": amount,
                          "topic": text(slot["topic"], "选题范围", 300)})
        with self.connection(write=True) as db:
            row = db.execute("SELECT data FROM task_center_plan WHERE id=1").fetchone()
            revision = json.loads(row[0])["revision"] if row else 0
            if type(data["expected_revision"]) is not int or data["expected_revision"] != revision:
                raise WorkError("方案已更新，请刷新后重试", "conflict")
            value = {"revision": revision + 1, "enabled": False, "timezone": "Asia/Shanghai", "start_time": data["start_time"],
                     "slots": slots, "worker_available": False, "worker_status": "not_connected", "updated_at": now()}
            db.execute("INSERT INTO task_center_plan VALUES(1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (encoded(value),))
        return value


def _page(cursor, limit):
    if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 200:
        raise WorkError("分页游标或数量无效")
