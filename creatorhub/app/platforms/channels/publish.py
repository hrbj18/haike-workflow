"""视频号发布入口(浏览器自动化视频号助手 channels.weixin.qq.com)。

视频号发布页是 wujie 微前端(内容在 shadowRoot 里)。Patchright 的定位器默认会穿透
**开放的** shadow DOM,故下面用普通 CSS 选择器即可;若视频号把 shadow root 设成 closed
则需改用 CDP pierce(参见 _CHANNELS_* 注释)。

⚠️ 实验性 + 需校准:发布页选择器随视频号改版/wujie 版本变化,集中在下面 _* 常量;
   选择器初值取自对小V猫的逆向观察(`.post-view` 系),务必用真实账号发一条核对。
   发布时弹真实窗口,遇「实名/过脸验证」「封面必填」可在窗口里手动处理。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Tuple

from ...browser.identity import Identity
from ...browser.manager import BrowserManager

log = logging.getLogger("creatorhub.channels")
# ★ 2026-09-14 加:本仓库没有任何 logging.basicConfig/dictConfig,所以
#   ``log.warning`` 出去的诊断(发布前查重结果、封面是否设上、平台核对结论)
#   全都进了黑洞 —— 排查视频号时在服务日志里 grep 一次都搜不到。
#   这里给本模块挂一个自己的 StreamHandler,和抖音/快手用 print 的效果对齐。
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[ch-publish] %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)
    log.propagate = False

_DEBUG_DIR = Path("./data/debug")

# ★ 2026-09-14 加:视频号的封面是**发布前置条件**(不像快手可以后补智能封面)。
# ★ 2026-09-21 更新:PublishIn / PublishTask 现已各自带 ``cover_path`` 字段(抖音侧
#   2026-09-20 上线),monitor.py 的 shipinhao 分支已把任务级 ``cover_path`` 透传进来
#   ⇒ **优先用任务级封面**,进程级 ``CREATORHUB_COVER_PATH`` 退化为兜底(仅在任务没给
#   封面时生效)。保留它是因为「一张封面用很多条」的批量场景仍然方便。
COVER_ENV = "CREATORHUB_COVER_PATH"


def _default_cover() -> str:
    return (os.getenv(COVER_ENV) or "").strip().strip('"')

# 视频号发布入口(实测):就是 create 页;视频/图文靠点左侧「视频」「图文」导航切换
# (逆向 server.jsc 里还有 finderNewLifeCreateg,但实测会 302 回 create,故不直接跳它)。
CREATE_URL_VIDEO = "https://channels.weixin.qq.com/platform/post/create"
CREATE_URL = CREATE_URL_VIDEO   # 兼容旧引用
# 作品管理列表页(发表成功后的落点,也是唯一可信的核对入口)
POST_LIST_URL = "https://channels.weixin.qq.com/platform/post/list"

# 标题/描述编辑器(wujie shadowRoot 内)。视频号「短标题」与「描述」是两个框,
# 这里优先填描述编辑器;短标题选择器留作备用。
_DESC_SEL = [
    '.post-view .post-desc-box .input-editor',
    '.post-desc-box .input-editor',
    'div.input-editor[contenteditable="true"]',
    'textarea[placeholder*="描述"]',
    'div[contenteditable="true"]',
]
_SHORT_TITLE_SEL = [
    '.post-view .short-title-wrap input',
    'input[placeholder*="标题"]',
]
# 文件上传 input(视频号发布页可能在 wujie iframe / shadowRoot 里)
_FILE_SEL = [
    '.post-view .upload input[type="file"]',
    '.post-view input[type="file"]',
    'input[type="file"][accept*="video"]',
    'input[type="file"]',
]
# 上传区(点击会弹原生文件对话框,必须用 expect_file_chooser 拦截,不能裸点)。
# 真实 UI:虚线「+」框,内含「上传时长8小时内…」提示文案。
_UPLOAD_ZONE = [
    'text=上传时长', 'text=上传图片', 'text=从这里上传',
    '.center-upload', '.finder-upload', '[class*="upload-entry"]',
    '[class*="upload"]',
]
# 左侧内容管理导航:视频 / 图文(点它进对应「列表页」)
_IMAGE_NAV = [
    'text=图文', 'a:has-text("图文")', 'li:has-text("图文")',
    '[class*="menu"]:has-text("图文")',
]
# 图文列表页里的「发表图文」按钮(在 micro/content iframe 内,必须跨 frame 点)
_CREATE_IMAGE_BTN = ['text=发表图文', 'button:has-text("发表图文")',
                     '[class*="btn"]:has-text("发表图文")']
# 发布按钮
_PUBLISH_BTN = [
    '.post-view .form-btns button.weui-desktop-btn_primary',
    '.post-view .form-btns button',
    'button:has-text("发表")',
    'button:has-text("发布")',
]
# 发布成功判据(页面跳转/出现提示)
_OK_TEXTS = ["发表成功", "发布成功", "提交成功"]

# ── 位置 POI(可选;选择器需真号校准,任何一步失败都跳过、不阻塞发布)──
_POI_TRIGGER = [
    'text=不显示位置', '[class*="position"]', '[class*="location"]',
    '.location-display', '.position-select',
]
_POI_INPUT = [
    'input[placeholder*="搜索位置"]', 'input[placeholder*="搜索地点"]',
    'input[placeholder*="位置"]', '[class*="position"] input',
    '[class*="location"] input',
]
_POI_RESULT = [
    '[class*="position"] [class*="item"]', '[class*="location"] [class*="item"]',
    '[class*="poi"] [class*="item"]', '[class*="position"] li',
    '.dropdown-item', '[class*="option"]',
]


async def _fill_first(page, selectors, text, timeout=2500) -> bool:
    for sel in selectors:
        try:
            el = page.locator(sel).first
            await el.click(timeout=timeout)
            try:
                await el.fill(text, timeout=timeout)
            except Exception:
                await page.keyboard.type(text, delay=30)   # contenteditable 不支持 fill
            return True
        except Exception:
            continue
    return False


async def _click_first(page, selectors, timeout=3000) -> bool:
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.count():
                await btn.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


async def _click_in_frames(page, selectors, timeout=4000) -> bool:
    """在主页面 + 所有子 frame(micro/content iframe)里点第一个命中的元素。
    视频号发布 UI 在 iframe 里,普通 page.click 点不到,必须遍历 frames。"""
    for frame in page.frames:
        for sel in selectors:
            try:
                loc = frame.locator(sel).first
                if await loc.count():
                    await loc.click(timeout=timeout)
                    return True
            except Exception:
                continue
    return False


async def _set_location(page, location: str):
    """设置视频号位置 POI(可选,best-effort)。任何一步失败都只记日志、跳过,不影响发布。
    流程:点开位置控件 -> 输入搜索 -> 点第一个结果。选择器需真号校准(见 _POI_*)。"""
    if not location:
        return
    try:
        if not await _click_in_frames(page, _POI_TRIGGER, timeout=3000):
            log.warning("[channels_publish] 未找到位置控件,跳过位置设置")
            return
        await page.wait_for_timeout(1200)
        inp, _fr = await _find_in_frames(page, _POI_INPUT)
        if inp is None:
            log.warning("[channels_publish] 未找到位置搜索框,跳过位置(位置选择器需校准 _POI_INPUT)")
            return
        await inp.click()
        await page.keyboard.type(location, delay=40)
        await page.wait_for_timeout(2200)      # 等搜索结果回来
        if not await _click_in_frames(page, _POI_RESULT, timeout=3000):
            log.warning("[channels_publish] 位置「%s」无匹配结果或结果选择器需校准 _POI_RESULT", location)
        else:
            log.info("[channels_publish] 已设置位置: %s", location)
    except Exception as e:
        log.warning("[channels_publish] 设置位置异常(已跳过): %r", e)


async def _clear_location(page) -> str:
    """Clear the publish form's saved POI, then read the form value back."""
    try:
        for frame in page.frames:
            control = frame.locator('.post-position-wrap .position-display').first
            if not await control.count() or not await control.is_visible():
                continue
            before = (await control.inner_text()).strip()
            if before == "不显示位置":
                return ""
            trigger = frame.locator('.post-position-wrap .location-name').first
            if not await trigger.count() or not await trigger.is_visible():
                return "找不到发布表单的当前位置文字"
            await trigger.click(timeout=3000)
            await page.wait_for_timeout(500)
            choice = frame.locator('.post-position-wrap').get_by_text(
                "不显示位置", exact=True).first
            if not await choice.count() or not await choice.is_visible():
                return "位置下拉中找不到可见的“不显示位置”选项"
            await choice.click(timeout=3000)
            await page.wait_for_timeout(400)
            after = (await control.inner_text()).strip()
            if after == "不显示位置":
                log.info("[channels_publish] 位置已由 %s 改为不显示位置", before)
                return ""
            return f"已选择不显示位置，但表单读回为 {after!r}"
        return "找不到发布表单位置控件，无法清除默认位置"
    except Exception as exc:  # noqa: BLE001
        return f"清除默认位置失败: {exc!r}"


