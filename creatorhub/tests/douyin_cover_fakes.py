"""抖音封面「发布时设置竖封面 3:4」的共用 fake page 与场景断言。

被 ``tests/test_douyin_cover.py`` 与 ``scripts/_verify_dy_cover.py`` 共用,
避免两处 fake 行为漂移(单测与真机前静态校验跑的是同一套场景)。

设计:
* ``CoverFakePage``   驱动 ``app.platforms.douyin.cover.set_douyin_cover``。
* ``PubFake*``        驱动 ``app.platforms.douyin.publish.publish_douyin`` 的
  「封面上传插入点」语义(封面 hook 是否被调用 / 发布是否照常走到点发布)。
* ``run_all()``       返回 ``{"cover": [(name, got, want)], "publish": [...]}``。
"""
from __future__ import annotations

import asyncio
import hashlib  # noqa: F401  (供用例侧比对指纹时参考,保持导出)
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.platforms.douyin import cover as cover_mod
from app.platforms.douyin import publish as pub_mod


# ───────────────────── 测试期落盘隔离(不污染 data/debug)─────────────────────
# 生产 ``cover.py::_cover_signature`` 会把封面缩略图像素**真实落盘**到 ``_DEBUG_DIR``
# (默认 ``./data/debug``)供线上取证 —— 这是**生产逻辑,保持不动**。但单测/静态校验
# 跑的是 fake 截图(如 ``b"A"``、``b"IMG"``),若照真落盘就会往取证目录写 1 字节假
# PNG,让后来排查的人误以为「封面像素流程在真机跑过」。
#
# 因此本模块(被 ``tests/test_douyin_cover.py`` 与 ``scripts/_verify_dy_cover.py``
# 共用)在**导入时**就把 cover 模块的 ``_DEBUG_DIR`` 重定向到一次性临时目录,覆盖:
#   * ``tests/test_douyin_cover.py`` 里绕过 ``run_all`` 直接调 ``set_douyin_cover`` 的用例;
#   * ``tests/test_douyin_cover_adversarial.py``(QA 套件)——只要它与本模块同进程即可
#     (``scripts/_qa_run_unittests.py`` 按模块名排序导入,``test_douyin_cover`` 先于
#     ``test_douyin_cover_adversarial``,故重定向在后者跑用例前已生效),无需改动该文件;
#   * ``scripts/_verify_dy_cover.py``。
# 用 ``mkdtemp`` 而非 ``TemporaryDirectory``:宿主 safe-delete 会拦截 ``TemporaryDirectory``
# 的清理(``tests/test_guide_site.py`` 的既有 ERROR 即由此而来);``mkdtemp`` 交由 OS
# 回收,清理永不报错,契合「测试本身不得失败」的要求。
_SESSION_DEBUG_DIR = Path(tempfile.mkdtemp(prefix="chrc-dycover-debug-"))
cover_mod._DEBUG_DIR = _SESSION_DEBUG_DIR


# ────────────────────────── cover 层 fake ──────────────────────────
def _text_label(sel: str):
    """从 ``text="完成"`` / ``text=完成`` 里取文案;不是 text 选择器则 None。"""
    if sel.startswith('text="') and sel.endswith('"') and len(sel) > 7:
        return sel[6:-1]
    if sel.startswith("text=") and len(sel) > 5:
        return sel[5:]
    return None


class _CoverThumb:
    """``locator.nth(i)`` 的截图句柄。"""

    def __init__(self, page):
        self.page = page

    async def screenshot(self, timeout=None, **kwargs):
        return self.page.next_shot()


class _CoverLocator:
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
        return _CoverThumb(self.page)

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


class _CoverKeyboard:
    def __init__(self, page):
        self.page = page

    async def press(self, key):
        self.page.keys.append(key)


