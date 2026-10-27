"""Plain-value adapters for all nine upstream TPL components (landscape only).

This is lightweight composition, not a claim of full-pack motion preservation.
Every displayed content/time is supplied by the creator. No JavaScript from HTTP.
"""
import json
import html
import shutil
import sys
from pathlib import Path

from backlot.work_catalog import WorkError


def text(id, label, size=60, required=True, item_chars=None):
    value = {"id":id,"label":label,"type":"text","maxChars":size,"required":required}
    if item_chars: value['itemChars'] = item_chars
    return value


DEFINITIONS = {
    "hero": ([text("line1","标题第一行",14),text("line2","标题第二行",14),text("sub","补充说明",40,False)], ["line1","line2"]),
    "point": ([text("word1","主张",12),text("word2","强调语",12),text("cards","要点（每行一项）",100,item_chars=14)], ["word1","word2","card1","card2","card3","card4"]),
    "number": ([text("label","数字含义",24),{"id":"value","label":"实际数值","type":"number","required":True},{"id":"from","label":"计数起点","type":"number","required":False},text("unit","单位",12),text("sub","数字依据或说明",64)], ["number"]),
    "compare": ([text("leftTitle","左侧标题",10),text("rightTitle","右侧标题",10),text("leftItems","左侧内容（每行一项）",100,item_chars=14),text("rightItems","右侧内容（每行一项）",100,item_chars=14),text("stamp","结论标签",12)], ["left","right","strike"]),
    "steps": ([text("title","流程标题",16),text("steps","步骤（每行一项）",120,item_chars=16)], ["step1","step2","step3","step4","step5"]),
    "quote": ([text("lines","结论（每行一句）",100,item_chars=28),text("by","作者或来源",30,False)], ["quote"]),
    "demo": ([text("title","产品名称",16),text("features","演示要点（每行一项）",100,item_chars=14),{"id":"image","label":"本期产品图片","type":"image","required":True}], ["feature1","feature2","feature3","feature4"]),
    "checklist": ([text("title","清单标题",16),text("items","清单（每行一项）",140,item_chars=16)], ["item1","item2","item3","item4","item5"]),
    "outro": ([text("title","片尾标题",14),text("lines","片尾文字（每行一句）",120,item_chars=20),text("prompt","行动邀请",40)], []),
}


def groups(names):
    return [{"id":"quick:"+id,"style":"quick","selection":"TPL."+id,"status":"quick-start","intents":["creator-lightweight-composition"],"phases":["entry","reading"],"counts":{},
             "cueRoles":{x:x for x in DEFINITIONS[id][1]},"entry":{"mode":"independent"},"exit":{},"effects":["TPL."+id],
             "duration":{"minFrames":180,"sourceSeconds":3,"maxHoldFrames":1500,"followingFrames":0},"layouts":["landscape"],
             "fields":DEFINITIONS[id][0],"label":title} for id,title in names]


def lines(value, maximum, label, minimum=1):
    result = [s.strip() for s in str(value or "").split("\n") if s.strip()]
    if not minimum <= len(result) <= maximum: raise WorkError(f"{label}需要{minimum}至{maximum}项，每行一项")
    return result