async def _find_in_frames(page, selectors):
    """在主页面 + 所有子 frame(wujie iframe)里找第一个命中的定位器。
    Patchright 定位器默认穿透**开放** shadowRoot,但不穿 iframe,故需遍历 page.frames。
    返回 (locator, frame) 或 (None, None)。"""
    for frame in page.frames:                # page.frames[0] 即主 frame
        for sel in selectors:
            try:
                loc = frame.locator(sel).first
                if await loc.count():
                    return loc, frame
            except Exception:
                continue
    return None, None


async def _collect_diag(page, tag: str) -> str:
    """采集发布页真实 DOM 诊断,返回**紧凑单行摘要**(会拼进 UI 错误文案,你不用翻控制台),
    同时打到服务端日志。每个 frame 报:普通/shadow 里的 file input 数、upload 元素数、
    .post-view 数、按钮文案。"""
    parts = []
    try:
        for i, fr in enumerate(page.frames):
            try:
                info = await fr.evaluate("""() => {
                    const q = (s) => document.querySelectorAll(s).length;
                    let sf = 0;
                    const walk = (root) => root.querySelectorAll('*').forEach(el => {
                        if (el.shadowRoot) { sf += el.shadowRoot.querySelectorAll('input[type=file]').length; walk(el.shadowRoot); }
                    });
                    try { walk(document); } catch(e){}
                    const btns = [...document.querySelectorAll('button,[role=button],.weui-desktop-btn')]
                        .map(b => (b.innerText||'').trim()).filter(Boolean).slice(0, 8);
                    const host = (location.host||'') + (location.pathname||'');
                    // ★ 2026-09-14 加:带上可见文字样本。只报元素个数时,
                    //   「pv=0 + btn=[取消/切换/我知道了]」这种现场根本判不出原因;
                    //   有文字才能一眼看出是登录墙/实名/异常提示。
                    const txt = (document.body ? (document.body.innerText||'') : '')
                        .replace(/\\s+/g,' ').slice(0,160);
                    return `${host} fi=${q('input[type=file]')} sf=${sf} up=${q('[class*=upload]')} pv=${q('.post-view')} txt=${txt} btn=[${btns.join('/')}]`;
                }""")
                parts.append(f"f{i}:{info}")
            except Exception:
                parts.append(f"f{i}:eval_err")
    except Exception:
        pass
    summary = " | ".join(parts) or "无 frame 信息"
    log.warning("[channels_publish/%s] %s", tag, summary)
    return summary


async def _dump(page, tag: str) -> str:
    """把当前页面截图 + URL/可见文本快照落盘,返回截图路径。

    ★ 2026-09-14 加:视频号发布失败时原来只有 ``_collect_diag`` 的单行 DOM 摘要,
      没有截图 —— 「点发表后停在 post/create,可见按钮是 取消/切换/我知道了」这类
      弹层拦截问题无法定性。补上与抖音/快手一致的截图落盘。
    """
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = _DEBUG_DIR / f"ch_publish_{tag}_{stamp}"
        png = str(base.with_suffix(".png"))
        try:
            await page.screenshot(path=png, full_page=True)
        except Exception:
            png = ""
        try:
            text = await page.inner_text("body")
        except Exception:
            text = ""
        # ★ 2026-09-14 加:视频号页面大量内容在 wujie iframe / shadowRoot 里,
        #   主 frame 的 inner_text 常常是空的。把每个 frame 的文字都收进来,
        #   快照才有诊断价值(否则「pv=0」的现场打开只有一行 url)。
        parts = []
        for index, frame in enumerate(page.frames):
            try:
                piece = await frame.inner_text("body")
            except Exception:
                continue
            if piece and piece.strip():
                parts.append(f"--- frame{index} ({frame.url[:80]}) ---\n{piece}")
        if parts:
            text = "\n\n".join(parts)
        base.with_suffix(".txt").write_text(
            f"url: {page.url}\n\n{text[:6000]}", encoding="utf-8")
        log.warning("[channels_publish] 已存诊断快照 tag=%s url=%s png=%s",
                    tag, page.url, png)
        return png
    except Exception as exc:
        log.warning("[channels_publish] 存快照失败: %r", exc)
        return ""


# 关掉提示弹层用的按钮文案。**不含「取消」** —— 视频号发布页的「取消」可能直接
# 丢弃当前发布表单,点错代价太大。
_DISMISS_BTN = [
    'button:has-text("我知道了")', 'button:has-text("知道了")',
    'button:has-text("跳过")', 'button:has-text("关闭")',
    '[class*="guide"] [class*="close"]', '[class*="dialog"] [class*="close"]',
]


async def _dismiss_overlays(page, rounds: int = 3) -> None:
    """best-effort 关掉视频号的提示/引导弹层(跨 frame 找)。

    弹层会用遮罩挡住按钮的点击(Playwright ``click()`` 要求「能收到事件」),
    只点语义明确的关闭按钮,绝不 force、绝不点任意祖先。
    """
    for _ in range(rounds):
        changed = False
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        for frame in page.frames:
            for selector in _DISMISS_BTN:
                try:
                    loc = frame.locator(selector)
                    for index in range(min(await loc.count(), 3)):
                        candidate = loc.nth(index)
                        if await candidate.is_visible():
                            await candidate.click(timeout=1500)
                            log.info("[channels_publish] 已关闭弹层(%s)", selector)
                            changed = True
                            break
                    if changed:
                        break
                except Exception:
                    continue
            if changed:
                break
        if not changed:
            break
        await page.wait_for_timeout(600)


# 上传/转码态文案;出现即表示还没就绪。
_UPLOADING_KW = ("上传中", "正在上传", "上传视频", "视频处理中", "转码中", "处理中",
                 "上传完成前")
