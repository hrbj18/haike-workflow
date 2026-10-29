#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""发布核对一条命令：把 DB 里的发布任务与**平台侧真实作品列表**对账。

为什么要这个脚本
----------------
2026-09-17 那次「测试发布」花了一小时，其中约 15 分钟是**手工做平台侧核对**：
小红书要 curl 一次自己的接口、快手要另跑 `_ks_check_works.py`，然后人肉把两张表
并到一起、逐条判断「uncertain 到底发没发」。这一步**每次发完都要做**，而且结论
直接决定「要不要补发」—— 补发错了就是造重复作品（快手/小红书没有发布前查重，
见 skill `creatorhub-publish` §0.11）。

所以把它收成一条命令：跑完给一张对账表，谁没发出去一眼能看见。

权威性说明（很重要）
--------------------
* **小红书**：`GET /api/publish/published?account_id=4` 是**平台权威** —— 它由
  CreatorHub 登录态直接读平台已发布笔记列表（顶层 `notes` / `total`）。
* **快手**：委托给 `_ks_check_works.py`（走 `cp.kuaishou.com` 创作平台，
  读 `rest/cp/works/v2/video/pc/photo/list` 台账 + DOM 卡片双重台账）。
  ❌ **不要**用 `POST /api/accounts/2/works/sync` —— 它走 `www.kuaishou.com`
  首页域，与 cp 是两条独立登录链，必然 400。
* **抖音 / 视频号**：暂无接口级核对路径，本脚本只报「未覆盖」，不编造结论。

用法::

    cd D:/刘宇钊/codex_work/creatorhub
    CODEBUDDY_SAFE_DELETE_ENABLED=0 ./.venv/Scripts/python.exe \\
        scripts/publish_audit.py                     # 审所有已支持账号
    ... scripts/publish_audit.py --account 4         # 只审小红书
    ... scripts/publish_audit.py --ids 38,39,26      # 只审这几条任务
    ... scripts/publish_audit.py --no-write          # 不落 md,只看屏幕

只读：不建任务、不改 DB、不碰线上持久浏览器 profile。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("CODEBUDDY_SAFE_DELETE_ENABLED", "0")

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "creatorhub.db"
SCRIPTS = ROOT / "scripts"
REPORTS = ROOT / "data" / "reports"
KS_CHECK = SCRIPTS / "_ks_check_works.py"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
API = "http://127.0.0.1:8000"

# 账号 → 平台。只有这两个平台有权威核对路径（见模块 docstring）。
AUDITABLE = {2: "kuaishou", 4: "xhs"}
# 本机账号固定的编号（skill `creatorhub-publish` §5）。用来在被跳过/库无任务时
# 仍能报出平台名，不至于在报告里显示成 `?`。
ACCOUNT_PLATFORM = {1: "douyin", 2: "kuaishou", 3: "channels", 4: "xhs"}
PLATFORM_CN = {"kuaishou": "快手", "xhs": "小红书", "douyin": "抖音",
               "channels": "视频号"}

TITLE_KEY_LEN = 12


def title_key(title: str) -> str:
    """标题比对键：去掉所有空白后取前 12 字。

    必须去空白 —— 平台侧有时会把标题里的空格去掉或重排（实测快手有这情况）。
    12 字足以区分，又不会被平台对长标题的截断影响。
    """
    return "".join(str(title or "").split())[:TITLE_KEY_LEN]


def utc_to_bj(ts) -> str:
    """把 **UTC 来源**的时间戳转成北京时间显示。

    ★ 只喂 UTC 来源进来！三种输入的时区语义**不一样**，混用会得到错 8 小时的时间：

    | 来源 | 形态 | 时区 |
    |---|---|---|
    | `publishtask.done_at / scheduled_at` | ISO 字符串 | **UTC** ✅ 用本函数 |
    | 快手 `photo/list` 的 `uploadTime` | 毫秒 epoch | **UTC** ✅ 用本函数 |
    | 小红书 `published` 的 `note["time"]` | `"2026-09-17 15:52"` | **已经是北京时间** ❌ 原样用 |

    踩过的坑：小红书那个串格式**不带秒**，于是 strptime 全部失败、函数落到
    `return raw[:16]` 的兜底分支，**碰巧**没被加 8 小时 —— 一旦平台改成带秒的格式
    （`"…15:52:30"`）就会立刻错 8 小时，而且不会有任何报错。所以要靠**调用点**区分，
    不能靠格式兜底。
    """
    import datetime as dt
    if ts in (None, ""):
        return ""
    raw = str(ts).strip()
    try:
        v = float(raw)
    except ValueError:
        pass
    else:
        if v > 1e11:          # 毫秒
            v /= 1000.0
        return (dt.datetime.fromtimestamp(v, dt.timezone.utc)
                + dt.timedelta(hours=8)).strftime("%m-%d %H:%M")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = dt.datetime.strptime(raw[:26], fmt)
        except ValueError:
            continue
        return (parsed + dt.timedelta(hours=8)).strftime("%m-%d %H:%M")
    return raw[:16]           # 认不出来就原样给,别假装算出时间了


