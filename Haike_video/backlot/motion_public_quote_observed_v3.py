"""Independent controls authored from observable outputs and public parameters.

This is a new implementation, not the protected motion-kit/poster-kit source.
Only explicitly implemented control/variant pairs are admitted. Fidelity remains
pending until the actual output has been compared with the bound reference.
"""
from copy import deepcopy
import base64
import json
import math
from pathlib import Path
import re
import shutil
import sys

from backlot.motion_public_io_v1 import atomic_private, fingerprint, read_json, sha

STYLES = {'template-01-integrated': 'light', 'template-04-dark-console': 'console'}
VARIANTS = {'light': {'title': {'type'}, 'steps': {'ladder'}, 'media': {'scan', 'tilt'}, 'gallery': {'stack'}, 'device': {'phone'}, 'quote': {'reveal', 'card'}, 'cta': {'button'}}, 'console': {'title': {'slam'}, 'steps': {'cards'}, 'media': {'zoom', 'tilt'}, 'gallery': {'carousel'}, 'device': {'tablet'}, 'quote': {'card'}, 'cta': {'arrow'}}}


def presenter_window(receipts, start, end):
    """Require declared real source coverage, including pre-entry and fade tail."""
    from backlot.motion_public_quote_execution_v3 import require
    derivation = receipts.get('avatar_derivation', {})
    windows = derivation.get('timeline_windows', [])
    require(derivation.get('audio_speed_changed') is False and any(
        isinstance(window, list) and len(window) == 2
        and all(type(n) in (int, float) and math.isfinite(n) for n in window)
        and window[0] <= start + .001 and end <= window[1] + .001
        for window in windows), '人物可见窗口缺少原速真实来源覆盖证明')


def control_props(control, props, *, style=None, variant=None):
    """Admit the implemented parameter surface rather than ignore old options."""
    from backlot.motion_public_quote_execution_v3 import require
    fields = {'title': {'kicker', 'line1', 'line2', 'lines'}, 'kinetic': {'kicker', 'lines'},
        'steps': {'title', 'steps'}, 'media': {'title', 'src', 'sourceStart'},
        'device': {'title', 'sub', 'src', 'sourceStart'}, 'gallery': {'title', 'items'},
        'polaroid': {'title', 'items'}, 'quote': {'text', 'who', 'lines', 'reveal_groups'}, 'cta': {'kicker', 'text', 'sub', 'dir'}}
    require(isinstance(props, dict) and not set(props) - fields[control], '该控件参数尚未实现，不能静默忽略')
    for name in {'title', 'sub', 'text', 'who', 'kicker', 'line1', 'line2'} & set(props):
        require(isinstance(props[name], str) and len(props[name]) <= (50 if name == 'text' else 40), '控件文字类型或阅读容量无效')
    if control in {'title', 'kinetic'}:
        lines = props.get('lines', [props.get('line1'), props.get('line2')])
        require(isinstance(lines, list) and len(lines) == 2 and all(isinstance(s, str) and 1 <= len(s) <= 6 for s in lines), '本版标题须为两行且每行1–6字')
    if control == 'quote':
        require(isinstance(props.get('text'), str) and 1 <= len(props['text']) <= 50
                and not set('\r\n\t') & set(props['text']), '引言正文须为1–50码点完整单段文字')
    if 'reveal_groups' in props:
        groups = props['reveal_groups']
        require(control == 'quote' and style == 'light' and variant == 'reveal', '仅浅色reveal开放短语分组')
        require(isinstance(groups, list) and 1 <= len(groups) <= 20
                and all(isinstance(s, str) and 1 <= len(s) <= 6 and not set('\r\n\t') & set(s) for s in groups)
                and ''.join(groups) == props['text'], '短语分组须容量有效并逐字concat等于完整引言')
    if control == 'steps':
        require(isinstance(props.get('steps'), list) and len(props['steps']) == 3
            and all(isinstance(s, str) and 1 <= len(s) <= 12 for s in props['steps']), '本版步骤控件只实现三项，每项1–12字')
    if control == 'quote' and 'lines' in props:
        require(isinstance(props['lines'], list) and 1 <= len(props['lines']) <= 5
                and all(isinstance(line, str) and 1 <= len(line) <= 20 and not {'\r', '\n'} & set(line) for line in props['lines'])
                and ''.join(props['lines']) == props.get('text'), '海报换行须逐字保留完整引言')
    if control in {'gallery', 'polaroid'}:
        require(isinstance(props.get('items'), list) and len(props['items']) == 3, '本版图库控件只实现三张真实素材')
        for item in props['items']:
            require(isinstance(item, dict) and not set(item) - {'src', 'sourceStart', 'caption'}
                and isinstance(item.get('src'), str) and isinstance(item.get('caption', ''), str), '图库子参数尚未实现或缺真实素材')
            require(type(item.get('sourceStart', 0)) in (int, float) and math.isfinite(item.get('sourceStart', 0))
                and item.get('sourceStart', 0) >= 0, '图库原速来源起点无效')
    if control in {'media', 'device'}:
        require(isinstance(props.get('src'), str) and type(props.get('sourceStart', 0)) in (int, float)
            and math.isfinite(props.get('sourceStart', 0)) and props.get('sourceStart', 0) >= 0, '真实媒体或原速来源起点无效')
    if control == 'cta':
        require(props.get('dir', 'down') == 'down', '本版结尾只实现向下引导，不回退其他方向')


