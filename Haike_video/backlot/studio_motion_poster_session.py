"""Public poster-kit recipe in the shared template session service.

No motion source is recreated here. This strategy binds editable content,
whole-sentence timing and owned assets to the existing component queue.
"""
from copy import deepcopy
from itertools import combinations
from pathlib import Path

from backlot import studio_motiongit as motion, studio_motiongit_render as renderer
from backlot.studio import atomic_private
from backlot.studio_dark_full_script import spoken
from backlot.studio_dark_native_content import _captions, _clock
from backlot.studio_investment_recompose import fingerprint
from backlot.work_catalog import WorkError, read_json, sha

ID = 'motiongit-poster-story-v1'
ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT/'Haike_video/templates/motiongit-poster-v1/profile.json'
DEFAULTS = ROOT/'.local/motion-poster/defaults.json'
LAYOUTS = {'landscape': {'label': '原生横版 16:9', 'engine': 'native', 'width': 1920, 'height': 1080},
           'portrait45': {'label': '海报重排 4:5（试制）', 'engine': 'component', 'width': 1440, 'height': 1800}}


def apply_layout(params, layout):
    """Reflow native controls inside the producer's 1080x1350 review viewport."""
    require(layout in LAYOUTS, '海报画幅尚未接入')
    params['layout'] = 'portrait' if layout == 'portrait45' else 'landscape'
    if layout == 'portrait45':
        # Native areas size each control; they do not shrink a landscape film.
        for segment in params['segments']:
            y, height = {'kinetic': (280, 800), 'polaroid': (190, 880),
                         'media': (180, 900)}.get(segment['control'], (80, 1020))
            segment['area'] = {'x': 40, 'y': y, 'w': 1000, 'h': height}
        params['captionPosition'] = {'bottomRatio': .38, 'leftRatio': .08, 'rightRatio': .08}
    else:
        params.pop('captionPosition', None)
        for segment in params['segments']: segment.pop('area', None)
    return params
def require(value, message, code='invalid'):
    if not value: raise WorkError(message, code)


def fields():
    return [{'id': g['id'], 'label': g['label'],
             'fields': [{**f, 'type': 'string'} for f in g['fields']]}
            for g in read_json(PROFILE)['groups']]


def at_path(value, key):
    for part in key.split('.'):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def set_path(value, key, item):
    parts = key.split('.'); parent = value
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    parent[int(parts[-1]) if isinstance(parent, list) else parts[-1]] = item


def package(value):
    from backlot.studio_motion_templates import verified
    raw = verified(value['tools']['package'])
    info = motion.inspect_package(raw); profile = read_json(PROFILE)
    require(info['template_id'] == profile['template_id'] and info['version'] == profile['version'],
            '海报原包版本尚未接入此制作配置')
    require(sha(verified(value['tools']['helper'])) == motion.HELPER_SHA, '海报官方入口未核验')
    result = next((p for p in motion.packages()['packages'] if p['sha256'] == sha(raw)), None)
    require(result is not None, '请先导入海报原包')
    result = motion._get('packages', result['id'])
    require(result.get('verification') == 'verified' and 'poster-kit' in result['workflows'], '请先核验海报公开控件')
    return result


def seed(*, check_sources=True):
    from backlot.studio_motion_templates import verified
    defaults = read_json(DEFAULTS); path = Path(defaults.get('latest_example_input', ''))
    if not path.is_absolute():path=ROOT/path
    require(path.is_file(), '此机器尚未配置海报原包和合法参考输入', 'unavailable')
    value = read_json(path); package(value)
    params = value['poster']['parameters']
    require([s['control']+'-'+s['variant'] for s in params['segments']] == [g['id'] for g in fields()],
            '此海报会话需要已核验的五组控件编排')
    if check_sources:
        for row in value['media']['wall']: verified(row['source'])
        for name in ['voice', 'captions', 'avatar', 'music']: verified(value[name])
    value.update(template_id=ID, content={g['id']: {f['key']: at_path(s['props'], f['key']) for f in g['fields']}
                 for g, s in zip(fields(), params['segments'])})
    return value


