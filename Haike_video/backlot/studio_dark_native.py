"""Single-queue, source-bound export of a reviewed official native project.

Only public MotionGit commands are invoked. Prepared native files are hashed as
opaque artifacts; this adapter neither edits nor interprets protected sources.
"""
from __future__ import annotations

from fractions import Fraction
import math
import os
from pathlib import Path
import shutil
import subprocess
import wave

from backlot.studio import atomic_private
from backlot.work_catalog import WorkCatalog, read_json, sha
from backlot.studio_investment_recompose import fingerprint
from backlot import studio_hum_production as speech
from backlot.production_queue import _sanitize

CONTRACT='motiongit-dark-native-v1'
KIND='studio_investment_recompose'
REQUEST_FILE='dark-native-request.json'
OUTPUT_FILE='dark-native.mp4'
PORTRAIT_FILE='dark-native-4x5.mp4'
PORTRAIT_CONTAIN={'width':1440,'height':1800,'contentWidth':1440,'contentHeight':810,
                  'x':0,'y':495,'background':'#030303','fit':'contain','cropped':False}
ROOT=Path(__file__).resolve().parents[1]
NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)
require=speech._require
FIELDS={'title','projectDirectory','instanceDirectory','helper','package','node','ffmpeg','ffprobe',
        'audio','previewReceipt','visualReview','planReview','outputRoot'}
FILE_FIELDS={'helper','package','node','ffmpeg','ffprobe','audio','previewReceipt','visualReview','planReview'}
OPTIONAL_FIELDS={'expected','audio_mode','music','portrait_companion','profile_id','output_layout','layoutReview'}
REFERENCE_EXPECTED={'width':1920,'height':1080,'fps':60,'frames':7344,'seconds':122.4}
GROUP_MIN_FRAMES={f'03-A:s{i:02}':n for i,n in enumerate([327,636,539,458,621,324,432,492,204],1)}
GROUP_MIN_FRAMES['03-A:independent-artifact-review']=840


def _package_profile(value):
    identity=value.get('profile_id')
    if identity is None:return None,None
    require(identity=='console04-v1','未登记的原生模板合同')
    path=ROOT/'templates/motiongit-console-v1/source-contract.json';profile=read_json(path)
    require(profile.get('schema')=='haike.native-package-contract/1' and profile.get('profile_id')==identity
            and (profile.get('width'),profile.get('height'),profile.get('fps'))==(1920,1080,60),'原生模板合同身份无效')
    from backlot.studio_motiongit import inspect_package,HELPER_SHA
    actual=inspect_package(value['package'])
    require(actual.get('template_id')==profile['template_id'] and actual.get('version') in profile['versions']
            and actual.get('support')=='official-helper' and sha(value['helper'])==HELPER_SHA,'原包或官方入口与此模板合同不匹配')
    require('expected' in value,'新原生模板必须提供本期完整时钟')
    return profile,path


