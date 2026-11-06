"""Taskbar presentation never changes a personal browser or account ownership."""
import asyncio
import threading
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from app.browser.manager import BrowserManager
from app.browser import window_presentation as windows
from app.browser.window_presentation import WindowInfo, WindowPresentation, WS_EX_APPWINDOW, WS_EX_TOOLWINDOW


CHROME = "C:/Google/Chrome/chrome.exe"


class Shell:
    def __init__(self):
        self.rows = {
            10: WindowInfo(10, 100, CHROME, "Chrome", 0x100, True),
            20: WindowInfo(20, 200, CHROME, "Chrome.Account", WS_EX_APPWINDOW | 0x100, False),
        }
        self.ids, self.styles = [], []
        self.default_app_id = lambda _: "Chrome"

    def windows(self):
        return list(self.rows.values())

    def set_app_id(self, handle, app_id):
        self.ids.append((handle, app_id))
        self.rows[handle] = replace(self.rows[handle], app_id=app_id)

    def set_style(self, handle, style):
        self.styles.append((handle, style))
        self.rows[handle] = replace(self.rows[handle], style=style)


def test_owned_background_window_joins_chrome_and_leaves_taskbar_without_touching_personal_window():
    shell = Shell()
    personal = shell.rows[10]
    presentation = WindowPresentation(shell)
    assert presentation.apply(200, background=True) == 2
    assert shell.rows[10] == personal
    assert shell.ids == [(20, "Chrome")]
    assert shell.rows[20].style & WS_EX_TOOLWINDOW
    assert not shell.rows[20].style & WS_EX_APPWINDOW
    assert shell.rows[20].style & 0x100
    assert presentation.apply(200, background=True) == 0


@pytest.mark.parametrize("original", [0x100, WS_EX_APPWINDOW | 0x100])
def test_interactive_open_restores_original_taskbar_bits_and_preserves_other_new_styles(original):
    shell = Shell()
    shell.rows[20] = replace(shell.rows[20], style=original)
    presentation = WindowPresentation(shell)
    presentation.apply(200, background=True)
    shell.rows[20] = replace(shell.rows[20], style=shell.rows[20].style | 0x8)
    presentation.apply(200, background=False)
    assert shell.rows[20].style == original | 0x8
    assert shell.rows[20].app_id == shell.rows[10].app_id
    assert not presentation._hidden_bits


def test_new_windows_in_the_same_owned_process_get_the_same_group_and_background_policy():
    shell = Shell()
    presentation = WindowPresentation(shell)
    presentation.apply(200, background=True)
    shell.rows[21] = WindowInfo(21, 200, CHROME, "Chrome.Account", 0x100, False)
    presentation.apply(200, background=True)
    assert all(shell.rows[handle].app_id == "Chrome" for handle in (20, 21))
    assert all(shell.rows[handle].style & WS_EX_TOOLWINDOW for handle in (20, 21))
    presentation.apply(200, background=False)
    assert all(not shell.rows[handle].style & WS_EX_TOOLWINDOW for handle in (20, 21))


def test_grouping_falls_back_to_registered_chrome_when_personal_browser_is_closed():
    shell = Shell()
    del shell.rows[10]
    WindowPresentation(shell).apply(200, background=False)
    assert shell.rows[20].app_id == "Chrome"


def test_an_unrelated_browser_executable_is_never_used_as_the_reference_group():
    shell = Shell()
    shell.rows[10] = replace(shell.rows[10], executable="C:/Another/chrome.exe", app_id="OtherChrome")
    shell.default_app_id = lambda _: ""
    WindowPresentation(shell).apply(200, background=True)
    assert not shell.ids
    assert shell.rows[20].style & WS_EX_TOOLWINDOW
    assert shell.rows[10].app_id == "OtherChrome"


def test_shell_grouping_failure_still_hides_background_button_and_preserves_retry_state():
    shell = Shell()
    shell.set_app_id = Mock(side_effect=OSError("fixture"))
    presentation = WindowPresentation(shell)
    presentation.apply(200, background=True)
    assert shell.rows[20].style & WS_EX_TOOLWINDOW
    shell.set_style = Mock(side_effect=OSError("fixture"))
    presentation.apply(200, background=False)
    assert (200, 20) in presentation._hidden_bits


