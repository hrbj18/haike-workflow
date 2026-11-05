"""Versioned motion contracts and preparation through owned renderer adapters.

JSON never selects an import, shell command, package installer or producer.
Preparation is read-only; existing queue/renderer gates still own production.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

WORKSPACE = Path(__file__).resolve().parents[2]
REGISTRY_DIR = WORKSPACE / 'Haike_video/config/motion-replay'
SCHEMA_PATH = REGISTRY_DIR / 'contract.schema.json'
REGISTRIES = {
    'numbered-02-05.json': 'backlot.motion_replay_numbered_02_05',
    'numbered-02-05-production.json': 'backlot.motion_replay_numbered_02_05_full',
    'numbered-06-11.json': 'backlot.motion_replay_numbered_06_11',
    'imported.json': 'backlot.motion_replay_imported',
    'imported-knowledge-full.json': 'backlot.motion_replay_knowledge_full',
    'imported-native-full.json': 'backlot.motion_replay_imported_native_full',
    'imported-promo-reference.json': 'backlot.motion_replay_promo_reference',
    'imported-promo-phase-v2.json': 'backlot.motion_replay_promo_phase_v2',
    'imported-promo-phase-v3.json': 'backlot.motion_replay_promo_phase_v3',
    'imported-knowledge-reference-public.json': 'backlot.motion_knowledge_public_execution_v1',
    'imported-knowledge-reference-public-v2.json': 'backlot.motion_knowledge_public_execution_v2',
    'imported-knowledge-reference-public-v3.json': 'backlot.motion_knowledge_public_execution_v3',
    'imported-public-v2.json': 'backlot.motion_replay_public_v2',
    'imported-public-v2-bound.json': 'backlot.motion_replay_public_v2_bound',
    'imported-public-poster-v3-bound.json': 'backlot.motion_replay_public_poster_v3_bound',
    'imported-public-paper-v3-bound.json': 'backlot.motion_replay_public_paper_v3_bound',
    'imported-public-quote-v3-bound.json': 'backlot.motion_replay_public_quote_v3_bound',
}
# These are owned code routes, not import names supplied by contract metadata.
PREPARATION_OVERRIDES = {
    ('numbered-06-11.json', template_id, '1.2.0-candidate.1'):
        ('backlot.motion_replay_chromatic_suite_production', 'prepare_contract')
    for template_id in ('chromatic-07', 'chromatic-08', 'chromatic-09',
                        'chromatic-six-10', 'chromatic-six-11')
}
MAX_REGISTRY_BYTES = 2 * 1024 * 1024


class ReplayError(ValueError):
    """An explicit contract/capability gate, safe to display to the operator."""


def _require(condition, message):
    if not condition:
        raise ReplayError(message)


def _read(path):
    _require(path.is_file() and not path.is_symlink()
             and 0 < path.stat().st_size <= MAX_REGISTRY_BYTES,
             '动效复刻合同不存在、过大或不是普通文件')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ReplayError('动效复刻合同无法读取，请恢复对应版本') from exc


def source_path(value, workspace=WORKSPACE):
    """Source identities are repository-relative, including through junctions."""
    _require(isinstance(value, str) and '\\' not in value and ':' not in value,
             '动效来源路径必须是仓库相对路径')
    relative = PurePosixPath(value)
    _require(not relative.is_absolute() and relative.parts
             and all(part not in {'.', '..'} for part in relative.parts),
             '动效来源路径越界')
    root = Path(workspace).resolve()
    path = root.joinpath(*relative.parts)
    _require(not path.is_symlink() and path.resolve().is_relative_to(root),
             '动效来源路径越界或重定向到仓库外')
    return path


def _unique(rows, label):
    ids = [row['id'] for row in rows]
    _require(len(ids) == len(set(ids)), f'{label}编号重复')
    return set(ids)


def validate_registry(document, *, schema_path=SCHEMA_PATH):
    validator = Draft202012Validator(_read(Path(schema_path)))
    errors = sorted(validator.iter_errors(document), key=lambda error: str(list(error.path)))
    if errors:
        location = '.'.join(str(part) for part in errors[0].path) or 'root'
        raise ReplayError(f'动效复刻合同字段无效：{location}')
    identities = set()
    for template in document['templates']:
        identity = (template['template_id'], template['version'])
        _require(identity not in identities, '同一动效模板版本重复登记')
        identities.add(identity)
        objects = _unique(template['objects'], '对象')
        actions = _unique(template['actions'], '动作')
        _unique(template['timeline']['events'], '事件')
        _unique(template['slots'], '槽位')
        for source in template['sources']:
            # Validate the lexical boundary without requiring local assets here.
            source_path(source['path'])
        for action in template['actions']:
            _require(set(action['objects']) <= objects, '动作引用未登记对象')
        for event in template['timeline']['events']:
            _require(event['action_id'] in actions, '时间线引用未知动作编号')
    return document


def load_registry(*, directory=REGISTRY_DIR):
    entries, identities = [], set()
    folder = Path(directory)
    for filename in REGISTRIES:
        path = folder / filename
        if not path.exists():
            continue
        document = validate_registry(_read(path))
        for template in document['templates']:
            identity = (template['template_id'], template['version'])
            _require(identity not in identities, '多个注册文件重复声明同一动效模板版本')
            identities.add(identity)
            item = deepcopy(template)
            item['_registry'] = filename
            entries.append(item)
    return entries


def resolve(template_id, version, *, directory=REGISTRY_DIR):
    _require(isinstance(template_id, str) and isinstance(version, str),
             '复刻需要明确的模板编号与精确版本')
    for template in load_registry(directory=directory):
        if (template['template_id'], template['version']) == (template_id, version):
            return template
    raise ReplayError('此动效模板或版本尚未适配，请保留原包并核对精确版本')


def verify_sources(template, *, workspace=WORKSPACE):
    result = []
    for source in template['sources']:
        path = source_path(source['path'], workspace)
        _require(path.is_file(), '动效实现来源缺失，请安装对应模板组件')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        _require(digest == source['sha256'], '动效实现来源已变化，需要重新适配与验收')
        result.append({'path': source['path'], 'sha256': digest})
    return result


def _invocation(template, value, request=None):
    """One envelope for original CLI, component and native/project inputs."""
    if value.get('status') not in {'prepared', 'inspect_only'}:
        return None
    consumer = value.get('consumer')
    if consumer:
        entrypoint = consumer.get('entrypoint')
        transport = 'http' if isinstance(entrypoint, str) and entrypoint.startswith('/api/') else 'project_python'
        payload = consumer.get('body', consumer.get('input'))
        context = {key: deepcopy(consumer[key]) for key in
                   ('http_entrypoint', 'requires_existing_queue', 'category') if key in consumer}
    elif value.get('queue_route'):
        route = value['queue_route']
        entrypoint, transport = route['entrypoint'], 'python_cli'
        payload = {'argv': deepcopy(route['argv'])}
        context = deepcopy(value.get('inputs', {}))
    else:
        entrypoint = value.get('entrypoint', template['renderer']['entrypoint'])
        transport, payload = 'component', value.get('input_props', value.get('props'))
        context = {key: deepcopy(value[key]) for key in ('assets', 'inputs', 'render_profile') if key in value}
    if value.get('production_contract'):
        context['production_contract'] = value['production_contract']
        if value.get('queue_admission'):
            context['queue_admission'] = value['queue_admission']
        if isinstance((request or {}).get('production_request'), dict):
            context['production_request'] = deepcopy(request['production_request'])
    _require(isinstance(entrypoint, str) and entrypoint and isinstance(payload, dict),
             '已准备的动效缺少实际入口或可消费输入，请修复所属适配器')
    return {'transport': transport, 'entrypoint': entrypoint,
            'input': deepcopy(payload), 'context': context,
            'operation': 'prepare_existing_renderer', 'submitted': False}


def prepare(template_id, version, request=None, *, workspace=WORKSPACE,
            directory=REGISTRY_DIR):
    """Prepare existing renderer inputs without running a video or paid stage."""
    _require(request is None or isinstance(request, dict), '复刻输入需要JSON对象')
    payload = deepcopy(request or {})
    for key, expected in [('template_id', template_id), ('version', version)]:
        _require(key not in payload or payload[key] == expected, '复刻输入的模板身份与请求不一致')
    template = resolve(template_id, version, directory=directory)
    checked_sources = verify_sources(template, workspace=workspace)
    requested = payload.get('action_ids')
    if requested is not None:
        known = {row['id'] for row in template['actions']}
        _require(isinstance(requested, list) and all(isinstance(v, str) for v in requested)
                 and len(requested) == len(set(requested)) and set(requested) <= known,
                 '请求含未知或重复动作编号')
    _require(template['renderer']['execution'] == 'supported',
             '此版本当前只支持检查或仍需适配，不能准备视频制作')
    module_name, function_name = PREPARATION_OVERRIDES.get(
        (template['_registry'], template_id, version),
        (REGISTRIES[template['_registry']], 'prepare'))
    from backlot.motion_platform import owned_module
    adapter = owned_module(module_name)
    value = getattr(adapter, function_name)(deepcopy(template), payload, workspace=Path(workspace))
    _require(isinstance(value, dict), '动效适配器返回格式无效')
    _require(value.get('status') in {'prepared', 'blocked', 'inspect_only'},
             '动效适配器没有返回明确的准备状态')
    return {**value, 'schema': 'haike.motion-replay-preparation/1',
            'template_id': template_id, 'version': version,
            'invocation': _invocation(template, value, payload),
            'source_verification': checked_sources, 'submitted': False,
            'production_gate': '沿现有统一队列或原生制作协议执行，并验收实际输出'}


def catalog(*, directory=REGISTRY_DIR):
    """Public capability summary; listing does not verify packages or sources."""
    return [{key: deepcopy(value) for key, value in template.items()
             if key in {'template_id', 'version', 'gallery_id', 'family',
                        'renderer', 'capabilities', 'validation'}}
            for template in load_registry(directory=directory)]
