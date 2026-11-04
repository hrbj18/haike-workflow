"""New public-source motion identity; original packages keep their own identity.

This module consumes only pinned public code and SHA-bound local inputs. Queue
dispatch is owned by the root integration; no registry command is executable.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import wave

from backlot.motion_public_io_v1 import WorkError, atomic_private, fingerprint, read_json, sha

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'templates/motiongit-public-components-v1'
CONTRACT = 'haike.motion-public-production/1'
KIND = 'studio_investment_recompose'
REQUEST_FILE = 'motion-public-request.json'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
FFMPEG9_DESCRIPTOR_SHA = '1d7055cadccd60e2442c5d279083b3dd8c9a46c1bae6d317e78a344826e6aa29'


def require(condition, message):
    if not condition:
        raise WorkError(message)


def component():
    path = ROOT / 'scripts/build_motion_public_components.py'
    spec = importlib.util.spec_from_file_location('haike_public_component_builder', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify(TEMPLATE)


def bound(value):
    require(isinstance(value, dict) and set(value) == {'path', 'sha256'}, '输入文件须精确绑定path和sha256')
    path = Path(value['path'])
    require(path.is_file() and not path.is_symlink() and sha(path) == value['sha256'], '输入文件缺失、为链接或摘要改变')
    return path.resolve()


def runtime():
    """Location-independent byte identity of execution, separate from the host."""
    manifest = component()
    identities = {
        'execution/motion_public_execution_v1.py': sha(Path(__file__)),
        'execution/motion_public_io_v1.py': sha(ROOT / 'backlot/motion_public_io_v1.py'),
        'execution/motion_public_observed_v1.py': sha(ROOT / 'backlot/motion_public_observed_v1.py'),
        'execution/motion_public_dark_v1.py': sha(ROOT / 'backlot/motion_public_dark_v1.py'),
        'execution/motion_public_dark_schema_v1.py': sha(ROOT / 'backlot/motion_public_dark_schema_v1.py'),
        'execution/motion_public_dark_remotion_v1.py': sha(ROOT / 'backlot/motion_public_dark_remotion_v1.py'),
        'component/observed-controls-v1.js': sha(TEMPLATE / 'observed-controls-v1.js'),
        'component/FFMPEG9.json': sha(TEMPLATE / 'FFMPEG9.json'),
        'execution/build_motion_public_components.py': sha(ROOT / 'scripts/build_motion_public_components.py'),
        'component/COMPONENT.json': sha(TEMPLATE / 'COMPONENT.json'),
        'component/capture_runtime.mjs': sha(TEMPLATE / 'capture_runtime.mjs'),
        'python/venv-executable': sha(Path(sys.executable)),
        'python/base-executable': sha(Path(sys._base_executable)),
    }
    for row in manifest['files']:
        identities['component/' + row['path']] = sha(TEMPLATE / row['path'])
    for path in sorted((TEMPLATE / 'dark-v1').rglob('*')):
        if path.is_file():
            identities['component/' + path.relative_to(TEMPLATE).as_posix()] = sha(path)
    python_dependencies = {}
    for name in ('numpy', 'fonttools', 'pillow'):
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            require(name != 'numpy', '动作音效所需NumPy缺失，须先准备固定运行依赖')
            python_dependencies[name] = 'not-installed; dependent optional source route cannot be claimed available'
            continue
        python_dependencies[name] = distribution.version
        base = Path(distribution.locate_file('')).resolve()
        for relative in distribution.files or []:
            path = Path(distribution.locate_file(relative)).resolve()
            if path.is_relative_to(base) and path.is_file() and path.suffix not in {'.pyc', '.pyo'} and '__pycache__' not in path.parts:
                identities['python/site-packages/' + path.relative_to(base).as_posix()] = sha(path)
    base = Path(sys.base_prefix)
    for directory in (base / 'Lib', base / 'DLLs'):
        if directory.is_dir():
            for path in directory.rglob('*'):
                if path.is_file() and not {'site-packages', '__pycache__', 'test', 'tests'} & set(path.relative_to(base).parts) and path.suffix not in {'.pyc', '.pyo'}:
                    identities['python/base/' + path.relative_to(base).as_posix()] = sha(path)
    for path in base.iterdir():
        if path.is_file() and path.suffix.lower() in {'.dll', '.exe', '.zip'}:
            identities['python/base/' + path.name] = sha(path)
    return {'implementation_id': 'haike.motion-public-execution/1',
            'files': [{'logical_path': name, 'sha256': identities[name]} for name in sorted(identities)],
            'python_abi': sys.implementation.cache_tag, 'python_version': sys.version, 'python_dependencies': python_dependencies}


def environment(tool_root, dependency_root, ffmpeg_root=None, *, engine=None):
    """Only known binary and npm/font bytes may execute, never caller commands."""
    if engine == 'dark-remotion/1':
        from backlot.motion_public_dark_remotion_v1 import environment as remotion_environment
        return remotion_environment(tool_root, dependency_root, ffmpeg_root)
    tool_root, dependency_root = Path(tool_root).resolve(), Path(dependency_root).resolve()
    tools = read_json(TEMPLATE / 'TOOLS.json')
    expected = [*[row for key, row in tools['tools'].items() if ffmpeg_root is None or key not in {'ffmpeg', 'ffprobe'}], *tools['browser_files']]
    identities = {}
    for row in expected:
        path = tool_root / row['path']
        require(path.resolve().is_relative_to(tool_root) and path.is_file() and not path.is_symlink()
                and sha(path) == row['sha256'], '公开组件工具缺失或不是已核版本：' + row['path'])
        identities['tools/' + row['path']] = row['sha256']
    if ffmpeg_root is not None:
        require(sha(TEMPLATE / 'FFMPEG9.json') == FFMPEG9_DESCRIPTOR_SHA, '新FFmpeg来源清单改变，禁止执行未知二进制')
        root = Path(ffmpeg_root).resolve()
        for row in read_json(TEMPLATE / 'FFMPEG9.json')['files']:
            path = root / row['path']
            require(path.resolve().is_relative_to(root) and path.is_file() and not path.is_symlink() and sha(path) == row['sha256'],
                    'FFmpeg9实际文件或原许可通知缺失/改变：' + row['path'])
            identities['ffmpeg9/' + row['path']] = row['sha256']
    deps = read_json(TEMPLATE / 'DEPENDENCIES.json')
    for item in deps['components']:
        if 'files' in item:
            rows = [(dependency_root / 'node_modules' / item['component'] / row['path'], row['sha256']) for row in item['files']]
        else:
            rows = [(dependency_root / 'fonts' / item['component'], item['sha256'])]
        for path, expected_sha in rows:
            require(path.resolve().is_relative_to(dependency_root) and path.is_file() and not path.is_symlink()
                    and sha(path) == expected_sha, '公开组件依赖缺失或摘要改变：' + path.name)
            identities['dependencies/' + path.relative_to(dependency_root).as_posix()] = expected_sha
    rows = [{'logical_path': name, 'sha256': identities[name]} for name in sorted(identities)]
    if engine == 'dark-groups/1':
        from backlot.motion_public_dark_v1 import dependency_files
        rows += dependency_files(dependency_root)
    return tools, rows


def norm(text):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', text).lower()


def real_clock(script, asr, voice, corrections=()):
    """Accept measured sentence/word evidence; never infer times from text length."""
    text = read_json(script).get('text')
    data = read_json(asr)
    require(isinstance(text, str) and text.strip() and data.get('audio_sha256') == sha(voice), '文稿或ASR未绑定本期完整口播')
    segments = deepcopy(data.get('segments'))
    require(isinstance(segments, list) and segments, '缺少真实ASR句词')
    require(isinstance(corrections, (list, tuple)), '转录校正须是明确清单')
    for correction in corrections:
        require(isinstance(correction, dict) and set(correction) == {'from', 'to', 'expected_count'}
                and isinstance(correction['from'], str) and correction['from']
                and isinstance(correction['to'], str) and len(correction['from']) == len(correction['to'])
                and type(correction['expected_count']) is int and correction['expected_count'] > 0, '仅开放等长、定次数转录文字校正，不改变ASR时钟')
        count = sum(row['text'].count(correction['from']) for row in segments)
        require(count == correction['expected_count'], '转录校正次数与真实ASR不一致')
        for row in segments:
            row['text'] = row['text'].replace(correction['from'], correction['to'])
    with wave.open(str(voice), 'rb') as stream:
        duration = stream.getnframes() / stream.getframerate()
        require(stream.getcomptype() == 'NONE' and stream.getsampwidth() == 2, '口播须为原速PCM16 WAV')
    previous = 0.0
    for row in segments:
        require(isinstance(row.get('text'), str) and 0 <= row['start'] < row['end'] <= duration + .025
                and row['start'] >= previous - .001, 'ASR句时钟无效或重叠')
        previous = row['end']
        words = row.get('words')
        require(isinstance(words, list) and words, '语义事件须有真实词时钟')
        previous_word = row['start']
        for word in words:
            require(isinstance(word.get('text'), str) and row['start'] <= word['start'] < word['end'] <= row['end'] + .001
                    and word['start'] >= previous_word - .001, 'ASR词时钟无效或重叠')
            previous_word = word['end']
    require(norm(''.join(s['text'] for s in segments)) == norm(text), 'ASR全文与原稿不一致；须先提交有来源的转录校正，不能丢稿或猜时码')
    return text, segments, duration


def semantic_spec(value, pack, segments, duration):
    """Bind complete scene ranges and internal cues to exact ASR indices."""
    fps = pack['fps']
    frames = math.ceil(duration * fps)
    sources = {scene['id']: scene for scene in pack['scenes']}
    require(isinstance(value.get('scenes'), list) and value['scenes'], '缺少完整公开动作语义计划')
    targets = []
    cursor = 0
    ids = set()
    for index, row in enumerate(value['scenes']):
        require(isinstance(row, dict) and not set(row) - {'id', 'action', 'sentence_start', 'sentence_end', 'slots', 'cues'}, '动作包含未开放字段')
        first, last = row.get('sentence_start'), row.get('sentence_end')
        require(type(first) is int and type(last) is int and first == cursor and first < last <= len(segments), '动作须按顺序完整覆盖真实句子')
        require(isinstance(row.get('id'), str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,80}', row['id']) and row['id'] not in ids, '动作实例ID无效或重复')
        ids.add(row['id']); cursor = last
        action = row.get('action')
        require(action in sources, '该公开版本没有所请求的动作；不能改用另一原模板控件')
        source = sources[action]
        start = 0 if index == 0 else round(segments[first]['start'] * fps)
        end = frames if index == len(value['scenes']) - 1 else round(segments[last]['start'] * fps)
        require(end - start >= source.get('minFrames', 1), '真实口播时窗不足以完成本组动作')
        allowed_cues = {cue['id']: cue for cue in source.get('cues', [])}
        cues = {}
        for cue_id, event in row.get('cues', {}).items():
            require(cue_id in allowed_cues and isinstance(event, dict) and not set(event) - {'sentence', 'word'}, '内部动作须绑定已登记事件和真实句词')
            sentence, word = event.get('sentence'), event.get('word')
            require(type(sentence) is int and first <= sentence < last, '事件句编号不在本场景')
            at = segments[sentence]['start']
            if word is not None:
                require(type(word) is int and 0 <= word < len(segments[sentence]['words']), '事件词编号无效')
                at = segments[sentence]['words'][word]['start']
            cues[cue_id] = {'at': at}
        required = {name for name, cue in allowed_cues.items() if cue.get('required', cue.get('kind') in {'word', 'semantic'})}
        require(required <= set(cues), '缺少必需内部动作的真实句词绑定：' + ','.join(sorted(required - set(cues))))
        targets.append({'id': row['id'], 'sceneId': action, 'startFrame': start, 'endFrame': end,
                        'cues': cues, 'slots': deepcopy(row.get('slots', {}))})
    require(cursor == len(segments), '动作计划未覆盖完整口播')
    spec = {'pack': pack['id'], 'version': pack['version'], 'fps': fps, 'layout': value.get('layout', 'portrait'),
            'brand': value['brand'], 'presenterLabel': value.get('presenter_label', 'AI数字人讲述'),
            'transcript': segments, 'scenes': targets, 'music': {'mode': 'none'}, 'repairPolicy': {'mode': 'off'},
            'fontPolicy': value.get('font_policy', 'exact')}
    if 'face_tracking' in value:
        spec['faceTracking'] = deepcopy(value['face_tracking'])
    return spec, frames


def preflight(value):
    if isinstance(value, dict) and value.get('engine') == 'dark-remotion/1':
        from backlot.motion_public_dark_remotion_v1 import preflight as remotion_preflight
        return remotion_preflight(value)
    if isinstance(value, dict) and value.get('engine') == 'dark-groups/1':
        raise WorkError('深色frame bridge仅是未验收实验；公共制作须保留已验证原renderer路线')
    if isinstance(value, dict) and value.get('engine') == 'observed-controls/1':
        from backlot.motion_public_observed_v1 import preflight as observed_preflight
        return observed_preflight(value)
    require(isinstance(value, dict) and not set(value) - {'pack_key', 'reference_id', 'title', 'brand', 'script', 'asr', 'assets', 'scenes', 'layout', 'presenter_label', 'font_policy', 'external_fonts', 'face_tracking', 'caption_corrections', 'tool_root', 'dependency_root', 'ffmpeg_root', 'work_root', 'source_receipts'}, '公开运行输入字段无效')
    manifest = component()
    key, reference = value.get('pack_key'), value.get('reference_id')
    require(key in manifest['packs'] and reference in manifest['references'] and key in manifest['references'][reference]['packs'], '公开组件与原参考身份关系不符')
    require(all(isinstance(value.get(k), str) and value[k].strip() for k in ('title', 'brand')), '缺少本期标题或品牌')
    assets = value.get('assets')
    require(isinstance(assets, dict) and all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', name) for name in assets), '素材文件名无效')
    require(not {'script.json', 'asr.json'} & set(assets), '素材名不能覆盖文稿或ASR证据')
    paths = {name: bound(item) for name, item in assets.items()}
    require({'voice.wav', 'presenter.mp4'} <= set(paths), '缺少完整口播与原速人物母视频；不生成占位人物')
    script, asr = bound(value['script']), bound(value['asr'])
    text, segments, duration = real_clock(script, asr, paths['voice.wav'], value.get('caption_corrections', ()))
    pack = read_json(TEMPLATE / manifest['packs'][key]['path'] / 'manifest.json')
    require(isinstance(value.get('scenes'), list) and value['scenes'], '缺少完整动作语义输入')
    for row in value['scenes']:
        scene = next((s for s in pack['scenes'] if s['id'] == row.get('action')), None)
        require(scene is not None, '公开动作不存在')
        declared_slots = {s['id']: s for s in scene.get('slots', [])}
        require(isinstance(row.get('slots', {}), dict) and set(row.get('slots', {})) <= set(declared_slots), '动作包含未知槽')
        for slot_id, supplied in row.get('slots', {}).items():
            kind = declared_slots[slot_id]['type']
            if kind in {'image', 'video', 'audio', 'sequence', 'wall', 'wall-sprites'}:
                require(isinstance(supplied, dict) and supplied.get('asset') in paths
                        and not set(supplied) - {'asset', 'offset'}, '媒体槽必须绑定本期已验资产和原速入点')
                require(isinstance(supplied.get('offset', 0), (float, int)) and not isinstance(supplied.get('offset', 0), bool)
                        and supplied.get('offset', 0) >= 0, '真实媒体入点无效')
    external_fonts = value.get('external_fonts', {})
    require(isinstance(external_fonts, dict) and set(external_fonts) <= {f['id'] for f in pack.get('externalFonts', [])}
            and all(name in paths for name in external_fonts.values()), '原字体须绑定已核素材，不能传任意路径')
    spec, frames = semantic_spec(value, pack, segments, duration)
    tools, environment_files = environment(value['tool_root'], value['dependency_root'], value.get('ffmpeg_root'))
    return {'paths': paths, 'script': script, 'asr': asr, 'text': text, 'segments': segments, 'duration': duration,
            'spec': spec, 'frames': frames, 'pack': manifest['packs'][key], 'tools': tools,
            'environment': environment_files, 'reference': {'template_id': reference, **manifest['references'][reference]},
            'original_package_equivalence': False}


def _env(request):
    root = Path(request['tool_root'])
    env = os.environ.copy()
    env['PATH'] = os.pathsep.join([str(_ffmpeg(request).parent), str(root / 'node'), env.get('PATH', '')])
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['ADU_PYTHON'] = sys.executable
    return env


def _ffmpeg(request):
    return Path(request.get('ffmpeg_root') or (Path(request['tool_root']) / 'ffmpeg')) / 'bin/ffmpeg.exe'


def _ffprobe(request):
    return _ffmpeg(request).with_name('ffprobe.exe')


def _command(args, folder, request, name, *, timeout=1800):
    result = subprocess.run([str(a) for a in args], cwd=folder, env=_env(request), capture_output=True,
        encoding='utf8', errors='replace', timeout=timeout, creationflags=NO_WINDOW)
    # Local-only diagnostics, never exported as public component source.
    (folder / (name + '.stdout.log')).write_text(result.stdout, encoding='utf8')
    (folder / (name + '.stderr.log')).write_text(result.stderr, encoding='utf8')
    require(result.returncode == 0, name + '失败：' + result.stderr[-1500:])
    return result.stdout


def _slot_media(source, target, assets, folder, request):
    """Prepare original-rate frames from explicitly bound videos, with receipts."""
    values = deepcopy(target['slots'])
    operations = []
    for slot in source.get('slots', []):
        slot_id, kind = slot['id'], slot['type']
        supplied = values.get(slot_id)
        if supplied is None:
            continue
        if kind in {'image', 'video', 'audio', 'sequence', 'wall', 'wall-sprites'}:
            path = assets[supplied['asset']]
            if kind in {'image', 'audio'}:
                values[slot_id] = str(path)
            elif kind == 'video':
                values[slot_id] = {'path': str(path), 'offset': supplied.get('offset', 0), 'rate': 1}
            elif kind == 'sequence':
                definition = request['_pack'].get('assetDefinitions', {}).get(slot_id, {})
                count = definition.get('originalFrames', slot.get('originalFrames'))
                fps = definition.get('fps', request['_pack']['fps'])
                require(type(count) is int and count > 0, '原序列缺少固定帧数合同')
                destination = folder / 'media' / (target['id'] + '-' + slot_id)
                destination.mkdir(parents=True, exist_ok=False)
                offset = supplied.get('offset', 0)
                probe = json.loads(_command([_ffprobe(request), '-v', 'error',
                    '-show_format', '-show_streams', '-of', 'json', path], folder, request, 'probe-' + target['id'] + '-' + slot_id))
                video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
                require(offset + count / fps <= float(video.get('duration') or probe['format']['duration']) + .001,
                        '原速序列素材不够长；禁止循环、变速或尾帧补齐')
                color = json.loads(_command([sys.executable, '-X', 'utf8', '-B', folder / 'runtime-source/scripts/color_management.py',
                    '--image', path], folder, request, 'color-' + target['id'] + '-' + slot_id))
                require(color['source_sha256'] == sha(path), '颜色探测绑定的真实源改变')
                _command([_ffmpeg(request), '-nostdin', '-v', 'error', '-n',
                    '-ss', str(offset), '-i', path, '-an', '-vf', 'fps=' + str(fps) + ',' + color['filter'], '-frames:v', str(count),
                    '-q:v', '2', destination / 'f_%04d.jpg'], folder, request, 'extract-' + target['id'] + '-' + slot_id)
                frames = sorted(destination.glob('f_*.jpg'))
                require(len(frames) == count, '原速序列实际解码帧不足')
                values[slot_id] = {'path': str(destination), 'glob': '*.jpg'}
                operations.append({'scene': target['id'], 'slot': slot_id, 'source_sha256': sha(path),
                    'offset': offset, 'fps': fps, 'frames': count, 'playback_rate': 1, 'color': color,
                    'files': {p.name: sha(p) for p in frames}})
            else:
                # Full wall choreography requires its real distinct-work index.
                # A video repeated over a grid is not accepted as that evidence.
                raise WorkError('完整作品墙尚需逐作品SHA与真实去重索引适配；不能用占位图或重复帧冒充闭包')
    return values, operations


def build_project(project, folder, request):
    if request.get('input_engine') == 'dark-remotion/1':
        from backlot.motion_public_dark_remotion_v1 import build_project as remotion_build
        return remotion_build(project, folder, request)
    if request.get('input_engine') == 'dark-groups/1':
        from backlot.motion_public_dark_v1 import build_project as dark_build
        return dark_build(project, folder, request)
    if request.get('input_engine') == 'observed-controls/1':
        from backlot.motion_public_observed_v1 import build_project as observed_build
        return observed_build(project, folder, request)
    prepared = folder / 'prepared.json'
    if prepared.exists():
        receipt = read_json(prepared)
        require(all((folder / name).resolve().is_relative_to(folder.resolve()) and not (folder / name).is_symlink()
                    and (folder / name).is_file() and sha(folder / name) == digest for name, digest in receipt['files'].items()), '已准备工程改变，不能静默复用')
        return receipt
    upstream = folder / 'runtime-source'
    require(not upstream.exists(), '前次准备未完成；保留失败现场，修正后冻结新项目')
    shutil.copytree(TEMPLATE / 'upstream', upstream)
    dependencies = Path(request['dependency_root'])
    fonts = upstream / 'assets/fonts'; fonts.mkdir(parents=True, exist_ok=True)
    for name in ('NotoSansSC.ttf', 'NotoSansMono.ttf', 'notosanssc-OFL.txt', 'notosansmono-OFL.txt'):
        shutil.copy2(dependencies / 'fonts' / name, fonts / name)
    manifest = component()
    pack_relative = Path(manifest['packs'][request['pack_key']]['path']).relative_to('upstream')
    pack_path = upstream / pack_relative
    pack = read_json(pack_path / 'manifest.json')
    assets = {name: project / 'assets/motion-public' / name for name in request['origins']}
    spec = deepcopy(request['spec'])
    spec['externalFontFiles'] = {key: str(assets[name]) for key, name in request['external_fonts'].items()}
    operations = []
    sources = {s['id']: s for s in pack['scenes']}
    for scene in spec['scenes']:
        scene['slots'], made = _slot_media(sources[scene['sceneId']], scene, assets, folder, {**request, '_pack': pack})
        operations.extend(made)
    # Join the exact narration with unchanged presenter video; do not take a
    # source clip's unrelated sound as the new narration or alter playback rate.
    master = folder / 'narration-master.mov'
    toolroot = Path(request['tool_root'])
    _command([_ffmpeg(request), '-nostdin', '-v', 'error', '-n', '-i', assets['presenter.mp4'],
        '-i', assets['voice.wav'], '-map', '0:v:0', '-map', '1:a:0', '-vf', 'fps=' + str(request['spec']['fps']),
        '-frames:v', str(request['frames']), '-c:v', 'libx264', '-crf', '16', '-preset', 'medium',
        '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2', '-t', str(request['frames'] / request['spec']['fps']), master], folder, request, 'join-narration')
    # BGM is an explicit independent input, with its original waveform and SHA.
    if 'music.wav' in assets:
        spec['music'] = {'mode': 'track', 'path': str(assets['music.wav']), 'offset': 0}
    atomic_private(folder / 'spec.json', spec)
    subtitles = [{'id': str(i), 't0': s['start'], 't1': s['end'], 'zh': s['text'], 'en': '',
        'wordTimesReliable': True, 'sp': [[w['start'], w['end'], len(w['text'])] for w in s['words']]}
        for i, s in enumerate(spec['transcript'])]
    (folder / 'subs.js').write_text('const SUBS=' + json.dumps(subtitles, ensure_ascii=False) + ';\n', encoding='utf8')
    _command([sys.executable, '-X', 'utf8', '-B', upstream / 'scripts/build_macro_project.py', 'project', pack_path,
        folder / 'spec.json', master, folder / 'project', '--subs-js', folder / 'subs.js'], folder, request, 'build-public-project')
    generated = folder / 'project'
    # The public renderer supports this explicit switch. No signature artwork
    # or personal brand assets were acquired or redistributed in this source.
    atomic_private(generated / 'output-signature.json', {'schema': 'adu-output-signature/1', 'enabled': False})
    # Only encoder settings change in this explicitly derived public renderer.
    # Source scene geometry, clocks, READY/decode gates and frame loop stay intact.
    renderer = upstream / 'scripts/render_project.mjs'
    original_renderer_sha = sha(renderer)
    original = renderer.read_text('utf8')
    needle = "'-crf', '15'"
    require(original.count(needle) == 1, '公开编码器入口改变，禁止猜测替换')
    replacement = "'-threads', '1', '-b:v', '20500k', '-minrate', '20500k', '-maxrate', '20500k', '-bufsize', '2000k', '-x264-params', 'nal-hrd=cbr:force-cfr=1:filler=1'"
    renderer.write_text(original.replace(needle, replacement), encoding='utf8')
    _command([toolroot / 'node/node.exe', TEMPLATE / 'capture_runtime.mjs', generated,
        dependencies / 'node_modules/playwright-core', toolroot / 'browser/chrome-headless-shell.exe', generated / 'sfx.json'],
        folder, request, 'capture-public-runtime')
    _command([sys.executable, '-X', 'utf8', '-B', generated / 'audio.py'], folder, request, 'public-sound')
    mix_audio(project, folder, request)
    files = {p.relative_to(folder).as_posix(): sha(p) for directory in (generated, upstream) for p in directory.rglob('*') if p.is_file()}
    receipt = {'schema': 'haike.motion-public-prepared/1', 'request_sha256': request['request_sha256'],
        'files': files, 'media_operations': operations, 'full_original_template_closure': False,
        'font_report': read_json(generated / 'font_policy.json'), 'build_report': read_json(generated / 'macro_build_report.json'),
        'renderer_derivation': {'upstream_sha256': original_renderer_sha, 'derived_sha256': sha(renderer),
            'change': 'CRF15 to single-thread 20.5Mbps CBR only; actual public readiness and frame gates retained'}}
    atomic_private(prepared, receipt)
    return receipt


def render_project(project, folder, request):
    if request.get('input_engine') == 'dark-remotion/1':
        from backlot.motion_public_dark_remotion_v1 import render_project as remotion_render
        return remotion_render(project, folder, request)
    generated, upstream = folder / 'project', folder / 'runtime-source'
    plan = read_json(generated / 'macro_plan.json')
    tools = read_json(TEMPLATE / 'TOOLS.json')['tools']
    toolroot = Path(request['tool_root'])
    command = [toolroot / tools['node']['path'], upstream / 'scripts/render_project.mjs', generated / 'index.html',
        '--playwright-module', Path(request['dependency_root']) / 'node_modules/playwright-core',
        '--browser', toolroot / tools['browser']['path'], '--fps', str(plan['fps']), '--width', str(plan['width']),
        '--height', str(plan['height'])]
    if request['phase'] == 'preview':
        preview = folder / 'preview'
        require(not preview.exists(), '预览目录已存在，须读回原任务或保留失败现场后冻结新项目')
        times = sorted({max(0, min((plan['end_frame'] - 1) / plan['fps'], frame / plan['fps']))
            for scene in plan['scenes'] for frame in [scene['output_start_frame'],
                scene['output_start_frame'] + 6, round((scene['output_start_frame'] + scene['output_end_frame']) / 2),
                scene['output_end_frame'] - 1] + [c['outputFrame'] + offset
                    for c in scene.get('cues', []) if c.get('outputFrame') is not None
                    for offset in (0, round(plan['fps'] * .3), round(plan['fps'] * .65))
                    if c['outputFrame'] + offset < scene['output_end_frame']]})
        _command([*command, '--stills-dir', preview, '--times', ','.join(map(str, times))], folder, request, 'public-preview')
        images = [{'name': p.name, 'sha256': sha(p)} for p in sorted(preview.glob('*.png'))]
        require(len(images) == len(times), '动作预览图片不完整')
        atomic_private(folder / 'preview.json', {'images': images, 'times': times, 'request_sha256': request['request_sha256'],
            'scope': 'all-selected-public-actions-sampled', 'original_fidelity': 'pending'})
        return {'status': 'completed', 'stage': '公开组件实际动作预览就绪，待逐图和原参考对照',
            'result': {'images': images, 'preview_sha256': sha(folder / 'preview.json'), 'qa_status': 'pending'}}
    require(read_json(folder / 'visual-review.json').get('inspected_images'), '缺少本期实际动作预览审核')
    binding = request.get('review_binding')
    require(binding and sha(folder / 'preview.json') == binding['preview_sha256']
            and all(sha(folder / 'preview' / row['name']) == row['sha256'] for row in binding['images']), '正式导出实际预览身份改变')
    # Actual runtime SFX extraction and mix must be present before a full export.
    require((generated / 'sfx.json').is_file(), '原动作音效回执尚未生成，不能静音导出冒充完整交付')
    output = folder / 'motion-public.mp4'
    if not (folder / 'result.json').exists():
        _command([*command, '--output', output, '--audio', generated / 'final.wav'], folder, request, 'public-render', timeout=7200)
        probe = json.loads(_command([_ffprobe(request), '-v', 'error', '-count_frames', '-show_streams',
            '-show_format', '-of', 'json', output], folder, request, 'public-output-probe'))
        video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
        require(int(video['nb_read_frames']) == request['frames'] and int(video['bit_rate']) >= 20_000_000
                and (video['width'], video['height']) == (plan['width'], plan['height'])
                and video['codec_name'] == 'h264' and video['pix_fmt'] == 'yuv420p'
                and audio['sample_rate'] == '48000' and audio['channels'] == 2, '完整成片编码、帧数或码率不合格')
        _command([_ffmpeg(request), '-nostdin', '-v', 'error', '-xerror', '-i', output, '-f', 'null', '-'], folder, request, 'public-decode')
        _command([_ffmpeg(request), '-nostdin', '-v', 'info', '-i', output,
            '-af', 'loudnorm=I=-16:TP=-1.8:LRA=11:print_format=json', '-f', 'null', '-'], folder, request, 'public-output-loudness')
        loud_text = (folder / 'public-output-loudness.stderr.log').read_text('utf8')
        loud = json.loads(loud_text[loud_text.rfind('{'):loud_text.rfind('}') + 1])
        require(float(loud['input_tp']) <= -1.5, '最终AAC真峰值超过-1.5dBTP，须保留视频只修本地混音')
        atomic_private(folder / 'result.json', {'output_sha256': sha(output), 'media': probe, 'loudness': loud, 'full_decode': 'passed',
            'original_fidelity': 'pending', 'continuous_listening': 'pending', 'full_original_template_closure': False})
    require(sha(output) == read_json(folder / 'result.json')['output_sha256'], '原公开组件成片已改变')
    return {'status': 'completed', 'stage': '公开组件完整视频已合成，原样式与视听验收待核',
        'result': {'output_path': str(output), 'output_sha256': sha(output), 'qa_status': 'pending'}}


def mix_audio(project, folder, request):
    generated = folder / 'project'
    voice = project / 'assets/motion-public/voice.wav'
    ffmpeg = _ffmpeg(request)
    duration = request['frames'] / request['spec']['fps']
    # Measured voice is continuous at original speed. Only the fractional silent
    # tail is padded to the frame clock. SFX are the actual mapped runtime events.
    graph = ('[0:a]aresample=48000,apad,atrim=duration=' + str(duration) + ',asplit=2[v][key];'
             '[1:a]volume=0.5[m];[m][key]sidechaincompress=threshold=0.025:ratio=4:attack=20:release=250[duck];'
             '[2:a]volume=0.35[s];[v][duck][s]amix=inputs=3:normalize=0:duration=longest,'
             'alimiter=limit=0.78:level=0,atrim=duration=' + str(duration) + '[out]')
    target = generated / 'final.wav'
    _command([ffmpeg, '-nostdin', '-v', 'error', '-n', '-i', voice, '-i', generated / 'bgm.wav',
        '-i', generated / 'sfx.wav', '-filter_complex', graph, '-map', '[out]', '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2', target],
        folder, request, 'public-mix')
    atomic_private(folder / 'audio-receipt.json', {'voice_sha256': sha(voice), 'bgm_sha256': sha(generated / 'bgm.wav'),
        'sfx_sha256': sha(generated / 'sfx.wav'), 'mix_sha256': sha(target), 'filter_complex': graph,
        'voice_playback_rate': 1, 'device_listening': 'pending', 'music_gain_requires_listening': True})
