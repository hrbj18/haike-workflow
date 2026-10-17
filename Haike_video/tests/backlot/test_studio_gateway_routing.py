"""Mixed routing never falls back on supplier, authentication or unknown errors."""

import json
from types import SimpleNamespace

import pytest

from backlot.studio_gateway_routing import GatewayRoutingClient
from backlot.work_catalog import WorkError


class FakeClient:
    def __init__(self, path, backend):
        self.state_dir, self.backend = path, backend
        self.directory = path
        self.account = "relay_" + "a" * 64
        self.current_account = self.account
        self.calls, self.intents = [], {}

    def verify_scope(self):
        if self.account != self.current_account:
            raise WorkError("当前海客账号已变化", "conflict")
        return self.account

    def quote(self, model, inputs, project_ref=""):
        self.calls.append(("quote", model))
        return {
            "id": ("iq_" if self.backend == "internal_audio" else "gquote_") + "1" * 32,
            "operation_id": "call_" + "2" * 32,
            "model": model,
            "max_charge_micros": "400",
        }

    def confirm(self, quote, ceiling, intent_id):
        self.calls.append(("confirm", intent_id))
        self.intents[intent_id] = quote["id"]
        return intent_id

    def resume(self, intent_id):
        self.calls.append(("resume", intent_id))
        return {
            "id": intent_id,
            "status": "submission_unknown",
            "backend": self.backend,
        }

    def request(self, *args, **kwargs):
        self.calls.append(("request", args[0]))
        return {"backend": self.backend}

    def upload(self, path, kind):
        self.calls.append(("upload", kind))
        return {"id": "gateway-file"}


@pytest.fixture
def mixed(tmp_path):
    studio = SimpleNamespace(private=tmp_path)
    (tmp_path / "service-mode.json").write_text(
        '{"mode":"gateway","audio_mode":"internal"}'
    )
    gateway, audio = (
        FakeClient(tmp_path / "relay", "gateway"),
        FakeClient(tmp_path / "audio", "internal_audio"),
    )
    sdk = GatewayRoutingClient(studio, gateway, internal_factory=lambda: audio)
    return studio, gateway, audio, sdk


def test_explicit_audio_only_routes_its_quote_intent_and_unknown_recovery(mixed):
    studio, gateway, audio, sdk = mixed
    quote = sdk.quote("haike/internal-tts", {"text": "hello"})
    assert quote["backend"] == "internal_audio"
    intent = sdk.confirm(quote, 400)
    assert sdk.wait(intent, 0)["status"] == "submission_unknown"
    restarted = GatewayRoutingClient(studio, gateway, internal_factory=lambda: audio)
    assert restarted.resume(intent)["backend"] == "internal_audio"
    assert not gateway.calls
    assert [call[0] for call in audio.calls] == ["quote", "confirm", "resume", "resume"]


def test_gateway_models_uploads_accounts_and_unknowns_never_use_internal(mixed):
    studio, gateway, audio, sdk = mixed
    assert sdk.upload("file.wav", "audio")["id"] == "gateway-file"
    assert sdk.request("/account/summary")["backend"] == "gateway"
    assert sdk.request("/capabilities")["backend"] == "gateway"
    quote = sdk.quote("haike/avatar", {})
    intent = sdk.confirm(quote, 400)
    assert sdk.resume(intent)["backend"] == "gateway"
    assert (
        GatewayRoutingClient(studio, gateway, internal_factory=lambda: audio).resume(
            intent
        )["backend"]
        == "gateway"
    )
    assert not audio.calls


def test_gateway_error_has_no_automatic_internal_fallback(mixed):
    _, gateway, audio, sdk = mixed

    def unavailable(*args):
        raise ValueError("fake unavailable relay")

    gateway.quote = unavailable
    with pytest.raises(ValueError, match="unavailable relay"):
        sdk.quote("haike/cosyvoice", {"text": "hello"})
    assert not audio.calls


def test_intent_backend_cannot_be_switched_and_audio_mode_cannot_be_http_enabled(mixed):
    studio, _, _, sdk = mixed
    audio_quote = sdk.quote("haike/internal-tts", {"text": "hello"})
    intent = sdk.confirm(audio_quote, 400)
    cloud_quote = sdk.quote("haike/avatar", {})
    with pytest.raises(WorkError, match="不能更换"):
        sdk.confirm(cloud_quote, 400, intent)
    (studio.private / "service-mode.json").write_text('{"mode":"gateway"}')
    with pytest.raises(WorkError, match="未启用"):
        sdk.quote("haike/internal-tts", {"text": "hello"})


def test_legacy_cloud_journal_restores_only_that_cloud_intent(mixed):
    _, gateway, audio, sdk = mixed
    intent = "call_" + "a" * 32
    gateway.state_dir.mkdir()
    (gateway.state_dir / (intent + ".json")).write_text(
        json.dumps({"body": {"call_intent_id": intent, "quote_id": "gquote_original"}})
    )
    assert sdk.resume(intent)["backend"] == "gateway"
    assert not audio.calls
    with pytest.raises(WorkError, match="没有该调用"):
        sdk.resume("call_" + "b" * 32)


def test_mixed_private_route_data_and_unknown_recovery_stay_with_account(mixed):
    studio, gateway, audio_a, sdk_a = mixed
    quote_a = sdk_a.quote("haike/internal-tts", {"text": "private A"})
    intent_a = sdk_a.confirm(quote_a, 400)
    assert not (sdk_a.directory / "quotes").exists()
    binding = json.loads(sdk_a._binding_path(intent_a).read_text(encoding="utf-8"))
    assert set(binding) == {"backend", "scope"}
    audio_a.current_account = "relay_" + "b" * 64
    with pytest.raises(WorkError, match="账号已变化"):
        sdk_a.resume(intent_a)
    audio_b = FakeClient(studio.private / "aud-b", "internal_audio")
    audio_b.account = audio_b.current_account = "relay_" + "b" * 64
    sdk_b = GatewayRoutingClient(studio, gateway, internal_factory=lambda: audio_b)
    with pytest.raises(WorkError, match="其他海客账号"):
        sdk_b.resume(intent_a)
    with pytest.raises(WorkError, match="缺少原配音"):
        sdk_b.confirm(quote_a, 400)
    assert not audio_b.calls and not gateway.calls
    # Rotating a Key within A keeps the same account directory and original unknown call.
    audio_a.current_account = audio_a.account
    assert (
        GatewayRoutingClient(studio, gateway, internal_factory=lambda: audio_a).resume(
            intent_a
        )["status"]
        == "submission_unknown"
    )
