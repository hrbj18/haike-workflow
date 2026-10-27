"""Isolated account/financial contracts; no real supplier call or production database."""

import io
import json
import logging
import ssl
import urllib.error
import wave
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from test_commerce import enable, fund, real_quote
from test_platform import key, submit

from gateway_client import GatewayError, HaikeClient
from platform_app import (
    adapters,
    bailian_voices,
    domain,
    gateway,
    voice_sources,
    voices,
)
from platform_app.app import create_app


def tariff(admin, model, meter="characters", cost="1000000"):
    response = admin.post(
        "/admin/v1/gateway-prices",
        json={
            "model": model,
            "rule": {
                "costs": {meter: cost},
                "multiplier": "1.5",
                "fee_micros": "0",
                "source": "离线测试采购凭证",
                "cost_basis": "假供应商合同测试",
                "confirmed": True,
            },
        },
    )
    assert response.status_code == 200, response.text


def audio(store, user_id):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\0\0" * 160000)
    return gateway.upload(store, user_id, "audio", buffer.getvalue())["id"]


def setup_clone(env):
    store, admin, customer, _, _, user, _ = env
    vault = enable(store)
    vault.update(
        "bailian",
        {
            "oss_endpoint": "https://oss-cn-beijing.aliyuncs.com",
            "oss_bucket": "test-private-voices",
            "oss_access_key_id": "fake-oss-id",
            "oss_access_key_secret": "fake-oss-secret",
        },
    )
    tariff(admin, voices.CLONE_MODEL, "voices", "10000")
    fund(env)
    headers, _ = key(customer)
    inputs = {
        "name": "我的声音",
        "audio_file": audio(store, user["id"]),
        "consent": True,
    }
    return vault, headers, inputs


class Bucket:
    def __init__(self):
        self.puts, self.deleted = [], []

    def put_object_from_file(self, name, path, headers):
        self.puts.append((name, path, headers))

    def sign_url(self, method, name, expiry, slash_safe):
        return (
            "https://test-private-voices.oss-cn-beijing.aliyuncs.com/"
            + name
            + "?signature=fake-private"
        )

    def delete_object(self, name):
        self.deleted.append(name)


def test_public_candidates_and_per_voice_account_preferences_shared_across_keys(env):
    store, admin, client, outsider, _, user, _ = env
    enable(store)
    headers, _ = key(client)
    other_headers, _ = key(outsider)
    second_headers, _ = key(client)
    initial = client.get("/v2/voices", headers=headers).json()
    assert len(initial["items"]) == 6
    assert [v["gender"] for v in initial["items"]].count("male") == 3
    assert all(
        v["status"] == "blocked" and v["verification"] == "candidate_unverified"
        for v in initial["items"]
    )
    assert all(
        v["compatible_models"] == ["cosyvoice-v3-flash"] for v in initial["items"]
    )
    assert "api_key" not in json.dumps(initial)
    image = gateway.upload(
        store, user["id"], "image", b"\x89PNG\r\n\x1a\nprivate-test-image"
    )["id"]
    selected = initial["items"][0]["id"]
    response = client.put(
        "/v2/voices/" + selected + "/preferences",
        headers=headers,
        json={"speech_rate": 1.25, "image_file_id": image},
    )
    assert response.status_code == 200, response.text
    assert (
        client.put(
            "/v2/voice-preferences", headers=headers, json={"voice_id": selected}
        ).status_code
        == 200
    )
    same = client.get("/v2/voices", headers=second_headers).json()
    assert same["preferences"]["voice_id"] == selected
    assert same["items"][0]["preferences"] == {
        "speech_rate": 1.25,
        "image_file_id": image,
    }
    assert (
        outsider.get("/v2/voices", headers=other_headers).json()["items"][0][
            "preferences"
        ]["image_file_id"]
        is None
    )
    assert (
        outsider.put(
            "/v2/voices/" + selected + "/preferences",
            headers=other_headers,
            json={"image_file_id": image},
        ).status_code
        == 404
    )
    assert outsider.get("/v2/files/" + image, headers=other_headers).status_code == 404
    media = client.get("/v2/files/" + image, headers=second_headers)
    assert media.status_code == 200 and media.content.endswith(b"private-test-image")
    assert "no-store" in media.headers["cache-control"]
    assert (
        client.get("/v2/account/summary", headers=headers).json()["account_id"]
        == user["id"]
    )
    tariff(admin, voices.PUBLIC_MODEL)
    opened = client.get("/v2/voices", headers=headers).json()
    assert all(
        v["available"] and v["verification"] == "candidate_unverified"
        for v in opened["items"]
    )


