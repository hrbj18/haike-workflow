"""Queue-owned rendering of frozen native component drafts and project adapters."""
from __future__ import annotations

import json
from copy import deepcopy
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from fractions import Fraction
from uuid import uuid4

from backlot import studio_motiongit as motion
from backlot.studio import atomic_private
from backlot.work_catalog import WorkCatalog, WorkError, read_json, sha
from backlot.studio_investment_recompose import fingerprint

CONTRACT = 'motiongit-component-render-v1'
KIND = 'studio_investment_recompose'
COMPONENT_WORKFLOWS = {'poster-kit', 'motion-kit'}


def entry_parameters(value):
    """The newer entry resolves media relative to --inputs, not the JSON file."""
    result=deepcopy(value['parameters'])
    if value['workflow']!='motion-kit':return result
    def walk(item):
        if isinstance(item,dict):
            for key,child in item.items():
                if key in {'src','voiceover','music','subtitles'} and isinstance(child,str):
                    item[key]=child.removeprefix('inputs/')
                else:walk(child)
        elif isinstance(item,list):
            for child in item:walk(child)
    walk(result)
    policies=result['timeline'].get('mediaPolicies')
    if policies is not None:
        mapped={key.removeprefix('inputs/'):row for key,row in policies.items()}
        motion.require(len(mapped)==len(policies),'同一素材有冲突的媒体显示策略')
        result['timeline']['mediaPolicies']=mapped
    return result


def component_timeline(value):
    workflow=value.get('workflow')
    motion.require(workflow in COMPONENT_WORKFLOWS, '此原生组件工作流尚未接入生产')
    parameters=value['parameters']
    if workflow=='motion-kit':
        motion.require(parameters.get('workflow')=='motion-kit' and isinstance(parameters.get('timeline'),dict),
                       '新版控件须使用原包声明的motion-kit与timeline封装')
        return parameters['timeline']
    return parameters


def _assets(value):
    folder = motion.STORE / 'drafts' / value['id'] / 'inputs'
    result = {}
    for asset in motion.asset_list(value['id'])['assets']:
        path = folder / asset['name']
        motion.require(path.is_file() and sha(path) == asset['sha256'], '草稿素材已改变')
        for alias in {asset['name'], asset['slot']}:
            motion.require(re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', alias) and not alias.startswith('.'), '素材绑定名仅支持安全文件名')
            motion.require(alias not in result or result[alias]['sha256'] == asset['sha256'], '素材绑定名冲突')
            result[alias] = {'path':str(path.resolve()), 'sha256':asset['sha256']}
    return result


def _check_bindings(parameters, assets):
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'src','voiceover','music','subtitles'} and isinstance(item, str) and item:
                    path = PurePosixPath(item)
                    motion.require(not path.is_absolute() and ':' not in item and '\\' not in item and '..' not in path.parts,
                                   '媒体必须绑定已导入素材，不能使用网址或任意本机路径')
                    motion.require(len(path.parts) <= 2 and (len(path.parts) == 1 or path.parts[0] == 'inputs')
                                   and path.name in assets, '媒体尚未导入：' + item[:160])
                walk(item)
        elif isinstance(value, list):
            for item in value: walk(item)
    walk(parameters)


