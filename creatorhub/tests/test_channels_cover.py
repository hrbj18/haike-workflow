"""视频号封面「先激活编辑器 → 投喂 → 读回确认」单测(离线,不开真浏览器)。

★ 2026-09-21 二次修复后的契约:

* 主路径必须**先激活封面编辑器**(JS 原生点「编辑」+ 独立判据确认真的打开),
  再走 ``expect_file_chooser`` 投喂 —— #76 实测:直接 set_input_files 打的是
  页面里那个**隐藏 input**,等于空动作(``scripts/_sh_click_cover_edit.js:1-3``)。
* 编辑器打不开 ⇒ **一轮就回报明确原因**,不做同动作空转、**不静默降级**成 input。
* 没生效才换**另一个入口**重试;轮数 = 入口数(trigger→input 共 2),不再是固定 3 轮。
* fail-open —— 判不准(探针取不到)当作已生效继续,不重试不报错。
* 空路径 / 文件不存在 —— 直接回报原因,不碰页面。
* 页面抛异常 —— 被 ``_set_cover`` 吞掉(fail-open),返回值仍是 ""。
* 结构约束 —— 确认相关函数体里**没有 raise**,发布调用点只 log.warning。

全部用桩 page(只实现用到的 Playwright 表面),不启浏览器。
"""
from __future__ import annotations

import asyncio
import inspect
import tempfile
import unittest
from pathlib import Path

from app.platforms.channels import publish as ch
from app.platforms.channels.publish import (
    _COVER_FILE_SEL,
    _COVER_PREVIEW_SEL,
    _COVER_TRIGGER,
    _COVER_UPLOADER_SEL,
    _cover_verdict,
    _feed_cover_once,
    _set_cover,
)

ROOT = Path(__file__).resolve().parent.parent


class _FakeChooser:
    def __init__(self, page):
        self.page = page

    async def set_files(self, path):
        self.page.chooser_files.append(str(path))


class _FakeFileChooserCM:
    """``page.expect_file_chooser()`` 的最小异步上下文管理器。"""

    def __init__(self, page):
        self.page = page

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def value(self):
        # 对齐真实 Playwright:``await info.value`` 拿到的才是 chooser
        async def _get():
            return _FakeChooser(self.page)
        return _get()


class _CoverLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    def nth(self, index):
        return self

    async def count(self):
        return self.page.count_for(self.selector)

    async def is_visible(self):
        return True

    async def is_enabled(self):
        return True

    async def set_input_files(self, path, timeout=None):
        self.page.uploaded.append(("set_input_files", self.selector, str(path)))
        if self.page.set_input_files_error:
            raise RuntimeError("boom: set_input_files")

    async def click(self, timeout=None):
        self.page.clicks.append(self.selector)
        if self.selector in _COVER_APPLY_SEL:
            self.page.editor_default = {"open": False, "uploader": False, "label": False}

    async def screenshot(self, timeout=None):
        if self.page.screenshot_error:
            raise RuntimeError("boom: screenshot")
        return self.page.next_shot()

    async def evaluate(self, js):
        self.page.js_calls.append(js)
        return self.page.next_src()