def load_tasks(account_ids: list[int]) -> list[dict]:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    q = ("SELECT id, platform, account_id, title, status, error, done_at"
         "  FROM publishtask WHERE account_id IN (%s)"
         % ",".join("?" * len(account_ids)))
    rows = [dict(r) for r in con.execute(q, account_ids)]
    con.close()
    return rows


def fetch_xhs_notes(account_id: int, timeout: float = 20.0) -> tuple[list[dict], str]:
    """读小红书平台侧已发布笔记。返回 (notes, 错误说明)。"""
    try:
        import httpx
    except ImportError:
        return [], "没有 httpx"
    url = f"{API}/api/publish/published?account_id={account_id}"
    try:
        # ★ trust_env=False 等价于 curl 的 --noproxy '*'：本机全局代理会劫持回环。
        with httpx.Client(trust_env=False, timeout=timeout) as c:
            r = c.get(url)
    except Exception as exc:
        return [], f"请求失败(服务没起?): {exc!r}"
    if r.status_code != 200:
        return [], f"HTTP {r.status_code}: {r.text[:120]}"
    try:
        data = r.json()
    except Exception as exc:
        return [], f"返回不是 JSON: {exc!r}"
    notes = data.get("notes")
    if not isinstance(notes, list):
        return [], f"返回里没有 notes 列表(顶层键 {list(data)[:6]})"
    return notes, ""


def run_ks_check(account_id: int, timeout: float = 240.0) -> tuple[dict, str]:
    """委托 `_ks_check_works.py` 做快手核对，读它落的 JSON。"""
    if not KS_CHECK.exists():
        return {}, f"找不到 {KS_CHECK}"
    py = str(VENV_PY) if VENV_PY.exists() else sys.executable
    fd, tmp = tempfile.mkstemp(suffix=".json", prefix="ks_audit_")
    os.close(fd)
    try:
        proc = subprocess.run(
            [py, "-u", str(KS_CHECK), "--account", str(account_id),
             "--json-out", tmp],
            cwd=str(ROOT), capture_output=True, timeout=timeout)
        raw = Path(tmp).read_text(encoding="utf-8") if Path(tmp).exists() else ""
        if not raw:
            tail = (proc.stdout or b"").decode("utf-8", "replace")[-400:]
            return {}, f"核对脚本没产出 JSON(rc={proc.returncode})。尾巴:{tail}"
        return json.loads(raw), ""
    except subprocess.TimeoutExpired:
        return {}, f"超时 {timeout:.0f}s"
    except Exception as exc:
        return {}, f"{exc!r}"
    finally:
        try:
            Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass


