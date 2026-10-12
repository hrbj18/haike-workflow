# -*- coding: utf-8 -*-
"""0930 批次看门狗：主进程崩溃/退出时把它重新拉起来。

为什么需要：主进程 batch_finish_930.py 是串行走完 6 条的常驻循环，
任何一步崩溃（渲染 ffmpeg 异常、QC 段错误、封面网络失败）都会让它退出，
后面几条就再也没人推进。看门狗只看**锁心跳**：
心跳陈旧 = 主进程没了 → 重新拉起。主进程健康时它什么都不做。

用法: python watchdog_930.py            # 常驻，每 60s 检查一次
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime

BASE = r"D:/刘宇钊/codex_work/haike-workflow/Haike_video"
WORK = os.path.join(BASE, ".backlot", "_diag", "923-batch")
PY = os.path.join(BASE, ".venv", "Scripts", "python.exe")
BATCH = os.path.join(BASE, "scripts", "template_video", "batch_finish_930.py")
LOCK = os.path.join(WORK, "batch_930.lock")
STATE = os.path.join(WORK, "batch_state_930.json")
WD_LOG = os.path.join(WORK, "watchdog_930.log")

CHECK_SEC = 60
# 主进程长步骤期间每 20s 刷一次心跳，所以 6 分钟没心跳基本可判定它没了。
STALE_MIN = 6


def wlog(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(WD_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def lock_age_min() -> float | None:
    if not os.path.isfile(LOCK):
        return None
    try:
        with open(LOCK, encoding="utf-8") as f:
            d = json.load(f)
        hb = d.get("hb", "")
        if not hb:
            return None
        t0 = datetime.strptime(hb[:19], "%Y-%m-%dT%H:%M:%S")
        return (datetime.now() - t0).total_seconds() / 60.0
    except Exception:
        return None


def all_settled() -> bool:
    try:
        with open(STATE, encoding="utf-8") as f:
            s = json.load(f)
        for t, i in s["tasks"].items():
            st = i["stage"]
            if st.startswith("done") or st == "cover_done":
                continue
            return False
        return True
    except Exception:
        return False


def spawn_controller(why: str) -> None:
    # ★ 拉起前必须清掉陈旧锁：否则新主进程 acquire_lock 时会认为
    #   "已有人持锁"而直接退出，看门狗就永远拉不起来它。
    try:
        if os.path.isfile(LOCK):
            os.remove(LOCK)
    except Exception:                            # noqa: BLE001
        pass
    subprocess.Popen([PY, BATCH], cwd=WORK,
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL)
    wlog(why)


def main() -> int:
    wlog(f"watchdog start pid={os.getpid()}")
    while True:
        try:
            if all_settled():
                wlog("all tasks done, watchdog exit")
                return 0
            age = lock_age_min()
            if age is None:
                spawn_controller("no lock -> spawn controller")
            elif age > STALE_MIN:
                spawn_controller(f"stale heartbeat {age:.1f}min -> respawn")
            else:
                wlog(f"controller alive (hb {age:.1f}min ago)")
        except Exception as e:                      # noqa: BLE001
            wlog(f"EXC {e}")
        time.sleep(CHECK_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
