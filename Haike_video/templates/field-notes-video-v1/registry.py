"""Independent semantic video candidate; never rewrites the photographic release."""
import hashlib


def entry(root):
    folder = 'Haike_video/templates/field-notes-video-v1/'
    source = folder + 'Scene.tsx'
    names = ('arrive', 'compare', 'connect', 'converge')
    event_names = (
        ('titleDemoteStart','titleDemoteEnd','mediaEnterStart','mediaEnterEnd','noteStart'),
        ('focusStart','focusEnd','returnStart','returnEnd','noteStart'),
        ('lineStart','lineEnd','mediaEnterStart','mediaEnterEnd','noteStart'),
        ('pathStart','travelStart','travelEnd','conclusionStart','conclusionEnd','noteStart'),
    )
    objects = [{'id': name, 'role': role, 'authority': {'path': source, 'scope': scope}} for name, role, scope in [
        ('scene','四场主体与真实视频','Arrive/Compare/Connect/Converge；源代码持有几何/曲线/裁切'),
        ('text','主标题/摘要/法律说明/地址','episode的短文案与固定合法说明；不可注入布局代码'),
        ('captions','完整原稿字幕','episode.captions与真实ASR同源，逐字覆盖sourceText'),
        ('presenter','本期原速人物窗','完整主声轨的指定窗口，独立25fps母片原速采样'),
        ('sound','完整声音','master.wav；完整原速旁白与授权背景音乐，主声音始终开启')]]
    actions=[]; events=[]
    for i,name in enumerate(names):
        identity='haike.field-notes-v2.video.'+name
        actions.append({'id':identity,'version':'2.1.0',
            'implementation':{'path':source,'symbol':name.capitalize(),'dispatch':'FieldNotesVideo -> ACTIONS[scene.actionId] -> actual function'},
            'objects':['scene','text','captions','presenter','sound'],
            'parameters':{'scene':f'episode.scenes[{i}]','events':list(event_names[i]),
                          'layout':'Scene.tsx owns geometry/easing; only validated absolute semantic event frames are inputs'},
            'phases':{'entry':f'scenes[{i}].from','active':{'events':list(event_names[i]),'clock':'absolute full-audio 30fps'},
                      'settled':'last event + at least36 frames reading; real footage keeps playing',
                      'exit':f'scenes[{i}].to; no timeline restart'}})
        for event in event_names[i]:
            events.append({'id':name+'.'+event,'action_id':identity,
                'anchor':{'input_path':f'episode.scenes[{i}].events.{event}','unit':'absolute_frame'},
                'window':{'within':f'episode.scenes[{i}].from/to','causality':'validated by validate_episode'},
                'reading':{'minimum_settled_frames':36,'until':f'episode.scenes[{i}].to'}})
    files=[folder+x for x in ['Scene.tsx','index.tsx','render.cjs','registry.py','webpack.cjs']]+[
        'Haike_video/backlot/motion_replay_numbered_02_05.py',
        'Haike_video/backlot/motion_replay_field_notes_video.py',
        'Haike_video/backlot/motion_replay_field_notes_render.py',
        'Haike_video/scripts/motion_replay_field_notes_video.py',
        'Haike_video/scripts/motion_replay_hq_guard.py',
        'Haike_video/remotion-composer/package-lock.json']
    return {'template_id':'field-notes-v2','version':'2.1.0','gallery_id':'field-notes-v2','number':5,'family':'numbered',
        'renderer':{'kind':'project','entrypoint':'Haike_video/scripts/motion_replay_field_notes_video.py',
                    'adapter':'backlot.motion_replay_numbered_02_05:prepare','execution':'supported'},
        'sources':[{'path':p,'sha256':hashlib.sha256((root/p).read_bytes()).hexdigest()} for p in files],
        'objects':objects,'actions':actions,
        'timeline':{'mode':'semantic','clock':{'fps':30,'duration':'ceil(full narration samples/rate*30)','speed':1},
                    'events':events,'retiming':'实际ASR语义锚点驱动内部事件；保持四场关系，不支持任意动作重排或替换'},
        'slots':[{'id':name,'kind':kind,'input_path':path,'required':True,'missing_policy':'阻断；不循环、静帧或省略音轨补足'}
                 for name,kind,path in [('prepared','local_prepared_directory','request.data'),('voice','complete_audio','public/master.wav'),
                     ('videos','real_video_playlists','episode.scenes[*].media'),('asr','real_speech_timing','timing.json'),
                     ('presenter','same_source_hq_windows','episode.presenters')]],
        'capabilities':{'full_production':True,'candidate':True,'gallery_default_changed':False,
            'reference_fidelity':'保留纸色/青珊瑚及四阶段信息关系；独立视频改编，不宣称照片版逐像素或私有GridToHero执行',
            'script_replacement':'已准备完整原稿、原生语音、真实ASR和合法素材后支持16至600秒',
            'semantic_reordering':False,'high_definition':'1080x1920/30fps,video>=20Mbps',
            'audio':'完整原速主旁白+授权背景音乐；仅本期人物窗，不能改变声速补长',
            'arbitrary_catalogue_action_replacement':False},
        'validation':{name:{'status':state,'method':method,'scope':scope,'evidence':evidence} for name,state,method,scope,evidence in [
            ('structure','pending','source identity/strict data gates/real queue','registered execution; final tests recorded per delivery',['Haike_video/tests/backlot/test_motion_replay_field_notes_video.py']),
            ('visual','pending','actual queued semantic event frames and encoded MP4','本期逐项验收，不继承旧照片版视觉确认',['.local/motion-production-20261103/A/design-review.json']),
            ('audio','pending','full input coverage, true peak and continuous device listen','技术与听审分开',['.local/motion-production-20261103/A/mix-provenance.json']),
            ('production','pending','exact-contract queue consumption and actual full MP4','not registration alone',['.local/motion-production-20261103/A/DELIVERY.json'])]}}
