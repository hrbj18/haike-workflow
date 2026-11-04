"""Independent reference-observed knowledge composition. No private kernel import."""
from __future__ import annotations
import hashlib,json,math,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TEMPLATE=ROOT/'Haike_video/templates/knowledge-reference-public-v2'
VERSION='5.1.0-independent.1'
PAPER='knowledge-explainer-sketchnote';CHALK='knowledge-explainer-chalkboard'
# Inherited from motion-replay-presentation.json, rather than from template IDs.
# These are stable existing front-end cards; the execution/version remain new.
GALLERY_IDS={PAPER:'motion-package-mg-178e6870ae932019c6bf2fe9',CHALK:'motion-package-mg-5b31b7dd6e6709861dc6ac88'}
PAPER_FAMILIES=('sketchnote.step-sequence','sketchnote.keyword-annotation','sketchnote.sticky-revision','sketchnote.return-loop')
SCIENCE=tuple('chalkboard.'+n for n in ('orbit-phase','surface-view','shadow-overlap','inclined-orbit','projection-compare','causal-compare','ray-topology','condition-proof'))
GENERIC=('compare','process','evidence','recap','definition')
OVERLAY='AI体质检测：非医疗诊断。不看病不卖药，给您个参考。'
FONT_FILES=('LXGWWenKai-Medium.ttf','LongCang.ttf','Fraunces.ttf','JetBrainsMono.ttf')
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(path)
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def canonical(text):return ''.join(c.lower() for c in text if c.isalnum())
def source_identity():
    files=[Path(__file__),ROOT/'Haike_video/backlot/motion_knowledge_public_production_v2.py',ROOT/'Haike_video/remotion-composer/package-lock.json']
    files += [p for p in TEMPLATE.rglob('*') if p.is_file() and 'node_modules' not in p.parts]
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(files)}
def phase_state(phase,inclination):
    a,k=math.radians(phase),math.radians(inclination);moon=(math.cos(a),math.sin(a)*math.cos(k),math.sin(a)*math.sin(k));return {'moon':moon,'lit':(1+moon[0])/2,'height':moon[2]}
def circle_overlap(r,R,d):
    require(r>0 and R>0 and d>=0,'圆面半径/距离无效')
    if d>=r+R:return 0.
    if d<=abs(r-R):return math.pi*min(r,R)**2
    return r*r*math.acos((d*d+r*r-R*R)/(2*d*r))+R*R*math.acos((d*d+R*R-r*r)/(2*d*R))-.5*math.sqrt((-d+r+R)*(d+r-R)*(d-r+R)*(d+r+R))
def geometry():return read(TEMPLATE/'geometry.json')
def paper_layout(count):
    require(type(count)is int and 1<=count<=4,'纸页对象数量无效');g=geometry()['paper'];one=count==1
    row=g['single'] if one else g['multiple'];width=row['width'] if one else count*row['widthPerItem']+row['widthExtra']
    fit=min(952/width,1328/row['height'])
    return {**row,'width':width,'fit':fit,'top':245+(1328-row['height']*fit)/2,'first_center':64+row['firstX']*fit}
def projected_point(moon,radius,view,rotation=0):
    if view=='top':return (moon[0]*radius,-moon[1]*radius)
    pitch,a=math.radians(82),math.radians(rotation);x=moon[0]*radius;y=-(moon[1]*math.cos(pitch)+moon[2]*math.sin(pitch))*radius
    return (x*math.cos(a)-y*math.sin(a),x*math.sin(a)+y*math.cos(a))
def section_state(body,shadow,offset):return {'offset':offset,'overlap':circle_overlap(body,shadow,abs(offset))/(math.pi*body*body)}
def ray_segments(m):
    rows=[]
    for index in range(m['count']):
        y=m['firstY']+index*m['gap'];end=m['endX'];hit_id=None
        for b in m['blockers']:
            dy=y-b['y']
            if abs(dy)>b['radius']:continue
            dx=math.sqrt(max(0,b['radius']**2-dy*dy));near,far=b['x']-dx,b['x']+dx
            if far<m['startX']:continue
            hit=max(m['startX'],near)
            if hit<=end:end,hit_id=hit,b['id']
        rows.append({'start':(m['startX'],y),'end':(end,y),'hit_id':hit_id})
    return rows
