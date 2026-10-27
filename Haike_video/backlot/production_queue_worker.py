"""Execution adapter for the durable Backlot production queue."""

from __future__ import annotations

import os
import socket
import threading
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from backlot.avatar_review_preview_pipeline import (
    read_avatar_review_preview_job,
    run_avatar_review_preview_job,
)
from backlot.production_queue import ProductionQueue, ProductionQueueConflict
from backlot.work_catalog import WorkCatalog
from backlot.workbench import (
    generate_full_preview_render,
    mark_full_preview_render_failed,
    read_review_preview_job,
    read_workbench,
    run_review_preview_job,
    run_autonomous_material_selection,
    start_full_preview_render,
)


Handler = Callable[[dict[str, Any]], dict[str, Any]]


class ProductionQueueWorker:
    """Claim and execute at most one registered parent production job at a time."""

    def __init__(
        self,
        queue: ProductionQueue,
        projects_root: str | Path,
        *,
        handlers: dict[str, Handler] | None = None,
        worker_id: str | None = None,
        lease_seconds: int = 120,
    ):
        self.queue = queue
        self.projects_root = Path(projects_root)
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
        self.lease_seconds = max(30, int(lease_seconds))
        self.handlers = handlers or {
            "review_preview": self._run_review_preview,
            "avatar_review_preview": self._run_avatar_review_preview,
            "full_preview": self._run_full_preview,
            "material_selection": self._run_material_selection,
            "published_remix": self._run_published_remix,
            "material_commentary": self._run_material_commentary,
            "commentary_presenter": self._run_commentary_presenter,
            # Versioned kind prevents already-running legacy workers from
            # silently executing a consumer contract with their shared key.
            "commentary_presenter_consumer_v1": self._run_commentary_presenter,
            "studio_graphic": self._run_studio_graphic,
            "studio_avatar": self._run_studio_avatar,
            "studio_motion": self._run_studio_motion,
            "studio_investment_recompose": self._run_investment_recompose,
        }

    def _run_studio_graphic(self, job):
        from backlot.studio_render import run_graphic
        return run_graphic(self._project_dir(job), job["frozen_request"])

    def _run_studio_avatar(self, job):
        from backlot.studio_avatar import run_avatar
        return run_avatar(self._project_dir(job), job["frozen_request"],
                          progress=lambda stage: self.queue.update_stage(
                              job["job_id"], self.worker_id, stage))

    def _run_studio_motion(self, job):
        from backlot.studio_motion import run_motion
        return run_motion(self._project_dir(job), job["frozen_request"])

    def _run_investment_recompose(self, job):
        if job.get("frozen_request", {}).get("contract") == "hum-production-v1":
            from backlot.studio_hum_production import run
            return run(self.queue, job)
        if job.get("frozen_request", {}).get("contract") == "motiongit-component-render-v1":
            from backlot.studio_motiongit_render import run
            return run(self.queue, job)
        if job.get("frozen_request", {}).get("contract") == "motiongit-narrated-pilot-v1":
            from backlot.studio_motiongit_narrated_pilot import run
            return run(self.queue, job)
        if job.get("frozen_request", {}).get("contract") == "store-material-wall-v1":
            from backlot.studio_store_material_wall import run
            return run(self.queue, job)
        if job.get("frozen_request", {}).get("contract") == "store-motion-showcase-v1":
            from backlot.studio_store_motion_showcase import run
            return run(self.queue, job)
        if job.get("frozen_request", {}).get("contract") == "store-opening-v1":
            from backlot.studio_store_opening import run
            return run(self.queue, job)
        if job.get("frozen_request", {}).get("contract") == "investment-six-v1":
            from backlot.studio_investment_six import run
            return run(self.queue, job)
        if job.get("frozen_request", {}).get("contract") == "store-footage-contrast-v1":
            from backlot.studio_store_footage import run
            return run(self.queue, job)
        if job.get("frozen_request", {}).get("contract") == "store-manager-lab-v1":
            from backlot.studio_store_manager_lab import run
            return run(self.queue, job)
        if job.get("frozen_request", {}).get("contract") == "store-manager-contrast-v1":
            from backlot.studio_store_manager import run
            return run(self.queue, job)
        if job.get("frozen_request", {}).get("contract") == "investment-contrast-five-v1":
            from backlot.studio_investment_contrast import run
            return run(self.queue, job)
        from backlot.studio_investment_full import CONTRACT as FULL_INVESTMENT_CONTRACT
        if job.get("frozen_request", {}).get("contract") == FULL_INVESTMENT_CONTRACT:
            from backlot.studio_investment_full import run
            return run(self.queue, job)
        from backlot.studio_investment_style_lab import CONTRACT as STYLE_LAB_CONTRACT
        if job.get("frozen_request", {}).get("contract") == STYLE_LAB_CONTRACT:
            from backlot.studio_investment_style_lab import run
            return run(self.queue, job)
        from backlot.studio_investment_source_art_v5 import CONTRACT as SOURCE_ART_V5_CONTRACT
        if job.get("frozen_request", {}).get("contract") == SOURCE_ART_V5_CONTRACT:
            from backlot.studio_investment_source_art_v5 import run
            return run(self.queue, job)
        from backlot.studio_investment_source_art_v4 import CONTRACT as SOURCE_ART_V4_CONTRACT
        if job.get("frozen_request", {}).get("contract") == SOURCE_ART_V4_CONTRACT:
            from backlot.studio_investment_source_art_v4 import run
            return run(self.queue, job)
        from backlot.studio_investment_source_video import CONTRACT as SOURCE_ART_CONTRACT
        if job.get("frozen_request", {}).get("contract") == SOURCE_ART_CONTRACT:
            from backlot.studio_investment_source_video import run
            return run(self.queue, job)
        from backlot.studio_investment_recompose import run
        return run(self.queue, job)

    def _project_dir(self, job: dict[str, Any]) -> Path:
        project_dir = (self.projects_root / str(job["project_id"])).resolve()
        root = os.path.normcase(str(self.projects_root.resolve()))
        try:
            inside_root = os.path.commonpath([root, os.path.normcase(str(project_dir))]) == root
        except ValueError:
            inside_root = False
        if not inside_root:
            raise ValueError("项目目录越界")
        if not project_dir.is_dir():
            raise ValueError("排队项目已经不存在")
        return project_dir

    @staticmethod
    def _error_contract(value: Any) -> tuple[dict[str, Any], bool, str | None]:
        if isinstance(value, dict):
            if not value:
                return {}, False, None
            message = str(value.get("message") or value.get("detail") or value.get("reason") or "任务失败")
            return (
                {"type": str(value.get("type") or "ProductionError"), "message": message[:1200]},
                bool(value.get("retryable")),
                str(value.get("safe_resume_point") or "") or None,
            )
        message = str(value or "任务失败")
        return {"type": "ProductionError", "message": message[:1200]}, False, None

    @classmethod
    def _normalize_parent(cls, state: dict[str, Any], *, fallback_stage: str) -> dict[str, Any]:
        status = str(state.get("status") or "failed")
        stage = str(state.get("stage") or fallback_stage)
        error, retryable, safe = cls._error_contract(state.get("error"))
        safe = str(state.get("safe_resume_point") or safe or "") or None
        result = state.get("result") if isinstance(state.get("result"), dict) else {}
        if status == "completed":
            return {"status": "completed", "stage": stage, "result": result}
        if status in {"awaiting_human", "ambiguous"}:
            return {
                "status": status, "stage": stage, "result": result, "error": error,
                "retryable": False, "safe_resume_point": safe,
            }
        if status in {"queued", "running", "generating", "rendering", "submitted", "downloading"}:
            return {
                "status": "failed", "stage": "底层任务未到达可确认终点",
                "error": {"type": "IncompleteParentJob", "message": "底层任务返回后仍在执行，请核对原任务"},
                "retryable": False, "safe_resume_point": safe,
            }
        return {
            "status": "failed", "stage": stage, "result": result, "error": error,
            "retryable": retryable, "safe_resume_point": safe,
        }

    def _run_material_commentary(self, job: dict[str, Any]) -> dict[str, Any]:
        from backlot.commentary_render import render
        return render(self._project_dir(job), str(job["parent_job_id"]))

    def _run_commentary_presenter(self, job: dict[str, Any]) -> dict[str, Any]:
        from backlot.commentary_presenter_job import run
        return run(self._project_dir(job), str(job["parent_job_id"]))

    def _run_published_remix(self, job: dict[str, Any]) -> dict[str, Any]:
        from backlot.published_remix_render import render
        return render(self._project_dir(job), str(job["parent_job_id"]))

    def _run_review_preview(self, job: dict[str, Any]) -> dict[str, Any]:
        project_dir = self._project_dir(job)
        state = run_review_preview_job(project_dir, str(job["parent_job_id"]))
        return self._normalize_parent(state, fallback_stage="无数字人一键审核预览")

    def _run_avatar_review_preview(self, job: dict[str, Any]) -> dict[str, Any]:
        project_dir = self._project_dir(job)
        state = run_avatar_review_preview_job(project_dir, str(job["parent_job_id"]))
        return self._normalize_parent(state, fallback_stage="有数字人一键审核预览")

    def _run_material_selection(self, job: dict[str, Any]) -> dict[str, Any]:
        project_dir = self._project_dir(job)
        state = run_autonomous_material_selection(project_dir, job.get("frozen_request") or {})
        plan = state.get("material_selection_plan") or {}
        status = str(plan.get("status") or "failed")
        result = {
            "plan_path": "artifacts/material_selection_plan.json",
            "scene_count": len(plan.get("scene_plans") or []),
            "sequence_count": len(plan.get("sequences") or []),
            "missing_scene_ids": [
                scene.get("scene_id") for scene in plan.get("scene_plans") or []
                if scene.get("status") != "ready"
            ],
        }
        if status == "adopted":
            return {"status": "completed", "stage": "全片选材完成，等待审核预览", "result": result}
        return {
            "status": "failed", "stage": "素材不足，等待补采后重试", "result": result,
            "error": {"type": "InsufficientMaterial", "message": "部分场景缺少满足来源、质量和时长要求的镜头"},
            "retryable": False, "safe_resume_point": "material_acquisition",
        }

    def _run_full_preview(self, job: dict[str, Any]) -> dict[str, Any]:
        project_dir = self._project_dir(job)
        try:
            current = read_workbench(project_dir)
            preview = ((current.get("automation") or {}).get("preview_render") or {})
            if str(preview.get("status") or "") == "failed":
                current = start_full_preview_render(project_dir, job.get("frozen_request") or {"confirmed": True})
                preview = ((current.get("automation") or {}).get("preview_render") or {})
            if str(preview.get("status") or "") not in {"completed", "preview_ready"}:
                current = generate_full_preview_render(project_dir)
                preview = ((current.get("automation") or {}).get("preview_render") or {})
        except Exception as exc:  # noqa: BLE001 - keep the project child state truthful
            try:
                mark_full_preview_render_failed(project_dir, exc)
            except Exception:
                pass
            raise
        status = str(preview.get("status") or "failed")
        if status in {"completed", "preview_ready"}:
            return {
                "status": "completed", "stage": "等待人工观看",
                "result": {
                    "output_path": preview.get("output_path"),
                    "version": preview.get("version"),
                },
            }
        error, retryable, safe = self._error_contract(preview.get("error"))
        return {
            "status": "failed", "stage": "合成全片审核预览", "error": error,
            "retryable": retryable, "safe_resume_point": safe or "full_preview",
        }

    def inspect_parent(self, job: dict[str, Any]) -> dict[str, Any]:
        project_dir = self._project_dir(job)
        if job["kind"] == "studio_investment_recompose":
            # Recover through its registered runner so version registration is
            # completed too; never put this private kind on the generic lane.
            return {"status": "failed", "stage": "本地重合成中断，保留源素材并恢复原任务", "retryable": True, "safe_resume_point": "local_recompose"}
        if job["kind"] in {"studio_graphic", "studio_avatar", "studio_motion"}:
            filename = {"studio_graphic": "graphic-preview.mp4", "studio_avatar": "avatar-preview.mp4", "studio_motion": "motion-preview.mp4"}[job["kind"]]
            if job["kind"] == "studio_avatar" and job["frozen_request"].get("draft", {}).get("input", {}).get("motion"):
                filename = "motion-preview.mp4"
            output = project_dir / "renders" / job["frozen_request"]["render_id"] / filename
            report = output.parent / "qa.json"
            if output.is_file() and report.is_file():
                return {"status": "completed", "stage": "合成完成，等待人工审核", "result": {"output_path": str(output), "qa_status": "pending"}}
            return {"status": "failed", "stage": "制作中断，原调用与产物保留，可恢复此任务", "retryable": True, "safe_resume_point": job["kind"]}
        if job["kind"] in {"commentary_presenter", "commentary_presenter_consumer_v1"}:
            from backlot.commentary_presenter_job import inspect
            return inspect(project_dir, str(job["parent_job_id"]))
        if job["kind"] == "material_commentary":
            from backlot.commentary_render import inspect
            return inspect(project_dir, str(job["parent_job_id"]))
        if job["kind"] == "published_remix":
            from backlot.published_remix_render import inspect
            return inspect(project_dir, str(job["parent_job_id"]))
        if job["kind"] == "material_selection":
            plan = (read_workbench(project_dir).get("material_selection_plan") or {})
            frozen = job.get("frozen_request") or {}
            if (
                plan.get("request_fingerprint") == frozen.get("request_fingerprint")
                and plan.get("proposal_fingerprint") == frozen.get("proposal_fingerprint")
                and (plan.get("window_qa") or {}).get("task_fingerprint") == frozen.get("window_qa_fingerprint")
            ):
                return {
                    "status": "completed" if plan.get("status") == "adopted" else "failed",
                    "stage": "全片选材完成" if plan.get("status") == "adopted" else "素材不足，等待补采",
                    "result": {"plan_path": "artifacts/material_selection_plan.json"},
                    "retryable": False,
                }
            return {"status": "failed", "stage": "选材任务中断，尚未落账", "retryable": True,
                    "safe_resume_point": "material_selection"}
        if job["kind"] == "review_preview":
            return self._normalize_parent(read_review_preview_job(project_dir), fallback_stage="无数字人一键审核预览")
        if job["kind"] == "avatar_review_preview":
            return self._normalize_parent(read_avatar_review_preview_job(project_dir), fallback_stage="有数字人一键审核预览")
        state = read_workbench(project_dir)
        preview = ((state.get("automation") or {}).get("preview_render") or {})
        status = str(preview.get("status") or "idle")
        if status in {"completed", "preview_ready"}:
            return {
                "status": "completed", "stage": "等待人工观看",
                "result": {"output_path": preview.get("output_path"), "version": preview.get("version")},
            }
        if status in {"generating", "running", "rendering"}:
            return {"status": "ambiguous", "stage": "底层合成仍标记运行，等待核对"}
        if status == "failed":
            error, retryable, safe = self._error_contract(preview.get("error"))
            return {"status": "failed", "stage": "合成失败", "error": error, "retryable": retryable, "safe_resume_point": safe or "full_preview"}
        return {"status": "queued", "stage": "等待从底层安全点恢复"}

    def reconcile_expired(self) -> list[dict[str, Any]]:
        reconciled: list[dict[str, Any]] = []
        for job in self.queue.expired_running():
            try:
                outcome = self.inspect_parent(job)
            except Exception as exc:  # noqa: BLE001 - recovery must preserve the queue record
                outcome = {
                    "status": "failed", "stage": "无法核对遗留生产任务",
                    "error": {"type": type(exc).__name__, "message": str(exc)[:1200]},
                    "retryable": False,
                }
            reconciled.append(self.queue.recover_expired(job["job_id"], **outcome))
            WorkCatalog(self.projects_root).activity(str(job["project_id"]), str(job["job_id"]), False)
        return reconciled

    def run_once(self) -> dict[str, Any] | None:
        self.reconcile_expired()
        job = self.queue.claim_next(self.worker_id, lease_seconds=self.lease_seconds)
        if job is None:
            return None
        return self._execute_claimed(job)

    def run_local_recompose(self, job_id: str) -> dict[str, Any]:
        job = self.queue.claim_local_recompose(job_id, self.worker_id, lease_seconds=self.lease_seconds)
        return self._execute_claimed(job)

    def _execute_claimed(self, job: dict[str, Any]) -> dict[str, Any]:
        stop = threading.Event()

        def renew() -> None:
            interval = max(5.0, self.lease_seconds / 3)
            while not stop.wait(interval):
                try:
                    self.queue.heartbeat(job["job_id"], self.worker_id, lease_seconds=self.lease_seconds)
                except ProductionQueueConflict:
                    return

        heartbeat = threading.Thread(target=renew, name=f"queue-heartbeat-{job['job_id']}", daemon=True)
        heartbeat.start()
        catalog = None
        activity_acquired = False
        try:
            catalog = WorkCatalog(self.projects_root)
            catalog.activity(str(job["project_id"]), str(job["job_id"]), True)
            activity_acquired = True
            self.queue.update_stage(job["job_id"], self.worker_id, "正在执行统一生产任务")
            handler = self.handlers.get(str(job["kind"]))
            if handler is None:
                raise ValueError("生产类型没有注册执行器")
            outcome = handler(job)
            if not isinstance(outcome, dict):
                raise TypeError("生产执行器没有返回状态合同")
            if job["kind"] != "studio_investment_recompose" and outcome.get("status") == "completed" and (outcome.get("result") or {}).get("output_path"):
                from backlot.work_ingest import completed
                try:
                    from backlot.work_catalog import read_json
                    qa = read_json(self.projects_root / str(job["project_id"]) / "artifacts/full_preview_render_report.json")
                    passed = (outcome["result"].get("qa_status") in {"passed", "pass"}
                              or ((qa.get("data") or {}).get("final_review") or {}).get("status") == "pass")
                    work = completed(catalog, str(job["project_id"]), outcome["result"]["output_path"],
                                     str(job["job_id"]), quality_passed=passed)
                    outcome["result"]["work_id"] = work["work_id"]
                except Exception as exc:
                    # Preserve successful media; registration can be retried independently.
                    outcome["result"]["work_registration_error"] = str(exc)[:300]
            return self.queue.finish(job["job_id"], self.worker_id, **outcome)
        except Exception as exc:  # noqa: BLE001 - queue records a durable, user-visible failure
            return self.queue.finish(
                job["job_id"], self.worker_id,
                status="failed", stage="统一生产任务执行失败",
                error={"type": type(exc).__name__, "message": str(exc)[:1200]},
                retryable=False,
            )
        finally:
            stop.set()
            heartbeat.join(timeout=1)
            if activity_acquired:
                catalog.activity(str(job["project_id"]), str(job["job_id"]), False)
