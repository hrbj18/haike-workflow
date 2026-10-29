"""Agent-neutral client for the MotionGit web production API (no Codex SDK)."""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', default='http://127.0.0.1:14756')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('catalog'); sub.add_parser('list')
    create = sub.add_parser('create'); create.add_argument('--template', default='motiongit-native-story-v1'); create.add_argument('--script', type=Path); create.add_argument('--preset'); create.add_argument('--source-session')
    get = sub.add_parser('get'); get.add_argument('session')
    action = sub.add_parser('action'); action.add_argument('session'); action.add_argument('action', choices=['save', 'clone', 'preset', 'source-quote', 'source-submit', 'source-resume', 'source-frames', 'source-review', 'prepare', 'plan-review', 'preview-review', 'submit', 'resume', 'local-resume']); action.add_argument('--data', type=Path, required=True)
    review = sub.add_parser('review'); review.add_argument('session')
    upload = sub.add_parser('upload'); upload.add_argument('session'); upload.add_argument('--revision', type=int, required=True); upload.add_argument('--slot', required=True); upload.add_argument('--kind', choices=['image', 'audio', 'video'], required=True); upload.add_argument('--file', type=Path, required=True)
    args = p.parse_args(); root = args.base.rstrip('/'); prefix = root+'/api/studio/motion-templates'
    body = None; method = 'GET'; content_type = 'application/json'
    if args.command == 'catalog': url = prefix+'/catalog'
    elif args.command == 'list': url = prefix+'/sessions'
    elif args.command == 'create':
        url = prefix+'/sessions'; method = 'POST'; value = {'template_id': args.template}
        if args.script: value['script'] = args.script.read_text(encoding='utf-8-sig')
        if args.preset: value['preset_id'] = args.preset
        if args.source_session: value['source_session_id'] = args.source_session
        body = json.dumps(value, ensure_ascii=False).encode()
    else:
        if not args.session.startswith('mts-') or not all(c in '0123456789abcdef' for c in args.session[4:]) or len(args.session) != 28: p.error('制作编号无效')
        url = prefix+'/sessions/'+args.session
        if args.command == 'review': url += '/review'
        elif args.command == 'action':
            if args.action != 'save': url += '/'+args.action
            method = 'POST'; body = json.dumps(json.loads(args.data.read_text(encoding='utf-8-sig')), ensure_ascii=False).encode()
        elif args.command == 'upload':
            from urllib.parse import urlencode
            url += '/assets?'+urlencode({'revision': args.revision, 'slot': args.slot, 'kind': args.kind, 'filename': args.file.name})
            method = 'POST'; content_type = 'application/octet-stream'; body = args.file.read_bytes()
    request = Request(url, data=body, method=method, headers={'Content-Type': content_type, 'Origin': root})
    try:
        with urlopen(request, timeout=180) as response: value = json.load(response)
    except HTTPError as exc:
        try: message = json.load(exc).get('detail', '操作未完成')
        except ValueError: message = '工作台没有返回有效结果'
        raise SystemExit(str(message)) from None
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
