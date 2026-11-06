"""Exercise real enrollment records and HTTP routes with isolated fake audio centres."""
import threading
import wave
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot.studio_audio_enrollment import AudioEnrollment
from backlot.work_catalog import WorkError
from lib import bailian_speech as records


class FakeCenter:
    def __init__(self, directory, model="haike/internal-tts"):
        self.directory = directory
        self.model = model
        self.calls = []
        self.quotes = []
        self.lose = None
        self.ready = True
        self.image_fails = False
        self.submitting = None
        self.release = None

    def voices(self):
        saved = records.read_record(self.directory / "catalog.json")
        return {"items": saved.get("items", [])}

    def media(self, identity):
        if identity == "file_audio":
            return b"fake reference", "audio/wav"
        if identity == "file_image":
            return b"fake portrait", "image/jpeg"
        raise WorkError("文件不属于当前账号", "missing")

    def quote(self, data):
        kind = "clone" if data["model"] == "haike/voice-clone" else "preview"
        self.quotes.append(data)
        return {"id": "quote_" + kind, "operation_id": "call_" + ("a" if kind == "clone" else "b") * 32,
                "max_charge_micros": "100" if kind == "clone" else "200", "model": data["model"],
                "estimate_only": self.model == "haike/internal-tts"}

    def _path(self, identity):
        return self.directory / "children" / (identity + ".json")

    def operation(self, identity):
        saved = records.read_record(self._path(identity))
        if not saved:
            raise WorkError("操作不存在", "missing")
        return saved

    def submit(self, data):
        identity = data["operation_id"]
        assert not self._path(identity).exists(), "a submitted child must only be queried"
        kind = data["quote_id"].removeprefix("quote_")
        saved = {"id": identity, "kind": kind, "status": "submission_unknown"}
        records.write_record(self._path(identity), saved)
        self.calls.append((kind, dict(data)))
        if self.submitting:
            self.submitting.set()
            assert self.release.wait(5)
        if self.lose == kind:
            raise TimeoutError("fake lost provider response")
        return self.job(identity)

    def job(self, identity):
        value = self.operation(identity)
        if not self.ready:
            return value
        voice = {"id": "private_voice", "name": "我的声音", "model": self.model}
        if value["kind"] == "clone":
            records.write_record(self.directory / "catalog.json", {"items": [voice]})
            result = {"voice": voice}
        else:
            result = {"audio_url": "/api/studio/audio-center/jobs/" + identity + "/audio"}
        value.update(status="succeeded", result=result)
        records.write_record(self._path(identity), value)
        return value

    def preferences(self, data, voice_id):
        if self.image_fails:
            raise ConnectionError("fake portrait link failure")
        records.write_record(self.directory / "portrait.json", {"voice_id": voice_id, **data})


@pytest.fixture
def rig(tmp_path):
    center = FakeCenter(tmp_path / "account-a")
    data = {"operation_id": "enroll_" + "1" * 32, "name": "我的声音", "audio_file": "file_audio",
            "image_file": "file_image", "text": "你好，这是我的声音。", "max_charge_micros": 500,
            "confirmed": True, "consent": True}
    return SimpleNamespace(center=center, enrollment=AudioEnrollment(center), data=data)


@pytest.mark.parametrize("model", ["haike/internal-tts", "haike/cosyvoice"])
def test_one_confirmation_clones_links_and_auditions_within_one_total_budget(rig, model):
    rig.center.model = model
    assert rig.enrollment.create(rig.data)["status"] == "queued"
    rig.enrollment.run(rig.data["operation_id"], max_wait=0)
    result = rig.enrollment.read(rig.data["operation_id"])
    assert result["status"] == "succeeded"
    assert result["reserved_micros"] == 300
    assert result["result"]["image_linked"] is True
    assert result["result"]["audio_url"].endswith("/audio")
    assert [kind for kind, _ in rig.center.calls] == ["clone", "preview"]
    assert [int(body["max_charge_micros"]) for _, body in rig.center.calls] == [100, 200]
    assert rig.center.quotes[1]["model"] == model
    assert rig.center.quotes[1]["input"]["voice_id"] == "private_voice"
    assert records.read_record(rig.center.directory / "portrait.json")["image_file_id"] == "file_image"


def test_restart_repeat_submission_and_get_only_reuse_original_paid_operations(rig):
    rig.enrollment.create(rig.data)
    rig.enrollment.run(rig.data["operation_id"], max_wait=0)
    calls = list(rig.center.calls)
    restarted = AudioEnrollment(rig.center)
    assert restarted.create(rig.data)["status"] == "succeeded"
    restarted.run(rig.data["operation_id"], max_wait=0)
    assert restarted.read(rig.data["operation_id"])["status"] == "succeeded"
    assert rig.center.calls == calls


