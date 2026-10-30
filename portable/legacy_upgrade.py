"""Offline, transactional bootstrap from the original 1027 delivery to 1.2.

Run with the destination's bundled Python. Both distribution archives are
validated before any installed file is changed. No pip, npm or network calls.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import zipfile

try:
    from release_core import safe_path, digest, json_bytes, _atomic_write, _parts, is_program_path
except ModuleNotFoundError:
    from app_update import safe_path, digest, json_bytes, _atomic_write, _parts, is_program_path

ID = '1027-to-1.2'
METADATA = {'VERSION.json', 'RELEASE.json', 'PACKAGE-MANIFEST.json', 'RUNTIME-INVENTORY.json'}
CACHE = '.local/md/shared-1.2/'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def require(value, message):
    if not value:
        raise ValueError(message)


@contextmanager
def database(path, readonly=False):
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) if readonly else sqlite3.connect(path, timeout=30)
    try:
        with db:
            yield db
    finally:
        db.close()


def allowed(name, resource=False):
    _parts(name)
    if not resource:
        return is_program_path(name) or name in METADATA or name in {
            'Haike_video/remotion-composer/package.json',
            'Haike_video/remotion-composer/package-lock.json'}
    return (name.startswith('Haike_video/remotion-composer/node_modules/')
            or name.startswith(CACHE)
            or re.fullmatch(r'\.local/motiongit/packages/mg-[a-f0-9]{24}/original\.motion', name)
            or name == '.local/motiongit/tools/1.0.0-rc.50/motion.mjs')


def stopped(target):
    # CIM checks cover manually launched servers as well as portable launchers.
    # A failure to inspect processes must not permit editing a running install.
    if os.name == 'nt':
        command = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                   "Select-Object ProcessId,CommandLine,ExecutablePath | ConvertTo-Json -Compress")
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                                capture_output=True, text=True, timeout=30)
        require(result.returncode == 0, '无法检查目标服务，请先关闭后台服务后重试')
        rows = json.loads(result.stdout) if result.stdout.strip() else []
        if isinstance(rows, dict):
            rows = [rows]
        prefix = str(target).casefold() + '\\'
        for row in rows:
            cmd = (row.get('CommandLine') or '').casefold()
            exe = (row.get('ExecutablePath') or '').casefold()
            if row['ProcessId'] != os.getpid() and exe.startswith(prefix) and 'backlot' in cmd and 'serve' in cmd:
                raise ValueError('目标工作台后台仍在运行，请关闭目标副本后台后重试；其他副本无需关闭')
    queue = safe_path(target, 'Haike_video/.backlot/production-queue.sqlite3')
    if queue.is_file():
        with database(queue, readonly=True) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='production_jobs'").fetchone()
            if exists:
                count = db.execute("SELECT COUNT(*) FROM production_jobs WHERE status IN ('queued','running')").fetchone()[0]
                require(not count, '目标副本有排队或执行中的制作任务，请先完成或暂停任务')


@contextmanager
def lock(target):
    import msvcrt
    path = safe_path(target, '.local/release-updates/install.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise ValueError('另一个升级或回退正在执行') from exc
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def archive_manifest(archive, name):
    require(len(archive.infolist()) <= 30000, '资源包文件数量超限')
    seen = set()
    for info in archive.infolist():
        _parts(info.filename)
        require(info.filename.casefold() not in seen, '资源包有重复路径')
        seen.add(info.filename.casefold())
        require(info.file_size < 400_000_000 and ((info.external_attr >> 16) & 0o170000) != 0o120000,
                '资源包含超大文件或链接')
    require(archive.getinfo(name).file_size < 24_000_000, '资源清单过大')
    return json.loads(archive.read(name))


def data_for(row, bundle, target, archive):
    if row.get('payload'):
        return safe_path(bundle, row['payload']).read_bytes()
    if row.get('reuse_from'):
        return safe_path(target, row['reuse_from']).read_bytes()
    return archive.read(row['blob'])


def preflight(bundle, target, resource):
    target = target.resolve(strict=True)
    require(not (target / '.git').exists(), '请选择已安装的1027便携目录，不能升级源码仓库')
    require((target / 'runtime/python/python.exe').is_file(), '目标目录缺少包内Python运行时')
    plan = read(bundle / 'UPGRADE.json')
    require(plan.get('id') == ID and plan.get('schema') == 1, '更新清单不适用')
    require(resource.is_file() and digest(resource) == plan['resources']['sha256'], '模板资源包缺失或摘要不符')
    release = read(target / 'RELEASE.json')
    current = release.get('version') == '1.2.0' and release.get('upgrade_id') == ID
    if current:
        require(release.get('source_commit') == plan['release']['source_commit'], '已安装其他1.2构建，不能覆盖')
    else:
        require(release.get('source_commit') == plan['base_source_commit'] and not release.get('version'),
                '此包仅用于原始1027（1.1）安装，当前版本不匹配')
        require(digest(target / 'PACKAGE-MANIFEST.json') == plan['base_manifest_sha256'],
                '目标不是原始1027清单，已停止以避免覆盖其他版本')
    pending = safe_path(target, '.local/release-updates')
    if pending.exists():
        for receipt in pending.glob('*/receipt.json'):
            require(read(receipt).get('status') not in {'installing', 'rollback_failed'},
                    '上次升级未完成，请先使用回执目录执行回退：' + str(receipt.parent))
    with zipfile.ZipFile(resource) as archive:
        resources = archive_manifest(archive, 'RESOURCES.json')
        require(resources.get('id') == ID, '模板包与程序包不匹配')
        rows = [{**row, 'resource': False} for row in plan['files']] + [
            {**row, 'resource': True} for row in resources['files']]
        names = set()
        for row in rows:
            name = row['path']
            require(allowed(name, row['resource']), '更新路径不在允许范围：' + name)
            require(name.casefold() not in names, '更新目标路径重复')
            names.add(name.casefold())
            require(re.fullmatch('[a-f0-9]{64}', row['sha256']) and 0 <= row['size'] < 400_000_000,
                    '更新文件大小或摘要无效')
        require(sum(row['size'] for row in rows) < 2_000_000_000, '解压内容过大')
        # Validate payload bytes and ALL overwritten files before writing.
        def verify(row):
            content = data_for(row, bundle, target, archive)
            require(len(content) == row['size'] and hashlib.sha256(content).hexdigest() == row['sha256'],
                    '更新文件或复用依赖损坏：' + row['path'])
            destination = safe_path(target, row['path'])
            if destination.exists():
                require(destination.is_file(), '目标路径不是文件：' + row['path'])
                actual = digest(destination)
                require(actual == row['sha256'] or (not current and actual == row.get('before_sha256')),
                        '目标文件有本地修改，已停止保留：' + row['path'])
            elif current:
                raise ValueError('已安装1.2的文件缺失：' + row['path'])
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(verify, rows))
        if not current:
            def dependency(row):
                file = safe_path(target, row['path'])
                require(file.is_file() and digest(file) == row['sha256'], '旧版依赖不匹配：' + row['path'])
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(dependency, plan['required_files']))
        require(shutil.disk_usage(target).free > sum(row['size'] for row in rows) + 600_000_000,
                '目标磁盘空间不足，请保留至少解压体积加600MB')
    stopped(target)
    cfg = safe_path(target, CACHE + '.venv/pyvenv.cfg')
    require(current or not cfg.exists(), '共享依赖目录已经有本机配置，请先核对，不能覆盖')
    if current:
        registry_path = safe_path(target, '.local/motiongit/registry.sqlite3')
        require(registry_path.is_file(), '已安装模板登记缺失')
        with database(registry_path, readonly=True) as db:
            for package in resources['packages']:
                found = db.execute('SELECT data FROM packages WHERE id=?', (package['id'],)).fetchone()
                require(found and json.loads(found[0]).get('sha256') == package['sha256'], '已安装模板登记不匹配')
    return plan, resources, rows, current


def registry(target, records, *, restoring=False):
    path = safe_path(target, '.local/motiongit/registry.sqlite3')
    path.parent.mkdir(parents=True, exist_ok=True)
    with database(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS packages(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
        for row in records:
            value = row['before'] if restoring else row['after']
            if value is None:
                db.execute('DELETE FROM packages WHERE id=?', (row['id'],))
            else:
                db.execute('INSERT OR REPLACE INTO packages VALUES(?,?)', (row['id'], value))


def registry_records(target, packages):
    path = safe_path(target, '.local/motiongit/registry.sqlite3')
    result = []
    for package in packages:
        value = dict(package)
        value.update(path=str(safe_path(target, '.local/motiongit/packages/' + value['id'] + '/original.motion')),
                     helper=str(safe_path(target, '.local/motiongit/tools/1.0.0-rc.50/motion.mjs')),
                     dependency_cache=CACHE.rstrip('/'))
        before = None
        if path.is_file():
            with database(path, readonly=True) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='packages'").fetchone():
                    row = db.execute('SELECT data FROM packages WHERE id=?', (value['id'],)).fetchone()
                    before = row[0] if row else None
        # Keep already imported, recipient-specific metadata completely intact.
        result.append({'id': value['id'], 'before': before,
                       'after': before if before is not None else json.dumps(value, ensure_ascii=False)})
    return result


def probe(target):
    code = ("import json,sys; from pathlib import Path; "
            "from backlot import studio_motion_templates as t; "
            "from backlot.server import create_app; "
            "items=t.catalog(); assert len([x for x in items if x['id'].startswith('motiongit-')])>=3; "
            "assert create_app(); import cv2,numpy,scipy,PIL; "
            "print(json.dumps({'ok':True,'templates':[{k:x.get(k) for k in ('id','status')} for x in items]}))")
    environment = os.environ.copy()
    environment.pop('PYTHONHOME', None)
    environment.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONNOUSERSITE='1',
                       HAIKE_PORTABLE_OFFLINE='1', PIP_NO_INDEX='1', NPM_CONFIG_OFFLINE='true')
    cache = safe_path(target, CACHE + '.venv/Lib/site-packages')
    environment['PYTHONPATH'] = os.pathsep.join([str(target / 'Haike_video'),
        str(target / 'Haike_video/.venv/Lib/site-packages'), str(cache)])
    result = subprocess.run([str(target / 'runtime/python/python.exe'), '-s', '-c', code],
                            cwd=target / 'Haike_video', env=environment,
                            capture_output=True, text=True, encoding='utf-8', timeout=120)
    require(result.returncode == 0, '升级后模块/模板/依赖检查失败：' + result.stderr[-1800:])
    return json.loads(result.stdout.strip().splitlines()[-1])


def restore(target, backup, *, automatic=False):
    target, backup = target.resolve(), backup.resolve(strict=True)
    require(backup.is_relative_to(safe_path(target, '.local/release-updates')), '回退记录不属于此安装')
    receipt = read(backup / 'receipt.json')
    require(receipt['target'] == str(target), '回退目录身份不匹配')
    if receipt['status'] == 'restored':
        return {'ok': True, 'already_restored': True}
    stopped(target)
    for row in receipt['files']:
        destination = safe_path(target, row['path'])
        if row['existed']:
            require(digest(safe_path(backup / 'files', row['path'])) == row['before_sha256'], '备份摘要不符')
        if not automatic:
            require(destination.is_file() and digest(destination) == row['after_sha256'],
                    '升级后文件又被修改，已停止回退：' + row['path'])
    if not automatic and receipt.get('registry_applied'):
        with database(safe_path(target, '.local/motiongit/registry.sqlite3')) as db:
            for row in receipt['registry']:
                current = db.execute('SELECT data FROM packages WHERE id=?', (row['id'],)).fetchone()
                require(current and current[0] == row['after'], '模板登记已修改，已停止回退')
    for row in reversed(receipt['files']):
        destination = safe_path(target, row['path'])
        if row['existed']:
            _atomic_write(destination, safe_path(backup / 'files', row['path']).read_bytes())
        else:
            destination.unlink(missing_ok=True)
    if receipt.get('registry_applied'):
        registry(target, receipt['registry'], restoring=True)
    receipt['status'] = 'restored'
    _atomic_write(backup / 'receipt.json', json_bytes(receipt))
    return {'ok': True, 'restored_files': len(receipt['files'])}


def apply(bundle, target, resource, *, check=False, health_check=probe):
    plan, resources, rows, current = preflight(bundle, target, resource)
    if check or current:
        return {'ok': True, 'check_only': check, 'already_current': current,
                'version': '1.2.0' if current else '1.1 / 1027', 'files': len(rows)}
    records = registry_records(target, resources['packages'])
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = safe_path(target, '.local/release-updates/' + ID + '-' + stamp)
    backup.mkdir(parents=True, exist_ok=False)
    writes = []
    manifest = read(target / 'PACKAGE-MANIFEST.json')
    entries = {row['path']: row for row in manifest['files']}
    with zipfile.ZipFile(resource) as archive:
        for row in rows:
            # Reuse inputs are read before writes, even when another entry replaces them.
            content = data_for(row, bundle, target, archive)
            writes.append((row['path'], content))
            if not row['path'].startswith('.local/'):
                entries[row['path']] = {k: row[k] for k in ('path', 'size', 'sha256')}
                entries[row['path']]['mutable'] = False
    runtime = target / 'runtime/python'
    writes.append((CACHE + '.venv/pyvenv.cfg', (
        f'home = {runtime}\ninclude-system-site-packages = false\nexecutable = {runtime / "python.exe"}\n').encode()))
    release = {**read(target / 'RELEASE.json'), **plan['release'], 'upgrade_id': ID,
               'upgraded_from': '20261027 / 1.1', 'resources_sha256': plan['resources']['sha256']}
    version = {k: release[k] for k in ('edition', 'version', 'channel', 'runtime_id', 'data_schema', 'platform')}
    version['display_version'] = '1.2'
    for name, content in [('VERSION.json', json_bytes(version)), ('RELEASE.json', json_bytes(release))]:
        writes.append((name, content))
        entries[name] = {'path': name, 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest(), 'mutable': False}
    inventory_path = target / 'RUNTIME-INVENTORY.json'
    if inventory_path.is_file():
        inventory = read(inventory_path)
        inventory['runtime_origin_source_commit'] = inventory['source_commit']
        inventory['source_commit'] = plan['release']['source_commit']
        content = json_bytes(inventory)
        writes.append(('RUNTIME-INVENTORY.json', content))
        entries['RUNTIME-INVENTORY.json'] = {'path': 'RUNTIME-INVENTORY.json', 'size': len(content),
            'sha256': hashlib.sha256(content).hexdigest(), 'mutable': False}
    manifest['files'] = [entries[name] for name in sorted(entries)]
    writes.append(('PACKAGE-MANIFEST.json', json_bytes(manifest)))
    receipt = {'schema': 1, 'target': str(target), 'id': ID, 'status': 'installing',
               'registry': records, 'registry_applied': False, 'files': []}
    for name, content in writes:
        destination = safe_path(target, name)
        after = hashlib.sha256(content).hexdigest()
        if destination.is_file() and digest(destination) == after:
            continue
        row = {'path': name, 'existed': destination.is_file(), 'after_sha256': after}
        if row['existed']:
            copy = safe_path(backup / 'files', name)
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(destination, copy)
            row['before_sha256'] = digest(copy)
        receipt['files'].append(row)
    _atomic_write(backup / 'receipt.json', json_bytes(receipt))
    try:
        for name, content in writes:
            destination = safe_path(target, name)
            if not destination.is_file() or digest(destination) != hashlib.sha256(content).hexdigest():
                _atomic_write(destination, content)
        # Persist intent first so an interruption inside SQLite is recoverable.
        receipt['registry_applied'] = True
        _atomic_write(backup / 'receipt.json', json_bytes(receipt))
        registry(target, records)
        receipt['probe'] = health_check(target)
        receipt['status'] = 'complete'
        _atomic_write(backup / 'receipt.json', json_bytes(receipt))
    except BaseException:
        try:
            restore(target, backup, automatic=True)
        except Exception:
            receipt['status'] = 'rollback_failed'
            _atomic_write(backup / 'receipt.json', json_bytes(receipt))
        raise
    return {'ok': True, 'version': '1.2.0', 'files_updated': len(receipt['files']),
            'backup': str(backup), 'templates': receipt['probe']['templates'],
            'next': '用原目录02-start.cmd启动，Ctrl+F5刷新；首次制作绑定自己的素材'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, type=Path)
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--resources', type=Path)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    try:
        target, bundle = args.target.resolve(strict=True), args.bundle.resolve(strict=True)
        with lock(target):
            if args.rollback:
                result = restore(target, args.rollback, automatic=read(args.rollback / 'receipt.json')['status'] in {'installing', 'rollback_failed'})
            else:
                plan = read(bundle / 'UPGRADE.json')
                resource = args.resources or bundle.parent / plan['resources']['filename']
                result = apply(bundle, target, resource, check=args.check)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
