"""Channels profile checks require business-level authentication evidence."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.browser.channels_fetcher import fetch_channels_self_profile


class _Locator:
    @property
    def first(self):
        return self

    async def is_visible(self, **_kwargs):
        return False


class _Response:
    url = (
        "https://channels.weixin.qq.com/cgi-bin/"
        "mmfinderassistant-bin/auth/get_auth_info"
    )

    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    async def json(self):
        return self.payload


class _Page:
    def __init__(self, responses=(), url="https://channels.weixin.qq.com/platform"):
        self.responses = responses
        self.url = url
        self.handler = None
        self.closed = False

    def on(self, event, handler):
        if event == "response":
            self.handler = handler

    async def goto(self, *_args, **_kwargs):
        for response in self.responses:
            await self.handler(response)

    async def wait_for_timeout(self, _ms):
        pass

    def get_by_text(self, *_args, **_kwargs):
        return _Locator()

    async def close(self):
        self.closed = True


class _Manager:
    def __init__(self, page):
        self.page = page

    async def new_page(self, *_args):
        return self.page


class ChannelsProfileEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_kuaishou_health_failure_checkpoints_before_closing_its_tab(self):
        from app.browser.ks_fetcher import fetch_ks_self_profile
        page = _Page()
        page.context = SimpleNamespace(cookies=AsyncMock(return_value=[]))
        page.goto = AsyncMock(side_effect=RuntimeError("synthetic local navigation failure"))
        saved = []

        class Manager(_Manager):
            async def snapshot_session(self, identity, context):
                self_outer.assertFalse(page.closed)
                self_outer.assertIs(context, page.context)
                saved.append(True)

        self_outer = self
        profile, error = await fetch_ks_self_profile(Manager(page), object())
        self.assertEqual(profile, {})
        self.assertTrue(error)
        self.assertEqual(saved, [True])
        self.assertTrue(page.closed)

    async def test_short_health_page_checkpoints_before_tab_storage_is_destroyed(self):
        page = _Page([_Response({"errCode": 0, "data": {"nickname": "fixture"}})])
        page.context = object()
        order = []

        class Manager(_Manager):
            async def snapshot_session(self, identity, context):
                self_outer.assertFalse(page.closed)
                self_outer.assertIs(context, page.context)
                order.append("snapshot")
                return True

        self_outer = self
        profile, error = await fetch_channels_self_profile(Manager(page), object())
        self.assertEqual(error, "")
        self.assertEqual(profile, {"nickname": "fixture"})
        self.assertEqual(order, ["snapshot"])
        self.assertTrue(page.closed)

    async def probe(self, *responses, url="https://channels.weixin.qq.com/platform"):
        page = _Page(responses, url)
        result = await fetch_channels_self_profile(_Manager(page), object())
        self.assertTrue(page.closed)
        return result

    async def test_business_failure_cannot_authenticate_nickname_payload(self):
        profile, error = await self.probe(_Response({
            "errCode": 300334,
            "data": {"finderUser": {"nickname": "stale-display-name"}},
        }))
        self.assertEqual(profile, {})
        self.assertEqual(error, "unconfirmed")

    async def test_transient_login_url_without_auth_response_is_unconfirmed(self):
        profile, error = await self.probe(
            url="https://channels.weixin.qq.com/login.html")
        self.assertEqual(profile, {})
        self.assertEqual(error, "unconfirmed")

    async def test_unknown_business_error_is_not_declared_logged_out(self):
        profile, error = await self.probe(_Response({"errCode": 99999, "data": {}}))
        self.assertEqual(profile, {})
        self.assertEqual(error, "unconfirmed")

    async def test_profile_without_business_success_is_not_accepted(self):
        profile, error = await self.probe(_Response({
            "data": {"finderUser": {"nickname": "display-only"}},
        }))
        self.assertEqual(profile, {})
        self.assertEqual(error, "unconfirmed")

    async def test_http_failure_cannot_authenticate_success_shaped_payload(self):
        profile, error = await self.probe(_Response({
            "errCode": 0, "data": {"finderUser": {"nickname": "cached-name"}},
        }, status=500))
        self.assertEqual(profile, {})
        self.assertEqual(error, "unconfirmed")

    async def test_conflicting_auth_responses_do_not_mark_account_active(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                responses = [
                    _Response({"errCode": 0, "data": {"finderUser": {"nickname": "valid-name"}}}),
                    _Response({"errCode": 300334, "data": {}}),
                ]
                if reverse:
                    responses.reverse()
                profile, error = await self.probe(*responses)
                self.assertEqual(profile, {})
                self.assertEqual(error, "unconfirmed")

    async def test_success_profile_on_login_url_is_a_conflict(self):
        profile, error = await self.probe(_Response({
            "errCode": 0, "data": {"nickname": "valid-name"},
        }), url="https://channels.weixin.qq.com/login.html")
        self.assertEqual(profile, {})
        self.assertEqual(error, "unconfirmed")

    async def test_supported_business_success_shapes_are_preserved(self):
        for payload in (
            {"errCode": 0, "data": {"finderUser": {"nickname": "valid-name"}}},
            {"baseResponse": {"retCode": "0"}, "data": {"finder": {"nickName": "valid-name"}}},
            {"err_code": 0, "data": {"finderInfo": {"nickname": "valid-name"}}},
            {"errCode": 0, "data": {"nickname": "valid-name"}},
        ):
            with self.subTest(payload=payload):
                profile, error = await self.probe(_Response(payload))
                self.assertEqual(profile, payload["data"])
                self.assertEqual(error, "")


if __name__ == "__main__":
    unittest.main()
