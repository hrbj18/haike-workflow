"""Evidence-bound spatial understanding and stable per-shot presenter placement.

Native directors interpret prepared source frames; the deterministic planner
chooses geometry. Missing understanding is explicit and hides the presenter.
"""
from __future__ import annotations

import math
from pathlib import Path

from backlot import commentary_evidence as evidence, commentary_library_bridge as bridge
from backlot.commentary_common import (
    CommentaryError, crop_filter, crop_value, digest, file_sha256, identifier,
    immutable, media_tools, number, probe, read_json, run, text, verified,
)

KINDS = {'person', 'action', 'subject', 'source_subtitle'}


def directory(project, identity):
    identifier(identity, 'LT-' if str(identity).startswith('LT-') else 'LP-')
    return Path(project).resolve()/'artifacts/commentary/layout'/identity[:27]


def prepare(project, payload, *, db_path=None):
    item = evidence.confirmed(project, payload.get('evidence_id'), check_files=True, db_path=db_path)
    start = number(payload.get('start', item['start']), '布局区间起点', item['start'], item['end'])
    end = number(payload.get('end', item['end']), '布局区间终点', start+.01, item['end'])
    if end-start > 30:
        raise CommentaryError('单次空间判断最多30秒；长镜头请分区间判断，未覆盖区间会隐藏出镜')
    request = {'version': 1, 'evidence_id': item['id'], 'source_sha256': item['sha256'],
        'crop': item['crop'], 'start': start, 'end': end,
        'model': text(payload.get('model', 'codex-native'), '画面判断模型', 120),
        'revision': text(payload.get('revision', ''), '空间判断版本', 80, empty=True)}
    fingerprint = digest(request); identity = 'LT-'+fingerprint; folder = directory(project, identity)
    if (folder/'task.json').is_file():
        return read_task(project, identity)
    source = bridge.resolve_source(item['media_id'], item['sha256'], db_path=db_path)
    video = next(s for s in probe(source)['streams'] if s['codec_type'] == 'video')
    cw = math.floor(video['width']*item['crop']['w']/2)*2
    ch = math.floor(video['height']*item['crop']['h']/2)*2
    folder.mkdir(parents=True, exist_ok=True)
    count = max(2, math.ceil((end-start)*4)+1)
    frames = []
    from PIL import Image, ImageDraw
    sheets = []
    for i in range(count):
        stamp = min(end-.001, start+(end-start)*i/(count-1))
        path = folder/f'frame-{i:03d}.png'
        run([media_tools()[0], '-v', 'error', '-nostdin', '-y', '-ss', stamp, '-i', source,
            '-frames:v', '1', '-vf', crop_filter(item['crop'])+',scale=640:640:force_original_aspect_ratio=decrease', path])
        frames.append({'id': f'F{i:03d}', 'time': stamp, 'path': str(path), 'sha256': file_sha256(path)})
    for at in range(0, count, 9):
        sheet = Image.new('RGB', (720, math.ceil(min(9,count-at)/3)*380), '#111827')
        draw = ImageDraw.Draw(sheet)
        for n, frame in enumerate(frames[at:at+9]):
            with Image.open(frame['path']) as image:
                image.thumbnail((240,360))
                x, y = n%3*240, n//3*380
                sheet.paste(image,(x+(240-image.width)//2,y+(360-image.height)//2))
                draw.text((x+5,y+362), f"{frame['id']} {frame['time']:.3f}s", fill='white')
        path = folder/f'sheet-{at//9:02d}.jpg'; sheet.save(path,quality=93)
        sheets.append({'path': str(path), 'sha256': file_sha256(path)})
    task = {**request, 'id': identity, 'fingerprint': fingerprint, 'source_size': {'width': cw, 'height': ch},
        'coordinate_space': 'cropped_source', 'frames': frames, 'sheets': sheets,
        'instruction': '实际查看全部带时间码图像，依据事件保护相关人物脸部、关键动作/手、核心物体和原字幕。'
        '矩形坐标相对裁切后的源图像，不含多宫格边框或成片补边。覆盖整个区间中的移动范围，不能只看首帧；'
        '背景路人不一律保护。看不清或有未检查的镜头变化则 coverage=uncertain。源字幕只避让，不移动。'
        '用 regions[{kind,label,box:{x,y,w,h},start,end}] 表达区域与时间，空区域必须说明确实没有保护对象。'
        'cuts 只填已确认的实际换镜源时间，不能把人物移动当切镜；边界不确定则按连续镜头保守避让。',
        'submission_template': {'task_id': identity, 'task_fingerprint': fingerprint,
            'reviewed_frame_ids': [], 'coverage': 'uncertain', 'regions': [], 'cuts': [], 'rationale': ''}}
    immutable(folder/'task.json',task)
    return read_task(project,identity)


def read_task(project, identity):
    folder=directory(project,identity)
    task = read_json(folder/'task.json')
    if task['id'] != identity: raise CommentaryError('空间判断任务身份不匹配')
    request={k:task[k] for k in ('version','evidence_id','source_sha256','crop','start','end','model','revision')}
    if digest(request)!=task['fingerprint'] or 'LT-'+task['fingerprint']!=identity:
        raise CommentaryError('空间判断任务来源指纹已变化，请重新准备任务')
    for item in task['frames']+task['sheets']:
        # Task images belong to their immutable task directory, independent of
        # the CLI caller's working directory or an old relative-path envelope.
        item['path']=str(verified(folder/Path(item['path']).name,item['sha256']))
    return task


def submit_protection(project, payload):
    task = read_task(project,payload.get('task_id'))
    if payload.get('task_fingerprint') != task['fingerprint']:
        raise CommentaryError('空间判断指纹已变化，请重新读取任务')
    reviewed = payload.get('reviewed_frame_ids')
    if not isinstance(reviewed,list) or any(not isinstance(f,str) for f in reviewed) or set(reviewed) != {f['id'] for f in task['frames']}:
        raise CommentaryError('必须实际查看空间判断的全部帧；未检查区间不能写为已理解')
    coverage = payload.get('coverage')
    if coverage not in {'complete','uncertain'}: raise CommentaryError('空间判断须为 complete 或 uncertain')
    raw = payload.get('regions')
    if not isinstance(raw,list) or len(raw)>100: raise CommentaryError('保护区域须为不超过100项的列表')
    regions = []
    for region in raw:
        if not isinstance(region,dict) or region.get('kind') not in KINDS:
            raise CommentaryError('保护类型须为人物、动作、主体或原字幕')
        start = number(region.get('start',task['start']), '保护起点', task['start'],task['end'])
        end = number(region.get('end',task['end']), '保护终点', start+.001,task['end'])
        if not isinstance(region.get('box'),dict): raise CommentaryError('保护区域必须给出明确的矩形坐标')
        regions.append({'kind': region['kind'], 'label': text(region.get('label'),'保护内容',200),
            'box': crop_value(region.get('box')), 'start':start, 'end':end})
    record = {k: task[k] for k in ('evidence_id','source_sha256','crop','start','end','source_size','coordinate_space','model')}
    cuts=payload.get('cuts',[])
    if not isinstance(cuts,list) or len(cuts)>100: raise CommentaryError('切镜时间列表无效')
    cuts=sorted(set(number(c,'实际换镜时间',task['start']+.001,task['end']-.001) for c in cuts))
    record.update(task_id=task['id'],task_fingerprint=task['fingerprint'],reviewed_frame_ids=sorted(set(reviewed)),
        coverage=coverage,regions=regions,cuts=cuts,rationale=text(payload.get('rationale'),'空间判断依据',3000))
    identity = 'LP-'+digest(record); record['id']=identity
    immutable(directory(project,identity)/'protection.json',record)
    return read_protection(project,identity)


def read_protection(project, identity):
    value = read_json(directory(project,identity)/'protection.json')
    if value['id'] != identity: raise CommentaryError('保护区域身份不匹配')
    if 'LP-'+digest({k:v for k,v in value.items() if k!='id'}) != identity:
        raise CommentaryError('保护区域内容指纹已变化')
    return value


def list_protections(project):
    paths=(Path(project)/'artifacts/commentary/layout').glob('LP-*/protection.json')
    return [read_protection(project,read_json(p)['id']) for p in sorted(paths,key=lambda p:(p.stat().st_mtime_ns,str(p)))]


def apply(identity, payload, *, projects_root, db_path=None):
    from backlot import material_commentary as flow
    from backlot.commentary_common import project_dir, CommentaryConflict
    current=flow.read(identity,db_path=db_path)
    if type(payload.get('revision')) is not int or payload['revision']!=current['revision']:
        raise CommentaryConflict('草稿已变化，请保存最新版本再自动选位')
    project=project_dir(identity,projects_root); records=list_protections(project)
    for segment in current['payload']['segments']:
        if 'presenter' not in segment: continue
        selected=[]
        for shot in segment['shots']:
            matching=[r for r in records if r['evidence_id']==shot['evidence_id'] and min(r['end'],shot['end'])>max(r['start'],shot['start'])]
            full=[r for r in matching if r['start']<=shot['start']+.001 and r['end']>=shot['end']-.001]
            if full:
                latest=full[-1]
                matching=[latest]+[r for r in matching if records.index(r)>records.index(latest)]
            selected.extend(r['id'] for r in matching)
        segment['presenter_layout']={'mode':'auto','protection_ids':list(dict.fromkeys(selected)),
            'locks':segment.get('presenter_layout',{}).get('locks',[])}
    saved=flow.save(identity,current,projects_root=projects_root,db_path=db_path)
    frozen=flow.compile_timeline(project,saved['payload'],db_path=db_path)
    pending=[]
    for segment in frozen['segments']:
        if 'layout_plan' not in segment: continue
        for placed in segment['layout_plan']['shots']:
            if placed['protection_ids']: continue
            shot=segment['shots'][placed['shot_index']]
            start=shot['start']
            while start<shot['end']-.001:
                end=min(start+30,shot['end'])
                task=prepare(project,{'evidence_id':shot['evidence_id'],'start':start,'end':end,'model':'codex-native'},db_path=db_path)
                pending.append({'id':task['id'],'evidence_id':shot['evidence_id'],'start':start,'end':end,
                    'status':'awaiting_spatial_understanding','instruction':'素材空间判断尚未完成，当前会隐藏雅雅；原生制作助手读取帧并提交保护区域后再次自动选位'})
                start=end
    return {'draft':saved,'layouts':[{'segment_id':s['id'],**s['layout_plan']} for s in frozen['segments'] if 'layout_plan' in s],
        'warnings':frozen['warnings'],'pending_tasks':pending}


def normalize(project, payload, shots):
    if not isinstance(payload,dict) or set(payload)-{'mode','protection_ids','locks'} or payload.get('mode')!='auto':
        raise CommentaryError('自动选位配置须为 auto，包含保护记录和手动锁定')
    ids = payload.get('protection_ids',[])
    if not isinstance(ids,list) or len(ids)>100: raise CommentaryError('保护记录列表无效')
    for identity in ids: read_protection(project,identity)
    locks = payload.get('locks',[])
    if not isinstance(locks,list) or len(locks)>len(shots)*100: raise CommentaryError('镜头锁定列表无效')
    result=[]; indexes=set()
    for lock in locks:
        if not isinstance(lock,dict): raise CommentaryError('镜头锁定须为对象')
        index=lock.get('shot_index'); position=lock.get('position'); cut_index=lock.get('cut_index')
        if type(index) is not int or not 0<=index<len(shots) or (index,cut_index) in indexes or position not in {'left','right','hidden'} or (cut_index is not None and (type(cut_index) is not int or not 0<=cut_index<=100)):
            raise CommentaryError('锁定须选择有效镜头与左、右或隐藏')
        indexes.add((index,cut_index))
        result.append({'shot_index':index,'position':position,
            'shot_fingerprint':digest(shots[index])})
        if cut_index is not None: result[-1]['cut_index']=cut_index
        if lock.get('shot_fingerprint') and lock['shot_fingerprint']!=digest(shots[index]):
            raise CommentaryError('已锁定镜头的素材或区间发生变化，请解除锁定并重新检查')
    return {'mode':'auto','protection_ids':list(dict.fromkeys(ids)),'locks':result}


def _intersects(a,b):
    return a['x']<b['x']+b['w'] and a['x']+a['w']>b['x'] and a['y']<b['y']+b['h'] and a['y']+a['h']>b['y']


def _mapped(box, size, profile):
    ratio=min(profile['width']/size['width'],profile['height']/size['height'])
    w=math.floor(size['width']*ratio/2+1e-8)*2; h=math.floor(size['height']*ratio/2+1e-8)*2
    return {'x':(profile['width']-w)/2+box['x']*w-4,'y':(profile['height']-h)/2+box['y']*h-4,
        'w':box['w']*w+8,'h':box['h']*h+8}


def _caption_layout(segment, profile, protected, geometry, cues, font_path, style):
    from PIL import ImageFont
    from backlot import commentary_captions as captions
    size=style['font_size'] if style else (36 if profile['height']>=profile['width'] else 32)
    font=ImageFont.truetype(str(font_path),size)
    margin=(style['outline_size']+style['shadow']+2) if style else 4
    lengths=[font.getlength(captions.display_text(c['text'],style)) for c in cues]
    if not lengths: return segment.get('subtitle_layout',{'x':.5,'y':.18,'max_width':.84})
    initial=segment.get('subtitle_layout',{'x':.5,'y':.18 if segment['subtitle_position']=='top' else .75,'max_width':.84})
    candidates=[initial]+[{'x':x,'y':y,'max_width':.84} for y in (.18,.28,.34,.42,.50,.62,.74,.80) for x in (.5,.7,.3,.28,.72)]
    obstacles=[p['box'] for p in protected]
    if geometry: obstacles.append({'x':geometry['x'],'y':geometry['y'],'w':geometry['size'],'h':geometry['size']})
    for candidate in candidates:
        x=round(candidate['x']*profile['width']); y=round(candidate['y']*profile['height'])
        boxes=[{'x':x-length/2-margin,'y':y-size-margin,'w':length+margin*2,'h':size+margin*2} for length in lengths]
        if max(lengths)>profile['width']*candidate['max_width']: continue
        if any(b['x']<0 or b['y']<0 or b['x']+b['w']>profile['width'] or b['y']+b['h']>profile['height'] for b in boxes): continue
        if any(_intersects(b,o) for b in boxes for o in obstacles): continue
        return candidate
    return None


def compile_layout(project, segment, profile, font_path, style=None):
    config=segment['presenter_layout']; size=segment['presenter']['geometry']['size']
    y=round(segment['presenter']['y']*profile['height']); cursor=0; output=[]
    records=[read_protection(project,p) for p in config['protection_ids']]
    windows=[]
    for index,shot in enumerate(segment['shots']):
        cuts={round((cut-shot['start'])*30) for record in records if record['evidence_id']==shot['evidence_id'] and record['coverage']=='complete'
            for cut in record.get('cuts',[]) if shot['start']<cut<shot['end']}
        boundaries=[0]+sorted(c for c in cuts if 0<c<shot['frames'])+[shot['frames']]
        for cut_index,(a,b) in enumerate(zip(boundaries,boundaries[1:])):
            windows.append((index,cut_index,{**shot,'start':shot['start']+a/30,'end':shot['start']+b/30,'frames':b-a}))
    for lock in config['locks']:
        if 'cut_index' in lock and not any(i==lock['shot_index'] and c==lock['cut_index'] for i,c,_ in windows):
            raise CommentaryError('锁定的换镜区间已不存在，请解除锁定并重新检查')
    grouped=[]; frame_cursor=0
    for index,cut_index,shot in windows:
        previous=grouped[-1][2] if grouped else None
        cut_at_start=any(abs(c-shot['start'])<=.5/30+.000001 for r in records
            if r['coverage']=='complete' and r['evidence_id'] in {shot['evidence_id'],previous['evidence_id'] if previous else None}
            for c in r.get('cuts',[]))
        continuous=previous and previous['media_id']==shot['media_id'] and previous['crop']==shot['crop'] and abs(previous['end']-shot['start'])<=.001 and not cut_at_start
        if continuous:
            group=grouped[-1][3]; group['end']=shot['end']; group['end_frame']+=shot['frames']
            group['evidence_ids'].add(shot['evidence_id']); group['windows'].append((index,cut_index))
        else:
            group={'start':shot['start'],'end':shot['end'],'start_frame':frame_cursor,
                'end_frame':frame_cursor+shot['frames'],'evidence_ids':{shot['evidence_id']},'windows':[(index,cut_index)]}
        grouped.append((index,cut_index,shot,group)); frame_cursor+=shot['frames']
    for index,cut_index,shot,group in grouped:
        selected=[p for p in records if p['evidence_id'] in group['evidence_ids']]
        reliable=bool(selected)
        covered=group['start']
        for record in sorted(selected,key=lambda r:r['start']):
            ev=evidence.read(project,record['evidence_id'])
            if record['source_sha256']!=ev['sha256'] or record['crop']!=shot['crop']:
                raise CommentaryError('保护区域与当前镜头来源或裁切不匹配')
            if record['end']<=group['start'] or record['start']>=group['end']: continue
            if record['start']>covered+.001 or record['coverage']!='complete': reliable=False
            covered=max(covered,record['end'])
        reliable=reliable and covered>=group['end']-.001
        protected=[]
        for record in selected:
            for region in record['regions']:
                if min(region['end'],group['end'])>max(region['start'],group['start']):
                    protected.append({**region,'box':_mapped(region['box'],record['source_size'],profile)})
        choices={p:{'x':round((.03 if p=='left' else .97-size/profile['width'])*profile['width']), 'y':y,'size':size} for p in ('left','right')}
        safe={p:not any(_intersects({'x':b['x'],'y':b['y'],'w':size,'h':size},r['box']) for r in protected) for p,b in choices.items()}
        lock=next((p for p in config['locks'] if p['shot_index']==index and p.get('cut_index')==cut_index),
            next((p for p in config['locks'] if p['shot_index']==index and 'cut_index' not in p),None))
        group_locks=[p for p in config['locks'] if any(p['shot_index']==i and ('cut_index' not in p or p['cut_index']==c) for i,c in group['windows'])]
        propagated=not lock and bool(group_locks)
        if propagated: lock=group_locks[0]
        reasons=[]; warnings=[]
        if len({p['position'] for p in group_locks})>1:
            warnings.append('同一连续镜头存在不同手动锁定，可能切换位置，请统一选择')
        if lock:
            position=lock['position']; reasons.append('沿用同一连续镜头的手动锁定位置' if propagated else '采用手动锁定位置')
            if position!='hidden' and (not reliable or not safe[position]): warnings.append('手动锁定存在遮挡或判断不确定，请人工检查')
        elif not reliable:
            position='hidden'; reasons.append('保护区域未完整覆盖实际出镜时段或判断不确定，隐藏雅雅并保留解说')
        else:
            position=next((p for p in ('right','left') if safe[p]),'hidden')
            reasons.append('左右均占用，隐藏雅雅并保留解说' if position=='hidden' else '完整镜头内保持安全位置')
        cues=[c for c in segment['cues'] if min(c['end'],group['end_frame']/30)>max(c['start'],group['start_frame']/30)]
        caption_layout=_caption_layout(segment,profile,protected,choices.get(position),cues,font_path,style)
        if not caption_layout and not lock and position!='hidden':
            for alternate in ('left','right'):
                if not reliable or not safe[alternate]: continue
                caption_layout=_caption_layout(segment,profile,protected,choices[alternate],cues,font_path,style)
                if caption_layout:
                    position=alternate; break
            if not caption_layout:
                position='hidden'; reasons.append('雅雅与大字幕无法共同安全放置，隐藏雅雅')
                caption_layout=_caption_layout(segment,profile,protected,None,cues,font_path,style)
        if not caption_layout:
            caption_layout=_caption_layout(segment,profile,[],choices.get(position),cues,font_path,style)
            warnings.append('新增字幕未找到完全避让重要区域的位置，待人工检查；未缩小字号')
        if not caption_layout:
            raise CommentaryError('字幕长度无法在当前画幅保持字号，请按真实语音拆短字幕')
        if position=='hidden':
            warnings.append('雅雅已隐藏，解说保留：'+('判断不确定或时段未覆盖' if not reliable else '两侧或联合字幕布局不安全'))
        reasons.extend('保护：'+r['label'] for r in protected)
        output.append({'shot_index':index,'cut_index':cut_index,'start_frame':cursor,'end_frame':cursor+shot['frames'],
            'position':position,'geometry':choices.get(position), 'protected_regions':protected,
            'subtitle_layout':caption_layout,
            'protection_ids':[p['id'] for p in selected],'reasons':reasons,'warnings':warnings,'locked':bool(lock)})
        cursor+=shot['frames']
    render_cues=[]
    for placement in output:
        for cue in segment['cues']:
            start=max(cue['start'],placement['start_frame']/30); end=min(cue['end'],placement['end_frame']/30)
            if end>start:
                render_cues.append({**cue,'start':start,'end':end,'subtitle_layout':placement['subtitle_layout'],
                    'presenter_geometry':placement['geometry']})
    segment['render_cues']=render_cues
    return {'version':1,'shots':output}