def surface_camera(moon,radius,p):
    g=geometry()['science'];target=g['surface'];return {'x':moon[0]+(target['center'][0]-moon[0])*p,'y':moon[1]+(target['center'][1]-moon[1])*p,'radius':radius+(target['radius']-radius)*p,
        'mini_scale':1+(target['miniScale']-1)*p,'mini_x':(target['miniEarth'][0]-g['center'][0]*target['miniScale'])*p,'mini_y':(target['miniEarth'][1]-g['center'][1]*target['miniScale'])*p}
def validate_model(family,m):
    require(isinstance(m,dict) and 'kind' in m,'真实科学机制必须有完整显式模型，不能用标题伪装')
    if family=='chalkboard.ray-topology':
        require(set(m)=={'kind','startX','endX','firstY','gap','count','blockers'} and m['kind']=='rays','光路只接受实际消费的射线/遮板模型')
        require(all(type(m[k])in{int,float} and math.isfinite(m[k]) for k in ('startX','endX','firstY','gap','count')),'射线参数必须为有限数值')
        require(type(m['count'])is int and 1<=m['count']<=12 and 64<=m['startX']<m['endX']<=1016 and 245<=m['firstY'] and m['firstY']+(m['count']-1)*m['gap']<=1450 and 10<=m['gap']<=100,'射线模型越界')
        require(1<=len(m['blockers'])<=4 and len({v['id'] for v in m['blockers']})==len(m['blockers']),'遮板ID/数量不符')
        for b in m['blockers']:require(set(b)=={'id','x','y','radius'} and all(type(b[k])in{int,float} and math.isfinite(b[k]) for k in ('x','y','radius')) and 10<=b['radius']<=120 and 64+b['radius']<=b['x']<=1016-b['radius'] and 245+b['radius']<=b['y']<=1450-b['radius'],'实际遮板越界')
        return
    common={'kind','phase','phaseSpeed','bodyRadius'}
    if family=='chalkboard.shadow-overlap':keys=common|{'occluderRadius','offset','offsetSpeed'};kind='section'
    elif family=='chalkboard.causal-compare':keys=common|{'occluderRadius','offset','offsetSpeed','counterPhase','counterSpeed'};kind='causal'
    else:
        keys=common|{'inclination','displayInclination','sunRadius','orbitRadius'};kind='orbit'
        if family in {'chalkboard.inclined-orbit','chalkboard.condition-proof'}:keys|={'occluderRadius','shadowOffset'}
    require(set(m)==keys and m.get('kind')==kind,'科学家族与实际模型字段不匹配；拒绝未消费的伪控件')
    require(all(type(v)in{int,float} and math.isfinite(v) for k,v in m.items() if k!='kind'),'模型数值必须有限')
    require(.1<=m['bodyRadius']<=.5 and abs(m['phaseSpeed'])<=90,'模型半径/连续角速度越界')
    if kind=='orbit':require(abs(m['inclination'])<=45 and abs(m['displayInclination'])<=45 and 1.2<=m['orbitRadius']<=2 and .1<=m['sunRadius']<=.6,'轨道/投影参数越界')
    if 'occluderRadius' in m:require(.1<=m['occluderRadius']<=1,'遮挡截面半径越界')
    if 'offset' in m:require(abs(m['offset'])<=3 and abs(m['offsetSpeed'])<=1,'截面扫描偏移越界')
    if 'counterSpeed' in m:require(abs(m['counterSpeed'])<=90,'反事实角速度越界')
    if 'shadowOffset' in m:require(abs(m['shadowOffset'])<=3,'轨道影带偏移越界')
