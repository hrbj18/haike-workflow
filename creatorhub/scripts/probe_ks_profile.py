"""只读探查快手账号的 profile：锁文件、cookie 名清单（不解密）。

用途：登录流程报「未登录」时，判断到底是**用户没登上**，还是**浏览器 profile 里
其实已有会话、只是判据没认出来**。
"""
from __future__ import annotations

import glob
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

PROFILES = Path("data/profiles")


def main(suffix: str) -> int:
    hits = glob.glob(str(PROFILES / f"*{suffix}"))
    if not hits:
        print("profile 不存在:", suffix)
        return 2
    root = Path(hits[0])
    print("profile:", root)

    print("\n--- 顶层锁文件 ---")
    for name in (".browser.lock", "lockfile", "SingletonLock"):
        p = root / name
        if not p.exists():
            continue
        try:
            raw = p.read_bytes()[:120]
        except PermissionError:
            # ★ 读不到 = **独占到句柄** = 有进程正抓着这个 profile（窗口还开着 / 僵尸进程）
            raw = b"<locked by another process>"
        age = time.time() - p.stat().st_mtime
        print(f"{name:16} {time.strftime('%H:%M:%S', time.localtime(p.stat().st_mtime))} "
              f"{p.stat().st_size}B  静默 {int(age)}s  {raw!r}")

    cookies = root / "Default" / "Network" / "Cookies"
    if not cookies.exists():
        cookies = root / "Default" / "Cookies"
    if not cookies.exists():
        print("找不到 Cookies 库")
        return 1

    tmp = Path(tempfile.gettempdir()) / f"ckprobe_{suffix}.db"
    try:
        shutil.copy2(cookies, tmp)
    except PermissionError:
        print("\n⚠️ Cookies 库被占用（浏览器还开着或句柄未释放）→ 用 immutable 只读打开")
        # ★ URI 必须是**绝对路径**（as_posix 给相对路径时 sqlite 会报
        #   "unable to open database file"，容易误判成文件损坏）
        uri = "file:///" + cookies.resolve().as_posix() + "?mode=ro&immutable=1"
        print("   uri:", uri)
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(tmp)

    rows = conn.execute(
        "select host_key, name, length(encrypted_value) from cookies order by host_key, name"
    ).fetchall()
    print(f"\n--- cookie 清单（共 {len(rows)} 条）---")
    for host, name, size in rows:
        mark = ""
        if name in {"kuaishou.web.cp.api_st", "kuaishou.web.cp.api_ph"}:
            mark = "  ★创作者强登录"
        elif name in {"passToken", "userId", "kuaishou.server.web_st", "web_st"}:
            mark = "  ★主站登录"
        print(f"{host:40} {name:36} {size:5}B{mark}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "8b9d0dcbe52def61da"))
