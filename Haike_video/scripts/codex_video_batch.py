"""Local CLI; no background worker, scheduler, or direct supplier client."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HAIKE = Path(__file__).resolve().parents[1]
if str(HAIKE) not in sys.path:
    sys.path.insert(0, str(HAIKE))

from backlot.codex_batch import BatchError, CodexBatch, LocalAPI


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("defaults", "resolve", "init", "prepare", "submit", "status", "resume", "report", "approve", "publish", "advance", "material-context", "material-apply", "budget-amend"))
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--slot", help="只处理一个明确槽位；省略则依规格顺序")
    parser.add_argument("--evidence", type=Path, help="approve/publish/budget-amend必需，advance可选：明确授权或本批实际审查证据JSON")
    parser.add_argument("--analysis", type=Path, help="material-apply专用：当前Agent实际观看后提交的分镜/素材分析JSON")
    parser.add_argument("--base", default="http://127.0.0.1:14756")
    parser.add_argument("--output", type=Path, help="defaults专用：写入补全后的新规格文件；已有文件不覆盖")
    args = parser.parse_args(argv)
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        if args.command in {"material-context", "material-apply"} and not args.slot:
            raise BatchError("素材分析命令必须提供明确--slot")
        if args.command == "material-apply" and args.analysis is None:
            raise BatchError("material-apply需要--analysis JSON；提交不会自动resume")
        if args.analysis is not None and args.command != "material-apply":
            raise BatchError("--analysis仅用于material-apply")
        if args.command == "defaults":
            from backlot.codex_batch_defaults import resolve_spec_defaults
            if not args.output or args.output.exists() or args.slot:
                raise BatchError("defaults需要新的--output路径；已有完整规格直接用于后续命令，不重新解析")
            resolved = resolve_spec_defaults(spec, api=LocalAPI(args.base))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            from lib.bailian_speech import operation_lock, write_record
            with operation_lock(args.output.parent / (args.output.name + ".lock")):
                if args.output.exists():
                    raise BatchError("完整规格已经存在，请读取原文件继续")
                write_record(args.output, resolved)
            print(json.dumps({"ok": True, "spec": str(args.output), "items": len(resolved["items"]),
                              "limit_micros": resolved["limit_micros"], "production_started": False}, ensure_ascii=False))
            return 0
        batch = CodexBatch(spec, api=LocalAPI(args.base))
        if args.command == "budget-amend":
            if args.evidence is None or args.slot:
                raise BatchError("budget-amend需要整批明确预算授权--evidence，不能单槽位修订")
            result = batch.amend_budget(json.loads(args.evidence.read_text(encoding="utf-8")))
        elif args.command == "material-context":
            result = batch.material_context(args.slot)
        elif args.command == "material-apply":
            result = batch.material_apply(json.loads(args.analysis.read_text(encoding="utf-8")), args.slot)
        elif args.command == "advance":
            evidence = json.loads(args.evidence.read_text(encoding="utf-8")) if args.evidence else None
            result = batch.advance(evidence, args.slot)
        elif args.command in {"approve", "publish"}:
            if args.evidence is None:
                raise BatchError("approve/publish必须提供明确审批证据，不从技术解码推定人工观看")
            result = getattr(batch, args.command)(json.loads(args.evidence.read_text(encoding="utf-8")), args.slot)
        elif args.command in {"resolve", "init"}:
            if args.slot:
                raise BatchError("resolve/init核对整个批次，不接受单槽位")
            result = getattr(batch, args.command)()
        else:
            result = getattr(batch, args.command)(args.slot)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get("ok") is False else 0
    except BatchError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "unknown_result": exc.unknown,
                          "action": "保留规格与原任务；先status/report核对，禁止换编号重复提交"}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError):
        print(json.dumps({"ok": False, "error": "规格/证据文件或API结构不可用，未自动重试"}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
