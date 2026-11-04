#!/usr/bin/env python3
"""Read-only motion contract validation and existing-renderer preparation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot import motion_replay


def main():
    parser = argparse.ArgumentParser(description='动效模板复刻合同与输入准备；不渲染或付费')
    parser.add_argument('command', choices=['catalog', 'verify', 'prepare'])
    parser.add_argument('--template-id')
    parser.add_argument('--version')
    parser.add_argument('--request', type=Path, help='适配器输入JSON文件；仅prepare使用')
    args = parser.parse_args()
    try:
        if args.command == 'catalog':
            value = {'templates': motion_replay.catalog(), 'sources_verified': False}
        elif args.command == 'verify':
            templates = ([motion_replay.resolve(args.template_id, args.version)]
                         if args.template_id else motion_replay.load_registry())
            value = {'templates': [{'template_id': item['template_id'],
                       'version': item['version'],
                       'sources': motion_replay.verify_sources(item)} for item in templates],
                     'scope': '合同、动作引用及来源身份；不代表画面、声音或生产接入通过'}
        else:
            value = motion_replay.prepare(args.template_id, args.version,
                      json.loads(args.request.read_text(encoding='utf-8')) if args.request else {})
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, ImportError) as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