def _expected(value,plan,clock,profile=None):
    """A short native film needs an explicitly reviewed, full-group clock."""
    if 'expected' not in value:
        require(plan.get('frames')==7344 and plan.get('seconds')==122.4
                and len(plan.get('completeGroups',[]))==10,'完整十组计划未通过')
        require(abs(clock['duration_seconds']-122.4)<.0001,'原版完整音轨须为122.4秒')
        return dict(REFERENCE_EXPECTED)
    expected=value['expected']
    portrait = bool(profile and (expected.get('width'),expected.get('height'))==(1080,1920)) if isinstance(expected,dict) else False
    require(isinstance(expected,dict) and set(expected)==set(REFERENCE_EXPECTED)
            and all(type(expected.get(k)) is int for k in ['width','height','fps','frames'])
            and (expected['width'],expected['height'],expected['fps']) in ([(1920,1080,60),(1080,1920,60)] if profile else [(1920,1080,60)])
            and 360<=expected['frames']<=36000 and speech._number(expected.get('seconds'))
            and abs(expected['seconds']-expected['frames']/60)<.000001,'原生短片须为6至600秒、1920×1080/60fps；已登记控制台另可用1080×1920，精确帧时钟未通过')
    if portrait:
        require('output_layout' in value and plan.get('nativeLayout')=='portrait', '原生竖屏须绑定已审核4:5视窗与实际竖屏计划')
    else:
        require(plan.get('nativeLayout','landscape')=='landscape', '原生横版计划不能绑定竖屏工程')
    seconds=expected['frames']/60
    require(plan.get('frames')==expected['frames'] and speech._number(plan.get('seconds'))
            and abs(plan['seconds']-seconds)<.000001,'受审原生计划与预期帧时钟不一致')
    minimums={k:v['minFrames'] for k,v in profile['groups'].items()} if profile else GROUP_MIN_FRAMES
    groups=plan.get('completeGroups');group_frames=plan.get('completeGroupFrames')
    require(isinstance(groups,list) and 1<=len(groups)<=10 and all(isinstance(g,str) for g in groups) and len(set(groups))==len(groups)
            and all(g in minimums for g in groups),'原生计划包含未知或重复完整组')
    require(isinstance(group_frames,dict) and set(group_frames)==set(groups)
            and all(type(group_frames[g]) is int and group_frames[g]>=minimums[g] for g in groups)
            and sum(group_frames.values())==expected['frames'],'原生完整动作时长未通过')
    if profile:
        require(expected['frames']<=profile['maximum_frames'] and all(group_frames[g]<=minimums[g]+profile['groups'][g]['maxHoldFrames'] for g in groups),
                '原生完整动作超出已声明停留容量')
        require(plan.get('native_profile')==profile['profile_id'],'本期计划与原生模板身份不一致')
    pair=['03-A:s02','03-A:s03']
    require(not any(g in groups for g in pair) or all(g in groups for g in pair)
            and groups.index(pair[1])==groups.index(pair[0])+1,'原生九宫格与主卡推进须连续相邻')
    require(math.ceil(clock['duration_seconds']*60-.000001)<=expected['frames']
            and 0<=seconds-clock['duration_seconds']+1e-9<=2,'原生帧时钟不能截断口播，尾部只允许0至2秒非语音')
    return dict(expected)


def _layout_review(value, expected, project, preview_path):
    from backlot import studio_motion_native_viewport as viewport
    from backlot.studio_motion_console import preview_images
    require(viewport.is_layout(value.get('output_layout')) and value.get('profile_id') == 'console04-v1'
            and (expected['width'],expected['height']) == (1080,1920)
            and not value.get('portrait_companion'), '4:5视窗只适用于已接入的控制台原生竖屏')
    path = Path(value.get('layoutReview',''))
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), '本期4:5画幅审核记录缺失')
    viewport.validate_review(read_json(path), preview_images(read_json(preview_path),project), sha(preview_path))
    return path.resolve()


def _music(value,expected):
    from backlot.studio_render import media_probe
    require(isinstance(value,dict) and not set(value)-{'path','gainDb','offsetSeconds','loop'}
            and isinstance(value.get('path'),str),'配乐须为受控本地文件及明确混音参数')
    source=Path(value['path'])
    require(source.is_absolute() and not source.is_symlink() and source.is_file()
            and source.stat().st_size>0 and source.suffix.lower() in {'.wav','.mp3','.m4a'},'本期配乐文件缺失或类型无效')
    gain=value.get('gainDb',-5);offset=value.get('offsetSeconds',0);loop=value.get('loop',False)
    require(speech._number(gain) and -40<=gain<=-3 and speech._number(offset) and offset>=0
            and type(loop) is bool,'配乐增益、入点或循环参数无效')
    info=media_probe(source)
    require(info.get('audio') and offset<info['duration']
            and (loop or offset+expected['seconds']<=info['duration']+.001),'本期配乐长度不足，须显式声明循环')
    return source.resolve(),{'gainDb':gain,'offsetSeconds':offset,'loop':loop}


def _tree(folder):
    return {p.relative_to(folder).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size}
            for p in sorted(folder.rglob('*')) if p.is_file() and p.relative_to(folder).parts[0]!='exports'}


