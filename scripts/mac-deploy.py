"""Native Mac source/offline deployment. Never copies Windows virtualenvs."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import time
import tomllib
import urllib.request
import webbrowser
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / '_distribution-tools/macos-runtime.json'
MODULES = ('Haike_video', 'creatorhub', 'copy_skill/copy_skill-main', 'api-platform')
FRONTENDS = ('Haike_video/remotion-composer', 'prototypes/haike-avatar-generator', 'creatorhub')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def architecture():
    if sys.platform != 'darwin':
        raise ValueError('Mac 部署入口只能在 macOS 上运行')
    arch = platform.machine()
    if arch not in {'arm64', 'x86_64'}:
        raise ValueError('仅支持 Apple Silicon 和 Intel Mac')
    if int(platform.mac_ver()[0].split('.')[0]) < 14:
        raise ValueError('需要 macOS 14 或更新版本')
    return arch


def contained(root, name):
    """Only archive-relative paths, including when tested on another OS."""
    if not isinstance(name, str) or '\\' in name or ':' in name:
        raise ValueError('归档路径无效')
    part = Path(name)
    target = Path(root) / part
    if part.is_absolute() or '..' in part.parts or not target.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('归档路径越界')
    return target


def obtain(row, offline):
    path = ROOT / 'deployment-cache/runtime' / row['name']
    if not path.is_file():
        if offline:
            raise ValueError('离线运行时缺失：' + row['name'])
        path.parent.mkdir(parents=True, exist_ok=True)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(row['url'], timeout=120) as response, path.with_suffix(path.suffix + '.part').open('wb') as stream:
            shutil.copyfileobj(response, stream)
        path.with_suffix(path.suffix + '.part').replace(path)
    if path.is_symlink() or path.stat().st_size != row['size'] or digest(path) != row['sha256']:
        raise ValueError('运行时归档校验失败：' + row['name'])
    return path


def unzip(source, target):
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        for item in archive.infolist():
            path = contained(target, item.filename)
            mode = item.external_attr >> 16
            if item.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            elif stat.S_ISLNK(mode):
                link = archive.read(item).decode('utf8')
                if not (path.parent / link).resolve().is_relative_to(target.resolve()):
                    raise ValueError('浏览器链接越界')
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists() and not path.is_symlink():
                    path.symlink_to(link)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as stream, path.open('wb') as output:
                    shutil.copyfileobj(stream, output)
                path.chmod((mode & 0o777) or 0o644)


def install_runtimes(arch, offline):
    spec = read(SPEC)
    for row in spec['assets']:
        if row['arch'] != arch:
            continue
        source = obtain(row, offline)
        kind = row['id']
        if kind == 'python':
            continue  # The verified shell bootstrap already extracted this one.
        if kind == 'node':
            directory = ROOT / 'runtime/macos' / arch / 'node'
            directory.mkdir(parents=True, exist_ok=True)
            with tarfile.open(source) as archive:
                archive.extractall(directory, filter='data')
        elif kind in {'ffmpeg', 'ffprobe'}:
            target = ROOT / 'runtime/macos' / arch / 'ffmpeg/bin' / kind
            target.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(source) as stream, target.open('wb') as output:
                shutil.copyfileobj(stream, output)
            target.chmod(0o755)
        elif kind in {'browser', 'login_browser'}:
            unzip(source, ROOT / 'runtime/macos' / arch / kind)
    return spec


def environment(arch):
    runtime = ROOT / 'runtime/macos' / arch
    nodes = list((runtime / 'node').glob('node-*/bin/node'))
    browsers = list((runtime / 'browser').glob('chrome-headless-shell-*/chrome-headless-shell'))
    if len(nodes) != 1 or len(browsers) != 1:
        raise ValueError('原生 Node 或渲染浏览器缺失；请先运行安装入口')
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONNOUSERSITE='1',
               PYTHONPATH=str(ROOT / 'Haike_video') + os.pathsep + str(ROOT / 'copy_skill/copy_skill-main/src'),
               VIDEOHUB_ROOT=str(ROOT), HAIKE_NODE_EXECUTABLE=str(nodes[0]),
               FFMPEG_BINARY=str(runtime / 'ffmpeg/bin/ffmpeg'),
               FFPROBE_BINARY=str(runtime / 'ffmpeg/bin/ffprobe'),
               REMOTION_BROWSER_EXECUTABLE=str(browsers[0]), CHROME_PATH=str(browsers[0]),
               HYPERFRAMES_BROWSER_PATH=str(browsers[0]), PRODUCER_HEADLESS_SHELL_PATH=str(browsers[0]),
               PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1', BACKLOT_NO_BROWSER='1',
               HYPERFRAMES_NO_TELEMETRY='1', HYPERFRAMES_NO_AUTO_INSTALL='1')
    env['PATH'] = os.pathsep.join([str(nodes[0].parent), str(runtime / 'ffmpeg/bin'), env.get('PATH', '')])
    env['NO_PROXY'] = ','.join(filter(None, (env.get('NO_PROXY', ''), 'localhost,127.0.0.1,::1')))
    return env


def python_for(module):
    return ROOT / module / '.venv/bin/python'


def execute(argv, *, cwd=ROOT, env=None, timeout=2400):
    subprocess.run([str(a) for a in argv], cwd=cwd, env=env, check=True, timeout=timeout)


def requirements(module, destination):
    if module == 'Haike_video':
        # Cloud audio plus the existing optional local ASR fallback; no local Qwen.
        lines = ['-r ' + str(ROOT / module / 'requirements.txt'),
                 'faster-whisper>=1.2,<2', 'onnxruntime>=1.20', 'setuptools>=68', 'wheel',
                 *tomllib.loads((ROOT / 'api-platform/pyproject.toml').read_text())['project']['dependencies']]
    elif (ROOT / module / 'requirements.txt').is_file():
        lines = ['-r ' + str(ROOT / module / 'requirements.txt'), 'setuptools>=68', 'wheel']
    else:
        lines = [*tomllib.loads((ROOT / module / 'pyproject.toml').read_text())['project']['dependencies'],
                 'setuptools>=68', 'wheel']
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text('\n'.join(lines) + '\n', encoding='utf8')


def install_python(arch, spec, offline, cache_only):
    modules = list(MODULES)
    crawler = 'copy_skill/copy_skill-main/third_party/MediaCrawler'
    if (ROOT / crawler / 'requirements.txt').is_file():
        modules.append(crawler)
    for module in modules:
        py = python_for(module)
        venv = py.parent.parent
        # Rebuilding is confined to dependencies; local config/data are outside .venv.
        execute([sys.executable, '-m', 'venv', str(venv)])
        folder = ROOT / 'deployment-cache/python' / arch / module.replace('/', '__')
        lock = folder / 'requirements.txt'
        req = folder / 'input.txt'
        requirements(module, req)
        wheel_args = ['--no-index', '--find-links', folder / 'wheels'] if offline else ['--index-url', spec['pip_index']]
        if offline and not lock.is_file():
            raise ValueError('离线 Python 依赖清单缺失：' + module)
        execute([py, '-m', 'pip', 'install', '--disable-pip-version-check', *wheel_args, '-r', lock if offline else req])
        if module == 'copy_skill/copy_skill-main':
            # Keep the source editable using an ordinary relative .pth, not a build-machine path.
            libraries = next((venv / 'lib').glob('python*/site-packages'))
            (libraries / 'haike_collection.pth').write_text(str(ROOT / module / 'src') + '\n', encoding='utf8')
        execute([py, '-m', 'pip', 'check'])
        if cache_only:
            result = subprocess.run([str(py), '-m', 'pip', 'freeze'], check=True, capture_output=True, text=True)
            if any(' @ ' in line or line.startswith('-e ') for line in result.stdout.splitlines()):
                raise ValueError('依赖冻结含构建机绝对路径')
            lock.write_text(result.stdout, encoding='utf8')
            execute([py, '-m', 'pip', 'wheel', '--index-url', spec['pip_index'], '--no-deps', '-r', lock,
                     '--wheel-dir', folder / 'wheels'])
            # input.txt contains temporary build paths; it is never a deployment input.
            req.unlink(missing_ok=True)


def install_frontends(arch, spec, offline, env):
    npm = Path(env['HAIKE_NODE_EXECUTABLE']).with_name('npm')
    cache = ROOT / 'deployment-cache/npm' / arch
    for module in FRONTENDS:
        folder = ROOT / module
        execute([npm, 'ci', '--no-audit', '--no-fund', '--cache', cache,
                 '--registry', spec['npm_registry'], *(['--offline'] if offline else [])], cwd=folder, env=env)
    frontend = ROOT / 'prototypes/haike-avatar-generator'
    execute([npm, 'run', 'build'], cwd=frontend, env=dict(env, HAIKE_EMBED_BASE='/ui/avatar-generator/'))
    shutil.copytree(frontend / 'dist/client', ROOT / 'Haike_video/backlot/ui/avatar-generator', dirs_exist_ok=True)
    execute([npm, 'run', 'build:ui'], cwd=ROOT / 'creatorhub', env=env)


def configure(arch, env):
    execute([sys.executable, ROOT / 'scripts/configure.py'], env=env)
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location('haike_mac_private_profile', ROOT / 'scripts/install-private-profile.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module.install(ROOT, python_for('Haike_video'), env=env)
    for relative in ('Haike_video/projects', 'Haike_video/renders', 'Haike_video/cache', 'Haike_video/temp', 'creatorhub/data'):
        (ROOT / relative).mkdir(parents=True, exist_ok=True)


def version():
    return read(ROOT / 'VERSION.json')['version']


def install(args):
    arch = architecture()
    spec = install_runtimes(arch, args.offline)
    env = environment(arch)
    install_python(arch, spec, args.offline, args.cache_only)
    install_frontends(arch, spec, args.offline, env)
    configure(arch, env)
    write(ROOT / '.local/mac-installation.json', {'schema': 1, 'version': version(), 'arch': arch,
          'install_root': str(ROOT), 'offline': args.offline, 'private_profile_present': (ROOT / 'private-profile').is_dir(),
          'paid_generation': False, 'platform_login_imported': False})
    return check(args)


def check(args):
    arch = architecture()
    env = environment(arch)
    for module in MODULES:
        code = 'import fastapi,uvicorn' if module != 'copy_skill/copy_skill-main' else 'import cv2,faster_whisper,onnxruntime;import douyin_intelligence'
        execute([python_for(module), '-c', code], env=env)
        execute([python_for(module), '-m', 'pip', 'check'])
    sources = subprocess.run([str(python_for('Haike_video')), str(ROOT / 'Haike_video/scripts/motion_replay.py'), 'verify', '--preferred'],
                             env=env, check=True, capture_output=True, text=True)
    status = json.loads(sources.stdout)
    if status.get('source_status') != 'verified' or status.get('template_count') != 18:
        raise ValueError('18 套动效模板来源检查未通过')
    execute([env['FFMPEG_BINARY'], '-version'], env=env)
    execute([env['FFPROBE_BINARY'], '-version'], env=env)
    execute([env['HAIKE_NODE_EXECUTABLE'], '--version'], env=env)
    result = {'ok': True, 'platform': 'macos-' + arch, 'version': version(), 'source_identity': '18 preferred verified',
              'paid_calls': 0, 'publishing': False, 'scope': 'native imports, source hashes and runtime versions'}
    write(ROOT / '.local/mac-check.json', result)
    print(json.dumps(result, ensure_ascii=False))
    return result


def http_json(port, path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f'http://127.0.0.1:{port}{path}', timeout=1) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def free_port(first, excluded=()):
    for port in range(first, first + 50):
        if port in excluded:
            continue
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                pass
    raise ValueError('没有空闲本机端口')


def start(args):
    arch = architecture()
    env = environment(arch)
    state = ROOT / '.local/mac-services.json'
    previous = read(state) if state.is_file() else {}
    backlot = previous.get('studio_port')
    publisher = previous.get('publisher_port')
    health = http_json(backlot, '/api/health') if backlot else None
    expected = hashlib.sha256(str((ROOT / 'creatorhub').resolve()).replace('\\', '/').casefold().encode()).hexdigest()
    account = http_json(publisher, '/api/download-sessions') if publisher else None
    if not (health and health.get('workspace') == str(ROOT.resolve()) and account and account.get('service_fingerprint') == expected):
        backlot = free_port(args.port)
        publisher = free_port(args.publisher_port, {backlot})
        env['HAIKE_CREATORHUB_URL'] = f'http://127.0.0.1:{publisher}'
        env['HAIKE_WORKSPACE_ID'] = expected
        logs = ROOT / '.local/mac-launcher'
        logs.mkdir(parents=True, exist_ok=True)
        children = []
        try:
            for name, module, command in [('publisher', 'creatorhub', ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(publisher)]),
                                          ('studio', 'Haike_video', ['-m', 'backlot', 'serve', '--port', str(backlot)])]:
                with (logs / (name + '.log')).open('ab') as stream:
                    children.append(subprocess.Popen([str(python_for(module)), *command], cwd=ROOT / module,
                        env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True))
            for _ in range(120):
                health = http_json(backlot, '/api/health')
                account = http_json(publisher, '/api/download-sessions')
                if health and health.get('workspace') == str(ROOT.resolve()) and account and account.get('service_fingerprint') == expected:
                    break
                if any(child.poll() is not None for child in children):
                    raise ValueError('服务启动失败，请查看 .local/mac-launcher 日志')
                time.sleep(.5)
            else:
                raise ValueError('服务在 60 秒内未就绪，已保留启动日志')
        except Exception:
            for child in children:
                if child.poll() is None:
                    child.terminate()
            raise
        write(state, {'root': str(ROOT), 'studio_port': backlot, 'publisher_port': publisher,
                      'pids': [p.pid for p in children]})
    result = {'ok': True, 'url': f'http://127.0.0.1:{backlot}/avatar', 'publisher_url': f'http://127.0.0.1:{publisher}/'}
    if not args.no_browser:
        webbrowser.open(result['url'])
    print(json.dumps(result, ensure_ascii=False))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['install', 'check', 'start'])
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--cache-only', action='store_true', help='Prepare redistributable native dependency caches, without credentials')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=14756)
    parser.add_argument('--publisher-port', type=int, default=8000)
    args = parser.parse_args()
    try:
        {'install': install, 'check': check, 'start': start}[args.command](args)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        # No profile payloads or credentials appear in exception strings.
        print('Mac 部署失败：' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
