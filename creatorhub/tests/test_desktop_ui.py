"""Render inert native widgets in isolated processes, without starting services.

The full API suite can leave native/thread state in its long-lived host. Two Tk
resource-read failures were observed only there; their cause is not established.
Keep the real widget assertions intact and run each case in a fresh interpreter,
with no retry or skip that could hide an actual installation or rendering error.
"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import tkinter as tk
import unittest

import pytest

if __name__ == "__main__":
    # Direct child execution starts with tests/ on sys.path, rather than the
    # project root that pytest supplies to its host process.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.ui import LauncherView, COLORS


class NativeDesktopViewCases(unittest.TestCase):
    __test__ = False  # pytest collects the process boundaries below instead.

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.owner = SimpleNamespace(root=self.root, **{name: lambda: None for name in (
            "start", "open_panel", "open_guide", "open_data", "diagnostics", "hide", "close")})
        self.view = LauncherView(self.owner, "0.1.0")
        self.root.update_idletasks()

    def tearDown(self):
        self.root.destroy()
        # Tcl objects must be collected on their creator thread, before threaded tests.
        self.view = self.owner = self.root = None
        import gc
        gc.collect()

    def test_web_theme_and_primary_action(self):
        self.assertEqual(self.root.cget("background"), COLORS["bg"])
        self.assertEqual(self.owner.open_button.cget("style"), "Primary.TButton")
        self.assertEqual(str(self.owner.open_button.cget("state")), "disabled")

    def test_ready_hides_progress_and_keeps_address(self):
        self.view.phase("starting")
        self.assertEqual(self.view.progress_row.winfo_manager(), "grid")
        self.view.phase("ready", "http://127.0.0.1:8123")
        self.assertEqual(self.view.progress_row.winfo_manager(), "")
        self.assertEqual(self.view.address.get(), "http://127.0.0.1:8123")
        self.assertEqual(self.view.badge.cget("style"), "Ready.TLabel")

    def test_failure_and_shutdown_are_distinct(self):
        self.view.phase("error")
        self.assertEqual(self.view.badge.cget("style"), "Error.TLabel")
        self.assertEqual(self.view.progress_row.winfo_manager(), "")
        self.view.phase("stopping")
        self.assertEqual(self.view.progress_row.winfo_manager(), "grid")

    def test_requested_layout_fits_default_size(self):
        page = self.root.winfo_children()[0]
        self.assertLessEqual(page.winfo_reqwidth(), 840)
        self.assertLessEqual(page.winfo_reqheight(), 670)


def _stop_owned_native_process(process):
    """Bound shutdown to this test's child tree, including Windows redirectors."""
    details = []
    if process.poll() is None:
        if os.name == "nt":
            try:
                stopped = subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=4, check=False,
                )
                if stopped.returncode:
                    details.append(f"taskkill exit {stopped.returncode}: {stopped.stderr or stopped.stdout}")
            except (OSError, subprocess.TimeoutExpired) as exc:
                details.append(f"taskkill: {exc}")
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError as exc:
                details.append(f"owned process group: {exc}")
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        # A failed tree shutdown must not make pytest hang while reaping its
        # directly owned child. This only targets the Popen process handle.
        try:
            process.kill()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired) as exc:
            details.append(f"owned child reap: {exc}")
    return "\n".join(details)


@pytest.mark.parametrize("case_name", [
    "test_web_theme_and_primary_action",
    "test_ready_hides_progress_and_keeps_address",
    "test_failure_and_shutdown_are_distinct",
    "test_requested_layout_fits_default_size",
])
def test_native_ui_case_in_isolated_process(case_name):
    command = [sys.executable, str(Path(__file__).resolve()),
               "NativeDesktopViewCases." + case_name, "-v"]
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
    # Files capture complete diagnostics without waiting for pipe EOF from an
    # orphaned descendant after a Windows venv redirector exits. Unlike a pipe
    # reader's locked close(), these handles also have a bounded cleanup path.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            command, cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=stdout, stderr=stderr, creationflags=flags,
            start_new_session=os.name != "nt",
        )
        timed_out = False
        cleanup = ""
        try:
            process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            timed_out = True
            cleanup = _stop_owned_native_process(process)
        except BaseException:
            _stop_owned_native_process(process)
            raise
        stdout.seek(0)
        stderr.seek(0)
        diagnostic = (f"stdout:\n{stdout.read().decode('utf-8', errors='replace')}\n"
                      f"stderr:\n{stderr.read().decode('utf-8', errors='replace')}")
        if timed_out:
            pytest.fail(f"Native Tk case {case_name} exceeded 30s\n{diagnostic}\n{cleanup}", pytrace=False)
        assert process.returncode == 0, (
            f"Native Tk case {case_name} exited {process.returncode}\n{diagnostic}"
        )


if __name__ == "__main__":
    unittest.main()
