"""Prepare /2 fixed public components; does not claim or execute production."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description='公开动效组件/2只读核验或独立冻结')
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--queue-db', type=Path, help='冻结时明确指定所属SQLite队列；不领取')
    parser.add_argument('--projects-root', type=Path, help='冻结时明确指定所属项目根目录')
    parser.add_argument('--output-request', type=Path)
    args = parser.parse_args(argv)
    from backlot import motion_public_production_v2 as producer
    try:
        if not args.input.is_file() or args.input.is_symlink() or args.input.stat().st_size > 8*1024*1024:
            raise ValueError('本期输入不存在、过大或为链接')
        if args.output_request and args.output_request.exists():
            raise ValueError('另存目标已存在，请保留原记录')
        value = json.loads(args.input.read_text('utf-8-sig'))
        if args.check:
            n = producer.preflight(value)
            result = {'status': 'validated', 'contract': producer.CONTRACT, 'frames': n['frames'], 'duration': n['duration']}
        else:
            if not args.queue_db or not args.projects_root:
                raise ValueError('冻结须明确提供--queue-db与--projects-root')
            from backlot.production_queue import ProductionQueue
            queue = ProductionQueue(args.queue_db, args.projects_root)
            request = producer.prepare(queue, value)
            if args.output_request:
                producer.atomic_private(args.output_request, request)
            result = {'status': 'prepared', 'contract': producer.CONTRACT, 'request_sha256': request['request_sha256'],
                      'project_id': request['project_id'], 'render_id': request['render_id'], 'submitted': False}
        print(json.dumps({**result, 'paid_calls': 0, 'publication': False}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, ImportError) as exc:
        print(json.dumps({'status': 'blocked', 'error_type': type(exc).__name__,
                          'message': str(exc) if isinstance(exc, producer.WorkError) else
                          '输入、指定项目位置或/2固定执行模块尚未就绪；保留旧任务，不回落旧合同。'}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
