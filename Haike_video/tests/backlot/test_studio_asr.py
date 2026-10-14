"""Real-clock contracts, without external model downloads or paid calls."""
import json
from pathlib import Path
import sys
import pytest
from backlot.studio import Studio, atomic_private
from backlot import studio_asr
from backlot.studio_avatar import captions, public_quote, run_avatar, key_identity
from backlot.work_catalog import WorkError, sha


def result():
    return {"segments": [{"start": .1, "end": 2.8, "text": "第一段第二段",
                          "words": [{"start": .1, "end": .4, "text": "第一段"},
                                    {"start": 2.2, "end": 2.8, "text": "第二段"}]}]}


def configure(s, tmp_path):
    model = tmp_path / "model"; model.mkdir()
    for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt"):
        (model / name).write_bytes(b"test-model")
    c = {"provider": "local-whisper", "verified": True, "python": sys.executable,
         "model_dir": str(model), "model_sha256": sha(model / "model.bin")}
    atomic_private(s.private / "studio-asr/config.json", c)
    return studio_asr.snapshot(s)


def test_word_clock_preserves_pause_and_rejects_fake_or_invalid_timing():
    data = studio_asr.validate_result(result(), 3)
    words = data["segments"][0]["words"]
    assert words[1]["start"] - words[0]["end"] == pytest.approx(1.8)
    assert captions(data, 3)[0]["startMs"] == 100
    bad = result(); bad["segments"][0]["words"][1]["start"] = float("nan")
    with pytest.raises(WorkError): studio_asr.validate_result(bad, 3)
    with pytest.raises(WorkError): studio_asr.validate_result({"segments": []}, 3)
    with pytest.raises(WorkError): studio_asr.validate_result(result(), 1)


def test_caption_chunks_use_word_boundaries_instead_of_character_interpolation():
    data = result(); data["segments"][0]["words"][0]["text"] = "甲" * 18
    data["segments"][0]["text"] = "甲" * 18 + "第二段"
    out = captions(studio_asr.validate_result(data, 3), 3)
    assert [(c["startMs"], c["endMs"]) for c in out] == [(100, 400), (2200, 2800)]


def test_local_result_cached_and_changed_audio_or_engine_cannot_replace_receipt(tmp_path, monkeypatch):
    s = Studio(tmp_path / "projects"); frozen = configure(s, tmp_path)
    audio = tmp_path / "audio.wav"; audio.write_bytes(b"test-audio")
    calls = []
    def worker(args, **kwargs):
        calls.append(args)
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        assert kwargs["timeout"] == 300
        atomic_private(Path(args[-1]), result())
        return type("Run", (), {"returncode": 0})()
    monkeypatch.setattr(studio_asr.subprocess, "run", worker)
    folder = tmp_path / "output"
    assert studio_asr.transcribe(s, frozen, audio, folder, 3)["clock"] == "audio-word-timestamps"
    studio_asr.transcribe(s, frozen, audio, folder, 3)
    assert len(calls) == 1
    audio.write_bytes(b"different")
    with pytest.raises(WorkError, match="不能覆盖"): studio_asr.transcribe(s, frozen, audio, folder, 3)
    atomic_private(s.private / "studio-asr/config.json", {"provider": "gateway"})
    with pytest.raises(WorkError, match="已改变"): studio_asr.transcribe(s, frozen, audio, folder, 3)


def test_local_job_does_not_submit_gateway_asr_and_old_job_keeps_gateway(tmp_path, monkeypatch):
    s = Studio(tmp_path / "projects"); frozen = configure(s, tmp_path)
    d = s.save_draft({"template_id": "graphic-news-v2", "title": "test", "text": "第一段第二段", "input": {}})
    d["input"] = {"soundMode": "audio", "subtitles": True}
    folder = s.projects_root / d["id"]; folder.mkdir(parents=True, exist_ok=True)
    audio = folder / "audio.wav"; audio.write_bytes(b"fake-audio")
    request = {"id": "test-quote", "draft": d, "key_identity": key_identity(s), "render_id": "test-render",
               "prepared": {"audio_path": str(audio), "audio_file": "audio", "image_file": "portrait", "duration": 3},
               "asr": frozen, "quotes": {"avatar": {"model": "haike/avatar", "max_charge_micros": "150"}},
               "max_charge_micros": 150}
    calls = []
    class Gateway:
        def confirm(self, q, maximum, identity):
            calls.append(q["model"]); return {"id": "intent", "model": q["model"]}
        def quote(self, model, *args): return {"model": model, "max_charge_micros": "0"}
        def wait(self, intent, timeout):
            return {"id": "job", "status": "succeeded", "result": result() if intent["model"] == "haike/tencent-asr" else {"video_url": "https://supplier.test/video"}}
    monkeypatch.setattr(studio_asr, "transcribe", lambda *a: studio_asr.validate_result(result(), 3))
    monkeypatch.setattr("backlot.studio_avatar.download_result", lambda url,p: p.write_bytes(b"fake-video"))
    monkeypatch.setattr("backlot.studio_composition.compose_avatar", lambda out,*a,**k: out/"output.mp4")
    assert run_avatar(folder, request, Gateway())["status"] == "completed"
    assert calls == ["haike/avatar"]
    assert public_quote(request)["items"][-1]["model"] == "local/whisper"
    old = {**request, "render_id": "legacy-render"}; old.pop("asr")
    assert run_avatar(folder, old, Gateway())["status"] == "completed"
    assert calls[-2:] == ["haike/tencent-asr", "haike/avatar"]
