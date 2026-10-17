"""Local-only SDK intents and conservative application budgets; fake suppliers only."""

import base64
import io
import json
import wave
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from backlot import ai_text
from backlot import studio_services as services
from backlot.studio_internal_gateway import DirectAdapter, InternalClient, _platform
from backlot.work_catalog import WorkError


class Audio:
    def __init__(self, directory):
        self.path = directory / "preview.wav"
        self.path.write_bytes(b"RIFF-fake-audio")
        self.jobs, self.submissions = {}, 0
        self.account = "relay_" + "a" * 64
        self.current_account = self.account
        self.directory = directory / "aud-a"

    def verify_scope(self):
        if self.account != self.current_account:
            raise WorkError("当前海客账号已变化", "conflict")
        return self.account

    def voices(self):
        return {
            "items": [{"id": "pub_longanyang", "available": True}],
            "preferences": {"voice_id": "pub_longanyang"},
        }

    def quote(self, data):
        assert data["input"]["purpose"] == "production"
        return {
            "id": "iq_" + "1" * 32,
            "operation_id": "call_" + "1" * 32,
            "model": data["model"],
            "max_charge_micros": "400",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }

    def operation(self, operation):
        if operation not in self.jobs:
            raise WorkError("missing", "missing")
        return self.jobs[operation]

    def submit(self, data):
        self.submissions += 1
        self.jobs[data["operation_id"]] = {
            "id": data["operation_id"],
            "status": "succeeded",
            "result": {"audio_url": "/internal/audio"},
        }
        return self.jobs[data["operation_id"]]

    def job(self, operation):
        return self.operation(operation)

    def preview(self, operation):
        return self.path


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_text, "CONFIG_ROOT", tmp_path)
    for name in services.ENV_WHITELIST:
        monkeypatch.delenv(name, raising=False)
    for name, value in {
        "OPENAI_API_KEY": "fake-internal-provider-secret",
        "OPENAI_BASE_URL": "https://example.test/v1",
        "OPENAI_TEXT_MODEL": "frozen-test-model",
        "RUNNINGHUB_API_KEY": "fake-rh-secret",
        "TENCENT_SECRET_ID": "fake-tencent-id",
        "TENCENT_SECRET_KEY": "fake-tencent-secret",
    }.items():
        monkeypatch.setenv(name, value)
    studio = SimpleNamespace(
        private=tmp_path / ".backlot",
        internal_admin_enabled=True,
        internal_bind_host="127.0.0.1",
    )
    studio.private.mkdir()
    (studio.private / "service-mode.json").write_text('{"mode":"internal"}')
    services.update_budget_policy(
        studio,
        {
            "per_call_micros": {
                "haike/text": "10000",
                "haike/avatar": "20000",
                "haike/tencent-asr": "10000",
            },
            "daily_limit_micros": "100000",
        },
    )
    return studio, Audio(tmp_path)


def test_audio_sdk_uses_one_audio_center_operation_and_returns_production_audio(local):
    studio, audio = local
    client = InternalClient(studio, audio_center=audio)
    quote = client.quote(
        "haike/internal-tts", {"voice_id": "pub_longanyang", "text": "你好"}
    )
    intent = client.confirm(quote, 400, "call_" + "2" * 32)
    assert audio.submissions == 0
    first = client.resume(intent)
    assert base64.b64decode(first["result"]["audio_base64"]) == audio.path.read_bytes()
    assert client.resume(intent)["id"] == quote["operation_id"]
    assert audio.submissions == 1
    summary = client.request("/account/summary")
    assert (
        summary["available_micros"] is None and summary["relay_authenticated"] is False
    )
    assert quote["cloud_billing"] is False


def test_unknown_sync_call_is_persisted_and_never_resubmitted_after_restart(local):
    studio, audio = local
    calls = []
    adapters = _platform()[0]

    class Supplier:
        def execute(self, *args):
            calls.append(1)
            raise adapters.Uncertain()

    client = InternalClient(studio, adapter=Supplier(), audio_center=audio)
    quote = client.quote(
        "haike/text",
        {"messages": [{"role": "user", "content": "你好"}], "max_output_tokens": 10},
    )
    intent = client.confirm(quote, 10000)
    assert not calls
    assert client.resume(intent)["status"] == "submission_unknown"
    restarted = InternalClient(studio, adapter=Supplier(), audio_center=audio)
    assert restarted.resume(intent)["status"] == "submission_unknown" and calls == [1]
    for path in (studio.private / "internal-services").rglob("*.json"):
        assert "fake-internal-provider-secret" not in path.read_text(encoding="utf-8")


def upload_inputs(client):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\0\0" * 16000)
    audio = client.studio.private / "raw.wav"
    image = client.studio.private / "raw.png"
    audio.write_bytes(buffer.getvalue())
    image.write_bytes(b"\x89PNG\r\n\x1a\nimage")
    return {
        "audio_file": client.upload(audio, "audio")["id"],
        "image_file": client.upload(image, "image")["id"],
    }


