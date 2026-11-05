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
TEMPLATE = ROOT / 'templates/motiongit-public-quote-controls-v3'
UPSTREAM_TEMPLATE = ROOT / 'templates/motiongit-public-components-v1'
CANDIDATE_MANIFEST_SHA = 'b7a8ef1148511b675d4c03085358be22c474f24afbdaaddabb14775255cd1f7b'
ENGINES = {'observed-quote-controls/3'}
CONTRACT = 'haike.motion-public-quote-production/3'
KIND = 'studio_investment_recompose'
REQUEST_FILE = 'motion-public-quote-v3-request.json'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
FFMPEG9_DESCRIPTOR_SHA = '1d7055cadccd60e2442c5d279083b3dd8c9a46c1bae6d317e78a344826e6aa29'


def require(condition, message):
    if not condition:
        raise WorkError(message)

def component():
    """Verify the new candidate and the retained upstream before consuming either."""
    require(sha(TEMPLATE / 'COMPONENT.json') == CANDIDATE_MANIFEST_SHA,
            'quote-v3候选清单不是已核固定摘要')
    manifest = read_json(TEMPLATE / 'COMPONENT.json')
    require(manifest.get('schema') == 'haike.motion-public-quote-components/3', 'quote-v3组件身份无效')
    upstream = manifest['retained_upstream']
    require(sha(UPSTREAM_TEMPLATE / 'COMPONENT.json') == upstream['component_sha256'],
            '保留的原公开上游身份改变')
    path = ROOT / 'scripts/build_motion_public_components.py'
    require(sha(path) == upstream['verifier_sha256'], '保留的原公开上游校验器改变')
    spec = importlib.util.spec_from_file_location('haike_public_quote_v3_retained_verifier', path)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    retained = verifier.verify(UPSTREAM_TEMPLATE)
    expected = set()
    for row in manifest['files']:
        name = row['path']
        path = TEMPLATE / name
        require(isinstance(name, str) and '\\' not in name and ':' not in name
                and not Path(name).is_absolute() and '..' not in Path(name).parts
                and path.resolve().is_relative_to(TEMPLATE.resolve()) and not path.is_symlink()
                and path.is_file() and path.stat().st_size == row['size'] and sha(path) == row['sha256'],
                'quote-v3候选源缺失、越界或摘要改变：' + str(name))
        require(name.casefold() not in expected, 'quote-v3候选源路径冲突')
        expected.add(name.casefold())
    actual = {p.relative_to(TEMPLATE).as_posix().casefold() for p in TEMPLATE.rglob('*')
              if p.is_file() and p.name != 'COMPONENT.json'}
    require(actual == expected, 'quote-v3候选目录含未绑定文件或缺件')
    return {**manifest, 'references': retained['references'], 'packs': retained['packs'],
            'reused_upstream_files': [{'path': 'COMPONENT.json'}, *retained['files']]}


def preflight(value):
    require(isinstance(value, dict) and value.get('engine') == 'observed-quote-controls/3',
            '引言v3只准入observed-quote-controls/3，不回退其他引擎')
    component()
    from backlot.motion_public_quote_observed_v3 import preflight as prepare
    return prepare(value)


def _boundary(request):
    """The controller supplies a live claim/decision guard, never serialized input."""
    guard = request.get('_phase_guard')
    require(callable(guard), 'quote-v3媒体执行缺少控制器实时claim/批准回调')
    guard()


def require_current_review(folder, request):
    """Honor the controller's concrete approval identity, including withdrawals."""
    binding = request.get('review_binding')
    review_path = folder / 'visual-review.json'
    require(isinstance(binding, dict) and binding.get('decision') == 'approve'
            and isinstance(binding.get('approval_id'), str) and binding['approval_id']
            and review_path.is_file() and not review_path.is_symlink()
            and sha(review_path) == binding.get('approval_sha256'), '本期具体批准已缺失、撤回或改变')
    review = read_json(review_path)
    expected = {key: binding.get(key) for key in ('request_sha256', 'preview_sha256', 'images')}
    require(review.get('decision') == 'approve' and review.get('approval_id') == binding['approval_id']
            and review.get('binding') == expected and expected['request_sha256'] == request['request_sha256']
            and sha(folder / 'preview.json') == expected['preview_sha256'], '当前批准不属于本期实际预览')
    preview = read_json(folder / 'preview.json')
    require(preview.get('request_sha256') == request['request_sha256']
            and preview.get('images') == expected['images'] and expected['images'], '当前批准图片清单改变')
    names = set()
    for row in expected['images']:
        name = row.get('name', '')
        path = folder / 'preview' / name
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.png', name) and name not in names
                and path.resolve().is_relative_to((folder / 'preview').resolve())
                and path.is_file() and not path.is_symlink() and sha(path) == row.get('sha256'), '实际批准PNG无效或改变')
        names.add(name)