# 封面入口。★ 2026-09-21 二次修复(视频号 #76 发布成功但封面是视频首帧)——
#   两条**实测**结论直接决定这里的写法:
#   ① 视频号是 Vue(原生 addEventListener),Playwright 的 ``locator.click()`` 会
#      「点了但毫无反应」⇒ 点「编辑」**必须走 JS 原生 el.click()**
#      (见 ``scripts/backfill_cover.py:1005-1006``、``scripts/_sh_open_cover_dialog.js:5``)。
#   ② 发布页/编辑页封面区入口文案是「编辑」;**编辑器打开之后**才存在投放区
#      ``div.single-cover-uploader-wrap``,点它才会弹原生文件对话框
#      (``backfill_cover.py::_apply_shipinhao`` 就是这么投喂成功的)。
# ★ 2026-09-21(#77)修正:**候选入口一律「先可见再点」**(``:visible`` 伪类 + 调用处
#   ``is_visible()`` 二次过滤)—— 视频号页面常年存在**不可见**的
#   ``<div class="text-wrap">上传封面</div>``(Playwright 报 ``element is not visible``),
#   用不带可见性的 ``text=`` 会「点了没反应 / 8s 超时」。
_COVER_TRIGGER = [
    ':text-is("编辑"):visible',                   # 发布页封面区「编辑」(主入口)
    'div.single-cover-uploader-wrap:visible',     # 已激活时的编辑器投放区
    ':text-is("设置封面"):visible', ':text-is("更换封面"):visible',
    ':text-is("编辑封面"):visible',
    'button:has-text("封面"):visible',
    '[class*="cover"] [class*="upload"]:visible',
    '[class*="cover-upload"]:visible',
]
# 编辑器里的**投放区**:点它触发原生文件选择框(backfill 实测可用)
_COVER_UPLOADER_SEL = 'div.single-cover-uploader-wrap'
# 「编辑器真的打开了」的独立判据(文案,**仅用于补充 detail**)。
# ★ 2026-09-21(#77):**必须剔除 `'上传封面'`** —— 那个
#   ``<div class="text-wrap">上传封面</div>`` **始终存在且不可见**,会让文案判据恒真
#   (假阳性)。保留的三个词也必须在 ``_COVER_EDITOR_JS`` 里**自身可见**才算命中;
#   且文案判据**不得**把 ``opened`` 抬成 True(唯一硬判据是投放区可见,见 _cover_editor_open)。
_COVER_EDITOR_OPEN_TXT = ('裁剪', '编辑封面', '替换封面')
# 编辑器里投喂后点一下「应用」,封面才会真正落到发布页
_COVER_EDITOR_APPLY_SEL = [
    '[class*="weui-desktop-dialog"] button:has-text("确认")',
    '[class*="single-cover"] button:has-text("确认")',
    'button:has-text("确认")',
    'text=确认',
    '[class*="weui-desktop-dialog"] button:has-text("确定")',
    '[class*="weui-desktop-dialog"] :text-is("确定")',
    '[class*="single-cover"] button:has-text("确定")',
    'button:has-text("确定")',
    'text=完成',
]
_COVER_EDITOR_OPEN_ATTEMPTS = 3   # 点「编辑」→ 等 → 未开则关引导后再点,最多几轮
_COVER_EDITOR_WAIT_MS = 1800
_COVER_FILE_SEL = [
    'input[type="file"][accept*="image"]',
    'input[type="file"][accept*="png"]',
]
# 点封面区「编辑」把封面编辑器**激活**的 JS。
# ★ 必须 el.click():视频号是 Vue,Playwright 的 locator.click() 点了没反应;
# ★ 优先取**可见**的那个 —— 页面里同时存在 0x0 的隐藏副本(见
#   ``_sh_open_cover_dialog.js:33-50``),只取「最后一个匹配」会拿到隐藏那个。
_COVER_EDIT_JS = r"""
(() => {
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
  const hasBox = (el) => {
    let b = null;
    try { b = el.getBoundingClientRect(); } catch (e) { return false; }
    if (!b || b.width <= 0 || b.height <= 0) return false;
    const cs = getComputedStyle(el);
    return cs.display !== "none" && cs.visibility !== "hidden"
           && parseFloat(cs.opacity || "1") > 0.05;
  };
  const findBy = (pred) => {
    let last = null, lastVis = null;
    for (const item of roots()) {
      let els = [];
      try { els = item.root.querySelectorAll("*"); } catch (e) { continue; }
      for (const el of els) {
        try { if (!pred(el)) continue; last = el; if (hasBox(el)) lastVis = el; } catch (e) {}
      }
    }
    return lastVis || last;
  };
  const rect = (el) => { const b = el.getBoundingClientRect();
    return [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)]; };
  const LABELS = ["编辑", "设置封面", "更换封面", "编辑封面"];
  let btn = findBy((el) => String(el.className || "").indexOf("edit-btn-zIndex") >= 0);
  let how = btn ? "edit-btn-zIndex" : "";
  if (!btn) { btn = findBy((el) => norm(el.textContent) === "编辑"); how = btn ? "text=编辑" : ""; }
  if (!btn) {
    btn = findBy((el) => LABELS.indexOf(norm(el.textContent)) >= 0 && el.children.length === 0);
    how = btn ? "短文案" : "";
  }
  if (!btn) return { ok: false, why: "没找到封面入口(edit-btn-zIndex /「编辑」都没命中)" };
  if (!hasBox(btn)) return { ok: false, why: "封面入口不可见(可能只匹配到隐藏副本)",
                             cls: String(btn.className || "").slice(0, 70) };
  const snap = { how: how, tag: btn.tagName, cls: String(btn.className || "").slice(0, 70),
                 txt: norm(btn.textContent).slice(0, 20), rect: rect(btn) };
  try { btn.click(); } catch (e) { return { ok: false, why: "JS click 抛异常: " + e }; }
  snap.ok = true;
  return snap;
})()
"""
# 「封面编辑器**真的**打开了」的独立判据 —— 不能「点了就算」。
# ★ 2026-09-21(#77):**唯一硬判据 = 投放区 ``div.single-cover-uploader-wrap`` 可见**;
#   文案判据(labOk)**必须该元素自身可见**才算命中(页面里恒有一个不可见的
#   「上传封面」text-wrap,只按存在判定会恒真),且 ``open`` 只由 uploader 决定,
#   文案/弹层仅用于补充 ``why``。判不开就**不投喂**,由调用方如实回报。
_COVER_EDITOR_JS = r"""
(() => {
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
  const hasBox = (el) => {
    let b = null;
    try { b = el.getBoundingClientRect(); } catch (e) { return false; }
    if (!b || b.width <= 0 || b.height <= 0) return false;
    const cs = getComputedStyle(el);
    return cs.display !== "none" && cs.visibility !== "hidden"
           && parseFloat(cs.opacity || "1") > 0.05;
  };
  const findBy = (pred) => {
    let last = null, lastVis = null;
    for (const item of roots()) {
      let els = [];
      try { els = item.root.querySelectorAll("*"); } catch (e) { continue; }
      for (const el of els) {
        try { if (!pred(el)) continue; last = el; if (hasBox(el)) lastVis = el; } catch (e) {}
      }
    }
    return lastVis || last;
  };
  const rect = (el) => { const b = el.getBoundingClientRect();
    return [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)]; };
  const uploader = findBy((el) => String(el.className || "").indexOf("single-cover-uploader-wrap") >= 0);
  const dialog = findBy((el) => String(el.className || "").indexOf("weui-desktop-dialog") >= 0);
  // ★ 文案判据:剔除「上传封面」(恒存在且不可见,会假阳性);
  //   且必须该元素**自身可见**才算命中。
  const LABELS = ["裁剪", "编辑封面", "替换封面"];
  const labelEl = findBy((el) => LABELS.indexOf(norm(el.textContent)) >= 0 && el.children.length === 0);
  const upOk = !!(uploader && hasBox(uploader));
  const dlgOk = !!(dialog && hasBox(dialog));
  const labOk = !!(labelEl && hasBox(labelEl));
  // ★ 唯一硬判据 = 投放区可见(编辑器真的打开了);文案/弹层只补充 why。
  const open = upOk;
  return {
    open: open, uploader: upOk, dialog: dlgOk, label: labOk,
    uploaderRect: upOk ? rect(uploader) : null,
    labelRect: labOk ? rect(labelEl) : null,
    why: open ? "" : ("投放区 single-cover-uploader-wrap " + (uploader ? "在但不可见" : "不存在")
                      + " / 弹层" + (dlgOk ? "可见" : "不可见")
                      + " / 「裁剪|编辑封面|替换封面」可见文案" + (labOk ? "出现" : "未出现")),
  };
})()
"""
# hover 封面**预览图**(带 _COVER_PREVIEW_JS 打的 ``data-chrc-cover`` 锚点)——
# 发布页上已有竖封面预览时,多半要 hover 它 / 点它旁边的按钮才出现可交互上传入口。
# 只派发鼠标事件、不点击;返回命中元素的 tag/cls/rect 供日志(取不到就 ok=False)。
_COVER_HOVER_JS = r"""
(() => {
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
  const hasBox = (el) => {
    let b = null;
    try { b = el.getBoundingClientRect(); } catch (e) { return false; }
    if (!b || b.width < 40 || b.height < 40) return false;
    const cs = getComputedStyle(el);
    return cs.display !== "none" && cs.visibility !== "hidden"
           && parseFloat(cs.opacity || "1") > 0.05;
  };
  const pick = () => {
    for (const item of roots()) {
      let hit = null;
      try { hit = item.root.querySelector("[data-chrc-cover]"); } catch (e) {}
      if (hit) return hit;
    }
    const LABELS = ["封面", "封面图", "设置封面", "更换封面", "编辑封面", "封面预览"];
    let anchor = null;
    for (const item of roots()) {
      if (anchor) break;
      let els = [];
      try { els = item.root.querySelectorAll("div,span,p,label,section,button"); } catch (e) { continue; }
      for (const el of els) {
        let t = "";
        try { t = norm(el.textContent); } catch (e) { continue; }
        if (LABELS.indexOf(t) >= 0) { anchor = el; break; }
      }
    }
    if (!anchor) return null;
    let node = anchor, best = null, bestArea = 0;
    for (let d = 0; d < 5 && node; d += 1, node = node.parentElement) {
      let cands = [];
      try { for (const el of node.querySelectorAll("img,video,canvas")) cands.push(el); } catch (e) {}
      for (const el of cands) {
        if (!hasBox(el)) continue;
        const r = el.getBoundingClientRect();
        const a = r.width * r.height;
        if (a > bestArea) { bestArea = a; best = el; }
      }
      if (best) break;
    }
    return best;
  };
  const el = pick();
  if (!el) return { ok: false, why: "没找到封面预览媒体元素" };
  const r = el.getBoundingClientRect();
  const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
  for (const t of ["mouseover", "mouseenter", "mousemove"]) {
    try {
      el.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true,
        view: window, clientX: cx, clientY: cy }));
    } catch (e) {}
  }
  return { ok: true, tag: el.tagName, cls: String(el.className || "").slice(0, 70),
           rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] };
})()
"""
# ★ 2026-09-21(视频号 #76)加:封面**预览区**定位 ——
#   **不猜类名**,先锚「封面」文案把范围收窄到封面区块,再按几何取最大的可见媒体元素。
#   移植自 ``scripts/_sh_mark_preview.js``(视频号封面编辑弹层上实测可用),唯一差异:
#   那个脚本取「弹层里最大的图」,而**发布页没有弹层**,全页最大的图会是左侧视频预览
#   ⇒ 必须先按文案锚点收窄,再在区块内取面积最大的。
#   载体必须同时收 img / video / canvas / background-image —— 视频号的封面预览
#   **未必是 <img>**(见 _sh_mark_preview.js:5 与 :50-52)。
#   每次调用先清旧标记;取不到就 ok=False,由 _cover_verdict 判 unknown 走 fail-open。
_COVER_PREVIEW_JS = r"""
(() => {
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
  const visibleBox = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") return false;
    if (parseFloat(cs.opacity || "1") < 0.05) return false;
    const r = el.getBoundingClientRect();
    return r.width >= 40 && r.height >= 40;
  };

  for (const item of roots()) {
    try {
      for (const el of item.root.querySelectorAll("[data-chrc-cover]")) {
        el.removeAttribute("data-chrc-cover");
      }
    } catch (e) {}
  }

  // ① 锚点:文案**整块等于**这几个短标签的元素(容器 textContent 太长,不会误命中)。
  const LABELS = ["封面", "封面图", "设置封面", "更换封面", "编辑封面", "封面预览"];
  let anchor = null;
  for (const item of roots()) {
    if (anchor) break;
    let els = [];
    try { els = item.root.querySelectorAll("div,span,p,label,section,button"); } catch (e) { continue; }
    for (const el of els) {
      let t = "";
      try { t = norm(el.textContent); } catch (e) { continue; }
      if (LABELS.indexOf(t) >= 0) { anchor = el; break; }
    }
  }
  if (!anchor) return { ok: false, why: "发布页没找到「封面」区块文案" };

  // ② 从锚点往上最多 5 层,取**第一层**能出候选的容器(别一路爬到整页)。
  let node = anchor;
  let cands = [];
  for (let depth = 0; depth < 5 && node; depth += 1, node = node.parentElement) {
    cands = [];
    try {
      for (const el of node.querySelectorAll("img,video,canvas")) cands.push(el);
    } catch (e) {}
    try {
      for (const el of node.querySelectorAll("div,span,section,a,li")) {
        const bi = getComputedStyle(el).backgroundImage;
        if (bi && bi !== "none" && bi.indexOf("url(") >= 0) cands.push(el);
      }
    } catch (e) {}
    const vis = cands.filter(visibleBox);
    if (vis.length) { cands = vis; break; }
  }

  // ③ 取面积最大者。
  let best = null;
  let bestArea = 0;
  for (const el of cands) {
    const r = el.getBoundingClientRect();
    const a = r.width * r.height;
    if (a > bestArea) { bestArea = a; best = el; }
  }
  if (!best) {
    return { ok: false, why: `「封面」区块内没有 >=40x40 的可见媒体元素(候选 ${cands.length})` };
  }
  best.setAttribute("data-chrc-cover", "1");
  const r = best.getBoundingClientRect();
  const cs = getComputedStyle(best);
  const bg = cs.backgroundImage && cs.backgroundImage !== "none" ? cs.backgroundImage : "";
  return {
    ok: true, tag: best.tagName,
    cls: String(best.className || "").slice(0, 70),
    rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
    src: ((best.currentSrc || best.src || "") || bg).slice(0, 130),
  };
})()
"""
# ★ 2026-09-21 加:封面**预览区**区块内元素的**兜底**选择器(仅当上面的 JS 锚点没命中时才走)。
#   原来是 5 条靠猜的类名,三条硬伤 ——
#     (a) `[class*="cover"]` 是**子串**匹配,``discover``/``coverage`` 也命中;
#     (b) 真实结构里没有 ``cover-preview``/``cover-wrap``/``poster`` 这些名字
#         (见 scripts/_sh_open_cover_dialog.js 用的 ``single-cover-uploader-wrap``
#         / ``edit-btn-zIndex`` / ``weui-desktop-dialog``);
#     (c) 5 条**全部以 img 结尾**,而封面预览未必是 <img>。
#   ⇒ 现在只留**词边界安全**的兜底(class 以 cover 开头、或作为独立 token 出现)。
#   ★ 关于 #76 那轮 ``f5f764868886f984`` 的定性:后来用 post/coverEdit 弹层逐像素
#     比对过 —— 当时拍到的**确实是视频首帧**,即封面**真的没挂上**,探针判「没生效」
#     是**判对了**,不是误判。真因在投喂侧:封面编辑器没被激活,投喂的是页面里那个
#     **隐藏的 input[type=file]**,等于空动作(见 scripts/_sh_click_cover_edit.js:1-3)。
#     ⇒ 修法是「先点『编辑』激活编辑器再投喂」(见 _cover_editor_open/_feed_cover_once),
#       而不是改判据。
_COVER_PREVIEW_SEL = [
    '[class^="cover"] img',
    '[class*=" cover"] img',
    '[class^="cover"]',
    '[class*=" cover"]',
]
# 确认/重试节奏(仅影响确认环节,不影响发布流程)。
# ★ 2026-09-21 二次修复:轮数 = **可用入口数**(trigger→input 共 2 个),不再固定 3 ——
#   #76 那轮三轮全是同一个 file input,等于同一动作重复 3 次、白拖 ~15s。
_COVER_CONFIRM_ROUNDS = 2
_COVER_SETTLE_MS = 2000   # 投喂后等预览图刷出来
_COVER_RETRY_MS = 1500    # 两轮之间
_COVER_PROBE_MAX = 3      # 每次确认最多探测几个预览元素(限住最坏耗时)


