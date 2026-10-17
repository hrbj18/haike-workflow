"""Private Bailian ASR shares SDK intents/budgets; no provider is contacted."""
import json
from types import SimpleNamespace
import wave

import pytest

from backlot import ai_text, studio_services
from backlot.studio_gateway_routing import GatewayRoutingClient
from backlot.studio_internal_gateway import InternalClient
from backlot.work_catalog import WorkError
from lib import bailian_speech


class Scope:
    def __init__(self, directory, suffix="a"):
        self.account = self.current_account = "relay_" + suffix * 64
        self.directory = directory / suffix

    def verify_scope(self):
        if self.account != self.current_account:
            raise WorkError("当前海客账号已变化", "conflict")
        return self.account

    def voices(self):
        pytest.fail("ASR must not enumerate voices")


class Relay:
    def __init__(self, path):
        self.state_dir = path
        self.calls = []

    def request(self, path, *args, **kwargs):
        self.calls.append(path)
        return {"items": [{"model": "haike/tencent-asr"}]}

    def upload(self, path, kind):
        self.calls.append("upload")
        return {"id": "relay-file"}


@pytest.fixture
def setup_asr(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_text, "CONFIG_ROOT", tmp_path)
    for name in studio_services.ENV_WHITELIST:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-private-bailian-key")
    studio = SimpleNamespace(private=tmp_path / ".backlot", projects_root=tmp_path / "projects",
        internal_admin_enabled=True, internal_bind_host="127.0.0.1")
    studio.private.mkdir()
    (studio.private / "service-mode.json").write_text('{"mode":"gateway","audio_mode":"gateway"}', encoding="utf-8")
    policy = studio.private / "studio-asr/policy.json"
    policy.parent.mkdir()
    policy.write_text('{"bailian_enabled":true,"default_provider":"gateway"}', encoding="utf-8")
    studio_services.update_budget_policy(studio, {"per_call_micros": {"haike/bailian-asr": "14584"}, "daily_limit_micros": "14584"})
    audio = tmp_path / "audio.wav"
    with wave.open(str(audio), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000); out.writeframes(b"\0\0" * 16000)
    scope = Scope(tmp_path / "accounts")
    return studio, scope, audio


def client_for(setup_asr, adapter):
    studio, scope, _ = setup_asr
    return InternalClient(studio, asr_only=True, audio_center=scope, adapter=adapter)


def test_unverified_bailian_default_can_quote_first_task_without_faking_verification(setup_asr):
    from backlot import studio_asr
    studio, _, audio = setup_asr
    policy_path = studio.private / "studio-asr/policy.json"
    policy_path.write_text(json.dumps({"bailian_enabled": True, "default_provider": "bailian", "verified": False}), encoding="utf-8")
    before = policy_path.read_bytes()
    snapshot = studio_asr.snapshot(studio)
    adapter = SimpleNamespace(execute=lambda *a: pytest.fail("Quotation must not execute paid ASR"))
    client = client_for(setup_asr, adapter)
    prepared = client.prepare_asr_audio(audio)
    quote = client.quote(snapshot["model"], {"audio_file": prepared["id"]})
    assert quote["model"] == "haike/bailian-asr" and quote["max_charge_micros"] == "14584"
    assert studio_asr.status(studio)["verified"] is False
    assert policy_path.read_bytes() == before


def test_explicit_bailian_asr_route_uses_private_files_intents_and_one_machine_budget(setup_asr):
    studio, scope, audio = setup_asr
    calls = []

    class Supplier:
        def execute(self, model, inputs, checkpoint, upstream_id=None):
            calls.append(model)
            checkpoint("provider-asr-001")
            return {"result": {"provider": "bailian", "segments": [{"start": 0, "end": 1, "text": "测试"}]}, "usage": {"input_tokens": 20}}

    local = client_for(setup_asr, Supplier())
    relay = Relay(studio.private / "relay")
    routed = GatewayRoutingClient(studio, relay, internal_asr_factory=lambda: local)
    prepared = routed.prepare_asr_audio(audio)
    quote = routed.quote("haike/bailian-asr", {"audio_file": prepared["id"]}, "project-one")
    assert prepared["backend"] == quote["backend"] == "internal_asr"
    assert quote["max_charge_micros"] == "14584"
    intent = routed.confirm(quote, 14584)
    assert calls == []
    result = routed.wait(intent, 0)
    assert result["status"] == "succeeded" and result["charged_micros"] is None
    assert calls == ["haike/bailian-asr"]
    assert GatewayRoutingClient(studio, relay, internal_asr_factory=lambda: local).resume(intent)["status"] == "succeeded"
    assert len(calls) == 1
    assert routed.request("/capabilities") == {"items": [{"model": "haike/tencent-asr"}]}
    assert relay.calls == ["/capabilities"]
    assert routed.upload(audio, "audio")["id"] == "relay-file"  # Ordinary upload never silently moves off relay.
    for path in studio.private.rglob("*.json"):
        assert "fake-private-bailian-key" not in path.read_text(encoding="utf-8")
    other = routed.prepare_asr_audio(audio)
    second = routed.quote("haike/bailian-asr", {"audio_file": other["id"]}, "project-two")
    if second["operation_id"] == quote["operation_id"]:
        pytest.fail("project reference must distinguish independent admitted work")
    with pytest.raises(WorkError) as error:
        routed.wait(routed.confirm(second, 14584), 0)
    assert error.value.code == "budget_limit" and len(calls) == 1


