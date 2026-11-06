"""Incremental dependencies for a pinned source update; no provider calls."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from portable.dependency_sources import environment
from portable.system_browser import environment as browser_environment
from portable.source_app_update import SHA, git

FRONTENDS = ('Haike_video/remotion-composer', 'Haike_video/motion-components/snapcn',
             'prototypes/haike-avatar-generator', 'creatorhub', '_distribution-tools/motion-html')


def runtime_environment(root=ROOT, *, browser_required=True):
    env = browser_environment(environment(), required=browser_required)
    nodes = [Path(env['HAIKE_NODE_EXECUTABLE'])] if env.get('HAIKE_NODE_EXECUTABLE') else []
    nodes += [root / 'runtime/node/node.exe', *root.glob('runtime/macos/*/node/node-*/bin/node')]
    node = next((p for p in nodes if p.is_file()), None)
    if node:
        env['PATH'] = str(node.parent) + os.pathsep + env.get('PATH', '')
        env['HAIKE_NODE_EXECUTABLE'] = str(node)
    return env


def execute(args, env, cwd=ROOT):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True, timeout=1800,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def python_for(module):
    return ROOT / module / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')


def install_windows_python(changed, env):
    uv = next((str(path) for path in (ROOT / 'runtime/uv/uv.exe', Path(sys.executable).with_name('uv.exe'))
               if path.is_file()), None) or shutil.which('uv', path=env.get('PATH'))
    for module in ('Haike_video', 'creatorhub', 'copy_skill/copy_skill-main'):
        lock = ('copy_skill/copy_skill-main/uv.lock' if module.startswith('copy_skill') else
                '_distribution-tools/locks/' + module + '.txt')
        inputs = {lock, module + '/pyproject.toml', module + '/requirements.txt', module + '/requirements-dev.txt'}
        py = python_for(module)
        if py.is_file() and not (changed & inputs):
            print('Reuse Python environment: ' + module, flush=True)
            continue
        if not uv:
            raise ValueError('补齐 Python 依赖需要 uv；请安装 uv 或让 Agent 修复运行环境。')
        if not py.is_file():
            execute([uv, 'venv', '--python', '3.12', ROOT / module / '.venv'], env)
        if module.startswith('copy_skill'):
            exported = ROOT / '.local/dependency-state/collector-requirements.txt'
            exported.parent.mkdir(parents=True, exist_ok=True)
            # uv sync would replay pypi.org URLs stored in uv.lock. Export pinned
            # versions/hashes, then select the mirror at install time instead.
            execute([uv, 'export', '--frozen', '--all-groups', '--no-emit-project',
                     '--output-file', exported], env, ROOT / module)
            execute([uv, 'pip', 'install', '--python', py, '--index-url', env['PIP_INDEX_URL'], '-r', exported], env)
            libraries = ROOT / module / '.venv/Lib/site-packages'
            (libraries / 'haike_collection.pth').write_text(str(ROOT / module / 'src') + '\n', encoding='utf-8')
        else:
            execute([uv, 'pip', 'install', '--python', py, '--index-url', env['PIP_INDEX_URL'], '-r', ROOT / lock], env)
            if module == 'Haike_video':
                execute([uv, 'pip', 'install', '--python', py, '--index-url', env['PIP_INDEX_URL'],
                         '-r', ROOT / module / 'requirements-dev.txt'], env)
        execute([uv, 'pip', 'check', '--python', py], env)


def install_mac_python(changed, env):
    spec = importlib.util.spec_from_file_location('haike_mac_setup', ROOT / 'scripts/mac-deploy.py')
    mac = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mac)
    modules = list(mac.MODULES)
    crawler = 'copy_skill/copy_skill-main/third_party/MediaCrawler'
    if (ROOT / crawler / 'requirements.txt').is_file():
        modules.append(crawler)
    for module in modules:
        lock = '_distribution-tools/locks/macos/' + platform.machine() + '/' + module.replace('/', '__') + '.txt'
        inputs = {lock, module + '/requirements.txt', module + '/pyproject.toml'}
        if module == 'Haike_video':
            inputs.add('api-platform/pyproject.toml')
        py = python_for(module)
        if py.is_file() and not (changed & inputs):
            print('Reuse Python environment: ' + module, flush=True)
            continue
        if not py.is_file():
            execute([sys.executable, '-m', 'venv', py.parent.parent], env)
        req = ROOT / '.local/dependency-state' / (module.replace('/', '__') + '.txt')
        mac.requirements(module, req)
        execute([py, '-m', 'pip', 'install', '--prefer-binary', '--index-url', env['PIP_INDEX_URL'],
                 '-r', req, *(['-r', ROOT / lock] if (ROOT / lock).is_file() else [])], env)
        execute([py, '-m', 'pip', 'check'], env)


def refresh(previous, *, root=ROOT, dependencies_only=False):
    if not SHA.fullmatch(previous):
        raise ValueError('原提交编号无效。')
    changed = set(git(root, 'diff', '--name-only', previous, 'HEAD').stdout.splitlines())
    env = runtime_environment(root, browser_required=not dependencies_only)
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm', path=env.get('PATH'))
    if not npm:
        raise ValueError('前端构建需要 Node.js 22+ 与 npm；原环境未修改。')
    execute([shutil.which('node', path=env.get('PATH')) or 'node', '-e',
             'if(Number(process.versions.node.split(".")[0])<22)process.exit(1)'], env)
    if sys.platform == 'darwin':
        install_mac_python(changed, env)
    else:
        install_windows_python(changed, env)
    for module in FRONTENDS:
        path = root / module
        if not (path / 'package-lock.json').is_file():
            continue
        inputs = {module + '/package-lock.json', module + '/package.json', module + '/.npmrc'}
        if not (path / 'node_modules').is_dir() or changed & inputs:
            execute([npm, 'ci', '--no-audit', '--no-fund', '--registry', env['npm_config_registry'],
                     *(['--legacy-peer-deps'] if module.endswith('/snapcn') else [])], env, path)
        else:
            print('Reuse npm dependencies: ' + module, flush=True)
    if dependencies_only:
        return
    if sys.platform == 'win32':
        execute([sys.executable, root / 'scripts/setup-windows-media.py'], env, root)
    execute([sys.executable, root / 'scripts/build-studio.py', '--skip-install'], env, root)
    # CreatorHub ships its compiled bundle in Git. Rebuilding tracked output on
    # clients would create a dirty checkout and prevent the next safe update.
    if not (root / 'creatorhub/app/web/workbench.js').is_file():
        raise ValueError('源码缺少账号服务的已提交界面文件。')
    video_python = python_for('Haike_video')
    if sys.platform in {'darwin', 'win32'}:
        execute([video_python, root / 'scripts/bind-media-runtime.py'], env, root)
    verified = subprocess.run([str(video_python), str(root / 'Haike_video/scripts/motion_replay.py'),
                               'verify', '--preferred'], cwd=root, env=env, check=True,
                              capture_output=True, text=True, encoding='utf-8', timeout=180,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    report = json.loads(verified.stdout)
    if report.get('source_status') != 'verified':
        raise ValueError('更新后的首选动效合同/源码检查未通过。')
    print('Preferred motion template sources verified.', flush=True)
    execute([sys.executable, root / 'scripts/check.py'], env, root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous', required=True)
    parser.add_argument('--dependencies-only', action='store_true', help='Rollback restores the saved compiled frontend.')
    args = parser.parse_args()
    refresh(args.previous, dependencies_only=args.dependencies_only)
