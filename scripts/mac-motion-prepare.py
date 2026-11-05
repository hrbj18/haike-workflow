"""Mac preparation for fixed motion controllers; never claims or renders a job."""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Haike_video'))
DIRECTORY_CONTRACTS = {
    'motion-replay-numbered-02-05-production-v1', 'haike-field-notes-video-production-v1',
}


def admit_directory(producer, value):
    """Keep prepared-directory admission read-only and strictly local."""
    if not isinstance(value, dict) or not {'data'} <= set(value) <= {'data', 'phase'}:
        raise ValueError('目录型模板仅接受data与可选phase')
    phase = value.get('phase', 'frames')
    if phase not in {'frames', 'render'}:
        raise ValueError('Mac本地准备入口只接受frames/render，不发起付费阶段')
    return producer.admit(ROOT, value['data'], phase=phase)


def main():
    from backlot.motion_replay_production import PRODUCERS
    parser = argparse.ArgumentParser()
    parser.add_argument('--contract', choices=list(PRODUCERS), required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--queue-db', type=Path)
    parser.add_argument('--projects-root', type=Path)
    parser.add_argument('--output-request', type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('mac_motion_deployment', ROOT / 'scripts/mac-deploy.py')
    deployment = importlib.util.module_from_spec(spec); spec.loader.exec_module(deployment)
    os.environ.update(deployment.environment(deployment.architecture()))
    from backlot.motion_replay_production import _producer
    producer = _producer({'contract': args.contract})
    if not args.input.is_file() or args.input.is_symlink() or args.input.stat().st_size > 8*1024*1024:
        raise ValueError('本期输入不存在、过大或为链接')
    value = json.loads(args.input.read_text('utf-8-sig'))
    if args.check:
        if args.contract in DIRECTORY_CONTRACTS:
            normalized = admit_directory(producer, value)
        elif args.contract == 'haike.knowledge-reference-public/3':
            if not isinstance(value, dict) or set(value) != {'data'}:
                raise ValueError('知识模板仅接受已准备的data目录')
            normalized, _ = producer.execution.validate(value['data'])
            producer.identity(value['data'])
        elif hasattr(producer, 'preflight'):
            normalized = producer.preflight(value)
        else:
            raise ValueError('此模板使用专属准备目录，请按原runbook通过统一契约准备')
        result = {'status': 'validated', 'contract': args.contract, 'frames': normalized.get('frames'), 'submitted': False}
    else:
        if not args.queue_db or not args.projects_root or not args.output_request or args.output_request.exists():
            raise ValueError('冻结须提供本副本队列、项目目录和未占用的另存请求位置')
        from backlot.motion_reference_public_queue_v1 import MotionReferencePublicProductionQueue
        queue = MotionReferencePublicProductionQueue(args.queue_db, args.projects_root)
        request = admit_directory(producer, value) if args.contract in DIRECTORY_CONTRACTS else producer.prepare(queue, value)
        args.output_request.parent.mkdir(parents=True, exist_ok=True)
        args.output_request.write_text(json.dumps(request, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        result = {'status': 'prepared', 'project_id': request['project_id'], 'contract': args.contract, 'submitted': False}
    print(json.dumps({**result, 'platform_adapter': 'haike.motion-native-adapter/1', 'paid_calls': 0, 'publication': False}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
