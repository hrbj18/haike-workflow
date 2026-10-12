r"""杀掉**只**占着某个 creatorhub profile 的 chrome 进程（不碰用户自己的浏览器）。

★ 为什么需要这个：headless 抓取进程一旦卡住，会一直持有 profile 的
  `.browser.lock` / `Cookies` 句柄 ⇒ 后续登录窗口打不开、cookie 读不到，
  而且**没有任何报错**（表现成"登录了但无效"）。

判据只有一个：chrome 命令行里出现该 profile 的绝对路径。
用户自己的 Chrome（`--user-data-dir=...\AppData\Local\Google\Chrome\User Data`）不会命中。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

PROFILES = Path("data/profiles")


def chrome_procs() -> list[dict]:
    ps = (
        "Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True, errors="replace")
    raw = (out.stdout or "").strip()
    if not raw:
        return []
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]
    return [d for d in data if d.get("CommandLine")]


def main(profile: str, apply: bool) -> int:
    hits = [p for p in PROFILES.iterdir() if profile in p.name]
    if not hits:
        print("找不到 profile:", profile)
        return 2
    root = str(hits[0].resolve())
    print("目标 profile:", root)

    # ★ 只用 **目录名（含 hash）** 匹配，不要用完整路径：
    #   PowerShell → 管道这段会把中文变成 U+FFFD（本项目路径里有「刘宇钊」），
    #   拿完整路径比较会**永远匹配不到 0 个**，看起来像"没有残留进程"。
    key = hits[0].name.lower()

    procs = chrome_procs()
    victims = [p for p in procs if key in (p["CommandLine"] or "").lower()]
    print(f"chrome 进程总数 {len(procs)}，命中该 profile 的 {len(victims)} 个")
    for p in victims:
        cmd = p["CommandLine"]
        mode = "headless" if "--headless" in cmd else "headed"
        print(f"  PID {p['ProcessId']:>6}  {mode}")

    if not victims:
        print("没有残留进程 → 无需处理")
        return 0
    if not apply:
        print("\n（dry-run；加 --apply 真正结束这些进程）")
        return 0

    main_pids = [p["ProcessId"] for p in victims
                 if "--type=" not in (p["CommandLine"] or "")]
    print("\n结束主进程:", main_pids)
    for pid in main_pids or [p["ProcessId"] for p in victims]:
        r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, text=True, errors="replace")
        print(" ", pid, (r.stdout or r.stderr).strip().replace("\n", " ")[:100])
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    raise SystemExit(main(args[0] if args else "8b9d0dcbe52def61da",
                          "--apply" in sys.argv))
