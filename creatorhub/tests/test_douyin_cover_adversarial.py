"""抖音竖封面(best-effort)独立对抗验证 —— 由 QA 另写,不复用 Engineer 的 fake 逻辑。

与 ``tests/douyin_cover_fakes.py`` 刻意解耦:
* 本文件自带 ``AdvCoverPage`` / ``AdvPubPage``,只实现 cover.py / publish.py 真正
  用到的 Playwright 表面,并由本文件独立断言。
* 场景是**对抗性**的(超时/异常/文件损坏/按钮点不中/改版缺锚点/必须成对清理的
  注入样式),目标不是复现「绿」,而是尝试把「不阻断发布」与「不误点/不残留」
  这两个硬约束打穿。

覆盖 7 类:
  1. set_douyin_cover 内部步骤抛 TimeoutError/RuntimeError ⇒ 发布仍走到 btn.click() 且 ok=True
  2. cover_path="" ⇒ set_douyin_cover 零调用,页面调用序列等价「无此功能」
  3. 封面文件不存在 / 空文件 / 非图片 ⇒ 不冒泡异常,只记日志
  4. 「完成」一直点不中 ⇒ 有超时上限,不无限挂
  5. 找不到竖封面锚点(模拟改版)⇒ 返回失败原因,绝不误喂别的 input[type=file]
  6. 封面成功但发布失败 ⇒ 错误信息不得把封面成功当成发布成功
  7. 连续两次调用不残留注入的 <style id="chrc-hover-show">

跑法: ./.venv/Scripts/python.exe scripts/_qa_run_unittests.py test_douyin_cover_adversarial
或直接: ./.venv/Scripts/python.exe tests/test_douyin_cover_adversarial.py
"""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.platforms.douyin import cover as cover_mod
from app.platforms.douyin import publish as pub_mod
from app.platforms.douyin.publish import publish_douyin

# 落盘隔离:本文件直接调 set_douyin_cover,而 cover.py::_cover_signature 会**真实落盘**
# 到 _DEBUG_DIR ⇒ 若不重定向,**单独跑本文件**就会往取证目录 data/debug/ 写 1 字节假
# PNG(命名与真机产物一致,足以误导「真机跑过」的判断)。
# 用 mkdtemp 而非 TemporaryDirectory:避开宿主 safe-delete 对清理的拦截
# (那是 tests/test_guide_site.py 既有 ERROR 的成因),清理永不报错。
cover_mod._DEBUG_DIR = Path(tempfile.mkdtemp(prefix="dy_cover_adv_"))

# ───────────────────── 独立 cover 层 fake(可观测样式注入/清理)─────────────────────
def _text_label(sel: str):
    if sel.startswith('text="') and sel.endswith('"') and len(sel) > 7:
        return sel[6:-1]
    if sel.startswith("text=") and len(sel) > 5:
        return sel[5:]
    return None


class _AdvThumb:
    def __init__(self, page):
        self.page = page

    async def screenshot(self, timeout=None, **kwargs):
        return self.page.next_shot()


class _AdvCoverLocator:
    def __init__(self, page, sel):
        self.page = page
        self.sel = sel
        self.first = self

    async def count(self):
        p = self.page
        if "chrc-vcover" in self.sel:
            return 1 if p.vertical_btn.get("ok") else 0
        if "bfc-upload" in self.sel:
            return 1 if (p.upload_mark or {}).get("selected") else 0
        if "bfc-thumb" in self.sel:
            return len(p.thumbs)
        label = _text_label(self.sel)
        if label is not None:
            return 1 if label in p.visible_texts else 0
        return 0

    async def is_visible(self, timeout=None):
        return True

    async def scroll_into_view_if_needed(self, timeout=None):
        self.page.ops.append(("scroll", self.sel))
        return None

    async def click(self, timeout=None):
        self.page.ops.append(("click", self.sel))
        lab = _text_label(self.sel)
        if lab is not None:
            self.page.clicked_labels.append(lab)
        if self.page.raise_on_click:
            raise self.page.raise_on_click

    def nth(self, index):
        return _AdvThumb(self.page)

    async def screenshot(self, timeout=None, **kwargs):
        return self.page.next_shot()

    async def set_input_files(self, files, timeout=None):
        self.page.ops.append(("upload", self.sel))
        self.page.uploaded.append((self.sel, files))
        if self.page.raise_on_upload:
            raise self.page.raise_on_upload


