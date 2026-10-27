"""List Hallmark references or create a video direction brief; no render or paid calls."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot import studio_art_direction as art


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('list')
    sub.add_parser('verify')
    item = sub.add_parser('brief')
    item.add_argument('theme_slug')
    item.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'list':
        result = art.catalog()
    elif args.action == 'verify':
        result = art.verify_references()
    else:
        result = art.video_brief(args.theme_slug)
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if getattr(args, 'output', None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(serialized)
    print(serialized)
    if args.action == 'verify' and not result['valid']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
