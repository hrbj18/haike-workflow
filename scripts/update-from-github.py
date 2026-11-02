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
MAX_DOWNLOAD = 800_000_000


def native_path(path):
    # This entry is deliberately a single downloaded file; mirror the verified
    # transaction core's filesystem adapter until that core has been extracted.
    value = os.path.abspath(os.fspath(path))
    if os.name == 'nt' and not value.startswith('\\\\?\\'):
        value = '\\\\?\\UNC\\' + value[2:] if value.startswith('\\\\') else '\\\\?\\' + value
    return Path(value)


def logical_path(path):
    value = os.fspath(path)
    if os.name == 'nt':
        if value.startswith('\\\\?\\UNC\\'):
            value = '\\\\' + value[8:]
        elif value.startswith('\\\\?\\'):
            value = value[4:]
    return Path(value)


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(native_path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with native_path(path).open('rb') as stream:
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
    root = logical_path(native_path(root).resolve())
    current = root
    for part in parts:
        current = current / part
        check = native_path(current)
        require(not check.is_symlink() and not (hasattr(check, 'is_junction') and check.is_junction()),
                '升级目录不能经过链接')
    require(logical_path(native_path(current).resolve()).is_relative_to(root), '升级目录越界')
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
    policy = bootstrap.get('project_compatibility')
    if policy is not None:
        require(policy == {'schema': 1, 'edition': 'haike-workflow-2',
                           'platform': 'windows-x64', 'data_schema': 1}, '海客项目兼容策略无效')
    limit = MAX_DOWNLOAD if policy else 200_000_000
    bases = bootstrap.get('modern_bases', [])
    require(isinstance(bases, list) and len(bases) <= 32, '运行依赖迁移基线清单无效')
    seen_bases = set()
    for base in bases:
        require(isinstance(base, dict) and isinstance(base.get('source_commit'), str)
                and re.fullmatch('[0-9a-f]{40}', base['source_commit'])
                and version(base.get('version')) < version(value['version']), '迁移基线版本或提交无效')
        identity = (base['version'], base['source_commit'])
        require(identity not in seen_bases, '迁移基线重复'); seen_bases.add(identity)
    for key in ('program', 'resources'):
        asset = bootstrap[key]
        parsed = https(asset['url'])
        require(parsed.netloc in {'github.com', 'api.github.com'}, '更新资产必须由GitHub托管')
        if parsed.netloc == 'github.com':
            require(parsed.path.startswith('/' + REPOSITORY + '/releases/download/'), '公开更新资产不属于官方仓库')
        require(type(asset.get('size')) is int and 0 < asset['size'] <= limit
                and re.fullmatch('[a-f0-9]{64}', asset.get('sha256', '')), '下载大小或摘要无效')
        require(asset.get('authentication') in {None, 'github-cli'}, '资源认证方式不支持')
    require(sum(bootstrap[k]['size'] for k in ('program', 'resources')) <= limit,
            '首次升级下载总量超过' + str(limit // 1_000_000) + 'MB')
    if value.get('template_capability') is not None:
        validate_template_capability(value['template_capability'])
    return value


def validate_template_capability(value):
    require(isinstance(value, dict) and value.get('schema') == 'haike.motion-capability/1'
            and isinstance(value.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', value['sha256'])
            and isinstance(value.get('presets'), list) and 0 < len(value['presets']) <= 100,
            '发行模板能力身份无效')
    ids = set()
    for row in value['presets']:
        require(isinstance(row, dict) and isinstance(row.get('id'), str)
                and re.fullmatch('[a-z0-9-]{4,80}', row['id']) and row['id'] not in ids
                and isinstance(row.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', row['sha256'])
                and type(row.get('requires_package')) is bool and isinstance(row.get('protocol'), str),
                '发行预设身份无效或重复')
        version(row.get('version')); ids.add(row['id'])


def verify_template_capability(root, expected=None, *, required=None):
    """The single-file bootstrap must verify bytes without executing target code."""
    if expected is None:
        expected = read(root / 'RELEASE.json').get('template_capability')
    if expected is None:
        require(required is None, '当前版本缺少本次模板能力，请安装修复发行版')
        return {'status': 'not-declared'}
    validate_template_capability(expected)
    path = safe(root, 'Haike_video/templates/motion-presets/delivery.json')
    require(native_path(path).is_file() and native_path(path).stat().st_size <= 2_000_000 and sha(path) == expected['sha256'],
            '模板交付清单缺失或已改变，不能报告已更新；请安装修复发行版')
    value = read(path)
    files = value.get('files')
    require(value.get('schema') == 'haike.motion-capability/1' and isinstance(files, dict)
            and 1 <= len(files) <= 20000 and value.get('presets') == expected['presets']
            and value.get('sha256') == hashlib.sha256(json.dumps(files, sort_keys=True,
                separators=(',', ':')).encode()).hexdigest(), '模板交付清单内容无效')
    forbidden = {'.local', '.backlot', '.venv', 'runtime', 'node_modules', 'projects', 'data', 'config', '.git'}
    for name, digest in files.items():
        require(isinstance(name, str) and not forbidden.intersection(name.casefold().split('/'))
                and name.startswith(('Haike_video/', 'portable/', 'scripts/', 'prototypes/haike-avatar-generator/'))
                and isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest), '模板交付路径或摘要无效')
        file = safe(root, name)
        require(native_path(file).is_file() and sha(file) == digest, '模板文件缺失或已改变：' + name + '；请安装修复发行版')
    if required is not None:
        validate_template_capability(required)
        actual = {r['id']: r for r in value['presets']}
        require(all(r['id'] in actual and version(actual[r['id']]['version']) >= version(r['version'])
                    and actual[r['id']]['protocol'] == r['protocol'] for r in required['presets']),
                '当前版本没有本次所需的正式预设，请安装修复发行版')
    return {'status': 'verified', 'presets': value['presets'], 'verified_files': len(files),
            'episode_inputs': 'user-provided', 'runtime_selftest': 'pending'}


def confirm_template_runtime(root, delivery, queue_guard=None):
    if delivery.get('status') != 'verified':
        return delivery
    manifest = read(safe(root, 'Haike_video/templates/motion-presets/delivery.json'))
    require('portable/audio_update_guard.py' in manifest.get('files', {}),
            '音色核对模块缺少本次交付身份，请安装修复发行版')
    guard_spec = importlib.util.spec_from_file_location('haike_verified_audio_guard',
        safe(root, 'portable/audio_update_guard.py'))
    guard = importlib.util.module_from_spec(guard_spec); guard_spec.loader.exec_module(guard)
    guard.reconcile(root)
    idle(root, queue_guard=queue_guard, audio_guard=guard)
    # The verifier and its public imports were hash-checked above. Only now may
    # the single-file entry execute installed code, with no inherited Python path.
    result = subprocess.run([str(root / 'runtime/python/python.exe'), '-s',
        str(root / 'portable/template_capability.py'), '--root', str(root), '--selftest'],
        cwd=root, capture_output=True, encoding='utf-8', timeout=240, env=python_environment())
    require(result.returncode == 0, '模板安装自检失败，请保留更新备份：' + result.stderr[-1000:])
    value = json.loads(result.stdout.strip().splitlines()[-1])
    require(value.get('status') == 'verified' and value.get('runtime_selftest') == 'passed',
            '程序文件已核验，但模板运行自检尚未通过')
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
            native_path(destination.parent).mkdir(parents=True, exist_ok=True)
            native_path(destination).write_bytes(zipped.read(item))
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
        return release.get('edition') == 'haike-workflow-2'
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


def queue_idle(root, queue_guard=None):
    queue = safe(root, 'Haike_video/.backlot/production-queue.sqlite3')
    if queue_guard is not None:
        queue_guard.require_idle(queue)
    elif queue.is_file():
        with closing(sqlite3.connect(queue.as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='production_jobs'").fetchone():
                require(not db.execute("SELECT 1 FROM production_jobs WHERE status NOT IN ('completed','failed','cancelled') OR status IS NULL LIMIT 1").fetchone(),
                        '请先完成或核对制作队列中的任务，再更新；原任务保留')


def audio_idle(root, audio_guard=None):
    if audio_guard is not None:
        audio_guard.require_idle(root)
        return
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


def idle_blockers(root, queue_guard=None, audio_guard=None):
    blockers = []
    for name, check in [('制作队列', lambda: queue_idle(root, queue_guard)),
                        ('音色操作', lambda: audio_idle(root, audio_guard))]:
        try:
            check()
        except ValueError as error:
            blockers.append(str(error))
        except (OSError, sqlite3.Error):
            blockers.append(name + '记录暂无法安全检查，原数据已保留')
    return blockers


def idle(root, queue_guard=None, audio_guard=None):
    blockers = idle_blockers(root, queue_guard, audio_guard)
    require(not blockers, '；'.join(blockers))


def stop_legacy(root, queue_guard=None, audio_guard=None):
    idle(root, queue_guard=queue_guard, audio_guard=audio_guard)
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
    environment.pop('PYTHONPATH', None)
    environment.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONNOUSERSITE='1')
    return environment


def ensure_no_pending_update(root):
    directory = safe(root, '.local/app-updates')
    state = safe(root, '.local/app-updates/state.json')
    if state.is_file():
        require(read(state).get('operation', {}).get('status') not in
                {'downloading', 'waiting', 'installing', 'restarting'}, '已有更新任务，请查询原更新记录，不要重复启动')
    for file in directory.glob('*/receipt.json'):
        value = read(safe(root, file.relative_to(root).as_posix()))
        preparation = value.get('program_changes_started') is False and value.get('status') in {'preparing', 'prepared', 'preparation_failed'}
        require(preparation or value.get('status') in {'complete', 'restored', 'rolled_back'},
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
            stop_legacy(root, queue_guard=getattr(installer, 'queue_module', lambda: None)(),
                audio_guard=getattr(installer, 'audio_module', lambda: None)())
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
    project_mode = bool(feed['bootstrap'].get('project_compatibility'))
    release = read(root / 'RELEASE.json')
    current = release.get('version')
    if current and version(current) >= version(feed['version']) and (not project_mode or version(current) > version(feed['version'])):
        expected = feed.get('template_capability') if current == feed['version'] else release.get('template_capability')
        try:
            delivery = verify_template_capability(root, expected, required=feed.get('template_capability'))
            if not check:
                delivery = confirm_template_runtime(root, delivery)
        except ValueError:
            if not project_mode or version(current) > version(feed['version']):
                raise
        else:
            return {'ok': True, 'already_current': True, 'version': current, 'template_delivery': delivery}
    migration = current and any(b.get('version') == current and b.get('source_commit') == release.get('source_commit')
                                for b in feed['bootstrap'].get('modern_bases', []))
    if current and not migration and not project_mode:
        if check:
            return {'ok': True, 'mode': 'application-updater', 'current': current, 'target': feed['version']}
        result = modern_update(root, feed['version'])
        result['template_delivery'] = confirm_template_runtime(root, verify_template_capability(root, feed.get('template_capability')))
        return result
    require(project_mode or migration or release['source_commit'] == BASE_SOURCE, '此发行版不支持当前旧安装')
    bootstrap = feed['bootstrap']
    if check and not project_mode:
        return {'ok': True, 'mode': 'runtime-migration' if migration else '1027-bootstrap', 'version': feed['version'],
                'download_bytes': sum(bootstrap[k]['size'] for k in ('program', 'resources'))}
    # Acquire and verify both archives before stopping any service.
    program = fetch_asset(root, bootstrap['program'])
    bundle = extract_program(root, program)
    plan = read(bundle / 'UPGRADE.json')
    require(plan['release']['version'] == feed['version']
            and plan['resources']['sha256'] == bootstrap['resources']['sha256'], '联网清单与已验证程序包不一致')
    require(plan['release'].get('template_capability') == feed.get('template_capability'),
            '联网清单与程序包的模板能力不一致')
    require([{k: b[k] for k in ('version', 'source_commit')} for b in plan.get('modern_bases', [])]
            == feed['bootstrap'].get('modern_bases', []), '联网清单与程序包的迁移基线不一致')
    require(plan.get('project_compatibility') == bootstrap.get('project_compatibility'), '程序包与项目兼容策略不一致')
    dependency_plan = None
    # Execute only the verified archive's own preflight before stopping the
    # running old server; apply() repeats all checks under its transaction lock.
    previous_path = list(sys.path)
    previous_core = sys.modules.pop('release_core', None)
    try:
        sys.path.insert(0, str(bundle))
        spec = importlib.util.spec_from_file_location('haike_online_installer', bundle / 'legacy_upgrade.py')
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        queue_guard = getattr(installer, 'queue_module', lambda: None)()
        audio_guard = getattr(installer, 'audio_module', lambda: None)()
        if project_mode:
            installer.project_identity(root, release, bootstrap['project_compatibility'])
            dependency = installer.dependency_module()
            report = dependency.inspect(root)
            installed_guard = safe(root, 'portable/queue_update_guard.py')
            revision_current = release.get('updater_revision', 0) >= feed.get('updater_revision', 0)
            guard_current = queue_guard is None or (installed_guard.is_file() and sha(installed_guard) == sha(bundle / 'queue_update_guard.py'))
            installed_audio = safe(root, 'portable/audio_update_guard.py')
            guard_current = guard_current and (audio_guard is None or (installed_audio.is_file()
                and sha(installed_audio) == sha(bundle / 'audio_update_guard.py')))
            if current == feed['version'] and not report['missing'] and revision_current and guard_current:
                try:
                    delivery = verify_template_capability(root, feed.get('template_capability'))
                    if not check:
                        delivery = confirm_template_runtime(root, delivery, queue_guard=queue_guard)
                except ValueError:
                    pass  # Same-version repair can restore missing template files.
                else:
                    return {'ok': True, 'already_current': True, 'version': current,
                            'dependencies': report, 'template_delivery': delivery}
            if check:
                blockers = idle_blockers(root, queue_guard=queue_guard, audio_guard=audio_guard)
                return {'ok': not blockers, 'check_only': True, 'mode': 'project-compatible',
                    'current': current, 'target': feed['version'], 'source_commit': release.get('source_commit'),
                    'dependencies': report, 'blockers': blockers, 'can_repair_dependencies': True,
                    'held_jobs_preserved': len(queue_guard.inspect(safe(root, 'Haike_video/.backlot/production-queue.sqlite3'))['held']) if queue_guard else 0,
                    'held_audio_preserved': len(audio_guard.inspect(root)['held']) if audio_guard else 0}
        installer.reconcile_audio(root)
        idle(root, queue_guard=queue_guard, audio_guard=audio_guard)
        if project_mode:
            dependency_plan = dependency.prepare(root, bundle, report)
        resources = fetch_asset(root, bootstrap['resources'])
        installer.preflight(bundle, root, resources, require_stopped=False, dependency_plan=dependency_plan)
    finally:
        sys.path[:] = previous_path
        sys.modules.pop('release_core', None)
        if previous_core is not None:
            sys.modules['release_core'] = previous_core
    command = [sys.executable, '-s', str(bundle / 'legacy_upgrade.py'),
               '--target', str(root), '--resources', str(resources)]
    if dependency_plan:
        command.extend(['--dependency-plan', str(dependency_plan)])
    # Full installer preflight follows immediately; only this target's idle
    # video server is stopped. Publisher and other installations keep running.
    stop_legacy(root, queue_guard=queue_guard, audio_guard=audio_guard)
    result = subprocess.run(command, capture_output=True, encoding='utf-8', timeout=600,
                            env=python_environment())
    if result.returncode:
        reverted = read(root / 'RELEASE.json')
        if reverted.get('source_commit') == release.get('source_commit') and reverted.get('version') == current:
            subprocess.run([str(root / 'runtime/python/python.exe'), '-s', str(root / 'portable/portable.py'),
                'start', '--no-browser'], capture_output=True, timeout=240, env=python_environment())
        raise ValueError('升级未完成，原程序或备份已保留：' + result.stderr[-1200:])
    output = json.loads(result.stdout)
    require(output.get('ok') and read(root / 'RELEASE.json')['version'] == feed['version'], '未确认安装结果')
    if start:
        finish_bootstrap_start(root, output, installer)
    output['mode'] = 'github-project-compatible' if project_mode else 'github-runtime-migration' if migration else 'github-online-bootstrap'
    output['template_delivery'] = confirm_template_runtime(root, verify_template_capability(root, feed.get('template_capability')), queue_guard=queue_guard)
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