def caption_chunks(sentences, limit=18):
    """Retain characters and use measured words; adapted from project-owned C helper."""
    result = []
    for sentence in sentences:
        text, words = sentence['text'], sentence['words']
        positions, cursor = [], 0
        for word in words:
            at = text.find(word['text'], cursor)
            if at < 0:
                positions = []; break
            cursor = at + len(word['text']); positions.append(cursor)
        if not positions:
            result.append({'s': sentence['start'], 'e': sentence['end'], 'text': text}); continue
        first = char_start = 0
        for index, word in enumerate(words):
            last = index == len(words) - 1
            stop = len(text) if last else positions[index]
            next_stop = len(text) if index + 1 == len(words) - 1 else positions[index + 1] if not last else stop
            if not last and next_stop - char_start <= limit:
                continue
            result.append({'s': words[first]['start'], 'e': sentence['end'] if last else word['end'],
                           'text': text[char_start:stop]})
            first, char_start = index + 1, stop
    from backlot.motion_public_quote_execution_v3 import require
    require(''.join(c['text'] for c in result) == ''.join(s['text'] for s in sentences), '字幕不能丢失实际ASR字符')
    return result


def default_reveal_groups(text):
    """Own deterministic Unicode policy, not an inferred native tokenizer."""
    from backlot.motion_public_quote_execution_v3 import require
    require(isinstance(text, str) and 1 <= len(text) <= 50, '默认短语正文容量无效')
    clauses = re.findall(r'[^，,。.!！?？；;：:]+[，,。.!！?？；;：:]*|[，,。.!！?？；;：:]+', text)
    result = []
    for clause in clauses:
        while len(clause) > 6:
            result.append(clause[:3]); clause = clause[3:]
        if clause: result.append(clause)
    if len(result) > 20:
        result = [text[i:i + 3] for i in range(0, len(text), 3)]
    require(result and ''.join(result) == text, '默认短语必须保留完整文字')
    return result


def require_quote_candidate_window(row):
    from backlot.motion_public_quote_execution_v3 import require
    cue = row['cues'][0] if row['cues'] else row['t0']
    require(cue + 1.58 <= row['t1'] - .4 + 1e-7, '引言时窗须覆盖自有候选完整正文署名及原退出相位')