def validate_episode(e):
    require(set(e)<= {'schema','implementation','template_id','version','fps','durationFrames','title','sourceText','captions','scenes','narration','music','musicGainDb','presenter','requiredOverlay','sourceLabel','previewOnly'},'不接受未开放的布局、字体或旧人物字段')
    require(e.get('schema')=='haike.knowledge-reference-public-episode/2' and e.get('implementation')=='knowledge-reference-public-v2','独立实现身份不符')
    require(e.get('version')==VERSION and e.get('template_id') in {PAPER,CHALK},'未知知识精确版本')
    require(e.get('fps')==60 and type(e.get('durationFrames'))is int and 60<=e['durationFrames']<=36000,'本实现只接受60fps完整主时钟')
    require(e.get('presenter')=='none','公开参考默认无人，不接受旧首尾口型/圆窗回退')
    require(e.get('requiredOverlay')==OVERLAY,'完整医疗边界不得删除')
    require(type(e.get('musicGainDb'))in{int,float} and math.isfinite(e['musicGainDb']) and -24<=e['musicGainDb']<=-8,'音乐增益须在已开放混音范围内')
    require(isinstance(e.get('sourceLabel'),str) and len(e['sourceLabel'])<=32 and not any(v in e['sourceLabel'] for v in ('DOCX','B6','完整原稿','.local','内部')),'来源标注必须面向观众')
    caps=e['captions'];require(caps and canonical(''.join(c['text'] for c in caps))==canonical(e['sourceText']),'真实完整字幕不能删词或替换成画面短标签')
    last=0
    for cue in caps:
        require(set(cue)=={'text','startMs','endMs','timestampMs','confidence'} and last<=cue['startMs']<cue['endMs']<=e['durationFrames']/60*1000,'字幕形状/实测顺序越界');last=cue['endMs']
    cursor=0;scene_ids=set();event_ids=set()
    for scene in e['scenes']:
        require(scene['id'] not in scene_ids and scene['from']==cursor and type(scene['to'])is int and scene['to']>cursor,'场景空白或编号重复');scene_ids.add(scene['id']);cursor=scene['to']
        family=scene['family'];require(family in (PAPER_FAMILIES if e['template_id']==PAPER else SCIENCE+GENERIC),'本样式不支持该机制')
        require(1<=len(scene['items'])<=(4 if e['template_id']==PAPER else 3),'对象数超出原生关系容量')
        ids={i['id'] for i in scene['items']};require(len(ids)==len(scene['items']),'对象ID重复')
        for i in scene['items']:
            require(set(i)<={'id','label','icon','notes','text','before','after','highlight','evidenceRef','kind'} and 0<len(i['label'])<=8 and all(len(v)<=16 for v in i.get('notes',[])),'实际画面短标签/注解超过本字号容量或包含未消费字段')
            require(len(i.get('notes',[]))<=3 and (e['template_id']==PAPER or not i.get('notes')),'注解超出实际已实现的纸页行数/样式容量')
            if 'highlight' in i:
                bounds=i['highlight'];require(isinstance(bounds,list) and len(bounds)==2 and all(type(v)is int for v in bounds) and 0<=bounds[0]<bounds[1]<=len(i['label']),'高亮起止须指向实际标签文字')
        for ev in scene['events']:
            require(ev['id'] not in event_ids and type(ev['at'])is int and type(ev['duration'])is int and scene['from']<=ev['at']<ev['at']+ev['duration']<=scene['to'],'内部动作须有独立合法窗口');event_ids.add(ev['id'])
            require(not ev.get('target') or ev['target'] in ids,'事件引用未知对象')
            allowed={'camera','camera-return','write','highlight','draw','annotation','connection','overview','conclusion','revision','return'} if e['template_id']==PAPER else {'heading','item','answer','connection','tab','note','diagram','inspect','condition-opposition','condition-plane','condition-overlap'}
            require(ev['kind'] in allowed,'未知内部事件不能只登记而不消费')
        keys={(v['kind'],v.get('target')) for v in scene['events']};require(len(keys)==len(scene['events']),'同一真实控件不能有歧义事件')
        if e['template_id']==PAPER:
            require(1<=len(scene.get('conclusion',[]))<=2,'纸页便签结论必须在实际两行容量内')
            for identity in ids:
                require(all((kind,identity) in keys for kind in ('camera','write','highlight','draw','annotation')),'每个纸页对象须独立绑定镜头/书写/荧光/绘图/注解')
            require(('overview',None) in keys and ('conclusion',None) in keys,'缺少整页回看/结论阅读事件')
            if family=='sketchnote.sticky-revision':require(scene.get('revision',{}).get('targetId') in ids and ('revision',None) in keys,'修订便签须指向原对象')
            if family=='sketchnote.return-loop':require(scene.get('return',{}).get('fromId') in ids and scene.get('return',{}).get('toId') in ids and ('return',None) in keys,'回看必须有明确起止对象')
        else:
            require(('heading',None) in keys,'粉笔章标题须绑定独立书写')
            if family in SCIENCE:
                validate_model(family,scene.get('model'));require(len(scene['items'])==1 and set(scene['items'][0])=={'id','label'},'科学图示只开放确实消费的同一对象ID/标签')
                required={'heading'}|({'inspect'} if family=='chalkboard.shadow-overlap' else {'diagram'})
                if family=='chalkboard.surface-view':required|={'inspect'}
                if family=='chalkboard.condition-proof':required|={'condition-opposition','condition-plane','condition-overlap'}
                require(all((kind,None) in keys for kind in required) and {kind for kind,target in keys}==required,'科学家族须有精确独立视图/条件事件，不能只登记不消费')
            else:
                require('model' not in scene,'通用B6论证不得假装科学模型')
                used={'heading','item'}|({'answer'} if family=='compare' else {'connection'} if family=='process' else {'tab','note'})
                require({kind for kind,target in keys}<=used,'通用图示含未消费的科学/其他家族事件')
                if scene.get('note'):require(('note',None) in keys,'实际说明文字必须有独立note事件')
                for identity in ids:require(('item',identity) in keys,'每个论证对象须绑定实际书写事件')
                if family=='compare':require(all(('answer',i) in keys for i in ids),'对照后状态须独立定时')
                if family=='process':require(('connection',None) in keys and len(ids)==3,'流程必须三个明确对象及关系事件')
                if family in {'evidence','recap','definition'}:require(all(('tab',i) in keys for i in ids),'章栏须与正文分别定时')
    require(cursor==e['durationFrames'],'场景未覆盖完整音轨')
    from PIL import ImageFont
    kai=lambda size:ImageFont.truetype(str(TEMPLATE/'public/fonts/LXGWWenKai-Medium.ttf'),size)
    require(kai(42).getlength(e['title'])<=940,'总标题超出原字号宽度，不缩字回退')
    for s in e['scenes']:
        for i in s['items']:
            require(kai(67 if e['template_id']==PAPER else 29).getlength(i['label'])<=(550 if e['template_id']==PAPER else 450),'实际字体标签宽度超出画面')
            require(all(kai(43).getlength(v)<=660 for v in i.get('notes',[])),'实际注解字体宽度超出画面')
        require(all(kai(48).getlength(v)<=760 for v in s.get('conclusion',[])),'便签结论需按完整文字分行，不自动缩字号')
    if not e.get('previewOnly'):
        last=e['scenes'][-1];pieces=list(last.get('conclusion',[]))
        for i in last['items']:pieces.extend(i.get('notes',[]));pieces.append(i.get('text',''))
        pieces.append(last.get('note',''));visible=canonical(''.join(pieces))
        require(all(canonical(clause) in visible for clause in ('AI体质检测','非医疗诊断','不看病不卖药','给您个参考')),'末段实际note/conclusion必须完整保留全部医疗边界，不能靠隐藏字段宣称出现')
    return e
