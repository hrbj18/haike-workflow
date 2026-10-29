from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from douyin_intelligence.mediacrawler_runner import CookieAccountEvidence


SELF = "https://www.douyin.com/aweme/v1/web/user/profile/self/?device_platform=webapp"
PROFILE = {"status_code": 0, "user": {"uid": "123456789", "nickname": "测试用户"}}


class Page:
    # Deliberately has no evaluate(), cookies(), or cached login flags.
    def __init__(self, *, challenge=False, title="抖音", url="https://www.douyin.com/"):
        self.handlers = {"request": [], "response": []}
        self.challenge = challenge
        self.page_title = title
        self.url = url

    def on(self, event, callback):
        self.handlers[event].append(callback)

    def remove_listener(self, event, callback):
        self.handlers[event].remove(callback)

    async def title(self):
        return self.page_title

    def locator(self, selector):
        page = self

        class Locator:
            @property
            def first(self):
                return self

            async def is_visible(self, **kwargs):
                return page.challenge

        return Locator()

    def emit(self, event, value):
        for callback in list(self.handlers[event]):
            callback(value)

    def response(self, payload=PROFILE, *, status=200, url=SELF, track=True, worker=False):
        request = SimpleNamespace(method="GET", url=url)

        async def body():
            return payload

        value = SimpleNamespace(request=request, url=url, status=status, json=body,
                                from_service_worker=worker)
        if track:
            self.emit("request", request)
        self.emit("response", value)
        return value


def test_cookie_account_needs_fresh_self_response_without_ui_flags():
    async def check():
        page = Page()
        observer = CookieAccountEvidence(page)
        observer.start_navigation()
        page.response()
        assert await observer.wait(timeout=.05) is True
        assert page.handlers == {"request": [], "response": []}

    asyncio.run(check())


@pytest.mark.parametrize("options", [
    {"status": 401},
    {"payload": {"status_code": 8, "user": PROFILE["user"]}},
    {"payload": {"status_code": False, "user": PROFILE["user"]}},
    {"payload": {"status_code": 0, "user": {"nickname": "没有身份"}}},
    {"payload": {"status_code": 0, "user": {"uid": "123"}}},
    {"payload": {"status_code": 0, "user": {"uid": True, "nickname": "没有身份"}}},
    {"payload": {"status_code": 0, "LOGIN_STATUS": "1", "HasUserLogin": "1"}},
    {"payload": "not an object"},
    {"url": "https://www.douyin.com/aweme/v1/web/user/profile/other/"},
    {"url": "https://evil.test/aweme/v1/web/user/profile/self/"},
    {"url": "https://www.douyin.com.evil.test/aweme/v1/web/user/profile/self/"},
    {"url": "http://www.douyin.com/aweme/v1/web/user/profile/self/"},
    {"track": False},
    {"worker": True},
])
def test_public_stale_unverified_or_failed_response_cannot_authenticate(options):
    async def check():
        page = Page()
        observer = CookieAccountEvidence(page)
        observer.start_navigation()
        page.response(**options)
        assert await observer.wait(timeout=.02) is False

    asyncio.run(check())


def test_previous_navigation_request_is_not_fresh_authentication():
    async def check():
        page = Page()
        observer = CookieAccountEvidence(page)
        observer.start_navigation()
        stale = page.response()
        observer.start_navigation()
        page.emit("response", stale)
        assert await observer.wait(timeout=.02) is False

    asyncio.run(check())


def test_conflicting_self_response_cannot_be_overridden_by_later_success():
    async def check():
        page = Page()
        observer = CookieAccountEvidence(page)
        observer.start_navigation()
        page.response(status=403)
        page.response()
        assert await observer.wait(timeout=.05) is False

    asyncio.run(check())


@pytest.mark.parametrize("page_options", [
    {"challenge": True}, {"title": "验证码中间页"}, {"title": "安全验证"},
    {"url": "https://www.douyin.com/login/"},
    {"url": "https://passport.douyin.com/"},
    {"url": "https://evil.test/"},
])
def test_visible_challenge_or_login_navigation_still_blocks_self_success(page_options):
    async def check():
        page = Page(**page_options)
        observer = CookieAccountEvidence(page)
        observer.start_navigation()
        page.response()
        assert await observer.wait(timeout=.05) is False

    asyncio.run(check())


def test_missing_self_response_times_out_without_cached_fallback():
    async def check():
        page = Page()
        observer = CookieAccountEvidence(page)
        observer.start_navigation()
        assert await observer.wait(timeout=.02) is False
        assert page.handlers == {"request": [], "response": []}

    asyncio.run(check())
