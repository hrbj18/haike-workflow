"""Read-only bridge to existing, exact-identity MotionGit routes.

Personal envelopes remain in the local store. This module neither runs their
helper nor creates drafts/jobs, and never converts a native group into a project
group. Returned bodies are consumed by the existing HTTP/CLI entrypoints.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from backlot.motion_replay import ReplayError

REGISTRY = Path(__file__).resolve().parents[1] / 'config/motion-replay/imported.json'
NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,159}\Z')
REQUEST_KEYS = {'workflow', 'parameters', 'assets', 'action_ids', 'package_id',
                'output_profile', 'title'}


def require(condition, message):
    if not condition:
        raise ReplayError(message)


def digest(value):
    """Canonical public-contract digest, independent of JSON formatting."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def file_sha(path):
    try:
        with Path(path).open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    except OSError as exc:
        raise ReplayError('本机文件不可读；请补齐原文件并检查当前用户的读取权限，不输出私有路径。') from exc


def public_contract(package, workflow):
    route = package['workflows'][workflow]
    return {'schema': route.get('schema', {}), 'controls': route.get('controls', {})}


def _registered(template):
    # Caller dictionaries cannot grant execution or change a package pin.
    entries = json.loads(REGISTRY.read_text(encoding='utf-8'))['templates']
    identity = (template.get('template_id'), template.get('version'))
    found = next((t for t in entries if (t['template_id'], t['version']) == identity), None)
    require(found is not None, '此原包或精确版本未适配，请保留原包并补充公开合同核对。')
    supplied_pin = template.get('package_identity')
    require(supplied_pin is None or supplied_pin == found['package_identity'],
            '请求模板的包SHA或helper身份不匹配；同名同版本的新包也须重新适配。')
    return found


def _package(template, workspace, package_id=None):
    pin = template['package_identity']
    store = Path(workspace).resolve() / '.local/motiongit'
    db_path = store / 'registry.sqlite3'
    require(db_path.is_file(), '缺少本机原包登记；请用现有导入入口导入有合法使用权的同版本原包，再显式核验。')
    try:
        with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True) as connection:
            rows = connection.execute('SELECT data FROM packages').fetchall()
        candidates = [json.loads(row[0]) for row in rows]
    except (sqlite3.Error, ValueError) as exc:
        raise ReplayError('本机原包登记不可读；请恢复私有登记与原包，不能以公开摘要替代授权。') from exc
    require(all(isinstance(p, dict) for p in candidates), '本机原包登记结构已损坏，请恢复私有登记备份。')
    matches = [p for p in candidates if p.get('template_id') == template['template_id']
               and p.get('version') == template['version'] and p.get('sha256') == pin['sha256']
               and (package_id is None or p.get('id') == package_id)]
    require(len(matches) == 1, '未找到唯一的同模板ID、精确版本和SHA原包；请导入并核验匹配原包，新版本须重新适配。')
    package = matches[0]
    require(package.get('verification') == 'verified' and package.get('runnable') is True
            and package.get('support') == 'official-helper', '原包尚未通过现有验签入口，请先显式核验，不自动执行包。')
    # Portable relocation uses only the canonical current-store copy, or the
    # recorded original after hashing it. No package paths enter the result.
    canonical = store / 'packages' / package['id'] / 'original.motion'
    source = canonical if canonical.is_file() else Path(package.get('path', ''))
    require(source.is_file() and not source.is_symlink(), '合法原包文件缺失；请补齐原始.motion，不复制保护核心或凭据到源码。')
    require(file_sha(source) == pin['sha256'], '原包字节已变化，请恢复匹配SHA原包或对新包重新适配。')
    from backlot import studio_motiongit as motion
    helper_pin = motion.helper_identity(package)
    require(helper_pin['version'] == pin['helper']['version']
            and helper_pin['sha256'] == pin['helper']['sha256'], '原包helper版本与登记不符，请保留旧版并重新核验。')
    canonical_helper = store / 'tools' / helper_pin['version'] / 'motion.mjs'
    helper = canonical_helper if canonical_helper.is_file() else Path(package.get('helper', ''))
    require(helper.is_file() and not helper.is_symlink()
            and file_sha(helper) == helper_pin['sha256'], '缺少已固定SHA的官方helper，请通过现有核验/安装入口补齐；本接口不下载或安装。')
    motion._hum_workflow(package)  # Existing project schema, only on a private copy.
    return package


