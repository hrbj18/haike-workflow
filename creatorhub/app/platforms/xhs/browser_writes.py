"""Visible, page-native Xiaohongshu writes with explicit ambiguity semantics."""
from __future__ import annotations

import inspect
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Sequence
from urllib.parse import urlencode, urlsplit

from ...browser.identity import Identity
from ...browser.manager import BrowserManager
from .media import validate_publish_files
from ...browser.xhs_selectors import (
    candidate_locator,
    find_present,
    find_visible,
    selector_candidates,
    selector_diagnostic,
)


PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?source=official"
PUBLISH_MANAGER_URL = "https://creator.xiaohongshu.com/new/note-manager"
_SUCCESS_TEXTS = ("发布成功", "发布完成")

_DEBUG_DIR = Path("./data/debug")

# ★★ 2026-09-18 加：平台**明确拒绝**的文案采样。
#   根因（实测任务 #43 · 小红书 · urkl 期）：本模块原来只有 `_SUCCESS_TEXTS`，
#   既**没有失败判据**、也**没有任何落盘**。于是「点击提交 → 平台弹拒绝提示 →
#   URL 不变 → `_visible_success` 全 False → 循环耗尽」这条路径只能报
#   「平台返回了业务拒绝结果」，**拿不到具体原因**：提示只活 2~3 秒，而
#   `data/debug/` 里连一张截图都没有（该模块此前全文无 screenshot 调用）。
#   #43 稳定复现两次、各耗时 80s，仍无法定性 ⇒ 移植抖音
#   `app/platforms/douyin/publish.py::_FAIL_KW` 的「点完立刻采样」做法。
#   ⚠️ 只放**语义唯一、不会出现在发布页静态 UI 里**的文案，避免误判成功/失败。
_FAIL_TEXTS = (
    "发布失败", "投稿失败", "上传失败", "发布出错", "发布异常",
    "内容不合规", "内容违规", "涉嫌违规", "审核不通过", "包含敏感信息",
    "无法发布", "发布受限", "请勿重复发布", "重复发布",
    "发布次数已达上限", "今日发布已达", "操作过于频繁",
    "请等待视频上传完成", "视频上传中", "请先上传", "请上传视频",
    "标题不能为空", "内容不能为空",
)


def _log(msg: str) -> None:
    print(f"[xhs-publish] {msg}", flush=True)


async def _dump(page: Any, tag: str) -> str:
    """把当前页面截图 + URL/可见文本快照落盘，返回截图路径。"""
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = _DEBUG_DIR / f"xhs_publish_{tag}_{stamp}"
        png = str(base.with_suffix(".png"))
        try:
            await page.screenshot(path=png, full_page=True)
        except Exception:
            png = ""
        try:
            txt = await page.inner_text("body")
        except Exception:
            txt = ""
        try:
            url = page.url
        except Exception:
            url = ""
        base.with_suffix(".txt").write_text(
            f"url: {url}\n\n{txt[:6000]}", encoding="utf-8")
        _log(f"已存诊断快照 tag={tag} url={url} png={png}")
        return png
    except Exception as exc:
        _log(f"存快照失败: {exc!r}")
        return ""


async def _sample_block_text(page: Any, evidence: dict) -> None:
    """采样页面上「平台明确拒绝」的文案。

    提示/toast 只活 2~3 秒，所以必须在点完提交后**密集轮询**采样，且判据要
    排在成功判据前面。命中即记进 evidence，供最终定性（而不是只报「业务拒绝」）。
    """
    try:
        text = await page.inner_text("body")
    except Exception:
        return
    if not text:
        return
    for kw in _FAIL_TEXTS:
        if kw in text and kw not in evidence["block_texts"]:
            evidence["block_texts"].append(kw)
            if not evidence["block_excerpt"]:
                evidence["block_excerpt"] = text[:800]
            _log(f"平台拒绝文案命中: {kw}")



def _publish_url(media_type: str) -> str:
    target = "video" if media_type == "video" else "image"
    return f"{PUBLISH_URL}&from=tab_switch&target={target}"