class _AdvKeyboard:
    def __init__(self, page):
        self.page = page

    async def press(self, key):
        self.page.keys.append(key)


class AdvCoverPage:
    """驱动真实 ``cover_mod.set_douyin_cover`` 的最小 Playwright fake。"""

    def __init__(self):
        self.url = "https://creator.douyin.com/creator-micro/content/post/video"
        self.frames = [self]
        self.keyboard = _AdvKeyboard(self)
        self.ops: list[tuple] = []
        self.clicked_labels: list[str] = []
        self.uploaded: list[tuple] = []
        self.keys: list[str] = []
        self.waits: list[int] = []
        self.js_calls: list[str] = []
        # 可配置行为
        self.visible_texts: set[str] = set()
        self.vertical_btn: dict = {"ok": False}
        self.upload_mark: dict = {"total": 0, "selected": None}
        self.thumbs: list[dict] = []
        self.shot_seq: list[bytes] = []
        self.shot_default = b"DEF"
        self.raise_on_click = None
        self.raise_on_upload = None
        self.raise_on_clear = False
        # 注入样式在 DOM 中的存续状态(用于对抗 #7)
        self.style_present = False
        self.style_injected = 0
        self.style_removed = 0

    def locator(self, sel, **kwargs):
        return _AdvCoverLocator(self, sel)

    async def wait_for_timeout(self, ms):
        self.waits.append(ms)

    async def evaluate(self, js, *args):
        self.js_calls.append(js)
        if "data-bfc-upload" in js:
            return dict(self.upload_mark)
        if "data-bfc-thumb" in js:
            return {"anchors": len(self.thumbs), "marked": list(self.thumbs)}
        if "data-chrc-vcover" in js:
            return dict(self.vertical_btn)
        if "createElement" in js:           # _force_show_hover(注入)
            self.style_present = True
            self.style_injected += 1
            return True
        if "getElementById" in js:          # _clear_hover_show(移除)
            if self.raise_on_clear:
                raise RuntimeError("clear boom")
            self.style_present = False
            self.style_removed += 1
            return None
        return None

    def get_by_text(self, text, exact=False):
        return _AdvCoverLocator(self, f"text={text}")

    def next_shot(self):
        return self.shot_seq.pop(0) if self.shot_seq else self.shot_default


# ───────────────────── 独立 publish 层 fake(同时兼容 cover 层表面)─────────────────────
class _AdvPubLocator:
    def __init__(self, page, sel, count=1, visible=True):
        self.page = page
        self.sel = sel
        self._count = count
        self._visible = visible
        self.first = self

    async def count(self):
        return self._count

    async def is_visible(self, timeout=None):
        return self._visible

    async def scroll_into_view_if_needed(self, timeout=None):
        return None

    async def click(self, timeout=None):
        self.page.clicks.append(self.sel)
        self.page.ops.append(("click", self.sel))

    async def wait_for(self, state=None, timeout=None):
        return None

    async def fill(self, *a, **k):
        return None

    async def press(self, *a, **k):
        return None

    async def set_input_files(self, files, timeout=None):
        self.page.uploaded.append((self.sel, files))

    async def screenshot(self, timeout=None, **kwargs):
        return b"X"

    def nth(self, index):
        return self

    async def inner_text(self):
        return ""


class _AdvBtn:
    def __init__(self):
        self.clicked = 0

    async def is_enabled(self):
        return True

    async def scroll_into_view_if_needed(self, timeout=None):
        return None

    async def click(self, timeout=None):
        self.clicked += 1


