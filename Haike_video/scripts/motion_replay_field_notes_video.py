"""Queue-only Field Notes video entry. Paid stages require explicit private receipts."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Haike_video'))
from backlot import motion_replay_field_notes_video as production
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from lib.checkpoint import init_project


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--phase',choices=['frames','render'],required=True)
    parser.add_argument('--enqueue-only',action='store_true')
    args=parser.parse_args()
    data=args.data.resolve(); request=production.admit(ROOT,data,phase=args.phase)
    projects=ROOT/'Haike_video/projects'; project=request['project_id']
    spec=production.read(data/'production.json')
    init_project(project,title=spec['title'],pipeline_type='animated-explainer',pipeline_dir=projects)
    queue=ProductionQueue(ROOT/'Haike_video/.backlot/production-queue.sqlite3',projects)
    job=queue.submit(project_id=project,kind='studio_investment_recompose',source='codex',priority='normal',
        parent_job_id=request['render_id'],frozen_request=request,idempotency_key=production.CONTRACT+':'+request['render_id'],start_paused=True)
    production.write(data/(args.phase+'-queue-job.json'),{'job_id':job['job_id'],'project_id':project,'render_id':request['render_id']})
    if not args.enqueue_only and job['status']=='paused':
        job=ProductionQueueWorker(queue,projects,worker_id='field-notes-'+args.phase,lease_seconds=300).run_local_recompose(job['job_id'])
    print(json.dumps({'job_id':job['job_id'],'project_id':project,'phase':args.phase,'status':job['status']},ensure_ascii=False),flush=True)
    return 0 if args.enqueue_only or job['status']=='completed' else 2


if __name__=='__main__':
    raise SystemExit(main())
