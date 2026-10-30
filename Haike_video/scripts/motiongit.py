"""Import, verify and edit MotionGit packages through the Haike project."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot import studio_motiongit as motion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('inspect', 'import'):
        sub.add_parser(name).add_argument('path', type=Path)
    sub.add_parser('list')
    sub.add_parser('verify').add_argument('package_id')
    sub.add_parser('check').add_argument('draft_id')
    sub.add_parser('clone').add_argument('draft_id')
    asset=sub.add_parser('asset');asset.add_argument('draft_id');asset.add_argument('path',type=Path);asset.add_argument('--slot')
    for name in ('preview','render'):
        item=sub.add_parser(name);item.add_argument('draft_id')
    for name in ('review','review-plan'):
        review=sub.add_parser(name);review.add_argument('request',type=Path);review.add_argument('evidence',type=Path)
    resume=sub.add_parser('resume');resume.add_argument('request',type=Path);resume.add_argument('--phase',choices=['preview','render'],default='render')
    save = sub.add_parser('save')
    save.add_argument('package_id'); save.add_argument('workflow'); save.add_argument('input', type=Path)
    save.add_argument('--draft-id'); save.add_argument('--revision', type=int, default=0); save.add_argument('--title', default='新视频')
    save.add_argument('--output-profile',choices=['native','4:5'],default='native')
    args = parser.parse_args()
    if args.action == 'inspect': result = motion.inspect_package(args.path)
    elif args.action == 'import': result = motion.import_package(args.path)
    elif args.action == 'list': result = motion.packages()
    elif args.action == 'verify': result = motion.verify_package(args.package_id)
    elif args.action == 'check': result = motion.validate_draft(args.draft_id)
    elif args.action == 'clone': result = motion.clone_draft(args.draft_id)
    elif args.action == 'asset':
        motion.require(args.path.is_file() and 0<args.path.stat().st_size<=motion.MAX_PACKAGE,'素材缺失或超过大小限制')
        result=motion.save_asset(args.draft_id,args.slot or args.path.name,args.path.read_bytes())
    elif args.action in {'preview','render','review','review-plan','resume'}:
        from backlot import studio_motiongit_render as render
        from backlot.production_queue import ProductionQueue, ProductionQueueConflict
        from backlot.production_queue_worker import ProductionQueueWorker
        root=Path(__file__).resolve().parents[1]
        queue=ProductionQueue(root/'.backlot/production-queue.sqlite3',root/'projects')
        if args.action in {'review','review-plan'}:
            function=render.review_plan if args.action=='review-plan' else render.review
            result=function(queue,json.loads(args.request.read_text(encoding='utf-8')),json.loads(args.evidence.read_text(encoding='utf-8')))
        else:
            request=json.loads(args.request.read_text(encoding='utf-8')) if args.action=='resume' else render.freeze(queue,args.draft_id)
            job=render.submit(queue,request,phase=args.phase if args.action=='resume' else args.action)
            print(json.dumps({'job_id':job['job_id'],'project_id':request['project_id'],'render_id':request['render_id']},ensure_ascii=False),flush=True)
            try:
                result=job if job['status']=='completed' else ProductionQueueWorker(queue,queue.projects_root,worker_id='motiongit-cli',lease_seconds=7200).run_local_recompose(job['job_id'])
            except ProductionQueueConflict:
                result={'status':'paused','job_id':job['job_id'],'project_id':request['project_id'],
                        'message':'统一生产队列忙；原任务已保留，稍后用同一草稿恢复。'}
    else:
        result = motion.save_draft(args.package_id, args.workflow, json.loads(args.input.read_text(encoding='utf-8-sig')),
                                   draft_id=args.draft_id, revision=args.revision, title=args.title,output_profile=args.output_profile)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
