"""Resume only the original avatar artifact; no network, media tool or paid calls."""
from copy import deepcopy
import json

import pytest

from backlot.studio import Studio, atomic_private
from backlot.studio_avatar import key_identity, run_avatar
from backlot.work_catalog import sha


class OriginalGateway:
    def __init__(self, job):
        self.job = job
        self.waits = []
        self.quotes = self.confirms = 0

    def quote(self, *args):
        self.quotes += 1
        raise AssertionError("recovery must not quote another call")

    def confirm(self, *args):
        self.confirms += 1
        raise AssertionError("recovery must not confirm another intent")

    def wait(self, intent, timeout):
        self.waits.append(intent)
        return deepcopy(self.job)


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    studio = Studio(tmp_path / "projects")
    project = studio.projects_root / "avatar-recovery"
    project.mkdir(parents=True)
    audio = project / "narration.wav"
    audio.write_bytes(b"offline-existing-audio")
    draft = {"id": project.name, "template_id": "avatar-safe-circle-v1", "title": "原任务恢复",
             "text": "测试保留原任务及未知费用。", "layout": {},
             "input": {"soundMode": "audio", "subtitles": False}}
    request = {"id": "quote-original", "render_id": "same-render", "draft": draft,
               "key_identity": key_identity(studio), "max_charge_micros": 5_000_000,
               "quotes": {}, "asr": {"provider": "gateway"},
               "prepared": {"audio_path": str(audio), "audio_file": "original-audio", "image_file": "original-image", "duration": 3.0}}
    folder = project / "renders/same-render"
    folder.mkdir(parents=True)
    state_path = folder / "gateway-state.json"
    job = {"id": "gj-original", "status": "submission_unknown", "result": {"video_url": "https://supplier.example/original.mp4"},
           "billing": {"usage_status": "reconciliation_pending", "reserved_micros": 2_000_000}}
    stage = {"quote": {"id": "original-avatar-quote", "model": "haike/avatar", "max_charge_micros": 2_000_000},
             "intent": "call_" + "a" * 32, "job": {"id": "gj-original", "status": "submission_unknown", "result": {}}}
    state = {"prepared": deepcopy(request["prepared"]), "stages": {"avatar": deepcopy(stage)}}
    atomic_private(state_path, state)
    downloads, compositions = [], []

    def download(url, path):
        downloads.append(url)
        path.write_bytes(b"offline-original-avatar-video")

    def compose(out, draft, video, audio, duration, cues, **kwargs):
        compositions.append(str(video))
        target = out / "avatar-preview.mp4"
        target.write_bytes(b"offline-final-composition")
        return target

    monkeypatch.setattr("backlot.studio_avatar.download_result", download)
    monkeypatch.setattr("backlot.studio_avatar.media_probe", lambda path: {
        "duration": 3.0, "video": {"width": 448, "height": 560, "codec_type": "video"}, "audio": None})
    monkeypatch.setattr("backlot.studio_storyboard.produce", lambda *args: None)
    monkeypatch.setattr("backlot.studio_composition.compose_avatar", compose)
    return {"project": project, "folder": folder, "request": request, "state": state,
            "state_path": state_path, "stage": stage, "job": job, "downloads": downloads, "compositions": compositions}


def read_state(case):
    return json.loads(case["state_path"].read_text(encoding="utf-8"))