@pytest.mark.parametrize("stage", ["clone", "preview"])
def test_lost_response_recovers_original_child_without_recreating_paid_work(rig, stage):
    rig.center.lose = stage
    rig.enrollment.create(rig.data)
    rig.enrollment.run(rig.data["operation_id"], max_wait=0)
    assert rig.enrollment.read(rig.data["operation_id"])["status"] == "paused"
    if stage == "clone":
        assert [kind for kind, _ in rig.center.calls] == ["clone"]
    rig.center.lose = None
    restarted = AudioEnrollment(rig.center)
    restarted.run(rig.data["operation_id"], max_wait=0)
    assert restarted.read(rig.data["operation_id"])["status"] == "succeeded"
    assert [kind for kind, _ in rig.center.calls] == ["clone", "preview"]


def test_unknown_clone_never_starts_preview_and_read_does_not_submit(rig):
    rig.center.ready = False
    rig.enrollment.create(rig.data)
    rig.enrollment.run(rig.data["operation_id"], max_wait=0)
    before = list(rig.center.calls)
    assert rig.enrollment.read(rig.data["operation_id"])["status"] == "paused"
    assert rig.center.calls == before and len(before) == 1
    rig.center.ready = True
    rig.enrollment.run(rig.data["operation_id"], max_wait=0)
    assert rig.enrollment.read(rig.data["operation_id"])["status"] == "succeeded"
    assert [kind for kind, _ in rig.center.calls] == ["clone", "preview"]


@pytest.mark.parametrize("maximum,expected,calls", [(99, "failed", []), (150, "partial", ["clone"])])
def test_total_budget_is_checked_before_each_paid_stage_and_preserves_cloned_voice(rig, maximum, expected, calls):
    rig.data["max_charge_micros"] = maximum
    rig.enrollment.create(rig.data)
    rig.enrollment.run(rig.data["operation_id"], max_wait=0)
    result = rig.enrollment.read(rig.data["operation_id"])
    assert result["status"] == expected and "总预算不足" in result["error"]
    assert [kind for kind, _ in rig.center.calls] == calls
    assert bool((result["result"] or {}).get("voice")) == bool(calls)


def test_optional_portrait_failure_preserves_audition_and_recovery_only_repairs_image(rig):
    rig.center.image_fails = True
    rig.enrollment.create(rig.data)
    rig.enrollment.run(rig.data["operation_id"], max_wait=0)
    result = rig.enrollment.read(rig.data["operation_id"])
    assert result["status"] == "partial" and result["result"]["audio_url"]
    assert "图片" in result["warning"]
    rig.center.image_fails = False
    rig.enrollment.run(rig.data["operation_id"], max_wait=0)
    assert rig.enrollment.read(rig.data["operation_id"])["status"] == "succeeded"
    assert len(rig.center.calls) == 2


def test_portrait_is_optional_and_an_unowned_file_stops_before_payment(rig):
    with pytest.raises(WorkError, match="当前账号"):
        rig.enrollment.create({**rig.data, "image_file": "file_foreign"})
    assert not rig.center.calls
    rig.data["image_file"] = None
    rig.enrollment.create(rig.data)
    rig.enrollment.run(rig.data["operation_id"], max_wait=0)
    result = rig.enrollment.read(rig.data["operation_id"])
    assert result["status"] == "succeeded" and not result["result"].get("image_linked")
    assert not (rig.center.directory / "portrait.json").exists()


def test_account_isolation_confirmation_and_frozen_inputs(rig, tmp_path):
    for invalid in ({"confirmed": False}, {"consent": False}, {"max_charge_micros": True}, {"operation_id": "../other"}):
        with pytest.raises(WorkError):
            rig.enrollment.create({**rig.data, **invalid})
    rig.enrollment.create(rig.data)
    with pytest.raises(WorkError, match="原任务"):
        rig.enrollment.create({**rig.data, "max_charge_micros": 1000})
    with pytest.raises(WorkError, match="当前账号"):
        AudioEnrollment(FakeCenter(tmp_path / "account-b")).read(rig.data["operation_id"])
    assert not rig.center.calls


