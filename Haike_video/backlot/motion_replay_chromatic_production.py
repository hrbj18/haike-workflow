"""Exact-version semantic Chromatic06 HD parent production, owned by the queue."""
from __future__ import annotations
from copy import deepcopy
from fractions import Fraction
import hashlib,json,math,os,re,shutil,subprocess,wave
from pathlib import Path

from backlot.studio import atomic_private
from backlot.work_catalog import WorkCatalog,WorkError,read_json,regular_path,sha
from backlot.studio_investment_recompose import fingerprint
from backlot.studio_render import media_probe
from backlot.production_queue import _sanitize as queue_sanitize
from lib.ffmpeg_locator import resolve_ffmpeg_pair

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/'templates/chromatic-06-production-v1'
CONTRACT='motion-replay-chromatic-production-v1'
VERSION='1.2.0-candidate.1'
KIND='studio_investment_recompose'
PROFILE={'codec':'h264','crf':16,'image_format':'png','x264_preset':'fast','pixel_format':'yuv420p','scale':1}
EVENTS={
 'haike.chromatic-06.cut-open':{'aperture','wipe','note'},
 'haike.chromatic-06.push-near':{'push','crossfade','settle','note'},
 'haike.chromatic-06.observe-colour':{'splitHalf','splitEdge','splitReturn','note'},
 'haike.chromatic-06.cut-close':{'wipe','note'},
}
OVERLAY='AI体质检测：非医疗诊断。\n不看病不卖药，给您个参考。'


def require(ok,message):
    if not ok:raise WorkError(message)


def name(value):
    return isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',value) and value not in {'.','..'}


def canonical(text):
    return ''.join(re.findall(r'[\w\u4e00-\u9fff]',text)).lower().replace('_','')


def sources_runtime():
    paths=[Path(__file__),TEMPLATE/'Scene.tsx',ROOT/'remotion-composer/package-lock.json',ROOT/'tools/video/video_compose.py']
    return {str(p.resolve()):sha(p) for p in paths}


def resolve_event(event,asr):
    require(isinstance(event,dict) and set(event)=={'from','to','anchor','offsetFrames','meaning'},'内部语义事件字段无效')
    anchor=event['anchor']
    require(isinstance(anchor,dict) and set(anchor)=={'kind','index','boundary'} and anchor['kind'] in {'word','cue'} and anchor['boundary'] in {'start','end'},'内部动作缺少真实词/句锚点')
    rows=asr['metadata']['words'] if anchor['kind']=='word' else asr['segments']
    require(type(anchor['index']) is int and 0<=anchor['index']<len(rows),'语义事件引用未知ASR项')
    require(type(event['offsetFrames']) is int and -60<=event['offsetFrames']<=120,'内部动作偏移超出可解释范围')
    frame=round(float(rows[anchor['index']][anchor['boundary']])*30)+event['offsetFrames']
    require(type(event['from']) is int and type(event['to']) is int and event['from']==frame and 1<=event['to']-frame<=120,
            '内部动作未实际消费ASR锚点或时长不受控')
    return frame


