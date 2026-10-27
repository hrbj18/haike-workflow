"""Prepare or resume native queue jobs for investment templates 3 through 10."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HAIKE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HAIKE))


def main(argv=None):
    parser = argparse.ArgumentParser(description="招商视频模板3至10；四画幅12秒/20Mbps本地风格测试，零云不发布")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--source-video", type=Path)
    parser.add_argument("--cues", type=Path)
    parser.add_argument("--template-number", type=int, choices=range(3, 11))
    parser.add_argument("--ratio", choices=("9x16", "4x5", "1x1", "16x9"))
    parser.add_argument("--palette-variant", choices=("default", "blue-beige", "cyan-charcoal", "black-pink"),
                        help="可选；新配色仅4x5且依次绑定模板07/08/09；default与省略保持旧默认")
    parser.add_argument("--title")
    parser.add_argument("--brand", default="海客AI社区服务站")
    parser.add_argument("--headline", help="可选；须与cues JSON的beat_titles首拍一致；省略时读取首拍")
    parser.add_argument("--cta", default="")
    parser.add_argument("--audio-plan", type=Path)
    parser.add_argument("--mixed-audio", type=Path)
    parser.add_argument("--audio-receipt", type=Path)
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
        from backlot.studio_investment_style_lab import CONTRACT, prepare, submit, validate
        queue = ProductionQueue(HAIKE / ".backlot/production-queue.sqlite3", projects_root=HAIKE / "projects")
        if args.action == "prepare":
            if any(item is None for item in (args.source_video, args.cues, args.template_number, args.ratio, args.title)):
                raise ValueError("prepare需要source-video、cues、template-number、ratio与title")
            request = prepare(queue, args.source_video, args.cues, template_number=args.template_number,
                ratio=args.ratio, title=args.title, brand=args.brand, headline=args.headline, cta=args.cta,
                audio_plan=args.audio_plan, mixed_audio=args.mixed_audio, audio_receipt=args.audio_receipt,
                palette_variant=args.palette_variant)
            if path.exists() and json.loads(path.read_text(encoding="utf-8")) != request:
                raise ValueError("此证据目录已有不同冻结请求，请保留原目录并为新请求使用另一目录")
            atomic_private(path, request)
            print(json.dumps({"prepared": True, **{key: request[key] for key in
                ("project_id", "render_id", "request_sha256", "template_id", "ratio", "render_profile", "audio_mode")},
                "cloud_calls": 0}, ensure_ascii=False))
            return 0
        request = json.loads(path.read_text(encoding="utf-8"))
        validate(queue, request)
        job = submit(queue, request) if args.action == "submit" else queue.find_by_idempotency_key(CONTRACT + ":" + request["request_sha256"])
        if job is None:
            raise ValueError("此模板测试尚未submit")
        if args.action in {"run", "resume"} and job["status"] != "completed":
            from backlot.production_queue_worker import ProductionQueueWorker
            job = ProductionQueueWorker(queue, HAIKE / "projects", worker_id="investment-style-lab-cli",
                lease_seconds=7200).run_local_recompose(job["job_id"])
        print(json.dumps({key: job.get(key) for key in
            ("job_id", "project_id", "status", "stage", "result", "error", "retryable")}, ensure_ascii=False))
        return 2 if job["status"] == "failed" else 0
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
