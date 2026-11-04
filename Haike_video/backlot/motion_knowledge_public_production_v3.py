"""Fixed queue producer for independently authored public knowledge scenes."""
from __future__ import annotations
import json,os,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
from backlot import motion_knowledge_public_execution_v3 as execution
from backlot.motion_knowledge_public_execution_v3 import ROOT,TEMPLATE,read,write,sha,require,digest
CONTRACT='haike.knowledge-reference-public/3'
KIND='studio_investment_recompose'
NO_WINDOW=0x08000000 if os.name=='nt' else 0
def runtime(data):
    config=read(Path(data)/'production.json');parent=Path(config['runtime_root'])
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    pair=resolve_ffmpeg_pair();require(pair is not None,'缺少既有FFmpeg/ffprobe；本入口不安装')
    values={'node':config.get('node_executable') or str(parent/'node/node.exe'),'browser':config['browser_executable'],'ffmpeg':pair[0],'ffprobe':pair[1]}
    for value in values.values():require(Path(value).is_file(),'所选既有运行组件缺失，不自动安装或换版本')
    return values
def identity(data):
    data=Path(data);return {'sources':execution.source_identity(),'inputs':{str(p.resolve()):sha(p) for p in [data/'production.json',data/'preparation.json',*(data/'public').rglob('*')] if p.is_file()},'runtime':{str(Path(p).resolve()):sha(p) for p in runtime(data).values()}}

def _frame_plan(data,e):
    data=Path(data);plan=read(data/'production.json').get('targeted_revision')
    if plan is None:return {'mode':'full_critical_states','frames':critical_frames(e)}
    require(isinstance(plan,dict) and set(plan)=={'schema','baseline_parent','baseline_review','scopes','frames'} and plan['schema']=='haike.knowledge-public-targeted-revision/2','定向复验必须绑定原实际审核、原父和具体失败状态')
    documents={}
    for key in ('baseline_parent','baseline_review'):
        binding=plan[key];path=Path(binding['path']).resolve()
        require(path.is_relative_to(ROOT/'.local') and path.is_file() and sha(path)==binding['sha256'],'定向复验原父/实际审核身份变化')
        documents[key]=read(path)
    parent,review=documents['baseline_parent'],documents['baseline_review']
    require(parent.get('implementation')=='knowledge-reference-public-v2' and parent.get('version')=='5.1.0-independent.1' and parent.get('template_id')==e['template_id'] and review.get('decision')=='changes_requested' and review.get('evidence',{}).get('actual_agent_viewing') is True and review.get('preview_binding',{}).get('identity_sha256')==digest(parent['identity']),'定向复验来源不是本组实际要求修改的v2预览')
    old_path=(Path(parent['data'])/'public/episode.json').resolve();require(sha(old_path)==parent['identity']['inputs'][str(old_path)],'原已审剧情/主时钟身份变化')
    old=read(old_path)
    require(set(e)==set(old) and all(e[k]==old[k] for k in e if k not in {'schema','implementation','version'}),'两缺陷定向修订不能改变原内容、模型、任何事件或完整声音/字幕时码')
    for key in ('narration','music'):
        if old.get(key):
            path=(Path(parent['data'])/'public'/old[key]).resolve();current=data/'public'/e[key]
            require(sha(path)==parent['identity']['inputs'][str(path)]==sha(current),'定向修订不能改变原声音/音乐字节')
    frames=plan['frames'];require(isinstance(frames,list) and 2<=len(frames)<=16 and all(isinstance(row,dict) and set(row)=={'frame','reason'} and type(row['frame'])is int and 0<=row['frame']<e['durationFrames'] and isinstance(row['reason'],str) and row['reason'].strip() for row in frames),'定向复验需有限、逐项说明失败点的真实帧')
    values=[row['frame'] for row in frames];require(values==sorted(set(values)),'两缺陷定向复验帧需唯一/有序，不再要求重验每场或全片首尾')
    require(plan['scopes']==(['paper.bulb-smoothing','paper.sticky-shadow'] if e['template_id']==execution.PAPER else ['chalk.material']),'本轮仅开放灯泡平滑/已定位便签重影或绿板材质定向复验')
    return {'mode':'targeted_failed_states_only','frames':values,'authority':plan}
