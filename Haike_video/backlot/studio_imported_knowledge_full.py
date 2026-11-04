"""Independent, redistributable knowledge boards; queue owns every render.

No MotionGit protected implementation is loaded. Original references keep their
own identities; this new execution identity owns its source and visual evidence.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import math
import re
import shutil
import subprocess
from backlot.studio import atomic_private
from backlot.work_catalog import read_json,sha,WorkError,WorkCatalog
from backlot.studio_investment_recompose import fingerprint
from backlot import studio_hum_production as speech
from lib.ffmpeg_locator import resolve_ffmpeg_pair

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/'templates/knowledge-full-independent-v1'
CONTRACT='haike.knowledge-full/1'
KIND='studio_investment_recompose'
REQUEST_FILE='knowledge-full-request.json'
REFERENCES={'sketchnote':('knowledge-explainer-sketchnote','2.7.3'),
            'chalkboard':('knowledge-explainer-chalkboard','2.7.2')}
RECIPES={'question','steps','evidence','compare','quote','notice','invitation'}
NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)

def require(ok,message):
    if not ok:raise WorkError(message)

def bound(value):
    require(isinstance(value,dict) and set(value)=={'path','sha256'},'源文件须绑定path/sha256')
    p=Path(value['path']);require(p.is_file() and not p.is_symlink() and sha(p)==value['sha256'],'源文件缺失或SHA改变')
    return p

def runtime():
    paths=[Path(__file__),Path(speech.__file__),ROOT/'remotion-composer/package-lock.json',*sorted(p for p in TEMPLATE.iterdir() if p.suffix in {'.tsx','.ts','.cjs','.md'}),*map(Path,resolve_ffmpeg_pair()),*toolchain()]
    require(all(p.is_file() for p in paths),'独立知识运行组件缺失')
    return {str(p.resolve()):sha(p) for p in paths}

def toolchain():
    import os
    from backlot import studio_motiongit as motion
    supplied=os.environ.get('REMOTION_BROWSER_EXECUTABLE')
    candidates=[Path(supplied)] if supplied else [ROOT.parent/'runtime/browser/chrome-headless-shell.exe',ROOT/'runtime/browser/chrome-headless-shell.exe',ROOT.parent/'.local/template-upgrade-20261102/runtime-smoke/runtime/browser/chrome-headless-shell.exe']
    browser=next((p for p in candidates if p.is_file()),None);node=motion.node_executable()
    require(browser and node and Path(node).is_file(),'知识组件缺少已安装的Node或浏览器，请由运行时准备恢复')
    return Path(node),browser

def preflight(value):
    require(isinstance(value,dict) and not set(value)-{'theme','title','brand','asr','script','assets','scenes','presenter','source_receipts'},'独立知识输入字段无效')
    theme=value.get('theme');require(theme in REFERENCES,'知识主题必须为纸笔或粉笔')
    assets=value.get('assets',{});require(isinstance(assets,dict) and all(re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',n) and not n.startswith('.') for n in assets),'资产名无效')
    paths={n:bound(a) for n,a in assets.items()}
    require({'voice.wav','music.wav','body.ttf'}<=set(paths),'缺少完整口播、独立配乐或OFL字体')
    asr=read_json(bound(value['asr']));script=read_json(bound(value['script']))
    require(asr.get('audio_sha256')==sha(paths['voice.wav']) and isinstance(script.get('text'),str),'真ASR没有绑定完整本期声音')
    sentences=asr.get('segments',[]);require(sentences and all(s.get('words') for s in sentences),'缺少真实句词时钟')
    from backlot.motion_replay_imported_production import caption_chunks
    captions=caption_chunks(sentences)
    for c in captions:c['text']=c['text'].replace('跟他','跟它').replace('1分钱','一分钱')
    norm=lambda s:re.sub(r'[^\w\u4e00-\u9fff]','',s).lower()
    require(norm(''.join(c['text'] for c in captions))==norm(script['text']),'字幕未保留完整原稿')
    clock=speech._clock(paths['voice.wav']);frames=math.ceil(clock['duration_seconds']*60);duration=frames/60
    audio=speech._audio_plan({'voice':'voice.wav','music':'music.wav','musicGainDb':-13,'tailSeconds':0},paths,clock)
    # The mixer clock is 30fps; visual clock preserves the complete same speech.
    # The shared audio mixer uses a 30fps integer clock; round only silent tail.
    frames=2*math.ceil(frames/2);duration=frames/60
    audio['durationFrames']=frames//2
    scenes=deepcopy(value.get('scenes'));require(isinstance(scenes,list) and scenes,'缺少完整语义图解')
    cursor=0;ids=set()
    for i,s in enumerate(scenes):
        require(isinstance(s,dict) and not set(s)-{'id','sentence_start','sentence_end','title','subtitle','recipe','labels','events','media'},'图解包含未开放字段')
        a,b=s.pop('sentence_start',None),s.pop('sentence_end',None)
        require(type(a) is int and type(b) is int and a==cursor and a<b<=len(sentences),'图解须连续覆盖所有真实句子')
        require(s.get('id') not in ids and isinstance(s.get('id'),str),'图解编号重复');ids.add(s['id']);cursor=b
        s['start']=0 if i==0 else float(sentences[a]['start'])
        s['end']=duration if i==len(scenes)-1 else float(sentences[b]['start'])
        require(s['end']-s['start']>=2.5 and s.get('recipe') in RECIPES,'图解动作时窗不足或未知')
        require(isinstance(s.get('title'),str) and 1<=len(s['title'])<=22 and isinstance(s.get('subtitle'),str) and len(s['subtitle'])<=30,'图解文字超出已设计容量')
        require(isinstance(s.get('labels'),list) and 1<=len(s['labels'])<=4 and all(isinstance(v,str) and 0<len(v)<=28 for v in s['labels']),'图解标签无效')
        cues=[]
        for ev in s.pop('events',[]):
            si,wi=ev.get('sentence'),ev.get('word')
            require(set(ev)<={'sentence','word'} and type(si) is int and a<=si<b,'动作须绑定本场真实词句')
            if wi is None:cues.append(float(sentences[si]['start']))
            else:
                require(type(wi) is int and 0<=wi<len(sentences[si]['words']),'词编号无效')
                cues.append(float(sentences[si]['words'][wi]['start']))
        require(cues and cues==sorted(cues) and all(s['start']<=c<s['end']-.2 for c in cues),'动作事件须有顺序并保留落定时间')
        s['cues']=cues
        media=s.get('media',[])
        require((s['recipe']=='evidence')==bool(media) and len(media)<=1,'证据图解绑定一段实际视频，其余图解不藏媒体')
        for m in media:
            require(set(m)=={'src','offset','label'} and m['src'] in paths and 0<=m['offset'],'证据源绑定无效')
            from backlot.studio_render import media_probe
            require(m['offset']+s['end']-s['start']<=media_probe(paths[m['src']])['duration']+.025,'真实视频窗口不足；不能循环、变速或尾帧补齐')
    require(cursor==len(sentences),'图解未覆盖全文')
    presenter=deepcopy(value.get('presenter'))
    if presenter:
        require(set(presenter)=={'src','windows','evidence'} and presenter['src'] in paths,'人物绑定无效')
        proof=read_json(bound(presenter.pop('evidence')))
        require(proof.get('source_audio_sha256')==sha(paths['voice.wav']) and proof.get('timeline_sha256')==sha(paths[presenter['src']]),'人物与完整口播/时钟不同源')
        reviewed=proof.get('verified_timeline_windows');require(isinstance(reviewed,list) and reviewed,'人物缺少实际核对的覆盖窗口')
        previous=0
        for w in presenter['windows']:
            require(set(w)=={'start','end','offset'} and previous<=w['start']<w['end']<=duration and abs(w['offset']-w['start'])<1/60,'人物须使用同一全局时钟的顺序窗口')
            require(any(lo<=w['offset'] and w['offset']+w['end']-w['start']<=hi+1/60 for lo,hi in reviewed),'人物显示区间超出真实已审素材')
            previous=w['end']
    require(isinstance(value.get('source_receipts'),dict),'须保留本期完整来源与授权')
    props={'theme':theme,'width':1080,'height':1920,'fps':60,'durationFrames':frames,'title':value['title'],'brand':value.get('brand','海客AI社区服务店'),'font':'body.ttf','audio':'master.wav','captions':captions,'scenes':scenes}
    if presenter:props['presenter']=presenter
    return {'props':props,'audio':audio,'paths':paths,'voice_clock':clock,'reference':{'template_id':REFERENCES[theme][0],'version':REFERENCES[theme][1],'implementation':'independent authored source; not original protected renderer'},'source_receipts':deepcopy(value['source_receipts']),'evidence':{'asr':value['asr'],'script':value['script'],'caption_count':len(captions),'full_text':True}}

def prepare(queue,value):
    n=preflight(value)
    require(shutil.disk_usage(queue.projects_root).free>=2*1024**3,'知识整片渲染需至少2GiB作业空间，请保留已有产物并释放无关空间')
    core={'contract':CONTRACT,'title':value['title'],'props':n['props'],'audio':n['audio'],'voice_clock':n['voice_clock'],'reference':n['reference'],'source_receipts':n['source_receipts'],'evidence':n['evidence'],'origins':{name:{'path':str(p),'sha256':sha(p)} for name,p in n['paths'].items()},'runtime':runtime(),'publication':False,'paid_calls':0}
    core['project_id']='studio-'+fingerprint(core)[:16];digest=fingerprint(core)
    r={**core,'request_sha256':digest,'render_id':'knowledge-full-'+digest[:20]}
    from lib.checkpoint import init_project
    project=queue.projects_root/r['project_id'];record=project/'artifacts'/REQUEST_FILE
    if not record.exists():
        init_project(r['project_id'],title=r['title'],pipeline_type='animated-explainer',pipeline_dir=queue.projects_root)
        dest=project/'assets/knowledge-full';dest.mkdir(parents=True,exist_ok=True)
        for name,path in n['paths'].items():shutil.copy2(path,dest/name)
        atomic_private(record,r)
    validate(queue,r);return r

def validate(queue,r):
    core={k:v for k,v in r.items() if k not in {'request_sha256','render_id','phase'}}
    require(r.get('contract')==CONTRACT and fingerprint(core)==r['request_sha256'],'知识组件请求身份改变')
    project=queue.projects_root/r['project_id'];require(read_json(project/'artifacts'/REQUEST_FILE)=={k:v for k,v in r.items() if k!='phase'},'冻结记录改变')
    require(all(sha(project/'assets/knowledge-full'/name)==v['sha256'] for name,v in r['origins'].items()),'冻结资产改变')
    done=read_json(project/'renders'/r['render_id']/'result.json')
    if not done:require(runtime()==r['runtime'],'执行组件改变，请保留旧版本并重新冻结')
    return project,project/'renders'/r['render_id']

def submit(queue,r,*,phase='preview'):
    validate(queue,r);require(phase in {'preview','render'},'制作阶段无效')
    folder=queue.projects_root/r['project_id']/'renders'/r['render_id']
    approval=read_json(folder/'visual-review.json')
    require(phase!='render' or approval.get('inspected_images'),'请先实际审阅全部图解预览')
    return queue.submit(kind=KIND,project_id=r['project_id'],source='codex',priority='normal',parent_job_id=r['render_id'],frozen_request={**r,'phase':phase},idempotency_key='knowledge-full:'+r['request_sha256']+':'+phase+':'+fingerprint(approval),start_paused=True)

def review(queue,r,evidence):
    _,folder=validate(queue,r);receipt=read_json(folder/'preview.json')
    require(receipt and evidence.get('preview_sha256')==sha(folder/'preview.json') and evidence.get('reviewer') and evidence.get('inspected_images')==receipt['images'],'审核须绑定本期全部实际图解预览')
    require(all(sha(folder/'preview'/v['name'])==v['sha256'] for v in receipt['images']),'预览图片改变')
    atomic_private(folder/'visual-review.json',{**evidence,'continuous_watching':'pending','continuous_listening':'pending','device_listening':'pending'})
    return {'reviewed':True,'scope':'sampled-preview'}

def run(queue,job):
    r=job['frozen_request']
    try:
        require(job['kind']==KIND and job['project_id']==r['project_id'],'父队列身份不一致')
        project,folder=validate(queue,r);folder.mkdir(parents=True,exist_ok=True)
        assets={n:project/'assets/knowledge-full'/n for n in r['origins']}
        public=folder/'public';public.mkdir(exist_ok=True)
        for name,path in assets.items():
            if name not in {'voice.wav','music.wav'}:shutil.copy2(path,public/name)
        atomic_private(folder/'props.json',r['props'])
        for p in TEMPLATE.iterdir():
            if p.suffix in {'.tsx','.ts','.cjs'}:
                (folder/'template').mkdir(exist_ok=True);shutil.copy2(p,folder/'template'/p.name)
        node,browser=toolchain()
        command=[str(node),str(TEMPLATE/'render.cjs'),str(ROOT/'remotion-composer'),str(folder),r['phase'],str(browser)]
        if r['phase']=='preview':
            subprocess.run(command,check=True,capture_output=True,creationflags=NO_WINDOW,timeout=1200)
            preview=read_json(folder/'preview.json')
            return {'status':'completed','stage':'独立图解实际预览已生成，等待逐图审阅','result':{'images':preview['images'],'preview_sha256':sha(folder/'preview.json'),'qa_status':'pending'}}
        require(read_json(folder/'visual-review.json').get('inspected_images'),'缺少本期实际预览审核')
        output=folder/'knowledge-full.mp4'
        if not read_json(folder/'result.json'):
            audio_receipt=speech.mix_master(r['audio'],assets,public/'master.wav');atomic_private(folder/'audio-receipt.json',audio_receipt)
            subprocess.run(command,check=True,capture_output=True,creationflags=NO_WINDOW,timeout=7200)
            ff,_=resolve_ffmpeg_pair();duration=r['props']['durationFrames']/60
            export=[ff,'-nostdin','-y','-v','error','-i',str(folder/'mezzanine.mp4'),'-i',str(public/'master.wav'),'-map','0:v:0','-map','1:a:0','-t',str(duration),'-c:v','libx264','-preset','slow','-b:v','20500k','-minrate','20500k','-maxrate','20500k','-bufsize','2000k','-x264-params','nal-hrd=cbr:force-cfr=1:filler=1','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart',str(output)]
            subprocess.run(export,check=True,capture_output=True,creationflags=NO_WINDOW)
            from backlot.studio_render import media_probe
            from backlot.studio_investment_audio_v5 import measure_audio
            info=media_probe(output);v=info['video'];a=info['audio'];loud=measure_audio(output)
            require((v['width'],v['height'])==(1080,1920) and v['codec_name']=='h264' and v['pix_fmt']=='yuv420p' and int(v['nb_frames'])==r['props']['durationFrames'] and int(v['bit_rate'])>=20000000 and a['channels']==2 and str(a['sample_rate'])=='48000' and loud['true_peak_dbtp']<=-1.5,'知识成片技术指标未通过')
            subprocess.run([ff,'-nostdin','-v','error','-xerror','-i',str(output),'-f','null','-'],check=True,capture_output=True,creationflags=NO_WINDOW)
            atomic_private(folder/'quality.json',{'media':info,'audio':loud,'full_decode':'passed','export_command':export,'continuous_watching':'pending','continuous_listening':'pending','device_listening':'pending','visual_review_sha256':sha(folder/'visual-review.json'),'full_text_evidence':r['evidence']})
            atomic_private(folder/'result.json',{'output_sha256':sha(output),'quality_sha256':sha(folder/'quality.json'),'paid_calls':0,'publication':False})
        require(sha(output)==read_json(folder/'result.json')['output_sha256'],'已有成片SHA改变')
        work=WorkCatalog(queue.projects_root).register(r['project_id'],output,work_key='main',mode='manual',event_id=job['job_id'],quality_passed=False,actor=CONTRACT,title=r['title'])
        return {'status':'completed','stage':'独立知识完整成片已合成，待视听复核','result':{'output_path':str(output),'output_sha256':sha(output),'work_id':work['work_id'],'qa_status':'pending'}}
    except Exception as exc:
        return {'status':'failed','stage':'独立知识本地阶段未完成，原源与请求保留','error':{'type':type(exc).__name__,'message':str(exc)[:1000]},'retryable':True,'safe_resume_point':'knowledge-full-local'}
