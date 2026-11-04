"""Versioned evidence cards for paper text shots, inside the native queue adapter.

This is project-owned composition. It does not modify or extract protected kit
code. Native controls/captions keep their own clock; evidence videos stay muted.
"""
from __future__ import annotations

import math
from pathlib import Path
from functools import lru_cache
from fractions import Fraction
import re
import subprocess
from uuid import uuid4

from backlot.work_catalog import WorkError

PROFILE = 'paper-evidence/1'
TEXT_AREA = {'x': 72, 'y': 110, 'w': 936, 'h': 600}
CARDS = ((72, 790, 936, 610), (642, 1180, 366, 218))
PORTRAIT_CARDS = ((124, 750, 392, 650), (564, 750, 392, 650))


def require(ok, message):
    if not ok:
        raise WorkError('纸感证据层：' + message)


def validate(parameters, assets=None, probe=None):
    support = parameters.get('paperSupport')
    if support is None:
        return None
    t = parameters.get('timeline', {})
    require(isinstance(support, dict) and set(support) == {'profile', 'shots'}
            and support['profile'] == PROFILE and isinstance(support['shots'], list), '配置格式无效')
    require(parameters.get('workflow') == 'motion-kit' and t.get('layout') == 'portrait'
            and t.get('styleProfile') == 'paper', '只支持原生9:16纸感模板')
    segments = t.get('segments', [])
    captions = t.get('captions', [])
    require(isinstance(segments, list) and segments and all(isinstance(s, dict) for s in segments)
            and isinstance(captions, list) and captions and all(isinstance(c, dict) for c in captions)
            and len(support['shots']) <= len(segments), '请先绑定真实时钟与字幕')
    require(not any(k in t for k in {'captionPosition', 'captionSafeArea', 'captionLayout', 'narrationLayout'}),
            '本版使用原包默认字幕区；改变字幕位置须另行验证布局')
    ids = [s.get('shotId') for s in segments]
    require(all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids), '镜头编号须唯一')
    indexed = {}
    for shot in support['shots']:
        require(isinstance(shot, dict) and set(shot) == {'shotId', 'cards'}
                and isinstance(shot['shotId'], str) and shot['shotId'] in ids
                and shot['shotId'] not in indexed, '素材镜头编号无效或重复')
        require(isinstance(shot['cards'], list) and len(shot['cards']) == 2, '文字镜头须绑定两路不同真实素材')
        indexed[shot['shotId']] = shot
    for segment in segments:
        shot = indexed.get(segment['shotId'])
        native_visual = bool(segment.get('props', {}).get('src')) or (
            segment.get('presenter') in {'card', 'small'} and bool(t.get('presenter', {}).get('src')))
        if native_visual:
            require(shot is None, '原生实拍或人物窗口不叠加证据卡，避免遮挡')
            continue
        require(shot is not None, '文字镜头缺少素材：' + segment['shotId'])
        require(segment.get('area') == TEXT_AREA, '文字动作须使用已验证的上方区域，避让素材和字幕')
        require(not t.get('overlays'), '本版证据层未验证额外叠层的避让，请另建明确布局变体')
        names = []
        for card in shot['cards']:
            require(isinstance(card, dict) and set(card) == {'src', 'sourceStart', 'captionIndices', 'meaning'},
                    '素材须声明文件、源入点、对应字幕和语义用途')
            name = card['src']
            require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', name)
                    and Path(name).suffix.lower() in {'.mp4', '.mov', '.webm', '.png', '.jpg', '.jpeg', '.webp'},
                    '素材须为本期安全文件名')
            names.append(name)
            start = card['sourceStart']
            require(type(start) in {int, float} and math.isfinite(start) and start >= 0, '源入点无效')
            require(isinstance(card['meaning'], str) and 4 <= len(card['meaning']) <= 180, '请说明素材与本段口播的关系')
            indices = card['captionIndices']
            require(isinstance(indices, list) and indices
                    and all(type(i) is int and 0 <= i < len(captions)
                            and captions[i]['s'] < segment['t1'] and captions[i]['e'] > segment['t0'] for i in indices)
                    and len(set(indices)) == len(indices),
                    '素材必须对应本镜真实字幕，不能借用无关台词')
            if assets is not None:
                require(name in assets, '素材未绑定：' + name)
                info = probe(Path(assets[name]['path']))
                require(info.get('video'), '素材没有可显示的画面')
                if Path(name).suffix.lower() in {'.mp4', '.mov', '.webm'}:
                    require(start + segment['t1'] - segment['t0'] <= info['duration'] + .025,
                            '素材区间不足，不允许循环或停帧：' + name)
        require(len(set(names)) == 2, '不能把同一路素材复制成两张证据卡')
        if assets is not None:
            require(len({assets[n]['sha256'] for n in names}) == 2, '同一素材改名不能冒充两路')
    return support