def _browser():
    """Prefer an installed Windows Chrome through the official override."""
    override=os.environ.get('CHROME_PATH')
    if override:
        path=Path(override)
        require(path.is_absolute() and path.is_file() and not path.is_symlink(),'CHROME_PATH指定的本机浏览器不可用')
        return path.resolve()
    if os.name=='nt':
        path=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
        if path.is_file() and not path.is_symlink():return path.resolve()
    return None


def _runtime_project(r,scratch):
    """The official renderer writes audio reports; keep reviewed inputs intact."""
    project=Path(r['instance'])/('rp-'+r['request_sha256'][:8])
    receipt_path=scratch/'runtime-project.json';receipt=read_json(receipt_path)
    if not receipt:
        require(not project.exists(),'原生执行副本未完成登记，请保留原文件并重新准备新版本')
        source=Path(r['native_project'])
        shutil.copytree(source,project,ignore=lambda folder,names:['exports'] if Path(folder)==source and 'exports' in names else [])
        receipt={'request_sha256':r['request_sha256'],'source_files':r['project_files'],'runtime_files':_tree(project)}
        require(receipt['runtime_files']==r['project_files'],'原生执行副本与受审工程不一致')
        atomic_private(receipt_path,receipt)
    require(receipt.get('request_sha256')==r['request_sha256'] and receipt.get('source_files')==r['project_files']
            and receipt.get('runtime_files')==_tree(project),'原生执行副本或恢复记录已变化，请保留并重新准备')
    return project


def _record_runtime_project(r,scratch,project,returncode):
    atomic_private(scratch/'runtime-project.json',{'request_sha256':r['request_sha256'],
        'source_files':r['project_files'],'runtime_files':_tree(project),'last_returncode':returncode})


