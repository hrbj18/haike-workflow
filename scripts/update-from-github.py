"""One GitHub release URL: acquire verified updates using the installed runtime.

Original 1027 installs use the transactional bootstrap. Existing portable 1.2
installs use their running application's normal download/restart worker. Never
reinstall Python, Node, FFmpeg, browser or pip/npm dependencies from the web.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import sqlite3
import subprocess
import sys
import time
from urllib import error, parse, request
from uuid import uuid4
import zipfile

REPOSITORY = 'hrbj18/haike-workflow'
BASE_SOURCE = '21d1ff23bd1debdb53a9e651a590895c755a8c03'
MAX_DOWNLOAD = 200_000_000


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def version(value):
    require(isinstance(value, str) and re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value), '版本号无效')
    return tuple(map(int, value.split('.')))


def safe(root, name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name,
            '升级路径无效')
    parts = name.split('/')
    require(not PurePosixPath(name).is_absolute() and all(p not in {'', '.', '..'}
        and not p.endswith((' ', '.')) and not any(c in p for c in '*?"<>|') for p in parts), '升级路径越界')
    root = Path(root).resolve()
    current = root
    for part in parts:
        current = current / part
        require(not current.is_symlink() and not (hasattr(current, 'is_junction') and current.is_junction()),
                '升级目录不能经过链接')
    require(current.resolve().is_relative_to(root), '升级目录越界')
    return current


def feed_url(url):
    parsed = parse.urlsplit(url)
    require(parsed.scheme == 'https' and parsed.netloc == 'github.com'
            and not parsed.query and not parsed.fragment and not parsed.username,
            '请提供正式GitHub仓库或发行页地址')
    parts = parsed.path.strip('/').split('/')
    require('/'.join(parts[:2]) == REPOSITORY, '请使用海客官方仓库的更新地址')
    if len(parts) == 2 or parts[2:] in [['releases'], ['releases', 'latest']]:
        return f'https://github.com/{REPOSITORY}/releases/latest/download/haike-update.json'
    require(len(parts) == 5 and parts[2:4] == ['releases', 'tag']
            and re.fullmatch(r'v\d+\.\d+\.\d+', parts[4]), '请使用正式版本发行页')
    return f'https://github.com/{REPOSITORY}/releases/download/{parts[4]}/haike-update.json'


def https(url):
    parsed = parse.urlsplit(url)
    require(parsed.scheme == 'https' and parsed.hostname and not parsed.username
            and not parsed.password and not parsed.fragment, '更新下载仅支持HTTPS')
    return parsed


class Redirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, message, headers, url):
        https(url)
        result = super().redirect_request(req, fp, code, message, headers, url)
        # GitHub asset APIs redirect to signed CDN URLs. Never forward the
        # user's GitHub credential to a CDN or any other redirected origin.
        if parse.urlsplit(url).netloc != parse.urlsplit(req.full_url).netloc:
            result.remove_header('Authorization')
        return result


def github_token():
    result = subprocess.run(['gh', 'auth', 'token', '--hostname', 'github.com'],
        capture_output=True, text=True, timeout=15,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    require(result.returncode == 0 and result.stdout.strip(),
        '授权资源库需要首次GitHub登录：请运行 gh auth login --hostname github.com --web')
    return result.stdout.strip()


def remote(url, authentication=None):
    parsed = https(url)
    headers = {'User-Agent': 'Haike-Video-Bootstrap/1', 'Accept': 'application/octet-stream'}
    if authentication:
        require(authentication == 'github-cli' and parsed.netloc == 'api.github.com'
                and re.fullmatch(r'/repos/hrbj18/[A-Za-z0-9_.-]+/releases/assets/\d+', parsed.path),
                '私有资源仅允许通过指定GitHub资产API认证')
        headers['Authorization'] = 'Bearer ' + github_token()
    return request.build_opener(Redirect()).open(request.Request(url, headers=headers), timeout=45)


def validate_feed(value):
    require(value.get('schema') == 1 and value.get('edition') == 'haike-workflow-2'
            and value.get('channel') == 'stable', '不是海客稳定更新清单')
    version(value['version'])
    bootstrap = value.get('bootstrap')
    require(isinstance(bootstrap, dict) and bootstrap.get('base_source_commit') == BASE_SOURCE,
            '发行版未提供1027直接升级入口')
    for key in ('program', 'resources'):
        asset = bootstrap[key]
        parsed = https(asset['url'])
        require(parsed.netloc in {'github.com', 'api.github.com'}, '更新资产必须由GitHub托管')
        if parsed.netloc == 'github.com':
            require(parsed.path.startswith('/' + REPOSITORY + '/releases/download/'), '公开更新资产不属于官方仓库')
        require(type(asset.get('size')) is int and 0 < asset['size'] <= MAX_DOWNLOAD
                and re.fullmatch('[a-f0-9]{64}', asset.get('sha256', '')), '下载大小或摘要无效')
        require(asset.get('authentication') in {None, 'github-cli'}, '资源认证方式不支持')
    require(sum(bootstrap[k]['size'] for k in ('program', 'resources')) <= MAX_DOWNLOAD,
            '首次升级下载总量超过200MB')
    return value


def fetch_asset(root, asset):
    directory = safe(root, '.local/github-updates/downloads')
    directory.mkdir(parents=True, exist_ok=True)
    path = safe(directory, asset['sha256'] + '.zip')
    if path.is_file() and path.stat().st_size == asset['size'] and sha(path) == asset['sha256']:
        return path
    partial = safe(directory, asset['sha256'] + '-' + uuid4().hex + '.part')
    count, digest = 0, hashlib.sha256()
    try:
        with remote(asset['url'], asset.get('authentication')) as response, partial.open('xb') as output:
            while block := response.read(1024 * 1024):
                count += len(block)
                require(count <= asset['size'], '下载文件超过声明大小，已停止')
                digest.update(block); output.write(block)
        require(count == asset['size'] and digest.hexdigest() == asset['sha256'], '下载摘要不符，原程序未修改')
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)
    return path


def extract_program(root, archive):
    # Keep extraction paths short on Windows; the nested source filenames can
    # otherwise exceed MAX_PATH even under a normal installation directory.
    directory = safe(root, '.local/gu/b/' + sha(archive)[:12] + '-' + uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as zipped:
        require(len(zipped.infolist()) < 20000 and sum(x.file_size for x in zipped.infolist()) < 100_000_000,
                '程序包解压大小超限')
        names = set()
        for item in zipped.infolist():
            require(not item.is_dir() and item.filename.casefold() not in names
                    and item.filename.startswith('haike-update-1.2/')
                    and ((item.external_attr >> 16) & 0o170000) != 0o120000, '程序包有非法条目')
            names.add(item.filename.casefold())
            destination = safe(directory, item.filename)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(zipped.read(item))
    bundle = safe(directory, 'haike-update-1.2')
    require((bundle / 'legacy_upgrade.py').is_file() and (bundle / 'UPGRADE.json').is_file(), '程序包缺少升级入口')
    return bundle


def processes():
    if os.name != 'nt':
        return []
    command = ('[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding; '
               'Get-CimInstance Win32_Process -Filter "Name=\'python.exe\' OR Name=\'pythonw.exe\'" | '
               'Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True,
        text=True, encoding='utf-8', errors='replace', timeout=30)
    require(result.returncode == 0, '无法检查工作台进程')
    rows = json.loads(result.stdout) if result.stdout.strip() else []
    return [rows] if isinstance(rows, dict) else rows


def supported(root):
    try:
        if (root / '.git').exists() or not (root / 'PACKAGE-MANIFEST.json').is_file():
            return False
        release = read(root / 'RELEASE.json')
        return release.get('edition') == 'haike-workflow-2' and (
            release.get('source_commit') == BASE_SOURCE or version(release.get('version', '0.0.0')) >= (1, 2, 0))
    except (OSError, ValueError, KeyError):
        return False


def discover():
    roots = {Path.cwd().resolve()} if supported(Path.cwd()) else set()
    for row in processes():
        if not re.search(r'\bbacklot\s+serve\b', row.get('CommandLine') or ''):
            continue
        path = Path(row.get('ExecutablePath') or '')
        for candidate in [path.parents[2], path.parents[3]] if len(path.parents) >= 4 else []:
            if supported(candidate):
                roots.add(candidate.resolve())
    require(len(roots) == 1, '未找到唯一安装目录，请让Codex核对后加 --target 指定原工作台目录')
    return roots.pop()


def idle(root):
    queue = safe(root, 'Haike_video/.backlot/production-queue.sqlite3')
    if queue.is_file():
        with closing(sqlite3.connect(queue.as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='production_jobs'").fetchone():
                require(not db.execute("SELECT 1 FROM production_jobs WHERE status NOT IN ('completed','failed','cancelled') LIMIT 1").fetchone(),
                        '请先完成或核对制作队列中的任务，再更新；原任务保留')
    studio = safe(root, 'Haike_video/.backlot/studio.sqlite3')
    if studio.is_file():
        with closing(sqlite3.connect(studio.as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='studio_audio_operations'").fetchone():
                require(not db.execute('SELECT 1 FROM studio_audio_operations WHERE attempts>0 AND outcome IS NULL LIMIT 1').fetchone(),
                        '音色操作结果待确认，请核对原操作后更新')
    audio = safe(root, 'Haike_video/.backlot/audio-center-internal')
    for file in audio.glob('*/operations/*/operation.json'):
        operation = read(safe(root, file.relative_to(root).as_posix()))
        require(operation.get('status') in {'succeeded', 'failed'},
                '音色操作正在执行或结果待确认，请先核对原操作后更新')


def stop_legacy(root):
    idle(root)
    prefix = str(root).casefold() + os.sep
    for row in processes():
        if (row.get('ExecutablePath') or '').casefold().startswith(prefix) and re.search(
                r'\bbacklot\s+serve\b', row.get('CommandLine') or ''):
            require(row['ProcessId'] != os.getpid(), '不能停止升级进程')
            os.kill(row['ProcessId'], signal.SIGTERM)
    time.sleep(.4)


def local(base, path, data=None):
    headers = {'Origin': base, 'Content-Type': 'application/json'}
    req = request.Request(base + path, headers=headers,
        data=json.dumps(data).encode() if data is not None else None)
    with request.build_opener(request.ProxyHandler({})).open(req, timeout=60) as response:
        return json.loads(response.read(2_000_000))


def running_base(root):
    state = safe(root, '.portable/services.json')
    for row in read(state).get('services', []) if state.is_file() else []:
        port = row.get('port')
        if row.get('kind') != 'backlot' or type(port) is not int or not 1024 <= port <= 65535:
            continue
        base = 'http://127.0.0.1:' + str(port)
        try:
            health = local(base, '/api/health')
            if health.get('ok') and Path(health['workspace']).resolve() == root:
                return base
        except (OSError, ValueError, KeyError):
            pass
    raise ValueError('请先启动此副本工作台，再运行联网更新；不要重新安装运行依赖')


def modern_update(root, expected):
    try:
        base = running_base(root)
    except ValueError:
        idle(root)
        ensure_no_pending_update(root)
        launch(root)
        base = running_base(root)
    snapshot = local(base, '/api/studio/app-update')
    operation = snapshot.get('operation', {})
    if operation.get('status') not in {'downloading', 'waiting', 'installing', 'restarting'}:
        snapshot = local(base, '/api/studio/app-update/check', {})
        require(snapshot['update'].get('version') == expected and snapshot['update']['status'] == 'available',
                snapshot['update'].get('message', '此版本没有兼容补丁'))
        snapshot = local(base, '/api/studio/app-update/install', {'version': expected, 'confirmed': True})
        operation = snapshot['operation']
    require(operation.get('target_version') == expected and operation.get('id'),
            '已有其他更新任务，请先核对原更新记录')
    identity = operation['id']
    deadline = time.monotonic() + 2100
    while time.monotonic() < deadline:
        try:
            snapshot = local(base, '/api/studio/app-update')
            require(snapshot.get('operation', {}).get('id') == identity, '更新记录已变化，请核对原更新任务')
            state = snapshot.get('operation', {}).get('status')
            require(state not in {'failed', 'rolled_back', 'cancelled'}, snapshot.get('operation', {}).get('message', '更新未完成'))
            if state == 'complete' and snapshot['current'].get('version') == expected:
                return {'ok': True, 'version': expected, 'url': base + '/avatar', 'mode': 'application-updater'}
        except (OSError, error.URLError):
            pass
        time.sleep(2)
    raise ValueError('更新仍在等待任务或恢复连接，请查询原更新记录，不要重复提交')


def python_environment():
    environment = os.environ.copy()
    environment.pop('PYTHONHOME', None)
    environment.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONNOUSERSITE='1')
    return environment


def ensure_no_pending_update(root):
    directory = safe(root, '.local/app-updates')
    state = safe(root, '.local/app-updates/state.json')
    if state.is_file():
        require(read(state).get('operation', {}).get('status') not in
                {'downloading', 'waiting', 'installing', 'restarting'}, '已有更新任务，请查询原更新记录，不要重复启动')
    for file in directory.glob('*/receipt.json'):
        require(read(safe(root, file.relative_to(root).as_posix())).get('status') in {'complete', 'restored', 'rolled_back'},
                '上次更新未恢复，请先按回执恢复备份')


def launch(root):
    result = subprocess.run([str(root / 'runtime/python/python.exe'), '-s', str(root / 'portable/portable.py'),
        'start', '--no-browser'], capture_output=True, encoding='utf-8', timeout=240, env=python_environment())
    require(result.returncode == 0, '本副本启动未完成，请查看原目录启动日志')


def finish_bootstrap_start(root, output, installer):
    try:
        launch(root)
        output['url'] = running_base(root) + '/avatar'
    except (ValueError, OSError, subprocess.SubprocessError) as startup:
        try:
            stop_legacy(root)
            with installer.lock(root):
                installer.restore(root, Path(output['backup']))
            launch(root)
            running_base(root)
        except (ValueError, OSError, subprocess.SubprocessError) as recovery:
            raise ValueError('正式启动未完成，恢复尚未确认，请保留备份 ' + output['backup']) from recovery
        raise ValueError('新版本正式启动失败，已恢复并启动原版本；备份：' + output['backup']) from startup


def run(url, target=None, *, check=False, start=True):
    root = Path(target).resolve(strict=True) if target else discover()
    require(supported(root), '目标不是受支持的已安装便携工作台，不能覆盖源码仓库')
    with remote(feed_url(url)) as response:
        raw = response.read(1_000_001)
    require(len(raw) <= 1_000_000, '更新清单超出大小限制')
    feed = validate_feed(json.loads(raw))
    release = read(root / 'RELEASE.json')
    current = release.get('version')
    if current and version(current) >= version(feed['version']):
        return {'ok': True, 'already_current': True, 'version': current}
    if current:
        if check:
            return {'ok': True, 'mode': 'application-updater', 'current': current, 'target': feed['version']}
        return modern_update(root, feed['version'])
    require(release['source_commit'] == BASE_SOURCE, '此发行版不支持当前旧安装')
    bootstrap = feed['bootstrap']
    if check:
        return {'ok': True, 'mode': '1027-bootstrap', 'version': feed['version'],
                'download_bytes': sum(bootstrap[k]['size'] for k in ('program', 'resources'))}
    # Acquire and verify both archives before stopping any service.
    program = fetch_asset(root, bootstrap['program'])
    resources = fetch_asset(root, bootstrap['resources'])
    bundle = extract_program(root, program)
    plan = read(bundle / 'UPGRADE.json')
    require(plan['release']['version'] == feed['version']
            and plan['resources']['sha256'] == bootstrap['resources']['sha256'], '联网清单与已验证程序包不一致')
    # Execute only the verified archive's own preflight before stopping the
    # running old server; apply() repeats all checks under its transaction lock.
    previous_path = list(sys.path)
    previous_core = sys.modules.pop('release_core', None)
    try:
        sys.path.insert(0, str(bundle))
        spec = importlib.util.spec_from_file_location('haike_online_installer', bundle / 'legacy_upgrade.py')
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        installer.preflight(bundle, root, resources, require_stopped=False)
    finally:
        sys.path[:] = previous_path
        sys.modules.pop('release_core', None)
        if previous_core is not None:
            sys.modules['release_core'] = previous_core
    command = [str(root / 'runtime/python/python.exe'), '-s', str(bundle / 'legacy_upgrade.py'),
               '--target', str(root), '--resources', str(resources)]
    # Full installer preflight follows immediately; only this target's idle
    # video server is stopped. Publisher and other installations keep running.
    stop_legacy(root)
    result = subprocess.run(command, capture_output=True, encoding='utf-8', timeout=600,
                            env=python_environment())
    if result.returncode:
        reverted = read(root / 'RELEASE.json')
        if reverted.get('source_commit') == BASE_SOURCE and not reverted.get('version'):
            subprocess.run([str(root / 'runtime/python/python.exe'), '-s', str(root / 'portable/portable.py'),
                'start', '--no-browser'], capture_output=True, timeout=240, env=python_environment())
        raise ValueError('升级未完成，原程序或备份已保留：' + result.stderr[-1200:])
    output = json.loads(result.stdout)
    require(output.get('ok') and read(root / 'RELEASE.json')['version'] == feed['version'], '未确认安装结果')
    if start:
        finish_bootstrap_start(root, output, installer)
    output['mode'] = 'github-online-bootstrap'
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('github_url')
    parser.add_argument('--target', type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--no-start', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.github_url, args.target, check=args.check, start=not args.no_start), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
