"""Standard-library delivery identity shared by build and transactional update.

Only public program paths are accepted. This verifies installed bytes; runtime
rendering and a user's personal-envelope/media readiness are separate checks.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re

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
    'portable/audio_update_guard.py', 'portable/queue_update_guard.py',
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
    return core.is_program_path(name) or name in {
        'Haike_video/remotion-composer/package.json',
        'Haike_video/remotion-composer/package-lock.json',
    }


def _read(path):
    path = core.native_path(path)
    require(path.is_file() and path.stat().st_size <= core.MAX_MANIFEST_BYTES, '模板交付清单缺失或过大')
    return core._json(path.read_bytes())


def _fingerprint(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def expectation(value, digest):
    return {'schema': SCHEMA, 'sha256': digest, 'presets': value['presets']}


def validate_expectation(value):
    return core.validate_template_capability(value)


def build(root, *, frontend_root=None, generated_files=None):
    """Build from a clean stage after its exact frontend has been compiled."""
    root = Path(root).resolve()
    manifest = _read(core.safe_path(root, MANIFEST))
    require(manifest.get('schema') == 'haike.motion-presets/1' and isinstance(manifest.get('presets'), list),
            '正式模板清单格式无效')
    generated_files = generated_files or {}
    names = {MANIFEST, *TRANSPORT, *generated_files}
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
        require(core.native_path(path).is_file(), '模板执行文件缺失：' + name)
        files[name] = core.digest(path)
    value = {'schema': SCHEMA, 'sha256': _fingerprint(files), 'files': files, 'presets': presets}
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
        require(core.native_path(path).is_file() and core.digest(path) == expected['sha256'],
                '正式模板交付清单缺失或不匹配，请保留备份并修复更新')
    value = _read(path)
    require(value.get('schema') == SCHEMA and isinstance(value.get('files'), dict)
            and 1 <= len(value['files']) <= core.MAX_FILES
            and value.get('sha256') == _fingerprint(value['files']), '模板交付文件身份无效')
    validate_expectation(expectation(value, core.digest(path)))
    if expected is not None:
        require(value['presets'] == expected['presets'], '安装的正式预设版本与本次发行不一致')
    require(all(name in value['files'] for name in [MANIFEST, *TRANSPORT]), '模板交付缺少必需的公共入口')
    for name, digest in value['files'].items():
        require(is_delivery_path(name) and isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest),
                '模板交付包含无效路径或摘要')
        file = core.safe_path(root, name)
        require(core.native_path(file).is_file() and core.digest(file) == digest, '模板执行文件缺失或已改变：' + name)
    runtime = {'status': 'not-declared'}
    if 'Haike_video/templates/motion-presets/runtime.json' in value['files']:
        spec = importlib.util.spec_from_file_location('haike_installed_motion_runtime', Path(root) / 'portable/motion_runtime.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        runtime = module.verify(root)
    spec = importlib.util.spec_from_file_location('haike_installed_template_selftest', Path(root) / 'portable/template_selftest.py')
    selftest = importlib.util.module_from_spec(spec); spec.loader.exec_module(selftest)
    receipt = selftest.recorded(root, core.digest(path))
    return {'status': 'verified', 'sha256': core.digest(path), 'presets': value['presets'],
            'verified_files': len(value['files']), 'runtimes': runtime,
            'runtime_selftest': receipt['status'], 'selftest': receipt, 'episode_inputs': 'user-provided'}


def selftest(root):
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
    args = parser.parse_args()
    print(json.dumps((selftest if args.selftest else verify)(args.root.resolve()), ensure_ascii=False))