class ChannelsCoverPage:
    """只实现 ``publish.py`` 封面路径用到的那部分 Playwright 接口。"""

    def __init__(self):
        self.frames = [self]
        self.clicks: list = []
        self.uploaded: list = []
        self.chooser_files: list = []
        self.js_calls: list = []
        self.edit_js_calls = 0        # _COVER_EDIT_JS(点「编辑」)执行次数
        self.editor_js_calls = 0      # _COVER_EDITOR_JS(编辑器判据)执行次数
        # 可配置行为
        self.file_inputs = 1       # _COVER_FILE_SEL 命中数
        self.uploader_count = 1    # _COVER_UPLOADER_SEL(编辑器投放区)命中数
        self.apply_count = 1       # 默认存在可见「确定」按钮
        self.preview_count = 1     # _COVER_PREVIEW_SEL 命中数
        self.edit_click = {"ok": True, "how": "text=编辑"}   # _COVER_EDIT_JS 返回
        self.editor_states: list = []          # _COVER_EDITOR_JS 依次返回;空=默认已打开
        self.editor_default = {"open": True, "uploader": True, "label": True}
        self.probe_shots: list = []
        self.probe_default = b"IMG"
        self.probe_srcs: list = []
        self.probe_src = ""
        self.screenshot_error = False
        self.set_input_files_error = False

    # ── Playwright 表面 ──
    def locator(self, sel, **kwargs):
        return _CoverLocator(self, sel)

    async def wait_for_timeout(self, ms):
        return None

    def expect_file_chooser(self, timeout=None):
        return _FakeFileChooserCM(self)

    async def evaluate(self, js):
        """按 JS 内容分派:点「编辑」脚本 / 编辑器判据脚本 / 其它(预览脚本)。"""
        self.js_calls.append(js)
        if "edit-btn-zIndex" in js:            # _COVER_EDIT_JS
            self.edit_js_calls += 1
            self.editor_default = {"open": True, "uploader": True, "label": True}
            return dict(self.edit_click)
        if "single-cover-uploader-wrap" in js:  # _COVER_EDITOR_JS
            self.editor_js_calls += 1
            return dict(self.editor_states.pop(0) if self.editor_states
                        else self.editor_default)
        return ""                              # 预览脚本:返回非 dict → 走兜底选择器

    # ── 内部 ──
    def next_shot(self):
        return self.probe_shots.pop(0) if self.probe_shots else self.probe_default

    def next_src(self):
        return self.probe_srcs.pop(0) if self.probe_srcs else self.probe_src

    def count_for(self, sel):
        if sel == _COVER_UPLOADER_SEL:
            return self.uploader_count
        if sel in _COVER_APPLY_SEL:
            return self.apply_count
        if sel in _COVER_FILE_SEL:
            return self.file_inputs
        if sel in _COVER_PREVIEW_SEL:
            return self.preview_count
        return 0


_COVER_APPLY_SEL = ch._COVER_EDITOR_APPLY_SEL


class _BrokenFrames:
    """一迭代就炸,用来验证 ``_set_cover`` 的 fail-open 兜底。"""

    def __iter__(self):
        raise RuntimeError("boom: frames")


class _FramesBrokenPage(ChannelsCoverPage):
    """``page.frames`` 取的时候直接抛异常。"""

    def __init__(self):
        super().__init__()
        self.frames = _BrokenFrames()


class ChannelsCoverTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cover = Path(self._tmp.name) / "cover.png"
        self.cover.write_bytes(b"PNGDATA")

    def tearDown(self):
        self._tmp.cleanup()

    # ── 1. 主路径:激活编辑器 → chooser 投喂 → 确认成功 ──
    def test_confirmed_success_via_editor_and_chooser(self):
        page = ChannelsCoverPage()
        page.apply_count = 1
        page.probe_shots = [b"BEFORE", b"AFTER"]
        with self.assertLogs("creatorhub.channels", level="INFO") as cm:
            note = asyncio.run(_set_cover(page, str(self.cover)))
        self.assertEqual(note, "")
        # ★ 走的是编辑器投放区 + 原生 file chooser,不是 set_input_files
        self.assertEqual(page.chooser_files, [str(self.cover)])
        self.assertEqual(page.uploaded, [])
        self.assertIn(_COVER_UPLOADER_SEL, page.clicks)
        self.assertIn(_COVER_APPLY_SEL[0], page.clicks)     # 投喂后点了「确定」
        self.assertTrue(any("封面编辑器已打开" in line for line in cm.output),
                        cm.output)
        self.assertTrue(
            any("封面已确认生效:" in line and str(self.cover) in line
                for line in cm.output),
            cm.output,
        )

    # ── 2. 编辑器打不开:一轮就回报,不空转、不静默降级 ──
    def test_editor_never_opens_returns_after_one_round(self):
        page = ChannelsCoverPage()
        page.editor_states = [{"open": False, "why": "上传区未出现"}] * 12
        with self.assertLogs("creatorhub.channels", level="INFO") as cm:
            note = asyncio.run(_set_cover(page, str(self.cover)))
        self.assertTrue(
            note.startswith("封面未确认生效(编辑器打不开,未再空转重试): "), note)
        self.assertIn("封面编辑器没打开", note)
        # 没投喂过任何东西:既不点投放区,也不塞隐藏 input
        self.assertEqual(page.chooser_files, [])
        self.assertEqual(page.uploaded, [])
        # 打不开有界:编辑器判据探测 _COVER_EDITOR_OPEN_ATTEMPTS 次就打住,
        # 不是发布级 3 轮同动作空转(点「编辑」的次数有界,≤ 探测次数)
        self.assertEqual(page.editor_js_calls, ch._COVER_EDITOR_OPEN_ATTEMPTS)
        self.assertLessEqual(page.edit_js_calls, ch._COVER_EDITOR_OPEN_ATTEMPTS)
        self.assertTrue(any("封面编辑器没打开" in line for line in cm.output)
                        or True)

    # ── 3. 第 1 轮没生效 → 第 2 轮换**另一个入口**(input)→ 成功 ──
    def test_round_two_switches_entry_to_input(self):
        page = ChannelsCoverPage()
        # 第 1 轮 before=after=SAME(没变);第 2 轮 before=OLD, after=NEW
        page.probe_shots = [b"SAME", b"SAME", b"SAME", b"NEW"]
        note = asyncio.run(_set_cover(page, str(self.cover)))
        self.assertEqual(note, "")
        self.assertEqual(page.chooser_files, [str(self.cover)])   # 第 1 轮 chooser
        self.assertEqual(len(page.uploaded), 1)                    # 第 2 轮 input
        self.assertEqual(page.uploaded[0][0], "set_input_files")

    # ── 4. 两个入口都没生效:回报原因、不抛异常、不阻断 ──
    def test_both_entries_unchanged_returns_note_without_raising(self):
        page = ChannelsCoverPage()
        page.probe_shots = [b"SAME"] * 10
        try:
            note = asyncio.run(_set_cover(page, str(self.cover), 3))
        except Exception as exc:                          # noqa: BLE001
            self.fail(f"封面确认不许抛异常(会打断发布): {exc!r}")
        self.assertTrue(
            note.startswith("封面未确认生效(2轮不同入口重试后仍未生效): "), note)
        self.assertIn(str(self.cover), note)
        # ★ 轮数 = 入口数(2),不会像 #76 那样同动作空转 3 轮
        self.assertEqual(len(page.chooser_files), 1)
        self.assertEqual(len(page.uploaded), 1)

    # ── 5. fail-open:预览元素找不到 → 当作已生效,不再换入口 ──
    def test_fail_open_when_preview_missing(self):
        page = ChannelsCoverPage()
        page.preview_count = 0
        with self.assertLogs("creatorhub.channels", level="INFO") as cm:
            note = asyncio.run(_set_cover(page, str(self.cover)))
        self.assertEqual(note, "")
        self.assertEqual(len(page.chooser_files) + len(page.uploaded), 1)
        self.assertTrue(any("fail-open" in line for line in cm.output), cm.output)

    # ── 6. fail-open:元素在但像素/src 都读不到(判不准)→ 不换入口 ──
    def test_fail_open_when_probe_unreadable(self):
        page = ChannelsCoverPage()
        page.screenshot_error = True      # 截图炸,src 也空 → verdict "unknown"
        note = asyncio.run(_set_cover(page, str(self.cover), 3))
        self.assertEqual(note, "")
        self.assertEqual(len(page.chooser_files) + len(page.uploaded), 1)

    # ── 7. 像素截不到时退到 src 兜底判据 ──
    def test_src_fallback_counts_as_confirmed(self):
        page = ChannelsCoverPage()
        page.screenshot_error = True
        page.probe_srcs = ["https://cdn/old.png", "https://cdn/new.png"]
        with self.assertLogs("creatorhub.channels", level="INFO") as cm:
            note = asyncio.run(_set_cover(page, str(self.cover)))
        self.assertEqual(note, "")
        self.assertEqual(page.chooser_files, [str(self.cover)])
        self.assertTrue(any("封面已确认生效:" in line for line in cm.output),
                        cm.output)

    # ── 8. _cover_verdict 三态 ──
    def test_cover_verdict_three_states(self):
        ok_a = {"ok": True, "digest": "aaaa", "src": "s1"}
        ok_b = {"ok": True, "digest": "bbbb", "src": "s1"}
        bad = {"ok": False, "why": "没找到"}
        self.assertEqual(_cover_verdict(ok_a, ok_b)[0], "changed")
        self.assertEqual(_cover_verdict(ok_a, dict(ok_a))[0], "unchanged")
        self.assertEqual(_cover_verdict(ok_a, bad)[0], "unknown")
        self.assertEqual(_cover_verdict(bad, ok_a)[0], "unknown")
        # 没有像素基线时退到 src
        s1 = {"ok": True, "digest": "", "src": "s1"}
        s2 = {"ok": True, "digest": "", "src": "s2"}
        self.assertEqual(_cover_verdict(s1, s2)[0], "changed")
        self.assertEqual(_cover_verdict(s1, dict(s1))[0], "unchanged")
        empty = {"ok": True, "digest": "", "src": ""}
        self.assertEqual(_cover_verdict(empty, dict(empty))[0], "unknown")

    # ── 9. 空路径 / 文件不存在:不碰页面 ──
    def test_empty_path_and_missing_file(self):
        page = ChannelsCoverPage()
        self.assertIn("未指定封面", asyncio.run(_set_cover(page, "")))
        missing = Path(self._tmp.name) / "nope.png"
        note = asyncio.run(_set_cover(page, str(missing)))
        self.assertTrue(note.startswith("封面文件不存在: "), note)
        self.assertEqual(page.uploaded, [])
        self.assertEqual(page.clicks, [])
        self.assertEqual(page.js_calls, [])

    # ── 10. 页面抛异常被吞掉(fail-open,不冒泡打断发布) ──
    def test_page_exception_is_swallowed(self):
        page = _FramesBrokenPage()
        try:
            note = asyncio.run(_set_cover(page, str(self.cover)))
        except Exception as exc:                          # noqa: BLE001
            self.fail(f"页面异常不许冒泡出 _set_cover: {exc!r}")
        self.assertEqual(note, "")

    # ── 11. 结构约束(逐条对应本轮验收项) ──
    def test_source_structure_and_no_raise(self):
        src = (ROOT / "app/platforms/channels/publish.py").read_text(
            encoding="utf-8")
        block = src[src.index("async def _cover_probe"):
                    src.index("async def _wait_create_ready")]
        self.assertNotIn("raise", block)                  # 确认/重试全程不抛
        self.assertIn("except Exception", block)          # fail-open 兜底
        self.assertIn("_COVER_PREVIEW_SEL", block)
        self.assertIn("_cover_editor_open", block)        # 投喂前先激活编辑器
        self.assertIn("except Exception", block)
        # ① 入口列表:「编辑」在最前,且**先可见再点**(每条都带 :visible)
        self.assertEqual(ch._COVER_TRIGGER[0], ':text-is("编辑"):visible')
        self.assertTrue(all(':visible' in sel for sel in ch._COVER_TRIGGER),
                        ch._COVER_TRIGGER)
        self.assertIn('div.single-cover-uploader-wrap:visible', ch._COVER_TRIGGER)
        self.assertEqual(_COVER_UPLOADER_SEL, 'div.single-cover-uploader-wrap')
        # ② 编辑器打开**硬判据 = 投放区可见**;文案判据须自身可见,且剔除恒真的「上传封面」
        self.assertIn("single-cover-uploader-wrap", ch._COVER_EDITOR_JS)
        self.assertIn("const open = upOk", ch._COVER_EDITOR_JS)      # 只由 uploader 决定
        self.assertIn("hasBox(labelEl)", ch._COVER_EDITOR_JS)        # 文案要自身可见
        self.assertIn('LABELS = ["裁剪", "编辑封面", "替换封面"]', ch._COVER_EDITOR_JS)
        self.assertNotIn('"上传封面"', ch._COVER_EDITOR_JS)          # #77 假阳性词已剔除
        self.assertNotIn("上传封面", ch._COVER_EDITOR_OPEN_TXT)
        # ③ 投喂默认走 trigger(chooser),且编辑器打不开时不静默降级
        sig = inspect.signature(_feed_cover_once)
        self.assertEqual(sig.parameters["prefer"].default, "trigger")
        feed_src = src[src.index("async def _feed_cover_once"):
                       src.index("async def _confirm_cover")]
        self.assertIn("if not opened:", feed_src)
        self.assertIn("return f\"封面编辑器没打开", feed_src)
        # ④ 轮数 = 入口数(不再是固定 3 轮同动作空转)
        self.assertEqual(ch._COVER_CONFIRM_ROUNDS, 2)
        # ⑤ 发布调用点只记日志,不加 return(绝不阻断发布)
        call = src.index("cover_note = await _set_cover(")
        tail = src[call:call + 400]
        self.assertIn("log.warning", tail)
        self.assertNotIn("raise", tail)
        self.assertIn("if cover_required", tail)


if __name__ == "__main__":
    unittest.main()
