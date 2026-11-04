"""Public delivery inventory for the 18 replay contracts; no renderer execution.

Source formulas, package signatures, episode inputs and actual viewing retain
their existing owners. This module never imports a registry-specified command.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sqlite3
import sys
from contextlib import closing

try:
    from . import app_update as core
except ImportError:
    spec = importlib.util.spec_from_file_location('haike_replay_delivery_core', Path(__file__).with_name('app_update.py'))
    core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)

SCHEMA = 'haike.motion-replay-delivery/1'
PREFIX = 'Haike_video/config/motion-replay/'
GROUPS = {'numbered-02-05.json': 4, 'numbered-06-11.json': 6, 'imported.json': 8}
TRANSPORT = ['portable/motion_replay_capability.py', 'Haike_video/backlot/motion_replay.py',
             'Haike_video/backlot/studio_motion_replay_api.py', 'Haike_video/backlot/studio_api.py',
             'Haike_video/backlot/studio_template_library.py', 'Haike_video/templates/motion-replay-presentation.json',
             'Haike_video/backlot/motion_replay_production.py', 'Haike_video/scripts/motion_replay_production.py',
             'Haike_video/backlot/motion_replay_field_notes_video.py',
             'Haike_video/backlot/motion_replay_chromatic_production.py',
             'Haike_video/backlot/motion_replay_imported_production.py',
             'Haike_video/backlot/production_queue_worker.py',
             'Haike_video/scripts/motion_replay.py', 'Haike_video/docs/MOTION_REPLAY_STANDARD.md',
             'Haike_video/backlot/motion_replay_numbered_02_05.py',
             'Haike_video/backlot/motion_replay_numbered_06_11.py',
             'Haike_video/backlot/motion_replay_imported.py',
             PREFIX + 'contract.schema.json']


def require(ok, message):
    if not ok:
        raise core.UpdateError(message)


def declared(root):
    return core.safe_path(root, 'Haike_video/config/motion-preferred-production.json').is_file() or any(
        core.safe_path(root, PREFIX + name).exists() for name in [*GROUPS, 'contract.schema.json'])


def current_delivery(root):
    # The installation chooses data through the fixed preferred file. Import
    # only this fixed, delivered checker; never a registry-provided module.
    spec = importlib.util.spec_from_file_location('haike_motion_delivery_runtime',
        core.safe_path(root, 'portable/motion_delivery_runtime.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def public_components(root):
    """Only the reviewed MIT Snapcn tree and public index, never TalkCraft code.

    Package/dependency metadata stays behind the existing migration gate. No
    assets, node_modules, fonts or runtime binaries are picked by this walk.
    """
    names = {name for name in core.PUBLIC_COMPONENT_INDEXES | core.PUBLIC_COMPONENT_LICENSES
             if core.safe_path(root, name).is_file()}
    folder = core.safe_path(root, 'Haike_video/motion-components/snapcn')
    if folder.is_dir():
        for path in folder.rglob('*'):
            if path.is_file():
                name = path.relative_to(root).as_posix()
                if core.is_program_path(name):
                    core.safe_path(root, name)
                    names.add(name)
    return names


def inventory(root):
    """Require the complete candidate; partial concurrent authoring cannot ship."""
    root = Path(root).resolve()
    if core.safe_path(root, 'Haike_video/config/motion-preferred-production.json').is_file():
        return current_delivery(root).inventory(root)
    names = set(TRANSPORT) | public_components(root)
    for name in [*GROUPS, 'contract.schema.json']:
        require(core.safe_path(root, PREFIX + name).is_file(), '18套动效合同尚未齐全：' + PREFIX + name)
    validate_documents(root)
    registries, identities, rows = {}, [], []
    seen = set()
    for name, count in GROUPS.items():
        path = core.safe_path(root, PREFIX + name)
        require(path.is_file(), '18套动效合同尚未齐全：' + PREFIX + name)
        value = core._read(path)
        require(value.get('schema') == 'haike.motion-replay-registry/1'
                and isinstance(value.get('templates'), list) and count <= len(value['templates']) <= 100,
                '动效合同分组数量或格式无效：' + name)
        registries[PREFIX + name] = core.digest(path); names.add(PREFIX + name)
        for row in value['templates']:
            identity = row.get('template_id')
            version=row.get('version')
            require(isinstance(identity, str) and identity and (identity,version) not in seen,
                    '动效合同身份重复或缺失')
            seen.add((identity,version))
            require(all(k in row for k in ['version', 'family', 'renderer', 'sources', 'objects', 'actions',
                                           'timeline', 'slots', 'capabilities', 'validation']),
                    '动效合同缺少v1必需字段：' + identity)
            renderer = row['renderer']
            require(isinstance(renderer, dict) and renderer.get('kind') in {'project', 'native_package'}
                    and renderer.get('execution') in {'supported', 'inspect_only', 'needs_adaptation'}
                    and renderer.get('entrypoint') and renderer.get('adapter'), '动效执行边界无效：' + identity)
            objects = {o['id'] for o in row['objects']}
            actions = set()
            for action in row['actions']:
                require(isinstance(action, dict) and action.get('id') and action['id'] not in actions
                        and all(k in action for k in ['version', 'implementation', 'objects', 'parameters', 'phases'])
                        and set(action['objects']) <= objects, '动效动作未绑定：' + identity)
                actions.add(action['id'])
            require(isinstance(row['timeline'], dict) and row['timeline'].get('mode') in {'source_locked', 'semantic', 'native'}
                    and all(e.get('action_id') in actions for e in row['timeline'].get('events', [])),
                    '动效时间线引用未知动作：' + identity)
            for source in row['sources']:
                require(isinstance(source, dict) and isinstance(source.get('path'), str)
                        and isinstance(source.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', source['sha256']),
                        '动效源码身份无效：' + identity)
                # Validate relative paths even when this is a private original.
                core._parts(source['path'])
                if core.is_program_path(source['path']):
                    file = core.safe_path(root, source['path'])
                    require(file.is_file() and core.digest(file) == source['sha256'],
                            '动效源码缺失或改变：' + source['path'])
                    names.add(source['path'])
            identities.append({'template_id': identity, 'version': row['version'],
                               'registry': PREFIX + name, 'execution': renderer['execution']})
            rows.append(row)
    for name in names:
        require(core.is_program_path(name) and core.safe_path(root, name).is_file(),
                '动效公共入口缺失或禁止分发：' + name)
    expectation = {'schema': SCHEMA, 'registries': registries, 'templates': identities}
    core.validate_motion_replay(expectation)
    return expectation, names, rows


def validate_documents(root):
    # Use the owning v1 schema/reference validator as well as our stdlib byte
    # inventory. Never run prepare(), a renderer or a registry-selected import.
    spec = importlib.util.spec_from_file_location('haike_installed_replay_contract',
                                                core.safe_path(root, 'Haike_video/backlot/motion_replay.py'))
    module = importlib.util.module_from_spec(spec)
    # A standalone 1027 bootstrap runs bundled Python before the Backlot venv
    # is on its import path. Inspect the verified installed dependencies, never
    # a developer/global fallback or a registry-selected module path.
    previous=list(sys.path)
    try:
        site=core.safe_path(root,'Haike_video/.venv/Lib/site-packages')
        if site.is_dir():sys.path.insert(0,str(site))
        spec.loader.exec_module(module)
        for name in GROUPS:
            module.validate_registry(core._read(core.safe_path(root, PREFIX + name)),
                                     schema_path=core.safe_path(root, PREFIX + 'contract.schema.json'))
    finally:
        sys.path[:]=previous


def package_readiness(root, row):
    if row['renderer']['kind'] != 'native_package':
        return 'not_required'
    identity = row.get('package_identity', {})
    digest = identity.get('sha256')
    originals = [s for s in row['sources'] if s['path'].endswith('.motion')]
    if originals and all(core.safe_path(root, s['path']).is_file()
                         and core.digest(core.safe_path(root, s['path'])) == s['sha256'] for s in originals):
        return 'bytes_match_official_verification_required'
    database = core.safe_path(root, '.local/motiongit/registry.sqlite3')
    if not database.is_file() or not digest:
        return 'user_package_required'
    try:
        # Read only; never import a personalized package, print its record or
        # trust an arbitrary absolute package path from local metadata.
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='packages' AND type='table'").fetchone():
                return 'user_package_required'
            for data, in db.execute('SELECT data FROM packages LIMIT 10000'):
                value = core._json(data.encode('utf-8'))
                package_id = value.get('id')
                if (value.get('sha256') != digest or value.get('template_id') != identity.get('template_id')
                        or value.get('version') != identity.get('version') or not isinstance(package_id, str)
                        or not re.fullmatch('mg-[0-9a-f]{24}', package_id)):
                    continue
                package = core.safe_path(root, '.local/motiongit/packages/' + package_id + '/original.motion')
                if package.is_file() and core.digest(package) == digest:
                    return 'bytes_match_official_verification_required'
                return 'registered_package_missing_or_changed'
    except (sqlite3.Error, OSError, ValueError, TypeError, AttributeError):
        return 'local_registry_unreadable'
    return 'user_package_required'


def helper_readiness(root, row):
    if row['renderer']['kind'] != 'native_package':
        return 'not_required'
    helper = row.get('package_identity', {}).get('helper')
    if not isinstance(helper, dict):
        return 'not_declared'
    version, digest = helper.get('version'), helper.get('sha256')
    require(isinstance(version, str) and re.fullmatch(r'[0-9A-Za-z.+-]{1,80}', version)
            and isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest), '原生工具身份无效')
    path = core.safe_path(root, '.local/motiongit/tools/' + version + '/motion.mjs')
    return 'missing' if not path.is_file() else 'verified_bytes' if core.digest(path) == digest else 'changed'


def private_component_readiness(root, row):
    # This is the one real private import in template 5's owning build.cjs and
    # adapter verify_release(); a TalkCraft alias elsewhere is not a dependency.
    if row['template_id'] != 'field-notes-v2':
        return 'not_required'
    if row.get('version') == '2.1.0':
        # The HD producer owns field-notes-video-v1/Scene.tsx, whose imports
        # are public React/Remotion. It does not consume the old private grid.
        return 'not_required'
    if row.get('version') != '2.0.0':
        return 'not_evaluated_for_this_version'
    config = core.safe_path(root, '.local/talkcraft-integration/state/config.json')
    if not config.is_file():
        return 'missing_private_component'
    try:
        upstream = Path(core._read(config)['upstream']).resolve(strict=True)
        source = upstream / 'template/cards/grid-to-hero.tsx'
        if not source.is_file() or not source.resolve().is_relative_to(upstream):
            return 'missing_private_component'
        plan = core._read(core.safe_path(root, 'Haike_video/templates/field-notes-v2/selection.json'))
        choices = [s for scene in plan['scenes'] for s in scene['selections'] if s['id'] == 'talkcraft:grid-to-hero']
        require(choices, '私有组件缺少精确来源身份')
        return ('bytes_match_permission_not_evaluated' if all(s['source_sha256'] == core.digest(source) for s in choices)
                else 'changed_private_component')
    except (OSError, ValueError, KeyError, TypeError):
        return 'private_binding_unreadable'


def report(root, expected):
    if expected.get('schema') == 'haike.motion-replay-delivery/2':
        return current_delivery(root).report(root, expected)
    actual, names, rows = inventory(root)
    require(actual == expected, '安装的18套动效合同与发行身份不一致')
    templates = []
    for row in rows:
        # A hash match establishes possession of these bytes, never the right
        # to distribute them or current official signature verification.
        local_sources = [s for s in row['sources'] if not core.is_program_path(s['path'])]
        local_status = 'not_required'
        if local_sources:
            local_status = ('bytes_match' if all(core.safe_path(root, s['path']).is_file()
                            and core.digest(core.safe_path(root, s['path'])) == s['sha256'] for s in local_sources)
                            else 'user_local_source_required')
        templates.append({'template_id': row['template_id'], 'version': row['version'],
                          'contract': 'verified', 'execution': row['renderer']['execution'],
                          'execution_scope': row.get('execution_scope', row['renderer'].get('scope',
                              '仅程序合同检查；按原协议及其门禁执行')),
                          'routes': row.get('routes', []),
                          'original_package': package_readiness(root, row), 'episode_inputs': 'user-provided',
                          'native_helper': helper_readiness(root, row),
                          'private_components': private_component_readiness(root, row),
                          'local_source_dependencies': local_status,
                          'required_slots': [s['id'] for s in row['slots'] if s['required']],
                          'permissions': 'not_evaluated_by_program_update', 'production_ready': False,
                          'validation': row['validation'], 'capabilities': row['capabilities']})
    return {'status': 'verified', 'scope': 'public-contracts-and-source-identities-only',
            'template_count': len({r['template_id'] for r in templates}), 'version_count': len(templates), 'templates': templates,
            'render_selftest': 'not-performed', 'episode_review': False,
            'private_originals_distributed': False, 'public_files': len(names)}
