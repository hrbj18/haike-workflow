"""Best-effort one-shot foreground activation for user-triggered windows."""
from __future__ import annotations

import sys
import time
from functools import lru_cache
from typing import Iterable, NamedTuple


EXPLORER_WINDOW_CLASSES = ("CabinetWClass", "ExploreWClass")
CHROMIUM_WINDOW_CLASSES = ("Chrome_WidgetWin_1",)


class WindowSnapshot(NamedTuple):
    foreground: int
    handles: frozenset[int]


@lru_cache(maxsize=1)
def _win32_api():
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    user32.EnumWindows.argtypes = [enum_proc, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD,
                                         wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindowAsync.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    return ctypes, user32, kernel32, enum_proc


def _handle_value(hwnd) -> int:
    if hwnd is None:
        return 0
    return hwnd if isinstance(hwnd, int) else int(hwnd.value or 0)


def _visible_windows(class_names: Iterable[str]) -> list[tuple[int, str]]:
    api = _win32_api()
    if not api:
        return []
    ctypes, user32, _, enum_proc = api
    allowed = set(class_names)
    windows: list[tuple[int, str]] = []

    @enum_proc
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        class_name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, class_name, len(class_name))
        if class_name.value not in allowed:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, len(title))
        windows.append((_handle_value(hwnd), title.value))
        return True

    user32.EnumWindows(visit, 0)
    return windows


def _foreground_window() -> int:
    api = _win32_api()
    if not api:
        return 0
    return _handle_value(api[1].GetForegroundWindow())


def capture_window_snapshot(class_names: Iterable[str]) -> WindowSnapshot:
    try:
        handles = frozenset(hwnd for hwnd, _ in _visible_windows(class_names))
        return WindowSnapshot(_foreground_window(), handles)
    except Exception:
        return WindowSnapshot(0, frozenset())


def _activate_window(hwnd: int, foreground: int) -> bool:
    api = _win32_api()
    if not api:
        return False
    _, user32, kernel32, _ = api
    current_thread = kernel32.GetCurrentThreadId()
    thread_ids = {
        user32.GetWindowThreadProcessId(handle, None)
        for handle in (foreground, hwnd) if handle
    }
    attached = []
    try:
        for thread_id in thread_ids:
            if thread_id and thread_id != current_thread and \
                    user32.AttachThreadInput(current_thread, thread_id, True):
                attached.append(thread_id)
        user32.ShowWindowAsync(hwnd, 9)  # SW_RESTORE
        flags = 0x0001 | 0x0002 | 0x0040  # SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
        positioned = bool(user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags))  # HWND_TOP
        focused = bool(user32.SetForegroundWindow(hwnd))
        return positioned or focused
    finally:
        for thread_id in reversed(attached):
            user32.AttachThreadInput(current_thread, thread_id, False)


def bring_window_to_front(snapshot: WindowSnapshot, class_names: Iterable[str],
                          title_hint: str = "", timeout: float = 2.0) -> bool:
    """Raise a new or matching window once, unless the user has switched away."""
    if sys.platform != "win32":
        return False
    wanted = title_hint.strip().casefold()
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            windows = _visible_windows(class_names)
            titles = dict(windows)
            handles = set(titles)
            current = _foreground_window()
            title_matches = [
                hwnd for hwnd, title in windows
                if wanted and wanted in title.casefold()
            ]
            target = 0
            if current in handles and (current not in snapshot.handles or
                                       current in title_matches):
                target = current
            if not target:
                target = next((hwnd for hwnd, _ in windows
                               if hwnd not in snapshot.handles), 0)
            if not target and title_matches:
                target = title_matches[0]
            if target:
                latest = _foreground_window()
                if latest not in (0, snapshot.foreground, target):
                    return False
                return _activate_window(target, latest or snapshot.foreground)
            if current not in (0, snapshot.foreground) and current not in handles:
                return False
            time.sleep(0.08)
    except Exception:
        pass
    return False


def bring_new_windows_onscreen(snapshot: WindowSnapshot,
                               class_names: Iterable[str],
                               x: int, y: int,
                               timeout: float = 2.0,
                               width: int = 0, height: int = 0) -> int:
    """把 ``snapshot`` 之后新出现的 Chromium 窗口搬到屏幕内的 ``(x, y)``。

    ★ 2026-09-18:``bring_window_to_front`` 用的是 ``SWP_NOMOVE``(只置顶不挪窝),
    对「窗口上次被自动任务钉在屏幕外」完全无能为力 —— Chromium 会把关闭时的窗口
    位置写进 profile 并在下次启动时原样恢复,而自动任务(publish/collect)正是把
    窗口钉在 ``OFFSCREEN_X/Y``。结果:用户主动打开扫码登录时,窗口开在屏幕外
    (实测视频号 = ``(-2037, 0)-(29, 1170)``,屏宽 2048),他根本看不到二维码。
    这里补上「挪窝」的那一半,作为 CDP ``Browser.setWindowBounds`` 之外的兜底 ——
    它不依赖页面是否已就绪,窗口刚创建就能生效。

    只按类名枚举、**不读窗口标题**:``GetWindowTextW`` 是跨进程消息,目标进程
    卡住时会一起阻塞(``_visible_windows`` 就有这个隐患),而这里只是搬位置,
    用不到标题。返回实际搬动的窗口数。
    """
    if sys.platform != "win32":
        return 0
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                       wintypes.LPARAM)
        user32.EnumWindows.argtypes = [enum_proc, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR,
                                         ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetWindowRect.argtypes = [wintypes.HWND,
                                         ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND,
                                        ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int,
                                        wintypes.UINT]
        user32.SetWindowPos.restype = wintypes.BOOL

        allowed = set(class_names)
        screen_w = int(user32.GetSystemMetrics(0))
        screen_h = int(user32.GetSystemMetrics(1))

        def candidates() -> list[int]:
            found: list[int] = []

            @enum_proc
            def visit(hwnd, _):
                if not user32.IsWindowVisible(hwnd):
                    return True
                name = ctypes.create_unicode_buffer(120)
                user32.GetClassNameW(hwnd, name, len(name))
                if name.value in allowed and _handle_value(hwnd) not in snapshot.handles:
                    found.append(_handle_value(hwnd))
                return True

            user32.EnumWindows(visit, 0)
            return found

        deadline = time.monotonic() + max(0.0, timeout)
        moved = 0
        while True:
            for hwnd in candidates():
                if user32.IsIconic(hwnd):
                    continue
                rect = wintypes.RECT()
                if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    continue
                left, top = rect.left, rect.top
                cur_w, cur_h = rect.right - left, rect.bottom - top
                if cur_w <= 0 or cur_h <= 0:
                    continue
                # 最小化窗口的 GetWindowRect 是哨兵值 (-25600,-25600) 159x27,
                # 别把它当"跑出屏幕"搬进来看起来像新窗口。
                if left <= -20000 or top <= -20000:
                    continue
                if (left >= 0 and top >= 0
                        and rect.right <= screen_w and rect.bottom <= screen_h):
                    continue   # 本来就在屏幕内
                want_w = min(width or screen_w, max(320, screen_w - x - 40), cur_w)
                want_h = min(height or screen_h, max(240, screen_h - y - 60), cur_h)
                # 0x0040 = SWP_SHOWWINDOW;不给 SWP_NOMOVE,所以 left/top 生效。
                user32.SetWindowPos(hwnd, 0, int(x), int(y),
                                    int(want_w), int(want_h), 0x0040)
                moved += 1
            if moved or time.monotonic() >= deadline:
                break
            time.sleep(0.08)
        return moved
    except Exception:
        return 0
