"""Bounded visual measurements that direct, but never replace, reference review.

Frames keep their source PTS. Scores describe decoded pixel changes, not object
identities, semantic cuts, camera truth, or a verdict about animation quality.
"""
from __future__ import annotations

import math
from pathlib import Path
import re
import subprocess
import unicodedata

import numpy as np
from PIL import Image

from backlot import reference_understanding as ref
from backlot.media_index import probe_media

CONTRACT = 'haike-reference-motion-scan-v1'
MAX_SAMPLES = 3600


def normalized(text):
    return ''.join(c.casefold() for c in unicodedata.normalize('NFKC', text) if c.isalnum())


def phrase_ranges(rows, phrase, duration, *, padding=.5, occurrence=None):
    """Locate supplied words on their measured clock; never divide sentence time."""
    query = normalized(phrase)
    ref.require(query and ref.number(padding) and 0 <= padding <= 10, '台词或前后留白无效')
    ref.require(occurrence is None or type(occurrence) is int and occurrence > 0, '出现序号从1开始')
    matches = []
    for sentence in rows:
        words = sentence.get('words', [])
        letters, owners = '', []
        for word in words:
            part = normalized(word['text'])
            letters += part
            owners.extend([word] * len(part))
        start = 0
        while words and (at := letters.find(query, start)) >= 0:
            first, last = owners[at], owners[at + len(query) - 1]
            matches.append({'start': max(0., first['start']-padding),
                            'end': min(duration, last['end']+padding),
                            'granularity': 'measured-word', 'sentence_id': sentence['id'],
                            'word_ids': list(dict.fromkeys(w['id'] for w in owners[at:at+len(query)]))})
            start = at + len(query)
        if not words and query in normalized(sentence['text']):
            matches.append({'start': max(0., sentence['start']-padding),
                            'end': min(duration, sentence['end']+padding),
                            'granularity': 'measured-sentence', 'sentence_id': sentence['id'], 'word_ids': []})
    ref.require(matches, '实测转录中未找到这句台词；不猜时间，请检查原文或指定区间')
    if occurrence is not None:
        ref.require(occurrence <= len(matches), '台词出现序号超出实测记录')
        matches = [matches[occurrence-1]]
    return matches


def _histogram(rgb):
    hist = np.concatenate([np.histogram(rgb[:, :, c], bins=16, range=(0, 256))[0]
                           for c in range(3)]).astype(float)
    return hist / hist.sum()


