"""Template 11 admission, exact-clock HQ bookends, and existing native renderer."""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from copy import deepcopy
from difflib import SequenceMatcher
from functools import lru_cache
import importlib.util
import json
import math
import re
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import wave

from PIL import Image, ImageDraw

from backlot.avatar_one_stop_policy import ROOT, digest, fingerprint, wav_duration, WORKFLOW_ID
from backlot.avatar_one_stop_tools import media_command, read, succeeded
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError

KIT = ROOT/'Haike_video/workflows/runninghub-high-quality'


@lru_cache(maxsize=1)
def hq_executor():
    spec = importlib.util.spec_from_file_location('haike_one_stop_hq_executor', KIT/'agent_cli.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical(text):
    from backlot.motion_replay_chromatic_production import canonical as normalize
    return normalize(text)


def local_source(path, expected):
    original = Path(path)
    windows = PureWindowsPath(path)
    migrated = ROOT/'_migration_external/original-paths'/windows.drive.rstrip(':')/Path(*windows.parts[1:])
    for candidate in (original, migrated):
        if candidate.is_file() and digest(candidate) == expected:
            return candidate.resolve()
    raise WorkError('原模板的授权素材尚未迁入本机，请由Agent补齐对应素材并继续原任务', 'missing')


def reference(value):
    config = read(value['policy']['default_script']['script_json'])
    source = config['provenance']
    path = Path(source['frozen_request'])
    if digest(path) != source['frozen_request_sha256']:
        raise WorkError('默认模板的原始分镜身份变化，请核对原始回执', 'conflict')
    result = read(path)
    if canonical(result['receipts']['script']['text']) != canonical(value['script']['text']):
        raise WorkError('本期原文已更换，需要Agent根据本期ASR准备独立分镜，不能套用旧稿锚点')
    return result


def word_map(old, new):
    def flatten(rows):
        text, owners = '', []
        for index, row in enumerate(rows):
            chunk = canonical(row['text'])
            text += chunk
            owners.extend([index]*len(chunk))
        return text, owners
    a, ao = flatten(old)
    b, bo = flatten(new)
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    if matcher.ratio() < .82:
        raise WorkError('新旧语音文字差异较大，请由Agent核对本期识别与原文，再准备语义锚点')
    votes = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            votes.setdefault(ao[block.a+offset], Counter())[bo[block.b+offset]] += 1
    mapping = {index: counts.most_common(1)[0][0] for index, counts in votes.items()}
    if not mapping:
        raise WorkError('没有可复用的语义锚点，请由Agent准备本期分镜')
    return mapping


def semantic_clock(old, new, mapping, old_end, new_end):
    # Piecewise interpolation between matched spoken words; the old overall
    # duration is never used as a playback-rate multiplier.
    points = {0: 0, old_end: new_end}
    for old_index, new_index in sorted(mapping.items()):
        for boundary in ('start', 'end'):
            x, y = round(old[old_index][boundary]*30), round(new[new_index][boundary]*30)
            if 0 < x < old_end:
                points[x] = max(0, min(new_end, y))
    xs = sorted(points)
    ys = [points[x] for x in xs]
    # Consecutive words can share boundaries; require a monotone real clock.
    if any(a > b for a, b in zip(ys, ys[1:])):
        raise WorkError('ASR时间顺序异常，请核对原识别结果')
    def clock(frame):
        if frame >= old_end:
            return new_end
        index = max(0, bisect_right(xs, frame)-1)
        return round(ys[index]+(frame-xs[index])/(xs[index+1]-xs[index])*(ys[index+1]-ys[index]))
    return clock


def allocate_clips(clips, start, end, sources, durations, candidates):
    """Cover a scene with real source frames, adding approved local alternatives."""
    selected, seen = [], set()
    capacity = 0
    for prototype in [*clips, *candidates]:
        name = prototype['src']
        identity = (sources[name]['sha256'], sources[name]['source_offset'])
        if identity in seen:
            continue
        seen.add(identity)
        available = math.floor(durations[name]*30+.01)-sources[name]['source_offset']
        if available < 30:
            continue
        selected.append((prototype, available))
        capacity += available
        if capacity >= end-start:
            break
    if capacity < end-start:
        raise WorkError('现有授权素材时长不足，请由Agent补充本期素材后继续，不能循环或冻尾')
    lengths = [max(1, min(available, math.floor((end-start)*available/capacity))) for _, available in selected]
    remainder = end-start-sum(lengths)
    for index, (_, available) in enumerate(selected):
        take = min(remainder, available-lengths[index])
        lengths[index] += take
        remainder -= take
    result, cursor = [], start
    for (prototype, _), frames in zip(selected, lengths):
        result.append({**deepcopy(prototype), 'from': cursor, 'to': cursor+frames,
                       'sourceFrom': sources[prototype['src']]['source_offset']})
        cursor += frames
    return result


def clean_captions(captions):
    rows = []
    for item in captions:
        row = {**item, 'text': item['text'].replace('\\"', '"').replace('\n', '')}
        if rows and (row['to']-row['from'] < 24 or rows[-1]['to']-rows[-1]['from'] < 24) and len(rows[-1]['text']+row['text']) <= 36:
            rows[-1].update(to=row['to'], text=rows[-1]['text']+row['text'])
        else:
            rows.append(row)
    for row in rows:
        text = row['text']
        if len(text) > 18:
            minimum = max(8, len(text)-18)
            choices = [i+1 for i, char in enumerate(text[:18]) if char in '，、；：——' and i+1 >= minimum]
            split = max(choices) if choices else max(minimum, min(18, (len(text)+1)//2))
            row['text'] = text[:split]+'\n'+text[split:]
    return rows


def propose(value, folder):
    original = reference(value)
    asr = read(folder/'asr.json')
    old = original['receipts']['asr']['metadata']['words']
    words = asr['metadata']['words']
    mapping = word_map(old, words)
    props = deepcopy(original['props'])
    total = math.ceil(wav_duration(folder/'narration.wav')*30)
    clock = semantic_clock(old, words, mapping, props['durationInFrames'], total)
    scenes = props['scenes']
    bounds = [0, *[clock(s['to']) for s in scenes[:-1]], total]
    # 0.2s cuts share integral 25fps and 30fps boundaries, without changing speech.
    bounds[1] = math.ceil(bounds[1]/6)*6
    bounds[-2] = math.floor(bounds[-2]/6)*6
    if not all(a < b for a, b in zip(bounds, bounds[1:])):
        raise WorkError('本期语音时长不适合原四幕分镜，请由Agent调整布局分段')
    for i, scene in enumerate(scenes):
        scene['from'], scene['to'] = bounds[i:i+2]
        knots = scene['knots']
        knots[0]['target'], knots[-1]['target'] = scene['from'], scene['to']
        for index, knot in enumerate(knots[1:-1], 1):
            anchor = knot['anchor']
            if anchor['kind'] == 'word' and anchor['index'] not in mapping and not canonical(old[anchor['index']]['text']):
                # Some ASR versions emit punctuation as a timed "word". Anchor
                # that pause to the nearest real spoken boundary, rather than
                # requiring the next ASR response to invent a punctuation row.
                when = old[anchor['index']][anchor['boundary']]
                _, old_index, boundary = min((abs(row[boundary]-when), i, boundary)
                    for i, row in enumerate(old) if i in mapping
                    for boundary in ('start', 'end'))
                anchor.update(index=old_index, boundary=boundary)
            if anchor['kind'] != 'word' or anchor['index'] not in mapping:
                raise WorkError('关键动作对应词缺失，请由Agent核对新ASR语义后重新绑定')
            anchor['index'] = mapping[anchor['index']]
            base = round(words[anchor['index']][anchor['boundary']]*30)
            target = max(knots[index-1]['target']+1, base+knot['offsetFrames'])
            target = min(scene['to']-(len(knots)-index-1), target)
            knot['target'], knot['offsetFrames'] = target, target-base
            if not -60 <= knot['offsetFrames'] <= 120:
                raise WorkError('本期动作锚点超出允许上下文，请由Agent调整分镜')
    sources, provenance, durations = {}, [], {}
    from backlot.motion_replay_chromatic_production import media_probe
    original_shots = {row['derived']: row for row in original['receipts']['media_origins']['shots']}
    limits_path = folder/'storyboard-source-limits.json'
    limits = read(limits_path) if limits_path.is_file() else {}
    if limits and limits.get('audio_sha256') != digest(folder/'narration.wav'):
        raise WorkError('素材精查范围不属于本期声音，请核对原检查记录', 'conflict')
    for name, raw in original_shots.items():
        try:
            path = local_source(raw['path'], raw['sha256'])
            offset = round(raw['range_seconds'][0]*30)
            approved_end = raw['range_seconds'][1]
        except WorkError:
            origin = original['origins'][name]
            path = local_source(origin['path'], origin['sha256'])
            offset = 0
            approved_end = float('inf')
        sources[name] = {'path': str(path), 'sha256': digest(path), 'source_offset': offset}
        durations[name] = min(media_probe(path)['duration'], approved_end)
        if name in limits.get('sources', {}):
            limit = limits['sources'][name]
            if (limit.get('sha256') != sources[name]['sha256'] or len(limit.get('reason', '')) < 8
                    or not offset/30 < limit['to_seconds'] <= durations[name]):
                raise WorkError('素材精查记录缺少匹配的来源、有效范围或检查结论')
            durations[name] = limit['to_seconds']
        provenance.append({**raw, 'selected_path': str(path), 'selected_sha256': digest(path)})
    candidates = [dict(src=name, objectPosition='50% 58%') for name in original_shots]
    for scene in scenes:
        for slot, clips in props['slots'][scene['id']].items():
            props['slots'][scene['id']][slot] = allocate_clips(clips, scene['from'], scene['to'], sources, durations, candidates)
    for caption in props['captions']:
        caption['from'], caption['to'] = clock(caption['from']), clock(caption['to'])
        if caption['from'] >= caption['to']:
            raise WorkError('本期字幕时间域过短，请由Agent重排真实字幕')
    props['captions'] = clean_captions(props['captions'])
    props['durationInFrames'] = total
    props['presenters'] = [dict(src='presenter-native30.mp4', **{'from': 0, 'to': bounds[1]}, sourceFrom=0, objectPosition='50% 35%'),
                           dict(src='presenter-native30.mp4', **{'from': bounds[-2], 'to': total}, sourceFrom=bounds[1], objectPosition='50% 35%')]
    medical = [c for c in props['captions'] if '体质' in c['text']]
    props['medicalFrom'] = max(0, min([clock(original['props']['medicalFrom'])]+[c['from'] for c in medical]))
    props['medicalTo'] = min(total, max([props['medicalFrom']+90, clock(original['props']['medicalTo'])]+[c['to'] for c in medical]))
    font = original['origins'][props['font']]
    font_path = local_source(font['path'], font['sha256'])
    sources[props['font']] = {'path': str(font_path), 'sha256': font['sha256']}
    mix = deepcopy(original['receipts']['mix'])
    music = local_source(mix['source_music'], mix['music_sha256'])
    mix['source_music'] = str(music)
    plan = {'schema': 'haike.avatar-one-stop-storyboard/1', 'script_sha256': value['script']['text_sha256'],
            'audio_sha256': digest(folder/'narration.wav'), 'asr_sha256': digest(folder/'asr.json'),
            'props': props, 'sources': sources, 'media_origins': provenance, 'mix': mix,
            'windows': [{'from': 0, 'to': bounds[1], 'sourceStartFrame': 0},
                        {'from': bounds[-2], 'to': total, 'sourceStartFrame': bounds[1]}],
            'original_request_sha256': original['request_sha256'], 'speech_stretched': False}
    validate_plan(value, folder, plan)
    atomic_private(folder/'storyboard-proposal.json', plan)


def validate_plan(value, folder, plan):
    from backlot.motion_replay_chromatic_suite_production import validate_props
    if (plan.get('schema') != 'haike.avatar-one-stop-storyboard/1'
            or plan.get('script_sha256') != value['script']['text_sha256']
            or plan.get('audio_sha256') != digest(folder/'narration.wav')
            or plan.get('asr_sha256') != digest(folder/'asr.json') or plan.get('speech_stretched') is not False):
        raise WorkError('本期分镜与原文、声音或识别身份不同', 'conflict')
    props = plan['props']
    if props['templateId'] != 'chromatic-six-11' or props['version'] != value['policy']['template']['version']:
        raise WorkError('一条龙当前需采用指定的动效模板11版本')
    # This validates only the proposed layout. A separate verified real avatar
    # receipt is mandatory again at actual production admission after HQ.
    receipts = {'script': value['script'], 'audio': value['stages']['narration']['result'],
                'asr': read(folder/'asr.json'), 'avatar': {'workflow_id': WORKFLOW_ID,
                    'instance_type': 'plus', 'api_type': 'NORMAL', 'status': 'verified',
                    'task_id': 'layout-validation-only', 'original_audio_sha256': plan['audio_sha256']}}
    validate_props(props, receipts)
    if props['durationInFrames'] != math.ceil(wav_duration(folder/'narration.wav')*30):
        raise WorkError('分镜时钟必须来自本期完整配音')
    expected_windows = [{'from': c['from'], 'to': c['to'], 'sourceStartFrame': c['sourceFrom']} for c in props['presenters']]
    if plan['windows'] != expected_windows or plan['windows'][0]['to'] % 6 or plan['windows'][1]['from'] % 6:
        raise WorkError('人物范围未对齐共同帧边界')
    for name, origin in plan['sources'].items():
        if Path(name).name != name or digest(origin['path']) != origin['sha256']:
            raise WorkError('分镜素材已经变化，请重新检查实际素材', 'conflict')
    from backlot.motion_replay_chromatic_production import media_probe
    probes = {name: media_probe(Path(source['path'])) for name, source in plan['sources'].items()
              if name != props['font']}
    for scene in props['slots'].values():
        for clips in scene.values():
            for clip in clips:
                source = plan['sources'][clip['src']]
                info = probes[clip['src']]
                if min(int((info.get('video') or {}).get(k, 0)) for k in ('width', 'height')) < 720:
                    raise WorkError('所选正式素材短边需至少720像素')
                if (clip['sourceFrom']+clip['to']-clip['from'])/30 > info['duration']+.035:
                    raise WorkError('素材不足以覆盖实际槽位，请挑选补充素材')
    return plan


def storyboard_evidence(plan, folder):
    """3fps source windows using template 11's actual 500:354 cover crop."""
    identity = fingerprint(plan)
    manifest = folder/'storyboard-evidence.json'
    if manifest.is_file():
        previous = read(manifest)
        if previous.get('plan_fingerprint') == identity and all(
                Path(s['path']).is_file() and digest(s['path']) == s['sha256'] for s in previous['sheets']):
            return previous
    directory = folder/'storyboard-evidence'/identity[:24]
    directory.mkdir(parents=True, exist_ok=True)
    windows = {}
    for scene in plan['props']['slots'].values():
        for clips in scene.values():
            for clip in clips:
                key = (clip['src'], clip['sourceFrom'], clip['objectPosition'])
                windows[key] = max(windows.get(key, 0), clip['to']-clip['from'])
    rows, sequences = [], []
    for index, ((name, source_start, focus), length) in enumerate(windows.items()):
        location = directory/f'window-{index:02d}'
        location.mkdir(exist_ok=True)
        x, y = [int(n)/100 for n in re.findall(r'\d+', focus)]
        crop = f'fps=3,scale=180:128:force_original_aspect_ratio=increase,crop=180:128:(iw-ow)*{x}:(ih-oh)*{y},setsar=1'
        media_command(['-ss', source_start/30, '-i', plan['sources'][name]['path'], '-t', length/30,
                       '-an', '-vf', crop, '-q:v', '2', location/'%03d.jpg'])
        frames = sorted(location.glob('*.jpg'))
        if len(frames) < max(1, math.floor(length/10)-1):
            raise WorkError('所选素材实际范围不足，请重新挑选素材')
        canvas = Image.new('RGB', (180*len(frames), 152), '#17243a')
        draw = ImageDraw.Draw(canvas)
        for i, path in enumerate(frames):
            with Image.open(path) as image:
                canvas.paste(image.convert('RGB'), (i*180, 0))
            draw.text((i*180+4, 132), f'{name} {source_start/30+i/3:.2f}s', fill='white')
        rows.append(canvas)
        sequences.append({'source': name, 'source_sha256': plan['sources'][name]['sha256'],
                          'from_seconds': source_start/30, 'to_seconds': (source_start+length)/30,
                          'object_position': focus, 'crop': '500:354', 'frames': len(frames)})
    sheets = []
    for offset in range(0, len(rows), 9):
        page = rows[offset:offset+9]
        canvas = Image.new('RGB', (max(row.width for row in page), 152*len(page)), '#17243a')
        for i, row in enumerate(page):
            canvas.paste(row, (0, i*152))
        path = directory/f'sources-{offset//9+1:02d}.jpg'
        canvas.save(path, quality=92)
        sheets.append({'path': str(path), 'sha256': digest(path), 'sequence_indices': list(range(offset, offset+len(page)))})
    result = {'schema': 'haike.avatar-one-stop-source-review/1', 'plan_fingerprint': identity,
              'sampling_fps': 3, 'sequences': sequences, 'sheets': sheets,
              'scope': 'actual selected source windows and template crop; separate from continuous motion/audio review'}
    atomic_private(manifest, result)
    return result


def recover_hq_downloads(executor, run):
    """Recover only existing SUCCESS artifacts through the original TLS URL.

    The immutable kit prefers an alternate CDN on Windows. If that CDN has a
    transport failure, the original object URL may still work. No create,
    upload, cancel, or task-ID mutation is performed by this recovery seam.
    """
    recovered = False
    for query_path in sorted(run.glob('segment_*/query.json')):
        case = query_path.parent
        ledger = read(case/'ledger.json')
        data = executor.body(read(query_path))
        if not ledger.get('task_id') or str(data.get('status', '')).upper() not in executor.SUCCESS:
            continue
        for row in data.get('results', []):
            node = str(row.get('nodeId', ''))
            kind = 'video.mp4' if node == '93' else 'native_checkpoint.png' if node.endswith('_107') else None
            if not kind or not row.get('url') or (case/kind).exists():
                continue
            try:
                from backlot.avatar_one_stop_download import windows_artifact
                if windows_artifact(executor,row,case/kind,case,ledger['task_id']):
                    recovered = True
                    continue
                executor.download(row['url'], case/kind)
            except Exception as error:
                # This optional original-URL fallback must not prevent the kit
                # from resuming its verified same-object CDN path.
                atomic_private(case/(kind+'.recovery-pending.json'), {'task_id': ledger['task_id'],
                    'node_id': node, 'error_class': type(error).__name__, 'new_generation': False,
                    'tls_verification': True})
                continue
            atomic_private(case/(kind+'.download.json'), {'task_id': ledger['task_id'], 'node_id': node,
                'source_query_sha256': digest(query_path), 'url_sha256': fingerprint(row['url']),
                'sha256': digest(case/kind), 'original_url': True, 'tls_verification': True,
                'new_generation': False, 'recovery': 'original object URL after alternate CDN failure'})
            recovered = True
    return recovered


def record_hq_usage(ledger, run, save):
    task_ids, costs = [], []
    for path in sorted(run.glob('segment_*/ledger.json')):
        row = read(path)
        if row.get('task_id'):
            task_ids.append(row['task_id'])
        usage = row.get('usage') or {}
        coin = usage.get('consumeCoins', usage.get('consume_coins')) if isinstance(usage, dict) else None
        cost = float(coin) if coin is not None else None
        if cost is not None and (not math.isfinite(cost) or cost < 0):
            raise WorkError('原高质量任务的RH用量回执无效，停止后续调用', 'conflict')
        costs.append(cost)
    ledger.update(task_ids=task_ids,
        known_usage_rh_coins=sum(c for c in costs if c is not None) if any(c is not None for c in costs) else None,
        unconfirmed_segments=sum(c is None for c in costs))
    if (run/'plan.json').is_file():
        ledger['plan'] = read(run/'plan.json')
    save()


def avatar(value, folder, save):
    from lib.bailian_speech import operation_lock
    group = value.get('budget_group_id', value.get('id', folder.name))
    with operation_lock(folder.parent/('rh-budget-'+fingerprint(group)[:20]+'.lock')):
        prior_exposure, prior_known, related = 0, 0, []
        for path in folder.parent.glob('os_*/task.json'):
            other = read(path)
            if other['id'] == value.get('id') or other.get('budget_group_id', other['id']) != group:
                continue
            ledger = other.get('paid', {}).get('avatar', {})
            if not ledger:
                continue
            known = ledger.get('known_usage_rh_coins') or 0
            reserve = (ledger.get('plan') or {}).get('reserve_coins', 0)
            if any(type(n) not in (int, float) or not math.isfinite(n) or n < 0 for n in (known, reserve)):
                raise WorkError('关联原任务的RH账本无效，停止新数字人调用', 'conflict')
            prior_exposure += max(known, reserve)
            prior_known += known
            related.append(other['id'])
        return _avatar(value, folder, save, prior_exposure=prior_exposure, prior_known=prior_known, related=related)


def _avatar(value, folder, save, *, prior_exposure=0, prior_known=0, related=()):
    plan = read(folder/'storyboard-approved.json')
    validate_plan(value, folder, plan)
    packed = folder/'hq-bookends.wav'
    with wave.open(str(folder/'narration.wav'), 'rb') as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 24000):
            raise WorkError('正式配音需为24kHz单声道PCM16')
        samples, data = audio.getnframes(), audio.readframes(audio.getnframes())
    raw = bytearray()
    for window in plan['windows']:
        start, end = window['from']*800, window['to']*800
        chunk = data[start*2:min(samples, end)*2]
        raw.extend(chunk+b'\0\0'*(end-start-len(chunk)//2))
    # Pad at the very end only, outside visible presenter windows, <=0.2s.
    unit = 4800*2
    raw.extend(b'\0'*((-len(raw)) % unit))
    with wave.open(str(packed), 'wb') as audio:
        audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        audio.writeframes(raw)
    executor = hq_executor()
    if executor.config()['workflow_id'] != WORKFLOW_ID or not 0 < value['budget_rh_coins'] <= 2000:
        raise WorkError('已安装执行器的工作流或本片累计预算不符，未发起新数字人调用')
    execution_plan = executor.make_plan(packed, '4x5', segment_seconds=45)
    if execution_plan['reserve_coins']+prior_exposure > value['budget_rh_coins']:
        raise WorkError('本片全部数字人片段累计预留超出2000 RH币，保留配音和分镜，未发起新调用', 'budget_limit')
    name = 'one-stop-'+value['id'][3:]
    ledger = value['paid'].setdefault('avatar', {'run_name': name, 'workflow_id': WORKFLOW_ID,
        'instance_type': 'plus', 'budget_rh_coins': value['budget_rh_coins'],
        'execution_budget_coins': value['budget_rh_coins']-prior_exposure,
        'prior_exposure_rh_coins': prior_exposure, 'prior_known_usage_rh_coins': prior_known,
        'related_tasks': list(related),
        'packed_audio_sha256': digest(packed), 'portrait_sha256': digest(folder/'refinement/result.png'), 'plan': execution_plan})
    if ledger['packed_audio_sha256'] != digest(packed) or ledger['portrait_sha256'] != digest(folder/'refinement/result.png'):
        raise WorkError('原数字人输入已经变化，不能替换输入后重复付费', 'conflict')
    if ledger.get('prior_exposure_rh_coins', 0) != prior_exposure:
        raise WorkError('关联修订的RH敞口已变化，请先核对原任务；不改变原调用预算后重发', 'budget_limit')
    save()
    args = [sys.executable, str(KIT/'agent_cli.py'), 'run', '--workspace', str(ROOT),
            '--audio', str(packed), '--image', str(folder/'refinement/result.png'),
            '--ratio', '4x5', '--name', name, '--segment-seconds', '45', '--budget-coins',
            str(ledger.get('execution_budget_coins', value['budget_rh_coins']))]
    run = KIT/'runs'/name
    try:
        recover_hq_downloads(executor, run)
        with (folder/'hq-execution.log').open('ab') as log:
            result = subprocess.run(args, stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode != 0 and recover_hq_downloads(executor, run):
                # Same immutable run command: verify existing artifacts and IDs.
                result = subprocess.run(args, stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    finally:
        # A successful cloud charge survives any local TLS/download exception.
        record_hq_usage(ledger, run, save)
    task_ids = ledger['task_ids']
    if result.returncode != 0 or not (run/'result.json').is_file():
        raise WorkError('原高质量数字人任务尚未完成，已保留所有片段与扣币记录；恢复只查询原任务，不换编号重发')
    if not task_ids:
        raise WorkError('原数字人缺少真实供应商任务编号，请核对原回执')
    report = read(run/'result.json')
    source = run/report['final_file']
    if digest(source) != report['sha256']:
        raise WorkError('原高质量数字人成片身份变化，请核对原任务', 'conflict')
    target = folder/'presenter-native30.mp4'
    media_command(['-i', source, '-an', '-vf', 'fps=30', '-c:v', 'libx264', '-preset', 'fast', '-crf', '16',
                   '-pix_fmt', 'yuv420p', target], timeout=300)
    return {'workflow_id': WORKFLOW_ID, 'instance_type': 'plus', 'api_type': 'NORMAL',
            'status': 'verified', 'task_id': ','.join(task_ids), 'task_ids': task_ids,
            'original_audio_sha256': plan['audio_sha256'], 'packed_audio_sha256': digest(packed),
            'portrait_sha256': digest(folder/'refinement/result.png'), 'derived_video_sha256': digest(target),
            'windows': plan['windows'], 'speech_stretched': False, 'sampling': '25fps to 30fps, rate 1'}


def production_queue(studio, queue=None):
    if queue is not None:
        return queue
    from backlot.production_queue import ProductionQueue
    from backlot.server import _production_queue_db_path
    return ProductionQueue(_production_queue_db_path(), studio.projects_root)


def completed_media(queue, identity, expected_sha256=None):
    # Native public queue responses deliberately redact filesystem paths. Local
    # orchestration must read the private result, then expose only scoped URLs.
    job = queue.get(identity, include_private=True)
    if job['status'] != 'completed':
        raise WorkError('原合成任务尚未完成，请继续原队列任务')
    result = deepcopy(job['result'])
    project = (Path(queue.projects_root)/job['project_id']).resolve()
    if result.get('output_path') == '[LOCAL_PATH]' or result.get('qa_report') == '[LOCAL_PATH]':
        frozen = job['frozen_request']
        if (frozen.get('contract') != 'motion-replay-chromatic-suite-production-v1'
                or frozen.get('template_id') != 'chromatic-six-11'
                or frozen.get('project_id') != job['project_id']
                or not re.fullmatch(r'chromatic-suite-[a-f0-9]{20}', frozen.get('render_id', ''))):
            raise WorkError('原队列缺少可验证的模板11成片位置', 'conflict')
        directory = project/'renders'/frozen['render_id']
        output, qa = directory/'chromatic-six-11-full.mp4', directory/'qa.json'
        receipt = read(directory/'result.json')
        if (receipt.get('output_sha256') != result.get('output_sha256') or receipt.get('qa_sha256') != digest(qa)
                or receipt.get('request_sha256') != frozen.get('request_sha256')):
            raise WorkError('本地成片回执与原冻结请求不符', 'conflict')
        result.update(output_path=str(output), qa_report=str(qa))
    output = Path(result['output_path']).resolve()
    qa = Path(result['qa_report']).resolve()
    if (not output.is_relative_to(project) or not qa.is_relative_to(project) or not output.is_file() or not qa.is_file()
            or digest(output) != result['output_sha256']
            or expected_sha256 is not None and result['output_sha256'] != expected_sha256):
        raise WorkError('原队列成片、检查报告或文件身份不一致，请检查原任务', 'conflict')
    return result


def compose(studio, queue, value, folder, save):
    from backlot.motion_replay_chromatic_suite_production import prepare, required_files
    from backlot.motion_replay_production import submit_frozen, execute
    queue = production_queue(studio, queue)
    plan = read(folder/'storyboard-approved.json')
    validate_plan(value, folder, plan)
    master = folder/'master.wav'
    mix = plan['mix']
    if digest(mix['source_music']) != mix['music_sha256']:
        raise WorkError('已选配乐身份变化，请核对原始配乐', 'conflict')
    seconds = plan['props']['durationInFrames']/30
    filters = (f'[0:a]aresample=48000,volume={mix["voice_gain_db"]}dB,apad,atrim=duration={seconds},asplit=2[voice][side];'
               f'[1:a]aresample=48000,volume={mix["music_gain_db"]}dB,atrim=duration={seconds}[music];'
               '[music][side]sidechaincompress=threshold=0.05:ratio=2.5:attack=15:release=180[bed];'
               '[voice][bed]amix=inputs=2:normalize=0,alimiter=limit=0.794:level=false:latency=true[out]')
    media_command(['-i', folder/'narration.wav', '-stream_loop', '-1', '-i', mix['source_music'],
                   '-filter_complex', filters, '-map', '[out]', '-t', seconds, '-ar', '48000', '-ac', '2',
                   '-c:a', 'pcm_s16le', master])
    request = {'title': value['script']['title'], 'template_id': 'chromatic-six-11',
               'version': value['policy']['template']['version'], 'props': plan['props'],
               'sources': {name: row['path'] for name, row in plan['sources'].items() if name in required_files(plan['props'])},
               'receipts': {'script': value['script'], 'asr': read(folder/'asr.json'),
                            'audio': value['stages']['narration']['result'],
                            'avatar': value['stages']['avatar']['result'], 'master_sha256': digest(master),
                            'mix': {**mix, 'speech_time_stretched': False, 'voice_sha256': digest(folder/'narration.wav')},
                            'media_origins': plan['media_origins']}, 'publication': False}
    request['sources'].update({'master.wav': str(master), 'presenter-native30.mp4': str(folder/'presenter-native30.mp4')})
    frozen = prepare(queue, request)
    job = submit_frozen(queue, frozen)
    value['stages']['composition']['queue_id'] = job['job_id']
    save()
    if job['status'] in {'running', 'queued'}:
        return {'status': 'waiting', 'message': '正在原生制作队列合成本片'}
    job = execute(queue, job['job_id'], confirmed=True, resume_local=True)
    if job['status'] == 'completed':
        return succeeded(completed_media(queue, job['job_id']))
    if job['status'] in {'running', 'queued'}:
        return {'status': 'waiting', 'message': '正在原生制作队列合成本片'}
    raise WorkError('原合成任务暂未完成，已保留冻结分镜和实际素材，请恢复原任务')


def quality(value, folder):
    result = value['stages']['composition']['result']
    output = Path(result['output_path'])
    if digest(output) != result['output_sha256']:
        raise WorkError('成片文件发生变化，请检查原队列产物', 'conflict')
    report = read(result['qa_report'])
    if report.get('technical') != 'pass' or report.get('full_decode') != 'pass':
        raise WorkError('成片技术检查未通过，请修复原合成任务')
    plan = read(folder/'storyboard-approved.json')
    frames = sorted({0, *[s['from']+max(1, (s['to']-s['from'])//2) for s in plan['props']['scenes']],
                     *[c['from'] for c in plan['props']['captions'] if '体质' in c['text']],
                     plan['props']['durationInFrames']-2})
    thumbs = []
    for index, frame in enumerate(frames):
        path = folder/f'qa-frame-{index:02d}.jpg'
        media_command(['-ss', frame/30, '-i', output, '-frames:v', '1', '-vf', 'scale=270:480', '-q:v', '2', path])
        with Image.open(path) as image:
            thumbs.append(image.copy().convert('RGB'))
    sheet = Image.new('RGB', (270*4, 510*math.ceil(len(thumbs)/4)), '#17243a')
    draw = ImageDraw.Draw(sheet)
    for i, image in enumerate(thumbs):
        x, y = i % 4*270, i//4*510
        sheet.paste(image, (x, y))
        draw.text((x+8, y+486), f'{frames[i]/30:.2f}s', fill='white')
    sheet.save(folder/'contact-sheet.jpg', quality=92)
    media_command(['-ss', max(.25, frames[1]/30), '-i', output, '-frames:v', '1', '-q:v', '2', folder/'cover.jpg'])
    atomic_private(folder/'quality.json', {'technical': 'pass', 'output_sha256': result['output_sha256'],
        'native_qa': report, 'representative_frames': frames, 'contact_sheet_sha256': digest(folder/'contact-sheet.jpg'),
        'visual_review': 'pending', 'audio_review': 'pending', 'publication': False})
