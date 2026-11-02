"""Paper v2: continuous owned footage, persistent titles, native auxiliary motion.

The public kit still authors its six controls and narration. This project-owned
layer shares one layout and clock between still review and the queued export.
Legacy paper-evidence/1 remains in paper_evidence.py.
"""
from __future__ import annotations

import hashlib
import json
import math
from bisect import bisect_right
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
import re
import subprocess
from uuid import uuid4

from backlot.work_catalog import WorkError

PROFILE = 'paper-evidence/2'
# The native compare control needs its full internal layout capacity. Render
# in that original area, then contain the complete result in the auxiliary band.
ACTION_AREA = {'x': 72, 'y': 110, 'w': 936, 'h': 600}
AUX = (60, 240, 960, 260)
MAIN = (60, 500, 960, 1200)
CAPTION_POSITION = {'bottomRatio': .025, 'leftRatio': .06, 'rightRatio': .06}
TITLE_SIZE, HEADING_SIZE = 64, 44


def require(ok, message):
    if not ok:
        raise WorkError('纸感连续主画面：' + message)


def number(value):
    return type(value) in {int, float} and math.isfinite(value)


def near(a, b):
    return number(a) and number(b) and abs(a-b) < .000001


def filename(value, suffixes):
    return (isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', value)
            and Path(value).suffix.lower() in suffixes)


def text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 28 and not any(ord(c) < 32 for c in value)