def validate_props(p,receipts):
    require(isinstance(p,dict) and set(p)=={'templateId','version','durationInFrames','fps','scenes','shots','captions','presenters','font','brand','medicalOverlay'},'完整生产画面字段未知或缺失')
    require(p['templateId']=='chromatic-06' and p['version']==VERSION and p['fps']==30,'生产模板需精确候选版本')
    require(type(p['durationInFrames']) is int and 300<=p['durationInFrames']<=18000,'完整视频时钟超出10至600秒')
    require(name(p['font']) and isinstance(p['brand'],str) and 0<len(p['brand'])<=18,'字体或品牌无效')
    require(p['medicalOverlay']==OVERLAY,'必须保留体质检测非医疗提示')
    asr=receipts['asr'];script=receipts['script'];audio=receipts['audio'];avatar=receipts['avatar']
    require(audio['script_sha256']==hashlib.sha256(script['text'].encode()).hexdigest(),'本期配音与完整脚本文字身份不符')
    require(asr['approved_script_sha256']==audio['script_sha256'] and asr['audio_sha256']==audio['audio_sha256'],'ASR未绑定本期完整旁白')
    require(avatar['workflow_id']=='2112180419025260546' and avatar['instance_type']=='plus' and avatar['api_type']=='NORMAL'
            and avatar['status']=='verified' and avatar.get('task_id'),'必须使用已完成的本期V5.3.1高质量Plus数字人')
    require(avatar.get('original_audio_sha256')==audio['audio_sha256'],'数字人未使用本期原始旁白的首尾片段')
    cursor=0;seen=set();action_ids=[]
    for s in p['scenes']:
        require(isinstance(s,dict) and not set(s)-{'id','actionId','from','to','title','note','label','events','disclosure','medical'},'场景字段未知')
        require(s['id'] not in seen and type(s['from']) is int and type(s['to']) is int and s['from']==cursor<s['to']<=p['durationInFrames'],'场景未连续覆盖完整旁白')
        seen.add(s['id']);cursor=s['to'];action_ids.append(s['actionId'])
        require(s['actionId'] in EVENTS and set(s['events'])==EVENTS[s['actionId']],'动作ID未绑定完整实际实现/内部事件')
        for key,event in s['events'].items():
            resolve_event(event,asr)
            require(s['from']<=event['from']<event['to']<=s['to'],'内部语义动作超出所属场景')
        for key,max_length,lines in [('title',24,2),('note',65,3),('label',22,1)]:
            require(isinstance(s[key],str) and len(s[key])<=max_length and len(s[key].splitlines())<=lines,'画面短文案超出原布局阅读预算')
        if s['actionId'].endswith('push-near'):
            require(s['events']['push']['from']<=s['events']['crossfade']['from']<=s['events']['settle']['to'],'推穿事件顺序无效')
        if s.get('medical'):require(s['to']-s['from']>=90,'医疗提示阅读不足3秒')
    require(cursor==p['durationInFrames'] and set(action_ids)==set(EVENTS),'全片缺失原6号动作或场景时钟')
    captions=p['captions'];previous=0
    for c in captions:
        require(set(c)=={'from','to','text'} and type(c['from']) is int and type(c['to']) is int and previous<=c['from']<c['to']<=cursor,'字幕时间越界或重叠')
        require(isinstance(c['text'],str) and len(c['text'])<=38 and len(c['text'].splitlines())<=2,'字幕超过两行预算')
        previous=c['to']
    require(canonical(''.join(c['text'] for c in captions))==canonical(script['text']),'字幕未覆盖完整文案或改变全文')
    for c in captions:
        if '体质' in c['text']:
            require(any(s.get('medical') and s['from']<=c['from'] and s['to']>=c['to'] for s in p['scenes']),
                    '体质检测字幕必须位于明确显示非医疗提示的场景')
    cursor=0;shot_ids=set()
    for shot in p['shots']:
        require(set(shot)=={'id','src','from','to','sourceFrom','objectPosition','description'} and shot['id'] not in shot_ids,'真实视频镜头字段/ID无效')
        shot_ids.add(shot['id'])
        require(name(shot['src']) and type(shot['from']) is int and type(shot['to']) is int and cursor==shot['from']<shot['to']<=p['durationInFrames'],'主视频须连续覆盖全片')
        require(type(shot['sourceFrom']) is int and shot['sourceFrom']>=0,'素材源入点无效')
        require(re.fullmatch(r'(?:100|\d{1,2})% (?:100|\d{1,2})%',shot['objectPosition']),'裁切焦点无效')
        cursor=shot['to']
    require(cursor==p['durationInFrames'],'真实视频未覆盖完整片长')
    require(len(p['presenters'])==2 and p['presenters'][0]['from']==0 and p['presenters'][-1]['to']==p['durationInFrames'],'本期人物仅首尾各一段')
    for a in p['presenters']:
        require(set(a)=={'src','from','to','sourceFrom'} and name(a['src']) and all(type(a[k]) is int for k in ('from','to','sourceFrom'))
                and 0<=a['from']<a['to']<=p['durationInFrames'] and a['sourceFrom']>=0,'同声源人物段格式无效')
    return {'action_ids':action_ids,'events':sum(len(s['events']) for s in p['scenes']),
            'complete_text_coverage':True,'speech_stretched':False,'semantic_clock':'ASR word/cue events consumed individually'}


def required_files(p):
    return {p['font'],'master.wav',*[s['src'] for s in p['shots']],*[s['src'] for s in p['presenters']]}


def freeze_safe(core):
    clean=queue_sanitize(core,redact_local_paths=False)
    require(all(clean.get(k)==core[k] for k in ('title','props','origins','runtime','contract_consumption')),
            '执行输入含队列保留凭据字段，不允许队列静默改变正文/动作/来源')
    return clean


