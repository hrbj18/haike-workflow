"""Real intent persistence with fake remote accounts; no provider or paid calls."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot.studio import Studio, sdk_type
from backlot.studio_audio import AudioCenter
from backlot.studio_avatar import tts_request, validate_voice
from backlot.studio_audio_api import router
from backlot.work_catalog import WorkError


class Missing(ValueError):
    status = 404
    code = "not_found"


class NoBalance(ValueError):
    status = 409
    code = 'commercial_balance_low'


@pytest.fixture
def relay(tmp_path, monkeypatch):
    studio = Studio(tmp_path / "projects")
    state = {"account": "account-a", "key": "fake-a", "quotes": {}, "jobs": {}, "calls": [], "drop": True}
    Base = sdk_type()

    class Client(Base):
        def request(self, path, body=None, idem=None, raw=None, **kwargs):
            state["calls"].append((state["account"], path, body, idem, kwargs))
            if path == "/account/summary":
                return {"account_id": state["account"], "key_id": state["key"]}
            if path == "/voices":
                return {"items": [{"id": "pub_one", "model": "haike/cosyvoice-public",
                                   "preferences": {"speech_rate": 1, "image_file_id": "file_image"}}],
                        "preferences": {"voice_id": "pub_one"}}
            if path == "/quotes":
                value = {"id": "gquote_" + str(len(state["quotes"]) + 1), "model": body["model"],
                         "max_charge_micros": "120", "expires_at": "2099-01-01T00:00:00Z"}
                state["quotes"][value["id"]] = body
                return value
            if path == "/jobs":
                if state.get('no_balance'):
                    raise NoBalance()
                key = (state["account"], idem)
                if key not in state["jobs"]:
                    state["jobs"][key] = {"id": "gj_test", "status": "succeeded", "charged_micros": "120",
                                          "result": {"voice": {"id": "voice_private", "name": "测试音色"}}}
                if state["drop"]:
                    state["drop"] = False
                    raise TimeoutError("fake lost response")
                return state["jobs"][key]
            if path.startswith("/requests/"):
                result = state["jobs"].get((state["account"], path.rsplit("/", 1)[1]))
                if result is None:
                    raise Missing()
                return result
            if path.startswith("/jobs/"):
                if state.get('lose_job_read'):
                    raise Missing()
                return next(iter(state["jobs"].values()))
            if path == "/voice-preferences" or path.endswith("/preferences"):
                assert kwargs["method"] == "PUT"
                return body
            if path == "/files/file_image":
                assert kwargs["response_bytes"] is True
                return b"\xff\xd8\xfffake-owned-image"
            raise AssertionError(path)

    monkeypatch.setattr(studio, "client", lambda config=None: Client("http://127.0.0.1:17894/v2", state["key"], tmp_path / "unused"))
    return studio, state


def quote_and_body(center):
    quote = center.quote({"model": "haike/voice-clone", "input": {"name": "我的音色", "audio_file": "file_one", "consent": True}})
    return quote, {"quote_id": quote["id"], "operation_id": quote["operation_id"],
                   "max_charge_micros": "120", "confirmed": True}


def test_lost_submission_recovers_one_paid_intent_and_get_never_submits(relay):
    studio, state = relay
    center = AudioCenter(studio)
    quote, body = quote_and_body(center)
    result = center.submit(body)
    assert result["status"] == "submission_unknown"
    intent = center.directory / "intents" / (quote["operation_id"] + ".json")
    assert json.loads(intent.read_text())["body"]["quote_id"] == quote["id"]
    before = len([c for c in state["calls"] if c[1] == "/jobs"])
    recovered = AudioCenter(studio).job(quote["operation_id"])
    assert recovered["status"] == "succeeded"
    assert len([c for c in state["calls"] if c[1] == "/jobs"]) == before
    assert AudioCenter(studio).submit(body)["status"] == "succeeded"
    assert len(state["jobs"]) == 1
    assert {c[3] for c in state["calls"] if c[1] == "/jobs"} == {quote["operation_id"]}


def test_account_switch_blocks_quotes_operations_media_but_key_rotation_keeps_them(relay):
    studio, state = relay
    center = AudioCenter(studio)
    quote, body = quote_and_body(center)
    center.submit(body)
    state["key"] = "fake-second-key-same-account"
    rotated = AudioCenter(studio)
    assert rotated.directory == center.directory
    assert rotated.job(quote["operation_id"])["status"] == "succeeded"
    state["account"] = "account-b"
    other = AudioCenter(studio)
    assert other.directory != center.directory
    before = len(state["calls"])
    with pytest.raises(WorkError, match="不属于"):
        other.job(quote["operation_id"])
    with pytest.raises(WorkError, match="不存在"):
        other.submit(body)
    with pytest.raises(WorkError, match="不属于"):
        other.preview(quote["operation_id"])
    assert len(state["calls"]) == before


def test_budget_and_operation_tampering_stop_before_submit(relay):
    studio, state = relay
    center = AudioCenter(studio)
    _, body = quote_and_body(center)
    with pytest.raises(WorkError, match="费用上限低于"):
        center.submit({**body, "max_charge_micros": "119"})
    with pytest.raises(WorkError, match="不一致"):
        center.submit({**body, "operation_id": "call_" + "0" * 32})
    with pytest.raises(WorkError, match="确认"):
        center.submit({**body, "confirmed": False})
    assert not state["jobs"]
    center.submit(body)
    with pytest.raises(WorkError, match="原操作"):
        center.submit({**body, "max_charge_micros": "121"})


def test_preferences_and_owned_media_forward_to_current_account(relay):
    studio, state = relay
    center = AudioCenter(studio)
    assert center.voices()["items"][0]["portrait_url"].endswith("/file_image")
    assert center.preferences({"voice_id": "pub_one"})["voice_id"] == "pub_one"
    assert center.preferences({"speech_rate": 1.2}, "pub_one")["speech_rate"] == 1.2
    content, mime = center.media("file_image")
    assert content.startswith(b"\xff\xd8\xff") and mime == "image/jpeg"
    with pytest.raises(WorkError):
        center.preferences({"owner_id": "another-account"})
    with pytest.raises(WorkError):
        center.media("../../other")


def test_cross_origin_writes_rejected_before_reading_relay_credentials(relay):
    studio, state = relay
    app = FastAPI()
    app.state.studio = studio
    app.state.works_projects_root = studio.projects_root
    app.include_router(router)
    client = TestClient(app)
    response = client.put("/api/studio/audio-center/preferences", json={"voice_id": "pub_one"}, headers={"Origin": "https://foreign.example"})
    assert response.status_code == 403
    assert state["calls"] == []
    assert client.get("/api/studio/audio-center").status_code == 200


def test_model_voice_and_speed_are_frozen_separately_without_legacy_rewrite():
    value = {"soundMode": "voice", "modelId": "haike/cosyvoice-public", "voiceId": "pub_one", "rate": 1.2}
    validate_voice(value)
    assert tts_request({"input": value, "text": "测试"}) == (
        "haike/cosyvoice-public", {"text": "测试", "voice_id": "pub_one", "speech_rate": 1.2})
    legacy = {"voiceId": "haike/cosyvoice", "rate": 1.2}
    assert tts_request({"input": legacy, "text": "旧任务"}) == ("haike/cosyvoice", {"text": "旧任务"})
    with pytest.raises(WorkError, match="重新选择"):
        validate_voice({**legacy, "soundMode": "voice"})


def test_existing_job_read_404_preserves_unknown_instead_of_enabling_new_charge(relay):
    studio, state = relay
    state['drop'] = False
    center = AudioCenter(studio)
    quote, body = quote_and_body(center)
    assert center.submit(body)['status'] == 'succeeded'
    state['lose_job_read'] = True
    assert center.submit(body)['status'] == 'submission_unknown'
    assert len(state['jobs']) == 1
    assert center.job(quote['operation_id'])['status'] == 'succeeded'


def test_definitive_budget_rejection_survives_refresh_and_can_resume_same_intent(relay):
    studio, state = relay
    state['no_balance'] = True
    center = AudioCenter(studio)
    quote, body = quote_and_body(center)
    result = center.submit(body)
    assert result['status'] == 'failed' and result['accepted'] is False
    assert '余额不足' in result['error']
    assert AudioCenter(studio).job(quote['operation_id'])['status'] == 'failed'
    assert not state['jobs']
    state['no_balance'] = False
    state['drop'] = False
    assert center.submit(body)['status'] == 'succeeded'
    assert len(state['jobs']) == 1
