"""抖音发布「顺带设竖封面 3:4」单测(离线,不开真浏览器)。

覆盖:
* cover 层 7 个场景(空路径 / 文件不存在 / 找不到封面区 / 投放区未命中不退化 /
  「完成」点不中 / 像素变化成功 / 像素未变假成功)
* publish 层 best-effort 与向后兼容(空 cover_path 时 hook 完全不触发、发布照常;
  有封面时 hook 被调用;hook 抛异常或返回失败时发布仍走到点发布)
* 结构约束:``cover_path`` 必须是 ``publish_douyin`` 的最后一个默认参数;
  ``cover.py`` 不得 import ``publish``(避免循环导入);插入点在点发布之前。

fake 与场景定义在 ``tests/douyin_cover_fakes.py``(与
``scripts/_verify_dy_cover.py`` 共用,避免行为漂移)。

落盘隔离:封面像素指纹在**生产**里会真实落盘到 ``cover._DEBUG_DIR``(取证目录
``data/debug``);本测试导入 ``tests.douyin_cover_fakes`` 时该常量已被重定向到一次性
临时目录(见 ``douyin_cover_fakes`` 文件头),故所有用例都不会往 ``data/debug`` 写
假 PNG。
"""
from __future__ import annotations

import asyncio
import inspect
import tempfile
import unittest
from pathlib import Path

from app.platforms.douyin import cover as cover_mod
from app.platforms.douyin import publish as pub_mod
from app.platforms.douyin.publish import publish_douyin
from tests.douyin_cover_fakes import CoverFakePage, run_all

ROOT = Path(__file__).resolve().parent.parent


class DouyinCoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = run_all()

    def test_cover_layer_scenarios(self):
        for name, got, want in self.results["cover"]:
            with self.subTest(name=name):
                self.assertEqual(got, want)

    def test_publish_layer_best_effort_and_compat(self):
        for name, got, want in self.results["publish"]:
            with self.subTest(name=name):
                self.assertEqual(got, want)

    def test_empty_cover_path_short_circuits_without_side_effects(self):
        page = CoverFakePage()
        note = asyncio.run(cover_mod.set_douyin_cover(page, ""))
        self.assertEqual(note, "")
        self.assertEqual(page.clicks, [])
        self.assertEqual(page.js_calls, [])
        self.assertEqual(page.keys, [])
        self.assertEqual(page.uploaded, [])

    def test_missing_cover_file_returns_reason_without_raising(self):
        page = CoverFakePage()
        note = asyncio.run(
            cover_mod.set_douyin_cover(page, "D:/no_such_dir/no_such_cover.png"))
        self.assertEqual(note, "封面文件不存在: D:/no_such_dir/no_such_cover.png")
        self.assertEqual(page.js_calls, [])

    def test_failure_path_leaves_no_injected_hover_style(self):
        """失败路径结束后**不得**残留 ``_force_show_hover`` 注入的样式。

        ``_open_cover_editor`` 在点按钮**之前**就注入 ``<style id="chrc-hover-show">``;
        若失败分支只按 Escape 就 return,该样式会泄漏到同页(把 ``[class*="hover-show"]``
        全部强制显示,污染后续布局与像素比对)。覆盖 QA 实测泄漏的两种失败分支:
        「找不到投放区 input」与「『完成』一直点不中」。
        """
        with tempfile.TemporaryDirectory(prefix="chrc-cover-fix-") as tmpdir:
            real_cover = Path(tmpdir) / "cover.jpg"
            real_cover.write_bytes(b"\xff\xd8\xff\xd9")

            def cfg_no_qualified_input():
                page = CoverFakePage()
                page.visible_texts = {"竖封面3:4", "上传封面"}
                page.vertical_btn = {"ok": True, "text": "选择封面"}
                page.upload_mark = {"total": 3, "selected": None}
                return page

            def cfg_finish_unclickable():
                page = CoverFakePage()
                page.visible_texts = {"竖封面3:4", "上传封面"}   # 故意没有「完成」
                page.vertical_btn = {"ok": True, "text": "选择封面"}
                page.upload_mark = {"total": 1, "selected": {"index": 0, "score": 35}}
                return page

            for name, build in (("找不到投放区 input", cfg_no_qualified_input),
                                ("「完成」一直点不中", cfg_finish_unclickable)):
                with self.subTest(case=name):
                    page = build()
                    note = asyncio.run(
                        cover_mod.set_douyin_cover(page, str(real_cover)))
                    # 失败路径应给出非空原因
                    self.assertTrue(note, f"{name}: 失败路径应返回非空原因")
                    # 该路径确实走到了 _open_cover_editor(样式被注入过)
                    self.assertGreaterEqual(
                        page.hover_injected, 1,
                        f"{name}: 未按预期注入 hover-show 样式(fake 观测异常)")
                    # 但结束后必须已被撤掉,页面不得残留
                    self.assertFalse(
                        page.hover_style_present,
                        f"{name}: 失败路径结束后仍残留 <style id=chrc-hover-show>")
                    # 注入几次就该配对清理几次
                    self.assertGreaterEqual(
                        page.hover_removed, page.hover_injected,
                        f"{name}: 清理次数少于注入次数(存在泄漏)")

    def test_publish_douyin_cover_path_is_last_default_param(self):
        params = inspect.signature(publish_douyin).parameters
        self.assertIn("cover_path", params)
        self.assertEqual(params["cover_path"].default, "")
        # 严格策略参数追加在 cover_path 后，既有位置参数调用仍兼容。
        self.assertEqual(params["cover_required"].default, False)
        self.assertIsNone(params["on_submit"].default)

    def test_cover_module_does_not_import_publish(self):
        src = inspect.getsource(cover_mod)
        self.assertNotIn("from .publish", src)
        self.assertNotIn("import publish", src)

    def test_cover_hook_inserted_after_upload_loop_and_before_publish_click(self):
        src = (ROOT / "app/platforms/douyin/publish.py").read_text(encoding="utf-8")
        i_loop = src.index("waited_ms += 2000")
        i_cover = src.index("if cover_path:")
        i_click = src.index("await btn.click(timeout=5000)")
        self.assertLess(i_loop, i_cover)
        self.assertLess(i_cover, i_click)

    def test_cover_hook_swallows_exceptions(self):
        # publish_douyin 里必须用 try/except 包住 hook —— 封面异常绝不冒泡打断发布
        src = (ROOT / "app/platforms/douyin/publish.py").read_text(encoding="utf-8")
        block = src[src.index("if cover_path:"):src.index("if btn is None:")]
        self.assertIn("try:", block)
        self.assertIn("except Exception", block)

    def test_monitor_passes_cover_path_to_publish_douyin(self):
        src = (ROOT / "app/engine/monitor.py").read_text(encoding="utf-8")
        self.assertIn('cover_path = getattr(t, "cover_path", "") or ""', src)
        # 封面喂给**发布器本身支持「发布时设封面」**的平台:
        #   · 抖音   —— publish_douyin 有 set_douyin_cover(任务级竖封面 3:4)
        #   · 视频号 —— publish_channels 有 _set_cover,封面是它的**发布前置条件**
        #   · 快手   —— publish_kuaishou 有 set_kuaishou_cover(2026-09-21 接入,best-effort)
        #   · 小红书 —— 发布器没有发布时封面能力,封面走发布后回填,不许在这里传
        # ★ 2026-09-21:视频号那条也接上了 —— 本测试原来断言全局 count == 1,
        #   是「只接抖音」的旧口径,没跟着改,于是稳定失败。改成**按调用点分段**断言,
        #   比全局计数更硬:既守住三个该接的平台,也守住一个不该接的平台。
        i_ks = src.index("publish_kuaishou(")
        i_ch = src.index("publish_channels(")
        i_cy = src.index("publish_douyin(")
        i_xhs = src.index("publish_xhs(")
        seg = {
            "kuaishou": src[i_ks:i_ch],
            "shipinhao": src[i_ch:i_cy],
            "douyin": src[i_cy:i_xhs],
            "xhs": src[i_xhs:],
        }
        self.assertIn("cover_path=cover_path", seg["kuaishou"])
        self.assertIn("cover_path=cover_path", seg["douyin"])
        self.assertIn("cover_path=cover_path", seg["shipinhao"])
        self.assertNotIn("cover_path=cover_path", seg["xhs"])

    def test_publish_module_allows_empty_cover_gate(self):
        # 冒烟:确认 publish_douyin 已通过 from .cover 拿到 set_douyin_cover
        self.assertTrue(hasattr(pub_mod, "set_douyin_cover"))


if __name__ == "__main__":
    unittest.main()
