"""Read-only visual inventory with optional, portable screenshot covers."""
from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'Haike_video/templates/library.json'
BINDINGS = ROOT / '.local/template-library-media.json'
COVERS = ROOT / 'Haike_video/templates/library-covers'


def entries():
    return [*json.loads(CATALOG.read_text(encoding='utf-8'))['templates'], *_imported_entries()]


def _imported_entries():
    """Project only catalog metadata; listing never verifies or executes a pack."""
    from backlot import studio_motiongit as motion
    if not (motion.STORE / 'registry.sqlite3').is_file():
        return []
    result = []
    for package in motion.packages()['packages']:
        identity = package.get('id', '')
        if (package.get('runtime') == 'project-source'
                or not isinstance(identity, str) or not re.fullmatch(r'[a-z0-9-]{4,80}', identity)):
            continue
        routes = package.get('workflows', {})
        verified = package.get('verification') == 'verified'
        production = verified and package.get('runnable') is True and (
            any(key in routes for key in ('motion-kit', 'poster-kit', 'hum-production', 'project-wall'))
            or routes.get('native', {}).get('production_protocol') == 'knowledge-story-v1')
        capability = '开放制作接口' if production else '仅参数编辑' if verified else '待核验，仅检查'
        controls = {key for route in routes.values() for key in route.get('controls', {})} if verified else set()
        layouts = set()
        for route in routes.values():
            schema = route.get('schema', {})
            for container in (schema, schema.get('properties', {}).get('timeline', {}), schema.get('properties', {}).get('brief', {})):
                layouts.update(v for v in container.get('properties', {}).get('layout', {}).get('enum', [])
                               if v in {'portrait', 'landscape'})
        ratio = ' / '.join(label for value, label in [('portrait', '竖屏'), ('landscape', '横屏')] if value in layouts) or '按原包支持画幅'
        result.append({'id': 'motion-package-' + identity, 'name': package.get('name') or '未命名原生模板',
            'group': '已导入 .motion', 'status': capability, 'capability_status': capability,
            'duration': '按本期音频和原包参数', 'ratio': ratio,
            'description': f"v{package.get('version', '未知')} · {capability}。"
                           + (f'原包声明{len(controls)}个动效控件；' if controls else '')
                           + '本机原包、模板参数与本期素材分开保存。换稿后的实际画面、声音和可用能力重新验收。',
            'runbook': 'Haike_video/templates/motiongit-imported/README.md',
            'href': '/motiongit?' + urlencode({'section': 'packages', 'package': identity}),
            'avatar': '人物能力以本包开放参数为准', 'family': 'imported-motion',
            'source_kind': 'imported-motion', 'package_id': identity,
            'template_id': package.get('template_id'), 'version': package.get('version'),
            'declared_control_count': len(controls)})
    return result


def entry(template_id):
    return next((item for item in entries() if item['id'] == template_id), None)


def media(template_id, kind):
    item = entry(template_id)
    return _media(item, kind) if item else None


def _media(item, kind):
    template_id = item['id']
    if kind not in ('poster', 'sample'):
        return None
    try:
        bindings = json.loads(BINDINGS.read_text(encoding='utf-8'))
        binding = bindings.get(template_id, {}) if isinstance(bindings, dict) else {}
        value = binding.get(kind) if isinstance(binding, dict) else None
        path = Path(value).resolve() if value else None
    except (OSError, ValueError, TypeError):
        path = None
    allowed = ('.jpg', '.jpeg', '.png', '.webp') if kind == 'poster' else ('.mp4', '.webm')
    if path and path.is_file() and path.suffix.lower() in allowed:
        return path
    # Distributed screenshots are named by catalog ID, never by an arbitrary
    # client path. Private sample bindings remain optional and take precedence.
    if kind == 'poster' and '/' not in template_id and '\\' not in template_id:
        cover = COVERS / (template_id + '.jpg')
        if (not cover.is_symlink() and cover.resolve().is_relative_to(COVERS.resolve())
                and cover.is_file()):
            return cover
    return None


def document(template_id):
    item = entry(template_id)
    return _document(item) if item else None


def _document(item):
    path = (ROOT / item['runbook']).resolve()
    roots = (ROOT / 'Haike_video/templates', ROOT / 'Haike-Videohub/agent-runbooks')
    if path.suffix != '.md' or not any(path.is_relative_to(p.resolve()) for p in roots):
        return None
    return path if path.is_file() else None


def library():
    result = []
    for item in entries():
        item = dict(item)
        for kind in ('poster', 'sample'):
            item[kind] = f"/api/studio/template-library/{item['id']}/media/{kind}" if _media(item, kind) else None
        item['guide'] = f"/api/studio/template-library/{item['id']}/guide" if _document(item) else None
        if item.get('source_kind') == 'imported-motion' and item['sample']:
            item['status'] = '本机开发样片'
        result.append(item)
    return {'templates': result}
