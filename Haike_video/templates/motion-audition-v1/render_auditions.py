"""Bounded local development auditions; no production, cloud or avatar calls."""
import argparse, hashlib, json, shutil, subprocess, sys, time
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--task',required=True);args=p.parse_args()
HERE=Path(__file__).resolve().parent
ROOT=next(x for x in HERE.parents if (x/'Haike_video/remotion-composer').exists())
TASK=Path(args.task).resolve(); OUT=TASK/'gallery';OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'Haike_video'))
from lib.ffmpeg_locator import resolve_ffmpeg_pair
FF,FP=resolve_ffmpeg_pair()
COMPOSER=ROOT/'Haike_video/remotion-composer'
NODE=Path('C:/Users/Administrator/AppData/Local/Programs/node-v24.21.0-win-x64/node.exe')
CLI=COMPOSER/'node_modules/@remotion/cli/remotion-cli.js'
shutil.copytree(HERE,COMPOSER/'projects/motion-audition-dev',dirs_exist_ok=True)
cases=json.loads((TASK/'cases.json').read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
receipts=[]
for case in cases:
 for mode in ['effect','baseline']+(['trace'] if case['effect']=='touch' else []):
  name=case['id']+'-'+mode;out=OUT/(name+'.mp4');raw=TASK/(name+'-intermediate.mp4');props=TASK/'props'/(name+'.json')
  if not out.exists():
   print('Rendering',name,flush=True)
   command=[str(NODE),str(CLI),'render','projects/motion-audition-dev/index.tsx','MotionAudition',str(raw),'--props='+str(props),'--public-dir='+str(TASK/'public'),'--concurrency=2','--codec=h264','--crf=16','--image-format=png','--log=error']
   with (TASK/(name+'.log')).open('w',encoding='utf-8') as log:subprocess.run(command,cwd=COMPOSER,stdout=log,stderr=subprocess.STDOUT,check=True)
   subprocess.run([FF,'-v','error','-y','-i',str(raw),'-c:v','libx264','-preset','fast','-b:v','20500k','-minrate','20500k','-maxrate','20500k','-bufsize','2000k','-x264-params','nal-hrd=cbr:force-cfr=1:filler=1','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(out)],check=True)
  probe=json.loads(subprocess.check_output([FP,'-v','error','-show_streams','-show_format','-of','json',str(out)]))
  v=next(s for s in probe['streams'] if s['codec_type']=='video')
  assert (v['width'],v['height'],int(v['nb_frames']))==(1440,1800,135)
  assert int(v['bit_rate'])>=20_000_000
  subprocess.run([FF,'-v','error','-xerror','-i',str(out),'-f','null','-'],check=True)
  if mode=='effect':subprocess.run([FF,'-v','error','-y','-ss','0.7' if case['effect']=='touch' else '2','-i',str(out),'-frames:v','1','-vf','scale=360:450',str(OUT/(case['id']+'.jpg'))],check=True)
  receipts.append({'id':name,'sha256':sha(out),'props_sha256':sha(props),'width':1440,'height':1800,'frames':135,'duration':v['duration'],'video_bitrate':v['bit_rate'],'full_decode':'pass'})
  (TASK/'render-receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf-8')
  print('Verified',name,flush=True)
catalog=[{k:c[k] for k in ['id','name','note','effect']} for c in cases]
(OUT/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(HERE/'gallery.html',OUT/'index.html')
(TASK/'source-receipt.json').write_text(json.dumps({'scope':'bounded development auditions','upstream_commit':'7aebcbe6514ed9e54e3a4a6786f83f8425a4a9af','source_manifest_sha256':sha(TASK/'sources.json'),'renderer':{str(p.relative_to(HERE)):sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in str(p)}},ensure_ascii=False,indent=2),encoding='utf-8')
print('DONE',OUT,flush=True)
