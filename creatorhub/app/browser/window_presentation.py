"""Keep owned account windows in Chrome's taskbar group, with no background buttons.

Window identity affects presentation only. Browser profiles, cookies, proxy routing
and ownership stay unchanged. Native calls are best-effort and Windows-only.
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID


WS_EX_TOOLWINDOW = 0x80
WS_EX_APPWINDOW = 0x40000
_TASKBAR_BITS = WS_EX_TOOLWINDOW | WS_EX_APPWINDOW


@dataclass(frozen=True)
class WindowInfo:
    handle: int
    pid: int
    executable: str
    app_id: str
    style: int
    onscreen: bool


class WindowPresentation:
    """Change only windows proven to belong to a managed browser process."""

    def __init__(self, api=None):
        self._api = api if api is not None else _windows_api()
        self._hidden_bits: dict[tuple[int, int], int] = {}
        self._managed_pids: set[int] = set()
        self._groups: dict[str, str] = {}
        self._lock = threading.Lock()

    @property
    def available(self):
        return self._api is not None

    def apply(self, pid: int, *, background: bool) -> int:
        if self._api is None or type(pid) is not int or pid <= 0:
            return 0
        with self._lock:
            windows = self._api.windows()
            owned = [window for window in windows if window.pid == pid]
            self._managed_pids.add(pid)
            current = {(window.pid, window.handle) for window in windows}
            self._hidden_bits = {key: value for key, value in self._hidden_bits.items() if key in current}
            changed = 0
            for window in owned:
                executable = os.path.normcase(window.executable)
                group = self._groups.get(executable)
                if not group:
                    reference = next((other for other in windows
                        if other.pid not in self._managed_pids and other.onscreen
                        and not other.style & WS_EX_TOOLWINDOW and other.app_id
                        and os.path.normcase(other.executable) == executable), None)
                    group = reference.app_id if reference else self._api.default_app_id(window.executable)
                    if group:
                        self._groups[executable] = group
                # Grouping failure must not prevent a background window being hidden.
                if group and group != window.app_id:
                    try:
                        self._api.set_app_id(window.handle, group)
                        changed += 1
                    except OSError:
                        pass
                key = (pid, window.handle)
                if background:
                    self._hidden_bits.setdefault(key, window.style & _TASKBAR_BITS)
                    style = (window.style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
                else:
                    original = self._hidden_bits.get(key)
                    if original is None:
                        continue
                    style = (window.style & ~_TASKBAR_BITS) | original
                if style != window.style:
                    try:
                        self._api.set_style(window.handle, style)
                        changed += 1
                    except OSError:
                        continue
                if not background:
                    self._hidden_bits.pop(key, None)
            return changed

    def forget(self, pid: int):
        with self._lock:
            self._managed_pids.discard(pid)
            self._hidden_bits = {key: value for key, value in self._hidden_bits.items() if key[0] != pid}


@lru_cache(maxsize=1)
def _windows_api():
    if sys.platform != "win32":
        return None
    try:
        return _WindowsShell()
    except (AttributeError, OSError):
        return None


class _WindowsShell:
    def __init__(self):
        from ctypes import wintypes as w

        class Guid(ctypes.Structure):
            _fields_ = [("data", ctypes.c_ubyte * 16)]

        class PropertyKey(ctypes.Structure):
            _fields_ = [("fmtid", Guid), ("pid", w.DWORD)]

        class CountedArray(ctypes.Structure):
            _fields_ = [("count", w.ULONG), ("values", ctypes.c_void_p)]

        class Value(ctypes.Union):
            _fields_ = [("string", ctypes.c_wchar_p), ("array", CountedArray), ("integer", ctypes.c_ulonglong)]

        class PropVariant(ctypes.Structure):
            _fields_ = [("vt", w.USHORT), ("reserved", w.USHORT * 3), ("value", Value)]

        self._variant = PropVariant
        self._key_type = PropertyKey
        self._iid = Guid.from_buffer_copy(UUID("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99").bytes_le)
        self._key = PropertyKey(Guid.from_buffer_copy(UUID("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3").bytes_le), 5)
        self._u = ctypes.WinDLL("user32", use_last_error=True)
        self._k = ctypes.WinDLL("kernel32", use_last_error=True)
        self._o = ctypes.WinDLL("ole32", use_last_error=True)
        self._s = ctypes.WinDLL("shell32", use_last_error=True)
        self._enum_proc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        bindings = [
            (self._u, "EnumWindows", [self._enum_proc, w.LPARAM], w.BOOL),
            (self._u, "IsWindowVisible", [w.HWND], w.BOOL),
            (self._u, "GetClassNameW", [w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
            (self._u, "GetWindowThreadProcessId", [w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
            (self._u, "GetWindowLongPtrW", [w.HWND, ctypes.c_int], ctypes.c_ssize_t),
            (self._u, "SetWindowLongPtrW", [w.HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t),
            (self._u, "MonitorFromWindow", [w.HWND, w.DWORD], w.HANDLE),
            (self._u, "ShowWindow", [w.HWND, ctypes.c_int], w.BOOL),
            (self._u, "SetWindowPos", [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT], w.BOOL),
            (self._k, "OpenProcess", [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            (self._k, "QueryFullProcessImageNameW", [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)], w.BOOL),
            (self._k, "CloseHandle", [w.HANDLE], w.BOOL),
            (self._o, "CoInitializeEx", [ctypes.c_void_p, w.DWORD], ctypes.c_long),
            (self._o, "CoUninitialize", [], None),
            (self._o, "PropVariantClear", [ctypes.POINTER(PropVariant)], ctypes.c_long),
            (self._s, "SHGetPropertyStoreForWindow", [w.HWND, ctypes.POINTER(Guid), ctypes.POINTER(ctypes.c_void_p)], ctypes.c_long),
        ]
        for library, name, arguments, result in bindings:
            function = getattr(library, name)
            function.argtypes, function.restype = arguments, result

    @staticmethod
    def _method(pointer, index, result, *arguments):
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *arguments)(table[index])

    @contextmanager
    def _store(self, handle):
        initialized = self._o.CoInitializeEx(None, 2)
        pointer = ctypes.c_void_p()
        try:
            # RPC_E_CHANGED_MODE means this worker thread already initialized COM.
            if initialized < 0 and initialized != -2147417850:
                raise OSError("COM initialization failed")
            if self._s.SHGetPropertyStoreForWindow(handle, ctypes.byref(self._iid), ctypes.byref(pointer)) < 0:
                raise OSError("Window property store unavailable")
            yield pointer
        finally:
            if pointer.value:
                self._method(pointer, 2, ctypes.c_ulong)(pointer)
            if initialized >= 0:
                self._o.CoUninitialize()

    def app_id(self, handle) -> str:
        with self._store(handle) as pointer:
            value = self._variant()
            try:
                get = self._method(pointer, 5, ctypes.c_long, ctypes.POINTER(self._key_type), ctypes.POINTER(self._variant))
                if get(pointer, ctypes.byref(self._key), ctypes.byref(value)) < 0:
                    raise OSError("Window identity unavailable")
                return value.value.string or "" if value.vt == 31 else ""
            finally:
                self._o.PropVariantClear(ctypes.byref(value))

    def set_app_id(self, handle, app_id):
        with self._store(handle) as pointer:
            value = self._variant()
            value.vt = 31  # VT_LPWSTR; this buffer remains owned by Python.
            buffer = ctypes.create_unicode_buffer(app_id)
            value.value.string = ctypes.cast(buffer, ctypes.c_wchar_p)
            set_value = self._method(pointer, 6, ctypes.c_long, ctypes.POINTER(self._key_type), ctypes.POINTER(self._variant))
            if set_value(pointer, ctypes.byref(self._key), ctypes.byref(value)) < 0:
                raise OSError("Window identity could not be updated")
            # SHGetPropertyStoreForWindow stores values immediately; no Commit.

    def set_style(self, handle, style):
        # Re-show without activation so Explorer refreshes the taskbar entry.
        self._u.ShowWindow(handle, 0)  # SW_HIDE
        try:
            ctypes.set_last_error(0)
            previous = self._u.SetWindowLongPtrW(handle, -20, style)
            if previous == 0 and ctypes.get_last_error():
                raise ctypes.WinError(ctypes.get_last_error())
            self._u.SetWindowPos(handle, None, 0, 0, 0, 0, 0x37)
        finally:
            self._u.ShowWindow(handle, 8)  # SW_SHOWNA: no activation or focus change.

    def _executable(self, pid):
        from ctypes import wintypes as w
        process = self._k.OpenProcess(0x1000, False, pid)
        if not process:
            return ""
        try:
            size = w.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            return buffer.value if self._k.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)) else ""
        finally:
            self._k.CloseHandle(process)

    def windows(self):
        from ctypes import wintypes as w
        result, executables = [], {}

        @self._enum_proc
        def visit(handle, _):
            if not self._u.IsWindowVisible(handle):
                return True
            name = ctypes.create_unicode_buffer(64)
            self._u.GetClassNameW(handle, name, len(name))
            if name.value != "Chrome_WidgetWin_1":
                return True
            pid = w.DWORD()
            self._u.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            if pid.value not in executables:
                executables[pid.value] = self._executable(pid.value)
            executable = executables[pid.value]
            if not executable or os.path.basename(executable).casefold() != "chrome.exe":
                return True
            try:
                app_id = self.app_id(handle)
            except OSError:
                app_id = ""
            result.append(WindowInfo(int(handle), pid.value, executable, app_id,
                self._u.GetWindowLongPtrW(handle, -20), bool(self._u.MonitorFromWindow(handle, 0))))
            return True

        self._u.EnumWindows(visit, 0)
        return result

    @staticmethod
    @lru_cache(maxsize=8)
    def default_app_id(executable):
        import winreg
        base = r"SOFTWARE\Clients\StartMenuInternet"
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, base) as clients:
                    index = 0
                    while True:
                        try:
                            name = winreg.EnumKey(clients, index)
                        except OSError:
                            break
                        index += 1
                        try:
                            with winreg.OpenKey(clients, name + r"\shell\open\command") as command_key:
                                command = winreg.QueryValueEx(command_key, "")[0].strip()
                            installed = command.split('"')[1] if command.startswith('"') else command.split()[0]
                            if os.path.normcase(installed) != os.path.normcase(executable):
                                continue
                            with winreg.OpenKey(clients, name + r"\Capabilities\FileAssociations") as associations:
                                program_id = winreg.QueryValueEx(associations, ".html")[0]
                            with winreg.OpenKey(root, "SOFTWARE\\Classes\\" + program_id + r"\Application") as application:
                                return str(winreg.QueryValueEx(application, "AppUserModelId")[0])
                        except (OSError, IndexError, AttributeError):
                            continue
            except OSError:
                continue
        return ""
