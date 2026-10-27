"""One customer credential spans privately configured channels and auditable tariffs."""

import csv
import io
import json

from test_commerce import enable, fund, real_quote
from test_platform import key, submit

from platform_app import adapters, domain, gateway, providers


def add_model(
    admin,
    model="haike/channel-a",
    channel="channel/test-a",
    target="upstream-a",
    costs=None,
):
    result = admin.post(
        "/admin/v1/gateway-models",
        json={
            "model": model,
            "name": "测试统一模型",
            "provider": channel,
            "target_model": target,
            "enabled": True,
        },
    )
    assert result.status_code == 200, result.text
    result = admin.post(
        "/admin/v1/gateway-prices",
        json={
            "model": model,
            "rule": {
                "costs": costs
                or {"input_tokens": "1000000", "output_tokens": "2000000"},
                "multiplier": "1.5",
                "fee_micros": "0",
                "source": "私有采购凭证",
                "cost_basis": "管理员核对成本",
                "confirmed": True,
            },
        },
    )
    assert result.status_code == 200, result.text


def channel(admin, suffix):
    channel_id = "channel/test-" + suffix
    result = admin.post(
        "/admin/v1/providers",
        json={
            "id": channel_id,
            "name": "平台" + suffix,
            "base_url": "https://" + suffix + ".example.test/v1",
            "api_key": "test-private-" + suffix,
        },
    )
    assert result.status_code == 200, result.text
    assert (
        admin.post(
            "/admin/v1/providers/" + channel_id, json={"config": {"enabled": True}}
        ).status_code
        == 200
    )
    return channel_id


def test_same_key_routes_across_channels_with_frozen_model_and_bill(env, monkeypatch):
    store, admin, customer, outsider, _, _user, _ = env
    channel(admin, "a")
    channel(admin, "b")
    add_model(admin)
    add_model(admin, "haike/channel-b", "channel/test-b", "upstream-b")
    fund(env)
    headers, _ = key(customer)
    assert customer.get("/admin/v1/providers").status_code == 403
    assert customer.post("/admin/v1/gateway-models", json={}).status_code == 403
    assert customer.post("/admin/v1/providers", json={}).status_code == 403
    catalogue = customer.get("/v2/capabilities", headers=headers).json()["items"]
    assert {m["model"] for m in catalogue} == {"haike/channel-a", "haike/channel-b"}
    assert all("provider" not in m and "target_model" not in m for m in catalogue)
    calls = []

    def fake_http(url, request_headers, body):
        calls.append((url, request_headers["Authorization"], body["model"]))
        return {
            "id": "receipt-" + str(len(calls)),
            "usage": {"prompt_tokens": 101, "completion_tokens": 3},
            "choices": [{"message": {"content": "成功"}, "finish_reason": "stop"}],
        }

    monkeypatch.setattr(adapters, "http", fake_http)
    adapter = adapters.Adapter(
        providers.Vault(store.path.parent), store.path.parent / "files"
    )
    q = real_quote(
        customer,
        headers,
        "haike/channel-a",
        {"messages": [{"role": "user", "content": "你好"}], "max_output_tokens": 10},
    )
    first = submit(customer, headers, q).json()
    assert submit(customer, headers, q).json()["id"] == first["id"]
    # Changing the upstream route and tariff cannot move a previously accepted call.
    add_model(
        admin,
        "haike/channel-a",
        "channel/test-b",
        "changed-model",
        {"input_tokens": "3000000", "output_tokens": "4000000"},
    )
    assert gateway.execute_one(store, adapter)
    assert calls == [
        (
            "https://a.example.test/v1/chat/completions",
            "Bearer test-private-a",
            "upstream-a",
        )
    ]
    bill = customer.get("/portal/v1/bills/" + first["id"]).json()
    assert bill["charged_micros"] == "161"  # ceil(101*1.5 + 3*3), once.
    assert bill["price"]["version"] == 1
    assert bill["billing"]["rounding_adjustment_micros"] == "0"
    assert bill["billing"]["lines"][0]["amount_micros"] == "152"
    assert bill["billing"]["lines"][1]["amount_micros"] == "9"
    assert len(bill["ledger"]) == 2
    assert "unit_cost_micros" not in json.dumps(bill)
    assert "test-private-" not in json.dumps(bill)
    assert outsider.get("/portal/v1/bills/" + first["id"]).status_code == 404
    q2 = real_quote(
        customer,
        headers,
        "haike/channel-b",
        {"messages": [{"role": "user", "content": "你好"}], "max_output_tokens": 10},
    )
    second = submit(
        customer, headers, q2, intent="intent-channel-b", idem="request-channel-b"
    ).json()
    assert gateway.execute_one(store, adapter)
    assert calls[-1] == (
        "https://b.example.test/v1/chat/completions",
        "Bearer test-private-b",
        "upstream-b",
    )
    exported = customer.get(
        "/portal/v1/bills/export?model=haike/channel-a&status=succeeded"
    )
    rows = list(csv.DictReader(io.StringIO(exported.text.lstrip("\ufeff"))))
    assert len(rows) == 1 and rows[0]["任务"] == first["id"]
    assert rows[0]["加价系数"] == "1.5"
    assert json.loads(rows[0]["逐项费用 JSON"])[1]["quantity"] == 3
    assert "私有采购凭证" not in exported.text
    assert customer.get("/admin/v1/gateway-jobs/export").status_code == 403
    assert customer.get("/admin/v1/gateway-jobs/" + first["id"]).status_code == 403
    admin_bill = admin.get("/admin/v1/gateway-jobs/" + first["id"]).json()
    assert admin_bill["billing"]["lines"][0]["unit_cost_micros"] == "1000000"
    operations = admin.get("/admin/v1/gateway-jobs/export")
    assert operations.status_code == 200 and "估算成本微元" in operations.text
    assert "test-private-" not in operations.text
    ledger_export = customer.get("/portal/v1/ledger/export")
    assert (
        len(list(csv.DictReader(io.StringIO(ledger_export.text.lstrip("\ufeff"))))) == 5
    )
    assert outsider.get("/portal/v1/ledger/export").text.count("gj_") == 0
    _, new_key = key(customer)
    new_headers = {"Authorization": "Bearer " + new_key["secret"]}
    assert {
        j["id"]
        for j in customer.get("/v2/account/usage", headers=new_headers).json()["items"]
    } == {first["id"], second["id"]}
    assert domain.verify_ledger(store)["ok"]
    # Private channel/model configuration survives a fresh Vault instance.
    assert "haike/channel-a" in providers.Vault(store.path.parent).models()


