"""Verified workspace credentials reach the actual collector/browser boundary."""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from douyin_intelligence import download_credentials_adapter as adapter
from douyin_intelligence.collector import creator_commands
from douyin_intelligence.config import load_config
from douyin_intelligence.search_collector import search_command


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setenv("HAIKE_DOWNLOAD_CREDENTIALS_DIR", str(tmp_path / "private"))
    store = adapter.credential_store()
    cookies = [{"name": "sessionid", "value": "fixture-private-download", "domain": ".douyin.com",
                "path": "/", "expires": -1, "secure": True, "httpOnly": True}]
    store.save("douyin", 17, cookies, verified=True, user_agent="fixture-chrome-ua", profile_dir=str(tmp_path / "download-profile"))
    store.select("douyin", 17)
    return store


def test_selected_account_reaches_both_command_builders_without_raw_cookie(saved, tmp_path):
    config = load_config()
    commands = [item[1] for item in creator_commands(config, tmp_path)]
    commands.append(search_command(config, tmp_path, 10, ["海客"]))
    for command in commands:
        assert command[command.index("--download-account-id") + 1] == "17"
        assert "fixture-private-download" not in " ".join(command)
        assert "--cookies" not in command


def test_supported_cookie_login_configuration_is_consumed_by_context(saved):
    cookies = adapter.account_cookies(17)
    upstream = SimpleNamespace(ENABLE_GET_MEDIA=True, ENABLE_GET_MEIDAS=True)
    argv = adapter.configure_cookie_login(upstream, ["--platform", "dy", "--lt", "qrcode"], cookies)
    assert upstream.LOGIN_TYPE == "cookie"
    assert upstream.COOKIES == "sessionid=fixture-private-download"
    assert argv == ["--platform", "dy", "--lt", "cookie"]
    assert "fixture-private-download" not in " ".join(argv)
    context = SimpleNamespace(add_cookies=AsyncMock())
    asyncio.run(adapter.inject_download_cookies(context, cookies))
    context.add_cookies.assert_awaited_once_with(cookies)


def test_unverified_selected_account_fails_before_browser_injection(saved):
    saved.update_status("douyin", 17, "unconfirmed")
    with pytest.raises(adapter.credential_module().DownloadCredentialError):
        adapter.account_cookies(17)


