"""Independent full-speech 07–11 candidates; source motion and real media clocks.

The accepted 06 producer is immutable. This module owns a separate queue contract.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import hashlib,re,wave,shutil,subprocess
from fractions import Fraction
from backlot.motion_replay_chromatic_production import require,name,canonical,freeze_safe,OVERLAY,PROFILE
from backlot.studio import atomic_private
from backlot.work_catalog import WorkCatalog,WorkError,read_json,regular_path,sha
from backlot.studio_investment_recompose import fingerprint
from backlot.studio_render import media_probe
from lib.ffmpeg_locator import resolve_ffmpeg_pair

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/'templates/chromatic-suite-production-v1'
CONTRACT='motion-replay-chromatic-suite-production-v1'
VERSION='1.2.0-candidate.1'
KIND='studio_investment_recompose'
# Ordered actual action identity, source motion domain and required video slots.
SPECS={
 'chromatic-07':(['fan-collect','pop-evidence','mark-attention','stick-memory'],[0,240,420,585,720],[['0','2','4'],['1','3','5'],['2'],['0','7']]),
 'chromatic-08':(['orbit-entry','gallery-tour','tilt-record','orbit-recap'],[0,150,420,570,720],[[f'08-intro-{i}' for i in range(4)],['08-gallery-0','08-gallery-1'],['08-tilt'],[f'08-outro-{i}' for i in range(4)]]),
 'chromatic-09':(['fold-open','journal-park','exposure-evidence','desk-recap'],[0,210,450,600,720],[['09-fold-left','09-fold-right','09-fold-front'],['09-park'],['09-exposure-a','09-exposure-b'],['09-desk-a','09-desk-b']]),
 'chromatic-six-10':(['impact','relay','assemble','register'],[0,150,438,570,720],[['impact'],[f'relay-{i}' for i in range(5)],['assemble'],[f'recap-{i}' for i in range(3)]]),
 'chromatic-six-11':(['route-start','route-travel','step-stop','pull-overview'],[0,180,390,540,720],[['route-0','route-4','route-2']]*4),
}

def sources_runtime():
    paths=[Path(__file__),ROOT/'backlot/motion_replay_chromatic_production.py',ROOT/'remotion-composer/package-lock.json',ROOT/'tools/video/video_compose.py']
    paths += [TEMPLATE/n for n in ('Scene.tsx','Runtime.tsx','Derived-A.tsx','Derived-B.tsx','Derived-C.tsx','SOURCE_MAP.json')]
    return {str(p.resolve()):sha(p) for p in paths}

def validate_clip(c,start,end):
    require(set(c)=={'src','from','to','sourceFrom','objectPosition'} and name(c['src']),'真实视频槽字段无效')
    require(all(type(c[k]) is int for k in ('from','to','sourceFrom')) and c['from']==start<c['to']<=end and c['sourceFrom']>=0,'视频槽不连续或源入点无效')
    require(re.fullmatch(r'(?:100|\d{1,2})% (?:100|\d{1,2})%',c['objectPosition']),'裁切焦点无效')

def validate_props(p,r):
    require(set(p)=={'templateId','version','durationInFrames','fps','scenes','slots','captions','presenters','font','medicalOverlay','medicalFrom','medicalTo'},'完整候选字段未知或缺失')
    tid=p['templateId'];require(tid in SPECS and p['version']==VERSION and p['fps']==30,'仅支持07–11精确新候选')
    require(type(p['durationInFrames']) is int and 300<=p['durationInFrames']<=18000 and name(p['font']),'全片时钟/字体无效')
    text=r['script']['text'];voice=r['audio'];asr=r['asr'];avatar=r['avatar']
    require(voice['script_sha256']==hashlib.sha256(text.encode()).hexdigest() and asr['approved_script_sha256']==voice['script_sha256'] and asr['audio_sha256']==voice['audio_sha256'],'全文、声音和ASR身份不同')
    require(avatar['workflow_id']=='2112180419025260546' and avatar['instance_type']=='plus' and avatar['api_type']=='NORMAL' and avatar['status']=='verified' and avatar['task_id'] and avatar['original_audio_sha256']==voice['audio_sha256'],'必须复用本期成功HQ V5.3.1 NORMAL Plus同声源人物')
    require(p['medicalOverlay']==OVERLAY and 0<=p['medicalFrom']<p['medicalTo']<=p['durationInFrames'] and p['medicalTo']-p['medicalFrom']>=90,'非医疗提示须有完整可读域')
    ids,bounds,slots=SPECS[tid];cursor=0;count=0
    require(len(p['scenes'])==4 and set(p['slots'])=={s['id'] for s in p['scenes']},'四个原动作或真实槽缺失')
    for i,s in enumerate(p['scenes']):
        require(set(s)=={'id','actionId','from','to','sourceFrom','sourceTo','title','note','knots'},'场景字段无效')
        require(s['actionId']=='haike.'+tid+'.'+ids[i] and s['from']==cursor<s['to']<=p['durationInFrames'] and [s['sourceFrom'],s['sourceTo']]==bounds[i:i+2],'四个动作顺序/源域/实际时钟无效')
        require(all(isinstance(s[k],str) and len(s[k])<=(24 if k=='title' else 44) and len(s[k].splitlines())<=2 for k in ('title','note')),'原布局文字超出阅读预算')
        knots=s['knots'];require(len(knots)>=4 and knots[0]=={'source':bounds[i],'target':s['from'],'event':'scene-start'} and knots[-1]=={'source':bounds[i+1],'target':s['to'],'event':'scene-end'},'缺少动作边界或独立内部事件')
        for a,b in zip(knots,knots[1:]):require(a['source']<b['source'] and a['target']<b['target'],'运动事件必须严格单调')
        for k in knots[1:-1]:
            require(set(k)=={'source','target','event','anchor','offsetFrames'} and k['event'] and type(k['offsetFrames']) is int and -60<=k['offsetFrames']<=120,'内部语义事件不完整')
            a=k['anchor'];require(set(a)=={'kind','index','boundary'} and a['kind'] in {'word','cue'} and a['boundary'] in {'start','end'},'语义锚点无效')
            rows=asr['metadata']['words'] if a['kind']=='word' else asr['segments']
            require(type(a['index']) is int and 0<=a['index']<len(rows) and k['target']==round(rows[a['index']][a['boundary']]*30)+k['offsetFrames'],'内部事件未消费真实ASR锚点')
            count+=1
        require(set(p['slots'][s['id']])==set(slots[i]),'真实槽ID与原组件不同')
        for clips in p['slots'][s['id']].values():
            end=s['from'];require(clips,'视频槽为空')
            for c in clips:validate_clip(c,end,s['to']);end=c['to']
            require(end==s['to'],'素材未覆盖整个实际可见域')
        cursor=s['to']
    require(cursor==p['durationInFrames'],'四动作未覆盖完整旁白')
    prev=0
    for c in p['captions']:
        require(set(c)=={'from','to','text'} and prev<=c['from']<c['to']<=cursor and len(c['text'])<=38 and len(c['text'].splitlines())<=2,'字幕时间或行数无效');prev=c['to']
        if '体质' in c['text']:require(p['medicalFrom']<=c['from'] and c['to']<=p['medicalTo'],'体质字幕不在非医疗提示可见域')
    require(canonical(''.join(c['text'] for c in p['captions']))==canonical(text),'字幕未覆盖完整文案')
    require(len(p['presenters'])==2 and p['presenters'][0]['from']==0 and p['presenters'][-1]['to']==cursor,'首尾同声源人物缺失')
    for c in p['presenters']:validate_clip(c,c['from'],cursor)
    require(p['presenters'][0]['to']<=p['scenes'][0]['to'] and p['presenters'][-1]['from']>=p['scenes'][-1]['from'],'人物超出首尾布局域')
    if tid=='chromatic-09':require(p['slots'][p['scenes'][0]['id']]['09-fold-left']==p['slots'][p['scenes'][0]['id']]['09-fold-front'],'翻页前面和底层必须同源同帧')
    if tid=='chromatic-07':
        c=p['slots'][p['scenes'][2]['id']]['2'][0];track=r['tracking']
        require(c['src']=='tracked-S030.mp4' and c['sourceFrom']==0 and c['to']-c['from']==165 and c['objectPosition']=='50% 58%' and track['source_from_seconds']==5.5 and track['frames']==165,'圈注仅允许原测量源/裁切/165帧有效域')
    return {'action_ids':[s['actionId'] for s in p['scenes']],'events':count,'complete_text_coverage':True,'speech_stretched':False,'media_clock':'real global frames, rate1','semantic_clock':'separate ASR anchors for internal source states'}

def clips(p):
    return [c for ss in p['slots'].values() for cs in ss.values() for c in cs]+p['presenters']

def required_files(p):return {p['font'],'master.wav',*[c['src'] for c in clips(p)]}

def prepare_contract(template,request,*,workspace):
    require(isinstance(request,dict) and set(request)<={'template_id','version','production_request','action_ids'} and isinstance(request.get('production_request'),dict),'完整制作需要production_request')
    v=request['production_request'];require(v['template_id']==template['template_id'] and v['version']==VERSION and v['props']['templateId']==v['template_id'],'候选输入身份不同')
    expected=[a['id'] for a in template['actions']];require(request.get('action_ids',expected)==expected,'不能删改原动作')
    check=validate_props(v['props'],v['receipts'])
    return {'status':'prepared','entrypoint':'Haike_video/templates/chromatic-suite-production-v1/Scene.tsx#ChromaticSuite','input_props':deepcopy(v['props']),'contract_consumption':check,'blockers':[],
      'production_contract':CONTRACT,'queue_admission':__name__+'.prepare(queue, production_request)','render_profile':{'width':1080,'height':1920,'fps':30,'audio_required':True,'minimum_video_bitrate':20000000}}

def prepare(queue,value):
    require(set(value)=={'title','template_id','version','props','sources','receipts','publication'} and value['publication'] is False,'请求字段或发布边界无效')
    from backlot.motion_replay import resolve,verify_sources,prepare as replay_prepare
    registered=resolve(value['template_id'],VERSION);verify_sources(registered)
    prepared=replay_prepare(value['template_id'],VERSION,{'production_request':value});p=prepared['input_props'];check=prepared['contract_consumption']
    paths={n:Path(path).resolve() for n,path in value['sources'].items()}
    require(set(paths)==required_files(p) and all(name(n) and path.is_file() for n,path in paths.items()),'实际素材缺失')
    media={n:media_probe(paths[n]) for n in {c['src'] for c in clips(p)}}
    for n,info in media.items():require(min(int((info.get('video')or{}).get(k,0)) for k in ('width','height'))>=720,'正式素材不足720短边')
    for c in clips(p):require((c['sourceFrom']+c['to']-c['from'])/30<=media[c['src']]['duration']+.035,'禁止素材循环/冻尾/变速补长')
    avatar=value['receipts']['avatar'];require(all(sha(paths[a['src']])==avatar['derived_video_sha256'] for a in p['presenters']),'人物不是冻结的同声源HQ派生')
    if p['templateId']=='chromatic-07':require(sha(paths['tracked-S030.mp4'])==value['receipts']['tracking']['derived_sha256'],'圈注源漂移')
    with wave.open(str(paths['master.wav']),'rb') as w:require(w.getframerate()==48000 and w.getnchannels()==2 and w.getsampwidth()==2 and abs(w.getnframes()/48000-p['durationInFrames']/30)<.001,'完整母带不匹配主时钟')
    require(value['receipts']['master_sha256']==sha(paths['master.wav']),'声音母带SHA漂移')
    core={**deepcopy(value),'contract':CONTRACT,'runtime':sources_runtime(),'origins':{n:{'path':str(path),'sha256':sha(path)} for n,path in paths.items()},'media':media,'contract_consumption':check}
    core.pop('sources');core=freeze_safe(core);core['project_id']='studio-'+fingerprint(core)[:16]
    digest=fingerprint(core);r={**core,'request_sha256':digest,'render_id':'chromatic-suite-'+digest[:20]}
    project=queue.projects_root/r['project_id'];frozen=project/'artifacts/chromatic-suite-production-request.json'
    if frozen.exists():existing=read_json(frozen);validate(queue,existing);return existing
    from lib.checkpoint import init_project
    init_project(r['project_id'],title=value['title'],pipeline_type='animated-explainer',pipeline_dir=queue.projects_root)
    public=project/'assets/chromatic-suite-production';public.mkdir(parents=True,exist_ok=True)
    for n,path in paths.items():shutil.copy2(path,public/n)
    atomic_private(frozen,r);validate(queue,r);return r

def validate(queue,r):
    digest=fingerprint({k:v for k,v in r.items() if k not in {'request_sha256','render_id'}})
    require(r['contract']==CONTRACT and r['request_sha256']==digest and r['render_id']=='chromatic-suite-'+digest[:20],'冻结请求身份变化')
    project=WorkCatalog(queue.projects_root).project(r['project_id'])
    require(read_json(project/'artifacts/chromatic-suite-production-request.json')==r and sources_runtime()==r['runtime'],'冻结请求或候选源码漂移')
    for n,o in r['origins'].items():require(sha(regular_path(project/'assets/chromatic-suite-production'/n,project))==o['sha256'],'冻结素材漂移')
    validate_props(r['props'],r['receipts']);return project

def submit(queue,r):
    validate(queue,r)
    return queue.submit(project_id=r['project_id'],kind=KIND,source='codex',priority='normal',parent_job_id=r['render_id'],frozen_request=r,idempotency_key=CONTRACT+':'+r['request_sha256'],start_paused=True)

def run(queue,job):
    r=job['frozen_request']
    try:
        require(job['kind']==KIND and job['project_id']==r['project_id'],'队列身份不同')
        project=validate(queue,r);folder=project/'renders'/r['render_id'];folder.mkdir(parents=True,exist_ok=True)
        output=folder/(r['template_id']+'-full.mp4');quality=folder/'qa.json';done=folder/'result.json'
        if done.exists():require(read_json(done)['output_sha256']==sha(output),'完成成片漂移')
        else:
            from tools.video.video_compose import VideoCompose
            from backlot.studio_investment_audio_v5 import measure_audio
            public=folder/'public';public.mkdir(exist_ok=True)
            for n in r['origins']:shutil.copy2(project/'assets/chromatic-suite-production'/n,public/n)
            atomic_private(folder/'props.json',r['props']);seconds=r['props']['durationInFrames']/30;raw=folder/'mezzanine.mp4'
            edits={'render_runtime':'remotion','composition_mode':'atelier','renderer_family':'bespoke','timeline':{'duration_seconds':seconds},'bespoke':{'entry':str(TEMPLATE/'Scene.tsx'),'composition_id':'ChromaticSuiteProduction','art_direction':str(TEMPLATE/'README.md'),'props_path':str(folder/'props.json'),'public_dir':str(public),'concurrency':2,**PROFILE}}
            if not raw.exists():
                rendered=VideoCompose().execute({'operation':'render','output_path':str(raw),'edit_decisions':edits,'asset_manifest':{'assets':[]},'script_text':r['receipts']['script']['text']})
                if not rendered.success:
                    atomic_private(folder/'render-diagnostic.json',{'error':str(rendered.error),'data':rendered.data});raise WorkError('渲染失败；诊断已保存：'+str(rendered.error)[-900:])
            ffmpeg,_=resolve_ffmpeg_pair()
            subprocess.run([ffmpeg,'-nostdin','-y','-v','error','-i',str(raw),'-i',str(public/'master.wav'),'-map','0:v:0','-map','1:a:0','-t',str(seconds),'-c:v','libx264','-preset','fast','-b:v','21000k','-minrate','21000k','-maxrate','21000k','-bufsize','2100k','-x264-params','nal-hrd=cbr:force-cfr=1:filler=1','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart',str(output)],check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            info=media_probe(output);v=info.get('video')or{};audio=measure_audio(output)
            require((v.get('width'),v.get('height'))==(1080,1920) and int(v.get('nb_frames',0))==r['props']['durationInFrames'] and abs(float(Fraction(v.get('avg_frame_rate','0/1')))-30)<.001 and int(v.get('bit_rate',0))>=20000000 and info.get('audio') and audio['true_peak_dbtp']<=-1.5,'正式输出参数/声音不达标')
            subprocess.run([ffmpeg,'-nostdin','-v','error','-xerror','-i',str(output),'-f','null','-'],check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            atomic_private(quality,{'technical':'pass','full_decode':'pass','media':info,'audio':audio,'contract_consumption':r['contract_consumption'],'visual_review':'pending','continuous_listening':'pending','external_speaker_test':'pending'})
            atomic_private(done,{'output_sha256':sha(output),'qa_sha256':sha(quality),'request_sha256':r['request_sha256'],'publication':False})
        work=WorkCatalog(queue.projects_root).register(r['project_id'],output,work_key='main',mode='manual',event_id=job['job_id'],quality_passed=False,actor='motion-replay-chromatic-suite-production',title=r['title'],summary='完整B6原声；独立原动作布局；HQ首尾人物；待实际视听验收，未发布')
        return {'status':'completed','stage':r['template_id']+'完整HD视频已生成，待实际审阅','result':{'output_path':str(output),'output_sha256':sha(output),'work_id':work['work_id'],'qa_report':str(quality)}}
    except Exception as error:
        return {'status':'failed','stage':'原本地父任务待恢复','error':{'type':type(error).__name__,'message':str(error)[:800]},'retryable':True,'safe_resume_point':'motion_replay_chromatic_suite_production'}