class AdvPubPage:
    """驱动 ``publish_douyin`` 的最小 fake;同时实现 cover 层需要的 evaluage/locator。"""

    def __init__(self):
        self.url = "https://creator.douyin.com/creator-micro/content/upload"
        self.frames = [self]
        self.keyboard = _AdvKeyboard(self)
        self.clicks: list[str] = []
        self.uploaded: list[tuple] = []
        self.ops: list[tuple] = []
        self.waits: list[int] = []
        self.gotos: list[str] = []

    def locator(self, sel, **kwargs):
        return _AdvPubLocator(self, sel)

    async def wait_for_timeout(self, ms):
        self.waits.append(ms)

    async def goto(self, url, wait_until=None, timeout=None):
        self.url = url
        self.gotos.append(url)

    async def evaluate(self, js, *args):
        if "data-bfc-thumb" in js:
            return {"anchors": 0, "marked": []}
        if "data-bfc-upload" in js:
            return {"total": 0, "selected": None}
        if "data-chrc-vcover" in js:
            return {"ok": False, "why": "no-anchor"}
        return {}

    async def screenshot(self, path=None, full_page=False):
        return None

    async def inner_text(self, sel="body"):
        return ""

    def on(self, *a, **k):
        return None

    def get_by_text(self, text, exact=False):
        return _AdvPubLocator(self, f"text={text}", count=0)


class _AdvCtx:
    def __init__(self, page):
        self.page = page
        self.closed = False

    async def new_page(self):
        return self.page

    async def close(self):
        self.closed = True


class _AdvMgr:
    def __init__(self, ctx):
        self.ctx = ctx

    async def open_background(self, identity):
        return self.ctx

    async def stop_minimize_hold(self, identity):
        return None


async def _default_page_state(page):
    return {"texts": [], "videos": 0, "url": page.url}


async def _run_publish(media_path: str, cover_path: str = "",
                       cover_override=None, cover_module_patches=None,
                       force_fail: bool = False):
    """驱动 ``publish_douyin``;返回观测点。

    cover_override:   直接替换 ``pub_mod.set_douyin_cover``(async(page, path))。
    cover_module_patches: {name: value} 打到 ``cover_mod`` 上的补丁(用来验证真实
                        set_douyin_cover 的内部步骤抛异常时发布是否照常)。
    force_fail:       让平台返回失败文案,用于「封面成功但发布失败」。
    """
    page = AdvPubPage()
    ctx = _AdvCtx(page)
    mgr = _AdvMgr(ctx)
    btn = _AdvBtn()
    cover_calls: list[str] = []

    real_cover = cover_mod.set_douyin_cover

    async def _recorder(page_, path_):
        cover_calls.append(path_)
        return await real_cover(page_, path_)

    if cover_override is not None:
        cover_entry = cover_override
    else:
        cover_entry = _recorder

    async def _fake_visible_any(page_, keywords):
        if keywords is pub_mod._FAIL_KW:
            return "发布失败" if force_fail else ""
        if keywords is pub_mod._SUCCESS_KW:
            return "" if force_fail else "发布成功"
        if keywords is pub_mod._VERIFY_KW:
            return ""
        return ""

    patches = [
        patch.object(pub_mod, "_dump", AsyncMock(return_value="")),
        patch.object(pub_mod, "_wait_editor", AsyncMock(return_value=True)),
        patch.object(pub_mod, "_page_state", _default_page_state),
        patch.object(pub_mod, "_state_sig", lambda state: "SIG"),
        patch.object(pub_mod, "_primary_publish_button", AsyncMock(return_value=btn)),
        patch.object(pub_mod, "_visible_success_hits", lambda state: []),
        patch.object(pub_mod, "_visible_any", _fake_visible_any),
        patch.object(pub_mod, "_verify_on_manage", AsyncMock(return_value=(True, "OK"))),
        patch.object(pub_mod, "set_douyin_cover", cover_entry),
    ]
    for name, value in (cover_module_patches or {}).items():
        patches.append(patch.object(cover_mod, name, value))

    with _exitstack(patches):
        ok, url, err = await pub_mod.publish_douyin(
            mgr, None, "", "video", "", "", [media_path],
            cover_path=cover_path, timeout_seconds=1)

    return {"ok": ok, "url": url, "err": err, "btn": btn,
            "cover_calls": cover_calls, "page": page, "ctx": ctx}