def fit_segments(segments, caps, seconds, controls, maximum_seconds=None, cue_holds=None):
    """Choose sentence gaps and real cue starts, preserving public hold/tail rules."""
    require(caps and all(0 <= c['t0'] < c['t1'] <= seconds+.001 for c in caps)
            and all(a['t1'] <= b['t0']+.001 for a, b in zip(caps, caps[1:])), '海报需要完整且有序的真实字幕时间')
    gaps = {0: [0], len(caps): [seconds]}
    for i, (a, b) in enumerate(zip(caps, caps[1:]), 1):
        gaps[i] = sorted({a['t1'], (a['t1']+b['t0'])/2, b['t0']})
    original = segments[-1]['t1']; states = {(0, 0): (0, [])}
    for index, segment in enumerate(segments):
        rule = controls[segment['control']]; count = len(segment['cues'])
        old_span = segment['t1']-segment['t0']; target = segment['t1']/original*seconds
        next_states = {}
        for end in ([len(caps)] if index == len(segments)-1 else range(1, len(caps))):
            for t1 in gaps[end]:
                best = None
                for (start, t0), (cost, path) in states.items():
                    if end-start < count or t1-t0 < rule['minDur']: continue
                    if maximum_seconds and t1-t0 > maximum_seconds.get(index, float('inf'))+.001: continue
                    eligible = [j for j in range(start, end) if caps[j]['t0'] <= t1-rule.get('tail', .7)+.001]
                    choice = None
                    for chosen in combinations(eligible, count):
                        if cue_holds and index in cue_holds:
                            starts = [caps[j]['t0'] for j in chosen]
                            if any(end-at < hold-.001 for at, end, hold in
                                   zip(starts, starts[1:]+[t1], cue_holds[index])): continue
                        cue_cost = sum((caps[j]['t0']-(t0+(cue-segment['t0'])/old_span*(t1-t0)))**2
                                       for j, cue in zip(chosen, segment['cues']))
                        if choice is None or cue_cost < choice[0]: choice = (cue_cost, chosen)
                    if choice is None: continue
                    proposal = (cost+(t1-target)**2+choice[0]*.15, path+[(start, end, t0, t1, list(choice[1]))])
                    if best is None or proposal[0] < best[0]: best = proposal
                if best is not None: next_states[(end, t1)] = best
        states = next_states
    require((len(caps), seconds) in states, '本期完整口播和素材无法容纳五组海报动作及可读退场，请重新选择编排；不会截句或加速口播')
    result = deepcopy(segments); maps = []
    for i, (segment, (start, end, t0, t1, chosen)) in enumerate(zip(result, states[(len(caps), seconds)][1])):
        segment.update(t0=t0, t1=t1, cues=[caps[j]['t0'] for j in chosen])
        targets = ([f'lines.{j}' for j in range(len(chosen))] if segment['control'] == 'kinetic' else
                   [f'items.{j}.caption' for j in range(len(chosen))] if segment['control'] in {'gallery', 'polaroid'} else
                   ['src', 'callouts.0.text'] if segment['control'] == 'media' else ['text', 'sub'])
        beats = []
        for j in range(start, end):
            active = max((k for k, at in enumerate(chosen) if at <= j), default=0)
            beats.append({'at': caps[j]['t0'], 'until': caps[j]['t1'], 'spokenText': caps[j]['zh'],
                          'timing': 'sentence', 'target': targets[active]})
        maps.append({'shot': i, 'start': t0, 'end': t1,
                     'spokenText': ''.join(c['zh'] for c in caps[start:end]), 'purpose': 'neutral-emphasis',
                     'timingSource': 'provided-captions', 'captionBinding': 'continuous',
                     'captionIndices': list(range(start, end)), 'beats': beats})
    return result, maps