def freeze(queue, draft_id):
    value = motion.draft(draft_id)
    if value['workflow'] in {'project-wall', 'hum-production'}:
        return motion.freeze_project_draft(queue, draft_id)
    parameters=component_timeline(value)
    motion.validate_draft(draft_id)
    package = motion._get('packages', value['package_id'])
    motion.require(package.get('verification') == 'verified' and package.get('helper'), '请先核验原包')
    assets = _assets(value)
    _check_bindings(value['parameters'], assets)
    # Audio is required by this narrated production contract, not by package import.
    motion.require(parameters.get('voiceover') and parameters.get('music'), '本期口播样片须绑定独立口播及配乐')
    motion.require(value.get('output_profile','native') != '4:5' or parameters.get('layout') == 'portrait',
                   '4:5适配目前以竖屏原生布局为基础，请先选择portrait并审核适配预览')
    _check_source_windows(parameters, assets)
    core = {'contract':CONTRACT,'draft':value,'package_id':package['id'],'package_sha256':package['sha256'],
            'helper_sha256':motion.HELPER_SHA,'assets':assets,'adapter_sha256':sha(__file__),
            'publication':False,'paid_calls':0}
    if value['workflow']=='motion-kit':core['entry_parameters']=entry_parameters(value)
    core['project_id'] = 'studio-' + fingerprint(core)[:16]
    digest = fingerprint(core)
    request = {**core,'request_sha256':digest,'render_id':'motiongit-component-'+digest[:20]}
    from lib.checkpoint import init_project
    project = queue.projects_root / request['project_id']
    path = project / 'artifacts/motiongit-component-request.json'
    if path.exists():
        motion.require(read_json(path) == request, '冻结请求不一致')
        motion.track_production(value,request)
        return request
    init_project(request['project_id'],title=value['title'],pipeline_type='animated-explainer',pipeline_dir=queue.projects_root)
    folder = project / 'assets/motiongit'
    folder.mkdir(parents=True,exist_ok=True)
    for name, asset in assets.items():
        shutil.copyfile(asset['path'], folder/name)
        motion.require(sha(folder/name) == asset['sha256'], '素材冻结复制失败')
    atomic_private(path,request)
    motion.track_production(value,request)
    return request


def recorded_request(queue,draft_id,render_id):
    value=motion.draft(draft_id)
    entry=next((r for r in motion.productions(draft_id)['productions'] if r['render_id']==render_id),None)
    motion.require(entry is not None,'此草稿版本没有对应制作记录')
    filename = {'motiongit-component-render-v1': 'motiongit-component-request.json',
                'hum-production-v1': 'hum-production-v1-request.json',
                'motiongit-narrated-pilot-v1': 'motiongit-narrated-pilot-request.json'}.get(entry['contract'])
    motion.require(filename is not None, '未支持的制作记录版本')
    request=read_json(queue.projects_root/entry['project_id']/'artifacts'/filename)
    motion.require(request.get('request_sha256')==entry['request_sha256'],'制作记录身份已变化')
    if entry['contract']==CONTRACT:
        motion.require(request.get('draft')==value,'草稿内容已变更，请生成新的预览')
        motion.require(request['assets']==_assets(value),'素材绑定已变更，请生成新的预览')
    elif entry['contract'] == 'hum-production-v1':
        from backlot import studio_hum_production as adapter
        adapter.validate(queue, request)
        parameters = value['parameters']
        expected_props = dict(parameters['props'])
        expected_props.update(width=adapter.WIDTH, height=adapter.HEIGHT, fps=adapter.FPS,
                              durationFrames=request['props']['durationFrames'], audio='master.wav')
        if 'shotPlan' in parameters:
            expected_props['scenes'] = adapter.plan_scenes(parameters['shotPlan'], request['props']['durationFrames'])
        motion.require(request['props'] == expected_props and request['title'] == value['title']
                       and request['provenance'] == adapter.canonical_provenance(parameters['provenance']), '完整口播草稿已变更，请生成新的预览')
        indexed = {a['slot']: a['sha256'] for a in motion.asset_list(draft_id)['assets']}
        motion.require(all(indexed.get(n) == a['sha256'] for n, a in request['origins'].items()), '素材或口播绑定已变更，请生成新的预览')
        frozen_audio = {k: v for k, v in request['audio'].items() if k not in {'durationFrames', 'voice_clock', 'mix_profile'}}
        provided_audio = dict(parameters['audio'])
        provided_audio.setdefault('tailSeconds', .25)
        provided_audio.setdefault('sfx', [])
        if provided_audio.get('music'):
            provided_audio.setdefault('musicGainDb', -16)
            provided_audio.setdefault('musicOffsetSeconds', 0)
            provided_audio.setdefault('loopMusic', False)
        motion.require(frozen_audio == provided_audio, '声音计划已变更，请生成新的预览')
    else:
        motion.require(request.get('props')==value['parameters'] and request.get('title')==value['title'],
                       '草稿内容已变更，请生成新的预览')
        indexed={a['slot']:a['sha256'] for a in motion.asset_list(draft_id)['assets']}
        motion.require(all(indexed.get(n)==a['sha256'] for n,a in request['origins'].items()),'素材绑定已变更，请生成新的预览')
    return request