def audit() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default=None,
                    help="逗号分隔的账号 id；默认审全部已支持账号(2 快手 / 4 小红书)")
    ap.add_argument("--ids", default=None, help="只审这几条任务 id(逗号分隔)")
    ap.add_argument("--no-write", action="store_true", help="不落 md 报告")
    ap.add_argument("--ks-timeout", type=float, default=240.0)
    args = ap.parse_args()

    accounts_all = ([int(x) for x in args.account.split(",") if x.strip()]
                    if args.account else sorted(AUDITABLE))
    want_ids = ([int(x) for x in args.ids.split(",") if x.strip()]
                if args.ids else None)

    unknown = [a for a in accounts_all if a not in AUDITABLE]
    not_covered: dict[int, str] = {}
    if unknown:
        # ★ 警告完必须真的把它摘掉,否则后面 AUDITABLE[acc] 直接 KeyError。
        #   同时登记进 not_covered 让退出码反映"这次核对是残缺的"。
        print(f"⚠️ 账号 {unknown} 没有权威核对路径,已跳过"
              f"(目前只支持 {sorted(AUDITABLE)})")
        for a in unknown:
            not_covered[a] = "该平台暂无接口级核对路径"
    accounts = [a for a in accounts_all if a in AUDITABLE]
    if not accounts:
        raise SystemExit("没有可核对的账号")

    # 库里的任务按请求账号全量读(含被跳过的),这样报告里还能标出被跳过账号的平台名;
    # 但下面出对账表时只走可核对账号。
    tasks_all = load_tasks(accounts_all)
    tasks = [t for t in tasks_all if t["account_id"] in accounts]
    if want_ids:
        tasks = [t for t in tasks if t["id"] in want_ids]
    by_acc: dict[int, list[dict]] = {}
    for t in tasks:
        by_acc.setdefault(t["account_id"], []).append(t)

    # ★★ 证据必须按 (平台, 标题键) 双键存,不能只按标题。
    #   踩过的坑:两个平台都发过同一条视频是常态(这正是"同步到多平台"的用途),
    #   只按标题去重时后处理的平台会**覆盖**前一个平台的证据 ⇒ 快手任务显示成
    #   "✅ 在 · 小红书id=..." —— 拿另一个平台的证据给这个平台背书,是纯粹的假阳性。
    #   这个项目已经因为"看到了不等于发出了"栽过好几次,不能再出这种错。
    evidence: dict[tuple[str, str], dict] = {}
    covered: dict[int, str] = {}
    # not_covered 已在上面为"无核对路径的账号"预置过,这里不要再清空。
    extra_notes: dict[int, list[dict]] = {}

    for acc in accounts:
        plat = AUDITABLE[acc]
        print(f"\n{'=' * 72}\n【{PLATFORM_CN[plat]}】账号 {acc} —— 拉平台侧作品列表\n{'=' * 72}")
        if plat == "xhs":
            notes, err = fetch_xhs_notes(acc)
            if err:
                print(f"  ❌ {err}")
                not_covered[acc] = err
                continue
            covered[acc] = f"{len(notes)} 条笔记"
            print(f"  ✅ 平台返回 {len(notes)} 条笔记")
            matched: set[str] = set()
            for n in notes:
                k = title_key(n.get("title"))
                # ★ 小红书的 note["time"] 已经是**北京时间**字符串，直接原样用，
                #   千万别过 utc_to_bj()（会再多加 8 小时）。见 utc_to_bj 的说明。
                evidence[(plat, k)] = {"platform": plat,
                                       "id": n.get("note_id"),
                                       "time": str(n.get("time") or "")[:16],
                                       "title": n.get("title") or ""}
                matched.add(k)
            # 平台上有、而 DB 任务里没有的（更早期笔记 / 手动发的）
            keys_in_db = {title_key(t["title"]) for t in by_acc.get(acc, [])}
            extra_notes[acc] = [n for n in notes
                                if title_key(n.get("title")) not in keys_in_db]
        elif plat == "kuaishou":
            data, err = run_ks_check(acc, args.ks_timeout)
            if err:
                print(f"  ❌ {err}")
                not_covered[acc] = err
                continue
            works = data.get("works") or []
            covered[acc] = f"{len(works)} 件作品"
            print(f"  ✅ 平台台账 {len(works)} 件作品 "
                  f"(DOM 卡片 {data.get('dom_card_count')} 张, "
                  f"剔除伪卡片 {data.get('dom_tab_pseudo_cards')} 个)")
            for w in works:
                k = title_key(w.get("caption"))
                # 快手的 uploadTime 是**毫秒 epoch**(UTC),要过 utc_to_bj() 换算;
                # 直接打出来就是一串 1789632384676,没人读得懂。
                evidence[(plat, k)] = {"platform": plat, "id": w.get("id"),
                                       "time": utc_to_bj(w.get("time")),
                                       "title": w.get("caption") or ""}
            keys_in_db = {title_key(t["title"]) for t in by_acc.get(acc, [])}
            extra_notes[acc] = [w for w in works
                                if title_key(w.get("caption")) not in keys_in_db]

    # ---- 合并出对账表 ----
    rows: list[dict] = []
    for acc in accounts:
        if acc in not_covered:
            for t in by_acc.get(acc, []):
                rows.append({"task": t, "found": None,
                             "why": f"未覆盖({not_covered[acc][:40]})"})
            continue
        for t in by_acc.get(acc, []):
            k = title_key(t["title"])
            ev = evidence.get((t["platform"], k))
            rows.append({"task": t, "found": bool(ev),
                         "why": (f"{ev['time']} · "
                                 f"{PLATFORM_CN[ev['platform']]}作品id={ev['id']}"
                                 if ev else "")})

    lines: list[str] = []
    add = lines.append
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    # 先算好再拼 —— 避免 f-string 里再嵌同种引号(3.12 以下会 SyntaxError)
    cover_bits = []
    for a in accounts:
        cnt = covered.get(a) or not_covered.get(a) or "?"
        cover_bits.append(f"{PLATFORM_CN[AUDITABLE[a]]}({a})『{cnt}』")
    for a, why in not_covered.items():
        if a not in AUDITABLE:      # 无核对路径、被跳过的账号也要在报告里留痕
            plat = PLATFORM_CN.get(
                ACCOUNT_PLATFORM.get(a)
                or next((t["platform"] for t in tasks_all
                         if t["account_id"] == a), ""), "?")
            cover_bits.append(f"{plat}({a})『已跳过：{why}』")
    add(f"# 发布核对（平台侧权威）· {ts}")
    add("")
    add(f"账号覆盖：{'、'.join(cover_bits)}")
    add("")
    add("| 任务 | 平台 | DB 状态 | 标题 | 平台侧 | 证据 |")
    add("|---|---|---|---|---|---|")

    miss: list[dict] = []
    for r in rows:
        t = r["task"]
        plat_cn = PLATFORM_CN.get(t["platform"], t["platform"])
        if r["found"] is True:
            mark = "✅ 在"
        elif r["found"] is False:
            mark = "❌ **不在**"
            miss.append(r)
        else:
            mark = "❓ 未覆盖"
        title = str(t["title"]).replace("|", "／")
        line = (f"| #{t['id']} | {plat_cn} | {t['status']} | {title} | {mark} "
                f"| {r['why']} |")
        add(line)

    add("")
    if miss:
        only_uncertain = all(m["task"]["status"] in ("uncertain", "failed")
                            for m in miss)
        add(f"## ⚠️ 平台侧**不存在**的 {len(miss)} 条")
        add("")
        for m in miss:
            t = m["task"]
            add(f"- **#{t['id']} [{PLATFORM_CN.get(t['platform'], t['platform'])}]** "
                f"{t['title']}  (DB 记为 `{t['status']}`)")
        add("")
        if only_uncertain:
            add("这些任务 DB 状态是 uncertain/failed —— 与平台侧一致，"
                "**可以补发**。补发前请确认：")
            add("")
            add("1. 本表是刚拉的（平台列表有延迟，但已发布作品不会有延迟）；")
            add("2. 补发前**没有**别的实例在写同一账号（`scripts/_proc_tree.py` 追浏览器归属）；")
            add("3. 补发后**再跑一次本脚本**复核 —— 别用任务的 `status` 当结论。")
        else:
            add("⚠️ 注意其中有 DB 记为 `done` 的条目 —— 那是**假成功**，"
                "按 skill `creatorhub-publish` §2/§3 排查发布器判定逻辑，不要直接重发。")
    else:
        add("## ✅ 全部命中 —— 没有任何任务缺作品")
    add("")
    for acc in accounts:
        ex = extra_notes.get(acc) or []
        if not ex:
            continue
        add(f"## 平台上多出来的作品（{PLATFORM_CN[AUDITABLE[acc]]} · {len(ex)} 件）")
        add("")
        add("这些在平台上存在、但 DB 里没有对应任务 —— 通常是更早期手工发的，"
            "或**别的实例/别的手动操作**发的。留个心眼：如果数量意外变多，"
            "要先怀疑是不是有重复投稿。")
        add("")
        for n in ex[:40]:
            nm = n.get("title") or n.get("caption") or ""
            # 时区语义按平台分：快手是毫秒 epoch(UTC)，小红书已经本地化好了。
            if AUDITABLE[acc] == "kuaishou":
                when = utc_to_bj(n.get("time") or n.get("uploadTime"))
            else:
                when = str(n.get("time") or "")[:16]
            add(f"- {when} · {str(nm)[:56]}")
        add("")

    # ★ 多条任务指向同一件作品：通常是"失败重试/补发"的历史，属正常；
    #   但如果出现在**我们没记为 uncertain/failed** 的条目上，就要留意是否有重复投稿。
    id2tasks: dict[tuple[str, str], list[int]] = {}
    for r in rows:
        if r["found"] is True:
            t = r["task"]
            wid = evidence[(t["platform"], title_key(t["title"]))]["id"]
            id2tasks.setdefault((t["platform"], str(wid)), []).append(t["id"])
    multi = {k: v for k, v in id2tasks.items() if len(v) > 1}
    if multi:
        add("## 多条任务指向同一件平台作品（多半是重试/补发历史，非错误）")
        add("")
        for (plat, wid), tids in multi.items():
            sts = {r["task"]["id"]: r["task"]["status"] for r in rows}
            detail = "、".join(f"#{i}({sts.get(i, '?')})" for i in sorted(tids))
            add(f"- {PLATFORM_CN.get(plat, plat)} 作品 `{wid}` ← {detail}")
        add("")

    text = "\n".join(lines)
    print(f"\n{'=' * 72}\n{text}\n{'=' * 72}")

    if not args.no_write:
        REPORTS.mkdir(parents=True, exist_ok=True)
        out = REPORTS / f"publish_audit_{time.strftime('%Y%m%d_%H%M%S')}.md"
        out.write_text(text, encoding="utf-8")
        print(f"已落盘: {out}")

    # 退出码：有缺失返回 3，全绿 0，有账号没覆盖返回 4
    if not_covered:
        return 4
    return 3 if miss else 0


if __name__ == "__main__":
    raise SystemExit(audit())
