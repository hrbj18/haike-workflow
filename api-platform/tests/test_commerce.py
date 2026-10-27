import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_platform import key, pay, quote, submit

from platform_app import adapters, commerce, domain, gateway, providers
from platform_app.store import Problem


def fund(env, amount="100000000", idem="admin-credit-0001"):
    _, admin, _, _, _, user, _ = env
    result = admin.post(
        "/admin/v1/users/" + user["id"] + "/credits",
        json={"amount_micros": amount, "note": "测试到账凭证"},
        headers={"Idempotency-Key": idem},
    )
    assert result.status_code == 200, result.text
    return result.json()


def enable(store, provider="bailian"):
    vault = providers.Vault(store.path.parent)
    vault.update(
        provider,
        {
            "api_key": "private-test-provider-secret",
            "enabled": True,
            "voice": "test-cloned-voice",
        },
    )
    return vault


def real_quote(client, headers, model="haike/cosyvoice", inputs=None):
    result = client.post(
        "/v2/quotes",
        headers=headers,
        json={
            "model": model,
            "input": inputs or {"text": "海" * 1000},
            "project_ref": "真实网关离线测试",
        },
    )
    assert result.status_code == 200, result.text
    return result.json()


class Success:
    calls = 0

    def execute(self, model, inputs, checkpoint, upstream_id):
        self.calls += 1
        return {
            "usage": {"characters": 2000},  # 1,000 Han characters in this fixture.
            "result": {"audio_url": "https://example.test/test.wav"},
            "upstream_id": "upstream-test-id",
        }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("你好", 4),
        ("中A文123", 8),
        ("中文。", 5),
        ("中 文。", 6),
        ("漢字カナ한글", 8),
        ("𠀀。", 3),
    ],
)
def test_bailian_quote_counts_han_with_official_billing_examples(text, expected):
    assert providers.bailian_tts_characters(text) == expected


def test_real_smoke_tts_receipt_preserves_cost_times_1_5(env):
    store, admin, client, _, _, user, _ = env
    enable(store)
    fund(env)
    headers, _ = key(client)
    text = "海客科技，让创作更简单。一个接口，连接配音、数字人和创作工作流。"
    q = real_quote(client, headers, inputs={"text": text})
    assert q["max_charge_micros"] == "7080"  # Actual upstream receipt: 59 chars.
    assert gateway.clean_input(None, user["id"], "haike/tencent-tts", {"text": text})[
        1
    ] == {"characters": 32}
    job = submit(client, headers, q).json()

    class RecordedReceipt:
        def execute(self, *args):
            return {
                "usage": {"characters": 59},
                "result": {"audio_url": "https://example.test/recorded.wav"},
                "upstream_id": "recorded-smoke-receipt",
            }

    gateway.execute_one(store, RecordedReceipt())
    bill = gateway.get_job(store, user, job["id"])
    assert bill["charged_micros"] == "7080" and bill["reserved_micros"] == "0"
    ops = admin.get("/admin/v1/gateway-jobs").json()["items"][0]
    assert ops["estimated_cost_micros"] == "4720"
    assert ops["estimated_profit_micros"] == "2360"
    assert domain.verify_ledger(store)["ok"]


def test_admin_create_customer_no_session_leak_and_tenant_guards(env):
    store, admin, client, outsider, _, _, _ = env
    before = admin.get("/portal/v1/me").json()
    created = admin.post(
        "/admin/v1/users",
        json={
            "name": "管理员创建客户",
            "email": "new@example.test",
            "password": "User-password-123",
        },
    ).json()
    assert created["role"] == "customer" and created["must_change_password"]
    assert "password" not in created and "password_hash" not in created
    assert admin.get("/portal/v1/me").json() == before
    for path in ["/admin/v1/users", "/admin/v1/providers", "/admin/v1/gateway-models"]:
        assert client.get(path).status_code == outsider.get(path).status_code == 403
    assert client.post("/admin/v1/users", json={}).status_code == 403
    assert (
        admin.post(
            "/admin/v1/users",
            json={
                "name": "重复",
                "email": "new@example.test",
                "password": "User-password-123",
            },
        ).status_code
        == 409
    )
    assert domain.verify_ledger(store)["ok"]


