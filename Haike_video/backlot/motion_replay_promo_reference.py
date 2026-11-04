"""Read-only preparation for the independent visible-reference promo component."""
from copy import deepcopy
from pathlib import Path
from backlot import studio_imported_promo_reference as production
from backlot.work_catalog import read_json
from backlot.motion_replay import ReplayError

REGISTRY=Path(__file__).resolve().parents[1]/'config/motion-replay/imported-promo-reference.json'
VERSION='3.0.0-reference-public.1'

def require(ok,message):
    if not ok:raise ReplayError(message)

def prepare(template,request,*,workspace):
    registered=next((t for t in read_json(REGISTRY)['templates'] if (t['template_id'],t['version'])==(template.get('template_id'),template.get('version'))),None)
    require(registered and template['version']==VERSION,'独立促销组件精确版本未登记')
    require(Path(workspace).resolve()==production.ROOT.parent,'请在此安装所属工作区准备')
    require(isinstance(request,dict) and not set(request)-{'template_id','version','workflow','input','action_ids'},'促销准备仅接受workflow/input/action_ids')
    require(request.get('workflow','promo-reference-full')=='promo-reference-full','此版本使用promo-reference-full路线')
    if 'input' not in request:return {'status':'blocked','submitted':False,'blockers':['请绑定完整声音、真实句词、原稿、OFL字体及已审实拍与六段动作链'],'consumer':None}
    value=deepcopy(request['input']);n=production.preflight(value)
    used=[f"haike.motiongit-promo-user.reference-public.{s['recipe']}" for s in n['props']['scenes']]
    if 'action_ids' in request:require(set(request['action_ids'])==set(used) and len(request['action_ids'])==len(used),'动作选择须与完整六段参考链一致')
    require(set(used)=={a['id'] for a in registered['actions']},'本期动作链与登记版本不符')
    return {'status':'prepared','submitted':False,'blockers':[],'production_contract':production.CONTRACT,'renderer':deepcopy(registered['renderer']),'action_bindings':deepcopy(registered['actions']),'props':n['props'],'timeline':{'clock':n['voice_clock'],'events':[{'scene_id':s['id'],'recipe':s['recipe'],'start':s['start'],'end':s['end'],'cues':s['cues']} for s in n['props']['scenes']]},'consumer':{'entrypoint':'backlot.studio_imported_promo_reference:prepare','input':value,'requires_existing_queue':True,'category':'independent_project_adapter'},'reproduction':{'implementation_identity':'promo-reference-independent-v1','reference_identity':n['reference'],'original_personal_package_required':False,'full_audio':True,'full_text':True,'paid_calls':0},'validation_scope':'只读完整输入/实测主钟/真实素材；图像、完整编码与听音分项另验'}
