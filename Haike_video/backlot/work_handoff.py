"""Derive an executable handoff from the current catalog, never legacy drafts.

Reading validates managed files without querying publishers or creating tasks.
Prepared materials and permission to publish are intentionally separate facts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from backlot.work_catalog import WorkError, regular_path, sha


def publication_summary(catalog, work):
    version = next((v for v in work["versions"] if v["version_id"] == work["final_version_id"]), None)
    material = work["materials"][-1] if work["materials"] else None
    data = material["data"] if material else {}
    notes = work.get("handoff") or {}
    missing, invalid, blockers = [], [], []
    video_path = None
    try:
        video_path = str(catalog.media_path_from_work(work))
    except (WorkError, OSError):
        invalid.append("最终成片不可用或内容已变化")
    current = bool(material and material["version_id"] == work["final_version_id"])
    if material and not current:
        invalid.append("发布资料属于旧版本，需为当前最终版重新准备")
    for key, label in (("title", "发布标题"), ("desc", "详情文案"), ("topics", "话题"), ("cover_path", "封面")):
        if not str(data.get(key) or "").strip():
            missing.append(label)
    cover_path = None
    proof_path = None
    for key, label in (("cover_path", "封面"), ("cover_proof_path", "封面来源证据")):
        if key == "cover_proof_path" and data.get("cover_origin") != "generated_ai" and not data.get(key):
            continue
        if not data.get(key):
            if key == "cover_proof_path":
                missing.append(label)
            continue
        try:
            path = regular_path(data[key], catalog.project(work["project_id"]))
            if sha(path) != data.get(key + "_sha256"):
                raise WorkError("文件内容已变化")
            if key == "cover_path":
                from backlot.publish_adapter import _check_cover_ratio
                if _check_cover_ratio(path):
                    raise WorkError("封面尺寸或比例无效")
                cover_path = str(path)
            else:
                proof_path = str(path)
        except (WorkError, OSError, ValueError):
            invalid.append(label + "不可用或与资料修订不一致")
    if data.get("cover_origin") == "generated_ai" and proof_path and cover_path:
        try:
            proof = json.loads(Path(proof_path).read_text(encoding="utf-8"))
            original = regular_path(proof["source_image_path"], catalog.project(work["project_id"]))
            if (proof.get("kind") != "ai_generated" or not proof.get("model")
                    or sha(original).upper() != str(proof.get("source_image_sha256", "")).upper()
                    or sha(cover_path).upper() != str(proof.get("final_cover_sha256", "")).upper()):
                raise WorkError("生成证据失效")
            from PIL import Image
            with Image.open(original) as image:
                image.verify()
        except (WorkError, OSError, ValueError, KeyError, TypeError):
            invalid.append("封面生成原图与来源证据不一致")
    ready = bool(version and current and not missing and not invalid)
    candidates = [{key: row.get(key) for key in ("platform", "account_id", "name", "status", "checked_at")}
                  for row in notes.get("candidate_accounts", []) if isinstance(row, dict)]
    targets = work["targets"]
    if not targets:
        blockers.append("本次目标账号待选择；候选账号不等于已选目标")
    rights = data.get("source_rights_status", "unknown")
    if rights not in {"owned", "confirmed"}:
        blockers.append("来源素材使用范围待确认")
    authorization = notes.get("publication_authorization") or {}
    authorized = bool(authorization.get("authorized") is True
                      and authorization.get("evidence")
                      and authorization.get("version_id") == work["final_version_id"]
                      and material and authorization.get("material_revision") == material["number"]
                      and authorization.get("targets") == targets)
    if not authorized:
        blockers.append("尚未记录对当前成片及资料修订的公开发布授权")
    return {
        "authority": "work_catalog", "catalog_revision": work["revision"],
        "video_approved": bool(version), "version_id": work["final_version_id"],
        "video_path": video_path, "video_sha256": version["sha256"] if version else None,
        "metadata_owner": "Codex", "materials_status": "prepared" if ready else "needs_preparation",
        "materials_ready": ready, "material_revision": material["number"] if material else None,
        "title": data.get("title"), "description": data.get("desc"), "topics": data.get("topics"),
        "cover_path": cover_path, "cover_sha256": data.get("cover_path_sha256"),
        "cover_origin": data.get("cover_origin"), "cover_proof_path": proof_path,
        "platform_metadata": data.get("platforms", {}), "request_evidence": data.get("request_evidence"),
        "targets": targets, "target_platforms": list(dict.fromkeys(t["platform"] for t in targets)),
        "candidate_accounts": candidates, "source_rights_status": rights,
        "publish_authorized": authorized, "missing_materials": missing, "invalid_materials": invalid,
        "publication_blockers": blockers, "ready_for_publication": ready and not blockers,
        "next_step": "；".join(missing + invalid + blockers) if missing or invalid or blockers
                     else "执行发布预检，核对冻结计划和既有任务后按具体授权提交",
    }


def export(catalog, work_id):
    """Refresh compatibility snapshots; the catalog remains authoritative."""
    snapshot = catalog.handoff(work_id)
    summary = snapshot["publish_handoff"]
    folder = catalog.project(snapshot["project_id"]) / "artifacts" / "publishing"
    # Check every existing directory component before creating output paths.
    for part in [folder, *folder.parents]:
        if part == catalog.projects_root:
            break
        if part.exists() and (part.is_symlink() or getattr(part.lstat(), "st_file_attributes", 0) & 0x400):
            raise WorkError("交接输出目录不能是符号链接或目录联接")
    folder.mkdir(parents=True, exist_ok=True)
    record = {"record_type": "agent_publish_handoff_snapshot", "schema_version": 2,
              "project_id": snapshot["project_id"], "work_id": work_id,
              "read_only_snapshot": True, "snapshot_at": snapshot["snapshot_at"], **summary,
              "status": "materials_prepared_pending_confirmation" if summary["materials_ready"] else "pending_publish_materials",
              "accounts": summary["targets"], "platform_results": snapshot["attempts"],
              "handoff": snapshot["handoff"],
              "formal_publish_package_path": snapshot["handoff"].get("formal_publish_package_path"),
              "refresh_command": f"python scripts/work_catalog_cli.py handoff {work_id}"}
    text = ("# YC 发布交接\n\n" if snapshot["project_id"].startswith("yc-") else "# 作品发布交接\n\n")
    text += f"这是作品库 revision {snapshot['revision']} 的只读快照；接手时先运行 `{record['refresh_command']}`。\n\n"
    text += f"- 成片：{summary['video_path']}\n- 版本：{summary['version_id']}\n- 发布资料：{summary['materials_status']}\n"
    text += f"- 标题：{summary['title']}\n- 详情：{summary['description']}\n- 话题：{summary['topics']}\n- 封面：{summary['cover_path']}\n"
    text += f"- 目标账号：{json.dumps(summary['targets'], ensure_ascii=False)}\n- 候选账号：{json.dumps(summary['candidate_accounts'], ensure_ascii=False)}\n"
    text += f"- 素材使用范围：{summary['source_rights_status']}\n- 公开发布已授权：{summary['publish_authorized']}\n- 下一步：{summary['next_step']}\n\n"
    text += "发布 POST 可能立即发表，不等于平台草稿；本快照不授予发表权限。来源未知时只做离线预检，缺项不能用其他作品的授权补齐。\n"
    for name, content in (("待发布交接.json", json.dumps(record, ensure_ascii=False, indent=2) + "\n"), ("待发布交接.md", text)):
        target = folder / name
        if target.exists() and (target.is_symlink() or getattr(target.lstat(), "st_file_attributes", 0) & 0x400):
            raise WorkError("交接快照不能覆盖符号链接或目录联接")
        pending = folder / (name + "." + os.urandom(8).hex() + ".tmp")
        try:
            with pending.open("x", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, target)
        finally:
            pending.unlink(missing_ok=True)
    return {"work_id": work_id, "revision": snapshot["revision"], "paths": [str(folder / "待发布交接.json"), str(folder / "待发布交接.md")], "publish_handoff": summary}