def prepare(queue,value):
    require(isinstance(value,dict) and FIELDS<=set(value) and not set(value)-FIELDS-OPTIONAL_FIELDS,'原生完整制作清单字段不完整')
    require(speech._text(value['title'],100),'原生作品名称无效')
    paths={k:Path(value[k]).resolve() for k in FIELDS if k!='title'}
    require(all(Path(value[k]).is_absolute() for k in paths),'原生入口须为本机绝对路径')
    require(all(paths[k].is_file() for k in FILE_FIELDS),'原生工具、媒体或审核记录缺失')
    project=paths['projectDirectory'];instance=paths['instanceDirectory']
    require(project.is_dir() and project.is_relative_to(instance),'原生工程须在其来源绑定实例中')
    require(paths['outputRoot'].is_relative_to(instance),'官方原生渲染暂存必须位于永久实例内')
    require(not paths['outputRoot'].is_relative_to(project),'官方渲染输出不能写入已审核准备工程')
    preview=read_json(paths['previewReceipt']);review=read_json(paths['visualReview']);plan=read_json(paths['planReview'])
    require(preview.get('reviewed') is True and review.get('preview_sha256')==sha(paths['previewReceipt'])
            and review.get('actual_images_viewed') and review.get('status')=='pass','实际原生预览尚未完成画面审核')
    profile,profile_path=_package_profile(value)
    clock=speech._clock(paths['audio']);expected=_expected(value,plan,clock,profile)
    require(('output_layout' in value)==('layoutReview' in value), '4:5布局和实际审核须一起绑定')
    if 'output_layout' in value:
        paths['layout_review']=_layout_review(value,expected,project,paths['previewReceipt'])
    mode=value.get('audio_mode','original_mix')
    require(isinstance(mode,str) and mode in {'original_mix','native_plus_music'},'未知原生混音模式')
    require((mode=='native_plus_music')==('music' in value),'原生动作音效配乐模式须绑定唯一外部配乐')
    require('portrait_companion' not in value or type(value['portrait_companion']) is bool,'4:5伴随版开关须为布尔值')
    music=None
    if mode=='native_plus_music':
        paths['music'],music=_music(value['music'],expected)
        require(paths['music']!=paths['audio'] and sha(paths['music'])!=sha(paths['audio']),'不能把同一口播重复绑定为配乐')
    tools={k:{'path':str(paths[k]),'sha256':sha(paths[k])} for k in FILE_FIELDS}
    if 'layout_review' in paths:tools['layout_review']={'path':str(paths['layout_review']),'sha256':sha(paths['layout_review'])}
    if 'output_layout' in value:
        from backlot import studio_motion_native_viewport as viewport
        tools['viewport_adapter']={'path':str(Path(viewport.__file__).resolve()),'sha256':sha(viewport.__file__)}
    if music is not None:tools['music']={'path':str(paths['music']),'sha256':sha(paths['music'])}
    browser=_browser()
    if browser is not None:tools['browser']={'path':str(browser),'sha256':sha(browser)}
    if profile_path is not None:tools['native_profile']={'path':str(profile_path),'sha256':sha(profile_path)}
    # Large scratch stays on the chosen persistent volume. Only final outputs
    # and small receipts enter the managed project; no junction is introduced.
    tree=_tree(project)
    core={'contract':CONTRACT,'title':value['title'],'native_project':str(project),'instance':str(instance),
          'output_root':str(paths['outputRoot']),'files':tools,'project_files':tree,'voice_clock':clock,
          'adapter_sha256':sha(__file__),'speech_adapter_sha256':sha(speech.__file__),
          'publication':False,'cloud_calls':0,'expected':expected,
          'audio_policy':'normalize original complete mixed track once; no extra music or effects'}
    if 'expected' in value or 'audio_mode' in value:
        core['audio_mode']=mode
    if music is not None:
        core['music']=music
        core['audio_policy']='native narration and action effects once, plus one explicit external music bed; no added voice or SFX'
    if 'portrait_companion' in value:core['portrait_companion']=value['portrait_companion']
    if profile is not None:core['native_profile']=profile['profile_id']
    if 'output_layout' in value:core['output_layout']=dict(value['output_layout'])
    temporary=ROOT.parent/'.local/mt';temporary.mkdir(parents=True,exist_ok=True)
    require(not temporary.is_symlink() and len(str(temporary))<=80, '本地渲染临时根须为工作区内短普通目录')
    core['temporary_root']=str(temporary.resolve())
    require(_sanitize(core,redact_local_paths=False)==core,'原生请求不满足无凭据队列契约')
    core['project_id']='studio-'+fingerprint(core)[:16];digest=fingerprint(core)
    r={**core,'request_sha256':digest,'render_id':CONTRACT+'-'+digest[:20]}
    managed=queue.projects_root/r['project_id'];request=managed/'artifacts'/REQUEST_FILE
    if request.exists():
        require(read_json(request)==r,'已有原生请求不同，请保留原版本');validate(queue,r);return r
    from lib.checkpoint import init_project
    init_project(r['project_id'],title=r['title'],pipeline_type='animated-explainer',pipeline_dir=queue.projects_root)
    atomic_private(request,r);validate(queue,r);return r


def validate(queue,r):
    core={k:v for k,v in r.items() if k not in {'request_sha256','render_id'}};digest=fingerprint(core)
    require(r.get('contract')==CONTRACT and r.get('request_sha256')==digest and r.get('render_id')==CONTRACT+'-'+digest[:20]
            and r.get('cloud_calls')==0 and r.get('publication') is False,'原生冻结请求身份无效')
    managed=WorkCatalog(queue.projects_root).project(r['project_id'])
    require(read_json(managed/'artifacts'/REQUEST_FILE)==r,'原生请求记录已变化')
    folder=managed/'renders'/r['render_id'];done=read_json(folder/'result.json')
    if done:
        require(done.get('request_sha256')==digest and sha(folder/OUTPUT_FILE)==done.get('output_sha256')
                and sha(folder/'quality.json')==done.get('quality_sha256'),'已完成原生作品或质量记录已变化')
        if r.get('portrait_companion'):
            require((folder/PORTRAIT_FILE).is_file() and sha(folder/PORTRAIT_FILE)==done.get('portrait_output_sha256')
                    and read_json(folder/'quality.json').get('portrait_companion',{}).get('output_sha256')==done.get('portrait_output_sha256'),
                    '已完成4:5伴随版或对应质量记录已变化')
    else:
        require(sha(__file__)==r['adapter_sha256'] and sha(speech.__file__)==r['speech_adapter_sha256'],'适配器已变化，请冻结新版本')
        require(all(sha(row['path'])==row['sha256'] for row in r['files'].values()),'工具、音轨或审核凭据已变化')
        require(_tree(Path(r['native_project']))==r['project_files'],'来源绑定原生工程已变化，请重新预览冻结')
        if 'output_layout' in r:
            _layout_review({'output_layout':r['output_layout'],'profile_id':r['native_profile'],
                            'layoutReview':r['files']['layout_review']['path']},r['expected'],
                           Path(r['native_project']),Path(r['files']['previewReceipt']['path']))
    return managed


