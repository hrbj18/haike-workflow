"""A public KS profile is not proof of our login; CP is checked separately."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import download_sessions as service


class _Response:
    def __init__(self, payload, *, cp=False, status=200, host=None):
        self.status = status
        self.payload = payload
        self.url = ("https://" + (host or ("cp.kuaishou.com" if cp else "www.kuaishou.com"))
                    + ("/rest/cp/creator/pc/home/infoV2" if cp else "/rest/v/profile/get"))

    async def json(self):
        return self.payload


class _Page:
    def __init__(self, response):
        self.response = response
        self.closed = False

    def on(self, _event, callback):
        self.callback = callback

    async def goto(self, url, **_kwargs):
        self.url = url
        self.callback(self.response)
        await asyncio.sleep(0)

    def get_by_text(self, *_args, **_kwargs):
        return SimpleNamespace(first=SimpleNamespace(is_visible=AsyncMock(return_value=False)))

    async def close(self):
        self.closed = True


def context(response):
    page = _Page(response)
    return SimpleNamespace(new_page=AsyncMock(return_value=page), page=page,
        cookies=AsyncMock(return_value=[
            {"name": "userId", "value": "123", "domain": ".kuaishou.com"},
            {"name": "passToken", "value": "fixture", "domain": ".kuaishou.com"}]))


class KuaishouScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_current_live_user_id_can_authenticate_web_profile(self):
        for returned, expected in (("123", "ready"), ("999", "unconfirmed"), (None, "unconfirmed")):
            with self.subTest(returned=returned):
                ctx = context(_Response({"result": 1, "userName": "fixture", "userId": returned}))
                result = await service._probe_download_scope(ctx, SimpleNamespace(platform="kuaishou"),
                                                              response_timeout=0.02)
                self.assertEqual(result, expected)
                self.assertTrue(ctx.page.closed)

    async def test_nested_profile_user_id_is_matched_to_live_cookie(self):
        ctx = context(_Response({"result": 1, "userProfile": {
            "profile": {"user_id": "123", "user_name": "fixture"}}}))
        self.assertEqual(await service._probe_download_scope(ctx, SimpleNamespace(platform="kuaishou"),
                                                            response_timeout=0.02), "ready")

    async def test_cp_needs_success_code_name_and_matching_current_user_id(self):
        for code, user_id, expected in ((1, "123", True), (1, "999", False),
                                       (50, "123", False), (None, "123", False)):
            with self.subTest(code=code, user_id=user_id):
                ctx = context(_Response({"result": code, "data": {
                    "userName": "fixture", "userId": user_id}}, cp=True))
                self.assertEqual(await service._probe_kuaishou_publish_scope(ctx, response_timeout=0.02), expected)
                self.assertTrue(ctx.page.closed)

    async def test_http_failure_or_another_host_never_confirms_cp(self):
        payload = {"result": 1, "data": {"userName": "fixture", "userId": "123"}}
        for options in ({"status": 500}, {"host": "evil.example"}):
            ctx = context(_Response(payload, cp=True, **options))
            self.assertFalse(await service._probe_kuaishou_publish_scope(ctx, response_timeout=0.02))
