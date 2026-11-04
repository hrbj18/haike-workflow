"""Append five exact candidates while preserving every previous registry object."""
import copy,json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'Haike_video'))
from backlot.motion_replay_chromatic_suite_production import SPECS,VERSION
REG=ROOT/'Haike_video/config/motion-replay/numbered-06-11.json';BASE='Haike_video/templates/chromatic-suite-production-v1'
def sha(path):return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
def build():
 d=json.loads(REG.read_text('utf-8'));before=copy.deepcopy(d['templates'])
 sources=[BASE+'/'+n for n in ('Scene.tsx','Runtime.tsx','Derived-A.tsx','Derived-B.tsx','Derived-C.tsx','SOURCE_MAP.json')]+['Haike_video/backlot/motion_replay_chromatic_suite_production.py']
 for tid,(ids,_,_) in SPECS.items():
  old=next(t for t in before if t['template_id']==tid and t['version']=='1.1.0');t=copy.deepcopy(old)
  t.update(version=VERSION,candidate=True,execution_scope='full current speech; actual original action functions; separate real media clock')
  t['renderer']={'kind':'project','entrypoint':BASE+'/Scene.tsx#ChromaticSuite','adapter':'backlot.motion_replay_chromatic_suite_production','execution':'supported'}
  t['sources']=[{'path':path,'sha256':sha(path)} for path in sources]
  t['objects']=[{'id':n,'role':role,'authority':{'path':BASE+'/Scene.tsx','symbol':'SuiteDrawing','scope':'original geometry retained in Derived-A/B/C, 1.5x HD scale'}} for n,role in [('stage','distinct original layout'),('videos','real HD footage'),('presenter','HQ current-audio bookends'),('captions','full script'),('medical','non-medical disclaimer')]]
  for a,id in zip(t['actions'],ids):
   assert a['id']=='haike.'+tid+'.'+id
   a.update(version=VERSION,implementation={'path':BASE+'/Scene.tsx','symbol':'ACTIONS','dispatch':'ACTIONS[actionId]'},objects=[o['id'] for o in t['objects']],parameters={'path':'production_request.props.scenes[].knots','type':'individually resolved ASR word/cue event knots; real video clock unaffected'})
  t['timeline']={'mode':'semantic','clock':'full actual narration,30fps','events':[{'id':a['id']+'.knots','action_id':a['id'],'anchor':{'path':'production_request.props.scenes[].knots','resolved_against':'receipts.asr.metadata.words'},'window':'actual absolute frames for independently anchored internal states','reading':'full narration and explicit medical reading domain'} for a in t['actions']], 'retiming':{'supported':True,'scope':'independent ASR internal state anchors, source easing retained; no video/audio time stretch'}}
  t['slots']=[{'id':n,'kind':k,'input_path':'production_request.'+n,'required':True,'missing_policy':'block before parent queue admission'} for n,k in [('props','semantic-composition'),('sources','local-hd-files'),('receipts','verified-upstream')]]
  t['capabilities']={k:{'supported':True,'scope':scope} for k,scope in [('complete_speech','10-600s original complete captions and continuous master'),('hd','1080x1920; native HD slots; output must verify >=20Mbps'),('audio','full master, unchanged speech rate'),('avatar','verified current-audio HQ V5.3.1 NORMAL Plus bookends')]}
  t['capabilities']['arbitrary_action_remix']={'supported':False,'reason':'exact four ordered original composite actions only'}
  t['validation']={k:{'status':'pending','method':m,'scope':'independent new candidate only','evidence':[]} for k,m in [('structure','focused semantic/source tests'),('visual','view actual complete output'),('audio_listening','continuous listening'),('other_machine','not executed')]}
  d['templates']=[x for x in d['templates'] if (x['template_id'],x['version'])!=(tid,VERSION)];d['templates'].append(t)
 assert all(x in d['templates'] for x in before if x['version']!=VERSION or x['template_id'] not in SPECS)
 from backlot.motion_replay import validate_registry
 validate_registry(d);REG.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('Five exact candidates appended; all prior objects preserved')
if __name__=='__main__':build()
