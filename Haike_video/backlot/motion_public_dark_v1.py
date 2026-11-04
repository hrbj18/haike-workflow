"""Fixed React frame execution of the project-owned complete dark groups.

Project source retains AGPL-3.0. React and esbuild retain their MIT notices.
This is not the original protected MotionGit runtime or a Remotion derivative.
"""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import wave

from backlot.motion_public_io_v1 import atomic_private, fingerprint, read_json, sha
from backlot.motion_public_dark_schema_v1 import validate_props, required_names, catalog

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'templates/motiongit-public-components-v1/dark-v1'
ENGINE = 'dark-groups/1'
DEPENDENCIES_SHA = 'b12c967ec93caf3f21c5845170f45f8a75bc081c05e929f7822712fc45c31a41'
NAMES = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}')


def dependency_files(root):
    from backlot.motion_public_execution_v1 import require
    root = Path(root).resolve()
    require(sha(SOURCE / 'DEPENDENCIES.json') == DEPENDENCIES_SHA, '深色组件npm固定清单改变')
    out = []
    for package in read_json(SOURCE / 'DEPENDENCIES.json')['components']:
        folder = root / 'node_modules' / package['component']
        declared = {row['path'] for row in package['files']}
        require(folder.is_dir() and not folder.is_symlink(), '缺少深色组件固定npm依赖')
        actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
        require(actual == declared, '深色npm目录多件或缺件，禁止静默执行其他代码')
        for row in package['files']:
            path = folder / row['path']
            require(path.resolve().is_relative_to(root) and not path.is_symlink() and sha(path) == row['sha256'], '深色npm实际字节或许可改变')
            out.append({'logical_path': 'dependencies/' + path.relative_to(root).as_posix(), 'sha256': row['sha256']})
    return sorted(out, key=lambda row: row['logical_path'])


def real_display_clock(script, asr, voice, aliases):
    """Allow counted display aliases, retaining every original measured word."""
    from backlot.motion_public_execution_v1 import require, norm
    text, data = read_json(script).get('text'), read_json(asr)
    require(isinstance(text, str) and text.strip() and data.get('audio_sha256') == sha(voice), '完整文稿或ASR没有绑定真实声音')
    rows = deepcopy(data.get('segments'))
    require(isinstance(rows, list) and rows and isinstance(aliases, list), '缺少真实ASR或明确显示归一化')
    for alias in aliases:
        require(isinstance(alias, dict) and set(alias) == {'from', 'to', 'expected_count'}
                and all(isinstance(alias[k], str) and 0 < len(alias[k]) <= 12 for k in ('from', 'to'))
                and type(alias['expected_count']) is int and alias['expected_count'] > 0, '显示别名须有界且定次数')
        require(sum(r['text'].count(alias['from']) for r in rows) == alias['expected_count'], '显示别名次数与原ASR不符')
        for row in rows:row['text'] = row['text'].replace(alias['from'], alias['to'])
    with wave.open(str(voice), 'rb') as audio:
        require(audio.getcomptype() == 'NONE' and audio.getsampwidth() == 2, '原速口播须为PCM16 WAV')
        duration = audio.getnframes() / audio.getframerate()
    previous = 0
    for row in rows:
        require(isinstance(row.get('text'), str) and previous <= row['start'] < row['end'] <= duration + .025, 'ASR句时钟无效')
        previous = row['end']; last = row['start']
        require(isinstance(row.get('words'), list) and row['words'], '完整组须绑定真实ASR词')
        for word in row['words']:
            require(isinstance(word.get('text'), str) and last - .001 <= word['start'] < word['end'] <= row['end'] + .001, 'ASR词时钟无效')
            last = word['end']
    require(norm(''.join(r['text'] for r in rows)) == norm(text), '显示归一化后的ASR全文仍不等于批准文稿')
    return text, rows, duration


def validate_content(scenes):
    from backlot.motion_public_execution_v1 import require
    definitions = read_json(SOURCE / 'CONTENT_FIELDS.json')
    for scene in scenes:
        require(scene['group'] in definitions and isinstance(scene.get('content'), dict)
                and set(scene['content']) <= set(definitions[scene['group']]), '完整组有未实现的内容字段')
        for key, content in scene['content'].items():
            expected = definitions[scene['group']][key]
            require(type(content).__name__ == expected and (expected != 'str' or len(content) <= 500)
                    and (expected != 'list' or len(content) <= 40)
                    and (expected not in {'int','float'} or math.isfinite(content)), '完整组内容类型或容量无效')
            if expected == 'list':
                require(all(isinstance(item, str) and len(item) <= 150 for item in content), '完整组列表只实现有界文字项')


