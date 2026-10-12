"""快手「发布时设封面」单测(离线,不开真浏览器)。

覆盖(≥8 条):
* cover 层:空路径短路 / 文件不存在 / 成功(像素变化) / 像素未变假成功 /
  「上传封面」投放区未命中 / 弹层 3 轮都不收 / page 抛异常不冒泡
* publish 层:``cover_path`` 默认值向后兼容(空封面时 cover hook 完全不触发、
  发布照常;有封面时 hook 被调用一次;hook 失败时发布仍走到点发布)
* 结构约束:cover hook 在点「发布」之前;``cover.py`` 不得 import ``publish``

落盘隔离:封面像素指纹在**生产**里会真实落盘到 ``cover._DEBUG_DIR``;本模块导入时
把它重定向到一次性临时目录,故所有用例都不会往 ``data/debug`` 写假 PNG。
"""
from __future__ import annotations

import asyncio
import inspect
import tempfile
import unittest
from PIL import Image
from pathlib import Path
from unittest.mock import AsyncMock, patch

import app.main  # noqa: F401 - initializes the package import graph used by browser modules
from app.platforms.kuaishou import cover as cover_mod
from app.platforms.kuaishou import publish as pub_mod
from app.platforms.kuaishou.publish import publish_kuaishou, set_kuaishou_cover

ROOT = Path(__file__).resolve().parent.parent

# 测试期落盘隔离(用 mkdtemp 而非 TemporaryDirectory:宿主 safe-delete 会拦截清理)。
cover_mod._DEBUG_DIR = Path(tempfile.mkdtemp(prefix="chrc-kscover-debug-"))


# ────────────────────────── cover 层 fake ──────────────────────────
def _text_label(sel: str):
    """从 ``text="确认"`` / ``text=确认`` 里取文案;不是 text 选择器则 None。"""
    if sel.startswith('text="') and sel.endswith('"') and len(sel) > 7:
        return sel[6:-1]
    if sel.startswith("text=") and len(sel) > 5:
        return sel[5:]
    return None


class _KSThumb:
    """``locator`` 的截图句柄。"""

    def __init__(self, page):
        self.page = page

    async def screenshot(self, timeout=None, **kwargs):
        return self.page.next_shot()


class _KSLocator:
    def __init__(self, page, sel, *, count=None, visible=True):
        self.page = page
        self.sel = sel
        self._count = count
        self._visible = visible
        self.first = self

    async def count(self):
        if self._count is not None:
            return self._count
        return self.page.count_for(self.sel)

    async def is_visible(self, timeout=None):
        return self._visible

    async def scroll_into_view_if_needed(self, timeout=None):
        return None

    async def click(self, timeout=None):
        self.page.clicks.append(self.sel)

    def nth(self, index):
        return _KSThumb(self.page)

    async def screenshot(self, timeout=None, **kwargs):
        return self.page.next_shot()

    async def set_input_files(self, files, timeout=None):
        self.page.uploaded.append((self.sel, files))

    async def wait_for(self, state=None, timeout=None):
        return None

    async def fill(self, *args, **kwargs):
        return None

    async def press(self, *args, **kwargs):
        return None

    async def inner_text(self):
        return ""


class _KSKeyboard:
    def __init__(self, page):
        self.page = page

    async def press(self, key):
        self.page.keys.append(key)