def preflight(value):
    from backlot import motion_public_quote_execution_v3 as e
    e.require(isinstance(value, dict) and not set(value) - {'engine', 'pack_key', 'reference_id', 'title', 'brand',
        'script', 'asr', 'assets', 'composition', 'tool_root', 'dependency_root', 'ffmpeg_root', 'work_root', 'source_receipts'}, '独立观察组件输入字段无效')
    e.require(value.get('engine') == 'observed-quote-controls/3', '引言专用引擎身份无效')
    reference = value.get('reference_id')
    e.require(reference in STYLES and value.get('pack_key') == 'observed-' + STYLES[reference], '独立观察样式与原参考身份不符')
    style = STYLES[reference]
    manifest = e.component()
    assets = value.get('assets')
    e.require(isinstance(assets, dict) and all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', name) for name in assets)
              and not {'script.json', 'asr.json'} & set(assets), '本期素材逻辑名无效')
    paths = {name: e.bound(row) for name, row in assets.items()}
    e.require('voice.wav' in paths and (style == 'poster' or 'presenter.mp4' in paths), '缺少完整本期口播或已授权人物母视频')
    script, asr = e.bound(value['script']), e.bound(value['asr'])
    composition = deepcopy(value.get('composition'))
    e.require(isinstance(composition, dict) and not set(composition) - {'base_timeline', 'semantic_scenes', 'caption_corrections', 'timeline'}, '观察组件编排字段无效')
    corrections = composition.get('caption_corrections', [])
    text, segments, measured_duration = e.real_clock(script, asr, paths['voice.wav'], corrections)
    original_segments = read_json(asr)['segments']
    captions = caption_chunks(original_segments)
    for correction in corrections:
        count = sum(c['text'].count(correction['from']) for c in captions)
        e.require(count == correction['expected_count'], '字幕校正次数改变')
        for caption in captions:
            caption['text'] = caption['text'].replace(correction['from'], correction['to'])
    e.require(e.norm(''.join(c['text'] for c in captions)) == e.norm(text), '观察组件字幕未保留完整原稿')
    events = []
    if 'timeline' in composition:
        e.require(style == 'poster', '显式海报时钟不能传给其他样式')
        base = composition['timeline']; rows = deepcopy(base.get('segments', []))
        cursor = 0
        for index, row in enumerate(rows):
            e.require(abs(row['t0'] - cursor) < .001 and row['t1'] > row['t0'], '显式海报场景必须连续覆盖')
            cursor = row['t1']
            for at in row.get('cues', []):
                measured = [s['start'] for s in segments] + [w['start'] for s in segments for w in s['words']]
                e.require(at == 0 or any(abs(at - time) <= .011 for time in measured), '海报动作必须引用真实句词时钟或明确开场0')
            row['id'] = 'poster-' + str(index)
            row['presenter'] = 'hide'
        duration = base['duration']
        e.require(abs(cursor - duration) < .001, '海报末场没有覆盖完整时间线')
    else:
        base = composition.get('base_timeline', {})
        duration = base.get('duration')
        authored = composition.get('semantic_scenes')
        e.require(isinstance(authored, list) and authored, '缺少本期实际控件语义计划')
        rows, cursor = [], 0
        for index, source in enumerate(authored):
            first, last = source.get('sentence_start'), source.get('sentence_end')
            e.require(type(first) is int and type(last) is int and first == cursor and first < last <= len(segments), '控件必须按真实ASR顺序完整覆盖')
            cursor = last
            t0 = 0 if index == 0 else segments[first]['start']
            if source.get('start_in_silence') is not None:
                at = source['start_in_silence']
                e.require(index > 0 and segments[first - 1]['end'] <= at <= segments[first]['start'], '预入场必须落在真实相邻语句停顿内')
                t0 = at
            t1 = duration if index == len(authored) - 1 else segments[last]['start']
            if index + 1 < len(authored) and authored[index + 1].get('start_in_silence') is not None:
                t1 = authored[index + 1]['start_in_silence']
            action = source.get('action_id', '')
            e.require(action.startswith('haike.' + reference + '.motion-kit.'), '原参考动作不能冒充其他模板控件')
            control = action.rsplit('.', 1)[-1]
            cues = []
            for cue in source.get('cues', []):
                if 'authored_at' in cue:
                    at = cue['authored_at']; e.require(index == 0 and at == 0, '仅开放明确开场0编排触发')
                    anchor = {'kind': 'authored', 'at': 0}
                else:
                    sentence = cue.get('sentence'); word = cue.get('word')
                    e.require(type(sentence) is int and first <= sentence < last, '内部动作语句不在本组')
                    at = segments[sentence]['start']
                    if word is not None:
                        e.require(type(word) is int and 0 <= word < len(segments[sentence]['words']), '内部动作词索引无效')
                        at = segments[sentence]['words'][word]['start']
                    anchor = {'kind': 'speech', 'sentence': sentence, 'word': word}
                e.require(t0 <= at < t1 and (not cues or at > cues[-1]), '内部控件事件须有序并在组内')
                cues.append(at); events.append({'id': source['id'] + '.' + cue['id'], 'at': at, 'anchor': anchor, 'original_action_id': action})
            rows.append({'id': source['id'], 'control': control, 'variant': source.get('variant'), 't0': t0, 't1': t1,
                'props': deepcopy(source['props']), 'cues': cues, 'presenter': source.get('presenter', 'hide'), 'original_action_id': action})
        e.require(cursor == len(segments), '控件未覆盖完整口播')
    e.require(isinstance(duration, (float, int)) and measured_duration <= duration <= measured_duration + .25,
              '完整音轨必须原速保留，只允许明确的短静音尾部')
    e.require(base.get('layout', 'portrait') == 'portrait', '本版观察组件仅声明竖屏几何')
    for row in rows:
        control, variant = row['control'], row.get('variant')
        e.require(control in VARIANTS[style] and variant in VARIANTS[style][control], '该控件变体尚未实现；不回退其他动效')
        e.require(isinstance(row.get('props'), dict) and row['t1'] - row['t0'] >= .5 and row.get('presenter') in {'hide', 'card'}, '控件参数、阅读窗口或人物域无效')
        control_props(control, row['props'], style=style, variant=variant)
        if style == 'light' and control == 'quote' and variant == 'reveal':
            row['props'].setdefault('reveal_groups', default_reveal_groups(row['props']['text']))
        if control == 'quote':
            require_quote_candidate_window(row)
        e.require('lines' not in row['props'] or control != 'quote' or style == 'poster', '仅v2海报引言开放明确换行')
        if style == 'paper' and control == 'quote':
            validate_quote_window(row)
        row['action_id'] = 'haike.public-observed.' + style + '.' + control + '.' + variant
        row['action_version'] = '3-quote-development'
        names = []
        if 'src' in row['props']:
            names.append(row['props']['src'])
        names += [item['src'] for item in row['props'].get('items', []) if isinstance(item, dict) and 'src' in item]
        e.require(all(name in paths for name in names), '控件真实素材尚未绑定')
        if row.get('presenter') == 'card':
            presenter_window(value.get('source_receipts', {}), max(0, row['t0'] - (.4 if row['t0'] else 0)),
                             min(duration, row['t1'] + .12))
    tools, identities = e.environment(value['tool_root'], value['dependency_root'], value.get('ffmpeg_root'))
    spec = {'schema': 'haike.observed-quote-controls-composition/3', 'style': style, 'fps': 60, 'width': 1080, 'height': 1920,
        'duration': duration, 'frames': round(duration * 60), 'brand': value.get('brand', ''), 'segments': rows,
        'captions': captions, 'events': events, 'presenter': deepcopy(base.get('presenter', {})),
        'caption_position': deepcopy(base.get('captionPosition', {'bottomRatio': .1, 'leftRatio': .06, 'rightRatio': .06})),
        'reference_id': reference, 'source_script_sha256': sha(script), 'audio_sha256': sha(paths['voice.wav']),
        'implementation_identity': 'haike.observed-quote-controls/3', 'original_fidelity': 'pending', 'all_original_controls_supported': False}
    return {'paths': paths, 'script': script, 'asr': asr, 'spec': spec, 'duration': duration, 'frames': spec['frames'],
        'environment': identities, 'reference': {'template_id': reference, **manifest['references'][reference]},
        'input_engine': 'observed-quote-controls/3', 'tools': tools}


