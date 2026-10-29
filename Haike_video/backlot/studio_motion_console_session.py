"""Console profile strategy for the existing shared MotionTemplate sessions.

Only public content fields and recipe durations are composed here. Source jobs,
payments, persistence, reviews and final production remain owned by the existing
session service and native queue adapter.
"""
from copy import deepcopy
from pathlib import Path

from backlot import studio_motion_console as compiler
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError,read_json,sha

ID='motiongit-console-story-v1'
ROOT=Path(__file__).resolve().parents[2]
PROFILE=ROOT/'Haike_video/templates/motiongit-console-v1/profile.json'
DEFAULTS=ROOT/'.local/motion-console/defaults.json'
LAYOUTS={'landscape':{'label':'原生横版 16:9','engine':'native','width':1920,'height':1080},
         'portrait45':{'label':'原生竖屏重排 · 4:5视窗','engine':'native','width':1440,'height':1800}}


def fields():
    return [{'id':g['id'],'fields':[{**f,'maxChars':f.get('maxLength',100),
             'multiline':f['key']=='body'} for f in g['fields']]} for g in read_json(PROFILE)['groups']]


def content(segments):
    result={};by_id={s['recipe']:s for s in segments}
    for group in fields():
        row={}
        for field in group['fields']:
            item=by_id[group['id']]['inputs']
            try:
                for part in field['key'].split('.'):item=item[int(part)] if isinstance(item,list) else item[part]
            except (IndexError,KeyError):item=''
            row[field['key']]=item
        result[group['id']]=row
    return result


def apply_content(segments,values):
    result=deepcopy(segments)
    for segment in result:
        for key,value in values[segment['recipe']].items():
            parts=key.split('.');target=segment['inputs']
            for part in parts[:-1]:target=target[int(part)] if isinstance(target,list) else target[part]
            last=parts[-1]
            if isinstance(target,list):
                index=int(last)
                if value=='':
                    if index<len(target):target.pop(index)
                elif index==len(target):target.append(value)
                else:target[index]=value
            else:target[last]=value
    return result


def seed(*,check_sources=True):
    defaults=read_json(DEFAULTS)
    if not isinstance(defaults,dict) or not defaults.get('latest_example_input'):
        raise WorkError('此机器尚未配置控制台原包和合法参考输入','unavailable')
    path=Path(defaults['latest_example_input'])
    if not path.is_absolute():path=(ROOT/path).resolve()
    if not path.is_absolute() or not path.is_file():raise WorkError('控制台本机参考输入不存在','unavailable')
    value=read_json(path)
    # Private bundled inputs use paths relative to their seed document. The
    # public session/production contract still receives absolute, SHA-bound files.
    def relocate(item):
        if isinstance(item,dict):
            if isinstance(item.get('path'),str) and 'sha256' in item:
                source=Path(item['path'])
                if not source.is_absolute():item['path']=str((path.parent/source).resolve())
            for child in item.values():relocate(child)
        elif isinstance(item,list):
            for child in item:relocate(child)
    relocate(value)
    if check_sources:compiler.source(value)
    else:
        # Browsing the catalog must not decode/probe six large source videos.
        # Full source validation still runs on create and preparation.
        package=compiler.packages.inspect_package(compiler.checked(value['tools']['package']))
        profile=read_json(compiler.PROFILE)
        compiler.require(package['template_id']==profile['template_id'] and package['version'] in profile['versions']
                         and package['support']=='official-helper','此控制台原包版本尚未接入')
        compiler.require(sha(compiler.checked(value['tools']['helper']))==compiler.packages.HELPER_SHA,'控制台官方入口未核验')
    expected=[g['id'] for g in fields()]
    compiler.require([s['recipe'] for s in value['console']['segments']]==expected,
                     '此会话版本需要已核验的五组控制台编排')
    value.update(template_id=ID,content=content(value['console']['segments']),
                 short_title=value.get('short_title','海客AI社区服务店'),
                 presenter_label=value.get('presenter_label','海客店长'))
    return value