def _closed_schema(schema, value, root, path='parameters'):
    """Reject undeclared keys even when a permissive package schema allows them.

    A schema object with no declared properties is an intentional open data map;
    controls' props are separately checked against the public control contract.
    The native schema validator still owns types, alternatives and constraints.
    """
    if '$ref' in schema:
        ref = schema['$ref']
        require(ref.startswith('#/'), '参数合同含未接入的外部引用，请重新适配。')
        target = root
        for part in ref[2:].split('/'):
            target = target[part.replace('~1', '/').replace('~0', '~')]
        return _closed_schema(target, value, root, path)
    if isinstance(value, dict):
        props = schema.get('properties', {})
        patterns = schema.get('patternProperties', {})
        if props and (schema.get('additionalProperties') is False or path == 'parameters'):
            require(not (set(value) - set(props) - {k for k in value
                        if any(re.search(pattern, k) for pattern in patterns)}),
                    f'参数含未开放字段：{path}；请按该版本公开槽填写。')
        for key, child in value.items():
            if key in props:
                _closed_schema(props[key], child, root, path + '.' + key)
    elif isinstance(value, list) and isinstance(schema.get('items'), dict):
        for index, child in enumerate(value):
            _closed_schema(schema['items'], child, root, f'{path}[{index}]')


def _control_value(value, spec, path, media_refs):
    kind = spec.get('type')
    types = {'string': str, 'array': list, 'object': dict, 'boolean': bool}
    if kind in types:
        require(isinstance(value, types[kind]), f'控件参数类型无效：{path}')
    elif kind in {'number', 'integer'}:
        require(type(value) in ({int} if kind == 'integer' else {int, float}), f'控件参数类型无效：{path}')
    elif kind in {'media', 'icon', 'enum'}:
        require(isinstance(value, str), f'控件参数类型无效：{path}')
        if kind == 'enum':
            require(value in spec.get('values', []), f'控件枚举未开放：{path}')
        if kind == 'media' and value:
            alias = value.removeprefix('inputs/')
            require(NAME.fullmatch(alias) is not None, f'控件素材须使用已导入平面绑定名：{path}')
            media_refs.add(alias)
    if isinstance(value, str):
        # These exact component schemas express visible-character bounds with
        # [*]* around every character; emphasis markers do not consume capacity.
        length = len(value.replace('*', '')) if 'max' in spec else len(value)
        require(length <= spec.get('max', spec.get('maxLength', float('inf'))), f'控件文字超出容量：{path}')
    if type(value) in {int, float}:
        import math
        require(math.isfinite(value) and spec.get('min', -float('inf')) <= value
                <= spec.get('max', float('inf')), f'控件数值超出范围：{path}')
    if isinstance(value, list):
        require(spec.get('minItems', 0) <= len(value) <= spec.get('maxItems', float('inf')),
                f'控件项目数量超出容量：{path}')
        item_spec = {k: v for k, v in spec.items() if k not in {'type', 'minItems', 'maxItems'}}
        item_spec.update(type=spec.get('of'), props=spec.get('props', {}))
        for index, item in enumerate(value):
            _control_value(item, item_spec, f'{path}[{index}]', media_refs)
    if isinstance(value, dict) and spec.get('props'):
        _control_props(value, spec['props'], path, media_refs)


def _control_props(value, fields, path, media_refs):
    require(isinstance(value, dict) and not set(value) - set(fields), f'控件含未开放参数：{path}')
    for key, field in fields.items():
        require(not field.get('required') or key in value, f'控件缺少必需参数：{path}.{key}')
        if key in value:
            _control_value(value[key], field, path + '.' + key, media_refs)


def _component_actions(template, workflow, parameters, package, assets):
    timeline = parameters['timeline'] if workflow == 'motion-kit' else parameters
    controls = package['workflows'][workflow]['controls']
    used, media_refs = [], set()
    for index, segment in enumerate(timeline['segments']):
        control = controls[segment['control']]
        _control_props(segment.get('props', {}), control.get('props', {}), f'segments[{index}].props', media_refs)
        cues = segment.get('cues', [])
        require(isinstance(cues, list) and all(type(c) in {int, float} for c in cues)
                and cues == sorted(cues) and len(cues) == len(set(cues))
                and all(segment['t0'] <= c < segment['t1'] for c in cues),
                '控件内部cue须按原合同使用全片绝对秒、升序且落在本组窗口内。')
        # The public count is a directing guide, not a required array length.
        # E.g. accepted compare/device drafts omit their automatic entry cue.
        # Keep the original helper fallback; do not invent a missing timestamp.
        used.append(f"haike.{template['template_id']}.{workflow}.{segment['control']}")
    require(media_refs <= set(assets), '控件公开media槽缺少已导入素材，请补齐这些绑定：' + ', '.join(sorted(media_refs - set(assets))))
    return used