def _check_source_windows(parameters, assets):
    from backlot.studio_render import media_probe
    def source(name): return Path(assets[PurePosixPath(name).name]['path'])
    speech=media_probe(source(parameters['voiceover']))
    music=media_probe(source(parameters['music']))
    duration=parameters['duration']
    motion.require(abs(speech['duration']-duration) <= .08 and music['duration']+.025 >= duration,
                   '全片须跟随完整本期口播时长，配乐须覆盖全片')
    motion.require(parameters.get('subtitles') or parameters.get('captions'), '口播样片须绑定真实字幕或SRT')
    for segment in parameters['segments']:
        def walk(value):
            if isinstance(value, dict):
                if value.get('src') and PurePosixPath(value['src']).suffix.lower() in {'.mp4','.mov','.webm'}:
                    info=media_probe(source(value['src']))
                    start=value.get('sourceStart',0)
                    motion.require(isinstance(start,(int,float)) and start >= 0
                                   and start+segment['t1']-segment['t0'] <= info['duration']+.025,
                                   '实拍区间不足，不能用循环或尾帧填充：'+value['src'])
                for item in value.values(): walk(item)
            elif isinstance(value,list):
                for item in value: walk(item)
        walk(segment['props'])


def submit(queue, request, *, phase='preview'):
    if request['contract'] == 'hum-production-v1':
        from backlot.studio_hum_production import submit as project_submit
        return project_submit(queue, request)
    if request['contract'] == 'motiongit-narrated-pilot-v1':
        from backlot.studio_motiongit_narrated_pilot import submit as project_submit
        return project_submit(queue,request)
    motion.require(phase in {'preview','render'}, '制作阶段无效')
    core={k:v for k,v in request.items() if k not in {'request_sha256','render_id','phase'}}
    motion.require(fingerprint(core)==request['request_sha256'],'冻结请求身份不一致')
    receipt=read_json(_paths(queue,request)/'result.json')
    if receipt:
        folder=_paths(queue,request)
        motion.require(receipt.get('request_sha256')==request['request_sha256']
                       and sha(folder/'native-final.mp4')==receipt.get('output_sha256')
                       and sha(folder/'quality.json')==receipt.get('quality_sha256'),'原成片或验收记录已变化')
    payload = {**request,'phase':phase};suffix=phase
    state=read_json(_paths(queue,request)/'native-state.json')
    approval=read_json(_paths(queue,request)/'plan-semantic-review.json')
    if phase=='preview' and request['draft']['workflow']=='motion-kit' and state and approval:
        motion.require(approval.get('request_sha256')==request['request_sha256'],'计划审核不属于本期')
        suffix+=':approved-plan:'+fingerprint(approval)[:16]
    return queue.submit(project_id=request['project_id'],kind=KIND,source='codex',priority='normal',
                        parent_job_id=request['render_id'],frozen_request=payload,
                        idempotency_key=CONTRACT+':'+request['request_sha256']+':'+suffix,start_paused=True)


def _paths(queue, request):
    return queue.projects_root / request['project_id'] / 'renders' / request['render_id']


def _execute(package, state, operation, *args, timeout=180):
    workflow=state.get('workflow','poster-kit')
    motion.require(workflow in COMPONENT_WORKFLOWS,'原生组件状态含未登记的工作流')
    flags=[] if workflow=='motion-kit' and operation!='setup' else ['--workflow',workflow]
    options={'temporary_root':motion.ROOT/'.local/mt'}
    return motion.helper_command(package,'run','--instance',state['instanceDirectory'],'--cache',state['cache'],
                                 operation,*flags,*args,'--language','zh',timeout=timeout,**options)


