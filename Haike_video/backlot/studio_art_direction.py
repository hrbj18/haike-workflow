"""Pinned Hallmark references for video planning; never executes upstream code."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from backlot.work_catalog import WorkError

ROOT = Path(__file__).resolve().parents[1] / 'design/hallmark'
GENRES = {'editorial': '编辑与品牌', 'modern-minimal': '产品与功能',
          'atmospheric': '氛围与影像', 'playful': '趣味与活动'}


def _catalog():
    return json.loads((ROOT / 'catalog.json').read_text(encoding='utf-8'))


def theme(slug):
    if not isinstance(slug, str) or not re.fullmatch(r'[a-z][a-z-]{0,39}', slug):
        raise WorkError('风格编号无效')
    value = next((t for t in _catalog()['themes'] if t['slug'] == slug), None)
    if value is None:
        raise WorkError('此风格不在当前已安装目录中')
    return value


def theme_asset(slug, suffix):
    value = theme(slug)
    if suffix not in {'jpg', 'md'}:
        raise WorkError('不支持此参考文件类型')
    path = ROOT / 'themes' / (value['slug'] + '.' + suffix)
    receipt = json.loads((ROOT / 'UPSTREAM.json').read_text(encoding='utf-8'))
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != receipt['files'].get('themes/' + path.name):
        raise WorkError('风格参考缺失或已改变，请恢复已登记版本')
    return path


def catalog():
    source = _catalog()
    return {**{k: source[k] for k in ('version', 'source_commit', 'source_url', 'scope')},
            'themes': [{**t, 'genre_zh': GENRES[t['genre']],
                        'image_url': f"/api/studio/motiongit/art-directions/{t['slug']}/image",
                        'reference_url': f"/api/studio/motiongit/art-directions/{t['slug']}/reference"}
                       for t in source['themes']]}


def normalize_selection(value):
    if value == {}:
        return None
    if not isinstance(value, dict):
        raise WorkError('视觉方向须为对象')
    selected = theme(value.get('theme_slug'))
    commit = _catalog()['source_commit']
    if value.get('source_commit', commit) != commit:
        raise WorkError('风格版本已改变，请重新选择并检查画面')
    return {'theme_slug': selected['slug'], 'source_commit': commit,
            'implementation_status': 'reference_selected'}


def video_brief(slug):
    selected = theme(slug)
    source = _catalog()
    return {'contract': 'hallmark-video-direction-v1', 'theme_slug': slug,
            'name': selected['name'], 'name_zh': selected['name_zh'],
            'source_commit': source['source_commit'], 'status': 'planning',
            'visual_material': selected['material'], 'summary_zh': selected['summary_zh'],
            'suggested_use_zh': selected['video_use_zh'],
            'theme_reference': theme_asset(slug, 'md').relative_to(ROOT.parents[1]).as_posix(),
            'decisions_to_complete': ['本期受众、信息重点与真实素材', '中文标题、正文、字幕字体及实际字形检查',
                                      '4:5构图、人物窗口与字幕避让', '逐镜头主次、动效选择与声音触发点'],
            'preserve': ['实际素材与事实', '口播原速和音频主时钟', '已认可的级联入场与选中放大',
                         '原包开放槽和项目自有模块的能力边界'],
            'review': {'opening_3_to_5_seconds': 'pending', 'keyframes': 'pending',
                       'continuous_audio_video': 'pending', 'user_aesthetic': 'pending'},
            'scope': '风格参考与制作计划；选择本身不会改变渲染参数或证明成片审美通过'}


def verify_references():
    source = _catalog()
    receipt = json.loads((ROOT / 'UPSTREAM.json').read_text(encoding='utf-8'))
    failures = [name for name, digest in receipt['files'].items()
                if not (ROOT / name).is_file() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    return {'valid': not failures and len(source['themes']) == 48,
            'theme_count': len(source['themes']), 'checked_files': len(receipt['files']),
            'source_commit': source['source_commit'], 'failures': failures}
