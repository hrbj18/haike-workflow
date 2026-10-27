"""Native queue CLI for EDL-driven investment films; zero providers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HAIKE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HAIKE))


def main(argv=None):
    parser = argparse.ArgumentParser(description="完整招商07/08/09；真实EDL、图文与实拍；30秒（08可显式45秒）4x5/20Mbps，零云不发布")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    for name in ("source-video", "source-cues", "edits", "storyboard", "audio-plan"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--template-number", type=int, choices=(7, 8, 9))
    parser.add_argument("--palette-variant", choices=("blue-beige", "cyan-charcoal", "black-pink"))
    parser.add_argument("--ratio", choices=("4x5",), default="4x5")
    parser.add_argument("--title")
    parser.add_argument("--brand", default="海客AI社区服务站")
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
        if path.is_symlink():
            raise ValueError("冻结请求不能是符号链接")
        from backlot.production_queue import ProductionQueue
        from backlot.studio import atomic_private
        from backlot.studio_investment_full import CONTRACT, prepare, submit, validate
        queue = ProductionQueue(HAIKE / ".backlot/production-queue.sqlite3", projects_root=HAIKE / "projects")
        if args.action == "prepare":
            if any(value is None for value in (args.source_video, args.source_cues, args.edits, args.storyboard,
                                               args.audio_plan, args.template_number, args.palette_variant, args.title)):
                raise ValueError("prepare需要原MP4、真实source-cues、edits、storyboard、audio-plan、模板编号、配色和标题")
            request = prepare(queue, args.source_video, args.source_cues, args.edits, args.storyboard, args.audio_plan,
                template_number=args.template_number, palette_variant=args.palette_variant,
                ratio=args.ratio, title=args.title, brand=args.brand)
            if path.exists() and json.loads(path.read_text(encoding="utf-8")) != request:
                raise ValueError("此目录已有不同冻结请求，请为新修订使用新evidence-dir")
            atomic_private(path, request)
            print(json.dumps({"prepared": True, **{k: request[k] for k in
                ("project_id", "render_id", "request_sha256", "template_id", "ratio", "render_profile", "audio_mode")},
                "content_end_frame": request["source_edits"]["content_end_frame"],
                "tail_hold_frames": request["source_edits"]["tail_hold_frames"], "cloud_calls": 0}, ensure_ascii=False))
            return 0
        request = json.loads(path.read_text(encoding="utf-8"))
        validate(queue, request)
        job = submit(queue, request) if args.action == "submit" else queue.find_by_idempotency_key(CONTRACT + ":" + request["request_sha256"])
        if job is None:
            raise ValueError("此完整招商任务尚未submit")
        if args.action in {"run", "resume"} and job["status"] != "completed":
            from backlot.production_queue_worker import ProductionQueueWorker
            job = ProductionQueueWorker(queue, HAIKE / "projects", worker_id="investment-full-cli",
                lease_seconds=7200).run_local_recompose(job["job_id"])
        print(json.dumps({k: job.get(k) for k in
            ("job_id", "project_id", "status", "stage", "result", "error", "retryable")}, ensure_ascii=False))
        return 2 if job["status"] == "failed" else 0
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