def kit_images(receipt,project):
    motion.require(receipt.get('schema')=='motiongit-preview/1' and isinstance(receipt.get('stills'),(list,dict)),
                   '新版组件预览回执不匹配')
    images=[];seen=set();project=Path(project).resolve()
    def checked(name,digest):
        motion.require(isinstance(name,str),'组件回执路径无效')
        path=PurePosixPath(name)
        motion.require(name and ':' not in name and '\\' not in name and not path.is_absolute() and '..' not in path.parts,
                       '组件回执路径无效')
        target=(project/name).resolve()
        motion.require(target.is_relative_to(project) and target.is_file() and not target.is_symlink()
                       and sha(target)==digest,'组件预览或工程身份已变化')
        return target
    if isinstance(receipt['stills'],dict):
        hashes=receipt.get('projectHashes',{})
        motion.require(hashes and 'motiongit-origin.json' in hashes and 'params.json' in hashes,'组件预览缺少来源和参数绑定')
        for name,digest in hashes.items():checked(name,digest)
        origin=read_json(project/'motiongit-origin.json')
        motion.require(origin.get('workflow')=='motion-kit' and origin.get('sourceBinding')==receipt.get('sourceBinding')
                       and origin.get('preparedParamsSha256')==sha(project/'params.json'),'组件预览来源与准备参数不匹配')
        rows=[{'path':name,'sha256':digest} for name,digest in receipt['stills'].items()]
    else:rows=receipt['stills']
    for row in rows:
        name=row.get('path','');path=PurePosixPath(name)
        motion.require(name and ':' not in name and '\\' not in name and not path.is_absolute()
                       and '..' not in path.parts and name not in seen,'组件预览图片路径无效或重复')
        target=checked(name,row.get('sha256'))
        images.append({'path':str(target),'sha256':row['sha256']});seen.add(name)
    motion.require(images,'组件预览未生成任何图片')
    return images


def review_plan(queue,request,evidence):
    folder=_paths(queue,request);state=read_json(folder/'native-state.json')
    motion.require(request['draft']['workflow']=='motion-kit' and state and state.get('plan_directory'),
                   '此版本没有待审核的新版组件计划')
    plan=Path(state['plan_directory']);report=plan/'report.json';inputs=plan/'inputs.json'
    motion.require(evidence.get('report_sha256')==sha(report) and evidence.get('inputs_sha256')==sha(inputs)
                   and evidence.get('inspected_plan') is True and evidence.get('reviewer')
                   and isinstance(evidence.get('description'),str) and 3<=len(evidence['description'])<=1000,
                   '请实际核对本期完整计划、台词与素材，审核须绑定当前版本')
    receipt=read_json(plan/'review.json')
    motion.require(receipt.get('inputsSha256')==sha(inputs),'计划源绑定已变化')
    receipt['reviewed']=True;atomic_private(plan/'review.json',receipt)
    atomic_private(folder/'plan-semantic-review.json',{**evidence,'request_sha256':request['request_sha256']})
    return {'reviewed':True,'scope':'plan-only','preview':'pending'}


def check_portrait_captions(receipt):
    """Check measured subtitle pixels in the actual 1080x1350 viewport."""
    samples=receipt.get('renderer',{}).get('captionSamples')
    motion.require(isinstance(samples,list),'4:5预览缺少实际字幕字框测量')
    items=[item for sample in samples for item in sample.get('items',[])]
    motion.require(items,'4:5预览未覆盖任何真实字幕，请补充实际口播时刻')
    for item in items:
        values=[item.get(k) for k in ['left','right','top','bottom']]
        motion.require(all(type(v) in {int,float} and math.isfinite(v) for v in values)
                       and -.5<=values[0]<values[1]<=1080.5 and -.5<=values[2]<values[3]<=1350.5,
                       '字幕超出4:5视窗；保留原声，调整公开字幕安全区后重新预览')


def encoding_layout(video,portrait45):
    """Convert the new kit's actual JPEG-range browser capture, not just tags."""
    filters=['crop=1080:1350:0:0'] if portrait45 else []
    scale='scale=1440:1800:flags=lanczos' if portrait45 else 'scale'
    options=[];policy='preserve-existing-source-color'
    if video.get('color_range')=='pc' or video.get('pix_fmt','').startswith('yuvj'):
        matrix={'bt470bg':'bt601','smpte170m':'bt601','bt709':'bt709'}.get(video.get('color_space'))
        motion.require(matrix is not None,'中间片全范围色彩矩阵未识别，请保留原片核对实际解码信息')
        transfer=video.get('color_transfer') or 'iec61966-2-1'
        motion.require(transfer in {'bt709','iec61966-2-1'},'中间片传递函数不在已核验浏览器SDR范围')
        color=f'in_color_matrix={matrix}:in_range=full:in_primaries=bt709:in_transfer={transfer}:out_color_matrix=bt709:out_range=limited:out_primaries=bt709:out_transfer=bt709'
        filters.append(scale+(':' if portrait45 else '=')+color)
        filters+=['format=yuv420p','setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709','sidedata=mode=delete']
        options=['-color_range','tv','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709']
        policy='full-range-browser-sdr-to-bt709-limited; actual libswscale matrix/transfer conversion'
    elif portrait45:filters.append(scale)
    return {'filter':','.join(filters),'options':options,'policy':policy,
            'source':{k:video.get(k) for k in ['pix_fmt','color_range','color_space','color_transfer','color_primaries']},
            'unspecified_browser_transfer':'sRGB assumed only for the observed browser JPEG capture' if video.get('color_transfer') is None else None}


