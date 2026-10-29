"""Exact-version MotionGit slot metadata; this module never runs a package.

The distributed map contains public input names and independent project fields.
Recognition neither verifies an imported envelope nor converts its runtime.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = ROOT / 'config/motion-adapters'
SCHEMA = 'haike-motion-adapter/1'
CATEGORIES = {'direct', 'project_adapter', 'locked'}
SOURCE_KINDS = {'text', 'dynamicText', 'number', 'image', 'video', 'sequence',
                'wall-sprites', 'caption-file', 'enum'}
IDENTITY = re.compile(r'[a-z0-9][a-z0-9-]{1,119}\Z')
VERSION = re.compile(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?\Z')
MAX_MAP_BYTES = 256 * 1024


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _validate(value):
    _require(isinstance(value, dict) and value.get('schema') == SCHEMA,
             '动效适配映射格式无效')
    _require(isinstance(value.get('adapter_id'), str)
             and IDENTITY.fullmatch(value['adapter_id']), '适配器编号无效')
    source = value.get('source', {})
    _require(isinstance(source, dict) and isinstance(source.get('template_id'), str)
             and IDENTITY.fullmatch(source['template_id']), '来源模板编号无效')
    versions = source.get('versions')
    _require(isinstance(versions, list) and versions and len(versions) == len(set(versions))
             and all(isinstance(v, str) and VERSION.fullmatch(v) for v in versions),
             '适配器必须声明精确版本，不能使用版本范围或通配符')
    policy = value.get('policy', {})
    _require(policy.get('exact_version_match') is True
             and policy.get('unknown_version') == 'needs_adaptation'
             and policy.get('automatic_motion_conversion') is False,
             '未知包或新版本必须重新核对适配')
    fields = value.get('fields', {})
    _require(isinstance(fields, dict) and set(fields) == CATEGORIES
             and all(isinstance(fields[k], list) for k in CATEGORIES),
             '适配字段须分为 direct、project_adapter、locked')
    contract = value.get('source_contract', {})
    _require(isinstance(contract, dict) and isinstance(contract.get('globals'), dict)
             and isinstance(contract.get('groups'), list), '缺少公开槽位清单')
    groups = {}
    for group in contract['groups']:
        _require(isinstance(group, dict) and isinstance(group.get('id'), str)
                 and group['id'] not in groups and isinstance(group.get('slots'), dict),
                 '公开动作组槽位清单无效')
        groups[group['id']] = group['slots']
    ids = set()
    for category, rows in fields.items():
        for row in rows:
            _require(isinstance(row, dict) and isinstance(row.get('id'), str)
                     and row['id'] and row['id'] not in ids, '替换字段编号重复或无效')
            ids.add(row['id'])
            if category == 'direct':
                ref = row.get('source', {})
                path = ref.get('input_path')
                group = ref.get('group')
                known = groups.get(group, {}) if group else contract['globals']
                document = 'adapter/parameter-map.json' if group else contract.get('schema')
                expected = (f'brief.segments[].candidates["{group}"].inputs.{path}'
                            if group else path)
                _require(isinstance(path, str) and path in known
                         and row.get('kind') in SOURCE_KINDS
                         and row['kind'] == known[path]
                         and ref.get('document') == document
                         and ref.get('parameter_path') == expected,
                         'direct 字段必须指向确实公开的同类型原生槽')
            elif category == 'project_adapter':
                _require(isinstance(row.get('project_paths'), list) and row['project_paths']
                         and all(isinstance(p, str) and p.startswith(
                             ('props.', 'audio.', 'sources', 'provenance.', 'shotPlan'))
                                 for p in row['project_paths']), '项目适配字段缺少实际输入路径')
                if 'source_group' in row:
                    slots = groups.get(row['source_group'], {})
                    _require(bool(slots), '项目字段引用未知来源动作组')
                    references = list(row.get('source_input_paths', []))
                    for binding in row.get('bindings', []):
                        references.extend(binding.get('source_input_paths', []))
                        _require(isinstance(binding.get('project_path'), str)
                                 and binding['project_path'].startswith('props.scenes['),
                                 '文字映射缺少实际项目字段')
                    _require(all(p in slots for p in references), '项目映射引用未公开原生槽')
            else:
                _require(isinstance(row.get('reason'), str) and row['reason'],
                         '锁定字段必须解释原因')
    project = value.get('project', {})
    _require(isinstance(project, dict) and isinstance(project.get('template_id'), str)
             and project.get('workbench_url', '').startswith('/motiongit?')
             and project.get('catalog_endpoint', '').startswith('/api/studio/'),
             '缺少项目模板的现有入口')
    return value


def load_registry(directory=None):
    """Read trusted distributable metadata only; no imports, shell or downloads."""
    folder = Path(directory) if directory is not None else REGISTRY_DIR
    entries = []
    identities = set()
    for path in sorted(folder.glob('*.json')):
        _require(path.is_file() and not path.is_symlink()
                 and 0 < path.stat().st_size <= MAX_MAP_BYTES, '动效映射文件无效或过大')
        entry = _validate(json.loads(path.read_text(encoding='utf-8')))
        for version in entry['source']['versions']:
            identity = (entry['source']['template_id'], version)
            _require(identity not in identities, '同一模板版本登记了多个适配器')
            identities.add(identity)
        entries.append(entry)
    return entries


def _needs(template_id, version, reason):
    return {'status': 'needs_adaptation', 'adapter_id': None,
            'source_template_id': template_id, 'source_version': version,
            'reason': reason, 'automatic_motion_conversion': False,
            'documentation': 'Haike_video/docs/MOTION_PACK_ADAPTERS.md'}


def resolve_adapter(template_id, version, *, directory=None):
    """Resolve an exact source identity without granting native execution."""
    if not (isinstance(template_id, str) and IDENTITY.fullmatch(template_id)
            and isinstance(version, str) and VERSION.fullmatch(version)):
        return _needs('unknown', 'unknown', '模板身份或版本未明确，需要先读取公开合同。')
    try:
        entries = load_registry(directory)
    except (OSError, ValueError, TypeError):
        return _needs(template_id, version, '本机适配映射不可用，保留原包并重新核对。')
    for entry in entries:
        if entry['source']['template_id'] == template_id and version in entry['source']['versions']:
            return {'status': 'mapped', 'adapter_id': entry['adapter_id'],
                    'source_template_id': template_id, 'source_version': version,
                    'automatic_motion_conversion': False,
                    'direct_scope': entry['policy']['direct_scope'],
                    'field_counts': {k: len(v) for k, v in entry['fields'].items()},
                    'map_file': 'Haike_video/config/motion-adapters/' + entry['adapter_id'].removeprefix('motiongit-') + '.json',
                    'documentation': 'Haike_video/docs/MOTION_PACK_ADAPTERS.md',
                    'project_template': deepcopy(entry['project']),
                    'groups': [{'source_group': g['id'], 'project_group': g['project_group'],
                                'preview_endpoint': g['preview']['endpoint']}
                               for g in entry['groups']],
                    'production_status': entry['policy']['production_status']}
    return _needs(template_id, version, '此包或版本尚未登记；需完成一次公开槽位和实际预览适配。')


def source_slot_support(template_id, version, group, input_path, *, directory=None):
    """An undeclared source/media slot must never be advertised as direct."""
    resolved = resolve_adapter(template_id, version, directory=directory)
    if resolved['status'] != 'mapped':
        return {'category': 'needs_adaptation', 'reason': resolved['reason']}
    for entry in load_registry(directory):
        if entry['adapter_id'] != resolved['adapter_id']:
            continue
        for row in entry['fields']['direct']:
            ref = row['source']
            if ref.get('group') == group and ref['input_path'] == input_path:
                return {'category': 'direct', 'field': deepcopy(row)}
    return {'category': 'locked', 'reason': '该版本没有公开这个原生槽；不能推定可直接替换。'}