def _node_attributes(node: dict) -> dict[str, str]:
    raw = list(node.get("attributes") or ())
    return {
        str(raw[index]).lower(): str(raw[index + 1])
        for index in range(0, len(raw) - 1, 2)
    }


def _node_children(node: dict):
    yield from node.get("children") or ()
    yield from node.get("shadowRoots") or ()
    content = node.get("contentDocument")
    if isinstance(content, dict):
        yield content


def _node_text(node: dict) -> str:
    value = str(node.get("nodeValue") or "")
    return value + "".join(_node_text(child) for child in _node_children(node))


def _find_publish_component_button(root: dict) -> dict | None:
    """Return the real button even when it lives in a closed shadow root."""
    hosts: list[dict] = []

    def collect(node: dict) -> None:
        if str(node.get("nodeName") or "").upper() == "XHS-PUBLISH-BTN":
            hosts.append(node)
        for child in _node_children(node):
            collect(child)

    collect(root)
    for host in hosts:
        buttons: list[dict] = []

        def find_buttons(node: dict) -> None:
            if str(node.get("nodeName") or "").upper() == "BUTTON":
                buttons.append(node)
            for child in _node_children(node):
                find_buttons(child)

        for shadow in host.get("shadowRoots") or ():
            find_buttons(shadow)
        if not buttons:
            continue
        enabled = [
            button for button in buttons
            if "disabled" not in _node_attributes(button)
        ] or buttons
        for button in enabled:
            if "发布" in _node_text(button):
                return button
        return enabled[0]
    return None


def _quad_center(model: dict) -> tuple[float, float] | None:
    box = model.get("model") or {}
    quad = box.get("border") or box.get("content") or ()
    if len(quad) < 8:
        return None
    xs = [float(quad[index]) for index in range(0, 8, 2)]
    ys = [float(quad[index]) for index in range(1, 8, 2)]
    return sum(xs) / 4, sum(ys) / 4


async def _click_closed_shadow_publish_button(page: Any) -> None:
    """Dispatch one trusted click to the closed-shadow publish button."""
    session = await page.context.new_cdp_session(page)
    try:
        await session.send("DOM.enable")
        document = await session.send(
            "DOM.getDocument", {"depth": -1, "pierce": True})
        button = _find_publish_component_button(document.get("root") or {})
        if button is None:
            raise RuntimeError("新版发布组件的内部按钮尚未就绪")
        backend_node_id = button.get("backendNodeId")
        if backend_node_id is None:
            raise RuntimeError("新版发布组件缺少可点击节点")
        with suppress(Exception):
            await session.send(
                "DOM.scrollIntoViewIfNeeded",
                {"backendNodeId": backend_node_id},
            )
        center = _quad_center(await session.send(
            "DOM.getBoxModel", {"backendNodeId": backend_node_id}))
        if center is None:
            raise RuntimeError("新版发布按钮当前没有可见点击区域")
        x, y = center
        await session.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y,
        })
        await session.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y,
            "button": "left", "clickCount": 1,
        })
        await session.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y,
            "button": "left", "clickCount": 1,
        })
    finally:
        with suppress(Exception):
            await session.detach()


class _PublishWebComponentLocator:
    """Locator facade for the creator-center closed-shadow publish control."""

    def __init__(self, page: Any, host: Any):
        self._page = page
        self._host = host

    def __getattr__(self, name: str):
        return getattr(self._host, name)

    async def is_enabled(self) -> bool:
        try:
            disabled = str(
                await self._host.get_attribute("submit-disabled") or ""
            ).strip().lower()
            loading = str(
                await self._host.get_attribute("submit-loading") or ""
            ).strip().lower()
            return disabled not in {"true", "1"} and loading not in {
                "true", "1"}
        except Exception:
            return True

    async def click(self, *_args, **_kwargs):
        await _click_closed_shadow_publish_button(self._page)


