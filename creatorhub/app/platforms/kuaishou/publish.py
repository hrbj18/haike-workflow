"""快手创作者服务平台浏览器发布。

当前快手把视频、图文、全景视频合并到了同一个 ``/article/publish/video``
页面；图文不再支持旧的 ``/article/publish/atlas`` 直达地址，需要先进入统一
发布页，再点击「上传图文」标签。上传入口还要求通过真实 file chooser 触发，
直接给旧页面上的第一个 file input 塞图片会命中隐藏的视频 input。
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Tuple
from urllib.parse import urlparse

from ...browser.identity import Identity
from ...browser.manager import BrowserManager
from .cover import set_kuaishou_cover

PUBLISH_URL = "https://cp.kuaishou.com/article/publish/video"
MANAGE_URL = "https://cp.kuaishou.com/article/manage/video"
VIDEO_URL = PUBLISH_URL
IMAGE_URL = PUBLISH_URL

_IMAGE_TAB = (
    '[role="tab"]:has-text("上传图文")',
    '.ant-tabs-tab:has-text("上传图文")',
    'text=上传图文',
)
_DESC_SEL = (
    '#work-description-edit',
    'div[contenteditable="true"][placeholder*="描述"]',
    'div[contenteditable="true"]',
    'textarea[placeholder*="描述"]',
    'textarea',
)
_SUCCESS_KW = ("发布成功", "作品发布成功", "投稿成功", "提交成功", "审核中")
_VERIFY_KW = ("安全验证", "扫码验证", "短信验证", "验证码", "拖动滑块", "身份验证")
# 平台在上传未完成时点「发布」会弹的提示。命中它 = 这次点击被平台拒绝，
# 绝不能当成成功（2026-09-14 误报成功的直接现场证据）。
_UPLOAD_GATE_KW = ("请在视频上传完成后再点击发布", "上传完成后再点击发布",
                   "视频上传完成后")
# 上传态文案；出现即表示还没传完。
_UPLOADING_KW = ("上传中", "正在上传", "上传视频中", "转码中", "处理中")
# ★ 2026-09-14 加:平台**拒绝**发布时的文案。原来只写了成功判据(_SUCCESS_KW),
#   没有任何失败判据 —— 于是「内容发布失败: 话题标签数量超过上限：4」这种明确
#   报错被当成「超时未命中任一判据」,排查了两轮才在快照里看到。
_FAIL_KW = ("内容发布失败", "发布失败", "提交失败", "发布出错", "内容不合规")
# ★ 快手话题标签上限。平台原文:「内容发布失败: 话题标签数量超过上限：4」——
#   给 6 个标签会**整条拒绝发布**,而且失败是静默的(只弹一个 toast)。
_MAX_TOPICS = 4
_DEBUG_DIR = Path("./data/debug")


def _log(message: str) -> None:
    print(f"[ks-publish] {message}", flush=True)


def _published_work_url(payload) -> str:
    """从发布成功回包中提取公开作品地址；字段缺失时由调用方回退管理页。"""
    if isinstance(payload, dict):
        for key in ("photoId", "photo_id", "photoIdStr", "photoID",
                    "workId", "work_id"):
            value = str(payload.get(key) or "").strip()
            if (not value.isdigit()
                    and re.fullmatch(r"[0-9A-Za-z_-]{8,}", value)):
                return f"https://www.kuaishou.com/short-video/{value}"
        for value in payload.values():
            found = _published_work_url(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _published_work_url(value)
            if found:
                return found
    return ""


async def _dump(page, tag: str) -> str:
    """保存当前发布页截图和文本，选择器再次改版时可直接定位。"""
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = _DEBUG_DIR / f"ks_publish_{tag}_{stamp}"
        png = str(base.with_suffix(".png"))
        try:
            await page.screenshot(path=png, full_page=True)
        except Exception:
            png = ""
        try:
            text = await page.locator("body").inner_text()
        except Exception:
            text = ""
        base.with_suffix(".txt").write_text(
            f"url: {page.url}\n\n{text[:6000]}", encoding="utf-8")
        return png
    except Exception as exc:
        _log(f"保存诊断快照失败: {exc!r}")
        return ""


def _title_probe(title: str) -> str:
    """取标题前 8 个非空白字符作为核对指纹。"""
    return "".join(str(title or "").split())[:8]


async def _verify_on_manage(ctx, title: str, timeout_ms: int = 90000
                            ) -> Tuple[bool, str]:
    """另开一页打开「视频管理」,确认本次作品究竟有没有提交成功。

    ★ 2026-09-14 加 —— 这是本次最大的一个认识修正:快手的「三路成功判据」
      (发布接口回包 / URL 跳管理页 / 页面成功文案)**只能证有、不能证无**。
      实测同一天出现过两种相反情况:
        (a) 回包说 result=1,平台「视频管理」里根本没有这条 → 假成功;
        (b) 三路一条都没命中,平台其实也没发 → 真失败(这次就是)。
      唯一可信的判据是创作平台自己的作品列表。所以发布动作结束后主动去核对:
      既能把假成功**降级**,也能把假失败**恢复成成功**,不再依赖启发式。
      核对走两条路:作品列表接口的 JSON 响应 + 管理页 DOM 文本。
    """
    probe = _title_probe(title)
    if not probe:
        return False, "无标题可比对"
    page = await ctx.new_page()
    hits: List[str] = []
    dom_hit = False

    async def on_response(response):
        try:
            if response.request.method not in ("GET", "POST"):
                return
            if "/rest/cp/" not in response.url:
                return
            if "json" not in (response.headers.get("content-type") or ""):
                return
            raw = await response.text()
            try:
                # 中文在响应里可能是 \uXXXX 转义,先解回可读文本再比对
                decoded = json.dumps(json.loads(raw), ensure_ascii=False)
            except Exception:
                decoded = raw
            if probe in decoded:
                hits.append(response.url)
        except Exception:
            return

    page.on("response", on_response)
    try:
        await page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=40000)
        waited = 0
        while waited * 1500 < timeout_ms:
            if hits:
                break
            try:
                text = await page.inner_text("body")
                if probe in text or probe in "".join(text.split()):
                    dom_hit = True
                    break
            except Exception:
                pass
            await page.wait_for_timeout(1500)
            waited += 1
        if hits:
            return True, f"作品列表接口命中标题「{probe}」({len(hits)} 个响应)"
        if dom_hit:
            return True, f"视频管理页 DOM 命中标题「{probe}」"
        return False, f"视频管理页列表中未出现本次标题「{probe}」"
    except Exception as exc:
        return False, f"核对失败: {exc!r}"
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def _click_first_visible(page, selectors, timeout=3000) -> bool:
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for index in range(await loc.count()):
                candidate = loc.nth(index)
                if not await candidate.is_visible():
                    continue
                await candidate.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


async def _dismiss_overlays(page, rounds: int = 3) -> None:
    """best-effort 关掉快手新版发布页的新手引导 / 弹窗。

    ★ 2026-09-14 踩坑:新版发布页会弹「1/4 作品信息」分步引导,它带全屏透明遮罩。
      Playwright 的 ``click()`` 除了 visible/enabled 还要求「能收到事件」,被遮罩挡住
      就必然重试到超时 —— 于是 5 个描述框选择器全挂(报「未找到作品描述输入框」),
      而上传其实早已成功、描述框就在页面上。这里只点语义明确的引导按钮,绝不 force、
      绝不点任意祖先。
    """
    buttons = (
        'button:has-text("我知道了")', 'button:has-text("知道了")',
        'button:has-text("跳过")', 'button:has-text("跳过引导")',
        'button:has-text("下一步")',
        '[class*="guide"] [class*="close"]', '[class*="guide"] [class*="skip"]',
    )
    for _ in range(rounds):
        changed = False
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        for selector in buttons:
            try:
                loc = page.locator(selector)
                for index in range(min(await loc.count(), 3)):
                    candidate = loc.nth(index)
                    if await candidate.is_visible():
                        await candidate.click(timeout=1500)
                        _log(f"已关闭引导弹层(选择器 {selector!r})")
                        changed = True
                        break
                if changed:
                    break
            except Exception:
                continue
        if not changed:
            break
        await page.wait_for_timeout(600)


async def _editor_text(editor) -> str:
    try:
        value = await editor.evaluate(
            "el => (el.value ?? el.innerText ?? el.textContent ?? '')")
    except Exception:
        return ""
    return "".join(str(value).split())


async def _fill_first(page, selectors, text, timeout=4000) -> bool:
    """把作品描述写进编辑器,并**读回确认真的写进去了**才算成功。

    ★ 2026-09-14 重写:原来用 ``locator(sel).first`` + ``click()`` + ``fill()``。
      两个问题:(1) ``.first`` 可能是页面上某个不可见的同名元素;
      (2) ``click()`` 会被引导弹窗的透明遮罩拦死。
      现在遍历每个选择器的前若干匹配项,挑「可见」的那个,用 ``focus()``(不做命中测试)
      + ``keyboard.insert_text()`` 写入;写不进才退回 click + fill。
      ``_editor_has_text`` 用「去空白后的前 12 字」做包含判据,既能容忍编辑器把换行
      规范化,又能识别出「一个字都没写进去」。
    """
    await _dismiss_overlays(page)
    need = "".join(str(text).split())[:12]
    for selector in selectors:
        try:
            loc = page.locator(selector)
            count = await loc.count()
        except Exception:
            continue
        for index in range(min(count, 4)):
            editor = loc.nth(index)
            try:
                if not await editor.is_visible():
                    continue
            except Exception:
                continue
            try:
                await editor.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
            # 路径一:focus + insert_text(遮罩拦不住,富文本编辑器也能收到 input 事件)
            try:
                await editor.focus(timeout=2000)
                modifier = "Meta" if sys.platform == "darwin" else "Control"
                await page.keyboard.press(f"{modifier}+A")
                await page.keyboard.press("Backspace")
                await page.keyboard.insert_text(str(text))
                await page.wait_for_timeout(300)
                if not need or need in await _editor_text(editor):
                    _log(f"已写入作品描述(选择器 {selector!r} 第 {index} 项,"
                         f"{len(str(text))} 字)")
                    return True
            except Exception as exc:
                _log(f"focus 写入失败 {selector!r}#{index}: {exc!r}")
            # 路径二:老路 click + fill
            try:
                await editor.click(timeout=timeout)
                try:
                    await editor.fill(text, timeout=timeout)
                except Exception:
                    await page.keyboard.press("Control+A")
                    await page.keyboard.type(text, delay=15)
                await page.wait_for_timeout(300)
                if not need or need in await _editor_text(editor):
                    _log(f"已写入作品描述(click+fill,选择器 {selector!r} 第 {index} 项)")
                    return True
            except Exception:
                continue
        _log(f"选择器 {selector!r} 未能写入描述")
    return False


async def _visible_text(page, keywords) -> str:
    for keyword in keywords:
        try:
            loc = page.get_by_text(keyword, exact=False)
            for index in range(await loc.count()):
                if await loc.nth(index).is_visible():
                    return keyword
        except Exception:
            continue
    return ""


async def _upload_files(page, media_type: str, files: List[str]) -> bool:
    """优先通过上传按钮的 file chooser 选择文件；CSS input 只作兜底。"""
    label = "上传图片" if media_type == "images" else "上传视频"
    want = files if media_type == "images" else files[:1]
    try:
        async with page.expect_file_chooser(timeout=8000) as chooser_info:
            button = page.get_by_role("button", name=label, exact=True)
            clicked = False
            for index in range(await button.count()):
                candidate = button.nth(index)
                if await candidate.is_visible():
                    await candidate.click(timeout=4000)
                    clicked = True
                    break
            if not clicked:
                raise RuntimeError(f"未找到“{label}”按钮")
        chooser = await chooser_info.value
        await chooser.set_files(want)
        return True
    except Exception as chooser_error:
        _log(f"file chooser 上传未命中，尝试 input 兜底: {chooser_error!r}")

    selector = ('input[type="file"][accept*="image"]'
                if media_type == "images"
                else 'input[type="file"][accept*="video"]')
    try:
        target = page.locator(selector).first
        await target.set_input_files(want, timeout=15000)
        return True
    except Exception:
        return False


async def _wait_editor(page, timeout_ms: int) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    while asyncio.get_running_loop().time() < deadline:
        for selector in _DESC_SEL:
            try:
                loc = page.locator(selector).first
                if await loc.count() and await loc.is_visible():
                    return True
            except Exception:
                continue
        await page.wait_for_timeout(500)
    return False


async def _wait_upload_done(page, timeout_ms: int = 900000,
                            quiet_rounds: int = 4) -> bool:
    """等到「视频上传/转码完成」再允许点发布。

    ★ 2026-09-14 踩坑(这是快手误报成功的另一半真因):上一版在描述写完、
      ``_primary_publish_button`` 一找到可点控件就立刻点「发布」——而那一刻页面
      还写着「73% 上传中」,平台于是弹出「请在视频上传完成后再点击发布」把这次
      提交挡了回去。表单看着填好了、按钮也可点,唯独视频还没落地。
      判据取「连续 quiet_rounds 轮(约 6s)页面里都看不到上传态文案」,避免上传
      进度文案在两次轮询之间短暂消失造成的误判。百分比只在出现上传态时读取,
      以免把「检测中99%」(创作助手的流量建议检测)错当成上传进度。
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_ms / 1000
    quiet = 0
    last_pct = ""
    while loop.time() < deadline:
        try:
            text = await page.locator("body").inner_text()
        except Exception:
            text = ""
        uploading = any(word in text for word in _UPLOADING_KW)
        if uploading:
            quiet = 0
            found = re.search(r"(\d{1,3})\s*%", text)
            pct = found.group(1) if found else ""
            if pct and pct != last_pct and pct.endswith("0"):
                _log(f"视频上传中 {pct}%")
                last_pct = pct
        else:
            quiet += 1
            if quiet >= quiet_rounds:
                _log("视频上传已就绪(页面不再显示上传态)")
                return True
        await page.wait_for_timeout(1500)
    _log("等待视频上传完成超时")
    return False


