from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from backlot.production_queue import ProductionQueue, ProductionQueueConflict, ProductionQueueError


def _project(root: Path, project_id: str, title: str | None = None) -> None:
    project_dir = root / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(
        json.dumps({"id": project_id, "title": title or project_id}, ensure_ascii=False),
        encoding="utf-8",
    )


def _queue(tmp_path: Path) -> tuple[ProductionQueue, Path]:
    projects = tmp_path / "projects"
    _project(projects, "alpha", "甲项目")
    _project(projects, "beta", "乙项目")
    return ProductionQueue(tmp_path / "state" / "queue.sqlite3", projects), projects


def _submit(
    queue: ProductionQueue,
    *,
    project_id: str,
    parent_job_id: str,
    priority: str = "normal",
    kind: str = "review_preview",
    source: str = "workbench",
    key: str | None = None,
) -> dict:
    return queue.submit(
        project_id=project_id,
        kind=kind,
        source=source,
        priority=priority,
        parent_job_id=parent_job_id,
        frozen_request={"confirmed": True},
        idempotency_key=key,
    )


def test_submit_is_idempotent_and_public_payload_redacts_secrets(tmp_path: Path) -> None:
    queue, _ = _queue(tmp_path)
    first = queue.submit(
        project_id="alpha",
        kind="review_preview",
        source="codex",
        priority="normal",
        parent_job_id="RP-1",
        frozen_request={
            "confirmed": True,
            "api_key": "must-not-leak",
            "nested": {"authorization": "must-not-leak", "budget": 5},
        },
        idempotency_key="stable-request",
    )
    second = queue.submit(
        project_id="alpha",
        kind="review_preview",
        source="codex",
        priority="normal",
        parent_job_id="RP-1",
        frozen_request={"confirmed": True},
        idempotency_key="stable-request",
    )

    assert first["job_id"] == second["job_id"]
    assert len(queue.list()["tasks"]) == 1
    assert "must-not-leak" not in json.dumps(queue.get(first["job_id"]), ensure_ascii=False)
    private = queue.get(first["job_id"], include_private=True)
    assert private["frozen_request"] == {"confirmed": True, "nested": {"budget": 5}}


def test_private_frozen_request_preserves_execution_paths_and_redacts_credentials(tmp_path: Path) -> None:
    queue, _ = _queue(tmp_path)
    audio = r"D:\生产 项目\assets\quote\narration.wav"
    portrait = r"D:\生产 项目\assets\quote\portrait.jpg"
    task = queue.submit(
        project_id="alpha",
        kind="studio_avatar",
        source="workbench",
        priority="normal",
        parent_job_id="studio-2",
        frozen_request={
            "prepared": {"audio_path": audio, "portrait_path": portrait},
            "assets": [{"path": portrait, "api_key": "nested-secret"}],
            "api_key": "top-secret",
            "note": "Authorization: inline-secret",
        },
    )

    private = queue.get(task["job_id"], include_private=True)["frozen_request"]
    assert private["prepared"] == {"audio_path": audio, "portrait_path": portrait}
    assert private["assets"] == [{"path": portrait}]
    assert private["note"] == "Authorization: [REDACTED]"
    assert "secret" not in json.dumps(private)
    claimed = queue.claim_next("worker")
    assert claimed["frozen_request"] == private
    for public in (task, queue.get(task["job_id"]), queue.list()):
        serialized = json.dumps(public)
        assert "frozen_request" not in serialized
        assert "narration.wav" not in serialized
        assert "portrait.jpg" not in serialized
        assert "secret" not in serialized


