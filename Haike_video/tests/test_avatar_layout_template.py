"""Layout contract and failure checks; no paid jobs or project mutations."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
module_spec = importlib.util.spec_from_file_location("avatar_layout_template", ROOT / "scripts/avatar_layout_template.py")
m = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(m)


def test_approved_geometry_clears_top_buffer():
    preset, _ = m.load_preset("douyin-safe-circle-v1")
    geometry = m.pixel_geometry(preset)
    assert geometry == {"x": 691, "y": 307, "width": 236, "height": 236}
    assert geometry["y"] - preset["presenter"]["ring_width"] >= 288


def test_overlong_text_rejected():
    preset, _ = m.load_preset("douyin-safe-circle-v1")
    font = m.font_path(preset)
    with pytest.raises(ValueError, match="安全框"):
        m.text_positions(preset, {"title": "非常长的标题" * 20, "test_subtitle": "短句"}, font)


def test_source_interval_and_unconfirmed_audio_rejected(tmp_path, monkeypatch):
    preset, _ = m.load_preset("douyin-safe-circle-v1")
    font = m.font_path(preset)
    (tmp_path / "source.mp4").write_bytes(b"probe is mocked")
    monkeypatch.setattr(m, "probe", lambda *args: {"streams": [{"codec_type": "video", "duration": "3"}, {"codec_type": "audio", "duration": "3"}]})
    spec = {"title": "产品", "test_subtitle": "产品演示", "duration_seconds": 3,
            "segments": [{"kind": "video", "path": "source.mp4", "duration_seconds": 3,
                          "source_in_seconds": 1, "asset_id": "a", "source_url": "https://example.com", "rights_status": "unknown"}],
            "avatar": {"path": "source.mp4"}, "audio": {"path": "source.mp4", "already_mixed": False}}
    with pytest.raises(ValueError, match="超出媒体时长"):
        m.validate(spec, tmp_path, preset, font, "ffprobe", True)
    spec["segments"][0]["source_in_seconds"] = 0
    with pytest.raises(ValueError, match="已确认混音"):
        m.validate(spec, tmp_path, preset, font, "ffprobe", True)
