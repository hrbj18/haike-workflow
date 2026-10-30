"""Detached update helper; never execute commands supplied by an update feed."""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib import parse, request

try:
    from . import app_update as core
    from .update_service import (download_package, private_path, read_json, set_operation, UpdateCancelled)
except ImportError:
    import app_update as core
    from update_service import download_package, private_path, read_json, set_operation, UpdateCancelled


def local_url(value):
    url = parse.urlsplit(value)
    if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"} or url.username or url.password or url.path not in {"", "/"} or url.query or url.fragment:
        raise core.UpdateError("更新助手只连接本机工作台")
    return value.rstrip("/")


def local_get(base, path, token=None):
    headers = {"X-Haike-Update-Token": token} if token else {}
    req = request.Request(local_url(base) + path, headers=headers)
    with request.build_opener(request.ProxyHandler({})).open(req, timeout=5) as response:
        data = response.read(2 * 1024 * 1024)
    return json.loads(data)


def matches(health, root, instance=None, pid=None):
    try:
        return (health.get("ok") is True and health.get("edition") == "haike-workflow-2"
                and Path(health["workspace"]).resolve() == Path(root).resolve()
                and (instance is None or health.get("instance_id") == instance)
                and (pid is None or health.get("pid") == pid))
    except (KeyError, TypeError, OSError):
        return False


def stop_verified(base, root, instance, pid):
    health = local_get(base, "/api/health")
    if not matches(health, root, instance, pid) or pid == os.getpid() or not isinstance(pid, int) or pid <= 1:
        raise core.UpdateError("工作台身份已变化，未停止任何进程")
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            next_health = local_get(base, "/api/health")
        except (OSError, ValueError):
            return
        if not matches(next_health, root, instance, pid):
            raise core.UpdateError("工作台端口被其他服务占用，已停止更新")
        time.sleep(0.25)
    raise core.UpdateError("工作台尚未完全停止，原程序未修改")


def start_server(root, port):
    root = Path(root)
    env = os.environ.copy()
    env.update(BACKLOT_PORT=str(port), BACKLOT_DETACHED="1")
    log_path = private_path(root, "restart.log")
    flags = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)) if os.name == "nt" else 0
    with log_path.open("ab") as log:
        return subprocess.Popen([sys.executable, "-s", "-m", "backlot", "serve", "--port", str(port)],
                                cwd=root / "Haike_video", env=env, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=log, creationflags=flags,
                                start_new_session=os.name != "nt")


