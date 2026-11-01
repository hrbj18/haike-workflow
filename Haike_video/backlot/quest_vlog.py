"""Independent reference-derived controls, using the existing speech-clock producer."""
from pathlib import Path

from backlot.work_catalog import WorkError, read_json

LAYOUT = Path(__file__).resolve().parents[1] / 'templates/hum-production-v1/quest/layout.json'


def require(ok, message):
    if not ok:
        raise WorkError(message)


def canvas(props):
    size = (props.get('width', 1080), props.get('height', 1920))
    require(size in {(r['width'], r['height']) for r in read_json(LAYOUT)['layouts'].values()},
            '任务口播模板支持16:9和9:16，须选择独立重排画幅')
    return size


def scene(row, media_ids):
    q = row.get('quest')
    require(row['module'] == 'quest' and isinstance(q, dict)
            and not set(q) - {'kind', 'items', 'accent', 'cues', 'presenter', 'chapter', 'transition',
                'variant', 'photoIds', 'comment', 'ranking', 'path', 'code'}, '任务口播场景参数无效')
    kind = q.get('kind')
    require(kind in read_json(LAYOUT)['kinds'] and row['frames'] >= read_json(LAYOUT)['kinds'][kind],
            '任务口播动作太短，无法保留完整入场、变化和阅读')
    items = q.get('items', [])
    limits = {'versus': (2, 2), 'quests': (2, 3), 'unlock': (2, 4), 'timeline': (2, 5),
              'books': (2, 4), 'clear': (2, 3), 'comment': (0, 0), 'ranking': (2, 5),
              'radar': (0, 3), 'path': (2, 5), 'editor': (2, 4)}
    low, high = limits.get(kind, (0, 4))
    require(isinstance(items, list) and low <= len(items) <= high
            and all(isinstance(s, str) and 0 < len(s) <= 12 and '\n' not in s for s in items),
            '任务口播标签数量或长度超出当前动作容量')
    require(isinstance(q.get('accent', ''), str) and len(q.get('accent', '')) <= 12
            and isinstance(q.get('chapter', ''), str) and len(q.get('chapter', '')) <= 18,
            '任务口播强调或章节文字过长')
    require(q.get('presenter', 'circle') in {'card', 'circle', 'hidden'}, '任务口播人物布局无效')
    cues = q.get('cues', [])
    # These are explicit authored/ASR-bound events, never inferred word timestamps.
    path_data = q.get('path', {})
    require(isinstance(path_data, dict), '路径参数须为对象')
    expected = len(path_data.get('stops', [])) if kind == 'path' and isinstance(path_data.get('stops', []), list) else len(items)
    require(isinstance(cues, list) and len(cues) == expected
            and all(type(c) is int and 15 <= c <= row['frames'] - 30 for c in cues)
            and all(a < b for a, b in zip(cues, cues[1:])),
            '任务口播每个标签须有明确事件帧，并保留至少一秒结果阅读')
    require(q.get('transition') is None or q['transition'] in read_json(LAYOUT)['transitions'], '任务转场尚未实现')
    require(q.get('variant') is None or (kind, q['variant']) in {('versus', 'panel'), ('unlock', 'tree')}, '此镜头不支持该任务变体')
    if q.get('variant') == 'tree':
        require(len(items) <= 3 and 0 < len(q.get('accent', '')) <= 6, '分支解锁须有根标签并保留二至三条分支')
    used = set()
    def photos(ids, low, high):
        require(isinstance(ids, list) and low <= len(ids) <= high and all(isinstance(i, str) for i in ids)
                and len(set(ids)) == len(ids) and set(ids) <= media_ids, '照片组须绑定不同的已审素材')
        used.update(ids)
    if 'photoIds' in q:
        require(kind == 'clear', '照片星座仅在通关/收尾镜头开放')
        photos(q['photoIds'], 3, 5)
    for field, owner in [('comment', 'comment'), ('ranking', 'ranking'), ('path', 'path'), ('code', 'editor')]:
        require(field not in q or kind == owner, '任务数据与当前动作不匹配：' + field)
    integer = lambda n: type(n) is int
    if kind == 'comment':
        c = q.get('comment', {})
        require(isinstance(c, dict) and not set(c) - {'author', 'body', 'from', 'until', 'proofFrom', 'photoIds'}
                and isinstance(c.get('author'), str) and 0 < len(c['author']) <= 18
                and isinstance(c.get('body'), str) and 0 < len(c['body']) <= 72
                and '\n' not in c['body'] and all(integer(c.get(k)) for k in ['from', 'until'])
                and 15 <= c['from'] < c['until'] <= row['frames'] - 30, '提问输入须有完整文案和独立编排时窗')
        if c.get('photoIds'):
            photos(c['photoIds'], 1, 3)
            require(integer(c.get('proofFrom')) and c['until'] <= c['proofFrom']
                    and c['proofFrom'] + (len(c['photoIds']) - 1) * 6 + 15 + 30 <= row['frames'],
                    '作品证据须在完整提问之后出现，并保留阅读')
    if kind == 'ranking':
        rank = q.get('ranking', {})
        require(isinstance(rank, dict) and not set(rank) - {'note', 'orders', 'strikes', 'meters'}
                and isinstance(rank.get('note'), str) and 0 < len(rank['note']) <= 24
                and isinstance(rank.get('orders'), list) and 1 <= len(rank['orders']) <= 4, '重排须说明依据并声明完整状态')
        previous = max(cues) + 15
        for event in rank['orders']:
            require(isinstance(event, dict) and set(event) == {'at', 'order'} and integer(event.get('at'))
                    and previous <= event['at'] <= row['frames'] - 48
                    and isinstance(event.get('order'), list) and all(integer(i) for i in event['order'])
                    and sorted(event['order']) == list(range(len(items))), '排序必须保留同一组条目，并留足移动和阅读时间')
            previous = event['at'] + 18
        require(isinstance(rank.get('strikes', []), list), '划除事件须为数组')
        for event in rank.get('strikes', []):
            require(isinstance(event, dict) and set(event) == {'at', 'index'} and integer(event.get('at'))
                    and 15 <= event['at'] <= row['frames'] - 40 and integer(event.get('index'))
                    and 0 <= event['index'] < len(items), '划除须引用同一条目的稳定编号')
        meters = rank.get('meters')
        require(meters is None or (isinstance(meters, list) and len(meters) == len(items)
                and all(type(n) in {int, float} and 0 <= n <= 1 for n in meters)), '条形值须明确绑定每条内容及排序依据')
    if kind == 'path':
        path = q.get('path', {})
        require(isinstance(path, dict) and not set(path) - {'id', 'stops', 'initial', 'reset', 'travelFrames'}
                and isinstance(path.get('id'), str) and 0 < len(path['id']) <= 48
                and isinstance(path.get('stops'), list) and 1 <= len(path['stops']) <= 8
                and all(integer(n) and 0 <= n < len(items) for n in [path.get('initial', 0), *path['stops']])
                and type(path.get('reset', False)) is bool and integer(path.get('travelFrames', 24))
                and 12 <= path.get('travelFrames', 24) <= 45, '路径须声明稳定ID、真实节点和移动时长')
        travel = path.get('travelFrames', 24)
        require(cues and cues[-1] + travel + 30 <= row['frames']
                and all(b - a >= travel for a, b in zip(cues, cues[1:])), '路径移动不能重叠，并须保留结果阅读')
    if kind == 'editor':
        require(isinstance(q.get('code'), list) and 1 <= len(q['code']) <= 5
                and all(isinstance(s, str) and 0 < len(s) <= 28 and '\n' not in s for s in q['code']), '编辑示意须提供自己的完整代码/流程行')
    if kind == 'radar':
        require(all(len(s) <= 6 for s in items), '扫描节点标签最多六字，完整说明留在字幕')
    require(not {'motion', 'selection', 'wallMediaIds'} & set(row), '任务口播不能套用旧素材墙动作')
    if kind in {'media', 'world'}:
        require(row.get('mediaId') in media_ids, '实拍任务镜头须绑定已审素材')
    elif row.get('mediaId') is not None:
        require(kind in {'headline', 'versus', 'quests', 'unlock', 'clear', 'path'} and row['mediaId'] in media_ids,
                '此任务镜头没有实拍槽，或素材不存在')
    return used | ({row['mediaId']} if row.get('mediaId') else set())