def submit(queue,r):
    validate(queue,r)
    return queue.submit(project_id=r['project_id'],kind=KIND,source='codex',priority='normal',parent_job_id=r['render_id'],
                        frozen_request=r,idempotency_key=CONTRACT+':'+r['request_sha256'],start_paused=True)


def _native_music_master(r,files,raw,scratch):
    """Keep native narration/SFX once and add only the frozen external music."""
    expected=r['expected'];duration=expected['seconds'];rate=48000
    samples=expected['frames']*(rate//expected['fps'])
    native=scratch/'native-audio-pcm.wav';output=scratch/'master.wav'
    decode=[str(files['ffmpeg']),'-nostdin','-y','-v','error','-xerror','-i',str(raw),
            '-map','0:a:0','-vn','-ar',str(rate),'-ac','2','-c:a','pcm_s16le',str(native)]
    subprocess.run(decode,check=True,capture_output=True,creationflags=NO_WINDOW)
    native_clock=speech._clock(native)
    require(abs(native_clock['duration_seconds']-duration)<=.08,'原生完整音轨与计划时钟不一致，不能截断或伸缩填时长')
    require(r['voice_clock']['duration_seconds']<=duration+.000001,'完整口播越过原生成片尾部')
    music=r['music'];gain=10**(music['gainDb']/20)
    command=[str(files['ffmpeg']),'-nostdin','-y','-v','error','-i',str(native)]
    if music['loop']:command+=['-stream_loop','-1']
    command+=['-ss',str(music['offsetSeconds']),'-i',str(files['music'])]
    filters=[
        f'[0:a]aresample={rate},aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={duration},asetpts=PTS-STARTPTS,asplit=2[native][duck]',
        f'[1:a]aresample={rate},aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS,volume={gain},apad,atrim=duration={duration},afade=t=in:d=0.15,afade=t=out:st={max(0,duration-.6)}:d=0.6[music]',
        '[music][duck]sidechaincompress=threshold=0.025:ratio=5:attack=12:release=220[bed]',
        f'[native][bed]amix=inputs=2:duration=longest:normalize=0:dropout_transition=0,loudnorm=I=-16:TP=-2.5:LRA=11,aresample={rate},apad=whole_len={samples},atrim=end_sample={samples},asetpts=N/SR/TB[out]',
    ]
    command+=['-filter_complex',';'.join(filters),'-map','[out]','-ar',str(rate),'-ac','2','-c:a','pcm_s16le',str(output)]
    subprocess.run(command,check=True,capture_output=True,creationflags=NO_WINDOW)
    with wave.open(str(output),'rb') as stream:
        require((stream.getnchannels(),stream.getsampwidth(),stream.getframerate(),stream.getnframes())==(2,2,rate,samples),'原生声音母带未精确对齐成片帧时钟')
    return {'command':command,'native_decode_command':decode,'master_sha256':sha(output),
            'native_render_sha256':sha(raw),'decoded_native_audio_sha256':sha(native),'native_audio_clock':native_clock,
            'source_voice_sha256':sha(files['audio']),'voice_clock':r['voice_clock'],
            'music_sha256':sha(files['music']),'music':music,'profile':speech.MIX,
            'duration_frames':expected['frames'],'fps':expected['fps'],'samples':samples,
            'source_is_already_mixed':True,'master_source':'native narration and native action effects',
            'additional_music':True,'additional_sfx':False,'added_voice':False,
            'speech_stretched':False,'speech_reordered':False,
            'frame_padding_seconds':duration-r['voice_clock']['duration_seconds']}


def _premixed_master(r,files,scratch):
    """The legacy path stays byte-compatible; explicit plans can add silence."""
    clock=speech._clock(files['audio'])
    plan=speech._audio_plan({'voice':'voice.wav','tailSeconds':0,'sfx':[]},{'voice.wav':files['audio']},clock)
    output=scratch/'master.wav'
    if 'audio_mode' not in r:
        master=speech.mix_master(plan,{'voice.wav':files['audio']},output)
    else:
        expected=r['expected'];duration=expected['seconds'];samples=expected['frames']*800
        plan['durationFrames']=math.ceil(expected['frames']/2)
        plan['tailSeconds']=duration-clock['duration_seconds']
        intermediate=output if expected['frames']%2==0 else scratch/'master-frame30.wav'
        master=speech.mix_master(plan,{'voice.wav':files['audio']},intermediate)
        if intermediate!=output:
            align=[str(files['ffmpeg']),'-nostdin','-y','-v','error','-i',str(intermediate),
                   '-af',f'apad=whole_len={samples},atrim=end_sample={samples},asetpts=N/SR/TB',
                   '-ar','48000','-ac','2','-c:a','pcm_s16le',str(output)]
            subprocess.run(align,check=True,capture_output=True,creationflags=NO_WINDOW)
            master['frame_alignment_command']=align
            master['master_sha256']=sha(output)
        with wave.open(str(output),'rb') as stream:
            require(stream.getnframes()==samples and stream.getframerate()==48000,'原混合轨母带与原生帧时钟不一致')
        master.update(duration_frames=expected['frames'],fps=60,frame_padding_seconds=duration-clock['duration_seconds'])
    master['source_is_already_mixed']=True;master['additional_music_or_sfx']=False
    return master


def _portrait_companion(r,files,source,output):
    """Frame the entire native landscape image; never crop or reflow its UI."""
    from backlot.studio_render import media_probe
    from backlot.studio_investment_audio_v5 import measure_audio
    expected=r['expected'];layout=PORTRAIT_CONTAIN
    filters=f"scale={layout['contentWidth']}:{layout['contentHeight']}:flags=lanczos,pad={layout['width']}:{layout['height']}:{layout['x']}:{layout['y']}:color=0x030303"
    command=[str(files['ffmpeg']),'-nostdin','-y','-v','error','-i',str(source),'-map','0:v:0','-map','0:a:0',
             '-vf',filters,'-frames:v',str(expected['frames']),'-t',str(expected['seconds']),
             '-c:v','libx264','-preset','slow','-b:v','20500k','-minrate','20500k','-maxrate','20500k','-bufsize','2000k',
             '-x264-params','nal-hrd=cbr:force-cfr=1:filler=1','-pix_fmt','yuv420p','-c:a','copy','-movflags','+faststart',str(output)]
    subprocess.run(command,check=True,capture_output=True,creationflags=NO_WINDOW)
    info=media_probe(output);v=info.get('video') or {};a=info.get('audio') or {};loud=measure_audio(output)
    require((v.get('width'),v.get('height'))==(1440,1800) and int(v.get('nb_frames',0))==expected['frames']
            and abs(float(Fraction(v.get('avg_frame_rate','0/1')))-expected['fps'])<.001
            and abs(info['duration']-expected['seconds'])<=.08 and v.get('codec_name')=='h264'
            and v.get('pix_fmt')=='yuv420p' and int(v.get('bit_rate',0))>=20000000
            and a.get('codec_name')=='aac' and str(a.get('sample_rate'))=='48000' and a.get('channels')==2
            and loud['true_peak_dbtp']<=-1.5,'4:5伴随版帧时钟、画质或声音未通过')
    subprocess.run([str(files['ffmpeg']),'-nostdin','-v','error','-xerror','-i',str(output),'-f','null','-'],check=True,capture_output=True,creationflags=NO_WINDOW)
    return {'output_sha256':sha(output),'source_sha256':sha(source),'media':info,'audio':loud,'full_decode':'passed',
            'layout':dict(layout),'command':command,'audio_policy':'copy final primary AAC; no added or retimed audio',
            'scope':'完整16:9原生画面居中装入4:5，不是4:5原生重排'}


def run(queue,job):
    r=job['frozen_request']
    try:
        require(job['kind']==KIND and job['project_id']==r['project_id'],'原生队列身份不一致')
        managed=validate(queue,r);folder=managed/'renders'/r['render_id'];folder.mkdir(parents=True,exist_ok=True)
        expected=r['expected'];duration=expected['seconds']
        output=folder/OUTPUT_FILE
        if not read_json(folder/'result.json'):
            from backlot.studio_render import media_probe
            from backlot.studio_investment_audio_v5 import measure_audio
            scratch=Path(r['output_root'])/r['render_id'];scratch.mkdir(parents=True,exist_ok=True)
            raw=scratch/'native-render.mp4';files={k:Path(v['path']) for k,v in r['files'].items()}
            env={**os.environ,'PATH':str(files['ffmpeg'].parent)+os.pathsep+os.environ.get('PATH',''),
                 'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'}
            if r.get('temporary_root'):
                temporary=Path(r['temporary_root'])
                require(temporary.resolve()==(ROOT.parent/'.local/mt').resolve() and temporary.is_dir()
                        and not temporary.is_symlink(), '冻结的本地临时根已变化，请保留原任务')
                env.update(TEMP=str(temporary),TMP=str(temporary))
            if 'browser' in files:env['CHROME_PATH']=str(files['browser'])
            prior=read_json(scratch/'native-render-receipt.json')
            if not prior:
                require(not raw.exists(),'有未验证原生输出，请保留并查询原任务后恢复')
                runtime_project=_runtime_project(r,scratch)
                command=[str(files['node']),str(files['helper']),'run',str(files['package']),'--instance',r['instance'],
                         'render',str(runtime_project),'--out',str(raw),'--language','zh']
                with (scratch/'native-render.log').open('wb') as log:
                    result=subprocess.run(command,cwd=scratch,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=NO_WINDOW)
                _record_runtime_project(r,scratch,runtime_project,result.returncode)
                require(result.returncode==0,'官方原生渲染未完成；详细私有日志保留在固定恢复目录')
                info=media_probe(raw);v=info.get('video') or {}
                require(v.get('width')==expected['width'] and v.get('height')==expected['height'] and int(v.get('nb_frames',0))==expected['frames']
                        and abs(float(Fraction(v.get('avg_frame_rate','0/1')))-expected['fps'])<.001
                        and abs(info['duration']-duration)<=.08,'官方输出与受审完整原生计划不一致')
                prior={'request_sha256':r['request_sha256'],'sha256':sha(raw),'media':info,'command':command}
                atomic_private(scratch/'native-render-receipt.json',prior)
            require(prior['request_sha256']==r['request_sha256'] and sha(raw)==prior['sha256'],'原生中间片身份已变化')
            if r.get('audio_mode','original_mix')=='native_plus_music':
                master=_native_music_master(r,files,raw,scratch)
            else:
                master=_premixed_master(r,files,scratch)
            atomic_private(folder/'audio-receipt.json',master)
            export=[str(files['ffmpeg']),'-nostdin','-y','-v','error','-i',str(raw),'-i',str(scratch/'master.wav'),
                    '-map','0:v:0','-map','1:a:0','-t',str(duration),'-c:v','libx264','-preset','slow','-b:v','20500k',
                    '-minrate','20500k','-maxrate','20500k','-bufsize','2000k','-x264-params','nal-hrd=cbr:force-cfr=1:filler=1',
                    '-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart',str(output)]
            final_expected=dict(expected)
            if 'output_layout' in r:
                from backlot.studio_motion_native_viewport import filtergraph
                from backlot.studio_motiongit_render import encoding_layout
                conversion=encoding_layout(media_probe(raw)['video'],False)
                filters=filtergraph(r['output_layout'])+(','+conversion['filter'] if conversion['filter'] else '')
                export[-1:-1]=['-vf',filters,*conversion['options']]
                final_expected.update(zip(['width','height'],r['output_layout']['output']))
            subprocess.run(export,check=True,capture_output=True,creationflags=NO_WINDOW)
            info=media_probe(output);v=info.get('video') or {};a=info.get('audio') or {};loud=measure_audio(output)
            require((v.get('width'),v.get('height'))==(final_expected['width'],final_expected['height']) and int(v.get('nb_frames',0))==expected['frames']
                    and abs(float(Fraction(v.get('avg_frame_rate','0/1')))-expected['fps'])<.001 and abs(info['duration']-duration)<=.08
                    and v.get('codec_name')=='h264' and v.get('pix_fmt')=='yuv420p' and int(v.get('bit_rate',0))>=20000000
                    and str(a.get('sample_rate'))=='48000' and a.get('channels')==2 and loud['true_peak_dbtp']<=-1.5,'原生成片视听参数未通过')
            subprocess.run([str(files['ffmpeg']),'-nostdin','-v','error','-xerror','-i',str(output),'-f','null','-'],check=True,capture_output=True,creationflags=NO_WINDOW)
            quality={'media':info,'audio':loud,'full_decode':'passed','native_render_sha256':prior['sha256'],
                           'preview_review_sha256':r['files']['visualReview']['sha256'],'audio_receipt_sha256':sha(folder/'audio-receipt.json'),
                           'nomusic_variant':('not_exported_native_source_contains_action_effects' if r.get('audio_mode')=='native_plus_music' else 'not_available_original_audio_already_mixed'),'export_command':export,
                           'expected':expected,'audio_policy':r['audio_policy'],
                           'continuous_watching':'pending','continuous_listening':'pending','visual_review':'pending'}
            if 'output_layout' in r:
                quality.update(output_layout=r['output_layout'],output_expected=final_expected,color_conversion=conversion,
                               layout_review_sha256=r['files']['layout_review']['sha256'])
            result={'request_sha256':r['request_sha256'],'output_sha256':sha(output),'cloud_calls':0,'publication':False}
            if r.get('portrait_companion'):
                quality['portrait_companion']=_portrait_companion(r,files,output,folder/PORTRAIT_FILE)
                result['portrait_output_sha256']=quality['portrait_companion']['output_sha256']
            atomic_private(folder/'quality.json',quality)
            result['quality_sha256']=sha(folder/'quality.json')
            atomic_private(folder/'result.json',result)
        work=WorkCatalog(queue.projects_root).register(r['project_id'],output,work_key='main',mode='manual',event_id=job['job_id'],quality_passed=False,actor=CONTRACT,title=r['title'])
        version=next(v for v in work['versions'] if v['sha256']==sha(output))
        result={'output_path':str(output),'output_sha256':sha(output),'work_id':work['work_id'],'version_id':version['version_id'],'qa_status':'pending'}
        if r.get('portrait_companion'):
            portrait=folder/PORTRAIT_FILE
            framed_work=WorkCatalog(queue.projects_root).register(r['project_id'],portrait,work_key='portrait45',mode='manual',event_id=job['job_id'],quality_passed=False,actor=CONTRACT,title=r['title']+' · 4:5完整横画面')
            framed_version=next(v for v in framed_work['versions'] if v['sha256']==sha(portrait))
            result.update(portrait_output_path=str(portrait),portrait_output_sha256=sha(portrait),portrait_work_id=framed_work['work_id'],portrait_version_id=framed_version['version_id'])
        return {'status':'completed','stage':('原生完整十组已生成，等待观看' if expected['frames']==7344 and duration==122.4 else '原生完整动作短片已生成，等待观看'),'result':result}
    except Exception as exc:
        return {'status':'failed','stage':'原生完整制作未完成，保留原任务恢复','error':{'type':type(exc).__name__,'message':str(exc)[:1200]},
                'retryable':True,'safe_resume_point':'dark-native-local'}
