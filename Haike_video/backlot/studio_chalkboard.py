"""Independent chalkboard reconstruction: public clock, reflow and queue authority."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from backlot.studio import atomic_private
from backlot.work_catalog import WorkCatalog,WorkError,read_json,sha
from backlot.studio_investment_recompose import fingerprint

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/'templates/chalkboard-explainer-v1'
DRIVER=ROOT/'scripts/chalkboard_render.cjs'
CONTRACT='haike-chalkboard-reconstruction-v1'
LAYOUTS={'4:5':(1440,1800),'9:16':(1080,1920)}


def require(ok,text):
    if not ok:raise WorkError(text)


def validate(props):
    require((props.get('width'),props.get('height')) in LAYOUTS.values(),'画幅须为已重排的4:5或9:16')
    require(props.get('fps') in {30,60} and type(props.get('durationFrames')) is int
            and 4<=props['durationFrames']/props['fps']<=600,'帧时钟或时长无效')
    seconds=props['durationFrames']/props['fps']
    chapters=props.get('chapters')
    require(isinstance(chapters,list) and 1<=len(chapters)<=40,'需要完整章节清单')
    cursor=0;ids=set()
    for row in chapters:
        require(row.get('id') and row['id'] not in ids,'章节ID重复或为空');ids.add(row['id'])
        require(row.get('kind') in {'orbit','surface','shadow','tilt','compare','recap'},'未实现的动作关系')
        require(abs(row['start']-cursor)<.001 and row['end']-row['start']>=8
                and row['end']<=seconds+.001,'章节须完整连续，保留至少8秒动作及阅读窗')
        require(isinstance(row.get('title'),str) and 1<=len(row['title'])<=17,'章节标题超过当前布局容量')
        require(isinstance(row.get('annotation'),list) and row['annotation']
                and all(isinstance(t,str) and len(t)<=27 for t in row['annotation']),'动作注解超过容量')
        cursor=row['end']
    require(abs(cursor-seconds)<.001,'章节必须覆盖整片')
    for window in props.get('surfaceWindows',[]):
        chapter=next((c for c in chapters if c['id']==window.get('chapter_id') and c['kind']=='surface'),None)
        require(chapter is not None,'放大窗口须属于实际surface章节')
        enter,exit=window.get('enter',[]),window.get('exit',[])
        require(len(enter)==len(exit)==2 and all(type(v) in {int,float} and math.isfinite(v) for v in enter+exit)
                and chapter['start']<=enter[0]<enter[1] and enter[1]+2<=exit[0]<exit[1]<=chapter['end'],
                '放大、完整阅读与归位窗口须有序，保留至少两秒阅读')
    for name in ['phaseKeys','nodeKeys']+(['comparisonPhaseKeys'] if props.get('comparisonPhaseKeys') else []):
        keys=props.get(name)
        require(isinstance(keys,list) and len(keys)>=2 and keys[0][0]==0 and keys[-1][0]>=seconds-.001,'连续模型时钟须覆盖全片')
        require(all(isinstance(k,list) and len(k)==2 and all(type(v) in {int,float} and math.isfinite(v) for v in k) for k in keys)
                and all(a[0]<b[0] for a,b in zip(keys,keys[1:])), '模型关键帧须严格有序且有限')
    model=props.get('model',{})
    required={'orbitRadius','bodyRadius','occluderRadius','sourceRadius','sourceDistance','inclinationDegrees','displayInclinationDegrees'}
    require(set(model)==required and all(type(v) in {int,float} and math.isfinite(v) for v in model.values()),'缺少完整物理模型')
    require(0<model['bodyRadius']<model['occluderRadius']<model['orbitRadius']<model['sourceDistance']
            and model['sourceRadius']>0 and 0<=model['inclinationDegrees']<90,'模型比例或单位无效')
    cursor=0
    for row in props.get('captions',[]):
        require(cursor<=row['start']<row['end']<=seconds+.001 and isinstance(row['text'],str)
                and 1<=len(row['text'])<=(46 if props['height']/props['width']>1.5 else 52),
                '字幕须为真实有序区间并符合当前两行容量；按实测边界拆句')
        cursor=row['end']
    for key in ['font','audio']:
        if props.get(key):
            require(Path(props[key]).name==props[key] and not any(c in props[key] for c in '/\\:'),
                    '素材使用已绑定的平面文件名')
    return seconds


def source_files():
    return [Path(__file__),DRIVER,ROOT/'backlot/production_queue_worker.py',ROOT/'backlot/work_catalog.py',
            ROOT/'remotion-composer/package-lock.json',*sorted(TEMPLATE.glob('*.ts')), *sorted(TEMPLATE.glob('*.tsx'))]


def caption_patch_frames(before, after):
    require({k:v for k,v in before.items() if k!='captions'}==
            {k:v for k,v in after.items() if k!='captions'},'字幕修订不能改变布局、物理模型或音轨')
    old,new=before.get('captions',[]),after.get('captions',[])
    require(len(old)==len(new),'字幕修订不能改变句数或实测时间')
    changed=[]
    for a,b in zip(old,new):
        require({k:v for k,v in a.items() if k!='text'}=={k:v for k,v in b.items() if k!='text'},
                '字幕修订只允许改文字，不能改变实测时间或句ID')
        if a['text']!=b['text']:changed.append(b)
    require(changed,'字幕修订没有实际文字变更')
    start=math.floor(min(c['start'] for c in changed)*after['fps'])
    end=math.ceil(max(c['end'] for c in changed)*after['fps'])
    require(0<start<end<after['durationFrames'] and (end-start)/after['fps']<=60,
            '当前局部字幕修订仅支持片内不超过60秒的区间，其余使用完整渲染')
    return [start,end-1]


def merge_caption_patch(ffmpeg, base, segment, target, frame_range, frame_count, fps, base_range='tv'):
    a,b=frame_range[0],frame_range[1]+1
    source='[0:v]scale=in_range=pc:out_range=tv,format=yuv420p,' if base_range=='pc' else '[0:v]'
    graph=(source+f'split=2[before][after];[before]trim=end_frame={a},setpts=PTS-STARTPTS[v0];'
           f'[1:v]setpts=PTS-STARTPTS[v1];[after]trim=start_frame={b}:end_frame={frame_count},'
           'setpts=PTS-STARTPTS[v2];[v0][v1][v2]concat=n=3:v=1:a=0[v]')
    subprocess.run([ffmpeg,'-nostdin','-v','error','-n','-i',str(base),'-i',str(segment),
        '-filter_complex',graph,'-map','[v]','-map','0:a:0?','-c:v','libx264','-preset','fast',
        '-b:v','21M','-minrate','21M','-maxrate','21M','-bufsize','42M',
        '-x264-params','nal-hrd=cbr:force-cfr=1:filler=1','-pix_fmt','yuv420p','-r',str(fps),
        '-frames:v',str(frame_count),'-c:a','copy','-colorspace','bt709','-color_primaries','bt709',
        '-color_trc','bt709','-color_range','tv','-movflags','+faststart',str(target)],capture_output=True,check=True,timeout=3600)


def mux_source_audio(ffmpeg, picture, audio, target, seconds):
    """Encode from the bound PCM source with native AAC priming metadata.

    Remotion's bundled encoder can leave two AAC frames ahead of the source.
    Copy the completed picture and retain the actual source clock at zero.
    """
    subprocess.run([ffmpeg,'-nostdin','-v','error','-n','-i',str(picture),'-i',str(audio),
        '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k',
        '-ar','48000','-ac','2','-af','apad','-t',str(seconds),'-movflags','+faststart',str(target)],
        capture_output=True,check=True,timeout=1800)


def freeze(queue,value):
    require(value.get('template_id')=='chalkboard-explainer-v1','模板身份无效')
    props=deepcopy(value['props']);validate(props)
    assets={}
    for name in {props.get('font'),props.get('audio')}-{None,''}:
        row=value.get('assets',{}).get(name,{})
        path=Path(row.get('path',''))
        require(path.is_absolute() and path.is_file() and not path.is_symlink() and sha(path)==row.get('sha256'),'素材缺失或SHA变化：'+name)
        assets[name]={'path':str(path),'sha256':sha(path)}
    require(props.get('font'),'须绑定本机合法字体，避免静默替代')
    tools={}
    for key in ['node','ffmpeg','ffprobe','browser']:
        row=value['tools'][key];path=Path(row['path'])
        require(path.is_file() and sha(path)==row['sha256'],'本地执行工具已变化：'+key)
        tools[key]={'path':str(path.resolve()),'sha256':sha(path)}
    require(value.get('reference',{}).get('source_sha256') and value.get('reference',{}).get('understanding_path'),
            '须提供本期参考身份与素材理解记录')
    from backlot.reference_understanding import load as load_understanding
    analysis_path=Path(value['reference']['understanding_path'])
    require(analysis_path.is_absolute() and analysis_path.is_file(),'素材理解记录不存在')
    analysis=read_json(analysis_path);task=load_understanding(analysis_path.parent/'task.json')
    require(analysis.get('task_fingerprint')==task['fingerprint']
            and analysis.get('source',{}).get('sha256')==value['reference']['source_sha256'],
            '参考片与已提交的素材理解不一致')
    files={str(p.resolve()):sha(p) for p in source_files()}
    reference={**value['reference'],'understanding_sha256':sha(analysis_path)}
    core={'contract':CONTRACT,'props':props,'assets':assets,'tools':tools,'source_files':files,
          'reference':reference,'paid_calls':0,'publication':False}
    require(not(value.get('caption_patch_from') and value.get('audio_remux_from')),'一次修订只选择一种复用来源')
    if value.get('caption_patch_from') or value.get('audio_remux_from'):
        source_request=value.get('caption_patch_from') or value['audio_remux_from']
        old_path=Path(source_request).resolve()
        require(old_path.is_relative_to(queue.projects_root.resolve()) and old_path.is_file(),
                '字幕修订须绑定本机既有项目的冻结请求')
        old=read_json(old_path)
        require(old.get('contract')==CONTRACT,'字幕修订来源不是本模板')
        base=queue.projects_root/old['project_id']/'renders'/old['render_id']/'chalkboard.mp4'
        quality=read_json(base.parent/'quality.json')
        require(quality.get('full_decode')=='passed' and base.is_file() and
                quality.get('video_sha256')==sha(base),'字幕修订须复用已完整解码的成片')
        require(old['tools']==tools and old['assets']==assets and
                old['reference']['source_sha256']==reference['source_sha256'],
                '字幕修订不得更换素材、工具或参考来源')
        visual=[p for p in source_files() if p.suffix in {'.ts','.tsx'} or p.name=='package-lock.json']
        require(all(old['source_files'].get(str(p.resolve()))==files[str(p.resolve())] for p in visual),
                '视觉源码变化，不能复用旧成片画面')
        reuse={'base_request':str(old_path),'base_request_sha256':sha(old_path),
            'base_video':str(base.resolve()),'base_sha256':sha(base),
            'base_range':next(s for s in quality['media']['streams'] if s['codec_type']=='video').get('color_range','tv')}
        if value.get('caption_patch_from'):
            reuse['frame_range']=caption_patch_frames(old['props'],props)
            core['caption_patch']=reuse
        else:
            require(old['props']==props and props.get('audio'),'音频编码修订须保持全部props及绑定音轨不变')
            core['audio_remux']=reuse
    identity=fingerprint(core)
    request={**core,'project_id':'chalk-'+identity[:20],'request_sha256':identity,'render_id':'chalk-'+identity[:24]}
    from lib.checkpoint import init_project
    project=queue.projects_root/request['project_id']
    path=project/'artifacts/chalkboard-request.json'
    if path.exists():
        require(read_json(path)==request,'冻结输入已变化，请保留原任务并新建版本')
        return request
    init_project(request['project_id'],title=props['title'],pipeline_type='animated-explainer',pipeline_dir=queue.projects_root)
    folder=project/'assets/chalkboard';folder.mkdir(parents=True,exist_ok=True)
    for name,row in assets.items():shutil.copy2(row['path'],folder/name)
    atomic_private(project/'artifacts/chalkboard-props.json',props)
    atomic_private(path,request)
    return request


def preview_frames(props):
    result={0,props['durationFrames']-1}
    for c in props['chapters']:
        for t in [c['start']+.35,c['start']+1.5,(c['start']+c['end'])/2,c['end']-.4]:
            result.add(min(props['durationFrames']-1,round(t*props['fps'])))
    return sorted(result)


def submit(queue,request,phase='preview'):
    require(phase in {'preview','render'},'制作阶段无效')
    if phase=='render':
        review=read_json(queue.projects_root/request['project_id']/'artifacts/chalkboard-preview-review.json')
        require(review.get('request_sha256')==request['request_sha256'],'请实际查看本期全部预览后提交审核')
    return queue.submit(project_id=request['project_id'],kind='studio_investment_recompose',source='codex',
        priority='normal',parent_job_id=request['render_id']+'-'+phase,
        frozen_request={**request,'phase':phase},idempotency_key=request['render_id']+'-'+phase,start_paused=True)


def review(queue,request,seen,description):
    folder=queue.projects_root/request['project_id']/'renders'/request['render_id']/'preview'
    expected={str(f)+'.png' for f in preview_frames(request['props'])}
    require(isinstance(seen,list) and len(seen)==len(expected) and set(seen)==expected
            and all((folder/n).is_file() for n in seen) and description.strip(),'须实际查看全部本期预览并记录描述')
    receipt={'request_sha256':request['request_sha256'],'seen':{n:sha(folder/n) for n in seen},
             'description':description,'scope':'sampled-preview','continuous_watch':'pending','continuous_listen':'pending'}
    atomic_private(queue.projects_root/request['project_id']/'artifacts/chalkboard-preview-review.json',receipt)
    return receipt


def run(queue,job):
    request=job['frozen_request'];props=request['props'];phase=request['phase']
    project=queue.projects_root/request['project_id'];out=project/'renders'/request['render_id'];out.mkdir(parents=True,exist_ok=True)
    try:
        expected=read_json(project/'artifacts/chalkboard-request.json')
        require({k:v for k,v in request.items() if k!='phase'}==expected,'任务与冻结请求不一致')
        for path,digest in request['source_files'].items():require(sha(path)==digest,'渲染源码已变化，请重新冻结')
        require(sha(request['reference']['understanding_path'])==request['reference']['understanding_sha256'],
                '素材理解记录变化，请保留原请求并重新冻结')
        for row in request['tools'].values():require(sha(row['path'])==row['sha256'],'渲染工具已变化')
        assets=project/'assets/chalkboard'
        for name,row in request['assets'].items():require(sha(assets/name)==row['sha256'],'冻结素材已变化')
        tools=request['tools'];env=dict(os.environ,PYTHONUTF8='1',REMOTION_BROWSER_EXECUTABLE=tools['browser']['path'])
        env['PATH']=str(Path(tools['ffmpeg']['path']).parent)+os.pathsep+env['PATH']
        target=out/'preview' if phase=='preview' else out/'chalkboard.mp4'
        reuse=request.get('caption_patch') or request.get('audio_remux')
        if reuse:
            require(sha(reuse['base_request'])==reuse['base_request_sha256'] and
                    sha(reuse['base_video'])==reuse['base_sha256'],'复用的基础成片或请求已变化')
        if phase=='preview' and request.get('audio_remux'):
            old=read_json(reuse['base_request']);old_project=queue.projects_root/old['project_id']
            seen=read_json(old_project/'artifacts/chalkboard-preview-review.json')
            require(seen.get('request_sha256')==old['request_sha256'] and
                    set(seen.get('seen',{}))=={str(f)+'.png' for f in preview_frames(props)},
                    '同画面复用须有完整原预览审核')
            target.mkdir(exist_ok=True)
            for name,digest in seen['seen'].items():
                picture=old_project/'renders'/old['render_id']/'preview'/name
                require(sha(picture)==digest,'原预览已变化')
                shutil.copy2(picture,target/name)
        if phase=='render':
            receipt=read_json(project/'artifacts/chalkboard-preview-review.json')
            require(receipt.get('request_sha256')==request['request_sha256'] and
                all(sha(out/'preview'/n)==h for n,h in receipt['seen'].items()),'本期预览审核已失效')
        complete=all((target/(str(f)+'.png')).is_file() for f in preview_frames(props)) if phase=='preview' else False
        patch=request.get('caption_patch') if phase=='render' else None
        if phase=='render' and target.is_file():
            cached=read_json(out/'quality.json') if (out/'quality.json').is_file() else {}
            complete=cached.get('full_decode')=='passed' and cached.get('video_sha256')==sha(target)
            if not complete:target.rename(out/('incomplete-'+uuid4().hex+'.mp4'))
        if not complete:
            encoded=out/'caption-patch.mp4' if patch else target
            if not request.get('audio_remux'):
                with (out/(phase+'.log')).open('a',encoding='utf-8') as log:
                    result=subprocess.run([tools['node']['path'],str(DRIVER),phase,str(project/'artifacts/chalkboard-props.json'),
                        str(assets),str(encoded),json.dumps(preview_frames(props)),
                        json.dumps(patch['frame_range'] if patch else None)],cwd=ROOT/'remotion-composer',env=env,
                        stdout=log,stderr=subprocess.STDOUT,timeout=14400,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                require(result.returncode==0,'本地渲染未完成；原日志、音轨和请求保留')
                if patch:merge_caption_patch(tools['ffmpeg']['path'],patch['base_video'],encoded,target,
                                             patch['frame_range'],props['durationFrames'],props['fps'],patch['base_range'])
            if phase=='render' and props.get('audio'):
                picture=Path(reuse['base_video']) if request.get('audio_remux') else out/('picture-'+uuid4().hex+'.mp4')
                if not request.get('audio_remux'):target.rename(picture)
                mux_source_audio(tools['ffmpeg']['path'],picture,assets/props['audio'],target,
                                 props['durationFrames']/props['fps'])
        if phase=='preview':
            return {'status':'completed','stage':'粉笔黑板预览待实际审核','result':{'preview_path':str(target),'frames':preview_frames(props)}}
        ffmpeg,ffprobe=tools['ffmpeg']['path'],tools['ffprobe']['path']
        probe=subprocess.run([ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(target)],capture_output=True,text=True,check=True)
        media=json.loads(probe.stdout);video=next(s for s in media['streams'] if s['codec_type']=='video')
        require((video['width'],video['height'])==(props['width'],props['height']) and
            int(video['nb_frames'])==props['durationFrames'] and float(Fraction(video['avg_frame_rate']))==props['fps'] and
            video['pix_fmt']=='yuv420p' and video.get('color_range')=='tv' and
            int(video['bit_rate'])>=20000000,'完整帧数、画幅、帧率、色彩范围或20Mbps未通过')
        subprocess.run([ffmpeg,'-nostdin','-v','error','-i',str(target),'-f','null','-'],capture_output=True,check=True,timeout=1800)
        atomic_private(out/'quality.json',{'media':media,'full_decode':'passed','video_sha256':sha(target),
            'visual':'preview-sampled','continuous_watch':'pending','continuous_listen':'pending',
            'reference':request['reference'],'layout':'independent-element-reflow',
            'audio_encoding':'native AAC from bound source at zero; picture stream copied' if props.get('audio') else 'none'})
        work=WorkCatalog(queue.projects_root).register(request['project_id'],target,work_key='main',mode='manual',
            event_id=job['job_id'],quality_passed=False,actor='chalkboard-reconstruction',title=props['title'],
            summary='粉笔黑板独立适配测试，完整模型时钟与参考音轨；未发布',ffprobe=ffprobe)
        return {'status':'completed','stage':'粉笔黑板成片已导出，待连续听看','result':{'work_id':work['work_id'],'output_path':str(target),'qa_status':'pending'}}
    except (WorkError,subprocess.SubprocessError,OSError,ValueError,KeyError) as exc:
        return {'status':'failed','stage':'粉笔黑板制作待恢复','error':{'type':'ChalkboardRender','message':str(exc)[:800]},
                'retryable':True,'safe_resume_point':'chalkboard-frozen-request'}
