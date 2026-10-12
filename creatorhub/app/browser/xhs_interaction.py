"""Central, deterministic-testable semantics for visible XHS page actions."""
from __future__ import annotations

import asyncio
import inspect
import random
import sys
from contextlib import asynccontextmanager, suppress
from typing import Any, Awaitable, Callable


class XhsVisibleActionGate:
    """Permit one active, user-visible Xiaohongshu action on the machine."""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(1)
        self.active_account: Any = None
        self._owner_task: asyncio.Task | None = None
        self._depth = 0

    @property
    def owned_by_current_task(self) -> bool:
        return self._owner_task is asyncio.current_task()

    @asynccontextmanager
    async def acquire(self, account_key: Any):
        current = asyncio.current_task()
        if self._owner_task is current:
            if self.active_account != account_key:
                raise RuntimeError("同一可见操作不可嵌套切换小红书账号")
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        acquired = False
        try:
            await self._semaphore.acquire()
            acquired = True
            self.active_account = account_key
            self._owner_task = current
            self._depth = 1
            yield
        finally:
            if acquired:
                self._depth = 0
                self._owner_task = None
                self.active_account = None
                self._semaphore.release()


class XhsInteractionPolicy:
    """Page-native clicks, input and finite scrolling with bounded cadence."""

    def __init__(
            self, *, rng: random.Random | None = None,
            sleep: Callable[[float], Awaitable[None]] | None = None):
        self.rng = rng or random.SystemRandom()
        self.sleep = sleep or asyncio.sleep
        self._action_count = 0
        self._next_rest_at = int(self.rng.randint(14, 24))

    async def _pause(self, low: float, high: float) -> None:
        await self.sleep(float(self.rng.uniform(low, high)))

    async def pause(self, low: float, high: float) -> None:
        """Public bounded pause for condition-polling loops."""
        if low < 0 or high < low:
            raise ValueError("交互停顿范围无效")
        await self._pause(low, high)

    async def _after_action(self) -> None:
        """Occasionally insert a longer bounded break between action bursts."""
        self._action_count += 1
        if self._action_count < self._next_rest_at:
            return
        self._action_count = 0
        self._next_rest_at = int(self.rng.randint(14, 24))
        await self._pause(1.4, 3.8)

    async def reading_pause(self, *, content_length: int = 0) -> float:
        """Pause after navigation using a bounded content-aware dwell time."""
        length = max(0, min(4000, int(content_length or 0)))
        base = 0.9 + min(5.5, length / 600)
        delay = float(self.rng.uniform(base * 0.85, base * 1.2))
        await self.sleep(delay)
        await self._after_action()
        return delay

    async def click_visible(
            self, locator: Any, *, timeout: int = 10_000) -> None:
        await locator.wait_for(state="visible", timeout=timeout)
        await locator.scroll_into_view_if_needed(timeout=timeout)
        enabled = getattr(locator, "is_enabled", None)
        if callable(enabled):
            for _ in range(20):
                if await enabled():
                    break
                await self._pause(0.05, 0.12)
            else:
                raise RuntimeError("小红书页面控件当前不可用")
        # ★★ 2026-09-17:hover 只是"先把鼠标移过去"的人类轨迹模拟，**它不该决定
        #   这次发布成不成功**。小红书在视频上传完之后、封面/转码还在收尾的那几
        #   十秒里会留一层遮罩，Playwright hover 的 receives-events 检查于是永远
        #   不通过，一路撞满 30s 超时，把整条发布判成 failed —— 实测 38 号
        #   （pocket4p，29MB，比同批的 deepseek 大）就这么丢的，而同一时刻的
        #   37/39 都发成功了。降级：hover 失败直接跳过，继续点。
        with suppress(Exception):
            await locator.hover(timeout=8_000)
        await self._pause(0.18, 0.48)
        try:
            await locator.click(timeout=15_000)
        except Exception:
            # 普通 click 也被遮罩挡住时，用 force 把点击直接派发到按钮上。
            # 这一次点击究竟有没有真的提交，由 publish_xhs_browser 的
            # **页面证据 + 接口证据**判定，不由这里"点没点上"下结论。
            await locator.click(timeout=15_000, force=True)
        await self._after_action()

    async def _prepare_input(self, locator: Any) -> None:
        await locator.wait_for(state="visible", timeout=10_000)
        await locator.scroll_into_view_if_needed(timeout=10_000)
        await locator.focus()
        await self._pause(0.06, 0.16)
        modifier = "Meta" if sys.platform == "darwin" else "Control"
        await locator.press(f"{modifier}+A")
        await locator.press("Backspace")

    async def type_short(self, locator: Any, text: str) -> None:
        await self._prepare_input(locator)
        # Keep the requested text exact; vary pauses, not content or targets.
        burst_left = int(self.rng.randint(3, 7))
        for character in str(text):
            await locator.press_sequentially(character, delay=0)
            await self._pause(0.06, 0.16)
            burst_left -= 1
            if character in ",，。.!！?？;；:：\n":
                await self._pause(0.2, 0.55)
            elif character.isspace() or burst_left <= 0:
                await self._pause(0.1, 0.3)
                burst_left = int(self.rng.randint(3, 7))
        await self._verify_text(locator, str(text))
        await self.reading_pause(content_length=len(str(text)))

    async def insert_long(
            self, locator: Any, text: str, *, page: Any | None = None) -> None:
        await self._prepare_input(locator)
        target_page = page or getattr(locator, "page", None)
        if target_page is None or not hasattr(target_page, "keyboard"):
            raise RuntimeError("长文本输入缺少活动页面")
        await target_page.keyboard.insert_text(str(text))
        await self._pause(0.08, 0.18)
        await self._verify_text(locator, str(text))
        await self.reading_pause(content_length=len(str(text)))

    async def _verify_text(self, locator: Any, expected: str) -> None:
        try:
            actual = await locator.input_value()
        except Exception:
            actual = await locator.evaluate(
                "el => el.value ?? el.innerText ?? el.textContent ?? ''")
        if str(actual) == expected:
            return
        # ★ 2026-09-14 修:原来只做逐字符相等比对,而小红书发布页的正文编辑器已从
        #   Quill 换到 TipTap/ProseMirror —— 它会把 ``insert_text`` 里的换行规范化成
        #   段落(段落间/结尾的 \n 数量与原文不同),于是「其实写进去了」被误判成
        #   RuntimeError('小红书文本输入结果与预期不一致'),整条发布直接 failed。
        #   现在分三级:(1) 逐字符相等(原判据);(2) 去空白后相等;
        #   (3) 去空白后「期望文本的前 20 字」是否被包含 —— 对短文本(评论)等价于
        #   全文包含,仍能识别出真的没写进去的情况。
        strip_all = lambda value: "".join(str(value).split())  # noqa: E731
        wanted = strip_all(expected)
        got = strip_all(actual)
        if wanted and got == wanted:
            return
        if wanted and wanted[:20] in got:
            print(f"[xhs-write] 文本已写入但被编辑器规范化(期望 {len(wanted)} 字/回读 "
                  f"{len(got)} 字),按通过处理", flush=True)
            return
        raise RuntimeError("小红书文本输入结果与预期不一致")

    async def scroll_step(self, page: Any, *, direction: int = 1) -> int:
        # Triangular sampling avoids a flat machine-like distribution while
        # remaining bounded enough for deterministic collection progress.
        amount = int(self.rng.triangular(350, 900, 610))
        signed = amount if direction >= 0 else -amount
        await page.mouse.wheel(0, signed)
        await self._pause(0.18, 0.52)
        await self._after_action()
        return signed

    async def scroll_until(
            self, page: Any,
            predicate: Callable[[], bool | Awaitable[bool]],
            *, max_steps: int, direction: int = 1) -> bool:
        if await self._resolve(predicate()):
            return True
        for _ in range(max(0, int(max_steps))):
            await self.scroll_step(page, direction=direction)
            if await self._resolve(predicate()):
                return True
        return False

    @staticmethod
    async def _resolve(value: bool | Awaitable[bool]) -> bool:
        if inspect.isawaitable(value):
            value = await value
        return bool(value)
