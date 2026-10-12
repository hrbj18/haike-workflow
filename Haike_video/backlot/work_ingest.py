"""Producer completion events and conservative, evidence-based historical import."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path

from backlot.work_catalog import WorkCatalog, WorkError, read_json, regular_path, sha


def historical_tasks(catalog):
    """Read only the legacy publication table, without starting its engine."""
    path = Path(os.environ.get("HAIKE_CREATORHUB_DB", str(catalog.projects_root.parent.parent / "CreatorHub/data/creatorhub.db")))
    if not path.is_file():
        return [], "历史发布库未连接"
    fields = {"id", "platform", "account_id", "title", "status", "media_json", "video_sha256",
              "acceptance_status", "acceptance_evidence_json", "result_url", "package_revision",
              "desc", "topics", "cover_path", "cover_origin", "cover_proof_path", "source_rights_status"}
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as db:
            db.row_factory = sqlite3.Row
            columns = {r[1] for r in db.execute("PRAGMA table_info(publishtask)")}
            rows = [dict(r) for r in db.execute("SELECT " + ",".join(sorted(fields & columns)) + " FROM publishtask ORDER BY id")]
        records = []
        for row in rows:
            try:
                row["media_paths"] = json.loads(row.pop("media_json", "[]") or "[]")
                row["acceptance_evidence"] = json.loads(row.pop("acceptance_evidence_json", "{}") or "{}")
                records.append(row)
            except ValueError:
                continue
        return records, "历史发布库只读连接"
    except (sqlite3.Error, OSError):
        return [], "历史发布库不可读取，未推断发布结果"


def automatic_materials(catalog, work):
    if work["materials"] and work["materials"][-1]["version_id"] == work["final_version_id"]:
        return work
    project = catalog.project(work["project_id"])
    meta = read_json(project / "project.json")
    policy = meta.get("work_policy", {})
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ff, _ = resolve_ffmpeg_pair()
    cover = project / "artifacts/publishing" / (work["final_version_id"] + "-cover.jpg")
    cover.parent.mkdir(parents=True, exist_ok=True)
    video = catalog.media_path(work["work_id"])
    subprocess.run([ff, "-y", "-v", "error", "-ss", "0.5", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=720:960:force_original_aspect_ratio=increase,crop=720:960", str(cover)],
                   capture_output=True, timeout=30, check=True)
    title = str(policy.get("title") or meta.get("title") or work["title"])
    desc = str(policy.get("desc") or (meta.get("intake") or {}).get("brief") or title)
    data = {"title": title, "desc": desc, "topics": policy.get("topics", "科技,人工智能"),
            "cover_path": str(cover), "cover_origin": "approved_video_frame",
            "source_rights_status": policy.get("source_rights_status", "unknown"),
            "request_evidence": "automatic completion; local video-frame cover; no paid generation"}
    return catalog.change(work["work_id"], "materials", {"revision": work["revision"], "data": data}, actor="automatic-local")


def completed(catalog, project_id, output_path, event_id, *, quality_passed=True,
              mode=None, work_key="main"):
    project = catalog.project(project_id)
    meta = read_json(project / "project.json")
    policy = meta.get("work_policy", {})
    mode = mode or policy.get("mode") or ("automatic" if (meta.get("intake") or {}).get("created_from") == "daily_automation" else "manual")
    work = catalog.register(project_id, output_path, work_key=work_key, mode=mode,
                            event_id=event_id, quality_passed=quality_passed, actor="production-completion")
    if mode == "automatic" and quality_passed:
        try:
            work = automatic_materials(catalog, work)
        except Exception as exc:
            # A valid completed video survives metadata failures; keep the gap visible.
            work = catalog.change(work["work_id"], "handoff", {"revision": work["revision"],
                "data": {**work["handoff"], "next_step": "补齐自动发布资料", "materials_error": str(exc)[:300]}}, actor="producer")
    return work


def import_preview(catalog):
    candidates = []
    tasks, connection = historical_tasks(catalog)
    for project in sorted(catalog.projects_root.iterdir()):
        if not project.is_dir() or not (project / "project.json").exists():
            continue
        try:
            # Explicit per-project producer/approval records, never mtime guessing.
            evidence = []
            for path in (project / "artifacts").glob("*-handoff.json"):
                data = read_json(path)
                if data.get("user_approved") is True or data.get("status") == "approved_final":
                    media = data.get("selected_final_path") or data.get("final_preview")
                    if media:
                        evidence.append({"path": media, "evidence": str(path), "work_key": data.get("work_key", "main"), "mode": "manual"})
            report = read_json(project / "artifacts/render_report.json")
            meta = read_json(project / "project.json")
            mode = (meta.get("work_policy") or {}).get("mode") or (
                "automatic" if (meta.get("intake") or {}).get("created_from") == "daily_automation" else "manual")
            if report.get("status") == "completed" and report.get("editorial_status") == "verified" and report.get("quality_evidence"):
                qc = read_json(project / report["quality_evidence"])
                if isinstance(qc, list) and qc and all(x.get("pass") is True for x in qc):
                    evidence.append({"path": report["output_path"], "evidence": str(project / "artifacts/render_report.json"),
                                     "work_key": "main", "mode": mode or "manual",
                                     "needs_user_confirmation": mode != "automatic"})
            if evidence:
                candidates.extend({"project_id": project.name, "decision": "needs_confirmation" if e.get("needs_user_confirmation") else "supported", **e} for e in evidence)
            else:
                renders = sorted(set((project / "renders").glob("*.mp4")) |
                                 set((project / "renders/previews").glob("*.mp4")) |
                                 set(project.glob("*.mp4")))
                for media in renders:
                    candidates.append({"project_id": project.name, "work_key": "main", "path": str(media),
                                       "decision": "needs_confirmation", "mode": "manual", "evidence": "缺少确切成片确认依据"})
            known = {str(Path(e["path"]) if Path(e["path"]).is_absolute() else project / e["path"]) for e in evidence}
            published = []
            for task in tasks:
                if task.get("status") != "done":
                    continue
                for raw in task.get("media_paths", []):
                    try:
                        media = regular_path(raw, project)
                    except (WorkError, TypeError):
                        continue
                    content = sha(media)
                    bound = task.get("video_sha256", "").lower() == content
                    published.append((task, media, content, bound))
            unique = {content for _, _, content, bound in published if bound}
            for task, media, content, bound in published:
                candidates.append({"project_id": project.name, "path": str(media), "work_key": "main", "mode": mode or "manual",
                    "decision": "supported" if bound and (str(media) in known or not evidence and len(unique) == 1) else "needs_confirmation",
                    "evidence": f"CreatorHub task {task['id']}; " + ("成片哈希对应" if bound else "只有历史路径，哈希未绑定"),
                    "publication": task})
        except (WorkError, KeyError, OSError) as exc:
            candidates.append({"project_id": project.name, "decision": "needs_confirmation", "error": str(exc)})
    for row in candidates:
        if row.get("path"):
            path = Path(row["path"])
            if not path.is_absolute():
                path = catalog.project(row["project_id"]) / path
            row["path"] = str(path)
            try:
                row["sha256"] = sha(regular_path(path, catalog.project(row["project_id"])))
            except WorkError:
                row["sha256"] = None; row["decision"] = "needs_confirmation"
    groups = {}
    existing = {(w["project_id"], w["work_key"]): w for w in catalog.list(include_candidates=True)}
    for row in candidates:
        prior = existing.get((row["project_id"], row.get("work_key")))
        if prior and prior["final_version_id"] and row.get("sha256"):
            chosen = next(v for v in prior["versions"] if v["version_id"] == prior["final_version_id"])
            if row["sha256"] != chosen["sha256"]:
                row["decision"] = "needs_confirmation"
                row["evidence"] += "；已有最终版，导入不能自动替换"
        if row["decision"] == "supported":
            groups.setdefault((row["project_id"], row["work_key"]), set()).add(row.get("sha256"))
    for row in candidates:
        if len(groups.get((row["project_id"], row.get("work_key")), [])) > 1:
            row["decision"] = "needs_confirmation"
            row["evidence"] += "；同作品有多版完成依据，需要人工指定最终版"
    return catalog.put_plan("import", {"candidates": candidates, "publication_connection": connection})


def import_apply(catalog, plan_id, *, confirmed_indices=None, evidence=""):
    with catalog.transaction() as db:
        row = db.execute("SELECT data FROM work_plans WHERE id=? AND kind='import'", (plan_id,)).fetchone()
        if not row:
            raise WorkError("导入计划不存在")
        plan = json.loads(row[0])
    selected = set(confirmed_indices or [])
    if selected and (not evidence or any(not isinstance(i, int) or i < 0 or i >= len(plan["candidates"]) for i in selected)):
        raise WorkError("人工导入需要有效候选编号和用户确认依据")
    choices = {}
    for i in selected:
        item = plan["candidates"][i]; key = (item["project_id"], item.get("work_key"))
        if key in choices and choices[key] != item.get("sha256"):
            raise WorkError("同一作品只能勾选一份最终版；独立长短片需分别指定作品编号")
        choices[key] = item.get("sha256")
    imported, pending = [], []
    for index, item in enumerate(plan["candidates"]):
        if (item["decision"] != "supported" and index not in selected) or not item.get("sha256"):
            pending.append(item); continue
        if sha(item["path"]) != item["sha256"]:
            raise WorkError("导入预览后文件已变化", "conflict")
        prior = next((w for w in catalog.list(include_candidates=True)
                      if w["project_id"] == item["project_id"] and w["work_key"] == item["work_key"]), None)
        if prior and prior["final_version_id"] and index not in selected:
            chosen = next(v for v in prior["versions"] if v["version_id"] == prior["final_version_id"])
            if chosen["sha256"] != item["sha256"]:
                pending.append({**item, "decision": "needs_confirmation", "evidence": "已有最终版，需人工确认替换"}); continue
        work = catalog.register(item["project_id"], item["path"], work_key=item["work_key"],
                                mode=item["mode"], event_id=item["evidence"],
                                quality_passed=item["mode"] == "automatic", actor="historical-import")
        if item["mode"] == "manual":
            work = catalog.change(work["work_id"], "confirm", {"revision": work["revision"],
                "version_id": next(v["version_id"] for v in work["versions"] if v["sha256"] == item["sha256"]),
                "evidence": evidence if index in selected else item["evidence"]}, actor="historical-evidence")
        if item.get("publication"):
            task = item["publication"]
            with catalog.transaction() as db:
                work = catalog._get(db, work["work_id"])
                if not any(a["task_id"] == task["id"] for a in work["attempts"]):
                    work["attempts"].append({"task_id": task["id"], "plan_id": plan_id,
                        "key": f"historical:{task['id']}", "platform": task["platform"], "account_id": task["account_id"],
                        "version_id": next(v["version_id"] for v in work["versions"] if v["sha256"] == item["sha256"]),
                        "material_revision": task.get("package_revision", 0), "status": task["status"],
                        "acceptance_status": "not_checked", "at": plan["created_at"], "source": "historical-readonly",
                        "published_metadata": {k: task.get(k) for k in ("title", "desc", "topics", "cover_path", "cover_origin", "cover_proof_path", "source_rights_status")}})
                    catalog._save(db, work, "historical-import", "historical-receipt")
            class SnapshotGateway:
                def tasks(self): return [task]
            from backlot.work_publish import sync
            sync(catalog, work["work_id"], SnapshotGateway())
        imported.append(work["work_id"])
    return {"imported": list(dict.fromkeys(imported)), "needs_confirmation": pending}
