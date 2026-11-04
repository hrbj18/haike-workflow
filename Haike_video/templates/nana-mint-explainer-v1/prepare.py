"""Prepare the explicitly identified private reference episode, without provider calls.

For a new episode use --episode with its own existing assets instead. Speech is
never stretched and every file remains local to the declared asset directory.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

SOURCE_SHA = 'b0a4cbec83e93d19509e2e31564f2859f1b556c7ae2cba67c9e93ee12193128c'
IDS = ['integration', 'terms', 'brief', 'result', 'workflow', 'compare', 'question', 'value', 'difference', 'course', 'examples', 'logic', 'closing']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def media_duration(scene, key):
    """Actual mounted source interval; unused hidden tails need no new lips."""
    duration = scene['end'] - scene['start']
    cue = scene.get('cues', {})
    delay = 2.1 if scene['id'] == 'brief' and key == 'presenter' else cue.get('overlay', 0) if key == 'overlay' else 0
    end = cue.get('presenterOff', 2.3) if scene['id'] == 'examples' and key == 'presenter' else cue.get('overlayEnd', 2.1) if scene['id'] == 'logic' and key == 'media' else duration
    return end - delay


def validate_episode(data):
    if data.get('version') != 1 or data.get('fps') != 30 or not 0 < data.get('duration', 0) <= 120:
        raise ValueError('仅接受版本1、30fps的本期输入。')
    if [s['id'] for s in data['scenes']] != IDS or len(data['chapters']) != 5:
        raise ValueError('需要完整的13个场景和五段章节。')
    end = 0
    for row in data['scenes']:
        if abs(row['start'] - end) > .001 or row['end'] <= row['start']:
            raise ValueError('场景必须连续覆盖完整声音。')
        end = row['end']
        duration = row['end'] - row['start']
        for key, at in row.get('cues', {}).items():
            if not isinstance(at, (int, float)) or not 0 <= at < duration:
                raise ValueError('动作cue超出本场景：' + row['id'] + '/' + key)
        if row['id'] == 'workflow':
            cue = row.get('cues', {})
            if not 0 < cue.get('prompt', 2.4) < cue.get('steps', 7.7) < cue.get('preview', 12.6) < duration:
                raise ValueError('输入、步骤和结果必须按本期实测语义先后出现。')
        if not 0 <= row['chapter'] < 5:
            raise ValueError('章节编号无效。')
        for name in ['media', 'presenter', 'overlay']:
            item = row.get(name)
            if item and (Path(item['file']).name != item['file'] or item['width'] <= 0 or item['height'] <= 0):
                raise ValueError('媒体必须是本期本地文件，尺寸须有效。')
    if abs(end - data['duration']) > .04:
        raise ValueError('场景没有覆盖完整主时钟。')
    reference = data.get('referenceClock')
    if reference:
        anchors = reference.get('anchors', [])
        if not data.get('reference') or not 0 < reference.get('duration', 0) <= 600 or len(anchors) < 2 or anchors[0] != [0, 0]:
            raise ValueError('原片对照须有完整、独立的原始时钟。')
        if any(len(a) != 2 or len(b) != 2 or not a[0] < b[0] or not a[1] < b[1] for a, b in zip(anchors, anchors[1:])):
            raise ValueError('原片语义对照时钟必须严格递增。')
        if abs(anchors[-1][0] - reference['duration']) > .04 or abs(anchors[-1][1] - data['duration']) > .04:
            raise ValueError('原片对照没有覆盖本期主时钟。')
    for cue in data['captions']:
        if not 0 <= cue['startMs'] < cue['endMs'] <= data['duration'] * 1000 + 40 or len(cue['text']) > 64:
            raise ValueError('字幕时间或单句长度超出范围；请依据实测语音重新分句。')
    for key in ['voice', 'font']:
        if Path(data[key]).name != data[key]:
            raise ValueError('声音与字体须使用本期本地文件名。')
    for key, color in data['palette'].items():
        if len(color) != 7 or not color.startswith('#') or any(c not in '0123456789abcdefABCDEF' for c in color[1:]):
            raise ValueError('配色只接受本地十六进制颜色：' + key)
    return data


def main():
    from frozen_release import verify, validate_style
    verify()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--transcript', type=Path)
    parser.add_argument('--font', type=Path)
    parser.add_argument('--episode', type=Path)
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--ffprobe', required=True)
    args = parser.parse_args()
    data_dir = args.output.resolve()
    public = data_dir / 'public'
    public.mkdir(parents=True, exist_ok=True)
    if (data_dir / 'episode.json').exists():
        raise ValueError('此目录已有冻结本期输入；复用已有产物或选择新的输出目录。')

    def run(*items):
        subprocess.run([args.ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', '-y', *map(str, items)], check=True, capture_output=True, timeout=180, creationflags=0x08000000)

    provenance = {}
    if args.episode:
        content = validate_episode(json.loads(args.episode.read_bytes()))
        validate_style(content)
        if not args.assets:
            raise ValueError('新一期需要显式指定--assets。')
        names = {content['voice'], content['font']}
        if content.get('reference'):
            names.add(content['reference'])
        names.update(s[k]['file'] for s in content['scenes'] for k in ['media', 'presenter', 'overlay'] if s.get(k))
        for name in names:
            source = (args.assets / name).resolve()
            if source.parent != args.assets.resolve() or not source.is_file():
                raise ValueError('缺少已声明的本期文件：' + name)
            shutil.copyfile(source, public / name)
            provenance[name] = {'source': str(source), 'sha256': sha(source), 'process': 'byte-identical user-bound local asset'}
    else:
        if not args.reference or sha(args.reference) != SOURCE_SHA or not args.transcript or not args.font:
            raise ValueError('参考样例需要本次精确原片SHA、实际转录和本地字体；其他参考先重新分析。')
        source = args.reference.resolve()
        raw = json.loads(args.transcript.read_bytes())
        corrections = {0: '剪辑行业的天真的塌了，CapCut，也就是剪映国际版。', 1: '正式宣布将以插件的形式接入Codex。', 3: '也不需要再学什么关键帧，也不需要再学什么时间线。', 8: '我们只需要把我们的素材拖给Codex。', 14: '素材拼接、转场特效、背景音乐，都可以一条线帮你完成。', 25: '方法、Skill和案例样片。'}
        captions = [{'text': corrections.get(i, s['text'].strip()), 'startMs': round(s['start'] * 1000), 'endMs': round(s['end'] * 1000), 'timestampMs': None, 'confidence': None} for i, s in enumerate(raw['segments'])]
        boundaries = [0, 6.0666666667, 12.3333333333, 18.1, 21.6333333333, 42.1, 47.7666666667, 51.1333333333, 55.4, 59.5, 63.2, 67.5, 71.7, 2236 / 30]
        titles = ['插件接入', '剪辑、关键帧与时间线', '告诉它，你想做什么', '先看成片：足球集锦与GOAL!效果', 'CapCut 官方演示', '口播中的制作时间对比', '剪辑师会消失吗？', '人的价值', '同样的工具', 'AI 代码剪辑', '提示词、方法、Skill 和案例样片', '视频创作的底层逻辑', '评论区打字']
        chapters = [0, 0, 1, 1, 2, 3, 3, 3, 3, 4, 4, 4, 4]
        scenes = [{'id': identity, 'start': boundaries[i], 'end': boundaries[i + 1], 'chapter': chapters[i], 'title': titles[i]} for i, identity in enumerate(IDS)]
        content = {'version': 1, 'title': '迎面而来的将是 AI 剪辑师', 'brand': 'CapCut', 'partner': 'Codex', 'duration': 2236 / 30, 'fps': 30, 'chapters': ['插件接入', '描述需求', '官方案例', '人的价值', '方法教程'], 'scenes': scenes, 'captions': captions, 'voice': 'mix.wav', 'font': 'font.ttf', 'reference': 'reference.mp4', 'phrase': '把素材剪成一条短片，说明时长、风格和观众。', 'cards': ['提示词', '方法', 'Skill'], 'palette': {'paper': '#edf5ef', 'ink': '#16313a', 'accent': '#167e79', 'line': '#cbdad4', 'sheet': '#f7fffa'}}
        content['scenes'][0].update(cues={'partner': 2.3, 'arrow': 3.4}, note='素材来源：参考片中的官方演示')
        content['scenes'][1].update(labels=['剪辑', '关键帧', '时间线'], note='放大查看真实剪辑画面')
        content['scenes'][2].update(labels=['时长', '风格', '给谁看'])
        content['scenes'][3].update(note='软件演示与需求描述')
        content['scenes'][4].update(cues={'prompt': 2.4, 'steps': 7.6666667, 'preview': 12.7333333}, note='素材来源：参考片中的软件演示　 /　独立示意步骤')
        content['scenes'][5].update(labels=['两三个小时', '五到十分钟'], cues={'arrow': 2.1, 'after': 3.3}, note='按原片口播呈现，非独立对时测评')
        content['scenes'][6].update(labels=['剪辑师', '会消失吗？', '我觉得不是'], cues={'answer': 2.5})
        content['scenes'][7].update(labels=['AI 技术门槛下放', '行业角色变化', 'AI 剪辑师', '工具背后依然是人'])
        content['scenes'][8].update(labels=['不同的人', '不同的视频水平'])
        content['scenes'][9].update(labels=['提示词', '方法', 'Skill'])
        content['scenes'][11].update(labels=['视听语言', '编导思维', '底层逻辑'])
        content['scenes'][12].update(labels=['剪辑', '全套教程，我发给你'])

        def crop(index, key, box, offset=0, image_at=None):
            row = scenes[index]
            start, duration = row['start'] + offset, row['end'] - row['start'] - offset
            w, h, x, y = box
            name = row['id'] + '-' + key + ('.png' if image_at is not None else '.mp4')
            target = public / name
            if not target.exists():
                if image_at is not None:
                    run('-ss', image_at, '-i', source, '-frames:v', 1, '-vf', f'crop={w}:{h}:{x}:{y}', target)
                else:
                    run('-ss', start, '-i', source, '-t', duration, '-an', '-vf', f"crop={w}:{h}:{x}:{y},setsar=1", '-r', 30, '-c:v', 'libx264', '-crf', 16, '-preset', 'fast', '-movflags', '+faststart', target)
            row[key] = {'file': name, 'width': w, 'height': h, 'kind': 'image' if image_at is not None else 'video'}
            provenance[name] = {'source': str(source), 'sha256': SOURCE_SHA, 'start': start, 'end': row['end'], 'crop': box, 'image_at': image_at, 'process': 'reference crop, original playback rate; H264 CRF16 or source PNG'}
            print('素材准备：' + name, flush=True)

        crop(0, 'media', [790, 430, 48, 180]); crop(0, 'presenter', [338, 450, 894, 164])
        crop(1, 'media', [850, 425, 55, 175]); crop(1, 'presenter', [286, 440, 944, 165])
        crop(2, 'media', [1140, 470, 60, 155], image_at=12.5); crop(2, 'presenter', [286, 450, 944, 155], offset=2.1)
        crop(3, 'media', [790, 430, 50, 170]); crop(3, 'overlay', [176, 408, 1026, 172]); crop(4, 'media', [1110, 480, 70, 105])
        crop(5, 'presenter', [330, 490, 60, 116]); crop(6, 'presenter', [705, 500, 65, 108])
        crop(7, 'presenter', [525, 520, 375, 95]); crop(8, 'presenter', [500, 480, 68, 145])
        crop(9, 'presenter', [430, 490, "'if(lt(t,0.7),425-355*t/0.7,70)'", 116])
        crop(10, 'media', [760, 440, 58, 165], image_at=64.8)
        crop(10, 'presenter', [280, 450, 950, 158])
        crop(10, 'overlay', [1074, 604, 96, 42], offset=3.4666666667)
        scenes[10]['cues'] = {'overlay': 3.4666666667, 'presenterOff': 2.3}
        scenes[11]['cues'] = {'overlayEnd': 2.1}
        crop(11, 'media', [1060, 510, 105, 45]); crop(12, 'presenter', [590, 560, 345, 68])
        shutil.copyfile(args.font, public / 'font.ttf')
        run('-i', source, '-vn', '-ar', 48000, '-ac', 2, '-c:a', 'pcm_s16le', public / 'mix.wav')
        run('-i', source, '-c:v', 'libx264', '-crf', 16, '-preset', 'fast', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', public / 'reference.mp4')
        provenance['font.ttf'] = {'source': str(args.font), 'sha256': sha(args.font), 'process': 'byte-identical local font'}
        provenance['mix.wav'] = {'source': str(source), 'sha256': SOURCE_SHA, 'process': 'full original mixed audio, original speed, PCM48k; no voice clone or paid generation'}
        validate_episode(content)
    # CaptureReveal explicitly loads the pinned local DM Sans face even when
    # the caller's Chinese face is selected. Keep that resource local as well.
    relative_font = Path('assets/fontsource/@fontsource-variable/dm-sans@5.3.0/files/dm-sans-latin-opsz-normal.woff2')
    cached_font = (args.assets / relative_font) if args.episode else (args.font.parent / Path(*relative_font.parts[1:]))
    if not cached_font.is_file():
        raise ValueError('缺少Snapcn的本地DM Sans缓存，不能在导出时依赖远程字体。')
    (public / relative_font).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cached_font, public / relative_font)
    voice_probe = json.loads(subprocess.check_output([args.ffprobe, '-v', 'error', '-show_format', '-of', 'json', str(public / content['voice'])], timeout=30))
    if abs(float(voice_probe['format']['duration']) - content['duration']) > .04:
        raise ValueError('音频时长与场景主时钟不同，禁止缩放声音适配。')
    media_probes = {}
    for row in content['scenes']:
        for key in ['media', 'presenter', 'overlay']:
            item = row.get(key)
            if not item or item.get('kind') == 'image':
                continue
            probe = json.loads(subprocess.check_output([args.ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(public / item['file'])], timeout=30))
            visible = media_duration(row, key)
            if not any(s['codec_type'] == 'video' for s in probe['streams']) or float(probe['format']['duration']) + .04 < visible:
                raise ValueError('媒体不足以覆盖原速可见区间：' + item['file'])
            media_probes[item['file']] = probe
    (public / 'content.json').write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding='utf-8')
    episode = {'contract': 'haike-nana-mint-episode-v1', 'paid_calls': 0, 'content': content, 'files': {p.relative_to(public).as_posix(): {'path': str(p), 'sha256': sha(p)} for p in sorted(public.rglob('*')) if p.is_file()}, 'media_probes': media_probes, 'provenance': provenance, 'rights': 'Third-party reference media stays private; template source and controlled slots are distributable separately.', 'continuous_listen': 'pending', 'reference_sha256': SOURCE_SHA if args.reference else None}
    (data_dir / 'episode.json').write_text(json.dumps(episode, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'public': str(public), 'duration': content['duration'], 'scenes': len(content['scenes']), 'paid_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