def configured(value):
    from backlot.studio_motion_templates import verified
    inputs = value['input']; params = deepcopy(inputs['poster']['parameters']); p = package(inputs)
    seconds = _clock(verified(inputs['voice']))['duration_seconds']
    _, caps = _captions(inputs['captions'], Path.cwd(), inputs['voice'], seconds)
    require(spoken(''.join(c['zh'] for c in caps)) == spoken(value['script']), '海报台词与完整音频字幕不一致')
    for group, segment in zip(fields(), params['segments']):
        for field in group['fields']: set_path(segment['props'], field['key'], value['content'][group['id']][field['key']])
    from backlot.studio_render import media_probe
    limits = {}
    for row in inputs['media']['wall']:
        if row['kind'] != 'video': continue
        remaining = media_probe(verified(row['source']))['duration']-row['at']
        for location in row['locations']:
            index = location['segment']; limits[index] = min(limits.get(index, float('inf')), remaining)
    # Project reading allowance observed necessary after the film caption reveal.
    # This changes real cue selection, never the original animation speed.
    holds = {i: [1.8+.12*len(item['caption']) for item in s['props']['items']]
             for i, s in enumerate(params['segments']) if s['control'] == 'polaroid'}
    holds.update({i: [1.5+.04*len(text) for text in s['props']['lines']]
                  for i, s in enumerate(params['segments']) if s['control'] == 'kinetic'})
    params['segments'], params['narrationMap'] = fit_segments(params['segments'], caps, seconds, p['workflows']['poster-kit']['controls'], limits, holds)
    for row in inputs['media']['wall']:
        for location in row['locations']:
            props = params['segments'][location['segment']]['props']
            set_path(props, location['path'], 'inputs/'+row['alias'])
            if 'start_path' in location: set_path(props, location['start_path'], row['at'])
    params.update(duration=seconds, ending='cut', voiceover='inputs/narration.wav', music='inputs/music.wav',
                  subtitles='inputs/captions.srt', presenter={'hide': True} if value['presenter_mode'] == 'hidden' else
                  {'src': 'inputs/presenter.mp4', 'audio': 'mute', 'framing': 'auto'})
    params['header'] = {'shortTitle': value['short_title'], 'source': {'kind': 'assistant-summary', 'field': 'script'}}
    apply_layout(params, value['layout'])
    motion.validate_parameters(p, 'poster-kit', params)
    return params


def input_slots(value, params=None):
    """Keep input editing available before a new narration has a legal plan."""
    rows = []
    for i, row in enumerate(value['input']['media']['wall']):
        video = Path(row['source']['path']).suffix.lower() not in {'.jpg', '.png', '.jpeg', '.webp'}
        seconds = (max(params['segments'][x['segment']]['t1']-params['segments'][x['segment']]['t0']
                       for x in row['locations']) if params is not None else None) if video else 0
        rows.append({'slot': f'wall-{i}', 'label': row['label'], 'at': row['at'], 'seconds': seconds,
                     'kind': 'video' if video else 'image', 'timing_pending': video and params is None})
    return rows


def slots(value):
    return input_slots(value, configured(value))


def prepare(store, value, queue):
    from backlot.studio_motion_templates import binding, verified
    params = configured(value)
    folder = ROOT/'.local/mp'/value['id']/'versions'/fingerprint({'params': params, 'inputs': value['input'], 'strategy': sha(__file__)})[:20]
    folder.mkdir(parents=True, exist_ok=True)
    atomic_private(folder/'parameters.json', params)
    review = read_json(verified(value['input']['source_review']))
    images = {r['path']: r for material in review['materials'] for r in material['actual_images_viewed']}
    value['build'] = binding(folder/'parameters.json')
    value['plan'] = {'token': sha(folder/'parameters.json'), 'summary': {'durationFrames': round(params['duration']*60),
                     'selectedScenes': [g['id'] for g in fields()], 'blocking': [], 'missing': [],
                     'scene_timing': [{k: s[k] for k in ['control', 'variant', 't0', 't1', 'cues']} for s in params['segments']]},
                     'images': list(images.values())}
    value['status'] = 'plan_review'
    return store.put(value, value['revision'])


