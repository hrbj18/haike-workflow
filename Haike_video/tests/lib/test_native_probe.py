"""Native capability probes must not crash or outlive the workbench host."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from lib import native_probe


def test_safe_import_and_required_symbols_succeed():
    assert native_probe.native_imports_available(("json",), symbols={"json": ("loads",)})
    assert not native_probe.native_imports_available(("json",), symbols={"json": ("absent_test_symbol",)})


def test_missing_import_is_unavailable_without_affecting_the_host():
    assert not native_probe.native_imports_available(("haike_nonexistent_test_native_module",))


def test_workbench_vad_preflight_uses_the_isolated_import_contract(monkeypatch):
    from backlot import workbench

    calls = []

    def unavailable(modules, *, symbols):
        calls.append((modules, symbols))
        return False

    monkeypatch.setattr(native_probe, "native_imports_available", unavailable)
    assert workbench._vad_runtime_available() is False
    assert calls == [(("onnxruntime",), {"faster_whisper.vad": ("get_speech_timestamps",)})]


def test_native_abnormal_exit_is_contained():
    script = (
        "import ctypes; ctypes.windll.kernel32.ExitProcess(3221225477)"
        if os.name == "nt" else "import os; os._exit(139)"
    )
    assert not native_probe._run_probe([sys.executable, "-c", script], timeout=3)
    assert native_probe.native_imports_available(("json",))


def _windows_alive(pid: int) -> bool:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ctypes.get_last_error() == 5
    try:
        code = wintypes.DWORD()
        return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
    finally:
        kernel.CloseHandle(handle)


@pytest.mark.skipif(os.name != "nt", reason="Windows venv redirector process-tree contract")
def test_timeout_reaps_the_owned_venv_child_and_descendant(tmp_path: Path):
    owner = tmp_path / "owner.txt"
    descendant = tmp_path / "descendant.txt"
    nested = (
        "import os,time; from pathlib import Path; "
        f"Path({str(descendant)!r}).write_text(str(os.getpid()),encoding='utf-8'); time.sleep(60)"
    )
    script = (
        "import os,subprocess,sys,time; from pathlib import Path; "
        f"Path({str(owner)!r}).write_text(str(os.getpid()),encoding='utf-8'); "
        f"subprocess.Popen([sys.executable,'-c',{nested!r}],creationflags=0x08000200); "
        "time.sleep(60)"
    )
    started = time.monotonic()
    assert not native_probe._run_probe([sys.executable, "-c", script], timeout=2)
    assert time.monotonic() - started < 12
    assert owner.exists() and descendant.exists()
    assert not _windows_alive(int(owner.read_text(encoding="utf-8")))
    assert not _windows_alive(int(descendant.read_text(encoding="utf-8")))


def test_probe_child_has_finite_hidden_process_boundary(monkeypatch):
    captured = {}

    class Child:
        def wait(self, *, timeout):
            captured["wait_timeout"] = timeout
            return 0
        def poll(self):
            return 0

    def launch(command, **kwargs):
        captured.update(kwargs)
        return Child()

    monkeypatch.setattr(native_probe.subprocess, "Popen", launch)
    assert native_probe.native_imports_available(("json",), timeout=1000)
    assert captured["wait_timeout"] == native_probe.IMPORT_TIMEOUT_SECONDS
    assert captured["stdout"] == subprocess.DEVNULL
    assert captured["stderr"] == subprocess.DEVNULL
    if os.name == "nt":
        assert captured["creationflags"] & subprocess.CREATE_NO_WINDOW
        assert captured["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert captured["start_new_session"] is True
