"""抖音「发布后核对」搜索词回归测试(离线,不开真浏览器)。

事故背景(2026-09-21,任务 #68)
------------------------------
抖音标题**可以含空格**:#68 的标题是 ``WiFi 8 开卖：这代不比快比不掉线``。
老代码把核对用的搜索词算成 ``"".join(title.split())[:8]`` —— **先去掉所有空格**
再取前 8 字,得到 ``WiFi8开卖：``。而抖音的作品管理搜索**按标题原文匹配**,
拿 ``WiFi8开卖：`` 去搜 ``WiFi 8 开卖：…`` 只会返回「没有相关作品」。

后果:一条**真的发出去了**的作品被 ``_verify_on_manage`` 判 not found,
任务被写成 ``failed``,错误信息还要人工"到平台复核"(见 14:03:56 的诊断快照里
``作品 (38)`` 与「发布成功」)。16:00 的 #74(标题 ``昇腾 960：…``)会踩同一个坑。

修法(``app/platforms/douyin/publish.py``)
------------------------------------------
1. :func:`_probe_candidates` —— 搜索词改成**多候选**:先试标题**原文**前缀
   (与平台匹配口径一致),再退到去空格前缀。
2. :func:`_compact_ws` —— 页面侧比对改成**去空白比对**(页面文本里的标题带空格)。
3. ``_EMPTY_RE`` 窗口 ``{0,10}`` → ``{0,40}`` —— 空态文案
   「没有找到与"<搜索词>"相关的作品」中间那段等于"搜索词长度 + 4",8 字搜索词
   就是 12 字,``{0,10}`` 够不着 ⇒ 空态识别不到,而空态里**又写着搜索词**
   ⇒ 会被读成"作品已存在"(2026-09-15 那次假命中的同源问题)。

本文件把这些行为钉住,全部离线跑。
"""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from app.platforms.douyin import publish as pub_mod

# 真实事故里那两条标题(第二条是 16:00 轮的 #74,含空格,会踩同一个坑)
TITLE_SPACED = "WiFi 8 开卖：这代不比快比不掉线"
TITLE_SPACED_2 = "昇腾 960：卡差两三年，改比怎么连"
TITLE_PLAIN = "四年不露面的中国人，成了亚洲首富"


class FakeBox:
    """``page.locator(sel).first`` 的替身:只管搜索框的 fill/press。"""

    def __init__(self, page: "FakePage"):
        self.page = page
        self.typed = ""

    async def count(self) -> int:
        return 1

    async def is_visible(self) -> bool:
        return True

    async def click(self, timeout=None):  # noqa: ANN001
        return None

    async def fill(self, text: str, timeout=None):  # noqa: ANN001
        self.typed = text

    async def press(self, key: str, timeout=None):  # noqa: ANN001
        if key == "Enter" and self.typed:
            self.page.probe = self.typed


class FakeLocator:
    def __init__(self, page: "FakePage"):
        self._box = FakeBox(page)
        self.first = self._box


class FakeFrame:
    def __init__(self, page: "FakePage"):
        self.page = page

    async def inner_text(self, sel: str) -> str:
        return self.page.body_text()


class FakePage:
    """最小可用的「作品管理页」替身。

    语义刻意照着真实平台来:页面 body 里能不能看到这条作品,取决于
    **搜索词是不是标题原文的子串** —— 拿去掉空格的搜索词去搜带空格的标题,
    平台就是查不到(这正是 #68 误报的机理)。

    ``visible=False`` 模拟"这条作品**根本没发出去**":平台永远只回空态,
    此时核对必须判 not found,不能被空态里那句含搜索词的提示骗成"找到了"。
    """

    def __init__(self, real_title: str, visible: bool = True):
        self.real_title = real_title
        self.visible = visible
        self.probe = None
        self.url = pub_mod.MANAGE_URL
        self.searches: list[str] = []
        self.frames = [FakeFrame(self)]

    # ---- 供被测代码调用 ----
    async def goto(self, url: str, wait_until=None, timeout=None):  # noqa: ANN001
        self.url = url

    async def wait_for_timeout(self, ms: int):
        return None

    def locator(self, sel: str) -> FakeLocator:
        return FakeLocator(self)

    async def inner_text(self, sel: str) -> str:
        return self.body_text()

    async def screenshot(self, path=None, full_page=True):  # noqa: ANN001
        if path:
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\n")

    async def close(self):
        return None

    # ---- 平台行为模拟 ----
    def body_text(self) -> str:
        probe = self.probe
        if probe is None:
            return "作品 (38) 加载中…"
        if probe not in self.searches:
            self.searches.append(probe)
        if self.visible and probe in self.real_title:   # 平台按原文子串匹配
            return f"作品 (39) 最新发布 {self.real_title} 审核中"
        # 搜无结果:空态文案**包含搜索词本身**(这正是那个假命中的陷阱)
        return f'没有找到与"{probe}"相关的作品'


class FakeCtx:
    def __init__(self, page: FakePage):
        self.page = page

    async def new_page(self) -> FakePage:
        return self.page