def test_tts_freezes_voice_rate_model_and_price_at_quote(env, monkeypatch):
    from dashscope.api_entities.dashscope_response import SpeechSynthesisResponse
    from dashscope.audio.http_tts.http_speech_synthesizer import HttpSpeechSynthesizer

    store, admin, client, _, _, user, _ = env
    vault = enable(store)
    tariff(admin, voices.PUBLIC_MODEL)
    fund(env)
    headers, _ = key(client)
    selected = "pub_longanlang_v3"
    client.put(
        "/v2/voices/" + selected + "/preferences",
        headers=headers,
        json={"speech_rate": 1.25},
    )
    q = real_quote(
        client, headers, voices.PUBLIC_MODEL, {"text": "你好", "voice_id": selected}
    )
    assert q["voice_selection"]["speech_rate"] == 1.25
    assert q["voice_selection"]["upstream_model"] == "cosyvoice-v3-flash"
    assert q["max_charge_micros"] == "600"
    client.put(
        "/v2/voices/" + selected + "/preferences",
        headers=headers,
        json={"speech_rate": 0.8},
    )
    tariff(admin, voices.PUBLIC_MODEL, cost="2000000")
    vault.update("bailian", {"voice": "different-global-voice"})
    called = []

    def synthesize(**kwargs):
        called.append(kwargs)
        return SpeechSynthesisResponse(
            status_code=200,
            usage={"characters": 4},
            output={
                "audio": {"url": "https://example.test/audio.wav", "id": "test-audio"}
            },
        )

    monkeypatch.setattr(HttpSpeechSynthesizer, "_http_call", synthesize)
    job = submit(client, headers, q).json()
    assert gateway.execute_one(
        store, adapters.Adapter(vault, store.path.parent / "files")
    )
    bill = gateway.get_job(store, user, job["id"])
    assert bill["status"] == "succeeded" and bill["charged_micros"] == "600"
    body = called[0]["body"]
    assert (body["model"], body["input"]["voice"], body["input"]["rate"]) == (
        "cosyvoice-v3-flash",
        "longanlang_v3",
        1.25,
    )
    assert "speech_rate" not in body["input"] and body["input"]["enable_ssml"] is False
    assert bill["voice_selection"] == q["voice_selection"]
    assert "private-test-provider-secret" not in json.dumps(bill)
    assert domain.verify_ledger(store)["ok"]


def test_clone_quote_is_blocked_without_confirmed_tariff_and_private_storage(env):
    store, admin, client, _, _, user, _ = env
    enable(store)
    headers, _ = key(client)
    inputs = {"name": "声音", "audio_file": audio(store, user["id"]), "consent": True}
    assert (
        client.post(
            "/v2/quotes",
            headers=headers,
            json={"model": voices.CLONE_MODEL, "input": inputs},
        ).status_code
        == 409
    )
    tariff(admin, voices.CLONE_MODEL, "voices", "0")
    assert (
        client.post(
            "/v2/quotes",
            headers=headers,
            json={"model": voices.CLONE_MODEL, "input": inputs},
        ).status_code
        == 409
    )
    assert not gateway.list_jobs(store, user)