def validate_quote_window(row):
    """Reserve complete typing, attribution entry and the existing exit phase."""
    from backlot.motion_public_quote_execution_v3 import require
    start = row['cues'][0] if row['cues'] else row['t0']
    ready = start + len(row['props']['text']) / 8 + .5 + .35 if row['variant'] == 'type' else row['t0'] + 1.8 + .35
    require(ready <= row['t1'] - .4 + 1e-7, '纸感引言时窗不足以完成逐字阅读、署名及原退出动作')


def _real_media(path, folder, request, key, start, end, offset=0):
    from backlot import motion_public_quote_execution_v3 as e
    e.require(re.fullmatch(r'[A-Za-z0-9_-]+', key), '派生素材ID无效')
    output = folder / 'project/media' / key
    output.mkdir(parents=True, exist_ok=False)
    ffmpeg = e._ffmpeg(request)
    color = json.loads(e._command([sys.executable, '-X', 'utf8', '-B', folder / 'runtime-source/scripts/color_management.py',
        '--image', path], folder, request, 'color-' + key))
    e.require(color['source_sha256'] == sha(path), '真实素材颜色证据的源身份改变')
    operation = {'source_sha256': sha(path), 'offset': offset, 'duration': end - start, 'fps': request['spec']['fps'],
                 'filter': color['filter'], 'ffmpeg_sha256': sha(ffmpeg), 'jpeg_quality': 2,
                 'static_image': path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}}
    cache = folder.parent / 'media-cache' / fingerprint(operation)
    cached = read_json(cache / 'receipt.json')
    if cached:
        e.require(cached.get('operation') == operation and all(re.fullmatch(r'[A-Za-z0-9_.-]+', row['name'])
            and (cache / row['name']).is_file() and not (cache / row['name']).is_symlink()
            and sha(cache / row['name']) == row['sha256'] for row in cached['files']), '原速派生帧缓存改变，不能复用')
        for row in cached['files']:
            try:
                import os
                os.link(cache / row['name'], output / row['name'])
            except OSError:
                shutil.copy2(cache / row['name'], output / row['name'])
        data = deepcopy(cached['media'])
        data['timelineStart'] = start
        if 'image' in data:data['image'] = (output / 'image.png').relative_to(folder / 'project').as_posix()
        else:data['directory'] = output.relative_to(folder / 'project').as_posix()
        return data
    if path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}:
        image = output / 'image.png'
        e._command([ffmpeg, '-nostdin', '-v', 'error', '-n', '-i', path, '-vf', color['filter'], '-frames:v', '1', image],
            folder, request, 'image-' + key)
        data = {'image': image.relative_to(folder / 'project').as_posix(), 'source_sha256': sha(path), 'color': color}
        _save_media_cache(cache, operation, data, output)
        return data
    probe = json.loads(e._command([e._ffprobe(request), '-v', 'error', '-show_streams',
        '-show_format', '-of', 'json', path], folder, request, 'probe-' + key))
    stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    duration = end - start; fps = request['spec']['fps']; count = math.ceil(duration * fps - 1e-7)
    e.require(offset >= 0 and offset + duration <= float(stream.get('duration') or probe['format']['duration']) + .001,
              '真实原速视频窗口不足；禁止重复、尾帧填充或变速')
    e._command([ffmpeg, '-nostdin', '-v', 'error', '-n', '-ss', str(offset), '-i', path, '-an',
        '-vf', 'fps=' + str(fps) + ',' + color['filter'], '-frames:v', str(count), '-q:v', '2', output / 'f_%05d.jpg'],
        folder, request, 'extract-' + key)
    frames = sorted(output.glob('f_*.jpg')); e.require(len(frames) == count, '真实媒体实际解码帧不完整')
    data = {'directory': output.relative_to(folder / 'project').as_posix(), 'timelineStart': start,
        'duration': duration, 'fps': fps, 'frames': count, 'sourceOffset': offset, 'playbackRate': 1,
        'source_sha256': sha(path), 'source_video': {k: stream.get(k) for k in ('width', 'height', 'r_frame_rate', 'bit_rate', 'color_space', 'color_transfer')},
        'color': color, 'frame_sha256': [sha(p) for p in frames]}
    _save_media_cache(cache, operation, data, output)
    return data


