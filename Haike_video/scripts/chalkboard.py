"""粉笔黑板双比例模板：检查、预览审核、统一队列导出及原请求恢复。"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backlot import studio_chalkboard as template
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.work_catalog import read_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['check','prepare','review','render','status'])
    parser.add_argument('--input',type=Path)
    parser.add_argument('--request',type=Path)
    parser.add_argument('--evidence',type=Path)
    args=parser.parse_args()
    queue=ProductionQueue(ROOT/'.backlot/production-queue.sqlite3',ROOT/'projects')
    if args.action=='check':
        value=read_json(args.input)
        print(json.dumps({'valid':True,'seconds':template.validate(value['props'])},ensure_ascii=False))
        return
    request=read_json(args.request) if args.request else template.freeze(queue,read_json(args.input))
    request_path=queue.projects_root/request['project_id']/'artifacts/chalkboard-request.json'
    print(json.dumps({'request':str(request_path),'project_id':request['project_id']},ensure_ascii=False),flush=True)
    if args.action=='review':
        evidence=read_json(args.evidence)
        result=template.review(queue,request,evidence['seen'],evidence['description'])
    elif args.action=='status':
        result={'project':str(queue.projects_root/request['project_id']),'render_id':request['render_id']}
    else:
        phase='preview' if args.action=='prepare' else 'render'
        job=template.submit(queue,request,phase)
        print(json.dumps({'job_id':job['job_id'],'status':job['status'],'phase':phase}),flush=True)
        result=job if job['status']=='completed' else ProductionQueueWorker(queue,queue.projects_root,
            worker_id='chalkboard-cli',lease_seconds=14400).run_local_recompose(job['job_id'])
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if isinstance(result,dict) and result.get('status')=='failed':
        raise SystemExit(1)


if __name__=='__main__':
    main()