def preflight(value, *, engine=ENGINE, environment_resolver=None):
    from backlot import motion_public_execution_v1 as e
    e.require(isinstance(value, dict) and not set(value) - {'engine', 'pack_key', 'reference_id', 'title', 'brand', 'script', 'asr',
        'assets', 'composition', 'tool_root', 'dependency_root', 'ffmpeg_root', 'work_root', 'source_receipts'}, '深色完整组输入含未实现字段')
    e.require(value.get('engine') == engine and value.get('pack_key') == 'owned-dark-cobalt'
              and value.get('reference_id') == 'template-03-native', '深色组件身份无效')
    e.require(all(isinstance(value.get(k), str) and 0 < len(value[k]) <= 100 for k in ('title', 'brand')), '缺少本期标题或品牌')
    supplied = value.get('assets')
    e.require(isinstance(supplied, dict) and all(isinstance(n, str) and NAMES.fullmatch(n) for n in supplied)
              and not {'script.json', 'asr.json'} & set(supplied), '深色资产逻辑名无效')
    paths = {name: e.bound(row) for name, row in supplied.items()}
    script, asr = e.bound(value['script']), e.bound(value['asr'])
    composition = value.get('composition')
    e.require(isinstance(composition, dict) and set(composition) == {'props', 'audio', 'display_aliases'}, '完整组须有固定画面、声音及显示别名')
    p, audio = deepcopy(composition['props']), deepcopy(composition['audio'])
    e.require(isinstance(p, dict) and p.get('variant') == 'cobalt' and {'voice.wav', 'music.wav', 'presenter.mp4'} <= set(paths), '本版仅实现完整cobalt十组和真实完整声画')
    text, segments, duration = real_display_clock(script, asr, paths['voice.wav'], composition['display_aliases'])
    validate_props(p, duration)
    e.require((p['width'], p['height'], p['fps']) == (1440, 1800, 30)
              and p['durationFrames'] == math.ceil(duration * p['fps'])
              and [s['group'] for s in p['scenes']] == ['s01','s02','s03','s04','s05','s06','s07','s08','s09','review'], '完整十组、原顺序及真实尾帧必须保留')
    e.require(set(audio) == {'voice', 'music', 'musicGainDb', 'musicOffsetSeconds', 'loopMusic', 'sfx'}
              and audio['voice'] == 'voice.wav' and audio['music'] == 'music.wav' and audio['sfx'] == []
              and type(audio['loopMusic']) is bool and audio['loopMusic'] is True
              and type(audio['musicGainDb']) in (int,float) and -40 <= audio['musicGainDb'] <= -8
              and audio['musicOffsetSeconds'] == 0, '本版仅实现原速完整口播、明确循环BGM与无额外SFX计划')
    e.require(required_names(p, audio) == set(paths), '资产必须准确覆盖本期字体、图、视频与音轨')
    e.require(all(sha(paths[n]) == 'a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da'
                  for n in p['fontAssets'].values()), '当前十组须用已取得原摘要的公开OFL字体')
    validate_content(p['scenes'])
    e.require(e.norm(''.join(c['text'] for c in p['captions'])) == e.norm(text), '字幕没有覆盖批准完整文稿')
    starts = [w['start'] * 1000 for s in segments for w in s['words']]
    ends = [w['end'] * 1000 for s in segments for w in s['words']]
    e.require(all(min(abs(c['startMs'] - at) for at in starts) <= 35 and min(abs(c['endMs'] - at) for at in ends) <= 35
                  for c in p['captions']), '字幕必须使用实际ASR词边界，不能重新猜时码')
    if environment_resolver is None:
        tools, environment = e.environment(value['tool_root'], value['dependency_root'], value.get('ffmpeg_root'))
        environment += dependency_files(value['dependency_root'])
    else:
        tools, environment = environment_resolver(value['tool_root'], value['dependency_root'], value.get('ffmpeg_root'))
    provenance = value.get('source_receipts', {})
    presenter = p.get('presenter')
    e.require(presenter and any(row.get('source_sha256') == sha(paths[presenter['src']])
              and row.get('voice_sha256') == sha(paths['voice.wav']) and row.get('reviewed') is True
              for row in provenance.get('presenterClips', [])), '人物母片须绑定本期完整口播与原来源审核')
    spec = {'width': p['width'], 'height': p['height'], 'fps': p['fps'], 'props': p, 'audio': audio,
            'display_aliases': composition['display_aliases'], 'transcript': segments}
    return {'input_engine': engine, 'spec': spec, 'paths': paths, 'script': script, 'asr': asr,
            'duration': duration, 'frames': p['durationFrames'], 'environment': environment,
            'reference': {'id': 'template-03-native', 'original_version': '2.7.18-alpha.2',
                'package_sha256': '0073456d9aef950f7548ca3e18fd752ab2577cc9bec23258c2cfcc689ad7009f',
                'implementation': 'C-owned complete cobalt ten groups with D fixed React frame bridge; original native pixel identity not claimed'}}


