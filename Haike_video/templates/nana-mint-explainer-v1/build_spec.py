"""Describe the implemented reference episode; values remain in its source table."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from prepare import media_duration

HERE = Path(__file__).resolve().parent
profile = json.loads((HERE / 'template-profile.json').read_bytes())
parser = argparse.ArgumentParser()
parser.add_argument('--episode', type=Path, required=True)
parser.add_argument('--output', type=Path, default=HERE / 'video-template-spec.json')
args = parser.parse_args()
episode = json.loads(args.episode.read_bytes())
content = episode['content']
duration = content['duration']
elements, assets, slots = [], [], []
evidence = [
    {'id': 'reference', 'source_kind': 'observation', 'source': 'https://www.douyin.com/video/7701714985299498725', 'locator': 'Full 74.533s overview plus75 actual native-PTS phase frames; private reference report.', 'method': 'Seven overview sheets and seven motion grids actually viewed. Reference objects and authored replacement decisions are separate.', 'file': None, 'sha256': episode.get('reference_sha256')},
    {'id': 'implementation', 'source_kind': 'design', 'source': 'User explicitly selected the existing53 Snapcn components.', 'locator': 'index.tsx/shared.tsx/scenes/*.tsx and per-episode content.json', 'method': 'Independent editable scene composition; exact geometry/easing is owned by named frozen source. No original source-code claim.', 'file': 'index.tsx', 'sha256': hashlib.sha256((HERE / 'index.tsx').read_bytes()).hexdigest()},
    {'id': 'snapcn', 'source_kind': 'measurement', 'source': 'Pinned local MIT Snapcn library', 'locator': '../../motion-components/snapcn/UPSTREAM.json', 'method': 'Use actual upstream components with existing offline-font and shared-host adapters.', 'file': '../../motion-components/snapcn/UPSTREAM.json', 'sha256': hashlib.sha256((HERE / '../../motion-components/snapcn/UPSTREAM.json').read_bytes()).hexdigest()},
]


def element(key, role, box, start=0, end=duration, kind='component', asset=None):
    value = {'id': key, 'type': kind, 'role': role, 'parent_id': None, 'z_index': len(elements),
             'content': {'mode': 'embedded' if asset else 'generated', 'binding': None, 'asset_id': asset, 'description': role + '; per-episode text and media are the controlled source of values.'},
             'layout': {'coordinate_space': 'canvas', 'anchor': 'top_left', 'box': [n * 1.5 for n in box], 'fit': 'contain' if asset else 'none', 'clip': 'self', 'style': {'authority': 'Boxes are1920x1080 canvas pixels. shared.tsx/scenes use1280x720 design pixels uniformly scaled1.5. No inferred official social-platform safe area.'}},
             'timing': {'relative_to': 'global', 'start': start, 'end': end},
             'states': [{'id': 'directed', 'visible': True, 'description': 'Half-open interval. Source-defined entry, settle/read and handoff; frame seeking reconstructs the same state.'}], 'transitions': [],
             'constraints': [{'kind': 'source_authority', 'target_id': None, 'rule': 'Version-frozen source owns numeric geometry and easing; actual source audio drives captions and scene cues. Never stretch speech or loop insufficient presenter footage.'}],
             'fixed': ['Chapter narrative order', 'Audio master clock', 'Existing Snapcn animation behavior'], 'replaceable': [], 'evidence_ids': ['reference', 'implementation', 'snapcn'],
             'acceptance': [{'check': 'visible_subject_and_reading', 'method': 'Actual initial/middle/settled and boundary frames per scene; playback separately.', 'pass_condition': 'Complete focal subject and face, readable Chinese, stable source clock, no unintended empty handoff or baked old subtitles in extracted regions.'}]}
    if kind == 'text':
        value['layout']['style'].update(font='Haike Nana Local; caller supplied local font', font_size=42, max_lines=2, overflow='Rewrite or split before rendering; never shrink below the intended reading hierarchy.')
    elements.append(value)
    return value


def slot(identity, target, prop, typ, limits):
    target['replaceable'].append(prop)
    slots.append({'id': identity, 'element_id': target['id'], 'property': prop, 'value_type': typ, 'required': True, 'limits': limits, 'missing': 'Stop preparation and identify the missing source.', 'overflow': 'Author resegments against measured speech or supplies a sufficient source; do not silently truncate, stretch or loop.'})


element('backdrop', 'Pale mint paper, quiet corner washes; optional argument grid', [0, 0, 1280, 720], kind='background')
nav = element('navigation', 'Persistent five-step chapter bar and frame-driven progress', [0, 0, 1280, 48])
slot('chapter_labels', nav, 'content.chapters', 'array', {'count': 5, 'max_chars_each': 12})
slot('brand', nav, 'content.brand/partner', 'string', {'max_chars_each': 20})
captions = element('captions', 'Native WordCaptions; actual Caption JSON milliseconds, fixed bottom dark pill', [60, 636, 1160, 72], kind='captions')
slot('captions', captions, 'content.captions', 'array', {'clock': 'source-measured milliseconds', 'max_chars_per_phrase': 64, 'max_lines': 2})
assets.append({'id': 'voice_asset', 'kind': 'audio', 'path': None, 'source': 'Per-episode full voice/music source; actual measured duration', 'embedded_content': ['Complete chosen voice/music mix; episode provenance and upstream receipts identify the actual source.'], 'rights_status': 'Private reference or user-authorized episode; new media requires its own user-bound source.'})
sound = element('voice', 'One continuous original-speed voice/music track; no double mixing', [0, 0, 1, 1], kind='audio', asset='voice_asset')
slot('voice', sound, 'content.voice', 'asset', {'min_duration': 0, 'max_duration': 120, 'speed': 1, 'match_scene_clock_tolerance_seconds': .04})
scenes = []
for row in content['scenes']:
    element_ids = ['backdrop', 'navigation', 'captions', 'voice']
    title = element(row['id'] + '_text', 'Editable scene text, short labels and semantic reading order; ' + row['id'], [45, 70, 1190, 540], row['start'], row['end'])
    slot(row['id'] + '_text', title, 'content.scenes[' + row['id'] + '].title/labels/cues', 'object', {'cue_units': 'local seconds', 'max_title_chars': 36, 'content_policy': 'Short authored headings; complete speech remains in timed captions.'})
    element_ids.append(title['id'])
    for name in ['media', 'presenter', 'overlay']:
        if not row.get(name):
            continue
        media = row[name]
        aid = row['id'] + '_' + name + '_asset'
        assets.append({'id': aid, 'kind': 'image' if media.get('kind') == 'image' else 'video', 'path': None, 'source': 'Per-episode user-bound local media, source/derived SHA recorded in episode.json', 'embedded_content': ['Actual UI, person and existing text inside the chosen crop stay baked in; outer template headings and graphics are editable.'], 'rights_status': 'Original downloaded reference only in ignored private episode; never bundled into public code.'})
        obj = element(row['id'] + '_' + name, name + ' source window; exact viewport/crop in ' + row['id'] + ' implementation', [45, 70, 1190, 550], row['start'], row['end'], asset=aid)
        slot(row['id'] + '_' + name, obj, 'content.scenes[' + row['id'] + '].' + name, 'asset', {'fit': 'presenter cover / evidence contain', 'playback_rate': 1, 'min_duration': media_duration(row, name), 'source_offset': 'Per-episode prepared source; no source time guessing.'})
        element_ids.append(obj['id'])
    scenes.append({'id': row['id'], 'start': row['start'], 'end': row['end'], 'purpose': row['title'], 'element_ids': element_ids, 'variant': ['introduction', 'workflow', 'argument', 'resources'][0 if row['chapter'] < 2 else row['chapter'] - 1]})
spec = {'schema_version': 1, 'standard_version': 'video-template-v1', 'template_id': 'nana-mint-explainer-v1', 'template_version': profile['version'], 'template_type': 'avatar', 'spec_kind': 'implementation', 'stage': 'specification',
        'authority': {'runbook': 'README.md', 'implementation_paths': ['index.tsx', 'shared.tsx', 'types.ts', 'scenes/Introduction.tsx', 'scenes/Workflow.tsx', 'scenes/Argument.tsx', 'scenes/Resources.tsx', 'prepare.py', 'render.cjs', 'webpack.cjs', '../../scripts/nana_mint_preview.py'], 'parameter_source': 'Version-frozen TSX owns exact layout and native motion. Private validated content.json owns scene times, cues, captions, labels and source binding; episode.json records media identity. This specification describes the current reference episode, not another numeric parameter source.'},
        'canvas': {'width': 1920, 'height': 1080, 'fps': 30, 'duration_seconds': duration, 'clock': 'Whole actual per-episode audio. Local event seconds and global Caption milliseconds are separate. Round to nearest30fps frame, tolerance0.5 frame; no speech stretch. Optional referenceClock maps only the silent visual comparison; standalone original reference retains its own duration.', 'coordinate_system': 'top_left_pixels'},
        'narrative': {'purpose': 'Reference-matched pale mint chapter-based talking-head explainer, using the existing53-component library.', 'information_hierarchy': ['Meaningful evidence or presenter', 'Short scene claim', 'Measured speech captions', 'Chapter orientation and notes'], 'structure': ['Evidence and brand relation', 'Describe requirements', 'Actual software demonstration', 'Efficiency comparison and human value', 'Resources and closing recall']},
        'scenes': scenes, 'assets': assets, 'elements': elements, 'slots': slots, 'evidence': evidence, 'unknowns': [],
        'validation': {k: {'status': 'pending', 'evidence_ids': ['implementation'], 'note': note} for k, note in {'structure': 'Single-spec schema and repository checks.', 'technical': 'This episode: bundle, actual frame queue, source/decode/clock. Full MP4 export separate.', 'visual': 'Actual all-scene output frames and reference phases, tracked in private REVIEW.', 'audio': 'Local measured ASR is not continuous listening.', 'platform': 'Real phone/social-platform view untested.', 'user_review': 'Interactive full preview offered for user assessment.', 'production': 'Exact local queue adapter; no generic frontend one-click registration.'}.items()},
        'extensions': {'avatar': {'face_crop': 'Presenter crop independent of window; private reference uses same-clock visible source region with measured frame windows. New presenter is a new asset/crop, not a face swap or voice clone.', 'synchronization': 'Whole audio clock retained, scene-local prepared presenter clips align to original global time. Brief presenter delayed2.1s. Keep raw ASR and actual word boundaries; edited caption text never invents new word timing.'}, 'graphic': {'text_policy': 'Local Chinese font; caption28px in1280 design pixels, short titles32–65px; max two caption lines. Source screenshots retain baked text.', 'asset_fit': 'Evidence contain; presenter cover with explicit native crop. At1920 output,1280-design geometry uniformly scaled1.5; this does not restore missing detail in downloaded reference media.'}, 'tutorial': {'step_mapping': 'Upload→describe→native visual window→result tied to measured local scene cues; illustrative input and step components distinguished from actual software playback.', 'callout_policy': 'Chapter bar and scene title are editable; never represent generated UI logs as new successful real operations.'}, 'material_edit': {'source_ranges': 'Private episode.provenance records original global ranges, exact crops, original playback speed and derived SHA.', 'cut_policy': 'Half-open scene intervals, source-synchronous visible presenter, no loop/stretch/freeze to hide shortages. Media changes reprepare and invalidate prior review.'}, 'snapcn': {'contract': 'haike-nana-mint-preview-v1', 'rules': ['Nine actual installed components: TextReveal/TextBuild/TextHighlight/TextSwap/PromptSend/AgentSteps/ScreenRecording/CaptureReveal/WordCaptions.', 'Pinned shared host and offline adapters; upstream source unchanged.', 'Full render requires source/media/bundle-bound actual-frame review and explicit render mode.']}},
        'operations': [
            {'id': 'prepare', 'entrypoint': 'prepare.py --reference/--transcript/--font OR --episode/--assets, plus explicit --output/--ffmpeg/--ffprobe', 'input': 'Known reference SHA plus local measured transcript, or a new complete authored episode and declared local files.', 'action': 'Preserve original clock, prepare reference source regions or copy new files, validate continuous scenes/cues and actual source durations.', 'output': 'Private public/content.json, local media and episode.json.', 'completion': 'Source identities, full sound duration and enough actual video for every visible window; no provider calls.', 'recovery': 'Read existing episode. A frozen output directory is never silently overwritten; choose a new episode or reuse exact existing outputs.'},
            {'id': 'preview', 'entrypoint': 'render.cjs bundle; ../../scripts/nana_mint_preview.py --mode frames; Remotion Studio using remotion.config.cjs', 'input': 'Validated private episode, existing local runtimes, shared pinned composition host.', 'action': 'Bundle same code used by interactive preview, freeze all inputs, submit and execute exact paused local job through unified queue.', 'output': 'Frame proofs, original queue/log, editable Studio template/reference/comparison compositions.', 'completion': 'Every intended scene and critical state actually reviewed; metadata success alone is insufficient.', 'recovery': 'Read jobs.json and original queue/log; preserve completed frame evidence. Input/code changes require a new frozen request.'},
            {'id': 'export', 'entrypoint': '../../scripts/nana_mint_preview.py --mode render', 'input': 'Explicit export request; actual reviewed frame identity and same source/media/bundle.', 'action': 'Submit unified local export, preserve whole audio, encode22Mbps CBR and verify actual video>=20Mbps/full decode/frame count.', 'output': 'MP4, quality.json and work registration.', 'completion': 'Actual MP4 technical evidence plus encoded-frame review; listening/user/platform remain independent.', 'recovery': 'Reuse source and any complete silent render; no repeated paid stage or publishing.'},
        ]}
spec['authority']['implementation_paths'] += ['template-profile.json', 'input-contract.json', 'frozen_release.py', 'verify-release.cjs', 'mix_audio.py']
spec['authority']['parameter_source'] = 'template-profile.json'
spec['narrative']['purpose'] = '动效模板3：用户已确认的薄荷章节数字人口播，13景编排及既有9组件；新一期以实测完整音轨重排受控时间参数。'
spec['extensions']['reuse'] = {'contract': 'haike-nana-mint-episode-v1', 'rules': [profile['reuse_scope'], 'Frozen geometry/motion and palette; new episode text/media/timing stay outside release files.', 'Music recipe is template-profile.json; private portrait/voice/music defaults are local only.', 'Only exact accepted episode gets historical passed evidence; new input remains specification/pending until actually checked.']}
approval_path = HERE / 'APPROVAL.json'
if approval_path.is_file():
    approval = json.loads(approval_path.read_bytes())
    canonical = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    exact = canonical == approval['accepted_content_sha256'] and {name: row['sha256'] for name, row in episode['files'].items()} == approval['accepted_episode_file_sha256']
    spec['evidence'].append({'id': 'accepted-baseline', 'source_kind': 'observation', 'source': 'User accepted the89.266667s v5 preview and explicitly named/froze 动效模板3. Exported MP4/full decode/17 encoded frames and identical AAC stream recorded inAPPROVAL.json.', 'locator': 'APPROVAL.json; linked private source/frame/stream identities', 'method': '44 source states actually viewed,17 final encoded states actually viewed, video22.02Mbps/full decode, accepted AAC stream identity; no new-device listening claim.', 'file': 'APPROVAL.json', 'sha256': hashlib.sha256(approval_path.read_bytes()).hexdigest()})
    if exact:
        spec['stage'] = 'ready'
        for key in ('structure', 'technical', 'visual', 'user_review'):
            spec['validation'][key].update(status='pass', evidence_ids=['accepted-baseline'], note='Exact accepted landscape89.266667s baseline only; new inputs have independent validation.')
        spec['validation']['audio'].update(status='pass', evidence_ids=['accepted-baseline'], note='User accepted v5 music balance; final AAC bytes identical, truepeak-2.0dBFS. Agent continuous device audition not claimed.')
        spec['validation']['production'].update(status='pending', evidence_ids=['accepted-baseline'], note='Local controlled CLI queue export verified. Gallery entry does not imply generic avatar-form one-click production.')
        spec['validation']['platform'].update(evidence_ids=['accepted-baseline'], note='Target phone/platform and another physical machine not tested.')

target = args.output.resolve()
target.parent.mkdir(parents=True, exist_ok=True)
if target.parent != HERE:
    def relative(name):
        source = (HERE / name).resolve()
        try:
            return Path(os.path.relpath(source, target.parent)).as_posix()
        except ValueError:
            # Windows cannot make a relative path across drive letters.
            # Per-episode snapshots may use absolute local source references.
            return source.as_posix()
    spec['authority']['runbook'] = relative(spec['authority']['runbook'])
    spec['authority']['implementation_paths'] = [relative(p) for p in spec['authority']['implementation_paths']]
    spec['authority']['parameter_source'] = relative(spec['authority']['parameter_source'])
    for item in spec['evidence']:
        if item.get('file'):
            item['file'] = relative(item['file'])
target.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')
print('Generated specification:', len(elements), 'elements,', len(slots), 'slots')
