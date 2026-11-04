"""Read-only exact-version preparation for independent knowledge components."""
from copy import deepcopy
from pathlib import Path
from backlot import studio_imported_knowledge_full as production
from backlot.work_catalog import read_json
from backlot.motion_replay import ReplayError

REGISTRY=Path(__file__).resolve().parents[1]/'config/motion-replay/imported-knowledge-full.json'
VERSION='3.0.0-independent.1'

def require(ok,message):
    if not ok:raise ReplayError(message)

def prepare(template,request,*,workspace):
    """Probe existing full inputs; no drafts, files, jobs, downloads or payments."""
    registered=next((t for t in read_json(REGISTRY)['templates'] if (t['template_id'],t['version'])==(template.get('template_id'),template.get('version'))),None)
    require(registered and template['version']==VERSION,'独立知识组件精确版本未登记')
    require(Path(workspace).resolve()==production.ROOT.parent,'请在此安装所属工作区准备')
    require(isinstance(request,dict) and not set(request)-{'template_id','version','workflow','input','action_ids'},'独立知识准备仅接受workflow/input/action_ids')
    require(request.get('workflow','knowledge-full')=='knowledge-full','此版本须使用独立knowledge-full路线')
    if 'input' not in request:return {'status':'blocked','submitted':False,'blockers':['请绑定完整口播、真ASR、原稿、授权实拍、OFL字体与语义图解；人物须有同源实际覆盖区间'],'consumer':None}
    value=deepcopy(request['input']);require(isinstance(value,dict),'input须为实际输入JSON对象')
    theme=registered['theme'];require(value.get('theme')==theme,'本期输入与所选纸笔/粉笔精确版本不符')
    n=production.preflight(value)
    used=list(dict.fromkeys(f"haike.{template['template_id']}.knowledge-full.{s['recipe']}" for s in n['props']['scenes']))
    if 'action_ids' in request:require(set(request['action_ids'])==set(used) and len(request['action_ids'])==len(set(used)),'动作选择须与实际图解一致，不能仅选动作后绕过正文时钟')
    require(set(used)<={a['id'] for a in registered['actions']},'实际图解含未登记动作')
    return {'status':'prepared','submitted':False,'blockers':[],'production_contract':production.CONTRACT,
        'renderer':deepcopy(registered['renderer']),'action_bindings':[a for a in registered['actions'] if a['id'] in used],
        'props':n['props'],'timeline':{'clock':n['voice_clock'],'events':[{'scene_id':s['id'],'recipe':s['recipe'],'start':s['start'],'end':s['end'],'cues':s['cues']} for s in n['props']['scenes']]},
        'consumer':{'entrypoint':'backlot.studio_imported_knowledge_full:prepare','input':value,'requires_existing_queue':True,'category':'independent_project_adapter'},
        'reproduction':{'implementation_identity':'knowledge-full-independent-v1','reference_identity':n['reference'],'original_personal_package_required':False,'full_audio':True,'full_text':True,'paid_calls':0},
        'validation_scope':'只读完整输入/真ASR/同源人物域/实拍时长；实际画面、完整编码和听音分项另验'}
