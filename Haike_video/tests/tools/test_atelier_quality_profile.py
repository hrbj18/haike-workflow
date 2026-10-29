"""The native high-fidelity profile must reach the actual Remotion CLI flags."""
from copy import deepcopy
from pathlib import Path

import pytest

from tools.video import video_compose
from tools.video.video_compose import VideoCompose


@pytest.fixture
def renderer(tmp_path, monkeypatch):
    module = tmp_path / "haike/tools/video/video_compose.py"
    composer = tmp_path / "haike/remotion-composer"
    (composer / "node_modules").mkdir(parents=True)
    entry = composer / "projects/isolated/index.tsx"
    entry.parent.mkdir(parents=True); entry.write_text("// fake entry", encoding="utf-8")
    monkeypatch.setattr(video_compose, "__file__", str(module))
    tool = VideoCompose()
    output = tmp_path / "out.mp4"
    calls = []
    def command(cmd, **kwargs):
        calls.append(cmd); output.write_bytes(b"fake-render")
    monkeypatch.setattr(tool, "run_command", command)
    monkeypatch.setattr(tool, "_run_final_review", lambda **kw: {"status": "pass"})
    monkeypatch.setattr(tool, "_run_atelier_checks", lambda *a: {"issues": []})
    return tool, output, calls, {"entry": str(entry), "composition_id": "Isolated", "crf": 16,
        "image_format": "png", "codec": "h264", "x264_preset": "slow", "pixel_format": "yuv420p", "scale": 1}


def test_png_crf16_slow_and_copy_of_issued_command_are_not_dropped(renderer):
    tool, output, calls, settings = renderer
    result = tool._render_via_atelier({"output_path": str(output)}, {"bespoke": settings})
    assert result.success and len(calls) == 1
    assert {"--image-format=png", "--crf=16", "--x264-preset=slow", "--pixel-format=yuv420p", "--codec=h264", "--scale=1"} <= set(calls[0])
    assert not any(a.startswith("--jpeg-quality") for a in calls[0])
    assert result.data["render_command"] == calls[0]


@pytest.mark.parametrize("change", [{"image_format": "gif"}, {"jpeg_quality": 80}, {"x264_preset": "invented"},
                                     {"pixel_format": "invented"}, {"codec": "copy"}])
def test_invalid_quality_options_fail_before_renderer_process(renderer, change):
    tool, output, calls, settings = renderer
    settings = {**deepcopy(settings), **change}
    result = tool._render_via_atelier({"output_path": str(output)}, {"bespoke": settings})
    assert not result.success and calls == []


def test_existing_atelier_without_profile_keeps_existing_defaults(renderer):
    tool, output, calls, settings = renderer
    settings = {key: settings[key] for key in ("entry", "composition_id", "crf")}
    assert tool._render_via_atelier({"output_path": str(output)}, {"bespoke": settings}).success
    assert not any(a.startswith(("--image-format", "--x264-preset", "--pixel-format", "--codec")) for a in calls[0])


def test_native_target_20mbps_uses_bitrate_flag_without_any_crf_override(renderer):
    tool, output, calls, settings = renderer
    settings = {**settings, "crf": None, "video_bitrate": "20M"}
    assert tool._render_via_atelier({"output_path": str(output)}, {"bespoke": settings}).success
    assert "--video-bitrate=20M" in calls[0]
    assert not any(flag.startswith("--crf") for flag in calls[0])


@pytest.mark.parametrize("bitrate", ["20M", "bad bitrate"])
def test_target_bitrate_cannot_be_combined_with_crf(renderer, bitrate):
    tool, output, calls, settings = renderer
    assert not tool._render_via_atelier({"output_path": str(output)}, {"bespoke": {**settings, "video_bitrate": bitrate}}).success
    assert calls == []


def test_explicit_h264_cbr_uses_native_single_encode_config(renderer):
    tool, output, calls, settings = renderer
    settings = {**settings, "crf": None, "video_bitrate": "22M", "h264_cbr": True}
    assert tool._render_via_atelier({"output_path": str(output)}, {"bespoke": settings}).success
    config = output.with_suffix(".cbr.config.js")
    assert f"--config={config}" in calls[0]
    content = config.read_text(encoding="utf-8")
    assert "nal-hrd=cbr:filler=1" in content and "libx264" in content
    assert "'-minrate'" in content and "'-maxrate'" in content


@pytest.mark.parametrize("change", [{"codec": "copy"}, {"video_bitrate": None}, {"crf": 16}, {"h264_cbr": "true"}])
def test_invalid_cbr_contract_does_not_launch(renderer, change):
    tool, output, calls, settings = renderer
    settings = {**settings, "crf": None, "video_bitrate": "22M", "h264_cbr": True, **change}
    assert not tool._render_via_atelier({"output_path": str(output)}, {"bespoke": settings}).success
    assert not calls
