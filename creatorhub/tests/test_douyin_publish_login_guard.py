"""Offline guards for an actual creator login page retaining its manage URL."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from app.platforms.douyin import publish as pub


LOGIN_BODY = """抖音创作者的一站式创作与服务平台
我是创作者
我是MCN机构
扫码登录
如何扫码
验证码登录
密码登录
获取验证码
登录
登录即代表同意用户协议和隐私政策
AI 赋能创作者
作品发布及管理
"""


class Page:
    def __init__(self, body=""):
        self.url = pub.UPLOAD_URL
        self.body = body
        self.reads = 0
        self.uploads = []
        self.closed = False

    async def goto(self, url, **kwargs):
        self.url = url

    async def wait_for_timeout(self, _ms):
        pass

    async def inner_text(self, _selector):
        self.reads += 1
        return self.body(self.reads) if callable(self.body) else self.body

    def on(self, *_args):
        pass

    def locator(self, selector):
        page = self
        class File:
            @property
            def first(self):
                return self

            async def set_input_files(self, files, **kwargs):
                page.uploads.append(list(files))
        if selector != 'input[type="file"]':
            raise AssertionError("unexpected live locator: " + selector)
        return File()

    async def close(self):
        self.closed = True


class Context:
    def __init__(self, page):
        self.page = page
        self.closed = False

    async def new_page(self):
        return self.page

    async def close(self):
        self.closed = True


class Manager:
    def __init__(self, ctx):
        self.ctx = ctx

    async def open_background(self, _identity):
        return self.ctx

    async def stop_minimize_hold(self, _identity):
        pass


class LoginLandingTextTests(unittest.TestCase):
    def test_captured_login_cluster_is_detected_without_login_url(self):
        self.assertTrue(pub._login_landing_text(LOGIN_BODY))
        self.assertTrue(pub._login_landing_text(LOGIN_BODY.replace("扫码登录", "扫\u200b码登录")))

    def test_a_login_word_or_editor_prose_does_not_claim_logged_out(self):
        for body in ("作品管理\n发布\n登录", "标题：我是创作者\n正文介绍扫码登录和密码登录的区别",
                     "扫码登录\n作品管理\n发布", "验证码登录\n密码登录\n作品管理"):
            with self.subTest(body=body):
                self.assertFalse(pub._login_landing_text(body))


class LoginPublishGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_manage_url_login_is_not_a_missing_work(self):
        page = Page(LOGIN_BODY)
        ctx = Context(page)
        with patch.object(pub, "_dump", AsyncMock(return_value="")), \
             patch.object(pub, "_manage_search", AsyncMock(side_effect=AssertionError("must not search login page"))) as search:
            found, detail = await pub._verify_on_manage(ctx, "机器人新闻", timeout_ms=1)
        self.assertFalse(found)
        self.assertTrue(detail.startswith("logged_out:"))
        self.assertEqual(page.url, pub.MANAGE_URL)
        search.assert_not_awaited()
        self.assertTrue(page.closed)

    async def _publish(self, page, **kwargs):
        ctx = Context(page)
        submitted = []
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "video.mp4"
            video.write_bytes(b"offline fake media; no browser is launched")
            result = await pub.publish_douyin(Manager(ctx), None, "", "video", "机器人新闻", "简介",
                [str(video)], cover_path="required-cover.png", cover_required=True,
                on_submit=lambda: submitted.append(True), **kwargs)
        return result, submitted, ctx

    async def test_initial_login_page_stops_before_upload_cover_or_submit(self):
        page = Page(LOGIN_BODY)
        with patch.object(pub, "_dump", AsyncMock(return_value="")), \
             patch.object(pub, "_verify_on_manage", AsyncMock(side_effect=AssertionError("must stop first"))) as verify, \
             patch.object(pub, "set_douyin_cover", AsyncMock()) as cover:
            (ok, _, error), submitted, ctx = await self._publish(page)
        self.assertFalse(ok)
        self.assertTrue(error.startswith("logged_out:"))
        self.assertEqual(page.uploads, [])
        self.assertEqual(submitted, [])
        verify.assert_not_awaited()
        cover.assert_not_awaited()
        self.assertTrue(ctx.closed)

    async def test_logged_out_duplicate_check_cannot_continue_to_upload(self):
        page = Page("作品发布\n填写作品标题")
        with patch.object(pub, "_dump", AsyncMock(return_value="")), \
             patch.object(pub, "_verify_on_manage", AsyncMock(return_value=(False, "logged_out:创作者未登录"))), \
             patch.object(pub, "set_douyin_cover", AsyncMock()) as cover:
            (ok, _, error), submitted, ctx = await self._publish(page)
        self.assertFalse(ok)
        self.assertTrue(error.startswith("logged_out:"))
        self.assertEqual(page.uploads, [])
        self.assertEqual(submitted, [])
        cover.assert_not_awaited()
        self.assertTrue(ctx.closed)

    async def test_session_lost_while_waiting_stops_before_cover_and_final_click(self):
        page = Page(lambda reads: LOGIN_BODY if reads >= 3 else "作品发布\n填写作品标题")
        with patch.object(pub, "_dump", AsyncMock(return_value="")), \
             patch.object(pub, "_verify_on_manage", AsyncMock(return_value=(False, "尚无作品"))), \
             patch.object(pub, "_wait_editor", AsyncMock(return_value=True)), \
             patch.object(pub, "_fill_first", AsyncMock(return_value=True)), \
             patch.object(pub, "_apply_publish_settings", AsyncMock()), \
             patch.object(pub, "_primary_publish_button", AsyncMock()) as button, \
             patch.object(pub, "set_douyin_cover", AsyncMock()) as cover:
            (ok, _, error), submitted, ctx = await self._publish(page)
        self.assertFalse(ok)
        self.assertTrue(error.startswith("logged_out:"))
        self.assertEqual(len(page.uploads), 1)
        self.assertEqual(submitted, [])
        button.assert_not_awaited()
        cover.assert_not_awaited()
        self.assertTrue(ctx.closed)

    async def test_login_loss_after_final_click_remains_write_uncertain(self):
        page = Page("作品发布\n填写作品标题")
        button = type("Button", (), {"is_enabled": AsyncMock(return_value=True),
            "scroll_into_view_if_needed": AsyncMock(), "click": AsyncMock()})()
        async def visible(_page, keywords):
            return "发布成功" if keywords is pub._SUCCESS_KW else ""
        with patch.object(pub, "_dump", AsyncMock(return_value="")), \
             patch.object(pub, "_verify_on_manage", AsyncMock(side_effect=[(False, "尚无作品"), (False, "logged_out:核对页未登录")])), \
             patch.object(pub, "_wait_editor", AsyncMock(return_value=True)), \
             patch.object(pub, "_fill_first", AsyncMock(return_value=True)), \
             patch.object(pub, "_apply_publish_settings", AsyncMock()), \
             patch.object(pub, "_primary_publish_button", AsyncMock(return_value=button)), \
             patch.object(pub, "_page_state", AsyncMock(return_value={"texts": [], "videos": 1})), \
             patch.object(pub, "_state_sig", return_value="stable"), \
             patch.object(pub, "_visible_any", visible), \
             patch.object(pub, "set_douyin_cover", AsyncMock(return_value="")):
            (ok, _, error), submitted, ctx = await self._publish(page)
        self.assertFalse(ok)
        self.assertTrue(error.startswith("write_uncertain:"))
        self.assertEqual(submitted, [True])
        button.click.assert_awaited_once()
        self.assertTrue(ctx.closed)


if __name__ == "__main__":
    unittest.main()
