"""Independent promo reference reconstruction; queue owns every render.

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
TEMPLATE=ROOT/'templates/promo-reference-independent-v1'
CONTRACT='haike.promo-reference-full/1'
KIND='studio_investment_recompose'
REQUEST_FILE='promo-reference-full-request.json'
REFERENCE={'template_id':'motiongit-promo-user','version':'2.6.4','package_sha256':'8d3e5baeef9310e4b49b41de93e07fee23c65fd606c2271f63e94c99815650fe','implementation':'independently authored from publicly viewable58.75s reference; no protected core'}
RECIPES={'orange','wall','detail','quote','notice','brand'}
NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)

def require(ok,message):
    if not ok:raise WorkError(message)

def bound(value):
    require(isinstance(value,dict) and set(value)=={'path','sha256'},'源文件须绑定path/sha256')
    p=Path(value['path']);require(p.is_file() and not p.is_symlink() and sha(p)==value['sha256'],'源文件缺失或SHA改变')
    return p

def runtime():
    paths=[Path(__file__),Path(speech.__file__),ROOT/'remotion-composer/package-lock.json',*sorted(p for p in TEMPLATE.iterdir() if p.suffix in {'.tsx','.ts','.cjs','.md'}),*map(Path,resolve_ffmpeg_pair()),*toolchain()]
    require(all(p.is_file() for p in paths),'独立促销运行组件缺失')
    return {str(p.resolve()):sha(p) for p in paths}

def toolchain():
    import os
    from backlot import studio_motiongit as motion
    supplied=os.environ.get('REMOTION_BROWSER_EXECUTABLE')
    candidates=[Path(supplied)] if supplied else [ROOT.parent/'runtime/browser/chrome-headless-shell.exe',ROOT/'runtime/browser/chrome-headless-shell.exe',ROOT.parent/'.local/template-upgrade-20261102/runtime-smoke/runtime/browser/chrome-headless-shell.exe']
    browser=next((p for p in candidates if p.is_file()),None);node=motion.node_executable()
    require(browser and node and Path(node).is_file(),'促销组件缺少已安装的Node或浏览器，请由运行时准备恢复')
    return Path(node),browser

def preflight(value):
    require(isinstance(value,dict) and not set(value)-{'title','brand','asr','script','assets','scenes','media','material_review','source_receipts'},'独立促销输入字段无效')
    assets=value.get('assets',{})
    require(isinstance(assets,dict) and all(re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',n) and not n.startswith('.') for n in assets),'资产名无效')
    paths={n:bound(a) for n,a in assets.items()}
    require({'voice.wav','music.wav','body.ttf'}<=set(paths),'缺少完整声音、独立配乐或OFL字体')
    asr=read_json(bound(value['asr']));script=read_json(bound(value['script']))
    require(asr.get('audio_sha256')==sha(paths['voice.wav']) and isinstance(script.get('text'),str),'真实ASR须绑定本期完整声音')
    sentences=asr.get('segments',[])
    require(sentences and all(s.get('words') for s in sentences),'须有真实句词时码')
    from backlot.motion_replay_imported_production import caption_chunks
    captions=caption_chunks(sentences,limit=24)
    for c in captions:c['text']=c['text'].replace('跟他','跟它').replace('1分钱','一分钱')
    for previous,current in zip(captions,captions[1:]):
        prefix=re.match(r'^[，,、。！？!?；;：:]+',current['text'])
        if prefix:
            previous['text']+=prefix.group();current['text']=current['text'][len(prefix.group()):]
    norm=lambda s:re.sub(r'[^\w\u4e00-\u9fff]','',s).lower()
    require(norm(''.join(c['text'] for c in captions))==norm(script['text']),'不得删减本期完整稿')
    clock=speech._clock(paths['voice.wav'])
    audio=speech._audio_plan({'voice':'voice.wav','music':'music.wav','musicGainDb':-13,'tailSeconds':0},paths,clock)
    frames=audio['durationFrames']*2;duration=frames/60
    media=deepcopy(value.get('media'));require(isinstance(media,list) and 4<=len(media)<=24,'作品墙须有4至24项真实素材')
    ids=set();proven=read_json(bound(value['material_review']))
    from PIL import Image,ImageFont
    from backlot.studio_render import media_probe
    for m in media:
        require(isinstance(m,dict) and set(m)=={'id','src','thumbnail','kind','label'} and isinstance(m['id'],str) and m['id'] not in ids,'素材身份无效')
        ids.add(m['id'])
        require(m['src'] in paths and m['thumbnail'] in paths and m['kind'] in {'image','video'} and 0<len(m['label'])<=20,'素材文件或标签无效')
        with Image.open(paths[m['thumbnail']]) as im:require(min(im.size)>=240,'缩略图像素不足')
        if m['kind']=='video':
            match=next((r for r in proven if r.get('alias')==m['src']),None)
            require(match and match.get('sha256')==sha(paths[m['src']]),'实拍须绑定原始实际看帧清单及源SHA')
            info=media_probe(paths[m['src']]);m['sourceDuration']=info['duration']
            require(info.get('video') and match.get('frames') and all(Path(f['image']).is_file() for f in match['frames']),'实拍缺少真实看帧记录')
        else:
            with Image.open(paths[m['src']]) as im:require(min(im.size)>=240,'真实图片像素不足')
    scenes=deepcopy(value.get('scenes'));require(isinstance(scenes,list) and scenes,'缺少完整原参考动作链')
    cursor=0;recipes=[]
    by_id={m['id']:m for m in media}
    for i,s in enumerate(scenes):
        require(isinstance(s,dict) and not set(s)-{'id','sentence_start','sentence_end','recipe','title','subtitle','labels','events','windows'},'促销镜头含未开放字段')
        a,b=s.pop('sentence_start',None),s.pop('sentence_end',None)
        require(type(a) is int and type(b) is int and a==cursor and a<b<=len(sentences),'镜头须依次覆盖全部真实句')
        cursor=b;s['start']=0 if i==0 else float(sentences[a]['start']);s['end']=duration if i==len(scenes)-1 else float(sentences[b]['start'])
        require(s.get('recipe') in RECIPES and s['end']-s['start']>=3,'动作类型或完整阅读窗无效')
        recipes.append(s['recipe'])
        require(isinstance(s.get('title'),str) and 0<len(s['title'])<=30 and len(s.get('subtitle',''))<=70,'标题超出原参考版式容量')
        require(isinstance(s.get('labels'),list) and 1<=len(s['labels'])<=6 and all(isinstance(x,str) and len(x)<=34 for x in s['labels']),'画面短标签无效')
        cues=[]
        for e in s.pop('events',[]):
            si,wi=e.get('sentence'),e.get('word')
            require(set(e)<= {'sentence','word'} and type(si) is int and a<=si<b,'事件必须绑定实际句词')
            require(wi is None or type(wi) is int and 0<=wi<len(sentences[si]['words']),'词时码编号无效')
            cues.append(float(sentences[si]['start'] if wi is None else sentences[si]['words'][wi]['start']))
        require(cues and cues==sorted(cues) and all(s['start']<=t<s['end']-.1 for t in cues),'动作须有真实时码与落定窗口')
        s['cues']=cues
        for w in s.get('windows',[]):
            require(set(w)=={'mediaId','start','end','offset'} and w['mediaId'] in by_id and by_id[w['mediaId']]['kind']=='video','视频窗口须绑定真实源')
            require(s['start']<=w['start']<w['end']<=s['end'] and w['offset']>=0 and w['offset']+w['end']-w['start']<=by_id[w['mediaId']]['sourceDuration']+.025,'实拍不得循环、冻结、变速或超出源区间')
    require(cursor==len(sentences) and recipes==['orange','wall','detail','quote','notice','brand'],'必须完整保留橙字、四列墙、同卡详情、情境转述、边界与品牌收尾')
    require(isinstance(value.get('source_receipts'),dict),'须保留原稿与素材授权')
    font=ImageFont.truetype(str(paths['body.ttf']),46)
    require(all(font.getlength(c['text'])<=1740 for c in captions),'字幕超过真实字体版心')
    for scene in scenes:
        require(ImageFont.truetype(str(paths['body.ttf']),76).getlength(scene['title'])<=1640 and ImageFont.truetype(str(paths['body.ttf']),30).getlength(scene['subtitle'])<=1640,'标题或辅助行超过真实字体容量')
        if scene['recipe']=='orange':
            require(all(ImageFont.truetype(str(paths['body.ttf']),154).getlength(label)<=1640 for label in scene['labels']),'橙底大字超过真实字体容量')
        if scene['recipe']=='detail':
            require(all(ImageFont.truetype(str(paths['body.ttf']),55).getlength(label)<=1160 for label in scene['labels']),'详情文字超过两行真实字体容量')
        if scene['recipe']=='quote':require(len(scene['labels'])==2,'情境转述须同时有正文与明确语境')
    props={'width':1920,'height':1080,'fps':60,'durationFrames':frames,'title':value['title'],'brand':value.get('brand','海客AI社区服务店'),'font':'body.ttf','audio':'master.wav','captions':captions,'scenes':scenes,'media':media}
    return {'props':props,'audio':audio,'paths':paths,'voice_clock':clock,'reference':deepcopy(REFERENCE),'source_receipts':deepcopy(value['source_receipts']),'evidence':{'asr':value['asr'],'script':value['script'],'material_review':value['material_review'],'caption_count':len(captions),'full_text':True}}

def prepare(queue,value):
    n=preflight(value)
    require(shutil.disk_usage(queue.projects_root).free>=2*1024**3,'促销整片渲染需至少2GiB作业空间，请保留已有产物并释放无关空间')
    core={'contract':CONTRACT,'title':value['title'],'props':n['props'],'audio':n['audio'],'voice_clock':n['voice_clock'],'reference':n['reference'],'source_receipts':n['source_receipts'],'evidence':n['evidence'],'origins':{name:{'path':str(p),'sha256':sha(p)} for name,p in n['paths'].items()},'runtime':runtime(),'publication':False,'paid_calls':0}
    core['project_id']='studio-'+fingerprint(core)[:16];digest=fingerprint(core)
    r={**core,'request_sha256':digest,'render_id':'promo-reference-full-'+digest[:20]}
    from lib.checkpoint import init_project
    project=queue.projects_root/r['project_id'];record=project/'artifacts'/REQUEST_FILE
    if not record.exists():
        init_project(r['project_id'],title=r['title'],pipeline_type='animated-explainer',pipeline_dir=queue.projects_root)
        dest=project/'assets/promo-reference-full';dest.mkdir(parents=True,exist_ok=True)
        for name,path in n['paths'].items():shutil.copy2(path,dest/name)
        atomic_private(record,r)
    validate(queue,r);return r

def validate(queue,r):
    core={k:v for k,v in r.items() if k not in {'request_sha256','render_id','phase'}}
    require(r.get('contract')==CONTRACT and fingerprint(core)==r['request_sha256'],'促销组件请求身份改变')
    project=queue.projects_root/r['project_id'];require(read_json(project/'artifacts'/REQUEST_FILE)=={k:v for k,v in r.items() if k!='phase'},'冻结记录改变')
    require(all(sha(project/'assets/promo-reference-full'/name)==v['sha256'] for name,v in r['origins'].items()),'冻结资产改变')
    done=read_json(project/'renders'/r['render_id']/'result.json')
    if not done:require(runtime()==r['runtime'],'执行组件改变，请保留旧版本并重新冻结')
    return project,project/'renders'/r['render_id']

def submit(queue,r,*,phase='preview'):
    validate(queue,r);require(phase in {'preview','render'},'制作阶段无效')
    folder=queue.projects_root/r['project_id']/'renders'/r['render_id']
    approval=read_json(folder/'visual-review.json')
    require(phase!='render' or approval.get('inspected_images'),'请先实际审阅全部图解预览')
    return queue.submit(kind=KIND,project_id=r['project_id'],source='codex',priority='normal',parent_job_id=r['render_id'],frozen_request={**r,'phase':phase},idempotency_key='promo-reference-full:'+r['request_sha256']+':'+phase+':'+fingerprint(approval),start_paused=True)

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
        assets={n:project/'assets/promo-reference-full'/n for n in r['origins']}
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
            return {'status':'completed','stage':'独立促销实际预览已生成，等待逐图审阅','result':{'images':preview['images'],'preview_sha256':sha(folder/'preview.json'),'qa_status':'pending'}}
        require(read_json(folder/'visual-review.json').get('inspected_images'),'缺少本期实际预览审核')
        output=folder/'promo-reference-full.mp4'
        if not read_json(folder/'result.json'):
            audio_receipt=speech.mix_master(r['audio'],assets,public/'master.wav');atomic_private(folder/'audio-receipt.json',audio_receipt)
            subprocess.run(command,check=True,capture_output=True,creationflags=NO_WINDOW,timeout=7200)
            ff,_=resolve_ffmpeg_pair();duration=r['props']['durationFrames']/60
            export=[ff,'-nostdin','-y','-v','error','-i',str(folder/'mezzanine.mp4'),'-i',str(public/'master.wav'),'-map','0:v:0','-map','1:a:0','-t',str(duration),'-c:v','libx264','-preset','slow','-b:v','20500k','-minrate','20500k','-maxrate','20500k','-bufsize','2000k','-x264-params','nal-hrd=cbr:force-cfr=1:filler=1','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart',str(output)]
            subprocess.run(export,check=True,capture_output=True,creationflags=NO_WINDOW)
            from backlot.studio_render import media_probe
            from backlot.studio_investment_audio_v5 import measure_audio
            info=media_probe(output);v=info['video'];a=info['audio'];loud=measure_audio(output)
            require((v['width'],v['height'])==(1920,1080) and v['codec_name']=='h264' and v['pix_fmt']=='yuv420p' and int(v['nb_frames'])==r['props']['durationFrames'] and int(v['bit_rate'])>=20000000 and a['channels']==2 and str(a['sample_rate'])=='48000' and loud['true_peak_dbtp']<=-1.5,'促销成片技术指标未通过')
            subprocess.run([ff,'-nostdin','-v','error','-xerror','-i',str(output),'-f','null','-'],check=True,capture_output=True,creationflags=NO_WINDOW)
            atomic_private(folder/'quality.json',{'media':info,'audio':loud,'full_decode':'passed','export_command':export,'continuous_watching':'pending','continuous_listening':'pending','device_listening':'pending','visual_review_sha256':sha(folder/'visual-review.json'),'full_text_evidence':r['evidence']})
            atomic_private(folder/'result.json',{'output_sha256':sha(output),'quality_sha256':sha(folder/'quality.json'),'paid_calls':0,'publication':False})
        require(sha(output)==read_json(folder/'result.json')['output_sha256'],'已有成片SHA改变')
        work=WorkCatalog(queue.projects_root).register(r['project_id'],output,work_key='main',mode='manual',event_id=job['job_id'],quality_passed=False,actor=CONTRACT,title=r['title'])
        return {'status':'completed','stage':'独立促销完整成片已合成，待视听复核','result':{'output_path':str(output),'output_sha256':sha(output),'work_id':work['work_id'],'qa_status':'pending'}}
    except Exception as exc:
        return {'status':'failed','stage':'独立促销本地阶段未完成，原源与请求保留','error':{'type':type(exc).__name__,'message':str(exc)[:1000]},'retryable':True,'safe_resume_point':'promo-reference-full-local'}


