"""Build a real 4:5 input; optionally hand it to the existing unified queue CLI."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backlot import studio_native_story_portrait as story
from backlot import studio_dark_native_content as content
from backlot.studio import atomic_private
from backlot.work_catalog import read_json, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check', action='store_true', help='Read-only media and clock checks')
    parser.add_argument('--render', action='store_true', help='Freeze and run the existing parent queue; no paid provider calls')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--presenter-mode', choices=('auto','small','hidden'), default='auto',
                        help='auto按动作使用大框/圆窗；small始终圆窗；hidden不显示口播人物。不生成新人。')
    args = parser.parse_args()
    if args.check and args.render: parser.error('check and render are mutually exclusive')
    value = story.convert(content.load_build(args.build))
    if args.presenter_mode == 'small':
        clip = value['props']['presenter']
        clip['modes'] = [{'from': clip['from'], 'frames': clip['frames'], 'mode': 'small'}]
    elif args.presenter_mode == 'hidden':
        clip = value['props'].pop('presenter')
        value['sources'].pop(clip['src'])
        value['provenance']['presenterClips'] = []
    normalized = story.dark.preflight(value)
    record = {'valid': True, 'engine': 'project-editable-remotion', 'native_4x5': False,
              'layout': '1440x1800-reflow', 'frames': normalized['props']['durationFrames'], 'fps': 60,
              'seconds': normalized['props']['durationFrames']/60, 'cloud_calls': 0,
              'build': str(args.build.resolve()), 'build_sha256': sha(args.build), 'presenter_mode': args.presenter_mode}
    if not args.check:
        output = args.output or args.build.with_name('portrait-input'+('' if args.presenter_mode=='auto' else '-'+args.presenter_mode)+'.json')
        if output.exists() and read_json(output) != value:
            raise RuntimeError('4:5输入已有不同版本；保留原输入并使用新输出路径')
        atomic_private(output, value); record['input'] = str(output.resolve())
        if args.render:
            command = [sys.executable, str(ROOT/'scripts/dark_full.py'), '--input', str(output.resolve())]
            if args.output_dir: command += ['--output-dir', str(args.output_dir.resolve())]
            subprocess.run(command, check=True)
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__': main()
