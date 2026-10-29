"""Offline login-panel seams; never opens a browser or contacts a platform."""
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.browser.identity import Identity
from app.browser.login import _expand_douyin_login_panel, interactive_login


class _Node:
    def __init__(self, page, *, visible=True, intercepted=False):
        self.page = page
        self.visible = visible
        self.intercepted = intercepted

    async def is_visible(self):
        return self.visible

    async def click(self, *, timeout):
        self.page.clicks.append(self)
        if self.intercepted:
            raise RuntimeError("fixture hydration detached this candidate")
        self.page.accepted_clicks += 1
        if self.page.accepted_clicks >= self.page.clicks_to_open:
            self.page.panel_visible = True


class _Locator:
    def __init__(self, nodes):
        self.nodes = nodes

    async def count(self):
        return len(self.nodes)

    def nth(self, index):
        return self.nodes[index]


class _Page:
    def __init__(self, *, hydrate_round=0, panel_visible=False,
                 panel_text="扫码登录", clicks_to_open=1, closed=False):
        self.round = 0
        self.hydrate_round = hydrate_round
        self.panel_visible = panel_visible
        self.panel_text = panel_text
        self.clicks_to_open = clicks_to_open
        self.closed = closed
        self.clicks = []
        self.accepted_clicks = 0
        self.lookups = []
        self.nodes = [_Node(self, visible=False), _Node(self)]

    def is_closed(self):
        return self.closed

    def get_by_text(self, text, *, exact):
        self.lookups.append((text, exact))
        if text == "登录":
            return _Locator(self.nodes if self.round >= self.hydrate_round else [])
        if self.panel_visible and text == self.panel_text:
            return _Locator([_Node(self)])
        return _Locator([])

    def get_by_role(self, role, *, name, exact):
        assert (role, name, exact) == ("button", "登录", True)
        return _Locator([])

    def locator(self, selector):
        assert selector == '[data-e2e="login-button"]'
        return _Locator([])

    async def click(self, *_args, **_kwargs):
        raise AssertionError("strict page.click must not be used")

    async def advance(self, seconds):
        assert seconds == 0.5
        self.round += 1


class DouyinLoginPanelTests(unittest.IsolatedAsyncioTestCase):
    async def expand(self, page):
        with patch("app.browser.login.asyncio.sleep", side_effect=page.advance):
            return await _expand_douyin_login_panel(page)

    async def test_chooses_visible_exact_cta_among_hidden_duplicates(self):
        page = _Page()
        self.assertTrue(await self.expand(page))
        self.assertEqual(page.clicks, [page.nodes[1]])
        self.assertIn(("登录", True), page.lookups)

    async def test_waits_for_homepage_hydration_before_clicking(self):
        page = _Page(hydrate_round=3)
        self.assertTrue(await self.expand(page))
        self.assertGreaterEqual(page.round, 3)
        self.assertEqual(page.accepted_clicks, 1)

    async def test_retries_click_swallowed_during_hydration(self):
        page = _Page(clicks_to_open=2)
        self.assertTrue(await self.expand(page))
        self.assertEqual(page.accepted_clicks, 2)
        self.assertGreaterEqual(page.round, 3)

    async def test_existing_qr_panel_is_never_clicked_again(self):
        page = _Page(panel_visible=True)
        self.assertTrue(await self.expand(page))
        self.assertEqual(page.clicks, [])
        self.assertEqual(page.round, 0)

    async def test_verification_panel_remains_for_user(self):
        page = _Page(panel_visible=True, panel_text="安全验证")
        self.assertTrue(await self.expand(page))
        self.assertEqual(page.clicks, [])
        self.assertNotIn(("登录", True), page.lookups)

    async def test_detached_candidate_does_not_hide_next_visible_cta(self):
        page = _Page()
        detached = _Node(page, intercepted=True)
        page.nodes.insert(1, detached)
        self.assertTrue(await self.expand(page))
        self.assertEqual(page.clicks, [detached, page.nodes[2]])

    async def test_never_hydrated_page_has_finite_retry_budget(self):
        page = _Page(hydrate_round=100)
        self.assertFalse(await self.expand(page))
        self.assertEqual(page.round, 15)
        self.assertEqual(page.clicks, [])

    async def test_closed_page_stops_without_touching_controls(self):
        page = _Page(closed=True)
        self.assertFalse(await self.expand(page))
        self.assertEqual(page.lookups, [])
        self.assertEqual(page.clicks, [])

    async def test_interactive_entry_expands_panel_before_cookie_polling(self):
        page = Mock()
        page.goto = AsyncMock()
        page.bring_to_front = AsyncMock()
        context = Mock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        manager = Mock(spec=["open_headed"])
        manager.open_headed = AsyncMock(return_value=context)
        identity = Identity(account_id=1, profile_dir="fixture", platform="douyin")
        with patch("app.browser.login._expand_douyin_login_panel",
                   new=AsyncMock(return_value=True)) as expand:
            result = await interactive_login(manager, identity, timeout_seconds=0)
        self.assertEqual(result, (False, "", ""))
        expand.assert_awaited_once_with(page)
        context.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