def test_async_checkpoint_is_only_queried_and_configuration_is_frozen(
    local, monkeypatch
):
    studio, audio = local
    calls = []
    adapters = _platform()[0]

    class Supplier:
        def execute(self, model, inputs, checkpoint, upstream_id):
            calls.append(upstream_id)
            if not upstream_id:
                checkpoint("original-task")
                raise adapters.Uncertain()
            return {
                "usage": {"tasks": 1},
                "result": {"video_url": "https://example.test/original.mp4"},
            }

    client = InternalClient(studio, adapter=Supplier(), audio_center=audio)
    quote = client.quote("haike/avatar", upload_inputs(client))
    intent = client.confirm(quote, 20000)
    assert client.resume(intent)["status"] == "processing"
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "changed-fake-key")
    with pytest.raises(WorkError) as error:
        client.resume(intent)
    assert error.value.code == "conflict" and calls == [None]
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "fake-rh-secret")
    assert client.resume(intent)["status"] == "succeeded"
    assert calls == [None, "original-task"]


def test_unknown_procurement_requires_explicit_budget_and_concurrent_daily_guard(local):
    studio, audio = local
    client = InternalClient(studio, audio_center=audio)
    services.update_budget_policy(
        studio, {"per_call_micros": {}, "daily_limit_micros": "10000"}
    )
    inputs = {
        "messages": [{"role": "user", "content": "test"}],
        "max_output_tokens": 10,
    }
    with pytest.raises(WorkError):
        client.quote("haike/text", inputs)
    services.update_budget_policy(
        studio,
        {"per_call_micros": {"haike/text": "6000"}, "daily_limit_micros": "10000"},
    )
    calls = []

    class Supplier:
        def execute(self, *args):
            calls.append(1)
            return {
                "result": {"choices": []},
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }

    client = InternalClient(studio, adapter=Supplier(), audio_center=audio)
    intents = [
        client.confirm(client.quote("haike/text", inputs, str(index)), 6000)
        for index in range(2)
    ]

    def run(intent):
        try:
            return client.resume(intent)["status"]
        except WorkError as error:
            return error.code

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(run, intents))
    assert sorted(outcomes) == ["budget_limit", "succeeded"] and len(calls) == 1


def test_capabilities_and_quotes_require_daily_budget_and_keep_names_generic(local):
    studio, audio = local
    client = InternalClient(studio, audio_center=audio)
    policy_path = studio.private / "internal-services" / "budget-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["daily_limit_micros"] = "0"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    capabilities = client.request("/capabilities")["items"]
    assert {item["status"] for item in capabilities} == {
        "budget_required",
        "unconfigured",
    }
    assert all(
        "Tencent" not in item["name"] and "RunningHub" not in item["name"]
        for item in capabilities
    )
    with pytest.raises(WorkError, match="每日预算"):
        client.quote("haike/text", {"messages": [{"role": "user", "content": "test"}]})


def test_configured_http_text_relay_is_available_and_quotable_without_execution(local, monkeypatch):
    studio, audio = local
    monkeypatch.setenv("OPENAI_BASE_URL", "http://relay.example.test/v1")

    class NoExecution:
        def execute(self, *args):
            pytest.fail("A capability or quote must not execute a supplier request")

    client = InternalClient(studio, adapter=NoExecution(), audio_center=audio)
    capability = next(item for item in client.request("/capabilities")["items"] if item["model"] == "haike/text")
    assert capability["status"] == "available"
    quote = client.quote("haike/text", {"messages": [{"role": "user", "content": "fixture"}]})
    assert quote["model"] == "haike/text" and quote["max_charge_micros"] == "10000"
    assert "fake-internal-provider-secret" not in json.dumps({"capability": capability, "quote": quote})


@pytest.mark.parametrize("endpoint", [
    "http://user:fake-private@relay.example.test/v1",
    "http://relay.example.test/v1?key=fake-private",
    "http://relay.example.test/v1#fake-private",
    "http://relay.example.test:invalid/v1",
    "ftp://relay.example.test/v1",
])
def test_invalid_text_relay_is_unconfigured_and_cannot_quote(local, monkeypatch, endpoint):
    studio, audio = local
    monkeypatch.setenv("OPENAI_BASE_URL", endpoint)
    client = InternalClient(studio, audio_center=audio)
    capability = next(item for item in client.request("/capabilities")["items"] if item["model"] == "haike/text")
    assert capability["status"] == "unconfigured"
    with pytest.raises(WorkError) as error:
        client.quote("haike/text", {"messages": [{"role": "user", "content": "fixture"}]})
    assert "fake-private" not in str(error.value)
    assert not list((client.directory / "quotes").glob("*.json"))


def test_avatar_does_not_inherit_text_relay_http_permission(local, monkeypatch):
    studio, audio = local
    monkeypatch.setenv("RUNNINGHUB_BASE_URL", "http://supplier.example.test")
    client = InternalClient(studio, audio_center=audio)
    capability = next(item for item in client.request("/capabilities")["items"] if item["model"] == "haike/avatar")
    assert capability["status"] == "unconfigured"
    with pytest.raises(WorkError, match="HTTPS"):
        client.quote("haike/avatar", {})


