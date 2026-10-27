"""Local, queue-owned five-second contrast design tests; no provider calls."""
from pathlib import Path
import shutil
import subprocess
from backlot.studio import atomic_private
from backlot.studio_investment_recompose import KIND, fingerprint
from backlot.work_catalog import WorkCatalog, WorkError, read_json, regular_path, sha

CONTRACT='investment-contrast-five-v1'
ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/'templates/investment-contrast-v1'
PROFILE={'codec':'h264','video_bitrate':'20M','crf':None,'image_format':'png','x264_preset':'slow','pixel_format':'yuv420p','scale':1}

def runtime():
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    files=[Path(__file__),TEMPLATE/'index.tsx',ROOT/'backlot/production_queue_worker.py',ROOT/'tools/video/video_compose.py',Path('C:/Windows/Fonts/msyh.ttc'),Path('C:/Windows/Fonts/msyhbd.ttc')]
    files.extend(Path(p) for p in resolve_ffmpeg_pair())
    return {str(p):sha(p) for p in files}

def prepare(queue,style,sources,title):
    if style not in (11,12,13) or set(sources)!={'avatar.mp4','shop.mp4','interaction.mp4','master.wav','audio-receipt.json','audio-plan.json','cue-evidence.json'}:
        raise WorkError('撞色短样需模板11/12/13与完整素材、混音和字幕来源')
    origins={k:{'path':str(Path(v).resolve()),'sha256':sha(v)} for k,v in sources.items()}
    signature=fingerprint({'style':style,'sources':origins,'runtime':runtime(),'profile':PROFILE})
    project_id='studio-'+signature[:16]
    project=queue.projects_root/project_id
    from lib.checkpoint import init_project
    frozen=project/'artifacts/contrast-request.json'
    if frozen.exists():
        request=read_json(frozen);validate(queue,request);return request
    init_project(project_id,title=title,pipeline_type='animated-explainer',pipeline_dir=queue.projects_root)
    assets=project/'assets/contrast';assets.mkdir(parents=True,exist_ok=True)
    for name,item in origins.items():shutil.copy2(item['path'],assets/name)
    core={'contract':CONTRACT,'project_id':project_id,'style':style,'title':title,'origins':origins,'runtime':runtime(),'profile':PROFILE,'duration':5,'frames':150,'width':1440,'height':1800,'fps':30,'development_test':True,'cloud_calls':0,'publication':False}
    digest=fingerprint(core);request={**core,'request_sha256':digest,'render_id':'local-contrast-'+digest[:20]}
    atomic_private(frozen,request);validate(queue,request);return request

def validate(queue,r):
    core={k:v for k,v in r.items() if k not in ('request_sha256','render_id')}
    digest=fingerprint(core)
    if r.get('contract')!=CONTRACT or r.get('request_sha256')!=digest or r.get('render_id')!='local-contrast-'+digest[:20] or r.get('profile')!=PROFILE or r.get('style') not in (11,12,13):raise WorkError('撞色短样请求身份错误')
    project=WorkCatalog(queue.projects_root).project(r['project_id'])
    if read_json(project/'artifacts/contrast-request.json')!=r:raise WorkError('冻结请求不一致')
    for name,item in r['origins'].items():
        if sha(regular_path(project/'assets/contrast'/name,project))!=item['sha256']:raise WorkError('素材已变化')
    final=project/'renders'/r['render_id']/'result.json'
    if final.exists():
        receipt=read_json(final)
        if receipt.get('request_sha256')!=digest or sha(project/'renders'/r['render_id']/'avatar-preview.mp4')!=receipt.get('output_sha256'):raise WorkError('已完成产物身份不一致')
    elif runtime()!=r['runtime']:raise WorkError('实现已变化，请创建新请求')
    return project

def submit(queue,r):
    validate(queue,r)
    return queue.submit(project_id=r['project_id'],kind=KIND,source='codex',priority='normal',parent_job_id=r['render_id'],frozen_request=r,idempotency_key=CONTRACT+':'+r['request_sha256'],start_paused=True)

