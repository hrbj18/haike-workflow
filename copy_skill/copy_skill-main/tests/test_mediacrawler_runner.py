from __future__ import annotations

import asyncio
import json

import pytest

from douyin_intelligence.mediacrawler_runner import (
    HumanVerificationRequired, install_human_verification_guard, reuse_existing_page,
)


class FakePage:
    def __init__(self, closed: bool = False):
        self.closed = closed

    def is_closed(self) -> bool:
        return self.closed


class FakeContext:
    def __init__(self, pages):
        self.pages = list(pages)


def test_runner_reuses_existing_project_page_without_creating_second_page() -> None:
    existing = FakePage()
    context = FakeContext([existing])

    async def forbidden(_context):
        raise AssertionError("must not create another page")

    page, audit = asyncio.run(reuse_existing_page(context, forbidden))
    assert page is existing
    assert audit == {"pages_before": 1, "pages_after": 1, "reused_existing_page": True}


def test_runner_creates_one_page_only_when_context_is_empty() -> None:
    context = FakeContext([])

    async def create(value):
        page = FakePage()
        value.pages.append(page)
        return page

    page, audit = asyncio.run(reuse_existing_page(context, create))
    assert page is context.pages[0]
    assert audit == {"pages_before": 0, "pages_after": 1, "reused_existing_page": False}


@pytest.mark.parametrize("method", ["begin", "check_page_display_slider", "move_slider"])
def test_verified_account_never_falls_back_to_upstream_login_or_slider(method, capsys):
    class Login:
        async def begin(self):
            pytest.fail("upstream login must not run after pong rejects account")

        async def check_page_display_slider(self, *args, **kwargs):
            pytest.fail("upstream challenge solver must not run")

        async def move_slider(self, *args, **kwargs):
            pytest.fail("upstream challenge gestures must not run")

    install_human_verification_guard(Login, credential_backed=True)
    with pytest.raises(HumanVerificationRequired, match="人工确认"):
        asyncio.run(getattr(Login(), method)())
    line = capsys.readouterr().out.strip()
    prefix = "COPY_SKILL_STATUS "
    assert line.startswith(prefix)
    assert json.loads(line[len(prefix):]) == {
        "status": "needs_human_verification", "platform": "douyin",
        "reason": "login_or_verification_required",
        "message": "抖音登录需要人工确认，请在工作台处理后恢复；未自动处理验证码",
    }


def test_legacy_interactive_login_keeps_manual_login_but_blocks_automatic_slider(capsys):
    called = []

    class Login:
        async def begin(self):
            called.append("manual-login")

        async def check_page_display_slider(self, *args, **kwargs):
            pytest.fail("upstream challenge solver must not run")

        async def move_slider(self, *args, **kwargs):
            pytest.fail("upstream challenge gestures must not run")

    original_begin = Login.begin
    install_human_verification_guard(Login, credential_backed=False)
    assert Login.begin is original_begin
    asyncio.run(Login().begin())
    assert called == ["manual-login"]
    with pytest.raises(HumanVerificationRequired):
        asyncio.run(Login().check_page_display_slider(move_step=10, slider_level="easy"))
    with pytest.raises(HumanVerificationRequired):
        asyncio.run(Login().move_slider("background", "gap", move_step=3))
    assert capsys.readouterr().out.count('"status": "needs_human_verification"') == 2