@lru_cache(maxsize=128)
def display_ratio(path, digest):
    from backlot.studio_render import media_probe
    video = media_probe(path)['video']
    w, h = video['width'], video['height']
    sar = video.get('sample_aspect_ratio')
    ratio = float(Fraction(sar.replace(':', '/'))) if sar and sar != 'N/A' else 1
    w *= ratio
    rotation = next((s.get('rotation', 0) for s in video.get('side_data_list', [])
                     if s.get('side_data_type') == 'Display Matrix'), 0)
    if abs(round(rotation)) % 180 == 90:
        w, h = h, w
    return w / h


def command(ffmpeg, source, target, parameters, assets, *, at=None, color=None, layouts=None):
    """One layout/filter path for public preview stills and final frames."""
    support = validate(parameters)
    require(support is not None, '缺少证据层')
    segments = {s['shotId']: s for s in parameters['timeline']['segments']}
    args = [str(ffmpeg), '-nostdin', '-v', 'error', '-y', '-i', str(source)]
    graph, base, index = [], '0:v', 0
    if color and color['filter']:
        graph.append('[0:v]' + color['filter'] + '[nativecolor]')
        base = 'nativecolor'
    for shot in support['shots']:
        segment = segments[shot['shotId']]
        start, end = segment['t0'], segment['t1']
        if at is not None and not start <= at < end:
            continue
        boxes = layouts.get(shot['shotId'], CARDS) if layouts else CARDS
        for card, (x, y, w, h) in zip(shot['cards'], boxes):
            index += 1
            offset = card['sourceStart'] + (at - start if at is not None else 0)
            path = Path(assets[card['src']]['path'])
            if path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}:
                args += ['-loop', '1']
            else:
                args += ['-ss', f'{offset:.6f}']
            args += ['-t', f'{end-start if at is None else .1:.6f}', '-i', str(path)]
            origin = start if at is None else 0
            label, out = f'card{index}', f'paper{index}'
            # Normalize display pixels before contain; resetting SAR after pad
            # alone would squeeze anamorphic source footage.
            graph.append(f"[{index}:v]scale=w='max(2,trunc(iw*sar/2)*2)':h=ih,setsar=1,"
                         f'scale={w-24}:{h-24}:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                         f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0xfaf6ec,setsar=1,'
                         f'drawbox=x=0:y=0:w=iw:h=ih:color=0xd0c7b3:t=2,'
                         f'drawbox=x=18:y=ih-8:w=84:h=3:color=0xb64c3b:t=fill,'
                         f'setpts=PTS-STARTPTS+{origin:.6f}/TB[{label}]')
            # The card is visible on frame zero; a small settling motion supplies
            # physical paper weight without an empty entrance or covering text.
            local = f'(t-{start:.6f})' if at is None else f'{at-start:.6f}'
            yy = f'{y}+12*exp(-6*{local})'
            enable = f":enable='gte(t,{start:.6f})*lt(t,{end:.6f})'" if at is None else ''
            graph.append(f'[{base}][{label}]overlay=x={x}:y=\'{yy}\':eof_action=pass:repeatlast=0{enable}[{out}]')
            base = out
    if graph:
        args += ['-filter_complex_threads', '1', '-filter_complex', ';'.join(graph), '-map', f'[{base}]']
    else:
        args += ['-map', '0:v:0']
    if at is not None:
        args += ['-frames:v', '1', '-update', '1', '-an']
    else:
        args += ['-map', '0:a:0', '-c:a', 'copy', '-c:v', 'libx264', '-preset', 'fast', '-crf', '16',
                 '-pix_fmt', 'yuv420p', *(color['options'] if color else []),
                 '-t', str(parameters['timeline']['duration']), '-movflags', '+faststart']
    return args + [str(target)]


def check_preview(receipt):
    """Use measured caption rectangles, rather than assuming the default fits."""
    samples = receipt.get('renderer', {}).get('captionSamples')
    require(isinstance(samples, list), '原生预览缺少字幕测量')
    items = [item for sample in samples for item in sample.get('items', [])]
    require(items, '预览没有覆盖真实字幕时刻')
    minimum = max(y + h + 12 for x, y, w, h in (*CARDS, *PORTRAIT_CARDS)) + 20
    for item in items:
        rect = [item.get(k) for k in ['left', 'right', 'top', 'bottom']]
        require(all(type(v) in {int, float} and math.isfinite(v) for v in rect)
                and 0 <= rect[0] < rect[1] <= 1081 and minimum <= rect[2] < rect[3] <= 1920,
                '实际字幕与素材区冲突或超出画布，请调整后新建预览')


def compose(ffmpeg, source, target, parameters, assets, *, at=None):
    target = Path(target)
    candidate = target.with_stem(target.stem + '-pending-' + uuid4().hex)
    color = None
    if at is None:
        from backlot.studio_motiongit_render import encoding_layout
        from backlot.studio_render import media_probe
        color = encoding_layout(media_probe(source)['video'], False)
    layouts = {s['shotId']: PORTRAIT_CARDS if all(
        display_ratio(str(assets[c['src']]['path']), assets[c['src']]['sha256']) < .85 for c in s['cards']) else CARDS
        for s in parameters['paperSupport']['shots']}
    subprocess.run(command(ffmpeg, source, candidate, parameters, assets, at=at, color=color, layouts=layouts), check=True,
                   capture_output=True, timeout=600, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    candidate.replace(target)