def test_clone_recovery_owns_voice_and_delete_keeps_frozen_synthesis(env, monkeypatch):
    from dashscope.audio.http_tts.http_speech_synthesizer import HttpSpeechSynthesizer

    store, _, client, outsider, _, user, _ = env
    vault, headers, inputs = setup_clone(env)
    bucket, requests = Bucket(), []
    monkeypatch.setattr(bailian_voices, "storage", lambda config: bucket)
    voice_id = "cosyvoice-v3.5-flash-haike-offline-voice"

    def fake(url, request_headers, body):
        action = body["input"]["action"]
        requests.append(action)
        if action == "create_voice":
            assert body["input"]["target_model"] == "cosyvoice-v3.5-flash"
            return {"output": {"voice_id": voice_id}}
        return {
            "output": {
                "status": "PROCESSING" if len(requests) == 2 else "OK",
                "target_model": "cosyvoice-v3.5-flash",
            }
        }

    monkeypatch.setattr(adapters, "http", fake)
    q = real_quote(client, headers, voices.CLONE_MODEL, inputs)
    assert q["max_charge_micros"] == "15000"
    job = submit(client, headers, q).json()
    second_headers, _ = key(client)
    assert submit(client, second_headers, q).json()["id"] == job["id"]
    adapter = adapters.Adapter(vault, store.path.parent / "files")
    assert gateway.execute_one(store, adapter)
    assert gateway.get_job(store, user, job["id"])["status"] == "running"
    gateway.recover(store)
    assert gateway.execute_one(store, adapter)
    result = gateway.get_job(store, user, job["id"])
    assert result["status"] == "succeeded" and result["charged_micros"] == "15000"
    assert (
        requests == ["create_voice", "query_voice", "query_voice"]
        and len(bucket.puts) == 1
    )
    assert bucket.puts[0][2] == {"x-oss-object-acl": "private"} and bucket.deleted
    local_voice = result["result"]["voice"]["id"]
    assert voice_id not in json.dumps(result)
    assert "fake-private" not in json.dumps(result)
    others, _ = key(outsider)
    assert all(
        v["id"] != local_voice
        for v in outsider.get("/v2/voices", headers=others).json()["items"]
    )
    assert (
        outsider.put(
            "/v2/voices/" + local_voice + "/preferences",
            headers=others,
            json={"speech_rate": 1.2},
        ).status_code
        == 404
    )
    assert (
        outsider.delete("/v2/voices/" + local_voice, headers=others).status_code == 404
    )
    bad = outsider.post(
        "/v2/quotes",
        headers=others,
        json={
            "model": voices.PRIVATE_MODEL,
            "input": {"text": "你好", "voice_id": local_voice},
        },
    )
    assert bad.status_code == 404
    tts_quote = real_quote(
        client, headers, voices.PRIVATE_MODEL, {"text": "你好", "voice_id": local_voice}
    )
    tts_job = submit(
        client, headers, tts_quote, intent="tts-existing", idem="tts-existing"
    ).json()
    assert (
        client.delete("/v2/voices/" + local_voice, headers=headers).status_code == 200
    )
    blocked = client.post(
        "/v2/quotes",
        headers=headers,
        json={
            "model": voices.PRIVATE_MODEL,
            "input": {"text": "你好", "voice_id": local_voice},
        },
    )
    assert blocked.status_code == 409
    captured = []
    monkeypatch.setattr(
        HttpSpeechSynthesizer,
        "call",
        lambda **kwargs: (
            captured.append(kwargs)
            or SimpleNamespace(
                status_code=200,
                usage={"characters": 4},
                audio_url="https://example.test/audio.wav",
                audio_id="test-audio",
            )
        ),
    )
    assert gateway.execute_one(store, adapter)
    assert gateway.get_job(store, user, tts_job["id"])["status"] == "succeeded"
    assert captured[0]["voice"] == voice_id
    assert domain.verify_ledger(store)["ok"]


@pytest.mark.parametrize("rejected", [False, True])
def test_clone_unknown_never_resubmits_and_rejection_releases_hold(
    env, monkeypatch, rejected
):
    store, _, client, _, _, user, _ = env
    vault, headers, inputs = setup_clone(env)
    monkeypatch.setattr(bailian_voices, "storage", lambda config: Bucket())
    calls = []

    def fake(*args):
        calls.append(1)
        raise adapters.Rejected() if rejected else adapters.Uncertain()

    monkeypatch.setattr(adapters, "http", fake)
    job = submit(
        client, headers, real_quote(client, headers, voices.CLONE_MODEL, inputs)
    ).json()
    adapter = adapters.Adapter(vault, store.path.parent / "files")
    assert gateway.execute_one(store, adapter)
    result = gateway.get_job(store, user, job["id"])
    assert result["status"] == ("failed" if rejected else "submission_unknown")
    assert result["reserved_micros"] == ("0" if rejected else "15000")
    gateway.recover(store)
    assert not gateway.execute_one(store, adapter) and len(calls) == 1
    assert domain.verify_ledger(store)["ok"]


def test_sdk_methods_binary_and_sanitized_error(tmp_path, monkeypatch):
    class FakeResponse(io.BytesIO):
        pass

    seen = []

    class Opener:
        def open(self, request, timeout):
            seen.append(request)
            if request.full_url.endswith("missing"):
                raise urllib.error.HTTPError(
                    request.full_url,
                    404,
                    "missing",
                    {},
                    io.BytesIO(
                        b'{"error":{"code":"not_found","message":"missing secret-test"}}'
                    ),
                )
            return FakeResponse(
                b"image-bytes" if request.get_method() == "GET" else b'{"ok":true}'
            )

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    sdk = HaikeClient("http://127.0.0.1/v2", "secret-test", tmp_path)
    assert sdk.request(
        "/voices/id/preferences", {"speech_rate": 1.1}, method="PUT"
    ) == {"ok": True}
    assert sdk.request("/files/id", response_bytes=True) == b"image-bytes"
    assert sdk.request("/voices/id", method="DELETE") == {"ok": True}
    assert [r.get_method() for r in seen] == ["PUT", "GET", "DELETE"]
    with pytest.raises(GatewayError) as error:
        sdk.request("/missing")
    assert error.value.status == 404 and error.value.code == "not_found"
    assert "secret-test" not in str(error.value)
    for path in (
        "//outside.test",
        "https://outside.test",
        "relative",
        "/path#fragment",
        "/\\outside",
    ):
        with pytest.raises(GatewayError):
            sdk.request(path)


