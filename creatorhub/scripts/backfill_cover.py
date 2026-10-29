"""给**已发布**作品后补封面。

为什么需要这个脚本
------------------
creatorhub 的 ``PublishIn`` / ``PublishTask`` 都没有封面对应字段,封面只在发布
环节由各平台发布器 best-effort 设置 —— 目前只有 ``channels/publish.py``(视频号)
真正实现了 ``_set_cover``,抖音/快手/小红书三家的作品封面一律由平台自动截帧。

而本机需求是「一张封面四个平台用」,视频号发布时已套上,另外三家要在**发布之后**
回到各自创作后台的「作品管理」里改封面。

用法
----
::

    # 只读探测:打开作品管理页,dump 可见文案 + 卡片上的操作入口
    python -m scripts.backfill_cover probe --account 1 --platform douyin

    # 真的改封面(会触发平台重新审核),按标题前缀定位作品
    python -m scripts.backfill_cover apply --account 1 --platform douyin \
        --cover "D:/.../cover-N90-1080x1920.png" --title "26.99万的小米澎程N90，值吗"

设计约束
--------
* **不许抢焦点**:统一走 ``BrowserManager.open_background()``(有头但最小化、
  绝不置顶)。用户明确投诉过反复弹窗顶掉他正在用的窗口。
* **只读探测与写操作分成两条命令**,写操作前必须先 probe 确认入口存在。
* 每次操作都把现场落到 ``data/debug/``(截图 + innerText),便于事后复核。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from contextlib import suppress
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlmodel import select  # noqa: E402

from app.browser.manager import BrowserManager  # noqa: E402
from app.config import load_config  # noqa: E402
from app.db import get_session, init_db  # noqa: E402
from app.models import DouyinAccount  # noqa: E402

# 各平台「作品/内容管理」入口。视频号不需要(封面是发布前置条件,已在发布时设置)。
MANAGE_URL = {
    "douyin": "https://creator.douyin.com/creator-micro/content/manage",
    "kuaishou": "https://cp.kuaishou.com/article/manage/video",
    # ★ 真实入口是 /new/note-manager(2026-09-14 从左侧菜单点进去确认);
    #   旧记的 /new/note-manage/note-manage 会 404「你访问的页面不见了」。
    "xhs": "https://creator.xiaohongshu.com/new/note-manager",
}

# 卡片上可能出现的「改封面」相关入口文案。抖音叫「修改」,快手叫「编辑」,
# 小红书叫「编辑」;先都收进来,由 probe 的真实结果再收紧。
ENTRY_KW = ("编辑", "修改", "封面", "更多", "管理", "更换", "设置")

DEBUG_DIR = ROOT / "data" / "debug"


def _log(msg: str) -> None:
    print(f"[backfill] {msg}", flush=True)


async def _apply_page_viewport(ctx, page, width: int, height: int) -> None:
    """把**页面视口**顶到账号配置的尺寸(不动原生窗口)。

    ★ 为什么要这一步:窗口按用户要求被压成**最小化**(不许抢焦点),此时 Chromium
      报出来的 ``innerWidth`` 只有 ~786×450 —— 平台会切到**窄屏响应式布局**,把卡片上
      的操作按钮整个藏掉(踩过:快手作品卡片 ``entries`` 全空、hover 菜单也没有)。
      窗口不能还原,所以只能改**页面视口**:CDP
      ``Emulation.setDeviceMetricsOverride`` 只影响渲染层,不改变原生窗口状态与置顶关系。
      顺带把视口对齐到账号指纹里的尺寸(``viewport_w/h``),对写操作的风控更一致。
    """
    try:
        session = await ctx.new_cdp_session(page)
        try:
            await session.send("Emulation.setDeviceMetricsOverride", {
                "width": int(width), "height": int(height),
                "deviceScaleFactor": 1, "mobile": False,
            })
        finally:
            with suppress(Exception):
                await session.detach()
        size = await page.evaluate("[window.innerWidth, window.innerHeight]")
        _log(f"页面视口已设为 {width}x{height}(实际 inner={size},原生窗口保持最小化)")
    except Exception as exc:
        _log(f"设置页面视口失败(继续): {exc!r}")


def build_manager(cfg) -> BrowserManager:
    """按 ``app/main.py`` 的 lifespan 装配一个等价的管理器。

    本机 ``browserruntime`` 表为空、账号 ``browser_backend`` 是 default/local,
    所以省掉指纹内核相关的入参不影响实际使用的 Chromium 二进制。
    """
    return BrowserManager(
        cfg.engine.user_agent, cfg.engine.profiles_dir,
        cfg.engine.max_live_contexts,
        native_ua_callback=None,
        xhs_browser_mode=cfg.engine.xhs_browser_mode,
        xhs_cdp_idle_seconds=cfg.engine.xhs_cdp_idle_seconds,
        resident_sessions=cfg.engine.resident_browser_sessions,
        session_idle_seconds=cfg.engine.browser_session_idle_seconds,
        native_write_gate_enabled=cfg.engine.native_write_gate_enabled,
        native_write_require_system_chrome=(
            cfg.engine.native_write_require_system_chrome),
        native_write_require_verified_proxy=(
            cfg.engine.native_write_require_verified_proxy),
        native_write_proxy_max_age_seconds=(
            cfg.engine.native_write_proxy_max_age_seconds),
        browser_exit_probe_url=cfg.engine.browser_exit_probe_url,
        browser_backend=cfg.engine.browser_backend,
    )


def load_account(account_id: int) -> DouyinAccount:
    with get_session() as session:
        acc = session.exec(
            select(DouyinAccount).where(DouyinAccount.id == account_id)
        ).first()
    if acc is None:
        raise SystemExit(f"账号 {account_id} 不存在")
    return acc


async def dump_page(page, tag: str, clip: str = "") -> dict:
    """把当前页面与所有 iframe 的可见文案、候选操作入口落盘。"""
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    info: dict = {"url": page.url, "frames": [], "entries": [], "tag": tag}
    full: list = []

    for frame in page.frames:
        try:
            text = await frame.inner_text("body")
        except Exception as exc:
            info["frames"].append({"url": frame.url[:90], "err": repr(exc)[:80]})
            continue
        text = text or ""
        info["frames"].append({
            "url": frame.url[:90],
            "len": len(text),
            "head": "\n".join(text.splitlines()[:40])[:1200],
        })
        full.append((frame.url[:90], text[:40000]))
        # 入口候选:短文案里含关键词的元素
        for sel in ("button", "a", '[role="button"]', '[class*="btn"]',
                    '[class*="operat"]', '[class*="action"]'):
            try:
                loc = frame.locator(sel)
                count = min(await loc.count(), 120)
            except Exception:
                continue
            for index in range(count):
                node = loc.nth(index)
                try:
                    if not await node.is_visible():
                        continue
                    label = " ".join((await node.inner_text() or "").split())
                except Exception:
                    continue
                if not label or len(label) > 14:
                    continue
                if any(word in label for word in ENTRY_KW):
                    tag_pair = {"frame": frame.url[:70], "sel": sel, "label": label}
                    if tag_pair not in info["entries"]:
                        info["entries"].append(tag_pair)

    png = DEBUG_DIR / f"cover_{tag}_{stamp}.png"
    shot_kw = {}
    if clip:
        try:
            parts = [float(v) for v in clip.split(",")]
            if len(parts) == 4:
                shot_kw["clip"] = {"x": parts[0], "y": parts[1],
                                   "width": parts[2], "height": parts[3]}
        except Exception:
            pass
    try:
        await page.screenshot(path=str(png), full_page=False, **shot_kw)
        info["screenshot"] = str(png)
    except Exception as exc:
        info["screenshot_err"] = repr(exc)[:120]
        # ★ 回退:小红书这类站点的 web font 一直不 settle,Playwright 的
        #   screenshot 会卡在 "waiting for fonts to load" 直到超时;
        #   直接走 CDP 的 Page.captureScreenshot 不吃这套。
        try:
            session = await page.context.new_cdp_session(page)
            try:
                params: dict = {"format": "png"}
                if shot_kw.get("clip"):
                    clip = shot_kw["clip"]
                    params["clip"] = {"x": clip.get("x", 0), "y": clip.get("y", 0),
                                      "width": clip.get("width", 1600),
                                      "height": clip.get("height", 900), "scale": 1}
                raw = await session.send("Page.captureScreenshot", params)
            finally:
                with suppress(Exception):
                    await session.detach()
            import base64 as _b64
            png.write_bytes(_b64.b64decode(raw["data"]))
            info["screenshot"] = str(png)
            info["screenshot_via"] = "cdp"
        except Exception as exc2:
            info["screenshot_err_cdp"] = repr(exc2)[:120]

    txt = DEBUG_DIR / f"cover_{tag}_{stamp}.txt"
    txt.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    raw = DEBUG_DIR / f"cover_{tag}_{stamp}.full.txt"
    with raw.open("w", encoding="utf-8") as fh:
        for furi, ftext in full:
            fh.write(f"===== {furi} =====\n{ftext}\n\n")
    info["full_text"] = str(raw)
    return info


def _viewport_from(args, acc) -> tuple[int, int]:
    """页面视口尺寸:``--viewport WxH`` 优先,否则用账号指纹里的 ``viewport_w/h``。"""
    if getattr(args, "viewport", ""):
        try:
            width, height = args.viewport.lower().replace("×", "x").split("x")
            return int(width), int(height)
        except Exception:
            _log(f"--viewport 解析失败({args.viewport!r}),改用账号指纹尺寸")
    return (int(getattr(acc, "viewport_w", 0) or 1280),
            int(getattr(acc, "viewport_h", 0) or 800))


def _title_probe(title: str) -> str:
    return "".join(title.split())[:8]


async def _safe_click(page, labels, wait_ms: int = 2500) -> str:
    """按文案点第一个可见命中,返回命中的 label(空串=都没找到)。"""
    for label in labels:
        for frame in page.frames:
            for sel in (f'text="{label}"', f'text={label}'):
                try:
                    loc = frame.locator(sel)
                    if await loc.count() == 0:
                        continue
                    node = loc.first
                    if not await node.is_visible():
                        continue
                    await node.scroll_into_view_if_needed(timeout=3000)
                    await node.click(timeout=4000)
                    await page.wait_for_timeout(wait_ms)
                    return label
                except Exception:
                    continue
    return ""


async def _dismiss_overlays(page, rounds: int = 3) -> None:
    """连按 Escape 收起话题自动补全/浮层。

    ★ 抖音编辑页的「话题自动补全」下拉会盖住「封面」区,不收起就点不到「设置封面」。
    ★ 千万别用 ``page.mouse.click(3, 3)`` 之类的「点空白处」收浮层 —— 抖音左侧
      那一列是导航栏,左上角 (3,3) 就是**返回首页的 logo**,一点就被带走了(已踩)。
    """
    for _ in range(rounds):
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await page.wait_for_timeout(500)


_HOVER_JS = ROOT / "scripts" / "_probe_hover.js"
_COVER_JS = ROOT / "scripts" / "_probe_cover.js"
_MARK_UPLOAD_JS = ROOT / "scripts" / "_mark_upload_input.js"
_MARK_THUMBS_JS = ROOT / "scripts" / "_mark_cover_thumbs.js"
_MARK_KS_EDIT_JS = ROOT / "scripts" / "_mark_ks_edit.js"
_MARK_KS_UPLOAD_JS = ROOT / "scripts" / "_mark_ks_upload.js"
_MARK_XHS_EDIT_JS = ROOT / "scripts" / "_mark_xhs_edit.js"
_MARK_XHS_UPLOAD_JS = ROOT / "scripts" / "_mark_xhs_upload.js"
_FORCE_XHS_COVER_JS = ROOT / "scripts" / "_force_xhs_cover_ui.js"
_COVER_THUMBS_JS = ROOT / "scripts" / "_cover_thumbs.js"

_HOVER_STYLE_ID = "bfc-hover-show"


async def _force_show_hover(page) -> bool:
    """注入一段**带 id 的** CSS,把 `[class*="hover-show"]` 强制显示。

    ★ 抖音的「编辑封面」挂在 `hover-show-*` 上,默认 `display:none`,靠 CSS `:hover`
      才显示;在最小化窗口里 `page.mouse.move()` **不生效**(computed display 恒为 none),
      合成 `mouseover/mouseenter` 也无效(CSS 伪类不吃合成事件)→ 只能改样式层。
    ★ 必须能**撤掉**:这段样式会把「编辑封面」黑框盖在封面缩略图上,污染像素指纹。
      所以不用 `add_style_tag`(拿不到可辨识的句柄),改成自己建带 id 的 `<style>`。
    """
    try:
        await page.evaluate(
            """(id) => {
              let s = document.getElementById(id);
              if (!s) {
                s = document.createElement('style');
                s.id = id;
                document.head.appendChild(s);
              }
              s.textContent = '[class*="hover-show"]{display:block!important;}';
            }""",
            _HOVER_STYLE_ID,
        )
        return True
    except Exception as exc:
        _log(f"注入 hover-show 样式失败: {exc!r}")
        return False


async def _clear_hover_show(page) -> None:
    """撤掉 ``_force_show_hover`` 注入的样式,让封面缩略图恢复"干净"像素。"""
    try:
        await page.evaluate(
            "(id) => { const s = document.getElementById(id); if (s) s.remove(); }",
            _HOVER_STYLE_ID,
        )
    except Exception:
        pass


async def _scroll_text_into_view(page, text: str) -> bool:
    for frame in page.frames:
        try:
            node = frame.locator(f'text="{text}"').first
            if await node.count():
                await node.scroll_into_view_if_needed(timeout=5000)
                await page.wait_for_timeout(1200)
                return True
        except Exception:
            continue
    return False


async def _open_cover_editor(page) -> str:
    """抖音:把「封面」区滚进视野 → 强制显示 hover-show 的「编辑封面」→ 点开。

    ★ 坑一:编辑页里文案为「设置封面」的只是一个 **区块标题 DIV**(cls `title-*`),
      点它什么也不会发生。
    ★ 坑二:真正能点的是 `编辑封面`,而它挂在 `hover-show-*` 类上 —— 默认
      `display:none`,**靠 CSS `:hover` 才显示**。实测在 `open_background()` 的
      **最小化**窗口里,`page.mouse.move()` 悬停**不生效**(computed display 始终
      是 none),合成 `mouseover/mouseenter` 事件也无效(CSS 伪类不吃合成事件)。
      → 直接注入一小段 CSS 把 `[class*="hover-show"]` 强制 `display:block`。
        这只影响渲染层,点上去仍走平台原本的点击回调,安全且确定。
    """
    await _scroll_text_into_view(page, "竖封面3:4")
    await _force_show_hover(page)
    await page.wait_for_timeout(1200)

    editors = page.get_by_text("编辑封面", exact=True)
    _log(f"封面入口数量: {await editors.count()}")
    for index in range(min(await editors.count(), 4)):
        node = editors.nth(index)
        try:
            if not await node.is_visible():
                continue
            await node.click(timeout=5000, force=True)
            await page.wait_for_timeout(3000)
            inputs = await page.locator('input[type="file"]').count()
            _log(f"封面入口#{index} 点击后 file input={inputs}")
            if inputs > 0:
                return f"编辑封面#{index}"
            await node.evaluate("e => e.parentElement.click()")
            await page.wait_for_timeout(3000)
            inputs = await page.locator('input[type="file"]').count()
            _log(f"封面入口#{index} 父元素点击后 file input={inputs}")
            if inputs > 0:
                return f"编辑封面#{index} parent"
        except Exception as exc:
            _log(f"封面入口#{index} 点击失败: {exc!r}")
            continue

    # 退路:悬停 + 按坐标点(万一那个窗口里 :hover 其实是好的)
    for attempt in range(3):
        try:
            info = await page.evaluate(_HOVER_JS.read_text(encoding="utf-8"))
            target = (info or {}).get("target") if isinstance(info, dict) else None
        except Exception:
            target = None
        if target:
            await page.mouse.move(target["x"], target["y"], steps=8)
            await page.wait_for_timeout(1200)
        rect = None
        try:
            probe = await page.evaluate(_COVER_JS.read_text(encoding="utf-8"))
            for item in (probe or {}).get("matched", []):
                r = item.get("rect") or [0, 0, 0, 0]
                if item.get("txt") == "编辑封面" and r[2] > 20:
                    rect = r
                    break
        except Exception:
            rect = None
        if rect:
            cx, cy = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
            await page.mouse.click(cx, cy)
            await page.wait_for_timeout(5000)
            return "编辑封面(坐标)"
        await _scroll_text_into_view(page, "竖封面3:4")
        await page.wait_for_timeout(1000)
    return ""


async def _apply_douyin(page, ctx, args) -> tuple[bool, str]:
    """抖音:作品管理 → 搜索定位 → 编辑作品 → 设置封面 → 提交修改。

    已确认的入口(2026-09-14 实测):编辑页 URL 是
    ``/creator-micro/content/post/video?mid=<id>&enter_from=edit_item``,
    页面上有「设置封面」、封面弹层里有「竖封面3:4 / 横封面4:3」两个 tab,
    保存按钮文案是「提交修改」。
    """
    probe = args.search or _title_probe(args.title)
    note = await _apply_search(page, probe)
    _log(f"定位作品: {note}")
    await page.wait_for_timeout(7000)
    await _safe_click(page, ["知道了"], wait_ms=1500)   # 「合集管理移到这里啦」提示

    # 搜索框可能没有真正筛选列表（置顶作品仍排第一）。必须在标题所属卡片内点击。
    cards = page.locator('[class*="video-card-sfa"]')
    matching = cards.filter(has_text=args.title)
    count = await matching.count()
    if count != 1:
        return False, f"按完整标题定位作品卡片得到 {count} 条，未点击任何编辑入口"
    edit = matching.get_by_text("编辑作品", exact=True)
    if await edit.count() != 1:
        return False, f"目标作品卡片的编辑入口有 {await edit.count()} 个，未点击"
    await edit.click(timeout=5000)
    await page.wait_for_timeout(4000)
    await page.wait_for_timeout(9000)
    # ★ 必须确认真的进了编辑页:编辑页 URL 形如
    #   /creator-micro/content/post/video?mid=<id>&enter_from=edit_item
    if "/content/post/" not in page.url:
        return False, f"点了「编辑作品」但没进编辑页,当前 URL={page.url[:120]}"
    _log(f"已进入编辑页 {page.url[:110]}")
    await _dismiss_overlays(page)
    await _safe_click(page, ["我知道了"], wait_ms=1000)

    # ★ 上传前的像素基线(此时还没注入 hover-show 样式,缩略图是"干净"的)。
    #   ★ 2026-09-21 #65(xpengg9l) 在这里连续失败三轮(「没找到封面缩略图(锚点命中 2 个,
    #     但近邻都没 img)」),而几十秒后的"上传后"探针却读得到 ⇒ 真因在
    #     ``_cover_signature`` 里(滚动后死等 900ms 就读 img,而封面区是懒加载的),
    #     已在那里改成**轮询等 img**。这里保留一层重试 + 逐次打日志,便于以后看时序。
    #   ★★ 顺序也改了:原来是「先投喂封面、再检查基线」,于是拿不到基线时白投喂一趟
    #     (不消耗抖音「每个作品最多修改 5 次」的名额,但白花 ~30s 并把编辑表单弄脏)。
    #     现在**基线拿不到就直接中止,封面编辑器都不打开**。
    base: dict = {}
    for attempt in range(5):
        base = await _cover_signature(page, "base")
        if base.get("ok"):
            break
        _log(f"第 {attempt + 1}/5 次取封面基线失败: {base.get('why')}(等 3s 再试)")
        await page.wait_for_timeout(3000)
    _log(f"封面基线: digest={base.get('digest') or base.get('why')} "
         f"stable={base.get('stable')} labels={base.get('labels')} src={base.get('srcs')}")
    if not base.get("ok"):
        info = await dump_page(page, "cover-nobaseline")
        return False, (f"拿不到上传前的封面像素基线({base.get('why')})"
                       f"⇒ **未做任何修改**(没打开封面编辑器、没投喂封面)"
                       f";现场 {info.get('screenshot')}")

    hit = await _open_cover_editor(page)
    if not hit:
        return False, "编辑页没能打开封面编辑器(hover-show 的「编辑封面」没点中)"
    _log("已打开封面编辑器")

    if args.dry_run:
        if args.js_file:
            # 诊断用:在「封面弹层打开」的状态下枚举真实 DOM 结构
            try:
                snippet = Path(args.js_file).read_text(encoding="utf-8")
                if args.js_arg:
                    snippet = snippet.replace(
                        "__ARG__", json.dumps(args.js_arg, ensure_ascii=False))
                res = await page.evaluate(snippet)
                print("=== JS 结果 ===")
                print(json.dumps(res, ensure_ascii=False, indent=1)[:12000])
            except Exception as exc:
                _log(f"JS 执行失败: {exc!r}")
        info = await dump_page(page, "apply-dry")
        _log(f"[dry-run] 停在这里。截图 {info.get('screenshot')} / 全文 {info.get('full_text')}")
        return False, "dry-run:已停在封面弹层,未做任何修改"

    # 上传封面文件(内部会点「完成」关掉封面编辑器)
    ok_upload, detail = await _upload_cover(page, args.cover)
    if not ok_upload:
        return False, detail
    _log(f"封面文件已投喂: {detail}")

    # ★★ 硬断言:封面**像素**必须真的变了。不通过就如实报失败 ——
    #    上一版脚本正是因为缺少这一步,喂错 input 之后一路报成功(典型假成功)。
    # ★ 撤掉 hover-show 样式(否则「编辑封面」黑框盖在缩略图上,像素与基线不可比)
    await _clear_hover_show(page)
    after = None
    for attempt in range(4):
        await page.wait_for_timeout(3500)
        cand = await _cover_signature(page, "after")
        if not cand.get("ok"):
            _log(f"第 {attempt + 1} 次取上传后指纹失败: {cand.get('why')}")
            after = cand
            continue
        after = cand
        if not base.get("ok") or cand["digest"] != base["digest"]:
            break
    _log(f"封面上传后: digest={after.get('digest') or after.get('why')} "
         f"stable={after.get('stable')} labels={after.get('labels')} src={after.get('srcs')}")

    # ★ base 在打开封面编辑器**之前**就已断言 ok(否则早就 return 了),所以这里
    #   不再需要 「if not base.get('ok')」 分支 —— 那是上一版的死代码(且顺序错:
    #   它会在白投喂一趟封面之后才报失败)。
    if not after.get("ok"):
        await dump_page(page, "cover-nosig")
        return False, (f"拿不到上传后的封面像素({after.get('why')}),无法断言;按未生效处理")
    if after["digest"] == base["digest"]:
        await dump_page(page, "cover-unchanged")
        return False, (f"封面文件投喂成功,但**像素前后一致**({after['digest']}),说明封面没真正换掉"
                       f"→ 按失败处理,未提交修改。基线图 {base.get('pngs')} / 上传后图 {after.get('pngs')}")
    if not (base.get("stable") and after.get("stable")):
        _log("警告:像素基线不稳定(页面在动),指纹差异可能含渲染抖动,已记录但继续")
    _log(f"封面像素已确认变化: {base['digest']} → {after['digest']}")

    # 保存整个编辑
    if not await _safe_click(page, ["提交修改"], wait_ms=6000):
        return False, (f"封面像素已确认变化({base['digest']}→{after['digest']}),"
                       f"但没找到「提交修改」按钮,改动未保存")
    await page.wait_for_timeout(8000)
    return True, (f"封面已更换并提交修改(像素 {base['digest']}→{after['digest']}, "
                  f"来源 {args.cover})")


async def _mark_upload_input(page) -> dict:
    """把封面弹层里**真正的投放区** ``input[type=file]`` 标上 ``data-bfc-upload="1"``。

    见 ``scripts/_mark_upload_input.js`` 的注释:同一页面还有「AI生成封面/生成参考图」
    区的别的图片输入框,按「第一个 accept 含 image」投喂会喂错地方 —— 编辑器照常关闭、
    封面 ``src`` 也变了,但封面其实没换。判据必须是祖先文案同时含「拖拽」+「上传封面」。
    """
    try:
        return await page.evaluate(_MARK_UPLOAD_JS.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {"err": repr(exc)[:160]}


async def _cover_signature(page, tag: str) -> dict:
    """封面缩略图区的**像素指纹**(用于判断上传到底有没有生效)。

    ★ 不能只看 ``img.src``:上传没生效时 src 也会变(换 CDN 变体),像素才作数。
    ★ 不能按 CDN URL 找图:那个选择器命中的是页面上别的图片,而且话题自动补全浮层
      会盖在它们上面 → 截出来是浮层文字(踩过)。**锚点是标签文案
      「竖封面3:4 / 横封面4:3」**。
    ★ 也不能自己算 clip 再截整页:编辑页会把封面区滚出视口,坐标变负就一张都截不到
      (踩过)。``locator.screenshot()`` 会自动把元素滚进视野,与滚动位置无关。
    """
    await _scroll_text_into_view(page, "竖封面3:4")
    # ★★ 2026-09-21 修(#65 xpengg9l 的真因):封面区是**滚动进视野之后才懒加载 img**,
    #   原来滚动后只 ``wait_for_timeout(900)`` 就去读 ⇒ 标签文案已渲染、``img`` 还没挂上,
    #   于是误报「锚点命中 2 个,但近邻都没 img」。而**同一个函数**在「上传后」探针
    #   (几十秒后)却能读到 ``labels=['竖封面3:4','横封面4:3']`` —— 说明不是选择器错,
    #   是**时序**错。外面加多少重试都只是碰运气,正解是这里**轮询等 img 出现**
    #   (最多约 18s);#68(wifi8) 页面轻,第一次就读到,所以一直没暴露这个坑。
    mark: dict = {}
    for _ in range(12):
        try:
            mark = await page.evaluate(_MARK_THUMBS_JS.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            return {"ok": False, "why": f"标记封面缩略图失败: {exc!r}"}
        if mark.get("err"):
            return {"ok": False, "why": f"标记封面缩略图失败: {mark['err']}"}
        if mark.get("marked"):
            break
        await page.wait_for_timeout(1500)
    if not mark.get("marked"):
        return {"ok": False,
                "why": f"没找到封面缩略图(锚点命中 {mark.get('anchors')} 个,但近邻都没 img;"
                       f"已轮询约 18s 等懒加载)"}
    marked = mark.get("marked") or []
    loc = page.locator('[data-bfc-thumb="1"]')
    count = await loc.count()
    shots: list[bytes] = []
    for index in range(count):
        try:
            shots.append(await loc.nth(index).screenshot(timeout=10000))
        except Exception as exc:
            _log(f"封面缩略图 #{index} 截图跳过: {exc!r}")
    if not shots:
        return {"ok": False, "why": f"封面缩略图 {count} 个都截不到"}

    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved = []
    for index, shot in enumerate(shots):
        path = DEBUG_DIR / f"cover_{tag}_{stamp}_{index}.png"
        path.write_bytes(shot)
        saved.append(str(path))

    first = b"|".join(shots)
    # 稳定性自检:同一组元素立刻再截一遍,字节不同说明页面还在动/图片还没加载完
    second: list[bytes] = []
    for index in range(count):
        try:
            second.append(await loc.nth(index).screenshot(timeout=10000))
        except Exception:
            continue
    return {
        "ok": True,
        "digest": hashlib.sha1(first).hexdigest()[:16],
        "stable": b"|".join(second) == first,
        "count": len(shots),
        "labels": [o.get("label") for o in marked],
        "srcs": [o.get("src") for o in marked],
        "pngs": saved,
    }


async def _upload_cover(page, cover_path: str, tab: str = "") -> tuple[bool, str]:
    """在封面编辑器里切到「上传封面」→ 投喂图片 → 点「完成」回编辑页。"""
    if not cover_path:
        return False, "未提供 --cover 路径"
    path = Path(cover_path)
    if not path.is_file():
        return False, f"封面文件不存在: {cover_path}"
    if tab:
        await _safe_click(page, [tab], wait_ms=2500)
    await _safe_click(page, ["上传封面"], wait_ms=3000)
    await page.wait_for_timeout(1500)

    # ★ 确定性路径:用 JS 把**投放区**那个 input 标出来再投喂。
    #   不再"随便挑一个 input[type=file]"——那条路实测会喂到 AI 参考图那边(已踩)。
    mark = await _mark_upload_input(page)
    selected = (mark or {}).get("selected")
    _log(f"上传输入框定位: total={mark.get('total')} selected={selected} err={mark.get('err')}")
    if not selected:
        if mark.get("err"):
            return False, f"定位上传输入框时出错: {mark['err']}"
        return False, ("封面弹层里没找到投放区 input(祖先文案未同时命中「拖拽」+「上传封面」);"
                       f"页面上共 {mark.get('total')} 个 file input")

    try:
        await page.locator('input[data-bfc-upload="1"]').set_input_files(
            str(path), timeout=30000)
    except Exception as exc:
        return False, f"投喂封面文件失败(投放区 input): {exc!r}"
    await page.wait_for_timeout(5000)
    _log("封面文件已投喂,等待裁切预览/上传完成")

    # 上传后抖音会做一次图片处理,「完成」要等它可点才有效
    for _ in range(10):
        hit = await _secure_click_finish(page)
        if hit:
            _log(f"封面编辑器已「{hit}」")
            return True, f"经投放区 input 投喂(sel={selected})并「{hit}」"
        await page.wait_for_timeout(2500)
    return False, "封面文件投喂了,但「完成」一直点不中(可能还在处理图片)"


async def _visible_any(page, keywords) -> str:
    """返回页面上第一个可见的命中文案(空串 = 都没命中)。"""
    for label in keywords:
        for frame in page.frames:
            for sel in (f'text="{label}"', f'text={label}'):
                try:
                    loc = frame.locator(sel)
                    if await loc.count() == 0:
                        continue
                    if await loc.first.is_visible():
                        return label
                except Exception:
                    continue
    return ""


# ---------------------------------------------------------------- 快手封面后补

KS_EDIT_PAGE = "/article/edit/video"


async def _ks_mark_card_edit(page, keyword: str) -> dict:
    """在快手作品管理页标记目标卡片的「编辑作品」入口(顺带强制显示 hover 操作区)。

    ★ 每张卡片都有「编辑作品」,必须按作品内容定位卡片,否则点到别的作品上。
    """
    try:
        src = _MARK_KS_EDIT_JS.read_text(encoding="utf-8").replace(
            "__ARG__", json.dumps(keyword, ensure_ascii=False))
        return await page.evaluate(src) or {}
    except Exception as exc:
        return {"err": repr(exc)[:160]}


async def _ks_mark_upload(page) -> dict:
    """在快手「封面截取 → 上传封面」页签里标出投放区的 file input。"""
    try:
        return await page.evaluate(
            _MARK_KS_UPLOAD_JS.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {"err": repr(exc)[:160]}


async def _ks_cover_sig(page, tag: str) -> dict:
    """快手编辑页「封面设置」缩略图的像素指纹。"""
    loc = page.locator('[class*="default-cover"] img, [class*="cover-full-editor"] img, [class*="cover-full-editor"]')
    try:
        if await loc.count() == 0:
            return {"ok": False, "why": "没找到封面缩略图([class*=default-cover] img)"}
        shot = await loc.first.screenshot(timeout=12000)
    except Exception as exc:
        return {"ok": False, "why": f"封面缩略图截图失败: {exc!r}"}
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DEBUG_DIR / f"kscover_{tag}_{stamp}.png"
    path.write_bytes(shot)
    return {"ok": True, "digest": hashlib.sha1(shot).hexdigest()[:16], "png": str(path)}


async def _apply_kuaishou(page, ctx, args) -> tuple[bool, str]:
    """快手:作品管理 → 编辑作品 → 封面设置 → 上传封面 → 发布。

    实测链路(2026-09-14):卡片操作区 `.video-item__controls__operations`
    (``display:none``,hover 才显示)里有「编辑作品」→ 跳到
    ``/article/edit/video?workId=...`` 编辑页 → 「封面设置」区的大封面
    (``_cover-full-editor``,``opacity:0`` 的悬浮层)点开 ``ant-modal``
    「封面截取」弹层 → 页签「上传封面」→ 投放区「拖拽图片到此或点击上传」
    出现**唯一**的 ``input[type=file]`` → 应用后点编辑页的「发布」保存。
    """
    probe = args.search or _title_probe(args.title)
    mark = await _ks_mark_card_edit(page, probe)
    if mark.get("err"):
        return False, f"标记作品卡片失败: {mark['err']}"
    if not mark.get("markedEdit"):
        return False, (f"作品管理页没定位到含「{probe}」的作品卡片 / 它的「编辑作品」入口 "
                       f"(cards={mark.get('cards')} hits={mark.get('hits')})")
    _log(f"卡片已定位 cls={((mark.get('card') or {}).get('cls'))} "
         f"ops={[o.get('txt') for o in (mark.get('ops') or [])]}")
    try:
        await page.locator('[data-bfc-edit="1"]').click(timeout=15000)
    except Exception as exc:
        return False, f"点「编辑作品」失败: {exc!r}"
    await page.wait_for_timeout(10000)
    if KS_EDIT_PAGE not in page.url:
        return False, f"点了「编辑作品」但没进编辑页,当前 URL={page.url[:120]}"
    _log(f"已进入编辑页 {page.url[:110]}")

    base = {"ok": False}
    for _ in range(12):
        base = await _ks_cover_sig(page, "base")
        if base.get("ok"):
            break
        await page.wait_for_timeout(2500)
    _log(f"封面基线: digest={base.get('digest') or base.get('why')}")

    try:
        await page.locator('[class*="cover-full-editor"]').first.click(timeout=15000)
    except Exception as exc:
        return False, f"点开封面弹层失败: {exc!r}"
    await page.wait_for_timeout(5000)
    try:
        await page.locator(
            '[class*="_header-title-item"]:has-text("上传封面")').first.click(timeout=15000)
    except Exception as exc:
        return False, f"切到「上传封面」页签失败: {exc!r}"
    await page.wait_for_timeout(2500)

    upmark = await _ks_mark_upload(page)
    _log(f"上传输入框定位: total={upmark.get('total')} selected={upmark.get('selected')}")
    if not upmark.get("selected"):
        return False, f"「上传封面」投放区没找到 file input: {upmark}"

    _log("开始投喂封面文件")
    try:
        await page.locator('input[data-bfc-upload="1"]').set_input_files(
            str(Path(args.cover)), timeout=30000)
    except Exception as exc:
        return False, f"投喂封面文件失败: {exc!r}"
    await page.wait_for_timeout(6000)

    if args.dry_run:
        info = await dump_page(page, "ks-dry-fed")
        _log(f"[dry-run] 文件已投喂,停在这里。截图 {info.get('screenshot')}")
        return False, "dry-run:已停在快手封面弹层(文件已投喂,未应用未保存)"

    # The current modal uses the pink primary "去编辑" action to apply an
    # uploaded image.  Its white "确认" action kept the original thumbnail.
    applied = await _safe_click(page, ["去编辑"], wait_ms=5000)
    if not applied:
        applied = await _safe_click(page, ["确认"], wait_ms=5000)
    if not applied:
        return False, "封面文件投喂了,但弹层里没点中「确认」/「去编辑」"
    _log(f"封面弹层已「{applied}」")

    if applied == "去编辑":
        finished = ""
        for _ in range(40):
            if await page.get_by_text("封面编辑", exact=True).count():
                finished = await _safe_click(page, ["完成"], wait_ms=5000)
                if finished:
                    break
            await page.wait_for_timeout(3000)
        if not finished:
            return False, "已进入封面编辑器，但没能点中「完成」"
        _log("封面编辑器已点「完成」")

    # Both actions may start an asynchronous image conversion.  Keep the
    # editor open until the modal has closed before judging the thumbnail.
    for _ in range(30):
        modal = page.locator('.ant-modal:visible')
        if await modal.count() == 0:
            break
        await page.wait_for_timeout(3000)

    after = None
    for _ in range(5):
        await page.wait_for_timeout(3000)
        cand = await _ks_cover_sig(page, "after")
        if cand.get("ok"):
            after = cand
            if not base.get("ok") or cand["digest"] != base["digest"]:
                break
    _log(f"封面弹层应用后: digest={after.get('digest') if after else None} / "
         f"{after.get('why') if after else 'None'}")
    if not base.get("ok"):
        await dump_page(page, "ks-nobase")
        return False, f"拿不到上传前的封面像素基线({base.get('why')}),按未生效处理"
    if not after or not after.get("ok"):
        await dump_page(page, "ks-nosig")
        return False, f"拿不到应用后的封面像素({after.get('why') if after else 'None'}),按未生效处理"
    if after["digest"] == base["digest"]:
        await dump_page(page, "ks-unchanged")
        return False, (f"封面文件投喂成功,但**像素前后一致**({after['digest']})→ 按失败处理,"
                       f"未点发布。基线图 {base.get('png')} / 应用后图 {after.get('png')}")
    _log(f"封面像素已确认变化: {base['digest']} → {after['digest']}")

    hit = await _safe_click(page, ["发布"], wait_ms=8000)
    if not hit:
        return False, (f"封面像素已变化({base['digest']}→{after['digest']}),"
                       f"但没找到「发布」按钮,改动未保存")
    ok, reason = False, ""
    for _ in range(20):
        await page.wait_for_timeout(3000)
        if KS_EDIT_PAGE not in page.url:
            ok, reason = True, f"URL 已离开编辑页({page.url[:90]})"
            break
        text_hit = await _visible_any(page, ("发布成功", "修改成功", "保存成功", "已发布"))
        if text_hit:
            ok, reason = True, f"命中成功文案「{text_hit}」"
            break
    _log(f"发布判定: ok={ok} {reason or '(未命中任一判据)'}")
    if not ok:
        info = await dump_page(page, "ks-publish-unconfirmed")
        return False, (f"封面已换,但点「发布」后未确认到成功信号,请到后台复核"
                       f"(现场 {info.get('screenshot')})")
    return True, (f"已更换封面并发布(像素 {base['digest']}→{after['digest']}, "
                  f"依据 {reason})")


# ---------------------------------------------------------------- 小红书封面后补

XHS_NOTE_MANAGER = "https://creator.xiaohongshu.com/new/note-manager"
XHS_UPDATE_PAGE = "/publish/update"
# ★ 小红书的「发布」是**自定义元素**(shadow DOM),普通 button/text 选择器**选不到**:
#   <xhs-publish-btn is-publish="true" submit-text="发布" save-text="暂存离开">
#   用 elementFromPoint 反查才发现的(遍历 button/div/span/a 全空)。
XHS_PUBLISH_SEL = 'xhs-publish-btn[is-publish="true"]'


async def _xhs_mark_edit(page, keyword: str) -> dict:
    """在笔记管理页标出目标笔记的「编辑」图标(删除按钮显式排除)。"""
    try:
        src = _MARK_XHS_EDIT_JS.read_text(encoding="utf-8").replace(
            "__ARG__", json.dumps(keyword, ensure_ascii=False))
        return await page.evaluate(src) or {}
    except Exception as exc:
        return {"err": repr(exc)[:160]}


async def _xhs_mark_upload(page) -> dict:
    """在「设置封面」弹层里标出上传封面图的 file input(排除视频输入框)。"""
    try:
        return await page.evaluate(
            _MARK_XHS_UPLOAD_JS.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {"err": repr(exc)[:160]}


async def _xhs_cover_sig(page, tag: str) -> dict:
    """笔记编辑页「设置封面」缩略图的像素指纹。

    ★ 选择器要按**可见性**挑:``[class*="cover--column"] img`` 会先命中
      「编辑封面」浮层里的隐藏 `img`(display:none),Playwright 报
      "element is not visible" 并超时(踩过)。这里按候选链逐个试,
      取第一个**可见**且截得到像素的。
    """
    candidates = [
        '[class~="default"][class~="column"] img',
        '[class~="default"][class~="column"]',
        '[class*="cover--column"] img',
    ]
    shot = b""
    used = ""
    for sel in candidates:
        loc = page.locator(sel)
        try:
            count = await loc.count()
        except Exception:
            continue
        for index in range(min(count, 4)):
            node = loc.nth(index)
            try:
                if not await node.is_visible():
                    continue
                box = await node.bounding_box()
                if not box or box["width"] < 40 or box["height"] < 40:
                    continue
                shot = await node.screenshot(timeout=15000)
                used = f"{sel}[{index}]"
                break
            except Exception:
                continue
        if shot:
            break
    if not shot:
        return {"ok": False, "why": "封面缩略图都不可见/截不到(试过 default column / cover--column)"}
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DEBUG_DIR / f"xhscover_{tag}_{stamp}.png"
    path.write_bytes(shot)
    return {"ok": True, "digest": hashlib.sha1(shot).hexdigest()[:16],
            "sel": used, "png": str(path)}


async def _apply_xhs(page, ctx, args) -> tuple[bool, str]:
    """小红书:笔记管理 → 编辑 → 设置封面 → 上传 → 完成 → 发布。

    实测链路(2026-09-14):
    * 笔记管理真实 URL 是 ``/new/note-manager``(旧记的 ``/new/note-manage/note-manage``
      是 404),入口在左侧 `d-menu-item`「笔记管理」上(JS 路由,不是 <a>)。
    * 卡片操作行 `note-card__actions`(`opacity:0`,hover 才显示)里有 5 个图标:
      权限/置顶/数据/**编辑(铅笔)**/删除(`--del`)。
    * 点编辑 → ``/publish/update?id=<noteId>&noteType=video``。
    * 「设置封面」区的「编辑封面」在 `[class*="operator"]`(`display:none`)里,
      注入 CSS 后才能点;点开是 `d-modal cover-modal`(1200×660)。
    * 弹层里 `label.upload-btn`「上传」包着一个 ``accept=image/*`` 的 input
      (同页还有 accept 为视频扩展名的输入框,必须排除)。
    * 底部提交是自定义元素 ``xhs-publish-btn[is-publish="true"]``。
    """
    probe = args.search or _title_probe(args.title)
    mark = await _xhs_mark_edit(page, probe)
    if mark.get("err"):
        return False, f"标记笔记卡片失败: {mark['err']}"
    if not mark.get("markedEdit"):
        return False, (f"笔记管理页没定位到含「{probe}」的笔记卡片 / 它的「编辑」图标 "
                       f"(rows={mark.get('rows')}, total={mark.get('total')})")
    _log(f"笔记卡片已定位,编辑图标 rect={mark.get('editRect')}")
    try:
        await page.locator('[data-bfc-xhs-edit="1"]').click(timeout=15000)
    except Exception as exc:
        return False, f"点「编辑」失败: {exc!r}"
    await page.wait_for_timeout(12000)
    if XHS_UPDATE_PAGE not in page.url:
        return False, f"点了「编辑」但没进笔记编辑页,当前 URL={page.url[:120]}"
    _log(f"已进入笔记编辑页 {page.url[:110]}")

    # 「编辑封面」藏在 display:none 的 hover 浮层里,先强制显示
    try:
        await page.evaluate(_FORCE_XHS_COVER_JS.read_text(encoding="utf-8"))
    except Exception as exc:
        _log(f"强制显示封面浮层失败(继续): {exc!r}")
    await page.wait_for_timeout(1500)

    base = await _xhs_cover_sig(page, "base")
    _log(f"封面基线: digest={base.get('digest') or base.get('why')}")

    try:
        await page.locator('[class*="cover-edit-entry"]').first.click(timeout=15000)
    except Exception as exc:
        return False, f"点开「编辑封面」失败: {exc!r}"
    await page.wait_for_timeout(7000)

    upmark = await _xhs_mark_upload(page)
    _log(f"上传输入框定位: total={upmark.get('total')} selected={upmark.get('selected')}")
    if not upmark.get("selected"):
        return False, f"封面弹层里没找到上传图片的 file input: {upmark}"

    _log("开始投喂封面文件")
    try:
        await page.locator('input[data-bfc-upload="1"]').set_input_files(
            str(Path(args.cover)), timeout=30000)
    except Exception as exc:
        return False, f"投喂封面文件失败: {exc!r}"
    await page.wait_for_timeout(7000)

    if args.dry_run:
        info = await dump_page(page, "xhs-dry-fed")
        _log(f"[dry-run] 文件已投喂,停在这里。截图 {info.get('screenshot')}")
        return False, "dry-run:已停在小红书封面弹层(文件已投喂,未保存)"

    if not await _safe_click(page, ["完成"], wait_ms=7000):
        return False, "封面文件投喂了,但弹层里没点中「完成」"
    _log("封面弹层已「完成」")

    after = None
    for _ in range(5):
        await page.wait_for_timeout(3000)
        cand = await _xhs_cover_sig(page, "after")
        if cand.get("ok"):
            after = cand
            if not base.get("ok") or cand["digest"] != base["digest"]:
                break
    _log(f"封面应用后: digest={after.get('digest') if after else None} / "
         f"{after.get('why') if after else 'None'}")
    if not base.get("ok"):
        await dump_page(page, "xhs-nobase")
        return False, f"拿不到上传前的封面像素基线({base.get('why')}),按未生效处理"
    if not after or not after.get("ok"):
        await dump_page(page, "xhs-nosig")
        return False, f"拿不到应用后的封面像素({after.get('why') if after else 'None'}),按未生效处理"
    if after["digest"] == base["digest"]:
        await dump_page(page, "xhs-unchanged")
        return False, (f"封面文件投喂成功,但**像素前后一致**({after['digest']})→ 按失败处理,"
                       f"未点发布。基线图 {base.get('png')} / 应用后图 {after.get('png')}")
    _log(f"封面像素已确认变化: {base['digest']} → {after['digest']}")

    try:
        await page.locator(XHS_PUBLISH_SEL).first.click(timeout=15000)
    except Exception as exc:
        return False, (f"封面像素已变化({base['digest']}→{after['digest']}),"
                       f"但点「发布」({XHS_PUBLISH_SEL})失败: {exc!r}")
    ok, reason = False, ""
    for _ in range(24):
        await page.wait_for_timeout(3000)
        if XHS_UPDATE_PAGE not in page.url:
            ok, reason = True, f"URL 已离开编辑页({page.url[:90]})"
            break
        text_hit = await _visible_any(page, ("发布成功", "已发布", "保存成功", "更新成功"))
        if text_hit:
            ok, reason = True, f"命中成功文案「{text_hit}」"
            break
    _log(f"发布判定: ok={ok} {reason or '(未命中任一判据)'}")
    if not ok:
        info = await dump_page(page, "xhs-publish-unconfirmed")
        return False, (f"封面已换,但点「发布」后未确认到成功信号,请到后台复核"
                       f"(现场 {info.get('screenshot')})")
    return True, (f"已更换封面并发布(像素 {base['digest']}→{after['digest']}, "
                  f"依据 {reason})")


# ── 视频号(shipinhao) ────────────────────────────────────────────────────────
# 实测链路(2026-09-14):
#   * 列表页 https://channels.weixin.qq.com/platform/post/list，内容在同域 iframe /
#     微前端里，作品的操作栏是 **shadow DOM** 里的 div.opr-item-wrap.edit-cover-item
#     (父 .opr / 祖父 .post-feed-item)。
#   * ★ 入口必须用 **JS el.click()**：视频号是 Vue(原生 addEventListener)，
#     Playwright 的 locator.click() 会「点击成功但毫无反应」。
#   * ★ 视口必须放大到 1920x1080：操作栏 rect.x ≈ 1353，1280 宽视口下被挤到屏幕外。
#   * 点击后进入 /platform/post/coverEdit?objectId=...，首次会弹引导「我知道了」。
#   * 封面缩略图上的 div.edit-btn 点开「编辑封面」弹层(weui-desktop-dialog)。
#   * ★ 弹层里**直接 set_input_files 投喂会让弹层关闭**(实测截图 sha1 与"未开弹层"
#     完全一致)，必须走真实路径：点 div.single-cover-uploader-wrap 触发 file chooser。
#   * ★ 视频号封面的槽位标注是「个人主页和分享卡片(3:4)」→ 与 3:4 主版封面完全匹配。
SH_MANAGE_URL = "https://channels.weixin.qq.com/platform/post/list"
SH_EDIT_PAGE = "/post/coverEdit"
SH_UPLOADER_SEL = "div.single-cover-uploader-wrap"


async def _sh_js(page, filename: str, arg: str = "") -> dict:
    """跑 scripts/<filename> 里的 JS(支持 __ARG__ 占位符替换)。"""
    snippet = (Path(__file__).resolve().parent / filename).read_text(encoding="utf-8")
    if arg:
        snippet = snippet.replace("__ARG__", json.dumps(arg, ensure_ascii=False))
    try:
        res = await page.evaluate(snippet)
    except Exception as exc:
        return {"err": repr(exc)[:200]}
    return res if isinstance(res, dict) else {"raw": res}


async def _sh_preview_sig(page, tag: str) -> dict:
    """弹层里最大那张图的**像素**指纹(逐元素截图 + sha1)。

    ★ 只看 img.src 会误判(失败时 src 也会变，只是 CDN 变体)，必须比像素。
    """
    mark = await _sh_js(page, "_sh_mark_preview.js")
    if not mark.get("ok"):
        return {"ok": False, "why": mark.get("why") or mark.get("err") or "标记失败",
                "mark": mark}
    try:
        shot = await page.locator('[data-bfc-sh="1"]').first.screenshot(timeout=20000)
    except Exception as exc:
        return {"ok": False, "why": f"截图失败 {exc!r}", "mark": mark}
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    png = DEBUG_DIR / f"sh_preview_{tag}_{datetime.now().strftime('%H%M%S')}.png"
    png.write_bytes(shot)
    return {"ok": True, "digest": hashlib.sha1(shot).hexdigest()[:16],
            "rect": mark.get("rect"), "src": mark.get("src"),
            "natural": mark.get("natural"), "png": str(png)}


async def _apply_shipinhao(page, ctx, args) -> tuple[bool, str]:
    """视频号：视频管理 → 修改描述和封面 → 编辑 → 上传封面 → 确认 → 完成。"""
    _log(f"打开 {SH_MANAGE_URL}")
    await page.goto(SH_MANAGE_URL, wait_until="domcontentloaded", timeout=90000)
    await page.wait_for_timeout(args.wait_ms)

    entry = await _sh_js(page, "_sh_open_list_entry.js",
                         args.search or args.title or "")
    _log(f"列表入口: {entry}")
    if not entry.get("ok"):
        return False, f"没点到「修改描述和封面」入口: {entry}"

    for _ in range(24):
        await page.wait_for_timeout(1500)
        if SH_EDIT_PAGE in page.url:
            break
    else:
        return False, f"点了入口但没进封面编辑页,当前 URL={page.url[:130]}"
    _log(f"已进入封面编辑页 {page.url[:110]}")

    dlg = await _sh_js(page, "_sh_open_cover_dialog.js")
    _log(f"编辑弹层: {dlg}")
    if not dlg.get("dialogOpen"):
        info = await dump_page(page, "sh-no-dialog")
        return False, (f"点「编辑」后没打开「编辑封面」弹层({dlg}),"
                       f"现场 {info.get('screenshot')}")

    base = {}
    for _ in range(5):
        base = await _sh_preview_sig(page, "base")
        if base.get("ok"):
            break
        await page.wait_for_timeout(3000)
    _log(f"封面基线: digest={base.get('digest') or base.get('why')} "
         f"rect={base.get('rect')} natural={base.get('natural')}")

    if args.dry_run:
        info = await dump_page(page, "sh-dry")
        _log(f"[dry-run] 停在「编辑封面」弹层,截图 {info.get('screenshot')}")
        return False, "dry-run:已停在视频号「编辑封面」弹层(未上传)"

    # ★ 走真实 file chooser：直接 set_input_files 会让弹层关闭
    _log(f"点「上传封面」({SH_UPLOADER_SEL}) 触发文件选择")
    try:
        async with page.expect_file_chooser(timeout=25000) as finfo:
            await page.locator(SH_UPLOADER_SEL).first.click(timeout=12000)
        chooser = await finfo.value
        await chooser.set_files(str(Path(args.cover)))
        _log("封面文件已投喂(file chooser)")
    except Exception as exc:
        info = await dump_page(page, "sh-chooser-fail")
        return False, f"点「上传封面」/投喂失败: {exc!r},现场 {info.get('screenshot')}"
    await page.wait_for_timeout(9000)

    after = None
    for _ in range(6):
        cand = await _sh_preview_sig(page, "after")
        if cand.get("ok"):
            after = cand
            if not base.get("ok") or cand["digest"] != base["digest"]:
                break
        await page.wait_for_timeout(3000)

    if getattr(args, "dry_run2", False):
        info = await dump_page(page, "sh-fed")
        _log(f"[dry-run2] 文件已投喂,停在裁剪界面,截图 {info.get('screenshot')}")
        return False, "dry-run2:已投喂封面但未点确认"

    if not base.get("ok"):
        return False, f"拿不到上传前的封面像素基线({base.get('why')}),按未生效处理"
    if not after or not after.get("ok"):
        return False, (f"拿不到上传后的封面像素"
                       f"({after.get('why') if after else None}),按未生效处理")
    if after["digest"] == base["digest"]:
        info = await dump_page(page, "sh-unchanged")
        return False, (f"封面投喂后**像素前后一致**({after['digest']})→ 按失败处理,未保存。"
                       f"基线图 {base.get('png')} / 上传后图 {after.get('png')}"
                       f" / 现场 {info.get('screenshot')}")
    _log(f"封面像素已确认变化: {base['digest']} → {after['digest']}")

    hit = await _sh_js(page, "_sh_click_text.js", "确认|weui-desktop-dialog")
    _log(f"点弹层「确认」: {hit}")
    if not hit.get("ok"):
        return False, f"弹层里点不到「确认」: {hit}"
    await page.wait_for_timeout(7000)

    fin = await _sh_js(page, "_sh_click_text.js", "完成|edit-btns")
    _log(f"点页面「完成」: {fin}")
    if not fin.get("ok"):
        info = await dump_page(page, "sh-finish-fail")
        return False, (f"封面像素已变({base['digest']}→{after['digest']}),"
                       f"但点不到页面「完成」: {fin},现场 {info.get('screenshot')}")
    await page.wait_for_timeout(4000)

    # ★★ 视频号会再弹一层**不可撤回**的二次确认：
    #   「仅支持修改一次，修改后不可撤回，修改记录将会展示在视频上。」＋「确认修改」
    #   点下去才真正落库 —— 而且这是**每个作品唯一的一次**修改机会(点过就再也不能改)。
    #   所以先落一张现场图留证据，再点。
    pre = await dump_page(page, "sh-before-final-confirm")
    _log(f"提交前现场 {pre.get('screenshot')}")
    cfm = await _sh_js(page, "_sh_click_text.js", "确认修改|weui-desktop-dialog")
    _log(f"点二次确认「确认修改」: {cfm}")
    if not cfm.get("ok"):
        info = await dump_page(page, "sh-confirm-fail")
        return False, (f"没点到「确认修改」: {cfm},现场 {info.get('screenshot')}")

    ok, reason = False, ""
    for _ in range(20):
        await page.wait_for_timeout(3000)
        if SH_EDIT_PAGE not in page.url:
            ok, reason = True, f"URL 已离开封面编辑页({page.url[:90]})"
            break
        text_hit = await _visible_any(page, ("保存成功", "修改成功", "提交成功",
                                            "已保存", "更新成功"))
        if text_hit:
            ok, reason = True, f"命中成功文案「{text_hit}」"
            break
        # 二次确认弹窗消失 = 提交已受理(视频号是 SPA,URL 不一定变)
        try:
            if await page.locator('text="确认修改"').count() == 0:
                ok, reason = True, "二次确认弹窗已消失(提交已受理)"
                break
        except Exception:
            pass
    _log(f"保存判定: ok={ok} {reason or '(未命中任一判据)'}")
    if not ok:
        info = await dump_page(page, "sh-unconfirmed")
        return False, (f"封面像素已变({base['digest']}→{after['digest']}),"
                       f"但点「完成」后未确认到成功信号,请到后台复核"
                       f"(现场 {info.get('screenshot')})")
    return True, f"已更换封面(像素 {base['digest']}→{after['digest']}, 依据 {reason})"


async def _secure_click_finish(page) -> str:
    """点封面编辑器的「完成」(收紧:只在弹层里点,避开页面上别的「完成」)。"""
    for label in ("完成", "确定", "保存"):
        for frame in page.frames:
            try:
                loc = frame.locator(f'text="{label}"')
                if await loc.count() == 0:
                    continue
                node = loc.first
                if not await node.is_visible():
                    continue
                await node.scroll_into_view_if_needed(timeout=3000)
                await node.click(timeout=5000)
                await page.wait_for_timeout(4000)
                return label
            except Exception:
                continue
    return ""



async def cmd_apply(args) -> int:
    cfg = load_config()
    init_db(cfg.db_path)
    acc = load_account(args.account)
    platform = acc.platform or args.platform or ""
    if platform not in ("douyin", "kuaishou", "xhs", "shipinhao"):
        raise SystemExit(f"apply 目前实现了抖音/快手/小红书/视频号,当前账号平台={platform}")
    mgr = build_manager(cfg)
    url = args.url or MANAGE_URL.get(platform) or SH_MANAGE_URL
    await mgr.start()
    identity = mgr.identity_for(acc)
    try:
        ctx = (await mgr.open_headed(identity) if args.visible
               else await mgr.open_background(identity))
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        vw, vh = _viewport_from(args, acc)
        await _apply_page_viewport(ctx, page, vw, vh)
        _log(f"打开 {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(max(args.wait_ms, 14000))
        if platform == "kuaishou":
            ok, detail = await _apply_kuaishou(page, ctx, args)
        elif platform == "xhs":
            ok, detail = await _apply_xhs(page, ctx, args)
        elif platform == "shipinhao":
            ok, detail = await _apply_shipinhao(page, ctx, args)
        else:
            ok, detail = await _apply_douyin(page, ctx, args)
        _log(f"结果: ok={ok} {detail}")
        if not ok:
            info = await dump_page(page, "apply-fail")
            _log(f"现场: {info.get('screenshot')} / {info.get('full_text')}")
        return 0 if ok else 1
    finally:
        await mgr.stop_minimize_hold(identity)
        await mgr.stop()


async def _apply_search(page, keyword: str) -> str:
    """在管理页的「搜索作品/搜索笔记」框里搜关键词。

    列表是虚拟滚动的,首屏只渲染 4~5 行 —— **不能** 用「首屏没有」当「不存在」
    的证据。用平台自带的搜索把目标作品筛出来才可靠。
    """
    candidates = [
        'input[placeholder*="搜索"]',
        'input[type="search"]',
        '[class*="search"] input',
        'input[placeholder*="作品"]',
    ]
    for frame in page.frames:
        for sel in candidates:
            try:
                loc = frame.locator(sel)
                if await loc.count() == 0:
                    continue
                box = loc.first
                if not await box.is_visible():
                    continue
                await box.click(timeout=3000)
                await box.fill(keyword, timeout=3000)
                await box.press("Enter", timeout=3000)
                return f"已搜索: {keyword} @ {frame.url[:60]} {sel}"
            except Exception:
                continue
    return "未找到搜索框"


async def _click_texts(page, labels: list[str], wait_ms: int = 3000) -> list[str]:
    """按文案依次点击(例如切到「审核中」标签页、进编辑页、点「设置封面」)。"""
    done = []
    for label in labels:
        hit = False
        for frame in page.frames:
            for sel in (f'text="{label}"', f'[class*="tab"]:has-text("{label}")',
                        f'text={label}'):
                try:
                    loc = frame.locator(sel)
                    if await loc.count() == 0:
                        continue
                    node = loc.first
                    if not await node.is_visible():
                        continue
                    await node.scroll_into_view_if_needed(timeout=3000)
                    await node.click(timeout=4000)
                    done.append(f"{label}@{frame.url[:40]}")
                    hit = True
                    break
                except Exception:
                    continue
            if hit:
                break
        if not hit:
            done.append(f"{label}(未找到)")
        await page.wait_for_timeout(wait_ms)
    return done


async def cmd_probe(args) -> int:
    cfg = load_config()
    init_db(cfg.db_path)
    acc = load_account(args.account)
    mgr = build_manager(cfg)
    url = args.url or MANAGE_URL.get(acc.platform or args.platform or "")
    if not url:
        raise SystemExit(f"没有为平台 {acc.platform} 配置管理页 URL")
    await mgr.start()
    identity = mgr.identity_for(acc)
    try:
        ctx = await mgr.open_background(identity)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        vw, vh = _viewport_from(args, acc)
        await _apply_page_viewport(ctx, page, vw, vh)
        _log(f"打开 {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(args.wait_ms)
        # 顺序很重要:先搜索把目标作品筛出来,再点它身上的按钮。
        if args.search:
            result = await _apply_search(page, args.search)
            _log(result)
            await page.wait_for_timeout(7000)
        if args.scroll_to:
            for frame in page.frames:
                try:
                    node = frame.locator(f'text="{args.scroll_to}"').first
                    if await node.count():
                        await node.scroll_into_view_if_needed(timeout=5000)
                        _log(f"已滚动到「{args.scroll_to}」")
                        break
                except Exception:
                    continue
            await page.wait_for_timeout(1200)
        if args.click:
            clicks = await _click_texts(page, [s for s in args.click.split(",") if s],
                                        wait_ms=args.click_wait_ms)
            _log(f"点击结果: {clicks}")
            await page.wait_for_timeout(2000)
        if args.js or args.js_file:
            snippet = args.js
            if args.js_file:
                snippet = Path(args.js_file).read_text(encoding="utf-8")
            # __ARG__ 占位符 → 命令行传入的字符串(避免引号/中文转义地狱)
            if args.js_arg:
                snippet = snippet.replace(
                    "__ARG__", json.dumps(args.js_arg, ensure_ascii=False))
            try:
                result = await page.evaluate(snippet)
            except Exception as exc:
                result = f"eval 失败: {exc!r}"
            print("=== JS 结果 ===")
            print(json.dumps(result, ensure_ascii=False, indent=1)[:24000])
        if args.click_selector:
            # 先跑 JS 打标记,再按标记点击 —— 用来在"目标卡片"里点某个入口,
            # 而不是点到列表里第一张卡片的同名按钮上。
            # ★ 多个选择器用 ``;;`` 分隔,按顺序点(例:先点开封面弹层,再点「上传封面」页签)。
            for one in [s for s in args.click_selector.split(";;") if s.strip()]:
                try:
                    node = page.locator(one.strip()).first
                    await node.click(timeout=12000)
                    _log(f"已点击 {one.strip()}")
                except Exception as exc:
                    _log(f"点击 {one.strip()} 失败: {exc!r}")
                await page.wait_for_timeout(args.click_wait_ms)
        if args.js2_file:
            # ★ 第二段 JS:跑在 --click-selector **之后**。
            #   用途:先点开弹层(JS `.click()` 触发不了 React 的处理器,
            #   必须用 Playwright 真实鼠标点击),再枚举弹层里的结构/打标记。
            try:
                snippet2 = Path(args.js2_file).read_text(encoding="utf-8")
                if args.js2_arg:
                    snippet2 = snippet2.replace(
                        "__ARG__", json.dumps(args.js2_arg, ensure_ascii=False))
                result2 = await page.evaluate(snippet2)
                print("=== JS2 结果 ===")
                print(json.dumps(result2, ensure_ascii=False, indent=1)[:24000])
            except Exception as exc:
                _log(f"JS2 执行失败: {exc!r}")
        if args.upload_selector:
            # 通用「把封面投喂给某个 file input」——用于在 probe 阶段快速验证
            # 某平台的封面上传入口(不用每次都改 apply 链路)。
            # ★ set_input_files 对**隐藏**的 input 同样有效(不需要可见、不需要点击)。
            if not args.cover:
                _log("给了 --upload-selector 但没给 --cover，跳过")
            else:
                try:
                    node = page.locator(args.upload_selector).first
                    await node.set_input_files(args.cover, timeout=30000)
                    _log(f"已把封面投喂给 {args.upload_selector}")
                except Exception as exc:
                    _log(f"投喂 {args.upload_selector} 失败: {exc!r}")
                await page.wait_for_timeout(args.click_wait_ms)
        info = await dump_page(page, args.tag or f"probe-{acc.platform}", clip=args.clip)
        print(json.dumps(info, ensure_ascii=False, indent=1)[:6000])
        _log(f"截图 {info.get('screenshot')}")
        _log(f"全文 {info.get('full_text')}")
    finally:
        await mgr.stop_minimize_hold(identity)
        await mgr.stop()
    return 0


async def main_async(args) -> int:
    if args.cmd == "probe":
        return await cmd_probe(args)
    if args.cmd == "apply":
        return await cmd_apply(args)
    raise SystemExit(f"未实现的命令: {args.cmd}")


def main() -> int:
    parser = argparse.ArgumentParser(description="给已发布作品后补封面")
    parser.add_argument("cmd", choices=["probe", "apply"])
    parser.add_argument("--account", type=int, required=True)
    parser.add_argument("--platform", default="")
    parser.add_argument("--url", default="")
    parser.add_argument("--cover", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--search", default="")
    parser.add_argument("--click", default="")
    parser.add_argument("--click-selector", default="",
                        help="跑完 JS(通常是打标记)后按 CSS 选择器点击")
    parser.add_argument("--click-wait-ms", type=int, default=4000)
    parser.add_argument("--tag", default="")
    parser.add_argument("--dry-run", action="store_true",
                        help="apply 时只走到封面弹层就停下并落现场,不做任何修改")
    parser.add_argument("--visible", action="store_true",
                        help="apply 时让浏览器留在屏幕内,供封面画布正确渲染")
    parser.add_argument("--dry-run2", dest="dry_run2", action="store_true",
                        help="视频号专用:投喂封面后停在裁剪界面(未点确认/完成)")
    parser.add_argument("--js", default="", help="在页面上执行这段 JS 并打印返回值")
    parser.add_argument("--js-file", default="", help="从文件读取 JS(避免引号转义地狱)")
    parser.add_argument("--js-arg", default="",
                        help="替换 JS 里的 __ARG__ 占位符(自动 JSON 转义)")
    parser.add_argument("--js2-file", default="",
                        help="第二段 JS,在 --click-selector 之后执行")
    parser.add_argument("--js2-arg", default="", help="替换第二段 JS 里的 __ARG__")
    parser.add_argument("--scroll-to", default="", help="先把这段文案滚动到视野内")
    parser.add_argument("--clip", default="", help="截图区域 x,y,w,h")
    parser.add_argument("--wait-ms", type=int, default=9000)
    parser.add_argument("--viewport", default="",
                        help="页面视口 WxH(默认用账号指纹里的尺寸;窗口保持最小化)")
    parser.add_argument("--upload-selector", default="",
                        help="probe 专用:最后把 --cover 投喂给这个 file input"
                             "(隐藏 input 也可),用于快速验证封面上传入口")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
