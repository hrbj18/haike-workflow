"""Native queue CLI for Template 6 v4 source/word-clock/media art tests."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

HAIKE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HAIKE))


def main(argv=None):
    parser = argparse.ArgumentParser(description="模板6 v4原片艺术测试；真实词时钟、可选真实素材、零云不发布")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--source-video", type=Path)
    parser.add_argument("--cues", type=Path)
    parser.add_argument("--word-clock", type=Path)
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
        if path.is_symlink(): raise ValueError("v4冻结请求不能是符号链接")
        from backlot.production_queue import ProductionQueue
        from backlot.studio import atomic_private
        from backlot.studio_investment_source_art_v4 import CONTRACT, prepare, submit, validate
        queue = ProductionQueue(HAIKE / ".backlot/production-queue.sqlite3", projects_root=HAIKE / "projects")
        if args.action == "prepare":
            if any(v is None for v in (args.source_video, args.cues, args.word_clock, args.art_config, args.title, args.brand)):
                raise ValueError("prepare需要--source-video、--cues、--word-clock、--art-config、--title及--brand")
            request = prepare(queue, args.source_video, args.cues, args.word_clock, args.art_config, title=args.title, brand=args.brand)
            if path.exists() and json.loads(path.read_text(encoding="utf-8")) != request: raise ValueError("此目录已有另一v4冻结请求")
            atomic_private(path, request)
            print(json.dumps({"prepared": True, "project_id": request["project_id"], "render_id": request["render_id"],
                "request_sha256": request["request_sha256"], "duration": request["prepared"]["duration"],
                "direction": request["art_direction"]["direction"], "cloud_calls": 0, "variant": "art-v4"}, ensure_ascii=False))
            return 0
        request = json.loads(path.read_text(encoding="utf-8"))
        validate(queue, request)
        job = submit(queue, request) if args.action == "submit" else queue.find_by_idempotency_key(CONTRACT + ":" + request["request_sha256"])
        if job is None: raise ValueError("此v4测试尚未submit")
        if args.action in {"run", "resume"} and job["status"] != "completed":
            from backlot.production_queue_worker import ProductionQueueWorker
            job = ProductionQueueWorker(queue, HAIKE / "projects", worker_id="source-art-v4-cli", lease_seconds=7200).run_local_recompose(job["job_id"])
        print(json.dumps({k: job.get(k) for k in ("job_id", "project_id", "status", "stage", "result", "error", "retryable")}, ensure_ascii=False))
        return 0 if job["status"] != "failed" else 2
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__": raise SystemExit(main())