async def _wait_video_ready(page, timeout_ms: int = 900000,
                            quiet_rounds: int = 4) -> bool:
    """等到视频上传/转码完成再允许点「发表」。

    ★ 2026-09-14 踩坑:原来只 ``wait_for_timeout(8000)`` 就往下走 —— 对一条 50s 的
      1080x1920 视频根本不够(快手同款问题实测在 70% 时就点了发布)。判据取
      「连续 quiet_rounds 轮(约 8s)页面里都看不到上传态文案」。
    """
    import asyncio

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_ms / 1000
    quiet = 0
    while loop.time() < deadline:
        text = ""
        try:
            text = await page.locator(".post-view").inner_text(timeout=5000)
        except Exception:
            pass
        if not text:
            for frame in page.frames:
                try:
                    text = await frame.inner_text("body")
                    if text:
                        break
                except Exception:
                    continue
        preview_ready = "封面预览" in text and "删除" in text
        if not preview_ready or any(word in text for word in _UPLOADING_KW):
            quiet = 0
        else:
            quiet += 1
            if quiet >= quiet_rounds:
                log.info("[channels_publish] 视频已就绪(页面不再显示上传态)")
                return True
        await page.wait_for_timeout(2000)
    log.warning("[channels_publish] 等待视频上传完成超时")
    return False


async def _dialog_texts(page) -> str:
    """把当前可见的弹层文案抓出来(跨 frame)。

    发布失败时「页面停在 post/create、按钮是 取消/切换/我知道了」这种现场,关键信息
    全在弹层里(例如「请先设置封面」)。原来只有 DOM 数量摘要,判不出原因。
    """
    found = []
    seen = set()
    for frame in page.frames:
        for sel in ('[class*="dialog"]', '[class*="modal"]', '[class*="popup"]',
                    '[role="dialog"]', '[class*="weui-desktop-dialog"]'):
            try:
                loc = frame.locator(sel)
                for index in range(min(await loc.count(), 4)):
                    node = loc.nth(index)
                    if not await node.is_visible():
                        continue
                    text = " ".join((await node.inner_text() or "").split())
                    if text and text[:120] not in seen:
                        seen.add(text[:120])
                        found.append(text[:300])
            except Exception:
                continue
    return " || ".join(found[:3])


async def _cover_probe(page) -> dict:
    """读回封面预览区的实际状态(像素指纹 + src),用于确认封面到底挂上没有。

    ★ 只信像素:上传**没生效**时 ``img.src`` 也会变(换 CDN 变体),故 digest 为主、
      src 仅作兜底 —— 与 ``scripts/backfill_cover.py::_cover_signature`` 同思路。
    ★ 本函数**不落盘、不抛异常**:任何一步取不到就返回 ``ok=False``,由调用方
      fail-open(当作已生效)继续发布。确认逻辑不许成为发布的新失败点。
    ★ 探测元素数/截图超时都有上限(见 ``_COVER_PROBE_MAX``),避免病态页面把
      发布流程拖长。
    """
    nodes = []
    mark: dict = {}
    # (1) 主判据:JS 锚点标记 —— 不猜类名(见 _COVER_PREVIEW_JS)。
    try:
        raw = await page.evaluate(_COVER_PREVIEW_JS)
        mark = raw if isinstance(raw, dict) else {}
    except Exception as exc:                                   # noqa: BLE001
        mark = {"why": f"执行封面标记脚本失败: {exc!r}"}
    if mark.get("ok"):
        try:
            loc = page.locator('[data-chrc-cover="1"]')
            if await loc.count():
                nodes = [loc.first]
        except Exception:                                      # noqa: BLE001
            nodes = []
    # (2) 兜底:词边界安全的 CSS(仅当 JS 锚点没命中时才走;顺序与原逻辑一致)
    if not nodes:
        for frame in page.frames:
            for sel in _COVER_PREVIEW_SEL:
                try:
                    loc = frame.locator(sel)
                    count = await loc.count()
                except Exception:
                    continue
                if not count:
                    continue
                for index in range(min(int(count), _COVER_PROBE_MAX)):
                    try:
                        node = loc.nth(index)
                        if await node.is_visible():
                            nodes.append(node)
                    except Exception:
                        continue
                if nodes:
                    break
            if nodes:
                break
    # ★ 2026-09-21(视频号 #76 事故):必须能一眼看出「到底锚到了谁」—— 原来只回报
    #   一个 digest,命错元素时只能对着 ``f5f764868886f984`` 猜是哪个元素。
    log.info("[channels_publish] 封面探针命中: %s | mark=%s",
             "JS锚点/data-chrc-cover" if nodes else "未命中", mark or "JS 锚点未命中")
    if not nodes:
        return {"ok": False,
                "why": f"封面预览元素没找到({mark.get('why') or '选择器待按真实页面校准'})"}

    shots: List[bytes] = []
    for node in nodes[:_COVER_PROBE_MAX]:
        try:
            shots.append(await node.screenshot(timeout=3000))
        except Exception:
            pass
    if shots:
        return {"ok": True,
                "digest": hashlib.sha1(b"|".join(shots)).hexdigest()[:16],
                "src": ""}

    # 像素截不到才退到 src / background-image(省一次 DOM 往返)
    srcs: List[str] = []
    for node in nodes[:_COVER_PROBE_MAX]:
        try:
            raw = await asyncio.wait_for(
                node.evaluate("el => (el.currentSrc || el.src ||"
                              " getComputedStyle(el).backgroundImage || '')"),
                timeout=4)
        except Exception:
            raw = ""
        if raw:
            srcs.append(str(raw))
    if not srcs:
        return {"ok": False, "why": "封面预览元素在,但像素与 src 都取不到"}
    return {"ok": True, "digest": "", "src": "|".join(srcs)}