def run(queue,job):
    r=job['frozen_request']
    try:
        if job['kind']!=KIND or job['project_id']!=r['project_id']:raise WorkError('队列身份不匹配')
        project=validate(queue,r);folder=project/'renders'/r['render_id'];folder.mkdir(parents=True,exist_ok=True)
        output=folder/'avatar-preview.mp4';receipt=read_json(folder/'result.json')
        if not receipt:
            from tools.video.video_compose import VideoCompose
            from backlot.studio_composition import mux_avatar_audio
            from backlot.studio_render import media_probe
            from backlot.studio_investment_audio_v5 import measure_audio
            from lib.ffmpeg_locator import resolve_ffmpeg_pair
            ffmpeg,_=resolve_ffmpeg_pair()
            public=folder/'public';public.mkdir(exist_ok=True)
            for name in ('avatar.mp4','shop.mp4','interaction.mp4','master.wav'):shutil.copy2(project/'assets/contrast'/name,public/name)
            shutil.copy2(TEMPLATE/'index.tsx',folder/'index.tsx')
            props={'style':r['style'],'avatar':'avatar.mp4','shop':'shop.mp4','interaction':'interaction.mp4','audio':'master.wav'}
            atomic_private(folder/'props.json',props)
            edits={'render_runtime':'remotion','composition_mode':'atelier','renderer_family':'bespoke','timeline':{'duration_seconds':5},'bespoke':{'entry':str(folder/'index.tsx'),'composition_id':'HaikeContrastFive','art_direction':str(TEMPLATE/'README.md'),'props_path':str(folder/'props.json'),'public_dir':str(public),'concurrency':2,**PROFILE}}
            raw=folder/'render.mp4'
            result=VideoCompose().execute({'operation':'render','output_path':str(raw),'edit_decisions':edits,'asset_manifest':{'assets':[]},'script_text':'AI这么火，生意到底怎么落地？看这家海客AI社区服务店。'})
            if not result.success:raise WorkError(str(result.error),'unavailable')
            mux_avatar_audio(ffmpeg,raw,public/'master.wav',output,5,prepared_master=True)
            info=media_probe(output);audio=measure_audio(output)
            v=info.get('video',{})
            if v.get('width')!=1440 or v.get('height')!=1800 or abs(info['duration']-5)>.06 or v.get('codec_name')!='h264' or audio['true_peak_dbtp']>-1.5:raise WorkError('短样编码/时长/声音峰值检查失败','unavailable')
            subprocess.run([ffmpeg,'-v','error','-i',str(output),'-f','null','-'],check=True,capture_output=True,creationflags=0x08000000)
            atomic_private(folder/'quality.json',{'media':info,'audio':audio,'profile':PROFILE,'render_command':(result.data or {}).get('render_command'),'full_decode':'passed','visual_review':'pending','listening':'pending'})
            validate(queue,r)
            receipt={'request_sha256':r['request_sha256'],'output_sha256':sha(output),'quality_sha256':sha(folder/'quality.json'),'cloud_calls':0,'publication':False}
            atomic_private(folder/'result.json',receipt)
        work=WorkCatalog(queue.projects_root).register(r['project_id'],output,work_key='main',mode='manual',event_id=job['job_id'],quality_passed=False,actor='local-contrast',title=r['title'],summary='5秒撞色设计测试；4:5；20Mbps目标；未发布')
        return {'status':'completed','stage':'撞色5秒样片完成，待审','result':{'output_path':str(output),'output_sha256':sha(output),'work_id':work['work_id'],'cloud_calls':0,'development_test':True}}
    except WorkError as e:return {'status':'failed','stage':str(e),'error':{'type':'ContrastSample','message':str(e)},'retryable':e.code=='unavailable','safe_resume_point':'contrast_sample'}
