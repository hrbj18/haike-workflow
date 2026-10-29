"""Explicit budget-only amendments; the original content spec stays immutable."""
from __future__ import annotations

import copy
from backlot.codex_batch import BatchError, _money, _no_secrets, canonical, fingerprint


def _path(batch):
    folder = batch.root / "Haike_video/.backlot/codex-batches" / ("batch-" + fingerprint(batch.spec["batch_id"])[:24])
    for part in (folder, *folder.parents):
        if part == batch.root:
            break
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & 0x400):
            raise BatchError("预算授权路径不能穿过链接或目录联接")
    return folder / "budget-authorization.json"


def validate(batch, evidence):
    _no_secrets(evidence)
    fields = {"batch_id", "spec_sha256", "authorized", "reason", "limit_micros", "items"}
    if (not isinstance(evidence, dict) or set(evidence) != fields
            or evidence["batch_id"] != batch.spec["batch_id"] or evidence["spec_sha256"] != batch.spec_hash
            or evidence["authorized"] is not True or not isinstance(evidence["reason"], str)
            or not 1 <= len(evidence["reason"].strip()) <= 500):
        raise BatchError("需要与原规格匹配的明确预算上调授权")
    _money(evidence["limit_micros"])
    rows = evidence["items"]
    if not isinstance(rows, list) or len(rows) != len(batch.spec["items"]):
        raise BatchError("预算修订必须一次覆盖全部原槽位")
    slots = {item["slot_id"]: item for item in batch.spec["items"]}
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"slot_id", "previous_max_charge_micros", "max_charge_micros", "prior_exposure_micros", "authorized_item_limit_micros"}:
            raise BatchError("预算修订槽位字段无效")
        slot = row["slot_id"]
        if slot not in slots or slot in seen:
            raise BatchError("预算修订槽位重复或不属于原批次")
        seen.add(slot)
        for key in ("previous_max_charge_micros", "max_charge_micros", "authorized_item_limit_micros"):
            _money(row[key])
        prior = row["prior_exposure_micros"]
        if type(prior) is not int or prior < 0:
            raise BatchError("历史失败或未知费用须保留为非负整数")
        if row["previous_max_charge_micros"] != slots[slot]["max_charge_micros"] or row["max_charge_micros"] <= row["previous_max_charge_micros"]:
            raise BatchError("预算修订仅允许提高原规格上限")
        if row["max_charge_micros"] + prior > row["authorized_item_limit_micros"]:
            raise BatchError("包含历史敞口后的单条预算超过授权")
    if sum(r["max_charge_micros"] + r["prior_exposure_micros"] for r in rows) > evidence["limit_micros"]:
        raise BatchError("包含历史敞口后的总预算超过授权")
    return copy.deepcopy(evidence)


def effective(batch):
    from lib.bailian_speech import read_record
    record = read_record(_path(batch))
    if not record:
        return None
    evidence = validate(batch, record.get("authorization"))
    if record.get("authorization_sha256") != fingerprint(evidence):
        raise BatchError("预算授权收据校验失败")
    return evidence


def _confirmed(result, queue_id, auth_hash, cap):
    receipt = result.get("budget_amendment") if isinstance(result, dict) else None
    return (isinstance(receipt, dict) and result.get("job_id") == queue_id
            and receipt.get("validated") is True
            and receipt.get("authorization_sha256") == auth_hash
            and receipt.get("max_charge_micros") == cap)


def amend(batch, evidence):
    from lib.bailian_speech import operation_lock, read_record, write_record
    evidence = validate(batch, evidence)  # No HTTP or mutations before full validation.
    batch._guard()
    path = _path(batch)
    with operation_lock(path.parent / "budget-amendment-lock"):
        previous = read_record(path)
        auth_hash = fingerprint(evidence)
        if previous and previous.get("authorization_sha256") != auth_hash:
            raise BatchError("本批已有不同预算修订，先核对原授权收据")
        requests = []
        for item in batch.spec["items"]:
            row = next(r for r in evidence["items"] if r["slot_id"] == item["slot_id"])
            task = batch._task(item)
            queue_id = task.get("links", {}).get("queue_job_id")
            job = batch.api.call("/api/production-queue/jobs/" + queue_id) if queue_id else None
            revision = task.get("facts", {}).get("execution", {}).get("draft_revision")
            if (not job or job.get("project_id") != batch._draft_id(item) or job.get("kind") != "studio_avatar"
                    or job.get("parent_job_id") != "studio-" + str(revision)
                    or task.get("facts", {}).get("execution", {}).get("publication_receipts")):
                raise BatchError("预算修订只适用于尚未发布的原数字人队列")
            payload = {"expected_revision": job["revision"], "previous_max_charge_micros": row["previous_max_charge_micros"],
                       "max_charge_micros": row["max_charge_micros"], "authorization_evidence": canonical(evidence)}
            endpoint = "/api/production-queue/jobs/" + queue_id + "/budget-amend"
            validation = batch.api.call(endpoint, {**payload, "validate_only": True})
            if not _confirmed(validation, queue_id, auth_hash, row["max_charge_micros"]):
                raise BatchError("原队列预算预检回执未确认，未修订或恢复任何任务")
            requests.append((item, row, endpoint, payload))
        if not previous:
            write_record(path, {"authorization": evidence, "authorization_sha256": auth_hash,
                                "original_spec_unchanged": True})
        for item, row, endpoint, payload in requests:
            # Publish authorization before queue admission. A crash resumes this
            # same receipt; the queue event makes a lost response idempotent.
            batch._patch(item, execution={"budget_amendment": {"authorization_sha256": auth_hash, **row,
                          "batch_limit_micros": evidence["limit_micros"]}},
                         budget_floor={"limit_micros": row["max_charge_micros"]})
            result = batch.api.call(endpoint, {**payload, "validate_only": False})
            if not _confirmed(result, endpoint.split("/")[-2], auth_hash, row["max_charge_micros"]):
                raise BatchError("原队列预算修订响应未确认，按原授权核对，禁止另建任务", unknown=True)
        return batch.status()