def test_original_unknown_avatar_artifact_recovers_twice_without_new_intent_or_settlement(recovery):
    case = recovery
    sdk = OriginalGateway(case["job"])
    first = run_avatar(case["project"], case["request"], sdk)
    assert first["status"] == "completed"
    stored = read_state(case)
    assert stored["stages"]["avatar"]["job"] == case["job"]
    assert stored["stages"]["avatar"]["intent"] == case["stage"]["intent"]
    assert stored["stages"]["avatar"]["quote"] == case["stage"]["quote"]
    receipt = stored["avatar_artifact_recovery"]
    assert receipt["job_id"] == "gj-original" and receipt["status"] == "submission_unknown"
    assert receipt["sha256"] == sha(case["folder"] / "avatar-source.mp4")
    assert receipt["duration"] == 3.0 and (receipt["width"], receipt["height"]) == (448, 560)
    assert receipt["billing_pending"] is True and receipt["billing_usage_status"] == "reconciliation_pending"
    assert first["result"]["avatar_artifact_recovery"] == receipt
    qa = json.loads((case["folder"] / "qa.json").read_text(encoding="utf-8"))
    assert qa["avatar_artifact_recovery"] == receipt
    second = run_avatar(case["project"], case["request"], sdk)
    assert second["status"] == "completed"
    assert sdk.quotes == sdk.confirms == 0
    assert sdk.waits == [case["stage"]["intent"]]
    assert case["downloads"] == [case["job"]["result"]["video_url"]]
    assert read_state(case)["stages"]["avatar"]["job"] == case["job"]
    assert "actual_micros" not in receipt


@pytest.mark.parametrize("status,result", [
    ("submission_unknown", {}), ("failed", {"video_url": "https://supplier.example/unusable.mp4"}),
    ("cancelled", {"video_url": "https://supplier.example/unusable.mp4"}),
    ("pending", {"video_url": "https://supplier.example/not-ready.mp4"}),
])
def test_only_unknown_original_job_with_video_artifact_can_be_recovered(recovery, status, result):
    case = recovery
    sdk = OriginalGateway({**case["job"], "status": status, "result": result})
    outcome = run_avatar(case["project"], case["request"], sdk)
    assert outcome["status"] == "failed" and not case["downloads"] and not case["compositions"]
    assert "avatar_artifact_recovery" not in read_state(case)
    assert sdk.quotes == sdk.confirms == 0


def test_different_job_id_cannot_replace_original_paid_job(recovery):
    case = recovery
    sdk = OriginalGateway({**case["job"], "id": "gj-another-job"})
    assert run_avatar(case["project"], case["request"], sdk)["status"] == "failed"
    assert read_state(case)["stages"]["avatar"]["job"] == case["stage"]["job"]
    assert not case["downloads"] and sdk.quotes == sdk.confirms == 0


def test_missing_original_intent_blocks_without_creating_another(recovery):
    case = recovery
    case["state"]["stages"]["avatar"].pop("intent")
    atomic_private(case["state_path"], case["state"])
    sdk = OriginalGateway(case["job"])
    assert run_avatar(case["project"], case["request"], sdk)["status"] == "failed"
    assert not sdk.waits and not case["downloads"]
    assert sdk.quotes == sdk.confirms == 0


@pytest.mark.parametrize("stage", ["tts", "asr", "asr_bailian"])
def test_other_unknown_stages_never_use_avatar_artifact_exception(recovery, stage):
    case = recovery
    case["state"]["stages"][stage] = {**deepcopy(case["stage"]), "intent": "call_" + "b" * 32}
    if stage == "tts":
        case["state"]["prepared"].pop("audio_path")
        case["request"]["draft"]["input"].update(soundMode="voice", modelId="haike/internal-tts", voiceId="test-voice")
    else:
        case["request"]["draft"]["input"]["subtitles"] = True
        if stage == "asr_bailian":
            case["request"]["asr"] = {"provider": "bailian", "model": "haike/bailian-asr"}
            case["state"]["prepared"]["bailian_audio_file"] = "original-bailian-audio"
    atomic_private(case["state_path"], case["state"])
    sdk = OriginalGateway(case["job"])
    assert run_avatar(case["project"], case["request"], sdk)["status"] == "failed"
    assert not case["downloads"] and not case["compositions"]
    assert sdk.quotes == sdk.confirms == 0 and sdk.waits == ["call_" + "b" * 32]
    assert read_state(case)["stages"][stage]["job"]["status"] == "submission_unknown"