@dataclass(frozen=True)
class XhsWriteOutcome:
    status: Literal["success", "failed", "uncertain"]
    result: str = ""
    error: str = ""
    method: str = "browser"

    @property
    def ok(self) -> bool:
        return self.status == "success"

    def legacy(self) -> tuple[bool, str, str]:
        if self.status == "success":
            return True, self.result, ""
        if self.status == "uncertain":
            detail = self.error or "页面提交后未取得明确成功证据，请先到平台核对"
            return False, "", f"write_uncertain:{detail}"
        return False, "", self.error or "页面操作失败"


async def _wait_until_enabled(locator: Any, interaction: Any,
                              *, attempts: int = 80) -> bool:
    for _ in range(max(1, attempts)):
        try:
            if await locator.count() and await locator.is_visible() \
                    and await locator.is_enabled():
                return True
        except Exception:
            pass
        await interaction.pause(0.2, 0.45)
    return False


async def _wait_for_visible(page: Any, group: str, interaction: Any,
                            *, attempts: int = 40) -> tuple[Any | None, str]:
    """Poll editors/widgets that are mounted after asynchronous upload work."""
    for index in range(max(1, attempts)):
        locator, name = await find_visible(page, group)
        if locator is not None:
            return locator, name
        if index + 1 < attempts:
            await interaction.pause(0.18, 0.32)
    return None, ""


async def _wait_for_present(page: Any, group: str, interaction: Any,
                            *, attempts: int = 60) -> tuple[Any | None, str]:
    """Poll hidden controls that are mounted shortly after a tab transition."""
    for index in range(max(1, attempts)):
        locator, name = await find_present(page, group)
        if locator is not None:
            return locator, name
        if index + 1 < attempts:
            await interaction.pause(0.18, 0.32)
    return None, ""


_VISIBILITY_LABELS = {
    "public": "公开可见",
    "private": "仅自己可见",
    "friends": "仅互关好友可见",
}


async def _set_publish_visibility(page: Any, interaction: Any,
                                  visibility: str) -> None:
    desired = _VISIBILITY_LABELS.get(str(visibility or "public"), "公开可见")
    candidates = page.locator(".d-select-description")
    current = None
    for index in range(int(await candidates.count())):
        candidate = candidates.nth(index)
        try:
            if await candidate.is_visible():
                current = candidate
                break
        except Exception:
            continue
    if current is not None:
        try:
            if str(await current.inner_text()).strip() == desired:
                return
        except Exception:
            pass
        await interaction.click_visible(current)
        await interaction.pause(0.15, 0.3)
    else:
        raise RuntimeError("未找到可见范围设置")

    options = page.get_by_text(desired, exact=True)
    for index in range(int(await options.count())):
        option = options.nth(index)
        try:
            cls = str(await option.get_attribute("class") or "")
            if await option.is_visible() and "name" in cls.split():
                await interaction.click_visible(option)
                await interaction.pause(0.15, 0.3)
                if str(await current.inner_text()).strip() != desired:
                    raise RuntimeError("可见范围设置后读回不一致")
                return
        except RuntimeError:
            raise
        except Exception:
            continue
    raise RuntimeError(f"未找到可见范围选项：{desired}")


async def _upload_is_busy(page: Any) -> bool:
    for candidate in selector_candidates("publish.progress"):
        try:
            locator = candidate_locator(page, candidate)
            if await locator.count() and await locator.is_visible():
                return True
        except Exception:
            continue
    return False


async def _wait_upload_complete(page: Any, interaction: Any,
                                *, attempts: int = 120) -> bool:
    stable = 0
    for _ in range(max(1, attempts)):
        if not await _upload_is_busy(page):
            stable += 1
            if stable >= 2:
                return True
        else:
            stable = 0
        await interaction.pause(0.25, 0.55)
    return False


class _SubmitLocator:
    """Mark the exact boundary where Patchright dispatches the sole submit click."""

    def __init__(self, locator: Any, state: dict, on_submit: Any = None):
        self._locator = locator
        self._state = state
        self._on_submit = on_submit

    def __getattr__(self, name: str):
        return getattr(self._locator, name)

    async def click(self, *args, **kwargs):
        if self._on_submit is not None:
            result = self._on_submit()
            if inspect.isawaitable(result):
                await result
        self._state["clicked"] = True
        return await self._locator.click(*args, **kwargs)