def _kit_prepare(package,request,state,folder,parameters):
    inst=Path(state['instanceDirectory']);plan=inst/'plan';project=inst/'project'
    timeline=inst/'timeline.json';expected=entry_parameters(request['draft'])
    motion.require(request.get('entry_parameters')==expected,'新版组件入口参数映射已变化，请冻结新版本')
    if not timeline.exists():atomic_private(timeline,expected)
    motion.require(read_json(timeline)==expected,'本期组件参数已变化')
    if not (plan/'report.json').exists():
        _execute(package,state,'plan',timeline,'--inputs',inst/'inputs','--out',plan,timeout=300)
    report=read_json(plan/'report.json');inputs=read_json(plan/'inputs.json')
    motion.require(report.get('ready') is True and report.get('workflow')=='motion-kit'
                   and abs(report.get('duration',0)-parameters['duration'])<.001
                   and inputs.get('paramsSha256')==sha(timeline),'新版组件计划或完整口播时钟不匹配')
    state['plan_directory']=str(plan);atomic_private(folder/'native-state.json',state)
    shutil.copy2(plan/'report.json',folder/'component-plan.json')
    if not read_json(plan/'review.json').get('reviewed'):
        motion.require(request['phase']=='preview','请先实际审核本期组件计划，再生成画面预览')
        return {'status':'completed','stage':'本期组件计划已生成，等待台词与素材审核','result':{
            'review_stage':'plan','request_id':request['render_id'],'report_sha256':sha(plan/'report.json'),
            'inputs_sha256':sha(plan/'inputs.json'),'qa_status':'pending'}}
    approval=read_json(folder/'plan-semantic-review.json')
    motion.require(approval.get('request_sha256')==request['request_sha256']
                   and approval.get('report_sha256')==sha(plan/'report.json')
                   and approval.get('inputs_sha256')==sha(plan/'inputs.json'),'本期完整计划尚未实际审核')
    if not project.exists():_execute(package,state,'prepare','@vault','--inputs','@vault','--plan',plan,'--out',project,timeout=600)
    if not (project/'preview.json').exists():
        _execute(package,state,'preview',project,'--times',','.join(f'{t:.3f}' for t in preview_times(parameters)),timeout=600)
    receipt=read_json(project/'preview.json');images=kit_images(receipt,project)
    public=folder/'native-preview';public.mkdir(exist_ok=True)
    names=[]
    for i,row in enumerate(images):
        name=f'{i:03}.png';shutil.copy2(row['path'],public/name);names.append(name)
    shutil.copy2(project/'preview.json',folder/'preview-review.json')
    state.update(prepared_project=str(project),preview_directory=str(project),preview_receipt=str(folder/'preview-review.json'),
                 images=names,images_directory=str(public),original_preview_images=images)
    if request['draft'].get('output_profile')=='4:5':
        from PIL import Image
        check_portrait_captions(receipt)
        adapted=folder/'layout-preview';adapted.mkdir(exist_ok=True)
        for name in names:
            with Image.open(public/name) as im:
                motion.require(im.size==(1080,1920),'4:5需要明确的原生竖屏内容布局')
                im.crop((0,0,1080,1350)).save(adapted/name)
        state.update(images_directory=str(adapted),layout_adaptation={'source':[1080,1920],
                     'viewport':[0,0,1080,1350],'output':[1440,1800],'scope':'explicit-portrait-layout-adaptation'})
    atomic_private(folder/'native-state.json',state)
    return None


def preview_times(parameters):
    """Include revealed content, not only a blank entrance or faded exit."""
    duration=parameters['duration'];times=set()
    for segment in parameters['segments']:
        start,end=segment['t0'],segment['t1']
        times.update(min(duration-.02,start+offset) for offset in (.1,(end-start)/2,max(.1,end-start-.2)))
        for cue in segment.get('cues',[]):
            if start<=cue<end:times.add(min(end-.4,cue+.65))
    for scene in parameters.get('narrationMap', []):
        for beat in scene.get('beats', []):
            start, end = beat.get('at'), beat.get('until')
            if isinstance(start, (int, float)) and isinstance(end, (int, float)) and 0 <= start < end <= duration:
                times.add((start+end)/2)
    return sorted(times)


