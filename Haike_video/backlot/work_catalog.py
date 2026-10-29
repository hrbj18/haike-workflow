"""Version-bound completed works shared by the web UI and local agents.

SQLite is authoritative; exports are read-only handoff snapshots. Mutations
use revision checks and one transaction, including activity/cleanup exclusion.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PLATFORMS = ("douyin", "kuaishou", "shipinhao")


class WorkError(ValueError):
    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.code = code


def now():
    return datetime.now(timezone.utc).isoformat()


def recorded_date(value):
    try:
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else None
    except (ValueError, AttributeError):
        return None


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise WorkError(f"记录无法读取：{Path(path).name}") from exc


def regular_path(raw, root):
    """Reject reparse points in every component, before resolving containment."""
    path = Path(os.path.abspath(raw))
    root = Path(root).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise WorkError("文件不在允许的托管目录内") from exc
    for part in [path, *path.parents]:
        if part == root.parent:
            break
        if part.exists() or part.is_symlink():
            st = part.lstat()
            if part.is_symlink() or getattr(st, "st_file_attributes", 0) & 0x400:
                raise WorkError("符号链接或目录联接不能作为托管文件")
    if not path.is_file() or path.stat().st_size == 0:
        raise WorkError("文件不存在或为空")
    return path


def probe(path):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    _, ffprobe = resolve_ffmpeg_pair()
    result = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format",
                             "-of", "json", str(path)], capture_output=True, timeout=30)
    try:
        data = json.loads(result.stdout)
        video = next(s for s in data["streams"] if s["codec_type"] == "video")
        duration = float(data["format"]["duration"])
        if result.returncode or duration <= 0:
            raise ValueError()
        return {"duration": duration, "width": video["width"], "height": video["height"],
                "has_audio": any(s["codec_type"] == "audio" for s in data["streams"])}
    except (ValueError, KeyError, StopIteration) as exc:
        raise WorkError("成片无法解码为有效视频") from exc


class WorkCatalog:
    def __init__(self, projects_root, db_path=None):
        self.projects_root = Path(projects_root).resolve()
        self.db_path = Path(db_path or self.projects_root.parent / ".backlot" / "works.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS works(id TEXT PRIMARY KEY, project TEXT NOT NULL,
                  revision INTEGER NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS work_events(id INTEGER PRIMARY KEY, work_id TEXT,
                  actor TEXT NOT NULL, action TEXT NOT NULL, at TEXT NOT NULL, detail TEXT);
                CREATE TABLE IF NOT EXISTS work_plans(id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                  data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS work_activity(project TEXT PRIMARY KEY, token TEXT,
                  at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS works_project ON works(project);
            """)

    @contextmanager
    def transaction(self):
        try:
            db = sqlite3.connect(self.db_path, timeout=30)
        except sqlite3.Error as exc:
            raise WorkError("作品数据库无法打开，请核对路径及文件状态", "unavailable") from exc
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=30000")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except sqlite3.Error as exc:
            db.rollback()
            raise WorkError("作品数据库不可读取；保留原数据，检查备份及文件状态", "unavailable") from exc
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def project(self, project_id):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", project_id):
            raise WorkError("项目编号无效")
        path = self.projects_root / project_id
        if not path.is_dir() or path.is_symlink() or path.resolve().parent != self.projects_root:
            raise WorkError("项目不存在或目录越界")
        return path

    @staticmethod
    def _get(db, work_id):
        row = db.execute("SELECT data FROM works WHERE id=?", (work_id,)).fetchone()
        if row is None:
            raise WorkError("作品不存在", "missing")
        try:
            return json.loads(row[0])
        except ValueError as exc:
            raise WorkError("作品记录损坏；保留原记录待修复", "unavailable") from exc

    @staticmethod
    def _save(db, work, actor, action):
        work["revision"] += 1
        work["updated_at"] = now()
        db.execute("INSERT INTO works VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                   "revision=excluded.revision,data=excluded.data",
                   (work["work_id"], work["project_id"], work["revision"], json.dumps(work, ensure_ascii=False)))
        db.execute("INSERT INTO work_events(work_id,actor,action,at,detail) VALUES(?,?,?,?,?)",
                   (work["work_id"], actor, action, now(), str(work["revision"])))

    @staticmethod
    def check_revision(work, revision):
        if revision != work["revision"]:
            raise WorkError("记录已更新，请刷新后重新操作", "conflict")

    def get(self, work_id):
        with self.transaction() as db:
            return self._get(db, work_id)

    def list(self, query="", include_candidates=False):
        with self.transaction() as db:
            rows = [json.loads(r[0]) for r in db.execute("SELECT data FROM works")]
        return sorted([w for w in rows if (include_candidates or w["final_version_id"])
                       and query.casefold() in (w["title"] + w["project_id"]).casefold()],
                      key=lambda w: w.get("project_created_at") or w["created_at"], reverse=True)

    def register(self, project_id, path, *, work_key="main", mode="manual", event_id="",
                 quality_passed=False, title="", actor="producer", summary=""):
        project = self.project(project_id)
        meta = read_json(project / "project.json")
        if mode not in {"manual", "automatic"} or not work_key or len(work_key) > 100:
            raise WorkError("作品类别或任务模式无效")
        path = regular_path(path if Path(path).is_absolute() else project / path, project)
        media, content = probe(path), sha(path)
        media["bytes"] = path.stat().st_size
        identity = hashlib.sha256(f"{project_id}:{work_key}".encode()).hexdigest()[:24]
        work_id = "work-" + identity
        with self.transaction() as db:
            lock = db.execute("SELECT token FROM work_activity WHERE project=?", (project_id,)).fetchone()
            if lock and lock[0].startswith("cleanup-"):
                raise WorkError("归档清理执行中，不能登记新版本", "conflict")
            row = db.execute("SELECT data FROM works WHERE id=?", (work_id,)).fetchone()
            work = json.loads(row[0]) if row else {
                "work_id": work_id, "project_id": project_id, "work_key": work_key,
                "title": title or meta.get("title") or project_id,
                "mode": mode, "revision": 0, "created_at": now(), "final_version_id": None,
                "versions": [], "confirmations": [], "materials": [], "targets": [],
                "attempts": [], "assets": [], "handoff": {}, "archive": "complete"}
            if work["mode"] != mode:
                raise WorkError("既有作品的自动/人工模式不能悄悄变更")
            original = json.dumps(work, sort_keys=True)
            work.setdefault("project_created_at", recorded_date(meta.get("created_at")))
            version = next((v for v in work["versions"] if v["sha256"] == content), None)
            if version is None:
                version = {"version_id": "v-" + content[:24], "sha256": content,
                           "paths": [], "media": media, "created_at": now(), "events": [],
                           "summary": summary, "availability": "present"}
                work["versions"].append(version)
                if work["archive"] == "archived":
                    work["archive"] = "partial"
            if version["availability"] != "present":
                version["availability"] = "present"
                if work["archive"] == "archived":
                    work["archive"] = "partial"
            if str(path) not in version["paths"]:
                version["paths"].append(str(path))
            if event_id and event_id not in version["events"]:
                version["events"].append(event_id)
            if mode == "automatic" and quality_passed:
                self._confirm(work, version["version_id"], actor, "automatic", event_id)
            if not row or json.dumps(work, sort_keys=True) != original:
                self._save(db, work, actor, "register")
        return work

    @staticmethod
    def _confirm(work, version_id, actor, mode, evidence):
        v = next((v for v in work["versions"] if v["version_id"] == version_id), None)
        if v is None or not evidence:
            raise WorkError("请选择成片版本并记录确认依据")
        if not any(Path(p).is_file() and sha(p) == v["sha256"] for p in v["paths"]):
            raise WorkError("成片文件已缺失或变化")
        if work["final_version_id"] != version_id:
            work["confirmations"].append({"version_id": version_id, "sha256": v["sha256"],
                                          "actor": actor, "mode": mode, "evidence": evidence, "at": now()})
            work["final_version_id"] = version_id

    def change(self, work_id, action, payload, *, actor="local-agent"):
        with self.transaction() as db:
            work = self._get(db, work_id)
            activity = db.execute("SELECT token FROM work_activity WHERE project=?", (work["project_id"],)).fetchone()
            if activity and activity[0].startswith("cleanup-"):
                raise WorkError("归档清理执行中，暂不能修改作品", "conflict")
            self.check_revision(work, payload.get("revision"))
            if action == "confirm":
                previous = work["final_version_id"]
                self.media_path_from_work(work, payload["version_id"])
                self._confirm(work, payload["version_id"], actor, "manual", str(payload.get("evidence") or ""))
                if previous == payload["version_id"]:
                    return work
            elif action == "materials":
                if not work["final_version_id"]:
                    raise WorkError("先确认最终成片")
                data = payload.get("data") or {}
                allowed = {"title", "desc", "topics", "cover_path", "cover_origin", "cover_proof_path",
                           "source_rights_status", "platforms", "request_evidence"}
                data = {k: v for k, v in data.items() if k in allowed}
                if any(not isinstance(v, str) for k, v in data.items() if k != "platforms"):
                    raise WorkError("发布文案、路径和来源说明必须是文字")
                if not isinstance(data.get("platforms", {}), dict) or any(
                    p not in PLATFORMS or not isinstance(v, dict) or any(
                        k not in {"title", "desc", "topics"} or not isinstance(text, str) for k, text in v.items())
                    for p, v in data.get("platforms", {}).items()):
                    raise WorkError("平台文案覆盖格式无效")
                if work["mode"] == "manual" and not data.get("request_evidence"):
                    raise WorkError("指定任务的发布资料需要记录用户要求")
                for key in ("cover_path", "cover_proof_path"):
                    if data.get(key):
                        p = regular_path(data[key], self.project(work["project_id"]))
                        data[key + "_sha256"] = sha(p)
                work["materials"].append({"number": len(work["materials"]) + 1,
                    "version_id": work["final_version_id"], "data": data, "actor": actor, "at": now()})
            elif action == "targets":
                if any(a["status"] not in {"done", "failed", "canceled"} for a in work["attempts"]):
                    raise WorkError("尚有未结束提交，不能修改目标")
                targets = payload.get("targets", [])
                if not isinstance(targets, list) or any(not isinstance(t, dict) for t in targets):
                    raise WorkError("目标账号应是列表")
                seen = set()
                for t in targets:
                    key = f"{t.get('platform')}:{t.get('account_id')}"
                    if t.get("platform") not in PLATFORMS or type(t.get("account_id")) is not int or t["account_id"] < 1 or key in seen:
                        raise WorkError("目标平台/账号无效或重复")
                    if t.get("scheduled_at"):
                        dt = datetime.fromisoformat(t["scheduled_at"].replace("Z", "+00:00"))
                        if dt.tzinfo is None or dt <= datetime.now(timezone.utc):
                            raise WorkError("排期必须包含时区且位于未来")
                    seen.add(key)
                if work["attempts"] and not payload.get("reason"):
                    raise WorkError("变更已提交作品的目标需记录原因")
                work["targets"] = targets
            elif action == "handoff":
                work["handoff"] = payload.get("data") or {}
            elif action == "asset":
                project = self.project(work["project_id"])
                raw = Path(payload["path"])
                roots = [project, self.projects_root.parent / ".backlot"]
                path = None
                for root in roots:
                    try:
                        path = regular_path(raw, root)
                        break
                    except WorkError:
                        continue
                if path is None or not payload.get("ownership_evidence"):
                    raise WorkError("专用产物需要托管路径和归属证据；用户外部原片不自动托管")
                if path.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv", ".wav", ".mp3", ".m4a", ".ogg", ".png", ".jpg", ".jpeg", ".webp"}:
                    raise WorkError("只登记媒体产物；数据库、配置、模型和记录不能作为素材删除")
                row = {"path": str(path), "root": str(root.resolve()), "sha256": sha(path),
                       "size": path.stat().st_size, "kind": payload.get("kind", "intermediate"),
                       "ownership": payload.get("ownership", "unknown"),
                       "evidence": payload["ownership_evidence"]}
                if row["ownership"] not in {"exclusive", "shared", "unknown"}:
                    raise WorkError("文件归属无效")
                work["assets"] = [a for a in work["assets"] if a["path"] != str(path)] + [row]
                if work["archive"] == "archived":
                    work["archive"] = "partial"
            else:
                raise WorkError("不支持的作品操作")
            self._save(db, work, actor, action)
        return work

    def media_path(self, work_id, version_id=None):
        work = self.get(work_id)
        return self.media_path_from_work(work, version_id)

    def media_path_from_work(self, work, version_id=None):
        v = next((v for v in work["versions"] if v["version_id"] == (version_id or work["final_version_id"])), None)
        if v:
            for p in v["paths"]:
                try:
                    path = regular_path(p, self.project(work["project_id"]))
                    if sha(path) == v["sha256"]:
                        return path
                except WorkError:
                    pass
        raise WorkError("成片已缺失或内容变化", "missing")

    def handoff(self, work_id):
        work = self.get(work_id)
        from backlot.work_handoff import publication_summary
        return {"snapshot_at": now(), "read_only_snapshot": True, **work,
                "publish_handoff": publication_summary(self, work),
                "capability": "原素材已清理；完整工程修改需重新准备素材" if work["archive"] == "archived"
                else "按已确认参数及素材可用性继续修改",
                "command": f"python scripts/work_catalog_cli.py show {work_id}"}

    def activity(self, project_id, token, active):
        with self.transaction() as db:
            if active:
                previous = db.execute("SELECT token FROM work_activity WHERE project=?", (project_id,)).fetchone()
                if previous and previous[0] != token:
                    raise WorkError("项目正在归档或被其他执行器使用", "conflict")
                db.execute("INSERT INTO work_activity VALUES(?,?,?) ON CONFLICT(project) DO UPDATE "
                           "SET token=excluded.token,at=excluded.at", (project_id, token, now()))
            else:
                db.execute("DELETE FROM work_activity WHERE project=? AND token=?", (project_id, token))

    def put_plan(self, kind, data):
        identity = kind + "-" + uuid4().hex
        data = {**data, "plan_id": identity, "created_at": now()}
        with self.transaction() as db:
            db.execute("INSERT INTO work_plans VALUES(?,?,?)", (identity, kind, json.dumps(data, ensure_ascii=False)))
        return data