def test_parallel_admin_credit_idempotency_and_immutable_ledger(env):
    store, _, _, _, actor, user, _ = env
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: commerce.credit(
                    store,
                    actor["id"],
                    user["id"],
                    100000000,
                    "入账凭证",
                    "credit-same-001",
                ),
                range(12),
            )
        )
    assert len({r["id"] for r in results}) == 1
    with pytest.raises(Problem, match="同一请求"):
        commerce.credit(
            store, actor["id"], user["id"], 200000000, "入账凭证", "credit-same-001"
        )
    assert (
        domain.wallet(store, user["id"])["commercial_available_micros"] == "100000000"
    )
    assert domain.verify_ledger(store)["ok"]


def test_redeem_preview_binding_replay_concurrency_and_revocation(env):
    store, admin, client, outsider, _actor, user, _other = env
    created = admin.post(
        "/admin/v1/redeem-codes",
        json={
            "amount_micros": "50000000",
            "count": 2,
            "expires_days": 30,
            "batch": "测试批次",
            "bound_user_id": user["id"],
        },
    )
    assert created.status_code == 200, created.text
    code = created.json()["items"][0]
    assert code["code"] not in admin.get("/admin/v1/redeem-codes").text
    assert (
        outsider.post(
            "/portal/v1/redeem-codes/preview", json={"code": code["code"]}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/portal/v1/redeem-codes/preview", json={"code": code["code"]}
        ).json()["amount_micros"]
        == "50000000"
    )
    assert domain.wallet(store, user["id"])["commercial_available_micros"] == "0"
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: commerce.redeem(store, user["id"], code["code"]), range(12)
            )
        )
    assert all(r["redeemed"] for r in results)
    assert domain.wallet(store, user["id"])["commercial_available_micros"] == "50000000"
    second = created.json()["items"][1]
    assert (
        admin.post("/admin/v1/redeem-codes/" + second["id"] + "/revoke").status_code
        == 200
    )
    assert (
        client.post(
            "/portal/v1/redeem-codes/redeem", json={"code": second["code"]}
        ).status_code
        == 409
    )
    with store.read() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM vouchers WHERE kind='redeem_credit'"
            ).fetchone()[0]
            == 1
        )
    assert domain.verify_ledger(store)["ok"]


def test_real_success_one_key_idempotency_price_snapshot_and_privacy(env):
    store, admin, client, outsider, actor, user, _ = env
    vault = enable(store)
    fund(env)
    headers, _created_key = key(client)
    q = real_quote(client, headers)
    assert q["max_charge_micros"] == "240000"
    job = submit(client, headers, q).json()
    assert job["status"] == "queued"
    assert submit(client, headers, q).json()["id"] == job["id"]
    rule = {
        **providers.catalogue(store, vault, True)[1]["rule"],
        "costs": {"characters": "1600000"},
    }
    providers.publish(store, actor["id"], "haike/cosyvoice", rule)
    adapter = Success()
    assert gateway.execute_one(store, adapter)
    assert not gateway.execute_one(store, adapter)
    bill = client.get("/portal/v1/bills/" + job["id"]).json()
    assert (
        bill["charged_micros"] == "240000"
        and bill["price"]["version"] == 1
        and not bill["simulation"]
    )
    assert adapter.calls == 1
    assert outsider.get("/portal/v1/bills/" + job["id"]).status_code == 404
    assert (
        "costs" not in json.dumps(bill)
        and "private-test-provider-secret"
        not in client.get("/portal/v1/catalogue").text
    )
    assert (
        client.get("/v2/account/usage", headers=headers).json()["items"][0]["id"]
        == job["id"]
    )
    assert domain.wallet(store, user["id"])["commercial_available_micros"] == "99760000"
    admin_bill = admin.get("/admin/v1/gateway-jobs").json()["items"][0]
    assert (
        admin_bill["estimated_cost_micros"] == "160000"
        and admin_bill["estimated_profit_micros"] == "80000"
    )
    assert "private-test-provider-secret" not in admin.get("/admin/v1/providers").text
    assert "private-test-provider-secret" not in vault.path.read_text()
    assert domain.verify_ledger(store)["ok"]