def continuity(scenes):
    """Same graph IDs retain node identity across adjacent scene/background changes."""
    known = {}
    for i, s in enumerate(scenes):
        q = s['quest']
        if i == 0:
            require(not q.get('transition'), '首镜头没有可承接的上一场转场')
        if q['kind'] != 'path':
            continue
        p = q['path']; old = known.get(p['id'])
        if old:
            previous, labels, destination = old
            require(labels == q['items'], '同一路径不能更换节点含义或顺序')
            require(p.get('reset') or (previous == i - 1 and p.get('initial', destination) == destination),
                    '路径接力不能静默回到起点；重新讲述须显式reset')
        known[p['id']] = i, q['items'], p['stops'][-1]


def fonts(props, paths, image_font):
    canvas(props)
    portrait = props['height'] > props['width']
    scale = props['width'] / (1080 if portrait else 1920)
    width = (936 if portrait else 1210) * scale
    title = image_font.truetype(str(paths['display.ttf']), round((110 if portrait else 104) * scale))
    label = image_font.truetype(str(paths['body.ttf']), round((50 if portrait else 46) * scale))
    caption = image_font.truetype(str(paths['body.ttf']), round((50 if portrait else 44) * scale))
    require(all(caption.getlength(c['text']) <= (936 if portrait else 1720) * scale for c in props['captions']),
            '任务口播字幕超出实际字体字框，请按真实词边界分句')
    for row in props['scenes']:
        require(all(title.getlength(line) <= width for line in row['title'].split('\n')),
                '任务口播标题超出实际字体字框')
        kind, q = row['quest']['kind'], row['quest']
        label_width = (360 if q.get('variant') == 'tree' else 388 if kind == 'versus' else 650 if kind == 'quests'
                       else 440 if kind == 'media' else 790) * scale if portrait else (width / 2 - 80 if kind == 'versus' else width)
        label_font = label
        if kind == 'path' and not portrait:
            label_font = image_font.truetype(str(paths['body.ttf']), round(30 * scale))
            label_width = min((width - 140 * scale) / (len(q['items']) - 1) - 20 * scale, 300 * scale)
        if kind == 'timeline':
            label_font = image_font.truetype(str(paths['body.ttf']), round(32 * scale))
            label_width = width / len(q['items']) - 16 * scale
            # The renderer wraps at characters inside fixed three/two-line boxes.
            # Measure actual glyphs rather than validating against the whole canvas.
            for text in q['items']:
                lines, line = 1, ''
                for char in text:
                    require(label_font.getlength(char) <= label_width, '时间线节点单字超出字框')
                    if label_font.getlength(line + char) > label_width:
                        lines += 1; line = char
                    else:
                        line += char
                require(lines <= (3 if portrait else 2), '时间线节点超出三行/两行容量，请缩短节点标签，完整说明保留在字幕')
            accent = image_font.truetype(str(paths['display.ttf']), round((80 if portrait else 64) * scale))
            require(accent.getlength(q.get('accent', '')) <= width, '时间线结论超出实际字体字框')
        else:
            if kind == 'books':
                label_font = image_font.truetype(str(paths['body.ttf']), round((42 if portrait else 34) * scale))
                label_width = width * .78 - 48 * scale
            require(all(label_font.getlength(s) <= label_width for s in q.get('items', [])), '任务标签超出字框')
        if q.get('variant') == 'tree':
            root_font = image_font.truetype(str(paths['display.ttf']), round(44 * scale))
            require(root_font.getlength(q['accent']) <= 201 * scale, '解锁根标签超出实际字体字框')
        if not portrait and (q.get('variant') == 'tree' or kind in {'ranking', 'radar'}):
            require('\n' not in row['title'], '横屏榜单/扫描/分支树须保留单行标题，避免动作区与字幕碰撞')
        if kind == 'path':
            require('\n' not in row['title'], '路径须保留单行标题，为移动标记和跨阶段曲线留空间')
            if row.get('mediaId'):
                require(portrait, '路径旁实拍当前只开放9:16独立版式；横屏请保留原路径或另用实拍镜头')
                available = (read_json(LAYOUT)['portrait']['pathMedia'][0] - 125 - 24) * scale
                path_font = image_font.truetype(str(paths['body.ttf']), round(44 * scale))
                require(all(path_font.getlength(text) <= available for text in q['items']),
                        '路径标签与实拍窗碰撞，请缩短节点标签，完整说明保留在字幕')
        if not portrait and kind in {'comment', 'path'}:
            require('\n' not in row['title'], '横屏提问/路径须保留单行标题，为照片和跨阶段曲线留空间')
        if not portrait and kind in {'media', 'world'}:
            media = next(m for m in props['media'] if m['id'] == row['mediaId'])
            if media.get('orientation') == 'portrait':
                require('\n' not in row['title'], '横屏中的竖素材须用单行标题，为完整高窗及说明留空间')
