"""Native queue entry for local-only Template 6 source-video art tests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HAIKE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HAIKE))


def main(argv=None):
    parser = argparse.ArgumentParser(description="模板6原视频艺术开发测试；零云、原速、不可发布")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--source-video", type=Path)
    parser.add_argument("--cues", type=Path, help="已存在真实cue数组JSON，每cue绑定原视频SHA；也支持顶层cues对象")
    parser.add_argument("--art-config", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--brand")
    parser.add_argument("--base", default="http://127.0.0.1:14756")
    actions = parser.add_mutually_exclusive_group()
    for name in ("prepare", "submit", "run", "resume", "status"):
        actions.add_argument("--" + name, dest="action", action="store_const", const=name)
    parser.set_defaults(action="prepare")
    args = parser.parse_args(argv)
    try:
        from scripts.avatar_investment_sample import check_workspace, validate_evidence_dir
        check_workspace(args.base)
        directory = validate_evidence_dir(args.evidence_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "request.json"
        if path.is_symlink(): raise ValueError("冻结请求不能是符号链接")
        from backlot.production_queue import ProductionQueue
        from backlot.studio import atomic_private
        from backlot.studio_investment_source_video import CONTRACT, prepare, submit, validate
        queue = ProductionQueue(HAIKE / ".backlot/production-queue.sqlite3", projects_root=HAIKE / "projects")
        if args.action == "prepare":
            if any(value is None for value in (args.source_video, args.cues, args.art_config, args.title, args.brand)):
                raise ValueError("prepare需要--source-video、--cues、--art-config、--title及--brand")
            request = prepare(queue, args.source_video, args.cues, args.art_config, title=args.title, brand=args.brand)
            if path.exists() and json.loads(path.read_text(encoding="utf-8")) != request:
                raise ValueError("此证据目录已属于另一冻结艺术测试，请使用新目录")
            atomic_private(path, request)
            print(json.dumps({"prepared": True, "project_id": request["project_id"], "render_id": request["render_id"],
                              "request_sha256": request["request_sha256"], "duration": request["prepared"]["duration"],
                              "direction": request["art_direction"]["direction"], "cloud_calls": 0}, ensure_ascii=False))
            return 0
        request = json.loads(path.read_text(encoding="utf-8"))
        validate(queue, request)
        job = submit(queue, request) if args.action == "submit" else queue.find_by_idempotency_key(CONTRACT + ":" + request["request_sha256"])
        if job is None: raise ValueError("此艺术测试尚未submit")
        if args.action in {"run", "resume"} and job["status"] != "completed":
            from backlot.production_queue_worker import ProductionQueueWorker
            worker = ProductionQueueWorker(queue, HAIKE / "projects", worker_id="source-video-art-cli", lease_seconds=7200)
            job = worker.run_local_recompose(job["job_id"])
        print(json.dumps({k: job.get(k) for k in ("job_id", "project_id", "status", "stage", "result", "error", "retryable")}, ensure_ascii=False))
        return 0 if job["status"] != "failed" else 2
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__": raise SystemExit(main())
