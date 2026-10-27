"""Actual receipts, versioned meters, and customer ceiling protection."""
import io
import wave

import pytest

from platform_app import adapters, domain, gateway, providers
from platform_app.runninghub_billing import receipt_cost


def test_real_wallet_receipt_and_coin_package_are_distinct():
    usage = {"consumeMoney": "0.264", "consumeCoins": None, "taskCostTime": "158"}
    r = receipt_cost(usage)
    assert (r["cost_micros"], r["sale_micros"], r["basis"]) == ("264000", "396000", "provider_wallet_cny")
    c = receipt_cost({"consumeCoins": "100"}, package_cny="50", package_coins="18000")
    assert (c["cost_micros"], c["sale_micros"]) == ("277778", "416667")
    with pytest.raises(ValueError): receipt_cost({"consumeCoins": "100"})
    with pytest.raises(ValueError): receipt_cost({"consumeMoney": ".264", "consumeCoins": "100"})


@pytest.mark.parametrize("usage", [{}, {"consumeMoney": "nan"}, {"consumeMoney": -1}, {"consumeMoney": True},
                                 {"consumeMoney": ".2", "thirdPartyConsumeMoney": ".1"}, {"consumeMoney": ".0000001"}])
def test_missing_or_ambiguous_cost_never_becomes_zero(usage):
    with pytest.raises(ValueError): receipt_cost(usage)


def test_wallet_mode_requires_matching_tariff_and_cannot_alter_legacy_model(tmp_path):
    vault = providers.Vault(tmp_path)
    before = dict(vault.models()["haike/avatar"])
    vault.update("runninghub", {"billing_mode": "wallet_receipt", "quote_cost_limit_micros": "1000000"})
    after = vault.models()["haike/avatar"]
    assert before["meters"] == {"tasks": 1} and after["meters"] == {"supplier_micros": 1000000}
    rule = {"costs": {"supplier_micros": "1000000"}, "multiplier": "1.5", "fee_micros": "0",
            "source": "供应商钱包回执", "cost_basis": "CNY实际实扣", "confirmed": True}
    providers.normalize("haike/avatar", rule, after)
    assert providers.calculate("haike/avatar", rule, {"supplier_micros": 264000}, after) == (264000, 396000)
    assert providers.MODELS["haike/avatar"] == before


def test_resume_reads_actual_cost_and_preserves_media_when_cost_missing(tmp_path, monkeypatch):
    vault = providers.Vault(tmp_path)
    vault.update("runninghub", {"api_key": "test-private", "enabled": True, "billing_mode": "wallet_receipt"})
    calls = []
    usage = {"consumeMoney": ".264", "taskCostTime": "158"}
    def fake(url, headers, *args, **kwargs):
        calls.append(url)
        return {"status": "SUCCESS", "usage": usage,
                "results": [{"outputType": "mp4", "url": "https://supplier.test/video.mp4"}]}
    monkeypatch.setattr(adapters, "http", fake)
    a = adapters.Adapter(vault, tmp_path)
    inputs = {"_model_info": vault.models()["haike/avatar"]}
    r = a.execute("haike/avatar", inputs, lambda x: None, upstream_id="existing-task")
    assert r["usage"] == {"supplier_micros": 264000} and len(calls) == 1
    usage.clear()
    with pytest.raises(adapters.ReceiptMissing) as e:
        a.execute("haike/avatar", inputs, lambda x: None, upstream_id="existing-task")
    assert e.value.upstream_id == "existing-task" and e.value.result["video_url"]


def test_actual_wallet_settlement_releases_unused_hold_and_freezes_old_tariff(env):
    from test_commerce import enable, fund, real_quote
    from test_platform import key, submit
    store, _admin, customer, _, _, user, _ = env
    vault = enable(store, "runninghub")
    vault.update("runninghub", {"billing_mode": "wallet_receipt", "quote_cost_limit_micros": "1000000"})
    fund(env); headers, _ = key(customer)
    rule = {"costs": {"supplier_micros": "1000000"}, "multiplier": "1.5", "fee_micros": "0",
            "source": "供应商任务钱包回执", "cost_basis": "CNY实扣，无附加费", "confirmed": True}
    providers.publish(store, user["id"], "haike/avatar", rule, vault)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(24000); f.writeframes(b"\0\0" * 24000)
    audio = gateway.upload(store, user["id"], "audio", buffer.getvalue())
    image = gateway.upload(store, user["id"], "image", b"\x89PNG\r\n\x1a\n")
    q = real_quote(customer, headers, "haike/avatar", {"audio_file": audio["id"], "image_file": image["id"]})
    assert q["max_charge_micros"] == "1500000"
    job = submit(customer, headers, q).json()
    # Later operator changes cannot reinterpret an accepted quote or receipt.
    vault.update("runninghub", {"billing_mode": "task"})
    class Recorded:
        def execute(self, model, inputs, checkpoint, upstream_id):
            assert inputs["_model_info"]["billing_mode"] == "wallet_receipt"
            assert inputs["_provider_config"]["billing_mode"] == "wallet_receipt"
            return {"usage": {"supplier_micros": 264000}, "result": {"video_url": "https://supplier.test/recorded.mp4"}, "upstream_id": "recorded-task"}
    gateway.execute_one(store, Recorded())
    bill = gateway.get_job(store, user, job["id"], admin=True)
    assert bill["charged_micros"] == "396000" and bill["reserved_micros"] == "0"
    assert bill["billing"]["released_micros"] == "1104000"
    assert bill["estimated_cost_micros"] == "264000" and bill["cost_status"] == "receipt_confirmed"
    assert domain.verify_ledger(store)["ok"]


def test_pexels_has_explicit_user_agent_and_bare_key(tmp_path, monkeypatch):
    vault = providers.Vault(tmp_path); vault.update("pexels", {"api_key": "test-private", "enabled": True})
    seen = []
    def fake(url, headers, **kw):
        seen.append(headers); return {"videos": [{"id": 1}]}
    monkeypatch.setattr(adapters, "http", fake)
    r = adapters.Adapter(vault, tmp_path).execute("haike/assets", {"query": "office", "per_page": 1, "media": "videos"}, lambda _: None)
    assert seen[0]["User-Agent"] == "HaikeVideo/1.0" and seen[0]["Authorization"] == "test-private"
    assert r["result"]["items"] == [{"id": 1}]
