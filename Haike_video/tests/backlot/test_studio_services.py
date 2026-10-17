"""Internal supplier management is startup-gated and never returns credentials."""

import json
from types import SimpleNamespace

import pytest

from backlot import ai_text
from backlot import studio_services as services
from backlot.work_catalog import WorkError


@pytest.fixture
def internal_studio(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_text, "CONFIG_ROOT", tmp_path)
    for name in services.ENV_WHITELIST:
        monkeypatch.delenv(name, raising=False)
    import lib.env_loader

    monkeypatch.setattr(lib.env_loader, "load_env", lambda *a, **k: None)
    import lib.tencent_cloud

    monkeypatch.setattr(lib.tencent_cloud, "load_env", lambda *a, **k: None)
    studio = SimpleNamespace(
        private=tmp_path / ".backlot",
        internal_admin_enabled=True,
        internal_bind_host="127.0.0.1",
    )
    studio.private.mkdir()
    (studio.private / "service-mode.json").write_text('{"mode":"internal"}')
    return studio


def test_service_mode_never_grants_provider_administration(internal_studio):
    studio = internal_studio
    assert services.service_mode(studio) == "internal"
    studio.internal_admin_enabled = False
    for action in (
        lambda: services.settings(studio),
        lambda: services.update_provider(studio, "bailian", {"api_key": "fake"}),
    ):
        with pytest.raises(WorkError) as error:
            action()
        assert error.value.code == "forbidden"
    studio.internal_admin_enabled = True
    studio.internal_bind_host = "0.0.0.0"
    with pytest.raises(WorkError):
        services.settings(studio)


def test_missing_mode_is_gateway_and_unknown_mode_fails_closed(internal_studio):
    path = internal_studio.private / "service-mode.json"
    path.unlink()
    assert services.service_mode(internal_studio) == "gateway"
    path.write_text('{"mode":"internal","query":"admin"}')
    assert services.service_mode(internal_studio) == "internal"
    path.write_text('{"mode":"admin"}')
    with pytest.raises(WorkError):
        services.service_mode(internal_studio)


def test_audio_override_is_private_and_defaults_to_service_mode(internal_studio):
    path = internal_studio.private / "service-mode.json"
    assert services.audio_mode(internal_studio) == "internal"
    path.write_text('{"mode":"gateway","audio_mode":"internal"}')
    assert services.service_mode(internal_studio) == "gateway"
    assert services.audio_mode(internal_studio) == "internal"
    internal_studio.internal_admin_enabled = False
    with pytest.raises(WorkError):
        services.settings(internal_studio)
    path.write_text('{"mode":"gateway","audio_mode":"automatic"}')
    with pytest.raises(WorkError):
        services.audio_mode(internal_studio)


def test_bailian_key_enables_tts_without_optional_oss_or_old_reader(
    internal_studio, monkeypatch
):
    from backlot import bailian_config

    monkeypatch.setattr(
        bailian_config, "read_bailian_config", lambda: {"configured": False}
    )
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-bailian-tts-only")
    public = next(
        p
        for p in services.settings(internal_studio)["providers"]
        if p["id"] == "bailian"
    )
    assert public["configured"] is True and public["has_key"] is True
    assert not any(
        f["configured"] for f in public["fields"] if f["name"].startswith("oss_")
    )
    assert "fake-bailian-tts-only" not in json.dumps(public)
    monkeypatch.delenv("DASHSCOPE_API_KEY")
    assert (
        next(
            p
            for p in services.settings(internal_studio)["providers"]
            if p["id"] == "bailian"
        )["configured"]
        is False
    )


