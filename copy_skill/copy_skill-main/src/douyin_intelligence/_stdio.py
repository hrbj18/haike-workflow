"""Keep the CLI's bootstrap diagnostics and final output in one encoding."""

from __future__ import annotations

import sys
from pathlib import Path


def is_cli_process() -> bool:
    # Package __init__ runs before ``python -m ...`` executes cli.py, including
    # before main() can configure its streams. Only that exact module/declared
    # console entry point owns this policy; a library import must leave its
    # host's streams alone.
    original_args = getattr(sys, "orig_argv", ())
    if any(
        flag == "-m" and module == "douyin_intelligence.cli"
        for flag, module in zip(original_args, original_args[1:])
    ):
        return True
    return bool(sys.argv) and Path(sys.argv[0]).stem == "douyin-intelligence"


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                # Captured or closed host streams can reject reconfiguration.
                # Their availability must not make the CLI bootstrap fail.
                pass