def wait_server(base, root, child, version, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            health = local_get(base, "/api/health")
            # Windows venv launchers can have a different parent PID; ownership
            # is established by the workspace + new server's instance ID.
            if matches(health, root) and health.get("version") == version:
                local_get(base, "/api/studio/templates")
                with request.build_opener(request.ProxyHandler({})).open(base + "/avatar", timeout=5) as page:
                    if page.status != 200 or b"<html" not in page.read(1024 * 1024).lower():
                        raise core.UpdateError("新版界面未能加载")
                return health
        except (OSError, ValueError):
            pass
        if child.poll() is not None:
            break
        time.sleep(0.5)
    raise core.UpdateError("更新后的工作台未能通过启动检查")


def run_update(root, identity):
    if not re.fullmatch(r"[0-9a-f]{24}", identity):
        raise core.UpdateError("更新任务编号无效")
    folder = private_path(root, identity + "/operation.json").parent
    command = read_json(folder / "operation.json")
    if command.get("id") != identity:
        raise core.UpdateError("更新任务记录无效")
    base = local_url(command["base_url"])
    port = parse.urlsplit(base).port or 80
    stopped, child = False, None
    candidate = command["candidate"]
    previous_version = core.read_release(root).get("version")
    def update(status, message, **fields):
        return set_operation(root, status, message, expected_id=identity, **fields)
    try:
        archive = folder / "package.zip"
        if command.get('local_package') is True:
            if archive.stat().st_size != candidate['package']['size'] or core.digest(archive) != candidate['package']['sha256']:
                raise core.UpdateError('本地更新包校验失败，原程序未修改')
        else:
            download_package(root, candidate, archive, operation_id=identity)
        bundle = folder / "bundle"
        core.extract_bundle(archive, bundle)
        plan = core.preflight(bundle, root)
        metadata_bytes = sum((Path(root) / name).stat().st_size for name in ("RELEASE.json", "PACKAGE-MANIFEST.json"))
        required_space = (sum(item["size"] for item in plan["files"]) + metadata_bytes) * 3 + 64 * 1024 ** 2
        if shutil.disk_usage(root).free < required_space:
            raise core.UpdateError("磁盘空间不足以备份和安装，原程序未修改。")
        for key in ("version", "base_version", "edition", "platform", "runtime_id", "data_schema"):
            if plan.get(key) != candidate.get(key):
                raise core.UpdateError("更新包与已确认的版本不一致")
        update("waiting", "更新包已就绪，正在等待制作、下载和发布任务结束。", progress=100)
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            ready = local_get(base, "/api/studio/app-update/readiness", command["token"])
            if ready.get("ready"):
                break
            update("waiting", ready.get("message", "正在等待现有任务结束。"))
            time.sleep(2)
        else:
            raise core.UpdateError("现有任务仍未结束，本次更新已延后，原程序未修改。")
        update("installing", "正在备份并安装更新，请勿关闭电脑。")
        # Recheck after closing admission, before stopping this exact instance.
        if not local_get(base, "/api/studio/app-update/readiness", command["token"]).get("ready"):
            raise core.UpdateError("仍有任务运行，本次更新已延后，原程序未修改。")
        stop_verified(base, root, command["instance_id"], command["server_pid"])
        stopped = True

        def healthy(target, manifest):
            nonlocal child
            update("restarting", "正在重启工作台并检查新版本。")
            child = start_server(root, port)
            try:
                wait_server(base, root, child, manifest["version"])
                return True
            except Exception:
                # Only terminate the process we just launched, never another
                # process subsequently occupying the same port.
                try:
                    h = local_get(base, "/api/health")
                    if matches(h, root):
                        stop_verified(base, root, h["instance_id"], h["pid"])
                except (OSError, ValueError):
                    pass
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=15)
                raise

        result = core.apply_update(bundle, root, health_check=healthy)
        update("complete", "更新完成，配置、账号和作品已保留。", progress=100, backup=result.get("backup"))
    except UpdateCancelled:
        return
    except Exception as exc:
        # The core rolls back its transaction before this handler. A shutdown
        # or download error before apply never changes the installed program.
        if stopped:
            try:
                child = start_server(root, port)
                wait_server(base, root, child, previous_version)
                update("rolled_back", "更新未完成，已恢复并启动原版本，配置、账号和作品已保留。")
                return
            except Exception:
                update("failed", "更新未完成，工作台暂未恢复启动。请保留更新备份，按更新文档恢复。")
        else:
            message = str(exc) if isinstance(exc, core.UpdateError) else "更新未完成，原程序未修改，请检查网络或稍后重试。"
            update("failed", message)
        raise


def manual_rollback(root, backup, port):
    base = f"http://127.0.0.1:{port}"
    # Never stop a live production server from the recovery CLI. Normally this
    # is used while startup is broken; a running instance must be closed first.
    try:
        health = local_get(base, "/api/health")
    except (OSError, ValueError):
        health = None
    if health is not None:
        raise core.UpdateError("请先关闭此副本工作台后再执行人工回退；未停止任何进程")
    result = core.rollback(root, backup)
    set_operation(root, "rolled_back", "已人工恢复原版本，正在重新启动工作台。")
    child = start_server(root, port)
    wait_server(base, root, child, core.read_release(root).get("version"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--operation")
    action.add_argument("--rollback", type=Path)
    parser.add_argument("--port", default=14756, type=int)
    args = parser.parse_args()
    if args.rollback:
        print(json.dumps(manual_rollback(args.root.resolve(), args.rollback, args.port), ensure_ascii=False))
    else:
        run_update(args.root.resolve(), args.operation)


if __name__ == "__main__":
    main()
