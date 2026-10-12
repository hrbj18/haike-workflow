"""抖音封面「生效确认 + 失败换路重试」的**纯桩**单测(不开浏览器、不连真账号)。

背景(2026-09-21):抖音 12:00 / 13:00 / 14:00 三条视频**没带上封面** —— 封面文件其实
投喂成功了(``total=6 selected={'index':4,'drag':True,'chainHit':True} relaxed=False``),
断点在最后一环。所以 ``set_douyin_cover`` 的返回值只说明「流程走到哪一步」是不够的,
必须**读回封面预览区的实际状态**确认到底挂上没有;确认「没生效」还要**换一条路径**重试。

覆盖(全部离线,用本文件自带的 ``LiveCoverPage`` 驱动真实 ``cover.py``):

  1. ``_cover_verdict`` 三态(纯函数:changed / unchanged / unknown)
  2. 像素一致时 **src 变了也不当依据**(防「换 CDN 变体」造成的假成功)
  3. 首查 changed ⇒ 立即返回 ``""``,不重试、不多投喂
  4. 首查 unchanged ⇒ 换路重试第 2 轮 changed ⇒ 返回 ``""``(且确实重新投喂过)
  5. 3 轮全 unchanged ⇒ 返回非空原因(格式对)、**不抛异常**
  6. fail-open:复检读不到封面区(选择器/结构变了)⇒ 当已生效 ``""``、不重试
  7. fail-open:换路后复检读不到 ⇒ 当已生效 ``""``
  8. 换路连封面编辑器都打不开 ⇒ 如实回报、不抛异常、不误投喂
  9. 全流程成功 ⇒ ``""``(老口径不变,既有调用方/用例不受影响)
 10. 全流程明确没生效 ⇒ 返回串形如
     ``封面未确认生效(3轮重试后仍未生效): <path>; 最后判据: ...``
 11. 缩略图截图全抛异常 ⇒ fail-open 返回 ``""``、不冒泡
 12. 静态:确认/重试这两个新函数里**没有** ``raise`` 语句
     (硬约束:确认逻辑只准加日志与重试,绝不许成为发布的新失败点)
 13. 发布层:封面返回**新的**失败串后发布照常成功(best-effort 未被打破)
 14. 判据文案保留「像素前后一致」**连续**子串
     (``tests/douyin_cover_fakes.py`` 的 7a 按这个子串判「假成功被如实报出来」)

落盘隔离:与 ``tests/test_douyin_cover_adversarial.py`` 同法,在**导入时**把
``cover_mod._DEBUG_DIR`` 重定向到一次性临时目录(``mkdtemp`` —— 避开宿主 safe-delete
对 ``TemporaryDirectory`` 清理的拦截),绝不往取证目录 ``data/debug`` 写假 PNG。
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.platforms.douyin import cover as cover_mod

# 落盘隔离(见文件头):必须在任何用例调 set_douyin_cover 之前生效。
cover_mod._DEBUG_DIR = Path(tempfile.mkdtemp(prefix="dy_cover_live_"))

# 真实存在的封面文件 —— ``set_douyin_cover`` 开头会 ``path.is_file()`` 短路。
_TMP_FILES = Path(tempfile.mkdtemp(prefix="dy_cover_live_files_"))
_COVER_FILE = _TMP_FILES / "cover-1080x1440.jpg"
_COVER_FILE.write_bytes(b"\xff\xd8\xff\xd9")


def _digest1(shot: bytes) -> str:
    """与 ``cover.py::_cover_signature`` 同算法造指纹(1 张缩略图 ⇒ 1 张元素截图)。

    ``_cover_signature`` 的 digest = ``sha1(b"|".join(shots))[:16]``,而稳定性自检
    会**再截一遍**(同一次调用共耗 2 张截图)。桩侧要造「和基线一致」的读数,就得按
    同一算法算,不能随手写个 "SAME" —— 否则会造出永远「变了」的假读数。
    """
    return hashlib.sha1(shot).hexdigest()[:16]

# 新失败串的**格式**断言:``封面未确认生效(N轮重试后仍未生效): <path>; 最后判据: ...``
_RE_NOT_CONFIRMED = re.compile(
    r"^封面未确认生效\((?P<rounds>\d+)轮重试后仍未生效\): (?P<path>.+?); 最后判据: (?P<last>.+)$")
# 静态硬约束:确认/重试函数里不许出现 ``raise`` 语句(docstring 里的「不 raise」不算)
_RE_RAISE_STMT = re.compile(r"^\s*raise\b", re.M)


def _text_label(sel: str):
    """从 ``text="完成"`` / ``text=完成`` 里取文案;不是 text 选择器则 None。"""
    if sel.startswith('text="') and sel.endswith('"') and len(sel) > 7:
        return sel[6:-1]
    if sel.startswith("text=") and len(sel) > 5:
        return sel[5:]
    return None


class _LiveThumb:
    """``locator.nth(i).screenshot()`` 的句柄。"""

    def __init__(self, page):
        self.page = page

    async def screenshot(self, timeout=None, **kwargs):
        return self.page.next_shot()


class _LiveLocator:
    """只实现 ``cover.py`` 用到的那部分 Playwright Locator 表面。"""

    def __init__(self, page, sel):
        self.page = page
        self.sel = sel
        self.first = self

    async def count(self):
        return self.page.count_for(self.sel)

    async def is_visible(self, timeout=None):
        return True

    async def scroll_into_view_if_needed(self, timeout=None):
        self.page.ops.append(("scroll", self.sel))

    async def click(self, timeout=None):
        self.page.ops.append(("click", self.sel))
        label = _text_label(self.sel)
        if label is not None:
            self.page.clicked_labels.append(label)

    def nth(self, index):
        return _LiveThumb(self.page)

    async def screenshot(self, timeout=None, **kwargs):
        return self.page.next_shot()

    async def set_input_files(self, files, timeout=None):
        self.page.ops.append(("upload", self.sel))
        self.page.uploaded.append((self.sel, files))

    async def inner_text(self):
        return ""

    async def wait_for(self, state=None, timeout=None):
        return None


class _LiveKeyboard:
    def __init__(self, page):
        self.page = page

    async def press(self, key):
        self.page.keys.append(key)


class LiveCoverPage:
    """驱动真实 ``cover_mod.set_douyin_cover`` / ``_confirm_cover`` 的最小 Playwright fake。

    可配置项(默认值 = 「什么都没命中」,由用例显式打开):
      * ``visible_texts``   —— ``text="X"`` 选择器能命中哪些文案
      * ``vertical_btn``    —— ``_MARK_VERTICAL_COVER_JS`` 的返回(能否点开封面编辑器)
      * ``upload_mark``     —— ``_MARK_UPLOAD_JS`` 的返回(投放区 input 有没有标到)
      * ``thumbs``          —— ``_MARK_THUMBS_JS`` 的返回(封面缩略图镜像)
      * ``finish_result``   —— ``_JS_FINISH_CANDS`` 的返回(「完成」点没点中)
      * ``modal_present``   —— 封面弹层还在不在
      * ``shot_seq`` / ``shot_default`` —— 元素截图字节流(造 digest 用)
      * ``raise_on_shot``   —— 让 ``screenshot()`` 抛异常(测 fail-open)
    """

    def __init__(self):
        self.url = "https://creator.douyin.com/creator-micro/content/post/video"
        self.frames = [self]
        self.keyboard = _LiveKeyboard(self)
        self.ops: list[tuple] = []
        self.clicked_labels: list[str] = []
        self.uploaded: list[tuple] = []
        self.keys: list[str] = []
        self.waits: list[int] = []
        self.js_calls: list[str] = []
        self.logs: list[str] = []
        # 可配置行为
        self.visible_texts: set[str] = set()
        self.vertical_btn: dict = {"ok": False}
        self.upload_mark: dict = {"total": 0, "selected": None}
        self.thumbs: list[dict] = []
        self.finish_result: dict = {"ok": True, "text": "完成"}
        self.modal_present = False
        self.shot_seq: list[bytes] = []
        self.shot_default = b"IMG"
        self.raise_on_shot = False
        # 注入样式在 DOM 中的存续状态
        self.hover_style_present = False
        self.hover_injected = 0
        self.hover_removed = 0

    # ── Playwright 表面 ──
    def locator(self, sel, **kwargs):
        return _LiveLocator(self, sel)

    async def wait_for_timeout(self, ms):
        self.waits.append(ms)

    async def evaluate(self, js, *args):
        self.js_calls.append(js)
        # ★ 顺序敏感:``_force_show_hover`` 的 JS 同时含 createElement 与 getElementById,
        #   必须先判 createElement;``_JS_FINISH_CANDS`` 自带 "doClick" 标记,排最前。
        if "doClick" in js:
            return dict(self.finish_result)
        if "data-chrc-vcover" in js:
            return dict(self.vertical_btn)
        if "data-bfc-upload" in js:
            return dict(self.upload_mark)
        if "data-bfc-thumb" in js:
            return {"anchors": len(self.thumbs), "marked": list(self.thumbs)}
        if "设置竖封面" in js:                    # _COVER_MODAL_JS
            return self.modal_present
        if "createElement" in js:                # _force_show_hover(注入)
            self.hover_style_present = True
            self.hover_injected += 1
            return True
        if "getElementById" in js:               # _clear_hover_show(移除)
            self.hover_style_present = False
            self.hover_removed += 1
            return None
        return None

    def get_by_text(self, text, exact=False):
        return _LiveLocator(self, f"text={text}")

    async def screenshot(self, path=None, full_page=False):
        return b"PNG"

    async def inner_text(self, sel="body"):
        return ""

    # ── 内部 ──
    def next_shot(self):
        if self.raise_on_shot:
            raise RuntimeError("screenshot boom")
        return self.shot_seq.pop(0) if self.shot_seq else self.shot_default

    def count_for(self, sel):
        if "chrc-vcover" in sel:
            return 1 if self.vertical_btn.get("ok") else 0
        if "bfc-upload" in sel:
            return 1 if (self.upload_mark or {}).get("selected") else 0
        if "bfc-thumb" in sel:
            return len(self.thumbs)
        label = _text_label(sel)
        if label is not None:
            return 1 if label in self.visible_texts else 0
        return 0


class _LogCapture:
    """把 ``cover_mod._log`` 换成收集器,便于断言「确认结果进了日志」。"""

    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, msg):
        self.lines.append(str(msg))

    def text(self) -> str:
        return "\n".join(self.lines)


def _run(coro):
    return asyncio.run(coro)


class DouyinCoverConfirmTests(unittest.TestCase):
    """第 1~8、11、14:确认判定与换路重试的**纯桩**行为。"""

    # ── 1. 三态纯函数 ──
    def test_01_cover_verdict_three_states(self):
        ok_old = {"ok": True, "digest": "AAA", "srcs": ["s1"]}
        ok_new = {"ok": True, "digest": "BBB", "srcs": ["s2"]}
        self.assertEqual(cover_mod._cover_verdict(ok_old, ok_new)[0], "changed")
        self.assertEqual(cover_mod._cover_verdict(ok_old, dict(ok_old))[0], "unchanged")
        # 复检读不到 / 基线读不到 / 空 dict / None ⇒ 一律 unknown(fail-open)
        self.assertEqual(cover_mod._cover_verdict(ok_old, {"ok": False, "why": "x"})[0],
                         "unknown")
        self.assertEqual(cover_mod._cover_verdict({"ok": False}, ok_new)[0], "unknown")
        self.assertEqual(cover_mod._cover_verdict(None, ok_new)[0], "unknown")
        self.assertEqual(cover_mod._cover_verdict(ok_old, None)[0], "unknown")
        self.assertEqual(cover_mod._cover_verdict({"ok": True}, {"ok": True})[0], "unknown")
        # 是**同步纯函数**(不 await、不碰页面):真机里判定逻辑要能独立单测
        self.assertFalse(asyncio.iscoroutinefunction(cover_mod._cover_verdict))
        # 注意:verdict 用的是 channels 同名函数的词表(changed/unchanged/unknown)
        self.assertEqual(
            sorted({cover_mod._cover_verdict(ok_old, ok_new)[0],
                    cover_mod._cover_verdict(ok_old, dict(ok_old))[0],
                    cover_mod._cover_verdict(None, None)[0]}),
            ["changed", "unchanged", "unknown"])

    # ── 2. src 不作为判据(防「换 CDN 变体」假成功)──
    def test_02_src_change_is_not_evidence(self):
        before = {"ok": True, "digest": "SAME", "srcs": ["https://cdn.a/old.jpg"]}
        after = {"ok": True, "digest": "SAME", "srcs": ["https://cdn.b/new.jpg"]}
        verdict, detail = cover_mod._cover_verdict(before, after)
        self.assertEqual(verdict, "unchanged",
                         "src 变了但像素一致 ⇒ 必须判「没生效」(典型假成功)")
        self.assertIn("像素前后一致", detail)

    # ── 3. 首查 changed ⇒ 立刻成功,不重试 ──
    def test_03_changed_returns_empty_without_retry(self):
        page = LiveCoverPage()
        page.vertical_btn = {"ok": True, "text": "选择封面"}   # 万一真去重试就投喂得出东西
        page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
        page.thumbs = [{"label": "竖封面3:4", "src": "s1"}]
        page.shot_seq = [b"NEW", b"NEW"]
        page.shot_default = b"NEW"
        cap = _LogCapture()
        with patch.object(cover_mod, "_log", cap):
            note = _run(cover_mod._confirm_cover(
                page, "D:/x/cover.jpg",
                {"ok": True, "digest": _digest1(b"OLD")},
                {"ok": True, "digest": _digest1(b"NEW")}))
        self.assertEqual(note, "")
        self.assertEqual(page.uploaded, [], "首查已生效却仍重投喂了文件")
        self.assertIn("封面已确认生效: D:/x/cover.jpg", cap.text())

    # ── 4. 首查 unchanged ⇒ 换路重试第 2 轮成功 ──
    def test_04_unchanged_then_retry_succeeds(self):
        page = LiveCoverPage()
        page.visible_texts = {"竖封面3:4", "完成"}
        page.vertical_btn = {"ok": True, "text": "选择封面"}
        page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
        page.thumbs = [{"label": "竖封面3:4", "src": "s1"}]
        # 换路第 1 次复读(2 张:first + stability)= 已变(sha1(OLD) → sha1(NEW))
        page.shot_seq = [b"NEW", b"NEW"]
        page.shot_default = b"NEW"
        cap = _LogCapture()
        with patch.object(cover_mod, "_log", cap):
            note = _run(cover_mod._confirm_cover(
                page, "D:/x/cover.jpg",
                {"ok": True, "digest": _digest1(b"OLD")},
                {"ok": True, "digest": _digest1(b"OLD")}))
        self.assertEqual(note, "")
        self.assertEqual(len(page.uploaded), 1, "换路应重新投喂 1 次")
        self.assertTrue(any("完成" in lab for lab in page.clicked_labels),
                        "换路后应重新点「完成」")
        self.assertIn("换路重试", cap.text())
        self.assertIn("封面已确认生效", cap.text())

    # ── 5. 3 轮全 unchanged ⇒ 非空原因 + 格式对 + 不抛异常 ──
    def test_05_all_rounds_unchanged_returns_reason_without_raising(self):
        page = LiveCoverPage()
        page.visible_texts = {"竖封面3:4", "完成"}
        page.vertical_btn = {"ok": True, "text": "选择封面"}
        page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
        page.thumbs = [{"label": "竖封面3:4", "src": "s1"}]
        page.shot_default = b"SAME"          # 永远不变 ⇒ 每轮都 unchanged
        same = _digest1(b"SAME")
        cap = _LogCapture()
        try:
            with patch.object(cover_mod, "_log", cap):
                note = _run(cover_mod._confirm_cover(
                    page, "D:/x/cover.jpg",
                    {"ok": True, "digest": same}, {"ok": True, "digest": same}))
        except Exception as exc:                     # noqa: BLE001
            self.fail(f"3 轮全失败时不许冒泡异常: {exc!r}")
        self.assertIsInstance(note, str)
        self.assertTrue(note, "明确没生效却返回了空串(会被当成成功)")
        matched = _RE_NOT_CONFIRMED.match(note)
        self.assertIsNotNone(matched, f"返回串格式不符: {note!r}")
        self.assertEqual(matched.group("rounds"), "3", "默认应重试 3 轮")
        self.assertEqual(matched.group("path"), "D:/x/cover.jpg")
        self.assertIn("像素前后一致", note)
        # 「3 轮」= 首查 1 轮 + 换路 2 轮(与 channels/publish.py::_confirm_cover 同口径)
        self.assertEqual(len(page.uploaded), 2, "换路轮数应是 rounds-1=2")

    # ── 6. fail-open:复检读不到封面区 ⇒ 当已生效 ──
    def test_06_fail_open_when_after_unreadable(self):
        page = LiveCoverPage()
        page.thumbs = []                      # 锚点/img 都没了(模拟改版)
        page.vertical_btn = {"ok": True, "text": "选择封面"}
        page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
        cap = _LogCapture()
        with patch.object(cover_mod, "_log", cap):
            note = _run(cover_mod._confirm_cover(
                page, "D:/x/cover.jpg",
                {"ok": True, "digest": _digest1(b"OLD")},
                {"ok": False, "why": "没找到封面缩略图"}))
        self.assertEqual(note, "", "判不了时必须 fail-open 当已生效,绝不当成失败")
        self.assertEqual(page.uploaded, [], "判不了时不该触发换路重试")
        self.assertIn("fail-open", cap.text())

    # ── 7. fail-open:换路后复检读不到 ⇒ 当已生效 ──
    def test_07_fail_open_when_retry_probe_unreadable(self):
        page = LiveCoverPage()
        page.visible_texts = {"竖封面3:4", "完成"}
        page.vertical_btn = {"ok": True, "text": "选择封面"}
        page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
        page.thumbs = [{"label": "竖封面3:4", "src": "s1"}]
        page.raise_on_shot = True             # 复读时截图直接抛
        same = _digest1(b"SAME")
        cap = _LogCapture()
        with patch.object(cover_mod, "_log", cap):
            note = _run(cover_mod._confirm_cover(
                page, "D:/x/cover.jpg",
                {"ok": True, "digest": same}, {"ok": True, "digest": same}))
        self.assertEqual(note, "", "复检读不到 ⇒ fail-open")
        self.assertEqual(len(page.uploaded), 1, "换路只应发生 1 次,读到判不了就停")

    # ── 8. 换路连编辑器都打不开 ⇒ 如实回报、不抛、不误投喂 ──
    def test_08_retry_cannot_reopen_reports_without_raising(self):
        page = LiveCoverPage()
        page.visible_texts = {"竖封面3:4"}     # 没有「选择封面/编辑封面」可点
        page.vertical_btn = {"ok": False, "why": "no-anchor"}
        same = _digest1(b"SAME")
        cap = _LogCapture()
        try:
            with patch.object(cover_mod, "_log", cap):
                note = _run(cover_mod._confirm_cover(
                    page, "D:/x/cover.jpg",
                    {"ok": True, "digest": same}, {"ok": True, "digest": same}))
        except Exception as exc:                     # noqa: BLE001
            self.fail(f"换路打不开编辑器时不许冒泡异常: {exc!r}")
        self.assertTrue(note)
        self.assertIn("未能换路重投喂", note)
        self.assertEqual(page.uploaded, [], "打不开编辑器却仍投喂了 input")

    # ── 11. 截图全抛异常 ⇒ fail-open,不冒泡 ──
    def test_11_screenshot_exception_is_fail_open(self):
        page = LiveCoverPage()
        page.vertical_btn = {"ok": True, "text": "选择封面"}
        page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
        page.thumbs = [{"label": "竖封面3:4", "src": "s1"}]
        page.raise_on_shot = True
        cap = _LogCapture()
        try:
            with patch.object(cover_mod, "_log", cap):
                note = _run(cover_mod._confirm_cover(
                    page, "D:/x/cover.jpg",
                    {"ok": True, "digest": _digest1(b"OLD")}, None))
        except Exception as exc:                     # noqa: BLE001
            self.fail(f"截图抛异常时不许冒泡: {exc!r}")
        self.assertEqual(note, "")
        self.assertIn("fail-open", cap.text())

    # ── 14. 兼容文案:既有用例按「像素前后一致」连续子串判假成功 ──
    def test_14_unchanged_detail_keeps_legacy_substring(self):
        _, detail = cover_mod._cover_verdict(
            {"ok": True, "digest": "D1"}, {"ok": True, "digest": "D1"})
        self.assertIn("像素前后一致", detail,
                      "tests/douyin_cover_fakes.py::7a 要求「像素前后一致」连续出现")


class DouyinCoverLiveEndToEndTests(unittest.TestCase):
    """第 9、10:走**完整** ``set_douyin_cover``(含第 4~9 步)的两条主路径。"""

    def _page(self, *, same_pixels: bool) -> LiveCoverPage:
        page = LiveCoverPage()
        page.visible_texts = {"竖封面3:4", "上传封面", "选择封面", "完成"}
        page.vertical_btn = {"ok": True, "text": "选择封面"}
        page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
        page.thumbs = [{"label": "竖封面3:4", "src": "s1"}]
        page.modal_present = False
        if same_pixels:
            page.shot_default = b"SAME"
        else:
            # 基线 2 张 OLD,之后 2 张 NEW(第 9 步第一次比对就命中变化)
            page.shot_seq = [b"OLD", b"OLD", b"NEW", b"NEW"]
            page.shot_default = b"NEW"
        return page

    def test_09_full_flow_success_returns_empty(self):
        page = self._page(same_pixels=False)
        cap = _LogCapture()
        with patch.object(cover_mod, "_log", cap):
            note = _run(cover_mod.set_douyin_cover(page, str(_COVER_FILE)))
        self.assertEqual(note, "", "像素已变 ⇒ 老口径仍返回空串(向后兼容)")
        self.assertEqual(page.uploaded,
                         [('input[data-bfc-upload="1"]', str(_COVER_FILE))])
        self.assertIn("封面已确认生效", cap.text())

    def test_10_full_flow_not_applied_returns_formatted_reason(self):
        page = self._page(same_pixels=True)
        cap = _LogCapture()
        try:
            with patch.object(cover_mod, "_log", cap):
                note = _run(cover_mod.set_douyin_cover(page, str(_COVER_FILE)))
        except Exception as exc:                     # noqa: BLE001
            self.fail(f"封面没生效也绝不许冒泡(会打断发布): {exc!r}")
        self.assertIsInstance(note, str)
        matched = _RE_NOT_CONFIRMED.match(note)
        self.assertIsNotNone(matched, f"返回串格式不符: {note!r}")
        self.assertEqual(matched.group("rounds"), "3")
        self.assertEqual(matched.group("path"), str(_COVER_FILE))
        # 失败出口必须撤掉注入的 hover-show 样式(否则污染同页后续像素/布局)
        self.assertFalse(page.hover_style_present)
        self.assertGreaterEqual(page.hover_removed, page.hover_injected)
        # 首查 1 次 + 换路 2 次 = 3 次投喂
        self.assertEqual(len(page.uploaded), 3)


class DouyinCoverLiveGuardTests(unittest.TestCase):
    """第 12、13:硬约束(不许新增 raise / 不许阻断发布)。"""

    def _src(self, name: str) -> str:
        import inspect
        return inspect.getsource(getattr(cover_mod, name))

    def test_12_confirm_helpers_have_no_raise_statement(self):
        for name in ("_cover_verdict", "_reopen_and_feed", "_confirm_cover"):
            with self.subTest(fn=name):
                src = self._src(name)
                self.assertIsNone(
                    _RE_RAISE_STMT.search(src),
                    f"{name} 里出现了 raise 语句 —— 确认逻辑只准加日志与重试")

    def test_12b_confirm_never_blocks_publish_static_shape(self):
        """静态形态:``_confirm_cover`` 里 ``unknown`` 分支必须紧跟 ``return ""``。"""
        src = self._src("_confirm_cover")
        self.assertIn('if verdict == "unknown":', src)
        window = src.split('if verdict == "unknown":')[1].splitlines()
        self.assertTrue(any(ln.strip().startswith("return \"\"")
                            for ln in window[:6]),
                        "fail-open 分支必须立刻返回空串(当已生效),不许继续折腾")

    def test_13_publish_layer_survives_new_failure_note(self):
        """发布层:封面返回**新的**失败串 ⇒ 发布照常走到点发布并成功。"""
        from tests.douyin_cover_fakes import run_publish

        media = _TMP_FILES / "clip.mp4"
        media.write_bytes(b"\x00\x00\x00\x18ftypmp42")

        note = ("封面未确认生效(3轮重试后仍未生效): "
                f"{_COVER_FILE}; 最后判据: 封面未确认生效(第 3/3 轮未生效,"
                f"像素前后一致(abc))")

        async def _fail(page, path):
            return note

        run = asyncio.run(run_publish(str(media), cover_path=str(_COVER_FILE),
                                      cover_impl=_fail))
        self.assertTrue(run["ok"], "封面新的失败串把发布搞失败了")
        self.assertEqual(run["btn"].clicked, 1, "封面失败后没点到发布按钮")
        self.assertEqual(run["cover_calls"], [str(_COVER_FILE)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
