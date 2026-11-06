"""Pinned main updates for clean Git installs, without touching original media.

This is separate from the Release/portable patch format. Browser input never
selects a repository, commit, command or local path. Dirty installs need the
documented one-time Agent migration; they are never reset or stashed here.
"""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys

try:
    from . import app_update as core
    from .dependency_sources import environment
except ImportError:
    import app_update as core
    from dependency_sources import environment

REPOSITORY = 'https://github.com/hrbj18/haike-workflow.git'
API = 'https://api.github.com/repos/hrbj18/haike-workflow'
RAW = 'https://raw.githubusercontent.com/hrbj18/haike-workflow/'
SHA = re.compile(r'^[0-9a-f]{40}$')
CONFIG_FILES = (
    '.env', '.env.local', 'creatorhub/.env',
    'Haike_video/config.local.yaml', 'Haike_video/.env', 'Haike_video/.env.local',
    'creatorhub/config.yaml', 'copy_skill/copy_skill-main/config/content_intelligence.local.json',
)
METADATA_TREES = ('Haike_video/.backlot', 'Haike_video/projects', 'creatorhub/data', '.local')
SKIP_DIRS = {'.git', '.venv', 'node_modules', 'app-updates', 'cache', 'media', 'videos',
             'audio', 'images', 'renders', 'output', 'temp', 'logs', 'browser_data'}