def approve_plan(store, value, token, seen, q):
    from backlot.studio_motion_templates import binding, verified
    from backlot.production_queue_worker import ProductionQueueWorker
    require(q is not None, '海报预览须使用当前项目统一队列')
    plan = value.get('plan', {})
    require(value['status'] == 'plan_review' and plan.get('token') == token
            and set(seen) == set(range(len(plan['images']))), '请实际检查本期海报编排和全部源图')
    params_path = verified(value['build']); require(sha(params_path) == token, '本期海报编排已变化')
    for image in plan['images']: verified(image)
    params = read_json(params_path); inputs = value['input']; p = package(inputs)
    build = read_json(params_path.parent/'component-run.json')
    if not build:
        d = motion.save_draft(p['id'], 'poster-kit', params, title=value['title'],
                              output_profile='4:5' if value['layout'] == 'portrait45' else 'native')
        from backlot import studio_motion_console as util
        for alias, path in [('narration.wav', verified(inputs['voice']))]+[(r['alias'], verified(r['source'])) for r in inputs['media']['wall']]:
            motion.save_asset(d['id'], alias, path.read_bytes())
        if value['presenter_mode'] != 'hidden': motion.save_asset(d['id'], 'presenter.mp4', verified(inputs['avatar']).read_bytes())
        _, caps = _captions(inputs['captions'], params_path.parent, inputs['voice'], params['duration'])
        text = '\n\n'.join(f"{i+1}\n{util._srt_time(c['t0'])} --> {util._srt_time(c['t1'])}\n{c['zh']}" for i, c in enumerate(caps))+'\n'
        motion.save_asset(d['id'], 'captions.srt', text.encode('utf-8'))
        music = params_path.parent/'music.wav'; m = inputs['music']
        util._run([verified(inputs['tools']['ffmpeg']), '-nostdin', '-v', 'error', '-y', *(['-stream_loop', '-1'] if m.get('loop') else []),
                   '-ss', m.get('offsetSeconds', 0), '-i', verified(m), '-t', params['duration'],
                   '-af', f"volume={m.get('gainDb', -3)}dB", '-ar', '48000', '-ac', '2', music])
        motion.save_asset(d['id'], 'music.wav', music.read_bytes())
        frozen = renderer.freeze(q, d['id']); build = {'request': str((q.projects_root/frozen['project_id']/'artifacts/motiongit-component-request.json').resolve())}
        atomic_private(params_path.parent/'component-run.json', build)
    frozen = read_json(build['request']); job = renderer.submit(q, frozen, phase='preview')
    if job['status'] in {'paused', 'failed'}:
        ProductionQueueWorker(q, q.projects_root, worker_id='poster-preview-'+value['id'], lease_seconds=7200).run_local_recompose(job['job_id'])
    job = q.get(job['job_id']); require(job['status'] == 'completed', '海报预览队列尚未完成，请保留原任务并恢复本地准备')
    folder = renderer._paths(q, frozen); state = read_json(folder/'native-state.json')
    files = [binding(Path(state['images_directory'])/name) for name in state['images']]
    require(files, '海报原生预览没有图片')
    value['component_run'] = {**build, 'preview_job_id': job['job_id']}
    value['preview_files'] = files
    value['preview'] = {'token': sha(Path(state['preview_receipt'])), 'engine': 'component',
                        'images': [{'id': i, 'url': f"/api/studio/motion-templates/sessions/{value['id']}/preview/{i}"} for i in range(len(files))]}
    value['status'] = 'preview_review'
    return store.put(value, value['revision'])


def approve_preview(store, value, token, queue):
    frozen = read_json(value['component_run']['request']); state = read_json(renderer._paths(queue, frozen)/'native-state.json')
    renderer.review(queue, frozen, {'preview_sha256': token, 'reviewer': 'user-or-agent', 'inspected_images': state['images']})
    value['frozen'] = {'request': value['component_run']['request'], 'engine': 'component'}
    return frozen
