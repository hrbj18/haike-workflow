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
PUBLIC_COVERS = ROOT / 'Haike_video/templates/public-covers'
PRESENTATION = ROOT / 'Haike_video/templates/motion-replay-presentation.json'


def entries():
    return [*json.loads(CATALOG.read_text(encoding='utf-8'))['templates'], *_imported_entries()]


def _imported_entries():
    """Project only catalog metadata; listing never verifies or executes a pack."""
    from backlot import studio_motiongit as motion
    result = []
    installed = motion.packages()['packages'] if (motion.STORE / 'registry.sqlite3').is_file() else []
    for package in installed:
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
            'declared_control_count': len(controls),
            'reference_preview': package.get('preview_url')})
    return [*result, *_uninstalled_motion_entries(result)]


def _uninstalled_motion_entries(installed):
    """Style references remain visible without importing a personalized pack."""
    from backlot import studio_motiongit as motion
    if not PRESENTATION.is_file():
        return []
    try:
        if PRESENTATION.is_symlink() or PRESENTATION.stat().st_size > 128 * 1024:
            return []
        document = json.loads(PRESENTATION.read_text(encoding='utf-8'))
        if document.get('schema') != 'haike.motion-replay-presentation/1':
            return []
        rows = document.get('templates', [])
        if not isinstance(rows, list) or len(rows) > 32:
            return []
    except (OSError, ValueError, TypeError):
        return []
    identities = {(row.get('template_id'), row.get('version')) for row in installed}
    used_ids = {row['id'] for row in installed}
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        identity, version, gallery_id, name = (row.get(key) for key in
                                               ('template_id', 'version', 'gallery_id', 'name'))
        if (not all(isinstance(value, str) and 0 < len(value) <= 180 for value in
                    (identity, version, gallery_id, name))
                or not re.fullmatch(r'motion-package-[a-z0-9-]+', gallery_id)
                or (identity, version) in identities or gallery_id in used_ids):
            continue
        # Reuse the existing CDN filter for reviewed static presentation data.
        # This projection does not verify or grant execution to any package.
        preview = motion._public_preview({'verification': 'verified', 'documents': {
            'guide': {'preview': {'video': row.get('reference_preview')}}}})
        result.append({'id': gallery_id, 'template_id': identity, 'version': version,
            'name': name, 'group': '未安装 .motion', 'category': '动效模板',
            'status': '需导入原包', 'capability_status': '未安装，需导入原包',
            'duration': '按原包与本期输入', 'ratio': '按原包支持画幅',
            'description': f'v{version} · 可查看原版样式；制作前需导入匹配的合法原包并核验本期输入。',
            'runbook': 'Haike_video/templates/motiongit-imported/README.md',
            'href': '/motiongit?section=packages', 'family': 'imported-motion',
            'source_kind': 'imported-motion', 'package_installed': False,
            'presentation_dependency': 'public_original_reference' if preview else 'local_original_cover',
            'avatar': '人物与视频能力以原包及本期实际输入为准', 'reference_preview': preview})
        identities.add((identity, version))
        used_ids.add(gallery_id)
    return result


def entry(template_id):
    return next((item for item in _production_entries() if item['id'] == template_id), None)


def _production_entries(preferred=None):
    from backlot.studio_motion_preferred import preferences
    choices = preferred if preferred is not None else {r['gallery_id']: r for r in preferences()}
    by_template = {r['template_id']: r for r in choices.values()}
    result, seen = [], set()
    for original in entries():
        item = dict(original)
        choice = choices.get(item['id']) or by_template.get(item.get('template_id', item['id']))
        if choice:
            if choice['gallery_id'] in seen:
                continue
            seen.add(choice['gallery_id'])
            item.update(id=choice['gallery_id'], template_id=choice['template_id'])
        result.append(item)
    return result


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
        for extension in allowed:
            cover = COVERS / (template_id + extension)
            if (not cover.is_symlink() and cover.resolve().is_relative_to(COVERS.resolve())
                    and cover.is_file()):
                return cover
    if kind == 'poster' and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,179}', template_id):
        for extension in allowed:
            cover = PUBLIC_COVERS / (template_id + extension)
            if (not cover.is_symlink() and cover.resolve().is_relative_to(PUBLIC_COVERS.resolve())
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
    from backlot import motion_replay
    from backlot.studio_motion_preferred import production_map
    preferred = production_map()
    replay_error, replay_entries = None, None
    result = []
    for item in _production_entries(preferred):
        item = dict(item)
        item['category'] = ('动效模板' if item.get('group') == '动画模板'
                            or item.get('source_kind') == 'imported-motion' else '固定模板')
        choice = preferred.get(item['id'])
        if choice:
            canvas = choice['replay']['capabilities'].get('canvas', {})
            item.update(reference_version=item.get('version'), reference_description=item.get('description'),
                        duration='按本期完整音轨编排',
                        ratio=(f"{canvas['width']}×{canvas['height']} · {canvas['fps']}帧" if canvas else '高清 · 按所选版本画幅'),
                        avatar='已有同声源人物可复用，按本期素材安排',
                        description='已登记完整高清有声制作路线。准备本期完整声音、真实ASR、人物与素材后，沿固定入口制作；不自动重复配音或生成人物。原封面和样片不重渲染。')
            item.update(category='动效模板', preferred_production={k: v for k, v in choice.items() if k != 'replay'},
                        replay=choice['replay'], source_kind=choice['source_kind'],
                        status='可准备本期输入', capability_status='固定生产入口')
            item.pop('href', None)
        elif item['category'] == '动效模板':
            if replay_entries is None:
                try:
                    replay_entries = motion_replay.catalog()
                except (OSError, ValueError):
                    replay_entries = []
                    replay_error = '复刻合同需要修复，原样片和模板仍保留'
            matches = [value for value in replay_entries if
                       (value.get('gallery_id') == item['id']
                        or value['template_id'] == item.get('template_id', item['id']))
                       and value['version'] == item.get('version')]
            if len(matches) == 1:
                item['replay'] = matches[0]
                item['replay']['sources_verified'] = False
            elif replay_error:
                item['replay_notice'] = replay_error
        for kind in ('poster', 'sample'):
            item[kind] = f"/api/studio/template-library/{item['id']}/media/{kind}" if _media(item, kind) else None
        item['guide'] = f"/api/studio/template-library/{item['id']}/guide" if _document(item) else None
        if item.get('source_kind') == 'imported-motion' and item['sample']:
            item['status'] = '本机开发样片'
        result.append(item)
    return {'templates': result}
