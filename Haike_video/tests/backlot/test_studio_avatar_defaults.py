"""Account-scoped preset APIs with fake catalogs; no provider or real config."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot import studio_audio_api
from backlot.work_catalog import WorkError


@pytest.fixture
def defaults_api(tmp_path, monkeypatch):
    state = {"account": "account-a", "voice_available": True, "voice_status": "ready", "calls": []}

    class Center:
        def __init__(self):
            self.account = state["account"]
            self.directory = tmp_path / self.account

        def voices(self):
            state["calls"].append("voices")
            return {"mode": "gateway", "items": [
                {"id": "voice-one", "model": "haike/cosyvoice-public", "name": "雅雅",
                 "available": state["voice_available"], "status": state["voice_status"], "preferences": {"speech_rate": 1.15, "image_file_id": "image-one"}},
                {"id": "voice-two", "model": "haike/internal-tts", "name": "檬檬",
                 "available": True, "preferences": {"speech_rate": 1.1, "image_file_id": "image-two"}}],
                "preferences": {"voice_id": "voice-one"}}

        def media(self, identity):
            if identity not in {"image-one", "image-two"}:
                raise WorkError("该图片不属于当前账号")
            return b"fake-image", "image/png"

    monkeypatch.setattr(studio_audio_api, "center", lambda request: Center())
    app = FastAPI()
    app.include_router(studio_audio_api.router)
    return TestClient(app), state


BASE = "/api/studio/audio-center/avatar-defaults"


def put(client, values, revision=0, scope=None):
    return client.put(BASE, json={"expected_revision": revision,
                                 "expected_scope_id": scope or client.get(BASE).json()["scope_id"], "values": values})


def test_read_reuses_voice_preferences_without_inventing_a_budget_or_writing(defaults_api, tmp_path):
    client, state = defaults_api
    response = client.get(BASE)
    assert response.status_code == 200
    value = response.json()
    assert value["revision"] == 0
    assert value["values"]["voice_id"] == "voice-one"
    assert value["values"]["speech_rate"] == 1.15
    assert value["values"]["portrait_file_id"] == "image-one"
    assert value["values"]["max_charge_micros"] is None
    assert value["values"]["network_materials_enabled"] is False
    assert "network_materials_enabled" not in value["missing_fields"]
    assert value["origins"]["max_charge_micros"] == "unset"
    assert "max_charge_micros" in value["missing_fields"]
    assert value["ready"] is False
    assert list(tmp_path.iterdir()) == []


def test_saved_partial_preset_survives_reopen_is_account_scoped_and_cas_protected(defaults_api):
    client, state = defaults_api
    changes = {"template_id": "avatar-deepblue-n1-v1", "target_duration_seconds": 30,
               "max_charge_micros": None, "allow_graphic_fallback": True}
    saved = put(client, changes)
    assert saved.status_code == 200
    assert saved.json()["revision"] == 1
    assert saved.json()["values"]["max_charge_micros"] is None
    assert client.get(BASE).json()["values"]["template_id"] == "avatar-deepblue-n1-v1"
    stale = put(client, {"max_charge_micros": 9000000})
    assert stale.status_code == 409
    state["account"] = "account-b"
    other = client.get(BASE).json()
    assert other["revision"] == 0 and other["values"]["template_id"] is None
    state["account"] = "account-a"
    assert client.get(BASE).json()["revision"] == 1


def test_foreign_origin_cannot_save_or_resolve_a_private_preset(defaults_api):
    client, state = defaults_api
    for method, path, payload in (("PUT", BASE, {"expected_revision": 0, "values": {}}),
                                  ("POST", BASE + "/resolve", {"overrides": {}})):
        response = client.request(method, path, json=payload, headers={"Origin": "https://foreign.example"})
        assert response.status_code == 403
    assert state["calls"] == []


def test_explicit_values_override_saved_preset_and_resolution_does_not_change_it(defaults_api):
    client, _ = defaults_api
    saved = {"template_id": "avatar-deepblue-n1-v1", "speech_rate": 1.15,
             "target_duration_seconds": 30, "max_charge_micros": 5000000, "allow_graphic_fallback": True}
    assert put(client, saved).status_code == 200
    payload = {"voice_id": "voice-two", "speech_rate": 1.1, "template_id": "avatar-full-width-v2"}
    response = client.post(BASE + "/resolve", json={"overrides": payload})
    assert response.status_code == 200
    value = response.json()
    assert value["ready"] is True
    assert value["values"]["speech_rate"] == 1.1
    assert value["values"]["portrait_file_id"] == "image-two"
    assert value["values"]["max_charge_micros"] == 5000000
    assert value["origins"]["speech_rate"] == "explicit"
    assert value["origins"]["max_charge_micros"] == "saved"
    assert value["origins"]["portrait_file_id"] == "voice_preferences"
    snapshot = deepcopy(value["snapshot"])
    assert client.post(BASE + "/resolve", json={"overrides": payload}).json()["snapshot"] == snapshot
    assert client.get(BASE).json()["values"]["speech_rate"] == 1.15
    assert put(client, {"max_charge_micros": 7000000}, 1).status_code == 200
    assert snapshot["values"]["max_charge_micros"] == 5000000
    cleared = client.post(BASE + "/resolve", json={"overrides": {"max_charge_micros": None}}).json()
    assert cleared["ready"] is False and "max_charge_micros" in cleared["missing_fields"]


@pytest.mark.parametrize("values", [
    {"max_charge_micros": True}, {"max_charge_micros": 0}, {"max_charge_micros": 0.5},
    {"speech_rate": True}, {"speech_rate": 2.1}, {"target_duration_seconds": 121},
    {"allow_graphic_fallback": "yes"}, {"template_id": "missing-template"}, {"provider_api_key": "not-a-real-key"},
    {"network_materials_enabled": "true"}, {"network_materials_enabled": 1},
], ids=["boolean-budget", "zero-budget", "fractional-micros", "boolean-rate", "rate-range", "duration-range", "fallback-type", "template", "supplier-field", "network-string", "network-number"])
def test_invalid_fields_never_change_an_existing_preset(defaults_api, values):
    client, _ = defaults_api
    response = put(client, values)
    assert response.status_code == 422
    assert client.get(BASE).json()["revision"] == 0


def test_unknown_voice_and_foreign_portrait_cannot_become_defaults(defaults_api):
    client, _ = defaults_api
    for values in ({"voice_id": "foreign-voice"}, {"portrait_file_id": "foreign-image"}):
        assert put(client, values).status_code == 422
    assert client.get(BASE).json()["revision"] == 0


def test_unavailable_voice_is_missing_instead_of_silently_switching(defaults_api):
    client, state = defaults_api
    state["voice_available"] = False
    value = client.post(BASE + "/resolve", json={"overrides": {}}).json()
    assert value["values"]["voice_id"] == "voice-one"
    assert value["ready"] is False and "voice_id" in value["missing_fields"]


def test_inactive_catalog_status_cannot_be_marked_ready(defaults_api):
    client, state = defaults_api
    state["voice_status"] = "disabled"
    value = client.get(BASE).json()
    assert value["voices"][0]["available"] is False
    assert "voice_id" in value["missing_fields"]


def test_account_change_during_edit_cannot_save_into_another_accounts_same_revision(defaults_api):
    client, state = defaults_api
    old = client.get(BASE).json()
    state["account"] = "account-b"
    response = put(client, {"template_id": "avatar-deepblue-n1-v1"}, scope=old["scope_id"])
    assert response.status_code == 409
    assert client.get(BASE).json()["revision"] == 0


def test_new_draft_preserves_resolved_snapshot_and_rejects_tampering(defaults_api, tmp_path):
    from backlot.studio import Studio
    client, _ = defaults_api
    overrides = {"template_id": "avatar-deepblue-n1-v1", "target_duration_seconds": 30,
                 "max_charge_micros": 5000000, "allow_graphic_fallback": False}
    resolved = client.post(BASE + "/resolve", json={"overrides": overrides}).json()
    assert resolved["ready"] is True
    studio = Studio(tmp_path / "drafts" / "projects")
    request = {"template_id": overrides["template_id"], "title": "默认预设🍊", "text": "测试台词",
               "input": {"soundMode": "voice", "modelId": resolved["voice_model"],
                         "voiceId": "voice-one", "rate": 1.15, "avatar_defaults_snapshot": resolved["snapshot"]}}
    draft = studio.save_draft(request)
    assert draft["input"]["avatar_defaults_snapshot"] == resolved["snapshot"]
    tampered = deepcopy(request)
    tampered["input"]["avatar_defaults_snapshot"]["values"]["max_charge_micros"] = 999999999
    with pytest.raises(WorkError, match="快照"):
        studio.save_draft(tampered)


def test_integer_speed_and_duration_snapshot_survive_browser_json_roundtrip(defaults_api):
    from backlot.studio_avatar_defaults import validate_snapshot
    client, _ = defaults_api
    response = client.post(BASE + "/resolve", json={"overrides": {
        "template_id": "avatar-full-width-v2", "speech_rate": 1.0, "target_duration_seconds": 30.0,
        "max_charge_micros": 4000000, "allow_graphic_fallback": False}})
    snapshot = response.json()["snapshot"]
    snapshot["values"]["speech_rate"] = 1
    snapshot["values"]["target_duration_seconds"] = 30
    assert validate_snapshot(snapshot)["values"]["speech_rate"] == 1


def test_snapshot_allows_unset_account_image_when_task_supplies_its_own_portrait(defaults_api):
    from backlot.studio_avatar_defaults import validate_snapshot
    client, _ = defaults_api
    response = client.post(BASE + "/resolve", json={"overrides": {
        "template_id": "avatar-full-width-v2", "portrait_file_id": None,
        "target_duration_seconds": 30, "max_charge_micros": 5000000, "allow_graphic_fallback": True}})
    value = response.json()
    assert value["missing_fields"] == ["portrait_file_id"]
    # The production input separately owns and validates the caller's local portrait;
    # an account preset must not turn a Studio asset ID into an account file ID.
    assert validate_snapshot(value["snapshot"])["values"]["portrait_file_id"] is None


def test_network_preset_is_account_scoped_explicit_false_wins_and_old_snapshot_stays_frozen(defaults_api):
    from backlot.studio_avatar_defaults import _checksum, validate_snapshot
    client, state = defaults_api
    assert put(client, {"network_materials_enabled": True}).status_code == 200
    assert client.get(BASE).json()["values"]["network_materials_enabled"] is True
    resolved = client.post(BASE + "/resolve", json={"overrides": {
        "template_id": "avatar-deepblue-n1-v1", "target_duration_seconds": 25,
        "max_charge_micros": 5000000, "allow_graphic_fallback": True,
        "network_materials_enabled": False}}).json()
    assert resolved["values"]["network_materials_enabled"] is False
    assert resolved["origins"]["network_materials_enabled"] == "explicit"
    assert validate_snapshot(resolved["snapshot"]) == resolved["snapshot"]
    old = deepcopy(resolved["snapshot"])
    old["schema_version"] = 1
    old["values"].pop("network_materials_enabled")
    old["origins"].pop("network_materials_enabled")
    old["fingerprint"] = _checksum({k: v for k, v in old.items() if k != "fingerprint"})
    assert validate_snapshot(old) == old
    state["account"] = "account-b"
    assert client.get(BASE).json()["values"]["network_materials_enabled"] is False


def test_draft_rejects_invalid_network_flag_before_persistence(tmp_path):
    from backlot.studio import Studio
    studio = Studio(tmp_path / "projects")
    for invalid in ("true", 1, None):
        with pytest.raises(WorkError, match="联网素材"):
            studio.save_draft({"template_id": "avatar-full-width-v2", "title": "素材测试", "text": "测试内容",
                               "input": {"network_materials_enabled": invalid}})
    assert studio.drafts() == []


def test_real_audio_identity_reuses_account_namespace_across_key_rotation(tmp_path, monkeypatch):
    from backlot.studio import Studio
    from backlot.studio_audio import AudioCenter
    from backlot.studio_avatar_defaults import AvatarDefaults
    state = {"account": "a", "key": "fake-key-a"}
    studio = Studio(tmp_path / "projects")

    class Client:
        base_url = "https://example.test/v2"
        def request(self, path, body=None, **kwargs):
            if path == "/account/summary":
                return {"account_id": state["account"], "key_id": state["key"]}
            if path == "/voices":
                return {"items": [], "preferences": {}}
            raise AssertionError("Preset access must not execute provider calls")

    monkeypatch.setattr(studio, "client", lambda config=None: Client())
    first = AvatarDefaults(AudioCenter(studio))
    first.save({"expected_revision": 0, "expected_scope_id": first.scope_id,
                "values": {"max_charge_micros": 4000000}})
    state["key"] = "fake-key-rotated"
    assert AvatarDefaults(AudioCenter(studio)).read()["values"]["max_charge_micros"] == 4000000
    state["account"] = "b"
    assert AvatarDefaults(AudioCenter(studio)).read()["values"]["max_charge_micros"] is None
