"""Reusable content preparation for the signed native film and 4:5 story bridge.

This module prepares local assets and public parameters. It never generates a
voice/avatar, publishes, or performs a full render. The existing parent queue
remains the sole full-film producer.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'templates/motiongit-native-story-v1/profile.json'
SCHEMA = 'haike.motion-native-content/1'
BUILD_SCHEMA = 'haike.motion-native-content-build/1'
REQUIRED = {'schema', 'template_id', 'title', 'brand', 'short_title', 'presenter_label',
            'layout', 'voice', 'captions', 'avatar', 'media', 'content', 'music', 'tools',
            'source_review', 'provenance'}
OPTIONAL = {'timeline', 'fonts', 'sfx', 'native_dependency_cache', 'native_instance_root'}
TOOLS = {'node', 'helper', 'package', 'ffmpeg', 'ffprobe'}
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def number(value):
    return type(value) in {int, float} and math.isfinite(value)


def asset(value, parent):
    require(isinstance(value, dict) and set(value) == {'path', 'sha256'}, '资产须包含path和sha256')
    require(isinstance(value['path'], str) and re.fullmatch('[a-f0-9]{64}', str(value['sha256'])), '资产路径或SHA无效')
    path = Path(value['path'])
    path = (path if path.is_absolute() else parent / path).resolve()
    require(path.is_file() and sha(path) == value['sha256'], '资产文件缺失或SHA变化，请保留原任务后核对输入')
    return {'path': str(path), 'sha256': value['sha256']}


def _run(command, *, env=None):
    result = subprocess.run([str(v) for v in command], capture_output=True,
                            creationflags=NO_WINDOW, env=env)
    require(result.returncode == 0, '本地媒体或官方准备命令失败；原日志与中间文件保留，请核对本次输入')
    return result.stdout


def _probe(tool, path):
    data = json.loads(_run([tool, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path]))
    return {'seconds': float(data.get('format', {}).get('duration', 0)),
            'video': next((s for s in data.get('streams', []) if s['codec_type'] == 'video'), None),
            'audio': next((s for s in data.get('streams', []) if s['codec_type'] == 'audio'), None)}


def _clock(path):
    with wave.open(str(path), 'rb') as stream:
        require(stream.getcomptype() == 'NONE' and stream.getsampwidth() == 2
                and stream.getnchannels() == 1 and stream.getframerate() in {24000, 48000},
                '口播须为完整24k或48k单声道PCM16 WAV')
        count, rate = stream.getnframes(), stream.getframerate()
        require(count > 0, '口播音频为空')
    return {'samples': count, 'sample_rate': rate, 'channels': 1, 'sample_width': 2,
            'duration_seconds': count / rate}


def _voice_proof(proof, digest):
    return any(proof.get(k) == digest for k in ['voice_sha256', 'source_voice_sha256',
               'original_audio_sha256', 'original_full_voice_sha256', 'original_voice_sha256'])


def _captions(value, parent, voice, seconds):
    require(isinstance(value, dict) and set(value) == {'path', 'sha256', 'voice_sha256', 'provenance'},
            '字幕须绑定完整原声SHA及真实词时码来源')
    source = asset({k: value[k] for k in ['path', 'sha256']}, parent)
    require(value['voice_sha256'] == voice['sha256'], '字幕与口播SHA不匹配')
    proof = asset(value['provenance'], parent)
    provenance = read(proof['path'])
    require(isinstance(provenance, dict) and _voice_proof(provenance, voice['sha256']), '词时码来源未绑定本期完整口播')
    captions = read(source['path'])
    require(isinstance(captions, list) and captions, '字幕须为非空原生数组')
    previous, all_words = 0., []
    for row in captions:
        require(isinstance(row, dict) and {'t0', 't1', 'zh', 'en', 'highlight'} <= set(row), '原生字幕字段不完整')
        a, b = row['t0'], row['t1']
        require(number(a) and number(b) and previous <= a < b <= seconds + .001, '字幕时间须在完整原声时钟内连续有序')
        require(all(isinstance(row[k], str) and row[k].strip() and '\n' not in row[k] for k in ['zh', 'en']),
                '中英文字幕须为真实短句且各一明确行')
        h = row['highlight']
        require(isinstance(h, dict) and h.get('source') in {'asr-word-boundaries', 'verified-word-boundaries'}
                and h.get('language') == 'zh' and isinstance(h.get('units'), list) and h['units'], '字幕缺少真实逐词时码')
        last = a
        for word in h['units']:
            require(isinstance(word, dict) and set(word) == {'text', 'start', 'end'}
                    and isinstance(word['text'], str) and word['text'] and number(word['start']) and number(word['end'])
                    and last - .001 <= word['start'] <= word['end'] <= b + .001, '逐词时码或内容越过原句边界')
            last = word['end']
        require(''.join(w['text'] for w in h['units']) == row['zh'], '字幕逐词文本须完整等于原句，不估算或遗漏标点')
        all_words.extend(h['units'])
        previous = b
    if isinstance(provenance.get('words'), list):
        require(provenance['words'] == all_words, '字幕与已绑定的原始ASR词记录不同')
    return {**source, 'voice_sha256': voice['sha256'], 'provenance': proof}, captions


def _distribute(parts, extra):
    """Only quiet intervals receive hold frames; protected spans stay exactly 1x."""
    while extra:
        available = [p for p in parts if p['kind'] == 'quiet' and p['frames'] < p['maximum']]
        require(available, '口播过长：本三组模板的静止间隔容量不足，请选择更多完整动作组')
        weights = sum(p['to'] - p['from'] for p in available)
        wanted = [(p, extra * (p['to'] - p['from']) / weights) for p in available]
        used = 0
        for p, amount in wanted:
            addition = min(p['maximum'] - p['frames'], math.floor(amount))
            p['frames'] += addition
            used += addition
        extra -= used
        if extra:
            eligible = [(p, amount - math.floor(amount)) for p, amount in wanted if p['frames'] < p['maximum']]
            for p, _ in sorted(eligible, key=lambda item: item[1], reverse=True):
                if not extra:
                    break
                p['frames'] += 1
                extra -= 1


def timeline(profile, voice_seconds, value, layout):
    require(isinstance(value, dict) and not set(value) - {'tail_seconds', 'group_frames'}, '时间设置字段无效')
    tail = value.get('tail_seconds', .25)
    require(number(tail) and 0 <= tail <= 2, '尾白须为0至2秒')
    frames = math.ceil((voice_seconds + tail) * 5 - 1e-9) * 12
    require(360 <= frames <= 36000, '完整片须在6至600秒范围内')
    if layout == 'portrait45':
        require('group_frames' not in value, '真4:5由项目排版引擎按实际口播分配完整组，不接受原生横版组帧数')
        require(frames >= 1680, '真4:5三组完整排版需要至少28秒；请使用更短的完整动作组合')
        require(frames / 60 - voice_seconds <= 2 + 1e-9, '帧对齐后的非语音尾部不得超过2秒')
        return {'fps': 60, 'frames': frames, 'seconds': frames / 60,
                'groups': [{'id': g['id'], 'native_id': g['native_id']} for g in profile['groups']],
                'timing_authority': 'studio_native_story_portrait', 'native_clock_available': False}
    baseline = sum(g['baseline_frames'] for g in profile['groups'])
    frames = max(frames, baseline)
    explicit = value.get('group_frames')
    if explicit is not None:
        require(isinstance(explicit, list) and len(explicit) == len(profile['groups'])
                and all(type(v) is int and v >= g['baseline_frames'] for v, g in zip(explicit, profile['groups'])),
                '原生逐组帧数不能短于已验的完整动作基线')
        frames = sum(explicit)
        require(frames % 12 == 0 and frames <= 36000 and frames / 60 >= voice_seconds, '原生全片须精确对齐25/60fps共同帧时钟且完整覆盖口播')
    require(0 <= frames / 60 - voice_seconds <= 2 + 1e-9, '本三组动作不能容纳过短口播；不快放或编造长尾白')
    groups = []
    all_parts = []
    for i, g in enumerate(profile['groups']):
        parts = [{**p, 'frames': p['baseline_frames'], 'maximum': g['max_quiet_frames']}
                 for p in g['clock_parts']]
        if explicit is not None:
            _distribute(parts, explicit[i] - g['baseline_frames'])
        groups.append((g, parts))
        all_parts.extend(parts)
    if explicit is None:
        _distribute(all_parts, frames - baseline)
    output, cursor = [], 0
    for g, parts in groups:
        current = 0
        for p in parts:
            p['target_from'] = current
            current += p['frames']
        anchors = {}
        for name, source_frame in g['cues'].items():
            part = next(p for p in parts if p['from'] <= source_frame <= p['to'])
            anchors[name] = part['target_from'] + round((source_frame - part['from']) * part['frames'] / (part['to'] - part['from']))
        output.append({'id': g['id'], 'native_id': g['native_id'], 'from': cursor,
                       'frames': current, 'anchors': anchors, 'clock_parts': parts})
        cursor += current
    require(cursor == frames, '动作调度与完整口播时钟不一致')
    return {'fps': 60, 'frames': frames, 'seconds': frames / 60, 'groups': output,
            'timing_authority': 'official_native_public_anchors', 'native_clock_available': True}


def check(input_path):
    """Read/probe only: no output writes, provider calls, queue jobs or rendering."""
    input_path = Path(input_path).resolve()
    parent, value, profile = input_path.parent, read(input_path), read(PROFILE)
    require(isinstance(value, dict) and REQUIRED <= set(value) and not set(value) - REQUIRED - OPTIONAL,
            '通用输入字段不完整或存在未知字段')
    require(value['schema'] == SCHEMA and value['template_id'] == profile['template_id'], '输入模板版本不匹配')
    for key, maximum in [('title', 100), ('brand', 60), ('short_title', 30), ('presenter_label', 30)]:
        require(isinstance(value[key], str) and 0 < len(value[key].strip()) <= maximum, '标题、品牌或人物标识为空或过长')
    require(value['layout'] in {'landscape', 'portrait45'}, '画幅仅支持原生横版或项目真4:5重排')
    provenance = value['provenance']
    require(isinstance(provenance, dict) and set(provenance) == {'source', 'authorized'}
            and provenance['authorized'] is True and isinstance(provenance['source'], str)
            and 3 <= len(provenance['source'].strip()) <= 500, '须明确本期口播与素材的授权来源')
    require(isinstance(value['tools'], dict) and set(value['tools']) == TOOLS, '须显式绑定当前授权包及本机工具链')
    tools = {k: asset(v, parent) for k, v in value['tools'].items()}
    voice = asset(value['voice'], parent)
    clock = _clock(voice['path'])
    captions, caption_rows = _captions(value['captions'], parent, voice, clock['duration_seconds'])
    plan = timeline(profile, clock['duration_seconds'], value.get('timeline', {}), value['layout'])
    a = value['avatar']
    require(isinstance(a, dict) and set(a) == {'path', 'sha256', 'voice_sha256', 'evidence', 'badge', 'same_voice_verified'}
            and a['same_voice_verified'] is True, '人物须提供完整视频、已验证的同声源证据与方形头像')
    avatar = {**asset({k: a[k] for k in ['path', 'sha256']}, parent),
              'voice_sha256': a['voice_sha256'], 'evidence': asset(a['evidence'], parent), 'badge': asset(a['badge'], parent)}
    proof = read(avatar['evidence']['path'])
    require(a['voice_sha256'] == voice['sha256'] and _voice_proof(proof, voice['sha256'])
            and any(proof.get(k) == avatar['sha256'] for k in ['video_sha256', 'sha256'])
            and proof.get('full_decode') == 'passed', '人物证据未证明本期完整同声源、视频SHA或完整解码')
    actual_review = proof.get('actual_view_status', proof.get('actual_six_frame_review', proof.get('actual_review')))
    require(actual_review in {'pass', 'passed-scoped', 'pass-scoped', 'pass-six-representative-frames'},
            '人物源尚未完成实际代表帧审查；时长和SHA不能替代看帧')
    avatar['same_voice_verified'] = True
    avatar['validated_evidence'] = {'source_voice_sha256': voice['sha256'], 'video_sha256': avatar['sha256'],
            'full_decode': 'passed', 'actual_review': actual_review,
            'review_path': avatar['evidence']['path'], 'review_sha256': avatar['evidence']['sha256'],
            'frames': proof.get('frames'), 'fps': proof.get('fps'),
            'scope': proof.get('review_scope', 'Upstream representative-frame review; continuous phoneme/listening not claimed.')}
    info = _probe(tools['ffprobe']['path'], avatar['path'])
    require(info['video'] and info['audio'] and info['seconds'] + .001 >= plan['seconds'], '人物视频不能完整覆盖成片时钟；禁止循环短缓存')
    from PIL import Image
    with Image.open(avatar['badge']['path']) as badge:
        require(badge.width == badge.height, '人物品牌头像须为明确裁切的本期方形图')
    media = value['media']
    require(isinstance(media, dict) and set(media) == {'wall', 'categories', 'lens'}, '素材须包含实拍墙、四卡封面和连续镜头')
    probe_cache = {}
    def view(v):
        require(isinstance(v, dict) and set(v) == {'id', 'source', 'at'}
                and isinstance(v['id'], str) and re.fullmatch('[A-Za-z0-9_-]{1,80}', v['id']), '素材选帧须有稳定ID、源文件和真实时间')
        source = asset(v['source'], parent)
        require(number(v['at']) and v['at'] >= 0, '素材选帧时间无效')
        suffix = Path(source['path']).suffix.lower()
        image = suffix in {'.jpg', '.jpeg', '.png', '.webp'}
        if image:
            require(v['at'] == 0, '图片时间须为0')
        else:
            if source['path'] not in probe_cache:
                probe_cache[source['path']] = _probe(tools['ffprobe']['path'], source['path'])
            require(probe_cache[source['path']]['video'] and v['at'] < probe_cache[source['path']]['seconds'], '选帧越过真实视频范围')
        return {'id': v['id'], 'source': source, 'at': v['at'], 'kind': 'image' if image else 'video-frame'}
    require(isinstance(media['wall'], list) and 4 <= len(media['wall']) <= 64, '实拍墙须有4至64个真实选帧')
    wall = [view(v) for v in media['wall']]
    require(len({v['id'] for v in wall}) == len(wall), '墙选帧ID重复')
    require(isinstance(media['categories'], list) and len(media['categories']) == 4, '四卡须恰好4个真实封面')
    categories = [view(v) for v in media['categories']]
    lens = media['lens']
    require(isinstance(lens, dict) and set(lens) == {'id', 'source', 'offset'}
            and isinstance(lens['id'], str) and re.fullmatch('[A-Za-z0-9_-]{1,80}', lens['id'])
            and number(lens['offset']) and lens['offset'] >= 0, '镜头素材须指定源、稳定ID与真实入点')
    lens_source = asset(lens['source'], parent)
    lens_info = _probe(tools['ffprobe']['path'], lens_source['path'])
    lens_seconds = profile['lens']['sequence_frames'] / profile['lens']['sequence_fps']
    require(lens_info['video'] and lens_info['seconds'] + .001 >= lens['offset'] + lens_seconds,
            '连续镜头素材不足12.3秒；不循环、不冻结或变速补齐')
    source_review = asset(value['source_review'], parent)
    source_data = read(source_review['path'])
    require(source_data.get('schema') == 'haike.motion-native-source-review/1'
            and source_data.get('status') == 'pass' and isinstance(source_data.get('materials'), list),
            '须提供本期实际看过的素材帧与源区间审核，不自动把生成资产视为已审')
    def source_check(digest, start, end):
        candidates = [r for r in source_data['materials'] if isinstance(r, dict) and r.get('source_sha256') == digest
                      and number(r.get('source_start_seconds')) and number(r.get('source_end_seconds'))
                      and r['source_start_seconds'] <= start + .000001 and r['source_end_seconds'] + .000001 >= end]
        require(candidates, '所选素材或连续镜头超出实际查看的源区间')
        r = candidates[0]
        require(isinstance(r.get('description'), str) and len(r['description'].strip()) >= 3
                and isinstance(r.get('observed_frames'), list) and r['observed_frames']
                and all(number(t) and r['source_start_seconds'] <= t <= r['source_end_seconds'] for t in r['observed_frames'])
                and isinstance(r.get('actual_images_viewed'), list) and r['actual_images_viewed'], '素材审核缺少语义描述或实际帧位置')
        for image in r['actual_images_viewed']:
            asset(image, Path(source_review['path']).parent)
        return {'reviewed': True, 'description': r['description'], 'source_start_seconds': r['source_start_seconds'],
                'source_end_seconds': r['source_end_seconds'], 'observed_frames': r['observed_frames'],
                'review_evidence': source_review}
    for item in wall + categories:
        item['review'] = source_check(item['source']['sha256'], item['at'], item['at'])
    lens_review = source_check(lens_source['sha256'], lens['offset'], lens['offset'] + lens_seconds)
    contents = value['content']
    require(isinstance(contents, dict) and set(contents) == {g['id'] for g in profile['groups']}, '须提供三组完整公开内容槽')
    for g in profile['groups']:
        content = contents[g['id']]
        require(isinstance(content, dict) and set(content) == {f['inputPath'] for f in g['fields']}, '内容槽缺失或包含未开放字段')
        for field in g['fields']:
            item = content[field['inputPath']]
            if field['type'] == 'number':
                require(number(item) and 1 <= item <= 1000, '动作数字必须为本期已核验、有限的正数')
            else:
                require(isinstance(item, str) and item.strip() and len(item) <= field.get('maxChars', 100)
                        and '\n' not in item and '<' not in item and '>' not in item, '文案为空、过长、含换行或HTML，请缩写后复核')
    m = value['music']
    require(isinstance(m, dict) and set(m) == {'path', 'sha256', 'gainDb', 'offsetSeconds', 'loop'}, '须冻结唯一配乐与混音设置')
    music = {**asset({k: m[k] for k in ['path', 'sha256']}, parent),
             **{k: m[k] for k in ['gainDb', 'offsetSeconds', 'loop']}}
    require(number(m['gainDb']) and -40 <= m['gainDb'] <= -3 and number(m['offsetSeconds'])
            and m['offsetSeconds'] >= 0 and type(m['loop']) is bool and music['sha256'] != voice['sha256'], '配乐设置无效或重复绑定口播')
    music_info = _probe(tools['ffprobe']['path'], music['path'])
    require(music_info['audio'] and m['offsetSeconds'] < music_info['seconds']
            and (m['loop'] or m['offsetSeconds'] + plan['seconds'] <= music_info['seconds'] + .001), '配乐长度不足且未显式声明循环')
    extras = {}
    if 'native_instance_root' in value:
        native_root = Path(value['native_instance_root']) if isinstance(value['native_instance_root'], str) else Path('.')
        require(value['layout'] == 'landscape' and native_root.is_absolute()
                and len(str(native_root)) <= 110 and native_root.parent.is_dir()
                and not native_root.is_symlink() and not native_root.is_junction(),
                '原生实例需使用110字符以内的绝对短缓存路径，父目录须存在；旧实例保留')
        extras['native_instance_root'] = str(native_root.resolve())
    if 'native_dependency_cache' in value:
        require(isinstance(value['native_dependency_cache'], str), '原生依赖缓存须为明确的本机目录')
        cache = Path(value['native_dependency_cache'])
        cache = cache if cache.is_absolute() else parent / cache
        receipt = cache / 'dependencies.json'
        require(cache.is_dir() and not cache.is_symlink() and receipt.is_file() and not receipt.is_symlink(),
                '已有原生依赖缓存须有真实官方签收文件；缺失时省略该字段准备新隔离缓存')
        dependency = read(receipt)
        require(isinstance(dependency, dict) and dependency.get('schema') == 'motiongit-dependencies/1'
                and all(re.fullmatch('[a-f0-9]{64}', str(dependency.get(k))) for k in
                        ['runtimeLockSha256', 'npmLockSha256', 'pythonRequirementsSha256']),
                '原生依赖缓存签收格式不匹配，不能自行伪造或修改')
        extras['native_dependency_cache'] = {'path': str(cache.resolve()), 'receipt_sha256': sha(receipt)}
    for name, keys in [('fonts', {'body', 'display'}), ('sfx', {'tick', 'whoosh', 'dong'})]:
        require(value['layout'] != 'portrait45' or name in value, '真4:5需显式绑定字体与三种动作音效')
        if name in value:
            require(isinstance(value[name], dict) and set(value[name]) == keys, '字体或音效字段不完整')
            extras[name] = {k: asset(v, parent) for k, v in value[name].items()}
    result = {k: value[k] for k in ['template_id', 'title', 'brand', 'short_title', 'presenter_label', 'layout']}
    result.update(schema=BUILD_SCHEMA, input_path=str(input_path), input_sha256=sha(input_path),
                  profile_sha256=sha(PROFILE), adapter_sha256=sha(__file__), tools=tools,
                  voice={**voice, 'clock': clock, 'provenance': provenance}, captions={**captions, 'method': 'actual-word-boundaries'}, avatar=avatar,
                  timeline=plan, content=deepcopy(contents), music=music,
                  media={'wall': wall, 'categories': categories,
                         'lens': {'id': lens['id'], **lens_source, 'offset': lens['offset'], 'seconds': lens_seconds, 'review': lens_review}},
                  source_review=source_review, provenance=provenance,
                  **extras)
    return result, caption_rows


def _contain(image, size):
    from PIL import Image, ImageOps
    canvas = Image.new('RGB', size, '#071018')
    fitted = ImageOps.contain(image.convert('RGB'), size, Image.Resampling.LANCZOS)
    canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    return canvas


def _put(tree, path, value):
    parts, node = path.split('.'), tree
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _native_params(built, captions):
    require(built['timeline']['native_clock_available'], '真4:5请进入项目重排桥接，不能用横版原生参数假装适配')
    profile = read(PROFILE)
    fulltext = ''.join(c['zh'] for c in captions)
    text_sha = hashlib.sha256(fulltext.encode('utf-8')).hexdigest()
    units, segments, offset = [], [], 0
    for g, shot in zip(profile['groups'], built['timeline']['groups']):
        text = ''.join(c['zh'] for c in captions if shot['from'] / 60 <= c['t0'] < (shot['from'] + shot['frames']) / 60)
        require(text, '某完整动作组没有对应真实台词，请调整分段或换模板')
        unit = {'id': f'{text_sha[:16]}:{offset}:{offset + len(text)}', 'start': offset, 'end': offset + len(text), 'text': text}
        offset += len(text)
        units.append(unit)
        flat = deepcopy(built['content'][g['id']])
        if g['id'] == 's01':
            flat['evidence.wall'] = {'path': 'media/wall', 'glob': '*.jpg'}
        elif g['id'] == 's04':
            for index in range(4):
                flat[f'categories.{index}.media'] = {'path': f'media/category-{index}', 'fps': 30,
                                                    'entityId': built['media']['categories'][index]['id']}
            flat.update({'wall.media': {'path': 'media/wall', 'glob': '*.jpg'},
                         'wall.icon': 'presenter-square.jpg', 'lens.media': {'path': 'media/lens', 'fps': 30,
                         'entityId': built['media']['lens']['id']}})
        else:
            flat['brand.avatar'] = 'presenter-square.jpg'
        inputs = {}
        for key, item in flat.items():
            _put(inputs, key, item)
        segments.append({'id': 'story-' + g['id'], 'text': text, 'intent': g['intent'], 'phases': g['phases'],
                         'counts': g['counts'], 'durationFrames': shot['frames'],
                         'anchors': {k: {'frame': v} for k, v in shot['anchors'].items()},
                         'ownershipRefs': [unit['id']], 'supportingRefs': {k: [unit['id']] for k in flat},
                         'preferredScenes': [g['native_id']], 'candidates': {g['native_id']: {'inputs': inputs}}})
    require(''.join(u['text'] for u in units) == fulltext, '真实字幕所有句子须完整进入内容证据')
    return {'media': {'talk': 'talk.mp4', 'captions': 'captions.json'}, 'brief': {
        'schema': 'adu-auto-brief/1', 'brand': built['brand'], 'layout': 'landscape',
        'narrationDuration': built['timeline']['seconds'], 'allowedStyles': ['03-A'],
        'fontPolicy': 'preferred', 'repairPolicy': {'mode': 'off'}, 'presenterLabel': built['presenter_label'],
        'header': {'shortTitle': built['short_title'], 'source': {'kind': 'assistant-summary', 'field': 'brief.contentEvidence.text'}},
        'contentEvidence': {'schema': 'adu-content-evidence/1', 'text': fulltext, 'textSha256': text_sha,
                            'sourceKind': 'Complete same-source measured captions; all text and word timings unchanged.', 'units': units},
        'segments': segments, 'music': {'mode': 'none'}}}


def build(input_path, destination):
    """Build deterministic local slots; no cloud calls, queue submission or render."""
    from PIL import Image
    built, captions = check(input_path)
    destination = Path(destination).resolve()
    receipt_path = destination / 'content-build.json'
    if receipt_path.exists():
        previous = load_build(receipt_path)
        require(previous['input_sha256'] == built['input_sha256'], '已有准备目录属于其他输入，请保留后另建版本')
        return previous
    require(not destination.exists() or not any(destination.iterdir()), '已有未完成准备目录，请保留并核对原记录')
    destination.mkdir(parents=True, exist_ok=True)
    inputs = destination / 'inputs'
    media = inputs / 'media'
    media.mkdir(parents=True)
    ff = built['tools']['ffmpeg']['path']
    def frame(source, at, target):
        if Path(source).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}:
            Image.open(source).convert('RGB').save(target, quality=95)
        else:
            _run([ff, '-nostdin', '-y', '-v', 'error', '-ss', at, '-i', source, '-frames:v', 1, '-q:v', 2, target])
    views = []
    for index, item in enumerate(built['media']['wall']):
        target = media / f'view-{index:02}.jpg'
        frame(item['source']['path'], item['at'], target)
        views.append({**item, 'path': str(target), 'sha256': sha(target)})
    collages, folder = [], media / 'wall-collages'
    folder.mkdir()
    for index in range(len(views) * 3):
        lead, kind = index % len(views), index // len(views)
        picks = [lead, (lead + 2 + kind) % len(views), (lead + 5) % len(views), (lead + 7 + kind) % len(views)]
        boxes = [[(4, 4, 632, 352), (644, 4, 632, 352), (4, 364, 632, 352), (644, 364, 632, 352)],
                 [(4, 4, 760, 712), (776, 4, 500, 352), (776, 364, 500, 352)],
                 [(4, 4, 416, 712), (432, 4, 416, 712), (860, 4, 416, 712)]][kind]
        image = Image.new('RGB', (1280, 720), '#071018')
        for pick, (x, y, w, h) in zip(picks, boxes):
            with Image.open(views[pick]['path']) as source:
                image.paste(_contain(source, (w, h)), (x, y))
        target = folder / f'collage-{index:03}.jpg'
        image.save(target, quality=94)
        collages.append({'id': f'photo-collage-{index:03}', 'path': str(target), 'sha256': sha(target),
                         'view_ids': [views[i]['id'] for i in picks[:len(boxes)]], 'kind': 'photo-collage-derivative'})
    wall = media / 'wall'
    wall.mkdir()
    count = read(PROFILE)['wall']['display_sheets']
    for i in range(count):
        with Image.open(collages[i % len(collages)]['path']) as source:
            cell = source.resize((160, 90), Image.Resampling.LANCZOS)
        image = Image.new('RGB', (640, 360))
        for y in range(4):
            for x in range(4):
                image.paste(cell, (x * 160, y * 90))
        image.save(wall / f'{i:03}.jpg', quality=94)
    index = [{'id': i, 'file': f'{i:03}.jpg', 'path': f'{i:03}.jpg', 'slug': collages[i % len(collages)]['id'],
              'entityId': collages[i % len(collages)]['id'], 'sourceIndex': i % len(collages),
              'width': 640, 'height': 360, 'frames': 16, 'columns': 4, 'rows': 4, 'frameWidth': 160, 'frameHeight': 90}
             for i in range(count)]
    write(wall / 'index.json', index)
    write(wall / 'wall-meta.json', {'uniqueWorks': len({c['sha256'] for c in collages}),
          'uniqueCount': len({c['sha256'] for c in collages}), 'realCount': len(collages),
          'sourceCount': len({v['source']['sha256'] for v in views}), 'distinctObservedViews': len(views),
          'collageDesigns': len(collages), 'displayCount': count, 'spriteCount': count,
          'sheetColumns': 4, 'sheetRows': 4, 'framesPerSheet': 16,
          'provenance': 'Photo collage derivatives of explicit source views; repeated display sheets are not independent camera clips.'})
    built['media']['wall'] = {'directory': str(wall), 'index': str(wall / 'index.json'),
          'manifest': str(wall / 'wall-meta.json'), 'views': views, 'collages': collages, 'display_sheets': count}
    categories = []
    for i, item in enumerate(built['media']['categories']):
        target = media / f'category-{i}-cover.jpg'
        frame(item['source']['path'], item['at'], target)
        with Image.open(target) as original:
            _contain(original, (1280, 720)).save(target, quality=95)
        sequence = media / f'category-{i}'
        sequence.mkdir()
        for j in range(1, 361):
            try:
                os.link(target, sequence / f'f_{j:04}.jpg')
            except OSError:
                shutil.copyfile(target, sequence / f'f_{j:04}.jpg')
        categories.append({**item, 'path': str(target), 'sha256': sha(target), 'sequence': str(sequence),
                           'fps': 30, 'frames': 360, 'kind': 'explicit-still-cover'})
    built['media']['categories'] = categories
    lens = built['media']['lens']
    sequence = media / 'lens'
    sequence.mkdir()
    _run([ff, '-nostdin', '-y', '-v', 'error', '-ss', lens['offset'], '-i', lens['path'],
          '-vf', 'fps=30,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x071018,setsar=1',
          '-frames:v', 369, '-q:v', 2, sequence / 'f_%04d.jpg'])
    require(len(list(sequence.glob('f_*.jpg'))) == 369, '连续实拍镜头解码帧数不足')
    lens.update(sequence=str(sequence), fps=30, frames=369)
    shutil.copyfile(built['avatar']['path'], inputs / 'talk.mp4')
    with Image.open(built['avatar']['badge']['path']) as badge:
        require(badge.width == badge.height, '人物方形头像须由本期实际形象明确裁切，不自动猜测人脸位置')
        badge.convert('RGB').resize((720, 720), Image.Resampling.LANCZOS).save(inputs / 'presenter-square.jpg', quality=96)
    built['avatar']['badge'] = {'path': str(inputs / 'presenter-square.jpg'), 'sha256': sha(inputs / 'presenter-square.jpg')}
    shutil.copyfile(built['captions']['path'], inputs / 'captions.json')
    built['captions'].update(path=str(inputs / 'captions.json'), sha256=sha(inputs / 'captions.json'))
    with wave.open(built['voice']['path'], 'rb') as source:
        params, data = source.getparams(), source.readframes(source.getnframes())
    samples = round(built['timeline']['seconds'] * params.framerate)
    padded = inputs / 'voice-padded.wav'
    with wave.open(str(padded), 'wb') as output:
        output.setparams(params)
        output.writeframes(data + b'\0' * (samples - params.nframes) * params.sampwidth)
    built['padded_voice'] = {'path': str(padded), 'sha256': sha(padded), 'clock': _clock(padded)}
    instance = Path(built.get('native_instance_root', destination / 'native-instance'))
    native = {'instance': str(instance), 'inputs': str(inputs),
              'params': str(destination / 'native-params.json'), 'plan': str(instance / 'plan'),
              'project': str(instance / 'project'), 'output_root': str(instance / 'renders')}
    built.update(status='built', directory=str(destination), native=native, cloud_calls=0, full_render_started=False)
    if built['layout'] == 'landscape':
        write(native['params'], _native_params(built, captions))
        built['next_entrypoint'] = 'Haike_video/scripts/dark_native_content.py native-plan --build <content-build.json>'
    else:
        built['next_entrypoint'] = 'Haike_video/scripts/native_story_portrait.py --build <content-build.json>'
    built['prepared_files'] = {p.relative_to(destination).as_posix(): sha(p) for p in sorted(inputs.rglob('*')) if p.is_file()}
    if Path(native['params']).is_file():
        built['prepared_files']['native-params.json'] = sha(native['params'])
    write(receipt_path, built)
    return built


def load_build(path):
    built = read(path)
    require(built.get('schema') == BUILD_SCHEMA and built.get('status') == 'built'
            and built['profile_sha256'] == sha(PROFILE) and built['adapter_sha256'] == sha(__file__), '准备输入的版本已变化，请保留原目录并准备新版本')
    require(sha(built['input_path']) == built['input_sha256'], '准备前后的通用输入已变化')
    for relative, digest in built['prepared_files'].items():
        target = (Path(built['directory']) / relative).resolve()
        require(target.is_relative_to(Path(built['directory'])) and target.is_file() and sha(target) == digest,
                '准备素材或参数已变化，请重新看帧并冻结新版本')
    for row in built['tools'].values():
        require(sha(row['path']) == row['sha256'], '本机工具或授权包已变化')
    if built.get('native_dependency_cache'):
        cache = built['native_dependency_cache']
        require(Path(cache['path']).is_dir() and sha(Path(cache['path']) / 'dependencies.json') == cache['receipt_sha256'],
                '已冻结的原生依赖缓存签收已变化，需保留原版本再核对官方setup')
    seen = set()
    def verify_assets(value, parent):
        if isinstance(value, dict):
            if isinstance(value.get('path'), str) and re.fullmatch('[a-f0-9]{64}', str(value.get('sha256'))):
                source = Path(value['path'])
                source = (source if source.is_absolute() else parent / source).resolve()
                identity = (source, value['sha256'])
                if identity not in seen:
                    require(source.is_file() and sha(source) == value['sha256'], '原声、数字人、素材或审核证据已变化')
                    seen.add(identity)
            for child in value.values():
                verify_assets(child, parent)
        elif isinstance(value, list):
            for child in value:
                verify_assets(child, parent)
    verify_assets(read(built['input_path']), Path(built['input_path']).parent)
    verify_assets(built, Path(built['directory']))
    return built


def _official(built, operation, arguments=()):
    require(built['layout'] == 'landscape', '真4:5须使用native_story_portrait项目重排桥接')
    require(operation in {'new', 'setup', 'doctor', 'check-params', 'plan', 'prepare', 'preview'}, '此入口仅支持准备和有界预览；整片必须进入统一队列')
    t, n = built['tools'], built['native']
    prefix = [t['node']['path'], t['helper']['path']]
    cache_path = built.get('native_dependency_cache', {}).get('path', str(Path(built['directory']) / 'native-dependencies'))
    cache = ['--cache', cache_path] if operation == 'setup' else []
    command = prefix + (['new', t['package']['path'], n['instance']] if operation == 'new' else
                        ['run', t['package']['path'], '--instance', n['instance'], *cache, operation, *map(str, arguments)])
    env = {**os.environ, 'PATH': str(Path(t['ffmpeg']['path']).parent) + os.pathsep + os.environ.get('PATH', ''),
           'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
    from backlot.studio_dark_native import _browser
    browser = _browser()
    if browser is not None: env['CHROME_PATH'] = str(browser)
    result = subprocess.run(command, capture_output=True, env=env, creationflags=NO_WINDOW)
    log = Path(built['directory']) / f'official-{operation}.log'
    log.write_bytes(result.stdout + result.stderr)
    require(result.returncode == 0, f'官方{operation}未完成；保留原实例并读取本期私有日志')


def native_plan(build_path):
    built = load_build(build_path)
    n = built['native']
    if not Path(n['instance']).exists():
        _official(built, 'new')
    for operation in ['setup', 'doctor']:
        _official(built, operation, ['--language', 'zh'])
    _official(built, 'check-params', [n['params'], '--inputs', n['inputs'], '--language', 'zh'])
    if not (Path(n['plan']) / 'report.json').exists():
        _official(built, 'plan', [n['params'], '--inputs', n['inputs'], '--out', n['plan'], '--language', 'zh'])
    report = read(Path(n['plan']) / 'report.json')
    require(report.get('ready') is True and report.get('durationFrames') == built['timeline']['frames']
            and report.get('selectedScenes') == [g['native_id'] for g in built['timeline']['groups']]
            and not report.get('blocking') and not report.get('missing') and not report.get('deferred'), '官方计划尚未ready，不能准备或渲染')
    capability = read(Path(n['plan']) / 'capabilities.json')
    actual = {g['id']: g for g in capability['groups']}
    require(all(actual[g['native_id']]['manifestDigest'] == g['manifest_digest'] for g in read(PROFILE)['groups']),
            '当前授权包与已适配公开契约不同，请先适配新包')
    return {'status': 'plan_ready_awaiting_actual_plan_review', 'plan': n['plan'],
            'plan_inputs_sha256': sha(Path(n['plan']) / 'inputs.json'), 'cloud_calls': 0}


def native_prepare(build_path, review_path):
    built = load_build(build_path)
    n, review = built['native'], read(review_path)
    require(review.get('status') == 'pass' and review.get('actual_plan_inspected') is True
            and review.get('plan_inputs_sha256') == sha(Path(n['plan']) / 'inputs.json'), '须实际核对本期计划与源素材后提供绑定SHA的技术审核')
    source_views = review.get('actual_source_images_viewed', [])
    require(isinstance(source_views, list) and source_views, '本期真实素材代表帧尚未实际查看')
    allowed = {v['path']: v['sha256'] for v in built['media']['wall']['views'] + built['media']['categories']}
    require(all(isinstance(v, dict) and v.get('path') in allowed and allowed[v['path']] == v.get('sha256')
                and sha(v['path']) == v['sha256'] for v in source_views), '源素材看帧证据与准备版本不匹配')
    official_review = Path(n['plan']) / 'review.json'
    data = read(official_review)
    data['reviewed'] = True
    write(official_review, data)
    if not Path(n['project']).exists():
        _official(built, 'prepare', ['@vault', '--inputs', '@vault', '--plan', n['plan'], '--out', n['project'], '--language', 'zh'])
    return {'status': 'prepared_awaiting_actual_preview', 'project': n['project'], 'cloud_calls': 0}


def native_preview(build_path, times):
    built = load_build(build_path)
    require(isinstance(times, list) and 1 <= len(times) <= 12
            and all(number(v) and 0 <= v < built['timeline']['seconds'] for v in times), '有界预览须为全片内1至12个真实秒数')
    _official(built, 'preview', [built['native']['project'], '--times', ','.join(str(v) for v in times), '--language', 'zh'])
    return {'status': 'preview_created_unreviewed', 'preview': str(Path(built['native']['project']) / 'preview.json'), 'cloud_calls': 0}


def native_manifest(build_path, review_path):
    built = load_build(build_path)
    require(built['layout'] == 'landscape', '真4:5请进入项目重排桥接，不生成contain清单')
    n, review = built['native'], read(review_path)
    preview_path = Path(n['project']) / 'preview.json'
    preview = read(preview_path)
    target = Path(built['directory']) / 'native-queue-input.json'
    visual = Path(built['directory']) / 'native-visual-review.json'
    if target.exists():
        previous = read(visual)
        require(previous.get('source_review_sha256') == sha(review_path)
                and previous.get('preview_sha256') == sha(preview_path), '已有原生冻结审核不同，请保留原请求')
        return {'status': 'reviewed_queue_input_ready', 'manifest': str(target),
                'next_entrypoint': 'Haike_video/scripts/dark_native.py --input <native-queue-input.json>',
                'cloud_calls': 0, 'queue_submitted': False}
    require(review.get('status') == 'pass' and review.get('actual_images_viewed'), '最终原生预览尚未实际看帧')
    require(review.get('unreviewed_preview_sha256') == sha(preview_path), '实际看帧审核未绑定本期原始预览回执')
    pictures = review['actual_images_viewed']
    require(isinstance(pictures, list) and len(pictures) >= 5, '须查看至少五个本期原生关键状态')
    project = Path(n['project']).resolve()
    require(len({v.get('path') for v in pictures if isinstance(v, dict)}) == len(pictures), '最终看帧证据包含重复图片')
    for image in pictures:
        p = Path(image.get('path', '')).resolve()
        require(p.is_relative_to(project) and p.suffix.lower() in {'.png', '.jpg', '.jpeg'}
                and p.is_file() and sha(p) == image.get('sha256')
                and preview.get('stills', {}).get(p.relative_to(project).as_posix()) == image['sha256'],
                '最终看帧证据不是本期预览回执绑定的实际图片')
    preview['reviewed'] = True
    write(preview_path, preview)
    write(visual, {**review, 'preview_sha256': sha(preview_path), 'source_review_sha256': sha(review_path),
                   'review_scope': 'actual-images-only; no claim of continuous listening or user acceptance'})
    plan = Path(built['directory']) / 'native-plan-review.json'
    write(plan, {'status': 'technical-plan-reviewed', 'completeGroups': [g['native_id'] for g in built['timeline']['groups']],
                 'completeGroupFrames': {g['native_id']: g['frames'] for g in built['timeline']['groups']},
                 'frames': built['timeline']['frames'], 'seconds': built['timeline']['seconds']})
    manifest = {'title': built['title'], 'projectDirectory': n['project'], 'instanceDirectory': n['instance'],
                **{k: v['path'] for k, v in built['tools'].items()}, 'audio': built['voice']['path'],
                'previewReceipt': str(preview_path), 'visualReview': str(visual), 'planReview': str(plan),
                'outputRoot': n['output_root'], 'expected': {'width': 1920, 'height': 1080, 'fps': 60,
                    'frames': built['timeline']['frames'], 'seconds': built['timeline']['seconds']},
                'audio_mode': 'native_plus_music', 'music': {k: v for k, v in built['music'].items() if k != 'sha256'},
                'portrait_companion': False}
    write(target, manifest)
    return {'status': 'reviewed_queue_input_ready', 'manifest': str(target),
            'next_entrypoint': 'Haike_video/scripts/dark_native.py --input <native-queue-input.json>',
            'cloud_calls': 0, 'queue_submitted': False}