def _script():
    path = Path(__file__).resolve().parents[1] / "scripts/download_douyin_mediacrawler.py"
    spec = importlib.util.spec_from_file_location("single_download_credentials_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_single_download_defaults_to_selected_account_and_keeps_values_memory_only(saved, tmp_path, monkeypatch, capsys):
    script = _script()
    observed = []

    async def resolve(args, cookies):
        observed.extend(cookies)
        return "7686317511540821299", "fixture title", "https://cdn.example/fixture.mp4"

    monkeypatch.setattr(script, "resolve", resolve)
    from douyin_intelligence import materials
    monkeypatch.setattr(materials, "download_video", lambda url, destination, config: destination.write_bytes(b"fixture-mp4"))
    monkeypatch.setattr("sys.argv", ["download", "7686317511540821299", "--output-dir", str(tmp_path / "out")])
    assert script.main() == 0
    assert observed[0]["value"] == "fixture-private-download"
    assert "fixture-private-download" not in capsys.readouterr().out
    assert not list(saved.root.glob(".download-*"))
    receipt = next((tmp_path / "out").rglob("download.json")).read_text()
    assert "fixture-private-download" not in receipt
    assert json.loads(receipt)["cookie_source"] == "download_account"


def test_single_download_explicit_cookie_file_keeps_precedence(saved, tmp_path, monkeypatch):
    script = _script()
    expected = [{"name": "sessionid", "value": "explicit-fixture"}]
    monkeypatch.setattr(script, "read_cookies", lambda path: expected)
    cookies, source = script.selected_cookies(SimpleNamespace(cookies="fixture.txt", account_id=17))
    assert cookies == expected and source == "explicit"


def test_single_download_exception_leaves_no_temporary_cookie_file(saved, monkeypatch, capsys):
    script = _script()

    async def fail(*args):
        raise RuntimeError("fixture-private-download")

    monkeypatch.setattr(script, "resolve", fail)
    monkeypatch.setattr("sys.argv", ["download", "7686317511540821299", "--account-id", "17"])
    assert script.main() == 1
    assert "fixture-private-download" not in capsys.readouterr().err
    assert not list(saved.root.glob(".download-*"))


@pytest.mark.parametrize("blocked_login", [False, True])
def test_real_runner_injects_store_cookie_before_upstream_opens_page(saved, tmp_path, monkeypatch, blocked_login, capsys):
    import logging
    import sys
    from douyin_intelligence import mediacrawler_runner as runner

    class Page:
        def __init__(self):
            self.handlers = {}

        def on(self, event, callback):
            self.handlers.setdefault(event, []).append(callback)

        def remove_listener(self, event, callback):
            self.handlers[event].remove(callback)

        async def goto(self, *args, **kwargs):
            pass

        def is_closed(self):
            return False

    class Context:
        def __init__(self):
            self.pages = []
            self.added = []
            self.overrides = []

        async def add_cookies(self, cookies):
            self.added.extend(cookies)

        async def new_page(self):
            assert self.added[0]["value"] == "fixture-private-download"
            page = Page()
            self.pages.append(page)
            return page

        async def new_cdp_session(self, page):
            context = self

            class Session:
                async def send(self, method, params):
                    context.overrides.append((method, params))

                async def detach(self):
                    pass
            return Session()

    context = Context()
    upstream = SimpleNamespace()
    async def update_aweme(item):
        return None
    class Store:
        async def store_content(self, content_item):
            return None
    store_module = SimpleNamespace(update_douyin_aweme=update_aweme,
        DouyinStoreFactory=type("StoreFactory", (), {"create_store": staticmethod(Store)}))
    monkeypatch.setitem(sys.modules, "store", SimpleNamespace(douyin=store_module))
    monkeypatch.setitem(sys.modules, "store.douyin", store_module)
    monkeypatch.setitem(sys.modules, "config", upstream)
    monkeypatch.setitem(sys.modules, "playwright.async_api", SimpleNamespace(BrowserContext=Context, Page=Page))
    monkeypatch.setitem(sys.modules, "media_platform.douyin.client", SimpleNamespace(DouYinClient=type("Client", (), {})))
    login_class = type("Login", (), {})
    monkeypatch.setitem(sys.modules, "media_platform.douyin.login", SimpleNamespace(DouYinLogin=login_class))
    monkeypatch.setitem(sys.modules, "loguru", SimpleNamespace(logger=SimpleNamespace(remove=lambda: None)))
    monkeypatch.setattr(logging, "disable", lambda level: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["runner", "--crawler-root", str(tmp_path), "--cdp-port", "9923", "--download-account-id", "17", "--", "--lt", "qrcode"])

    def upstream_main(*args, **kwargs):
        assert upstream.ENABLE_GET_MEDIA is False and upstream.ENABLE_GET_MEIDAS is False
        assert login_class.begin is login_class.check_page_display_slider is login_class.move_slider
        assert sys.argv[-2:] == ["--lt", "cookie"]
        assert upstream.COOKIES == "sessionid=fixture-private-download"
        asyncio.run(Context.new_page(context))
        if blocked_login:
            asyncio.run(login_class().begin())

    monkeypatch.setattr(runner.runpy, "run_path", upstream_main)
    if blocked_login:
        with pytest.raises(SystemExit) as stopped:
            runner.main()
        assert stopped.value.code == 3
    else:
        runner.main()
    assert context.added == adapter.account_cookies(17)
    assert context.overrides == [("Network.setUserAgentOverride", {"userAgent": "fixture-chrome-ua"})]
    output = capsys.readouterr().out
    assert "fixture-private-download" not in output
    assert ('"status": "needs_human_verification"' in output) is blocked_login


def test_collection_profiles_ports_and_run_paths_are_separate_per_account(saved, tmp_path):
    cookies = adapter.account_cookies(17)
    saved.save("douyin", 18, cookies, verified=True)
    original = load_config()
    first = adapter.download_collection_config(original)
    other = load_config()
    other["media_crawler"]["download_account_id"] = 18
    second = adapter.download_collection_config(other)
    for field in ("user_data_dir", "browser_lease_root", "browser_state_path", "runs_output", "cdp_port"):
        assert first["media_crawler"][field] != second["media_crawler"][field]
    assert first["media_crawler"]["cdp_port"] == 10017
    assert second["media_crawler"]["cdp_port"] == 10018
    assert adapter.download_collection_config(first) == first
    assert Path(first["media_crawler"]["runs_output"]).is_relative_to(Path(original["media_crawler"]["runs_output"]))


def test_proxy_transport_is_rejected_before_browser_prepare(saved, monkeypatch):
    from douyin_intelligence import search_collector
    saved.save("douyin", 17, adapter.account_cookies(17), verified=True,
               proxy="http://fixture-user:fixture-password@127.0.0.1:9191")
    monkeypatch.setattr(search_collector, "BrowserSession", lambda *args: pytest.fail("browser must not open"))
    with pytest.raises(adapter.credential_module().DownloadCredentialError, match="代理") as error:
        search_collector.collect_search(load_config(), 10, keywords=["测试"])
    assert "fixture-password" not in str(error.value)


def test_no_selected_account_preserves_legacy_browser_configuration(saved):
    saved.delete("douyin", 17)
    config = load_config()
    assert adapter.download_collection_config(config) is config
