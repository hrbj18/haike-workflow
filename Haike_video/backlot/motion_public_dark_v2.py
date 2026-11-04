"""Version2 dark input/audio helpers; original Remotion is the only dark engine."""
from copy import deepcopy
import math
from pathlib import Path
import re
import wave
from backlot.motion_public_io_v1 import atomic_private, read_json, sha
from backlot.motion_public_dark_schema_v2 import validate_props, required_names, catalog
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'templates/motiongit-public-components-v2/dark-v2'
ENGINE = 'dark-remotion/2'
NAMES = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}')

def real_display_clock(script, asr, voice, aliases):
    """Allow counted display aliases, retaining every original measured word."""
    from backlot.motion_public_execution_v2 import require, norm
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
    from backlot.motion_public_execution_v2 import require
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
    from backlot import motion_public_execution_v2 as e
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
    e.require(environment_resolver is not None, '完整深色仅接受固定原Remotion环境')
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
                'implementation': 'C-owned complete cobalt ten groups with two marketing-only label guards; original Remotion retained; original native pixel identity not claimed'}}

def mix_audio(assets, folder, generated, request):
    from backlot import motion_public_execution_v2 as e
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
