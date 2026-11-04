"""Compile duration, ASR cues and section clocks once; the player consumes this plan."""
import json
import math
import unicodedata
from pathlib import Path
from story_plan import story_policy,validate_story,schedule_story

HERE=Path(__file__).resolve().parent


def units(text):
    return sum(1 if unicodedata.east_asian_width(c) in 'WF' else .5 for c in text)


def require(condition,message):
    if not condition:
        raise ValueError(message)


def frames(seconds,fps=30):
    require(type(seconds) in (int,float) and math.isfinite(seconds) and seconds>=0,'时间应为非负有限秒数')
    return math.ceil(seconds*fps-1e-7)


def wrap_caption(text,limit=20):
    require(isinstance(text,str) and text.strip() and units(text)<=limit*2,'字幕最多两行，每行20个全角单位；请用真实ASR分句重新整理长句')
    result=[];line=''
    for char in text:
        if char=='\n':
            require(bool(line.strip()),'字幕存在空行');result.append(line);line='';continue
        if units(line+char)>limit:
            result.append(line);line=''
        line+=char
    if line:result.append(line)
    require(1<=len(result)<=2,'字幕最多两行')
    return result


def schedule_motions(beats,book):
    """Freeze each variant's choices. Seeking never changes the authored schedule."""
    policy=book['motionPolicy']
    for recipe in book['recipes']:
        pools=recipe['motion'];history=[];counts=dict.fromkeys(pools['media'],0)
        for beat in beats:
            intent=beat['intent'];preferred=policy['intents'][intent]
            eligible=[m for m in pools['media'] if m not in history[-policy['cooldown']:]]
            media=recipe['mediaEffect'] if not history else min(eligible,key=lambda m:(counts[m],preferred.index(m),pools['media'].index(m)))
            chapter=beat['chapter']
            beat.setdefault('motions',{})[recipe['id']]={
                'mediaEffect':media,
                'headlineEffect':pools['headline'][chapter%len(pools['headline'])],
                'conclusionEffect':pools['conclusion'][chapter%len(pools['conclusion'])],
            }
            history.append(media);counts[media]+=1


