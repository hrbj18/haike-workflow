"""FFmpeg capability resolution.

Motivation: avatar assembly keeps its filter graph in a file to stay under the
Windows command-line limit. Builds can implement the current ``-/filter_complex``
syntax or the older ``-filter_complex_script`` option.
"""

from __future__ import annotations

import subprocess

import pytest

from lib import ffmpeg_locator as locator


def _binary(tmp_path, name="ffmpeg.exe"):
    path = tmp_path / name
    path.write_bytes(b"stub")
    return str(path)


def _runner(stderr: str, returncode: int = 1):
    def run(command, **_kwargs):
        return subprocess.CompletedProcess(command, returncode, "", stderr)

    return run


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    """The probe memoises per binary; a stale entry would hide a regression."""
    monkeypatch.setattr(locator, "_OPTION_SUPPORT", {})


def test_option_name_gains_its_leading_dash():
    assert locator._normalise_option("filter_complex_script") == "-filter_complex_script"
    assert locator._normalise_option("-filter_complex_script") == "-filter_complex_script"
    assert locator._normalise_option("  -x  ") == "-x"


def test_probe_passes_the_dashed_flag_to_ffmpeg(tmp_path, monkeypatch):
    seen = {}

    def run(command, **_kwargs):
        seen["command"] = command
        return subprocess.CompletedProcess(command, 1, "", "Missing argument for option 'x'.")

    monkeypatch.setattr(locator.subprocess, "run", run)
    locator.supports_option(_binary(tmp_path), "filter_complex_script")
    assert seen["command"][-1] == "-filter_complex_script"


def test_an_unrecognised_option_is_reported_as_unsupported(tmp_path, monkeypatch):
    """FFmpeg prints the option *without* its dash.

    Matching on the dashed form made every build look capable, which is the one
    answer this probe must never get wrong.
    """
    monkeypatch.setattr(locator.subprocess, "run",
                        _runner("Unrecognized option 'filter_complex_script'.\n"
                                "Error splitting the argument list: Option not found\n"))
    assert locator.supports_option(_binary(tmp_path), "-filter_complex_script") is False


def test_a_known_option_is_reported_as_supported(tmp_path, monkeypatch):
    monkeypatch.setattr(locator.subprocess, "run",
                        _runner("Missing argument for option 'filter_complex_script'.\n"))
    assert locator.supports_option(_binary(tmp_path), "-filter_complex_script") is True


def test_the_probe_runs_once_per_binary(tmp_path, monkeypatch):
    calls = {"n": 0}

    def run(command, **_kwargs):
        calls["n"] += 1
        return subprocess.CompletedProcess(command, 1, "", "Missing argument for option 'x'.")

    monkeypatch.setattr(locator.subprocess, "run", run)
    binary = _binary(tmp_path)
    assert locator.supports_option(binary, "-filter_complex_script") is True
    assert locator.supports_option(binary, "-filter_complex_script") is True
    assert calls["n"] == 1


def test_a_missing_binary_is_unsupported_without_probing(tmp_path, monkeypatch):
    def exploding(command, **_kwargs):
        raise AssertionError("no probe should run for a missing binary")

    monkeypatch.setattr(locator.subprocess, "run", exploding)
    assert locator.supports_option(str(tmp_path / "absent.exe"), "-filter_complex_script") is False


def test_resolution_skips_a_build_without_the_option(tmp_path, monkeypatch):
    broken, working = _binary(tmp_path, "broken.exe"), _binary(tmp_path, "working.exe")
    monkeypatch.setattr(locator, "candidate_pairs", lambda: [(broken, broken), (working, working)])
    monkeypatch.setattr(locator, "supports_option", lambda binary, option: binary == working)
    assert locator.resolve_ffmpeg_with_option("-filter_complex_script") == (working, working)