class CoverFakePage:
    """只实现 ``cover.py`` 用到的那部分 Playwright 接口。"""

    def __init__(self):
        self.url = "https://creator.douyin.com/creator-micro/content/post/video"
        self.frames = [self]
        self.keyboard = _CoverKeyboard(self)
        self.clicks: list[str] = []
        self.uploaded: list[tuple] = []
        self.keys: list[str] = []
        self.js_calls: list[str] = []
        # 可配置行为
        self.visible_texts: set[str] = set()
        self.vertical_btn: dict = {"ok": False}
        self.upload_mark: dict = {"total": 0, "selected": None}
        self.thumb_marked: list = []
        self.shot_seq: list = []
        self.shot_default = b"IMG"
        # 注入样式在 DOM 中的可观测存续状态(用于断言失败路径也撤掉 hover-show 样式)
        self.hover_style_present = False
        self.hover_injected = 0
        self.hover_removed = 0

    # ── Playwright 表面 ──
    def locator(self, sel, **kwargs):
        return _CoverLocator(self, sel)

    async def wait_for_timeout(self, ms):
        return None

    async def evaluate(self, js, *args):
        self.js_calls.append(js)
        if "data-chrc-vcover" in js:
            return dict(self.vertical_btn)
        if "data-bfc-upload" in js:
            return dict(self.upload_mark)
        if "data-bfc-thumb" in js:
            return {"anchors": len(self.thumb_marked), "marked": list(self.thumb_marked)}
        if "createElement" in js:            # _force_show_hover(注入)
            self.hover_style_present = True
            self.hover_injected += 1
            return True
        if "getElementById" in js:           # _clear_hover_show(移除)
            self.hover_style_present = False
            self.hover_removed += 1
            return None
        return None

    def get_by_text(self, text, exact=False):
        return _CoverLocator(self, f"text={text}", count=0)

    # ── 内部 ──
    def next_shot(self):
        return self.shot_seq.pop(0) if self.shot_seq else self.shot_default

    def count_for(self, sel):
        if "chrc-vcover" in sel:
            return 1 if self.vertical_btn.get("ok") else 0
        if "bfc-upload" in sel:
            return 1 if self.upload_mark.get("selected") else 0
        if "bfc-thumb" in sel:
            return len(self.thumb_marked)
        label = _text_label(sel)
        if label is not None:
            return 1 if label in self.visible_texts else 0
        return 0


# ────────────────────────── publish 层 fake ──────────────────────────
class _PubLocator:
    def __init__(self, page, sel, *, count=1, visible=True):
        self.page = page
        self.sel = sel
        self._count = count
        self._visible = visible
        self.first = self

    async def count(self):
        return self._count

    async def is_visible(self, timeout=None):
        return self._visible

    async def wait_for(self, state=None, timeout=None):
        return None

    async def click(self, timeout=None):
        self.page.clicks.append(self.sel)

    async def fill(self, text, timeout=None):
        return None

    async def press(self, key, timeout=None):
        return None

    async def set_input_files(self, files, timeout=None):
        self.page.uploaded.append((self.sel, files))

    async def inner_text(self):
        return ""


class _PubBtn:
    def __init__(self):
        self.clicked = 0
        self.click_error = False

    async def is_enabled(self):
        return True

    async def scroll_into_view_if_needed(self, timeout=None):
        return None

    async def click(self, timeout=None):
        self.clicked += 1
        if self.click_error:
            raise TimeoutError("ambiguous click timeout")


class PubFakePage:
    def __init__(self):
        self.url = "https://creator.douyin.com/creator-micro/content/upload"
        self.clicks: list[str] = []
        self.uploaded: list[tuple] = []
        self.trace: list[tuple] = []

    def locator(self, sel, **kwargs):
        return _PubLocator(self, sel)

    async def wait_for_timeout(self, ms):
        self.trace.append(("wait", ms))
        return None

    async def goto(self, url, wait_until=None, timeout=None):
        self.url = url
        self.trace.append(("goto", url))

    async def screenshot(self, path=None, full_page=False):
        return None

    async def inner_text(self, sel="body"):
        return ""

    def on(self, *args, **kwargs):
        return None

    def get_by_text(self, text, exact=False):
        return _PubLocator(self, f"text={text}", count=0)


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


