"""Isolated development-sample input contracts; no render, service or provider."""
import copy
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def sample(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    path = Path(__file__).resolve().parents[1] / "scripts/avatar_template7_sample.py"
    spec = importlib.util.spec_from_file_location("template7_sample_contract_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def case(sample, tmp_path, monkeypatch):
    import lib.ffmpeg_locator as locator
    import tools.analysis.composition_validator as validator

    for name in ("avatar.mp4", "broll.mp4", "audio.wav", "font.ttc"):
        (tmp_path / name).write_bytes(("isolated-" + name).encode())
    monkeypatch.setattr(locator, "resolve_ffmpeg_pair", lambda: ("unused-ffmpeg", "unused-ffprobe"))
    monkeypatch.setattr(sample, "probe", lambda *_: {"streams": [
        {"codec_type": "video", "duration": "19"}, {"codec_type": "audio", "duration": "19"}]})
    monkeypatch.setattr(sample, "fit_text", lambda _value, style, _field, _font, max_key="font_size", **_: style[max_key])
    monkeypatch.setattr(validator, "CompositionValidator", lambda: SimpleNamespace(
        execute=lambda _: SimpleNamespace(success=True, data={"valid": True}, error=None)))
    monkeypatch.setattr(sample, "run", lambda *_args, **_kwargs: pytest.fail("input preparation must not run a process"))
    manifest = {
        "duration_seconds": 19, "font_path": str(tmp_path / "font.ttc"),
        "title_lines": ["测试标题", "视觉结构"], "brand": "测试品牌", "tagline": ["本地开发验证"],
        "source_pill": "来源：测试夹具", "media": {"avatar": "avatar.mp4", "broll": "broll.mp4", "audio": "audio.wav"},
        "scenes": [{"id": "whole", "start": 0, "end": 19, "mode": "broll", "source_in": 0}],
        "cues": [{"start": 0, "end": 1.5, "text": "测试字幕"}],
    }
    manifest_path = tmp_path / "input.json"

    def prepare(value=None, project="isolated-project"):
        manifest_path.write_text(json.dumps(value or manifest, ensure_ascii=False), encoding="utf-8")
        return sample.prepare(manifest_path, tmp_path / project)

    return SimpleNamespace(manifest=manifest, prepare=prepare, project=tmp_path / "isolated-project")


def test_19s_prepare_is_repeatable_and_changed_input_cannot_replace_frozen_project(case):
    first, props, _, _ = case.prepare()
    second, _, _, _ = case.prepare()
    assert first["fingerprint"] == second["fingerprint"]
    assert props["cues"] == [{"startMs": 0, "endMs": 1500, "text": "测试字幕", "timestampMs": None, "confidence": None}]
    assert first["duration_seconds"] == 19 and first["cloud_calls"] == 0
    assert first["publication"] is False and first["production_integration"] is False
    state_before = (case.project / "artifacts/sample-state.json").read_bytes()
    changed = copy.deepcopy(case.manifest)
    changed["title_lines"][0] = "另一个输入"
    with pytest.raises(ValueError, match="已有不同冻结输入"):
        case.prepare(changed)
    assert (case.project / "artifacts/sample-state.json").read_bytes() == state_before


@pytest.mark.parametrize("next_start", [6.1, 5.9, 6.01], ids=["gap", "overlap", "off-frame"])
def test_scene_clock_rejects_gaps_overlaps_and_non_frame_boundaries(case, next_start):
    value = copy.deepcopy(case.manifest)
    value["scenes"] = [
        {"id": "a", "start": 0, "end": 6.01 if next_start == 6.01 else 6, "mode": "broll"},
        {"id": "b", "start": next_start, "end": 19, "mode": "broll", "source_in": 0},
    ]
    with pytest.raises(ValueError, match="无缝覆盖|帧时钟"):
        case.prepare(value)
    assert not case.project.exists()


def test_source_selection_must_fit_existing_media(case):
    value = copy.deepcopy(case.manifest)
    value["scenes"][0]["source_in"] = 1
    with pytest.raises(ValueError, match="超出素材时长"):
        case.prepare(value)
    assert not case.project.exists()


def test_remote_media_is_rejected_without_download(case):
    value = copy.deepcopy(case.manifest)
    value["media"]["avatar"] = "https://example.invalid/avatar.mp4"
    with pytest.raises(ValueError, match="不接受URL"):
        case.prepare(value)
    assert not case.project.exists()


def test_caption_too_wide_at_minimum_size_is_rejected_with_real_font(sample):
    layout = sample.read_json(sample.TEMPLATE / "layout.json")
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / layout["fonts"]["windows_file"]
    if not font.is_file():
        pytest.skip("Windows reference font is unavailable; no substitute font is assumed equivalent")
    style = layout["captions"]
    assert sample.fit_text("短句字幕", style, "字幕", font) >= style["min_font_size"]
    with pytest.raises(ValueError, match="最小字号.*超出安全框"):
        sample.fit_text("超长字幕" * 20, style, "字幕", font, width=style["width"] - 2 * style["stroke_width"])


def test_legacy_cached_video_gets_master_audio_without_rendering_frames(sample, tmp_path, monkeypatch):
    import tools.video.video_compose as native

    project = tmp_path / "sample"
    project.mkdir()
    output, master = project / "sample.mp4", tmp_path / "master.wav"
    output.write_bytes(b"native-video-with-delayed-audio")
    master.write_bytes(b"frozen-master-clock")
    original = output.read_bytes()
    state = {"project": str(project), "output": str(output), "duration_seconds": 19,
             "render_completed": True, "output_sha256": sample.digest(output),
             "fingerprint": "isolated-legacy-fixture", "caption_timing": "manual_reference_clock",
             "source_media": {"audio": {"path": str(master), "sha256": sample.digest(master)}}}
    mux_calls, probes = [], []

    def local_command(command, **_kwargs):
        if "-map" in command:
            mux_calls.append(command)
            assert output.read_bytes() == original  # Atomic replacement follows a successful temporary mux.
            assert command[command.index("-c:v") + 1] == "copy"
            assert command[command.index("-t") + 1] == "19"
            assert command[command.index("-map") + 1] == "0:v:0"
            assert str(master) in command and "1:a:0" in command
            Path(command[-1]).write_bytes(b"same-video-master-audio")
        elif "-frames:v" in command:
            Path(command[-1]).write_bytes(b"isolated-review-image")
        else:
            assert "null" in command  # Final local full-decode QA only.
        return ""

    def final_probe(*_args):
        probes.append(True)
        return {"streams": [{"codec_type": "video", "duration": "19", "width": 1080,
                             "height": 1920, "avg_frame_rate": "30/1"},
                            {"codec_type": "audio", "duration": "19"}]}

    monkeypatch.setattr(native, "VideoCompose", lambda: pytest.fail("cached migration must not render video frames"))
    monkeypatch.setattr(sample, "run", local_command)
    monkeypatch.setattr(sample, "probe", final_probe)
    args = (state, {"scenes": []}, {"bespoke": {}}, ("unused-ffmpeg", "unused-ffprobe"), 2)
    migrated = sample.render(*args)
    assert migrated["audio_clock_mux"] == "master_wav_v1" and len(mux_calls) == 1 and len(probes) == 1
    assert output.read_bytes() == b"same-video-master-audio"
    evidence = sample.read_json(project / "artifacts/sample-evidence.json")
    assert evidence["audio_clock_audio_sha256"] == sample.digest(master)
    assert evidence["audio_clock_mux"] == "master_wav_v1" and evidence["full_decode"] == "passed"
    assert sample.render(*args)["status"] == "existing_render_reused"
    assert len(mux_calls) == 1 and len(probes) == 1