def prepare(queue,value):
    require(isinstance(value,dict) and set(value)=={'data'},'生产准备只接受独立本期data')
    data=Path(value['data']).resolve();e,_=execution.validate(data);spec=read(data/'production.json');project=spec['project_id']
    require(Path(project).name==project and (Path(queue.projects_root)/project).is_dir(),'先在既有项目根初始化独立项目')
    prepared=execution.prepare({'template_id':e['template_id'],'version':execution.VERSION},value,workspace=ROOT)
    request={'contract':CONTRACT,'implementation':'knowledge-reference-public-v3','template_id':e['template_id'],'gallery_id':execution.GALLERY_IDS[e['template_id']],'version':execution.VERSION,'data':str(data),'project_id':project,'title':e['title'],
       'identity':identity(data),'registered_preparation':prepared,'inspection_plan':_frame_plan(data,e),'paid_calls':0,'publication':False}
    request['render_id']='knowledge-'+digest(request)[:20]
    return request
def validate(queue,request):
    require('review_binding' not in request or request.get('production_phase')=='render','预览身份不能包含审核绑定')
    base={k:v for k,v in request.items() if k not in {'production_phase','review_binding'}}
    require(base==prepare(queue,{'data':request['data']}),'源码、字体、时钟或本期输入已变化；保留原冻结，不自动重做')
    return execution.validate(request['data'])[0]

REVISION_REPAIR='保留原父和产物；从备份恢复原预览/审核的精确字节，或显式建立新revision的data与project_id后重新准备，不以新审核自动重建旧父'

def _key(request,phase):
    return CONTRACT+':'+phase+':'+request['render_id']

def _preview_snapshot(queue,request,e):
    """Bind the completed original queue parent, every expected PNG and receipt."""
    existing=queue.find_by_idempotency_key(_key(request,'preview'))
    require(existing is not None,'尚未提交本期开发预览；先沿公共队列提交preview')
    job=queue.get(existing['job_id'],include_private=True)
    require(job['status']=='completed' and not job['cancel_requested'],'原开发预览尚未完成或已请求取消；继续原父，不另建任务')
    expected={k:v for k,v in request.items() if k not in {'production_phase','review_binding'}}
    require(job['frozen_request']=={**expected,'production_phase':'preview'},'预览父与本期冻结请求不符；'+REVISION_REPAIR)
    data=Path(request['data']);path=data/'preview-result.json'
    require(path.is_file(),'已完成预览缺少清单；'+REVISION_REPAIR)
    preview=read(path)
    require(isinstance(preview,dict),'预览清单结构无效；'+REVISION_REPAIR)
    require(preview.get('queue_job_id')==job['job_id'] and preview.get('identity')==request['identity'],'预览清单与原父/源码身份不符；'+REVISION_REPAIR)
    out=Path(queue.projects_root)/request['project_id']/'renders'/('preview-'+request['render_id'])
    frames=request['inspection_plan']['frames'];images=preview.get('images')
    require(isinstance(images,list) and len(images)==len(frames) and all(isinstance(row,dict) for row in images),'预览关键帧清单缺失；'+REVISION_REPAIR)
    from PIL import Image
    for frame,row in zip(frames,images):
        image=(out/'frames'/(str(frame).zfill(6)+'.png')).resolve()
        require(row.get('frame')==frame and row.get('path')==str(image),'预览帧次序/位置不符；'+REVISION_REPAIR)
        require(image.is_file(),'预览PNG删失；'+REVISION_REPAIR)
        require(sha(image)==row.get('sha256'),'预览PNG字节变化；'+REVISION_REPAIR)
        try:
            with Image.open(image) as actual:
                require(actual.format=='PNG' and actual.size==(1080,1920),'预览PNG尺寸/编码无效；'+REVISION_REPAIR)
                actual.verify()
        except OSError as exc:
            raise ValueError('预览PNG无法解码；'+REVISION_REPAIR) from exc
    receipt=(out/'contract-consumption.json').resolve()
    require(preview.get('receipt')==str(receipt) and receipt.is_file(),'预览执行回执删失；'+REVISION_REPAIR)
    require(preview.get('receipt_sha256')==sha(receipt),'预览执行回执字节变化；'+REVISION_REPAIR)
    consumed=read(receipt)
    require(isinstance(consumed,dict),'预览执行回执结构无效；'+REVISION_REPAIR)
    require(consumed.get('contract')==CONTRACT and consumed.get('phase')=='preview' and consumed.get('queue_job_id')==job['job_id'] and consumed.get('identity')==request['identity'] and consumed.get('executed_internal_events')==execution.resolved_events(e),'预览执行回执与本期动作/原父不符；'+REVISION_REPAIR)
    return {'preview_job_id':job['job_id'],'identity_sha256':digest(request['identity']),
        'preview_manifest':{'path':str(path.resolve()),'sha256':sha(path)},
        'receipt':{'path':str(receipt),'sha256':sha(receipt)},'images':images}