def _assets(request, workspace):
    rows = request.get('assets', {})
    require(isinstance(rows, dict), 'assets须为绑定名到本地文件身份的对象。')
    result = {}
    for alias, row in rows.items():
        require(isinstance(alias, str) and NAME.fullmatch(alias) and isinstance(row, dict)
                and set(row) == {'path', 'sha256'}, '素材须使用安全平面绑定名及path/sha256。')
        require(isinstance(row['path'], str) and isinstance(row['sha256'], str), '素材路径和SHA须为字符串。')
        source = Path(row['path'])
        if not source.is_absolute():
            source = Path(workspace) / source
        require(source.is_file() and not source.is_symlink() and file_sha(source) == row['sha256'],
                '绑定素材缺失或SHA不符，请补齐原素材并重新审核。')
        result[alias] = {'path': str(source.resolve()), 'sha256': row['sha256']}
    return result


def _selected(request, used):
    wanted = request.get('action_ids')
    if wanted is not None:
        require(isinstance(wanted, list) and all(isinstance(a, str) for a in wanted)
                and len(wanted) == len(set(wanted)) and set(wanted) == set(used),
                'action_ids必须与参数实际使用的完整动作组一致；请修改真实segments/scenes后再准备，不能只提交动作选择列表。')


def _dark(template, request, assets):
    from backlot import studio_dark_full as dark
    value = deepcopy(request['parameters'])
    require(isinstance(value, dict) and not set(value) - {'props', 'audio', 'provenance', 'shotPlan'},
            'dark-full须使用独立项目props/audio/provenance/shotPlan；不能将项目字段写进原包direct。')
    require(all(k in value for k in ['props', 'audio', 'provenance']), 'dark-full缺少props/audio/provenance。')
    supplied = {'title': request.get('title', '动效复刻'), **value,
                'sources': {name: asset['path'] for name, asset in assets.items()}}
    checked = dark.preflight(supplied)
    used = [f"haike.{template['template_id']}.dark-full.{s['group']}" for s in checked['props']['scenes']]
    _selected(request, used)
    # A native reference reconstruction cannot silently select fewer groups.
    return used, {'entrypoint': 'backlot.studio_dark_full.prepare', 'input': supplied,
                  'normalized_props': checked['props'], 'normalized_audio': checked['audio'],
                  'http_entrypoint': '/api/studio/dark-full/drafts',
                  'category': 'project_adapter', 'requires_existing_queue': True}