def test_resolution_returns_none_when_no_build_supports_it(tmp_path, monkeypatch):
    broken = _binary(tmp_path, "broken.exe")
    monkeypatch.setattr(locator, "candidate_pairs", lambda: [(broken, broken)])
    monkeypatch.setattr(locator, "supports_option", lambda binary, option: False)
    assert locator.resolve_ffmpeg_with_option("-filter_complex_script") is None


@pytest.mark.parametrize(("supported", "expected"), [
    ({"-/filter_complex", "-filter_complex_script"}, "-/filter_complex"),
    ({"-/filter_complex"}, "-/filter_complex"),
    ({"-filter_complex_script"}, "-filter_complex_script"),
])
def test_graph_file_resolution_accepts_current_and_legacy_syntax(tmp_path, monkeypatch, supported, expected):
    binary = _binary(tmp_path)
    monkeypatch.setattr(locator, "candidate_pairs", lambda: [(binary, "ffprobe")])
    monkeypatch.setattr(locator, "supports_option", lambda _binary, option: option in supported)
    assert locator.resolve_ffmpeg_with_graph_file() == (binary, "ffprobe", expected)


def test_graph_file_resolution_preserves_runtime_order_and_skips_incapable_builds(tmp_path, monkeypatch):
    broken = _binary(tmp_path, "broken.exe")
    legacy = _binary(tmp_path, "legacy.exe")
    modern = _binary(tmp_path, "modern.exe")
    monkeypatch.setattr(locator, "candidate_pairs", lambda: [
        (broken, "broken-probe"), (legacy, "legacy-probe"), (modern, "modern-probe"),
    ])
    monkeypatch.setattr(locator, "supports_option", lambda binary, option:
                        (binary, option) in {(legacy, "-filter_complex_script"), (modern, "-/filter_complex")})
    assert locator.resolve_ffmpeg_with_graph_file() == (legacy, "legacy-probe", "-filter_complex_script")


def test_graph_file_resolution_never_falls_back_to_an_inline_graph(tmp_path, monkeypatch):
    binary = _binary(tmp_path)
    monkeypatch.setattr(locator, "candidate_pairs", lambda: [(binary, "ffprobe")])
    monkeypatch.setattr(locator, "supports_option", lambda _binary, option: option == "-filter_complex")
    assert locator.resolve_ffmpeg_with_graph_file() is None


def test_candidate_pairs_are_existing_and_deduplicated(monkeypatch):
    monkeypatch.setattr(locator, "_from_environment", lambda: ("a", "b"))
    monkeypatch.setattr(locator, "_from_video_compose", lambda: ("a", "b"))
    monkeypatch.setattr(locator, "_from_static_ffmpeg", lambda: None)
    monkeypatch.setattr(locator.Path, "is_file", lambda self: True)
    assert locator.candidate_pairs() == [("a", "b")]


def test_the_repository_binary_supports_a_graph_file_option():
    """A bundled build must read a graph file through either supported syntax."""
    pair = locator._from_static_ffmpeg()
    if not pair:
        pytest.skip("static-ffmpeg is not installed in this environment")
    assert any(locator.supports_option(pair[0], option) for option in
               ("-/filter_complex", "-filter_complex_script"))
    chosen = locator.resolve_ffmpeg_with_graph_file()
    assert chosen is not None


def test_detected_runtime_reads_a_graph_larger_than_windows_argv_from_file(tmp_path):
    if not locator.candidate_pairs():
        pytest.skip("FFmpeg is not installed in this environment")
    runtime = locator.resolve_ffmpeg_with_graph_file()
    assert runtime is not None, "Installed FFmpeg must support a file-backed complex graph"
    binary, _probe, option = runtime
    graph = tmp_path / "中文滤镜图.txt"
    graph.write_text("color=c=black:s=16x16:r=1:d=1" + " " * 40_000 + "[out]", encoding="utf-8")
    command = [binary, "-hide_banner", "-nostdin", "-v", "error", option, str(graph),
               "-map", "[out]", "-frames:v", "1", "-f", "null", "-"]
    assert sum(map(len, command)) < 4096
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30, check=False)
    assert result.returncode == 0, result.stderr
