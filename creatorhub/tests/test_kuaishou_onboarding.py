"""Offline cover-entry regressions for the native Joyride interception evidence."""
from __future__ import annotations

import asyncio
import unittest

import app.main  # noqa: F401 - initializes browser package imports
from app.platforms.kuaishou import cover, publish


class _Locator:
    def __init__(self, page, kind, label=""):
        self.page, self.kind, self.label = page, kind, label
        self.first = self

    def nth(self, index):
        assert index == 0
        return self

    def get_by_role(self, role, *, name, exact=False):
        assert self.kind == "portal" and role == "button" and exact
        return _Locator(self.page, "tour-button", name)

    async def count(self):
        if self.kind == "cover":
            return 1
        if self.kind in {"portal", "overlay"}:
            return int(self.page.overlay)
        if self.kind == "tour-button":
            return int(self.page.overlay and self.label in self.page.tour_labels)
        return 0

    async def is_visible(self, **kwargs):
        return bool(await self.count())

    async def click(self, *, timeout):
        if self.kind == "cover":
            self.page.cover_attempts += 1
            if self.page.overlay:
                raise TimeoutError("react-joyride__overlay intercepts pointer events")
            self.page.cover_opened = True
            return
        assert self.kind == "tour-button", "must not click an unscoped page button"
        self.page.tour_clicks.append(self.label)
        if self.page.dismisses:
            self.page.overlay = False

    async def wait_for(self, *, state, timeout):
        assert state == "hidden" and timeout <= 3000
        if self.page.overlay:
            raise TimeoutError("Joyride overlay remains visible")


class _Keyboard:
    async def press(self, key):
        assert key == "Escape"


class _Page:
    def __init__(self, *, overlay=True, labels=("跳过引导",), dismisses=True):
        self.overlay, self.tour_labels, self.dismisses = overlay, labels, dismisses
        self.keyboard = _Keyboard()
        self.cover_attempts = 0
        self.cover_opened = False
        self.tour_clicks = []
        self.waits = []

    def locator(self, selector):
        if selector == '[class*="cover-full-editor"]':
            return _Locator(self, "cover")
        if selector == "#react-joyride-portal":
            return _Locator(self, "portal")
        if selector == "#react-joyride-portal .react-joyride__overlay":
            return _Locator(self, "overlay")
        # The page also has unrelated business buttons; they are not tour actions.
        return _Locator(self, "unrelated")

    async def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)


class KuaishouOnboardingTests(unittest.TestCase):
    def test_late_known_tour_is_dismissed_at_cover_entry(self):
        async def run():
            page = _Page(overlay=False)
            await publish._dismiss_overlays(page)
            # The live failure occurred after this earlier publisher cleanup,
            # while the cover baseline was being acquired.
            page.overlay = True
            opened = await cover._open_cover_modal(page)
            self.assertTrue(opened)
            self.assertEqual(page.tour_clicks, ["跳过引导"])
            self.assertTrue(page.cover_opened)
            self.assertEqual(page.cover_attempts, 1)
        asyncio.run(run())

    def test_unknown_tour_controls_stop_without_clicking_underlying_cover(self):
        page = _Page(labels=("立即发布",))
        self.assertFalse(asyncio.run(cover._open_cover_modal(page)))
        self.assertEqual(page.tour_clicks, [])
        self.assertEqual(page.cover_attempts, 0)

    def test_known_button_without_overlay_disappearance_still_stops(self):
        page = _Page(labels=("我知道了",), dismisses=False)
        self.assertFalse(asyncio.run(cover._open_cover_modal(page)))
        self.assertGreater(len(page.tour_clicks), 0)
        self.assertLessEqual(len(page.tour_clicks), 6)
        self.assertEqual(page.cover_attempts, 0)

    def test_no_tour_preserves_normal_cover_entry(self):
        page = _Page(overlay=False)
        self.assertTrue(asyncio.run(cover._open_cover_modal(page)))
        self.assertEqual(page.cover_attempts, 1)
        self.assertEqual(page.tour_clicks, [])


if __name__ == "__main__":
    unittest.main()
