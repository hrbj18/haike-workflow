"""Prepare reusable story inputs; whole-film exports remain in the project queue."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backlot import studio_dark_native_content as content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check', help='只读校验本地输入、源时码与真实媒体；不创建制作任务')
    check.add_argument('--input', type=Path, required=True)
    build = commands.add_parser('build', help='本地提取素材并准备公开参数；不付费、不生成数字人、不渲染全片')
    build.add_argument('--input', type=Path, required=True)
    build.add_argument('--out', type=Path, required=True)
    for name, help_text in [('native-plan', '官方new/setup/check/plan；无全片或付费'),
                            ('native-prepare', '凭实际计划/源素材审核准备原生工程'),
                            ('native-preview', '有界关键帧预览，不是整片制作'),
                            ('native-manifest', '凭实际看帧审核生成统一队列输入；不入队')]:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument('--build', type=Path, required=True)
        if name in {'native-prepare', 'native-manifest'}:
            sub.add_argument('--review', type=Path, required=True)
        if name == 'native-preview':
            sub.add_argument('--times', required=True, help='逗号分隔的1至12个全片秒数')
    args = parser.parse_args()
    if args.command == 'check':
        result, _ = content.check(args.input)
        result = {'status': 'input_checked', 'layout': result['layout'], 'timeline': result['timeline'],
                  'read_only': True, 'cloud_calls': 0, 'queue_submitted': False}
    elif args.command == 'build':
        result = content.build(args.input, args.out)
        result = {k: result[k] for k in ['status', 'directory', 'layout', 'timeline', 'next_entrypoint', 'cloud_calls']}
        result['build'] = str(Path(result['directory']) / 'content-build.json')
    elif args.command == 'native-plan':
        result = content.native_plan(args.build)
    elif args.command == 'native-prepare':
        result = content.native_prepare(args.build, args.review)
    elif args.command == 'native-preview':
        result = content.native_preview(args.build, [float(v) for v in args.times.split(',')])
    else:
        result = content.native_manifest(args.build, args.review)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