def test_fixed_markup_and_no_extra_fee_are_enforced(env):
    store, admin, customer, _, _, _, _ = env
    vault = enable(store)
    rule = providers.catalogue(store, vault, True)[1]["rule"]
    for change in ({"multiplier": "2"}, {"fee_micros": "1"}):
        result = admin.post(
            "/admin/v1/gateway-prices",
            json={"model": "haike/cosyvoice", "rule": {**rule, **change}},
        )
        assert result.status_code == 422
    headers, _ = key(customer)
    q = real_quote(customer, headers)
    result = submit(customer, headers, q)
    assert (
        result.status_code == 409
        and result.json()["error"]["code"] == "commercial_balance_low"
    )


def test_fractional_unit_prices_bill_rounding_and_ceiling(env):
    store, admin, customer, _, _, user, _ = env
    channel(admin, "a")
    add_model(admin, costs={"input_tokens": "1", "output_tokens": "1"})
    fund(env)
    headers, _ = key(customer)
    q = real_quote(
        customer,
        headers,
        "haike/channel-a",
        {"messages": [{"role": "user", "content": "hi"}], "max_output_tokens": 10},
    )
    assert q["price"]["rates"][0]["price_micros"] == "1.5"
    job = submit(customer, headers, q).json()
    with store.write() as db:
        row = db.execute(
            "SELECT * FROM gateway_jobs WHERE id=?", (job["id"],)
        ).fetchone()
        gateway.finish(db, row, {"usage": {"input_tokens": 1, "output_tokens": 1}})
    bill = gateway.get_job(store, user, job["id"])
    assert bill["charged_micros"] == "1"
    assert bill["billing"]["rounding_adjustment_micros"] == "-1"
    assert sum(int(r["amount_micros"]) for r in bill["billing"]["lines"]) + int(
        bill["billing"]["rounding_adjustment_micros"]
    ) == int(bill["charged_micros"])
    assert domain.verify_ledger(store)["ok"]


def test_bill_ceiling_discount_release_and_model_pause(env):
    store, admin, customer, _, _, user, _ = env
    channel(admin, "a")
    add_model(admin)
    fund(env)
    headers, _ = key(customer)
    inputs = {"messages": [{"role": "user", "content": "hi"}], "max_output_tokens": 10}
    q = real_quote(customer, headers, "haike/channel-a", inputs)
    job = submit(customer, headers, q).json()
    with store.write() as db:
        gateway.finish(
            db,
            db.execute(
                "SELECT * FROM gateway_jobs WHERE id=?", (job["id"],)
            ).fetchone(),
            {"usage": {"input_tokens": 1000000, "output_tokens": 1000000}},
        )
    bill = gateway.get_job(store, user, job["id"])
    assert bill["charged_micros"] == q["max_charge_micros"]
    assert int(bill["billing"]["ceiling_discount_micros"]) == 4500000 - int(
        q["max_charge_micros"]
    )
    q2 = real_quote(customer, headers, "haike/channel-a", inputs)
    job2 = submit(
        customer, headers, q2, intent="failure-intent", idem="failure-request"
    ).json()
    released = gateway.cancel(store, user, job2["id"])
    assert released["billing"]["released_micros"] == q2["max_charge_micros"]
    assert all(r["amount_micros"] is None for r in released["billing"]["lines"])
    assert released["charged_micros"] == "0"
    admin.post(
        "/admin/v1/gateway-models",
        json={
            "model": "haike/channel-a",
            "name": "暂停模型",
            "provider": "channel/test-a",
            "target_model": "upstream-a",
            "enabled": False,
        },
    )
    assert customer.get("/v2/capabilities", headers=headers).json()["items"] == []
    unavailable = customer.post(
        "/v2/quotes",
        headers=headers,
        json={"model": "haike/channel-a", "input": inputs},
    )
    assert unavailable.status_code == 409
    assert domain.verify_ledger(store)["ok"]