def _publish_response_handler(evidence: dict, submitted: dict):
    def on_response(response):
        try:
            url = str(response.url or "")
            request = response.request
            method = str(getattr(request, "method", "") or "").upper()
            status = int(response.status)
            if submitted["clicked"] and method == "POST" \
                    and 200 <= status < 300 and any(
                    marker in url.lower() for marker in (
                        "/publish", "/note/create", "/web_api/sns/v2/note")):
                evidence["responses"].append(response)
        except Exception:
            return
    return on_response


def _publish_payload_accepted(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("success") is False:
        return False
    if payload.get("success") is True:
        return True
    for key in ("code", "result_code"):
        if key not in payload:
            continue
        value = payload[key]
        if value == 0 or str(value).strip().lower() in {"0", "ok", "success"}:
            return True
    data = payload.get("data")
    return bool(isinstance(data, dict) and data.get("success") is True)


async def _consume_publish_responses(evidence: dict) -> bool:
    while evidence["responses"]:
        response = evidence["responses"].pop(0)
        try:
            payload = await response.json()
        except Exception:
            continue
        if _publish_payload_accepted(payload):
            evidence["accepted"] = True
            evidence["url"] = str(getattr(response, "url", "") or "")
            return True
        evidence["business_rejected"] = True
        # ★ 2026-09-18 加：原来这里只置一个布尔量，payload 直接被丢弃 ⇒ 事后
        #   无从知道平台到底为什么拒（任务 #43 就是这种情况）。现在把原文留下。
        if len(evidence["rejected_payloads"]) < 10:
            url = str(getattr(response, "url", "") or "")
            if isinstance(payload, (dict, list)):
                body: Any = payload
            else:
                body = str(payload)[:800]
            evidence["rejected_payloads"].append({"url": url, "payload": body})
            _log(f"发布响应被拒 url={url} payload={str(body)[:400]}")
    return bool(evidence["accepted"])


async def _visible_success(page: Any) -> bool:
    raw_url = str(getattr(page, "url", "") or "")
    lower_url = raw_url.lower()
    if any(marker in lower_url
           for marker in ("/publish/success", "publish_success")):
        return True
    # Current creator-center variants return to content management rather than
    # a dedicated success route. This check only runs after the one submit
    # click, and excludes auth/risk/error routes from success evidence.
    try:
        parsed = urlsplit(raw_url)
        path = (parsed.path or "/").lower()
        if parsed.hostname == "creator.xiaohongshu.com" \
                and "/publish/publish" not in path \
                and not any(marker in lower_url for marker in (
                    "login", "passport", "verify", "captcha", "error")):
            return True
    except Exception:
        pass
    for text in _SUCCESS_TEXTS:
        try:
            locator = page.get_by_text(text, exact=False).first
            if await locator.count() and await locator.is_visible():
                return True
        except Exception:
            continue
    return False


async def _confirm_published_title(page: Any, title: str, interaction: Any,
                                   *, attempts: int = 40) -> bool:
    """Confirm the submitted note is present in creator note management.

    ★★ 2026-09-17 修（假阴性根因）：旧实现每一轮只 pause 0.45~0.8s 就
      ``page.reload()``。而创作平台的笔记列表是 **DOM ready 之后才异步拉取的
      XHR** —— 每 0.7 秒重载一次页面，那个 XHR 永远拿不到返回，SPA 也就永远
      没机会把列表渲染出来 ⇒ 恒判「未找到」⇒ 已经发出去的笔记被记成
      ``uncertain``。实测 32/34/35 三条在平台侧**都已真实发布**，却全部记为
      uncertain（列表里能查到对应标题）。

      现在分两阶段：
        阶段 1 完全不 reload，只轮询 —— 给异步列表 XHR 它需要的那个时间窗；
        阶段 2 才 reload 兜底，且次数少、间隔拉到秒级，不再饿死 XHR。
      匹配也从「整串精确」放宽为「整串精确 → 前 12 字子串」两级 —— 渲染层
      可能给标题加省略号/前后缀，旧的全字符串精确匹配对这种改写零容错。
    """
    title = str(title or "").strip()
    if not title:
        return False
    probe = title[:12]

    async def _found() -> bool:
        for text, exact in ((title, True), (probe, False)):
            try:
                locator = page.get_by_text(text, exact=exact).first
                if await locator.count() and await locator.is_visible():
                    return True
            except Exception:
                continue
        return False

    def _closed() -> bool:
        try:
            return bool(page.is_closed())
        except Exception:
            return False

    try:
        await page.goto(
            PUBLISH_MANAGER_URL,
            wait_until="domcontentloaded",
            timeout=40_000,
        )
    except Exception:
        return False

    # 阶段 1：不 reload，让异步列表 XHR 有机会跑完。
    for _ in range(max(1, attempts)):
        if await _found():
            return True
        if _closed():
            return False
        await interaction.pause(0.4, 0.7)

    # 阶段 2：兜底 reload（少量 + 秒级间隔）。
    for _ in range(2):
        with suppress(Exception):
            await page.reload(wait_until="load", timeout=40_000)
        for _ in range(6):
            if await _found():
                return True
            if _closed():
                return False
            await interaction.pause(0.5, 0.9)
    return False


async def publish_xhs_browser(
        mgr: BrowserManager, identity: Identity, media_type: str,
        title: str, desc: str, topics: Sequence[str], files: Sequence[str],
        *, timeout_seconds: int = 180,
        visibility: str = "public",
        on_submit: Any = None) -> XhsWriteOutcome:
    """Submit one note once; never retry or switch transport after submission."""
    try:
        paths = validate_publish_files(media_type, files)
    except ValueError as exc:
        return XhsWriteOutcome("failed", error=str(exc))
    title = (title or "").strip()[:20]
    tags = [str(topic).strip().lstrip("#") for topic in topics if str(topic).strip()]
    body = ((desc or "") + (
        "\n" + " ".join(f"#{tag}" for tag in tags) if tags else ""
    )).strip()[:1000]
    interaction = mgr.xhs_interaction
    submitted = {"clicked": False}
    evidence = {
        "accepted": False,
        "url": "",
        "responses": [],
        "business_rejected": False,
        # ★ 2026-09-18 加：定性用的现场（见 _FAIL_TEXTS 注释）
        "block_texts": [],
        "block_excerpt": "",
        "rejected_payloads": [],
    }
    on_response = _publish_response_handler(evidence, submitted)

    try:
        # ★ 2026-09-17:发布改走**后台租约**(有头但最小化、绝不置顶)。
        # 原来用默认 foreground=True,每次发布都会把窗口拉到前台抢焦点;一条笔记
        # 要跑两分钟,期间反复顶掉用户正在用的窗口。抖音/快手/视频号三个发布器
        # 早已切到后台租约,小红书这里补齐。仍然是有头浏览器(写操作风控更稳)。
        async with mgr.visible_page(
                identity, url=_publish_url(media_type),
                foreground=False) as page:
            if "login" in page.url or "passport" in page.url:
                return XhsWriteOutcome("failed", error="logged_out:创作平台未登录")

            # The URL already selects image/video mode.  New builds render the
            # active tab's text inside an overlaying child, so clicking that
            # text can be intercepted by its own active tab.  Do not click an
            # already-selected mode; wait for its file input instead.

            file_input, _ = await _wait_for_present(
                page, "publish.file", interaction)
            if file_input is None:
                diagnostic = await selector_diagnostic(page, "publish.file")
                return XhsWriteOutcome(
                    "failed", error=f"未找到媒体上传控件(发布页可能改版)；{diagnostic}")
            await file_input.set_input_files(paths, timeout=15_000)
            if not await _wait_upload_complete(page, interaction):
                return XhsWriteOutcome("failed", error="媒体上传在限定时间内未完成")

            if title:
                title_input, _ = await _wait_for_visible(
                    page, "publish.title", interaction)
                if title_input is None:
                    diagnostic = await selector_diagnostic(
                        page, "publish.title")
                    return XhsWriteOutcome(
                        "failed", error=f"未找到标题输入框(发布页可能改版)；{diagnostic}")
                await interaction.type_short(title_input, title)
            if body:
                body_input, _ = await _wait_for_visible(
                    page, "publish.body", interaction)
                if body_input is None:
                    diagnostic = await selector_diagnostic(
                        page, "publish.body")
                    return XhsWriteOutcome(
                        "failed", error=f"未找到正文输入框(发布页可能改版)；{diagnostic}")
                await interaction.insert_long(body_input, body, page=page)

            try:
                await _set_publish_visibility(page, interaction, visibility)
            except Exception as exc:
                return XhsWriteOutcome(
                    "failed", error=f"设置可见范围失败: {exc}")

            publish_button, publish_selector = await _wait_for_visible(
                page, "publish.submit", interaction)
            if publish_button is None:
                diagnostic = await selector_diagnostic(page, "publish.submit")
                return XhsWriteOutcome(
                    "failed", error=f"未找到发布按钮(发布页可能改版)；{diagnostic}")
            if publish_selector == "publish_web_component":
                publish_button = _PublishWebComponentLocator(
                    page, publish_button)
            if not await _wait_until_enabled(
                    publish_button, interaction,
                    attempts=max(4, min(120, timeout_seconds * 2))):
                return XhsWriteOutcome("failed", error="发布按钮一直不可用，请检查页面提示")

            try:
                page.on("response", on_response)
            except Exception:
                pass
            try:
                # This wrapper records the precise click-dispatch boundary.  There
                # is intentionally no second click and no API fallback below it.
                await interaction.click_visible(
                    _SubmitLocator(publish_button, submitted, on_submit))
            except Exception as exc:
                if submitted["clicked"]:
                    return XhsWriteOutcome(
                        "uncertain", error=f"发布已提交但连接中断: {exc!r}")
                return XhsWriteOutcome("failed", error=f"发布按钮点击失败: {exc!r}")

            attempts = max(4, min(80, int(timeout_seconds * 2)))
            for index in range(attempts):
                network_ok = await _consume_publish_responses(evidence)
                # ★ 2026-09-18：平台拒绝提示只活 2~3 秒 ⇒ 前 30 轮（约 12 秒）
                #   密集采样，把「为什么被拒」抓下来（见 _FAIL_TEXTS）。
                if index < 30:
                    await _sample_block_text(page, evidence)
                if await _visible_success(page):
                    result = str(
                        getattr(page, "url", "") or evidence["url"])
                    # ★★ 2026-09-17:两条**互相独立**的成功证据 —— ① 页面跳到了
                    #   发布成功页/内容管理；② 拦截到的 POST /publish 响应 2xx
                    #   且 payload 判定成功。二者同时成立就是确凿的，此时再去
                    #   笔记管理页找标题只是锦上添花，而那个查找在列表未渲染时
                    #   会给出**假阴性**（实测把已发布的 32/34/35 全记成
                    #   uncertain，见 _confirm_published_title 的说明）⇒
                    #   双证据成立直接判成功，不允许核对结果推翻它。
                    if network_ok:
                        return XhsWriteOutcome("success", result=result)
                    await interaction.pause(0.8, 1.2)
                    confirmed = await _confirm_published_title(
                        page, title, interaction,
                        attempts=max(
                            4,
                            min(
                                120,
                                timeout_seconds if media_type == "video"
                                else timeout_seconds // 3,
                            ),
                        ),
                    )
                    if confirmed:
                        return XhsWriteOutcome("success", result=result)
                    return XhsWriteOutcome(
                        "uncertain",
                        error=("平台进入了发布成功页，但笔记管理中未找到"
                               "本次标题，请到平台核对"),
                    )
                try:
                    if page.is_closed():
                        break
                except Exception:
                    break
                await interaction.pause(0.25, 0.55)
            # ★ 2026-09-18：走到这里 ⇒ 连**页面级成功证据**都没有（_visible_success
            #   全程 False：页面一直卡在 /publish/publish，或跳到了 login/verify/
            #   captcha/error）。原来只能报一句「业务拒绝」、无任何现场，无法定性。
            #   现在把 ① 页面上命中的拒绝文案 ② 被拒响应 payload 原文 ③ 截图 全留下。
            if evidence["block_texts"]:
                detail = f"平台明确拒绝：{'、'.join(evidence['block_texts'][:4])}"
            elif evidence["business_rejected"]:
                detail = "平台返回了业务拒绝结果，但提交状态仍需核对"
            elif evidence["accepted"]:
                # 接口 2xx 成功但页面始终没跳 ⇒ 大概率已发出去，只是没拿到
                # 页面级证据，仍按 uncertain 交人工核对，但把原因说清楚。
                detail = "发布接口已返回成功响应，但页面未确认"
            else:
                detail = "发布按钮已点击一次，但未取得明确成功证据"
            if evidence["rejected_payloads"]:
                detail += (
                    f"（已留被拒响应原文 {len(evidence['rejected_payloads'])} 条）")
            png = await _dump(
                page, "blocked" if evidence["business_rejected"] else "unclear")
            if png and not evidence["block_texts"]:
                detail += f"；诊断截图 {png}"
            return XhsWriteOutcome(
                "uncertain", error=f"{detail}，请到平台核对")
    except Exception as exc:
        status = "uncertain" if submitted["clicked"] else "failed"
        prefix = "发布已提交后页面异常" if submitted["clicked"] else "发布页面异常"
        return XhsWriteOutcome(status, error=f"{prefix}: {exc!r}")
    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass


async def _locator_visible(locator: Any) -> bool:
    try:
        return bool(await locator.count() and await locator.is_visible())
    except Exception:
        return False


async def _find_reply_target(page: Any, comment_id: str, target_text: str):
    if comment_id:
        safe_id = str(comment_id).replace('"', '\\"')
        locator = page.locator(f'[data-comment-id="{safe_id}"]').first
        if await _locator_visible(locator):
            return locator
    if target_text:
        locator = page.get_by_text(target_text, exact=True).first
        if await _locator_visible(locator):
            return locator
    return None


async def _find_comment_input(page: Any):
    locator, _ = await find_visible(page, "comment.editor")
    return locator


def _comment_response_handler(evidence: dict):
    def on_response(response):
        try:
            url = str(response.url or "").lower()
            request = response.request
            method = str(getattr(request, "method", "") or "").upper()
            status = int(response.status)
            if method == "POST" and 200 <= status < 300 and any(
                    marker in url for marker in (
                        "/comment/post", "/comment/create", "/comment/add")):
                evidence["accepted"] = True
        except Exception:
            return
    return on_response


async def comment_xhs_browser(
        mgr: BrowserManager, identity: Identity, note_id: str, xsec_token: str,
        content: str, *, target_comment_id: str = "",
        target_text: str = "", max_scrolls: int = 16,
        timeout_seconds: int = 30,
        on_submit: Any = None) -> XhsWriteOutcome:
    """Post one visible comment/reply once, preserving an uncertain result."""
    note_id = str(note_id or "").strip()
    content = str(content or "").strip()
    if not note_id:
        return XhsWriteOutcome("failed", error="缺少目标笔记 ID")
    if not content:
        return XhsWriteOutcome("failed", error="评论内容为空")
    query = urlencode({
        "xsec_token": xsec_token or "", "xsec_source": "pc_comment"})
    url = f"https://www.xiaohongshu.com/explore/{note_id}"
    if xsec_token:
        url += f"?{query}"
    interaction = mgr.xhs_interaction
    submitted = {"clicked": False}
    evidence = {"accepted": False}
    on_response = _comment_response_handler(evidence)
    page = None

    try:
        async with mgr.visible_page(identity, url=url) as page:
            if "login" in page.url or "passport" in page.url:
                return XhsWriteOutcome("failed", error="logged_out:账号未登录")

            if target_comment_id:
                target = await _find_reply_target(
                    page, target_comment_id, target_text)
                for _ in range(max(0, int(max_scrolls))):
                    if target is not None:
                        break
                    await interaction.scroll_step(page)
                    target = await _find_reply_target(
                        page, target_comment_id, target_text)
                if target is None:
                    return XhsWriteOutcome(
                        "failed", error="未找到目标评论，已停止且不会降级为顶层评论")

                reply = None
                try:
                    reply = target.get_by_text("回复", exact=True).first
                    if not await _locator_visible(reply):
                        reply = None
                except Exception:
                    reply = None
                if reply is None:
                    try:
                        reply = target.locator(
                            'button:has-text("回复"),[class*="reply"]').first
                        if not await _locator_visible(reply):
                            reply = None
                    except Exception:
                        reply = None
                if reply is None:
                    return XhsWriteOutcome(
                        "failed", error="已找到目标评论，但未找到该评论的回复入口")
                await interaction.click_visible(reply)
                await interaction.pause(0.2, 0.45)

            editor = await _find_comment_input(page)
            for _ in range(max(0, int(max_scrolls))):
                if editor is not None:
                    break
                await interaction.scroll_step(page)
                editor = await _find_comment_input(page)
            if editor is None:
                diagnostic = await selector_diagnostic(page, "comment.editor")
                return XhsWriteOutcome(
                    "failed", error=f"未找到评论输入框(页面可能改版)；{diagnostic}")
            if len(content) <= 80:
                await interaction.type_short(editor, content)
            else:
                await interaction.insert_long(editor, content, page=page)

            send, _ = await find_visible(page, "comment.submit")
            if send is None:
                diagnostic = await selector_diagnostic(page, "comment.submit")
                return XhsWriteOutcome(
                    "failed", error=f"未找到评论发送按钮(页面可能改版)；{diagnostic}")
            if not await _wait_until_enabled(
                    send, interaction,
                    attempts=max(4, min(60, timeout_seconds * 2))):
                return XhsWriteOutcome("failed", error="评论发送按钮当前不可用")
            existing_matches = 0
            try:
                existing_matches = int(await page.get_by_text(
                    content, exact=True).count())
            except Exception:
                pass
            try:
                page.on("response", on_response)
            except Exception:
                pass
            try:
                await interaction.click_visible(
                    _SubmitLocator(send, submitted, on_submit))
            except Exception as exc:
                if submitted["clicked"]:
                    return XhsWriteOutcome(
                        "uncertain", error=f"评论已提交但连接中断: {exc!r}")
                return XhsWriteOutcome("failed", error=f"评论发送失败: {exc!r}")

            for _ in range(max(4, min(60, timeout_seconds * 2))):
                own_text_added = False
                try:
                    own_text = page.get_by_text(content, exact=True)
                    own_text_added = int(await own_text.count()) > existing_matches
                except Exception:
                    pass
                if own_text_added:
                    return XhsWriteOutcome("success", result="ok")
                try:
                    if page.is_closed():
                        break
                except Exception:
                    break
                await interaction.pause(0.2, 0.45)
            detail = ("接口已接受但页面未显示新评论" if evidence["accepted"]
                      else "评论按钮已点击一次，但未取得明确成功证据")
            return XhsWriteOutcome(
                "uncertain", error=f"{detail}，请到平台核对")
    except Exception as exc:
        status = "uncertain" if submitted["clicked"] else "failed"
        prefix = "评论提交后页面异常" if submitted["clicked"] else "评论页面异常"
        return XhsWriteOutcome(status, error=f"{prefix}: {exc!r}")
    finally:
        if page is not None:
            try:
                page.remove_listener("response", on_response)
            except Exception:
                pass
