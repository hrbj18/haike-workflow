"""Read material evidence for the original Studio draft/version, never a new preset."""
from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import re
import sqlite3


_DRAFT = re.compile(r"studio-[a-f0-9]{16}\Z")
_ASSET = re.compile(r"[a-f0-9]{32}\Z")


def _read(path, sql, parameters):
    if not path.is_file():
        return None
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(sql, parameters).fetchone()
        return dict(row) if row is not None else None


def _safe_folder(root, project_id, render_id):
    path = root / project_id / "renders" / render_id
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink() or (parent.exists() and getattr(parent.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("material evidence path is linked")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("material evidence escapes project")
    return path


def task_material_result(projects_root, studio_path, queue_path, bound):
    """Return only safe presentation data; raw frozen requests never leave here.

    A generated task is pinned to its queue's frozen draft and render ID. An
    unsubmitted task may read its draft, but never guesses the newest render.
    """
    root = Path(projects_root)
    project_id = bound.get("draft_id") or bound.get("project_id")
    draft, render_id = None, None
    try:
        if bound.get("draft_id") and bound.get("project_id") and bound["draft_id"] != bound["project_id"]:
            raise ValueError("task project bindings differ")
        if bound.get("queue_job_id"):
            row = _read(Path(queue_path), "SELECT project_id,kind,parent_job_id,frozen_request FROM production_jobs WHERE job_id=?",
                        (bound["queue_job_id"],))
            if row is None or row.get("kind") != "studio_avatar":
                return None
            if project_id and project_id != row["project_id"]:
                raise ValueError("material project binding differs")
            project_id = row["project_id"]
            request = json.loads(row["frozen_request"])
            draft = request.get("draft")
            render_id = request.get("render_id")
            if not isinstance(draft, dict) or draft.get("id") != project_id or type(draft.get("revision")) is not int:
                raise ValueError("material draft binding differs")
            if render_id != "studio-" + str(draft["revision"]) or row["parent_job_id"] != render_id:
                raise ValueError("material version binding differs")
        elif isinstance(project_id, str) and _DRAFT.fullmatch(project_id):
            row = _read(Path(studio_path), "SELECT data FROM studio_drafts WHERE id=?", (project_id,))
            if row is None:
                return None
            draft = json.loads(row["data"])
            if not isinstance(draft, dict) or draft.get("id") != project_id or type(draft.get("revision")) is not int:
                raise ValueError("invalid draft")
            render_id = "studio-" + str(draft["revision"])
        if not isinstance(project_id, str) or not _DRAFT.fullmatch(project_id) or not draft:
            return None
        from backlot.studio_network_materials import public_result
        folder = _safe_folder(root, project_id, render_id)
        value = public_result(folder, draft=draft)
        for item in value.get("items", []):
            asset_id = item.get("asset_id")
            if isinstance(asset_id, str) and _ASSET.fullmatch(asset_id):
                asset = _read(Path(studio_path), "SELECT draft_id,name,kind FROM studio_assets WHERE id=?", (asset_id,))
                if asset and asset["draft_id"] == project_id:
                    item["preview_url"] = "/api/studio/assets/" + asset_id
                    item["name"] = asset["name"]
                    item["kind"] = asset["kind"]
        return value
    except (sqlite3.Error, ValueError, TypeError, AttributeError, KeyError, OSError):
        return {"enabled": None, "status": "unavailable", "used_count": None, "items": [],
                "message": "原任务的素材记录暂不可读，请保留原任务后重新读取。"}
