"""Read-only additive native knowledge preparation; original pack versions stay fixed."""
from copy import deepcopy
from pathlib import Path
from backlot import studio_motiongit as motion,studio_imported_native_knowledge as production
from backlot.motion_replay_imported import _assets,_package,_selected
from backlot.motion_replay import ReplayError
from backlot.work_catalog import read_json
ROOT=Path(__file__).resolve().parents[2]
REGISTRY=ROOT/'Haike_video/config/motion-replay/imported-native-full.json'
VERSION='4.0.0-native-production.1'

def prepare(template,request,*,workspace):
    def require(ok,message):
        if not ok:raise ReplayError(message)
    registered=next((t for t in read_json(REGISTRY)['templates'] if (t['template_id'],t['version'])==(template.get('template_id'),template.get('version'))),None)
    require(registered and registered['version']==VERSION,'原生知识制作精确版本未登记')
    require(Path(workspace).resolve()==ROOT,'请使用当前安装所属工作区')
    require(not set(request)-{'template_id','version','workflow','parameters','assets','title','action_ids'},'原生知识只读准备字段无效')
    require(request.get('workflow','native')=='native','本版本须使用原native公开入口')
    if 'parameters' not in request:return {'status':'blocked','submitted':False,'blockers':['须绑定本期完整声音、真ASR字幕、实际论证与原生公开recipe；默认无人物，选人物模式须真实连续来源。']}
    origin=next(t for t in read_json(ROOT/'Haike_video/config/motion-replay/imported.json')['templates'] if (t['template_id'],t['version'])==(registered['template_id'],registered['reference_version']))
    package=_package(origin,workspace);parameters=deepcopy(request['parameters']);motion.validate_parameters(package,'native',parameters)
    assets=_assets(request,workspace);clock=production.bindings({'parameters':parameters},assets)
    used=list(dict.fromkeys(f"haike.{template['template_id']}.native.{s['family']}" for s in parameters['segments']))
    require(set(used)<={a['id'] for a in registered['actions']},'原生实际家族不属于本精确知识包')
    _selected(request,used)
    consumer={'package_id':package['id'],'parameters':parameters,'assets':assets,'title':request.get('title','完整原生知识讲解')}
    return {'status':'prepared','submitted':False,'blockers':[],'production_contract':production.CONTRACT,
        'renderer':deepcopy(registered['renderer']),'action_bindings':[a for a in registered['actions'] if a['id'] in used],
        'consumer':{'entrypoint':'backlot.studio_imported_native_knowledge:prepare','input':consumer,'requires_existing_queue':True,'category':'original_native_adapter'},
        'timeline':{'clock':clock,'segments':parameters['segments']},
        'reproduction':{'source':'unchanged original public native helper/parameters','original_version':registered['reference_version'],'original_package_sha256':package['sha256'],'default_presenter':parameters.get('presenter',{}).get('mode','none'),'protected_core_extracted':False},
        'validation_scope':'只读schema/完整声音/真ASR/素材身份；原生helper计划与真实预览、全片导出、听审仍由父队列分项验收'}
