# -*- coding: utf-8 -*-
"""删除**已发布**的视频号作品 —— 默认只探测，绝不真删。

为什么需要
----------
视频号后台没有批量删除接口（后台也没有开放 API），只能走「作品管理」页面的 UI。
而该页面的操作栏在 **shadow DOM** 里、事件是 Vue 的原生监听，Playwright 的
``locator.click()`` 会「点击成功但毫无反应」，必须用 JS ``el.click()``。

安全边界（★ 2026-09-21 封面误改事故的直接教训：回填脚本关键词没命中时静默回退到
「列表第一条」，把 B 作品的封面改错了，而视频号**每条作品只允许修改一次且不可撤回**）
----------------------------------------------------------------------------
1. **默认 dry-run**：不传 ``--apply`` 时只做「定位卡片 → 找『删除』条目 → 高亮 + 截图」，
   **一个删除类按钮都不点**。点删除只发生在显式 ``--apply`` 的分支里。
2. **关键词没命中就报错退出**：由 ``sh_open_delete.js`` 保证 ``ok=false`` 并回传前 8 条
   卡片文案；**绝不退化成「列表第一条」**，也不做模糊匹配兜底。
3. **点完二次确认后要用列表状态复验**：轮询「目标卡片从列表里消失」，消失才算成功；
   只看「点到了确认按钮」不算。

用法
----
::

    # 只探测（默认）：定位「删除」入口、高亮、落现场图，不点任何删除按钮
    ./.venv/Scripts/python.exe scripts/sh_delete_post.py --kw "华为在上海发了昇腾960" --tag probe

    # 真的删（不可逆；务必先用 dry-run 确认 --kw 命中的是目标作品）
    ./.venv/Scripts/python.exe scripts/sh_delete_post.py --kw "..." --apply --tag xxx

★ ``--kw`` 取的是**作品描述的正文**（视频号列表卡片不显示短标题），要取自
  ``publishtask.desc`` 的首段；拿标题会一张卡都匹配不到。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import traceback
from contextlib import suppress
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
for _p in (str(ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ★ 只**读**复用 backfill_cover.py 的骨架（建 context / 切 profile / 页面视口 /
#   落现场图 / dump_page），一行都不改它。
import backfill_cover as bf  # noqa: E402

DEBUG_DIR = bf.DEBUG_DIR
SH_MANAGE_URL = "https://channels.weixin.qq.com/platform/post/list"
DELETE_JS = "sh_open_delete.js"

ACCOUNT_ID = 3            # 视频号账号（= data/profiles/account_2dfcbc6e...）
MIN_VIEWPORT_W = 1920     # ★ 操作栏 rect.x ≈ 1353，窄于 1920 会被挤到屏幕外点不到

# 复验：目标卡片是否还在列表里。total=0 表示列表还没渲染出来，不算「已删除」。
VERIFY_JS = r"""
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const kw = String(__ARG__ || "");
  const norm = (s) => (s || "").replace(/\s+/g, "").trim();
  const roots = () => {
    const out = [{ root: document }];
    const dig = (r, d) => {
      if (!r || d > 5) return;
      let els = [];
      try { els = r.querySelectorAll("*"); } catch (e) { return; }
      for (const el of els) {
        if (el.shadowRoot) { out.push({ root: el.shadowRoot }); dig(el.shadowRoot, d + 1); }
      }
    };
    dig(document, 0);
    for (const f of document.querySelectorAll("iframe")) {
      let d = null;
      try { d = f.contentDocument; } catch (e) { d = null; }
      if (d && d.body) { out.push({ root: d }); dig(d, 0); }
    }
    return out;
  };
  const collect = () => {
    const items = [];
    for (const it of roots()) {
      let els = [];
      try { els = it.root.querySelectorAll('[class*="post-feed-item"]'); } catch (e) { continue; }
      for (const el of els) if (items.indexOf(el) < 0) items.push(el);
    }
    return items;
  };
  let items = [];
  for (let i = 0; i < 12; i++) { items = collect(); if (items.length) break; await sleep(2000); }
  let hit = false;
  for (const el of items) if (norm(el.textContent).indexOf(norm(kw)) >= 0) { hit = true; break; }
  // 顺带把页面顶部「视频 (26)」这个总数抠出来：删掉一条它会 26 → 25（_apply 的验收证据之一）
  let countText = "";
  for (const it of roots()) {
    let els = [];
    try { els = it.root.querySelectorAll("div,span,p,strong,b"); } catch (e) { continue; }
    for (const el of els) {
      const t = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (!/^视频\s*[（(]\s*\d+/.test(t)) continue;
      if (t.length > 40) continue;
      if (!countText || t.length < countText.length) countText = t;
    }
  }
  return { ok: true, total: items.length, hit: hit, kw: kw, countText: countText,
           heads: items.slice(0, 6).map((e) => norm(e.textContent).slice(0, 40)) };
})()
"""

# ★ 二次确认：**只找不点**。在**可见的、文案含「删除」的对话框**里挑出确认按钮，
#   把它的文案/class/屏幕矩形交回 Python 侧，由 Python 用**真实鼠标**去点。
#
#   ★ 2026-09-21 17:13 实测教训（apply --tag del76）：原来这里用 JS ``b.click()`` 直接点
#     「确定」，结果 ① 作品没被删掉（17:17 只读复验仍在列表里）② 进程死在那次
#     ``page.evaluate`` 上（既没有 confirm-miss 现场也没有 _after.png）——JS 合成点击
#     + 无超时的 evaluate 组合，出问题就完全查不出来。⇒ 改成：JS 只探测，Python 用
#     ``locator.click()`` / ``page.mouse.click()`` 真点，且每次调用都有超时兜底。
#
#   实测该弹窗结构（del76 那次的 dump）：div.weui-desktop-dialog(720,288,480,224)
#     > .weui-desktop-dialog__hd > .confirm-header 「删除视频」
#     > .footer>.weui-desktop-btn_wrp cancel 「取消」 (852,448,100,32)
#     > .footer>.weui-desktop-btn_wrp        「确定」 (968,448,100,32)  ← 要点的这个
#   注意：弹层里**没有**「删除后不可恢复」这类正文，标题就叫「删除视频」。
CONFIRM_FIND_JS = r"""
(() => {
  const norm = (s) => (s || "").replace(/\s+/g, "").trim();
  const rr = (el) => { const b = el.getBoundingClientRect();
    return [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)]; };
  const vis = (el) => {
    try {
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden") return false;
      if (Number(cs.opacity) === 0) return false;
      const b = el.getBoundingClientRect();
      return b.width > 1 && b.height > 1;
    } catch (e) { return false; }
  };
  const roots = () => {
    const out = [{ root: document }];
    const dig = (r, d) => {
      if (!r || d > 5) return;
      let els = [];
      try { els = r.querySelectorAll("*"); } catch (e) { return; }
      for (const el of els) {
        if (el.shadowRoot) { out.push({ root: el.shadowRoot }); dig(el.shadowRoot, d + 1); }
      }
    };
    dig(document, 0);
    for (const f of document.querySelectorAll("iframe")) {
      let d = null;
      try { d = f.contentDocument; } catch (e) { d = null; }
      if (d && d.body) { out.push({ root: d }); dig(d, 0); }
    }
    return out;
  };
  const wanted = ["确认删除", "删除作品", "确定", "确认"];
  const dialogs = [];
  for (const item of roots()) {
    let els = [];
    try {
      els = item.root.querySelectorAll(
        '[class*="dialog"],[class*="modal"],[class*="popup"],[class*="confirm"],[role="dialog"]');
    } catch (e) { continue; }
    for (const d of els) {
      if (!vis(d)) continue;
      const t = norm(d.textContent);
      if (t.indexOf("删除") < 0) continue;
      dialogs.push({ el: d, cls: String(d.className || "").slice(0, 80), rect: rr(d),
                     text: t.slice(0, 200) });
    }
  }
  if (!dialogs.length) return { ok: false, why: "没有可见的、文案含「删除」的对话框",
                                cands: [], seen: [] };
  // ★★ 2026-09-21 17:27 实测教训：原来用 ``dialogs[dialogs.length-1]`` 当作用域 —— 而
  //   `[class*="dialog"]` 会把弹层里的**每一层**都收进来（__wrp / __hd / __title /
  //   confirm-header…），DOM 顺序最后一个是**标题节点 confirm-header（文案「删除视频」）**，
  //   它里面根本没有「确定」按钮 ⇒ cands 只有标题、seen 只有「删除视频」，白跑一次。
  //   ⇒ 现在**不选容器了**：把所有「可见 + 文案含『删除』」的容器里的候选按钮**并集**起来，
  //     按 (text,rect) 去重后再挑 —— 容器层次怎么变都不影响。
  const cands = [];
  const dinfo = [];
  for (const box of dialogs) {
    dinfo.push({ cls: box.cls, rect: box.rect, text: box.text.slice(0, 120) });
    let inner = [];
    try { inner = box.el.querySelectorAll("button,a,div,span"); } catch (e) { inner = []; }
    for (const b of inner) {
      const bt = norm(b.textContent);
      if (!bt || bt.length > 8) continue;
      const c = String(b.className || "").slice(0, 80);
      const r = rr(b);
      const one = { text: bt, cls: c, tag: b.tagName, rect: r, visible: vis(b),
                    cancel: c.toLowerCase().indexOf("cancel") >= 0 || bt.indexOf("取消") >= 0,
                    inCls: box.cls };
      if (!cands.some((x) => x.text === one.text && x.rect[0] === r[0] && x.rect[1] === r[1])) {
        cands.push(one);
      }
    }
  }
  const seen = [];
  for (const c of cands) if (c.visible && seen.indexOf(c.text) < 0) seen.push(c.text);
  // ★★ 这里**只挑不点**（b.click() 已废弃，见文件头 17:13 的教训）。挑法：
  //   文案按 wanted 优先级精确匹配 → 必须可见 → **绝不选带 cancel 类或文案含「取消」的**
  //   → 同级里取面积最小的那个（最内层热区，中心点也最准）。
  let pick = null;
  for (const w of wanted) {
    for (const c of cands) {
      if (c.text !== w || !c.visible || c.cancel) continue;
      if (!pick || c.rect[2] * c.rect[3] < pick.rect[2] * pick.rect[3]) pick = c;
    }
    if (pick) break;
  }
  return { ok: !!pick,
           why: pick ? "" : "对话框里没有匹配的确认按钮（绝不乱点）",
           label: pick ? pick.text : "", cls: pick ? pick.cls : "",
           tag: pick ? pick.tag : "", rect: pick ? pick.rect : null,
           inCls: pick ? pick.inCls : "",
           dialogText: dinfo.length ? dinfo[0].text : "",
           dialogCls: dinfo.length ? dinfo[0].cls : "",
           dialogRect: dinfo.length ? dinfo[0].rect : null,
           cands: cands.slice(0, 14), seen: seen.slice(0, 14), dialogs: dinfo.slice(0, 8) };
})()
"""


def _log(msg: str) -> None:
    print(f"[sh-delete] {msg}", flush=True)


# ★ evaluate 一律加超时：17:13 那次就是卡在某次**没有超时**的 evaluate 上 —— 进程直接
#   没了，confirm-miss 现场和 _after.png 全都没落地，查无对证。宁可超时失败，不要静默卡死。
EVAL_TIMEOUT = 60.0      # JS 内部自己最长等 ~18s（弹窗轮询），再留足余量
CLICK_TIMEOUT = 15.0     # 单次真实鼠标点击


async def _js_file(page, filename: str, kw: str = "",
                   click_del: bool = False, click_more: bool = False) -> dict:
    """跑 scripts/<filename>（照抄 backfill_cover._sh_js，多支持两个布尔开关）。

    ★ ``click_del`` 默认 False —— 不显式置 True，JS 里的「删除」条目绝不会被点。
    """
    src = (SCRIPTS / filename).read_text(encoding="utf-8")
    src = src.replace("__ARG__", json.dumps(kw, ensure_ascii=False))
    src = src.replace("__CLICKDEL__", "true" if click_del else "false")
    src = src.replace("__CLICKMORE__", "true" if click_more else "false")
    try:
        res = await asyncio.wait_for(page.evaluate(src), EVAL_TIMEOUT)
    except asyncio.TimeoutError:
        return {"err": f"evaluate 超过 {EVAL_TIMEOUT:.0f}s 没返回（页面主线程可能被卡住）"}
    except Exception as exc:
        return {"err": repr(exc)[:300]}
    return res if isinstance(res, dict) else {"raw": res}


async def _js_src(page, src: str, arg: str = "") -> dict:
    if arg != "":
        src = src.replace("__ARG__", json.dumps(arg, ensure_ascii=False))
    try:
        res = await asyncio.wait_for(page.evaluate(src), EVAL_TIMEOUT)
    except asyncio.TimeoutError:
        return {"err": f"evaluate 超过 {EVAL_TIMEOUT:.0f}s 没返回（页面主线程可能被卡住）"}
    except Exception as exc:
        return {"err": repr(exc)[:300]}
    return res if isinstance(res, dict) else {"raw": res}


def _brief(res: dict) -> str:
    keys = ("ok", "total", "kw", "title", "entryFound", "entryText", "entryCls",
            "rect", "visible", "shadow", "moreClicked", "clickedDelete",
            "dialogShown", "why")
    return json.dumps({k: res.get(k) for k in keys if k in res}, ensure_ascii=False)


async def _shot(page, path: Path) -> None:
    try:
        await asyncio.wait_for(
            page.screenshot(path=str(path), full_page=False), 40)
        _log(f"截图 {path} ({path.stat().st_size} 字节)")
    except Exception as exc:
        _log(f"截图失败 {path}: {exc!r}")


async def _wait_dialog_gone(page, timeout: float) -> tuple[str, float]:
    """等二次确认弹窗消失。返回 ("gone" | "visible" | "unknown", 已等待秒数)。

    ★ 三态：``unknown`` = 探测本身出错（evaluate 超时/报错）——**绝不能当成 gone**，
      更不能拿它当理由去补点坐标（坐标是弹窗位置，弹窗没了就会点到下面的列表上）。
    """
    t0 = time.monotonic()
    while True:
        cf = await _js_src(page, CONFIRM_FIND_JS)
        waited = time.monotonic() - t0
        if "err" in cf:
            state = "unknown"
        else:
            state = "visible" if cf.get("ok") else "gone"
        if state != "visible" or waited >= timeout:
            return state, waited
        await page.wait_for_timeout(2000)


async def _locator_click_label(page, label: str) -> str:
    """① Playwright ``locator.click()``：真实鼠标事件 + 可操作性检查。

    作用域限定在 ``div.weui-desktop-dialog`` 内，文案精确等于实测到的 label
    （「确定」）；``.last`` 取最内层的那个，避开同名隐藏副本引发的 strict 冲突。
    """
    loc = page.locator("div.weui-desktop-dialog:visible").locator(f'text="{label}"').last
    await asyncio.wait_for(loc.click(timeout=8000), CLICK_TIMEOUT + 5)
    return f'locator(div.weui-desktop-dialog:visible >> text="{label}")'


async def _mouse_click_rect(page, rect) -> str:
    """② 兜底：按 JS 现测的 rect 做一次**真实鼠标**点击（先 move 再 click）。

    实测 rect=[968,448,100,32] → 点中心 (1018,464)。不依赖任何选择器。
    """
    if not (len(rect) == 4 and rect[2] > 0 and rect[3] > 0):
        return "rect 不可用，未点"
    cx, cy = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
    await page.mouse.move(cx, cy)
    await asyncio.wait_for(page.mouse.click(cx, cy), CLICK_TIMEOUT)
    return f"mouse.click({cx:.0f},{cy:.0f})"


async def _run(args) -> int:
    cfg = bf.load_config()
    bf.init_db(cfg.db_path)
    acc = bf.load_account(ACCOUNT_ID)
    platform = (acc.platform or "").strip()
    if platform != "shipinhao":
        raise SystemExit(f"本脚本只处理视频号；账号 {ACCOUNT_ID} 的平台是 {platform!r}")

    tag = args.tag or "probe"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    mode = "APPLY(真删)" if args.apply else "DRY-RUN(只探测)"
    _log(f"模式={mode} 账号={ACCOUNT_ID} kw={args.kw!r} tag={tag}")

    png_before = DEBUG_DIR / f"sh_del_{tag}_{stamp}_before.png"
    png_dialog = DEBUG_DIR / f"sh_del_{tag}_{stamp}_dialog.png"
    png_click1 = DEBUG_DIR / f"sh_del_{tag}_{stamp}_afterclick.png"
    png_click2 = DEBUG_DIR / f"sh_del_{tag}_{stamp}_afterclick2.png"
    png_after = DEBUG_DIR / f"sh_del_{tag}_{stamp}_after.png"

    mgr = bf.build_manager(cfg)
    await mgr.start()
    identity = mgr.identity_for(acc)
    page = None
    after_done = False
    try:
        ctx = await mgr.open_background(identity)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        vw = max(int(getattr(acc, "viewport_w", 0) or 0), MIN_VIEWPORT_W)
        vh = int(getattr(acc, "viewport_h", 0) or 0) or 1080
        await bf._apply_page_viewport(ctx, page, vw, vh)
        _log(f"打开 {SH_MANAGE_URL}")
        await page.goto(SH_MANAGE_URL, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(14000)

        # ── ① 只定位：找目标卡片 + 「删除」条目（**这一步永不点删除**，apply 也一样） ──
        res = await _js_file(page, DELETE_JS, args.kw, click_del=False, click_more=True)
        _log(f"列表入口: {_brief(res)}")
        evidence = DEBUG_DIR / f"sh_del_{tag}_{stamp}.json"
        evidence.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        _log(f"JS 原始返回 {evidence}")

        if not res.get("ok"):
            info = await bf.dump_page(page, f"shdel-{tag}-nomatch")
            _log("★ 中止：关键词没命中目标卡片 / 没找到「删除」条目（绝不退化成列表第一条）")
            _log("  heads(列表前 8 条卡片文案)=" + json.dumps(res.get("heads"), ensure_ascii=False))
            _log("  entries(操作栏 dump)=" + json.dumps(res.get("entries"), ensure_ascii=False)[:2500])
            _log("  delTexts(全页含「删除」的短文案)="
                 + json.dumps(res.get("delTexts"), ensure_ascii=False)[:2000])
            _log(f"  现场 {info.get('screenshot')}")
            return 1

        _log(f"命中卡片 title={res.get('title')!r} total={res.get('total')} "
             f"inner={res.get('inner')}")
        _log(f"找到「删除」条目: text={res.get('entryText')!r} cls={res.get('entryCls')!r} "
             f"tag={res.get('entryTag')} rect={res.get('rect')} "
             f"visible={res.get('visible')} shadow={res.get('shadow')}")
        _log("操作栏条目 dump(entries)=" + json.dumps(res.get("entries"), ensure_ascii=False)[:2500])

        # ★ 真·「删除前」现场：先只 hover 命中卡片（让操作栏绘制出来），再截图。
        #   17:13 那次的 _before.png 其实是「弹窗已打开」之后拍的（与 _dialog.png 逐字节相同），
        #   名不副实 ⇒ 现在把「定位」和「点删除」拆成两步，这张才是删除前。
        card = res.get("cardRect") or []
        if len(card) == 4 and card[2] > 0:
            await page.mouse.move(card[0] + card[2] / 2, card[1] + card[3] / 2)
            _log(f"鼠标已移到命中卡片中心（无害 hover，cardRect={card}）")
            await page.wait_for_timeout(1500)
        await _shot(page, png_before)
        base_chk = await _js_src(page, VERIFY_JS, args.kw)
        _log(f"删除前基线: total={base_chk.get('total')} hit={base_chk.get('hit')} "
             f"页面总数={base_chk.get('countText')!r}")

        # ── ② dry-run：停在这里（至此没点过任何删除类按钮） ──────────────────
        if not args.apply:
            _log("[dry-run] 已把「删除」条目高亮并落图，**没有点任何删除类按钮**，到此退出")
            _log("页面里已有的「删除」相关对话框(可见=正在展示 / 不可见=预渲染模板)="
                 + json.dumps(res.get("dialogs"), ensure_ascii=False)[:2500])
            return 0

        # ── ③ apply：点「删除」条目 → 等二次确认弹窗 ─────────────────────────
        res2 = await _js_file(page, DELETE_JS, args.kw, click_del=True, click_more=False)
        _log(f"点「删除」条目后: {_brief(res2)}")
        if not res2.get("entryFound"):
            info = await bf.dump_page(page, f"shdel-{tag}-relocate-fail")
            _log(f"★ 第二次没能重新定位到「删除」条目（**不会盲点**），中止"
                 f"（现场 {info.get('screenshot')}）")
            return 1
        _log(f"clickedDelete={res2.get('clickedDelete')} dialogShown={res2.get('dialogShown')}")
        vis_dialogs = [d for d in (res2.get("dialogs") or []) if d.get("visible")]
        _log("可见的确认弹窗=" + json.dumps(vis_dialogs, ensure_ascii=False)[:2500])
        if not res2.get("dialogShown"):
            info = await bf.dump_page(page, f"shdel-{tag}-nodialog")
            _log(f"★ 点了「删除」但没等到二次确认弹窗，中止（现场 {info.get('screenshot')}）")
            return 1
        await _shot(page, png_dialog)

        # ── ④ 找「确定」按钮（**只读探测，不点**） ────────────────────────────
        cf = await _js_src(page, CONFIRM_FIND_JS)
        _log(f"确认按钮探测: ok={cf.get('ok')} label={cf.get('label')!r} cls={cf.get('cls')!r} "
             f"tag={cf.get('tag')} rect={cf.get('rect')} inCls={cf.get('inCls')!r} "
             f"why={cf.get('why')}")
        _log("弹层容器(dialogs)=" + json.dumps(cf.get("dialogs"), ensure_ascii=False)[:1500])
        _log("弹层文案=" + json.dumps(cf.get("dialogText"), ensure_ascii=False))
        _log("弹层内候选按钮(cands)=" + json.dumps(cf.get("cands"), ensure_ascii=False)[:2200])
        _log("弹层内可见短文案(seen)=" + json.dumps(cf.get("seen"), ensure_ascii=False))
        if not cf.get("ok"):
            info = await bf.dump_page(page, f"shdel-{tag}-confirm-miss")
            _log(f"★ 没找到可点的确认按钮（绝不乱点），中止（现场 {info.get('screenshot')}）")
            return 1

        # 点击前**现测**一次坐标（弹层可能有位移），坐标只用来做兜底点击
        cf = await _js_src(page, CONFIRM_FIND_JS)
        if not cf.get("ok"):
            info = await bf.dump_page(page, f"shdel-{tag}-confirm-recheck")
            _log(f"★ 点击前坐标复测失败，中止（现场 {info.get('screenshot')}）")
            return 1
        label = cf.get("label") or "确定"
        rect = cf.get("rect") or []
        _log(f"点击前现测: label={label!r} rect={rect}（中心 "
             f"{rect[0] + rect[2] / 2 if len(rect) == 4 else '?'},"
             f"{rect[1] + rect[3] / 2 if len(rect) == 4 else '?'}）")

        # ── ⑤ 真实鼠标点「确定」：locator 优先，落回 mouse.click；每步都截图 ──
        how1 = ""
        try:
            how1 = await _locator_click_label(page, label)
            _log(f"① locator.click 成功: {how1}")
        except Exception as exc:
            how1 = f"locator 失败:{exc!r}"
            _log(f"① locator.click 失败: {exc!r}")
        await _shot(page, png_click1)          # ★ 点完**立刻**截图
        state, waited = await _wait_dialog_gone(page, 12.0)
        _log(f"① 之后弹窗状态={state}（等了 {waited:.1f}s）")

        how2 = ""
        if state == "visible":
            # ① 没生效 ⇒ 落回真实鼠标点 JS 现测的 rect 中心
            try:
                how2 = await _mouse_click_rect(page, rect)
                _log(f"② page.mouse.click: {how2}")
            except Exception as exc:
                how2 = f"mouse.click 失败:{exc!r}"
                _log(f"② page.mouse.click 失败: {exc!r}")
            await _shot(page, png_click2)
            state, waited = await _wait_dialog_gone(page, 24.0)
            _log(f"② 之后弹窗状态={state}（又等了 {waited:.1f}s）")
        elif state == "unknown":
            _log("★ 弹窗状态探测失败(unknown)：**不做兜底点击**（坐标可能已不在弹窗上）")

        _log(f"点「确定」的结果: ① {how1} / ② {how2 or '(未启用)'} → 弹窗 {state}")
        if state == "visible":
            info = await bf.dump_page(page, f"shdel-{tag}-confirm-noeffect")
            _log(f"★ 点了「确定」但二次确认弹窗**仍可见**（按未生效处理，**不再重复点**）"
                 f"（现场 {info.get('screenshot')}）")
            return 1

        # ── ⑥ 复验：列表里目标卡片必须消失（total 20 → 19） ──────────────────
        gone, chk, detail = False, {}, ""
        for i in range(8):
            await page.wait_for_timeout(3000)
            chk = await _js_src(page, VERIFY_JS, args.kw)
            detail = (f"第 {i + 1} 次: total={chk.get('total')} hit={chk.get('hit')} "
                      f"页面总数={chk.get('countText')!r}")
            if chk.get("total", 0) > 0 and chk.get("hit") is False:
                gone = True
                break
        if not gone:
            _log(f"列表没刷新出新状态({detail})，重新打开列表页再复验")
            await page.goto(SH_MANAGE_URL, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(14000)
            for i in range(8):
                chk = await _js_src(page, VERIFY_JS, args.kw)
                detail = (f"重载后第 {i + 1} 次: total={chk.get('total')} "
                          f"hit={chk.get('hit')} 页面总数={chk.get('countText')!r}")
                if chk.get("total", 0) > 0 and chk.get("hit") is False:
                    gone = True
                    break
                await page.wait_for_timeout(3000)

        await _shot(page, png_after)
        after_done = True
        _log(f"复验结果: gone={gone} {detail}")
        if not gone:
            info = await bf.dump_page(page, f"shdel-{tag}-unverified")
            _log("★ 点了确认但目标卡片**仍在列表里**，按未删除处理，请到后台人工复核"
                 f"（现场 {info.get('screenshot')}）")
            _log("  列表前 6 条=" + json.dumps(chk.get("heads"), ensure_ascii=False))
            return 1
        _log("★ 已确认目标作品从列表消失，删除生效")
        return 0
    except Exception:
        _log("★ 未捕获异常（完整栈如下，绝不再静默死去）:\n" + traceback.format_exc())
        return 1
    finally:
        # ★ 无论从哪条路径退出（成功 / 失败 / 异常 / 超时），都必须留下 _after.png
        if page is not None and not after_done:
            with suppress(Exception):
                await _shot(page, png_after)
        with suppress(Exception):
            await mgr.stop_minimize_hold(identity)
        with suppress(Exception):
            await mgr.stop()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="删除视频号已发布作品（默认只探测，绝不真删）")
    parser.add_argument("--kw", required=True,
                        help="作品**文案**关键词（必填；必须能在列表卡片里命中。"
                             "视频号列表显示的是描述正文，不是短标题）")
    parser.add_argument("--apply", action="store_true",
                        help="★ 真的点「删除」并处理二次确认（默认 dry-run：只定位+高亮+截图）")
    parser.add_argument("--tag", default="", help="落盘文件名后缀")
    args = parser.parse_args()
    if not (args.kw or "").strip():
        # 空关键词 = 无法确定点哪一条 ⇒ 按「绝不猜」中止（杜绝「取列表第一条」）
        raise SystemExit("--kw 不能为空：按「绝不猜」中止（绝不退化成列表第一条）")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