class KSFakePage:
    """只实现 ``kuaishou/cover.py`` 用到的那部分 Playwright 接口。"""

    def __init__(self):
        self.url = "https://cp.kuaishou.com/article/publish/video"
        self.frames = [self]
        self.keyboard = _KSKeyboard(self)
        self.clicks: list[str] = []
        self.uploaded: list[tuple] = []
        self.keys: list[str] = []
        self.js_calls: list[str] = []
        # 可配置行为
        self.visible_texts: set[str] = set()
        self.thumb_count = 1
        self.upload_mark: dict = {"total": 0, "selected": None}
        self.cover_full_editor_count = 1
        self.modal_present = False
        self.shot_seq: list[bytes] = []
        self.shot_default = b"IMG"
        self.raise_on = ""            # "" | "locator" | "evaluate"

    # ── Playwright 表面 ──
    def locator(self, sel, **kwargs):
        if self.raise_on == "locator":
            raise RuntimeError("locator boom")
        return _KSLocator(self, sel)

    async def wait_for_timeout(self, ms):
        return None

    async def evaluate(self, js, *args):
        self.js_calls.append(js)
        if self.raise_on == "evaluate":
            raise RuntimeError("evaluate boom")
        if "ant-modal" in js:
            return self.modal_present
        if "data-bfc-upload" in js:
            return dict(self.upload_mark)
        return None

    # ── 内部 ──
    def next_shot(self):
        return self.shot_seq.pop(0) if self.shot_seq else self.shot_default

    def count_for(self, sel):
        if "cover-full-editor" in sel:
            return self.cover_full_editor_count
        if "data-bfc-upload" in sel:
            return 1 if self.upload_mark.get("selected") else 0
        if "cover" in sel:
            return self.thumb_count
        label = _text_label(sel)
        if label is not None:
            return 1 if label in self.visible_texts else 0
        return 0


# ────────────────────────── publish 层 fake ──────────────────────────
class _PubBodyLocator:
    async def inner_text(self):
        return ""


class _PubBtn:
    def __init__(self):
        self.clicked = 0
        self.click_error = False

    async def scroll_into_view_if_needed(self, timeout=None):
        return None

    async def bounding_box(self):
        return {"x": 1.0, "y": 2.0, "width": 10.0, "height": 5.0}

    async def evaluate(self, expr):
        return "<div>发布</div>"

    async def click(self, timeout=None):
        self.clicked += 1
        if self.click_error:
            raise TimeoutError("ambiguous click timeout")


class _PubFakePage:
    def __init__(self):
        self.url = "https://cp.kuaishou.com/article/manage/video"

    def locator(self, sel, **kwargs):
        return _PubBodyLocator()

    def on(self, *args, **kwargs):
        return None

    async def goto(self, url, wait_until=None, timeout=None):
        self.url = url

    async def wait_for_timeout(self, ms):
        return None


class _PubCtx:
    def __init__(self, page):
        self.page = page
        self.closed = False

    async def new_page(self):
        return self.page

    async def close(self):
        self.closed = True


class _PubMgr:
    def __init__(self, ctx):
        self.ctx = ctx

    async def open_background(self, identity):
        return self.ctx

    async def stop_minimize_hold(self, identity):
        return None


async def _run_publish(media_path: str, cover_path: str = "", cover_impl=None,
                       click_error: bool = False, **publish_kwargs):
    """用 fake 驱动 ``publish_kuaishou``,返回关键观测点。"""
    page = _PubFakePage()
    ctx = _PubCtx(page)
    mgr = _PubMgr(ctx)
    btn = _PubBtn()
    btn.click_error = click_error
    cover_calls: list = []

    async def _rec(page_, path_, **_kwargs):
        cover_calls.append(path_)
        if cover_impl is not None:
            return await cover_impl(page_, path_)
        return ""

    async def _fake_visible_text(page_, keywords):
        if keywords is pub_mod._SUCCESS_KW:
            return "发布成功"
        return ""

    with patch.object(pub_mod, "_upload_files", AsyncMock(return_value=True)), \
         patch.object(pub_mod, "_wait_editor", AsyncMock(return_value=True)), \
         patch.object(pub_mod, "_wait_upload_done", AsyncMock(return_value=True)), \
         patch.object(pub_mod, "_dismiss_overlays", AsyncMock(return_value=None)), \
         patch.object(pub_mod, "_choose_visibility", AsyncMock(return_value=None)), \
         patch.object(pub_mod, "_dump", AsyncMock(return_value="")), \
         patch.object(pub_mod, "_primary_publish_button", AsyncMock(return_value=btn)), \
         patch.object(pub_mod, "_visible_text", _fake_visible_text), \
         patch.object(pub_mod, "_verify_on_manage",
                      AsyncMock(return_value=(True, "核对通过"))), \
         patch.object(pub_mod, "set_kuaishou_cover", _rec):
        kwargs = {"timeout_seconds": 1}
        if cover_path:
            kwargs["cover_path"] = cover_path
        ok, url, err = await publish_kuaishou(
            mgr, None, "", "video", "", "", [media_path], **kwargs,
            **publish_kwargs)

    return {"ok": ok, "url": url, "err": err, "btn": btn,
            "cover_calls": cover_calls, "page": page}