def test_unknown_clone_verified_receipt_resumes_query_without_second_creation(
    env, monkeypatch
):
    store, admin, client, _, _, user, _ = env
    vault, headers, inputs = setup_clone(env)
    monkeypatch.setattr(bailian_voices, "storage", lambda config: Bucket())
    operations = []

    def unknown(*args):
        operations.append("create")
        raise adapters.Uncertain()

    monkeypatch.setattr(adapters, "http", unknown)
    quote = real_quote(client, headers, voices.CLONE_MODEL, inputs)
    job = submit(client, headers, quote).json()
    adapter = adapters.Adapter(vault, store.path.parent / "files")
    gateway.execute_one(store, adapter)
    endpoint = "/admin/v1/gateway-jobs/" + job["id"] + "/voice-receipt"
    receipt = {
        "upstream_voice_id": "cosyvoice-v3.5-flash-haike-recovered",
        "evidence": "假供应商控制台核对的原创建凭证",
    }
    assert client.post(endpoint, json=receipt).status_code == 403
    assert (
        admin.post(
            endpoint, json={**receipt, "upstream_voice_id": "cosyvoice-v3-flash-wrong"}
        ).status_code
        == 422
    )
    assert admin.post(endpoint, json=receipt).json()["recovery"] == "query_only"
    assert admin.post(endpoint, json=receipt).status_code == 409

    def query(url, request_headers, body):
        operations.append(body["input"]["action"])
        assert body["input"] == {
            "action": "query_voice",
            "voice_id": receipt["upstream_voice_id"],
        }
        return {"output": {"status": "OK", "target_model": "cosyvoice-v3.5-flash"}}

    monkeypatch.setattr(adapters, "http", query)
    gateway.execute_one(store, adapter)
    result = gateway.get_job(store, user, job["id"])
    assert (
        result["status"] == "succeeded"
        and result["charged_micros"] == quote["max_charge_micros"]
    )
    assert operations == ["create", "query_voice"] and domain.verify_ledger(store)["ok"]


@pytest.mark.parametrize("rate", [0.49, 2.01, True, "1.2"])
def test_invalid_voice_speed_cannot_quote_or_reserve(env, rate):
    store, admin, client, _, _, user, _ = env
    enable(store)
    tariff(admin, voices.PUBLIC_MODEL)
    headers, _ = key(client)
    response = client.post(
        "/v2/quotes",
        headers=headers,
        json={
            "model": voices.PUBLIC_MODEL,
            "input": {
                "text": "你好",
                "voice_id": "pub_longanyang",
                "speech_rate": rate,
            },
        },
    )
    assert response.status_code == 422
    assert not gateway.list_jobs(store, user)


def test_clone_consent_foreign_audio_and_admin_secret_boundary(env):
    _store, admin, client, outsider, _, _, _ = env
    vault, headers, inputs = setup_clone(env)
    for changed in (
        {**inputs, "consent": False},
        {**inputs, "voice_id": "arbitrary-upstream"},
    ):
        assert (
            client.post(
                "/v2/quotes",
                headers=headers,
                json={"model": voices.CLONE_MODEL, "input": changed},
            ).status_code
            == 422
        )
    other_headers, _ = key(outsider)
    assert (
        outsider.post(
            "/v2/quotes",
            headers=other_headers,
            json={"model": voices.CLONE_MODEL, "input": inputs},
        ).status_code
        == 404
    )
    assert "fake-oss-secret" not in json.dumps(vault.public())
    assert "fake-oss-id" not in json.dumps(vault.public())
    assert "private-test-provider-secret" not in admin.get("/admin/v1/providers").text


