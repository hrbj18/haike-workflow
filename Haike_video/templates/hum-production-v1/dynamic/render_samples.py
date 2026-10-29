"""Render four bounded development auditions from the same production composition."""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
a=argparse.ArgumentParser();a.add_argument('--task',required=True);args=a.parse_args()
HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'Haike_video/remotion-composer').exists());T=Path(args.task).resolve();OUT=T/'samples';OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'Haike_video'))
from lib.ffmpeg_locator import resolve_ffmpeg_pair
ff,fp=resolve_ffmpeg_pair();COM=ROOT/'Haike_video/remotion-composer';node='C:/Users/Administrator/AppData/Local/Programs/node-v24.21.0-win-x64/node.exe';cli=COM/'node_modules/@remotion/cli/remotion-cli.js'
shutil.copytree(HERE.parent,COM/'projects/dynamic-scenes-dev',dirs_exist_ok=True)
rows=[]
for i,(action,label) in enumerate([('click-open','同卡点击展开与返回'),('waterfall','连续流动的素材瀑布'),('spatial-gallery','空间素材画廊'),('reflow','多屏主次重排')]):
 props=T/'props'/(action+'.json');dest=OUT/(action+'.mp4');raw=T/(action+'-raw.mp4');signature=hashlib.sha256(props.read_bytes()+b''.join(p.read_bytes() for p in sorted(HERE.rglob('*.ts*')))).hexdigest();stamp=OUT/(action+'.identity')
 if dest.exists() and (not stamp.exists() or stamp.read_text()!=signature):raise RuntimeError('Changed audition source; preserve old output and use a new task directory: '+action)
 if not dest.exists():
  print('Rendering',action,flush=True)
  with (T/(action+'-render.log')).open('w',encoding='utf-8') as log:subprocess.run([node,str(cli),'render','projects/dynamic-scenes-dev/index.tsx','HumProduction',str(raw),'--props='+str(props),'--public-dir='+str(T/'public'),'--concurrency=2','--crf=16','--log=error'],cwd=COM,stdout=log,stderr=subprocess.STDOUT,check=True)
  subprocess.run([ff,'-v','error','-y','-i',str(raw),'-c:v','libx264','-preset','fast','-b:v','20500k','-minrate','20500k','-maxrate','20500k','-bufsize','2000k','-x264-params','nal-hrd=cbr:force-cfr=1:filler=1','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(dest)],check=True);stamp.write_text(signature)
 probe=json.loads(subprocess.check_output([fp,'-v','error','-show_streams','-of','json',str(dest)]));v=probe['streams'][0];assert (v['width'],v['height'],int(v['nb_frames']))==(1440,1800,150) and int(v['bit_rate'])>=20_000_000
 subprocess.run([ff,'-v','error','-xerror','-i',str(dest),'-f','null','-'],check=True)
 subprocess.run([ff,'-v','error','-y','-ss','2.8','-i',str(dest),'-frames:v','1','-vf','scale=360:450',str(OUT/(action+'.jpg'))],check=True)
 rows.append({'id':'D0'+str(i+1),'name':label,'action':action,'file':dest.name,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'duration':5,'frames':150,'bitrate':v['bit_rate'],'decode':'pass'});(OUT/'catalog.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8');print('Verified',action,flush=True)
print('Four auditions complete.',flush=True)
