"""Read-only, exact-version bridges to the four frozen numbered renderers.

No queue submission, bundle build, supplier call or media copying happens here.
The input is an existing prepared episode, never a request to invent new timing.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess


BASE = 'Haike_video/templates/'
SPECS = {
    'kinetic-field-v1': ('1.0.0', BASE + 'kinetic-field-v1', 'release.json'),
    'nana-mint-explainer-v1': ('1.0.0', BASE + 'nana-mint-explainer-v1', 'release.json'),
    'field-notes-v1': ('1.0.0', BASE + 'chromatic-motion-lab-v1', 'custom-recipes/release.json'),
    'field-notes-v2': ('2.0.0', BASE + 'field-notes-v2', 'release.json'),
}
REGISTRY = 'Haike_video/config/motion-replay/numbered-02-05.json'


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _read(path):
    _require(path.is_file() and path.stat().st_size < 16 * 1024 * 1024, '缺少或过大的本地JSON输入')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _inside(root, value):
    path = (root / value).resolve()
    _require(path.is_relative_to(root.resolve()) and path.is_file(), '清单文件缺失或越过所属目录')
    return path


def _check_rows(root, rows):
    count = 0
    for row in rows:
        if row.get('virtual'):
            continue
        path = _inside(root, row['path'])
        _require(_sha(path) == row['sha256'], '输入或冻结文件身份变化，请恢复原文件或另建版本')
        count += 1
    return count


def _module(path):
    spec = importlib.util.spec_from_file_location('_motion_replay_original_' + path.parent.name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _probe(path):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    pair = resolve_ffmpeg_pair()
    _require(pair and Path(pair[1]).is_file(), '缺少现有FFprobe，不能核对本期媒体时钟；不自动安装')
    return json.loads(subprocess.check_output(
        [pair[1], '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
        timeout=30, creationflags=0x08000000 if __import__('os').name == 'nt' else 0))


def _duration(path, kind):
    probe = _probe(path)
    streams = [row for row in probe.get('streams', []) if row.get('codec_type') == kind]
    _require(streams, '本期媒体流类型不符合槽位')
    duration = float(streams[0].get('duration', probe.get('format', {}).get('duration', 0)))
    _require(math.isfinite(duration) and duration > 0, '本期媒体时长无效')
    return duration


def verify_release(template, *, workspace):
    """Also verifies every nested release entry, including the v4 base of v5."""
    root = Path(workspace).resolve()
    identity = template.get('template_id')
    _require(identity in SPECS and template.get('version') == SPECS[identity][0], '模板编号或精确版本不支持')
    canonical = next(row for row in _read(root / REGISTRY)['templates'] if row['template_id'] == identity)
    _require(template['sources'] == canonical['sources'], '来源合同与本适配器的版本登记不一致')
    count = _check_rows(root, canonical['sources'])
    release_file = root / SPECS[identity][1] / SPECS[identity][2]
    release = _read(release_file)
    _require(release['template_id'] == identity and release['version'] == SPECS[identity][0], '原定稿版本清单身份不匹配')
    if 'files' in release:
        rows = [{'path': (release_file.parent / name).resolve().relative_to(root).as_posix(), 'sha256': digest}
                for name, digest in release['files'].items()]
    else:
        rows = release['sources']
    count += _check_rows(root, rows)
    dependencies = release.get('dependencies', {})
    for name, version in dependencies.items():
        actual = _read(root / 'Haike_video/remotion-composer/node_modules' / name / 'package.json')
        _require(actual.get('version') == version, '已安装渲染依赖版本变化，需要重新验收')
    if identity == 'field-notes-v2':
        original = next(row for row in _read(root / REGISTRY)['templates'] if row['template_id'] == 'field-notes-v1')
        count += verify_release(original, workspace=root)['checked_files']
        # The one native grid import is private. Only its public identity is returned.
        config = _read(root / '.local/talkcraft-integration/state/config.json')
        upstream = Path(config['upstream']).resolve()
        native = _inside(upstream, 'template/cards/grid-to-hero.tsx')
        plan = _read(root / SPECS[identity][1] / 'selection.json')
        expected = plan['scenes'][1]['selections'][0]['source_sha256']
        _require(_sha(native) == expected, '模板5实际导入的私有网格组件版本不匹配')
        count += 1
    return {'status': 'pass', 'checked_files': count, 'scope': '原release全部源码与依赖；不授予私有素材分发许可'}


def _prepared_files(data, rows):
    # Prepared v2/v3 record absolute source paths; rendering always reads public/.
    public = data / 'public'
    for name, row in rows.items():
        target = _inside(public, name)
        _require(_sha(target) == row['sha256'], '本期public素材身份变化，不能继承旧审核')
    return len(rows)


def _nana(data, folder):
    manifest = _read(data / 'episode.json')
    _require(manifest.get('contract') == 'haike-nana-mint-episode-v1', '需要模板3已准备的episode.json')
    count = _prepared_files(data, manifest['files'])
    content = _read(data / 'public/content.json')
    _require(content == manifest['content'], '模板3实际消费的content.json与准备清单不同')
    original = _module(folder / 'prepare.py')
    original.validate_episode(content)
    _require(content['palette'] == _read(folder / 'template-profile.json')['palette'], '模板3薄荷色板已锁定')
    _require(abs(_duration(data / 'public' / content['voice'], 'audio') - content['duration']) <= .04,
             '完整音轨与本期语义主时钟不符，禁止拉伸声音')
    for scene in content['scenes']:
        for key in ('media', 'presenter', 'overlay'):
            media = scene.get(key)
            if media:
                path = _inside(data / 'public', media['file'])
                _require(media['file'] in manifest['files'], '未绑定必需媒体SHA')
                if media.get('kind') != 'image':
                    _require(_duration(path, 'video') + .04 >= original.media_duration(scene, key), '原速媒体不足以覆盖本期可见区间')
    # All these fields are actually consumed by the original TSX branches.
    cues = {'integration': {'partner', 'arrow'}, 'workflow': {'prompt', 'steps', 'preview'},
            'compare': {'arrow', 'after'}, 'question': {'answer'},
            'examples': {'presenterOff', 'overlay'}, 'logic': {'overlayEnd'}}
    for scene in content['scenes']:
        _require(set(scene.get('cues', {})) <= cues.get(scene['id'], set()), '本期含源码未消费的动作cue')
    return content, count


def _kinetic(data, folder):
    episode = _read(data / 'episode.json')
    _require(episode.get('contract') == 'kinetic-field-assets-v1' and episode.get('template_id') == 'kinetic-field-v1'
             and episode.get('template_version') == '1.0.0', '需要模板2已准备的精确版本输入')
    count = _prepared_files(data, episode['files'])
    request = {'contract': 'kinetic-field-request-v1', 'content': episode['content'],
               'avatar_sync': episode['sync'], 'rights': episode['rights'],
               'files': {name: {'path': str((data / 'public' / name).resolve()), 'sha256': row['sha256'],
                                'provenance': row.get('source', {}).get('provenance', episode['rights'])}
                         for name, row in episode['files'].items()}}
    _module(folder / 'prepare_inputs.py').validate(request, _probe)
    return episode, count


def _field_notes(data, identity, root):
    episode = _read(data / 'episode.json')
    _require(episode.get('schema') == 'haike.chromatic-avatar-episode/2' and episode.get('mode') == 'visual-preview'
             and episode.get('previewQuality') == 'low' and episode.get('durationInFrames') == 720
             and episode.get('fps') == 30, '模板4/5仅开放原24秒30fps低清静音输入')
    if identity == 'field-notes-v1':
        prep = _read(data / 'preparation.json')
        count = _check_rows(data, prep['files'])
        bound = {row['path'] for row in prep['files']}
        _require(any(row['path'] == 'episode.json' for row in prep['files']), '准备清单未绑定实际episode.json')
        spans = [(i * 180, (i + 1) * 180) for i in range(4)]
    else:
        build = _read(data / 'build-manifest.json')
        _require(build.get('templateId') == identity and build.get('version') == '2.0.0', '需要模板5原构建输入清单')
        count = _check_rows(data, build['assets'] + build['outputs'])
        bound = {row['path'] for row in build['assets']}
        _require(any(row['path'] == 'episode.json' for row in build['outputs']), '构建清单未绑定实际episode.json')
        plan = _read(root / SPECS[identity][1] / 'selection.json')
        spans = [(scene['from'], scene['to']) for scene in plan['scenes']]
    _require([(s['from'], s['to']) for s in episode['segments']] == spans, '固定四场时钟不允许重排或拉长')
    _require(len(episode['captions']) == 4 and [(c['from'], c['to']) for c in episode['captions']] == spans,
             '示意字幕必须覆盖固定四场')
    clips = episode.get('presenterClips', [])
    _require(len(clips) == 1 and clips[0]['from'] == 0 and clips[0]['to'] == 720, '需要原连续24秒人物窗')
    assets = episode.get('photos', []) + [clips[0]['src'], '/assets/font.ttf']
    _require(len(episode.get('photos', [])) >= (7 if identity == 'field-notes-v2' else 5), '缺少固定照片索引所需素材')
    for name in assets:
        _require(isinstance(name, str) and name.startswith('/assets/') and '?' not in name and '#' not in name,
                 '模板4/5只消费已准备的本地assets资源')
        _inside(data, name.lstrip('/'))
        _require(name.lstrip('/') in bound, '必需资源未在输入清单绑定SHA')
    _require(_duration(_inside(data, clips[0]['src'].lstrip('/')), 'video') + 1 / 30 >= 24, '连续人物素材不足24秒')
    episode = deepcopy(episode)
    episode['fontSrc'] = '/assets/font.ttf'
    episode['fontFamily'] = 'Haike Custom Field Notes' if identity == 'field-notes-v1' else 'Field Notes Review'
    return episode, count


def resolve_events(template, content):
    """Resolve the exact fields the renderer reads; never synthesize ASR anchors."""
    result = []
    scenes = {row['id']: row for row in content.get('scenes', [])}
    for event in template['timeline']['events']:
        row = deepcopy(event)
        anchor = row['anchor']
        if isinstance(anchor, dict) and anchor.get('scene_id'):
            scene = scenes[anchor['scene_id']]
            local = scene.get('cues', {}).get(anchor.get('cue'), anchor.get('default_local_seconds', 0)) + anchor.get('offset_seconds', 0)
            row['resolved_seconds'] = scene['start'] + local
            row['resolved_frame'] = round(row['resolved_seconds'] * 30)
            row['scene_window_seconds'] = [scene['start'], scene['end']]
        result.append(row)
    return result


def prepare(template, request, *, workspace):
    """Validate an already prepared episode and return consumable renderer props.

    request = {data: <prepared directory>, action_ids?: <entire ordered binding>}
    Missing data returns an explicit blocker. Unknown fields and action edits fail.
    """
    if template.get('template_id') == 'field-notes-v2' and template.get('version') == '2.1.0':
        from backlot.motion_replay_field_notes_render import prepare as prepare_video
        return prepare_video(template, request, workspace=workspace)
    _require(isinstance(request, dict) and not (set(request) - {'data', 'action_ids'}), '仅接受data和完整action_ids；换稿先运行原prepare入口')
    root = Path(workspace).resolve()
    release = verify_release(template, workspace=root)
    canonical = next(row for row in _read(root / REGISTRY)['templates'] if row['template_id'] == template['template_id'])
    expected = [row['id'] for row in canonical['actions']]
    if 'action_ids' in request:
        _require(request['action_ids'] == expected, '本版本动作顺序锁定；不支持选择子集、替换或重排动作')
    result = {'status': 'blocked', 'execution_status': 'not_submitted', 'submitted': False,
              'renderer': deepcopy(canonical['renderer']), 'release_verification': release,
              'action_bindings': deepcopy(canonical['actions']), 'blockers': [],
              'inputs': None, 'props': None, 'queue_route': None,
              'reproduction': deepcopy(canonical['reproduction']),
              'validation_scope': '仅输入/源码/媒体时钟核验；不继承旧视觉/听审，不执行制作'}
    if 'data' not in request:
        result['blockers'] = ['缺少data：提供原准备入口生成的独立本期目录，不从私有默认自动取材']
        return result
    _require(isinstance(request['data'], str) and request['data'].strip(), 'data必须是本地目录字符串')
    data = Path(request['data'])
    data = (data if data.is_absolute() else root / data).resolve()
    _require(data.is_dir(), '本期准备目录不存在')
    identity = canonical['template_id']
    folder = root / SPECS[identity][1]
    if identity == 'kinetic-field-v1':
        content, count = _kinetic(data, folder)
        props = {'content': content['content']}
        public = data / 'public'
        route = {'entrypoint': 'Haike_video/scripts/kinetic_field_preview.py',
                 'argv': ['--install-root', str(root), '--data', str(data), '--phase', 'stills'],
                 'next': '实际看帧后写本期design-review；明确导出请求后同入口--phase video'}
    elif identity == 'nana-mint-explainer-v1':
        content, count = _nana(data, folder)
        props = {'episodeFile': 'content.json', 'episode': content}
        public = data / 'public'
        route = {'entrypoint': 'Haike_video/scripts/nana_mint_preview.py',
                 'argv': ['--install-root', str(root), '--data', str(data), '--mode', 'frames'],
                 'next': '可显式指定runtime-root；本期bundle/真实帧审核通过后同入口--mode render'}
    else:
        content, count = _field_notes(data, identity, root)
        props = {'templateId': identity, 'version': canonical['version'], 'episode': content, 'actionIds': expected}
        public = data
        route = None
        result['blockers'].append('原模板4/5仅接本地Player预览；尚无合法统一父队列完整渲染路由，有声/高清另适配')
    consumed = (data / 'public/content.json') if identity == 'nana-mint-explainer-v1' else (data / 'episode.json')
    result.update(status='prepared', inputs={'data': str(data), 'public_dir': str(public),
                  'episode_manifest': str(data / 'episode.json'), 'renderer_input_file': str(consumed),
                  'verified_media_files': count},
                  props=props, queue_route=route, timeline=resolve_events(canonical, content),
                  execution_status='prepared_only' if route else 'preview_prepared_production_blocked')
    return result