def build_project(project, folder, request):
    from backlot import motion_public_execution_v1 as e
    if (folder / 'prepared.json').exists():
        receipt = read_json(folder / 'prepared.json')
        e.require(all((folder / name).resolve().is_relative_to(folder.resolve()) and not (folder / name).is_symlink()
                      and sha(folder / name) == digest for name, digest in receipt['files'].items()), '完整十组已准备工程改变')
        return receipt
    upstream, generated = folder / 'runtime-source', folder / 'project'
    e.require(not upstream.exists() and not generated.exists(), '保留未完成准备现场，不能覆盖重来')
    shutil.copytree(e.TEMPLATE / 'upstream', upstream);generated.mkdir()
    assets = {name: project / 'assets/motion-public' / name for name in request['origins']}
    p = deepcopy(request['spec']['props']);p.pop('audio', None)
    public = generated / 'assets';public.mkdir()
    for name in required_names(p, request['spec']['audio']):
        if name.lower().endswith(('.jpg','.png','.ttf','.woff2')):shutil.copy2(assets[name], public / name)
    dependency = Path(request['dependency_root'])
    npm_files = dependency_files(dependency)
    source = folder / 'dark-source';shutil.copytree(SOURCE, source)
    env = os.environ.copy();env['NODE_PATH'] = str(dependency / 'node_modules')
    compiler = dependency / 'node_modules/@esbuild/win32-x64/esbuild.exe'
    command = [str(compiler), str(source / 'entry.tsx'), '--bundle', '--platform=browser', '--format=iife',
        '--define:process.env.NODE_ENV="production"', '--alias:remotion=' + str(source / 'frame-bridge.tsx'),
        '--outfile=' + str(generated / 'bundle.js'), '--metafile=' + str(folder / 'bundle-inputs.json')]
    result = subprocess.run(command, env=env, cwd=folder, capture_output=True, creationflags=e.NO_WINDOW)
    (folder / 'dark-compile.stdout.log').write_bytes(result.stdout);(folder / 'dark-compile.stderr.log').write_bytes(result.stderr)
    e.require(result.returncode == 0, '固定深色React编译失败')
    bundle_inputs = read_json(folder / 'bundle-inputs.json')['inputs']
    bound = []
    for relative in bundle_inputs:
        path = (folder / relative).resolve()
        e.require(path.is_file() and not path.is_symlink() and (path.is_relative_to(source) or path.is_relative_to(dependency / 'node_modules')), '编译器解析到未绑定源目录')
        bound.append({'logical_path': ('source/' + path.relative_to(source).as_posix()) if path.is_relative_to(source)
                      else 'dependencies/' + path.relative_to(dependency).as_posix(), 'sha256': sha(path)})
    definitions = {m['id']: m for m in p['media']};needed = {}
    for scene in p['scenes']:
        for clip in scene.get('videoWindows', []):
            needed.setdefault(definitions[clip['mediaId']]['src'], set()).add((round(clip['offset'] * p['fps']), clip['frames']))
    presenter = p['presenter']
    for mode in presenter['modes']:
        if mode['mode'] != 'hidden':needed.setdefault(presenter['src'], set()).add((round(presenter['offset'] * p['fps']) + mode['from'] - presenter['from'], mode['frames']))
    mapped, operations = {}, []
    for name, intervals in needed.items():
        info = json.loads(e._command([e._ffprobe(request), '-v','error','-show_streams','-show_format','-of','json',assets[name]], folder, request, 'probe-' + name))
        stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
        seconds = float(stream.get('duration', info['format']['duration']))
        color = json.loads(e._command([sys.executable,'-X','utf8','-B',upstream/'scripts/color_management.py','--image',assets[name]], folder, request, 'color-' + name))
        for start, count in sorted(intervals):
            e.require((start + count) / p['fps'] <= seconds + 1 / p['fps'], '原速媒体窗口超过真实源，禁止尾帧补齐')
            directory = generated / ('frames-' + name.replace('.','-') + '-' + str(start) + '-' + str(count));directory.mkdir()
            e._command([e._ffmpeg(request),'-nostdin','-v','error','-n','-ss',str(start/p['fps']),'-i',assets[name],'-an',
                '-vf','fps='+str(p['fps'])+','+color['filter'],'-frames:v',str(count),'-q:v','2',directory/'f_%04d.jpg'], folder, request, 'extract-' + directory.name)
            frames = sorted(directory.glob('f_*.jpg'));e.require(len(frames) == count, '完整组原速媒体实际解码帧不足')
            mapped.setdefault(name, []).append({'start':start, 'count':count, 'path':directory.name})
            operations.append({'source_name':name,'source_sha256':sha(assets[name]),'start_frame':start,'frames':count,
                'fps':p['fps'],'playback_rate':1,'color':color,'files':{f.name:sha(f) for f in frames}})
    js = lambda value: json.dumps(value, ensure_ascii=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    html = '<!doctype html><meta charset="utf-8"><style>html,body{margin:0;width:100%;height:100%;overflow:hidden}*{box-sizing:border-box}#root{position:absolute;inset:0}</style><div id="root"></div><script>window.DARK_INPUT=' + js(p) + ';window.DARK_MEDIA=' + js(mapped) + ';</script><script src="bundle.js"></script>'
    (generated / 'index.html').write_text(html, encoding='utf8')
    plan = {'schema':'haike.dark-full-frame-plan/1','width':p['width'],'height':p['height'],'fps':p['fps'],'end_frame':p['durationFrames'],
        'scenes':[{'id':s['id'],'output_start_frame':s['from'],'output_end_frame':s['from']+s['frames'],
            'cues':[{'id':key,'outputFrame':s['from']+round(at*p['fps'])} for key,at in s.get('cueTimes',{}).items()]} for s in p['scenes']]}
    atomic_private(generated / 'macro_plan.json', plan)
    atomic_private(generated / 'output-signature.json', {'schema':'adu-output-signature/1','enabled':False})
    renderer = upstream / 'scripts/render_project.mjs';before = sha(renderer);text = renderer.read_text('utf8')
    e.require(text.count("'-crf', '15'") == 1, '公开编码器入口改变')
    renderer.write_text(text.replace("'-crf', '15'", "'-threads', '1', '-b:v', '20500k', '-minrate', '20500k', '-maxrate', '20500k', '-bufsize', '2000k', '-x264-params', 'nal-hrd=cbr:force-cfr=1:filler=1'"), encoding='utf8')
    e._command([Path(request['tool_root'])/'node/node.exe',e.TEMPLATE/'capture_runtime.mjs',generated,
        dependency/'node_modules/playwright-core',Path(request['tool_root'])/'browser/chrome-headless-shell.exe',generated/'sfx.json'], folder, request, 'capture-dark-runtime')
    mix_audio(assets, folder, generated, request)
    files = {f.relative_to(folder).as_posix():sha(f) for directory in (upstream,generated,source) for f in directory.rglob('*') if f.is_file()}
    receipt = {'schema':'haike.dark-public-prepared/1','request_sha256':request['request_sha256'],'files':files,
        'media_operations':operations,'compiler_inputs':bound,'npm_files':npm_files,'renderer_derivation':{'before_sha256':before,'after_sha256':sha(renderer)},
        'full_original_template_closure':False,'implementation':'project-owned cobalt complete ten groups; independent fixed frame bridge'}
    atomic_private(folder / 'prepared.json', receipt)
    return receipt


def mix_audio(assets, folder, generated, request):
    from backlot import motion_public_execution_v1 as e
    p, audio = request['spec']['props'], request['spec']['audio'];duration = p['durationFrames'] / p['fps'];samples = p['durationFrames'] * (48000 // p['fps'])
    gain = 10 ** (audio['musicGainDb'] / 20)
    graph = (f'[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={duration},asetpts=PTS-STARTPTS,asplit=2[voice][duck];'
        f'[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS,volume={gain},apad,atrim=duration={duration},afade=t=in:d=0.15,afade=t=out:st={max(0,duration-.6)}:d=0.6[music];'
        '[music][duck]sidechaincompress=threshold=0.025:ratio=5:attack=12:release=220[bed];'
        f'[voice][bed]amix=inputs=2:duration=longest:normalize=0:dropout_transition=0,loudnorm=I=-16:TP=-2.5:LRA=11,aresample=48000,apad=whole_len={samples},atrim=end_sample={samples},asetpts=N/SR/TB[out]')
    e._command([e._ffmpeg(request),'-nostdin','-v','error','-n','-i',assets['voice.wav'],'-stream_loop','-1','-i',assets['music.wav'],
        '-filter_complex',graph,'-map','[out]','-ar','48000','-ac','2','-c:a','pcm_s16le',generated/'final.wav'], folder, request, 'dark-audio-mix')
    with wave.open(str(generated/'final.wav'),'rb') as stream:
        e.require((stream.getnchannels(),stream.getsampwidth(),stream.getframerate(),stream.getnframes()) == (2,2,48000,samples), '深色声音母带未按真实帧钟落定')
    atomic_private(folder/'audio-receipt.json', {'voice_sha256':sha(assets['voice.wav']),'music_sha256':sha(assets['music.wav']),
        'mix_sha256':sha(generated/'final.wav'),'filter_complex':graph,'voice_playback_rate':1,'source_audio_muted':True,
        'sfx_plan':'none explicitly authored in this C complete ten-group input; no invented original SFX', 'device_listening':'pending'})
