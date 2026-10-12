# -*- coding: utf-8 -*-
"""0930 批次常驻守护启动器。

用途：把 batch_finish_930.py 以 **脱离父进程** 的方式拉起，
使其不随 Bash 工具后台任务 / 本会话的结束而被杀（Windows 上
DETACHED_PROCESS 会脱离控制台，也不继承父进程的 job object）。

用法:
  python spawn_detached_930.py            # 若已有一个活跃持锁者则跳过
  python spawn_detached_930.py --force    # 不管锁，强制再拉一个（通常不需要）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime

BASE = r"D:/刘宇钊/codex_work/haike-workflow/Haike_video"
WORK = os.path.join(BASE, ".backlot", "_diag", "923-batch")
PY = os.path.join(BASE, ".venv", "Scripts", "python.exe")
TARGET = os.path.join(BASE, "scripts", "template_video", "batch_finish_930.py")
LOCK = os.path.join(WORK, "batch_930.lock")
LOG = os.path.join(WORK, "batch_930_daemon.log")
LOCK_STALE_MIN = 15

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def lock_alive() -> bool:
    if not os.path.isfile(LOCK):
        return False
    try:
        with open(LOCK, encoding="utf-8") as f:
            d = json.load(f)
        hb = d.get("hb", "")
        if not hb:
            return False
        t0 = datetime.strptime(hb[:19], "%Y-%m-%dT%H:%M:%S")
        age = (datetime.now() - t0).total_seconds() / 60.0
        return age < LOCK_STALE_MIN
    except Exception:
        return False


def main() -> int:
    force = "--force" in sys.argv
    if lock_alive() and not force:
        print(f"SKIP: an active controller already holds the lock ({LOCK})")
        return 0
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    f = open(LOG, "a", encoding="utf-8")
    p = subprocess.Popen(
        [PY, TARGET],
        cwd=WORK,
        env=env,
        stdout=f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    print(f"SPAWNED pid={p.pid} -> {LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