def preview_integrity(queue,request):
    """Read-only integrity status, including completed-but-missing recovery advice."""
    existing=queue.find_by_idempotency_key(_key(request,'preview'))
    try:
        e=validate(queue,request);snapshot=_preview_snapshot(queue,request,e)
        return {'status':'ready','queue_job_id':snapshot['preview_job_id'],'binding':snapshot,'automatic_rebuild':False}
    except (ValueError,OSError,KeyError,TypeError) as exc:
        return {'status':'incomplete' if existing and existing['status']=='completed' else 'not_ready',
            'queue_job_id':existing['job_id'] if existing else None,'queue_status':existing['status'] if existing else None,
            'reason':str(exc),'repair':REVISION_REPAIR,'automatic_rebuild':False}

def _approved_binding(queue,request,e):
    snapshot=_preview_snapshot(queue,request,e);path=Path(request['data'])/'design-review.json'
    require(path.is_file(),'完整渲染入队前须明确批准本期完整预览')
    review=read(path)
    require(isinstance(review,dict),'审核记录结构无效；'+REVISION_REPAIR)
    require(review.get('schema')=='haike.knowledge-reference-public-review/3' and review.get('decision')=='approve','本期审核未批准（reject/changes_requested均不能导出）')
    require(review.get('preview_binding')==snapshot,'审核没有绑定当前全部预览PNG；'+REVISION_REPAIR)
    evidence=review.get('evidence',{})
    require(evidence.get('decision')=='approve' and evidence.get('actual_agent_viewing') is True and evidence.get('images')==snapshot['images'] and isinstance(evidence.get('notes'),str) and evidence['notes'].strip(),'批准缺少实际查看及完整图片证据')
    return {'schema':'haike.knowledge-reference-public-render-review-binding/3','preview':snapshot,
        'review':{'path':str(path.resolve()),'sha256':sha(path),'decision':'approve'}}

def _verify_render_binding(queue,request,e):
    require(request.get('production_phase')=='render' and isinstance(request.get('review_binding'),dict),'完整渲染缺少入队时冻结的具体审核绑定')
    require(request['review_binding']==_approved_binding(queue,request,e),'等待期间审核/预览绑定已变化；'+REVISION_REPAIR)

