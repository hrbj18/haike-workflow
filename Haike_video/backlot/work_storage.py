"""Preview-bound archival deletion; never delete entire projects or shared libraries."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path

from backlot.work_catalog import WorkError, now, read_json, regular_path, sha


def eligible(work):
    if not work["final_version_id"] or not work["targets"]:
        return False
    if any(a["status"] not in {"done", "failed", "canceled"} for a in work["attempts"]):
        return False
    for target in work["targets"]:
        matches = [a for a in work["attempts"] if a["platform"] == target["platform"]
                   and a["account_id"] == target["account_id"] and a["version_id"] == work["final_version_id"]]
        if not matches or matches[-1]["status"] != "done" or matches[-1].get("acceptance_status") != "verified":
            return False
    return True


def active(catalog, db, project_id, own_token=None):
    lock = db.execute("SELECT token FROM work_activity WHERE project=?", (project_id,)).fetchone()
    if lock and lock[0] != own_token:
        return True
    queue = catalog.projects_root.parent / ".backlot" / "production-queue.sqlite3"
    if queue.exists():
        try:
            with sqlite3.connect(queue.resolve().as_uri() + "?mode=ro", uri=True) as source:
                if source.execute("SELECT 1 FROM production_jobs WHERE project_id=? AND status IN "
                                  "('queued','running','paused','ambiguous','awaiting_human') LIMIT 1", (project_id,)).fetchone():
                    return True
        except sqlite3.Error as exc:
            raise WorkError("生产任务状态无法核对，暂不清理") from exc
    wb = read_json(catalog.project(project_id) / "artifacts/workbench.json")
    def running(value):
        if isinstance(value, dict):
            return value.get("status") in {"queued", "running", "generating", "rendering", "submitted", "downloading"} or any(running(v) for v in value.values())
        return isinstance(value, list) and any(running(v) for v in value)
    return running(wb.get("automation", {}))


def fingerprint(path):
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "inode": stat.st_ino, "device": stat.st_dev, "nlink": stat.st_nlink, "sha256": sha(path)}


def _foreign_paths(catalog, selected):
    result = set()
    library = Path(os.environ.get("OPENMONTAGE_MATERIAL_LIBRARY_DIR") or
                   catalog.projects_root.parent / ".backlot/material-library") / "library.sqlite3"
    if library.exists():
        try:
            with sqlite3.connect(library.resolve().as_uri() + "?mode=ro", uri=True) as db:
                result.update(os.path.normcase(os.path.abspath(r[0])) for r in db.execute("SELECT path FROM locations"))
        except sqlite3.Error as exc:
            raise WorkError("共享素材库引用无法核对，暂不清理") from exc
    def walk(value, project):
        if isinstance(value, dict):
            for v in value.values():
                walk(v, project)
        elif isinstance(value, list):
            for v in value:
                walk(v, project)
        elif isinstance(value, str) and value and ("/" in value or "\\" in value):
            path = Path(value)
            if not path.is_absolute():
                path = project / path
            result.add(os.path.normcase(os.path.abspath(path)))
    for project in catalog.projects_root.iterdir():
        if not project.is_dir() or project.name in selected or project.is_symlink():
            continue
        for name in ("scene_plan.json", "artifacts/workbench.json", "artifacts/asset_manifest.json"):
            walk(read_json(project / name), project)
    return result


def _inventory(catalog, work, all_works, foreign):
    root = catalog.project(work["project_id"])
    kept_versions = {work["final_version_id"]} | {a["version_id"] for a in work["attempts"]
                    if a["status"] not in {"failed", "canceled"}}
    protected = set()
    for v in work["versions"]:
        if v["version_id"] in kept_versions:
            available = []
            for raw in v["paths"]:
                try:
                    p = regular_path(raw, root)
                    if sha(p) == v["sha256"]:
                        available.append(p)
                except WorkError:
                    pass
            if not available:
                raise WorkError("受保护成片缺失或内容变化，不能清理")
            # A stable shortest project-local location survives, not every copy.
            protected.add(str(min(available, key=lambda p: (len(p.parts), len(str(p))))))
    for m in work["materials"]:
        data = m["data"]
        for key in ("cover_path", "cover_proof_path"):
            if data.get(key):
                protected.add(data[key])
        if data.get("cover_proof_path"):
            proof = read_json(data["cover_proof_path"])
            if proof.get("source_image_path"):
                protected.add(proof["source_image_path"])
    # Declared evidence paths remain available for audits and handoff.
    def evidence(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if k.endswith("path") and isinstance(v, str):
                    protected.add(v)
                else:
                    evidence(v)
        elif isinstance(value, list):
            for v in value:
                evidence(v)
        elif isinstance(value, str) and Path(value).is_absolute():
            protected.add(value)
    evidence(work["handoff"])
    for attempt in work["attempts"]:
        evidence(attempt.get("acceptance", {}))
    other = set()
    for w in all_works:
        if w["work_id"] != work["work_id"]:
            other.update(a["path"] for a in w["assets"])
            other.update(p for v in w["versions"] for p in v["paths"])
            for material in w["materials"]:
                other.update(material["data"][k] for k in ("cover_path", "cover_proof_path") if material["data"].get(k))
    protected = {os.path.normcase(os.path.abspath(p)) for p in protected}
    other = {os.path.normcase(os.path.abspath(p)) for p in other} | foreign
    entries = {a["path"]: a for a in work["assets"]}
    for v in work["versions"]:
        for p in v["paths"]:
            entries.setdefault(p, {"path": p, "root": str(root), "sha256": v["sha256"],
                                   "ownership": "exclusive", "kind": "render", "evidence": v["events"]})
    # Unknown local files are visible, but absence of a reference never proves ownership.
    registered = {os.path.normcase(os.path.abspath(p)) for p in entries}
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()
                   and not getattr((Path(folder) / d).lstat(), "st_file_attributes", 0) & 0x400]
        for name in files:
            p = Path(folder) / name
            key = os.path.normcase(os.path.abspath(p))
            # Another work's ledger is not an unknown file belonging to this work.
            # This also avoids a second selected work's inventory overriding its owner's delete row.
            if key not in registered and key not in other:
                entries[str(p)] = {"path": str(p), "root": str(root), "ownership": "unknown",
                                   "kind": "unregistered", "sha256": None}
    output = []
    for row in entries.values():
        raw = row["path"]; reason = ""
        if os.path.normcase(os.path.abspath(raw)) in protected or row["kind"] in {"evidence", "cover", "record"}:
            reason = "成片或必要证据保留"
        elif row["ownership"] != "exclusive":
            reason = "公共/共享素材或归属未确认"
        elif os.path.normcase(os.path.abspath(raw)) in other:
            reason = "其他作品或项目仍使用"
        try:
            path = regular_path(raw, row["root"])
            stamp = fingerprint(path) if row.get("sha256") else {"size": path.stat().st_size}
            if row.get("sha256") and stamp["sha256"] != row["sha256"]:
                reason = "文件内容已改变，需重新登记"
        except WorkError as exc:
            stamp = {}; reason = str(exc)
        output.append({"work_id": work["work_id"], "path": raw, "root": row["root"],
                       "fingerprint": stamp, "delete": not bool(reason), "reason": reason})
    return output


def plan(catalog, work_ids):
    if not work_ids or len(work_ids) != len(set(work_ids)):
        raise WorkError("请选择不重复的作品")
    with catalog.transaction() as db:
        works = [catalog._get(db, wid) for wid in work_ids]
        for w in works:
            if not eligible(w) or active(catalog, db, w["project_id"]):
                raise WorkError(f"{w['title']}：目标尚未全部核验，或存在活动任务")
        all_works = [json.loads(r[0]) for r in db.execute("SELECT data FROM works")]
        foreign = _foreign_paths(catalog, {w["project_id"] for w in works})
        rows = [r for w in works for r in _inventory(catalog, w, all_works, foreign)]
        unique = {}
        for r in rows:
            key = os.path.normcase(os.path.abspath(r["path"]))
            if key not in unique or not r["delete"]:
                unique[key] = r
        rows = list(unique.values())
    data = {"revisions": {w["work_id"]: w["revision"] for w in works}, "entries": rows,
            "estimated_bytes": sum(r["fingerprint"].get("size", 0) for r in rows
                                   if r["delete"] and r["fingerprint"].get("nlink", 1) == 1),
            "state": "planned", "permanent_delete": True}
    from hashlib import sha256
    data["digest"] = sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return catalog.put_plan("cleanup", data)


def report(catalog, work_id):
    work = catalog.get(work_id)
    with catalog.transaction() as db:
        all_works = [json.loads(r[0]) for r in db.execute("SELECT data FROM works")]
    rows = _inventory(catalog, work, all_works, _foreign_paths(catalog, {work["project_id"]}))
    return {"entries": rows, "registered_bytes": sum(r["fingerprint"].get("size", 0) for r in rows),
            "eligible": eligible(work), "scope": "已登记专用文件；未登记文件不猜测归属"}


def execute(catalog, plan_id, digest, confirmed, actor="local-agent"):
    if confirmed is not True:
        raise WorkError("需要确认这份永久删除计划")
    with catalog.transaction() as db:
        row = db.execute("SELECT data FROM work_plans WHERE id=? AND kind='cleanup'", (plan_id,)).fetchone()
        if not row:
            raise WorkError("清理计划不存在")
        data = json.loads(row[0])
        if data["digest"] != digest:
            raise WorkError("清理计划摘要不符", "conflict")
        if data["state"] == "completed":
            return data
        if data["state"] == "canceled":
            raise WorkError("清理计划已结束，需重新预览")
        works = [catalog._get(db, wid) for wid in data["revisions"]]
        for w in works:
            catalog.check_revision(w, data["revisions"][w["work_id"]])
            if not eligible(w) or active(catalog, db, w["project_id"], plan_id):
                raise WorkError("清理条件已改变，请重新预览", "conflict")
        all_works = [json.loads(r[0]) for r in db.execute("SELECT data FROM works")]
        foreign = _foreign_paths(catalog, {w["project_id"] for w in works})
        current = {r["path"]: r for w in works for r in _inventory(catalog, w, all_works, foreign)}
        data.setdefault("results", [])
        for result in data["results"]:
            if result["status"] == "deleting" and not Path(result["path"]).exists():
                result.update(status="deleted", bytes=0, reason="恢复时文件已不存在；不推断释放空间")
        finished = {r["path"] for r in data["results"] if r["status"] == "deleted"}
        # Validate all candidates before deleting the first byte.
        for item in data["entries"]:
            if item["delete"] and item["path"] not in finished:
                check = current.get(item["path"])
                if not check or not check["delete"] or check["fingerprint"] != item["fingerprint"]:
                    raise WorkError("文件或引用已变化，请重新生成清理计划", "conflict")
        for w in works:
            db.execute("INSERT INTO work_activity VALUES(?,?,?) ON CONFLICT(project) DO UPDATE "
                       "SET token=excluded.token,at=excluded.at", (w["project_id"], plan_id, now()))
        data.setdefault("disk_free_before", {str(catalog.project(w["project_id"]).anchor):
                        shutil.disk_usage(catalog.project(w["project_id"])).free for w in works})
        for item in data["entries"]:
            if not item["delete"] or item["path"] in finished:
                continue
            data["results"] = [r for r in data["results"] if r["path"] != item["path"]]
            data["results"].append({"path": item["path"], "status": "deleting"})
            db.execute("UPDATE work_plans SET data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), plan_id))
            db.commit(); db.execute("BEGIN IMMEDIATE")
            try:
                if any(active(catalog, db, w["project_id"], plan_id) for w in works):
                    raise WorkError("出现新的生产任务，本次文件删除已停止")
                other_refs = _foreign_paths(catalog, {w["project_id"] for w in works})
                def referenced(value):
                    if isinstance(value, str):
                        return Path(value).is_absolute() and os.path.normcase(os.path.abspath(value)) == os.path.normcase(item["path"])
                    if isinstance(value, dict):
                        return any(referenced(v) for v in value.values())
                    return isinstance(value, list) and any(referenced(v) for v in value)
                for record in db.execute("SELECT id,data FROM works"):
                    if record[0] != item["work_id"] and referenced(json.loads(record[1])):
                        other_refs.add(os.path.normcase(item["path"]))
                if os.path.normcase(item["path"]) in other_refs:
                    raise WorkError("执行时新增其他作品或共享素材引用，保留此文件")
                path = regular_path(item["path"], item["root"])
                if fingerprint(path) != item["fingerprint"]:
                    raise WorkError("执行时文件已变化，请核对原清理计划")
                path.unlink()
                data["results"][-1].update(status="deleted",
                    bytes=item["fingerprint"]["size"] if item["fingerprint"]["nlink"] == 1 else 0)
            except (OSError, WorkError) as exc:
                data["results"][-1].update(status="failed", reason=str(exc))
            # Persist per file, including failures; commit before proceeding.
            db.execute("UPDATE work_plans SET data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), plan_id))
            db.commit(); db.execute("BEGIN IMMEDIATE")
        deleted = {r["path"] for r in data["results"] if r["status"] == "deleted"}
        complete = all(not r["delete"] or r["path"] in deleted for r in data["entries"])
        data.update(state="completed" if complete else "partial", finished_at=now(),
                    deleted_bytes=sum(r.get("bytes", 0) for r in data["results"] if r["status"] == "deleted"))
        data["disk_free_after"] = {drive: shutil.disk_usage(drive).free for drive in data["disk_free_before"]}
        data["observed_free_change"] = {drive: n - data["disk_free_before"][drive] for drive, n in data["disk_free_after"].items()}
        if complete:
            for w in works:
                w["archive"] = "archived"
                for a in w["assets"]:
                    if a["path"] in deleted:
                        a["availability"] = "cleaned"
                for v in w["versions"]:
                    if all(p in deleted or not Path(p).exists() for p in v["paths"]):
                        v["availability"] = "cleaned"
                catalog._save(db, w, actor, "archive-cleanup")
                db.execute("DELETE FROM work_activity WHERE project=? AND token=?", (w["project_id"], plan_id))
        db.execute("UPDATE work_plans SET data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), plan_id))
    return data


def cancel(catalog, plan_id):
    """End a partial plan without undoing completed deletions or claiming archive success."""
    with catalog.transaction() as db:
        row = db.execute("SELECT data FROM work_plans WHERE id=? AND kind='cleanup'", (plan_id,)).fetchone()
        if not row:
            raise WorkError("清理计划不存在")
        data = json.loads(row[0])
        if data["state"] == "completed":
            return data
        data.update(state="canceled", finished_at=now())
        db.execute("DELETE FROM work_activity WHERE token=?", (plan_id,))
        db.execute("UPDATE work_plans SET data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), plan_id))
        return data