def test_unavailable_native_api_and_invalid_processes_do_nothing(monkeypatch):
    monkeypatch.setattr(windows, "_windows_api", lambda: None)
    presentation = WindowPresentation()
    assert not presentation.available
    assert presentation.apply(200, background=True) == 0
    shell = Shell()
    presentation = WindowPresentation(shell)
    for pid in (None, 0, -1, True, "200"):
        assert presentation.apply(pid, background=True) == 0
    assert not shell.ids and not shell.styles


def context(process_id=200):
    session = SimpleNamespace(send=AsyncMock(return_value={"processInfo": [
        {"type": "renderer", "id": 999}, {"type": "browser", "id": process_id}]}), detach=AsyncMock())
    handlers = {}
    ctx = SimpleNamespace(browser=SimpleNamespace(new_browser_cdp_session=AsyncMock(return_value=session)),
        on=lambda event, handler: handlers.setdefault(event, []).append(handler))
    return ctx, session, handlers


def test_manager_resolves_only_owned_browser_pid_caches_it_and_updates_popup_windows(tmp_path):
    manager = BrowserManager(tmp_path)
    controller = SimpleNamespace(available=True, apply=Mock(return_value=1), forget=Mock())
    manager._window_presentation = controller
    ctx, session, handlers = context()

    async def run():
        await manager._present_windows(ctx, background=True)
        handlers["page"][0](object())
        await manager._window_contexts[id(ctx)]["task"]
        await manager._present_windows(ctx, background=False)
        handlers["close"][0]()

    asyncio.run(run())
    session.send.assert_awaited_once_with("SystemInfo.getProcessInfo")
    session.detach.assert_awaited_once()
    assert controller.apply.call_args_list == [call(200, background=True), call(200, background=True), call(200, background=False)]
    controller.forget.assert_called_once_with(200)
    assert not manager._window_contexts


@pytest.mark.parametrize("pid", [None, True, "200", -1])
def test_unknown_browser_pid_never_falls_back_to_another_window(tmp_path, pid):
    manager = BrowserManager(tmp_path)
    controller = SimpleNamespace(available=True, apply=Mock())
    manager._window_presentation = controller
    ctx, session, _ = context(pid)
    asyncio.run(manager._present_windows(ctx, background=True))
    controller.apply.assert_not_called()
    session.detach.assert_awaited_once()
    assert not manager._window_contexts


def test_native_presentation_failure_does_not_prevent_browser_use(tmp_path):
    manager = BrowserManager(tmp_path)
    manager._window_presentation = SimpleNamespace(available=True, apply=Mock(side_effect=OSError("fixture")))
    ctx, _, _ = context()
    asyncio.run(manager._present_windows(ctx, background=False))
    assert manager._window_contexts[id(ctx)]["background"] is False


def test_manager_stop_releases_temporary_window_state_without_close_events(tmp_path):
    manager = BrowserManager(tmp_path)
    controller = SimpleNamespace(available=True, apply=Mock(return_value=1), forget=Mock())
    manager._window_presentation = controller
    manager._pw = SimpleNamespace(stop=AsyncMock())
    ctx, _, _ = context()

    async def run():
        await manager._present_windows(ctx, background=True)
        await manager.stop()

    asyncio.run(run())
    controller.forget.assert_called_once_with(200)
    assert not manager._window_contexts


def test_foreground_request_wins_over_an_inflight_background_refresh_and_keeps_popup_updates(tmp_path):
    manager = BrowserManager(tmp_path)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def apply(pid, *, background):
        calls.append((pid, background))
        if len(calls) == 2:
            entered.set()
            assert release.wait(3)

    manager._window_presentation = SimpleNamespace(available=True, apply=apply)
    ctx, _, handlers = context()

    async def run():
        await manager._present_windows(ctx, background=True)
        handlers["page"][0](object())
        assert await asyncio.to_thread(entered.wait, 3)
        handlers["page"][0](object())  # A second window appears while enumeration is running.
        interactive = asyncio.create_task(manager._present_windows(ctx, background=False))
        await asyncio.sleep(0)
        release.set()
        await interactive
        await manager._window_contexts[id(ctx)]["task"]

    asyncio.run(run())
    assert calls[:2] == [(200, True), (200, True)]
    assert calls[2:] == [(200, False), (200, False)]
