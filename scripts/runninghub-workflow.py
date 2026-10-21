"""Read or explicitly save the Agent's workflow preference; never call providers."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFERENCE = ROOT / '.local/runninghub-workflow/default.json'
WORKFLOWS = {
    'economy': {'name': '性价比数字人', 'workflow_id': '2094449979141218305',
                'entry': 'START_HERE.md', 'scope': 'Studio及统一队列现有生产入口'},
    'high-quality': {'name': '高质量数字人 V5.3.1', 'workflow_id': '2112180419025260546',
                     'entry': 'Haike_video/workflows/runninghub-high-quality/README.md',
                     'scope': '独立生成入口；正式父视频仍需统一队列适配与验收'},
}


def selected(path=PREFERENCE):
    if not path.exists():
        return 'economy'
    value = json.loads(path.read_text(encoding='utf-8'))['default']
    if value not in WORKFLOWS:
        raise ValueError('默认工作流无效，请明确重新选择；不会自动换工作流')
    return value


def select(value, confirmed, path=PREFERENCE):
    if not confirmed or value not in WORKFLOWS:
        raise ValueError('修改默认需用户明确指定，并传 --confirm-default-change')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'default': value}, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['show', 'select'], nargs='?', default='show')
    parser.add_argument('--workflow', choices=WORKFLOWS)
    parser.add_argument('--confirm-default-change', action='store_true')
    args = parser.parse_args()
    if args.action == 'select':
        select(args.workflow, args.confirm_default_change)
    print(json.dumps({'default': selected(), 'workflows': WORKFLOWS,
                      'scope': 'Agent新任务偏好；既有任务和Studio供应商配置保持原冻结路由'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