def test_asr_quote_file_and_intent_cannot_cross_accounts_or_backend(setup_asr):
    studio, scope, audio = setup_asr
    supplier = SimpleNamespace(execute=lambda *a: pytest.fail("no supplier call expected"))
    local_a = client_for(setup_asr, supplier)
    relay = Relay(studio.private / "relay")
    a = GatewayRoutingClient(studio, relay, internal_asr_factory=lambda: local_a)
    prepared = a.prepare_asr_audio(audio)
    quote = a.quote("haike/bailian-asr", {"audio_file": prepared["id"]})
    intent = a.confirm(quote, 14584)
    scope_b = Scope(scope.directory.parent, "b")
    local_b = InternalClient(studio, asr_only=True, audio_center=scope_b, adapter=supplier)
    b = GatewayRoutingClient(studio, relay, internal_asr_factory=lambda: local_b)
    with pytest.raises(WorkError) as error:
        b.quote("haike/bailian-asr", {"audio_file": prepared["id"]})
    assert error.value.code == "missing"
    assert prepared["id"] not in str(error.value)
    with pytest.raises(WorkError):
        b.confirm(quote, 14584)
    with pytest.raises(WorkError, match="其他海客账号"):
        b.resume(intent)
    scope.current_account = scope_b.account
    with pytest.raises(WorkError, match="账号已变化"):
        a.resume(intent)
    with pytest.raises(WorkError):
        local_b.quote("haike/tencent-asr", {"audio_file": prepared["id"]})
    assert relay.calls == []


@pytest.mark.parametrize("kind,definitive,accepted,expected", [
    ("invalid_key", True, False, "failed"), ("insufficient_balance", True, False, "failed"),
    ("other", False, False, "submission_unknown"), ("invalid_key", False, True, "processing"),
])
def test_structured_bailian_failure_keeps_accepted_and_unknown_calls_recoverable(setup_asr, kind, definitive, accepted, expected):
    class Supplier:
        def execute(self, model, inputs, checkpoint, upstream_id=None):
            if accepted:
                checkpoint("accepted-asr-001")
            error = bailian_speech.BailianSpeechError("fake supplier text must never be persisted")
            error.failure_kind, error.provider_code = kind, "TEST_PROVIDER_CODE"
            error.http_status, error.definitive, error.accepted = 401, definitive, accepted
            raise error

    local = client_for(setup_asr, Supplier())
    prepared = local.prepare_asr_audio(setup_asr[2])
    quote = local.quote("haike/bailian-asr", {"audio_file": prepared["id"]})
    result = local.wait(local.confirm(quote, 14584), 0)
    assert result["status"] == expected
    assert result["failure_kind"] == kind and result["provider_code"] == "TEST_PROVIDER_CODE"
    assert result["definitive"] is definitive and result["accepted"] is accepted
    for path in setup_asr[0].private.rglob("*.json"):
        assert "fake supplier text" not in path.read_text(encoding="utf-8")