def configured(value):
    result=deepcopy(value['input'])
    defaults=read_json(DEFAULTS)
    if defaults.get('native_dependency_cache'):
        cache=Path(defaults['native_dependency_cache'])
        result['native_dependency_cache']=str(cache if cache.is_absolute() else (ROOT/cache).resolve())
    result.update(title=value['title'],brand=value['brand'],script=value['script'])
    result['console']['layout']='portrait' if value['layout']=='portrait45' else 'landscape'
    result['console']['presenterMode']=value.get('presenter_mode','auto')
    result['console']['segments']=apply_content(result['console']['segments'],value['content'])
    clock=compiler.native.speech._clock(compiler.checked(result['voice']))
    _,caps=compiler._captions(result['captions'],Path.cwd(),result['voice'],clock['duration_seconds'])
    contract=read_json(compiler.PROFILE)
    result['console']['segments']=compiler.fit_segments(result['console']['segments'],caps,
                                                       clock['duration_seconds'],contract['groups'])
    return result


def slots(value):
    result=[]
    for label,row,start,seconds in compiler.media_windows(value['input']['media'],configured(value)['console']['segments']):
        name=label.replace('wall.','wall-')
        result.append({'slot':name,'label':f'扇形实拍 {int(name[5:])+1}' if name.startswith('wall-') else '焦点实拍',
                       'at':start,'seconds':seconds,'kind':'video'})
    return result


def prepare(store,value,queue):
    from backlot.studio_investment_recompose import fingerprint
    inputs=configured(value)
    folder=ROOT/'.local/ms'/value['id']/'versions'/fingerprint({'input':inputs,'compiler':sha(compiler.__file__),
                                                             'strategy':sha(__file__),
                                                             'presenter':compiler.presenter.identity()})[:24]
    folder.mkdir(parents=True,exist_ok=True);input_path=folder/'input.json'
    atomic_private(input_path,inputs)
    built=compiler.build(input_path,folder/'build');build_path=folder/'build/console-build.json'
    result=compiler.plan(build_path)
    review=read_json(compiler.checked(inputs['source_review']))
    images={i['path']:i for r in review['materials'] for i in r.get('actual_images_viewed',[])}
    source_images=list(images.values());calibration=inputs['console'].get('cropCalibration')
    if calibration:
        from backlot import studio_motion_face_crop as face_crop
        proof=face_crop.validate(calibration,inputs['avatar'],inputs['tools'],inputs['console']['presenterCrop'])
        for sample in proof['samples']:images[sample['diagnostic']['path']]=sample['diagnostic']
    value['build']=compiler.bound(build_path)
    value['plan']={'token':result['plan_sha256'],'summary':{'durationFrames':built['frames'],
                   'selectedScenes':built['recipes'],'blocking':[],'missing':[]},'images':list(images.values()),
                   'source_images':source_images}
    value['status']='plan_review'
    return store.put(value,value['revision'])


