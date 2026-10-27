"""The actual bounded probes checkpoint owned live tabs before closing them."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app import download_sessions as service
from app.browser.identity import Identity


def rig(kind, *, navigation_cancel=False):
    events = []
    platform = "shipinhao" if kind == "channels" else "kuaishou"
    cookie = {"name":"sessionid" if platform == "shipinhao" else "kuaishou.server.webday7_st",
              "value":"fixture-only", "domain":"channels.weixin.qq.com" if platform == "shipinhao" else ".kuaishou.com"}
    cookies = [cookie, {"name":"userId", "value":"fixture-user", "domain":".kuaishou.com"}] if platform == "kuaishou" else [cookie]
    if kind == "channels":
        url = "https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/auth/get_auth_info"
        payload = {"errCode":0,"data":{"finderUser":{"nickname":"fixture"}}}
        home = "https://channels.weixin.qq.com/platform"
    elif kind == "kuaishou":
        url = "https://www.kuaishou.com/rest/v/profile/get"
        payload = {"result":1,"userId":"fixture-user","userName":"fixture"}
        home = "https://www.kuaishou.com/new-reco"
    else:
        url = "https://cp.kuaishou.com/rest/cp/creator/pc/home/info"
        payload = {"result":1,"data":{"userId":"fixture-user","userName":"fixture"}}
        home = "https://cp.kuaishou.com/"
    response = SimpleNamespace(url=url,status=200,json=AsyncMock(return_value=payload))

    class Page:
        closed = False
        url = home

        def on(self, event, callback):
            assert event == "response"
            self.callback = callback

        async def goto(self, *_args, **_kwargs):
            events.append("navigate")
            if navigation_cancel:
                raise asyncio.CancelledError()
            self.callback(response)
            await asyncio.sleep(0)

        def get_by_text(self, *_args, **_kwargs):
            return SimpleNamespace(first=SimpleNamespace(is_visible=AsyncMock(return_value=False)))

        async def close(self):
            events.append("close-owned-page")
            self.closed = True

    page = Page()
    unrelated = SimpleNamespace(close=AsyncMock())
    context = SimpleNamespace(new_page=AsyncMock(return_value=page),cookies=AsyncMock(return_value=cookies),
        close=AsyncMock(),add_cookies=AsyncMock(),clear_cookies=AsyncMock(),pages=[unrelated,page])
    return SimpleNamespace(kind=kind,platform=platform,page=page,context=context,events=events,unrelated=unrelated)


async def run_probe(value, checkpoint):
    if value.kind == "cp":
        return await service._probe_kuaishou_publish_scope(value.context, response_timeout=.05,
                                                          checkpoint_callback=checkpoint)
    return await service._probe_download_scope(value.context, SimpleNamespace(platform=value.platform),
                                               response_timeout=.05, checkpoint_callback=checkpoint)


def assert_only_owned_page_closed(value):
    assert value.page.closed
    value.context.close.assert_not_awaited()
    value.unrelated.close.assert_not_awaited()
    value.context.add_cookies.assert_not_awaited()
    value.context.clear_cookies.assert_not_awaited()


@pytest.mark.parametrize("kind", ["channels","kuaishou","cp"])
def test_ready_real_probe_checkpoints_before_its_tab_is_closed(kind):
    async def scenario():
        value = rig(kind)
        async def checkpoint():
            assert not value.page.closed, "tab-scoped sessionStorage must still exist"
            value.events.append("checkpoint-live-tab")
            return True
        result = await run_probe(value, checkpoint)
        assert result == (True if kind == "cp" else "ready")
        assert value.events == ["navigate","checkpoint-live-tab","close-owned-page"]
        assert_only_owned_page_closed(value)
    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["channels","cp"])
@pytest.mark.parametrize("failure", ["rejected","error","cancelled"])
def test_failed_or_cancelled_checkpoint_never_strands_the_probe_tab_or_claims_it_saved(kind, failure):
    async def scenario():
        value = rig(kind)
        async def checkpoint():
            value.events.append("checkpoint-live-tab")
            if failure == "error":
                raise RuntimeError("private exception must not leave the process")
            if failure == "cancelled":
                raise asyncio.CancelledError()
            return False
        if failure == "cancelled":
            with pytest.raises(asyncio.CancelledError):
                await run_probe(value, checkpoint)
        else:
            assert await run_probe(value, checkpoint) == (True if kind == "cp" else "ready")
        assert value.events == ["navigate","checkpoint-live-tab","close-owned-page"]
        assert_only_owned_page_closed(value)
    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["channels","cp"])
def test_cancelled_navigation_still_checkpoints_closes_and_propagates(kind):
    async def scenario():
        value = rig(kind, navigation_cancel=True)
        async def checkpoint():
            assert not value.page.closed
            value.events.append("checkpoint-live-tab")
        with pytest.raises(asyncio.CancelledError):
            await run_probe(value, checkpoint)
        assert value.events == ["navigate","checkpoint-live-tab","close-owned-page"]
        assert_only_owned_page_closed(value)
    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["channels","cp"])
def test_host_cancellation_during_checkpoint_closes_page_and_drains_callback(kind):
    async def scenario():
        value = rig(kind)
        started = asyncio.Event()
        finished = asyncio.Event()
        async def checkpoint():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                finished.set()
        task = asyncio.create_task(run_probe(value, checkpoint))
        waiter = asyncio.create_task(started.wait())
        try:
            completed, _pending = await asyncio.wait({task, waiter}, timeout=1,
                                                     return_when=asyncio.FIRST_COMPLETED)
            if task in completed:
                await task  # Consume an early probe error before the seam opens.
            assert waiter in completed, "checkpoint did not start within its local bound"
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            for owned in (task, waiter):
                if not owned.done():
                    owned.cancel()
            await asyncio.gather(task, waiter, return_exceptions=True)
        assert finished.is_set()
        assert_only_owned_page_closed(value)
    asyncio.run(scenario())


@pytest.mark.parametrize("platform,count", [("shipinhao",1),("kuaishou",2),("douyin",0),("xhs",0)])
def test_refresh_binds_only_owned_native_scopes_and_does_not_fabricate_checkpoint_time(monkeypatch, platform, count):
    async def scenario():
        context = SimpleNamespace(cookies=AsyncMock(return_value=[{"name":"sessionid","value":"fixture","domain":".douyin.com"}]))
        identity = Identity(account_id=7,platform=platform,profile_dir="fixture-profile")
        account = SimpleNamespace(id=7,platform=platform,status="active")
        @asynccontextmanager
        async def locked(*_args):
            yield
        browser = SimpleNamespace(identity_for=lambda row: identity,lock_for=locked,
            context_for=AsyncMock(return_value=context),snapshot_session=AsyncMock(return_value=False))
        runtime = SimpleNamespace(browser=browser,engine=None,open_browsers={})
        store = SimpleNamespace(save=Mock(),read_cookies=lambda *_args,**_kwargs:[],
            metadata=lambda *_args,**_kwargs:{"last_checked_at":"2026-10-16T10:00:00Z"})
        async def downloaded(ctx, row, **options):
            assert ctx is context and row is account
            if count:
                assert callable(options.get("checkpoint_callback"))
                await options["checkpoint_callback"]()
            else:
                assert not options.get("checkpoint_callback")
            return "ready"
        async def published(ctx, **options):
            assert ctx is context
            await options["checkpoint_callback"]()
            return True
        monkeypatch.setattr(service,"_runtime",lambda:runtime)
        monkeypatch.setattr(service,"_account",lambda _:account)
        monkeypatch.setattr(service,"credential_store",lambda:store)
        monkeypatch.setattr(service,"_probe_download_scope",downloaded)
        monkeypatch.setattr(service,"_probe_kuaishou_publish_scope",published)
        monkeypatch.setattr(service,"download_session_metadata",lambda _: {"id":7,"observability":{"checkpoint_at":None}})
        monkeypatch.setattr(service,"_PUBLISH_EVIDENCE",{})
        monkeypatch.setattr(service,"_CHECK_LOCKS",{})
        result = await service.refresh_download_session(7)
        assert result["observability"]["checkpoint_at"] is None
        assert browser.snapshot_session.await_count == count
        for call in browser.snapshot_session.await_args_list:
            assert call.args == (identity,context)
        assert account.status == "active"
        store.save.assert_called_once()
    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["channels","cp"])
def test_hung_optional_checkpoint_is_bounded_drained_and_does_not_change_auth_verdict(monkeypatch, kind):
    async def scenario():
        value = rig(kind)
        drained = asyncio.Event()
        async def checkpoint():
            try:
                await asyncio.Event().wait()
            finally:
                drained.set()
        monkeypatch.setattr(service,"_PROBE_CHECKPOINT_TIMEOUT_SECONDS",.02)
        assert await asyncio.wait_for(run_probe(value, checkpoint), timeout=1) == (True if kind == "cp" else "ready")
        assert drained.is_set()
        assert_only_owned_page_closed(value)
    asyncio.run(scenario())
