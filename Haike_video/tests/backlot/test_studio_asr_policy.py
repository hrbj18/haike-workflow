"""User-selected Bailian primary and narrowly authorized offline fallback."""
import json
import sys
from pathlib import Path

import pytest

from backlot import studio_asr
from backlot.studio import Studio, atomic_private
from backlot.work_catalog import WorkError, sha


def local_engine(studio, folder):
    model = folder / "model"
    model.mkdir()
    for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt"):
        (model / name).write_bytes(b"fixture")
    config = {"provider": "local-whisper", "verified": True, "python": sys.executable,
              "model_dir": str(model), "model_sha256": sha(model / "model.bin")}
    atomic_private(studio.private / "studio-asr/config.json", config)
    return config


def policy(studio, **changes):
    value = {"default_provider": "bailian", "bailian_enabled": True,
             "verified": True, "fallback_on": ["invalid_key", "insufficient_balance"]}
    value.update(changes)
    atomic_private(studio.private / "studio-asr/policy.json", value)


def test_verified_primary_does_not_turn_local_backup_into_primary(tmp_path):
    studio = Studio(tmp_path / "projects")
    config = local_engine(studio, tmp_path)
    policy(studio)
    frozen = studio_asr.snapshot(studio)
    assert frozen["provider"] == "bailian"
    assert frozen["model"] == "haike/bailian-asr"
    assert frozen["fallback"]["identity"] == studio_asr.identity(config)
    public = studio_asr.status(studio)
    assert public["provider"] == "bailian" and public["ready"] is True
    assert public["fallback_ready"] is True
    assert "python" not in json.dumps(public) and str(tmp_path) not in json.dumps(public)


def test_candidate_can_be_explicitly_tested_without_switching_default(tmp_path):
    studio = Studio(tmp_path / "projects")
    local_engine(studio, tmp_path)
    policy(studio, default_provider="gateway", verified=False)
    assert studio_asr.snapshot(studio)["provider"] == "gateway"
    assert studio_asr.snapshot(studio, provider="bailian")["provider"] == "bailian"
    policy(studio, verified=False)
    with pytest.raises(WorkError, match="验收"):
        studio_asr.snapshot(studio)


@pytest.mark.parametrize("kind", ["invalid_key", "insufficient_balance"])
def test_only_definitive_unaccepted_auth_or_credit_rejection_can_fallback(kind):
    frozen = {"provider": "bailian", "fallback_on": ["invalid_key", "insufficient_balance"],
              "fallback": {"provider": "local-whisper", "identity": "fixture"}}
    job = {"status": "failed", "failure_kind": kind, "definitive": True, "accepted": False}
    assert studio_asr.should_fallback(frozen, job)
    for changed in ({"status": "submission_unknown"}, {"accepted": True},
                    {"upstream_id": "accepted-task"}, {"definitive": False},
                    {"failure_kind": "rate_limit"}, {"failure_kind": "permission"}):
        assert not studio_asr.should_fallback(frozen, {**job, **changed})
    assert not studio_asr.should_fallback({**frozen, "fallback": None}, job)


def test_missing_local_backup_is_not_advertised_as_available(tmp_path):
    studio = Studio(tmp_path / "projects")
    policy(studio)
    assert studio_asr.status(studio)["fallback_ready"] is False
    assert studio_asr.snapshot(studio)["fallback"] is None


def test_local_worker_stays_available_under_bailian_primary(tmp_path, monkeypatch):
    studio = Studio(tmp_path / "projects")
    config = local_engine(studio, tmp_path)
    policy(studio)
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"synthetic audio")
    def worker(args, **kwargs):
        atomic_private(Path(args[-1]), {"segments": [{"start": .1, "end": .8, "text": "中文",
            "words": [{"start": .1, "end": .8, "text": "中文"}]}]})
        return type("Run", (), {"returncode": 0})()
    monkeypatch.setattr(studio_asr.subprocess, "run", worker)
    result = studio_asr.transcribe(studio, {"identity": studio_asr.identity(config)}, audio, tmp_path / "out", 1)
    assert result["provider"] == "local-whisper"


def test_bailian_word_clock_keeps_real_pause():
    from backlot.studio_avatar import clock_captions
    result = {"provider": "bailian", "segments": [{"start": .1, "end": 2.8, "text": "第一段第二段",
              "words": [{"start": .1, "end": .4, "text": "第一段"},
                        {"start": 2.2, "end": 2.8, "text": "第二段"}]}]}
    assert [item["startMs"] for item in clock_captions(result, 3)] == [100, 2200]