def _parent(queue,job):
    request=job.get('frozen_request') or {};phase=request.get('production_phase')
    require(job.get('kind')==KIND and request.get('contract')==CONTRACT and phase in {'preview','render'}
        and job.get('project_id')==request.get('project_id') and job.get('parent_job_id')==phase+'-'+str(request.get('render_id')),'知识v2原父kind/project/parent/精确合同不符')
    original=queue.find_by_idempotency_key(_key(request,phase))
    require(original is not None and original['job_id']==job.get('job_id'),'知识v2原父与本期固定幂等键不符')
    return request

def validate_claim(queue,job_id):
    """Read-only admission check before the root dispatcher acquires any lease."""
    job=queue.get(job_id,include_private=True);request=_parent(queue,job)
    require((job['status']=='paused' or job['status']=='failed' and job['retryable']) and not job['cancel_requested'],'原父当前不可领取或已取消；保留原任务')
    e=validate(queue,request)
    if request['production_phase']=='render':
        require(not e.get('previewOnly'),'示意模型测试不能完整导出');_verify_render_binding(queue,request,e)
    return {'job_id':job_id,'claim_ready':True,'phase':request['production_phase'],'request_sha256':digest(request),'frozen_sha256':digest(request),'side_effects':False}

def _claimed(queue,job):
    actual=queue.get(job['job_id'],include_private=True);request=_parent(queue,actual)
    require(actual.get('status')=='running' and actual.get('frozen_request')==job.get('frozen_request')
        and all(actual.get(k)==job.get(k) for k in ('job_id','kind','project_id','parent_job_id','worker_id','attempt_count'))
        and isinstance(actual.get('worker_id'),str) and bool(actual['worker_id'])
        and type(actual.get('attempt_count'))is int and actual['attempt_count']>0,'知识v2真实领取身份/冻结/工作者/尝试次数不符')
    expiry=actual.get('lease_expires_at')
    try:deadline=datetime.fromisoformat(expiry.replace('Z','+00:00')) if isinstance(expiry,str) else None
    except ValueError:deadline=None
    require(deadline is not None and deadline.tzinfo is not None and deadline>datetime.now(timezone.utc),'知识v2原父领取租约已失效')
    require(not actual['cancel_requested'],'知识v2原父已请求取消；保留现场，不记成功')
    return request

def _execution_boundary(queue,job,e=None):
    request=_claimed(queue,job);e=validate(queue,request) if e is None else e
    if request['production_phase']=='render':_verify_render_binding(queue,request,e)
    return e

def submit(queue,request,*,phase='preview'):
    chosen=request.get('production_phase') or phase
    require(chosen in {'preview','render'} and phase in {'preview',chosen},'未知或冲突阶段')
    e=validate(queue,request);require(chosen!='render' or not e.get('previewOnly'),'示意模型测试不能冒称完整生产')
    frozen={**request,'production_phase':chosen}
    if chosen=='render':
        binding=_approved_binding(queue,request,e)
        require('review_binding' not in request or request['review_binding']==binding,'调用方审核绑定已过期；'+REVISION_REPAIR)
        frozen['review_binding']=binding
        existing=queue.find_by_idempotency_key(_key(request,chosen))
        if existing:
            require(queue.get(existing['job_id'],include_private=True)['frozen_request']==frozen,'原渲染父已绑定另一审核；'+REVISION_REPAIR)
    result=queue.submit(project_id=request['project_id'],kind=KIND,source='codex',priority='normal',parent_job_id=chosen+'-'+request['render_id'],frozen_request=frozen,
        idempotency_key=_key(request,chosen),start_paused=True)
    if chosen=='preview' and result['status']=='completed':result['artifact_integrity']=preview_integrity(queue,request)
    return result