def test_concurrent_workers_share_the_same_exclusive_parent_intent(rig):
    rig.center.submitting, rig.center.release = threading.Event(), threading.Event()
    rig.enrollment.create(rig.data)
    worker = threading.Thread(target=rig.enrollment.run, args=(rig.data["operation_id"],), kwargs={"max_wait": 0})
    worker.start()
    try:
        assert rig.center.submitting.wait(3)
        assert rig.enrollment.create(rig.data)["status"] == "processing"
        AudioEnrollment(rig.center).run(rig.data["operation_id"], max_wait=0)
        assert len(rig.center.calls) == 1
    finally:
        rig.center.release.set()
        worker.join(5)
    assert rig.enrollment.read(rig.data["operation_id"])["status"] == "succeeded"
    assert len(rig.center.calls) == 2


@pytest.mark.parametrize("submitted", [False, True])
def test_crash_between_parent_checkpoint_and_child_intent_safely_completes_once(rig, submitted):
    rig.enrollment.create(rig.data)
    path = rig.enrollment._path(rig.data["operation_id"])
    value = records.read_record(path)
    quote = rig.center.quote({"model": "haike/voice-clone", "input": {}})
    quote["expires_at"] = "2000-01-01T00:00:00+00:00" if submitted else "2099-01-01T00:00:00+00:00"
    value["children"]["clone"] = {"quote": quote, "submitted": submitted}
    records.write_record(path, value)
    rig.enrollment.run(rig.data["operation_id"], max_wait=0)
    assert rig.enrollment.read(rig.data["operation_id"])["status"] == "succeeded"
    assert [kind for kind, _ in rig.center.calls] == ["clone", "preview"]


def test_http_single_confirmation_returns_an_enrollment_and_cross_origin_cannot_create(rig, monkeypatch):
    from backlot import studio_audio_api
    monkeypatch.setattr(studio_audio_api, "center", lambda request: rig.center)
    app = FastAPI()
    app.include_router(studio_audio_api.router)
    with TestClient(app) as client:
        rejected = client.post("/api/studio/audio-center/enrollments", json=rig.data, headers={"Origin": "https://foreign.test"})
        assert rejected.status_code == 403 and not rig.center.calls
        response = client.post("/api/studio/audio-center/enrollments", json=rig.data)
        assert response.status_code == 200 and response.json()["id"] == rig.data["operation_id"]
        path = "/api/studio/audio-center/enrollments/" + rig.data["operation_id"]
        assert client.get(path).json()["status"] == "succeeded"
        assert client.post(path + "/resume", json={}).status_code == 200
        assert len(rig.center.calls) == 2


def test_enrollment_integrates_with_real_internal_quotes_files_and_operations(tmp_path):
    from backlot.studio_audio_internal import InternalAudioCenter, PRIVATE_TARGET
    private = tmp_path / "private"
    private.mkdir()
    (private / "service-mode.json").write_text('{"mode":"internal"}')
    profiles, calls = [], []

    def wav(source, target):
        with wave.open(str(target), "wb") as audio:
            audio.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\x00\x00" * 240)

    def execute(request, folder, checkpoint, state, *, initial):
        calls.append((request["kind"], initial))
        assert (folder / "operation.json").is_file()
        if request["kind"] == "clone":
            profiles.append({"id": "my_voice", "name": "我的声音", "provider_id": "bailian",
                             "provider_voice_id": PRIVATE_TARGET + "-fixture", "model_id": PRIVATE_TARGET,
                             "available": True, "is_custom_cloud_voice": True, "speech_rate": 1.})
            return {"status": "succeeded", "result": {"voice": {"id": "my_voice", "name": "我的声音"}}}
        wav(None, folder / "preview.wav")
        return {"status": "succeeded", "result": {}}

    backend = SimpleNamespace(catalog=lambda: profiles, default=lambda: None,
                              identity=lambda provider: "fixture-account", normalize_audio=wav,
                              freeze=lambda profile, rate: {**profile, "speech_rate": rate}, execute=execute)
    center = InternalAudioCenter(SimpleNamespace(private=private), backend=backend,
                                 pricing={"clone:bailian:" + PRIVATE_TARGET: {"fixed_micros": 100}})
    audio = center.upload(b"fixture decoded only by fake backend", "audio", "sample.wav")
    enrollment = AudioEnrollment(center)
    data = {"operation_id": "enroll_" + "f" * 32, "name": "我的声音", "audio_file": audio["id"],
            "image_file": None, "text": "测试声音", "max_charge_micros": 10000, "confirmed": True, "consent": True}
    enrollment.create(data)
    enrollment.run(data["operation_id"], max_wait=0)
    result = enrollment.read(data["operation_id"])
    assert result["status"] == "succeeded"
    operation = result["result"]["audio_url"].split("/")[-2]
    assert center.preview(operation).is_file()
    assert calls == [("clone", True), ("tts", True)]
    enrollment.run(data["operation_id"], max_wait=0)
    assert calls == [("clone", True), ("tts", True)]