def test_direct_adapter_reuses_durable_bailian_transport_and_keeps_word_timestamps(setup_asr, monkeypatch):
    from backlot import bailian_asr
    observed = []

    def transcribe(audio, *, artifact_dir, on_accepted, **kwargs):
        observed.append((audio, artifact_dir))
        on_accepted("upstream-existing-1")
        return "测试", [{"start": .1, "end": .8, "text": "测试", "words": [{"start": .1, "end": .8, "text": "测试"}]}], {
            "provider": "bailian", "model": bailian_speech.ASR_MODEL, "task_id": "upstream-existing-1", "usage": {"input_tokens": 3}}

    monkeypatch.setattr(bailian_asr, "transcribe_file", transcribe)
    local = client_for(setup_asr, None)
    prepared = local.prepare_asr_audio(setup_asr[2])
    quote = local.quote("haike/bailian-asr", {"audio_file": prepared["id"]})
    intent = local.confirm(quote, 14584)
    result = local.wait(intent, 0)
    assert result["status"] == "succeeded"
    assert result["result"]["provider"] == "bailian"
    assert result["result"]["segments"][0]["words"][0]["start"] == .1
    assert observed[0][0].is_relative_to(local.directory / "files")
    assert observed[0][1].is_relative_to(local.directory)
    assert local.resume(intent)["status"] == "succeeded" and len(observed) == 1


def test_private_gate_and_no_http_file_path_or_foreign_gateway_file(setup_asr):
    studio, scope, audio = setup_asr
    local = client_for(setup_asr, SimpleNamespace())
    with pytest.raises(WorkError) as error:
        local.quote("haike/bailian-asr", {"audio_file": str(audio)})
    assert error.value.code == "missing" and str(audio) not in str(error.value)
    with pytest.raises(WorkError) as error:
        local.quote("haike/bailian-asr", {"audio_file": "file_" + "f" * 24})
    assert error.value.code == "missing"
    (studio.private / "studio-asr/policy.json").write_text('{"bailian_enabled":false}', encoding="utf-8")
    with pytest.raises(WorkError):
        local.prepare_asr_audio(audio)


def test_missing_key_is_definitive_local_rejection_before_any_network(setup_asr, monkeypatch):
    from backlot import bailian_asr
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setattr(bailian_asr, "transcribe_file", lambda *a, **k: pytest.fail("missing Key must not reach transport"))
    local = client_for(setup_asr, None)
    prepared = local.prepare_asr_audio(setup_asr[2])
    quote = local.quote("haike/bailian-asr", {"audio_file": prepared["id"]})
    assert quote["billing_unit"] == "tokens"
    result = local.wait(local.confirm(quote, 14584), 0)
    assert result["status"] == "failed" and result["failure_kind"] == "invalid_key"
    assert result["definitive"] is True and result["accepted"] is False
    assert result["provider_code"] == "LOCAL_KEY_MISSING"


def test_unknown_never_reexecutes_but_accepted_retries_only_its_original_task(setup_asr):
    calls = []

    class Supplier:
        def execute(self, model, inputs, checkpoint, upstream_id=None):
            calls.append(upstream_id)
            raise bailian_speech.BailianAmbiguous("synthetic submit unknown")

    local = client_for(setup_asr, Supplier())
    prepared = local.prepare_asr_audio(setup_asr[2])
    quote = local.quote("haike/bailian-asr", {"audio_file": prepared["id"]})
    intent = local.confirm(quote, 14584)
    assert local.wait(intent, 0)["status"] == "submission_unknown"
    restarted = client_for(setup_asr, Supplier())
    assert restarted.resume(intent)["status"] == "submission_unknown" and calls == [None]


def test_accepted_auth_failure_retains_original_task_and_credential_change_cannot_fallback(setup_asr, monkeypatch):
    calls = []

    class Supplier:
        def execute(self, model, inputs, checkpoint, upstream_id=None):
            calls.append(upstream_id)
            checkpoint("accepted-asr-original")
            raise bailian_speech.BailianSpeechError(
                "poll auth failure",
                failure_kind="invalid_key",
                provider_code="InvalidApiKey",
                http_status=401,
                definitive=True,
                accepted=True,
                task_id="accepted-asr-original",
            )

    local = client_for(setup_asr, Supplier())
    prepared = local.prepare_asr_audio(setup_asr[2])
    quote = local.quote("haike/bailian-asr", {"audio_file": prepared["id"]})
    intent = local.confirm(quote, 14584)
    first = local.wait(intent, 0)
    assert first["status"] == "processing" and first["definitive"] is False
    assert first["accepted"] is True and first["upstream_id"] == "accepted-asr-original"
    assert local.resume(intent)["status"] == "processing"
    assert calls == [None, "accepted-asr-original"]
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(WorkError, match="配置已变化"):
        local.resume(intent)
    assert len(calls) == 2