def test_clone_sdk_rejects_traversal_before_reading_any_file(local):
    studio, audio = local
    client = InternalClient(studio, audio_center=audio)
    with pytest.raises(WorkError, match="文件编号"):
        client.quote("haike/voice-clone", {"audio_file": "file_../../outside.wav"})


def test_audio_only_sdk_cannot_recover_generic_intents_or_take_over_gateway(local):
    studio, audio = local
    full = InternalClient(studio, audio_center=audio)
    generic = full.confirm(
        full.quote("haike/text", {"messages": [{"role": "user", "content": "test"}]}),
        10000,
    )
    (studio.private / "service-mode.json").write_text(
        '{"mode":"gateway","audio_mode":"internal"}'
    )
    with pytest.raises(WorkError):
        InternalClient(studio, audio_center=audio)
    with pytest.raises(WorkError, match="当前账号目录"):
        InternalClient(
            studio, audio_only=True, audio_center=audio, state_dir=full.state_dir
        )
    client = InternalClient(studio, audio_only=True, audio_center=audio)
    for action in (
        lambda: client.upload("unused.wav", "audio"),
        lambda: client.quote("haike/text", {}),
        lambda: client.request("/account/summary"),
        lambda: client.request("/capabilities"),
    ):
        with pytest.raises(WorkError) as error:
            action()
        assert error.value.code == "forbidden"
    with pytest.raises(WorkError) as error:
        client.resume(generic)
    assert error.value.code == "missing"
    quote = client.quote(
        "haike/internal-tts", {"voice_id": "pub_longanyang", "text": "test"}
    )
    assert client.resume(client.confirm(quote, 400))["status"] == "succeeded"


def test_mixed_sdk_private_quotes_and_intents_are_account_scoped(local):
    studio, audio_a = local
    (studio.private / "service-mode.json").write_text(
        '{"mode":"gateway","audio_mode":"internal"}'
    )
    client_a = InternalClient(studio, audio_only=True, audio_center=audio_a)
    quote_a = client_a.quote(
        "haike/internal-tts", {"voice_id": "pub_longanyang", "text": "private A"}
    )
    intent_a = client_a.confirm(quote_a, 400)
    audio_a.current_account = "relay_" + "b" * 64
    for action in (
        lambda: client_a.resume(intent_a),
        lambda: client_a.confirm(quote_a, 400),
        lambda: client_a.request(
            "/quotes/" + quote_a["id"] + "/renew", {"confirmed": True}
        ),
    ):
        with pytest.raises(WorkError) as error:
            action()
        assert error.value.code == "conflict"
    audio_b = Audio(studio.private)
    audio_b.account = audio_b.current_account = "relay_" + "b" * 64
    audio_b.directory = studio.private / "aud-b"
    client_b = InternalClient(studio, audio_only=True, audio_center=audio_b)
    assert (
        client_b.path == client_a.path
    )  # Budget totals contain no private quote payload.
    assert (
        client_b.directory != client_a.directory
        and client_b.state_dir != client_a.state_dir
    )
    with pytest.raises(WorkError) as error:
        client_b.resume(intent_a)
    assert (
        error.value.code == "missing"
        and not audio_a.submissions
        and not audio_b.submissions
    )


def test_internal_client_is_not_enabled_by_admin_flag_alone(local):
    studio, audio = local
    (studio.private / "service-mode.json").write_text('{"mode":"gateway"}')
    with pytest.raises(WorkError):
        InternalClient(studio, audio_center=audio)


def test_tencent_existing_tc3_contract_checkpoints_then_only_queries(
    local, monkeypatch
):
    import requests

    studio, audio = local
    client = InternalClient(studio, audio_center=audio)
    files = upload_inputs(client)
    calls = []

    def post(url, headers, data, timeout):
        calls.append(headers["X-TC-Action"])
        if headers["X-TC-Action"] == "CreateRecTask":
            payload = json.loads(data)
            assert base64.b64decode(payload["Data"]).startswith(b"RIFF")
            response = {"Data": {"TaskId": 123}}
        else:
            assert json.loads(data) == {"TaskId": 123}
            response = {
                "Data": {
                    "Status": 1 if len(calls) == 2 else 2,
                    "AudioDuration": 1.0,
                    "Result": "[00:00:00.000,00:00:01.000]你好",
                }
            }
        return SimpleNamespace(json=lambda: {"Response": response})

    monkeypatch.setattr(requests, "post", post)
    info, config = client._model("haike/tencent-asr")
    inputs = {
        "audio_file": files["audio_file"],
        "_model_info": info,
        "_runtime_provider_config": config,
    }
    adapter = DirectAdapter(client.vault, client.directory / "files")
    checkpointed = []
    assert adapter.execute("haike/tencent-asr", inputs, checkpointed.append)["pending"]
    assert adapter.execute("haike/tencent-asr", inputs, checkpointed.append, "123")[
        "usage"
    ] == {"seconds": 1}
    assert checkpointed == ["123"] and calls == [
        "CreateRecTask",
        "DescribeTaskStatus",
        "DescribeTaskStatus",
    ]