async def _primary_publish_button(page):
    """新版提交控件是 div.button-primary，不是 button。只取精确“发布”。"""
    selectors = (
        'div[class*="button-primary"]',
        '[role="button"]',
        'button',
        'div[class*="publish"]',
    )
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for index in range(await loc.count() - 1, -1, -1):
                candidate = loc.nth(index)
                if not await candidate.is_visible():
                    continue
                if ((await candidate.inner_text()) or "").strip() != "发布":
                    continue
                aria_disabled = await candidate.get_attribute("aria-disabled")
                classes = str(await candidate.get_attribute("class") or "").lower()
                if aria_disabled == "true" or "disabled" in classes:
                    continue
                try:
                    if not await candidate.is_enabled():
                        continue
                except Exception:
                    pass
                return candidate
        except Exception:
            continue
    return None


async def _choose_visibility(page, visibility: str) -> None:
    label = {
        "public": "所有人可见",
        "friends": "好友可见",
        "private": "仅自己可见",
    }.get(visibility, "所有人可见")
    if visibility == "public":
        return  # 当前默认即所有人可见，少一次点击更稳。
    try:
        choices = page.get_by_text(label, exact=True)
        for index in range(await choices.count() - 1, -1, -1):
            choice = choices.nth(index)
            if await choice.is_visible():
                await choice.click(timeout=2500)
                return
    except Exception:
        _log(f"未能设置查看权限“{label}”，继续使用页面当前值")