def critical_frames(e):
    total=e['durationFrames'];frames={0,total-1}
    for s in e['scenes']:
        frames.update([s['from'],max(0,s['from']-1),s['to']-1])
        for ev in s['events']:frames.update([ev['at'],ev['at']+ev['duration']//2,ev['at']+ev['duration']])
    for c in e['captions']:frames.add(round((c['startMs']+c['endMs'])/2000*e['fps']))
    return sorted(v for v in frames if 0<=v<total)
def review(queue,request,evidence):
    e=validate(queue,request);data=Path(request['data']);snapshot=_preview_snapshot(queue,request,e)
    require(isinstance(evidence,dict) and evidence.get('decision') in {'approve','reject','changes_requested'},'审核必须明确选择approve/reject/changes_requested')
    require(evidence.get('actual_agent_viewing') is True and isinstance(evidence.get('notes'),str) and evidence['notes'].strip(),'必须实际查看同源开发图并记录所见差异')
    require(evidence.get('images')==snapshot['images'],'必须逐项绑定实际开发关键帧，不接受空审核')
    record={'schema':'haike.knowledge-reference-public-review/3','decision':evidence['decision'],'preview_binding':snapshot,'evidence':evidence,
        'scope':'Sampled independent-reference visual check only; no original package redistribution/continuous listening claim'}
    write(data/'design-review.json',record)
    return {'status':{'approve':'approved','reject':'rejected','changes_requested':'changes_requested'}[evidence['decision']],
        'decision':evidence['decision'],'data':str(data),'preview_job_id':snapshot['preview_job_id']}
def probe(rt,path):return json.loads(subprocess.check_output([rt['ffprobe'],'-v','error','-show_streams','-show_format','-of','json',str(path)],timeout=30,creationflags=NO_WINDOW))
def run(queue,job):
    request=_claimed(queue,job);e=_execution_boundary(queue,job);data=Path(request['data']);phase=request['production_phase']
    rt=runtime(data)
    out=Path(queue.projects_root)/request['project_id']/'renders'/(phase+'-'+request['render_id']);out.mkdir(parents=True,exist_ok=True)
    with (out/'bundle.log').open('w',encoding='utf-8') as stream:
        if not (data/'bundle/index.html').exists():
            subprocess.run([rt['node'],str(TEMPLATE/'render.cjs'),'bundle',str(data)],check=True,stdout=stream,stderr=subprocess.STDOUT,timeout=300,creationflags=NO_WINDOW)
            write(data/'bundle-binding.json',{'identity':identity(data),'files':{str(p.relative_to(data/'bundle')):sha(p) for p in (data/'bundle').rglob('*') if p.is_file()}})
    binding=read(data/'bundle-binding.json');require(binding['identity']==identity(data),'bundle与冻结源不一致')
    require(binding['files']=={str(p.relative_to(data/'bundle')):sha(p) for p in (data/'bundle').rglob('*') if p.is_file()},'开发bundle字节变化')
    _execution_boundary(queue,job)
    target=out/'frames' if phase=='preview' else out/'silent.mp4';frames=request['inspection_plan']['frames']
    with (out/'render.log').open('w',encoding='utf-8') as stream:
        subprocess.run([rt['node'],str(TEMPLATE/'render.cjs'),phase,str(data),str(target),rt['browser'],','.join(map(str,frames))],check=True,stdout=stream,stderr=subprocess.STDOUT,timeout=10800,creationflags=NO_WINDOW)
    _execution_boundary(queue,job)
    receipt={'contract':CONTRACT,'implementation':request['implementation'],'template_id':e['template_id'],'gallery_id':execution.GALLERY_IDS[e['template_id']],'version':execution.VERSION,'queue_job_id':job['job_id'],'phase':phase,
      'identity':request['identity'],'registered_preparation':request['registered_preparation'],'executed_internal_events':execution.resolved_events(e),'review_binding':request.get('review_binding'),'inspection_plan':request['inspection_plan'],
      'fps':e['fps'],'duration_frames':e['durationFrames'],'episode_sha256':sha(data/'public/episode.json'),'original_materials':'OFL fonts + input voice/music/ASR only; all graphics independently authored','new_paid_calls':0}
    write(out/'contract-consumption.json',receipt)
    if phase=='preview':
        value={'queue_job_id':job['job_id'],'identity':identity(data),'receipt':str(out/'contract-consumption.json'),'receipt_sha256':sha(out/'contract-consumption.json'),'images':[{'frame':f,'path':str(target/(str(f).zfill(6)+'.png')),'sha256':sha(target/(str(f).zfill(6)+'.png'))} for f in frames]}
        write(data/'preview-result.json',value);return {'status':'completed','stage':'独立知识开发关键帧已生成，待实际对照','result':{'preview_dir':str(target),'frames':len(frames),'receipt':str(out/'contract-consumption.json')}}
    master=out/'master.wav';seconds=e['durationFrames']/e['fps'];inputs=['-i',str(data/'public'/e['narration'])]
    if e.get('music'):
        inputs+=['-i',str(data/'public'/e['music'])];graph=f'[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=-1dB,apad,atrim=duration={seconds},asplit=2[voice][control];[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={e["musicGainDb"]}dB,apad,atrim=duration={seconds}[music];[music][control]sidechaincompress=threshold=0.04:ratio=2.5:attack=35:release=350:mix=0.7[ducked];[voice][ducked]amix=inputs=2:normalize=0,aresample=192000,alimiter=limit=0.70:level=false:latency=1,aresample=48000,atrim=duration={seconds}[out]'
    else:graph=f'[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=-1dB,apad,atrim=duration={seconds},alimiter=limit=0.70:level=false:latency=1[out]'
    subprocess.run([rt['ffmpeg'],'-nostdin','-v','error','-y',*inputs,'-filter_complex',graph,'-map','[out]','-c:a','pcm_s16le',str(master)],check=True,capture_output=True,timeout=180,creationflags=NO_WINDOW)
    final=out/'knowledge-full.mp4';subprocess.run([rt['ffmpeg'],'-nostdin','-v','error','-y','-i',str(target),'-i',str(master),'-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(seconds),'-movflags','+faststart',str(final)],check=True,capture_output=True,timeout=180,creationflags=NO_WINDOW)
    value=probe(rt,final);video=next(v for v in value['streams'] if v['codec_type']=='video');require((video['width'],video['height'])==(1080,1920) and int(video['nb_frames'])==e['durationFrames'] and int(video['bit_rate'])>=20000000,'完整HD/20Mbps/帧数验收失败')
    subprocess.run([rt['ffmpeg'],'-nostdin','-v','error','-xerror','-i',str(final),'-f','null','-'],check=True,capture_output=True,timeout=300,creationflags=NO_WINDOW)
    cover=out/'cover.png';subprocess.run([rt['ffmpeg'],'-nostdin','-v','error','-y','-ss','5.5','-i',str(final),'-frames:v','1',str(cover)],check=True,capture_output=True,timeout=30,creationflags=NO_WINDOW)
    _execution_boundary(queue,job)
    qa={'status':'technical_pass_actual_visual_audio_pending','probe':value,'sha256':sha(final),'full_decode':'pass','continuous_listening':'not_performed','device_listening':'not_performed','reference_fidelity':'pending_actual_comparison','receipt':str(out/'contract-consumption.json')};write(out/'quality.json',qa)
    from backlot.work_catalog import WorkCatalog
    work=WorkCatalog(queue.projects_root).register(request['project_id'],final,work_key='knowledge-public-independent',mode='manual',event_id=job['job_id'],quality_passed=False,title=e['title'],actor='public-knowledge-reference',summary='独立公开知识图解，完整HD有声；原风格/编码图/听审分项待验',ffprobe=rt['ffprobe'])
    result={'queue_job_id':job['job_id'],'output_video':str(final),'cover':str(cover),'work_id':work['work_id'],'quality':str(out/'quality.json'),'receipt':str(out/'contract-consumption.json')};write(data/'render-result.json',result)
    return {'status':'completed','stage':'独立知识完整视频已生成，待实际画面声音验收','result':result}