@pytest.mark.parametrize(
    ("provider", "payload"),
    [
        ("bailian", {"api_key": "fake-bailian-private"}),
        (
            "tencent",
            {"secret_id": "fake-tencent-id", "secret_key": "fake-tencent-private"},
        ),
        ("runninghub", {"api_key": "fake-runninghub-private"}),
        (
            "text-ai",
            {
                "api_key": "fake-openai-private",
                "base_url": "https://example.test/v1",
                "model": "test-model",
            },
        ),
        ("doubao-text", {"api_key": "fake-doubao-private"}),
        (
            "doubao-speech",
            {"api_key": "fake-speech-private", "voice_type": "test-voice"},
        ),
        ("doubao-asr", {"api_key": "fake-asr-private"}),
        ("pexels", {"api_key": "fake-pexels-private"}),
    ],
)
def test_existing_private_config_writers_preserve_blank_secrets(
    internal_studio, provider, payload
):
    saved = services.update_provider(internal_studio, provider, payload)
    assert saved["has_key"]
    secret_fields = [f for f in saved["fields"] if f["secret"]]
    assert secret_fields and all("value" not in f for f in secret_fields)
    for name, value in payload.items():
        if name in {"api_key", "secret_id", "secret_key"}:
            assert value not in json.dumps(saved)
    original = ai_text._secrets_path().read_text()
    services.update_provider(
        internal_studio, provider, {f["name"]: "" for f in secret_fields}
    )
    after = ai_text._secrets_path().read_text()
    for item in services.PROVIDERS[provider]["fields"]:
        if item["secret"] and item["name"] in payload:
            assert payload[item["name"]] in original and payload[item["name"]] in after
    snapshot = services.settings(internal_studio)
    assert all(
        value not in json.dumps(snapshot)
        for key, value in payload.items()
        if key in {"api_key", "secret_id", "secret_key"}
    )


def test_unknown_fields_invalid_endpoint_and_env_injection_are_rejected(
    internal_studio,
):
    for payload in (
        {"api_key": "fake", "clear_api_key": True},
        {"api_key": "fake\nINJECT=bad"},
        {"api_key": "fake", "base_url": "https://user:secret@example.test"},
        {"api_key": "fake", "base_url": "http://example.test/v1?key=fake-private"},
        {"api_key": "fake", "base_url": "http://example.test/v1#fake-private"},
        {"api_key": "fake", "base_url": "http://@example.test/v1"},
        {"api_key": "fake", "base_url": "http://example.test:invalid/v1"},
        {"api_key": "fake", "base_url": "ftp://example.test/v1"},
    ):
        with pytest.raises(WorkError):
            services.update_provider(internal_studio, "text-ai", payload)
    assert not ai_text._secrets_path().is_file()


def test_explicit_text_http_relay_can_be_saved_without_exposing_key(internal_studio):
    saved = services.update_provider(internal_studio, "text-ai", {
        "api_key": "fake-http-private", "base_url": "http://relay.example.test/v1", "model": "test-model",
    })
    assert saved["has_key"] and saved["configured"]
    assert "fake-http-private" not in json.dumps(saved)
    _, values = ai_text._read_env_file(ai_text._secrets_path())
    assert values["OPENAI_BASE_URL"] == "http://relay.example.test/v1"


@pytest.mark.parametrize("provider", ["runninghub", "doubao-text", "bailian"])
def test_text_http_support_does_not_relax_other_suppliers(provider):
    field = "oss_endpoint" if provider == "bailian" else "base_url"
    with pytest.raises(WorkError, match="HTTPS"):
        services._validate({field: "http://supplier.example.test/v1"}, provider)


def test_budget_policy_is_explicit_nonfree_and_supplier_specific(internal_studio):
    assert services.budget_policy(internal_studio)["daily_limit_micros"] == "0"
    policy = {
        "per_call_micros": {"haike/text": "10000"},
        "daily_limit_micros": "20000",
        "audio_pricing": {
            "clone:bailian:cosyvoice-v3.5-flash": {
                "fixed_micros": 0,
                "free_confirmed": True,
            }
        },
    }
    assert services.update_budget_policy(internal_studio, policy) == policy
    for change in (
        {**policy, "daily_limit_micros": "0"},
        {**policy, "per_call_micros": {"haike/text": "0"}},
        {
            **policy,
            "audio_pricing": {
                "clone:bailian:cosyvoice-v3.5-flash": {"fixed_micros": 0}
            },
        },
    ):
        with pytest.raises(WorkError):
            services.update_budget_policy(internal_studio, change)
    assert services.budget_policy(internal_studio) == policy


def test_refresh_only_supplier_whitelist_not_server_or_database_controls(
    internal_studio, monkeypatch
):
    ai_text._secrets_path().write_text(
        'OPENAI_API_KEY="fake-refresh"\nBACKLOT_PORT="9999"\n'
    )
    monkeypatch.setenv("BACKLOT_PORT", "14756")
    services.refresh_private_environment()
    import os

    assert os.environ["OPENAI_API_KEY"] == "fake-refresh"
    assert os.environ["BACKLOT_PORT"] == "14756"
