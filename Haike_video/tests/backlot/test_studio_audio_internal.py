"""Real local intent/files with fake providers; never read credentials or call a cloud."""
import io
import json
import threading
import wave
from types import SimpleNamespace

import pytest

from backlot.studio_audio_internal import (
    InternalAudioCenter, LegacyAudioBackend, PRIVATE_TARGET, PUBLIC, PUBLIC_TARGET, TTS_MODEL,
)
from backlot.work_catalog import WorkError
from lib import bailian_speech as records


def wav(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\x00\x00" * 240)


class FakeBackend:
    def __init__(self):
        self.key = "fake-account-a"
        self.calls, self.initials = [], 0
        self.ready = False
        self.profiles = [{"id": "pub_" + upstream, "name": name, "gender": gender,
                          "provider_id": "bailian", "model_id": PUBLIC_TARGET, "provider_voice_id": upstream,
                          "speech_rate": 1., "verification": "candidate_unverified", "available": True}
                         for upstream, name, gender in PUBLIC]

    def identity(self, provider):
        return records.fingerprint(self.key)

    def catalog(self):
        return [dict(item) for item in self.profiles]

    def default(self):
        return None

    def freeze(self, profile, rate):
        return {**profile, "speech_rate": rate}

    def normalize_audio(self, source, target):
        wav(target)

    def delete(self, identity):
        self.profiles = [p for p in self.profiles if p["id"] != identity]

    def execute(self, request, folder, checkpoint, state, *, initial):
        persisted = json.loads((folder / "operation.json").read_text(encoding="utf-8"))
        assert persisted["id"].startswith("call_") and persisted["maximum"] >= 0
        self.calls.append(initial)
        if initial:
            self.initials += 1
            assert persisted["status"] == "submitting"
            checkpoint({"upstream_id": "saved-provider-task"})
        if not self.ready:
            return None
        if request["kind"] == "tts":
            wav(folder / "preview.wav")
            return {"status": "succeeded", "result": {}}
        return {"status": "succeeded", "result": {"voice": {"id": "clone_one", "name": request["name"]}}}


@pytest.fixture
def local(tmp_path, monkeypatch):
    # All tests use an explicit fake backend; no .env reader or real provider constructor runs.
    backend = FakeBackend()
    private = tmp_path / "private"
    private.mkdir()
    (private / "service-mode.json").write_text('{"mode":"internal"}')
    center = InternalAudioCenter(SimpleNamespace(private=private), backend=backend)
    return center, backend


def body(quote):
    return {"quote_id": quote["id"], "operation_id": quote["operation_id"],
            "max_charge_micros": quote["max_charge_micros"], "confirmed": True}


def quoted(center, **inputs):
    return center.quote({"model": TTS_MODEL, "input": {"voice_id": "pub_longanyang", "text": "你好a。", **inputs}})


def test_quote_explicit_direct_estimate_han_double_count_and_real_public_model(local):
    center, backend = local
    quote = quoted(center)
    assert quote["provider"] == "bailian" and quote["provider_model"] == PUBLIC_TARGET
    assert quote["estimated_characters"] == 6 and quote["max_charge_micros"] == "600"
    assert quote["mode"] == "internal_local" and quote["relay_authenticated"] is False
    assert quote["estimate_only"] and not quote["provider_budget_enforced"]
    assert backend.key not in json.dumps(quote)
    catalog = center.voices()
    assert len(catalog["items"]) == 6
    assert sum(v["gender"] == "male" for v in catalog["items"]) == 3
    assert all(v["verification"] == "candidate_unverified" and v["model_id"] == PUBLIC_TARGET for v in catalog["items"])


def test_lost_response_repeat_quote_restart_and_get_preserve_one_paid_intent(local):
    center, backend = local
    quote = quoted(center)
    assert center.submit(body(quote))["status"] == "submission_unknown"
    assert quoted(center)["operation_id"] == quote["operation_id"]
    restarted = InternalAudioCenter(center.studio, backend=backend)
    assert restarted.job(quote["operation_id"])["status"] == "submission_unknown"
    assert restarted.submit(body(quoted(restarted)))["status"] == "submission_unknown"
    assert backend.initials == 1
    backend.ready = True
    result = restarted.job(quote["operation_id"])
    assert result["status"] == "succeeded" and result["charged_micros"] is None
    assert result["result"]["audio_url"].endswith("/audio")
    assert restarted.preview(quote["operation_id"]).is_file()
    assert backend.initials == 1
    assert restarted.submit(body(quote))["status"] == "succeeded"
    assert backend.initials == 1


def test_account_change_budget_tampering_and_unconfirmed_are_blocked(local):
    center, backend = local
    quote = quoted(center)
    for invalid in ({**body(quote), "confirmed": False}, {**body(quote), "max_charge_micros": "599"},
                    {**body(quote), "operation_id": "call_" + "0" * 32}):
        with pytest.raises(WorkError):
            center.submit(invalid)
    assert backend.initials == 0
    center.submit(body(quote))
    with pytest.raises(WorkError, match="上限"):
        center.submit({**body(quote), "max_charge_micros": "601"})
    backend.key = "fake-account-b"
    with pytest.raises(WorkError, match="配置已变化"):
        center.job(quote["operation_id"])
    assert backend.initials == 1


def test_local_preferences_image_and_upload_do_not_touch_relay_account(local, tmp_path):
    from PIL import Image
    center, backend = local
    image = io.BytesIO()
    Image.new("RGB", (256, 256), "blue").save(image, "PNG")
    upload = center.upload(image.getvalue(), "image", "portrait.png")
    center.preferences({"voice_id": "pub_longanyang"})
    center.preferences({"speech_rate": 1.2, "image_file_id": upload["id"]}, "pub_longanyang")
    restarted = InternalAudioCenter(center.studio, backend=backend)
    catalog = restarted.voices()
    assert catalog["preferences"]["voice_id"] == "pub_longanyang"
    assert catalog["items"][0]["preferences"] == {"speech_rate": 1.2, "image_file_id": upload["id"]}
    assert restarted.media(upload["id"])[1] == "image/jpeg"
    with pytest.raises(WorkError):
        restarted.media("../../secret")
    other = tmp_path / "other"
    other.mkdir()
    (other / "service-mode.json").write_text('{"mode":"internal"}')
    isolated = InternalAudioCenter(SimpleNamespace(private=other), backend=backend)
    with pytest.raises(WorkError, match="不存在"):
        isolated.media(upload["id"])
    assert isolated.voices()["preferences"]["voice_id"] is None


def test_clone_requires_confirmed_price_and_id_is_durable_before_provider(local):
    center, backend = local
    upload = center.upload(b"fake audio decoded by fake backend", "audio", "sample.wav")
    request = {"model": "haike/voice-clone", "input": {"name": "我的声音", "audio_file": upload["id"], "consent": True}}
    with pytest.raises(WorkError, match="费用估算"):
        center.quote(request)
    center.pricing["clone:bailian:" + PRIVATE_TARGET] = {"fixed_micros": 0}
    with pytest.raises(WorkError, match="确认免费"):
        center.quote(request)
    center.pricing["clone:bailian:" + PRIVATE_TARGET] = {"fixed_micros": 100}
    quote = center.quote(request)
    assert center.submit(body(quote))["status"] == "submission_unknown"
    backend.ready = True
    assert center.job(quote["operation_id"])["result"]["voice"]["name"] == "我的声音"
    assert backend.initials == 1


def test_frozen_rate_is_unchanged_by_later_preference_mutation(local):
    center, backend = local
    quote = quoted(center, speech_rate=1.1)
    center.preferences({"speech_rate": 1.4}, "pub_longanyang")
    center.submit(body(quote))
    assert center.operation(quote["operation_id"])["request"]["profile"]["speech_rate"] == 1.1
    assert center.runtime_profile("pub_longanyang")["speech_rate"] == 1.4


def test_production_text_limit_and_public_voice_cannot_be_deleted(local):
    center, _ = local
    with pytest.raises(WorkError):
        quoted(center, text="a" * 181)
    quote = quoted(center, text="a" * 20000, purpose="production")
    assert int(quote["max_charge_micros"]) == 2000000
    with pytest.raises(WorkError):
        quoted(center, text="a" * 20001, purpose="production")
    with pytest.raises(WorkError, match="不能删除"):
        center.delete("pub_longanyang")


def test_failed_download_recovers_same_bailian_http_result_without_synthesizing_twice(tmp_path, monkeypatch):
    from backlot import tts_runtime
    from platform_app import adapters
    from tools.base_tool import ToolStatus
    from tools.audio.voicebox_tts import VoiceboxTTS

    monkeypatch.setattr(VoiceboxTTS, "get_status", lambda *_: ToolStatus.UNAVAILABLE)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-only")
    backend = LegacyAudioBackend(tmp_path / "isolated")
    backend.center.provider_status = lambda _: ToolStatus.UNAVAILABLE
    profile = {"id": "pub_longanyang", "name": "龙安洋", "provider_id": "bailian",
               "model_id": PUBLIC_TARGET, "provider_voice_id": "longanyang", "speech_rate": 1.2}
    request = {"kind": "tts", "profile": profile, "text": "测试。"}
    state, calls = {}, []
    def execute(adapter, model, inputs, checkpoint, upstream_id=None):
        config = adapter.vault.load()["bailian"]
        assert config["tts_model"] == PUBLIC_TARGET and config["voice"] == "longanyang" and config["speech_rate"] == 1.2
        calls.append(inputs["text"])
        return {"result": {"audio_url": "https://fixture.oss-cn-beijing.aliyuncs.com/audio.wav"}, "usage": {"characters": 5}}
    monkeypatch.setattr(adapters.Adapter, "execute", execute)
    def checkpoint(update):
        state.update(json.loads(json.dumps(update)))
    monkeypatch.setattr(records, "download", lambda *_: (_ for _ in ()).throw(OSError("fake lost download")))
    with pytest.raises(OSError):
        backend.execute(request, tmp_path, checkpoint, state, initial=True)
    monkeypatch.setattr(records, "download", lambda url, target: wav(target))
    monkeypatch.setattr(tts_runtime, "_convert_to_wav", lambda source, target: target.write_bytes(source.read_bytes()) and None)
    assert backend.execute(request, tmp_path, checkpoint, state, initial=False)["status"] == "succeeded"
    assert calls == ["测试。"]


def test_unknown_bailian_segment_is_not_resubmitted_or_followed_by_new_segments(tmp_path, monkeypatch):
    from platform_app import adapters
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-only")
    backend = LegacyAudioBackend(tmp_path / "isolated")
    calls, state = [], {}
    def unknown(*args, **kwargs):
        calls.append(1)
        raise adapters.Uncertain()
    monkeypatch.setattr(adapters.Adapter, "execute", unknown)
    request = {"kind": "tts", "text": "a" * 900,
               "profile": {"provider_id": "bailian", "provider_voice_id": "longanyang",
                           "model_id": PUBLIC_TARGET, "speech_rate": 1.0}}
    def checkpoint(update):
        state.update(json.loads(json.dumps(update)))
    with pytest.raises(adapters.Uncertain):
        backend.execute(request, tmp_path, checkpoint, state, initial=True)
    assert backend.execute(request, tmp_path, checkpoint, state, initial=False) is None
    assert len(calls) == 1 and set(state["bailian_chunks"]) == {"0"}


def test_concurrent_same_operation_cannot_submit_twice(local):
    center, backend = local
    quote = quoted(center)
    started, release, errors = threading.Event(), threading.Event(), []
    execute = backend.execute
    def blocked(*args, **kwargs):
        started.set()
        assert release.wait(3)
        return execute(*args, **kwargs)
    backend.execute = blocked
    def first():
        try:
            center.submit(body(quote))
        except Exception as error:
            errors.append(error)
    worker = threading.Thread(target=first)
    worker.start()
    assert started.wait(3)
    try:
        with pytest.raises(records.BailianSpeechError, match="正在执行"):
            center.submit(body(quote))
    finally:
        release.set()
        worker.join(3)
    assert not errors and not worker.is_alive() and backend.initials == 1


@pytest.mark.parametrize("first_query", ["timeout", "DEPLOYING"])
def test_real_legacy_clone_saves_provider_identity_and_recovers_by_query_only(tmp_path, monkeypatch, first_query):
    import requests
    from tools.base_tool import ToolStatus
    from tools.audio.voicebox_tts import VoiceboxTTS
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-only")
    monkeypatch.setenv("DASHSCOPE_WORKSPACE_ID", "")
    for name in ("BAILIAN_OSS_ENDPOINT", "BAILIAN_OSS_BUCKET", "BAILIAN_OSS_ACCESS_KEY_ID", "BAILIAN_OSS_ACCESS_KEY_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(VoiceboxTTS, "get_status", lambda *_: ToolStatus.UNAVAILABLE)
    backend = LegacyAudioBackend(tmp_path / "isolated")
    backend.center.provider_status = lambda provider: ToolStatus.AVAILABLE if provider == "bailian" else ToolStatus.UNAVAILABLE
    calls, state = [], {}
    source = tmp_path / "upload.wav"
    wav(source)
    def normalize(source, target):
        wav(target)
        return {"reference_duration_seconds": 6, "reference_trimmed": False}
    backend.clone._normalize = normalize
    backend.clone.upload_audio = lambda *args, **kwargs: {"file_url": "oss://fake/reference.wav"}
    cloud_voice = PRIVATE_TARGET + "-haike-fake-test"
    def post(url, **kwargs):
        action = kwargs["json"]["input"]["action"]
        assert state.get("legacy_job_id"), "local operation checkpoint must precede create_voice"
        assert kwargs["allow_redirects"] is False
        calls.append(action)
        if action == "query_voice" and len(calls) == 2:
            if first_query == "timeout":
                raise requests.Timeout("fake lost first query")
            return SimpleNamespace(status_code=200, ok=True, json=lambda: {"output": {"status": first_query}})
        output = {"voice_id": cloud_voice} if action == "create_voice" else {"status": "OK", "target_model": PRIVATE_TARGET}
        return SimpleNamespace(status_code=200, ok=True, json=lambda: {"output": output})
    monkeypatch.setattr(requests, "post", post)
    def checkpoint(update):
        state.update(update)
    request = {"kind": "clone", "name": "测试克隆", "model_id": PRIVATE_TARGET, "audio_path": str(source)}
    pending = backend.execute(request, tmp_path, checkpoint, state, initial=True)
    assert pending == {"status": "processing", "accepted": True}
    assert cloud_voice not in json.dumps(pending)
    saved = records.read_record(backend.clone._path(state["legacy_job_id"]))
    assert saved["voice_id"] == cloud_voice and saved["status"] == "checking"
    result = backend.execute(request, tmp_path, checkpoint, state, initial=False)
    assert result["status"] == "succeeded" and result["result"]["voice"]["name"] == "测试克隆"
    assert calls == ["create_voice", "query_voice", "query_voice"]


def test_doubao_accepted_task_is_saved_before_query_and_get_only_recovers_it(tmp_path, monkeypatch):
    import requests
    from backlot import studio_avatar, tts_runtime
    from tools.audio.doubao_tts import DoubaoTTS
    monkeypatch.setenv("DOUBAO_SPEECH_API_KEY", "fake-speech-only")
    backend = LegacyAudioBackend(tmp_path / "isolated")
    folder = tmp_path / ("call_" + "a" * 32)
    folder.mkdir()
    state, calls = {}, []
    def checkpoint(update):
        state.update(update)
    def post(url, **kwargs):
        calls.append(url)
        assert kwargs["allow_redirects"] is False
        if url == DoubaoTTS.SUBMIT_URL:
            assert state["doubao_request_id"] and kwargs["json"]["req_params"]["audio_params"]["speech_rate"] == 20
            return SimpleNamespace(status_code=200, json=lambda: {"code": 20000000, "data": {"task_id": "accepted-fake"}})
        assert url == DoubaoTTS.QUERY_URL and state["doubao_task_id"] == "accepted-fake"
        assert kwargs["json"] == {"task_id": "accepted-fake"}
        status = 1 if len(calls) == 2 else 2
        return SimpleNamespace(status_code=200, json=lambda: {"code": 20000000,
                               "data": {"task_status": status, "audio_url": "https://fake.example/audio.mp3", "usage": {"characters": 3}}})
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(studio_avatar, "download_result", lambda url, path: path.write_bytes(b"fake mp3"))
    monkeypatch.setattr(tts_runtime, "_convert_to_wav", lambda source, target: wav(target))
    request = {"kind": "tts", "text": "测试", "profile": {"provider_id": "doubao", "provider_voice_id": "fake-voice",
                 "resource_id": "seed-tts-2.0", "speech_rate": 1.2}}
    assert backend.execute(request, folder, checkpoint, state, initial=True)["status"] == "processing"
    assert backend.execute(request, folder, checkpoint, state, initial=False)["status"] == "succeeded"
    assert calls == [DoubaoTTS.SUBMIT_URL, DoubaoTTS.QUERY_URL, DoubaoTTS.QUERY_URL]


def test_real_catalog_only_contains_six_ali_public_candidates_and_existing_custom_cloud(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-only")
    backend = LegacyAudioBackend(tmp_path / "isolated")
    backend.center._doubao_profiles = lambda _: [
        {"id": "doubao_builtin", "provider_id": "doubao", "is_custom_cloud_voice": False},
        {"id": "tencent_builtin", "provider_id": "tencent", "is_custom_cloud_voice": False},
        {"id": "local_qwen", "provider_id": "voicebox_tts", "is_custom_cloud_voice": False},
        {"id": "my_clone", "provider_id": "bailian", "is_custom_cloud_voice": True},
    ]
    backend.center._tencent_profiles = lambda _: []
    backend.center._bailian_profiles = lambda _: []
    profiles = backend.catalog()
    assert {p["id"] for p in profiles} == {"my_clone", *["pub_" + v[0] for v in PUBLIC]}
    assert all(p["model_id"] == PUBLIC_TARGET and p["verification"] == "candidate_unverified"
               for p in profiles if p["id"].startswith("pub_"))


def test_requote_preserves_submitted_original_price_and_does_not_reprice_unknown_call(local):
    center, backend = local
    quote = quoted(center)
    center.submit(body(quote))
    center.pricing["tts:bailian:" + PUBLIC_TARGET] = {"per_character_micros": 1000}
    requote = quoted(center)
    assert requote == quote
    assert center.submit(body(requote))["status"] == "submission_unknown"
    assert backend.initials == 1


def test_public_voice_is_never_sent_to_private_v35_even_if_legacy_profile_was_misconfigured(local):
    center, backend = local
    backend.profiles.append({**backend.profiles[0], "id": "legacy_bad", "model_id": PRIVATE_TARGET})
    with pytest.raises(WorkError, match="公共音色请选择v3"):
        quoted(center, voice_id="legacy_bad")
    assert backend.initials == 0


@pytest.fixture
def mixed(tmp_path, monkeypatch):
    import backlot.studio_audio_internal as module
    from backlot import studio_services
    # Keep Windows' legacy MAX_PATH headroom for nested account/file checkpoints.
    private = tmp_path.parent / ("mix-" + records.fingerprint(tmp_path.name)[:8])
    private.mkdir()
    (private / "service-mode.json").write_text('{"mode":"gateway","audio_mode":"internal"}')
    state = {"key": "fake-key-a", "base": "https://relay.test/v2", "denied": set(),
             "accounts": {"fake-key-a": "account-a", "fake-key-a-rotated": "account-a", "fake-key-b": "account-b"},
             "calls": [], "backends": {}, "summary_override": None}
    class Gateway:
        def __init__(self, config):
            self.base_url, self.key = config["base_url"], config["api_key"]
        def request(self, path):
            assert path == "/account/summary"
            state["calls"].append((self.base_url, path))
            if self.key in state["denied"]:
                raise RuntimeError("private upstream error must not reach browser")
            if state["summary_override"] is not None:
                return state["summary_override"]
            return {"account_id": state["accounts"][self.key]}
    def client(config=None):
        assert config is not None, "account checks must bypass recursive audio routing"
        return Gateway(dict(config))
    studio = SimpleNamespace(private=private,
        configuration=lambda: {"base_url": state["base"], "api_key": state["key"]}, client=client)
    def backend(directory):
        return state["backends"].setdefault(str(directory), FakeBackend())
    monkeypatch.setattr(module, "LegacyAudioBackend", backend)
    monkeypatch.setattr(studio_services, "refresh_private_environment", lambda: None)
    return studio, state


def test_mixed_accounts_isolate_private_voice_preferences_images_quotes_and_operations(mixed):
    from PIL import Image
    studio, state = mixed
    first = InternalAudioCenter(studio)
    first.backend.profiles.append({"id": "private_a", "name": "A的声音", "provider_id": "bailian",
        "provider_voice_id": PRIVATE_TARGET + "-fake-a", "model_id": PRIVATE_TARGET, "speech_rate": 1.,
        "available": True, "is_custom_cloud_voice": True})
    first.preferences({"voice_id": "private_a"})
    image = io.BytesIO()
    Image.new("RGB", (256, 256), "blue").save(image, "PNG")
    uploaded = first.upload(image.getvalue(), "image", "a.png")
    first.preferences({"image_file_id": uploaded["id"], "speech_rate": 1.3}, "private_a")
    quote = quoted(first)
    first.backend.ready = True
    assert first.submit(body(quote))["status"] == "succeeded"
    assert first.preview(quote["operation_id"]).is_file()

    state["key"] = "fake-key-b"
    with pytest.raises(WorkError, match="账号已变化"):
        first.voices()
    second = InternalAudioCenter(studio)
    assert second.directory != first.directory
    assert second.voices()["preferences"]["voice_id"] is None
    assert all(item["id"] != "private_a" for item in second.voices()["items"])
    assert second.voices()["items"][0]["preferences"] == {"speech_rate": 1.}
    assert quoted(second)["operation_id"] != quote["operation_id"]
    for operation in (lambda: second.media(uploaded["id"]), lambda: second.runtime_profile("private_a"),
                      lambda: second.job(quote["operation_id"]), lambda: second.preview(quote["operation_id"]),
                      lambda: second.submit(body(quote))):
        with pytest.raises(WorkError):
            operation()
    assert not second.backend.calls

    state["key"] = "fake-key-a-rotated"
    state["denied"].add("fake-key-a")
    assert first.verify_scope() == first.account
    rotated = InternalAudioCenter(studio)
    assert rotated.directory == first.directory
    assert rotated.voices()["preferences"]["voice_id"] == "private_a"
    private_voice = next(item for item in rotated.voices()["items"] if item["id"] == "private_a")
    assert private_voice["preferences"] == {"speech_rate": 1.3, "image_file_id": uploaded["id"]}
    assert rotated.media(uploaded["id"])[1] == "image/jpeg"
    assert rotated.job(quote["operation_id"])["status"] == "succeeded"
    assert rotated.backend.initials == 1


def test_mixed_authentication_failure_or_revoked_key_never_reads_old_private_state(mixed):
    studio, state = mixed
    center = InternalAudioCenter(studio)
    center.preferences({"voice_id": "pub_longanyang"})
    state["denied"].add("fake-key-a")
    before = set(state["backends"])
    with pytest.raises(WorkError, match="无法核验") as failure:
        InternalAudioCenter(studio)
    assert "private upstream" not in str(failure.value)
    assert set(state["backends"]) == before
    with pytest.raises(WorkError, match="无法核验"):
        center.voices()  # A cached SDK centre must not bypass revocation.
    with pytest.raises(WorkError, match="无法核验"):
        quoted(center)
    assert not center.backend.calls


@pytest.mark.parametrize("summary", [{}, {"account_id": 4}, {"account_name": " "},
                                    {"account_id": "local", "mode": "internal_local"}])
def test_mixed_malformed_or_internal_identity_is_not_gateway_authentication(mixed, summary):
    studio, state = mixed
    state["summary_override"] = summary
    with pytest.raises(WorkError, match="无法核验"):
        InternalAudioCenter(studio)
    assert not state["backends"]


def test_mixed_account_name_identity_is_stable_but_other_gateway_origin_is_isolated(mixed):
    studio, state = mixed
    state["summary_override"] = {"account_name": "stable-legacy-account"}
    first = InternalAudioCenter(studio)
    first.preferences({"voice_id": "pub_longanyang"})
    state["key"] = "fake-key-a-rotated"
    assert InternalAudioCenter(studio).voices()["preferences"]["voice_id"] == "pub_longanyang"
    state["base"] = "https://another-relay.test/v2"
    other = InternalAudioCenter(studio)
    assert other.directory != first.directory and other.voices()["preferences"]["voice_id"] is None


def test_only_six_public_verifications_are_shared_from_original_local_scope(mixed):
    studio, state = mixed
    old = studio.private / "audio-center-internal" / "local-machine"
    old.mkdir(parents=True)
    fingerprint = FakeBackend().identity("bailian")
    entries = {"pub_" + upstream: {"credential_identity": fingerprint, "model_id": PUBLIC_TARGET,
               "operation_id": "call_" + "1" * 32} for upstream, _, _ in PUBLIC}
    entries["private_local"] = {"credential_identity": fingerprint, "model_id": PRIVATE_TARGET}
    records.write_record(old / "verifications.json", entries)
    records.write_record(old / "preferences.json", {"voice_id": "private_local", "voices": {"pub_longanyang": {"speech_rate": 1.8}}})
    for key in ("fake-key-a", "fake-key-b"):
        state["key"] = key
        center = InternalAudioCenter(studio)
        catalog = center.voices()
        assert len(catalog["items"]) == 6 and all(v["verification"] == "provider_verified" for v in catalog["items"])
        assert catalog["preferences"]["voice_id"] is None
        assert all(v["preferences"]["speech_rate"] == 1. for v in catalog["items"])
        assert not (center.directory / "preferences.json").exists()
        assert not (center.directory / "operations").exists()
        center.backend.key = "another-direct-supplier-account"
        assert all(v["verification"] == "candidate_unverified" for v in center.voices()["items"])
