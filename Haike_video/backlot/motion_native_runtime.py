"""Native tools and installed browsers behind the inherited renderer interface.

Native requests retain a separate platform identity. Old Windows requests and
their binary hashes are neither rewritten nor executed on another platform.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
COMPOSER = ROOT / 'Haike_video/remotion-composer'
HTML = ROOT / '_distribution-tools/motion-html'
SPEC = ROOT / '_distribution-tools/macos-runtime.json'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text('utf8'))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def architecture():
    if sys.platform == 'win32':
        return 'windows-x64'
    arch = platform.machine().lower()
    require(arch in {'arm64', 'x86_64'}, 'Mac动效只接受原生Apple Silicon或Intel环境')
    return arch


def root():
    if sys.platform == 'win32':
        return ROOT / 'runtime'
    return ROOT / 'runtime/macos' / architecture()


def binary(kind):
    runtime = root()
    if kind == 'browser':
        from portable.system_browser import resolve
        installed = resolve(required=False)
        if installed:
            return installed
    if sys.platform == 'win32':
        if kind == 'node':
            matches = [runtime / 'node/node.exe', Path(shutil.which('node') or '__missing_node__')]
        elif kind in {'ffmpeg', 'ffprobe'}:
            matches = [runtime / 'ffmpeg/bin' / (kind + '.exe'), runtime / 'ffmpeg' / (kind + '.exe')]
        else:
            matches = []
        found = next((p for p in matches if p.is_file()), None)
        require(found is not None, '本机媒体工具尚未准备：' + kind)
        return found.resolve()
    if kind == 'node':
        matches = list((runtime / 'node').glob('node-*/bin/node'))
    elif kind == 'browser':
        matches = list((runtime / 'playwright').glob('chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell'))
    elif kind in {'ffmpeg', 'ffprobe'}:
        matches = [runtime / 'ffmpeg/bin' / kind]
    else:
        raise ValueError('未登记的Mac动效工具')
    require(len(matches) == 1 and matches[0].is_file(), '原生Mac动效工具尚未准备：' + kind)
    return matches[0].resolve()


def tools():
    return {'tools': {name: {'path': str(binary(name))} for name in ('node', 'browser', 'ffmpeg', 'ffprobe')}}


def identity():
    from backlot.motion_platform import MANIFEST, verify
    document = verify()
    installed = installation_path()
    require(installed.is_file(), 'Mac动效原生依赖绑定缺失；请重新运行安装检查')
    data = read(installed)
    require(data.get('arch') == architecture() and data.get('runtime_spec_sha256') == sha(runtime_spec()), '运行时平台或锁定来源改变')
    for row in data['files']:
        path = ROOT / row['path']
        require(path.resolve().is_relative_to(ROOT) and path.is_file() and sha(path) == row['sha256'], 'Mac动效原生工具或依赖文件改变')
    return {'id': 'haike.motion-native-adapter/1', 'version': document['adapter_version'], 'arch': architecture(),
            'derivation_sha256': sha(MANIFEST), 'platform_router_sha256': sha(ROOT / 'Haike_video/backlot/motion_platform.py'),
            'runtime_spec_sha256': sha(runtime_spec()), 'installation_identity_sha256': sha(installed),
            'executables': {name: sha(binary(name)) for name in ('node', 'browser', 'ffmpeg', 'ffprobe')}}


def environment(tool_root, dependency_root, ffmpeg_root=None, *, template=None, dark=False):
    require(Path(tool_root).resolve() == root().resolve(), 'Mac动效工具路径须属于本副本固定原生运行时')
    require(ffmpeg_root is None or Path(ffmpeg_root).resolve() == (root() / 'ffmpeg').resolve(), 'Mac FFmpeg路径与原生运行时不符')
    expected = COMPOSER if dark else HTML
    require(Path(dependency_root).resolve() == expected.resolve(), 'Mac动效依赖路径与固定制作路线不符')
    # Pure JS/fonts retain the original independently recorded byte hashes.
    if not dark:
        for item in read(Path(template) / 'DEPENDENCIES.json')['components']:
            rows = [(HTML / 'node_modules' / item['component'] / r['path'], r['sha256']) for r in item['files']] if 'files' in item else [(HTML / 'fonts' / item['component'], item['sha256'])]
            for path, checksum in rows:
                require(path.resolve().is_relative_to(HTML) and path.is_file() and not path.is_symlink() and sha(path) == checksum, 'Mac公开HTML依赖或原字体摘要变化')
    bound = identity()
    rows = [{'logical_path': 'native/' + key, 'sha256': value} for key, value in bound['executables'].items()]
    rows.extend({'logical_path': 'native/' + key, 'sha256': bound[key]} for key in ('derivation_sha256', 'runtime_spec_sha256', 'installation_identity_sha256', 'platform_router_sha256'))
    return (dark_descriptor() if dark else tools()), rows


def dark_descriptor(original=None):
    if original is None:
        from backlot.motion_public_dark_remotion_v2 import descriptor
        original = descriptor()
    result = deepcopy(original)
    result['executables'] = {'node': str(binary('node')), 'browser': str(binary('browser')),
                             'cli': 'node_modules/@remotion/cli/remotion-cli.js'}
    result['native_adapter'] = 'haike.motion-native-adapter/1'
    return result


def link_dependencies(generated, dependency_root):
    generated, dependency_root = Path(generated).resolve(), Path(dependency_root).resolve()
    require(any(generated.is_relative_to((ROOT / base).resolve()) for base in ('.local', 'Haike_video/projects'))
            and dependency_root == COMPOSER.resolve(), '原renderer工程或固定依赖目录无效')
    target = generated / 'node_modules'
    require(not target.exists() and not target.is_symlink(), '保留已有依赖映射，不能覆盖')
    try:
        target.symlink_to(COMPOSER / 'node_modules', target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            raise
        subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(target), str(COMPOSER / 'node_modules')],
                       check=True, capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def render_script(canonical):
    from backlot.motion_platform import NATIVE_RENDERERS, verify
    verify()
    relative = Path(canonical).resolve().relative_to(ROOT).as_posix()
    require(relative in NATIVE_RENDERERS, '未登记的原生Mac编码适配器')
    return ROOT / NATIVE_RENDERERS[relative]


def source_files():
    """Freeze the separate native implementation and installed tool binding."""
    from backlot.motion_platform import MANIFEST, verify
    document = verify()
    identity()
    paths = [MANIFEST, Path(__file__), ROOT / 'Haike_video/backlot/motion_platform.py',
             ROOT / 'scripts/build-native-motion.py', installation_path()]
    paths += [ROOT / row['derived'] for row in document['modules'] + document['renderers']]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}


def bind_installation():
    """Installer calls after npm integrity checks; all subsequent runs rehash it."""
    rows = []
    for base in (COMPOSER / 'node_modules', HTML / 'node_modules', HTML / 'fonts'):
        require(base.is_dir(), 'Mac动效依赖尚未安装')
        for path in sorted(base.rglob('*')):
            # npm .bin is a generated symlink; the actual target is included.
            if path.is_file() and not path.is_symlink() and '.cache' not in path.parts:
                rows.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)})
    spec = read(runtime_spec())
    external_tools = {}
    for name in ('node', 'browser', 'ffmpeg', 'ffprobe'):
        path = binary(name)
        entry = next((r for r in spec.get('assets', []) if r['id'] == name and r['arch'] == architecture()), {})
        if name != 'browser' and entry.get('binary_sha256'):
            require(sha(path) == entry['binary_sha256'], 'Mac二进制与发布方固定归档内容不符')
        if path.is_relative_to(ROOT):
            rows.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)})
        else:
            require(name in {'browser', 'node'}, '外部媒体工具未登记')
            external_tools[name] = {'path': str(path), 'sha256': sha(path)}
    target = installation_path()
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps({'schema': 'haike.native-motion-installation/1', 'arch': architecture(),
                                 'runtime_spec_sha256': sha(runtime_spec()), 'files': rows,
                                 'external_tools': external_tools}, indent=2) + '\n', encoding='utf8')
    return {'native_motion_files': len(rows), 'arch': architecture()}


def installation_path():
    return ROOT / ('.local/system-motion-runtime.json' if sys.platform == 'win32' else '.local/mac-motion-runtime.json')


def runtime_spec():
    return ROOT / 'portable/dependency-downloads.json' if sys.platform == 'win32' else SPEC