class KuaishouCoverTests(unittest.TestCase):
    def _real_cover(self, tmp: Path) -> str:
        path = tmp / "cover.jpg"
        Image.new("RGB", (600, 800), "#123456").save(path, "JPEG")
        return str(path)

    # ── 1. 空路径 → 直接返回且不碰页面 ──
    def test_empty_cover_path_short_circuits_without_side_effects(self):
        page = KSFakePage()
        note = asyncio.run(set_kuaishou_cover(page, ""))
        self.assertEqual(note, "")
        self.assertEqual(page.clicks, [])
        self.assertEqual(page.js_calls, [])
        self.assertEqual(page.keys, [])
        self.assertEqual(page.uploaded, [])

    # ── 2. 文件不存在 → 返回原因串,不抛异常,不交互 ──
    def test_missing_cover_file_returns_reason_without_raising(self):
        page = KSFakePage()
        note = asyncio.run(
            set_kuaishou_cover(page, "D:/no_such_dir/no_such_cover.png"))
        self.assertEqual(note, "封面文件不存在: D:/no_such_dir/no_such_cover.png")
        self.assertEqual(page.js_calls, [])

    # ── 3. 成功:投喂成功且像素变化 → 返回空串 ──
    def test_feed_success_and_pixel_change_returns_empty(self):
        with tempfile.TemporaryDirectory(prefix="chrc-ks-cover-ok-") as tmp:
            cover = self._real_cover(Path(tmp))
            page = KSFakePage()
            page.visible_texts = {"确认"}
            page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 15}}
            page.modal_present = False
            page.shot_seq = [b"BASE", b"AFTER"]
            page.shot_default = b"AFTER"
            note = asyncio.run(set_kuaishou_cover(page, cover))
            self.assertEqual(note, "")
            self.assertEqual(page.uploaded[0][0], 'input[data-bfc-upload="1"]')
            self.assertTrue(page.uploaded[0][1].endswith(".ks-upload.png"))
            self.assertTrue(Path(page.uploaded[0][1]).is_file())
            self.assertTrue(any("确认" in c for c in page.clicks))

    # ── 4. 像素没变 → 返回原因串 ──
    def test_unchanged_pixel_returns_reason(self):
        with tempfile.TemporaryDirectory(prefix="chrc-ks-cover-same-") as tmp:
            cover = self._real_cover(Path(tmp))
            page = KSFakePage()
            page.visible_texts = {"确认"}
            page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 15}}
            page.modal_present = False
            page.shot_seq = []
            page.shot_default = b"SAME"
            note = asyncio.run(set_kuaishou_cover(page, cover))
            self.assertTrue(note, "像素未变应返回非空原因")
            self.assertIn("像素前后一致", note)

    # ── 5. 弹层 3 轮都不收 → 返回原因串 ──
    def test_modal_never_closes_returns_reason(self):
        with tempfile.TemporaryDirectory(prefix="chrc-ks-cover-stuck-") as tmp:
            cover = self._real_cover(Path(tmp))
            page = KSFakePage()
            page.visible_texts = {"确认"}
            page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 15}}
            page.modal_present = True          # 永远收不起来
            page.shot_seq = [b"BASE", b"AFTER"]
            page.shot_default = b"AFTER"
            note = asyncio.run(set_kuaishou_cover(page, cover))
            self.assertTrue(note, "弹层未收起应返回非空原因")
            self.assertIn("收不起来", note)

    # ── 6. 找不到 file input → 返回原因串且不抛异常 ──
    def test_no_file_input_returns_reason_without_raising(self):
        with tempfile.TemporaryDirectory(prefix="chrc-ks-cover-noinput-") as tmp:
            cover = self._real_cover(Path(tmp))
            page = KSFakePage()
            page.upload_mark = {"total": 3, "selected": None}
            page.modal_present = False
            note = asyncio.run(set_kuaishou_cover(page, cover))
            self.assertTrue(note, "找不到投放区应返回非空原因")
            self.assertIn("投放区", note)
            self.assertEqual(page.uploaded, [])

    # ── 7. page 抛异常 → 返回原因串不抛 ──
    def test_page_exception_returns_reason_without_raising(self):
        with tempfile.TemporaryDirectory(prefix="chrc-ks-cover-boom-") as tmp:
            cover = self._real_cover(Path(tmp))
            for mode in ("locator", "evaluate"):
                with self.subTest(mode=mode):
                    page = KSFakePage()
                    page.raise_on = mode
                    note = asyncio.run(set_kuaishou_cover(page, cover))
                    self.assertIsInstance(note, str)
                    self.assertTrue(note, f"{mode}: 异常路径应返回非空原因")

    # ── 8. cover_path 默认值不破坏旧调用 ──
    def test_cover_path_default_is_backward_compatible(self):
        params = inspect.signature(publish_kuaishou).parameters
        self.assertIn("cover_path", params)
        self.assertEqual(params["cover_path"].default, "")
        # 新的严格策略参数排在 cover_path 后；旧位置参数调用保持兼容。
        self.assertLess(list(params).index("allow_save"),
                        list(params).index("cover_path"))
        # 旧口径调用(完全不传 cover_path)必须能跑通,且不触发封面 hook
        with tempfile.TemporaryDirectory(prefix="chrc-ks-cover-old-") as tmp:
            media = Path(tmp) / "fake.mp4"
            media.write_bytes(b"\x00\x00\x00\x18ftypmp42")
            run = asyncio.run(_run_publish(str(media)))
            self.assertTrue(run["ok"], f"旧调用应发布成功: {run['err']!r}")
            self.assertEqual(run["cover_calls"], [])
            self.assertEqual(run["btn"].clicked, 1)

    # ── 9. 有封面 → hook 被调用一次且带正确路径;hook 失败不阻断发布 ──
    def test_cover_hook_called_and_failure_does_not_block_publish(self):
        with tempfile.TemporaryDirectory(prefix="chrc-ks-cover-hook-") as tmp:
            media = Path(tmp) / "fake.mp4"
            media.write_bytes(b"\x00\x00\x00\x18ftypmp42")
            cover = self._real_cover(Path(tmp))

            run_a = asyncio.run(_run_publish(str(media), cover_path=cover))
            self.assertEqual(run_a["cover_calls"], [cover])
            self.assertTrue(run_a["ok"])
            self.assertEqual(run_a["btn"].clicked, 1)

            async def _fail(page_, path_):
                return "封面文件不存在: x"

            run_b = asyncio.run(_run_publish(str(media), cover_path=cover,
                                             cover_impl=_fail))
            self.assertTrue(run_b["ok"], "封面失败不得阻断发布")
            self.assertEqual(run_b["btn"].clicked, 1)

    # ── 10. monitor 把 cover_path 传到 publish_kuaishou ──
    def test_monitor_passes_cover_path_to_publish_kuaishou(self):
        src = (ROOT / "app/engine/monitor.py").read_text(encoding="utf-8")
        i_ks = src.index("publish_kuaishou(")
        i_ch = src.index("publish_channels(")
        seg = src[i_ks:i_ch]
        self.assertIn("cover_path=cover_path", seg)

    # ── 11. 结构约束:cover hook 在点「发布」之前;cover.py 不 import publish ──
    def test_cover_hook_inserted_before_publish_click(self):
        src = (ROOT / "app/platforms/kuaishou/publish.py").read_text(
            encoding="utf-8")
        i_cover = src.index("await set_kuaishou_cover(page, cover_path)")
        i_click = src.index("await button.click(timeout=5000)")
        self.assertLess(i_cover, i_click)

    def test_cover_module_does_not_import_publish(self):
        src = inspect.getsource(cover_mod)
        self.assertNotIn("from .publish", src)
        self.assertNotIn("import publish", src)


if __name__ == "__main__":
    unittest.main()
