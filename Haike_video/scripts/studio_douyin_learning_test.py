"""Bounded local learning test, deliberately absent from production HTTP/queue APIs."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot.studio import Studio
from backlot.studio_douyin_learning import require_learning_scope, run_learning_test
from backlot.work_catalog import WorkError


def main(argv=None):
    parser = argparse.ArgumentParser(description="本地学习测试：机器人搜索一页、最多下载1条并登记素材库")
    parser.add_argument("--purpose", required=True, choices=["learning_test"])
    parser.add_argument("--confirm", action="store_true", help="明确仅本地学习测试，不构成商用授权")
    parser.add_argument("--run-id", required=True, help="唯一编号；原编号不重复采集")
    parser.add_argument("--projects-root", type=Path, default=Path(__file__).resolve().parents[1] / "projects")
    parser.add_argument("--workbench-url", default="http://127.0.0.1:14756")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--search-only", action="store_true", help="只保存无签名URL的安全候选，不下载；编号不可重采")
    mode.add_argument("--register-only", action="store_true", help="仅恢复此编号已有文件入库，不重新搜索或下载")
    args = parser.parse_args(argv)
    try:
        require_learning_scope(args.purpose, args.confirm)
        result = run_learning_test(Studio(args.projects_root), run_id=args.run_id,
            purpose=args.purpose, confirmed=args.confirm, workbench_url=args.workbench_url,
            search_only=args.search_only, register_only=args.register_only)
    except WorkError as exc:
        parser.exit(1, str(exc) + "\n")
    except Exception:
        parser.exit(1, "学习测试暂未完成，请查看原编号安全记录；已有文件不重新下载。\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