def test_mock_funding_cannot_pay_real_and_commercial_cannot_pay_demo(env):
    store, _, client, _, _, _, _ = env
    pay(client)
    enable(store)
    headers, _ = key(client)
    assert (
        submit(client, headers, real_quote(client, headers)).json()["error"]["code"]
        == "commercial_balance_low"
    )
    order = client.post(
        "/portal/v1/recharges",
        json={"amount_fen": 10000},
        headers={"Idempotency-Key": "new-order-0001"},
    ).json()
    assert (
        client.post("/portal/v1/recharges/" + order["id"] + "/mock-confirm").status_code
        == 409
    )
    fund(env)
    with store.write() as db:
        # Existing simulation credits still cannot be conflated with commercial funds.
        db.execute("UPDATE commercial_wallets SET available=200000000")
    assert (
        submit(client, headers, quote(client, headers), idem="demo-other-0001").json()[
            "error"
        ]["code"]
        == "simulation_balance_low"
    )


@pytest.mark.parametrize("outcome", ["rejected", "unknown", "overrun", "incomplete"])
def test_failed_unknown_overrun_and_missing_usage_financial_boundaries(env, outcome):
    store, admin, client, _, _, user, _ = env
    enable(store)
    fund(env)
    headers, _ = key(client)
    q = real_quote(client, headers)
    job = submit(client, headers, q).json()

    class Fake:
        def execute(self, *args):
            if outcome == "rejected":
                raise adapters.Rejected()
            if outcome == "unknown":
                raise RuntimeError("Never leak supplier private-test-provider-secret")
            return {
                "usage": {"characters": 3000} if outcome == "overrun" else {},
                "result": {"receipt": True},
            }

    gateway.execute_one(store, Fake())
    actual = gateway.get_job(store, user, job["id"])
    if outcome == "rejected":
        assert actual["status"] == "failed" and actual["reserved_micros"] == "0"
    elif outcome == "overrun":
        assert actual["charged_micros"] == q["max_charge_micros"]
    else:
        assert (
            actual["status"] == "submission_unknown"
            and actual["reserved_micros"] == q["max_charge_micros"]
        )
        assert not gateway.execute_one(
            store, Fake()
        )  # An ambiguous paid submission is never repeated.
        assert "private-test" not in json.dumps(actual)
        assert (
            admin.post(
                "/admin/v1/gateway-jobs/" + job["id"] + "/reconcile",
                json={
                    "outcome": "failed",
                    "usage": {},
                    "evidence": "供应商核对凭证：没有接受此请求",
                },
            ).status_code
            == 200
        )
    assert domain.verify_ledger(store)["ok"]


def test_receipt_missing_keeps_artifact_and_reconciliation_settles_once(env):
    store, admin, client, _, _, user, _ = env
    enable(store)
    fund(env)
    headers, _ = key(client)
    job = submit(client, headers, real_quote(client, headers)).json()

    class MissingReceipt:
        def execute(self, *args):
            raise adapters.ReceiptMissing(
                "returned-audio-id", {"audio_url": "https://example.test/audio.wav"}
            )

    gateway.execute_one(store, MissingReceipt())
    pending = gateway.get_job(store, user, job["id"])
    assert pending["status"] == "submission_unknown"
    assert pending["result"]["audio_url"] == "https://example.test/audio.wav"
    assert not gateway.execute_one(store, MissingReceipt())
    body = {
        "outcome": "succeeded",
        "usage": {"characters": 1000},
        "evidence": "供应商账单已核对：实际字符数 1000",
    }
    path = "/admin/v1/gateway-jobs/" + job["id"] + "/reconcile"
    settled = admin.post(path, json=body)
    assert settled.status_code == 200
    assert settled.json()["charged_micros"] == "120000"
    assert settled.json()["result"]["audio_url"] == pending["result"]["audio_url"]
    assert admin.post(path, json=body).status_code == 409
    assert domain.verify_ledger(store)["ok"]