def build_project(project, folder, request):
    require(request.get('input_engine') in ENGINES, '未登记的引言v3执行引擎')
    _boundary(request)
    from backlot.motion_public_quote_observed_v3 import build_project as build
    result = build(project, folder, request)
    _boundary(request)
    return result


def bound(value):
    require(isinstance(value, dict) and set(value) == {'path', 'sha256'}, '输入文件须精确绑定path和sha256')
    path = Path(value['path'])
    require(path.is_file() and not path.is_symlink() and sha(path) == value['sha256'], '输入文件缺失、为链接或摘要改变')
    return path.resolve()

def runtime():
    """Location-independent byte identity of execution, separate from the host."""
    manifest = component()
    identities = {
        'execution/motion_public_quote_execution_v3.py': sha(Path(__file__)),
        'execution/motion_public_io_v1.py': sha(ROOT / 'backlot/motion_public_io_v1.py'),
        'execution/motion_public_quote_observed_v3.py': sha(ROOT / 'backlot/motion_public_quote_observed_v3.py'),
        'component/observed-quote-controls-v3.js': sha(TEMPLATE / 'observed-quote-controls-v3.js'),
        'component/FFMPEG9.json': sha(TEMPLATE / 'FFMPEG9.json'),
        'execution/build_motion_public_components.py': sha(ROOT / 'scripts/build_motion_public_components.py'),
        'component/COMPONENT.json': sha(TEMPLATE / 'COMPONENT.json'),
        'component/capture_runtime.mjs': sha(TEMPLATE / 'capture_runtime.mjs'),
        'python/venv-executable': sha(Path(sys.executable)),
        'python/base-executable': sha(Path(sys._base_executable)),
    }
    for row in manifest['files']:
        identities['component/' + row['path']] = sha(TEMPLATE / row['path'])
    for row in manifest['reused_upstream_files']:
        identities['retained-v1/' + row['path']] = sha(UPSTREAM_TEMPLATE / row['path'])
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
    return {'implementation_id': 'haike.motion-public-quote-execution/3',
            'files': [{'logical_path': name, 'sha256': identities[name]} for name in sorted(identities)],
            'python_abi': sys.implementation.cache_tag, 'python_version': sys.version, 'python_dependencies': python_dependencies}

def environment(tool_root, dependency_root, ffmpeg_root=None, *, engine=None):
    """Only known binary and npm/font bytes may execute, never caller commands."""
    require(engine is None or engine in ENGINES, '未登记的quote-v3环境引擎')
    component()
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
    _boundary(request)
    result = subprocess.run([str(a) for a in args], cwd=folder, env=_env(request), capture_output=True,
        encoding='utf8', errors='replace', timeout=timeout, creationflags=NO_WINDOW)
    # Local-only diagnostics, never exported as public component source.
    (folder / (name + '.stdout.log')).write_text(result.stdout, encoding='utf8')
    (folder / (name + '.stderr.log')).write_text(result.stderr, encoding='utf8')
    require(result.returncode == 0, name + '失败：' + result.stderr[-1500:])
    _boundary(request)
    return result.stdout

def quote_preview_times(plan, request, base_times):
    """Retain all action witnesses and add quantized sparse-constraint quote frames."""
    targets = []
    fps = plan['fps']
    for row in request['spec']['segments']:
        if row['control'] != 'quote':
            continue
        for cue in row['cues'] or [row['t0']]:
            for offset in (.10, .64, .65, .74, 1.58):
                frame = round((cue + offset) * fps)
                time = frame / fps
                require(0 <= frame < plan['end_frame'] and row['t0'] <= time < row['t1'],
                        '引言定向取样必须位于本场实际输出帧内')
                targets.append({'scene_id': row['id'], 'cue': cue, 'offset': offset, 'frame': frame, 'time': time})
    times = sorted(set(base_times) | {row['time'] for row in targets})
    return times, targets


def render_project(project, folder, request):
    require(request.get("input_engine") in ENGINES, "未登记的quote-v3执行引擎")
    _boundary(request)
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
        base_action_times = list(times)
        times, quote_targets = quote_preview_times(plan, request, times)
        _command([*command, '--stills-dir', preview, '--times', ','.join(map(str, times))], folder, request, 'public-preview')
        images = [{'name': p.name, 'sha256': sha(p)} for p in sorted(preview.glob('*.png'))]
        require(len(images) == len(times), '动作预览图片不完整')
        atomic_private(folder / 'preview.json', {'images': images, 'times': times, 'request_sha256': request['request_sha256'],
            'scope': 'all-selected-public-actions-sampled', 'original_fidelity': 'pending',
            'base_action_times': base_action_times, 'quote_constraint_samples': quote_targets})
        return {'status': 'completed', 'stage': '公开组件实际动作预览就绪，待逐图和原参考对照',
            'result': {'images': images, 'preview_sha256': sha(folder / 'preview.json'), 'qa_status': 'pending'}}
    require_current_review(folder, request)
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