def validate(data):
    data=Path(data).resolve();require(data.is_relative_to(ROOT/'.local'),'本期输入应在私有.local中，公共源码只含实现与OFL字体')
    manifest=read(data/'preparation.json');require(manifest.get('schema')=='haike.knowledge-reference-public-preparation/2','缺少独立来源准备合同')
    public=data/'public';files={}
    for row in manifest['files']:
        p=(public/row['path']).resolve();require(p.is_relative_to(public) and p.is_file() and sha(p)==row['sha256'],'输入资源身份变化')
        require(row['path'] not in files and p.suffix.lower() in {'.json','.wav','.ttf','.txt'},'不接受重复资源、原截图、私有图包或旧影片作为可替换主画面');files[row['path']]=p
    for font in FONT_FILES:require(sha(files['fonts/'+font])==sha(TEMPLATE/'public/fonts'/font),'真实字体不匹配，不静默回退')
    e=validate_episode(read(public/'episode.json'))
    if manifest.get('development_fixture') is True:
        require(e.get('previewOnly') is True and not e['narration'] and not e.get('music'),'机制开发示意必须静音且不可完整生产')
        require(manifest.get('evidence_scope')=='Independently authored geometry fixture; no corresponding narration/ASR or original-performance claim' and manifest.get('new_paid_calls')==0,'示意不能伪称实测声源或原演出')
        return e,manifest
    params=read(manifest['original_parameters']['path']);require(sha(manifest['original_parameters']['path'])==manifest['original_parameters']['sha256'],'原声稿/ASR准备身份变化')
    require(e['sourceText']==params['script'],'原批准全文未完整保留')
    expected=[{'text':c['text'],'startMs':round(c['start']*1000),'endMs':round(c['end']*1000),'timestampMs':None,'confidence':None} for c in params['captions']]
    require(e['captions']==expected,'字幕不能猜时码或删除原句')
    evidence=manifest['sentence_evidence'];require(sha(evidence['path'])==evidence['sha256']==params['sentenceEvidence']['sha256'],'实际句证据摘要不符')
    require(sha(files[e['narration']])==params['sentenceEvidence']['audioSha256'],'完整原声与ASR不对应')
    with wave.open(str(files[e['narration']]),'rb') as a:
        duration=a.getnframes()/a.getframerate();require(0<=e['durationFrames']/60-duration<1/60+.001,'声音被裁切或多加静音')
    require(manifest.get('new_paid_calls')==0,'本入口只复用已有B6原声/ASR，不购买服务')
    return e,manifest