def review(queue, request, evidence):
    folder = _paths(queue,request)
    state = read_json(folder/'native-state.json')
    motion.require(state and state.get('preview_directory'), '请先生成本期预览')
    kit=state.get('workflow')=='motion-kit'
    preview = Path(state['preview_directory'])/('preview.json' if kit else 'preview-review.json')
    persistent=Path(state.get('preview_receipt') or preview)
    motion.require(evidence.get('preview_sha256') == sha(persistent) and evidence.get('reviewer')
                   and evidence.get('inspected_images') == state['images'], '审核证据未绑定本期全部预览图')
    motion.require(preview.is_file() and sha(preview)==sha(persistent),'原生制作实例已改变，请保留原成片并重新生成预览')
    receipt = read_json(preview)
    if kit:
        originals=kit_images(receipt,Path(state['prepared_project']))
        motion.require(originals==state['original_preview_images'],'本期原生组件预览已变化')
        inner=Path(state['prepared_project'])/'project/preview.json'
        if inner.exists():
            from backlot.studio_motion_console import acknowledge_nested_preview
            acknowledge_nested_preview(Path(state['prepared_project']),originals)
    receipt['reviewed'] = True
    atomic_private(preview,receipt)
    if persistent!=preview: shutil.copy2(preview,persistent)
    atomic_private(folder/'visual-review.json',{**evidence,'reviewed_preview_sha256':sha(preview),
                                              'scope':'sampled-preview','continuous_watching':'pending','continuous_listening':'pending'})
    return {'reviewed':True,'scope':'sampled-preview'}


