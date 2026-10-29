"""Bound native dependency discovery so a broken DLL cannot crash the host."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from typing import Mapping, Sequence


IMPORT_TIMEOUT_SECONDS = 10.0
_NAME = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
_IMPORT_SCRIPT = """
import importlib, json, os, sys
if os.name == 'nt':
    import ctypes
    ctypes.windll.kernel32.SetErrorMode(0x8003)
modules, symbols = json.loads(sys.argv[1])
for name in modules:
    importlib.import_module(name)
for name, attributes in symbols.items():
    module = importlib.import_module(name)
    for attribute in attributes:
        getattr(module, attribute)
"""


def _stop_owned_probe(process: subprocess.Popen) -> None:
    """Reap only our child, including a Windows venv redirector's descendants."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/taskkill.exe"
        try:
            subprocess.run(
                [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=4, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        # The probe starts its own session, so this group contains only the
        # process we created and any children it created itself.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def _run_probe(command: Sequence[str], *, timeout: float) -> bool:
    options = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    try:
        process = subprocess.Popen(
            list(command), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_DOTENV_DISABLED": "1"},
            **options,
        )
    except OSError:
        return False
    try:
        return process.wait(timeout=max(0.01, min(float(timeout), IMPORT_TIMEOUT_SECONDS))) == 0
    except subprocess.TimeoutExpired:
        return False
    finally:
        _stop_owned_probe(process)


def native_imports_available(
    modules: Sequence[str], *, symbols: Mapping[str, Sequence[str]] | None = None,
    timeout: float = IMPORT_TIMEOUT_SECONDS,
) -> bool:
    """Probe a fixed import/symbol contract in a disposable interpreter.

    Native crashes, missing dependencies and timeout all mean unavailable.
    No result is cached here: callers own their explicit snapshot/refresh policy.
    Child output is discarded, so diagnostics cannot expose environment secrets.
    """
    module_names = list(modules)
    required = {name: list(attributes) for name, attributes in (symbols or {}).items()}
    names = [*module_names, *required, *(attribute for values in required.values() for attribute in values)]
    if not names or any(not isinstance(name, str) or not _NAME.fullmatch(name) for name in names):
        return False
    return _run_probe(
        [sys.executable, "-c", _IMPORT_SCRIPT, json.dumps([module_names, required])],
        timeout=timeout,
    )