async def publish_kuaishou(mgr: BrowserManager, identity: Identity,
                           storage_state_json: str, media_type: str, title: str,
                           desc: str, media_paths: List[str], topics: str = "",
                           headed: bool = True, timeout_seconds: int = 180,
                           visibility: str = "public", allow_save: bool = True,
                           cover_path: str = "",
                           cover_required: bool = False,
                           on_submit: Callable[[], None] | None = None,
                           ) -> Tuple[bool, str, str]:
    """发布一条快手作品，返回 ``(ok, result_url, error)``。"""
    files = [str(Path(path).resolve()) for path in media_paths
             if path and Path(path).exists()]
    if not files:
        return False, "", "没有可用的本地媒体文件(路径不存在)"
    tags = [tag.strip().lstrip("#") for tag in (topics or "").split(",")
            if tag.strip()]
    # ★ 超过上限要**主动截断**,否则平台会把整条作品判为发布失败(见 _MAX_TOPICS)。
    if len(tags) > _MAX_TOPICS:
        _log(f"话题标签 {len(tags)} 个超过快手上限 {_MAX_TOPICS},截断为: "
             f"{'/'.join(tags[:_MAX_TOPICS])}")
        tags = tags[:_MAX_TOPICS]
    body = ((title + "\n" if title else "") + (desc or "")
            + ("\n" + " ".join(f"#{tag}" for tag in tags) if tags else ""))
    # 当前发布页明确显示 0/500。
    body = body.strip()[:500]

    # ★ 2026-09-14 改:原来用 open_headed —— 每次发布都新开一个 Chromium 窗口并
    #   主动置顶抢焦点,一条视频要跑两三分钟,用户在工作时被反复顶窗。改用
    #   open_background:仍有头(写操作风控更稳),但窗口最小化且绝不置顶。
    ctx = await mgr.open_background(identity)
    page = await ctx.new_page()
    ok, result_url, error = False, "", ""
    # armed: 只有**点了「发布」之后**收到的回包才算发布结果。
    # ★ 2026-09-14 踩坑:监听器原来在 page.goto 之前就挂上,于是发布页加载期间
    #   任何一次 /rest/cp/works/*/publish* 的 POST(表单校验之类)只要 result=1,
    #   就在「点击后 0s」把 ok 置真 —— 实测报 done 时页面 url 还是
    #   /article/publish/video、视频还在 73% 上传中,平台从未收到这次提交。
    publish_response = {"armed": False, "seen": False, "ok": False,
                        "message": "", "url": "", "posts": 0, "retried": 0}

    async def on_response(response):
        if (not publish_response["armed"]
                or response.request.method != "POST"):
            return
        path = urlparse(response.url).path.lower()
        # 计数用:**点击后平台到底有没有收到过任何 /rest/cp/ 的 POST**。
        # 这决定了「补一次点击」是否安全 —— 一个 POST 都没有 = 这次点击根本没生效。
        if "/rest/cp/" in path:
            publish_response["posts"] += 1
        if publish_response["seen"]:
            return
        if "/rest/cp/works/" not in path or "/publish" not in path:
            return
        if any(word in path for word in ("config", "snapshot", "tips")):
            return
        try:
            payload = await response.json()
        except Exception:
            return
        publish_response["seen"] = True
        publish_response["ok"] = payload.get("result") in (1, "1")
        publish_response["message"] = str(
            payload.get("message") or payload.get("error_msg")
            or payload.get("errorMsg") or "")
        if publish_response["ok"]:
            publish_response["url"] = _published_work_url(payload)

    page.on("response", on_response)
    try:
        _log(f"打开统一发布页 media_type={media_type}, files={len(files)}")
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(3500)
        body_text = ""
        try:
            body_text = await page.locator("body").inner_text()
        except Exception:
            pass
        if ("passport" in page.url or "/login" in page.url
                or "立即登录" in body_text):
            await _dump(page, "loggedout")
            return False, "", "logged_out:快手创作平台未登录"

        if media_type == "images":
            if not await _click_first_visible(page, _IMAGE_TAB, timeout=3500):
                await _dump(page, "no-image-tab")
                return False, "", "未找到“上传图文”标签(发布页可能改版)"
            await page.wait_for_timeout(700)

        if not await _upload_files(page, media_type, files):
            await _dump(page, "upload-failed")
            return False, "", "上传文件失败:未找到可用的快手上传入口"

        editor_timeout = 120000 if media_type == "video" else 45000
        if not await _wait_editor(page, editor_timeout):
            await _dump(page, "no-editor")
            return False, "", ("文件已选择，但上传后未进入编辑页。请查看弹出的快手窗口，"
                                  "确认文件格式、尺寸或转码状态")

        if body and not await _fill_first(page, _DESC_SEL, body):
            await _dump(page, "no-editor-fill")
            return False, "", "已上传媒体，但未找到作品描述输入框"
        await _choose_visibility(page, visibility)
        # 当前快手图文页未提供稳定的“允许下载”控件；保留参数兼容队列模型。
        _ = allow_save
        await page.wait_for_timeout(700)

        # ★ 2026-09-14 修:表单填好 != 视频传完。实测在「73% 上传中」时点发布,
        #   平台弹「请在视频上传完成后再点击发布」挡回,却因回包提前置真而报 done。
        if media_type == "video":
            if not await _wait_upload_done(page):
                png = await _dump(page, "upload-timeout")
                return False, "", ("等待视频上传完成超时,主动放弃点击发布以免误报成功。"
                                   f"诊断快照: {png or 'data/debug'}")
            await _dismiss_overlays(page)
            await page.wait_for_timeout(800)

        # 封面(best-effort):快手不设封面就是取视频首帧,发布照常成功 ——
        # 所以这里失败只记日志,绝不让一条本来能发的作品失败。
        # ★ 位置:必须在「视频上传/转码就绪」之后(封面区要视频就绪才渲染),
        #   又必须在点击「发布」之前;而封面弹层残留会**吃掉「发布」的点击**,
        #   故 set_kuaishou_cover 内部会显式确认弹层收起(最多 3 轮)。
        if cover_path:
            try:
                cover_note = await set_kuaishou_cover(page, cover_path)
            except Exception as exc:               # noqa: BLE001
                cover_note = f"封面步骤异常: {exc!r}"
            if cover_note:
                _log(f"警告:封面未设置 —— {cover_note}")
                if cover_required:
                    return False, "", f"必需封面未确认: {cover_note}"
            else:
                _log(f"封面已设置: {cover_path}")
        elif cover_required:
            return False, "", "必需封面路径为空"

        button = None
        for _index in range(90):
            button = await _primary_publish_button(page)
            if button is not None:
                break
            await page.wait_for_timeout(1000)
        if button is None:
            await _dump(page, "no-publish-button")
            return False, "", "未找到可用的“发布”按钮(已保存 data/debug 诊断快照)"
        await button.scroll_into_view_if_needed(timeout=3000)
        # 从这一刻起才接受发布回包(见 on_response 的 armed 注释)。
        publish_response["armed"] = True
        # ★ 2026-09-14 加取证:实测出现过「点了发布、Playwright 认为点中、平台毫无反应」
        #   —— 必须看清到底点的是哪个元素、落在哪个坐标,否则无从定位。
        try:
            box = await button.bounding_box()
            html = await button.evaluate("el => el.outerHTML")
            _log(f"发布按钮 box={box} html={str(html)[:200]!r}")
        except Exception as exc:
            _log(f"发布按钮取证失败: {exc!r}")
        if on_submit is not None:
            try:
                on_submit()
            except Exception as exc:
                return False, "", f"发表前写入标记失败: {exc!r}"
        try:
            await button.click(timeout=5000)
        except Exception as exc:
            if on_submit is not None:
                await _dump(page, "click-result-unknown")
                return False, "", f"write_uncertain:首次发表点击结果不明: {exc!r}"
            # 引导/弹窗遮罩会把首次点击吃掉:关掉弹层后再试一次,仍失败才算失败。
            _log(f"首次点击发布失败({exc!r}),关闭弹层后重试")
            await _dismiss_overlays(page)
            button = await _primary_publish_button(page)
            if button is None:
                await _dump(page, "no-publish-button-retry")
                return False, "", "关闭弹层后仍未找到“发布”按钮"
            await button.scroll_into_view_if_needed(timeout=3000)
            await button.click(timeout=5000)
        _log("已点击发布，等待平台确认")
        # ★ 2026-09-14 加:点击后**立刻**落一张快照。上一轮只在 60s 判据超时后才截图,
        #   而那时弹层可能已被平台自己收掉,导致「点了没反应」无现场可看。
        await page.wait_for_timeout(2500)
        try:
            await _dump(page, "post-click-2s")
        except Exception:
            pass

        waited = 0
        ok_reason = ""
        regated = 0
        # 启发式判据只在「有没有更快的成功信号」上有用,真正的裁决交给后面的平台核对
        # (__verify_on_manage),所以这里不必等满 180s —— 省下的时间给核对用。
        while waited < min(max(int(timeout_seconds), 180), 60):
            url_lower = page.url.lower()
            # ★ 2026-09-14 加,放在循环最前面:失败 toast 会自己消失,必须优先抓。
            #   原来只写成功判据不写失败判据,平台明确报的
            #   「内容发布失败: 话题标签数量超过上限：4」被当成「超时未命中任一判据」,
            #   白跑两轮、还差点被判成平台风控。
            failure = await _visible_text(page, _FAIL_KW)
            if failure:
                detail = ""
                try:
                    text = await page.locator("body").inner_text()
                    for line in text.splitlines():
                        if any(word in line for word in _FAIL_KW):
                            detail = " ".join(line.split())[:160]
                            break
                except Exception:
                    pass
                error = f"快手拒绝发布: {detail or failure}"
                _log(f"平台明确报错 → {error}")
                await _dump(page, "platform-rejected")
                break
            gate = await _visible_text(page, _UPLOAD_GATE_KW)
            if gate and regated < 1:
                # 兜底自愈:万一上传态判据被绕过(平台改文案/进度条未见),平台会用
                # 「请在视频上传完成后再点击发布」明确否决这次提交。此时把可能已置真
                # 的回包作废,补等上传完成后再点一次(**只补一次**,避免重复投稿)。
                regated += 1
                _log(f"平台拒绝提前发布(命中「{gate}」),作废本轮回包并补等上传完成")
                publish_response.update(seen=False, ok=False, message="", url="")
                if await _wait_upload_done(page, timeout_ms=600000):
                    publish_response["armed"] = True
                    retry_btn = await _primary_publish_button(page)
                    if retry_btn is not None:
                        await retry_btn.scroll_into_view_if_needed(timeout=3000)
                        await retry_btn.click(timeout=5000)
                        _log("上传完成后已重新点击发布")
                waited = 0
                continue
            if publish_response["seen"]:
                if publish_response["ok"]:
                    ok = True
                    ok_reason = f"发布接口回包 result=1 (page.url={page.url})"
                    break
                error = ("快手拒绝发布:"
                         + (publish_response["message"] or "未知原因"))
                break
            # ★ 2026-09-14:点击后 20s 内平台**一个 /rest/cp/ POST 都没收到** ——
            #   说明这次 locator 点击根本没触发提交(Playwright 认为点中了,页面
            #   却零反应,实测已复现两次)。此时补一次**坐标点击**是安全的:
            #   两个点击之间平台零请求,不可能造成重复投稿。反过来,只要已经收到过
            #   任何 POST(提交确实发出去了),就绝不补点。
            if (waited == 20 and publish_response["retried"] == 0
                    and publish_response["posts"] == 0):
                publish_response["retried"] = 1
                _log("点击后 20s 平台零 POST → 判定点击未生效,补一次坐标点击")
                try:
                    box = await button.bounding_box()
                except Exception:
                    box = None
                if box:
                    cx, cy = (box["x"] + box["width"] / 2,
                              box["y"] + box["height"] / 2)
                    await page.mouse.click(cx, cy)
                    _log(f"坐标点击完成 ({cx:.0f},{cy:.0f})")
                    await page.wait_for_timeout(2000)
                    await _dump(page, "retried-mouse-click")
                    continue
            if any(part in url_lower for part in (
                    "/article/manage", "/content/manage", "/article/list")):
                ok = True
                ok_reason = f"URL 落到管理页 (page.url={page.url})"
                break
            success = await _visible_text(page, _SUCCESS_KW)
            if success:
                ok = True
                ok_reason = f"页面命中成功文案「{success}」"
                break
            verification = await _visible_text(page, _VERIFY_KW)
            if verification:
                _log(f"等待用户在可见窗口完成“{verification}”")
            await page.wait_for_timeout(1000)
            waited += 1
        _log(f"启发式判定: ok={ok} 依据={ok_reason or '(超时未命中任一判据)'} "
             f"用时={waited}s")
        if ok:
            await _dump(page, "declared-ok")

        # ★★ 用创作平台的作品列表做最终裁决(__verify_on_manage 的 docstring 有完整
        #    理由):三路启发式判据只能证有、不能证无。核对不上就把「成功」降级,
        #    核对上了就把「失败」升级 —— 不再让启发式决定一条作品的成功与否。
        if not error:
            found, detail = await _verify_on_manage(ctx, title)
            _log(f"平台核对: found={found} {detail}")
            if found and not ok:
                ok = True
                ok_reason = f"平台核对通过({detail})"
            elif not found and ok:
                _log("⚠️ 启发式判成功但平台核对未通过 → 降级为未确认")
                ok = False
                error = (f"启发式判据判成功({ok_reason}),但打开「视频管理」核对未发现本次"
                         f"作品({detail});按未确认处理,不计入配额,请到平台复核。")
            elif not found and not ok:
                png = await _dump(page, "unconfirmed")
                error = ("已点击发布但平台未收到:打开「视频管理」核对未发现本次作品"
                         f"({detail})。诊断截图: {png or 'data/debug'}")

        _log(f"最终判定: ok={ok} 依据={ok_reason or error or '(无)'}")

        if ok:
            # 发布回包有 photoId 时直达作品；否则打开作品管理页。不能保存当前
            # /article/publish/video，否则“查看”只会重新回到上传页。
            current_url = str(page.url or "")
            current_path = urlparse(current_url).path.lower()
            if "/short-video/" in current_path or any(part in current_path for part in (
                    "/article/manage", "/content/manage", "/article/list")):
                result_url = current_url
            else:
                result_url = publish_response["url"] or MANAGE_URL
    except Exception as exc:
        try:
            await _dump(page, "exception")
        except Exception:
            pass
        error = f"发布异常: {exc!r}"
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
