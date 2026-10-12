"""Manage the local archive of already-published video files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backlot.published_clip_index import (  # noqa: E402
    ClipIndexError, configured_source, get_video, import_interaction_index, import_visual_overview,
    list_videos, scan, search, summary,
)
from backlot.published_clip_transcription import transcribe_batch  # noqa: E402
from backlot import published_clip_analysis as analysis  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help="隔离数据库路径；正式库默认在 .backlot/published-clips/")
    commands = parser.add_subparsers(dest="command", required=True)
    p_scan = commands.add_parser("scan", help="只读原片，登记媒体元数据")
    p_scan.add_argument("--source", type=Path, required=True)
    p_transcribe = commands.add_parser("transcribe", help="使用已缓存的本地模型建立转写时间轴")
    p_transcribe.add_argument("--source", type=Path)
    p_transcribe.add_argument("--video-id")
    p_transcribe.add_argument("--limit", type=int)
    p_transcribe.add_argument("--force", action="store_true")
    p_transcribe.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    p_transcribe.add_argument("--model-path", type=Path)
    commands.add_parser("status")
    p_search = commands.add_parser("search")
    p_search.add_argument("query", nargs="?", default="")
    p_search.add_argument("--tag", default="")
    p_search.add_argument("--confirmed-only", action="store_true")
    p_search.add_argument("--limit", type=int, default=50)
    p_video = commands.add_parser("video")
    p_video.add_argument("video_id")
    p_import = commands.add_parser("import-interactions")
    p_import.add_argument("index", type=Path)
    p_visual = commands.add_parser("import-visual-overview")
    p_visual.add_argument("analysis", type=Path)
    p_analyze = commands.add_parser("analyze", help="本地声音与画面变化候选分析")
    p_analyze.add_argument("--source", type=Path)
    p_analyze.add_argument("--video-id")
    p_analyze.add_argument("--benchmark", action="store_true")
    p_analyze.add_argument("--force", action="store_true")
    p_analyze.add_argument("--limit", type=int, default=10)
    commands.add_parser("benchmark-init", help="冻结十条代表素材，不自动生成真值")
    commands.add_parser("benchmark-report", help="报告完整人工真值覆盖与识别质量")
    args = parser.parse_args()
    try:
        if args.command == "scan":
            result = scan(args.source, db_path=args.db)
        elif args.command == "transcribe":
            root = args.source or configured_source()
            if root is None:
                raise ClipIndexError("请先运行 scan --source 指定成片目录")
            def progress(row):
                print(json.dumps(row, ensure_ascii=False), flush=True)
            result = transcribe_batch(source_root=root, db_path=args.db,
                model_path=args.model_path, device=args.device, video_id=args.video_id,
                limit=args.limit, force=args.force, progress=progress)
        elif args.command == "status":
            result = {"summary": summary(db_path=args.db), "videos": list_videos(db_path=args.db)}
        elif args.command == "search":
            result = search(args.query, tag=args.tag, confirmed_only=args.confirmed_only,
                            db_path=args.db, limit=args.limit)
        elif args.command == "video":
            result = get_video(args.video_id, db_path=args.db)
        elif args.command == "import-interactions":
            result = import_interaction_index(args.index, db_path=args.db)
        elif args.command == "benchmark-init":
            result = analysis.seed_benchmark(db_path=args.db)
        elif args.command == "benchmark-report":
            cases = analysis.benchmark_cases(db_path=args.db)
            result = {"evaluation": analysis.evaluate(cases), "cases": cases}
        elif args.command == "analyze":
            root = args.source or configured_source()
            if root is None:
                raise ClipIndexError("请先配置成片目录")
            identities = ([args.video_id] if args.video_id else
                          [c["video_id"] for c in analysis.benchmark_cases(db_path=args.db)] if args.benchmark else
                          [v["id"] for v in list_videos(db_path=args.db)][:max(1, args.limit)])
            rows = []
            for identity in identities:
                try:
                    item = analysis.analyze(identity, source_root=root, db_path=args.db, force=args.force)
                    row = {"video_id": identity, "status": item["status"], "cached": item["cached"],
                           "candidates": (item.get("result") or {}).get("candidate_count", 0)}
                except Exception as exc:
                    row = {"video_id": identity, "status": "failed", "error": str(exc)}
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
            result = {"processed": len(rows), "failed": sum(r["status"] == "failed" for r in rows)}
            print(json.dumps(result, ensure_ascii=False))
            return 2 if result["failed"] else 0
        else:
            result = import_visual_overview(args.analysis, db_path=args.db)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ClipIndexError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
