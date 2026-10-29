"""Validate, freeze, produce and resume the complete editable multi-screen template."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backlot import studio_dark_full as adapter
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import atomic_private
from backlot.work_catalog import read_json,sha


def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True);g.add_argument('--input',type=Path);g.add_argument('--request',type=Path)
    p.add_argument('--check',action='store_true');p.add_argument('--freeze-only',action='store_true');p.add_argument('--output-dir',type=Path)
    a=p.parse_args();q=ProductionQueue(ROOT/'.backlot/production-queue.sqlite3',ROOT/'projects')
    if a.input and a.check:
        n=adapter.preflight(read_json(a.input));print(json.dumps({'valid':True,'frames':n['props']['durationFrames'],'fps':n['props']['fps'],'seconds':n['props']['durationFrames']/n['props']['fps'],'voice_clock':n['audio']['voice_clock'],'cloud_calls':0},ensure_ascii=False));return
    r=adapter.prepare(q,read_json(a.input)) if a.input else read_json(a.request)
    project=adapter.validate(q,r);request=project/'artifacts'/adapter.REQUEST_FILE
    print(json.dumps({'valid':True,'project_id':r['project_id'],'render_id':r['render_id'],'request':str(request)},ensure_ascii=False),flush=True)
    if a.freeze_only or a.check:return
    job=adapter.submit(q,r)
    if job['status']!='completed':job=ProductionQueueWorker(q,q.projects_root,worker_id='dark-full-cli',lease_seconds=7200).run_local_recompose(job['job_id'])
    if job['status']!='completed':
        print(json.dumps({'job_id':job['job_id'],'status':job['status'],'error':job.get('error'),'request':str(request)},ensure_ascii=False));raise RuntimeError('保留原任务及请求恢复，未重新生成上游素材')
    folder=project/'renders'/r['render_id'];source=folder/adapter.OUTPUT_FILE
    destination=a.output_dir or folder;destination.mkdir(parents=True,exist_ok=True)
    target=destination/(r['render_id']+'.mp4')
    if target.exists() and sha(target)!=sha(source):raise RuntimeError('交付目录已有不同版本，保留原文件')
    if not target.exists():shutil.copy2(source,target)
    record={'project_id':r['project_id'],'render_id':r['render_id'],'request':str(request),'output':str(target),'sha256':sha(target),'job_id':job['job_id'],'work_id':job['result'].get('work_id'),'version_id':job['result'].get('version_id'),'cloud_calls':0,'published':False}
    if (folder/adapter.NOMUSIC_FILE).is_file():
        no=destination/(r['render_id']+'-nomusic.mp4')
        if no.exists() and sha(no)!=sha(folder/adapter.NOMUSIC_FILE):raise RuntimeError('无配乐备选交付路径有不同内容')
        if not no.exists():shutil.copy2(folder/adapter.NOMUSIC_FILE,no)
        record['nomusic_output']=str(no)
    atomic_private(folder/'delivery.json',record)
    print(json.dumps(record,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
