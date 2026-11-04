"""Owned unified-queue adapter for one low-resolution reference-led test."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from lib.checkpoint import init_project

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/'templates/kinetic-field-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
    p=argparse.ArgumentParser();p.add_argument('--install-root',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--phase',choices=['stills','video'],required=True);a=p.parse_args()
    install=a.install_root.resolve();data=a.data.resolve();episode=read(data/'episode.json')
    if episode['contract']!='kinetic-field-assets-v1' or episode['paid_calls']!=0:raise ValueError('Wrong local sample contract')
    for row in episode['files'].values():
        if sha(row['path'])!=row['sha256']:raise ValueError('Asset changed')
    files=[Path(__file__),data/'episode.json',ROOT/'templates/animation-signatures-v2/shared.tsx',ROOT/'templates/warm-workbench-v1/webpack.cjs',ROOT/'remotion-composer/package-lock.json']
    for base in [TEMPLATE,data/'public',data/'bundle',ROOT/'motion-components/snapcn/compat',ROOT/'motion-components/snapcn/upstream/registry/snap-cn',ROOT/'motion-components/snapcn/upstream/registry/snap-cn-ui/core']:
        files.extend(x for x in base.rglob('*') if x.is_file() and '__pycache__' not in x.parts)
    identity={str(x):sha(x) for x in sorted(set(files))}
    def review():
        value=read(data/'design-review.json')
        if value.get('status')!='pass' or value.get('identity')!=identity:raise ValueError('Current actual image review is required')
        if len(value.get('images',[]))<10 or len(value.get('observations',[]))<3:raise ValueError('Missing review evidence')
        for row in value['images']:
            if sha(row['path'])!=row['sha256']:raise ValueError('Reviewed frame changed')
    if a.phase=='video':review()
    frozen={'contract':'kinetic-field-test-v1','identity':identity,'phase':a.phase,'data':str(data),'paid_calls':0,'review_sha':sha(data/'design-review.json') if a.phase=='video' else None}
    digest=hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest();pid='kinetic-'+digest[:12];rid=a.phase+'-'+digest[:16];projects=install/'Haike_video/projects'
    init_project(pid,title='动效模板2 · 活力现场',pipeline_type='animated-explainer',pipeline_dir=projects)
    out=projects/pid/'renders'/rid;out.mkdir(parents=True,exist_ok=True);write(projects/pid/'artifacts/kinetic-request.json',frozen)
    queue=ProductionQueue(install/'Haike_video/.backlot/production-queue.sqlite3',projects)
    job=queue.submit(project_id=pid,kind='studio_investment_recompose',source='codex',priority='normal',parent_job_id=rid,frozen_request=frozen,idempotency_key='kinetic-field:'+digest,start_paused=True)
    receipt={'job_id':job['job_id'],'project_id':pid,'output':str(out),'request_sha256':digest,'identity':identity};write(data/(a.phase+'-job.json'),{**receipt,'status':job['status']});print(json.dumps({k:v for k,v in receipt.items() if k!='identity'}),flush=True)
    def execute(claim):
        for file,value in identity.items():
            if sha(file)!=value:raise ValueError('Frozen source changed: '+file)
        if a.phase=='video':
            if sha(data/'design-review.json')!=frozen['review_sha']:raise ValueError('Review changed')
            review()
        with (out/'render.log').open('w',encoding='utf-8') as log:
            subprocess.run([str(install/'runtime/node/node.exe'),str(TEMPLATE/'render.cjs'),a.phase,str(data),str(out),str(install/'runtime/browser/chrome-headless-shell.exe')],check=True,stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000)
        if a.phase=='video':
            movie=out/'kinetic-field.mp4';probe=json.loads(subprocess.check_output([str(install/'runtime/ffmpeg/bin/ffprobe.exe'),'-v','error','-show_streams','-show_format','-of','json',str(movie)],creationflags=0x08000000))
            v=next(s for s in probe['streams'] if s['codec_type']=='video')
            if (v['width'],v['height'],v['nb_frames'],v['r_frame_rate'])!=(270,480,'384','24/1'):raise ValueError('Wrong output contract')
            if not any(s['codec_type']=='audio' for s in probe['streams']):raise ValueError('Missing audio')
            write(out/'proofs.json',{'sha256':sha(movie),'probe':probe,'paid_calls':0,'visual':'pending-final-review'})
        return {'status':'completed','stage':'16秒动效测试 '+a.phase,'result':{'preview_dir':str(out),'count':1}}
    if job['status']=='completed':result=job
    elif job['status']=='paused':result=ProductionQueueWorker(queue,projects,handlers={'studio_investment_recompose':execute},worker_id='kinetic-field-test',lease_seconds=300).run_local_recompose(job['job_id'])
    else:raise RuntimeError('Resume original job after checking state: '+job['status'])
    write(data/(a.phase+'-job.json'),{**receipt,'status':result['status']});print(json.dumps({'status':result['status'],'output':str(out)}),flush=True)
    if result['status']!='completed':raise SystemExit(2)
if __name__=='__main__':main()
