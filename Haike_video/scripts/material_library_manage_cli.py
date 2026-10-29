"""通用素材管理、观察与项目追溯；不触发付费分析或生产。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot import material_library_management as management
from backlot import material_library_refs as refs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="独立测试库路径；省略使用共享库")
    parser.add_argument("--output", help="另存结果 JSON")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    search = commands.add_parser("search")
    for name in ("query", "tag", "collection", "platform"):
        search.add_argument("--" + name, default="")
    for name, default in (("archived", "active"), ("aspect", "all"), ("review-status", "all"), ("health", "all")):
        search.add_argument("--" + name, default=default)
    search.add_argument("--page", type=int, default=1)
    search.add_argument("--page-size", type=int, default=24)
    search.add_argument("--min-duration", type=float)
    search.add_argument("--max-duration", type=float)
    for name in ("detail", "health", "observations"):
        commands.add_parser(name).add_argument("media_id")
    relink = commands.add_parser("relink")
    relink.add_argument("media_id"); relink.add_argument("path")
    for name in ("metadata", "import-project", "observe", "reference", "usage"):
        commands.add_parser(name).add_argument("json_path")
    for name in ("get-reference", "resolve"):
        commands.add_parser(name).add_argument("ref_id")
    use = commands.add_parser("usage-query")
    use.add_argument("--media-id", default=""); use.add_argument("--project-id", default="")
    alias = commands.add_parser("alias")
    alias.add_argument("namespace"); alias.add_argument("external_id")
    args = parser.parse_args(argv)
    kwargs = {"db_path": args.db}
    try:
        if args.command == "status": result = management.summary(**kwargs)
        elif args.command == "search":
            payload = {key: value for key, value in vars(args).items()
                       if key not in {"db", "output", "command"} and value is not None}
            result = management.search(payload, **kwargs)
        elif args.command == "detail":
            result = management.detail(args.media_id, **kwargs)
            result["observations"] = refs.list_observations(args.media_id, **kwargs)
            result["usage"] = refs.list_usage(media_id=args.media_id, **kwargs)
        elif args.command == "health": result = management.check_health(args.media_id, **kwargs)
        elif args.command == "relink": result = management.relink(args.media_id, args.path, **kwargs)
        elif args.command == "observations": result = refs.list_observations(args.media_id, **kwargs)
        elif args.command == "get-reference": result = refs.get_reference(args.ref_id, **kwargs)
        elif args.command == "resolve": result = refs.resolve_reference(args.ref_id, **kwargs)
        elif args.command == "usage-query": result = refs.list_usage(media_id=args.media_id, project_id=args.project_id, **kwargs)
        elif args.command == "alias": result = refs.lookup_alias(args.namespace, args.external_id, **kwargs)
        else:
            payload = json.loads(Path(args.json_path).read_text(encoding="utf-8-sig"))
            function = {"metadata": management.update_metadata, "import-project": refs.import_project,
                        "observe": refs.save_observation, "reference": refs.freeze_reference,
                        "usage": refs.record_usage}[args.command]
            result = function(payload, **kwargs)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0
    except (management.MaterialConflictError, refs.MaterialReferenceConflictError) as exc:
        print(json.dumps({"error": str(exc), "status": "conflict"}, ensure_ascii=False)); return 3
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False)); return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