def video_window(info, path):
    """A long audio track cannot extend the valid picture window."""
    video = info.get('video')
    require(isinstance(video, dict) and video, '素材没有可显示的视频轨')
    try:
        origin = float(info.get('format', {}).get('start_time', 0))
        start = float(video.get('start_time', origin))-origin
        duration = video.get('duration')
        if duration is None and video.get('duration_ts') is not None:
            duration = int(video['duration_ts'])*float(Fraction(video['time_base']))
        if duration is not None:
            end = start+float(duration)
        else:
            # WebM may omit stream duration. Read timestamps from its actual
            # video packets, never substitute format.duration or audio length.
            from lib.ffmpeg_locator import resolve_ffmpeg_pair
            result = subprocess.run([str(resolve_ffmpeg_pair()[1]), '-v', 'error', '-select_streams', 'v:0',
                '-show_packets', '-show_entries', 'packet=pts_time,duration_time', '-of', 'json', str(path)],
                check=True, capture_output=True, timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            packets = json.loads(result.stdout)['packets']
            start = min(float(p['pts_time']) for p in packets)-origin
            end = max(float(p['pts_time'])+float(p['duration_time']) for p in packets)-origin
        require(math.isfinite(start) and math.isfinite(end) and end > start, '无法确定真实视频时间范围')
        return start, end
    except (ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        raise WorkError('纸感连续主画面：无法验证视频帧源窗，请先规范化该素材') from exc


@lru_cache(maxsize=128)
def frozen_probe(path, digest):
    # The queue verifies frozen file identities. Include that identity so a
    # new source never inherits another source's cached timestamps.
    from backlot.studio_render import media_probe
    return media_probe(path)


@lru_cache(maxsize=128)
def video_timestamps(path, digest):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    result = subprocess.run([str(resolve_ffmpeg_pair()[1]), '-v', 'error', '-select_streams', 'v:0',
        '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)],
        check=True, capture_output=True, timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    origin = float(frozen_probe(path, digest).get('format', {}).get('start_time', 0))
    times = sorted({float(f['best_effort_timestamp_time'])-origin for f in json.loads(result.stdout)['frames']})
    require(times and all(math.isfinite(t) for t in times), '缺少真实视频帧时间')
    return times


def source_clock(path, digest, requested):
    # A video frame holds until the next timestamp. Seeking beyond the final
    # frame's PTS can return no image even though that frame covers requested.
    times = video_timestamps(str(path), digest)
    index = bisect_right(times, requested+.0000001)-1
    require(index >= 0, '素材该时刻还没有视频帧')
    return max(0, times[index]-.0000001), requested-times[index]


def validate(parameters, assets=None, probe=None):
    support = parameters.get('paperSupport')
    require(isinstance(support, dict) and set(support) == {'profile', 'title', 'font', 'shots'}
            and support.get('profile') == PROFILE and text(support.get('title'))
            and filename(support.get('font'), {'.ttf', '.otf'}), '缺少固定标题、字体或新版配置')
    t = parameters.get('timeline', {})
    require(parameters.get('workflow') == 'motion-kit' and t.get('layout') == 'portrait'
            and t.get('styleProfile') == 'paper', '仅支持原生9:16纸感模板')
    duration = t.get('duration')
    segments, captions = t.get('segments'), t.get('captions')
    shots = support['shots']
    require(number(duration) and duration > 0 and isinstance(segments, list) and segments
            and all(isinstance(s, dict) for s in segments)
            and isinstance(shots, list) and len(shots) == len(segments)
            and isinstance(captions, list) and captions
            and all(isinstance(c, dict) and number(c.get('s')) and number(c.get('e'))
                    and 0 <= c['s'] < c['e'] <= duration for c in captions), '须绑定完整时钟、真实字幕及每一镜素材')
    require(t.get('captionPosition') == CAPTION_POSITION and t.get('captionSafeArea') == 'frame'
            and not t.get('presenter') and not t.get('overlays') and t.get('hud') is False,
            '请使用已验证的字幕区；人物在主素材层绑定，不叠加未知窗口')
    ids, cursor = set(), 0
    for segment, shot in zip(segments, shots):
        sid = segment.get('shotId')
        start, end = segment.get('t0'), segment.get('t1')
        require(isinstance(sid, str) and sid and sid not in ids and near(start, cursor)
                and number(end) and start < end <= duration,
                '原生镜头必须从0秒连续覆盖全片，不能断档或重叠')
        ids.add(sid); cursor = end
        require(segment.get('area') == ACTION_AREA and segment.get('presenter') == 'hide',
                '原生动作须在上方辅助区，避让标题和主素材')
        require(isinstance(shot, dict) and set(shot) == {'shotId', 'heading', 'clips'}
                and shot['shotId'] == sid and text(shot.get('heading'))
                and isinstance(shot['clips'], list) and 0 < len(shot['clips']) <= 20,
                '每镜须按顺序提供短标题及连续素材')
        local = 0
        for clip in shot['clips']:
            require(isinstance(clip, dict) and set(clip) in [
                {'src', 'sourceStart', 'start', 'end', 'captionIndices', 'meaning', 'kind'},
                {'src', 'sourceStart', 'start', 'end', 'captionIndices', 'meaning', 'kind', 'voiceSha256', 'videoSha256'}],
                '素材须声明源窗、镜头内时段、字幕索引和用途')
            require(filename(clip.get('src'), {'.mp4', '.mov', '.webm'})
                    and number(clip.get('sourceStart')) and clip['sourceStart'] >= 0
                    and near(clip.get('start'), local) and number(clip.get('end'))
                    and local < clip['end'] <= end-start+.000001
                    and clip.get('kind') in {'media', 'presenter'}, '素材时段断档、重叠或文件名无效')
            local = clip['end']
            a, b = start+clip['start'], start+clip['end']
            indices = clip.get('captionIndices')
            require(isinstance(clip.get('meaning'), str) and 4 <= len(clip['meaning']) <= 180
                    and isinstance(indices, list) and indices and len(set(indices)) == len(indices)
                    and all(type(i) is int and 0 <= i < len(captions)
                            and captions[i]['s'] < b and captions[i]['e'] > a for i in indices),
                    '素材须对应当前时段真实字幕并说明语义，不能随意填画面')
            if clip['kind'] == 'presenter':
                require(near(clip['sourceStart'], a)
                        and all(isinstance(clip.get(k), str) and re.fullmatch('[0-9a-f]{64}', clip[k])
                                for k in ['voiceSha256', 'videoSha256']), '人物须提供同源声音/视频身份并使用连续原声时钟')
            else:
                require('voiceSha256' not in clip and 'videoSha256' not in clip, '实拍素材不能冒用人物同源证明')
            if assets is not None:
                require(clip['src'] in assets, '素材未导入：' + clip['src'])
                info = probe(Path(assets[clip['src']]['path']))
                first, last = video_window(info, assets[clip['src']]['path'])
                require(clip['sourceStart'] >= first-.000001
                        and clip['sourceStart']+clip['end']-clip['start'] <= last+.000001,
                        '真实素材区间不足，不允许循环或越界停帧：' + clip['src'])
                if clip['kind'] == 'presenter':
                    voice = assets.get(t.get('voiceover'), {})
                    require(voice.get('sha256') == clip['voiceSha256']
                            and assets[clip['src']]['sha256'] == clip['videoSha256'], '人物与本期声音不匹配')
        require(near(local, end-start), '主素材没有覆盖本镜最后一帧')
    require(near(cursor, duration), '主素材没有覆盖全片结尾')
    if assets is not None:
        require(support['font'] in assets, '固定标题字体未导入')
        fonts = title_fonts(Path(assets[support['font']]['path']))
        for value, font in [(support['title'], fonts[0]), *[(s['heading'], fonts[1]) for s in shots]]:
            box = font.getbbox(value, stroke_width=1)
            require(box[2]-box[0] <= 944, '标题过长，请缩短文字，不能自动缩小字号')
    return support


def title_fonts(path):
    from PIL import ImageFont
    return tuple(ImageFont.truetype(str(path), size) for size in (TITLE_SIZE, HEADING_SIZE))


def title_images(folder, support, assets):
    """Private generated plates, derived from frozen text and licensed font."""
    from PIL import Image, ImageDraw
    fontpath = Path(assets[support['font']]['path'])
    fonts = title_fonts(fontpath)
    rows = [('theme', support['title'], fonts[0]), *[('chapter', s['heading'], fonts[1]) for s in support['shots']]]
    result = []
    for kind, value, font in rows:
        identity = hashlib.sha256((PROFILE+kind+value+assets[support['font']]['sha256']).encode()).hexdigest()[:24]
        path = Path(folder)/('paper-title-'+identity+'.png')
        size = (1080, 230) if kind == 'theme' else (960, 70)
        im = Image.new('RGB', size, '#faf6ec')
        draw = ImageDraw.Draw(im)
        draw.text((60 if kind == 'theme' else 16, 38 if kind == 'theme' else 7), value,
                  font=font, fill='#292d32', stroke_width=1, anchor='lt')
        if kind == 'theme':
            draw.line((60, 210, 1020, 210), fill='#c9c0ae', width=2)
            draw.rectangle((60, 210, 180, 215), fill='#b64c3b')
        # Rebuild deterministic derived plates even if a damaged or replaced
        # cache decodes. Atomic replace makes interrupted writes recoverable.
        candidate = path.with_stem(path.stem+'-pending-'+uuid4().hex)
        im.save(candidate)
        candidate.replace(path)
        result.append(path)
    return result[0], result[1:]


def clips(parameters):
    for segment, shot in zip(parameters['timeline']['segments'], parameters['paperSupport']['shots']):
        for clip in shot['clips']:
            yield segment['t0']+clip['start'], segment['t0']+clip['end'], clip


def preview_times(parameters):
    duration = parameters['timeline']['duration']
    times = {float(i) for i in range(math.ceil(duration)) if i < duration}
    for a, b, _ in clips(parameters):
        times.update(max(0, min(duration-1/60, p)) for p in (a-1/60, a, a+1/60, b-1/60))
    times.add(duration-1/60)
    return times


def command(ffmpeg, source, target, parameters, assets, plates, *, at=None, color=None):
    validate(parameters)
    args = [str(ffmpeg), '-nostdin', '-v', 'error', '-y', '-i', str(source)]
    graph, base, index = [], '0:v', 0
    if color and color['filter']:
        graph.append('[0:v]'+color['filter']+'[nativecolor]'); base = 'nativecolor'
    ax, ay, aw, ah = AUX
    graph.append(f'[{base}]split=2[canvas][nativeaux]')
    graph.append(f'[canvas]drawbox=x=0:y=0:w=iw:h={MAIN[1]+MAIN[3]}:color=0xfaf6ec:t=fill[clean]')
    graph.append(f"[nativeaux]crop={ACTION_AREA['w']}:{ACTION_AREA['h']}:{ACTION_AREA['x']}:{ACTION_AREA['y']},"
                 f'scale={aw}:{ah}:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                 f'pad={aw}:{ah}:(ow-iw)/2:(oh-ih)/2:color=0xfaf6ec[auxiliary]')
    graph.append(f'[clean][auxiliary]overlay={ax}:{ay}[withaux]'); base = 'withaux'
    x, y, w, h = MAIN
    for a, b, clip in clips(parameters):
        if at is not None and not a <= at < b:
            continue
        index += 1
        offset = clip['sourceStart'] + (at-a if at is not None else 0)
        lead = 0
        if 'sha256' in assets[clip['src']]:
            offset, lead = source_clock(assets[clip['src']]['path'], assets[clip['src']]['sha256'], offset)
        args += ['-ss', f'{offset:.9f}', '-t', f'{(b-a if at is None else .1)+lead:.9f}', '-i', str(assets[clip['src']]['path'])]
        graph.append(f"[{index}:v]scale=w='max(2,trunc(iw*sar/2)*2)':h=ih,setsar=1,split=2[sharp{index}][soft{index}]")
        graph.append(f'[soft{index}]scale=96:120:force_original_aspect_ratio=increase,crop=96:120,'
                     f'gblur=sigma=5,scale={w}:{h}[fill{index}]')
        graph.append(f'[sharp{index}]scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2[subject{index}]')
        origin = a if at is None else 0
        graph.append(f'[fill{index}][subject{index}]overlay=(W-w)/2:(H-h)/2,setsar=1,'
                     f'setpts=PTS-STARTPTS+{origin-lead:.9f}/TB[main{index}]')
        enable = f":enable='gte(t,{a:.9f})*lt(t,{b:.9f})'" if at is None else ''
        # Resample the final valid source frame to the native FPS within this
        # real source window. Never let a clip remain after its explicit end.
        graph.append(f'[{base}][main{index}]overlay={x}:{y}:eof_action=repeat:repeatlast=1{enable}[body{index}]')
        base = f'body{index}'
    theme, chapters = plates
    overlay_plates = [(theme, 0, 0, 0, parameters['timeline']['duration'])]
    overlay_plates += [(path, 60, 136, s['t0'], s['t1'])
                       for path, s in zip(chapters, parameters['timeline']['segments'])
                       if at is None or s['t0'] <= at < s['t1']]
    for path, xx, yy, a, b in overlay_plates:
        index += 1
        args += ['-i', str(path)]
        enable = f":enable='gte(t,{a:.9f})*lt(t,{b:.9f})'" if at is None else ''
        out = f'title{index}'
        graph.append(f'[{base}][{index}:v]overlay={xx}:{yy}:eof_action=repeat:repeatlast=1{enable}[{out}]')
        base = out
    args += ['-filter_complex_threads', '1', '-filter_complex', ';'.join(graph), '-map', f'[{base}]']
    if at is not None:
        args += ['-frames:v', '1', '-update', '1', '-an']
    else:
        args += ['-map', '0:a:0', '-c:a', 'copy', '-c:v', 'libx264', '-preset', 'fast', '-crf', '16',
                 '-pix_fmt', 'yuv420p', *(color['options'] if color else []), '-t', str(parameters['timeline']['duration']),
                 '-movflags', '+faststart']
    return args+[str(target)]


def check_preview(receipt):
    samples = receipt.get('renderer', {}).get('captionSamples')
    require(isinstance(samples, list), '原生预览缺少实际字幕测量')
    items = [i for sample in samples for i in sample.get('items', [])]
    require(items, '预览未覆盖真实字幕')
    for item in items:
        left, right, top, bottom = [item.get(k) for k in ['left', 'right', 'top', 'bottom']]
        require(all(number(v) for v in [left, right, top, bottom])
                and 0 <= left < right <= 1081 and MAIN[1]+MAIN[3]+12 <= top < bottom <= 1920,
                '字幕与主素材重叠或超出画面，请调整后重新预览')


def compose(ffmpeg, source, target, parameters, assets, *, at=None):
    from backlot.studio_render import media_probe
    from backlot.studio_motiongit_render import encoding_layout
    identities = {str(a['path']): a['sha256'] for a in assets.values()}
    support = validate(parameters, assets, lambda p: frozen_probe(str(p), identities[str(p)]))
    target = Path(target)
    candidate = target.with_stem(target.stem+'-pending-'+uuid4().hex)
    plates = title_images(target.parent, support, assets)
    color = encoding_layout(media_probe(source)['video'], False) if at is None else None
    subprocess.run(command(ffmpeg, source, candidate, parameters, assets, plates, at=at, color=color),
                   check=True, capture_output=True, timeout=1200, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    candidate.replace(target)


def check_output(ffmpeg, source, expected_frames):
    """Every encoded frame must retain textured footage and a readable title.

    Contrast is a technical empty-frame gate. Semantic subjects and suitability
    still require actual image review; this metric never replaces that review.
    """
    import numpy as np
    x, y, w, h = MAIN
    graph = (f'[0:v]split=2[m][t];[m]crop={w}:{h}:{x}:{y},scale=32:40,format=gray[main];'
             '[t]crop=960:100:60:38,scale=32:8,format=gray,pad=32:40:0:0:black[title];'
             '[main][title]hstack=inputs=2[out]')
    proc = subprocess.Popen([str(ffmpeg), '-nostdin', '-v', 'error', '-i', str(source), '-filter_complex_threads', '1',
                             '-filter_complex', graph, '-map', '[out]', '-an', '-f', 'rawvideo', '-pix_fmt', 'gray', 'pipe:1'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    count, bad, minimum = 0, [], [255., 255.]
    try:
        while True:
            raw = proc.stdout.read(64*40)
            if not raw:
                break
            require(len(raw) == 64*40, '逐帧检测数据不完整')
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(40, 64)
            body, title = frame[:, :32], frame[:8, 32:]
            contrasts = [float(body.std()), float(title.std())]
            minimum = [min(a, b) for a, b in zip(minimum, contrasts)]
            if contrasts[0] < 5 or contrasts[1] < 10 or not 5 < body.mean() < 250:
                if len(bad) < 20: bad.append(count)
            count += 1
        error = proc.stderr.read().decode('utf-8', errors='replace')
        require(proc.wait(timeout=60) == 0, '逐帧检测解码失败：'+error[:160])
    finally:
        if proc.poll() is None:
            proc.kill(); proc.wait()
        proc.stdout.close(); proc.stderr.close()
    require(abs(count-expected_frames) <= 1 and not bad, '发现主素材/标题空帧或帧数不足：'+str(bad))
    return {'profile': PROFILE, 'checked_frames': count, 'empty_frames': 0,
            'minimum_main_contrast': minimum[0], 'minimum_title_contrast': minimum[1],
            'semantic_review': 'separate-actual-images'}