def approve_plan(store,value,token,seen):
    plan=value.get('plan',{})
    compiler.require(value['status']=='plan_review' and plan.get('token')==token
                     and set(seen)==set(range(len(plan['images']))),'请实际查看控制台计划和全部素材帧')
    path=compiler.checked(value['build']);built=compiler.load(path)
    review_path=path.parent/'web-plan-review.json'
    source_images=plan.get('source_images',plan['images'])
    review={'status':'pass','actual_plan_inspected':True,'plan_sha256':token,
            'actual_source_images_viewed':source_images}
    if review_path.exists():
        prior=read_json(review_path)
        current=Path(built['instance'])/'plan/plan.json'
        if (prior.get('status')=='pass' and prior.get('actual_plan_inspected') is True
                and prior.get('plan_sha256')==token and prior.get('actual_source_images_viewed')==source_images
                and prior.get('reviewed_plan_sha256')==sha(current)):
            review['reviewed_plan_sha256']=prior['reviewed_plan_sha256']
    atomic_private(review_path,review)
    inputs=read_json(built['input_path']);times=[];at=0
    c=inputs['console']
    if c.get('cropCalibrationRequired') and not c.get('cropCalibration'):
        from backlot import studio_motion_face_crop as face_crop
        probe=compiler.prepare_and_preview(path,review_path,
                    [round(built['frames']/60*f,3) for f in [.1,.3,.5,.7,.9]],calibration_import=True)
        project=Path(probe['project'])
        calibration=face_crop.calibrate(project,inputs['avatar'],inputs['tools'],path.parent/'face-calibration')
        proof=read_json(compiler.checked(calibration))
        value['input']['console'].update(presenterCrop=proof['crop'],cropCalibration=calibration)
        value['status']='ready_to_prepare';value.pop('build',None);value.pop('plan',None)
        value=store.put(value,value['revision'])
        # Changed crop is a new public parameter set and new plan. Preserve the
        # provisional instance; actually review new plan + 7 diagnostics first.
        return prepare(store,value,None)
    for segment in inputs['console']['segments']:
        seconds=segment['durationFrames']/60
        times.extend([round(at+min(.7,seconds/3),3),round(at+seconds-.4,3)]);at+=seconds
    if value['layout']=='portrait45':
        caps=compiler._captions(inputs['captions'],Path.cwd(),inputs['voice'],at)[1]
        expanded=list(times)+[round((c['t0']+c['t1'])/2,3) for c in caps];at=0
        for segment in inputs['console']['segments']:
            seconds=segment['durationFrames']/60
            expanded.extend([round(at+min(.15,seconds/3),3),round(at+seconds/2,3),round(at+seconds-.04,3)])
            expanded.extend(round(at+anchor+.12,3) for anchor in segment.get('anchors',{}).values() if anchor+.12<seconds)
            at+=seconds
        times=sorted(set(expanded))
    result=compiler.prepare_and_preview(path,review_path,times)
    preview=read_json(result['preview']);files=compiler.preview_images(preview,result['project'])
    value['preview_files']=files;token=sha(result['preview'])
    if value['layout']=='portrait45':
        from backlot import studio_motion_native_viewport as viewport
        from backlot.studio_investment_recompose import fingerprint
        pairs=viewport.crop_images(files,path.parent/'viewport-preview')
        value['viewport_images']=pairs;value['preview_files']=[row['image'] for row in pairs]
        token=fingerprint({'source_preview_sha256':token,'layout':viewport.CONSOLE_45,'images':pairs})
    value['preview']={'token':token,'images':[{'id':i,'url':
        f"/api/studio/motion-templates/sessions/{value['id']}/preview/{i}",
        'label':preview['stills'][i].get('label','交付画面')} for i in range(len(files))],'engine':'native'}
    value['status']='preview_review'
    return store.put(value,value['revision'])


def approve_preview(store,value,token,queue):
    from backlot import studio_dark_native as native
    path=compiler.checked(value['build']);review_path=path.parent/'web-preview-review.json'
    built=compiler.load(path);preview_path=compiler.preview_path(Path(built['instance'])/'project')
    review={'status':'pass','unreviewed_preview_sha256':token,'actual_images_viewed':value['preview_files']}
    if value['layout']=='portrait45':
        from backlot import studio_motion_native_viewport as viewport
        from backlot.studio_investment_recompose import fingerprint
        require_token=fingerprint({'source_preview_sha256':sha(preview_path),'layout':viewport.CONSOLE_45,'images':value['viewport_images']})
        compiler.require(token==require_token,'4:5预览身份已变化，请重新准备本期画面')
        review.update(unreviewed_preview_sha256=sha(preview_path),layout=viewport.CONSOLE_45,viewport_images=value['viewport_images'],
                      review_scope='final-viewport-only; omitted original auxiliary top HUD is not claimed viewed')
    atomic_private(review_path,review)
    manifest=compiler.manifest(path,review_path);frozen=native.prepare(queue,manifest)
    value['frozen']={'request':str(queue.projects_root/frozen['project_id']/'artifacts'/native.REQUEST_FILE),'engine':'native'}
    return frozen
