"""Rebuild ONLY the sidecar registry from the unchanged approved release files.

Run after reviewing a sidecar change. Never regenerates any original release.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = 'Haike_video/templates/'
SIDE = BASE + 'motion-replay-numbered-02-05/'


def read(name):
    return json.loads((ROOT / name).read_bytes())


def sources(paths):
    return [{'path': name, 'sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest()} for name in paths]


def validation(scope, evidence):
    return {name: {'status': state, 'method': method, 'scope': scope, 'evidence': evidence}
            for name, state, method in [
                ('source_identity', 'pass', '原release全部源码哈希核对；运行时prepare再次核对'),
                ('historical_visual', 'pass', '原冻结验收记录；本轮不追溯升级旧结论'),
                ('sidecar_visual', 'pending', '旁路包装须实际比较代表状态；结构检查不证明画面'),
                ('continuous_audio', 'pending', '未进行本轮完整设备听审'),
                ('production', 'pending', 'prepared不等于入队/完整输出；逐期沿原gate验收'),
                ('platform', 'pending', '未发布；未做目标平台/异机验收')]}


def action(identity, version, name, path, symbol, objects, params, phases):
    return {'id': 'haike.' + identity + '.' + name, 'version': version,
            'implementation': {'path': path, 'symbol': symbol, 'dispatch': '原组件真实调用；不使用selection/data-effect作为执行器'},
            'objects': objects, 'parameters': params, 'phases': dict(zip(('entry', 'active', 'settled', 'exit'), phases))}


def event(name, act, anchor, window, reading):
    return {'id': name, 'action_id': act['id'], 'anchor': anchor, 'window': window, 'reading': reading}


def objects(path, rows):
    return [{'id': name, 'role': role, 'authority': {'path': path, 'scope': detail}}
            for name, role, detail in rows]


def base(identity, version, number, entrypoint, files, obj, acts, events, clock, scope, evidence):
    return {'template_id': identity, 'version': version, 'gallery_id': identity, 'family': 'numbered',
            'number': number, 'renderer': {'kind': 'project', 'entrypoint': entrypoint,
                'adapter': 'backlot.motion_replay_numbered_02_05:prepare', 'execution': 'supported',
                'scope': '只准备；执行能力以queue_route和blockers为准'},
            'sources': sources(files+['Haike_video/backlot/motion_replay_numbered_02_05.py']), 'objects': obj, 'actions': acts,
            'timeline': {'mode': 'source_locked', 'clock': clock, 'events': events,
                'retiming': '锁定原窗口；不接受动作子集、替换、重排或时间伸缩'},
            'slots': [{'id': 'prepared-episode', 'kind': 'local_prepared_directory', 'input_path': 'request.data',
                'required': True, 'missing_policy': '阻断；先运行原prepare，显式提供独立本期目录，不自动读取私有默认'}],
            'capabilities': {'reference_fidelity': scope, 'script_replacement': '本适配器只消费原prepare的已准备输入；不自动写稿/配音/切人物',
                'semantic_reordering': False, 'arbitrary_catalogue_action_replacement': False,
                'action_selection': '仅接受完整固定顺序；变更明确拒绝',
                'high_definition': False, 'audio': '保留原行为'},
            'validation': validation(scope, evidence)}


def kinetic():
    identity, version = 'kinetic-field-v1', '1.0.0'
    folder = BASE + identity + '/'
    plan = read(folder + 'layout.json')
    mapping = [
        ('angled-panel-settle','Duo',0,.5,3.65), ('keyword-assemble','Duo',.65,1.5,3.65),
        ('split-divider-morph','Duo',1.5,2.15,3.65), ('tape-reveal','Tape',2.4,2.85,3.65),
        ('footage-iris','Hands',3.2,3.65,6.6), ('short-marker','Hands',3.8,4.25,6.6),
        ('detail-loupe','Hands',4.6,5.25,6.6), ('hand-drawn-arrow','Hands',5.6,6.05,6.6),
        ('photo-cascade','Collage',6.76,7.32,8.3), ('stack-to-location','Location',7.4,8.3,12),
        ('pin-pop','Location',8.5,9.05,12), ('floor-strip','Location',9.3,9.85,12),
        ('location-focus','Location',10.7,11.2,12), ('portrait-disc','Invitation',12,12.55,16),
        ('headline-assemble','Invitation/TextReveal',12.7,13.4,16), ('photo-fan','Invitation',13.65,14.2,16),
        ('invitation-stamp','Invitation',14.4,14.85,16)]
    obj = objects(folder+'index.tsx', [('paired-footage','双实拍主体','Duo的分割遮罩/几何/取景'),
        ('detail','互动与放大窗','Hands同源视频、虹膜和箭头'),('photos','现场照片','Collage与Invitation'),
        ('location','门店和人物','Location源2秒起取与8秒同源人物窗'),('invitation','数字人邀请','Invitation原人物/标题/印章'),
        ('shell','品牌与标签','Shell与本期content字段'),('sound','完整16秒音轨','Audio sample.wav gain=layout.audio.gain')])
    acts, events = [], []
    for name, symbol, start, end, until in mapping:
        act = action(identity,version,name,folder+'index.tsx',symbol,
            ['paired-footage'] if symbol in ('Duo','Tape') else ['detail'] if symbol=='Hands' else ['photos'] if symbol=='Collage' else ['location'] if symbol=='Location' else ['invitation'],
            {'source_locked': 'index.tsx的秒级公式/曲线/几何；layout.primary_actions仅为索引',
             'content': 'episode.content；input-contract.text_limits'},
            [f'{start}s触发', f'{start}–{end}s；headline-assemble内部逐词相位取TextReveal实际参数' if name=='headline-assemble' else f'{start}–{end}s',
             f'动作保持/背景持续行为取源码，最大至{until}s', f'{until}s父级卸载或全片结束'])
        acts.append(act)
        events.append(event(name,act,{'absolute_seconds':start}, {'seconds':[start,end], 'endpoint':'源码条件与逐帧采样'},
            {'until_seconds':until,'note':'保持期仍含源码定义的轻量运动；不改成静帧'}))
        if name=='headline-assemble':
            act['parameters']['source_locked']='Invitation.Sequence from=round(12.7*24)=305；TextReveal实际intro3/hold3/recede5/assemble9/wordDelay2/wordStagger3/wordDuration6/wordFade默认2帧'
            act['phases']['entry']='全局305帧挂载TextReveal；不把layout.primary_actions的估计13.4s当精确落定点'
            act['phases']['active']='局部intro[0,3]、recede[3,8]、assemble[3,12]；后续词pushStart=3+2+(i-1)*3，持续6帧'
            events[-1]['anchor']={'absolute_frame':305,'fps':24}
            events[-1]['window']={'start_frame':305,'motion_end_frame':'305 + max(12, 5 + max(0, word_count-2)*3 + 6)；word_count=closingTitle.split(" ").filter(Boolean).length','source_authority':'TextReveal源码','parent_end_frame':384}
            events[-1]['reading']={'from_frame':'按motion_end_frame求值；原两词内容317帧起','until_frame':384}
    result = base(identity,version,2,'Haike_video/scripts/kinetic_field_preview.py',
        [folder+x for x in ['release.json','index.tsx','layout.json','content.json','input-contract.json','prepare_inputs.py','render.cjs']],
        obj,acts,events,{'fps':24,'duration_seconds':16,'design_canvas':[540,960],'frozen_renderer_scale':.5,'encoded_size':[270,480]},
        '原16秒低清有声确认效果；原渲染器scale=.5；本轮不提升高清/听审状态', [folder+'APPROVAL.json',folder+'README.md'])
    result['capabilities']['audio']='完整sample.wav原速，layout.audio.gain；不重新混音'
    result['validation']['sidecar_visual']={'status':'not_applicable','method':'未增加模板2视觉实现；原冻结源码和输入字节核验',
        'scope':'仅旁路参数/入口；不声称本轮看过视频或听音','evidence':['.local/motion-standard-unification/A/prepare-results.json']}
    result['reproduction']={'prepare_entrypoint':folder+'prepare_inputs.py', 'request_contract':folder+'input-contract.json',
        'queue_entrypoint':'Haike_video/scripts/kinetic_field_preview.py', 'preview_phase':'stills', 'export_phase':'video',
        'gate':'核源码/素材/bundle及本期真实design-review；不自动提交'}
    return result


def nana():
    identity, version = 'nana-mint-explainer-v1', '1.0.0'
    folder = BASE + identity + '/'
    profile = read(folder+'template-profile.json')
    obj = objects(folder+'shared.tsx', [('background','薄荷纸面','Backdrop'),('navigation','五章导航','Shell'),
        ('media','软件/素材窗','MediaWindow原速取样与显式clean UI holds'),('presenter','同声源人物窗','Presenter源取景与各scene固定外框'),
        ('graphics','标题、对比、图解','四个scenes文件原生组件'),('captions','实测字幕','index.tsx WordCaptions毫秒转帧'),
        ('sound','完整原声混音','index.tsx Audio(episode.voice)原速，只混入一次')])
    acts, events = [], []
    for name in profile['scene_ids']:
        symbol = 'Introduction' if name in profile['scene_ids'][:4] else 'Workflow' if name=='workflow' else 'Argument' if name in profile['scene_ids'][5:9] else 'Resources'
        act=action(identity,version,name,folder+'scenes/'+symbol+'.tsx',symbol+'(scene.id='+name+')',
            ['media','presenter','graphics'], {'content':'public/content.json scenes[id='+name+']',
             'timing':'start/end为全局秒；cues为场景局部秒，只有实际源码消费的cue可变；其余局部时钟锁定',
             'source_locked':'TSX几何、原生动画参数；不开放generic x/y/easing'},
             ['scene.start挂载','组件内部局部帧公式及明确cue','各内部动画落定后保留到scene.end；内部保持按源码','scene.end卸载；不加通用退出动画'])
        acts.append(act)
        events.append(event(name,act,{'scene_id':name,'default_local_seconds':0}, {'start':'scene.start','end':'scene.end','unit':'seconds'}, '本期真实scene时钟；内部关键事件另列'))
    cue_events={'integration':[('partner',2.3),('arrow',3.4)],'workflow':[('prompt',2.4),('steps',7.7),('preview',12.6)],
        'compare':[('arrow',2.1),('after',3.3)],'question':[('answer',2.5)],
        'examples':[('presenterOff',2.3),('overlay',2.4)],'logic':[('overlayEnd',2.1)]}
    fixed={'terms':[('label-1',1.75),('label-2',3.5),('media-focus',2.5)],
        'brief':[('label-0',.25),('label-1',1.07),('label-2',1.89),('presenter-on',2.1)],
        'value':[('right-card-on',.2),('right-card-arrow',1.2)],'difference':[('row-0',.35),('row-1',1),('row-2',1.65)],
        'course':[('step-0',.65),('step-1',1.01),('step-2',1.37)],
        'logic':[('card-0',0),('card-1',.4),('card-2',.8)],'closing':[('comment-card',.3)]}
    for name, rows in cue_events.items():
        for cue, default in rows:
            events.append(event(name+'.'+cue,acts[profile['scene_ids'].index(name)],
                {'scene_id':name,'cue':cue,'default_local_seconds':default,'consumed_by':f'scene.cues.{cue}'},
                {'start':'scene.start + cue','end':'源码定义的动画局部持续/下一cue/scene.end'},
                'cue来自本期实测语义时码；不从文案长度推算；examples相关cue只在overlay存在时消费'))
    for name, rows in fixed.items():
        for label, at in rows:
            events.append(event(name+'.'+label,acts[profile['scene_ids'].index(name)],
                {'scene_id':name,'default_local_seconds':at,'source_locked':True},
                {'start':'scene.start + 固定局部秒','end':'源码公式/父scene.end'},
                '本事件没有独立语义输入；不宣称随任意新稿自动适配'))
    for label, offset in [('type-start',.5),('type-end',2.9),('cursor',3.4),('send-click',4.1)]:
        events.append(event('workflow.prompt.'+label,acts[4],
            {'scene_id':'workflow','cue':'prompt','default_local_seconds':2.4,'offset_seconds':offset,
             'source_locked':'PromptSend局部typeStart/typeDuration/cursorAt/clickAt'},
            {'start':'scene.start + cues.prompt + 固定局部偏移','end':'组件内部公式；最大至cues.steps'},
            '随真实prompt锚点整体移动；组件内部输入/发送时距锁定，不支持独立语义覆盖'))
    files=[folder+x for x in ['release.json','index.tsx','shared.tsx','types.ts','prepare.py','template-profile.json','input-contract.json','render.cjs']]+[folder+'scenes/'+x+'.tsx' for x in ['Introduction','Workflow','Argument','Resources']]
    result=base(identity,version,3,'Haike_video/scripts/nana_mint_preview.py',files,obj,acts,events,
        {'fps':30,'canvas':[1920,1080],'master':'完整episode.voice实际声音；scenes/captions/cues本期实测', 'accepted_duration_seconds':2678/30},
        '已认可89.266667秒横屏1080p有声版本；每期新输入独立验收', [folder+'APPROVAL.json',folder+'VALIDATION.md'])
    result['timeline']['mode']='semantic'
    result['timeline']['retiming']='已准备content的scene.start/end和明确cues由原TSX真实消费；固定局部事件保持锁定；本旁路不接受独立events覆盖/自动ASR/任意重排'
    result['capabilities'].update(high_definition='1920×1080/30fps原入口；确认片已导出，新期另验',
        audio='复用本期完整混音；保留原v5音轨，不二次加乐；连续设备听审仍pending',
        semantic_reordering='13景顺序固定；可消费作者依据本期ASR准备的scene/cue/caption时间，不支持任意语义重排')
    result['validation']['sidecar_visual']={'status':'not_applicable','method':'未增加模板3视觉实现；原release及当前定稿public/content/音轨身份核验',
        'scope':'只返回原props与真实cue；未重新渲染、连续观看或听审','evidence':['.local/motion-standard-unification/A/prepare-results.json']}
    result['reproduction']={'prepare_entrypoint':folder+'prepare.py','request_contract':folder+'input-contract.json',
        'queue_entrypoint':'Haike_video/scripts/nana_mint_preview.py','preview_mode':'frames','export_mode':'render',
        'gate':'原队列核本期bundle/声音/媒体/真实图片review；不自动提交'}
    return result


def notes(number):
    identity='field-notes-v1' if number==4 else 'field-notes-v2'
    version='1.0.0' if number==4 else '2.0.0'
    folder=BASE+('chromatic-motion-lab-v1/' if number==4 else identity+'/')
    source=folder+('RecipeStage.tsx' if number==4 else 'Scene.tsx')
    binding=read(SIDE+'bindings.snapshot.json')[identity]
    obj=objects(source,[('headline','固定短标题','RecipeStage.Stage或Title'),('material','真实照片','固定Img、Media或私有GridToHero导入；照片不自动换视频'),
        ('note','场景短句','固定note时钟'),('presenter','连续辅助人物窗','原连续24秒视频，muted/volume0，取景不变'),
        ('caption','示意字幕','固定四场；不冒充真实ASR/口型'),('chrome','纸面品牌与进度','原场景的几何/颜色/边界')])
    acts, events=[],[]
    for action_id,start,end,symbol in binding['stages']:
        name=action_id.rsplit('.',1)[-1]
        active = ['标题39–63让位，照片51–87进入','实际GridToHero在0–202执行，之后Freeze202','线18–52绘制，照片53–77进入','来源42–82汇聚，结论83–107展开'][len(acts)] if number==5 else '局部帧title0–18、media24–90、note96–120；summary行24/38/52开始'
        stable = [110,203,96,113][len(acts)] if number==5 else 120
        act=action(identity,version,name,source,symbol,['headline','material','note'],
            {'source_locked':'原源码几何、曲线、照片索引和部分固定文字；不开放163动作任意替换',
             'callable':SIDE+'FieldNotes.tsx:MotionReplayFieldNotesAction', 'dispatch_index':len(acts)},
            ['局部0帧；标题原source入场',active,f'局部{stable}至{end-start-1}帧阅读'+('；网格保持原Freeze202' if number==5 and len(acts)==1 else ''),f'全局{end}帧场景卸载或720帧全片结束'])
        acts.append(act)
        events.append(event(name,act,{'absolute_frame':start}, {'frames':[start,end],'fps':30,'endpoint':'[from,to)'},{'frames':[start+stable,end]}))
    # Internal events matter independently of the outer scene window.
    internals = [[('title-demote',39,63),('photo-enter',51,87)], [('grid-focus',50,180),('grid-return',180,203)],
                 [('line-draw',18,52),('photo-enter',53,77)], [('source-travel',42,82),('conclusion-expand',83,107)]] if number==5 else [
        [('title',0,18),('parallax',24,90),('note',96,120)], [('title',0,18),('paired-reveal',24,90),('note',96,120)],
        [('title',0,18),('reflow',24,90),('note',96,120)], [('summary-row0',24,40),('summary-row1',38,54),('summary-row2',52,68),('highlight-note',96,120)]]
    for i, rows in enumerate(internals):
        start,end=binding['stages'][i][1:3]
        for label,a,b in rows:
            events.append(event(acts[i]['id'].rsplit('.',1)[-1]+'.'+label,acts[i],{'absolute_frame':start+a,'source_local_frame':a},
                {'frames':[start+a,start+b],'fps':30}, {'until_frame':end,'source_locked':True}))
    freeze=folder+('custom-recipes/release.json' if number==4 else 'release.json')
    wrapper=SIDE+('FieldNotesV1.tsx' if number==4 else 'FieldNotes.tsx')
    files=[freeze,source,folder+('custom-recipes/field-notes.json' if number==4 else 'selection.json'),wrapper,SIDE+'action-bindings.cjs',SIDE+'Preview.tsx',SIDE+'build-preview.cjs']
    for act in acts:
        act['parameters']['callable']=wrapper+':MotionReplayFieldNotesAction'
    result=base(identity,version,number,wrapper+':MotionReplayFieldNotes',files,obj,acts,events,
        {'fps':30,'frames':720,'canvas':[720,1280],'master':'固定作者时钟；静音示意，无音频重排'},
        '原24秒竖屏低清静音用户认可样式；照片仍是照片，人物全片辅助小窗',
        [folder+('custom-recipes/VALIDATION.json' if number==4 else 'VALIDATION.json')])
    result['capabilities'].update(audio='静音；人物Video muted/volume0；未开放主声音',
        full_production=False,high_definition=False,private_dependency='模板5真实网格组件保留本机原包；哈希不授予分发权' if number==5 else '无需模板5私有网格组件')
    result['validation']['sidecar_visual']={'status':'pass','method':'Codex内置浏览器源组件/旁路Player对应帧实际查看；先核视频ready与原时钟，保存全页原图、联系表和数值差异',
        'scope':('4个对应状态' if number==4 else '7个对应状态')+'；两项动作ID调用另读回源场景/局部帧；仅本机低清静音抽查，像素非全同，未做新完整连播/音频/高清验收',
        'evidence':[f'.local/motion-standard-unification/A/comparison-{number}.jpg','.local/motion-standard-unification/A/frame-comparison.json',
                    '.local/motion-standard-unification/A/decoded-frame-evidence.json','.local/motion-standard-unification/A/action-proof.json']}
    result['reproduction']={'prepare_entrypoint':BASE+'chromatic-motion-lab-v1/prepare.py' if number==4 else folder+'build.cjs',
        'existing_preview_entrypoint':folder+('CustomPreview.tsx' if number==4 else 'Preview.tsx'),
        'wrapper_entrypoint':wrapper+':MotionReplayFieldNotes',
        'wrapper_build_entrypoint':SIDE+'build-preview.cjs',
        'gate':'只允许本地Player预览；完整渲染必须等待合法统一队列适配，不绕过队列'}
    return result


def main():
    # The CJS binding is executable; the snapshot is checked by tests, not a runtime selector.
    from subprocess import check_output
    snapshot=json.loads(check_output(['node','-e',"process.stdout.write(JSON.stringify(require('./action-bindings.cjs').bindings))"],cwd=ROOT/SIDE))
    (ROOT/SIDE/'bindings.snapshot.json').write_text(json.dumps(snapshot,indent=2)+'\n',encoding='utf-8')
    import importlib.util
    candidate_path=ROOT/BASE/'field-notes-video-v1/registry.py'
    spec=importlib.util.spec_from_file_location('_field_notes_video_registry',candidate_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    document={'schema':'haike.motion-replay-registry/1','templates':[kinetic(),nana(),notes(4),notes(5),module.entry(ROOT)]}
    (ROOT/'Haike_video/config/motion-replay/numbered-02-05.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
