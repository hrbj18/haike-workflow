r"""按事实修正账号的 `status`（登录态缓存标记），带备份与审计事件。

★ 为什么需要单独的工具：`POST /api/risk-control/accounts/{id}/clear` 只清
  `AccountRiskState`（风控等级/冷却），**不动** `DouyinAccount.status`；
  而发布闸门 `app/risk.py` 判的是后者：
      if account.status == "invalid" and kind != LOGIN:
          return RiskDecision(False, "账号登录态已失效，等待重新登录", signal="auth_required")
  ⇒ 用户重新登录成功后，这个标记**不会自动回写**，发布会被**永久卡住**，
    而且报的是"登录失效"，把人引向反复扫码。

★ 安全性：本工具**只改缓存标记**，不写任何 cookie、不伪造登录态。
  发布链路自己会跑真实的登录自检（快手 = `_ks_self_profile`），
  登录若真的失效，发布照样会失败并把标记打回 `invalid`。

用法：
    python scripts/set_account_status.py 2 active --reason "..." [--apply]
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


def _audit(conn: sqlite3.Connection, account_id: int, status: str,
           reason: str) -> None:
    """往 riskevent 写一条人工修正记录。

    ★ 不能只列"我想到的"列：`riskevent` 有 `NOT NULL` 的列（如 `network_key`），
      漏一列整条 insert 就被拒 —— 而审计记录**丢了自己也不会有人知道**。
      所以这里**按表结构补齐**：所有 NOT NULL 且无默认值的列都给个安全值。
    """
    cols = conn.execute("pragma table_info(riskevent)").fetchall()
    data = {
        "account_id": account_id,
        "platform": "",
        "operation_kind": "read_light",
        "outcome": "manual",
        "signal": "risk_cleared",
        "detail": f"agent@127.0.0.1 按事实修正 status={status}：{reason}",
        "occurred_at": datetime.now().isoformat(sep=" "),
        "created_at": datetime.now().isoformat(sep=" "),
    }
    names, values = [], []
    for _cid, name, ctype, notnull, default, pk in cols:
        if pk or name == "id":
            continue                    # ★ 自增主键绝不能塞占位值
        if name in data:
            names.append(name)
            values.append(data[name])
        elif notnull and default is None:
            # ★ 占位值必须**匹配列类型**：往 INTEGER 列塞 '' 会报
            #   "datatype mismatch"，把整条审计记录丢掉。
            ctype = (ctype or "").upper()
            names.append(name)
            values.append(0 if "INT" in ctype else 0.0 if "REAL" in ctype or "FLOA" in ctype else "")
    try:
        conn.execute(
            f"insert into riskevent ({','.join(names)}) "
            f"values ({','.join('?' * len(names))})", values)
        print("已写审计事件")
    except Exception as e:              # 审计失败不该阻断主修复
        print("（审计事件写入跳过:", e, "）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("account_id", type=int)
    ap.add_argument("status", choices=("active", "invalid"))
    ap.add_argument("--reason", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if len(args.reason.strip()) < 3:
        print("reason 至少要 3 个字符")
        return 2
    if not DB.exists():
        print("找不到数据库:", DB)
        return 2

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "select id, platform, nickname, status from douyinaccount where id = ?",
        (args.account_id,)).fetchone()
    if row is None:
        print("账号不存在:", args.account_id)
        return 2
    print(f"账号 {row['id']} {row['platform']} {row['nickname']}")
    print(f"  status: {row['status']}  →  {args.status}")
    print(f"  reason: {args.reason}")

    if not args.apply:
        print("\n（dry-run；加 --apply 真正写库）")
        conn.close()
        return 0

    backup = DB.with_name(f"{DB.stem}.backup-{time.strftime('%Y%m%d-%H%M%S')}.db")
    conn.close()
    shutil.copy2(DB, backup)
    print("\n已备份:", backup)

    conn = sqlite3.connect(DB)
    conn.execute("update douyinaccount set status = ? where id = ?",
                 (args.status, args.account_id))
    _audit(conn, args.account_id, args.status, args.reason)
    conn.commit()
    after = conn.execute("select status from douyinaccount where id = ?",
                         (args.account_id,)).fetchone()[0]
    conn.close()
    print(f"完成：status = {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
