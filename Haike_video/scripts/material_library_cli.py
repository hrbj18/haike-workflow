"""Single offline entry for economical agents: register, review, choose, resume."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot import material_library as library
from backlot import material_library_evidence as evidence
from backlot import material_library_selection as selection


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="测试或独立素材库SQLite路径")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("register", "scan", "ingest"):
        cmd = commands.add_parser(name)
        cmd.add_argument("path")
    commands.add_parser("status")
    commands.add_parser("sync-published")
    query = commands.add_parser("query")
    query.add_argument("query", nargs="?", default="")
    plan = commands.add_parser("plan")
    plan.add_argument("topic")
    for name in ("prepare", "submit", "candidates", "select", "acquire"):
        cmd = commands.add_parser(name)
        cmd.add_argument("json_path")
        if name == "select":
            cmd.add_argument("--clips", nargs=3)
            cmd.add_argument("--template-key")
    finish = commands.add_parser("finish-acquisition")
    finish.add_argument("request_id")
    finish.add_argument("json_path")
    parser.add_argument("--output", help="另存返回JSON，便于下阶段复用")
    args = parser.parse_args(argv)
    kwargs = {"db_path": Path(args.db) if args.db else None}
    try:
        if args.command == "register": result = library.register_file(args.path, **kwargs)
        elif args.command == "scan": result = library.scan_folder(args.path, **kwargs)
        elif args.command == "ingest": result = library.ingest_catalog(args.path, **kwargs)
        elif args.command == "status": result = library.summary(**kwargs)
        elif args.command == "sync-published": result = library.sync_published(**kwargs)
        elif args.command == "query": result = {"media": library.list_media(args.query, **kwargs), "clips": library.list_clips(args.query, **kwargs)}
        elif args.command == "plan": result = selection.default_plan(args.topic)
        elif args.command == "prepare": result = evidence.prepare_task(read(args.json_path), **kwargs)
        elif args.command == "submit": result = evidence.submit_task(read(args.json_path), **kwargs)
        elif args.command == "candidates": result = selection.compact_candidates(read(args.json_path), **kwargs)
        elif args.command == "select":
            result = selection.select(read(args.json_path), clip_ids=args.clips, **kwargs)
            if args.template_key and result["status"] == "ready":
                result["template_spec"] = selection.to_template_spec(result, args.template_key, **kwargs)
        elif args.command == "acquire": result = selection.acquisition_request(read(args.json_path), **kwargs)
        else: result = selection.finish_acquisition(args.request_id, read(args.json_path), **kwargs)
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if isinstance(result, dict) and result.get("status") in {"needs_material", "budget_exhausted"} else 0
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