class _exitstack:
    """轻量 contextmanager.ExitStack 替身,避免额外 import。"""

    def __init__(self, patches):
        self._patches = patches

    def __enter__(self):
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False


# ───────────────────── 临时文件(不触发 safe-delete 清理)─────────────────────
_TMPROOT = Path(tempfile.mkdtemp(prefix="chrc-adv-"))
_MEDIA = _TMPROOT / "clip.mp4"
_MEDIA.write_bytes(b"\x00\x00\x00\x18ftypmp42")
_COVER_OK = _TMPROOT / "cover-1080x1440.jpg"
_COVER_OK.write_bytes(b"\xff\xd8\xff\xff\xd9")
_COVER_EMPTY = _TMPROOT / "empty.jpg"          # 0 字节
_COVER_EMPTY.write_bytes(b"")
_COVER_NOTIMG = _TMPROOT / "notimage.jpg"      # 文本冒充图片
_COVER_NOTIMG.write_text("this is not an image", encoding="utf-8")
_COVER_MISSING = str(_TMPROOT / "nope-404.png")


# ───────────────────── 场景 ─────────────────────
class DouyinCoverAdversarialTests(unittest.TestCase):
    # ── #1 内部步骤抛异常 ⇒ 发布照常 ──
    def test_01_internal_step_raises_timeout_publish_still_clicks(self):
        for name, boom in (("TimeoutError", TimeoutError),
                           ("RuntimeError", RuntimeError)):
            stack = {
                "_scroll_text_into_view": AsyncMock(side_effect=boom("cover step")),
            }
            r = asyncio.run(_run_publish(str(_MEDIA), cover_path=str(_COVER_OK),
                                         cover_module_patches=stack))
            print(f"[ADV-1 {name}] ok={r['ok']} btn_clicked={r['btn'].clicked} "
                  f"cover_calls={len(r['cover_calls'])} err={r['err']!r}")
            self.assertTrue(r["ok"], f"{name}: 封面内部抛异常导致发布失败")
            self.assertEqual(r["btn"].clicked, 1, f"{name}: 未点到发布按钮")

    def test_01b_deferred_step_raises_after_scroll(self):
        # 走得更深:滚动成功后再抛(验证不是只有「第一步」被兜住)
        for name, boom in (("TimeoutError", TimeoutError),
                           ("RuntimeError", RuntimeError)):
            stack = {
                "_scroll_text_into_view": AsyncMock(return_value=True),
                "_open_cover_editor": AsyncMock(side_effect=boom("open editor")),
            }
            r = asyncio.run(_run_publish(str(_MEDIA), cover_path=str(_COVER_OK),
                                         cover_module_patches=stack))
            print(f"[ADV-1b {name}] ok={r['ok']} btn_clicked={r['btn'].clicked} "
                  f"err={r['err']!r}")
            self.assertTrue(r["ok"], f"{name}: 深层步骤抛异常导致发布失败")
            self.assertEqual(r["btn"].clicked, 1)

    def test_01c_boundary_override_raises(self):
        async def boom(page, path):
            raise TimeoutError("boundary")
        r = asyncio.run(_run_publish(str(_MEDIA), cover_path=str(_COVER_OK),
                                     cover_override=boom))
        print(f"[ADV-1c boundary] ok={r['ok']} btn_clicked={r['btn'].clicked}")
        self.assertTrue(r["ok"])
        self.assertEqual(r["btn"].clicked, 1)

    # ── #2 空 cover_path ⇒ 零调用 + 与「无此功能」等价 ──
    def test_02_empty_cover_path_zero_calls_and_equivalent(self):
        r_empty = asyncio.run(_run_publish(str(_MEDIA), cover_path=""))
        self.assertEqual(r_empty["cover_calls"], [],
                         "cover_path 为空却仍调用了 set_douyin_cover")
        self.assertTrue(r_empty["ok"])
        self.assertEqual(r_empty["btn"].clicked, 1)
        # 与「封面逻辑为 no-op」对比:唯一差异只能是那一次 gated 的 800ms 等待。
        # 注意:常规发布流程本身也含一次 800ms 等待(publish.py L465),故用「计数差 1」
        # 而不是 assertNotIn —— 其余等待序列必须逐字一致。
        async def noop_cover(page, path):
            return ""
        r_noop = asyncio.run(_run_publish(str(_MEDIA), cover_path=str(_COVER_OK),
                                          cover_override=noop_cover))
        empty_w = r_empty["page"].waits
        noop_w = r_noop["page"].waits
        print(f"[ADV-2] empty_waits={len(empty_w)} noop_waits={len(noop_w)} "
              f"empty_800={empty_w.count(800)} noop_800={noop_w.count(800)}")
        self.assertEqual(noop_w.count(800), empty_w.count(800) + 1,
                         "封面 hook 未带来且仅带来一次 800ms 等待")
        self.assertEqual([w for w in noop_w if w != 800],
                         [w for w in empty_w if w != 800],
                         "空 cover_path 的页面等待序列与「无封面 hook」不一致")

    # ── #3 文件不存在 / 空文件 / 非图片 ⇒ 不冒泡 ──
    def test_03_bad_cover_files_never_raise(self):
        cases = [("missing", _COVER_MISSING), ("empty", str(_COVER_EMPTY)),
                 ("not-image", str(_COVER_NOTIMG))]
        for name, path in cases:
            page = AdvCoverPage()          # 页面什么锚点都没有
            try:
                note = asyncio.run(cover_mod.set_douyin_cover(page, path))
            except Exception as exc:       # noqa: BLE001
                self.fail(f"{name}: set_douyin_cover 冒泡了异常 {exc!r}")
            print(f"[ADV-3 {name}] note={note!r} uploaded={page.uploaded}")
            self.assertIsInstance(note, str)
            self.assertTrue(note, f"{name}: 坏文件却返回了空串(会被当成成功)")
            self.assertEqual(page.uploaded, [], f"{name}: 坏文件却投喂了 input")
        # 发布层:即使封面层直接抛 FileNotFoundError/ValueError 也不阻断
        for name, exc in (("FileNotFoundError", FileNotFoundError),
                          ("ValueError", ValueError)):
            async def boom(page, path, _e=exc):
                raise _e("bad cover")
            r = asyncio.run(_run_publish(str(_MEDIA), cover_path=str(_COVER_OK),
                                         cover_override=boom))
            print(f"[ADV-3 pub {name}] ok={r['ok']} btn={r['btn'].clicked}")
            self.assertTrue(r["ok"])
            self.assertEqual(r["btn"].clicked, 1)

    # ── #4 「完成」点不中 ⇒ 有上限,不挂死 ──
    def test_04_finish_unclickable_is_bounded(self):
        page = AdvCoverPage()
        page.visible_texts = {"竖封面3:4", "上传封面"}     # 故意没有 完成/确定/保存
        page.vertical_btn = {"ok": True, "text": "选择封面"}
        page.thumbs = [{"label": "竖封面3:4", "src": "s1"}]
        page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
        note = asyncio.run(asyncio.wait_for(
            cover_mod.set_douyin_cover(page, str(_COVER_OK)), timeout=20))
        finish_waits = [w for w in page.waits if w == 2500]
        print(f"[ADV-4] note={note!r} finish_retry_waits={len(finish_waits)} "
              f"uploaded={bool(page.uploaded)}")
        self.assertIn("完成", note)
        self.assertEqual(page.uploaded,
                         [('input[data-bfc-upload="1"]', str(_COVER_OK))])
        self.assertLessEqual(len(finish_waits), 10,
                             "「完成」重试没有上限(可能无限挂)")
        self.assertGreaterEqual(len(finish_waits), 1)

    # ── #5 找不到竖封面锚点 ⇒ 不误喂别的 file input ──
    def test_05_no_vertical_anchor_no_misfeed(self):
        page = AdvCoverPage()
        # 模拟改版:有「上传封面」入口,但页面里存在 3 个 file input,且没有一个
        # 同时命中「拖拽」+「上传封面」——JS 判据故意不标任何一个。
        page.visible_texts = {"选择封面", "上传封面"}
        page.vertical_btn = {"ok": False, "why": "no-anchor"}
        page.thumbs = []
        page.upload_mark = {"total": 3, "selected": None}
        note = asyncio.run(cover_mod.set_douyin_cover(page, str(_COVER_OK)))
        print(f"[ADV-5] note={note!r} uploaded={page.uploaded} "
              f"clicks={page.clicked_labels}")
        self.assertTrue(note)
        self.assertEqual(page.uploaded, [], "改版场景误喂了别的 input[type=file]")
        # 失败路径必须按 Escape 兜底(不留残弹层)
        self.assertIn("Escape", page.keys)

    def test_05b_ai_cover_trap_first_input_tempting(self):
        # 更贴 2026-09-14 的坑:第一个 accept 含 image 的 input 极具诱惑。
        # 只要 JS 判据不给 selected,实现就**不允许**退化去挑那一个。
        page = AdvCoverPage()
        page.visible_texts = {"竖封面3:4", "上传封面"}
        page.vertical_btn = {"ok": True, "text": "编辑封面"}
        page.upload_mark = {"total": 4, "selected": None,
                            "scored": [{"index": 0, "score": 11, "accept": "image/*"}]}
        note = asyncio.run(cover_mod.set_douyin_cover(page, str(_COVER_OK)))
        print(f"[ADV-5b] note={note!r} uploaded={page.uploaded}")
        self.assertIn("投放区", note)
        self.assertEqual(page.uploaded, [])

    # ── #6 封面成功但发布失败 ⇒ 不得把封面成功当发布成功 ──
    def test_06_cover_ok_but_publish_fail(self):
        async def cover_ok(page, path):
            return ""                      # 封面「成功」
        r = asyncio.run(_run_publish(str(_MEDIA), cover_path=str(_COVER_OK),
                                     cover_override=cover_ok, force_fail=True))
        print(f"[ADV-6] ok={r['ok']} url={r['url']!r} err={r['err']!r}")
        self.assertFalse(r["ok"], "发布失败却被判成功")
        self.assertEqual(r["url"], "")
        self.assertTrue(r["err"])
        self.assertNotIn("封面已设置", r["err"])
        self.assertIn("发布失败", r["err"])

    # ── #7 连续两次调用不残留注入样式 ──
    def test_07a_two_successful_calls_no_residual_style(self):
        def mk():
            page = AdvCoverPage()
            page.visible_texts = {"竖封面3:4", "上传封面", "完成"}
            page.vertical_btn = {"ok": True, "text": "选择封面"}
            page.thumbs = [{"label": "竖封面3:4", "src": "s1"}]
            page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
            # 两次调用各需 base(2) + after(2) = 4 张,共 8 张;确保两次都走成功路径
            page.shot_seq = [b"B", b"B", b"A", b"A", b"B", b"B", b"A", b"A"]
            return page

        page = mk()
        n1 = asyncio.run(cover_mod.set_douyin_cover(page, str(_COVER_OK)))
        n2 = asyncio.run(cover_mod.set_douyin_cover(page, str(_COVER_OK)))
        print(f"[ADV-7a] n1={n1!r} n2={n2!r} injected={page.style_injected} "
              f"removed={page.style_removed} present={page.style_present}")
        self.assertEqual(n1, "")
        self.assertEqual(n2, "")
        self.assertGreaterEqual(page.style_injected, 2)
        self.assertGreaterEqual(page.style_removed, page.style_injected)
        self.assertFalse(page.style_present, "成功路径后仍残留注入样式")

    def test_07b_two_failed_calls_residual_style(self):
        """spec #7(修复后转正):失败路径结束后**不得**残留注入的 hover-show 样式。

        覆盖 QA 上轮实测泄漏的 4 条失败路径:打开编辑器失败 / 上传入口缺失 /
        未命中投放区 input / 「完成」点不中。修复(`_close_overlay` 入口补
        ``_clear_hover_show``)后每条都应「注入即清理」。
        """
        def cfg_open_fail():
            p = AdvCoverPage()
            p.visible_texts = {"竖封面3:4"}          # 能滚到,没有可点按钮
            return p

        def cfg_upload_entry_missing():
            p = AdvCoverPage()
            p.visible_texts = {"竖封面3:4"}          # 没有「上传封面」入口
            p.vertical_btn = {"ok": True, "text": "选择封面"}
            return p

        def cfg_no_qualified_input():
            p = AdvCoverPage()
            p.visible_texts = {"竖封面3:4", "上传封面"}
            p.vertical_btn = {"ok": True, "text": "选择封面"}
            p.upload_mark = {"total": 3, "selected": None}
            return p

        def cfg_finish_unclickable():
            p = AdvCoverPage()
            p.visible_texts = {"竖封面3:4", "上传封面"}   # 没有「完成」
            p.vertical_btn = {"ok": True, "text": "选择封面"}
            p.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
            return p

        modes = [("open-editor-fail", cfg_open_fail),
                 ("upload-entry-missing", cfg_upload_entry_missing),
                 ("no-qualified-input", cfg_no_qualified_input),
                 ("finish-unclickable", cfg_finish_unclickable)]
        leaks = []
        for name, factory in modes:
            page = factory()
            notes = [asyncio.run(cover_mod.set_douyin_cover(page, str(_COVER_OK)))
                     for _ in range(2)]
            print(f"[ADV-7b {name}] notes={notes} injected={page.style_injected} "
                  f"removed={page.style_removed} present={page.style_present}")
            with self.subTest(case=name):
                self.assertTrue(isinstance(notes[0], str) and notes[0],
                                f"{name}: 失败路径应返回非空原因")
                self.assertGreaterEqual(page.style_injected, 1,
                                        f"{name}: 该路径应注入过 hover-show 样式")
                self.assertFalse(page.style_present,
                                 f"{name}: 失败路径结束后仍残留 <style id=chrc-hover-show>")
                self.assertGreaterEqual(page.style_removed, page.style_injected,
                                        f"{name}: 清理次数少于注入次数(存在泄漏)")
            if page.style_present or page.style_removed < page.style_injected:
                leaks.append(name)
        print(f"[ADV-7b] 仍泄漏的失败路径 = {leaks}")
        self.assertEqual(leaks, [],
                         f"这些失败路径残留了 <style id=chrc-hover-show>: {leaks}")

    # ── #8 (Round2-a) _close_overlay 只允许出现在失败 return 之前 ──
    def test_08_close_overlay_only_before_failure_return(self):
        """`_close_overlay` 必须只作「失败出口」:每次调用后紧跟 return。

        若被挪到「之后还要继续执行」的位置,就会**过早**撤掉强制显示样式,
        使后续「选择封面」按钮重新变回 display:none 而点不中。
        """
        src = Path(cover_mod.__file__).read_text(encoding="utf-8")
        lines = src.splitlines()
        call_sites = [i for i, ln in enumerate(lines) if "await _close_overlay(" in ln]
        print(f"[ADV-8] _close_overlay 调用点(1基行号)={[i + 1 for i in call_sites]}")
        self.assertGreaterEqual(len(call_sites), 5,
                                "失败路径调用点少于预期的 5 处")
        for i in call_sites:
            window = [ln.strip() for ln in lines[i + 1:i + 4]]
            self.assertTrue(any(w.startswith("return") for w in window),
                            f"_close_overlay 调用后 3 行内无 return(行 {i + 1}): {window}")

    # ── #9 (Round2-b) 失败后重试仍可用 ──
    def test_09_retry_after_failures_then_success(self):
        """「失败 → 失败 → 成功」连调:第三次仍能注入样式并完成。

        证明失败留下的清理不会让后续重试失效(每次都重新注入)。
        """
        page = AdvCoverPage()
        # call1:打不开编辑器
        page.visible_texts = {"竖封面3:4"}
        page.vertical_btn = {"ok": False}
        n1 = asyncio.run(cover_mod.set_douyin_cover(page, str(_COVER_OK)))
        # call2:能打开,但没有合格 input
        page.vertical_btn = {"ok": True, "text": "选择封面"}
        page.visible_texts = {"竖封面3:4", "上传封面"}
        page.upload_mark = {"total": 3, "selected": None}
        n2 = asyncio.run(cover_mod.set_douyin_cover(page, str(_COVER_OK)))
        # call3:成功
        page.visible_texts = {"竖封面3:4", "上传封面", "完成"}
        page.thumbs = [{"label": "竖封面3:4", "src": "s1"}]
        page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
        page.shot_seq = [b"B", b"B", b"A", b"A"]
        n3 = asyncio.run(cover_mod.set_douyin_cover(page, str(_COVER_OK)))
        print(f"[ADV-9] n1={n1!r} n2={n2!r} n3={n3!r} injected={page.style_injected} "
              f"removed={page.style_removed} present={page.style_present}")
        self.assertTrue(n1, "call1 应失败且返回原因")
        self.assertTrue(n2, "call2 应失败且返回原因")
        self.assertEqual(n3, "", "call3 应成功返回空串")
        self.assertGreaterEqual(page.style_injected, 3, "每次调用都应重新注入样式")
        self.assertGreaterEqual(page.style_removed, page.style_injected)
        self.assertFalse(page.style_present)

    # ── #10 (Round2-c) 无注入时 _close_overlay 为安全 no-op ──
    def test_10_close_overlay_without_injection_is_safe_noop(self):
        page = AdvCoverPage()          # 从未注入过样式
        try:
            res = asyncio.run(cover_mod._close_overlay(page))
        except Exception as exc:       # noqa: BLE001
            self.fail(f"_close_overlay 在无注入页面抛异常: {exc!r}")
        print(f"[ADV-10 no-injection] res={res!r} present={page.style_present} "
              f"removed={page.style_removed} keys={page.keys}")
        self.assertIsNone(res)
        self.assertFalse(page.style_present)
        self.assertEqual(page.style_removed, 1)          # 仍无害地调了一次 remove
        self.assertEqual(page.keys.count("Escape"), 2)   # rounds 默认 2

    def test_10b_close_overlay_swallows_clear_error(self):
        page = AdvCoverPage()
        page.raise_on_clear = True     # 清理用的 evaluate 本身抛异常
        try:
            res = asyncio.run(cover_mod._close_overlay(page))
        except Exception as exc:       # noqa: BLE001
            self.fail(f"_close_overlay 未吞掉清理异常: {exc!r}")
        print(f"[ADV-10b clear-raises] res={res!r} keys={page.keys}")
        self.assertIsNone(res)
        self.assertEqual(page.keys.count("Escape"), 2)   # 清理失败仍继续 Escape


if __name__ == "__main__":
    unittest.main(verbosity=2)
