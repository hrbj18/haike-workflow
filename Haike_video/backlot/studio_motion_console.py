"""Source-bound preparation for the official console native recipes.

This module never generates speech/presenters or exports a complete movie.
The reviewed project is handed to studio_dark_native and its existing queue.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess

import jsonschema

from backlot.studio import atomic_private
from backlot.work_catalog import read_json,sha
from backlot.studio_investment_recompose import fingerprint
from backlot import studio_dark_native as native
from backlot import studio_motiongit as packages
from backlot.studio_dark_full_script import spoken
from backlot.studio_dark_native_content import _captions, _voice_proof

ROOT=Path(__file__).resolve().parents[1]
PROFILE=ROOT/'templates/motiongit-console-v1/source-contract.json'
SCHEMA='haike.motion-console-build/1'
NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)
require=native.require


def bound(path):
    path=Path(path).resolve()
    require(path.is_file() and not path.is_symlink(),'控制台输入文件缺失或不是普通文件')
    return {'path':str(path),'sha256':sha(path)}


def checked(value):
    require(isinstance(value,dict) and isinstance(value.get('path'),str),'控制台输入未绑定文件身份')
    path=Path(value['path'])
    require(path.is_absolute() and path.is_file() and not path.is_symlink() and sha(path)==value.get('sha256'),
            '控制台源文件身份已变化，请保留原任务并重新绑定')
    return path


def _run(command,timeout=300,env=None,log=None):
    result=subprocess.run(list(map(str,command)),capture_output=True,timeout=timeout,env=env,creationflags=NO_WINDOW)
    if log is not None:Path(log).write_bytes(result.stdout+b'\n'+result.stderr)
    require(result.returncode==0,'控制台本地准备未完成；原输入保留，请检查本期私有日志')
    return result


def _probe(tools,path):
    result=_run([checked(tools['ffprobe']),'-v','error','-show_streams','-show_format','-of','json',path],60)
    return json.loads(result.stdout)


def _seconds(info):return float(info['format']['duration'])


def _srt_time(seconds):
    total=round(seconds*1000);ms=total%1000;total//=1000
    return f'{total//3600:02}:{total//60%60:02}:{total%60:02},{ms:03}'


def sentence_boundaries(captions,segments):
    frames=0
    for segment in segments[:-1]:
        frames+=segment['durationFrames'];boundary=frames/60
        require(not any(c['t0']+1e-6<boundary<c['t1']-1e-6 for c in captions),
                f'完整动作组在{boundary:.3f}秒切断真实字幕句；须按实际句间隙重新安排完整组')


def following_frames(segments,groups):
    remaining=sum(s['durationFrames'] for s in segments)
    for segment in segments:
        remaining-=segment['durationFrames']
        require(remaining>=groups[segment['recipe']].get('minFollowingFrames',0),
                '此动作组的原生退场需要后续帧；请选择可结束的完整组，不截断原生动作或音效尾部')


def fit_segments(segments,captions,seconds,groups):
    """Fit complete groups to genuine sentence gaps, keeping native cue clocks."""
    require(type(seconds) in {int,float} and math.isfinite(seconds) and seconds>0,
            '完整口播时长无效')
    total=math.ceil(seconds*5-1e-8)*12
    require(captions and all(0<=c['t0']<c['t1']<=seconds+.001 for c in captions),
            '需要本期完整的真实字幕时间')
    require(all(a['t1']<=b['t0']+.001 for a,b in zip(captions,captions[1:])),
            '字幕时间重叠，不能确定完整句间隙')
    candidates=[f for f in range(1,total) if not any(c['t0']+1e-6<f/60<c['t1']-1e-6 for c in captions)]
    weight=sum(s['durationFrames'] for s in segments);states={0:(0,[])};elapsed=0
    for i,segment in enumerate(segments):
        rule=groups[segment['recipe']];elapsed+=segment['durationFrames']
        minimum=max(rule['minFrames'],math.ceil(max(segment.get('anchors',{}).values(),default=0)*60)+1)
        maximum=rule['minFrames']+rule['maxHoldFrames'];following=rule.get('minFollowingFrames',0)
        target=total*elapsed/weight;next_states={}
        for end in ([total] if i==len(segments)-1 else candidates):
            if total-end<following:continue
            best=None
            for start,(cost,path) in states.items():
                if minimum<=end-start<=maximum:
                    proposal=(cost+(end-target)**2,path+[end-start])
                    if best is None or proposal[0]<best[0]:best=proposal
            if best is not None:next_states[end]=best
        states=next_states
    require(total in states,'当前完整动作组合无法适配本期口播；需重新选择完整组，不能截句或变速')
    result=deepcopy(segments)
    for segment,frames in zip(result,states[total][1]):segment['durationFrames']=frames
    sentence_boundaries(captions,result);following_frames(result,groups)
    return result


def plan_facts(report,frames,recipes,layout='landscape'):
    contract=report.get('native_contract',{})
    require(report.get('status')=='ready-for-review' and report.get('mode')=='native'
            and report.get('layout')==layout and report.get('fps')==60
            and report.get('total_frames')==frames and not report.get('problems')
            and not report.get('whole_sentence_crossings') and contract.get('ready') is True
            and contract.get('status')=='ready' and not contract.get('blocking') and not contract.get('missing')
            and contract.get('durationFrames')==frames and contract.get('selectedScenes')==recipes,
            '控制台官方计划未通过或不匹配本期完整编排，请查看原报告')
    return contract


def media_windows(media,segments):
    """Only selected recipes consume slots; include their entire playback window."""
    require(isinstance(media,dict),'控制台素材需要对象')
    windows=[]
    for segment in segments:
        seconds=segment['durationFrames']/60
        if segment['recipe']=='works-fan':
            wall=media.get('wall')
            require(isinstance(wall,list) and len(wall)==6,'扇形展陈需要六个真实视频槽')
            for i,row in enumerate(wall):
                require(isinstance(row,dict),'扇形素材槽无效')
                windows.append((f'wall.{i}',row,row.get('at'),seconds))
        elif segment['recipe']=='result-inspector':
            row=media.get('lens')
            require(isinstance(row,dict),'焦点检查动作需要实拍窗口素材')
            windows.append(('lens',row,row.get('offset'),seconds))
    return windows


def review_media(windows,review,tools):
    require(review.get('status')=='pass' and isinstance(review.get('materials'),list),
            '真实素材尚未完成本期审核')
    for label,row,start,seconds in windows:
        raw=checked(row.get('source'))
        require(raw.suffix.lower() in {'.mp4','.mov','.m4v','.mkv','.webm'},
                '控制台原生实拍槽需要真实视频；静态图片请选择已声明的图片组件')
        require(type(start) in {int,float} and math.isfinite(start) and start>=0,
                f'{label}素材入点须为非负秒数')
        info=_probe(tools,raw)
        require(any(s.get('codec_type')=='video' for s in info['streams'])
                and start+seconds<=_seconds(info)+.001,'实拍素材区间不足以覆盖完整动作：'+label)
        matches=[r for r in review['materials'] if r.get('source_sha256')==sha(raw)
                 and r.get('source_start_seconds',0)-.001<=start
                 and r.get('source_end_seconds',0)+.001>=start+seconds
                 and r.get('actual_images_viewed')]
        require(matches,'本期控制台素材的完整使用区间未被实际审核：'+label)
        for image in matches[0]['actual_images_viewed']:checked(image)


def source(value):
    """Verify exact speech/provenance before any official package operation."""
    require(isinstance(value,dict),'控制台输入需要JSON对象')
    profile=read_json(PROFILE)
    required={'title','brand','voice','captions','avatar','tools','media','music','console','source_review'}
    require(required<=set(value),'控制台输入缺少完整声音、人物、素材或编排')
    tools=value['tools']
    for key in ['node','helper','package','ffmpeg','ffprobe']:checked(tools[key])
    require(sha(checked(tools['helper']))==packages.HELPER_SHA,'控制台官方入口未核验')
    package=packages.inspect_package(checked(tools['package']))
    require(package['template_id']==profile['template_id'] and package['version'] in profile['versions']
            and package['support']=='official-helper','此控制台适配器不匹配当前原包版本')
    voice=checked(value['voice']);clock=native.speech._clock(voice)
    _,caps=_captions(value['captions'],Path.cwd(),value['voice'],clock['duration_seconds'])
    require(spoken(''.join(c['zh'] for c in caps))==spoken(value.get('script',''.join(c['zh'] for c in caps))),
            '控制台文稿与完整字幕不同')
    avatar=checked(value['avatar']);proof=read_json(checked(value['avatar']['evidence']))
    require(_voice_proof(proof,sha(voice)) and proof.get('video_sha256',proof.get('sha256'))==sha(avatar)
            and str(proof.get('actual_view_status','')).startswith('pass') and proof.get('full_decode')=='passed','人物没有本期同声源和实际看帧依据')
    review=read_json(checked(value['source_review']))
    video=_probe(tools,avatar)
    require(any(s.get('codec_type')=='video' for s in video['streams'])
            and _seconds(video)+.001>=clock['duration_seconds'],'控制台人物不足以覆盖完整口播')
    c=value['console'];crop=c.get('presenterCrop')
    require(c.get('layout','landscape') in {'landscape','portrait'}, '此控制台原生布局未接入')
    require(isinstance(crop,dict) and set(crop)=={'cx','cy','h'} and all(type(n) in {int,float} and math.isfinite(n) and 0<n<=1 for n in crop.values()),
            '须根据实际导入人物帧设置有效脸部圆窗')
    if c.get('cropCalibrationRequired'):
        require(c['cropCalibrationRequired']==sha(avatar),'新人物变化后须重新校准圆窗')
    if c.get('presenterFramingRequired'):
        require(c['presenterFramingRequired']==sha(avatar) and c.get('presenterFraming'),
                '请先提取并审核本期数字人满幅取景')
    if c.get('presenterFraming'):
        from backlot import studio_motion_presenter_framing as framing
        framing.validate(c['presenterFraming'],value['avatar'],tools['ffmpeg'])
    if c.get('cropCalibration'):
        from backlot import studio_motion_face_crop as face_crop
        face_crop.validate(c['cropCalibration'],value['avatar'],tools,crop)
    segments=c.get('segments')
    require(isinstance(segments,list) and 1<=len(segments)<=10,'控制台需要已规划的完整场景')
    recipes=[];frames=0
    for segment in segments:
        require(isinstance(segment,dict) and segment.get('recipe') in profile['groups'],'当前控制台场景尚未接入')
        recipe=segment['recipe'];require(recipe not in recipes,'本版使用每组一个独立实例，重复组须另行声明')
        recipes.append(recipe)
        rule=deepcopy(profile['segment_contracts'][recipe]);rule['$defs']=profile['input_contracts']
        errors=list(jsonschema.Draft202012Validator(rule).iter_errors(segment))
        require(not errors,'控制台参数不符合原包公开场景合同：'+(str(errors[0].message)[:220] if errors else ''))
        motion=profile['groups'][recipe]
        require(segment['durationFrames']<=motion['minFrames']+motion['maxHoldFrames'],
                '此完整动作组超过原包允许的静止延长容量')
        frames+=segment['durationFrames']
    sentence_boundaries(caps,segments)
    following_frames(segments,profile['groups'])
    review_media(media_windows(value['media'],segments),review,tools)
    require(frames<=profile['maximum_frames'] and clock['duration_seconds']<=frames/60+.000001
            and 0<=frames/60-clock['duration_seconds']<=2,'控制台完整场景不能截断或拉伸口播，非语音尾部最多2秒')
    return {'profile':profile,'clock':clock,'captions':caps,'frames':frames,'recipes':recipes,'layout':c.get('layout','landscape')}


def reviewed_images(rows,allowed,minimum=1):
    """Bind actual viewing declarations to distinct images of this exact stage."""
    require(isinstance(rows,list) and len(rows)>=minimum,'本期实际看帧证据不足')
    seen=set()
    for row in rows:
        path=checked(row);key=str(path.resolve())
        require(key not in seen,'重复图片不能计为多张实际看帧证据')
        require(allowed.get(key)==row['sha256'],'看帧证据不是当前阶段的绑定图片')
        seen.add(key)
    return seen


def preview_images(preview,project):
    project=Path(project).resolve()
    require(preview.get('schema')=='motiongit-preview/1' and isinstance(preview.get('stills'),list)
            and len(preview['stills'])>=5,'控制台官方预览回执结构不匹配')
    require(preview.get('parameterSha256')==sha(project/'parameters.json')
            and preview.get('sourceLockSha256')==read_json(project/'instance.json').get('sourceLockSha256'),
            '控制台预览不是本期准备工程或原包来源')
    images=[];seen=set()
    for row in preview['stills']:
        name=row.get('path') if isinstance(row,dict) else None
        require(isinstance(name,str) and name and ':' not in name and '\\' not in name
                and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,
                '控制台预览图片路径无效')
        path=(project/name).resolve();require(path.is_relative_to(project) and str(path) not in seen,
                '控制台预览图片逃逸或重复')
        image={'path':str(path),'sha256':row.get('sha256')};checked(image);images.append(image);seen.add(str(path))
    return images


def acknowledge_nested_preview(project,actual):
    """The console has outer and inner receipts for the very same viewed pixels."""
    project=Path(project).resolve();inner=project/'project';path=inner/'preview.json';receipt=read_json(path)
    outer=read_json(project/'preview.json')
    require(receipt.get('schema')=='motiongit-preview/1' and isinstance(receipt.get('stills'),dict)
            and isinstance(receipt.get('projectHashes'),dict)
            and receipt.get('sourceBinding',{}).get('sourceLockSha256')==outer.get('sourceLockSha256'),
            '控制台内层预览回执或原包来源不匹配')
    expected={row['path']:row['sha256'] for row in actual};mapped={}
    for name,digest in receipt['stills'].items():
        require(isinstance(name,str) and ':' not in name and '\\' not in name
                and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,'内层预览路径无效')
        target=(inner/name).resolve();require(target.is_relative_to(inner),'内层预览不能越过本期工程')
        checked({'path':str(target),'sha256':digest});mapped[str(target)]=digest
    require(mapped==expected,'内外层预览不是同一批实际已查看的图片')
    for name,digest in receipt['projectHashes'].items():
        require(isinstance(name,str) and ':' not in name and '\\' not in name
                and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,'内层工程绑定路径无效')
        target=(inner/name).resolve();require(target.is_relative_to(inner),'内层工程绑定不能逃逸')
        checked({'path':str(target),'sha256':digest})
    if not receipt.get('reviewed'):
        receipt['reviewed']=True;atomic_private(path,receipt)
    return bound(path)


def build(input_path,destination):
    input_path=Path(input_path).resolve();value=read_json(input_path);facts=source(value)
    destination=Path(destination).resolve();receipt=destination/'console-build.json'
    if receipt.exists():
        existing=load(receipt);require(existing['input_sha256']==sha(input_path),'已有控制台准备目录属于其他输入')
        return existing
    require(not destination.exists() or not any(destination.iterdir()),'控制台准备目录已有未完成产物，请保留并另建版本')
    destination.mkdir(parents=True,exist_ok=True);inputs=destination/'inputs';inputs.mkdir()
    tools=value['tools'];ff=checked(tools['ffmpeg']);copied={}
    def copy(name,row):
        target=inputs/name;shutil.copy2(checked(row),target);copied[name]=bound(target);return target
    voice=copy('voice.wav',value['voice'])
    # Native talk carries this exact complete narration once. No sound from the
    # original presenter container or evidence clip is added to the film mix.
    talk=inputs/'talk.mp4'
    # Stream-copy truncation may retain B-frames past -t (observed +80ms),
    # breaking the official complete-audio clock. Both 25fps and 60fps share
    # the 0.2s quantum selected above. Re-encode only this owned presenter mux.
    seconds=facts['frames']/60
    frame_filter=''
    if value['console'].get('presenterFraming'):
        from backlot import studio_motion_presenter_framing as framing
        proof=framing.validate(value['console']['presenterFraming'],value['avatar'],tools['ffmpeg'])
        frame_filter=framing.filtergraph(proof['geometry'])+','
    _run([ff,'-nostdin','-v','error','-y','-i',checked(value['avatar']),'-i',voice,
          '-map','0:v:0','-map','1:a:0','-t',seconds,'-vf',
          frame_filter+f'fps=25,tpad=stop_mode=clone:stop_duration=2,trim=duration={seconds},setpts=PTS-STARTPTS',
          '-c:v','libx264','-preset','fast','-crf','16','-pix_fmt','yuv420p','-af','apad',
          '-c:a','aac','-b:a','256k','-ar','24000','-ac','1',talk],300,log=destination/'talk-mux.log')
    talk_info=_probe(tools,talk)
    require(abs(_seconds(talk_info)-seconds)<=.025,'本期人物封装时钟不匹配；原声和原人物保留')
    if frame_filter:
        stream=next(s for s in talk_info['streams'] if s.get('codec_type')=='video')
        require((stream.get('width'),stream.get('height'))==(720,1280),'人物满幅取景输出尺寸不正确')
    copied['talk.mp4']=bound(talk)
    caps=inputs/'subtitles.srt'
    caps.write_text('\n\n'.join(f"{i+1}\n{_srt_time(c['t0'])} --> {_srt_time(c['t1'])}\n{c['zh']}" for i,c in enumerate(facts['captions']))+'\n',encoding='utf8')
    copied['subtitles.srt']=bound(caps)
    wall_aliases={};unique={}
    wall=value['media']['wall'] if 'works-fan' in facts['recipes'] else []
    for i,row in enumerate(wall):
        source_path=checked(row['source']);digest=sha(source_path)
        require(source_path.suffix.lower() in {'.mp4','.mov','.m4v','.mkv','.webm'},
                '控制台原生扇列槽需要真实视频；静态图片请选择已声明的图片组件')
        if digest not in unique:unique[digest]=copy(f'wall-{len(unique)}'+source_path.suffix.lower(),row['source'])
        wall_aliases[f'w{i}']={'path':unique[digest].name,'offset':row['at']}
    if 'result-inspector' in facts['recipes']:
        lens=value['media']['lens'];evidence=copy('evidence'+checked(lens['source']).suffix.lower(),lens['source'])
    params={'mode':'native','layout':facts['layout'],'brand':value['brand'],'durationSeconds':facts['frames']/60,
            'presenterCrop':value['console']['presenterCrop'],'subtitleLanguage':'zh',
            'media':{'talk':'talk.mp4','subtitles':'subtitles.srt','music':'','grainTexture':'@style/assets/noise.png'},
            'segments':deepcopy(value['console']['segments'])}
    # Media aliases are owned copies, never arbitrary package-selected paths.
    for segment in params['segments']:
        if segment['recipe']=='works-fan':segment['inputs']['media']=deepcopy(wall_aliases)
        if segment['recipe']=='result-inspector':segment['inputs']['media']={'bvid':{'path':evidence.name,'offset':lens['offset']}}
    atomic_private(destination/'params.json',params)
    package_key=tools['package']['sha256'][:12]
    identity=fingerprint({'input':sha(input_path),'compiler':sha(__file__),'renderer':sha(native.__file__)})[:16]
    # Keep new trials on the workspace volume; short owned paths also avoid the
    # Windows transaction-name limit. Frozen older C: projects keep their paths.
    instance=ROOT.parent/'.local/mc'/identity;instance.parent.mkdir(parents=True,exist_ok=True)
    require(len(str(instance))<=110,'控制台原生实例路径过长，请配置短缓存目录')
    cache=Path(value.get('native_dependency_cache') or ROOT.parent/'.local/md'/package_key)
    require(cache.is_absolute() and len(str(cache))<=110 and not cache.is_symlink(),
            '控制台依赖缓存需要本机短绝对路径')
    copied['params.json']=bound(destination/'params.json')
    result={'schema':SCHEMA,'input_path':str(input_path),'input_sha256':sha(input_path),'compiler_sha256':sha(__file__),
            'contract_sha256':sha(PROFILE),'directory':str(destination),'files':copied,'tools':deepcopy(tools),
            'frames':facts['frames'],'recipes':facts['recipes'],'layout':facts['layout'],'instance':str(instance),
            'cache':str(cache),'cloud_media_calls':0,'full_render_started':False}
    atomic_private(receipt,result);return result


def load(path):
    value=read_json(path)
    require(value.get('schema')==SCHEMA and value.get('compiler_sha256')==sha(__file__)
            and value.get('contract_sha256')==sha(PROFILE),'控制台编译器或合同已更新，请保留原版本并重新准备')
    require(sha(value['input_path'])==value['input_sha256'],'控制台原输入已变化')
    for row in [*value['files'].values(),*value['tools'].values()]:checked(row)
    source(read_json(value['input_path']))
    return value


def official(build,operation,args=()):
    require(operation in {'new','setup','doctor','check-params','plan','prepare','preview'},'此入口只准备和有界预览，整片须进入统一队列')
    tools=build['tools'];prefix=[checked(tools['node']),checked(tools['helper'])]
    if operation=='new':command=[*prefix,'new',checked(tools['package']),build['instance']]
    else:
        command=[*prefix,'run',checked(tools['package']),'--instance',build['instance']]
        if operation=='setup':command+=['--cache',build['cache']]
        command+=[operation,*map(str,args),'--language','zh']
    temporary=ROOT.parent/'.local/mt';temporary.mkdir(exist_ok=True)
    require(len(str(temporary))<=80,'官方依赖临时目录过长，请先配置短工作区缓存')
    env={**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','TEMP':str(temporary),'TMP':str(temporary),
         'PATH':str(checked(tools['ffmpeg']).parent)+os.pathsep+os.environ.get('PATH','')}
    browser=native._browser()
    if browser:env['CHROME_PATH']=str(browser)
    return _run(command,900,env,Path(build['directory'])/f'official-{operation}.log')


def plan(build_path):
    b=load(build_path);inst=Path(b['instance']);folder=Path(b['directory'])
    if not inst.exists():official(b,'new')
    for op in ['setup','doctor']:official(b,op)
    official(b,'check-params',[folder/'params.json','--inputs',folder/'inputs'])
    target=inst/'plan'
    if not (target/'plan.json').exists():official(b,'plan',[folder/'params.json','--inputs',folder/'inputs','--out',target])
    report=read_json(target/'plan.json');plan_facts(report,b['frames'],b['recipes'],b.get('layout','landscape'))
    inputs=read_json(target/'inputs.json')
    require(inputs.get('paramsSha256')==sha(folder/'params.json') and report.get('sourceParameterSha256')==sha(folder/'params.json'),
            '控制台计划未绑定本期原始参数')
    return {'build':str(build_path),'plan':str(target),'plan_sha256':sha(target/'plan.json'),
            'inputs_sha256':sha(target/'inputs.json'),'report':report,'cloud_media_calls':0}


def prepare_project(build_path,review_path):
    b=load(build_path);inst=Path(b['instance']);review=read_json(review_path);p=inst/'plan'
    require(review.get('status')=='pass' and review.get('actual_plan_inspected') is True
            and sha(p/'plan.json') in {review.get('plan_sha256'),review.get('reviewed_plan_sha256')}
            and review.get('actual_source_images_viewed'),
            '须实际查看本期控制台计划及源图，审核与当前版本绑定')
    plan_facts(read_json(p/'plan.json'),b['frames'],b['recipes'],b.get('layout','landscape'))
    source_value=read_json(b['input_path']);source_review=read_json(checked(source_value['source_review']))
    allowed={str(checked(row).resolve()):row['sha256'] for material in source_review['materials']
             for row in material.get('actual_images_viewed',[])}
    reviewed_images(review['actual_source_images_viewed'],allowed)
    body=read_json(p/'plan.json')
    if not body.get('reviewed'):
        body['reviewed']=True;atomic_private(p/'plan.json',body)
    review['reviewed_plan_sha256']=sha(p/'plan.json');atomic_private(review_path,review)
    acknowledgement=read_json(p/'review.json');acknowledgement['reviewed']=True;atomic_private(p/'review.json',acknowledgement)
    project=inst/'project'
    if not project.exists():official(b,'prepare',['@vault','--inputs','@vault','--plan',p,'--out',project])
    require((project/'instance.json').is_file() and (project/'parameters.json').is_file(),
            '控制台准备工程未完整生成，保留当前目录并重新准备新版本')
    return project


def prepare_and_preview(build_path,review_path,times,*,calibration_import=False):
    b=load(build_path)
    project=prepare_project(build_path,review_path)
    inputs=read_json(b['input_path']);c=inputs.get('console',{})
    if c.get('cropCalibrationRequired'):
        require(c.get('cropCalibration') or calibration_import is True,
                '新人物尚未自动校准，不生成沿用旧圆窗的正式预览')
    require(isinstance(times,list) and 5<=len(times)<=64 and len(set(times))==len(times)
            and all(type(t) in {int,float} and 0<=t<b['frames']/60 for t in times),
            '控制台预览需要5至64个互不重复的本期动作关键时刻')
    if not (project/'preview.json').exists():official(b,'preview',[project,'--times',','.join(map(str,times))])
    preview=read_json(project/'preview.json');preview_images(preview,project)
    require(preview.get('times_s')==times,'本工程已有不同时间范围的预览，请保留并另建版本')
    # This native runtime defers talk-frame import until bounded preview.
    # Inspect its actual output, never assume prepare already imported it.
    if c.get('cropCalibration'):
        from backlot import studio_motion_face_crop as face_crop
        face_crop.validate(c['cropCalibration'],inputs['avatar'],inputs['tools'],c['presenterCrop'],project)
    return {'project':str(project),'preview':str(project/'preview.json'),'cloud_media_calls':0}


def manifest(build_path,review_path):
    b=load(build_path);value=read_json(b['input_path']);inst=Path(b['instance']);folder=Path(b['directory'])
    if value['console'].get('cropCalibrationRequired'):
        require(value['console'].get('cropCalibration'),'新人物没有本期圆窗校准，不得冻结导出')
    review=read_json(review_path);preview_path=inst/'project/preview.json';preview=read_json(preview_path)
    require(review.get('status')=='pass' and sha(preview_path) in
            {review.get('unreviewed_preview_sha256'),review.get('reviewed_preview_sha256')}
            and len(review.get('actual_images_viewed',[]))>=5,'控制台原生预览尚未完成本期实际看帧')
    actual=preview_images(preview,inst/'project');allowed={row['path']:row['sha256'] for row in actual}
    portrait=b.get('layout')=='portrait'
    if portrait:
        from backlot import studio_motion_native_viewport as viewport
        require(review.get('layout')==viewport.CONSOLE_45,'原生竖屏须实际检查4:5视窗')
        # The reviewer saw the final viewport, not the omitted auxiliary HUD.
        viewport.validate_review({'status':'pass','layout':review['layout'],'images':review.get('viewport_images'),
                                  'source_preview_sha256':sha(preview_path)},actual,sha(preview_path))
        cropped=[row['image'] for row in review['viewport_images']]
        require(review['actual_images_viewed']==cropped,'实际看帧须对应本期最终4:5视窗')
    else:
        seen=reviewed_images(review['actual_images_viewed'],allowed,minimum=len(actual))
        require(seen==set(allowed),'须实际查看本期全部控制台预览')
    inner_review=acknowledge_nested_preview(inst/'project',actual)
    preview['reviewed']=True;atomic_private(preview_path,preview)
    review['reviewed_preview_sha256']=sha(preview_path);atomic_private(review_path,review)
    visual={**review,'preview_sha256':sha(preview_path),'inner_preview_review':inner_review};atomic_private(folder/'visual-review.json',visual)
    params=read_json(folder/'params.json')
    p={'native_profile':'console04-v1','completeGroups':b['recipes'],
       'completeGroupFrames':{s['recipe']:s['durationFrames'] for s in params['segments']},'frames':b['frames'],'seconds':b['frames']/60}
    p['nativeLayout']=b.get('layout','landscape')
    atomic_private(folder/'plan-review.json',p)
    result={'title':value['title'],'projectDirectory':str(inst/'project'),'instanceDirectory':str(inst),
            **{k:str(checked(value['tools'][k])) for k in ['helper','package','node','ffmpeg','ffprobe']},
            'audio':str(checked(value['voice'])),'previewReceipt':str(preview_path),'visualReview':str(folder/'visual-review.json'),
            'planReview':str(folder/'plan-review.json'),'outputRoot':str(inst/'renders'),'profile_id':'console04-v1',
            'expected':{'width':1080 if portrait else 1920,'height':1920 if portrait else 1080,'fps':60,'frames':b['frames'],'seconds':b['frames']/60},
            'audio_mode':'native_plus_music','music':{'path':str(checked(value['music'])),
                'gainDb':value['music'].get('gainDb',value['music'].get('gain_db',-3)),
                'offsetSeconds':value['music'].get('offsetSeconds',value['music'].get('offset',0)),
                'loop':value['music'].get('loop',False)}}
    if portrait:
        viewport_review={'status':'pass','layout':review['layout'],'source_preview_sha256':sha(preview_path),
                         'images':review['viewport_images'],'scope':'final-viewport-only; original auxiliary top HUD omitted'}
        atomic_private(folder/'viewport-review.json',viewport_review)
        result.update(output_layout=review['layout'],layoutReview=str(folder/'viewport-review.json'))
    atomic_private(folder/'native-queue-input.json',result)
    return result