def test_n1_shorter_caption_groups_preserve_observed_word_boundaries_and_text():
    from backlot.studio_avatar import captions, clock_captions

    # The N1 opening needs a narrower line. Uneven speech and pauses make
    # equal-duration splitting observably incorrect.
    words = [
        {"text": "10月15日", "start": .24, "end": 1.31},
        {"text": "敏捷", "start": 1.54, "end": 1.92},
        {"text": "机器人", "start": 2.03, "end": 2.88},
        {"text": "公司", "start": 3.12, "end": 3.53},
        {"text": "公布", "start": 4.06, "end": 4.73},
        {"text": "迪吉特", "start": 5.61, "end": 6.31},
    ]
    text = "".join(word["text"] for word in words)
    result = {"provider": "bailian", "segments": [
        {"start": .24, "end": 6.31, "text": text, "words": words}]}

    cues = captions(result, 6.8, max_chars=14)
    assert [cue["text"] for cue in cues] == ["10月15日敏捷机器人公司", "公布迪吉特"]
    assert "".join(cue["text"] for cue in cues) == text
    assert all(len(cue["text"]) <= 14 for cue in cues)
    assert [cue["startMs"] for cue in cues] == pytest.approx([240, 4060])
    assert [cue["endMs"] for cue in cues] == pytest.approx([3530, 6310])
    assert cues[1]["startMs"] > cues[0]["endMs"]

    # Other templates retain the existing 18-character default; visual
    # wrapping must never change the six observed storyboard word clocks.
    default = captions(result, 6.8)
    assert [cue["text"] for cue in default] == [text]
    clock = clock_captions(result, 6.8)
    assert [cue["text"] for cue in clock] == [word["text"] for word in words]
    assert [cue["startMs"] for cue in clock] == pytest.approx([word["start"] * 1000 for word in words])
    assert [cue["endMs"] for cue in clock] == pytest.approx([word["end"] * 1000 for word in words])


@pytest.mark.parametrize("outcome", ["success", "invalid_key", "insufficient_balance", "unknown", "budget"])
def test_real_avatar_runner_bailian_fallback_and_preserved_old_spending(tmp_path, monkeypatch, outcome):
    from backlot.studio_avatar import run_avatar, key_identity
    studio = Studio(tmp_path / "projects")
    draft = studio.save_draft({"template_id": "graphic-news-v2", "title": "test", "text": "中文", "input": {}})
    draft["input"] = {"soundMode": "audio", "subtitles": True}
    project = studio.projects_root / draft["id"]
    project.mkdir(parents=True, exist_ok=True)
    audio = project / "audio.wav"
    audio.write_bytes(b"fixture")
    request = {"id": "recovery-fixture", "draft": draft, "key_identity": key_identity(studio),
               "render_id": "existing-render", "prepared": {"audio_path": str(audio), "duration": 3,
                    "audio_file": "cloud-audio", "image_file": "cloud-portrait"},
               "quotes": {}, "max_charge_micros": 100,
               "asr": {"provider": "bailian", "model": "haike/bailian-asr",
                    "fallback": {"provider": "local-whisper", "identity": "fixture"},
                    "fallback_on": ["invalid_key", "insufficient_balance"]}}
    folder = project / "renders/existing-render"
    previous = {"quote": {"model": "haike/tencent-asr", "max_charge_micros": "20"},
                "intent": "original-tencent", "job": {"id": "old-cloud-job", "status": "submission_unknown"}}
    atomic_private(folder / "gateway-state.json", {"prepared": request["prepared"], "stages": {"asr": previous}})
    calls, offline = [], []
    transcription = {"provider": "bailian", "segments": [{"start": .1, "end": 2, "text": "中文",
                        "words": [{"start": .1, "end": 2, "text": "中文"}]}]}
    class Gateway:
        def prepare_asr_audio(self, path):
            assert Path(path) == audio
            return {"id": "private-audio", "backend": "internal_asr"}
        def quote(self, model, inputs, *args):
            if model == "haike/bailian-asr":
                assert inputs == {"audio_file": "private-audio"}
            return {"model": model, "max_charge_micros": "80" if outcome == "budget" and model == "haike/avatar" else "10"}
        def confirm(self, quote, maximum, intent):
            calls.append(quote["model"])
            return quote["model"]
        def wait(self, intent, timeout):
            if intent == "haike/tencent-asr":
                raise AssertionError("Old Tencent call must be preserved without re-submitting")
            if intent == "haike/avatar":
                return {"id": "avatar-job", "status": "succeeded", "result": {"video_url": "https://fixture.test/video"}}
            if outcome in {"invalid_key", "insufficient_balance"}:
                return {"id": "rejected-asr", "status": "failed", "failure_kind": outcome,
                        "definitive": True, "accepted": False}
            if outcome == "unknown":
                return {"id": "unknown-asr", "status": "submission_unknown"}
            return {"id": "asr-job", "status": "succeeded", "result": transcription}
    def local(*args):
        offline.append(True)
        return {**transcription, "provider": "local-whisper"}
    monkeypatch.setattr(studio_asr, "transcribe", local)
    monkeypatch.setattr("backlot.studio_avatar.download_result", lambda url, path: path.write_bytes(b"fake-video"))
    monkeypatch.setattr("backlot.studio_composition.compose_avatar", lambda out, *a, **kw: out / "output.mp4")
    result = run_avatar(project, request, Gateway())
    saved = json.loads((folder / "gateway-state.json").read_text(encoding="utf-8"))
    assert saved["stages"]["asr"] == previous
    if outcome in {"unknown", "budget"}:
        assert result["status"] == "failed"
        assert calls == ["haike/bailian-asr"] and not offline
    else:
        assert result["status"] == "completed"
        assert calls == ["haike/bailian-asr", "haike/avatar"]
        assert bool(offline) is (outcome in {"invalid_key", "insufficient_balance"})
        assert saved["asr_resolution"]["provider"] == ("local-whisper" if offline else "bailian")