def prepare(template, request, *, workspace):
    """Validate and prepare existing inputs; no helper, jobs, writes or payments.

    Native routes return a /motiongit/drafts body plus upload identities. Project
    dark-full returns its real prepare(queue, input) manifest. Missing resources
    raise ReplayError with a concrete remediation; no readiness is fabricated.
    """
    require(isinstance(template, dict) and isinstance(request, dict), '模板和请求须为JSON对象。')
    template = _registered(template)
    require(not set(request) - REQUEST_KEYS, '准备请求含未开放字段，请使用workflow/parameters/assets/action_ids。')
    workflow = request.get('workflow', template['default_workflow'])
    require(isinstance(workflow, str), 'workflow须为精确的工作流字符串。')
    routes = {r['workflow']: r for r in template['routes']}
    require(workflow in routes, '此模板版本未开放该制作路线，请使用登记的精确工作流。')
    route = routes[workflow]
    package = _package(template, workspace, request.get('package_id'))
    require(isinstance(request.get('parameters'), dict), '缺少实际parameters，请复制既有草稿并按原参数合同填写。')
    parameters = deepcopy(request['parameters'])
    assets = _assets(request, workspace)
    profile = request.get('output_profile', 'native')
    require(profile in route['output_profiles'], '此路线未开放该画幅；项目4:5不能冒充原包direct。')
    require(isinstance(request.get('title', '动效复刻'), str)
            and 0 < len(request.get('title', '动效复刻')) <= 100, '标题须为1至100字。')
    try:
        if workflow == 'dark-full':
            used, consumer = _dark(template, request, assets)
            runtime = 'passed-existing-project-preflight'
        else:
            from backlot import studio_motiongit as motion
            require(workflow in package['workflows'], '本机登记缺少该工作流，请用现有入口重新核验此精确原包。')
            require(digest(public_contract(package, workflow)) == route['public_contract_sha256'],
                    '本机公开参数合同已变化，请重新核对原包和适配器，不能自动套用旧动作。')
            if workflow not in {'project-wall', 'hum-production'}:
                _closed_schema(package['workflows'][workflow]['schema'], parameters,
                               package['workflows'][workflow]['schema'])
            motion.validate_parameters(package, workflow, parameters)
            if workflow in {'motion-kit', 'poster-kit'}:
                from backlot import studio_motiongit_render as render
                used = _component_actions(template, workflow, parameters, package, assets)
                render._check_bindings(parameters, assets)
                timeline = render.component_timeline({'workflow': workflow, 'parameters': parameters})
                require(timeline.get('voiceover') and timeline.get('music'), '请补齐独立完整口播和配乐绑定，保持主声音开启。')
                require(profile != '4:5' or timeline.get('layout') == 'portrait', '4:5路线需要原生portrait参数及本期字幕安全区复核。')
                render._check_source_windows(timeline, assets)
                runtime = 'passed-existing-media-window-checks'
            elif workflow == 'native' and template['template_id'] == 'knowledge-explainer-sketchnote':
                from backlot import studio_motion_knowledge as knowledge
                knowledge.bindings({'parameters': parameters}, assets)
                used = [f"haike.{template['template_id']}.native.{s['family']}" for s in parameters['segments']]
                runtime = 'passed-existing-knowledge-bindings'
            elif workflow in {'project-wall', 'hum-production'}:
                used = [f"haike.{template['template_id']}.{workflow}.composition"]
                if workflow == 'project-wall':
                    from backlot import studio_motiongit_narrated_pilot as pilot
                    supplied = {'props': parameters, 'sources': {k: v['path'] for k, v in assets.items()},
                                'title': request.get('title', '动效复刻')}
                    # Existing freeze/prepare owns source receipts and clock QA.
                    missing = pilot._required_names(parameters) - set(assets)
                    require(not missing, '项目素材墙缺少实际素材/音轨/字体，请按原prepare合同补齐全部绑定。')
                    require(set(assets) == pilot._required_names(parameters), '项目素材墙含未声明素材绑定。')
                    pilot._validate_receipts(parameters, {k: Path(v['path']) for k, v in assets.items()})
                else:
                    from backlot import studio_hum_production as hum
                    supplied = {'title': request.get('title', '动效复刻'), **parameters,
                                'sources': {k: v['path'] for k, v in assets.items()}}
                    hum.preflight(supplied)
                runtime = 'passed-existing-project-source-receipts'
            else:
                if template['template_id'] == 'knowledge-explainer-chalkboard':
                    used = [f"haike.{template['template_id']}.native.{s['family']}" for s in parameters['segments']]
                elif template['template_id'] == 'template-03-native':
                    groups = [key for s in parameters.get('brief', {}).get('segments', [])
                              for key in s.get('candidates', {})]
                    used = [f"haike.{template['template_id']}.native.{g}" for g in groups]
                    require(used, '仅参数编辑也须指定公开原生动作组，不能由适配器猜测。')
                else:
                    used = [f"haike.{template['template_id']}.native.reference-composition"]
                runtime = 'not-supported-for-production'
            _selected(request, used)
            consumer = {'entrypoint': '/api/studio/motiongit/drafts',
                        'body': {'package_id': package['id'], 'workflow': workflow,
                                 'parameters': parameters, 'output_profile': profile,
                                 'title': request.get('title', '动效复刻')},
                        'category': route['category'], 'requires_existing_queue': True}
    except ReplayError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        # Existing WorkError can contain arbitrary user-supplied values. Do not
        # reflect a path, signed URL, or parameter value into public diagnostics.
        raise ReplayError('原有参数/素材/时钟检查未通过；请在该路线现有check/preflight入口核对类型、容量、完整源区间和同源审核。') from exc
    known = {a['id']: a for a in template['actions']}
    require(set(used) <= set(known), '实际参数使用了未登记动作，请重新适配，不能推定支持。')
    return {'status': 'inspect_only' if route['execution'] == 'inspect_only' else 'prepared',
            'workflow': workflow, 'package_verification': {
                'template_id': template['template_id'], 'version': template['version'],
                'sha256': package['sha256'], 'verification': 'verified', 'bytes_checked': True,
                'helper_sha256': template['package_identity']['helper']['sha256']},
            'consumer': consumer, 'action_bindings': [deepcopy(known[a]) for a in dict.fromkeys(used)],
            'asset_bindings': [{'name': k, 'sha256': v['sha256']} for k, v in sorted(assets.items())],
            'runtime_validation': runtime, 'submitted': False,
            'semantic_validation': 'pending-original-plan-review; explicit cues retained, native automatic/fallback events are not newly aligned semantic evidence',
            'blockers': ([{'code': 'parameter_edit_only', 'remediation': '此原生版本只开放参数编辑，需独立实现并验收生产适配；不调用produce。'}]
                         if route['execution'] == 'inspect_only' else []),
            'next_gates': ['现有草稿保存/素材上传', '原计划及全部本期预览实际审核',
                           '原冻结和统一队列导出', '实际编码画面、完整声音及本期用户确认'],
            'validation_scope': '只读准备；不表示已渲染、观看、听审、许可确认或正式生产验收。'}