def _cover_verdict(before: dict, after: dict) -> Tuple[str, str]:
    """比对投喂前后的封面指纹,返回 ``(verdict, detail)``。

    verdict 三态:
      * ``"changed"``   —— 明确**已生效**(像素或 src 变了)
      * ``"unchanged"`` —— 明确**没生效**(指纹前后一致)→ 才值得重试
      * ``"unknown"``   —— **判不准**(元素没找到/基线没取到)→ fail-open,不重试
    """
    if not after.get("ok"):
        return "unknown", f"投喂后取不到封面预览({after.get('why')})"
    if not before.get("ok"):
        return "unknown", f"投喂前没取到基线({before.get('why')})"
    b_digest, a_digest = before.get("digest") or "", after.get("digest") or ""
    if b_digest and a_digest:
        if b_digest != a_digest:
            return "changed", f"像素 {b_digest}→{a_digest}"
        return "unchanged", f"像素指纹前后一致({a_digest})"
    b_src, a_src = before.get("src") or "", after.get("src") or ""
    if b_src and a_src:
        if b_src != a_src:
            return "changed", "src 变化(无像素基线)"
        return "unchanged", "src 前后一致(无像素基线)"
    return "unknown", "像素与 src 都没取到"


async def _dismiss_guide(page) -> bool:
    """点掉视频号的首次引导弹层「我知道了」(它会遮住封面区/封面编辑器)。

    见 ``scripts/_sh_open_cover_dialog.js:58-70``:引导挡着时封面编辑器打不开,
    必须**点掉引导后重新点「编辑」**。
    """
    el, _frame = await _find_in_frames(page, ['text=我知道了',
                                              'button:has-text("我知道了")'])
    if el is None:
        return False
    try:
        await el.click(timeout=3000)
        await page.wait_for_timeout(1200)
        return True
    except Exception:
        return False


async def _cover_entry_desc(node) -> str:
    """把定位器当前指向的元素描述成一行 ``tag/cls/text/rect``(供日志)。"""
    try:
        info = await node.evaluate(
            """el => ({tag: el.tagName,
                       cls: String(el.className || "").slice(0, 60),
                       txt: (el.textContent || "").replace(/\\s+/g, "").slice(0, 20),
                       rect: (() => { const b = el.getBoundingClientRect();
                         return [Math.round(b.x), Math.round(b.y),
                                 Math.round(b.width), Math.round(b.height)]; })()})""")
    except Exception as exc:                          # noqa: BLE001
        return f"(取元素信息失败: {exc!r})"
    if not isinstance(info, dict):
        return str(info)
    return (f"tag={info.get('tag')} cls={info.get('cls')} "
            f"txt={info.get('txt')} rect={info.get('rect')}")


async def _cover_pick_entry(page):
    """按 ``_COVER_TRIGGER``(可见优先)找第一个**可见**封面入口。

    返回 ``(locator, 描述)`` 或 ``(None, 原因描述)``。**只认可见元素**
    (``is_visible()`` 二次过滤):页面里常年存在不可见的隐藏副本,点隐藏副本 = 空动作
    (``scripts/_sh_click_cover_edit.js:1-3``)。找不到就如实返回 None,由调用方回报。
    """
    errs: list = []
    for sel in _COVER_TRIGGER:
        for frame in page.frames:
            try:
                loc = frame.locator(sel)
                count = int(await loc.count())
            except Exception:
                continue
            for index in range(min(count, 3)):
                try:
                    node = loc.nth(index)
                    if not await node.is_visible():
                        continue
                    return node, f"<{sel}> {await _cover_entry_desc(node)}"
                except Exception as exc:              # noqa: BLE001
                    errs.append(f"{sel}: {exc!r}")
    return None, ("没找到可见的封面入口(候选全部不可见/未命中)"
                  + (f";异常 {errs[:2]}" if errs else ""))


async def _cover_editor_open(page,
                             attempts: int = _COVER_EDITOR_OPEN_ATTEMPTS
                             ) -> tuple[bool, str]:
    """点封面区「编辑」把封面编辑器**激活**,并确认它**真的打开了**。

    返回 ``(是否打开, 说明)``。

    ★ **唯一硬判据 = 投放区 ``div.single-cover-uploader-wrap`` 可见**
      (``_COVER_EDITOR_JS`` 的 ``uploader``);``uploader=False`` 时**一律返回 False**,
      文案判据(labOk)只进日志/``detail``,**不得**把 opened 抬成 True ——
      2026-09-21 #77:页面里那个恒存在且不可见的「上传封面」text-wrap 曾让文案判据
      恒真、误报「编辑器已打开」,随后点隐藏入口 8s 超时、掉进隐藏 input 兜底。
    ★ 点「编辑」必须用 JS 原生 ``el.click()`` —— 视频号是 Vue,Playwright 的
      ``locator.click()`` 会「点了没反应」(``scripts/backfill_cover.py:1005-1006``)。
    ★ 每轮顺序:判据 → **hover 封面预览图** → JS 点「编辑」 → 仍没点中则找
      **可见**候选入口再点一次 → 关引导「我知道了」 → 下一轮重判。
    """
    last = "编辑器判据未命中"
    for attempt in range(1, max(1, attempts) + 1):
        state: dict = {}
        try:
            raw = await page.evaluate(_COVER_EDITOR_JS)
            state = raw if isinstance(raw, dict) else {}
        except Exception as exc:                      # noqa: BLE001
            state = {"why": f"执行编辑器判据脚本失败: {exc!r}"}
        up_ok = bool(state.get("uploader"))
        # ★ 两个判据**分开打**:合一句 `uploader=False label=True` 会严重误导
        log.info("[channels_publish] 编辑器判据 第 %d/%d 次: uploader(可见投放区)=%s "
                 "label(可见文案)=%s dialog(可见弹层)=%s", attempt, attempts,
                 up_ok, state.get("label"), state.get("dialog"))
        if state.get("open") and up_ok:
            log.info("[channels_publish] 封面编辑器已打开(第 %d 次探测 uploader=%s"
                     " label=%s)", attempt, up_ok, state.get("label"))
            return True, (f"已打开(第{attempt}次探测 uploader={up_ok}"
                          f" label={state.get('label')})")
        last = state.get("why") or last
        log.warning("[channels_publish] 封面编辑器未打开(第 %d/%d 次 uploader=%s"
                    " label=%s): %s", attempt, attempts, up_ok, state.get("label"), last)
        if attempt >= attempts:
            break
        # (1) hover 封面预览图(预览区多半要 hover 才出现可交互入口)
        try:
            hov = await page.evaluate(_COVER_HOVER_JS)
            if isinstance(hov, dict):
                log.info("[channels_publish] hover 封面预览: ok=%s tag=%s cls=%s rect=%s",
                         hov.get("ok"), hov.get("tag"), hov.get("cls"), hov.get("rect"))
        except Exception as exc:                      # noqa: BLE001
            log.info("[channels_publish] hover 封面预览失败(忽略): %r", exc)
        # (2) JS 原生点「编辑」(Vue 下 Playwright click 无效)
        clicked: dict = {}
        try:
            raw = await page.evaluate(_COVER_EDIT_JS)
            clicked = raw if isinstance(raw, dict) else {}
        except Exception as exc:                      # noqa: BLE001
            clicked = {"ok": False, "why": f"执行「编辑」点击脚本失败: {exc!r}"}
        log.info("[channels_publish] 封面编辑器激活尝试 %d/%d: edit=%s",
                 attempt, attempts, clicked or "未命中")
        js_ok = bool(clicked.get("ok"))
        if not js_ok:
            last = str(clicked.get("why") or "JS 点「编辑」未命中")
        # (3) 按**可见**候选入口再核一遍(取证:把命中的 tag/cls/text/rect 打进日志);
        #     JS 没点中且找到可见入口时,才补一次点击(点不中只记日志,绝不点隐藏副本)
        node, desc = await _cover_pick_entry(page)
        log.info("[channels_publish] 可见候选入口: %s", desc)
        if node is not None and not js_ok:
            try:
                await node.click(timeout=4000)
                log.info("[channels_publish] 已点可见候选入口: %s", desc)
            except Exception as exc:                  # noqa: BLE001
                log.info("[channels_publish] 候选入口点击失败(忽略): %r", exc)
        await page.wait_for_timeout(_COVER_EDITOR_WAIT_MS)
        if await _dismiss_guide(page):
            log.info("[channels_publish] 已点掉引导弹层「我知道了」")
    return False, last


