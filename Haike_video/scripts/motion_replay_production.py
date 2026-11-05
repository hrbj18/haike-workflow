"""Queue-only CLI for frozen motion production; no arbitrary JSON commands."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def prepare_platform_environment():
    """An Agent's fresh Mac shell uses the same pinned tools as the launcher."""
    if sys.platform != 'darwin':
        return
    spec = importlib.util.spec_from_file_location('haike_motion_cli_mac', ROOT.parent / 'scripts/mac-deploy.py')
    deployment = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deployment)
    os.environ.update(deployment.environment(deployment.architecture()))


def main():
    parser = argparse.ArgumentParser(description='完整动效父视频统一队列入口')
    sub = parser.add_subparsers(dest='command', required=True)
    submit = sub.add_parser('submit', help='校验所属适配器的冻结请求并暂停入队，不生成视频')
    submit.add_argument('--request', required=True)
    submit.add_argument('--phase', choices=['audio', 'asr', 'avatar', 'frames', 'preview', 'render'])
    execute = sub.add_parser('execute', help='按原编号领取执行，不自动重试失败或未知任务')
    execute.add_argument('--job-id', required=True)
    execute.add_argument('--confirmed', action='store_true')
    execute.add_argument('--resume-local', action='store_true', help='明确恢复可重试的原本地合成，不适用于付费或受理未知阶段')
    status = sub.add_parser('status', help='只读查询原队列编号')
    status.add_argument('--job-id', required=True)
    args = parser.parse_args()
    try:
        prepare_platform_environment()
        from backlot.motion_reference_public_queue_v1 import MotionReferencePublicProductionQueue as ProductionQueue
        from backlot.server import PROJECTS_DIR, _production_queue_db_path
        from backlot import motion_replay_production as production
        queue = ProductionQueue(_production_queue_db_path(), PROJECTS_DIR)
        if args.command == 'submit':
            request = Path(args.request)
            if not request.is_file() or request.is_symlink() or request.stat().st_size > 8 * 1024 * 1024:
                raise ValueError('冻结请求不存在、过大或不是普通文件')
            result = production.submit_frozen(queue, json.loads(request.read_text(encoding='utf-8-sig')), phase=args.phase)
        elif args.command == 'execute':
            from lib.env_loader import load_env
            load_env(ROOT)
            from backlot.studio_services import refresh_private_environment
            refresh_private_environment()
            result = production.execute(queue, args.job_id, confirmed=args.confirmed, resume_local=args.resume_local)
        else:
            result = production.status(queue, args.job_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        from lib.bailian_speech import safe_error
        print(json.dumps({'status':'blocked','message':safe_error(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
