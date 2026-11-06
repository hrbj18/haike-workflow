"""Local dialogue Agent entry; suppliers and actual rendering remain project tools."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

MODULE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE))


def main():
    parser = argparse.ArgumentParser(description='数字人口播内的一条龙Agent调用功能')
    parser.add_argument('--projects-root', type=Path)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('defaults')
    sub.add_parser('list')
    create = sub.add_parser('create')
    create.add_argument('--portrait', type=Path, required=True)
    create.add_argument('--audio', type=Path, required=True)
    create.add_argument('--audio-role', choices=['sample', 'narration'], default='sample')
    create.add_argument('--text-file', type=Path)
    create.add_argument('--title')
    create.add_argument('--request-id', default='')
    create.add_argument('--draft-id')
    create.add_argument('--speech-rate', type=float)
    revise = sub.add_parser('revise')
    revise.add_argument('id')
    revise.add_argument('--speech-rate', type=float, required=True)
    revise.add_argument('--synthesis-seed', type=int)
    revise.add_argument('--reason-file', type=Path, required=True)
    revise.add_argument('--request-id', default='')
    for name in ('get', 'context', 'advance', 'run', 'apply', 'adopt-image', 'file'):
        command = sub.add_parser(name)
        command.add_argument('id')
        if name == 'apply':
            command.add_argument('--json-file', type=Path, required=True)
        if name == 'adopt-image':
            command.add_argument('--image-file', type=Path, required=True)
            command.add_argument('--sha256', required=True)
            command.add_argument('--reason-file', type=Path, required=True)
        if name == 'file':
            command.add_argument('kind', choices=['source', 'reference', 'sample', 'refined', 'audition', 'narration', 'video', 'cover', 'contact-sheet'])
        if name == 'run':
            command.add_argument('--max-wait', type=int, default=900)
    args = parser.parse_args()
    from lib.env_loader import load_env
    load_env(MODULE)
    from backlot.avatar_one_stop import OneStop
    from backlot.studio import Studio
    from lib.paths import PROJECTS_DIR
    service = OneStop(Studio(args.projects_root or PROJECTS_DIR))
    if args.action == 'create':
        defaults = service.defaults()
        draft = service.studio.draft(args.draft_id) if args.draft_id else service.studio.save_draft({
            'template_id': 'avatar-safe-circle-v1', 'title': args.title or defaults['title'],
            'text': defaults['text'], 'input': {'motion_production': {
                'gallery_id': 'chromatic-six-11', 'template_id': 'chromatic-six-11',
                'version': defaults['template']['version'],
                'production_contract': 'motion-replay-chromatic-suite-production-v1'}}})
        assets = {kind: service.studio.save_asset(draft['id'], path.name, kind, path.read_bytes())
                  for kind, path in [('image', args.portrait), ('audio', args.audio)]}
        request = {'draft_id': draft['id'], 'portrait_id': assets['image']['id'], 'audio_id': assets['audio']['id'],
                   'audio_role': args.audio_role, 'request_id': args.request_id, 'consent': True}
        if args.title:
            request['title'] = args.title
        if args.text_file:
            request['text'] = args.text_file.read_text('utf-8-sig')
        if args.speech_rate is not None:
            request['speech_rate'] = args.speech_rate
        result = service.create(request)
        result['avatar_url'] = '/avatar?one_stop='+result['id']
    elif args.action == 'defaults':
        result = service.defaults()
    elif args.action == 'list':
        result = {'items': service.list()}
    elif args.action == 'context':
        result = service.context(args.id, private=True)
    elif args.action == 'get':
        result = service.get(args.id)
    elif args.action == 'revise':
        result = service.revise(args.id, {'speech_rate':args.speech_rate,
            'reason':args.reason_file.read_text('utf-8-sig'), 'request_id':args.request_id,
            **({'synthesis_seed': args.synthesis_seed} if args.synthesis_seed is not None else {})})
    elif args.action == 'apply':
        result = service.apply(args.id, json.loads(args.json_file.read_text('utf-8-sig')))
    elif args.action == 'adopt-image':
        result = service.adopt_image(args.id, args.image_file, observed_sha256=args.sha256,
                                     reason=args.reason_file.read_text('utf-8-sig'))
    elif args.action == 'file':
        result = {'path': str(service.file(args.id, args.kind))}
    else:
        deadline = time.monotonic()+(args.max_wait if args.action == 'run' else 0)
        while True:
            result = service.advance(args.id)
            if args.action != 'run' or result['status'] != 'waiting' or time.monotonic() >= deadline:
                break
            print(json.dumps(result, ensure_ascii=False), flush=True)
            time.sleep(3)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except Exception as error:
        from backlot.work_catalog import WorkError
        print(json.dumps({'status': 'paused', 'message': str(error) if isinstance(error, WorkError) else
                          '输入、配置或本地运行时未就绪；请核对原任务记录后继续，未自动重复付费调用',
                          'error_class': type(error).__name__}, ensure_ascii=False), flush=True)
        sys.exit(1)
