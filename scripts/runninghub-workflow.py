"""Read or explicitly save the Agent's workflow preference; never call providers."""
import argparse
import json
import math
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


def preference(path=PREFERENCE):
    if not path.exists():
        return {'default': 'economy'}
    value = json.loads(path.read_text(encoding='utf-8'))
    if value['default'] not in WORKFLOWS:
        raise ValueError('默认工作流无效，请明确重新选择；不会自动换工作流')
    rule = value.get('duration_rule')
    if rule is not None and (not isinstance(rule, dict) or rule.get('workflow') not in WORKFLOWS
                             or type(rule.get('max_video_seconds')) not in (int, float)
                             or not math.isfinite(rule['max_video_seconds']) or rule['max_video_seconds'] <= 0):
        raise ValueError('时长条件无效，不会静默切换工作流')
    return value


def selected(path=PREFERENCE, duration_seconds=None):
    value = preference(path)
    if duration_seconds is not None:
        if type(duration_seconds) not in (int, float) or not math.isfinite(duration_seconds) or duration_seconds <= 0:
            raise ValueError('视频总时长必须为正数；不能使用出镜片段累计时长代替')
        rule = value.get('duration_rule')
        if rule and duration_seconds <= rule['max_video_seconds']:
            return rule['workflow']
    return value['default']


def select(value, confirmed, path=PREFERENCE, max_video_seconds=None):
    if not confirmed or value not in WORKFLOWS:
        raise ValueError('修改默认需用户明确指定，并传 --confirm-default-change')
    payload = {'default': value}
    if max_video_seconds is not None:
        if type(max_video_seconds) not in (int, float) or not math.isfinite(max_video_seconds) or max_video_seconds <= 0:
            raise ValueError('默认规则的视频时长上限必须为正数')
        payload = {'default': preference(path)['default'],
                   'duration_rule': {'workflow': value, 'max_video_seconds': max_video_seconds}}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['show', 'select'], nargs='?', default='show')
    parser.add_argument('--workflow', choices=WORKFLOWS)
    parser.add_argument('--confirm-default-change', action='store_true')
    parser.add_argument('--max-video-seconds', type=float, help='仅为不超过此总时长的新视频保存默认规则')
    parser.add_argument('--duration-seconds', type=float, help='新视频完整时长；不是数字人出镜累计时长')
    args = parser.parse_args()
    if args.action == 'select':
        select(args.workflow, args.confirm_default_change, max_video_seconds=args.max_video_seconds)
    print(json.dumps({'default': selected(duration_seconds=args.duration_seconds),
                      'preference': preference(), 'duration_seconds': args.duration_seconds, 'workflows': WORKFLOWS,
                      'scope': 'Agent新任务偏好；既有任务和Studio供应商配置保持原冻结路由'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
