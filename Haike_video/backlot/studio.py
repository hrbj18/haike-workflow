"""Focused creation/configuration module for the two Haike video products."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import threading
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from backlot.work_catalog import WorkError, WorkCatalog
_CALENDAR_LOCK = threading.RLock()

TEMPLATES = [
    {"id": "avatar-motion-adu-v1", "kind": "avatar", "name": "ADu 动效口播", "ratio": "9:16 / 16:9", "width": 1080, "height": 1920,
     "description": "11种风格 · 完整镜头组 · 精确口播时钟", "version": 1, "render_ready": True, "adapter_version": "adu-3.14.0-rc.1", "layout": {"title_size": 60, "accent": "#316dd6"}},
    {"id": "graphic-news-v2", "kind": "graphic", "name": "资讯三景", "ratio": "9:16", "width": 1080, "height": 1920, "duration": 9,
     "description": "大标题 · 结论条 · 三段素材与详情卡", "poster": "graphic-news.png", "version": 2, "render_ready": True,
     "layout": {"title_size": 80, "detail_size": 52, "accent": "#ffcd3c", "background": "#050c16"}},
    {"id": "avatar-safe-circle-v1", "kind": "avatar", "name": "模板1 · 圆框口播", "ratio": "9:16", "width": 1080, "height": 1920,
     "description": "圆框人物 · 素材卡片", "poster": "template1-layout.png", "version": 1, "render_ready": True, "adapter_version": "studio-avatar-v1",
     "layout": {"title_size": 60, "accent": "#316dd6"}},
    {"id": "avatar-full-width-v2", "kind": "avatar", "name": "模板2 · 全宽讲解", "ratio": "9:16", "width": 1080, "height": 1920,
     "description": "圆框人物 · 全宽素材带", "poster": "template2-layout.png", "version": 2, "render_ready": True, "adapter_version": "studio-avatar-v1",
     "layout": {"title_size": 60, "accent": "#316dd6"}},
    {"id": "avatar-template3-card-3x4-v001", "kind": "avatar", "name": "模板3 · 卡片讲解", "ratio": "3:4", "width": 1080, "height": 1440,
     "description": "白色卡片 · 章节讲解", "poster": "template3-poster.png", "sample": "template3-sample.mp4", "version": 1, "render_ready": True, "adapter_version": "studio-avatar-v1",
     "layout": {"title_size": 60, "accent": "#316dd6"}},
]


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def atomic_private(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        os.replace(temp, path)
        os.chmod(path, 0o600)
    finally:
        if temp.exists(): temp.unlink()


def sdk_type():
    root = Path(__file__).resolve().parents[2] / "api-platform"
    if str(root) not in sys.path: sys.path.insert(0, str(root))
    from gateway_client import HaikeClient
    return HaikeClient


class Studio:
    def __init__(self, projects_root):
        self.projects_root = Path(projects_root)
        self.private = self.projects_root.parent / ".backlot"
        self.db_path = self.private / "studio.sqlite3"
        self.config_path = self.private / "haike-api/client-config.json"
        self.private.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS studio_drafts(id TEXT PRIMARY KEY, revision INTEGER, data TEXT);
            CREATE TABLE IF NOT EXISTS studio_assets(id TEXT PRIMARY KEY, draft_id TEXT, name TEXT, kind TEXT, path TEXT);
            CREATE TABLE IF NOT EXISTS studio_calendar(id TEXT PRIMARY KEY, revision INTEGER, data TEXT);
            CREATE TABLE IF NOT EXISTS studio_quotes(id TEXT PRIMARY KEY, data TEXT);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=20); db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE"); yield db; db.commit()
        except Exception:
            db.rollback(); raise
        finally: db.close()

    def configuration(self):
        try: return json.loads(self.config_path.read_text(encoding="utf-8"))
        except FileNotFoundError: return {}

    def settings(self):
        c = self.configuration(); key = c.get("api_key", "")
        return {"base_url": c.get("base_url", "https://8.138.207.71:17894/v2"), "configured": bool(key),
                "key_hint": "••••" + key[-4:] if key else "", "checked_at": c.get("checked_at")}

    def client(self, config=None):
        c = config or self.configuration()
        if not c.get("api_key"): raise WorkError("请先在API设置填写统一海客Key")
        return sdk_type()(c["base_url"], c["api_key"], self.private / "haike-api/intents")

    def connect(self, data):
        previous = self.configuration()
        c = {"base_url": str(data.get("base_url", "")).strip().rstrip("/"),
             "api_key": str(data.get("api_key") or previous.get("api_key", "")).strip()}
        if not 8 <= len(c["api_key"]) <= 512 or any(ch.isspace() for ch in c["api_key"]):
            raise WorkError("请输入有效的海客API Key")
        if c["base_url"] != previous.get("base_url") and not data.get("api_key"):
            raise WorkError("更换网关地址时请重新填写Key，不向新地址发送已有Key")
        try:
            summary = self.client(c).request("/account/summary")
            capabilities = self.client(c).request("/capabilities")
        except Exception:
            raise WorkError("连接失败：请核对网关地址、Key和服务状态；原配置保持不变") from None
        c["checked_at"] = timestamp(); atomic_private(self.config_path, c)
        from backlot.studio_asr import status
        return {"settings": self.settings(), "summary": summary, "capabilities": capabilities, "local_asr": status(self)}

    def template(self, template_id):
        item = next((t for t in TEMPLATES if t["id"] == template_id), None)
        if not item: raise WorkError("所选模板不存在，请刷新模板目录")
        return item

    def save_draft(self, data):
        template = self.template(data.get("template_id"))
        title = str(data.get("title") or "未命名视频").strip()
        if not 1 <= len(title) <= 120: raise WorkError("标题需要1至120个字")
        text = str(data.get("text") or "")
        if len(text) > 10000: raise WorkError("文案最多10,000字")
        layout = data.get("layout") or template["layout"]
        if not isinstance(layout, dict) or set(layout) - {"title_size", "detail_size", "accent", "background"}:
            raise WorkError("模板排版参数不支持")
        for k in ("title_size", "detail_size"):
            if k in layout and (type(layout[k]) is not int or not 32 <= layout[k] <= 88): raise WorkError("字号需要32至88")
        for k in ("accent", "background"):
            if k in layout and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(layout[k])): raise WorkError("颜色格式无效")
        draft_id = data.get("id") or "studio-" + uuid4().hex[:16]
        if not re.fullmatch(r"studio-[a-f0-9]{16}", draft_id): raise WorkError("制作项目编号无效")
        with self.db() as db:
            row = db.execute("SELECT * FROM studio_drafts WHERE id=?", (draft_id,)).fetchone()
            if row and data.get("revision") != row["revision"]: raise WorkError("项目已更新，请刷新后继续", "conflict")
            revision = row["revision"] + 1 if row else 1
            value = {"id": draft_id, "revision": revision, "kind": template["kind"], "template_id": template["id"],
                     "template_version": template["version"], "title": title, "text": text, "layout": layout,
                     "input": data.get("input") or {}, "updated_at": timestamp(), "status": "draft"}
            if not isinstance(value["input"], dict): raise WorkError("制作内容格式无效")
            allowed = {"headlines", "details", "conclusion", "materials", "bgm"} if template["kind"] == "graphic" else {"soundMode", "voiceId", "rate", "subtitles", "audio", "portrait", "ai", "motion"}
            if template["id"] == "avatar-motion-adu-v1":
                allowed = {"source", "motionLayout", "style", "segments", "music", "captions", "face", "subtitleBottom", "texture", "selectionMode"}
            if set(value["input"]) - allowed: raise WorkError("制作内容包含不支持的字段；API Key只能保存在API设置")
            if len(json.dumps(value)) > (300000 if template["id"] == "avatar-motion-adu-v1" else 60000): raise WorkError("制作内容过大")
            db.execute("INSERT INTO studio_drafts VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,data=excluded.data",
                       (draft_id, revision, json.dumps(value, ensure_ascii=False)))
        return value

    def drafts(self):
        with self.db() as db: return [json.loads(r[0]) for r in db.execute("SELECT data FROM studio_drafts ORDER BY rowid DESC")]

    def draft(self, draft_id):
        with self.db() as db: row = db.execute("SELECT data FROM studio_drafts WHERE id=?", (draft_id,)).fetchone()
        if not row: raise WorkError("制作项目不存在", "missing")
        return json.loads(row[0])

    def save_asset(self, draft_id, filename, kind, content):
        self.draft(draft_id)
        if kind not in {"image", "audio", "video"}: raise WorkError("素材类型无效")
        suffix = Path(filename).suffix.lower()
        permitted = {"image": {".png", ".jpg", ".jpeg"}, "audio": {".wav", ".mp3", ".m4a", ".ogg"}, "video": {".mp4", ".mov"}}
        if suffix not in permitted[kind] or not content or len(content) > 80 * 1024 * 1024: raise WorkError("文件格式不支持或超过80MB")
        asset_id = uuid4().hex
        folder = self.projects_root / draft_id / "assets/studio"; folder.mkdir(parents=True, exist_ok=True)
        path = folder / (asset_id + suffix); path.write_bytes(content)
        try:
            if kind == "image":
                from PIL import Image
                with Image.open(path) as img:
                    if min(img.size) < 256: raise WorkError("图片宽高至少256像素")
                    img.verify()
            else:
                from backlot.studio_render import media_probe
                info = media_probe(path)
                if info["duration"] <= 0 or info["duration"] > 600: raise WorkError("素材时长需要在10分钟内")
                if kind == "video" and not info.get("video"): raise WorkError("文件没有视频画面")
                if kind == "audio" and not info.get("audio"): raise WorkError("文件没有音轨")
        except Exception:
            path.unlink(missing_ok=True)
            raise WorkError("素材无法读取，请检查格式、尺寸和时长") from None
        with self.db() as db:
            db.execute("INSERT INTO studio_assets VALUES(?,?,?,?,?)", (asset_id, draft_id, Path(filename).name[:160], kind, str(path)))
        return {"id": asset_id, "name": Path(filename).name[:160], "kind": kind, "url": f"/api/studio/assets/{asset_id}"}

    def asset(self, asset_id, draft_id=None):
        with self.db() as db: row = db.execute("SELECT * FROM studio_assets WHERE id=?", (asset_id,)).fetchone()
        if not row or (draft_id and row["draft_id"] != draft_id): raise WorkError("素材不存在或不属于此项目", "missing")
        path = Path(row["path"])
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(self.projects_root.resolve()): raise WorkError("素材路径不可用")
        return path

    def calendar(self):
        with self.db() as db: return [json.loads(r[0]) for r in db.execute("SELECT data FROM studio_calendar ORDER BY rowid DESC")]

    def calendar_get(self, plan_id):
        with self.db() as db: row = db.execute("SELECT data FROM studio_calendar WHERE id=?", (plan_id,)).fetchone()
        if not row: raise WorkError("排期不存在", "missing")
        return json.loads(row[0])

    def save_calendar(self, data, catalog=None, transaction=None):
        catalog = catalog or WorkCatalog(self.projects_root)
        work = catalog.get(str(data.get("work_id") or ""))
        if not work.get("final_version_id"): raise WorkError("请先在作品中确认最终成片，再设置排期")
        try:
            when = datetime.fromisoformat(str(data.get("scheduled_at") or "").replace("Z", "+00:00"))
            if when.tzinfo is None or when <= datetime.now(timezone.utc): raise ValueError()
        except ValueError: raise WorkError("发布时间必须带时区且位于未来") from None
        accounts = data.get("accounts")
        if not isinstance(accounts, list) or not accounts: raise WorkError("请至少选择一个发布账号")
        seen = set()
        for a in accounts:
            if not isinstance(a, dict) or a.get("platform") not in {"douyin", "kuaishou", "shipinhao"} or type(a.get("account_id")) is not int or a["account_id"] < 1:
                raise WorkError("发布账号格式无效")
            identity = (a["platform"], a["account_id"])
            if identity in seen: raise WorkError("发布账号重复")
            seen.add(identity)
        plan_id = data.get("id") or "calendar-" + uuid4().hex
        with (nullcontext(transaction) if transaction else self.db()) as db:
            row = db.execute("SELECT * FROM studio_calendar WHERE id=?", (plan_id,)).fetchone()
            if row:
                old = json.loads(row["data"])
                if data.get("revision") != row["revision"]: raise WorkError("排期已更新，请刷新", "conflict")
                if old["status"] != "draft": raise WorkError("已提交的排期请先取消，再创建新计划", "conflict")
            value = {"id": plan_id, "revision": row["revision"] + 1 if row else 1, "work_id": work["work_id"],
                     "title": work["title"], "version_id": work["final_version_id"], "scheduled_at": when.astimezone(timezone.utc).isoformat(),
                     "timezone": "Asia/Shanghai", "accounts": [{"platform": a["platform"], "account_id": a["account_id"]} for a in accounts],
                     "status": "draft", "updated_at": timestamp()}
            for r in db.execute("SELECT data FROM studio_calendar WHERE id!=?", (plan_id,)):
                other = json.loads(r[0])
                if other["status"] not in {"canceled", "failed"} and other["work_id"] == value["work_id"] and other["version_id"] == value["version_id"]:
                    if any(a in other["accounts"] for a in value["accounts"]): raise WorkError("同一成片和账号已有排期，请编辑原计划", "conflict")
            db.execute("INSERT INTO studio_calendar VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,data=excluded.data",
                       (plan_id, value["revision"], json.dumps(value, ensure_ascii=False)))
        return value

    def batch_calendar(self, data, catalog=None):
        ids = data.get("work_ids")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 60 or len(set(ids)) != len(ids): raise WorkError("请选择1至60个不同成片")
        interval = data.get("interval_days")
        if interval not in {1, 7}: raise WorkError("连续作品只支持每天或每周一条")
        try: start = datetime.fromisoformat(str(data.get("scheduled_at")).replace("Z", "+00:00"))
        except ValueError: raise WorkError("请填写有效的起始发布时间") from None
        # All-or-nothing: a duplicate/invalid later work never leaves earlier plans silently saved.
        with self.db() as db:
            return [self.save_calendar({"work_id": work_id, "accounts": data.get("accounts"), "scheduled_at": (start + timedelta(days=i*interval)).isoformat()}, catalog, db) for i, work_id in enumerate(ids)]

    def update_calendar(self, plan_id, patch):
        with self.db() as db:
            row = db.execute("SELECT * FROM studio_calendar WHERE id=?", (plan_id,)).fetchone()
            if not row: raise WorkError("排期不存在", "missing")
            value = json.loads(row["data"]); value.update(patch); value["revision"] += 1; value["updated_at"] = timestamp()
            db.execute("UPDATE studio_calendar SET revision=?,data=? WHERE id=?", (value["revision"], json.dumps(value, ensure_ascii=False), plan_id))
        return value

    def sync_calendar(self, catalog=None):
        from backlot import work_publish
        catalog = catalog or WorkCatalog(self.projects_root)
        # Keep a status query from overwriting an activation or partial cancellation receipt.
        with _CALENDAR_LOCK:
            for p in self.calendar():
                if p["status"] not in {"scheduled", "running", "uncertain"} or not p.get("publish_plan_id"): continue
                w = work_publish.sync(catalog, p["work_id"])
                attempts = [a for a in w["attempts"] if a["plan_id"] == p["publish_plan_id"]]
                states = {a["status"] for a in attempts}
                if not states: continue
                state = ("done" if states == {"done"} else "canceled" if states == {"canceled"}
                         else "uncertain" if "uncertain" in states else "running" if states & {"running", "publishing"}
                         else "failed" if states & {"failed", "canceled"} else "scheduled")
                self.update_calendar(p["id"], {"status": state, "attempts": attempts})
            return self.calendar()

    def activate_calendar(self, plan_id, confirmed, catalog=None, gateway=None):
        # Local HTTP handlers run on multiple threads; serialize activation/cancel receipts.
        with _CALENDAR_LOCK:
            return self._activate_calendar(plan_id, confirmed, catalog, gateway)

    def _activate_calendar(self, plan_id, confirmed, catalog=None, gateway=None):
        from backlot import work_publish
        if confirmed is not True: raise WorkError("请确认具体成片、账号和时间后启用自动发布")
        plan = self.calendar_get(plan_id)
        if plan["status"] not in {"draft", "submitting", "uncertain"}: raise WorkError("该计划已经提交或取消")
        catalog = catalog or WorkCatalog(self.projects_root)
        if plan["status"] == "draft":
            work = catalog.get(plan["work_id"])
            if work["final_version_id"] != plan["version_id"]: raise WorkError("最终成片已改变，请重新保存排期")
            when = datetime.fromisoformat(plan["scheduled_at"])
            if when <= datetime.now(timezone.utc): raise WorkError("发布时间已过，请重新排期")
            if any(a["version_id"] == plan["version_id"] and a["status"] in {"canceled", "failed"} for a in work["attempts"]) and work["materials"]:
                work = catalog.change(work["work_id"], "materials", {"revision": work["revision"], "data": work["materials"][-1]["data"]}, actor="studio-calendar-revision")
            work = catalog.change(work["work_id"], "targets", {"revision": work["revision"], "targets": [dict(a, scheduled_at=plan["scheduled_at"]) for a in plan["accounts"]], "reason": "用户在发布日历确认排期"})
            prepared = work_publish.prepare(catalog, work["work_id"], work["revision"])
            plan = self.update_calendar(plan_id, {"status": "submitting", "publish_plan_id": prepared["plan_id"]})
        try:
            work = work_publish.submit(catalog, plan["publish_plan_id"], True, gateway=gateway, actor="studio-calendar")
        except WorkError:
            self.update_calendar(plan_id, {"status": "uncertain", "message": "提交尚未确认，恢复原计划查询，不要重复创建"})
            raise
        attempts = [a for a in work["attempts"] if a["plan_id"] == plan["publish_plan_id"]]
        uncertain = any(not a.get("task_id") for a in attempts)
        return self.update_calendar(plan_id, {"status": "uncertain" if uncertain else "scheduled", "task_ids": [a["task_id"] for a in attempts if a.get("task_id")], "message": "部分提交待核对，请恢复原提交" if uncertain else "排期已交给发布服务，等待执行"})

    def cancel_calendar(self, plan_id, gateway=None):
        with _CALENDAR_LOCK:
            return self._cancel_calendar(plan_id, gateway)

    def _cancel_calendar(self, plan_id, gateway=None):
        from backlot.work_publish import CreatorGateway
        plan = self.calendar_get(plan_id)
        if plan["status"] == "canceled": return plan
        if plan["status"] in {"submitting", "uncertain"}: raise WorkError("提交结果未知，请先恢复原计划取得任务编号", "conflict")
        gateway = gateway or CreatorGateway()
        for task_id in plan.get("task_ids", []):
            receipt = gateway.call(f"/api/publish/{task_id}/cancel", data={}, method="POST")
            if receipt.get("status") != "canceled": raise WorkError("发布服务尚未确认取消，请同步原任务状态", "unavailable")
            canceled = list(dict.fromkeys([*plan.get("canceled_task_ids", []), task_id]))
            plan = self.update_calendar(plan_id, {"canceled_task_ids": canceled, "status": "canceling", "message": "正在取消各账号排期，未确认的账号可继续重试取消"})
        if plan.get("task_ids"):
            catalog = WorkCatalog(self.projects_root)
            with catalog.transaction() as db:
                work = catalog._get(db, plan["work_id"])
                for a in work["attempts"]:
                    if a.get("plan_id") == plan.get("publish_plan_id") and a.get("task_id") in plan["task_ids"]: a["status"] = "canceled"
                catalog._save(db, work, "studio-calendar", "publish-cancel-receipt")
        return self.update_calendar(plan_id, {"status": "canceled", "message": "计划已取消"})
