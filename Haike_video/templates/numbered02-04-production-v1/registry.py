"""Write only new exact-version registry; original registry objects never change."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Haike_video'))
from backlot import motion_replay_numbered_02_05_production as production


def entry(identity):
    fps,width,height,names=production.SPECS[identity]
    file='Haike_video/templates/numbered02-04-production-v1/'+('Kinetic.tsx' if identity=='kinetic-field-v1' else 'nana/index.tsx' if identity=='nana-mint-explainer-v1' else 'FieldNotes.tsx')
    authority={'path':file,'scope':'Derived frozen native geometry/easing; source owns placement, clips follow absolute full-audio clock'}
    objects=[{'id':name,'role':role,'authority':authority} for name,role in [('scene','原动效和场景'),('media','连续真实视频'),('presenter','同声源真实人物窗口'),('caption','完整ASR字幕'),('sound','完整原速主声音')]]
    acts=[];events=[]
    for index,name in enumerate(names):
        action_id=production.actions(identity)[index]
        acts.append({'id':action_id,'version':'2.0.0','implementation':{'path':file,
            'symbol':('useActionWindows -> '+name) if identity=='kinetic-field-v1' else 'NanaTemplate.scenes -> '+name if identity=='nana-mint-explainer-v1' else 'RecipeStage.Stage -> '+name,
            'dispatch':'Exact action windows consumed by original-derived component; unknown/partial/reordered selections rejected'},
            'objects':['scene','media','presenter','caption','sound'],
            'parameters':{'window':f'episode.actions["{action_id}"]','geometry':'bound source, not caller supplied','media':'episode.media; actual video frame clock independent from frozen geometry'},
            'phases':{'entry':f'actions[{action_id}].from','active':f'actions[{action_id}].from/to','settled':'Original settled geometry continues while footage and master voice stay1x','exit':'owning stage.to'}})
        events.append({'id':name,'action_id':action_id,'anchor':{'input_path':f'episode.actions["{action_id}"].from','unit':'absolute_frame'},
            'window':{'input_path':f'episode.actions["{action_id}"]'},'reading':{'rule':'scene retains full measured semantic passage; individual motion keeps original duration'}})
        internal=(['keyword.lower-pop'] if name=='keyword-assemble' else ['arrow.head'] if name=='hand-drawn-arrow' else ['title.actual-mounted','title.native2word-assembled'] if name=='headline-assemble' else []) if identity=='kinetic-field-v1' else (
            ['title.start','title.settled','media.start','media.settled','note.start','note.settled'] if identity=='field-notes-v1' else list(production.NANA_CUES[name]))
        for event in internal:
            events.append({'id':name+'.internal.'+event,'action_id':action_id,'anchor':{'source':'backlot/motion_replay_numbered_02_05_production.py:resolve_events','control':event,'stage_index':index},
                'window':{'scope':'consumed source cue or native fixed frame interval; resolved event receipt records absolute frame'},'reading':{'until':'owning stage.to'}})
    if identity=='nana-mint-explainer-v1':
        workflow=production.actions(identity)[4]
        for name,offset in [('typing-start',.5),('typing-end',1.6),('cursor',1.8),('click',2.1)]:events.append({'id':'workflow.prompt.'+name,'action_id':workflow,
            'anchor':{'input_path':'episode.nativeNana.scenes[4].cues.prompt','offset_seconds':offset},'window':{'source':'nana/scenes/Workflow.tsx:PromptSend'},'reading':{'until':'steps cue mounts native AgentSteps'}})
    return {'template_id':identity,'version':'2.0.0','gallery_id':identity,'family':'numbered','number':{'kinetic-field-v1':2,'nana-mint-explainer-v1':3,'field-notes-v1':4}[identity],
        'renderer':{'kind':'project','entrypoint':'backlot.motion_replay_numbered_02_05_production:run','adapter':'backlot.motion_replay_numbered_02_05_full:prepare','execution':'supported'},
        'sources':[{'path':name,'sha256':digest} for name,digest in production.source_identity().items()],
        'objects':objects,'actions':acts,'timeline':{'mode':'semantic','clock':{'fps':fps,'duration':'ceil(full native narration seconds*fps)','speech_speed':1},
            'events':events,'retiming':'真实ASR分别锚定内部事件/原场景，延长阅读与真实视频持有期，不整片等比拉长，不改变声音速度'},
        'slots':[{'id':name,'kind':kind,'input_path':path,'required':True,'missing_policy':'阻断；不得照片/静音/冻结人物补长'} for name,kind,path in [
            ('prepared','local_prepared_directory','request.data'),('voice','complete_original_audio','public/master.wav'),('asr','real_alignment','reuse-source.json'),
            ('videos','real_original_video','episode.media'),('presenters','same_voice_hq','episode.presenters')]],
        'capabilities':{'full_production':True,'high_definition':[width,height],'fps':fps,'complete_audio':True,'script_replacement':'通过完整原声音/ASR和受控原组件输入准备',
            'reference_fidelity':'原组件源码派生并保留几何/运动公式；视频替换与标题/法律字幕适配另验，非旧媒体逐像素重播','arbitrary_action_replacement':False},
        'validation':{key:{'status':'pending','method':method,'scope':'Per-template actual full output required; registration alone is not acceptance','evidence':'.local/motion-full-delivery-20261104/A/DELIVERY_INDEX.json'} for key,method in [
            ('structure','strict manifest/action/source/ASR/voice-window checks'),('visual','actual original/reference and new semantic-state frames'),('production','single-lane parent/full encoded file'),('audio','full source/master/AAC technical and separate device listen')]}}


def main():
    output=ROOT/'Haike_video/config/motion-replay/numbered-02-05-production.json'
    output.write_text(json.dumps({'schema':'haike.motion-replay-registry/1','templates':[entry(name) for name in production.SPECS]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