async def _apply_cover_editor(page) -> str:
    """编辑器里投喂后点一次「确定」,封面才会真正落到发布页(best-effort)。

    返回非空串 = 没点成/点失败(调用方只记日志)。**不抛异常、绝不点「取消」**
    (``_DISMISS_BTN`` 刻意不含「取消」:发布页的「取消」可能丢弃整个发布表单)。
    """
    try:
        # The page keeps a hidden duplicate dialog in the DOM.  Selecting the
        # first matching "确定" hits that hidden button and leaves the real
        # cover editor open, which then blocks the final publish click.
        for frame in page.frames:
            for selector in _COVER_EDITOR_APPLY_SEL:
                nodes = frame.locator(selector)
                count = min(await nodes.count(), 12)
                for index in range(count):
                    node = nodes.nth(index)
                    if not await node.is_visible() or not await node.is_enabled():
                        continue
                    try:
                        await node.click(timeout=5000)
                        await page.wait_for_timeout(_COVER_SETTLE_MS)
                        state = await page.evaluate(_COVER_EDITOR_JS)
                        if not (isinstance(state, dict) and state.get("uploader")):
                            log.info("[channels_publish] 封面编辑器已确认收起")
                            return ""
                    except Exception as exc:  # noqa: BLE001
                        log.warning("[channels_publish] 可见的封面确定按钮未生效: %r", exc)
        return "没能点中可见的「确定/完成」并收起封面编辑器"
    except Exception as exc:  # noqa: BLE001
        return f"封面编辑器收尾异常: {exc!r}"


async def _feed_cover_by_editor(page, cover_path: str) -> str:
    """在**已激活**的封面编辑器里投喂:点投放区触发原生文件对话框。"""
    last = ""
    for frame in page.frames:
        try:
            loc = frame.locator(_COVER_UPLOADER_SEL)
            count = await loc.count()
        except Exception:
            continue
        for index in range(min(int(count), 3)):
            try:
                node = loc.nth(index)
                if not await node.is_visible():
                    continue
                async with page.expect_file_chooser(timeout=15000) as info:
                    await node.click(timeout=8000)
                chooser = await info.value
                await chooser.set_files(cover_path)
                log.info("[channels_publish] 已通过 file chooser 投喂封面(%s)",
                         _COVER_UPLOADER_SEL)
                return ""
            except Exception as exc:                  # noqa: BLE001
                last = repr(exc)
                continue
    # 退一步:找**可见**的「上传封面/替换封面」文案入口(隐藏副本会点了没反应)
    el, _frame = await _find_in_frames(
        page, [':text-is("上传封面"):visible', ':text-is("替换封面"):visible'])
    if el is not None:
        try:
            if not await el.is_visible():
                return "退路入口存在但不可见(不点隐藏副本)"
            desc = await _cover_entry_desc(el)
            async with page.expect_file_chooser(timeout=15000) as info:
                await el.click(timeout=8000)
            chooser = await info.value
            await chooser.set_files(cover_path)
            log.info("[channels_publish] 已通过 file chooser 投喂封面(可见文案入口 %s)",
                     desc)
            return ""
        except Exception as exc:                      # noqa: BLE001
            return f"点可见「上传封面」入口触发文件对话框失败: {exc!r}"
    return ("编辑器里没找到封面投放区(single-cover-uploader-wrap / 可见「上传封面」都没命中)"
            + (f";最后异常 {last}" if last else ""))


async def _feed_cover_by_input(page, cover_path: str) -> str:
    """**兜底**路径:直接把文件塞给 input[type=file]。

    ★ 视频号该页的 input 是**隐藏**的,直接 set_input_files 实测**不生效**
      (``scripts/_sh_click_cover_edit.js:1-3``)⇒ 这条只在「换一个真正不同的入口」
      时使用,日志会写明是兜底路径,绝不冒充主路径的成功。
    """
    for frame in page.frames:
        for sel in _COVER_FILE_SEL:
            try:
                loc = frame.locator(sel).first
                if await loc.count():
                    await loc.set_input_files(cover_path, timeout=15000)
                    log.warning("[channels_publish] 已通过 file input 投喂封面"
                                "(兜底路径:该 input 多为隐藏、可能不生效)")
                    return ""
            except Exception:
                continue
    return "没找到封面的 input[type=file]"


async def _feed_cover_once(page, cover_path: str, prefer: str = "trigger") -> str:
    """投喂一次封面文件。返回 "" = 投喂动作没报错;否则返回原因串。

    ★ 默认 ``prefer="trigger"``:**先激活封面编辑器,再走 file chooser** ——
      点「编辑」(JS 原生 click)→ 确认编辑器真的打开 → 点投放区触发原生文件对话框。
      编辑器打不开就**直接回报原因(不投喂、不静默降级成 input 冒充成功)**。
    ``prefer="input"``:明确记录的兜底路径(直接塞隐藏 input),只用于「换一个真正
      不同的入口」的那一轮。
    """
    if prefer == "input":
        return await _feed_cover_by_input(page, cover_path)
    opened, detail = await _cover_editor_open(page)
    if not opened:
        return f"封面编辑器没打开(点了「编辑」但没出现上传区): {detail}"
    return await _feed_cover_by_editor(page, cover_path)


async def _confirm_cover(page, cover_path: str,
                         rounds: int = _COVER_CONFIRM_ROUNDS,
                         strict: bool = False) -> str:
    """投喂封面并**读回确认**;不确定就 fail-open,绝不阻断发布。

    返回 ``""`` = 已生效 / 判不准(都按已生效继续);非空串 = 明确没生效的原因。

    ★ 2026-09-21 二次修复:每一轮必须换一个**真的不同**的入口 ——
      第 1 轮 ``prefer="trigger"``(激活封面编辑器 → file chooser);
      第 2 轮 ``prefer="input"``(直接塞隐藏 input,日志写明是兜底路径)。
      #76 那轮三轮全走同一个 file input、等于同一动作重复 3 次,这里根除。
    ★ 编辑器打不开 ⇒ **一轮就回报明确原因**,不做同动作空转。
    """
    plans = ["trigger", "input"][:max(1, rounds)]
    last = ""
    for index, entry in enumerate(plans, start=1):
        before = await _cover_probe(page)
        feed_note = await _feed_cover_once(page, cover_path, prefer=entry)
        if feed_note:
            last = (f"封面未确认生效(第 {index}/{len(plans)} 轮未投喂成功,"
                    f"入口={entry}): {feed_note}")
            log.warning("[channels_publish] %s", last)
            if "封面编辑器没打开" in feed_note:
                # ★ 编辑器打不开:再走一轮同一个动作没意义,一轮就如实回报
                return (f"封面未确认生效(编辑器打不开,未再空转重试): {cover_path};"
                        f" 原因: {feed_note}")
            await page.wait_for_timeout(_COVER_RETRY_MS)
            continue
        if entry == "trigger":
            # 编辑器里投喂完还要点一下「确定」,封面才会落到发布页
            apply_note = await _apply_cover_editor(page)
            if apply_note:
                # 文件上传完成时「确定」会短暂被遮罩挡住；点击报超时不等于
                # 封面没落到发布页。先读回预览，再决定是否阻断发表。
                log.warning("[channels_publish] 封面编辑器收尾待读回: %s", apply_note)
        else:
            apply_note = ""
        await page.wait_for_timeout(_COVER_SETTLE_MS)
        verdict, detail = _cover_verdict(before, await _cover_probe(page))
        if verdict == "changed":
            log.info("[channels_publish] 封面已确认生效: %s (%s)", cover_path, detail)
            return ""
        if apply_note:
            return f"封面编辑器收尾失败且预览未确认变化: {apply_note}; {detail}"
        if verdict == "unknown":
            if strict:
                return f"封面预览无法确认: {detail}"
            # ★ fail-open:确认这一步本身判不了(选择器没命中/页面结构变了),
            #   当作已生效继续走发布,不重试、不报错。
            log.info("[channels_publish] 封面生效无法确认(%s),按 fail-open 继续发布",
                     detail)
            return ""
        last = (f"封面未确认生效(第 {index}/{len(plans)} 轮未生效,"
                f"入口={entry},{detail})")
        log.warning("[channels_publish] %s,换下一个入口", last)
        await page.wait_for_timeout(_COVER_RETRY_MS)
    return (f"封面未确认生效({len(plans)}轮不同入口重试后仍未生效): {cover_path};"
            f" 最后判据: {last}")


