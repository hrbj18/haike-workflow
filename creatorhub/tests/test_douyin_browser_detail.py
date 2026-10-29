"""Only an owned page's target response can supply browser video evidence."""
import asyncio
from types import SimpleNamespace

import pytest

from app.browser.douyin_detail import DetailReadError, fetch_douyin_video_detail
from app.browser.identity import Identity
from app.risk import RiskCategory, classify_platform_error


TARGET = "7695986814054477297"
OTHER = "7695986814054477298"
API = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=" + TARGET
VIDEO = {"aweme_id": TARGET, "video": {"duration": 30000,
         "play_addr": {"url_list": ["https://cdn.example/PRIVATE_SIGNED_URL"]}}}


class Page:
    def __init__(self, specs, *, final_url=None, gate=None, document_status=200):
        self.specs = specs
        self.url = "about:blank"
        self.final_url = final_url
        self.gate = gate or {"challenge": False, "login": False}
        self.document_status = document_status
        self.listeners = {}
        self.closed = False
        self.navigations = []
        self.json_reads = []

    def on(self, event, callback):
        self.listeners[event] = callback

    def remove_listener(self, event, callback):
        assert self.listeners[event] is callback
        self.listeners.pop(event)

    async def goto(self, url, **kwargs):
        self.navigations.append(url)
        self.url = self.final_url or url
        for index, spec in enumerate(self.specs):
            async def read(spec=spec, index=index):
                self.json_reads.append(index)
                if spec.get("error"):
                    raise ValueError("PRIVATE_COOKIE PRIVATE_SIGNED_URL")
                return spec.get("payload", {"status_code": 0, "aweme_detail": VIDEO})
            response = SimpleNamespace(url=spec.get("url", API), status=spec.get("status", 200),
                json=read, request=SimpleNamespace(method=spec.get("method", "GET"),
                    frame=SimpleNamespace(page=spec.get("page", self))))
            self.listeners["response"](response)
        await asyncio.sleep(0)
        return SimpleNamespace(status=self.document_status)

    async def evaluate(self, script):
        assert "fetch(" not in script and "localStorage" not in script
        return dict(self.gate)

    def is_closed(self):
        return self.closed

    async def close(self):
        self.closed = True


def read(page):
    seen = []

    async def new_page(identity, *, block_media):
        seen.append((identity, block_media))
        return page

    identity = Identity(account_id=3, profile_dir="fixture-owned-profile", platform="douyin")
    result = asyncio.run(fetch_douyin_video_detail(SimpleNamespace(new_page=new_page), identity,
                                                 TARGET, wait_seconds=0.02))
    assert seen == [(identity, True)]
    assert page.closed and not page.listeners
    assert page.navigations == ["https://www.douyin.com/video/" + TARGET]
    return result


def test_exact_https_target_detail_is_returned_from_owned_page():
    page = Page([{}])
    raw, error = read(page)
    assert raw == VIDEO and error == ""
    assert page.json_reads == [0]


def test_feed_only_returns_the_exact_target_video():
    recommended = {**VIDEO, "aweme_id": OTHER}
    page = Page([{"url": "https://www.douyin.com/aweme/v1/web/tab/feed/?fixture=1",
                  "payload": {"status_code": 0, "aweme_list": [recommended, VIDEO]}}])
    assert read(page) == (VIDEO, "")


@pytest.mark.parametrize("url", [API.replace("https:", "http:"),
    API.replace("www.douyin.com", "www.douyin.com.evil.example"),
    API.replace("www.douyin.com", "evil.example"),
    API.replace("www.douyin.com", "user:secret@www.douyin.com"),
    API.replace("www.douyin.com", "www.douyin.com:444"),
    API.replace("/aweme/detail/", "/aweme/post/"),
    API.replace(TARGET, OTHER), API + "&aweme_id=" + OTHER])
def test_wrong_host_protocol_endpoint_or_request_id_is_never_read(url):
    page = Page([{"url": url}])
    assert read(page) == (None, "detail_unconfirmed")
    assert page.json_reads == []


@pytest.mark.parametrize("spec", [{"page": object()}, {"method": "POST"}])
def test_other_page_or_wrong_request_method_is_not_evidence(spec):
    page = Page([spec])
    assert read(page) == (None, "detail_unconfirmed")
    assert page.json_reads == []


@pytest.mark.parametrize("payload", [
    {"status_code": 0, "aweme_detail": {**VIDEO, "aweme_id": OTHER}},
    {"status_code": 0, "aweme_detail": {"aweme_id": TARGET, "images": [{}]}},
    {"status_code": 0, "aweme_detail": {"aweme_id": TARGET, "video": {}}},
    {"status_code": 0, "aweme_detail": {**VIDEO, "images": [{}]}},
    {"status_code": 8, "aweme_detail": VIDEO},
    {"status_code": False, "aweme_detail": VIDEO},
    {"aweme_detail": VIDEO},
])
def test_missing_business_success_or_target_video_never_authorizes_download(payload):
    assert read(Page([{"payload": payload}])) == (None, "detail_unconfirmed")


@pytest.mark.parametrize("gate,expected", [({"challenge": True, "login": False}, "verification_required"),
    ({"challenge": False, "login": True}, "login_required")])
def test_visible_login_or_challenge_blocks_even_valid_target_response(gate, expected):
    assert read(Page([{}], gate=gate)) == (None, expected)


@pytest.mark.parametrize("payload,expected", [
    ({"status_code": 8, "status_msg": "请完成安全验证"}, "verification_required"),
    ({"status_code": 8, "status_msg": "请登录"}, "login_required"),
])
def test_platform_challenge_or_login_response_is_explicit(payload, expected):
    assert read(Page([{"payload": payload}])) == (None, expected)


def test_foreign_verify_url_cannot_create_a_platform_risk_signal():
    assert read(Page([{}], final_url="https://foreign.example/verify")) == (None, "detail_unconfirmed")


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_http_status_is_preserved_without_returning_raw_transport_text(status):
    assert read(Page([{"status": status}])) == (None, "http_" + str(status))


def test_network_json_failure_is_safe_and_page_is_closed():
    assert read(Page([{"error": True}])) == (None, "network_error")


@pytest.mark.parametrize("code,category", [("verification_required", RiskCategory.RISK),
    ("login_required", RiskCategory.AUTH), ("network_error", RiskCategory.NETWORK),
    ("http_403", RiskCategory.RISK), ("http_429", RiskCategory.RISK),
    ("http_401", RiskCategory.AUTH), ("http_503", RiskCategory.NETWORK),
    ("detail_unconfirmed", RiskCategory.BUSINESS)])
def test_safe_error_codes_preserve_engine_risk_categories(code, category):
    assert classify_platform_error(DetailReadError(code))[0] == category