def prepare_contract(template,request,*,workspace):
    require(isinstance(request,dict) and set(request)<={'template_id','version','production_request','action_ids'}
            and isinstance(request.get('production_request'),dict),'完整候选需要production_request；不接受历史预览或未开放字段')
    value=request['production_request']
    require(value.get('template_id')=='chromatic-06' and value.get('version')==VERSION,'完整制作输入身份不同')
    expected=[a['id'] for a in template['actions']]
    require(request.get('action_ids',expected)==expected,'完整生产候选不可删改原动作集合')
    consumed=validate_props(value['props'],value['receipts'])
    return {'status':'prepared','entrypoint':'Haike_video/templates/chromatic-06-production-v1/Scene.tsx#ChromaticProduction',
       'input_props':deepcopy(value['props']),'contract_consumption':consumed,'blockers':[],
       'production_contract':CONTRACT,'queue_admission':'backlot.motion_replay_chromatic_production.prepare(queue, production_request)',
       'render_profile':{'width':1080,'height':1920,'fps':30,'audio_required':True,'minimum_video_bitrate':20000000}}


def prepare(queue,value):
    require(set(value)=={'title','template_id','version','props','sources','receipts','publication'},'完整生产请求字段不完整')
    require(value['template_id']=='chromatic-06' and value['version']==VERSION and value['publication'] is False,'候选身份或发布边界无效')
    # Resolve exact source action IDs through the public versioned contract.
    from backlot.motion_replay import resolve,verify_sources,prepare as replay_prepare
    registered=resolve('chromatic-06',VERSION);verify_sources(registered)
    require(set(EVENTS)=={a['id'] for a in registered['actions']},'生产动作与统一注册合同不一致')
    prepared=replay_prepare('chromatic-06',VERSION,{'production_request':value})
    check=prepared['contract_consumption'];p=prepared['input_props']
    paths={n:Path(path).resolve() for n,path in value['sources'].items()}
    require(set(paths)==required_files(p) and all(name(n) and path.is_file() for n,path in paths.items()),'本期实际素材槽缺失或路径无效')
    media={}
    for n in {s['src'] for s in p['shots']}|{s['src'] for s in p['presenters']}:
        info=media_probe(paths[n]);v=info.get('video')or{}
        require(v and min(int(v.get('width',0)),int(v.get('height',0)))>=720,'正式主素材或人物不足720短边，不能以代理上采样冒充')
        media[n]=info
    for s in p['shots']+p['presenters']:
        require((s['sourceFrom']+s['to']-s['from'])/30<=media[s['src']]['duration']+.035,'真实素材帧数不足，禁止循环/冻尾/变速补长')
    require(all(sha(paths[a['src']])==value['receipts']['avatar']['derived_video_sha256'] for a in p['presenters']),
            '首尾人物不是同一已验高质量原片的30fps派生')
    with wave.open(str(paths['master.wav']),'rb') as w:
        require(w.getframerate()==48000 and w.getnchannels()==2 and w.getsampwidth()==2 and abs(w.getnframes()/48000-p['durationInFrames']/30)<.001,'完整声音母带与原速主时钟不一致')
    require(value['receipts']['master_sha256']==sha(paths['master.wav']),'母带与冻结声音回执不同')
    core={**deepcopy(value),'contract':CONTRACT,'runtime':sources_runtime(),'origins':{n:{'path':str(path),'sha256':sha(path)} for n,path in paths.items()},'media':media,'contract_consumption':check}
    core.pop('sources');core=freeze_safe(core);core['project_id']='studio-'+fingerprint(core)[:16]
    digest=fingerprint(core);request={**core,'request_sha256':digest,'render_id':'chromatic-'+digest[:20]}
    project=queue.projects_root/request['project_id'];frozen=project/'artifacts/chromatic-production-request.json'
    if frozen.exists():
        existing=read_json(frozen);validate(queue,existing);return existing
    from lib.checkpoint import init_project
    init_project(request['project_id'],title=value['title'],pipeline_type='animated-explainer',pipeline_dir=queue.projects_root)
    public=project/'assets/chromatic-production';public.mkdir(parents=True,exist_ok=True)
    for n,path in paths.items():shutil.copy2(path,public/n)
    atomic_private(frozen,request);validate(queue,request);return request


def validate(queue,r):
    digest=fingerprint({k:v for k,v in r.items() if k not in {'request_sha256','render_id'}})
    require(r['contract']==CONTRACT and r['request_sha256']==digest and r['render_id']=='chromatic-'+digest[:20],'父视频冻结请求身份变化')
    project=WorkCatalog(queue.projects_root).project(r['project_id'])
    require(read_json(project/'artifacts/chromatic-production-request.json')==r,'本期冻结请求不同')
    require(sources_runtime()==r['runtime'],'候选源码已变化，请保留旧产物后定向重验')
    for n,origin in r['origins'].items():require(sha(regular_path(project/'assets/chromatic-production'/n,project))==origin['sha256'],'本期冻结素材已变化')
    validate_props(r['props'],r['receipts']);return project