async def run_publish(media_path: str, cover_path: str = "", cover_impl=None,
                      click_error: bool = False, **publish_kwargs):
    """用 fake 驱动 ``publish_douyin``,返回关键观测点。

    cover_impl(page, path) 可注入「封面 hook 的行为」(默认返回 "")。
    """
    page = PubFakePage()
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

    async def _fake_state(page_):
        return {"texts": [], "videos": 0, "url": page_.url}

    async def _fake_visible_any(page_, keywords):
        if keywords is pub_mod._FAIL_KW:
            return ""
        if keywords is pub_mod._SUCCESS_KW:
            return "发布成功"
        if keywords is pub_mod._VERIFY_KW:
            return ""
        return ""

    with patch.object(pub_mod, "_dump", AsyncMock(return_value="")), \
         patch.object(pub_mod, "_wait_editor", AsyncMock(return_value=True)), \
         patch.object(pub_mod, "_page_state", _fake_state), \
         patch.object(pub_mod, "_state_sig", lambda state: "SIG"), \
         patch.object(pub_mod, "_primary_publish_button", AsyncMock(return_value=btn)), \
         patch.object(pub_mod, "_visible_success_hits", lambda state: []), \
         patch.object(pub_mod, "_visible_any", _fake_visible_any), \
         patch.object(pub_mod, "_verify_on_manage",
                      AsyncMock(return_value=(True, "核对通过"))), \
         patch.object(pub_mod, "set_douyin_cover", _rec):
        ok, url, err = await pub_mod.publish_douyin(
            mgr, None, "", "video", "", "", [media_path],
            cover_path=cover_path, timeout_seconds=1, **publish_kwargs)

    return {"ok": ok, "url": url, "err": err, "btn": btn,
            "cover_calls": cover_calls, "page": page, "ctx": ctx}


# ────────────────────────── 场景 ──────────────────────────
async def _cover_scenarios(tmp: Path):
    results: list = []

    def rec(name, got, want):
        results.append((name, got, want))

    missing = str(tmp / "no_such_cover.png")
    real_cover = tmp / "cover-1080x1440.jpg"
    real_cover.write_bytes(b"\xff\xd8\xff\xd9")

    # 1. cover_path 为空 → 立即返回,且不点击/不注入/不按键
    page = CoverFakePage()
    note = await cover_mod.set_douyin_cover(page, "")
    rec("1a 空封面 -> 返回空串", note, "")
    rec("1b 空封面 -> 不点击任何东西", page.clicks, [])
    rec("1c 空封面 -> 无 JS 交互", page.js_calls, [])
    rec("1d 空封面 -> 无按键", page.keys, [])

    # 2. 文件不存在 → 返回原因字符串,不抛异常,不交互
    page = CoverFakePage()
    note = await cover_mod.set_douyin_cover(page, missing)
    rec("2a 文件不存在 -> 返回原因", note.startswith("封面文件不存在"), True)
    rec("2b 文件不存在 -> 无 JS 交互", page.js_calls, [])

    # 3. 找不到封面区
    page = CoverFakePage()
    note = await cover_mod.set_douyin_cover(page, str(real_cover))
    rec("3a 找不到封面区 -> 返回原因",
        "没找到封面区" in note, True)

    # 4. _mark_upload_input 拿不到 selected -> 返回原因,且**不退化**为随便挑 input
    page = CoverFakePage()
    page.visible_texts = {"竖封面3:4", "上传封面"}
    page.vertical_btn = {"ok": True, "text": "选择封面"}
    page.thumb_marked = []
    page.upload_mark = {"total": 3, "selected": None}
    note = await cover_mod.set_douyin_cover(page, str(real_cover))
    rec("4a 投放区未命中 -> 返回原因(含投放区)", "投放区" in note, True)
    rec("4b 投放区未命中 -> 未投喂任何 input", page.uploaded, [])
    rec("4c 投放区未命中 -> 失败路径按 Escape 兜底", "Escape" in page.keys, True)

    # 5. 「完成」一直点不中 -> 返回原因,但确实投喂到了投放区 input
    page = CoverFakePage()
    page.visible_texts = {"竖封面3:4", "上传封面"}      # 故意没有「完成」
    page.vertical_btn = {"ok": True, "text": "选择封面"}
    page.thumb_marked = []
    page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
    note = await cover_mod.set_douyin_cover(page, str(real_cover))
    rec("5a 完成点不中 -> 返回原因(含完成)", "完成" in note, True)
    rec("5b 完成点不中 -> 确实投喂到投放区 input",
        page.uploaded, [('input[data-bfc-upload="1"]', str(real_cover))])
    rec("5c 完成点不中 -> 失败路径按 Escape 兜底", "Escape" in page.keys, True)

    # 6. 成功路径:像素指纹变化 -> 返回空串
    page = CoverFakePage()
    page.visible_texts = {"竖封面3:4", "上传封面", "完成"}
    page.vertical_btn = {"ok": True, "text": "选择封面"}
    page.thumb_marked = [{"label": "竖封面3:4", "src": "s1"},
                         {"label": "横封面4:3", "src": "s2"}]
    page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
    page.shot_seq = [b"B", b"B", b"B", b"B"]
    page.shot_default = b"A"
    note = await cover_mod.set_douyin_cover(page, str(real_cover))
    rec("6a 像素变化 -> 返回空串(成功)", note, "")
    rec("6b 成功 -> 投喂了投放区 input",
        page.uploaded, [('input[data-bfc-upload="1"]', str(real_cover))])
    rec("6c 成功 -> 点了「完成」",
        any("完成" in c for c in page.clicks), True)
    rec("6d 成功 -> 撤掉了 hover-show 注入样式",
        any("getElementById" in js and "createElement" not in js
            for js in page.js_calls), True)

    # 7. 像素未变(典型假成功) -> 返回原因
    page = CoverFakePage()
    page.visible_texts = {"竖封面3:4", "上传封面", "完成"}
    page.vertical_btn = {"ok": True, "text": "选择封面"}
    page.thumb_marked = [{"label": "竖封面3:4", "src": "s1"}]
    page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
    page.shot_seq = []
    page.shot_default = b"B"
    note = await cover_mod.set_douyin_cover(page, str(real_cover))
    rec("7a 像素未变 -> 返回原因(像素前后一致)", "像素前后一致" in note, True)

    return results


