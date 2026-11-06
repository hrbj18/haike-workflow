"""Detached source transaction, reusing the existing admission and restart guard."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit

try:
    from . import app_update as core, source_app_update as source, update_worker as worker
    from .update_service import (UpdateCancelled, current_release, private_path, read_json,
                                 remote_open, set_operation, write_json)
except ImportError:
    import app_update as core
    import source_app_update as source
    import update_worker as worker
    from update_service import (UpdateCancelled, current_release, private_path, read_json,
                                remote_open, set_operation, write_json)


def publisher_identity(root, base):
    base = worker.local_url(base)
    health = worker.local_get(base, '/health')
    expected = hashlib.sha256(str((Path(root) / 'creatorhub').resolve()).replace('\\', '/').casefold().encode()).hexdigest()
    if (health.get('status') != 'ok' or health.get('service_fingerprint') != expected
            or not isinstance(health.get('pid'), int) or health['pid'] <= 1
            or health['pid'] == os.getpid() or not health.get('instance_id')):
        raise core.UpdateError('账号服务缺少可核对的更新身份，请先让 Agent 完成一次最新版接入。')
    return health


def stop_publisher(root, base, expected):
    actual = publisher_identity(root, base)
    if any(actual.get(key) != expected.get(key) for key in ('pid', 'instance_id', 'service_fingerprint')):
        raise core.UpdateError('账号服务身份已变化，未停止该服务。')
    if actual.get('update_inflight') != 0:
        raise core.UpdateError('账号服务仍有请求处理，已延后更新，原任务保留。')
    os.kill(actual['pid'], signal.SIGTERM)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            health = worker.local_get(base, '/health')
        except (OSError, ValueError):
            return
        if health.get('instance_id') != actual['instance_id']:
            raise core.UpdateError('账号服务端口出现其他实例，已停止更新。')
        time.sleep(.25)
    raise core.UpdateError('原账号服务尚未退出。')


def start_publisher(root, base, previous_instance=None):
    try:
        existing = worker.local_get(base, '/health')
    except (OSError, ValueError):
        existing = None
    if existing is not None:
        raise core.UpdateError('账号服务端口仍有实例，未启动第二个服务。')
    module = Path(root) / 'creatorhub'
    py = module / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    flags = (getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)) if os.name == 'nt' else 0
    with private_path(root, 'publisher-restart.log').open('ab') as log:
        child = subprocess.Popen([str(py), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                                  '--port', str(urlsplit(base).port or 80)], cwd=module,
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 creationflags=flags, start_new_session=os.name != 'nt')
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            identity = publisher_identity(root, base)
            # A Windows venv launcher can have a child PID; workspace identity
            # and the unique instance below establish ownership after startup.
            if identity['instance_id'] != previous_instance:
                return child, identity
            time.sleep(.5)
        except (OSError, ValueError):
            if child.poll() is not None:
                break
            time.sleep(.5)
    worker.terminate_started(child)
    raise core.UpdateError('账号服务重启检查未通过。')


def record_mac_services(root, base, health, publisher_base):
    path = Path(root) / '.local/mac-services.json'
    if sys.platform != 'darwin' or not path.is_file():
        return
    state = read_json(path)
    if Path(state.get('root', '')).resolve() != Path(root).resolve():
        return
    try:
        publisher = publisher_identity(root, publisher_base) if publisher_base else None
    except (OSError, ValueError):
        publisher = None
    state.update(studio_port=urlsplit(base).port or 80, studio_pid=health['pid'],
                 pids=([publisher['pid']] if publisher else []) + [health['pid']])
    if publisher:
        state.update(publisher_port=urlsplit(publisher_base).port or 80, publisher_pid=publisher['pid'])
    write_json(path, state)


def restore_program(root, receipt, folder):
    """No force: preserve any edits made concurrently, including index changes."""
    if (not source.SHA.fullmatch(receipt.get('base_commit', ''))
            or not source.SHA.fullmatch(receipt.get('source_commit', ''))
            or receipt.get('base_branch', '') not in {'', 'main'}):
        raise core.UpdateError('源码回退提交/分支身份无效。')
    current = source.git(root, 'rev-parse', 'HEAD').stdout.strip()
    if current not in {receipt['base_commit'], receipt['source_commit']}:
        raise core.UpdateError('源码已被其他操作切换，保留现场；请让 Agent 核对回退。')
    if source.git(root, 'status', '--porcelain', '--untracked-files=normal').stdout.strip():
        raise core.UpdateError('更新期间出现本地修改，保留工作树和 index；请让 Agent 核对回退。')
    source.switch(root, receipt['base_commit'])
    if receipt.get('dependencies_started'):
        source.restore_dependencies(root, receipt.get('python_inventory', []), folder)
        source.refresh(root, receipt['source_commit'], dependencies_only=True)
        source.restore_dependencies(root, receipt.get('python_inventory', []), folder)
    for row in receipt.get('metadata', []):
        if row['path'] == '.local/mac-motion-runtime.json':
            saved = core.safe_path(Path(folder) / 'metadata', row['path'])
            if core.digest(saved) != row['sha256']:
                raise core.UpdateError('原生运行时绑定备份摘要不匹配。')
            shutil.copyfile(saved, core.safe_path(Path(root), row['path']))
    saved_ui = Path(folder) / 'ui'
    if saved_ui.is_dir():
        shutil.copytree(saved_ui, Path(root) / 'Haike_video/backlot/ui/avatar-generator', dirs_exist_ok=True)
    branch = receipt.get('base_branch')
    if branch and source.git(root, 'rev-parse', 'refs/heads/' + branch).stdout.strip() == receipt['base_commit']:
        source.git(root, 'checkout', branch)


def manual_rollback(root, folder, port):
    root, folder = Path(root).resolve(), Path(folder).resolve()
    if folder.parent != private_path(root).parent:
        raise core.UpdateError('回退目录不属于本副本的源码更新。')
    receipt = read_json(folder / 'receipt.json')
    if receipt.get('kind') != 'source' or receipt.get('installation') != str(root):
        raise core.UpdateError('源码回退回执身份不匹配。')
    publisher = receipt.get('publisher_base')
    restart_publisher = receipt.get('publisher_restarted', bool(publisher))
    if publisher and restart_publisher:
        try:
            worker.local_get(publisher, '/health')
        except (OSError, ValueError):
            pass
        else:
            raise core.UpdateError('请先核对并关闭本副本账号服务，再执行源码回退；未停止任何进程。')
    with core._install_lock(root):
        restore_program(root, receipt, folder)
        receipt['status'] = 'rolled_back'
        write_json(folder / 'receipt.json', receipt)
        if publisher and restart_publisher:
            start_publisher(root, publisher)
        child = worker.start_server(root, port, publisher_base=publisher)
        base = 'http://127.0.0.1:' + str(port)
        health = worker.wait_server(base, root, child, receipt['base_version'], source_commit=receipt['base_commit'])
        record_mac_services(root, base, health, publisher)
        set_operation(root, 'rolled_back', '已人工恢复并启动原源码，原数据和素材保留。')
    return {'ok': True, 'status': 'rolled_back', 'source_commit': receipt['base_commit'], 'media_copied': False}


def run_source_update(root, identity):
    root = Path(root).resolve()
    folder = private_path(root, identity + '/operation.json').parent
    command = read_json(folder / 'operation.json')
    if command.get('id') != identity:
        raise core.UpdateError('源码更新任务身份无效。')
    candidate = command['candidate']
    base = worker.local_url(command['base_url'])
    port = urlsplit(base).port or 80
    publisher_base = worker.local_url(os.environ.get('HAIKE_CREATORHUB_URL', 'http://127.0.0.1:8000'))
    receipt = None
    stopped = publisher_stopped = False
    child = publisher_child = None
    publisher_new_identity = None
    previous_version = current_release(root)['version']

    def update(status, message, **fields):
        return set_operation(root, status, message, expected_id=identity, **fields)

    with core._install_lock(root):
        try:
            source.validate(candidate, current_release(root))
            previous = source.prepare(root, candidate, remote_open)
            changed = source.git(root, 'diff', '--name-only', candidate['base_commit'], candidate['source_commit']).stdout.splitlines()
            publisher_changed = any(name.startswith('creatorhub/') or
                                    (name.startswith('_distribution-tools/locks/') and 'creatorhub' in name) for name in changed)
            publisher_old_identity = publisher_identity(root, publisher_base) if publisher_changed else None
            update('waiting', '源码已固定，正在等待制作、下载和发布任务结束。', progress=100)
            deadline = time.monotonic() + 1800
            while time.monotonic() < deadline:
                ready = worker.local_get(base, '/api/studio/app-update/readiness', command['token'])
                if ready.get('ready'):
                    break
                update('waiting', ready.get('message') or '正在等待现有任务结束。')
                time.sleep(2)
            else:
                raise core.UpdateError('任务仍未结束，本次源码更新已延后，原程序未修改。')
            update('installing', '正在备份配置和任务记录、安装源码；原视频素材保留在原位置。')
            if not worker.local_get(base, '/api/studio/app-update/readiness', command['token']).get('ready'):
                raise core.UpdateError('仍有任务运行，原程序未修改。')
            state = source.inspect(root)
            if not state['can_install'] or state['head'] != candidate['base_commit']:
                raise core.UpdateError(state.get('reason') or '当前源码已变化，原程序未修改。')
            worker.stop_verified(base, root, command['instance_id'], command['server_pid'])
            stopped = True
            if publisher_changed:
                stop_publisher(root, publisher_base, publisher_old_identity)
                publisher_stopped = True
            metadata = source.backup_metadata(root, folder)
            python_inventory = source.dependency_inventory(root)
            ui = root / 'Haike_video/backlot/ui/avatar-generator'
            if ui.is_dir():
                shutil.copytree(ui, folder / 'ui')
            source.git(root, 'update-ref', 'refs/haike-updates/' + identity + '/previous', candidate['base_commit'])
            receipt = dict(kind='source', status='prepared', backup_complete=True, installation=str(root),
                           version=candidate['version'], base_version=previous_version,
                           source_commit=candidate['source_commit'], base_commit=candidate['base_commit'],
                           base_branch=previous['branch'], metadata=metadata, media_copied=False,
                           python_inventory=python_inventory,
                           publisher_base=publisher_base, publisher_restarted=publisher_changed)
            write_json(folder / 'receipt.json', receipt)
            source.switch(root, candidate['source_commit'])
            receipt.update(status='applying', dependencies_started=True)
            write_json(folder / 'receipt.json', receipt)
            source.refresh(root, candidate['base_commit'])
            update('restarting', '正在启动新版并核对提交、模板和页面。')
            if publisher_stopped:
                publisher_child, publisher_new_identity = start_publisher(root, publisher_base, publisher_old_identity['instance_id'])
            child = worker.start_server(root, port, publisher_base=publisher_base)
            health = worker.wait_server(base, root, child, candidate['version'], source_commit=candidate['source_commit'],
                                        previous_instance=command['instance_id'])
            record_mac_services(root, base, health, publisher_base)
            receipt['status'] = 'complete'
            write_json(folder / 'receipt.json', receipt)
            update('complete', '源码更新完成，原配置、账号、草稿、任务和作品已保留。', progress=100)
        except UpdateCancelled:
            return
        except Exception as exc:
            # Stop only the instances started by this operation before rollback.
            if child is not None:
                try:
                    health = worker.local_get(base, '/api/health')
                    if worker.matches(health, root) and health.get('instance_id') != command['instance_id']:
                        worker.stop_verified(base, root, health['instance_id'], health['pid'])
                except (OSError, ValueError):
                    pass
                worker.terminate_started(child)
            if publisher_new_identity:
                stop_publisher(root, publisher_base, publisher_new_identity)
            try:
                if receipt:
                    restore_program(root, receipt, folder)
                    receipt['status'] = 'rolled_back'
                    write_json(folder / 'receipt.json', receipt)
                if publisher_stopped:
                    start_publisher(root, publisher_base)
                if stopped:
                    child = worker.start_server(root, port, publisher_base=publisher_base)
                    health = worker.wait_server(base, root, child, previous_version, source_commit=candidate['base_commit'])
                    record_mac_services(root, base, health, publisher_base)
                    update('rolled_back', '更新未完成，已恢复并启动原源码；原数据和素材保留。')
                    return
                update('failed', str(exc) if isinstance(exc, core.UpdateError) else '源码取得或检查失败，原程序未修改，请检查网络后重试。')
            except Exception:
                update('failed', '源码更新中断，保留了回退提交和元数据备份。请让 Agent 按更新回执恢复；不要重复安装。')
            raise
