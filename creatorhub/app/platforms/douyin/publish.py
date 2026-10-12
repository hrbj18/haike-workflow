"""抖音发布入口(浏览器自动化抖音创作者服务平台 creator.douyin.com)。

抖音 PC 端上传要分片传 upload 节点 + a_bogus 签名 + create_aweme,纯 HTTP 直发链路长、
易随改版失效;发布是低频写操作,和快手一样走浏览器自动化性价比最高,也贴合本项目
「登录态浏览器 + 免手写签名」的路线:用账号专属持久 profile(已含创作者登录态)打开
发布页,上传文件、填标题/正文、点发布。

⚠️ 实验性:发布页选择器随抖音改版可能失效,集中在下面的 _* 选择器常量;
   发布时弹真实窗口,遇滑块验证 / 需补封面 / 定位话题必填可在窗口里手动处理。

调试:失败(含「已点发布但未确认成功」)时会把截图 + 页面 URL/文本快照写到
   data/debug/dy_publish_*.{png,txt},并在服务端控制台打印 [dy-publish] 日志。
   抖音创作平台改版频繁,首次真机发布基本都要据此把选择器校准一次。
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Tuple

from ...browser.identity import Identity
from ...browser.manager import BrowserManager
from .cover import close_cover_overlay, set_douyin_cover

UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"
# 图文发布入口(default-tab=3 直达「发布图文」;失败再退回点 tab)
IMAGE_URL = "https://creator.douyin.com/creator-micro/content/upload?default-tab=3"
# 作品管理页。★ 2026-09-14 加:这是**唯一**能证伪「抖音到底发出去没有」的地方。
# 注意 creatorhub 自己的 /api/works/sync 抓的是**公开主页**,刚发布/审核中的作品在
# 那里看不见 —— 所以它不能用来判「没发出去」,只能判「已经发出去了」。
MANAGE_URL = "https://creator.douyin.com/creator-micro/content/manage"
_TAB_IMAGE = ['div:has-text("发布图文")', 'text=发布图文', 'text=图文']
# 视频有独立「标题」短标题输入;图文有「作品标题」
_TITLE_SEL = ['input[placeholder*="填写作品标题"]', 'input[placeholder*="作品标题"]',
              'input[placeholder*="标题"]', '.title-input input', 'input.semi-input']
# 正文/简介富文本(抖音创作者用 editor-kit 富文本,contenteditable)
_DESC_SEL = ['.editor-kit-editor-container [contenteditable="true"]',
             'div[data-placeholder*="简介"]', 'div[data-placeholder*="作品"]',
             'div[contenteditable="true"]', '.zone-container',
             'textarea[placeholder*="简介"]', 'textarea']
# 最终提交按钮(排除「定时发布」等干扰,后面再按 enabled + 文本精确过滤)
_PUBLISH_BTN = ['button:has-text("发布")', 'button:has-text("发布作品")',
                'div[class*="content-confirm"] button', '.publish-btn button', '.button-publish']

_DEBUG_DIR = Path("./data/debug")

# 发布成功信号(文案任一命中即算成功)。
# ⚠️ 只放「语义唯一、只在真发布成功后才出现」的文案。
#    2026-09-12 实测事故:原来的列表里有「发布完成」,而发布页静态 UI 里就带这几个字,
#    于是「点了发布但其实没提交成功」被误判成成功 —— 任务 18 秒就 done、error 为空、
#    result_url 还是发布表单页,而抖音创作平台「作品管理」里根本没有这条作品。
#    同理「已发布」「审核中」是作品管理页的标签文案,也必须排除。
#    真正的强判据是 URL 跳到 /content/manage(抖音发布成功的必然动作),见下方成功判定。
_SUCCESS_KW = ("发布成功", "作品发布成功", "投稿成功")
# 抖音风控人工验证(短信验证码 / 扫码 / 滑块):需用户在弹出窗口里手动完成,不能自动化
_VERIFY_KW = ("接收短信验证码", "短信验证码", "为确保是本人操作", "输入验证码",
              "安全验证", "完成验证", "拖动滑块", "使用原设备扫码", "身份验证")
# 上传/转码中的标志:命中就再等等再点发布(只会让我们等更久,不会误判成功,方向安全)
_UPLOADING_KW = ("上传中", "正在上传", "上传进度", "转码中", "处理中", "视频处理中")
# ★ 2026-09-14 加:平台**明确拒绝**的文案。
#   教训(快手同款):原来这套流程只有「成功判据」没有「失败判据」,平台明明弹了
#   「内容发布失败: …」,我们却一路等到超时、最后报「超时未命中任一判据」,连带把
#   失败写成了成功(done)。挂在页面上的 toast 只活 2~3 秒,所以必须**点击后立刻采样**,
#   而且判据要排在成功判据**前面**。
_FAIL_KW = ("发布失败", "投稿失败", "上传失败", "内容不合规", "发布出错",
            "请等待视频上传完成", "视频上传中", "请先上传", "请上传视频",
            "发布次数已达上限", "今日发布已达", "操作过于频繁", "网络异常",
            "标题不能为空", "内容不能为空")
# 失败文案里属于「上传还没完」的:这类可以等一会儿再补点一次,其余直接判失败。
_UPLOAD_BLOCK_KW = ("请等待视频上传完成", "视频上传中", "请先上传", "请上传视频")
# 发现人工验证弹窗(短信验证码 / 原设备扫码)后额外给的时间:要留够人走到电脑前 + 拿手机收码。
# 实测抖音对「新登录态首次发布」会弹这个框,300s 常常不够人反应过来。
_VERIFY_GRACE_SECONDS = 900


def _log(msg: str) -> None:
    print(f"[dy-publish] {msg}", flush=True)


async def _visible_any(page, keywords) -> str:
    """返回第一个当前可见的关键词文案(无则空串);用于快速轮询,不阻塞等待。"""
    for kw in keywords:
        try:
            if await page.get_by_text(kw, exact=False).first.is_visible():
                return kw
        except Exception:
            continue
    return ""


async def _dump(page, tag: str) -> str:
    """把当前页面截图 + URL/可见文本快照落盘,返回截图路径(供日志/前端提示)。"""
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = _DEBUG_DIR / f"dy_publish_{tag}_{stamp}"
        png = str(base.with_suffix(".png"))
        try:
            await page.screenshot(path=png, full_page=True)
        except Exception:
            png = ""
        try:
            txt = await page.inner_text("body")
        except Exception:
            txt = ""
        base.with_suffix(".txt").write_text(
            f"url: {page.url}\n\n{txt[:4000]}", encoding="utf-8")
        _log(f"已存诊断快照 tag={tag} url={page.url} png={png}")
        return png
    except Exception as e:
        _log(f"存快照失败: {e!r}")
        return ""


async def _click_first(page, selectors, timeout=2500) -> bool:
    for sel in selectors:
        try:
            await page.click(sel, timeout=timeout)
            return True
        except Exception:
            continue
    return False


_JS_CLICK_PUBLISH = r"""
(() => {
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
  // ★ 「暂存」必须排除:抖音发布页有「暂存离开」,它文本里也含「发布」(!),
  //   是除了「发布」按钮外唯一命中 /发布/ 的干扰项;同理排除预览/取消/草稿。
  const bad = /定时|取消|返回|草稿|暂存|预览|再想想|不发布/;
  if (!document.body) return { ok: false, why: "no-body" };
  const cands = Array.from(document.querySelectorAll(
      'button, [role="button"], div[class*="confirm"] button'));
  let hit = [];
  cands.forEach((el) => {
    const t = norm(el.innerText || el.textContent || "");
    if (!t || bad.test(t) || !/发布/.test(t)) return;
    const r = el.getBoundingClientRect();
    if (r.width < 10 || r.height < 10) return;
    hit.push({ el, t, r });
  });
  if (!hit.length) return { ok: false, why: "no-match" };
  // ★ 先收窄到「精确等于发布/发布作品」的那批 —— 比按位置排序更硬。
  const exact = hit.filter((h) => /^(发布|发布作品)$/.test(h.t));
  if (exact.length) hit = exact;
  // 发布按钮在表单最底部:先按 bottom 最大排序,同排取最宽的那个
  hit.sort((a, b) => {
    if (Math.abs(b.r.bottom - a.r.bottom) > 4) return b.r.bottom - a.r.bottom;
    return b.r.width - a.r.width;
  });
  const pick = hit[0];
  try { pick.el.scrollIntoView({ block: "center" }); } catch (e) {}
  pick.el.click();                     // 原生 click:不经命中测试,遮挡拦不住
  return { ok: true, text: pick.t, n: hit.length, exact: exact.length };
})();
"""


async def _js_click_publish(page) -> dict:
    """【第三层兜底】用 JS 原生 ``el.click()`` 点「发布」。

    ★ 2026-09-21 事故(Task #62):封面弹层残留时,``page.click()`` 会被那层透明遮罩
      **吃掉** —— Playwright 的 actionability 检查(是否 receipt events)判它没点到,
      两路点击于是全失败,一条本来能发的作品被判 failed。
      JS 原生 ``el.click()`` 由元素自身派发事件,**不经过命中测试**,遮挡拦不住它。
    ★ 只在本函数内 ``scrollIntoView``,不注入任何持久样式;找不到候选就如实报
      ``ok=False``,绝不"随便挑一个按钮"。
    """
    try:
        return dict(await page.evaluate(_JS_CLICK_PUBLISH) or {})
    except Exception as exc:                       # noqa: BLE001
        return {"ok": False, "why": repr(exc)}


async def _fill_first(page, selectors, text, timeout=3000) -> bool:
    for sel in selectors:
        try:
            el = page.locator(sel).first
            await el.wait_for(state="visible", timeout=timeout)
            await el.click(timeout=timeout)
            try:
                await el.fill(text, timeout=timeout)
            except Exception:
                # contenteditable 富文本 fill 不一定支持,退回键入
                await page.keyboard.type(text)
            _log(f"填入文本用选择器 {sel!r}")
            return True
        except Exception:
            continue
    return False


async def _wait_editor(page, timeout_ms: int) -> bool:
    """等发布表单出现(简介编辑器可见)= 上传/转码完成、已跳到编辑页。"""
    for sel in _DESC_SEL:
        try:
            await page.locator(sel).first.wait_for(state="visible", timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


async def _manage_search(page, probe: str) -> str:
    """把作品管理页的搜索框填上 probe(平台自带搜索能穿透虚拟滚动列表)。返回诊断串。"""
    for sel in ('input[placeholder*="搜索"]', 'input[type="search"]',
                '[class*="search"] input'):
        try:
            box = page.locator(sel).first
            if await box.count() == 0 or not await box.is_visible():
                continue
            await box.click(timeout=3000)
            # ★ 先清空再填:同一关键词重复按 Enter 平台不一定重新发请求,
            #   而核对是靠**轮询**的(作品列表要过几十秒才会出现新作品)。
            try:
                await box.fill("", timeout=2000)
                await page.wait_for_timeout(300)
            except Exception:
                pass
            await box.fill(probe, timeout=3000)
            await box.press("Enter", timeout=3000)
            return f"已用搜索框 {sel!r} 搜「{probe}」"
        except Exception:
            continue
    return ""


async def _manage_longest_text(page) -> str:
    text = ""
    for frame in page.frames:
        try:
            candidate = await frame.inner_text("body")
        except Exception:
            continue
        if len(candidate) > len(text):
            text = candidate
    return " ".join(text.split())


# 抖音「搜索无结果」的空态文案。★ 关键：这句提示**包含搜索词本身**，所以
# 不能拿 `probe in 页面文本` 当"作品已存在"的证据 —— 必须让空态判据优先。
# 正则刻意**不**匹配列表底部的「没有更多了」/「没有更多作品」（那里没有"相关"）。
#
# ★ 2026-09-21 把窗口从 `{0,10}` 放宽到 `{0,40}`：空态的完整文案是
#   「没有找到与"<搜索词>"相关的作品」，中间那段**等于搜索词长度 + 4**。
#   搜索词最长 8 个字符 ⇒ 中间最长 12 字，`{0,10}` 刚好够不着 ⇒ 空态识别不到，
#   而下一行的 `probe in 页面文本` 又必然命中（因为空态里就写着这个词），
#   于是「没发出去」被读成「已存在」。窗口放到 40 之后任何长度的搜索词都覆盖得到，
#   同时仍然避得开列表底部的「没有更多了」（那里没有"相关"）。
_EMPTY_RE = re.compile(r"没有[^。！？\n]{0,40}相关|暂无[^。！？\n]{0,40}作品|未搜索到[^。！？\n]{0,40}作品")


_PROBE_MIN_MS = 40000
"""单个候选搜索词占用的**最短**核对时长(见 ``_verify_on_manage``)。

★ 抽成模块常量是为了**可测** —— 测试把它 monkeypatch 成很小的值,否则一条
  「确实没发出去」的用例要真等 2×40 秒。
"""


def _compact_ws(text: str) -> str:
    """去掉**所有**空白后再比对。

    ★ 2026-09-21 加：抖音标题**允许含空格**（实测 #68 标题 =
      `WiFi 8 开卖：这代不比快比不掉线`），而 ``_manage_longest_text()`` 会把页面
      空白归一成单个空格 ⇒ 拿「去空格版的搜索词」直接 `in` 比对**永远为假**。
    """
    return "".join((text or "").split())


def _probe_candidates(title: str):
    """核对用的搜索词候选（**按优先级**排列）。

    ★ 2026-09-21 加（Task #68 误报 failed 的根因）。
      原来只用「去空格后的前 8 字」：``"".join(title.split())[:8]``。
      抖音标题里可以含空格，而**平台搜索按标题原文匹配** ⇒ 用去空格版
      `WiFi8开卖：` 去搜 `WiFi 8 开卖：…` 只会得到「没有相关作品」，于是
      「发布后核对」判 not found、「发布前查重」也判 not duplicate
      —— 一条真发出去的作品被写成 `failed`（还提示"请到平台复核"）。
      所以现在**先试标题原文前缀**（与平台存储/匹配口径一致），再退到去空格版
      （兜住平台把空格折叠掉的情况）。两个都试，谁先命中用谁。
    """
    text = (title or "").strip()
    if not text:
        return []
    cands = []
    for cand in (text[:8], _compact_ws(text)[:8]):
        if cand and cand not in cands:
            cands.append(cand)
    return cands


async def _verify_on_manage(ctx, title: str, timeout_ms: int = 150000,
                            interval_ms: int = 12000) -> Tuple[bool, str]:
    """打开「作品管理」核对本次作品是否**真的**落库。返回 (found, detail)。

    ★ 2026-09-14 加(起因:任务 3 报 done,而抖音后台压根没有这条作品)。
    ★ 2026-09-14 二次修正:第一版只查一次就下结论,结果**误报失败** ——
      点完发布抖音会立刻跳到 /content/manage?enter_from=publish,但那一瞬间作品列表
      还写着「加载中…」,新作品要过几十秒才出现在列表里。所以这里必须**轮询**:
      命中标题立刻返回;期间看到「没有…相关作品」只记一笔(可能还没落库),
      只有等满 timeout 仍不见标题才判 not found。
    ★ 2026-09-21 三次修正(Task #68 误报 failed):搜索词改用
      :func:`_probe_candidates` 的**多候选**（原文前缀 → 去空格前缀）,
      比对改成**去空白比对**（:func:`_compact_ws`）。原因是标题里的空格:
      抖音按标题原文匹配,去空格的搜索词搜不到带空格的标题。
    """
    probes = _probe_candidates(title)
    if not probes:
        return False, "标题为空,跳过核对"
    page = await ctx.new_page()
    try:
        await page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(6000)
        # 每个候选分到的时间片。下限 40s 是给"列表要过几十秒才刷新"留的余量
        # (单候选时就是完整 timeout,与改动前一致)。
        # ★ 抽成模块常量是为了**可测**:测试把它 monkeypatch 成很小的值,
        #   否则一次 not-found 用例要真等 2×40 秒。
        per_probe_ms = max(_PROBE_MIN_MS, timeout_ms // len(probes))
        notes, rounds_total, saw_empty = [], 0, False
        for probe in probes:
            probe_ws = _compact_ws(probe)
            deadline = asyncio.get_running_loop().time() + per_probe_ms / 1000
            rounds = 0
            while asyncio.get_running_loop().time() < deadline:
                rounds += 1
                rounds_total += 1
                found_note = await _manage_search(page, probe)
                if not found_note:
                    return False, "作品管理页未找到搜索框(无法核对)"
                notes.append(found_note)
                await page.wait_for_timeout(8000)
                compact = await _manage_longest_text(page)
                # ★★★ 必须**先判「空态」、再判「命中」**（2026-09-15 修）。
                #   抖音搜索无结果时页面写的是「没有找到与"<搜索词>"相关的作品」——
                #   **这句提示本身就含 probe** ⇒ 先判 `probe in compact` 会把它读成
                #   「作品管理里已存在同名作品」，于是"发布前查重"把整条发布**跳过**、
                #   还返回 done。实测：微鸭这条被这么跳过，而创作后台根本没有它
                #   （任务表也证明此前从未发过）⇒ 纯假命中。
                #   空态优先后：空态只记 saw_empty，继续轮询；只有列表里真的出现
                #   标题才判命中。正则刻意避开列表底部的「没有更多了」。
                if _EMPTY_RE.search(compact):
                    saw_empty = True
                elif probe_ws and probe_ws in _compact_ws(compact):
                    await _dump(page, "manage-hit")
                    return True, (f"{found_note} → 第 {rounds} 轮命中标题"
                                  f"「{probe}」(按去空白比对)")
                await page.wait_for_timeout(interval_ms)
        tried = " / ".join(dict.fromkeys(notes))
        return False, (f"{tried} → 两个候选共轮询 {rounds_total} 轮 / "
                       f"{timeout_ms // 1000}s 仍未出现标题"
                       + "、".join(f"「{p}」" for p in probes)
                       + ("(平台始终返回「没有相关作品」)" if saw_empty else ""))
    except Exception as exc:
        return False, f"核对异常: {exc!r}"
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def _page_state(page) -> dict:
    """采集一个「与抖音改版无关」的页面状态指纹:可见按钮的文案/可用性 + 短文案集合 + <video> 数量。

    上传 / 转码过程中进度百分比、倒计时会不断变化 → 指纹持续变化;上传完成后页面不再抖动 →
    指纹连续多次采样保持一致。用它判断「视频真的传完了、可以点发布」,比猜抖音文案/选择器稳。
    """
    try:
        return await page.evaluate(
            """() => {
                const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 1 && r.height > 1
                        && s.visibility !== 'hidden' && s.display !== 'none';
                };
                const btns = [...document.querySelectorAll('button')].filter(vis)
                    .map((b) => ((b.innerText || '').trim().slice(0, 12))
                                + (b.disabled ? '\u00b7off' : '\u00b7on'));
                const texts = [...document.querySelectorAll('div,span,p,label')]
                    .filter(vis)
                    .map((e) => (e.innerText || '').trim())
                    .filter((t) => t && t.length <= 24);
                return {
                    btns: btns,
                    texts: [...new Set(texts)].slice(0, 120),
                    videos: document.querySelectorAll('video').length,
                };
            }"""
        )
    except Exception:
        return {}


def _state_sig(state: dict) -> str:
    """把状态指纹压成一个字符串,用于「连续采样是否稳定」的判定。"""
    if not state:
        return ""
    return "|".join(state.get("btns") or []) + "##" \
        + "|".join(state.get("texts") or []) + "##" + str(state.get("videos"))


def _visible_success_hits(state: dict) -> List[str]:
    """当前页面里能命中「成功文案」的词 —— 用于日志溯源(误报时一眼看出是哪个词)。"""
    texts = (state or {}).get("texts") or []
    return [kw for kw in _SUCCESS_KW if any(kw in t for t in texts)]


async def _primary_publish_button(page):
    """挑最终「发布」按钮:文本恰为发布/发布作品、可见、可用;取最后一个(表单底部)。"""
    try:
        btns = page.locator('button')
        n = await btns.count()
    except Exception:
        return None
    cand = None
    for i in range(n):
        b = btns.nth(i)
        try:
            if not await b.is_visible():
                continue
            t = ((await b.inner_text()) or "").strip()
            if t in ("发布", "发布作品", "发布视频", "发布图文"):
                cand = b   # 页面里可能多个,取靠后的(底部提交)
        except Exception:
            continue
    return cand


async def _dump_radios(page) -> None:
    """把页面上疑似单选项/可点标签的真实文案打出来,便于按实际文案校准。"""
    try:
        texts = await page.eval_on_selector_all(
            'label, [role="radio"], .semi-radio, .semi-radio-addon, [class*="radio"]',
            "els => els.map(e => (e.innerText||'').trim()).filter(t => t && t.length <= 12)")
        seen, out = set(), []
        for t in texts:
            if t not in seen:
                seen.add(t); out.append(t)
        _log(f"页面可选项文案候选: {out[:40]}")
    except Exception as e:
        _log(f"枚举单选项失败: {e!r}")


async def _choose_radio(page, label: str) -> bool:
    """点一个单选项。**只走安全精确策略**,绝不 force / 不点任意祖先 ——
    否则可能误点「继续添加/封面」等触发系统选图框的按钮,卡死自动化。"""
    # 1) 无障碍 role=radio(Semi 给单选组件挂 role),用 check() 语义最稳
    try:
        loc = page.get_by_role("radio", name=label, exact=True)
        if await loc.count():
            await loc.first.scroll_into_view_if_needed(timeout=2000)
            try:
                await loc.first.check(timeout=2500)
            except Exception:
                await loc.first.click(timeout=2500)
            _log(f"已选发布设置「{label}」(role)")
            return True
    except Exception:
        pass
    # 2) 仅在 Semi 单选组件内、且整项文本恰等于 label 的元素上点(不碰其它任何东西)
    try:
        radios = page.locator('label.semi-radio, .semi-radio, label[class*="radio"]')
        n = await radios.count()
        for i in range(n):
            r = radios.nth(i)
            try:
                txt = ((await r.inner_text()) or "").strip()
            except Exception:
                continue
            if txt == label:
                await r.scroll_into_view_if_needed(timeout=2000)
                await r.click(timeout=2000)
                _log(f"已选发布设置「{label}」(semi-radio)")
                return True
    except Exception:
        pass
    _log(f"⚠️ 未点中发布设置「{label}」(已安全跳过,不乱点)—— 打印页面实际可选项供校准:")
    await _dump_radios(page)
    return False


async def _apply_publish_settings(page, visibility: str, allow_save: bool) -> None:
    """设置「谁可以看」「保存权限」。公开 / 允许为抖音默认值,非默认才点,减少误点。"""
    vis_label = {"friends": "好友可见", "private": "仅自己可见"}.get(visibility, "")
    if vis_label:                       # public=默认,不动
        await _choose_radio(page, vis_label)
    if not allow_save:                  # 允许=默认,只在「不允许」时点
        await _choose_radio(page, "不允许")


async def publish_douyin(mgr: BrowserManager, identity: Identity,
                         storage_state_json: str, media_type: str, title: str,
                         desc: str, media_paths: List[str], topics: str = "",
                         visibility: str = "public", allow_save: bool = True,
                         headed: bool = True, timeout_seconds: int = 180,
                         cover_path: str = "",
                         cover_required: bool = False,
                         on_submit: Callable[[], None] | None = None,
                         ) -> Tuple[bool, str, str]:
    """发布一条抖音作品。返回 (ok, result_url, error)。
    storage_state_json 仅用于校验(实际登录态在该账号持久 profile 里)。
    visibility: public 公开 | friends 好友可见 | private 仅自己可见;allow_save: 是否允许他人保存。
    cover_path: 竖封面图本地路径(3:4,best-effort);留空则用视频首帧。"""
    files = [str(Path(p)) for p in media_paths if p and Path(p).exists()]
    if not files:
        return False, "", "没有可用的本地媒体文件(路径不存在)"
    tags = [t.strip().lstrip("#") for t in (topics or "").split(",") if t.strip()]
    # 抖音正文 = 简介 + 话题(话题写进正文,发布时自动识别 #)
    body = ((desc or "") + ("\n" + " ".join(f"#{t}" for t in tags) if tags else "")).strip()[:2000]

    # ★ 2026-09-14 改:open_headed 会新开 Chromium 窗口并置顶抢焦点,发布期间反复
    #   顶掉用户正在用的窗口。改用 open_background(有头但最小化、不置顶)。
    ctx = await mgr.open_background(identity)
    page = await ctx.new_page()

    # 保险:媒体上传我们全用 set_input_files(不触发 filechooser),故任何 filechooser
    # 事件都是意外(比如误点了「继续添加/封面」的 <input type=file>),自动取消避免卡死。
    # 注:抖音部分选图用系统级 showOpenFilePicker,此 hook 拦不到 —— 根本对策是别乱点。
    def _fc_guard(fc):
        async def _cancel():
            try:
                await fc.set_files([])
            except Exception:
                pass
        asyncio.ensure_future(_cancel())
    try:
        page.on("filechooser", _fc_guard)
    except Exception:
        pass

    ok, result_url, error = False, "", ""
    try:
        url = IMAGE_URL if media_type == "images" else UPLOAD_URL
        _log(f"打开发布页 {url} (media_type={media_type}, files={len(files)})")
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(3000)
        if "passport" in page.url or "/login" in page.url:
            await _dump(page, "loggedout")
            return False, "", "logged_out:抖音创作平台未登录,请先在账号页点「创作者登录」"

        # ★ 发布前查重:若作品管理里已经有同名作品,说明上一次其实发成功了(只是没被
        #   我们确认到),这里直接返回成功 —— 既避免重复投稿,也把「假失败」纠回来。
        #   和视频号发布器同一套思路(那边在 publish_channels 里做同样的前置核对)。
        if title:
            existed, detail = await _verify_on_manage(ctx, title, timeout_ms=25000,
                                                      interval_ms=8000)
            _log(f"发布前查重: found={existed} {detail}")
            if existed:
                _log("作品管理里已存在同名作品 → 跳过本次上传(防重复投稿)")
                return True, MANAGE_URL, ""
        if media_type == "images":
            await _click_first(page, _TAB_IMAGE, timeout=2000)
            await page.wait_for_timeout(1200)
        try:
            await page.locator('input[type="file"]').first.set_input_files(
                files if media_type == "images" else files[:1], timeout=15000)
            _log("已提交文件,等待上传/转码…")
        except Exception as e:
            await _dump(page, "nofileinput")
            return False, "", f"上传文件失败(未找到文件输入框?): {e!r}"

        # 等表单编辑器出现(= 已跳到编辑页;视频转码慢,给足时间)
        edit_timeout = 120000 if media_type == "video" else 45000
        if not await _wait_editor(page, edit_timeout):
            await _dump(page, "noeditor")
            return False, "", ("上传后未进入编辑页(视频可能仍在转码或上传失败)。"
                               "请在弹出的窗口里查看,或到抖音创作平台重试。")
        _log(f"已进入编辑页 url={page.url}")
        await page.wait_for_timeout(1500)

        if title:
            await _fill_first(page, _TITLE_SEL, title.strip()[:30])
            await page.wait_for_timeout(400)
        if body:
            if not await _fill_first(page, _DESC_SEL, body):
                _log("警告:未能填入简介(选择器可能改版)")
        await page.wait_for_timeout(800)

        # 发布设置:谁可以看 / 保存权限(公开、允许为默认,仅非默认才点)
        await _apply_publish_settings(page, visibility, allow_save)
        await page.wait_for_timeout(600)

        # 等「视频真的传完」再点发布。
        # 原来只等按钮 enabled 就点,而抖音上传中按钮也可能是 enabled 的 —— 点了等于没提交,
        # 随后又被静态文案「发布完成」误判成成功(2026-09-12 事故:18s 假成功,作品管理里没有该作品)。
        # 现在用「上传中标志消失 + 页面状态指纹连续稳定 + 按钮可用 + 至少等满 min_dwell」四重条件,
        # 判据不依赖抖音具体文案/选择器(指纹只是采样,稳定与否才是信号)。
        stable_needed = 4          # 连续 4 次采样(约 8s)不变
        min_dwell_ms = 35000       # ★ 15s→35s:23MB/1080x1920 实测 15s 内传不完,
                                   #   而抖音上传中按钮也可能是 enabled 的,点早了等于没提交。
        max_wait_ms = 300000       # 最多等 300s
        waited_ms, stable, prev_sig = 0, 0, None
        btn = None
        while True:
            state = await _page_state(page)
            sig = _state_sig(state)
            btn = await _primary_publish_button(page)
            enabled = False
            if btn is not None:
                try:
                    enabled = await btn.is_enabled()
                except Exception:
                    enabled = False
            stable = stable + 1 if (sig and sig == prev_sig) else 0
            prev_sig = sig
            hits = _visible_success_hits(state)
            uploading = [kw for kw in _UPLOADING_KW
                         if any(kw in t for t in (state.get("texts") or []))]
            _log(f"发布就绪检查 {waited_ms // 1000}s: 按钮{'可用' if enabled else '未就绪'}"
                 f" 指纹稳定 {stable}/{stable_needed} <video>{state.get('videos')}"
                 f"{' 上传中' + str(uploading) if uploading else ''}"
                 f"{' 命中成功文案' + str(hits) if hits else ''}")
            if (enabled and not uploading and stable >= stable_needed
                    and waited_ms >= min_dwell_ms):
                break
            if waited_ms >= max_wait_ms:
                _log(f"⚠️ 等上传完成超时({max_wait_ms // 1000}s),按当前状态继续尝试发布")
                break
            await page.wait_for_timeout(2000)
            waited_ms += 2000

        # 封面(best-effort):抖音不设封面就是取视频首帧,发布照常成功 ——
        # 所以这里失败只记日志,绝不让一条本来能发的作品失败。
        # ★ 位置:必须等「视频上传/转码就绪」循环跑完(封面区要视频就绪才渲染),
        #   又必须在 btn.click() 之前。
        if cover_path:
            try:
                if cover_required:
                    cover_note = await set_douyin_cover(page, cover_path, strict=True)
                else:
                    cover_note = await set_douyin_cover(page, cover_path)
            except Exception as exc:               # noqa: BLE001
                cover_note = f"封面步骤异常: {exc!r}"
            if cover_note:
                _log(f"警告:封面未设置 —— {cover_note}")
                if cover_required:
                    return False, "", f"必需封面未确认: {cover_note}"
            else:
                _log(f"封面已设置: {cover_path}")
            await page.wait_for_timeout(800)
        elif cover_required:
            return False, "", "必需封面路径为空"

        if btn is None:
            btn = await _primary_publish_button(page)
        if btn is None:
            await _dump(page, "nobtn")
            return False, "", "未找到发布按钮(发布页可能改版)。已存诊断截图到 data/debug/。"
        try:
            await btn.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        if on_submit is not None:
            try:
                on_submit()
            except Exception as exc:
                return False, "", f"发表前写入标记失败: {exc!r}"
        try:
            await btn.click(timeout=5000)
            _log("已点击发布按钮")
        except Exception as exc1:                      # noqa: BLE001
            if on_submit is not None:
                await _dump(page, "click-result-unknown")
                return False, "", f"write_uncertain:首次发表点击结果不明: {exc1!r}"
            # 第 2 层:用文本选择器再点一次
            _log(f"直接点击失败({exc1!r}),退到文本选择器重试")
            clicked = await _click_first(page, _PUBLISH_BTN, timeout=4000)
            if not clicked:
                # 第 3 层(★ 2026-09-21 新增,Task #62 事故):封面弹层若残留,它的透明
                #   遮罩会把点击吃掉。先**留现场**、再收干净弹层、最后用 JS 原生点击
                #   绕过遮挡。三层全废才判失败。
                await _dump(page, "clickfail")
                gone = await close_cover_overlay(page, rounds=2)
                _log(f"点击兜底: 封面弹层已收起={gone},改用 JS 原生点击")
                js = await _js_click_publish(page)
                _log(f"点击兜底: JS 原生点击 -> {js}")
                if not js.get("ok"):
                    return False, "", ("发布按钮点击失败(可能被弹层遮挡/需补封面)。"
                                       "已存诊断截图到 data/debug/。")
                _log(f"已用 JS 原生点击发布按钮(文案={js.get('text')!r})")
            else:
                _log("已用文本选择器点击发布按钮")

        # ★ 点击后立刻抓一次现场。平台拒绝的 toast 只活 2~3 秒,等 300s 超时再抓
        #   什么都看不见(快手就是这么把「话题标签超上限」漏掉的)。
        await page.wait_for_timeout(2500)
        try:
            await _dump(page, "post-click-2s")
        except Exception:
            pass

        # 成功判定 + 风控验证等待:抖音点发布后常弹「短信验证码/扫码」要本人操作,
        # 这时必须把弹出的窗口留给用户手动完成,故轮询等待、给足时间(默认最多 5 分钟)。
        # ★ 判据顺序:失败 → 上传挡回(可补点) → 成功。失败必须排在成功前面。
        ok = False
        ok_reason = ""
        retried = 0
        deadline = max(int(timeout_seconds), 300)   # 秒;留足人工验证时间
        waited, verify_notified = 0, False
        while waited < deadline:
            failure = await _visible_any(page, _FAIL_KW)
            if failure:
                detail = ""
                try:
                    body_text = await page.inner_text("body")
                    for line in body_text.splitlines():
                        if any(word in line for word in _FAIL_KW):
                            detail = " ".join(line.split())[:160]
                            break
                except Exception:
                    pass
                if (failure in _UPLOAD_BLOCK_KW and retried == 0):
                    # 上传还没完 → 等上传态消失后补点一次,不算真失败
                    retried = 1
                    _log(f"平台挡回「{detail or failure}」→ 等上传完成后补点一次")
                    for _ in range(90):
                        state = await _page_state(page)
                        if not [kw for kw in _UPLOADING_KW
                                if any(kw in t for t in (state.get("texts") or []))]:
                            break
                        await page.wait_for_timeout(2000)
                    await page.wait_for_timeout(3000)
                    try:
                        await btn.click(timeout=5000)
                        _log("已补点发布按钮")
                    except Exception as exc:
                        _log(f"补点失败: {exc!r}")
                    waited += 2
                    continue
                error = f"抖音拒绝发布: {detail or failure}"
                _log(f"平台明确报错 → {error}")
                await _dump(page, "platform-rejected")
                break
            # ★ 先看成功文案再看 URL:抖音确认发布时先弹「发布成功」(过几秒就没了),
            #   把它当依据比只记"URL 跳了"更有说服力。
            hit = await _visible_any(page, _SUCCESS_KW)
            if hit:
                ok = True
                ok_reason = f"命中成功文案「{hit}」"
                _log(ok_reason)
                break
            if "/content/manage" in page.url:
                ok = True
                ok_reason = "URL 已跳到作品管理页"
                break
            vkw = await _visible_any(page, _VERIFY_KW)
            if vkw and not verify_notified:
                verify_notified = True
                await _dump(page, "verify")
                # 人工验证需要人真的过来操作,常规窗口(300s)不够 —— 一旦发现验证弹窗,
                # 单独把这个窗口放宽,不影响正常失败路径的反馈速度。
                deadline = max(deadline, waited + _VERIFY_GRACE_SECONDS)
                _log(f"⚠️ 抖音要求人工验证「{vkw}」—— 请在弹出的浏览器窗口里完成"
                     f"(输入短信验证码 / 原设备扫码),完成后本流程会自动继续,"
                     f"最多再等 {_VERIFY_GRACE_SECONDS}s")
            await page.wait_for_timeout(2000)
            waited += 2
        _log(f"启发式判定: ok={ok} 依据={ok_reason or '(超时未命中任一判据)'} 用时={waited}s")

        # ★ 权威核对:无论如何都去作品管理页搜一次标题。
        #   启发式"成功"可以被降级(URL 跳转并不等于作品真的落库 —— 2026-09-14 任务 3
        #   就是这样:URL 跳到了 content/manage,后台却搜不到这条作品);
        #   启发式"失败"也可以被升级(抖音刚发布的视频可能还在审核中)。
        if not error:
            # After the publish click, Douyin can leave the editor while the
            # browser is still uploading the video in the background.  The
            # previous 150 s verification window closed the browser at 19%
            # for a 71 MB video, preventing the upload from ever finishing.
            # Keep the context alive until the work appears in Content Manage.
            verify_timeout_ms = 600000 if media_type == "video" else 150000
            found, detail = await _verify_on_manage(
                ctx, title, timeout_ms=verify_timeout_ms, interval_ms=10000)
            _log(f"平台核对: found={found} {detail}")
            if found and not ok:
                ok = True
                ok_reason = f"平台核对通过({detail})"
            elif not found and ok:
                ok = False
                _log(f"启发式成功依据「{ok_reason}」被平台核对推翻")
                ok_reason = ""
                error = (f"启发式判据判成功,但打开「作品管理」轮询核对未发现本次作品"
                         f"({detail});按未发出处理,不计入配额,请到平台复核。")
            elif not found and not ok:
                png = await _dump(page, "unconfirmed")
                error = ("已点击发布但平台未确认:作品管理页搜索不到本次作品"
                         f"({detail})。诊断截图: {png or 'data/debug'}")
        _log(f"最终判定: ok={ok} 依据={ok_reason or error or '(无)'}")
        if ok:
            result_url = result_url or MANAGE_URL
            _log(f"发布成功 url={result_url}")
        elif not error:
            if verify_notified:
                error = ("发布被抖音风控拦下,需人工验证(短信验证码/扫码),但在等待时间内未完成。"
                         "请在弹窗里完成验证后重试;若窗口已关,重新点「立即发布」再操作。")
            else:
                png = await _dump(page, "unconfirmed")
                error = ("已点发布但未在页面确认到成功信号,且作品管理页也搜不到本次作品。"
                         "请到抖音创作平台「作品管理」复核;若确实没发出去,把 data/debug 里最新一张 "
                         f"dy_publish_unconfirmed_*.png {'('+png+') ' if png else ''}发我校准选择器。")
    except Exception as e:
        try:
            await _dump(page, "exception")
        except Exception:
            pass
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