def test_price_trial_uses_one_point_five_without_publishing_unconfirmed_cost(env):
    store, admin, *_ = env
    rule = {
        "costs": {"characters": "800000"},
        "multiplier": "1.5",
        "fee_micros": "0",
        "source": "",
        "cost_basis": "",
        "confirmed": False,
    }
    response = admin.post(
        "/admin/v1/gateway-prices/preview",
        json={"model": "haike/cosyvoice", "rule": rule, "usage": {"characters": 10000}},
    )
    assert response.status_code == 200
    assert response.json()["cost_micros"] == "800000"
    assert response.json()["sale_micros"] == "1200000"
    assert response.json()["profit_micros"] == "400000"
    assert (
        admin.post(
            "/admin/v1/gateway-prices", json={"model": "haike/cosyvoice", "rule": rule}
        ).status_code
        == 422
    )
    with store.read() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM gateway_prices WHERE model='haike/cosyvoice'"
            ).fetchone()[0]
            == 1
        )


def test_token_bill_export_keeps_both_usage_meters_and_customer_rates(env):
    store, admin, client, _, _, user, _ = env
    enable(store, "openai")
    fund(env)
    rule = {
        "costs": {"input_tokens": "1000000", "output_tokens": "2000000"},
        "multiplier": "1.5",
        "fee_micros": "0",
        "source": "测试采购凭证",
        "cost_basis": "测试专用采购成本",
        "confirmed": True,
    }
    assert (
        admin.post(
            "/admin/v1/gateway-prices", json={"model": "haike/text", "rule": rule}
        ).status_code
        == 200
    )
    headers, _ = key(client)
    q = real_quote(
        client,
        headers,
        "haike/text",
        {"messages": [{"role": "user", "content": "海客"}], "max_output_tokens": 10},
    )
    job = submit(client, headers, q).json()

    class Tokens:
        def execute(self, *args):
            return {
                "usage": {"input_tokens": 2, "output_tokens": 3},
                "result": {"text": "验收结果"},
                "upstream_id": "test-chat-receipt",
            }

    gateway.execute_one(store, Tokens())
    exported = client.get("/portal/v1/bills/export")
    row = next(csv.DictReader(io.StringIO(exported.text.lstrip("\ufeff"))))
    assert json.loads(row["完整计量回执 JSON"]) == {
        "input_tokens": 2,
        "output_tokens": 3,
    }
    assert len(json.loads(row["固定单价 JSON"])) == 2
    assert row["供应商任务编号"] == "test-chat-receipt" and row["实扣微元"] == "12"
    assert "测试专用采购成本" not in exported.text
    assert gateway.get_job(store, user, job["id"])["status"] == "succeeded"
    assert domain.verify_ledger(store)["ok"]


def test_concurrent_real_jobs_honor_shared_key_daily_budget(env):
    store, _, client, _, _, user, _ = env
    vault = enable(store)
    fund(env)
    headers, created = key(client, "240000")
    actor = {**user, "key_id": created["key"]["id"]}
    quotes = [real_quote(client, headers) for _ in range(6)]

    def accept(pair):
        i, q = pair
        try:
            return gateway.accept(
                store,
                vault,
                actor,
                q["id"],
                int(q["max_charge_micros"]),
                "intent-concurrent-" + str(i),
                "idem-concurrent-" + str(i),
            )["id"]
        except Problem as e:
            return e.code

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(accept, enumerate(quotes)))
    assert len([r for r in results if r.startswith("gj_")]) == 1
    assert results.count("daily_limit") == 5
    assert domain.verify_ledger(store)["ok"]
