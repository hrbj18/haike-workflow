"""Frozen account-specific publication plans over the existing CreatorHub contract."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import request, error

from backlot.work_catalog import WorkError, now, sha
from backlot.publish_adapter import PublishIntent, build_publish_payload, submission_key


class CreatorGateway:
    def __init__(self, base_url=None):
        self.base_url = (base_url or os.environ.get(
            "HAIKE_CREATORHUB_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.opener = request.build_opener(request.ProxyHandler({}))

    def call(self, path, data=None, key=None, method=None):
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Idempotency-Key"] = key
        req = request.Request(self.base_url + path, headers=headers,
                              data=None if data is None else json.dumps(data).encode(), method=method)
        try:
            with self.opener.open(req, timeout=15) as response:
                return json.load(response)
        except (error.URLError, ValueError) as exc:
            raise WorkError("发布服务不可用或响应不明，请查询原提交，不重复创建", "unavailable") from exc

    def accounts(self):
        rows = self.call("/api/accounts")
        return [{"id": r.get("id"), "platform": r.get("platform"), "status": r.get("status"),
                 "name": r.get("nickname") or r.get("name"), "has_creator": bool(r.get("has_creator"))} for r in rows]

    def tasks(self):
        return self.call("/api/publish")

    def submit(self, payload, key):
        cap = self.call("/api/publish/capabilities")
        if cap.get("contract_version") != 2 or payload["expected_platform"] not in cap.get("required_cover_platforms", []):
            raise WorkError("发布服务不支持指定封面契约 v2")
        accounts = self.accounts()
        if not any(a["id"] == payload["account_id"] and a["platform"] == payload["expected_platform"]
                   and a["status"] == "active" and a["has_creator"] for a in accounts):
            raise WorkError("发布账号平台不符或需要恢复登录")
        return self.call("/api/publish", payload, key)


def prepare(catalog, work_id, revision):
    work = catalog.get(work_id)
    catalog.check_revision(work, revision)
    if not work["targets"] or not work["materials"]:
        raise WorkError("请先选择目标账号并准备发布资料")
    material = work["materials"][-1]
    if material["version_id"] != work["final_version_id"]:
        raise WorkError("最终版已改变，请为新版确认发布资料")
    video = catalog.media_path(work_id)
    data = material["data"]
    if data.get("source_rights_status") not in {"owned", "confirmed"}:
        raise WorkError("来源使用范围尚未确认，可保存资料但不能提交")
    if not data.get("title") or not data.get("desc"):
        raise WorkError("标题或详情未准备")
    for field in ("cover_path", "cover_proof_path"):
        if data.get(field) and sha(data[field]) != data.get(field + "_sha256"):
            raise WorkError("封面或生成证据已改变，请保存新的资料修订")
    payloads = []
    for target in work["targets"]:
        overrides = data.get("platforms", {}).get(target["platform"], {})
        intent = PublishIntent(account_id=target["account_id"], platform=target["platform"],
            video_path=video, title=overrides.get("title", data["title"]),
            desc=overrides.get("desc", data["desc"]), topics=overrides.get("topics", data.get("topics", "")),
            cover_path=data.get("cover_path", ""), cover_origin=data.get("cover_origin", "provided_image"),
            cover_proof_path=data.get("cover_proof_path", ""),
            package_id=work_id + "-" + work["final_version_id"], package_revision=material["number"],
            source_rights_status=data["source_rights_status"], scheduled_at=target.get("scheduled_at"))
        result = build_publish_payload(intent)
        if result.blocked:
            raise WorkError("；".join(result.blocked))
        payloads.append({"payload": result.payload, "warnings": result.warnings,
                         "key": submission_key(result.payload)})
    return catalog.put_plan("publish", {"work_id": work_id, "revision": revision,
        "version_id": work["final_version_id"], "material_revision": material["number"], "entries": payloads})


def submit(catalog, plan_id, confirmed, gateway=None, actor="local-agent"):
    if confirmed is not True:
        raise WorkError("请确认这份计划将提交真实发布任务")
    gateway = gateway or CreatorGateway()
    with catalog.transaction() as db:
        row = db.execute("SELECT data FROM work_plans WHERE id=? AND kind='publish'", (plan_id,)).fetchone()
        if not row:
            raise WorkError("发布计划不存在")
        plan = json.loads(row[0]); work = catalog._get(db, plan["work_id"])
        lock = db.execute("SELECT token FROM work_activity WHERE project=?", (work["project_id"],)).fetchone()
        if lock and lock[0].startswith("cleanup-"):
            raise WorkError("归档清理执行中，不能提交发布", "conflict")
        existing = [a for a in work["attempts"] if a["plan_id"] == plan_id]
        if not existing:
            catalog.check_revision(work, plan["revision"])
            for entry in plan["entries"]:
                p = entry["payload"]
                if any(a["platform"] == p["expected_platform"] and a["account_id"] == p["account_id"]
                       and a["version_id"] == plan["version_id"]
                       and a["status"] not in {"failed", "canceled"} for a in work["attempts"]):
                    raise WorkError("同一版本和账号已有提交，请查询原任务")
                if sha(p["media"][0] if "media" in p else p["media_paths"][0]) != p["video_sha256"].lower():
                    raise WorkError("成片与发布计划不一致")
            for entry in plan["entries"]:
                p = entry["payload"]
                work["attempts"].append({"plan_id": plan_id, "key": entry["key"],
                    "version_id": plan["version_id"], "material_revision": plan["material_revision"],
                    "platform": p["expected_platform"], "account_id": p["account_id"],
                    "task_id": None, "status": "submitting", "acceptance_status": "not_checked", "at": now()})
            catalog._save(db, work, actor, "publish-submit-intent")
    # Intent is durable before network access; retries use exactly the same key.
    failures = []
    for entry in plan["entries"]:
        current = catalog.get(work["work_id"])
        attempt = next(a for a in current["attempts"] if a["key"] == entry["key"])
        if attempt["task_id"] is not None:
            continue
        payload = entry["payload"]
        for file_key, hash_key in (("cover_path", "cover_sha256"), ("cover_proof_path", "cover_proof_sha256")):
            if payload.get(file_key) and sha(payload[file_key]) != str(payload.get(hash_key, "")).lower():
                raise WorkError("封面或证据与冻结发布计划不一致")
        if sha(payload["media_paths"][0]) != payload["video_sha256"].lower():
            raise WorkError("成片与冻结发布计划不一致")
        try:
            result = gateway.submit(entry["payload"], entry["key"])
            task = result.get("task", result)
            if not task.get("id"):
                raise WorkError("提交响应未包含任务编号，请查询原提交", "unavailable")
        except WorkError as exc:
            # A platform outage must not prevent the other frozen targets.
            # Preserve this exact plan/key so a later recovery cannot fork it.
            with catalog.transaction() as db:
                current = catalog._get(db, work["work_id"])
                a = next(a for a in current["attempts"] if a["key"] == entry["key"])
                a.update(status="uncertain" if exc.code == "unavailable" else "blocked",
                         blocked_reason=str(exc), error=str(exc), synced_at=now())
                catalog._save(db, current, actor, "publish-target-blocked")
            failures.append(exc)
            continue
        with catalog.transaction() as db:
            current = catalog._get(db, work["work_id"])
            a = next(a for a in current["attempts"] if a["key"] == entry["key"])
            a.update(task_id=task["id"], status=task.get("status", "pending"))
            a.pop("blocked_reason", None)
            a.pop("error", None)
            catalog._save(db, current, actor, "publish-receipt")
    if failures:
        raise WorkError("部分平台待恢复，其他平台已继续提交；请查询原发布计划：" + str(failures[0]), failures[0].code)
    return catalog.get(work["work_id"])


def sync(catalog, work_id, gateway=None):
    gateway = gateway or CreatorGateway()
    tasks = gateway.tasks()
    with catalog.transaction() as db:
        work = catalog._get(db, work_id); changed = False
        lock = db.execute("SELECT token FROM work_activity WHERE project=?", (work["project_id"],)).fetchone()
        if lock and lock[0].startswith("cleanup-"):
            raise WorkError("归档清理执行中，发布结果稍后同步", "conflict")
        for a in work["attempts"]:
            t = next((t for t in tasks if t.get("id") == a["task_id"]), None)
            if t is None:
                continue
            evidence = t.get("acceptance_evidence") or t.get("acceptance_evidence_json") or "{}"
            try:
                evidence = json.loads(evidence) if isinstance(evidence, str) else evidence
            except ValueError:
                evidence = {}
            version = next(v for v in work["versions"] if v["version_id"] == a["version_id"])
            bound = (t.get("platform") == a["platform"] and t.get("account_id") == a["account_id"]
                     and str(t.get("video_sha256", "")).lower() == version["sha256"])
            verified = (bound and isinstance(evidence, dict) and bool(evidence.get("work_id"))
                        and all(evidence.get(k) is True for k in
                                ("unique_work", "video_matches", "title_matches", "cover_matches")))
            values = {"status": t.get("status", "uncertain"), "result_url": t.get("result_url", ""),
                      "error": t.get("error") or "", "blocked_reason": t.get("blocked_reason") or "",
                      "next_allowed_at": t.get("next_allowed_at"), "platform_status": t.get("platform_status"),
                      "acceptance_status": "verified" if verified and t.get("acceptance_status") == "verified" else "not_checked",
                      "identity_verified": bound,
                      "acceptance": evidence, "synced_at": now()}
            if any(a.get(k) != v for k, v in values.items() if k != "synced_at"):
                a.update(values); changed = True
        if changed:
            catalog._save(db, work, "creatorhub", "publish-sync")
    return work


def acceptance(catalog, work_id, task_id, data, gateway=None):
    work = catalog.get(work_id)
    if not any(a["task_id"] == task_id for a in work["attempts"]):
        raise WorkError("任务不属于此作品")
    gateway = gateway or CreatorGateway()
    gateway.call(f"/api/publish/{task_id}/acceptance", data, method="PUT")
    return sync(catalog, work_id, gateway)