def _run_verify(title: str, *, min_ms: int = 1, timeout_ms: int = 100000,
                visible: bool = True):
    """跑一次 ``_verify_on_manage``,返回 ``(found, detail, page)``。

    ``timeout_ms`` 要**同时**把 ``_PROBE_MIN_MS`` 一起调小才有意义 ——
    单候选时长是 ``max(_PROBE_MIN_MS, timeout_ms // 候选数)``,两者都得压。
    """
    page = FakePage(title, visible=visible)
    ctx = FakeCtx(page)
    old_dir = pub_mod._DEBUG_DIR
    old_min = pub_mod._PROBE_MIN_MS
    with tempfile.TemporaryDirectory() as tmp:
        pub_mod._DEBUG_DIR = Path(tmp)
        pub_mod._PROBE_MIN_MS = min_ms
        try:
            found, detail = asyncio.run(
                pub_mod._verify_on_manage(ctx, title, timeout_ms=timeout_ms))
        finally:
            pub_mod._DEBUG_DIR = old_dir
            pub_mod._PROBE_MIN_MS = old_min
    return found, detail, page


class ProbeCandidatesTests(unittest.TestCase):
    def test_原文前缀排第一(self):
        cands = pub_mod._probe_candidates(TITLE_SPACED)
        self.assertEqual(cands[0], TITLE_SPACED[:8])
        self.assertIn(" ", cands[0], "原文前缀必须保留空格 —— 平台按原文匹配")
        self.assertEqual(cands[1], "WiFi8开卖：")

    def test_无空格标题只产生一个候选(self):
        self.assertEqual(pub_mod._probe_candidates(TITLE_PLAIN),
                         [TITLE_PLAIN[:8]])

    def test_空标题没有候选(self):
        for bad in ("", "   ", None):
            self.assertEqual(pub_mod._probe_candidates(bad), [])

    def test_两个候选去重(self):
        # 前 8 字里没有空格 ⇒ 原文前缀与去空格前缀相同,不应重复出现
        self.assertEqual(len(pub_mod._probe_candidates("昇腾960卡差两三年")), 1)


class EmptyStateRegexTests(unittest.TestCase):
    def test_能识别含长搜索词的空态(self):
        # 老窗口 {0,10} 在这里会失配:中间是 `找到与"WiFi8开卖："` = 12 字
        text = '没有找到与"WiFi8开卖："相关的作品'
        self.assertIsNotNone(pub_mod._EMPTY_RE.search(text))

    def test_能识别其他空态措辞(self):
        self.assertIsNotNone(pub_mod._EMPTY_RE.search("暂无相关作品"))
        self.assertIsNotNone(pub_mod._EMPTY_RE.search('未搜索到与"X"相关的作品'))

    def test_不会误伤列表底部(self):
        # 列表底部是没有"相关"的,不能被当成空态,否则永远找不到作品
        self.assertIsNone(pub_mod._EMPTY_RE.search("没有更多了"))
        self.assertIsNone(pub_mod._EMPTY_RE.search("没有更多作品"))


class CompactWhitespaceTests(unittest.TestCase):
    def test_去空白后能跨空格命中(self):
        page_title = "  " + TITLE_SPACED + "  "
        probe = pub_mod._compact_ws(TITLE_SPACED)[:8]
        self.assertNotIn(probe, " ".join(page_title.split()),
                         "★ 老写法(直接 in)在这个标题上必然失配 —— 这就是 #68 误报的根因")
        self.assertIn(probe, pub_mod._compact_ws(page_title))


class VerifyOnManageTests(unittest.TestCase):
    def test_带空格标题能找到作品(self):
        found, detail, page = _run_verify(TITLE_SPACED)
        self.assertTrue(found, detail)
        self.assertIn("命中标题", detail)
        # 第一个候选(原文前缀,带空格)就该命中,不必退到去空格版
        self.assertIn(" ", page.searches[0])

    def test_昇腾标题也能找到(self):
        found, detail, _ = _run_verify(TITLE_SPACED_2)
        self.assertTrue(found, detail)

    def test_无空格标题行为不变(self):
        found, detail, _ = _run_verify(TITLE_PLAIN)
        self.assertTrue(found, detail)

    def test_确实没有时判not_found且不误报(self):
        # 平台侧根本没有这条作品:只有空态。而空态文案**含搜索词本身**,
        # 绝不能因此判"找到了" —— 这正是 2026-09-15 那次假命中的同源陷阱。
        found, detail, _ = _run_verify(TITLE_SPACED, min_ms=1, timeout_ms=4,
                                       visible=False)
        self.assertFalse(found, detail)
        self.assertIn("仍未出现标题", detail)

    def test_搜不到时会依次尝试两个候选(self):
        # 平台侧永远搜不到 ⇒ 两个候选都应被试过,且第一次带空格、第二次不带
        found, detail, page = _run_verify(TITLE_SPACED, min_ms=1, timeout_ms=4,
                                          visible=False)
        self.assertFalse(found, detail)
        self.assertEqual(len(page.searches), 2, page.searches)
        self.assertIn(" ", page.searches[0])
        self.assertNotIn(" ", page.searches[1])
        # 两个候选都要出现在失败原因里,便于事后判断是"没发出去"还是"搜不到"
        for probe in pub_mod._probe_candidates(TITLE_SPACED):
            self.assertIn(probe, detail)


if __name__ == "__main__":
    unittest.main()
