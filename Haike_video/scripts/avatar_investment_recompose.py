"""Versioned local-only Investment A footnotes or fixed clear-v2 captions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HAIKE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HAIKE))


def main(argv=None):
    parser = argparse.ArgumentParser(description="招商A本地展示修正版：脚注或clear-v2字幕，不识别、不配音、不生成数字人、不发布")
    parser.add_argument("--request", type=Path, required=True, help="忽略的本地目录内保存冻结修正版请求")
    parser.add_argument("--source-queue", help="prepare时已完成的原studio_avatar队列ID")
    parser.add_argument("--footnote-index", type=int, help="prepare时重点卡索引，从0开始")
    parser.add_argument("--footnote", default=None, help="新脚注；默认空串表示移除")
    parser.add_argument("--caption-style", choices=["clear-v2"], help="只刷新为模板已冻结的clear-v2字幕；不改脚注或其他内容")
    parser.add_argument("--base", default="http://127.0.0.1:14756")
    actions = parser.add_mutually_exclusive_group()
    for name in ("prepare", "submit", "run", "resume", "status"):
        actions.add_argument("--" + name, dest="action", action="store_const", const=name)
    parser.set_defaults(action="prepare")
    args = parser.parse_args(argv)
    try:
        from scripts.avatar_investment_sample import check_workspace, validate_evidence_dir
        check_workspace(args.base)
        path = validate_evidence_dir(args.request.parent) / args.request.name
        if path.is_symlink(): raise ValueError("冻结请求不能是符号链接")
        from backlot.production_queue import ProductionQueue
        from backlot.studio import atomic_private
        from backlot.studio_investment_recompose import KIND, prepare, submit, validate
        queue = ProductionQueue(HAIKE / ".backlot/production-queue.sqlite3", projects_root=HAIKE / "projects")
        if args.action == "prepare":
            if args.source_queue is None: raise ValueError("prepare需要原队列")
            if args.caption_style:
                if args.footnote_index is not None or args.footnote is not None: raise ValueError("字幕刷新不能同时修改脚注")
                request = prepare(queue, args.source_queue, caption_style=args.caption_style)
            else:
                if args.footnote_index is None: raise ValueError("脚注prepare需要脚注索引")
                request = prepare(queue, args.source_queue, {"emphasis_index": args.footnote_index, "footnote": args.footnote or ""})
            if path.exists() and json.loads(path.read_text(encoding="utf-8")) != request:
                raise ValueError("此冻结请求已属于另一修正版，请使用新路径")
            atomic_private(path, request)
            print(json.dumps({"prepared": True, "source_queue_id": request["source_queue_id"], "source_task_id": request["source_task_id"],
                              "source_work_id": request["source_work_id"], "render_id": request["render_id"], "cloud_calls": 0}, ensure_ascii=False))
            return 0
        request = json.loads(path.read_text(encoding="utf-8"))
        validate(queue, request)
        key = KIND + ":" + request["request_sha256"]
        job = submit(queue, request) if args.action == "submit" else queue.find_by_idempotency_key(key)
        if job is None: raise ValueError("此修正版尚未submit")
        if args.action in {"run", "resume"} and job["status"] != "completed":
            from backlot.production_queue_worker import ProductionQueueWorker
            worker = ProductionQueueWorker(queue, HAIKE / "projects", worker_id="investment-local-cli", lease_seconds=7200)
            # This is the worker's queue-claim authority, never a direct runner.
            job = worker.run_local_recompose(job["job_id"])
        print(json.dumps({k: job.get(k) for k in ("job_id", "project_id", "title", "status", "stage", "result", "error", "retryable")}, ensure_ascii=False))
        return 0 if job["status"] != "failed" else 2
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__": raise SystemExit(main())