def submit(queue,r):
    validate(queue,r)
    return queue.submit(project_id=r['project_id'],kind=KIND,source='codex',priority='normal',parent_job_id=r['render_id'],
       frozen_request=r,idempotency_key=CONTRACT+':'+r['request_sha256'],start_paused=True)


def run(queue,job):
    r=job['frozen_request']
    try:
        require(job['kind']==KIND and job['project_id']==r['project_id'],'队列和父视频身份不同')
        project=validate(queue,r);folder=project/'renders'/r['render_id'];folder.mkdir(parents=True,exist_ok=True)
        output=folder/'chromatic-06-full.mp4';quality=folder/'qa.json';done=folder/'result.json'
        if done.exists():
            receipt=read_json(done);require(receipt['output_sha256']==sha(output),'完成成片身份变化')
        else:
            from tools.video.video_compose import VideoCompose
            from backlot.studio_investment_audio_v5 import measure_audio
            source=project/'assets/chromatic-production';public=folder/'public';public.mkdir(exist_ok=True)
            for n in r['origins']:shutil.copy2(source/n,public/n)
            atomic_private(folder/'props.json',r['props']);seconds=r['props']['durationInFrames']/30
            raw=folder/'mezzanine.mp4'
            edits={'render_runtime':'remotion','composition_mode':'atelier','renderer_family':'bespoke','timeline':{'duration_seconds':seconds},
               'bespoke':{'entry':str(TEMPLATE/'Scene.tsx'),'composition_id':'Chromatic06Production','art_direction':str(TEMPLATE/'README.md'),
                   'props_path':str(folder/'props.json'),'public_dir':str(public),'concurrency':2,**PROFILE}}
            if not raw.exists():
                rendered=VideoCompose().execute({'operation':'render','output_path':str(raw),'edit_decisions':edits,'asset_manifest':{'assets':[]},'script_text':r['receipts']['script']['text']})
                if not rendered.success:
                    atomic_private(folder/'render-diagnostic.json',{'error':str(rendered.error),'data':rendered.data})
                    raise WorkError('正式原生渲染失败；诊断已保留：'+str(rendered.error)[-1000:])
            ffmpeg,_=resolve_ffmpeg_pair()
            command=[ffmpeg,'-nostdin','-y','-v','error','-i',str(raw),'-i',str(public/'master.wav'),'-map','0:v:0','-map','1:a:0',
                '-t',str(seconds),'-c:v','libx264','-preset','fast','-b:v','21000k','-minrate','21000k','-maxrate','21000k','-bufsize','2100k',
                '-x264-params','nal-hrd=cbr:force-cfr=1:filler=1','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart',str(output)]
            subprocess.run(command,check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            info=media_probe(output);video=info.get('video')or{};audio=measure_audio(output)
            require((video.get('width'),video.get('height'))==(1080,1920) and int(video.get('nb_frames',0))==r['props']['durationInFrames']
                and abs(float(Fraction(video.get('avg_frame_rate','0/1')))-30)<.001 and int(video.get('bit_rate',0))>=20000000
                and bool(info.get('audio')) and audio['true_peak_dbtp']<=-1.5,'正式输出尺寸/时钟/码率/音轨/峰值不达标')
            subprocess.run([ffmpeg,'-nostdin','-v','error','-xerror','-i',str(output),'-f','null','-'],check=True,capture_output=True,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            atomic_private(quality,{'technical':'pass','full_decode':'pass','media':info,'audio':audio,'complete_text_coverage':True,
              'contract_consumption':r['contract_consumption'],'visual_review':'pending','continuous_listening':'pending','external_speaker_test':'pending'})
            atomic_private(done,{'output_sha256':sha(output),'qa_sha256':sha(quality),'request_sha256':r['request_sha256'],'publication':False})
        work=WorkCatalog(queue.projects_root).register(r['project_id'],output,work_key='main',mode='manual',event_id=job['job_id'],
           quality_passed=False,actor='motion-replay-chromatic-production',title=r['title'],summary='完整B6；语义契约驱动、真实高清视频、高质量首尾数字人；待视听审阅，未发布')
        return {'status':'completed','stage':'6号完整高清视频已生成，待实际审阅','result':{'output_path':str(output),'output_sha256':sha(output),'work_id':work['work_id'],'qa_report':str(quality)}}
    except Exception as error:
        return {'status':'failed','stage':'6号完整视频需从原本地合成恢复','error':{'type':type(error).__name__,'message':str(error)[:800]},
                'retryable':True,'safe_resume_point':'motion_replay_chromatic_production'}
