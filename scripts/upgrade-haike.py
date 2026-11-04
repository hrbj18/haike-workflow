"""Unified Haike upgrade: inspect, fixed portable dispatch, or isolated Git source."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from portable import unified_upgrade as upgrade


def main(argv=None):
    parser = argparse.ArgumentParser(description='统一识别便携安装、历史布局和Git源码；保留原配置、作品与未提交修改')
    parser.add_argument('action', choices=['plan', 'apply', 'apply-candidate'])
    parser.add_argument('--target', type=Path, default=Path.cwd())
    parser.add_argument('--github-url', default=upgrade.OFFICIAL)
    parser.add_argument('--destination', type=Path, help='Git/隔离源码候选目录，必须位于原目标之外')
    parser.add_argument('--online', action='store_true', help='plan时核对官方清单；默认仅本地识别')
    parser.add_argument('--no-start', action='store_true', help='便携事务安装后不启动目标；正式自检仍按原事务执行')
    parser.add_argument('--candidate-feed', type=Path, help='仅供已标记隔离目标的本地候选清单')
    parser.add_argument('--test-release-base', help='候选验收的明确本机回环HTTP服务')
    parser.add_argument('--rollback', type=Path, help='候选隔离目标内原事务给出的备份目录')
    args = parser.parse_args(argv)
    try:
        if args.action == 'apply-candidate':
            if not args.candidate_feed:
                parser.error('apply-candidate需要--candidate-feed及独立测试目录标记')
            result = upgrade.apply_candidate(args.target, args.candidate_feed,
                test_release_base=args.test_release_base, rollback=args.rollback,destination=args.destination)
        elif args.action == 'plan':
            feed = upgrade.load_feed(args.github_url) if args.online else None
            result = {'ok': True, 'check_only': True, **upgrade.plan(args.target, args.github_url, feed=feed, destination=args.destination)}
        else:
            result = upgrade.execute(args.target, args.github_url, destination=args.destination, start=not args.no_start)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('ok',True) else 2
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({'ok': False, 'message': str(exc), 'original_tree_reset': False}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
