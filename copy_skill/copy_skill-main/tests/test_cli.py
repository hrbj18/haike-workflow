from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from douyin_intelligence._stdio import configure_utf8_stdio, is_cli_process
from douyin_intelligence.cli import _run_crawl_command, build_parser
from douyin_intelligence.config import load_config

ROOT = Path(__file__).parents[1]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "douyin_intelligence.cli", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )


def test_doctor_and_crawl_plan_are_offline_and_secret_free() -> None:
    doctor = _run("doctor")
    assert doctor.returncode == 0
    assert json.loads(doctor.stdout)["ready_for_offline_pipeline"] is True

    plan = _run("crawl-plan", "--mode", "creator")
    assert plan.returncode == 0
    payload = json.loads(plan.stdout)
    assert len(payload["commands"]) == 3
    assert all("--cookies" not in command for command in payload["commands"])
    assert all("creator" in command[command.index("--save_data_path") + 1] for command in payload["commands"])


def test_crawl_refuses_to_open_browser_without_explicit_flag() -> None:
    result = _run("crawl", "--mode", "creator")
    assert result.returncode == 2
    assert "--allow-browser" in result.stderr


def test_new_collection_commands_refuse_browser_without_explicit_flag() -> None:
    for command in ("browser-start", "browser-close", "collect-creators", "collect-materials"):
        result = _run(command)
        assert result.returncode == 2
        assert "--allow-browser" in result.stderr


@pytest.fixture
def controlled_native_bootstrap_warning(tmp_path: Path) -> Path:
    # Deterministically force the optional runtime warning *before* cli.main;
    # installing a complete MSVC runtime on a release machine must not make
    # this regression vacuous. No native DLL or browser is loaded by this hook.
    (tmp_path / "sitecustomize.py").write_text(
        "import builtins\n"
        "_original_import = builtins.__import__\n"
        "def _controlled_native(name, globals=None, locals=None, fromlist=(), level=0):\n"
        "    module = _original_import(name, globals, locals, fromlist, level)\n"
        "    if level == 1 and name == 'native_runtime' and (globals or {}).get('__package__') == 'douyin_intelligence':\n"
        "        module.runtime_dir_candidates = lambda: []\n"
        "        builtins.__import__ = _original_import\n"
        "    return module\n"
        "builtins.__import__ = _controlled_native\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.skipif(sys.platform != "win32", reason="Windows legacy code-page bootstrap")
def test_cli_bootstrap_warning_and_argument_error_are_both_utf8(controlled_native_bootstrap_warning: Path) -> None:
    bootstrap = controlled_native_bootstrap_warning
    result = subprocess.run(
        [sys.executable, "-m", "douyin_intelligence.cli", "crawl", "--mode", "creator"],
        cwd=ROOT,
        capture_output=True,
        env={
            **os.environ,
            "PYTHONPATH": str(bootstrap) + os.pathsep + os.environ.get("PYTHONPATH", ""),
            "PYTHONIOENCODING": "gbk",
            "PYTHONUTF8": "0",
        },
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    # Decode bytes here so a failure is an explicit UnicodeDecodeError rather
    # than a Windows subprocess reader thread silently yielding stderr=None.
    diagnostic = result.stderr.decode("utf-8")
    assert "MSVC runtime" in diagnostic
    assert "crawl 必须显式提供 --allow-browser" in diagnostic


def test_library_import_preserves_host_stream_encoding() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import sys; before=sys.stderr.encoding; import douyin_intelligence; print(before == sys.stderr.encoding)"],
        cwd=ROOT,
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "gbk", "PYTHONUTF8": "0"},
        timeout=30,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b"True"


@pytest.mark.parametrize(
    ("original_args", "entry_point", "expected"),
    [
        (["python", "-X", "dev", "-m", "douyin_intelligence.cli"], "-m", True),
        (["python", "-m", "other", "douyin_intelligence.cli"], "other.py", False),
        (["python", "-c", "douyin_intelligence.cli"], "-c", False),
        (["python"], "douyin-intelligence.exe", True),
        (["python"], "douyin-intelligence", True),
        (["python"], "other-douyin-intelligence.exe", False),
    ],
)
def test_only_declared_cli_entry_points_own_stdio(monkeypatch, original_args, entry_point, expected) -> None:
    monkeypatch.setattr(sys, "orig_argv", original_args)
    monkeypatch.setattr(sys, "argv", [entry_point])
    assert is_cli_process() is expected


def test_cli_stream_configuration_tolerates_captured_and_closed_streams(monkeypatch) -> None:
    class ClosedStream:
        def reconfigure(self, **_kwargs):
            raise ValueError("closed")

    monkeypatch.setattr(sys, "stdout", object())
    monkeypatch.setattr(sys, "stderr", ClosedStream())
    configure_utf8_stdio()


def test_normalize_cli_writes_standard_file(tmp_path: Path) -> None:
    output = tmp_path / "normalized.json"
    result = _run(
        "normalize",
        "--input",
        str(ROOT / "tests" / "fixtures" / "creator_contents_2026-08-25.jsonl"),
        "--output",
        str(output),
    )
    assert result.returncode == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload["items"]) == 4


def test_explicit_crawl_has_a_finite_sanitized_timeout(monkeypatch) -> None:
    config = load_config()
    observed: dict[str, object] = {}

    def expire(_command, **kwargs):
        observed.update(kwargs)
        raise subprocess.TimeoutExpired("crawler", kwargs["timeout"])

    monkeypatch.setattr("douyin_intelligence.cli.subprocess.run", expire)
    assert _run_crawl_command(config, ["crawler"]) == 124
    # The timeout is derived from the live config (was hard-coded to the old
    # ``collection_timeout_seconds: 120``); assert the configured value instead
    # of a frozen literal so the bound tracks config changes.
    expected = max(10, int(config["media_crawler"]["collection_timeout_seconds"]))
    assert observed["timeout"] == expected
    # The crawler used to run behind ``stdout/stderr=DEVNULL``, so a non-zero
    # exit produced no diagnostic at all.  Output is now captured (and a tail
    # echoed on failure); assert we do NOT silence it again.
    assert "stdout" not in observed
    assert "stderr" not in observed
    assert observed["capture_output"] is True
    assert observed["text"] is True
    assert observed["encoding"] == "utf-8"
    assert observed["errors"] == "replace"


def test_daily_material_pack_cli_surface_has_build_validate_and_quick() -> None:
    parser = build_parser()
    build = parser.parse_args(["daily-material-pack", "build", "--input", "selection.json", "--quick"])
    validate = parser.parse_args(["daily-material-pack", "validate", "--pack", "daily-material-pack.json"])
    assert build.command == "daily-material-pack" and build.action == "build" and build.quick is True
    assert validate.action == "validate" and validate.pack == "daily-material-pack.json"