async def _publish_scenarios(tmp: Path):
    results: list = []

    def rec(name, got, want):
        results.append((name, got, want))

    media = tmp / "fake.mp4"
    media.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    cover = tmp / "cover.jpg"
    cover.write_bytes(b"\xff\xd8\xff\xd9")

    # R1/R2: cover_path 为空 -> 封面 hook 完全不触发(等价于改动前序列),发布照常
    run_a = await run_publish(str(media), cover_path="")
    rec("R1 空封面 -> set_douyin_cover 未被调用", run_a["cover_calls"], [])
    rec("R2 空封面 -> 发布照常成功", run_a["ok"], True)
    rec("R2 空封面 -> 确实点了发布按钮一次", run_a["btn"].clicked, 1)

    # R3: 确定性 —— 同样的空封面跑两遍,交互轨迹逐字一致
    run_b = await run_publish(str(media), cover_path="")
    rec("R3 空封面 -> 两次运行的页面交互轨迹一致",
        run_b["page"].trace == run_a["page"].trace, True)

    # R4: 有封面 -> hook 被调用一次且带正确路径,发布照常
    run_c = await run_publish(str(media), cover_path=str(cover))
    rec("R4 有封面 -> hook 被调用一次", len(run_c["cover_calls"]), 1)
    rec("R4 有封面 -> hook 收到封面路径", run_c["cover_calls"][0], str(cover))
    rec("R4 有封面 -> 发布照常成功", run_c["ok"], True)
    rec("R4 有封面 -> 确实点了发布按钮一次", run_c["btn"].clicked, 1)

    # R5: best-effort —— 封面 hook 抛异常,发布仍走到点发布且成功
    async def _boom(page, path):
        raise RuntimeError("cover boom")

    run_d = await run_publish(str(media), cover_path=str(cover), cover_impl=_boom)
    rec("R5 封面抛异常 -> 发布仍成功", run_d["ok"], True)
    rec("R5 封面抛异常 -> 仍点了发布按钮一次", run_d["btn"].clicked, 1)
    rec("R5 封面抛异常 -> 封面确实被尝试过", len(run_d["cover_calls"]), 1)

    # R6: best-effort —— 封面返回失败原因串,发布仍成功
    async def _fail(page, path):
        return "封面文件不存在: x"

    run_e = await run_publish(str(media), cover_path=str(cover), cover_impl=_fail)
    rec("R6 封面返回失败 -> 发布仍成功", run_e["ok"], True)
    rec("R6 封面返回失败 -> 仍点了发布按钮一次", run_e["btn"].clicked, 1)

    return results


def run_all() -> dict:
    """跑全部场景,返回 {"cover": [(name, got, want)], "publish": [...]}。"""
    with tempfile.TemporaryDirectory(prefix="chrc-cover-",
                                     ignore_cleanup_errors=True) as tmpdir:
        tmp = Path(tmpdir)
        # 封面像素落盘目录:模块导入时已整体重定向到 _SESSION_DEBUG_DIR(见文件头);
        # 这里再收窄到本次运行的临时子目录,双保险且互不污染。
        with patch.object(cover_mod, "_DEBUG_DIR", tmp / "dbg"):
            cover_results = asyncio.run(_cover_scenarios(tmp))
        publish_results = asyncio.run(_publish_scenarios(tmp))
    return {"cover": cover_results, "publish": publish_results}
