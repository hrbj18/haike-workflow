"""Trusted release discovery and durable orchestration for the local updater.

Install candidates come from a configured HTTPS feed or an inspected local ZIP.
Browser requests never supply a URL, path, command, PID or update manifest.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse, request

try:
    from . import app_update as core
except ImportError:  # The detached helper uses a frozen copy of these files.
    import app_update as core

DEFAULT_FEED = "https://github.com/hrbj18/haike-workflow/releases/latest/download/haike-update.json"
ACTIVE = {"downloading", "waiting", "installing", "restarting"}
MAINTENANCE = {"waiting", "installing", "restarting"}
_LOCK = threading.RLock()


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def private_path(root, name="state.json"):
    path = core.safe_path(Path(root), ".local/app-updates/" + name)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return default if default is not None else {}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class UpdateCancelled(core.UpdateError):
    """The original helper must stop without replacing a newer operation."""


@contextmanager
def state_guard(root):
    # Separate from the installer's transaction lock: HTTP cancellation and a
    # detached helper coordinate even when they are in different processes.
    with _LOCK, private_path(root, "operation.lock").open("a+b") as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b"0"); stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def set_operation(root, status, message, expected_id=None, **fields):
    with state_guard(root):
        path = private_path(root)
        state = read_json(path)
        operation = state.setdefault("operation", {})
        if expected_id and (operation.get("id") != expected_id or operation.get("status") == "cancelled"):
            raise UpdateCancelled("本次更新已暂缓")
        if status == "cancelled" and operation.get("status") not in {"downloading", "waiting", "cancelled"}:
            raise core.UpdateError("程序已开始安装，请等待更新与启动检查结束")
        operation.update(status=status, message=message, updated_at=utcnow(), **fields)
        write_json(path, state)
        return operation


def maintenance(root):
    try:
        return (read_json(private_path(root)).get("operation", {}).get("status") in MAINTENANCE
                or bool(core.pending_receipts(root)))
    except (OSError, ValueError):
        # A damaged update record must not silently admit production.
        return True


def https_url(url):
    parsed = parse.urlsplit(str(url))
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.fragment):
        raise core.UpdateError("更新地址必须使用有效的 HTTPS 地址")
    return str(url)


class SecureRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def remote_open(url, timeout=15):
    url = https_url(url)
    req = request.Request(url, headers={"User-Agent": "Haike-Video-Updater/1", "Accept": "application/json, application/octet-stream"})
    return request.build_opener(SecureRedirect()).open(req, timeout=timeout)


def current_release(root):
    root = Path(root)
    value = core.read_release(root)
    source = (root / ".git").exists()
    value.update(package_type="source" if source or not (root / "PACKAGE-MANIFEST.json").is_file() else "portable",
                 development=source, dirty=False)
    if source:
        try:
            options = {"cwd": root, "capture_output": True, "text": True, "timeout": 5,
                       "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            value["source_commit"] = subprocess.run(["git", "rev-parse", "HEAD"], **options).stdout.strip()
            result = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"], **options)
            value["dirty"] = bool(result.stdout.strip()) or result.returncode != 0
        except (OSError, subprocess.SubprocessError):
            value["dirty"] = True
    return value


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 1:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def capability(root, current):
    if current.get("package_type") != "portable" or current.get("development"):
        return {"can_install": False, "reason": "当前为源码开发副本，可检查版本；请通过版本管理更新，避免覆盖本地修改。"}
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
        return {"can_install": False, "reason": "第一版一键更新适用于 Windows x64 便携安装。"}
    installed = read_json(Path(root) / "RELEASE.json")
    if not all(installed.get(key) is not None for key in ("version", "edition", "platform", "runtime_id", "data_schema")):
        return {"can_install": False, "reason": "此旧安装缺少版本信息，请先使用完整新版包迁移。"}
    return {"can_install": True, "reason": ""}


class UpdateService:
    def __init__(self, root, feed_url=None):
        self.root = Path(root).resolve()
        self.feed_url = feed_url or os.environ.get("HAIKE_UPDATE_FEED_URL", DEFAULT_FEED)

    def snapshot(self):
        current = current_release(self.root)
        state = read_json(private_path(self.root))
        update = {k: v for k, v in state.get("update", {"status": "unchecked", "message": "尚未检查更新"}).items()
                  if k not in {"candidate", "feed_url", "local_archive"}}
        cap = capability(self.root, current)
        pending = core.pending_receipts(self.root)
        operation_record = state.get("operation", {})
        if operation_record.get("status") in ACTIVE:
            identity = operation_record.get("id", "")
            if len(identity) == 24 and all(c in "0123456789abcdef" for c in identity):
                command = read_json(private_path(self.root, identity + "/operation.json"))
                updated = datetime.fromisoformat(operation_record.get("updated_at", utcnow()))
                stale = (datetime.now(timezone.utc) - updated).total_seconds() > 120
                if stale and not process_alive(command.get("worker_pid")):
                    committed = False
                    if not pending and current.get("version") == operation_record.get("target_version"):
                        for receipt in private_path(self.root).parent.glob("*/receipt.json"):
                            record = read_json(receipt)
                            if record.get("status") == "complete" and record.get("version") == current.get("version"):
                                committed = True
                                break
                    if committed:
                        set_operation(self.root, "complete", "已确认上次更新完成，新版本已启动，配置、账号和作品已保留。", progress=100)
                    else:
                        set_operation(self.root, "failed", "上次更新助手已中断。请按更新文档恢复备份后重试。" if pending else "上次更新助手已中断，请核对当前版本后重新检查更新。")
                    state = read_json(private_path(self.root))
        if pending:
            cap = {"can_install": False, "reason": "发现尚未恢复的更新，请先按更新文档恢复备份。"}
        update["can_install"] = bool(cap["can_install"] and update.get("status") == "available")
        operation = {k: v for k, v in state.get("operation", {"status": "idle", "message": ""}).items()
                     if k in {"status", "message", "id", "target_version", "progress", "updated_at"}}
        return {"current": current, "update": update, "operation": operation, "capability": cap}

    def check(self):
        with _LOCK:
            state = read_json(private_path(self.root))
            if state.get("operation", {}).get("status") in ACTIVE:
                return self.snapshot()
        current = current_release(self.root)
        try:
            with remote_open(self.feed_url) as response:
                raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise core.UpdateError("版本清单过大，已停止检查")
            candidate = self.validate_candidate(json.loads(raw), current)
            if candidate['package'].get('kind', 'patch') == 'patch' and len(raw)+candidate['package']['size'] > core.MAX_ARCHIVE_BYTES:
                raise core.UpdateError('更新包与清单总大小超过300 MB')
            newer = core.version_tuple(candidate["version"]) > core.version_tuple(current.get("version") or "0.0.0")
            compatible = (candidate["package"].get("kind", "patch") == "patch"
                          and all(candidate.get(k) == current.get(k) for k in ("runtime_id", "data_schema", "platform"))
                          and candidate["base_version"] == current.get("version"))
            status = "available" if newer and compatible else "incompatible" if newer else "current"
            message = {"available": "发现新的稳定版本", "incompatible": "此版本需要完整升级，请按发行说明迁移。", "current": "当前已是最新稳定版"}[status]
            if status == "current" and current.get("development"):
                message = "未发现更新的稳定版本；当前副本仍为开发状态。"
            update = {"status": status, "message": message, "version": candidate["version"],
                      "notes": candidate.get("notes", ""), "published_at": candidate.get("published_at", ""),
                      "size": candidate["package"]["size"], "candidate": candidate,
                      "feed_url": self.feed_url, "checked_at": utcnow()}
        except error.HTTPError as exc:
            update = {"status": "unavailable", "message": "尚未发布可用的更新清单，请稍后重试。" if exc.code == 404 else "更新服务暂时无法访问，请稍后重试。"}
        except (OSError, ValueError, KeyError, TypeError):
            update = {"status": "unavailable", "message": "暂时无法检查更新，请检查网络或稍后重试。"}
        with _LOCK:
            state = read_json(private_path(self.root))
            if state.get("operation", {}).get("status") not in ACTIVE:
                state["update"] = update
                if update.get('status') == 'available':
                    state['operation'] = {'status':'idle', 'message':''}
                write_json(private_path(self.root), state)
        return self.snapshot()

    @staticmethod
    def validate_candidate(value, current, *, local=False):
        if (not isinstance(value, dict) or type(value.get("schema")) is not int or value.get("schema") != 1
                or value.get("edition") != "haike-workflow-2" or value.get("channel") != "stable"
                or type(value.get("data_schema")) is not int or value["data_schema"] < 1
                or not isinstance(value.get("runtime_id"), str) or not value["runtime_id"]
                or not isinstance(value.get("platform"), str)):
            raise core.UpdateError("更新清单格式不兼容")
        core.version_tuple(value["version"])
        core.version_tuple(value["base_version"])
        if core.version_tuple(value["version"]) <= core.version_tuple(value["base_version"]):
            raise core.UpdateError("更新版本必须高于基线版本")
        package = value["package"]
        if not isinstance(package, dict):
            raise core.UpdateError("更新包信息无效")
        if local:
            if 'url' in package:
                raise core.UpdateError('本地更新包不能指定下载地址')
        else:
            https_url(package["url"])
        kind = package.get("kind", "patch")
        if kind not in {"patch", "full"}:
            raise core.UpdateError("更新包类型无效")
        limit = core.MAX_ARCHIVE_BYTES if kind == "patch" else 2 * 1024 ** 3 - 1
        if (not isinstance(package.get("size"), int) or isinstance(package["size"], bool)
                or not 0 < package["size"] <= limit):
            raise core.UpdateError("更新包大小无效")
        digest = package.get("sha256", "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise core.UpdateError("更新包校验信息无效")
        if not isinstance(value.get("notes", ""), str):
            raise core.UpdateError("更新说明格式无效")
        return value

    def import_archive(self, archive):
        """Inspect a bounded local upload; only install() admits a restart."""
        with _LOCK:
            state = read_json(private_path(self.root))
            if state.get('operation', {}).get('status') in ACTIVE or core.pending_receipts(self.root):
                raise core.UpdateError('已有更新正在处理，请先完成或恢复原更新')
            current = current_release(self.root)
            cap = capability(self.root, current)
            if not cap['can_install']:
                raise core.UpdateError(cap['reason'])
            archive = Path(archive)
            relative = archive.relative_to(self.root).as_posix()
            if not relative.startswith('.local/app-updates/import-') or archive.name != 'package.zip':
                raise core.UpdateError('更新包不属于本次本地导入')
            archive = core.safe_path(self.root, relative)
            if not archive.is_file() or not 0 < archive.stat().st_size <= core.MAX_ARCHIVE_BYTES:
                raise core.UpdateError('更新包超过300 MB或内容为空')
            checksum = core.digest(archive)
            with tempfile.TemporaryDirectory(dir=archive.parent, prefix='inspect-') as temporary:
                bundle = Path(temporary)/'bundle'
                core.extract_bundle(archive, bundle)
                plan = core.preflight(bundle, self.root)
            candidate = {key: plan[key] for key in ('schema', 'edition', 'version',
                         'base_version', 'runtime_id', 'data_schema', 'platform')}
            candidate.update(channel=plan.get('channel', 'stable'), notes='本地程序更新包，已核对版本、依赖和文件完整性。',
                             package={'size': archive.stat().st_size, 'sha256': checksum})
            self.validate_candidate(candidate, current, local=True)
            state['update'] = {'status':'available', 'source':'local', 'message':'本地更新包已检查，可以安装',
                              'version':candidate['version'], 'size':candidate['package']['size'],
                              'notes':candidate['notes'], 'candidate':candidate,
                              'local_archive':relative, 'checked_at':utcnow()}
            state['operation'] = {'status':'idle', 'message':''}
            write_json(private_path(self.root), state)
            return self.snapshot()

    def install(self, version, base_url, instance_id, server_pid, confirmed=False, launch=True):
        with _LOCK:
            state = read_json(private_path(self.root))
            if state.get("operation", {}).get("status") in ACTIVE:
                return self.snapshot()
            current = current_release(self.root)
            if core.pending_receipts(self.root):
                raise core.UpdateError("发现尚未恢复的更新，请先按更新文档恢复备份")
            if not capability(self.root, current)["can_install"]:
                raise core.UpdateError(capability(self.root, current)["reason"])
            update = state.get("update", {})
            local = update.get('source') == 'local'
            if confirmed is not True or update.get("status") != "available" or update.get("version") != version or (not local and update.get("feed_url") != self.feed_url):
                raise core.UpdateError("请先重新检查版本，再确认本次更新")
            candidate = self.validate_candidate(update["candidate"], current, local=local)
            if candidate["package"].get("kind", "patch") != "patch":
                raise core.UpdateError("完整安装包请按发行说明迁移，不可作为程序补丁安装")
            if candidate["base_version"] != current["version"]:
                raise core.UpdateError("当前版本已变化，请重新检查更新")
            operation_id = secrets.token_hex(12)
            folder = private_path(self.root, operation_id + "/operation.json").parent
            operation = {"id": operation_id, "status": "downloading", "message": "正在下载更新包", "progress": 0,
                         "target_version": version, "updated_at": utcnow()}
            command = {"id": operation_id, "candidate": candidate, "base_url": base_url,
                       "instance_id": instance_id, "server_pid": server_pid,
                       "token": secrets.token_urlsafe(32)}
            if local:
                archive = core.safe_path(self.root, update['local_archive'])
                if archive.stat().st_size != candidate['package']['size'] or core.digest(archive) != candidate['package']['sha256']:
                    raise core.UpdateError('本地更新包已变化，请重新导入')
                shutil.copyfile(archive, folder/'package.zip')
                command['local_package'] = True
                operation['message'] = '本地更新包已就绪，正在核对安装条件'
            write_json(folder / "operation.json", command)
            state["operation"] = operation
            write_json(private_path(self.root), state)
            if launch:
                helper = folder / "helper"
                helper.mkdir()
                try:
                    for name in ("app_update.py", "update_service.py", "update_worker.py"):
                        shutil.copyfile(Path(__file__).parent / name, helper / name)
                    flags = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)) if os.name == "nt" else 0
                    with (folder / "helper.log").open("ab") as log:
                        child = subprocess.Popen([sys.executable, "-s", str(helper / "update_worker.py"), "--root", str(self.root), "--operation", operation_id],
                                                 cwd=helper, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                                 creationflags=flags, start_new_session=os.name != "nt")
                    command["worker_pid"] = child.pid
                    write_json(folder / "operation.json", command)
                except Exception:
                    set_operation(self.root, "failed", "更新助手未能启动，原程序未修改。")
                    raise core.UpdateError("更新助手未能启动，请稍后重试")
            return self.snapshot()

    def cancel(self):
        set_operation(self.root, "cancelled", "已暂缓本次更新，原程序与现有任务保持原样。")
        return self.snapshot()


def download_package(root, candidate, destination, operation_id=None):
    package = candidate["package"]
    size, received, digest = package["size"], 0, hashlib.sha256()
    if shutil.disk_usage(Path(root)).free < size * 4 + 256 * 1024 ** 2:
        raise core.UpdateError("磁盘空间不足，请清理空间后重试")
    with remote_open(package["url"], timeout=30) as response, Path(destination).open("xb") as output:
        while block := response.read(1024 * 1024):
            received += len(block)
            if received > size:
                raise core.UpdateError("更新包大小与版本清单不符")
            output.write(block)
            digest.update(block)
            set_operation(root, "downloading", "正在下载更新包", expected_id=operation_id, progress=int(received * 100 / size))
    if received != size or digest.hexdigest() != package["sha256"]:
        raise core.UpdateError("更新包校验失败，原程序未修改。请重新检查更新。")
