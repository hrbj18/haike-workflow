# -*- coding: utf-8 -*-
"""修正抖音任务 10 的「假成功」账目。

背景：`_verify_on_manage()` 把抖音「搜索无结果」的空态提示（**含搜索词本身**）
当成了"作品已存在"，于是**发布前查重**把整条发布跳过并返回 done —— 创作后台
根本没有这条作品，而 done 会写 `last_write_at`，白占 7200s 发布配额。

按 skill `creatorhub-publish` §3 的顺序（**先备份**）：
  ① 备份 data/creatorhub.db
  ② publishtask.status: done → failed（同时写清原因）
  ③ 对应 riskevent: outcome success → manual（**留溯源，不删**）
  ④ accountriskstate.last_write_at 置空
  ⑤ 再调 POST /api/risk-control/accounts/1/clear 清任务行上缓存的 next_allowed_at

用法（**默认 dry-run**）：
  ./.venv/Scripts/python.exe scripts/fix_dy_false_done.py            # 只看
  ./.venv/Scripts/python.exe scripts/fix_dy_false_done.py --apply    # 落库
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "creatorhub.db"
TASK_ID = 10
ACCOUNT_ID = 1
REASON = ("发布未生效(假查重命中):发布前查重把抖音「没有找到与『搜索词』相关的作品」"
          "空态提示当成了已存在同名作品 → 整条发布被跳过,创作后台无此作品。"
          "已修 _verify_on_manage(空态判据优先)后重发。")

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def show(cur) -> None:
    print("--- publishtask 10~13 ---")
    for row in cur.execute(
            "select id, account_id, status, created_at, done_at, substr(error,1,60) "
            "from publishtask where id between 10 and 13"):
        print("   ", row)
    print("--- riskevent（按 id 倒序 8 条） ---")
    cols = [c[1] for c in cur.execute("pragma table_info(riskevent)")]
    print("    columns:", cols)
    for row in cur.execute(
            "select id, account_id, operation_kind, outcome, signal, occurred_at "
            "from riskevent order by id desc limit 8"):
        print("   ", row)
    print("--- accountriskstate ---")
    print("    columns:", [c[1] for c in cur.execute("pragma table_info(accountriskstate)")])
    for row in cur.execute("select * from accountriskstate"):
        print("   ", row)


def main() -> int:
    apply = "--apply" in sys.argv
    if not DB.is_file():
        print(f"✗ 找不到 {DB}")
        return 2

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = DB.with_name(f"creatorhub.db.bak-dyfix-{stamp}")
    if apply:
        shutil.copy2(DB, bak)
        print(f"已备份 → {bak.name}")

    con = sqlite3.connect(f"file:{DB}?mode=rw", uri=True, timeout=20)
    cur = con.cursor()
    print(f"=== {'APPLY' if apply else 'DRY-RUN'} ===")
    show(cur)

    if not apply:
        print("\n（dry-run，未改动。加 --apply 落库）")
        con.close()
        return 0

    cur.execute("update publishtask set status='failed', error=? "
                "where id=? and status='done'", (REASON, TASK_ID))
    print(f"② publishtask#{TASK_ID} → failed：{cur.rowcount} 行")

    cur.execute("update riskevent set outcome='manual', signal='false_success_corrected' "
                "where account_id=? and operation_kind='publish' and outcome='success' "
                "and id in (select max(id) from riskevent where account_id=? "
                "and operation_kind='publish' and outcome='success')",
                (ACCOUNT_ID, ACCOUNT_ID))
    print(f"③ riskevent → manual：{cur.rowcount} 行")

    cur.execute("update accountriskstate set last_write_at=NULL where account_id=?",
                (ACCOUNT_ID,))
    print(f"④ accountriskstate.last_write_at 置空：{cur.rowcount} 行")

    con.commit()
    show(cur)
    con.close()

    body = json.dumps({"confirmed": True,
                       "reason": "抖音任务10为假查重命中,已按事实修正,请放行重发"}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:8000/api/risk-control/accounts/{ACCOUNT_ID}/clear",
        data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with OPENER.open(req, timeout=30) as resp:
            print("⑤ clear →", resp.read().decode("utf-8")[:300])
    except Exception as exc:  # noqa: BLE001
        print(f"⑤ clear 调用失败（服务没起？）：{exc!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
