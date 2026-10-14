"""Durable voice intents and account-scoped cached media, without external calls."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from backlot import studio_voices
from backlot.studio import Studio, atomic_private
from backlot.work_catalog import WorkError


@pytest.fixture
def rig(tmp_path, monkeypatch):
    studio = Studio(tmp_path / "projects")
    atomic_private(studio.config_path, {"base_url": "http://127.0.0.1:17894/v2", "api_key": "test-voice-account-one"})
    class Client:
        def __init__(self): self.intents = []; self.downloads = 0; self.lost = True
        def quote(self, *args): return {"id": "clone-quote", "max_charge_micros": "0"}
        def confirm(self, q, maximum):
            self.intents.append({"id": "intent-one"}); return self.intents[-1]
        def resume(self, intent):
            assert intent["id"] == "intent-one"
            if self.lost: self.lost = False; raise OSError("response lost")
            return {"id": "clone-job", "status": "succeeded", "result": {"voice_id": "voice_owned"}}
        def request(self, path, data=None):
            return {"items": [{"id": "voice_owned", "sample_status": "succeeded", "sample_url": "/v2/voices/voice_owned/sample"}]}
        def media(self, path): self.downloads += 1; return b"RIFFcached-audio"
    client = Client(); monkeypatch.setattr(studio, "client", lambda: client)
    return studio, client


def test_lost_confirmation_and_parallel_retries_keep_original_intent(rig):
    studio, client = rig
    operation = studio_voices.quote_clone(studio, {"name": "我的口播", "sample_id": "file-one", "consent": True})
    with pytest.raises(WorkError, match="原任务"):
        studio_voices.confirm(studio, operation["id"], True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: studio_voices.confirm(studio, operation["id"], True), range(4)))
    assert len(client.intents) == 1
    assert all(j["job"]["id"] == "clone-job" and j["voice_id"] == "voice_owned" for j in jobs)
    assert "test-voice-account" not in json.dumps(studio_voices.operations(studio))


def test_changed_account_cannot_confirm_old_quote_or_read_old_cache(rig, monkeypatch):
    studio, client = rig
    operation = studio_voices.quote_clone(studio, {"name": "我的口播", "consent": True})
    first = studio_voices.sample(studio, "voice_owned")
    assert studio_voices.sample(studio, "voice_owned") == first and client.downloads == 1
    atomic_private(studio.config_path, {"base_url": "http://127.0.0.1:17894/v2", "api_key": "test-voice-account-two"})
    assert studio_voices.operations(studio) == []
    with pytest.raises(WorkError): studio_voices.confirm(studio, operation["id"], True)
    monkeypatch.setattr(client, "request", lambda *args: {"items": []})
    with pytest.raises(WorkError): studio_voices.sample(studio, "voice_owned")
    assert client.downloads == 1


def test_library_rejects_path_like_voice_ids_before_local_media_access(rig, monkeypatch):
    studio, client = rig
    monkeypatch.setattr(client, "request", lambda *args: {"items": [{"id": "../../private"}]})
    with pytest.raises(WorkError, match="无效"):
        studio_voices.sample(studio, "../../private")
    assert client.downloads == 0