def _save_media_cache(cache, operation, media, output):
    """Only fresh derived media are linked, never installation/source programs."""
    import os
    from backlot.motion_public_quote_execution_v3 import require
    require(not cache.exists(), '派生缓存已有残留，保留现场而不覆盖')
    cache.mkdir(parents=True)
    files = []
    for file in sorted(output.iterdir()):
        if file.is_file():
            try:os.link(file, cache / file.name)
            except OSError:shutil.copy2(file, cache / file.name)
            files.append({'name': file.name, 'sha256': sha(file)})
    atomic_private(cache / 'receipt.json', {'operation': operation, 'media': media, 'files': files,
        'source': 'actual decoded immutable derived media; not installation files'})


def build_project(project, folder, request):
    from backlot import motion_public_quote_execution_v3 as e
    if (folder / 'prepared.json').exists():
        receipt = read_json(folder / 'prepared.json')
        e.require(all((folder / name).is_file() and not (folder / name).is_symlink() and sha(folder / name) == digest
                      for name, digest in receipt['files'].items()), '已冻结观察组件工程改变')
        return receipt
    upstream = folder / 'runtime-source'
    e.require(not upstream.exists(), '前次准备未完成；保留失败现场，修复后冻结新身份')
    shutil.copytree(e.UPSTREAM_TEMPLATE / 'upstream', upstream)
    generated = folder / 'project'; generated.mkdir()
    fonts = generated / 'fonts'; fonts.mkdir()
    dependencies = Path(request['dependency_root'])
    for name in ('NotoSansSC.ttf', 'notosanssc-OFL.txt'):
        shutil.copy2(dependencies / 'fonts' / name, fonts / name)
    # The exact original Geist/Mono bytes are openly embedded in upstream CSS.
    required_fonts = {'0c855f7567881c1f3c41738616d4274cea4afbd2bf6aa198be467aefc157ee6d': 'Geist.woff2',
                      '5f3d6ad60f29d6cb708414ec6887163d63bf197377ef5417d2483ff31ace6c3b': 'GeistMono.woff2'}
    for css in (upstream / 'packs').rglob('*.css'):
        for encoded in re.findall(r'data:[^;"\s)]+;base64,([A-Za-z0-9+/=]+)', css.read_text('utf8')):
            raw = base64.b64decode(encoded)
            import hashlib
            digest = hashlib.sha256(raw).hexdigest()
            if digest in required_fonts and not (fonts / required_fonts[digest]).exists():
                (fonts / required_fonts[digest]).write_bytes(raw)
    e.require(all((fonts / name).is_file() and sha(fonts / name) == digest for digest, name in required_fonts.items()), '精确公开Geist字体缺件')
    for notice in (upstream / 'packs/paper-balance/1.1.1-candidate/licenses').glob('*'):
        if notice.is_file():shutil.copy2(notice, fonts / notice.name)
    props = deepcopy(request['spec']); props['media'] = {}
    assets = {name: project / 'assets/motion-public' / name for name in request['origins']}
    for index, row in enumerate(props['segments']):
        role = 's' + str(index)
        if 'src' in row['props']:
            key = role + '-main'; row['mediaKey'] = key
            props['media'][key] = _real_media(assets[row['props']['src']], folder, request, key,
                row['t0'], row['t1'], row['props'].get('sourceStart', 0))
        if row['props'].get('items'):
            row['mediaKeys'] = []
            for item_index, item in enumerate(row['props']['items']):
                key = role + '-item' + str(item_index); row['mediaKeys'].append(key)
                start = row['cues'][min(item_index, len(row['cues']) - 1)] if row['cues'] else row['t0']
                end = row['cues'][item_index + 1] if item_index + 1 < len(row['cues']) else row['t1']
                props['media'][key] = _real_media(assets[item['src']], folder, request, key, start, end, item.get('sourceStart', 0))
        if row.get('presenter') == 'card':
            key = role + '-presenter'; row['presenterMediaKey'] = key
            visible_start = max(0, row['t0'] - (.4 if index else 0))
            visible_end = min(props['duration'], row['t1'] + .12)
            presenter_window(request.get('source_receipts', {}), visible_start, visible_end)
            props['media'][key] = _real_media(assets['presenter.mp4'], folder, request, key, visible_start, visible_end, visible_start)
    atomic_private(generated / 'input.json', props)
    (generated / 'input.js').write_text('window.INPUT=' + json.dumps(props, ensure_ascii=False) + ';\n', encoding='utf8')
    shutil.copy2(e.TEMPLATE / 'observed-quote-controls-v3.js', generated / 'observed-quote-controls-v3.js')
    (generated / 'index.html').write_text('''<!doctype html><meta charset="utf-8"><style>
@font-face{font-family:NotoSource;font-weight:100 900;src:url(fonts/NotoSansSC.ttf)}
@font-face{font-family:Geist;font-weight:100 900;src:url(fonts/Geist.woff2)}
@font-face{font-family:GeistMono;font-weight:100 900;src:url(fonts/GeistMono.woff2)}
html,body{margin:0;background:#000}#stage{position:relative;width:1080px;height:1920px;overflow:hidden}
</style><div id="stage"></div><script src="input.js"></script><script src="observed-quote-controls-v3.js"></script>''', encoding='utf8')
    plan = {'schema': 'haike.observed-quote-controls-plan/3', 'width': 1080, 'height': 1920, 'fps': props['fps'],
        'end_frame': props['frames'], 'scenes': [{'id': r['id'], 'output_start_frame': round(r['t0'] * props['fps']),
            'output_end_frame': round(r['t1'] * props['fps']), 'cues': [{'outputFrame': round(at * props['fps'])} for at in r['cues']]} for r in props['segments']],
        'audio': {'sfxMixSource': 'runtime-scene-S-only', 'mixProfile': 'legacy-macro'},
        'original_fidelity': 'pending', 'all_original_controls_supported': False}
    atomic_private(generated / 'macro_plan.json', plan)
    atomic_private(generated / 'output-signature.json', {'schema': 'adu-output-signature/1', 'enabled': False})
    atomic_private(generated / 'macro_music.json', {'mode': 'track', 'path': str(assets['music.wav']), 'offset': 0} if 'music.wav' in assets else {'mode': 'none'})
    renderer = upstream / 'scripts/render_project.mjs'
    text = renderer.read_text('utf8');needle = "'-crf', '15'"
    e.require(text.count(needle) == 1, '固定公开编码入口改变')
    renderer.write_text(text.replace(needle, "'-threads','1','-b:v','20500k','-minrate','20500k','-maxrate','20500k','-bufsize','2000k','-x264-params','nal-hrd=cbr:force-cfr=1:filler=1'"), encoding='utf8')
    tools = Path(request['tool_root'])
    e._command([tools / 'node/node.exe', e.TEMPLATE / 'capture_runtime.mjs', generated,
        dependencies / 'node_modules/playwright-core', tools / 'browser/chrome-headless-shell.exe', generated / 'sfx.json'], folder, request, 'capture-observed-runtime')
    e._command([sys.executable, '-X', 'utf8', '-B', upstream / 'scripts/macro_audio.py', generated], folder, request, 'observed-sound')
    # The original voice remains the mix source; no extracted avatar audio enters.
    e.mix_audio(project, folder, request)
    files = {p.relative_to(folder).as_posix(): sha(p) for directory in (generated, upstream) for p in directory.rglob('*') if p.is_file()}
    receipt = {'schema': 'haike.observed-quote-controls-prepared/3', 'request_sha256': request['request_sha256'], 'files': files,
        'font_report': {'NotoSansSC.ttf': sha(fonts / 'NotoSansSC.ttf'), **{name: digest for digest, name in required_fonts.items()},
            'license': 'OFL with retained original notices; reference glyph/layout comparison pending', 'poster_original_cjk_woff2_identity': 'not_acquired'},
        'original_fidelity': 'pending', 'all_original_controls_supported': False}
    atomic_private(folder / 'prepared.json', receipt)
    return receipt
