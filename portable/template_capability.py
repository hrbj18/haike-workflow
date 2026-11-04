"""Delivery identity shared by build and transactional update.

Only public program paths are accepted. This verifies installed bytes; runtime
rendering and a user's personal-envelope/media readiness are separate checks.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
from functools import lru_cache

try:
    from . import app_update as core
except ImportError:
    import importlib.util
    _spec = importlib.util.spec_from_file_location('haike_capability_core', Path(__file__).with_name('app_update.py'))
    core = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(core)

PATH = 'Haike_video/templates/motion-presets/delivery.json'
MANIFEST = 'Haike_video/templates/motion-presets/manifest.json'
SCHEMA = 'haike.motion-capability/1'
TRANSPORT = [
    'Haike_video/backlot/studio_motion_presets.py', 'Haike_video/backlot/studio_motiongit.py',
    'Haike_video/backlot/studio_motiongit_api.py', 'Haike_video/scripts/motiongit.py',
    'portable/template_capability.py', 'portable/motion_runtime.py', 'portable/app_update.py',
    'portable/motion_delivery_runtime.py',
    'portable/audio_update_guard.py',
    'portable/schema_runtime.py',
    'portable/template_selftest.py', 'Haike_video/remotion-composer/runtime-selftest.mjs',
    'Haike_video/remotion-composer/src/RuntimeSelftest.tsx',
    'Haike_video/backlot/studio_motion_runtime.py',
    'Haike_video/backlot/production_queue.py', 'Haike_video/backlot/production_queue_worker.py',
    'Haike_video/tools/video/video_compose.py', 'Haike_video/remotion-composer/package.json',
    'Haike_video/remotion-composer/package-lock.json',
    'prototypes/haike-avatar-generator/src/MotionGitLibrary.jsx',
]


def require(ok, message):
    if not ok:
        raise core.UpdateError(message)


def is_delivery_path(name):
    # Dependency locks are verified bytes, but remain forbidden as ordinary
    # program-patch payloads. Only the controlled resource migration changes them.
    return current_module().program_path(name) or name in {
        'Haike_video/remotion-composer/package.json',
        'Haike_video/remotion-composer/package-lock.json',
    }


def _read(path):
    require(path.is_file() and path.stat().st_size <= core.MAX_MANIFEST_BYTES, '模板交付清单缺失或过大')
    return core._json(path.read_bytes())


def _fingerprint(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def expectation(value, digest):
    replay = value.get('motion_replay')
    key = 'motion_upgrade' if isinstance(replay, dict) and replay.get('schema') == 'haike.motion-replay-delivery/2' else 'motion_replay'
    return {'schema': SCHEMA, 'sha256': digest, 'presets': value['presets'],
            **({key: replay} if replay is not None else {})}


@lru_cache(maxsize=32)
def current_module(root=None):
    path = Path(root)/'portable/motion_delivery_runtime.py' if root is not None else Path(__file__).with_name('motion_delivery_runtime.py')
    spec = importlib.util.spec_from_file_location('haike_current_motion_delivery', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def replay_module(root):
    # The detached update worker freezes this verifier before replacing files.
    # Replay inspection must use the hash-checked target's module afterwards.
    spec = importlib.util.spec_from_file_location('haike_replay_delivery', core.safe_path(root, 'portable/motion_replay_capability.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def validate_expectation(value):
    core.validate_template_capability(value)
    if 'motion_upgrade' in value:
        current_module().validate_expectation(value['motion_upgrade'])
    return value


def build(root, *, frontend_root=None, generated_files=None):
    """Build from a clean stage after its exact frontend has been compiled."""
    root = Path(root).resolve()
    manifest = _read(core.safe_path(root, MANIFEST))
    require(manifest.get('schema') == 'haike.motion-presets/1' and isinstance(manifest.get('presets'), list),
            '正式模板清单格式无效')
    generated_files = generated_files or {}
    names = {MANIFEST, *TRANSPORT, *generated_files}
    replay = None
    if (root / 'portable/motion_replay_capability.py').is_file():
        module = replay_module(root)
        if module.declared(root):
            replay, replay_files, _ = module.inventory(root)
            missing_transport = set(module.TRANSPORT) - set(replay_files)
            require(not missing_transport, '动效复刻公共入口未绑定交付身份：' + ', '.join(sorted(missing_transport)))
            names.update(replay_files)
    presets = []
    for row in manifest['presets']:
        recipe = row.get('recipe')
        require(isinstance(recipe, str) and re.fullmatch(r'[a-z0-9-]+\.json', recipe), '预设文件路径无效')
        name = 'Haike_video/templates/motion-presets/' + recipe
        require(core.digest(core.safe_path(root, name)) == row.get('sha256'), '正式预设与版本清单不一致')
        names.add(name); names.update(row['engine_files'])
        presets.append({k: row[k] for k in ['id', 'version', 'sha256', 'protocol', 'requires_package']})
    # Bind the entry and public program assets, including lazy chunks. Private
    # preview bitmaps from old local deliveries stay outside public code patches.
    frontend_root = Path(frontend_root).resolve() if frontend_root is not None else root
    ui = core.safe_path(frontend_root, 'Haike_video/backlot/ui/avatar-generator')
    require((ui / 'index.html').is_file(), '请先构建本次前端再生成模板交付清单')
    ui_names = {p.relative_to(frontend_root).as_posix() for p in ui.rglob('*')
                if p.is_file() and core.is_program_path(p.relative_to(frontend_root).as_posix())}
    names.update(ui_names)
    files = {}
    for name in sorted(names):
        require(is_delivery_path(name), '模板交付不能包含私人或运行数据：' + name)
        path = Path(generated_files[name]) if name in generated_files else core.safe_path(frontend_root if name in ui_names else root, name)
        require(path.is_file(), '模板执行文件缺失：' + name)
        files[name] = core.digest(path)
    value = {'schema': SCHEMA, 'sha256': _fingerprint(files), 'files': files, 'presets': presets}
    if replay is not None:
        value['motion_replay'] = replay
    validate_expectation(expectation(value, '0' * 64))
    return value


def verify(root, expected=None):
    """Missing original envelopes are not a failure of public code delivery."""
    root = Path(root).resolve()
    if expected is None:
        release = core.safe_path(root, 'RELEASE.json')
        expected = _read(release).get('template_capability') if release.is_file() else None
    path = core.safe_path(root, PATH)
    if expected is None and not path.exists():
        return {'status': 'not-declared', 'presets': []}
    if expected is not None:
        validate_expectation(expected)
        require(path.is_file() and core.digest(path) == expected['sha256'],
                '正式模板交付清单缺失或不匹配，请保留备份并修复更新')
    value = _read(path)
    require(value.get('schema') == SCHEMA and isinstance(value.get('files'), dict)
            and 1 <= len(value['files']) <= core.MAX_FILES
            and value.get('sha256') == _fingerprint(value['files']), '模板交付文件身份无效')
    validate_expectation(expectation(value, core.digest(path)))
    if expected is not None:
        require(value['presets'] == expected['presets'], '安装的正式预设版本与本次发行不一致')
        require(value.get('motion_replay') == expected.get('motion_upgrade', expected.get('motion_replay')), '安装的动效复刻合同与本次发行不一致')
    require(all(name in value['files'] for name in [MANIFEST, *TRANSPORT]), '模板交付缺少必需的公共入口')
    for name, digest in value['files'].items():
        require(is_delivery_path(name) and isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest),
                '模板交付包含无效路径或摘要')
        file = core.safe_path(root, name)
        require(file.is_file() and core.digest(file) == digest, '模板执行文件缺失或已改变：' + name)
    runtime = {'status': 'not-declared'}
    schema_runtime = {'status': 'not-declared'}
    current18 = value.get('motion_replay', {}).get('schema') == 'haike.motion-replay-delivery/2'
    if not current18 and 'Haike_video/templates/motion-presets/schema-runtime.json' in value['files']:
        spec = importlib.util.spec_from_file_location('haike_installed_schema_runtime', core.safe_path(root, 'portable/schema_runtime.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        schema_runtime = module.verify(root)
    if not current18 and 'Haike_video/templates/motion-presets/runtime.json' in value['files']:
        spec = importlib.util.spec_from_file_location('haike_installed_motion_runtime', Path(root) / 'portable/motion_runtime.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        runtime = module.verify(root)
    spec = importlib.util.spec_from_file_location('haike_installed_template_selftest', Path(root) / 'portable/template_selftest.py')
    selftest = importlib.util.module_from_spec(spec); spec.loader.exec_module(selftest)
    receipt = selftest.recorded(root, core.digest(path))
    replay = {'status': 'not-declared', 'templates': []}
    if 'motion_replay' in value:
        require('portable/motion_replay_capability.py' in value['files'], '动效复刻交付缺少能力检查入口')
        module = replay_module(root)
        require(all(name in value['files'] for name in module.TRANSPORT), '动效复刻公共入口未绑定交付身份')
        replay = module.report(root, value['motion_replay'])
        require(replay['status'] == 'verified', '18套必需组件资源缺失或改变：' +
                (replay.get('resource_issues') or [{'path':'unknown'}])[0]['path'])
    return {'status': 'verified', 'sha256': core.digest(path), 'presets': value['presets'],
            'verified_files': len(value['files']), 'runtimes': runtime,
            'schema_runtime': schema_runtime,
            'runtime_selftest': receipt['status'], 'selftest': receipt, 'episode_inputs': 'user-provided',
            'motion_replay': replay}


def selftest(root):
    if core.safe_path(Path(root), 'Haike_video/config/motion-preferred-production.json').is_file():
        result = verify(root)
        component = current_module(root).component_selftest(root)
        return {**result, 'component_selftest': component, 'runtime_selftest': 'component-passed-media-not-performed'}
    result = verify(root)
    if result['status'] != 'verified' or result['runtime_selftest'] == 'passed':
        return result
    spec = importlib.util.spec_from_file_location('haike_template_selftest_runner', Path(root) / 'portable/template_selftest.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    runtime = core.safe_path(root, 'Haike_video/templates/motion-presets/runtime.json')
    receipt = module.run(root, result['sha256'], core._read(runtime) if runtime.is_file() else None)
    return {**result, 'runtime_selftest': receipt['status'], 'selftest': receipt}


def write(root):
    value = build(root)
    data = core.json_bytes(value)
    path = core.safe_path(root, PATH)
    core._atomic_write(path, data)
    return expectation(value, hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--component-selftest', action='store_true', help='仅实际组件import/计算；不渲染或调用provider')
    parser.add_argument('--diagnostic-plan', action='store_true', help='给D输出目标内固定调用与工具映射')
    parser.add_argument('--write-capability', action='store_true', help='离线stage生成delivery.json并返回release.template_capability字段')
    parser.add_argument('--runtime-bindings', type=Path, help='明确声明并逐文件核SHA的系统/只读运行时映射')
    args = parser.parse_args()
    bindings = _read(args.runtime_bindings) if args.runtime_bindings else None
    if args.write_capability:
        result = write(args.root.resolve())
    elif args.component_selftest or args.diagnostic_plan:
        checker = current_module(args.root.resolve())
        result = (checker.component_selftest if args.component_selftest else checker.diagnostic_plan)(
            args.root.resolve(), runtime_bindings=bindings)
    else:
        result = (selftest if args.selftest else verify)(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False))