def resolved_events(e):
    return [{'scene':s['id'],'action_id':'haike.public-knowledge-v2.'+s['family'],'object_id':v.get('target'),'id':v['id'],'kind':v['kind'],'from':v['at'],'to':v['at']+v['duration']} for s in e['scenes'] for v in s['events']]
def prepare(template,request,*,workspace=ROOT):
    require(Path(workspace).resolve()==ROOT,'工作区不符');require(isinstance(request,dict) and set(request)=={'data'},'独立知识入口只接受本期冻结data')
    e,_=validate(request['data']);require(template['template_id']==e['template_id'] and template['version']==VERSION,'原包与独立实现身份不得混称')
    require(template.get('gallery_id',GALLERY_IDS[e['template_id']])==GALLERY_IDS[e['template_id']],'知识模板必须继承既有前端卡片ID，不能以模板ID代替')
    return {'status':'prepared','submitted':False,'blockers':[],'implementation':'knowledge-reference-public-v2','gallery_id':GALLERY_IDS[e['template_id']],'source_identity':source_identity(),'internal_events':resolved_events(e),
      'consumer':{'entrypoint':'backlot.motion_knowledge_public_production_v2:prepare','input':request,'requires_existing_queue':True,'category':'knowledge-reference-public'},
      'production_contract':'haike.knowledge-reference-public/2','queue_admission':{'entrypoint':'Haike_video/scripts/motion_replay_production.py','first_phase':'preview','render_requires':'Explicit approve decision, original completed preview and every PNG; binding frozen before admission'},
      'invocation':{'transport':'project_python','entrypoint':'backlot.motion_knowledge_public_production_v2:prepare','input':request,'context':{'workspace':str(ROOT)}},
      'validation_scope':'source/input/font/semantic structure only; actual frame fidelity and original package redistribution are separate'}