async def _set_cover(page, cover_path: str,
                     rounds: int = _COVER_CONFIRM_ROUNDS,
                     strict: bool = False) -> str:
    """best-effort 给视频号设置封面,并**读回确认**结果。

    返回 ``""`` = 成功 / 跳过 / 判不准(都按已生效继续);非空串 = 失败原因 ——
    调用方只把非空串记进日志,**绝不阻断发布**。

    ★ 视频号封面虽是发布前置条件,但「确认」这一步本身不许成为新的失败点:
      判不准(选择器漂移)按 fail-open 走;只有明确读到「没生效」才换**另一个入口**
      重试;重试完仍没生效也只回报原因,不抛异常、不提前中断发布。
    ★ 2026-09-21 二次修复:主路径改为「**先点『编辑』激活封面编辑器,再走
      file chooser 投喂**」—— 直接 set_input_files 打的是页面里那个**隐藏 input**,
      #76 实测完全不生效(见 ``scripts/_sh_click_cover_edit.js:1-3``)。
    """
    if not cover_path:
        return "未指定封面(可设 CREATORHUB_COVER_PATH 指定默认封面)"
    if not Path(cover_path).exists():
        return f"封面文件不存在: {cover_path}"
    try:
        return await _confirm_cover(page, cover_path, rounds, strict=strict)
    except Exception as exc:                      # noqa: BLE001
        if strict:
            return f"封面确认流程异常: {exc!r}"
        # ★ fail-open 兜底:调用点没有 try,这里冒泡会打断发布 —— 一律吞掉
        log.warning("[channels_publish] 封面确认流程异常(按 fail-open 继续发布): %r", exc)
        return ""