def test_priority_then_fifo_and_single_global_execution_lease(tmp_path: Path) -> None:
    queue, _ = _queue(tmp_path)
    normal = _submit(queue, project_id="alpha", parent_job_id="RP-normal", priority="normal")
    background = _submit(queue, project_id="beta", parent_job_id="RP-background", priority="background")
    priority = _submit(
        queue,
        project_id="beta",
        parent_job_id="PRJ-priority",
        priority="priority",
        kind="full_preview",
    )

    claimed = queue.claim_next("worker-one")
    assert claimed and claimed["job_id"] == priority["job_id"]
    # A second process must not claim a different job while one global lane is occupied.
    assert queue.claim_next("worker-two") is None
    queue.finish(priority["job_id"], "worker-one", status="completed", stage="完成")

    claimed = queue.claim_next("worker-two")
    assert claimed and claimed["job_id"] == normal["job_id"]
    queue.finish(normal["job_id"], "worker-two", status="completed", stage="完成")
    claimed = queue.claim_next("worker-two")
    assert claimed and claimed["job_id"] == background["job_id"]


def test_concurrent_claim_never_grants_two_execution_slots(tmp_path: Path) -> None:
    queue, _ = _queue(tmp_path)
    _submit(queue, project_id="alpha", parent_job_id="RP-1")
    _submit(queue, project_id="beta", parent_job_id="RP-2")
    barrier = threading.Barrier(3)
    results: list[dict | None] = []

    def claim(worker: str) -> None:
        barrier.wait()
        results.append(queue.claim_next(worker))

    threads = [threading.Thread(target=claim, args=(f"worker-{index}",)) for index in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert sum(result is not None for result in results) == 1


def test_pause_resume_cancel_retry_and_ambiguous_guard(tmp_path: Path) -> None:
    queue, _ = _queue(tmp_path)
    paused = _submit(queue, project_id="alpha", parent_job_id="RP-pause")
    assert queue.pause(paused["job_id"])["status"] == "paused"
    assert queue.resume(paused["job_id"])["status"] == "queued"
    assert queue.cancel(paused["job_id"])["status"] == "cancelled"

    failed = _submit(queue, project_id="alpha", parent_job_id="RP-retry", key="retryable")
    claimed = queue.claim_next("worker")
    assert claimed and claimed["job_id"] == failed["job_id"]
    queue.finish(
        failed["job_id"],
        "worker",
        status="failed",
        stage="供应商暂时不可用",
        error={"message": "稍后重试"},
        retryable=True,
        safe_resume_point="audio",
    )
    assert queue.retry(failed["job_id"])["status"] == "queued"

    # Finish it as ambiguous and prove that ordinary retry cannot duplicate a paid submit.
    claimed = queue.claim_next("worker")
    assert claimed and claimed["job_id"] == failed["job_id"]
    queue.finish(failed["job_id"], "worker", status="ambiguous", stage="等待核对")
    with pytest.raises(ProductionQueueConflict, match="核对"):
        queue.retry(failed["job_id"])


def test_running_cancel_waits_for_parent_boundary_and_events_are_auditable(tmp_path: Path) -> None:
    queue, _ = _queue(tmp_path)
    task = _submit(queue, project_id="alpha", parent_job_id="RP-1")
    claimed = queue.claim_next("worker")
    assert claimed and claimed["job_id"] == task["job_id"]
    requested = queue.cancel(task["job_id"])
    assert requested["status"] == "running"
    assert requested["cancel_requested"] is True
    final = queue.finish(task["job_id"], "worker", status="completed", stage="底层任务完成")
    assert final["status"] == "cancelled"
    assert "安全任务边界" in final["stage"]
    assert [event["event_type"] for event in queue.events(task["job_id"])] == [
        "submitted",
        "claimed",
        "cancel_requested",
        "finished",
    ]


def test_public_failure_redacts_local_paths_and_inline_authorization(tmp_path: Path) -> None:
    queue, _ = _queue(tmp_path)
    task = _submit(queue, project_id="alpha", parent_job_id="RP-secret")
    queue.claim_next("worker")
    final = queue.finish(
        task["job_id"],
        "worker",
        status="failed",
        stage="失败",
        error={
            "message": r"C:\private\project\secret.json failed; x-api-key: visible-secret",
            "retryable": False,
        },
    )

    serialized = json.dumps(final, ensure_ascii=False)
    assert "C:\\private" not in serialized
    assert "visible-secret" not in serialized
    assert "[LOCAL_PATH]" in serialized
    assert "[REDACTED]" in serialized


_BUDGET_STOP = "后续报价超过本次总费用上限，已完成产物保留；未提交这一步"


def _budget_blocked_avatar(tmp_path, *, status="failed", message=_BUDGET_STOP, kind="studio_avatar", request_changes=None):
    queue, projects = _queue(tmp_path)
    request = {"id": "original-request", "render_id": "studio-2", "max_charge_micros": 4860000,
               "key_identity": "original-account-hash", "analysis_mode": "agent",
               "draft": {"id": "alpha", "revision": 2, "text": "原口播稿", "input": {"rate": 1.15}},
               "prepared": {"image_file": "original-image"}, "quotes": {"tts": {"id": "original-tts-quote"}}}
    request.update(request_changes or {})
    task = queue.submit(project_id="alpha", kind=kind, source="codex", priority="normal",
                        parent_job_id="studio-2", frozen_request=request, idempotency_key="original-avatar")
    claimed = queue.claim_next("original-worker")
    assert claimed["job_id"] == task["job_id"]
    queue.finish(task["job_id"], "original-worker", status=status, stage=message,
                 error={"type": "StudioAvatar", "message": message}, retryable=False, safe_resume_point="studio_avatar")
    path = projects / "alpha/renders/studio-2/gateway-state.json"
    path.parent.mkdir(parents=True)
    state = {"prepared": {"audio_path": str(path.parent / "narration.wav"), "duration": 43.64},
             "stages": {name: {"quote": {"id": "quote-" + name, "model": model, "max_charge_micros": amount},
                                "intent": "original-" + name, "job": {"id": "job-" + name, "status": "succeeded", "charged_micros": None}}
                        for name, model, amount in [("tts", "haike/internal-tts", "43520"), ("asr_bailian", "haike/bailian-asr", "100000")]}}
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return queue, task["job_id"], path


def _amend(queue, job_id, **changes):
    data = {"expected_revision": queue.get(job_id)["revision"], "previous_max_charge_micros": 4860000,
            "max_charge_micros": 5860000, "authorization_evidence": "本批用户明确授权每条6元、整批18元，旧费用预留保留"}
    data.update(changes)
    return queue.amend_studio_avatar_budget(job_id, **data)


def test_avatar_budget_validate_then_amend_preserves_original_request_and_receipts(tmp_path):
    queue, job_id, state_path = _budget_blocked_avatar(tmp_path)
    before = queue.get(job_id, include_private=True)
    state_bytes = state_path.read_bytes()
    events = queue.events(job_id)
    preview = _amend(queue, job_id, validate_only=True)
    assert preview["status"] == "failed" and preview["budget_amendment"]["applied"] is False
    assert preview["budget_amendment"]["validated"] is True
    assert queue.get(job_id, include_private=True) == before and queue.events(job_id) == events
    result = _amend(queue, job_id)
    assert result["job_id"] == job_id and result["status"] == "queued"
    assert result["budget_amendment"]["applied"] is True and result["budget_amendment"]["replayed"] is False
    after = queue.get(job_id, include_private=True)
    expected = {**before["frozen_request"], "max_charge_micros": 5860000}
    assert after["frozen_request"] == expected
    for key in ("idempotency_key", "parent_job_id", "project_id", "source", "kind", "priority", "created_at", "attempt_count", "result"):
        assert after[key] == before[key]
    assert state_path.read_bytes() == state_bytes
    assert queue.claim_next("same-job-worker")["frozen_request"] == expected
    assert [e["event_type"] for e in queue.events(job_id)] == ["submitted", "claimed", "finished", "budget_amended", "claimed"]
    assert "frozen_request" not in json.dumps(result)


def test_avatar_budget_amendment_replay_does_not_requeue_running_job(tmp_path):
    queue, job_id, state_path = _budget_blocked_avatar(tmp_path)
    revision = queue.get(job_id)["revision"]
    first = _amend(queue, job_id)
    queue.claim_next("running-worker")
    before = queue.get(job_id, include_private=True)
    replay = _amend(queue, job_id, expected_revision=revision)
    assert replay["status"] == "running" and replay["budget_amendment"]["replayed"] is True
    assert replay["budget_amendment"]["authorization_sha256"] == first["budget_amendment"]["authorization_sha256"]
    assert queue.get(job_id, include_private=True) == before
    assert sum(e["event_type"] == "budget_amended" for e in queue.events(job_id)) == 1
    for change in ({"previous_max_charge_micros": 4860001}, {"max_charge_micros": 5860001},
                   {"authorization_evidence": "另一份授权不能冒充原修订"}):
        with pytest.raises(ProductionQueueConflict):
            _amend(queue, job_id, **change)


@pytest.mark.parametrize("change", [
    {"max_charge_micros": True}, {"max_charge_micros": 5860000.0}, {"max_charge_micros": 4860000},
    {"max_charge_micros": 4859999}, {"max_charge_micros": 1000000001}, {"previous_max_charge_micros": False},
    {"expected_revision": True}, {"authorization_evidence": ""}, {"authorization_evidence": "\n"},
    {"validate_only": "yes"},
])
def test_avatar_budget_amendment_rejects_invalid_authorization_or_amounts(tmp_path, change):
    queue, job_id, path = _budget_blocked_avatar(tmp_path)
    before, state = queue.get(job_id, include_private=True), path.read_bytes()
    with pytest.raises(ProductionQueueError):
        _amend(queue, job_id, **change)
    assert queue.get(job_id, include_private=True) == before and path.read_bytes() == state


@pytest.mark.parametrize("status,message,kind", [
    ("failed", "素材账号登录暂时无法检查", "studio_avatar"),
    ("ambiguous", _BUDGET_STOP, "studio_avatar"), ("completed", _BUDGET_STOP, "studio_avatar"),
    ("failed", _BUDGET_STOP, "full_preview"),
])
def test_avatar_budget_amendment_only_reopens_exact_unsubmitted_budget_failure(tmp_path, status, message, kind):
    queue, job_id, path = _budget_blocked_avatar(tmp_path, status=status, message=message, kind=kind)
    before = queue.get(job_id, include_private=True)
    with pytest.raises(ProductionQueueConflict):
        _amend(queue, job_id)
    assert queue.get(job_id, include_private=True) == before


@pytest.mark.parametrize("problem", ["avatar_quote", "avatar_intent", "avatar_unknown", "tts_failed", "asr_unknown", "empty_stages", "missing", "invalid", "stale_revision", "old_limit", "foreign_draft", "other_render"])
def test_avatar_budget_amendment_guards_existing_paid_stage_and_original_version(tmp_path, problem):
    request_changes = {"draft": {"id": "beta", "revision": 2}} if problem == "foreign_draft" else {"render_id": "../outside"} if problem == "other_render" else None
    queue, job_id, path = _budget_blocked_avatar(tmp_path, request_changes=request_changes)
    value = json.loads(path.read_text(encoding="utf-8"))
    if problem == "avatar_quote": value["stages"]["avatar"] = {"quote": {"id": "avatar-quote"}}
    elif problem == "avatar_intent": value["stages"]["avatar"] = {"intent": "original-avatar-intent"}
    elif problem == "avatar_unknown": value["stages"]["avatar"] = {"job": {"status": "submission_unknown"}}
    elif problem == "tts_failed": value["stages"]["tts"]["job"]["status"] = "failed"
    elif problem == "asr_unknown": value["stages"]["asr_bailian"]["job"]["status"] = "submission_unknown"
    elif problem == "empty_stages": value["stages"] = {}
    path.write_text(json.dumps(value), encoding="utf-8")
    if problem == "missing": path.unlink()
    elif problem == "invalid": path.write_text("{invalid", encoding="utf-8")
    changes = {"expected_revision": 1} if problem == "stale_revision" else {"previous_max_charge_micros": 4859999} if problem == "old_limit" else {}
    before, events = queue.get(job_id, include_private=True), queue.events(job_id)
    with pytest.raises(ProductionQueueConflict):
        _amend(queue, job_id, **changes)
    assert queue.get(job_id, include_private=True) == before and queue.events(job_id) == events
