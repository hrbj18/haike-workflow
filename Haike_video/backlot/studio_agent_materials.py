"""Accept the working Agent's observations on the original audio clock.

This module never invokes an LLM. The existing producer owns search/download,
the Agent owns visual judgement, and retries keep the original paid stages.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import shutil

from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, sha
from backlot.studio_network_materials import MaterialSearchError, _source_url


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def directory(studio, draft):
    path = studio.projects_root / draft['id'] / 'renders' / ('studio-' + str(draft['revision']))
    for parent in (path, *path.parents):
        if parent == studio.projects_root:
            break
        if parent.is_symlink() or (parent.exists() and getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400):
            raise WorkError('Agent素材路径不能穿过目录链接')
    path.mkdir(parents=True, exist_ok=True)
    return path


def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def context(studio, draft):
    folder = directory(studio, draft)
    value = read(folder / 'agent-material-context.json')
    if value is None:
        return {'draft_id': draft['id'], 'draft_revision': draft['revision'], 'status': 'pending_audio',
                'message': '由当前Agent分析。制作取得真实音轨和字幕后，在此读取分镜与素材待办。', 'candidates': []}
    if value['draft_fingerprint'] != fingerprint(draft):
        raise WorkError('Agent分析上下文与原草稿不一致，请核对原版本', 'conflict')
    value['candidates'] = [read(path) for path in sorted((folder / 'agent-candidates').glob('*/candidate.json'))]
    value['analysis'] = read(folder / 'agent-analysis.json')
    return value


def _effective(draft, current, materials):
    from copy import deepcopy
    value = deepcopy(draft)
    value['text'] = current['script']
    declared = {m['id']: m for m in (draft['input'].get('ai') or {}).get('materials', [])}
    reviewed = {m['asset_id'] for m in materials}
    if any(m.get('mode') == 'must' and ident not in reviewed for ident, m in declared.items()):
        raise WorkError('Agent尚未观看并纳入必须使用的用户素材')
    value['input'].setdefault('ai', {})['materials'] = [
        {'id': m['asset_id'], 'mode': declared.get(m['asset_id'], {}).get('mode', 'prefer'), 'offset': m.get('offset', 0)} for m in materials]
    return value


def _materials(studio, draft, values):
    if not isinstance(values, list) or len(values) > 12:
        raise WorkError('Agent最多提交12份已观看素材')
    output, seen = [], set()
    for item in values:
        allowed = {'asset_id', 'sha256', 'source', 'source_url', 'rights_confirmed', 'observed_frames', 'reason', 'offset'}
        if not isinstance(item, dict) or set(item) - allowed or item.get('rights_confirmed') is not True:
            raise WorkError('Agent素材需要明确来源、使用权与观看依据')
        path = studio.asset(item.get('asset_id'), draft['id'])
        if path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.mp4', '.mov'}:
            raise WorkError('Agent素材需要项目内图片或视频')
        if item.get('asset_id') in seen or sha(path) != item.get('sha256'):
            raise WorkError('Agent素材重复或文件SHA已改变', 'conflict')
        seen.add(item['asset_id'])
        source = item.get('source')
        if source not in {'user', 'pexels', 'douyin'}:
            raise WorkError('Agent素材来源无效')
        if source != 'user' and not _source_url(item.get('source_url'), source):
            raise WorkError('网络素材需要可核对的原平台公开来源')
        _observation(item)
        offset = item.get('offset', 0)
        if type(offset) not in {int, float} or not math.isfinite(offset) or not 0 <= offset <= 600:
            raise WorkError('素材起点需要0至600秒')
        if path.suffix.lower() in {'.mp4', '.mov'}:
            from backlot.studio_render import media_probe
            duration = media_probe(path)['duration']
            if any(at > duration for at in item['observed_frames']):
                raise WorkError('观看记录超出实际视频时长')
        elif item['observed_frames'] != [0]:
            raise WorkError('图片观看记录使用0秒')
        output.append(dict(item))
    return output


def _observation(item):
    observed = item.get('observed_frames')
    if (not isinstance(observed, list) or not 1 <= len(observed) <= 12
            or any(type(at) not in {int, float} or not math.isfinite(at) or at < 0 for at in observed)
            or not isinstance(item.get('reason'), str) or not 1 <= len(item['reason'].strip()) <= 1000):
        raise WorkError('请由当前Agent实际观看代表帧，记录观看位置和具体选用依据')


def apply(studio, draft, data):
    from backlot.studio_storyboard import _LOCK, validate_plan
    with _LOCK:
        current = context(studio, draft)
        if (not isinstance(data, dict) or set(data) - {'draft_revision', 'clock_sha256', 'scenes', 'materials', 'decisions'}
                or type(data.get('draft_revision')) is not int or data.get('draft_revision') != draft['revision'] or not current.get('clock_sha256')
                or data.get('clock_sha256') != current['clock_sha256']):
            raise WorkError('Agent分析需要匹配原草稿版本与真实音频时钟', 'conflict')
        if len(json.dumps(data)) > 300000:
            raise WorkError('Agent分析结果过大')
        folder = directory(studio, draft)
        old = read(folder / 'agent-analysis.json', {})
        value = {**old, 'draft_revision': draft['revision'], 'clock_sha256': current['clock_sha256']}
        if 'scenes' in data:
            materials = _materials(studio, draft, data.get('materials', []))
            validate_plan({'scenes': data['scenes']}, _effective(draft, current, materials), current['cues'], current['duration'])
            if old.get('scenes'):
                if len(old['scenes']) != len(data['scenes']):
                    raise WorkError('原字幕分段已冻结，请在未解决段落补充素材', 'conflict')
                adopted = read(folder / 'storyboard.json', {}).get('scenes', [])
                previous_materials = {m['asset_id']: m for m in old.get('materials', [])}
                incoming_materials = {m['asset_id']: m for m in materials}
                for index, (previous, incoming) in enumerate(zip(old['scenes'], data['scenes'])):
                    if any(previous[k] != incoming[k] for k in ('from_cue', 'to_cue', 'script_start', 'script_end')):
                        raise WorkError('原字幕分段已冻结，请保留真实音频时钟', 'conflict')
                    selected = adopted[index] if index < len(adopted) else {}
                    if selected.get('asset') and (previous != incoming or (
                            previous.get('asset_id') and previous_materials.get(previous['asset_id']) != incoming_materials.get(previous['asset_id']))):
                        raise WorkError('已采用画面已冻结，请只补充尚未解决的段落', 'conflict')
            value.update(scenes=data['scenes'], materials=materials)
        elif 'materials' in data:
            raise WorkError('新增素材须随同完整分镜提交')
        if not value.get('scenes'):
            raise WorkError('请先提交覆盖真实字幕的分镜')
        decisions = dict(value.get('decisions', {}))
        proposed = data.get('decisions', [])
        if not isinstance(proposed, list) or len(proposed) > 60:
            raise WorkError('Agent候选审核结果无效')
        for decision in proposed:
            if not isinstance(decision, dict) or set(decision) != {'candidate_id', 'sha256', 'suitable', 'observed_frames', 'reason'}:
                raise WorkError('候选审核字段不完整')
            identity = decision['candidate_id']
            if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{24}', identity) or type(decision['suitable']) is not bool:
                raise WorkError('候选审核编号或结论无效')
            candidate = read(folder / 'agent-candidates' / identity / 'candidate.json')
            if not candidate or candidate['sha256'] != decision['sha256']:
                raise WorkError('候选审核与原素材SHA不一致', 'conflict')
            _observation(decision)
            positions = {frame['at_seconds'] for frame in candidate['frames']}
            if set(decision['observed_frames']) != positions:
                raise WorkError('请使用已提供的真实代表帧位置记录观看依据')
            if identity in decisions and decisions[identity] != decision:
                raise WorkError('原候选审核已冻结，不能覆盖已采用结论', 'conflict')
            decisions[identity] = decision
        value['decisions'] = decisions
        atomic_private(folder / 'agent-analysis.json', value)
        return {'ok': True, 'draft_revision': draft['revision'], 'analysis_sha256': fingerprint(value), 'next': 'resume_original_job'}


def plan(studio, draft, folder, cues, duration, *, audio_sha256=None):
    from backlot.studio_storyboard import validate_plan, verify_spoken_script
    script = ''.join(c['text'] for c in cues) if draft['input'].get('soundMode') == 'audio' else draft['text']
    clock = {'script': script, 'cues': cues, 'duration': duration, 'audio_sha256': audio_sha256}
    current = {'draft_id': draft['id'], 'draft_revision': draft['revision'], 'draft_fingerprint': fingerprint(draft),
               'clock_sha256': fingerprint(clock), **clock, 'status': 'needs_plan',
               'message': '等待当前Agent读取真实字幕、安排分镜并提交素材观察结果。'}
    old = read(Path(folder) / 'agent-material-context.json')
    if old and old['clock_sha256'] != current['clock_sha256']:
        raise WorkError('原任务的音频时钟发生变化，请核对已保留音轨', 'conflict')
    atomic_private(Path(folder) / 'agent-material-context.json', current)
    receipt = read(Path(folder) / 'agent-analysis.json')
    if not receipt:
        raise MaterialSearchError(current['message'], 'awaiting_agent')
    if receipt['clock_sha256'] != current['clock_sha256']:
        raise WorkError('原Agent分析不属于当前音频时钟', 'conflict')
    materials = _materials(studio, draft, receipt.get('materials', []))
    effective = _effective(draft, current, materials)
    verify_spoken_script(script, cues)
    scenes = validate_plan({'scenes': receipt['scenes']}, effective, cues, duration)
    for scene in scenes:
        if not scene['asset_id']:
            continue
        item = next(m for m in materials if m['asset_id'] == scene['asset_id'])
        path = studio.asset(item['asset_id'], draft['id'])
        scene['asset'] = {'id': item['asset_id'], 'kind': 'video' if path.suffix.lower() in {'.mp4', '.mov'} else 'image',
                          'name': path.name, 'offset': item.get('offset', 0),
                          'provenance': {'source': item['source'], 'source_url': _source_url(item.get('source_url'), item['source']),
                                         'rights': 'agent-confirmed', 'reviewed_by': 'current-agent', 'reason': item['reason']}}
        scene['asset_sha256'] = item['sha256']
        if scene['asset']['kind'] == 'video':
            from backlot.studio_render import media_probe
            if item.get('offset', 0) + scene['end'] - scene['start'] > media_probe(path)['duration'] + .05:
                raise WorkError('已审素材片长不足，请补充可覆盖本段的画面')
    return {'schema': 'haike-storyboard/1', 'analysis_mode': 'agent', 'model': 'current-agent',
            'scenes': scenes, 'duration': duration, 'timing': 'observed ASR', 'human_review': 'agent-reviewed',
            'agent_analysis_sha256': fingerprint(receipt)}


def review(studio, draft, folder, scene, path, identity, provenance):
    from backlot.studio_render import media_probe
    from backlot.studio_storyboard import image_preview
    folder = Path(folder)
    current = read(folder / 'agent-material-context.json')
    if not current:
        raise WorkError('缺少原音频分析上下文，请恢复原任务')
    digest = sha(path)
    candidate_id = fingerprint([scene['id'], scene.get('query'), scene.get('label'), scene.get('text'), identity, digest])[:24]
    candidate_dir = folder / 'agent-candidates' / candidate_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    retained = candidate_dir / 'source.mp4'
    if not retained.exists():
        shutil.copyfile(path, retained)
    if sha(retained) != digest:
        raise WorkError('保留候选素材已变化，请恢复原文件', 'conflict')
    length = media_probe(retained)['duration']
    if length + .05 < scene.get('end', 0) - scene.get('start', 0):
        return False
    frames = []
    for index, at in enumerate([0, length * .5, max(0, length - .2)]):
        frame = candidate_dir / ('frame-' + str(index) + '.jpg')
        if not frame.exists():
            image_preview(retained, frame, at)
        frames.append({'at_seconds': at, 'path': str(frame),
                       'url': f"/api/studio/drafts/{draft['id']}/agent-materials/frames/{candidate_id}/{index}"})
    source = provenance.get('source')
    atomic_private(candidate_dir / 'candidate.json', {'candidate_id': candidate_id, 'scene_id': scene['id'], 'sha256': digest,
                   'source': source, 'source_url': _source_url(provenance.get('source_url'), source),
                   'frames': frames, 'duration': length, 'label': scene['label'], 'query': scene['query']})
    receipt = read(folder / 'agent-analysis.json', {})
    decision = receipt.get('decisions', {}).get(candidate_id)
    if decision and decision['sha256'] == digest:
        return decision['suitable']
    current.update(status='needs_review', message='候选画面已保留，等待当前Agent观看代表帧并提交选用结论。')
    atomic_private(folder / 'agent-material-context.json', current)
    raise MaterialSearchError(current['message'], 'awaiting_agent')


def frame(studio, draft, candidate_id, index):
    if not re.fullmatch(r'[a-f0-9]{24}', candidate_id) or index not in {0, 1, 2}:
        raise WorkError('代表帧编号无效')
    folder = directory(studio, draft)
    path = folder / 'agent-candidates' / candidate_id / ('frame-' + str(index) + '.jpg')
    if not path.resolve().is_relative_to(folder.resolve()) or not path.is_file() or path.is_symlink():
        raise WorkError('代表帧尚未生成', 'missing')
    return path
