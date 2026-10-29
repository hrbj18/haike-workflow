"""Read-only visual inventory with optional, portable screenshot covers."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'Haike_video/templates/library.json'
BINDINGS = ROOT / '.local/template-library-media.json'
COVERS = ROOT / 'Haike_video/templates/library-covers'


def entries():
    return json.loads(CATALOG.read_text(encoding='utf-8'))['templates']


def entry(template_id):
    return next((item for item in entries() if item['id'] == template_id), None)


def media(template_id, kind):
    if kind not in ('poster', 'sample') or entry(template_id) is None:
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
    if not item:
        return None
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
            item[kind] = f"/api/studio/template-library/{item['id']}/media/{kind}" if media(item['id'], kind) else None
        item['guide'] = f"/api/studio/template-library/{item['id']}/guide" if document(item['id']) else None
        result.append(item)
    return {'templates': result}
