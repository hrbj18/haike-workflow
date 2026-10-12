r"""查看/清除发布任务的「延迟位」（`publishtask.next_allowed_at` 等）。

★ 为什么要单独清：`AsyncEngine._defer_row()` 写 `next_allowed_at` 时用的是
      row.next_allowed_at = max(row.next_allowed_at or proposed, proposed)
  —— **只增不减**。于是"账号登录失效 → 延迟 15 分钟"这条一旦写进去，
  即使**22 秒后**登录态就被修好了，任务仍会一直等到那个时间点，
  而且报的还是那句"账号登录态已失效"，把人继续引向反复扫码。

★ 安全性：本工具只清**任务上的等待位**（`blocked_*` / `next_allowed_at`），
  不动账号登录态、不动风控等级。清完后发布仍会跑真实的登录自检，
  真失效就再被挡一次 —— 不存在"清一下就放出错误内容"的风险。

用法：
    python scripts/clear_task_deferral.py --list
    python scripts/clear_task_deferral.py 11 [--apply]
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB = Path("data/creatorhub.db")
COLS = ("id", "account_id", "status", "blocked_signal", "blocked_reason",
        "blocked_at", "next_allowed_at", "error")


def _rows(conn: sqlite3.Connection, only: int | None) -> list[dict]:
    sql = f"select {','.join(COLS)} from publishtask"
    args: tuple = ()
    if only is not None:
        sql += " where id = ?"
        args = (only,)
    out = []
    for r in conn.execute(sql + " order by id", args):
        d = dict(zip(COLS, r))
        if d["next_allowed_at"] or d["blocked_signal"]:
            out.append(d)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_id", nargs="?", type=int)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    rows = _rows(conn, args.task_id)
    if not rows:
        print("没有带延迟位的发布任务")
        conn.close()
        return 0

    now = datetime.utcnow()
    print(f"当前 UTC {now.isoformat(sep=' ', timespec='seconds')}")
    for d in rows:
        print(f"  任务 {d['id']}  账号 {d['account_id']}  status={d['status']}")
        print(f"     signal={d['blocked_signal']}  next_allowed_at={d['next_allowed_at']}")
        print(f"     reason={d['blocked_reason'] or d['error']}")

    if args.list or not args.apply:
        print("\n（dry-run；加 --apply 真正清除）")
        conn.close()
        return 0
    if args.task_id is None:
        print("\n清除需要指定任务号（避免误清一批）")
        conn.close()
        return 2

    conn.close()
    backup = DB.with_name(f"{DB.stem}.backup-{time.strftime('%Y%m%d-%H%M%S')}.db")
    shutil.copy2(DB, backup)
    print("\n已备份:", backup)

    conn = sqlite3.connect(DB)
    conn.execute(
        "update publishtask set blocked_reason='', blocked_signal='', "
        "blocked_operation='', blocked_at=NULL, next_allowed_at=NULL, "
        "status='pending', error='' where id = ?", (args.task_id,))
    conn.commit()
    after = conn.execute(
        f"select {','.join(COLS)} from publishtask where id = ?",
        (args.task_id,)).fetchone()
    conn.close()
    print("清除后:", dict(zip(COLS, after)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
