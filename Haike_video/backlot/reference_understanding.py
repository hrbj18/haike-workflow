"""Reference evidence: measured pictures + speech, persistent objects and events.

The agent supplies interpretations after viewing. This module records evidence,
validates its identity and produces a reconstruction brief; it does not call AI,
transcribe, certify continuous playback or bypass the production queue.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

from PIL import Image, ImageDraw, ImageFont, ImageOps

from backlot.media_index import probe_media

CONTRACT = 'haike-reference-understanding-v1'
MAX_FRAMES = 2400


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    from backlot.studio import atomic_private
    atomic_private(path, value)


def require(value, message):
    if not value:
        raise ValueError(message)


def number(value):
    return type(value) in {float, int} and math.isfinite(value)


def transcript(raw, source_sha, duration):
    """Only admit the clock of this source, never estimated wording durations."""
    if raw is None:
        return []
    require(raw.get('source_sha256') == source_sha, '转录必须绑定同一原视频SHA，不能混用另一音轨时间轴')
    require(raw.get('clock') == 'measured-seconds', '转录须声明真实秒时钟')
    rows, end, identifiers = [], 0., set()
    require(isinstance(raw.get('segments'), list) and raw['segments'], '转录缺少实测句子')
    for index, row in enumerate(raw['segments']):
        a, b, text = row.get('start'), row.get('end'), row.get('text')
        require(number(a) and number(b) and end <= a < b <= duration+.001
                and isinstance(text, str) and text.strip(), '句时间或文案无效；不估算时间')
        identity = row.get('id', f'sentence-{index+1}')
        require(isinstance(identity, str) and identity and identity not in identifiers, '句ID重复或为空')
        identifiers.add(identity)
        words, previous = [], a
        for j, word in enumerate(row.get('words', [])):
            x, y, t = word.get('start'), word.get('end'), word.get('text')
            require(number(x) and number(y) and previous <= x < y <= b+.001
                    and isinstance(t, str) and t.strip(), '词时间或文案无效；句时间不均摊成词时间')
            words.append({'id': f'{identity}:w{j+1}', 'start': x, 'end': y, 'text': t})
            previous = y
        rows.append({'id': identity, 'start': a, 'end': b, 'text': text, 'words': words})
        end = b
    return rows


def context_at(rows, at):
    active = [r for r in rows if r['start'] <= at < r['end']]
    return {'sentence_ids': [r['id'] for r in active],
            'text': ' '.join(r['text'] for r in active),
            'word_ids': [w['id'] for r in active for w in r.get('words',[]) if w['start'] <= at < w['end']]}


def ranges(values, duration, every_frame=False):
    require(number(duration) and duration > 0, '参考视频时长无效')
    if not values:
        values = [f'0:{duration}:{max(duration/30, .1)}']
    result = []
    for value in values:
        parts = value.split(':')
        require(len(parts) in {2, 3}, '范围格式为开始秒:结束秒[:采样间隔秒]')
        a, b = map(float, parts[:2])
        step = None if every_frame else float(parts[2]) if len(parts) == 3 else .1
        require(number(a) and number(b) and 0 <= a < b <= duration+.001
                and (step is None or number(step) and step > 0), '取证区间或采样间隔无效')
        result.append({'start': a, 'end': min(b, duration), 'step': step})
    require(len(result) <= 40, '单次最多40个区间；按问题分批取证')
    return result


def _font(size):
    candidates = [Path('C:/Windows/Fonts/msyh.ttc'), Path('C:/Windows/Fonts/simhei.ttf'),
                  Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')]
    return next((ImageFont.truetype(str(p), size) for p in candidates if p.is_file()), ImageFont.load_default())


def _lines(text, maximum=31):
    return [text[i:i+maximum] for i in range(0, min(len(text), maximum*3), maximum)] or ['（此时无对应台词）']


def sheets(directory, frames, cell_width=480):
    require(240 <= cell_width <= 1280, '宫格单元宽度需为240–1280')
    with Image.open(frames[0]['path']) as first:
        picture_height = round(cell_width*first.height/first.width)
    height = picture_height+112
    font = _font(18)
    output = []
    for page in range(0, len(frames), 12):
        rows = frames[page:page+12]
        canvas = Image.new('RGB', (cell_width*4, height*3), '#eeeae1')
        draw = ImageDraw.Draw(canvas)
        for index, row in enumerate(rows):
            x, y = index % 4*cell_width, index//4*height
            with Image.open(row['path']) as im:
                fitted = ImageOps.contain(im.convert('RGB'), (cell_width-12, height-112))
                canvas.paste(fitted, (x+(cell_width-fitted.width)//2, y+28))
            draw.text((x+6, y+3), f"{row['id']}  {row['at']:.4f}s", font=font, fill='#15202b')
            for j, line in enumerate(_lines(row['speech']['text'], max(12, cell_width//19))):
                draw.text((x+6, y+height-76+j*22), line, font=font, fill='#15202b')
        target = directory / f'grid-{page//12+1:04d}.jpg'
        canvas.save(target, quality=93)
        output.append({'id': f'grid-{page//12+1:04d}', 'path': str(target.resolve()),
                       'sha256': sha(target), 'frame_ids': [r['id'] for r in rows]})
    return output


def prepare(source, output, *, ffmpeg, ffprobe, model, selected_ranges=None,
            every_frame=False, transcript_path=None, revision='1', cell_width=480):
    source = Path(source).resolve()
    require(source.is_file(), '参考视频不存在')
    info = probe_media(source, ffprobe)
    duration = float(info['format']['duration'])
    source_sha = sha(source)
    speech = transcript(read(transcript_path) if transcript_path else None, source_sha, duration)
    windows = ranges(selected_ranges, duration, every_frame)
    require(isinstance(model, str) and model.strip(), '填写实际分析模型标识')
    identity = {'contract': CONTRACT, 'source': {'path': str(source), 'sha256': source_sha,
                'duration': duration}, 'ranges': windows, 'speech': speech, 'model': model,
                'revision': str(revision), 'cell_width': cell_width,
                'grid_layout': 'source-aspect-v1', 'extraction': 'native-pts-bounded-v3'}
    identity_sha = digest(identity)
    directory = Path(output).resolve() / identity_sha[:24]
    task_path = directory/'task.json'
    if task_path.is_file():
        load(task_path)
        return {'task': str(task_path), 'template': str(directory/'submission-template.json'), 'reused': True}
    require(not directory.exists(), '上次取证尚未完成；保留现场，使用新的revision')
    directory.mkdir(parents=True)
    frames = []
    for index, window in enumerate(windows):
        target = directory/f'range-{index+1}'
        target.mkdir()
        a, b, step = window['start'], window['end'], window['step']
        select = f'gte(t,{max(0,a-1e-7):.9f})*lt(t,{b:.9f})'
        if step is not None:
            select += f'*(isnan(prev_selected_t)+gte(t-prev_selected_t,{step:.9f}))'
        remaining = MAX_FRAMES-len(frames)
        require(remaining > 0, '本次取证超过2400帧，请分批并缩小问题范围')
        # Seek slightly earlier so FFmpeg's microsecond seek rounding cannot
        # discard the frame exactly at a non-terminating rational boundary.
        seek = max(0,a-.05)
        command = [ffmpeg, '-hide_banner', '-nostdin', '-ss', str(seek), '-t', str(b-seek), '-copyts', '-i', str(source),
                   '-an', '-sn', '-vf', f"select='{select}',showinfo", '-fps_mode', 'vfr',
                   '-frames:v', str(remaining+1), str(target/'frame-%06d.png')]
        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                 timeout=max(120, (b-a)*5), creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        require(process.returncode == 0, '局部取证失败；原视频和已完成证据保留')
        pts = [float(v) for v in re.findall(r'\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:([\d.eE+-]+)', process.stderr)]
        files = sorted(target.glob('frame-*.png'))
        require(files and len(files) == len(pts) and len(files) <= remaining, '原生帧与PTS数量不符或超出预算')
        for file, at in zip(files, pts):
            require(a-.001 <= at < b+.001, '抽帧PTS越过请求区间')
            frames.append({'id': f'frame-{len(frames)+1:06d}', 'path': str(file.resolve()),
                           'sha256': sha(file), 'at': at, 'range': index,
                           'speech': context_at(speech, at)})
    grids = sheets(directory, frames, cell_width)
    task = {**identity, 'fingerprint': identity_sha, 'frames': frames, 'grids': grids,
            'evidence_sha256': digest({'frames': frames, 'grids': grids})}
    write(task_path, task)
    template = {'task_fingerprint': identity_sha, 'reviewed_grid_ids': [], 'whole_piece': '',
                'objects': [], 'events': [], 'unknowns': [], 'continuous_watch': 'pending',
                'continuous_listen': 'pending'}
    write(directory/'submission-template.json', template)
    return {'task': str(task_path), 'template': str(directory/'submission-template.json'),
            'frames': len(frames), 'grids': len(grids), 'speech_available': bool(speech), 'reused': False}


def load(path):
    task = read(path)
    identity = {k: v for k, v in task.items() if k not in {'fingerprint','frames','grids','evidence_sha256'}}
    require(task.get('contract') == CONTRACT and digest(identity) == task.get('fingerprint'), '取证任务身份变化')
    require(sha(task['source']['path']) == task['source']['sha256'], '参考片变化，不能复用旧证据')
    require(digest({'frames':task['frames'],'grids':task['grids']}) == task['evidence_sha256'], '证据索引变化')
    for row in task['frames']+task['grids']:
        require(sha(row['path']) == row['sha256'], '证据图片变化')
    return task


def validate_submission(task, value):
    require(value.get('task_fingerprint') == task['fingerprint'], '提交属于另一取证任务')
    reviewed = value.get('reviewed_grid_ids')
    expected = {r['id'] for r in task['grids']}
    require(isinstance(reviewed,list) and len(reviewed)==len(expected) and set(reviewed)==expected,
            '实际查看所有宫格后填写对应ID')
    require(isinstance(value.get('whole_piece'),str) and value['whole_piece'].strip(), '填写全片表达及观察范围')
    frame_map = {r['id']:r for r in task['frames']}
    objects, events = value.get('objects'), value.get('events')
    require(isinstance(objects,list) and objects and isinstance(events,list) and events, '缺少对象及完整动作说明')
    ids = [r.get('id') for r in objects]
    require(all(isinstance(i,str) and i for i in ids) and len(set(ids))==len(ids), '对象ID重复或无效')
    sentences = {r['id']:r for r in task['speech']}
    event_ids = set()
    for obj in objects:
        require(obj.get('role') and obj.get('appearance') and obj.get('lifetime'), '对象缺少作用、外观或存续范围')
    for event in events:
        identity = event.get('id')
        require(identity and identity not in event_ids, '动作ID重复或为空')
        event_ids.add(identity)
        require(event.get('object_id') in ids and event.get('purpose'), '动作缺少已登记对象或表达作用')
        a,b = event.get('start'),event.get('end')
        require(number(a) and number(b) and 0<=a<b<=task['source']['duration']+.001, '动作时间越界')
        phases = event.get('phases')
        require(isinstance(phases,list) and phases, '登记进入、运动、停留及离开中的实际阶段')
        for phase in phases:
            refs = phase.get('frame_ids')
            require(phase.get('state') and isinstance(refs,list) and refs
                    and set(refs).issubset(frame_map), '动作阶段缺少状态或真实帧引用')
            require(all(a-.001<=frame_map[r]['at']<=b+.001 for r in refs), '动作证据不在本段时间范围')
        trigger = event.get('trigger',{})
        require(trigger.get('kind') in {'speech','action','authored'}, '动作须说明台词、动作或独立编排触发')
        if trigger['kind']=='speech':
            row = sentences.get(trigger.get('sentence_id'))
            require(row is not None, '语义绑定需要同源真实台词证据')
            if trigger.get('word_id'):
                require(trigger['word_id'] in {w['id'] for w in row['words']}, '不得从句时钟臆造逐词事件')
        require(event.get('preserve') and event.get('retiming'), '说明需保留的动作和换稿后的时序规则')
    require(isinstance(value.get('unknowns'),list), '明确记录尚不能确认的问题')
    for key in ['continuous_watch','continuous_listen']:
        require(value.get(key) in {'pending','performed','not_applicable'}, '连续听看须独立记录')
    return value


def submit(path, submission_path):
    task = load(path)
    value = validate_submission(task, read(submission_path))
    output = Path(path).parent/'analysis.json'
    result = {'contract': CONTRACT, 'task_fingerprint': task['fingerprint'], 'analysis': value,
              'source': task['source'], 'evidence_sha256': task['evidence_sha256'],
              'production_ready': False}
    if output.exists():
        require(read(output)==result, '已有不同分析，保留旧结论并新建revision')
    write(output,result)
    lines = ['# 参考片动作与语义分析', '', value['whole_piece'], '',
             '本报告是参考理解，不代表生产接入或连续听看已通过。', '', '## 动作菜谱', '']
    for e in value['events']:
        lines += [f"### {e['start']:.3f}–{e['end']:.3f}s · {e['id']}", '',
                  f"对象：{e['object_id']}；作用：{e['purpose']}",
                  f"保留：{e['preserve']}", f"换稿：{e['retiming']}"]
        lines += [f"- {p['state']}；证据：{', '.join(p['frame_ids'])}" for p in e['phases']]
        lines += ['']
    lines += ['## 未确认', '', *[f'- {v}' for v in value['unknowns']]]
    (output.parent/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return {'analysis':str(output),'report':str(output.parent/'report.md'),'production_ready':False}


def compare(reference_path, target_path, mapping_path, output):
    """Correspondence is explicit: changed speech need not share source seconds."""
    reference, target = load(reference_path), load(target_path)
    mapping = read(mapping_path)
    require(isinstance(mapping,list) and mapping, '按相同含义或动作阶段填写对照帧')
    left = {r['id']:r for r in reference['frames']}
    right = {r['id']:r for r in target['frames']}
    pairs = []
    for row in mapping:
        require(row.get('reference_frame') in left and row.get('target_frame') in right
                and isinstance(row.get('reason'),str) and row['reason'].strip(), '对照缺少真实帧或对应理由')
        pairs.append({'reference':left[row['reference_frame']], 'target':right[row['target_frame']],
                      'reason':row['reason']})
    identity = {'reference':reference['fingerprint'],'target':target['fingerprint'],'pairs':pairs}
    directory = Path(output).resolve()/digest(identity)[:24]
    if (directory/'comparison.json').is_file():
        saved=read(directory/'comparison.json')
        require(saved['identity']==identity,'已有对照身份变化')
        for row in saved['pictures']:
            require(sha(row['path'])==row['sha256'],'已有对照图片变化')
        return {'comparison':str(directory/'comparison.json'),'pictures':saved['pictures']}
    require(not directory.exists(),'保留未完成对照，使用新的输出目录')
    directory.mkdir(parents=True)
    pictures=[]
    for i,pair in enumerate(pairs):
        canvas=Image.new('RGB',(1200,760),'#eeeae1');draw=ImageDraw.Draw(canvas);font=_font(20)
        for x,key,label in [(0,'reference','参考'),(600,'target','适配')]:
            frame=pair[key]
            with Image.open(frame['path']) as im:
                fitted=ImageOps.contain(im.convert('RGB'),(580,640))
                canvas.paste(fitted,(x+(600-fitted.width)//2,40+(640-fitted.height)//2))
            draw.text((x+10,10),f"{label} {frame['id']} / {frame['at']:.4f}s",font=font,fill='#15202b')
        for j,line in enumerate(_lines(pair['reason'],55)):
            draw.text((10,690+j*22),line,font=font,fill='#15202b')
        file=directory/f'pair-{i+1:03d}.jpg';canvas.save(file,quality=94)
        pictures.append({'path':str(file),'sha256':sha(file)})
    write(directory/'comparison.json',{'identity':identity,'pictures':pictures,
          'visual_judgment':'pending','continuous_playback':'pending','production_ready':False})
    return {'comparison':str(directory/'comparison.json'),'pictures':pictures}
