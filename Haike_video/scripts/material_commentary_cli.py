"""素材解说：先取证，再自由编排，统一队列生产。"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backlot import material_commentary as flow, commentary_evidence as evidence, commentary_audio as audio
from backlot import commentary_alignment as alignment, commentary_editorial as editorial
from backlot import commentary_presenter as presenter, commentary_presenter_job as presenter_job
from backlot import commentary_layout as layout
from backlot.commentary_common import CommentaryConflict, project_dir
from backlot.production_queue import ProductionQueue, DEFAULT_DB_NAME


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects-root", type=Path, default=ROOT / "projects")
    parser.add_argument("--db", type=Path, help="独立测试素材库")
    parser.add_argument("--queue-db", type=Path)
    parser.add_argument("--output", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    create = commands.add_parser("create"); create.add_argument("title")
    for name in ("brief", "versions", "editorial"):
        command = commands.add_parser(name); command.add_argument("project")
    for name in ("save", "evidence", "audio-import", "alignment-import", "compare", "quote", "tts", "presenter-import", "presenter-quote", "presenter-submit", "layout-prepare", "layout-protection", "layout-apply"):
        command = commands.add_parser(name); command.add_argument("project"); command.add_argument("json_path", type=Path)
    review = commands.add_parser("review"); review.add_argument("project"); review.add_argument("evidence_id"); review.add_argument("json_path", type=Path)
    status = commands.add_parser("presenter-status"); status.add_argument("project"); status.add_argument("generation_id")
    task = commands.add_parser("layout-task"); task.add_argument("project"); task.add_argument("task_id")
    for name in ("preflight", "submit"):
        command = commands.add_parser(name); command.add_argument("project"); command.add_argument("revision", type=int)
    args = parser.parse_args(argv)
    kw = {"projects_root": args.projects_root, "db_path": args.db}
    try:
        payload = json.loads(args.json_path.read_text(encoding="utf-8-sig")) if hasattr(args, "json_path") else None
        if payload is not None and not isinstance(payload, dict): raise ValueError("输入必须为JSON对象")
        if args.command == "list": result = flow.list_drafts(db_path=args.db)
        elif args.command == "create": result = flow.create(args.title, **kw)
        else:
            flow.read(args.project, db_path=args.db)
            project = project_dir(args.project, args.projects_root)
            if args.command == "brief": result = flow.brief(args.project, **kw)
            elif args.command == "editorial": result = editorial.audit(flow.read(args.project, db_path=args.db)["payload"], project=project)
            elif args.command == "compare": result = editorial.compare(args.project, payload, **kw)
            elif args.command == "alignment-import": result = alignment.import_alignment(project, payload)
            elif args.command == "versions": result = flow.versions(args.project, **kw)
            elif args.command == "save": result = flow.save(args.project, payload, **kw)
            elif args.command == "evidence": result = evidence.prepare(project, payload, db_path=args.db)
            elif args.command == "review": result = evidence.review(project, args.evidence_id, payload, db_path=args.db)
            elif args.command == "audio-import": result = audio.import_audio(project, payload.get("path", ""),
                narration_text=payload.get("text", ""), kind=payload.get("kind", "narration"), provenance=payload.get("provenance", "用户导入"))
            elif args.command == "quote": result = audio.quote(payload)
            elif args.command == "tts": result = audio.synthesize(project, payload)
            elif args.command == "presenter-import": result = presenter.import_presenter(project, payload)
            elif args.command == "presenter-quote": result = presenter_job.quote(project, payload)
            elif args.command == "presenter-status": result = presenter_job.inspect(project, args.generation_id)
            elif args.command == "layout-prepare": result = layout.prepare(project,payload,db_path=args.db)
            elif args.command == "layout-protection": result = layout.submit_protection(project,payload)
            elif args.command == "layout-apply": result = layout.apply(args.project,payload,**kw)
            elif args.command == "layout-task": result = layout.read_task(project,args.task_id)
            elif args.command == "presenter-submit":
                queue = ProductionQueue(args.queue_db or args.projects_root.parent / ".backlot" / DEFAULT_DB_NAME, args.projects_root)
                result = presenter_job.submit(project, payload, queue)
            elif args.command == "preflight": result = flow.preflight(args.project, args.revision, **kw)
            else:
                queue = ProductionQueue(args.queue_db or args.projects_root.parent / ".backlot" / DEFAULT_DB_NAME, args.projects_root)
                result = flow.submit(args.project, args.revision, queue, **kw)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if isinstance(result, dict) and result.get("status") == "needs_material" else 0
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"error": str(exc), **getattr(exc, "detail", {})}, ensure_ascii=False))
        return 2 if isinstance(exc, flow.MaterialGap) else 3 if isinstance(exc, CommentaryConflict) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