def options(scene, start, end):
    kind=scene['group'].split(':')[1]; fields,roles=DEFINITIONS[kind]; v=scene['slots']; anchors=scene['anchors']
    for f in fields:
        if f.get('required',True) and f['id'] not in v: raise WorkError("轻量动画缺少"+f['label'])
        if f['type']=='text' and f['id'] in v and len(v[f['id']])>f['maxChars']: raise WorkError(f['label']+"超过文字容量")
        if f.get('itemChars') and any(len(line.strip())>f['itemChars'] for line in v.get(f['id'],'').split('\n')):
            raise WorkError(f"{f['label']}每行最多{f['itemChars']}字，请缩短画面文案，口播原文保持完整")
    # Upstream TPL draws some text with innerHTML. HTTP accepts plain text only.
    v={key:html.escape(value,quote=True) if isinstance(value,str) and not (kind=='outro' and key=='prompt') else value for key,value in v.items()}
    def at(role):
        if role not in anchors: raise WorkError("请标注本段实际动作落点："+role)
        value=start+anchors[role]['at']
        if value>end-.35: raise WorkError("动作落点太接近段尾，请留出入场与阅读时间")
        return value
    o={'t0':start,'t1':end,'tag':'海客科技'}
    if end-start<3: raise WorkError('轻量动画每个分镜至少3秒')
    if kind=='hero': o.update(lines=[[v['line1'],at('line1')],[v['line2'],at('line2')]],sub=v.get('sub',''))
    elif kind=='point':
        cards=lines(v['cards'],4,'要点');o.update(words=[[v['word1'],at('word1')],[v['word2'],at('word2'),'slam']],cards=[[x,at('card'+str(i+1))] for i,x in enumerate(cards)])
    elif kind=='number': o.update(label=v['label'],at=at('number'),value=v['value'],unit=v['unit'],sub=v['sub'],**{'from':v.get('from',0)})
    elif kind=='compare': o.update(left={'title':v['leftTitle'],'items':lines(v['leftItems'],4,'左侧内容')},right={'title':v['rightTitle'],'items':lines(v['rightItems'],4,'右侧内容')},leftAt=at('left'),rightAt=at('right'),strikeAt=at('strike'),stamp=v['stamp'])
    elif kind=='steps': o.update(title=v['title'],steps=[[x,at('step'+str(i+1))] for i,x in enumerate(lines(v['steps'],5,'步骤',2))])
    elif kind=='quote': o.update(at=at('quote'),lines=lines(v['lines'],4,'结论'),by=v.get('by',''),cam='none')
    elif kind=='demo': o.update(title=v['title'],features=[[x,at('feature'+str(i+1))] for i,x in enumerate(lines(v['features'],4,'演示要点'))],image=v['image']['path'])
    elif kind=='checklist': o.update(title=v['title'],items=[[x,at('item'+str(i+1))] for i,x in enumerate(lines(v['items'],5,'清单'))])
    elif kind=='outro': o.update(title=v['title'],lines=lines(v['lines'],5,'片尾文字'),prompt=v['prompt'])
    return {'kind':kind,'options':o}


def build(saved, video, engineering, subtitles, command, runtime):
    command('new',engineering)
    # The starter carries an optional-data comment different from import's stub.
    # Clear only freshly created data files, never an existing user engineering.
    (engineering/'talkmap.js').write_text('// Optional data absent. Generated data may replace this stub.\n',encoding='utf-8')
    command('import',engineering,video,timeout=600)
    report=saved['report']; duration=report['durationFrames']/60
    config={'brand':'海客科技','account':'海客科技','demo':False,'fps':60,'width':1920,'height':1080,'end':duration,'talkFrames':0,'subtitles':True,
            'subtitlePreset':'standard','subtitlePosition':saved['brief']['subtitlePosition'],'subtitleStyle':{},'race':{'labels':['口播'],'keys':[0,duration]}}
    (engineering/'config.js').write_text('window.CONFIG='+json.dumps(config,ensure_ascii=False)+';\n',encoding='utf-8')
    compiled=[]
    for i,scene in enumerate(saved['quickScenes']):
        scene=json.loads(json.dumps(scene))
        if scene['kind']=='demo':
            src=Path(scene['options']['image']);dest=engineering/'assets'/('demo-'+str(i)+src.suffix);shutil.copy2(src,dest);scene['options']['image']=dest.relative_to(engineering).as_posix()
        compiled.append('TPL.'+scene['kind']+'('+json.dumps(scene['options'],ensure_ascii=False)+');')
    (engineering/'scenes.js').write_text('window.END=CONFIG.end;\n'+'\n'.join(compiled),encoding='utf-8')
    shutil.copy2(subtitles,engineering/'subs.js')
    music=dict(saved['brief']['music'])
    if music['mode']=='track':
        src=Path(music['path']);target=engineering/'assets'/('music'+src.suffix);shutil.copy2(src,target);music['path']=target.relative_to(engineering).as_posix()
    # Freeze the same upstream sound recipe as complete projects, with a real score.
    root=runtime();sys.path.insert(0,str(root/'scripts'))
    from build_macro_project import write_project_audio, prepare_face
    prepare_face(engineering,saved['brief'],True,60,report['durationFrames'])
    write_project_audio(engineering,music)
    (engineering/'macro_plan.json').write_text(json.dumps({'fps':60,'end_frame':report['durationFrames'],'width':1920,'height':1080,'audio':{'sfxMixSource':'runtime-scene-S-only','mixProfile':'legacy-macro'},'scenes':[]}),encoding='utf-8')