def compile_timeline(data,total_frames,book=None):
    book=book or json.loads((HERE/'recipes.json').read_text('utf-8'))
    policy=book['timeline'];fps=book['canvas']['fps']
    require(type(total_frames) is int and policy['minFrames']<=total_frames<=policy['maxFrames'],'本版支持3秒至60分钟；时长必须由音轨或显式时长确定')
    require(data.get('schema')=='haike.chromatic-avatar-episode/2','不支持的内容版本')
    require(data.get('mode') in {'visual-preview','narrated-preview'},'仅支持visual-preview或narrated-preview')
    allowed={'schema','mode','durationSeconds','audio','audioStart','captionSource','presenter','presenterStart','presenterCrop','presenterClips','presenterName','font','photos','headline','kicker','captions','chapters','presentation'}
    require(not(set(data)-allowed),'输入含不支持的字段')
    require(data.get('presentation','legacy') in {'legacy','bookends'},'presentation仅支持legacy或bookends')
    story=data.get('presentation')=='bookends'
    if story:policy={**policy,'segmentFrames':story_policy(total_frames,fps)['targetFrames'],'maxSegmentFrames':story_policy(total_frames,fps)['maxFrames']}
    if data['mode']=='narrated-preview':
        require(bool(data.get('audio')) and data.get('captionSource')=='asr','有声预览需要本期原音轨及captionSource=asr的真实时间字幕')
    else:
        require(not data.get('audio'),'静音布局预览不接音轨，请使用narrated-preview')
        require(not data.get('audioStart'),'静音布局预览不接受audioStart')
    require(data.get('captionSource','illustrative') in {'asr','illustrative'},'captionSource仅支持asr或illustrative')
    for key in ['font','presenterName']:
        require(isinstance(data.get(key),str) and data[key].strip(),key+'必填')
    require('\n' not in data['presenterName'] and units(data['presenterName'])<=book['slots']['presenterName']['units'],'人物名字超长或含换行')
    photos=data.get('photos')
    require(isinstance(photos,list) and 3<=len(photos)<=200 and all(isinstance(p,str) and p.strip() for p in photos),'照片需3至200张本地图片')
    def text_fields(item):
        if 'headline' in item:
            lines=item['headline'].split('\n') if isinstance(item['headline'],str) else []
            require(1<=len(lines)<=2 and all(x.strip() and units(x)<=book['slots']['headline']['unitsPerLine'] for x in lines),'标题最多两行，每行7个全角单位')
        for key,limit in [('kicker',18),('conclusion',16)]:
            if key in item:require(isinstance(item[key],str) and item[key].strip() and '\n' not in item[key] and units(item[key])<=limit,key+'过长/为空/含换行')
    text_fields(data)
    cues=[];last_end=0
    require(isinstance(data.get('captions'),list) and bool(data['captions']),'请提供JSON字幕；静音版也需要明确示意字幕')
    for cue in data['captions']:
        require(isinstance(cue,dict) and all(k in cue for k in ['text','startMs','endMs']),'v2字幕使用Caption JSON的text/startMs/endMs字段')
        require(type(cue['startMs']) in (int,float) and type(cue['endMs']) in (int,float),'字幕毫秒时间必须为数字')
        start,end=frames(cue['startMs']/1000,fps),frames(cue['endMs']/1000,fps)
        require(start>=last_end and start<end<=total_frames,'字幕重叠、倒序、越界或短于一帧；不自动改变真实时间')
        cues.append({'from':start,'to':end,'text':cue['text'],'lines':wrap_caption(cue['text'])})
        last_end=end
    supplied=data.get('chapters')
    sections=[]
    if supplied is not None:
        require(isinstance(supplied,list) and bool(supplied),'chapters不可为空数组')
        end=0
        for chapter in supplied:
            require(isinstance(chapter,dict) and not(set(chapter)-{'from','to','headline','kicker','conclusion','photos','intent','role','composition','labels'}),'章节含不支持的字段')
            start,stop=chapter.get('from'),chapter.get('to')
            require(type(start) is int and type(stop) is int and start==end and stop-start>=policy['minSegmentFrames'] and stop<=total_frames,'章节需连续覆盖全片，每章至少3秒')
            text_fields(chapter)
            require(isinstance(chapter.get('intent','explain'),str) and chapter.get('intent','explain') in book['motionPolicy']['intents'],'章节intent须为hook/explain/compare/detail/recap/cta')
            selected=chapter.get('photos',list(range(len(photos))))
            require(isinstance(selected,list) and len(selected)>=3 and all(type(n) is int and 0<=n<len(photos) for n in selected),'章节photos为至少三个有效的零基照片索引')
            sections.append({**chapter,'photos':selected});end=stop
        require(end==total_frames,'章节未完整覆盖全片')
    else:
        sections=[{'from':0,'to':total_frames,'photos':list(range(len(photos)))}]
    if story:validate_story(sections,total_frames,book,require)
    else:require(all(not(set(c)&{'role','composition','labels'}) for c in sections),'role/composition/labels仅用于bookends模式')
    # Split long chapters into content beats, favouring actual cue boundaries.
    beats=[]
    for chapter_index,chapter in enumerate(sections):
        start=chapter['from'];chapter_end=chapter['to']
        while start<chapter_end:
            remaining=chapter_end-start
            if story and chapter['role']!='material' or remaining<=policy['maxSegmentFrames']:stop=chapter_end
            else:
                target=start+policy['segmentFrames']
                candidates=[c['to'] for c in cues if start+policy['minSegmentFrames']<=c['to']<=min(start+policy['maxSegmentFrames'],chapter_end-policy['minSegmentFrames'])]
                stop=min(candidates,key=lambda n:(abs(n-target),n)) if candidates else target
                if chapter_end-stop<policy['minSegmentFrames']:stop=chapter_end
            order=chapter['photos'];offset=len(beats)%len(order)
            intent=chapter.get('intent') or ('hook' if not beats else 'recap' if stop==total_frames else 'explain')
            beats.append({**chapter,'from':start,'to':stop,'chapter':chapter_index,'chapterFrom':chapter['from'],'chapterTo':chapter_end,'photos':order[offset:]+order[:offset],'intent':intent})
            start=stop
    if story:
        extra=schedule_story(beats,book,total_frames,require)
        revision=book['storyPolicy']['revision'];conclusion=extra['presenterWindows'][-1]['from']
    else:
        schedule_motions(beats,book);extra={};revision=book['motionPolicy']['revision'];conclusion=max(0,total_frames-min(policy['conclusionFrames'],max(60,total_frames//3)))
    return {'durationInFrames':total_frames,'fps':fps,'captions':cues,'segments':beats,'chapterCount':len(sections),'motionScheduleRevision':revision,'conclusionFrom':conclusion,**extra}