def run(queue, job):
    request = job['frozen_request']
    try:
        core = {k:v for k,v in request.items() if k not in {'request_sha256','render_id','phase'}}
        motion.require(fingerprint(core) == request['request_sha256'] and request['contract'] == CONTRACT,
                       '制作请求身份不一致')
        parameters=component_timeline(request['draft'])
        project = queue.projects_root/request['project_id']
        expected = read_json(project/'artifacts/motiongit-component-request.json')
        motion.require(expected == {k:v for k,v in request.items() if k != 'phase'}, '冻结制作请求已变化')
        package = motion._get('packages',request['package_id'])
        motion.require(package['sha256'] == request['package_sha256'] and sha(package['path']) == package['sha256'], '原包身份已变化')
        for name, asset in request['assets'].items():
            motion.require(sha(project/'assets/motiongit'/name) == asset['sha256'], '冻结素材已变化')
        folder = _paths(queue,request)
        folder.mkdir(parents=True,exist_ok=True)
        completed=read_json(folder/'result.json')
        if request['phase']=='render' and completed:
            output=folder/'native-final.mp4'
            motion.require(completed.get('request_sha256')==request['request_sha256']
                           and sha(output)==completed.get('output_sha256')
                           and sha(folder/'quality.json')==completed.get('quality_sha256'),'已完成成片或验收记录已变化')
            return {'status':'completed','stage':'已恢复原生成片','result':{'work_id':completed['work_id'],
                    'version_id':completed['version_id'],'output_sha256':completed['output_sha256'],'qa_status':'pending'}}
        motion.require(sha(__file__) == request['adapter_sha256'] or (folder/'result.json').exists(),
                       '制作适配器已变化，请保留旧任务并冻结新版请求')
        state = read_json(folder/'native-state.json')
        if not state:
            short=motion.ROOT/('.local/mk' if request['draft']['workflow']=='motion-kit' else '.local/mpk')/request['request_sha256'][:16]
            short.parent.mkdir(parents=True,exist_ok=True)
            info=motion.helper_command(package,'new',short)
            state = {'instanceDirectory':info['instanceDirectory'],
                     'cache':str(motion.ROOT/'.local/mkd'/request['package_sha256'][:12]) if request['draft']['workflow']=='motion-kit'
                              else package.get('dependency_cache') or str(Path(info['instanceDirectory'])/'poster-cache'),
                     'workflow':request['draft']['workflow']}
            atomic_private(folder/'native-state.json',state)
        motion.require(state.get('workflow','poster-kit')==request['draft']['workflow'],'本期原生实例工作流已改变')
        inst = Path(state['instanceDirectory'])
        if not state.get('setup'):
            _execute(package,state,'setup',timeout=900)
            state['setup'] = True; atomic_private(folder/'native-state.json',state)
        inputs = inst/'inputs';inputs.mkdir(exist_ok=True)
        for name,asset in request['assets'].items():
            targets=(inputs/name,) if state['workflow']=='motion-kit' else (inputs/name,inst/name)
            for target in targets:
                if not target.exists(): shutil.copyfile(project/'assets/motiongit'/name,target)
                motion.require(sha(target) == asset['sha256'], '原生实例素材身份不一致')
        if state['workflow']=='motion-kit':
            pending=_kit_prepare(package,request,state,folder,parameters)
            if pending:return pending
            preview=Path(state['preview_directory'])
        else:
            timeline = inst/'timeline.json'
            if not timeline.exists(): atomic_private(timeline,request['draft']['parameters'])
            motion.require(read_json(timeline) == request['draft']['parameters'], '原生参数已变化')
            plan = inst/'plan'
            if not (plan/'host-plan.json').exists():
                _execute(package,state,'plan','--timeline',timeline,'--out',plan)
            planned = read_json(plan/'host-plan.json')
            if not planned.get('reviewed'):
                # Old poster entry accepts structural acknowledgement here.
                motion.validate_parameters(package,request['draft']['workflow'],request['draft']['parameters'])
                report = json.loads(planned['result'])
                motion.require(abs(report['duration']-parameters['duration']) < .001, '原生计划音频时长不一致')
                planned['reviewed'] = True;atomic_private(plan/'host-plan.json',planned)
                atomic_private(folder/'plan-structural-review.json',{'scope':'structure-only','parameters_sha256':planned['parametersSha256'],
                               'semantic_acceptance':'pending','report':report})
            preview = inst/'preview'
            if not (preview/'preview-review.json').exists():
                times=preview_times(parameters)
                _execute(package,state,'preview','--timeline','@vault','--plan',plan,'--out',preview,'--times',','.join(f'{t:.3f}' for t in times),timeout=600)
            state.update(preview_directory=str(preview),plan_directory=str(plan),images=sorted(f.name for f in preview.glob('*.png')))
            public_preview=folder/'native-preview';public_preview.mkdir(exist_ok=True)
            for name in state['images']: shutil.copy2(preview/name,public_preview/name)
            shutil.copy2(preview/'preview-review.json',folder/'preview-review.json')
            shutil.copy2(plan/'host-plan.json',folder/'host-plan.json')
            state['preview_receipt']=str(folder/'preview-review.json')
            state['images_directory']=str(public_preview)
            if request['draft'].get('output_profile') == '4:5':
                from PIL import Image
                adapted=folder/'layout-preview';adapted.mkdir(exist_ok=True)
                for name in state['images']:
                    with Image.open(preview/name) as im:
                        motion.require(im.size == (1080,1920), '4:5适配源尺寸与已核验布局不一致')
                        im.crop((0,0,1080,1350)).save(adapted/name)
                state['images_directory']=str(adapted)
                state['layout_adaptation']={'source':[1080,1920],'viewport':[0,0,1080,1350],'output':[1440,1800],
                    'scope':'explicit-portrait-layout-adaptation','gate':'review every adapted frame for complete subject and captions'}
        atomic_private(folder/'native-state.json',state)
        if request['phase'] == 'preview':
            return {'status':'completed','stage':'原生预览已生成，等待画面审核','result':{'request_id':request['render_id'],
                    'images':state['images'],'preview_sha256':sha(folder/'preview-review.json'),'qa_status':'pending'}}
        visual=read_json(folder/'visual-review.json')
        review_file=preview/('preview.json' if state['workflow']=='motion-kit' else 'preview-review.json')
        motion.require(visual and visual.get('reviewed_preview_sha256') == sha(review_file)
                       and read_json(review_file).get('reviewed'), '本期原生预览尚未完成实际画面审核')
        raw=Path(state.get('raw_output') or inst/'native-film.mp4')
        if raw.exists():
            from backlot.studio_render import media_probe
            try:
                raw_info=media_probe(raw)
                raw_valid=bool(raw_info.get('audio')) and abs(raw_info['duration']-parameters['duration'])<=.08
            except (WorkError,ValueError,OSError): raw_valid=False
            if not raw_valid:
                raw=inst/('native-film-recovery-'+uuid4().hex+'.mp4')
        state['raw_output']=str(raw);atomic_private(folder/'native-state.json',state)
        if not raw.exists():
            if state['workflow']=='motion-kit':_execute(package,state,'render',state['prepared_project'],'--out',raw,timeout=1800)
            else:_execute(package,state,'render','--timeline','@vault','--plan',plan,'--preview-review',preview,'--out',raw,timeout=1800)
        from lib.ffmpeg_locator import resolve_ffmpeg_pair
        from backlot.studio_render import media_probe
        from backlot.studio_investment_audio_v5 import measure_audio
        ffmpeg,_=resolve_ffmpeg_pair()
        output=folder/'native-final.mp4'
        candidate=folder/('encoding-'+uuid4().hex+'.mp4')
        conversion=encoding_layout(media_probe(raw)['video'],request['draft'].get('output_profile')=='4:5')
        if not completed:
            layout_filter=['-vf',conversion['filter']] if conversion['filter'] else []
            subprocess.run([ffmpeg,'-nostdin','-v','error','-i',str(raw),*layout_filter,'-c:v','libx264','-preset','slow',
                '-b:v','20500k','-minrate','20500k','-maxrate','20500k','-bufsize','2000k',
                '-x264-params','nal-hrd=cbr:force-cfr=1:filler=1','-pix_fmt','yuv420p',
                *conversion['options'],
                '-af','alimiter=limit=0.8:level=false','-c:a','aac','-b:a','192k','-ar','48000','-ac','2',
                '-movflags','+faststart',str(candidate)],check=True,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        info=media_probe(candidate); audio=measure_audio(candidate)
        motion.require(int(info['video'].get('bit_rate',0)) >= 20000000 and audio['true_peak_dbtp'] <= -1.5,
                       '视频码率或混音峰值未通过')
        video=info['video'];fps=float(Fraction(video.get('avg_frame_rate','0/1')))
        motion.require(video.get('codec_name')=='h264' and video.get('pix_fmt')=='yuv420p' and fps>0
                       and abs(info['duration']-parameters['duration'])<=.08
                       and abs(int(video.get('nb_frames',0))-round(parameters['duration']*fps))<=1,
                       '成片编码、完整帧数或原声时长未通过')
        if request['draft'].get('output_profile') == '4:5':
            motion.require((info['video']['width'],info['video']['height']) == (1440,1800), '4:5输出尺寸不一致')
        subprocess.run([ffmpeg,'-nostdin','-v','error','-i',str(candidate),'-f','null','-'],check=True,capture_output=True)
        if output.exists():
            output.rename(folder/('unconfirmed-'+uuid4().hex+'.mp4'))
        candidate.rename(output)
        info=media_probe(output)
        atomic_private(folder/'quality.json',{'media':info,'audio':audio,'color_conversion':conversion,'full_decode':'passed','visual_review':'sampled-native-preview',
                       'continuous_watching':'pending','continuous_listening':'pending'})
        work=WorkCatalog(queue.projects_root).register(request['project_id'],output,work_key='main',mode='manual',
            event_id=job['job_id'],quality_passed=False,actor='motiongit-components',title=request['draft']['title'],
            summary='MotionGit原生组件实拍口播；原声时钟、配乐及原生音效；未发布')
        version=next(v for v in work['versions'] if v['sha256']==sha(output))
        atomic_private(folder/'result.json',{'request_sha256':request['request_sha256'],'output_sha256':sha(output),
                       'quality_sha256':sha(folder/'quality.json'),'work_id':work['work_id'],'version_id':version['version_id']})
        return {'status':'completed','stage':'原生成片已导出，等待观看','result':{'work_id':work['work_id'],'version_id':version['version_id'],
                 'output_sha256':sha(output),'qa_status':'pending'}}
    except (WorkError,subprocess.SubprocessError,OSError,ValueError,KeyError) as exc:
        return {'status':'failed','stage':'MotionGit本地制作待恢复','error':{'type':'MotionGitRender','message':str(exc)[:800]},
                'retryable':True,'safe_resume_point':'motiongit_component'}
