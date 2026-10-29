# -*- coding: utf-8 -*-
"""0930 批次一键状态摘要：state 阶段 + 成片 + QC 结论 + 采集进度 + 进程心跳。

用法: python status_930.py
"""
from __future__ import annotations

import io
import json
import os
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = r"D:/刘宇钊/codex_work/haike-workflow/Haike_video"
WORK = os.path.join(BASE, ".backlot", "_diag", "923-batch")
STATE = os.path.join(WORK, "batch_state_930.json")
LOCK = os.path.join(WORK, "batch_930.lock")
COLLECT = os.path.join(WORK, "collect_0930b.log")
FINAL = os.path.join(WORK, "final_930")


def tail(path: str, n: int = 6) -> list[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [x.rstrip() for x in f.read().splitlines()[-n:]]
    except Exception:
        return []


def main() -> int:
    print("=" * 78)
    print("0930 批次状态", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 78)

    # 进程心跳
    if os.path.isfile(LOCK):
        try:
            d = json.load(open(LOCK, encoding="utf-8"))
            t0 = datetime.strptime(d["hb"][:19], "%Y-%m-%dT%H:%M:%S")
            age = (datetime.now() - t0).total_seconds() / 60
            print(f"controller pid={d.get('pid')} heartbeat {age:.1f}min ago"
                  f"  [{'ALIVE' if age < 6 else 'STALE'}]")
        except Exception as e:                      # noqa: BLE001
            print(f"lock unreadable: {e}")
    else:
        print("controller: NO LOCK (not running?)")

    # 任务
    s = json.load(open(STATE, encoding="utf-8"))
    print()
    print(f"{'key':<5}{'stage':<14}{'tries':<16}{'成片':<8}{'QC':<10} title")
    for t, i in s["tasks"].items():
        final = os.path.join(WORK, i["final"])
        have = "YES" if os.path.isfile(final) else "-"
        mb = f"{os.path.getsize(final)/1e6:.1f}M" if have == "YES" else ""
        qc = "-"
        qj = os.path.join(WORK, f"qc_final_{i['qc_label']}.json")
        if os.path.isfile(qj):
            try:
                j = json.load(open(qj, encoding="utf-8"))
                qc = "PASS" if j[0].get("pass") else "RISK"
            except Exception:
                qc = "?"
        tr = f"p{i.get('pick_tries',0)}/c{i.get('cut_tries',0)}/q{i.get('qc_tries',0)}"
        print(f"{t:<5}{i['stage']:<14}{tr:<16}{mb or have:<8}{qc:<10} {i['title']}")

    # 成片清单
    print()
    if os.path.isdir(FINAL):
        fs = sorted(os.listdir(FINAL))
        print(f"final_930: {len(fs)} 个")
        for f in fs:
            print(f"  {f}  {os.path.getsize(os.path.join(FINAL,f))/1e6:.1f}M")
    else:
        print("final_930: (空)")

    # 采集进度
    print()
    done, started = [], None
    if os.path.isfile(COLLECT):
        with open(COLLECT, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("=== END "):
                    done.append(line.split()[2])
                elif line.startswith("=== START "):
                    started = line.split()[2]
    print(f"采集完成主题({len(done)}): {', '.join(done)}")
    print(f"采集中: {started or '-'}")

    # 最近日志
    print()
    print("--- batch_finish_930.log ---")
    for x in tail(os.path.join(WORK, "batch_finish_930.log"), 6):
        print(" ", x[:150])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