@pytest.mark.parametrize("probe", [
    {"duration": 3, "video": None},
    {"duration": float("nan"), "video": {"width": 448, "height": 560}},
    {"duration": 0, "video": {"width": 448, "height": 560}},
    {"duration": 1, "video": {"width": 448, "height": 560}},
    {"duration": 5, "video": {"width": 448, "height": 560}},
    {"duration": 3, "video": {"width": 0, "height": 560}},
    {"duration": 3, "video": {"width": 448, "height": False}},
    {"duration": 3, "video": {"width": 448, "height": 560, "duration": "1.000"}},
])
def test_returned_avatar_media_must_pass_probe_before_composition(recovery, monkeypatch, probe):
    case = recovery
    monkeypatch.setattr("backlot.studio_avatar.media_probe", lambda path: probe)
    sdk = OriginalGateway(case["job"])
    result = run_avatar(case["project"], case["request"], sdk)
    assert result["status"] == "failed" and not case["compositions"]
    assert case["downloads"] == [case["job"]["result"]["video_url"]]
    assert "avatar_artifact_recovery" not in read_state(case)
    assert read_state(case)["stages"]["avatar"]["job"]["status"] == "submission_unknown"
    assert not (case["folder"] / "avatar-source.mp4").exists()
    assert len(list(case["folder"].glob("avatar-source.unverified-*.mp4"))) == 1
    assert sdk.quotes == sdk.confirms == 0


def test_unverified_download_is_preserved_aside_and_same_intent_can_refetch(recovery, monkeypatch):
    case = recovery
    sdk = OriginalGateway(case["job"])
    monkeypatch.setattr("backlot.studio_avatar.media_probe", lambda path: {"duration": 3, "video": None})
    assert run_avatar(case["project"], case["request"], sdk)["status"] == "failed"
    quarantined = list(case["folder"].glob("avatar-source.unverified-*.mp4"))
    assert len(quarantined) == 1 and quarantined[0].read_bytes() == b"offline-original-avatar-video"
    monkeypatch.setattr("backlot.studio_avatar.media_probe", lambda path: {
        "duration": 3, "video": {"width": 448, "height": 560, "duration": "3.000"}})
    assert run_avatar(case["project"], case["request"], sdk)["status"] == "completed"
    assert sdk.waits == [case["stage"]["intent"]] * 2 and sdk.quotes == sdk.confirms == 0
    assert len(case["downloads"]) == 2
    assert quarantined[0].is_file()


def test_verified_source_hash_change_is_not_overwritten_or_quarantined(recovery):
    case = recovery
    sdk = OriginalGateway(case["job"])
    assert run_avatar(case["project"], case["request"], sdk)["status"] == "completed"
    receipt = read_state(case)["avatar_artifact_recovery"]
    source = case["folder"] / "avatar-source.mp4"
    source.write_bytes(b"changed-offline-fixture")
    assert run_avatar(case["project"], case["request"], sdk)["status"] == "failed"
    assert source.read_bytes() == b"changed-offline-fixture"
    assert read_state(case)["avatar_artifact_recovery"] == receipt
    assert not list(case["folder"].glob("avatar-source.unverified-*.mp4"))
    assert len(case["downloads"]) == 1 and sdk.quotes == sdk.confirms == 0


@pytest.mark.parametrize("status", ["failed", "cancelled", "pending"])
def test_cached_source_does_not_override_known_failed_original_job(recovery, status):
    case = recovery
    sdk = OriginalGateway(case["job"])
    assert run_avatar(case["project"], case["request"], sdk)["status"] == "completed"
    state = read_state(case)
    state["stages"]["avatar"]["job"]["status"] = status
    atomic_private(case["state_path"], state)
    assert run_avatar(case["project"], case["request"], sdk)["status"] == "failed"
    assert (case["folder"] / "avatar-source.mp4").is_file()
    assert len(case["compositions"]) == 1 and sdk.quotes == sdk.confirms == 0