async def _wait_create_ready(page, timeout_ms: int = 120000,
                             quiet_rounds: int = 3) -> bool:
    """等视频号发布页(wujie 微前端)**初始化完成**。

    ★ 2026-09-14 踩坑(视频号两次失败的同一个真因):``goto`` 之后固定
      ``wait_for_timeout(4000)`` 远远不够。页面顶部会长时间挂一个
      「页面初始化中」的 toast,这期间:
        - ``.post-view`` 根本不存在(DOM 诊断 ``pv=0``)
        - 上传入口、描述框都还没渲染
        - 主 frame 的可见文字只有「视频号 · 助手」几个字
      历史失败报的是「未找到可用上传入口/文件选择器」,而截图里其实**已经**
      是正常的发布页(有虚线「+」上传框和「上传时长8小时内…」提示),只是晚了一步。
      判据:既能看到上传区文案(「上传时长」/「发表动态」),又连续 quiet_rounds 轮
      看不到「初始化」字样。
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_ms / 1000
    quiet = 0
    while loop.time() < deadline:
        try:
            if await page.locator('.post-view .upload input[type="file"]').count():
                log.info("[channels_publish] 上传入口已渲染,发布页就绪")
                return True
        except Exception:
            pass
        text = ""
        for frame in page.frames:
            try:
                piece = await frame.inner_text("body")
            except Exception:
                continue
            if piece and piece.strip():
                text += piece + "\n"
        ready_marker = ("上传时长" in text or "发表动态" in text
                        or "视频描述" in text or "添加描述" in text)
        initializing = "初始化" in text
        if ready_marker and not initializing:
            quiet += 1
            if quiet >= quiet_rounds:
                log.info("[channels_publish] 发布页初始化完成")
                return True
        else:
            quiet = 0
        await page.wait_for_timeout(2000)
    log.warning("[channels_publish] 等待发布页初始化超时")
    return False


async def _verify_on_post_list(ctx, title: str, timeout_ms: int = 90000
                               ) -> tuple[bool, str]:
    """另开一页打开视频号「作品管理」,核对本次标题是否真的在列表里。

    ★ 2026-09-14 加,与快手 ``_verify_on_manage`` 同一思路:视频号这边的
      「跳列表页 / 命中成功 toast」同样只能证有、不能证无 —— 实测量过
      「三路都没命中、平台其实也没发」的假失败,以及「疑似弹层拦截」的假不确定。
      唯一可信的判据是创作平台自己的作品列表,故发布动作结束后主动去核对:
      核对不上就把「成功」降级、核对上了就把「失败」升级。
      核对走两条路:作品列表接口的 JSON 响应 + 列表页 DOM 文本。
    """
    probe = "".join(str(title or "").split())[:8]
    if not probe:
        return False, "无标题可比对"
    page = await ctx.new_page()
    hits: list[str] = []
    dom_hit = False

    async def on_response(response):
        try:
            if "/post" not in response.url and "list" not in response.url \
                    and "cgi-bin" not in response.url:
                return
            if "json" not in (response.headers.get("content-type") or ""):
                return
            raw = await response.text()
            try:
                decoded = json.dumps(json.loads(raw), ensure_ascii=False)
            except Exception:
                decoded = raw
            if probe in decoded:
                hits.append(response.url)
        except Exception:
            return

    page.on("response", on_response)
    try:
        await page.goto(POST_LIST_URL, wait_until="domcontentloaded",
                        timeout=40000)
        waited = 0
        while waited * 1500 < timeout_ms:
            if hits:
                break
            for frame in page.frames:
                try:
                    text = await frame.inner_text("body")
                except Exception:
                    continue
                if probe in text or probe in "".join(text.split()):
                    dom_hit = True
                    break
            if dom_hit:
                break
            await page.wait_for_timeout(1500)
            waited += 1
        if hits:
            return True, f"作品列表接口命中标题「{probe}」({len(hits)} 个响应)"
        if dom_hit:
            return True, f"作品管理页 DOM 命中标题「{probe}」"
        return False, f"作品管理列表中未出现本次标题「{probe}」"
    except Exception as exc:
        return False, f"核对失败: {exc!r}"
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def publish_channels(mgr: BrowserManager, identity: Identity,
                           storage_state_json: str, media_type: str, title: str,
                           desc: str, media_paths: List[str], topics: str = "",
                           headed: bool = True, timeout_seconds: int = 180,
                           location: str = "", cover_path: str = "",
                           location_mode: str = "keep",
                           cover_required: bool = False,
                           on_submit: Callable[[], None] | None = None,
                           ) -> Tuple[bool, str, str]:
    """发布一条视频号作品。返回 (ok, result_url, error)。
    location:可选,视频号位置 POI(best-effort,设不上不影响发布)。
    cover_path:可选,封面图;缺省时取进程级默认封面(见 CREATORHUB_COVER_PATH)。
    storage_state_json 仅校验用,实际登录态在该账号持久 profile 里。"""
    files = [str(Path(p)) for p in media_paths if p and Path(p).exists()]
    if not files:
        return False, "", "没有可用的本地媒体文件(路径不存在)"
    tags = [t.strip().lstrip("#") for t in (topics or "").split(",") if t.strip()]
    # 视频号正文:描述 + 话题(标题另填短标题框)
    body = ((desc or "")
            + ("\n" + " ".join(f"#{t}" for t in tags) if tags else "")).strip()[:1000]

    # ★ 2026-09-14 改:open_headed 会新开 Chromium 窗口并置顶抢焦点,发布期间反复
    #   顶掉用户正在用的窗口。改用 open_background(有头但最小化、不置顶)。
    ctx = await mgr.open_background(identity)
    page = await ctx.new_page()
    ok, result_url, error = False, "", ""
    try:
        # ★ 2026-09-14 加:发布前查重。视频号上一次尝试(10:35)是「已点发表但未确认
        #   成功」—— 页面停在 post/create,既不能证明发了、也不能证明没发。直接重发
        #   有**重复投稿**风险,所以先去创作后台的作品列表按标题核对一次:
        #   已有同名作品就直接判成功返回,不再上传(用户要的是「发出去了」,不是「再发一遍」)。
        if title:
            existed, detail = await _verify_on_post_list(
                ctx, title, timeout_ms=45000)
            log.warning("[channels_publish] 发布前查重: found=%s %s", existed, detail)
            if existed:
                log.warning("[channels_publish] 已存在同名作品,跳过本次上传(防重复)")
                return True, POST_LIST_URL, ""

        # 视频号发布入口就是 create 页;图文/视频靠点左侧导航切换(finderNewLifeCreateg 会 302 回 create)
        await page.goto(CREATE_URL_VIDEO, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(4000)
        if "login.html" in page.url or page.url.rstrip("/").endswith("/login"):
            return False, "", f"logged_out:视频号助手未登录(落到 {page.url})"

        # ★ 2026-09-14 加:等 wujie 微前端初始化完成再动手(见 _wait_create_ready)。
        #   原来 goto 后只等 4s,页面还在「页面初始化中」,于是上传入口找不到、
        #   pv=0,报出误导性的「未找到可用上传入口」。
        if not await _wait_create_ready(page, timeout_ms=120000):
            diag = await _collect_diag(page, "create-timeout")
            log.warning("[channels_publish] 发布页初始化超时,仍继续尝试: %s", diag)
            await _dump(page, "create-timeout")
        await _dismiss_overlays(page)

        # 图文:点左侧「图文」→ 图文列表页 → 点「发表图文」→ 图文发布表单
        # (视频号 UI 在 micro/content iframe 里,按钮要跨 frame 点)
        if media_type == "images":
            await _click_in_frames(page, _IMAGE_NAV, timeout=4000)
            await page.wait_for_timeout(2000)
            if await _click_in_frames(page, _CREATE_IMAGE_BTN, timeout=5000):
                await page.wait_for_timeout(2500)
            else:
                diag = await _collect_diag(page, "no-create-image-btn")
                return False, "", f"未找到「发表图文」按钮,无法进图文发布页。DOM诊断: {diag}"

        want = files if media_type == "images" else files[:1]
        uploaded = False
        # 首选:直接给隐藏 <input type=file> 塞文件(不弹原生对话框,最稳)
        up, _fr = await _find_in_frames(page, _FILE_SEL)
        if up is not None:
            try:
                await up.set_input_files(want, timeout=20000)
                uploaded = True
            except Exception:
                uploaded = False
        # 兜底:input 是点击时按需创建 —— 用 expect_file_chooser 拦截原生文件框(关键!
        # 裸点上传区会弹 Windows「打开」对话框把 Patchright 卡死,必须这样接管)
        if not uploaded:
            try:
                async with page.expect_file_chooser(timeout=10000) as fc_info:
                    if not await _click_in_frames(page, _UPLOAD_ZONE, timeout=4000):
                        raise RuntimeError("未点到上传区")
                chooser = await fc_info.value
                await chooser.set_files(want)
                uploaded = True
            except Exception:
                uploaded = False
        if not uploaded:
            diag = await _collect_diag(page, "upload-failed")
            # ★ 2026-09-14 加:失败必须留图。原来这条路径只报 DOM 计数、不落快照,
            #   于是「上传入口找不到 + pv=0」查了两轮都只能靠猜。
            png = await _dump(page, "upload-failed")
            return False, "", (f"上传失败(未找到可用上传入口/文件选择器)。DOM诊断: {diag}"
                               f"{'; 诊断截图: ' + png if png else ''}")

        # 等待转码/上传(视频较久)
        # ★ 2026-09-14 修:原来固定 wait_for_timeout(8000) 就往下走 —— 对一条 50s 的
        #   1080x1920 视频根本不够。快手侧实测就是在「70% 上传中」点了发布,被平台
        #   弹窗挡回却误判成功。这里改成按上传态文案轮询到就绪为止。
        if media_type == "video":
            if not await _wait_video_ready(page):
                png = await _dump(page, "upload-timeout")
                return False, "", ("等待视频上传完成超时,主动放弃点击发表以免误报成功。"
                                   f"诊断快照: {png or 'data/debug'}")
        else:
            await page.wait_for_timeout(4000)
        # 关掉可能出现的引导/公告弹层(它们带遮罩,会挡住后续所有点击)
        await _dismiss_overlays(page)

        if title:
            el, _tf = await _find_in_frames(page, _SHORT_TITLE_SEL)
            if el is None and cover_required:
                return False, "", "找不到视频号短标题输入框"
            if el is not None:
                try:
                    await el.fill(title[:16])
                    if cover_required and await el.input_value() != title[:16]:
                        return False, "", "视频号短标题读回与发布包不一致"
                except Exception as exc:
                    if cover_required:
                        return False, "", f"视频号短标题无法确认: {exc!r}"
        if body:
            el, _df = await _find_in_frames(page, _DESC_SEL)
            if el is not None:
                try:
                    await el.click()
                    await page.keyboard.type(body, delay=20)
                except Exception:
                    pass
        # Empty location is an explicit clear request for versioned packages.
        if location_mode == "clear":
            location_note = await _clear_location(page)
            if location_note:
                png = await _dump(page, "location-not-cleared")
                return False, "", (f"发布前位置未清除: {location_note}; "
                                   f"诊断截图: {png}")
        elif location_mode == "set":
            await _set_location(page, location)
        # 封面:视频号把封面当发布前置条件,必须在按「发表」之前设好
        cover_note = await _set_cover(
            page,
            cover_path if cover_required else cover_path or _default_cover(),
            strict=cover_required,
        )
        if cover_note:
            log.warning("[channels_publish] 封面未设置: %s", cover_note)
            if cover_required or cover_path:
                png = await _dump(page, "cover-not-applied")
                return False, "", f"封面未设置: {cover_note}; 诊断截图: {png}"
        await page.wait_for_timeout(1500)

        log.info("[channels_publish] 封面已处理，开始定位发表按钮")
        pub, _pf = await _find_in_frames(page, _PUBLISH_BTN)
        if pub is None:
            diag = await _collect_diag(page, "no-publish-btn")
            await _dump(page, "no-publish-btn")
            return False, "", (f"上传/填写已完成但未找到发表按钮。DOM诊断: {diag}")
        if on_submit is not None:
            try:
                on_submit()
            except Exception as exc:
                return False, "", f"发表前写入标记失败: {exc!r}"
        try:
            log.info("[channels_publish] 已定位发表按钮，准备点击")
            await pub.click(timeout=5000)
            log.info("[channels_publish] 已点击发表，等待平台回执")
        except Exception as e:
            if on_submit is not None:
                await _dump(page, "click-result-unknown")
                return False, "", f"write_uncertain:首次发表点击结果不明: {e!r}"
            # 弹层遮罩会吃掉点击:关掉后再试一次,仍失败才算失败
            log.warning("[channels_publish] 点发表失败(%r),关闭弹层后重试", e)
            await _dismiss_overlays(page)
            pub, _pf = await _find_in_frames(page, _PUBLISH_BTN)
            if pub is None:
                await _dump(page, "no-publish-btn-retry")
                return False, "", "关闭弹层后仍未找到发表按钮"
            try:
                await pub.click(timeout=5000)
            except Exception as exc2:
                await _dump(page, "click-fail")
                return False, "", f"点发表失败: {exc2!r}"

        # 等成功:视频号发表后会**跳到「图文/视频管理」列表页**(URL 含 PostList),
        # 或短暂弹「发表成功」toast。以跳列表页为主判据(实测 finderNewLifePostList)。
        last_dialog = ""
        for _ in range(int(timeout_seconds / 2)):
            url_l = page.url.lower()
            # finderNewLifePostList / post/list 等管理列表页 -> 发表成功后的落点
            if "postlist" in url_l or "/post/list" in url_l:
                ok = True
                break
            # toast 可能在主页面或 micro/content iframe 里
            for fr in page.frames:
                try:
                    if any([await fr.get_by_text(t, exact=False).count() for t in _OK_TEXTS]):
                        ok = True
                        break
                except Exception:
                    pass
            if ok:
                break
            # ★ 2026-09-14:弹层出现 = 这次提交被平台拦下(典型「请先设置封面」)。
            #   立刻记录文案,避免等到超时后现场已被刷掉、无从定性。
            dlg = await _dialog_texts(page)
            if dlg and dlg != last_dialog:
                last_dialog = dlg
                log.warning("[channels_publish] 发表后出现弹层: %s", dlg)
            await page.wait_for_timeout(2000)
        result_url = page.url if ok else ""
        # ★★ 用创作平台的作品列表做最终裁决(见 _verify_on_post_list 的说明):
        #    「跳列表页 / 命中成功文案」只能证有、不能证无。核对不上把成功降级、
        #    核对上了把失败升级 —— 不让启发式决定一条作品的成败。
        if ok or not error:
            log.info("[channels_publish] 页面回执判据 ok=%s，开始作品管理核对", ok)
            found, detail = await _verify_on_post_list(ctx, title)
            log.warning("[channels_publish] 平台核对: found=%s %s", found, detail)
            if found and not ok:
                ok = True
                result_url = result_url or page.url
            elif not found and ok:
                log.warning("[channels_publish] 启发式判成功但平台核对未通过 → 降级")
                ok = False
                error = (f"启发式判据判成功,但打开「作品管理」核对未发现本次作品"
                         f"({detail});按未确认处理,请到平台复核。")
            elif not found and not ok:
                error = (error or "已点发表但未确认成功") + \
                        f"; 且「作品管理」核对未发现本次作品({detail})"
        if not ok:
            dialog = last_dialog or await _dialog_texts(page)
            png = await _dump(page, "no-success")
            error = (f"已点发表但未确认成功;请到视频号助手核对。"
                     f"当前页: {page.url}"
                     + (f"; 页面弹层: {dialog}" if dialog else "")
                     + (f"; 封面: {cover_note}" if cover_note else "")
                     + f"; {error}"
                     + (f"; 诊断截图: {png}" if png else ""))
    except Exception as e:
        error = f"发布异常: {e!r}"
    finally:
        try:
            await ctx.close()
        except Exception:
            pass
        try:
            await mgr.stop_minimize_hold(identity)
        except Exception:
            pass
    return ok, result_url, error