def git(root, *args, check=True):
    return subprocess.run(['git', '-c', 'core.longpaths=true', '-c', 'core.autocrlf=false', *args],
                          cwd=root, check=check, capture_output=True, text=True, encoding='utf-8',
                          timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def inspect(root):
    try:
        root = Path(root).resolve()
        if not (root / '.git').exists():
            raise core.UpdateError('此源码副本没有 Git 身份；请让 Agent 按源码升级教程完成一次接入。')
        origin = git(root, 'remote', 'get-url', 'origin').stdout.strip().rstrip('/')
        if origin not in {REPOSITORY, REPOSITORY[:-4], 'git@github.com:hrbj18/haike-workflow.git'}:
            raise core.UpdateError('此副本未绑定官方仓库，已保留原目录；请先让 Agent 核对来源。')
        head = git(root, 'rev-parse', 'HEAD').stdout.strip()
        if not SHA.fullmatch(head):
            raise core.UpdateError('无法核对当前源码提交。')
        if git(root, 'status', '--porcelain', '--untracked-files=normal').stdout.strip():
            raise core.UpdateError('此副本有未提交或暂存的修改，已保留现场；请让 Agent 合并或迁到独立源码副本后使用页面更新。')
        branch = git(root, 'symbolic-ref', '--quiet', '--short', 'HEAD', check=False).stdout.strip()
        if branch not in {'', 'main'}:
            raise core.UpdateError('当前位于开发分支，页面不会切换该分支；请让 Agent 核对后切换正式源码副本。')
        if sys.platform not in {'win32', 'darwin'}:
            raise core.UpdateError('当前系统尚未支持源码页面更新。')
        return {'can_install': True, 'reason': '', 'channel': 'main', 'head': head, 'branch': branch}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {'can_install': False, 'channel': 'main', 'reason': str(exc) if isinstance(exc, core.UpdateError)
                else '无法检查 Git 安装条件，请确认 Git 可用后重试。'}


def remote_json(opener, url):
    with opener(url) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise core.UpdateError('源码更新信息过大，已停止检查。')
    value = json.loads(data)
    if not isinstance(value, dict):
        raise core.UpdateError('源码更新信息无效。')
    return value


def discover(current, opener):
    row = remote_json(opener, API + '/commits/main')
    commit = row.get('sha', '')
    if not SHA.fullmatch(commit):
        raise core.UpdateError('官方 main 提交身份无效。')
    version = remote_json(opener, RAW + commit + '/VERSION.json')
    core.version_tuple(version.get('version'))
    if version.get('edition') != core.EDITION or type(version.get('data_schema')) is not int:
        raise core.UpdateError('官方源码版本信息不兼容。')
    candidate = dict(kind='source', repository=REPOSITORY, source_commit=commit,
                     base_commit=current.get('source_commit'), version=version['version'],
                     edition=version['edition'], data_schema=version['data_schema'])
    compatible = version['data_schema'] == current.get('data_schema', 1)
    status = ('current' if commit == current.get('source_commit') else
              'available' if compatible and core.version_tuple(version['version']) >= core.version_tuple(current['version'])
              else 'incompatible')
    return dict(status=status, source='main', channel='main', source_commit=commit,
                version=version['version'], candidate=candidate,
                message={'current': '当前源码已与官方 main 一致。',
                         'available': '发现 main 源码更新；确认后核对检查结果、补齐依赖并重启。',
                         'incompatible': '此源码涉及版本或数据结构迁移，请由 Agent 按升级教程处理。'}[status],
                notes=str(row.get('commit', {}).get('message', '')).split('\n\n')[0][:1000],
                published_at=row.get('commit', {}).get('committer', {}).get('date', ''))


def validate(candidate, current):
    if (candidate.get('kind') != 'source' or candidate.get('repository') != REPOSITORY
            or not SHA.fullmatch(candidate.get('source_commit', ''))
            or not SHA.fullmatch(candidate.get('base_commit', ''))
            or candidate['base_commit'] != current.get('source_commit')
            or candidate.get('edition') != core.EDITION
            or candidate.get('data_schema') != current.get('data_schema', 1)
            or core.version_tuple(candidate.get('version')) < core.version_tuple(current.get('version'))):
        raise core.UpdateError('已确认的源码身份或当前版本发生变化，请重新检查更新。')
    return candidate


def prepare(root, candidate, opener):
    """Network and immutable Git objects only; installed files stay untouched."""
    state = inspect(root)
    if not state['can_install'] or state['head'] != candidate['base_commit']:
        raise core.UpdateError(state.get('reason') or '当前源码已变化，请重新检查。')
    for workflow in ('source.yml', 'components.yml'):
        result = remote_json(opener, API + '/actions/workflows/' + workflow + '/runs?branch=main&event=push&head_sha='
                             + candidate['source_commit'] + '&per_page=10')
        runs = [run for run in result.get('workflow_runs', []) if run.get('head_sha') == candidate['source_commit']
                and run.get('head_branch') == 'main' and run.get('event') == 'push']
        if not runs or max(runs, key=lambda run: run.get('id', 0)).get('conclusion') != 'success':
            raise core.UpdateError('目标 main 的源码/组件检查尚未通过；原程序未修改，请稍后重新检查。')
    git(root, 'fetch', '--no-tags', '--depth=1', REPOSITORY, candidate['source_commit'])
    if git(root, 'rev-parse', 'FETCH_HEAD').stdout.strip() != candidate['source_commit']:
        raise core.UpdateError('取得的源码提交与已确认目标不一致。')
    metadata = json.loads(git(root, 'show', candidate['source_commit'] + ':VERSION.json').stdout)
    if any(metadata.get(key) != candidate[key] for key in ('version', 'edition', 'data_schema')):
        raise core.UpdateError('源码中的版本身份与已确认目标不一致。')
    # Python/npm locks are repaired incrementally. A different native Python,
    # Node, browser or encoder needs the platform install/migration route.
    runtime_spec = ('_distribution-tools/macos-runtime.json' if sys.platform == 'darwin'
                    else 'portable/dependency-downloads.json')
    changed = git(root, 'diff', '--name-only', candidate['base_commit'], candidate['source_commit']).stdout.splitlines()
    if runtime_spec in changed:
        def identity(value):
            if isinstance(value, dict):
                return {key: identity(val) for key, val in value.items() if key not in {
                    'url', 'urls', 'upstream', 'upstream_download', 'homepage', 'documentation',
                    'checksums_url', 'version_policy', 'provider', 'build_metadata', 'pip_index', 'npm_registry', 'pypi', 'npm'}}
            return [identity(item) for item in value] if isinstance(value, list) else value
        before = git(root, 'show', candidate['base_commit'] + ':' + runtime_spec, check=False)
        after = git(root, 'show', candidate['source_commit'] + ':' + runtime_spec, check=False)
        if before.returncode or after.returncode or identity(json.loads(before.stdout)) != identity(json.loads(after.stdout)):
            raise core.UpdateError('目标包含原生运行时版本变化，请让 Agent 按平台源码教程迁移；原程序未修改。')
    if shutil.disk_usage(root).free < 512 * 1024 * 1024:
        raise core.UpdateError('空间不足以安全构建和回退，请先保留并整理本机空间；原程序未修改。')
    # Never allow a future source tree to overwrite local private state through Git.
    names = git(root, 'ls-tree', '-r', '--name-only', candidate['source_commit']).stdout.splitlines()
    for name in names:
        parts = Path(name).parts
        if any(part in {'.local', '.backlot', '.venv', 'node_modules', 'runtime', 'projects', 'browser_data'} for part in parts):
            raise core.UpdateError('目标源码含本机数据路径，已停止更新：' + name)
        if Path(name).name.startswith('.env') and Path(name).name != '.env.example':
            raise core.UpdateError('目标源码含本机环境配置，已停止更新。')
    return state


def backup_metadata(root, folder):
    """Only structured metadata and consistent SQLite snapshots, never media."""
    root, folder = Path(root).resolve(), Path(folder)
    names = {name for name in CONFIG_FILES if core.safe_path(root, name).is_file()}
    for tree in METADATA_TREES:
        directory = core.safe_path(root, tree)
        if not directory.is_dir():
            continue
        for parent, dirs, files in os.walk(directory, followlinks=False):
            dirs[:] = [d for d in dirs if d.casefold() not in SKIP_DIRS and not (Path(parent) / d).is_symlink()]
            for file in files:
                if Path(file).suffix.lower() not in {'.json', '.yaml', '.yml', '.toml', '.ini', '.sqlite3', '.sqlite', '.db'}:
                    continue
                names.add((Path(parent) / file).relative_to(root).as_posix())
    rows = []
    required = sum(core.safe_path(root, name).stat().st_size for name in names)
    if shutil.disk_usage(folder).free < 2 * required + 64 * 1024 * 1024:
        raise core.UpdateError('空间不足以备份配置和数据库，原媒体未复制。')
    for name in sorted(names):
        source = core.safe_path(root, name)
        if source.is_symlink():
            raise core.UpdateError('元数据包含链接，请让 Agent 核对原数据位置。')
        target = core.safe_path(folder / 'metadata', name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as stream:
            database = stream.read(16) == b'SQLite format 3\x00'
        if database:
            with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as db, \
                 closing(sqlite3.connect(str(target))) as out:
                db.backup(out)
                if out.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise core.UpdateError('数据库一致性备份未通过检查。')
        else:
            before = (source.stat().st_size, source.stat().st_mtime_ns)
            shutil.copyfile(source, target)
            if before != (source.stat().st_size, source.stat().st_mtime_ns) or core.digest(source) != core.digest(target):
                raise core.UpdateError('元数据备份时发生变化，请稍后重试。')
        rows.append(dict(path=name, sha256=core.digest(target), size=target.stat().st_size, sqlite_snapshot=database))
    return rows


def switch(root, commit):
    # No --force / reset / stash. Git also refuses untracked-file collisions.
    if not isinstance(commit, str) or not SHA.fullmatch(commit):
        raise core.UpdateError('源码切换提交编号无效。')
    git(root, 'checkout', '--no-overwrite-ignore', '--detach', commit)
    if git(root, 'rev-parse', 'HEAD').stdout.strip() != commit:
        raise core.UpdateError('源码切换未能确认。')


def refresh(root, previous_commit, dependencies_only=False):
    env = environment()
    subprocess.run([sys.executable, str(Path(root) / 'scripts/update-source-dependencies.py'),
                    '--previous', previous_commit, *(['--dependencies-only'] if dependencies_only else [])],
                   cwd=root, env=env, check=True, timeout=2400,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def installed_packages(python):
    result = subprocess.run([str(python), '-c',
        'import importlib.metadata,json;print(json.dumps({d.metadata["Name"]:d.version for d in importlib.metadata.distributions() if d.metadata["Name"]}))'],
        capture_output=True, text=True, encoding='utf-8', check=True, timeout=60,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    values = json.loads(result.stdout)
    if not isinstance(values, dict) or any(not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or '\n' in version
                                           for name, version in values.items()):
        raise core.UpdateError('无法保存原 Python 依赖版本清单。')
    return values


def dependency_inventory(root):
    rows = []
    for module in ('Haike_video', 'creatorhub', 'copy_skill/copy_skill-main',
                   'copy_skill/copy_skill-main/third_party/MediaCrawler', 'api-platform'):
        relative = module + ('/.venv/Scripts/python.exe' if os.name == 'nt' else '/.venv/bin/python')
        py = Path(root) / relative
        if py.is_file():
            rows.append({'python': relative, 'packages': installed_packages(py)})
    return rows


def restore_dependencies(root, rows, folder):
    """Restore recorded versions and remove only packages added by the update."""
    env = environment()
    uv = next((str(p) for p in (Path(root) / 'runtime/uv/uv.exe', Path(sys.executable).with_name('uv.exe'))
               if p.is_file()), None) or shutil.which('uv', path=env.get('PATH'))
    normalize = lambda name: re.sub(r'[-_.]+', '-', name).lower()
    for index, row in enumerate(rows):
        allowed = {module + ('/.venv/Scripts/python.exe' if os.name == 'nt' else '/.venv/bin/python')
                   for module in ('Haike_video', 'creatorhub', 'copy_skill/copy_skill-main',
                                  'copy_skill/copy_skill-main/third_party/MediaCrawler', 'api-platform')}
        if row['python'] not in allowed:
            raise core.UpdateError('依赖回退位置不属于本副本模块。')
        py = Path(root) / row['python']
        # Mac venv/bin/python is intentionally a link to its base interpreter.
        # The venv container must remain local; the interpreter link is valid.
        core.safe_path(Path(root), py.parent.parent.relative_to(root).as_posix())
        before, after = row['packages'], installed_packages(py)
        if {normalize(n): v for n, v in before.items()} == {normalize(n): v for n, v in after.items()}:
            continue
        removed = sorted(name for name in after if normalize(name) not in {normalize(n) for n in before})
        req = Path(folder) / ('python-before-' + str(index) + '.txt')
        req.write_text(''.join(name + '==' + value + '\n' for name, value in sorted(before.items())), encoding='utf-8')
        prefix = [uv, 'pip'] if uv else [str(py), '-m', 'pip']
        target = ['--python', str(py)] if uv else []
        options = dict(cwd=root, env=env, check=True, timeout=1800,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if removed:
            subprocess.run([*prefix, 'uninstall', *target, *([] if uv else ['-y']), *removed], **options)
        subprocess.run([*prefix, 'install', *target, '--index-url', env['PIP_INDEX_URL'], '-r', str(req)], **options)
        subprocess.run([*prefix, 'check', *target], **options)