def test_signed_source_staging_requires_no_oss_and_only_serves_accepted_job(
    env, monkeypatch
):
    store, admin, customer, _, _, user, _ = env
    vault = enable(store)
    tariff(admin, voices.CLONE_MODEL, "voices", "10000")
    fund(env)
    headers, _ = key(customer)
    file_id = audio(store, user["id"])
    origin = "https://gateway.example.test"
    app = create_app(
        store.path, worker_enabled=False, testing=True, public_origin=origin
    )
    calls, sources = [], []
    monkeypatch.setattr(
        bailian_voices,
        "storage",
        lambda config: pytest.fail("signed mode must not access OSS"),
    )
    with TestClient(app, base_url=origin) as cloud:
        q = real_quote(
            cloud,
            headers,
            voices.CLONE_MODEL,
            {"name": "免OSS私人音色", "audio_file": file_id, "consent": True},
        )
        cloud_store = app.state.store
        # Even a correctly signed reference cannot authorize a nonexistent/unaccepted job.
        expiry = int(voice_sources.time.time()) + 600
        fake_job = "gj_" + "0" * 24
        fake_token = voice_sources.signature(
            voice_sources.secret(cloud_store), fake_job, file_id, expiry
        )
        assert (
            cloud.get(
                voice_sources.PREFIX + fake_job,
                params={"expires": expiry, "signature": fake_token},
            ).status_code
            == 404
        )
        assert cloud.get("/v2/files/" + file_id).status_code == 401

        def fake(url, request_headers, body):
            action = body["input"]["action"]
            calls.append(action)
            if action == "create_voice":
                source = body["input"]["url"]
                sources.append(source)
                assert source.startswith(origin + voice_sources.PREFIX)
                fetched = cloud.get(source)  # Supplier receives no platform Key.
                assert fetched.status_code == 200 and fetched.content.startswith(
                    b"RIFF"
                )
                assert fetched.headers["content-type"] == "audio/wav"
                return {"output": {"voice_id": "cosyvoice-v3.5-flash-haike-signed"}}
            return {
                "output": {
                    "status": "PROCESSING" if len(calls) == 2 else "OK",
                    "target_model": "cosyvoice-v3.5-flash",
                }
            }

        monkeypatch.setattr(adapters, "http", fake)
        job = submit(cloud, headers, q).json()
        adapter = adapters.Adapter(vault, store.path.parent / "files")
        assert gateway.execute_one(cloud_store, adapter)
        source = sources[0]
        assert cloud.get(source).status_code == 200
        parts = urlsplit(source)
        query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        assert (
            cloud.get(parts.path, params={**query, "signature": "0" * 64}).status_code
            == 404
        )
        assert (
            cloud.get(
                parts.path, params={**query, "expires": str(int(query["expires"]) + 1)}
            ).status_code
            == 404
        )
        assert (
            cloud.get(source, headers={"Host": "attacker.example.test"}).status_code
            == 403
        )
        assert (
            cloud.get(voice_sources.PREFIX + file_id, params=query).status_code == 404
        )
        with monkeypatch.context() as expiry_patch:
            expiry_patch.setattr(
                voice_sources,
                "time",
                SimpleNamespace(time=lambda: int(query["expires"]) + 1),
            )
            assert cloud.get(source).status_code == 404
        assert gateway.execute_one(cloud_store, adapter)
        assert (
            cloud.get(source).status_code == 404
        )  # Completion revokes before natural expiry.
        result = gateway.get_job(cloud_store, user, job["id"])
        assert result["status"] == "succeeded"
        assert "signature=" not in json.dumps(result)
        with store.read() as db:
            row = db.execute(
                "SELECT input_json,snapshot FROM gateway_quotes WHERE id=?", (q["id"],)
            ).fetchone()
            assert "signature=" not in row["input_json"] + row["snapshot"]
        assert calls == ["create_voice", "query_voice", "query_voice"]
        assert domain.verify_ledger(cloud_store)["ok"]


def test_signed_reference_log_filter_redacts_tokens():
    private = "/v2/voice-sources/gj_test?expires=123&signature=private-token"
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("supplier", "GET", private, "1.1", 200),
        None,
    )
    voice_sources.RedactSourceAccess().filter(record)
    assert "private-token" not in record.getMessage()
    assert "[private-reference]" in record.getMessage()


@pytest.mark.parametrize("wrapped", [True, False])
def test_sdk_certificate_failure_has_structured_admin_remediation(
    tmp_path, monkeypatch, wrapped
):
    class Opener:
        def open(self, request, timeout):
            error = ssl.SSLCertVerificationError(1, "certificate expired secret-test")
            raise urllib.error.URLError(error) if wrapped else error

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    sdk = HaikeClient("https://gateway.example.test/v2", "secret-test", tmp_path)
    with pytest.raises(GatewayError) as error:
        sdk.request("/account/summary")
    assert error.value.code == "tls_certificate_invalid" and error.value.status is None
    assert "管理员" in str(error.value) and "证书" in str(error.value)
    assert "secret-test" not in str(error.value)
