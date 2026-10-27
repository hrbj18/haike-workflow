"""Douyin technology content intelligence supplier."""

import sys

from ._stdio import configure_utf8_stdio as _configure_utf8_stdio, is_cli_process as _is_cli_process

# Windows may otherwise emit an early CP936 runtime warning before cli.main
# switches to UTF-8, creating one mixed-encoding stderr pipe. This package is
# also imported as a library, whose host retains control of its own streams.
if sys.platform == "win32" and _is_cli_process():
    _configure_utf8_stdio()

from .native_runtime import preload_msvc_runtime as _preload_msvc_runtime

__version__ = "0.1.0"

# Import-time side effect: preload the Visual C++ 14.4x runtime *before* any
# native extension (onnxruntime / ctranslate2 / opencv) is imported by a
# submodule.  This runs on every ``import douyin_intelligence`` -- including
# ``python -m douyin_intelligence.cli`` -- and is a safe no-op on non-Windows or
# when no matching runtime is available (it only warns, never raises).  See
# ``native_runtime.py`` for the full root-cause write-up; do not remove it
# without moving the preload to another guaranteed-early entry point.
_preload_msvc_runtime()

