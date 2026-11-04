"""Pinned sidecar runtimes for the two exact, public native protocols.

No personal envelope, episode data, account configuration or protected template
core is included. Generated venv paths belong to the destination installation.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import re

try:
    from . import app_update as core
except ImportError:
    try:
        import release_core as core
    except ImportError:
        _spec = importlib.util.spec_from_file_location('haike_runtime_core', Path(__file__).with_name('app_update.py'))
        core = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(core)

PATH = 'Haike_video/templates/motion-presets/runtime.json'
SCHEMA = 'haike.motion-runtimes/1'
HELPER = '.local/motiongit/tools/1.0.0-rc.54/motion.mjs'
HELPER_SHA = '90f00d37cafdc9a204babce24b86b683c097c8a60b74b862b28cfe1a081b2a3f'
HELPER_BYTES = 852945
PROFILES = {
    'paper-rc54-v1': {'template_id': 'template-02-expanded', 'version': '2.7.21-alpha.5',
        'workflow': 'motion-kit', 'cache': '.local/md/paper-rc54-v1-kit',
        'cache_argument': '.local/md/paper-rc54-v1', 'venv': '.venv', 'imports': ['numpy']},
    'knowledge-rc54-v1': {'template_id': 'knowledge-explainer-sketchnote', 'version': '2.7.3',
        'workflow': 'native', 'cache': '.local/md/knowledge-rc54-v1',
        'cache_argument': '.local/md/knowledge-rc54-v1', 'venv': 'audio-venv', 'imports': ['numpy', 'scipy.signal']},
}


def require(ok, message):
    if not ok:
        raise core.UpdateError(message)


def public_resource(name):
    """A narrowly scoped sidecar, never general permission to overwrite .local."""
    core._parts(name)
    if name == HELPER:
        return True
    return any(name.startswith(p['cache'] + '/') and name.casefold() != (p['cache'] + '/' + p['venv'] + '/pyvenv.cfg').casefold()
               for p in PROFILES.values())


def validate(value):
    require(isinstance(value, dict) and value.get('schema') == SCHEMA
            and isinstance(value.get('profiles'), list) and len(value['profiles']) == len(PROFILES),
            '模板运行依赖清单无效')
    seen = set()
    for row in value['profiles']:
        require(isinstance(row, dict) and row.get('id') in PROFILES and row['id'] not in seen,
                '模板运行依赖身份无效或重复')
        expected = PROFILES[row['id']]
        require(all(row.get(k) == v for k, v in expected.items()) and row.get('helper_sha256') == HELPER_SHA,
                '模板运行依赖版本或位置不匹配')
        files = row.get('files')
        require(isinstance(files, dict) and 1 <= len(files) <= 20000, '模板运行依赖文件清单为空或过大')
        folded = set()
        for name, digest in files.items():
            core._parts(name)
            require(name.casefold() not in folded and isinstance(digest, str)
                    and re.fullmatch('[0-9a-f]{64}', digest) and name.casefold() != (row['venv'] + '/pyvenv.cfg').casefold(),
                    '模板运行依赖文件身份无效')
            folded.add(name.casefold())
        require(row['venv'] + '/Scripts/python.exe' in files, '模板运行依赖缺少本机Python入口')
        if row['workflow'] == 'motion-kit':
            require({'package.json', 'package-lock.json', 'kit-dependencies.json'} <= set(files),
                    '组件运行依赖缺少锁文件')
        seen.add(row['id'])
    return value


def read(root):
    path = core.safe_path(root, PATH)
    if not path.exists():
        return None
    return validate(core._read(path))


def build_profile(identity, source):
    require(identity in PROFILES, '运行依赖方案未登记')
    source = Path(source).resolve(strict=True)
    require(source.is_dir(), '运行依赖来源不是目录')
    row = {'id': identity, **PROFILES[identity], 'helper_sha256': HELPER_SHA}
    sources = []
    for file in sorted(source.rglob('*')):
        relative = file.relative_to(source).as_posix()
        require(not file.is_symlink() and not (hasattr(file, 'is_junction') and file.is_junction()),
                '运行依赖来源不能包含目录联接或符号链接')
        if not file.is_file() or '__pycache__' in file.parts or '.cache' in file.parts:
            continue
        if file.suffix.lower() in {'.pyc', '.pyo'} or file.name == 'pyvenv.cfg':
            continue
        # pip/console .exe launchers embed their old absolute interpreter path.
        # Execution uses python -m; retain only generic venv launchers and DLLs.
        if '/Scripts/' in relative and file.name not in {'python.exe', 'pythonw.exe'} and file.suffix.lower() != '.dll':
            continue
        require(public_resource(row['cache'] + '/' + relative), '运行依赖来源包含未允许的位置')
        sources.append((row['cache'] + '/' + relative, file))
    def hashed(item):
        name, file = item
        return name.removeprefix(row['cache'] + '/'), core.digest(file)
    with ThreadPoolExecutor(max_workers=8) as pool:
        row['files'] = dict(pool.map(hashed, sources))
    return row, sources


def configuration_writes(root, value):
    """Return transaction writes; never overwrite a foreign existing venv cfg."""
    validate(value); root = Path(root).resolve()
    result = []
    for row in value['profiles']:
        name = row['cache'] + '/' + row['venv'] + '/pyvenv.cfg'
        marker = '# haike-motion-runtime=' + row['id']
        runtime = core.safe_path(root, 'runtime/python')
        content = (marker + f'\nhome = {runtime}\ninclude-system-site-packages = false\n'
                   f'executable = {runtime / "python.exe"}\n').encode('utf-8')
        path = core.safe_path(root, name)
        if path.exists():
            require(path.is_file() and path.stat().st_size < 4096, '模板运行环境配置异常')
            old = path.read_bytes()
            require(old == content or old.decode('utf-8-sig').splitlines()[0:1] == [marker],
                    '模板依赖目录已有其他环境配置，已停止保留：' + row['id'])
        result.append((name, content))
    return result


def verify(root, value=None, *, configuration=True):
    root = Path(root).resolve(); value = read(root) if value is None else validate(value)
    if value is None:
        return {'status': 'not-declared', 'profiles': []}
    helper = core.safe_path(root, HELPER)
    require(helper.is_file() and helper.stat().st_size == HELPER_BYTES and core.digest(helper) == HELPER_SHA,
            '原生模板rc.54工具缺失或身份不符')
    def checked(item):
        name, digest = item
        path = core.safe_path(root, name)
        require(path.is_file() and core.digest(path) == digest, '模板运行依赖缺失或已改变：' + name)
    files = [(r['cache'] + '/' + name, digest) for r in value['profiles'] for name, digest in r['files'].items()]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(checked, files))
    if configuration:
        for name, content in configuration_writes(root, value):
            path = core.safe_path(root, name)
            require(path.is_file() and path.read_bytes() == content,
                    '模板Python环境尚未绑定当前安装位置，请用本副本启动器修复')
    return {'status': 'verified', 'profiles': [r['id'] for r in value['profiles']], 'verified_files': len(files)}


def relocate(root):
    """Only installation-owned, pinned environments may be rebound after a move."""
    value = read(root)
    if value is None:
        return {'status': 'not-declared'}
    verify(root, value, configuration=False)
    count = 0
    for name, content in configuration_writes(root, value):
        path = core.safe_path(root, name)
        if not path.is_file() or path.read_bytes() != content:
            core._atomic_write(path, content); count += 1
    return {'status': 'bound', 'configurations_updated': count}


def resolve(root, package, workflow):
    value = read(root)
    if value is None:
        return None
    for row in value['profiles']:
        if (row['template_id'], row['version'], row['workflow']) == (
                package.get('template_id'), package.get('version'), workflow):
            require(package.get('helper_version') == '1.0.0-rc.54', '模板工具版本与运行依赖不匹配')
            verify(root, value)
            return {**row, 'cache_path': str(core.safe_path(root, row['cache'])),
                    'cache_argument_path': str(core.safe_path(root, row['cache_argument']))}
    return None
