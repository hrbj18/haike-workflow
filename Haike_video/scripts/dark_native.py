"""Freeze or resume an actually reviewed full native reference through the queue."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backlot import studio_dark_native as adapter
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.work_catalog import read_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--input',type=Path);group.add_argument('--request',type=Path)
    parser.add_argument('--freeze-only',action='store_true')
    args=parser.parse_args();queue=ProductionQueue(ROOT/'.backlot/production-queue.sqlite3',ROOT/'projects')
    r=adapter.prepare(queue,read_json(args.input)) if args.input else read_json(args.request)
    project=adapter.validate(queue,r)
    print(json.dumps({'project_id':r['project_id'],'render_id':r['render_id'],'request':str(project/'artifacts'/adapter.REQUEST_FILE)},ensure_ascii=False),flush=True)
    if args.freeze_only:return
    job=adapter.submit(queue,r)
    if job['status']!='completed':job=ProductionQueueWorker(queue,queue.projects_root,worker_id='dark-native-cli',lease_seconds=14400).run_local_recompose(job['job_id'])
    print(json.dumps({'job_id':job['job_id'],'status':job['status'],'result':job.get('result'),'error':job.get('error')},ensure_ascii=False),flush=True)
    if job['status']!='completed':raise RuntimeError('原生制作未完成，沿原request恢复')


if __name__=='__main__':main()
