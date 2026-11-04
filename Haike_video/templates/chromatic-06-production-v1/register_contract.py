"""Author only the independent candidate and refresh adapter hash without changing old capabilities."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
REG=ROOT/'Haike_video/config/motion-replay/numbered-06-11.json'
BASE='Haike_video/templates/chromatic-06-production-v1'
MODULE='Haike_video/backlot/motion_replay_chromatic_production.py'
ADAPTER='Haike_video/backlot/motion_replay_numbered_06_11.py'
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def build():
 d=json.loads(REG.read_text('utf-8'))
 # The adapter gained only exact-version dispatch. Old Scene/props/capabilities
 # do not change, so preserve every old field and refresh only that owned file.
 for t in d['templates']:
  for s in t['sources']:
   if s['path']==ADAPTER:s['sha256']=sha(ADAPTER)
 d['templates']=[t for t in d['templates'] if (t['template_id'],t['version'])!=('chromatic-06','1.2.0-candidate.1')]
 ids=['cut-open','push-near','observe-colour','cut-close'];symbols=['CutOpen','PushNear','ObserveColour','CutClose']
 objects=[{'id':x,'role':r,'authority':{'path':BASE+'/Scene.tsx','symbol':s,'scope':'original720 geometry scaled1.5; all actual inputs explicit in Props'}}
  for x,r,s in [('stage','original blue/orange main scene','Drawing'),('main-videos','continuous HD original footage','Footage'),('presenter','HQ same-audio bookends','Presenter'),('caption','complete original script','Drawing'),('medical','non-medical diagnostic disclaimer','Drawing')]]
 actions=[{'id':'haike.chromatic-06.'+id,'version':'1.2.0-candidate.1','implementation':{'path':BASE+'/Scene.tsx','symbol':symbol,'dispatch':'ACTIONS[actionId]'},
  'objects':[o['id'] for o in objects],'parameters':{'path':'production_request.props.scenes[].events','type':'separate ASR word/cue anchors and bounded designed duration; no scene-percent interpolation'},
  'phases':{'entry':'source geometry; event-specific window','active':'actual Scene ACTIONS consumes each named internal event','settled':'holds source stage while real footage continues; exact reading interval from request','exit':'explicit next semantic scene, no audio stretching'}} for id,symbol in zip(ids,symbols)]
 t={'template_id':'chromatic-06','version':'1.2.0-candidate.1','family':'numbered','candidate':True,
  'renderer':{'kind':'project','entrypoint':BASE+'/Scene.tsx#ChromaticProduction','adapter':'backlot.motion_replay_numbered_06_11','execution':'supported'},
  'sources':[{'path':p,'sha256':sha(p)} for p in [BASE+'/Scene.tsx',MODULE,ADAPTER]],'objects':objects,'actions':actions,
  'timeline':{'mode':'semantic','clock':'complete unmodified current narration plus <=1/30s frame-alignment tail; 30fps',
   'events':[{'id':a['id']+'.semantic-events','action_id':a['id'],'anchor':{'path':'production_request.props.scenes[].events','resolved_against':'receipts.asr actual words/cues'},'window':'from/to absolute frames independently resolved for every internal event','reading':'bounded action duration plus actual remaining speech; no fixed24s clock'} for a in actions],
   'retiming':{'supported':True,'scope':'this independent candidate uses separate real ASR anchors for aperture/wipe/push/crossfade/settle/split/notes; event bounds/order/text budgets validated'}},
  'slots':[{'id':id,'kind':kind,'input_path':'production_request.'+path,'required':True,'missing_policy':'block before parent admission'} for id,kind,path in [('props','semantic-composition','props'),('sources','local-hd-files','sources'),('receipts','verified-upstream','receipts')]],
  'capabilities':{'complete_speech':{'supported':True,'scope':'actual audio10-600s; complete original captions'},'hd':{'supported':True,'scope':'1080x1920 with real HD originals; actual output must verify20Mbps'},'audio':{'supported':True,'scope':'continuous full master; original speech speed; separate mix'},'avatar':{'supported':True,'scope':'completed HQ V5.3.1/NORMAL/Plus bookends only'},'arbitrary_action_remix':{'supported':False,'reason':'only these four composite action implementations; complete semantic events required'}},
  'validation':{k:{'status':status,'method':method,'scope':scope,'evidence':evidence} for k,status,method,scope,evidence in [
   ('structure','pending','focused tests required','semantic event binding and parent queue admission',[]),('visual','pending','actual full output must be viewed','this independent candidate only',[]),('audio_listening','pending','continuous listening required','complete current output',[]),('other_machine','pending','not executed','other physical host',[])]}}
 d['templates'].append(t);REG.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('Candidate registered; old1.1 identity/capabilities preserved, adapter hash updated')
if __name__=='__main__':build()