def measurements(previous, current):
    """Resolution-independent pixel diagnostics; no aesthetic pass threshold."""
    ref.require(previous.shape == current.shape and current.ndim == 3 and current.shape[2] == 3,
                '测量帧的尺寸或通道不一致')
    delta = np.abs(current.astype(float)-previous.astype(float)).mean(axis=2)/255
    h, w = delta.shape
    tiles = []
    for row in range(4):
        for col in range(6):
            block = delta[row*h//4:(row+1)*h//4, col*w//6:(col+1)*w//6]
            tiles.append({'row': row, 'column': col, 'mean_change': round(float(block.mean()), 6)})
    mean = float(delta.mean())
    fraction = float((delta > .08).mean())
    histogram = float(np.abs(_histogram(current)-_histogram(previous)).sum()/2)
    return {'mean_change': round(mean, 6), 'changed_fraction': round(fraction, 6),
            'histogram_change': round(histogram, 6), 'tiles': tiles,
            'cut_candidate': fraction > .6 and (mean > .23 or histogram > .45)}


def suggested_ranges(frames, duration, *, limit=18, padding=.6):
    selected = []
    ranked = sorted(frames[1:], key=lambda f: (f['motion']['cut_candidate'],
                    f['motion']['mean_change']), reverse=True)
    for row in ranked:
        if row['motion']['mean_change'] < .015:
            continue
        if any(abs(row['at']-other['at']) < 1.2 for other in selected):
            continue
        selected.append(row)
        if len(selected) >= limit:
            break
    return [{'start': max(0., r['previous_at']-padding), 'end': min(duration, r['at']+padding),
             'sample_id': r['id'], 'priority': 'possible-cut' if r['motion']['cut_candidate'] else 'motion-change',
             'reason': '像素变化线索；精确边界、对象与含义须回看原生帧'}
            for r in sorted(selected, key=lambda f: f['at'])]


def load_scan(path):
    value = ref.read(path)
    ref.require(value.get('contract') == CONTRACT, '运动测量版本无效')
    identity = value.get('identity', {})
    ref.require(ref.digest(identity) == value.get('fingerprint'), '运动测量任务身份变化')
    ref.require(ref.sha(identity['source']['path']) == identity['source']['sha256'], '运动测量原片已改变')
    ref.require(ref.digest(value['frames']) == value.get('evidence_sha256'), '运动测量索引已改变')
    for frame in value['frames']:
        ref.require(ref.sha(frame['path']) == frame['sha256'], '运动测量图片已改变')
    return value


def scan(source, output, *, ffmpeg, ffprobe, every=.25, width=320, revision='1'):
    source = Path(source).resolve()
    ref.require(source.is_file(), '参考视频不存在')
    ref.require(ref.number(every) and .1 <= every <= 5, '测量间隔须为0.1–5秒')
    ref.require(type(width) is int and 96 <= width <= 640, '测量宽度须为96–640像素')
    info = probe_media(source, ffprobe)
    duration = float(info['format']['duration'])
    ref.require(math.isfinite(duration) and 0 < duration <= every*(MAX_SAMPLES-1),
                '本次测量超过3600帧预算；增加间隔或先选择较短的源片段')
    identity = {'source': {'path': str(source), 'sha256': ref.sha(source), 'duration': duration},
                'every': every, 'width': width, 'revision': str(revision),
                'method': 'native-pts-rgb-delta-histogram-grid-v1',
                'tools': {'ffmpeg_sha256': ref.sha(ffmpeg), 'ffprobe_sha256': ref.sha(ffprobe)}}
    fingerprint = ref.digest(identity)
    folder = Path(output).resolve()/fingerprint[:24]
    target = folder/'scan.json'
    if target.exists():
        saved = load_scan(target)
        return summary(target, saved, reused=True)
    ref.require(not folder.exists(), '保留未完成的运动测量，使用新revision继续')
    folder.mkdir(parents=True)
    vf = f"select='isnan(prev_selected_t)+gte(t-prev_selected_t,{every:.9f})',scale={width}:-2,showinfo"
    process = subprocess.run([str(ffmpeg), '-hide_banner', '-nostdin', '-copyts', '-i', str(source),
        '-an', '-sn', '-vf', vf, '-fps_mode', 'vfr', '-frames:v', str(MAX_SAMPLES+1),
        str(folder/'sample-%06d.png')], capture_output=True, text=True, encoding='utf-8',
        errors='replace', timeout=max(120, duration*3),
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    ref.require(process.returncode == 0, '运动测量解码失败，原片与已完成证据已保留')
    times = [float(t) for t in re.findall(r'\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:([\d.eE+-]+)', process.stderr)]
    files = sorted(folder.glob('sample-*.png'))
    ref.require(files and len(files) == len(times) <= MAX_SAMPLES, '测量图片与原生PTS不匹配或超出预算')
    frames, previous = [], None
    for file, at in zip(files, times):
        ref.require(math.isfinite(at) and 0 <= at <= duration+.001
                    and (not frames or at > frames[-1]['at']), '测量PTS无效或顺序错误')
        with Image.open(file) as im:
            current = np.array(im.convert('RGB'))
        row = {'id': f'sample-{len(frames)+1:06d}', 'path': str(file),
               'sha256': ref.sha(file), 'at': at, 'previous_at': frames[-1]['at'] if frames else at,
               'motion': measurements(previous, current) if previous is not None else None}
        frames.append(row)
        previous = current
    value = {'contract': CONTRACT, 'identity': identity, 'fingerprint': fingerprint,
             'frames': frames, 'evidence_sha256': ref.digest(frames),
             'suggested_ranges': suggested_ranges(frames, duration),
             'review_status': 'pending', 'production_ready': False,
             'limits': ['仅测量降采样帧像素变化，不判断语义或真实镜头运动',
                        '变化发生在相邻样本之间；不是逐帧准确的剪切点',
                        '静止可能是必要阅读；分数不是审美或质量判据']}
    ref.write(target, value)
    return summary(target, value, reused=False)


def summary(path, value, *, reused):
    return {'status': 'measurements_ready', 'scan': str(path), 'reused': reused,
            'samples': len(value['frames']), 'suggested_ranges': value['suggested_ranges'],
            'review_status': value['review_status'], 'production_ready': False}
