import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from platform_app import domain
from platform_app.worker import claim, complete_simulation, recover_interrupted

BASE = "http://127.0.0.1"
HEADERS = {"Origin": BASE}
RULE = {
    "mode": "markup",
    "cost_micros": "800000",
    "multiplier": "1.3",
    "margin": "0.3",
    "fixed_micros": "1040000",
    "fee_micros": "0",
}


def key(client, budget="100000000"):
    r = client.post(
        "/portal/v1/api-keys",
        json={"name": "测试 Key", "daily_limit_micros": budget, "expires_days": 90},
    )
    assert r.status_code == 200
    k = r.json()
    return {"Authorization": "Bearer " + k["secret"]}, k


def pay(client, fen=10000, idem="recharge-0001"):
    r = client.post(
        "/portal/v1/recharges",
        json={"amount_fen": fen},
        headers={"Idempotency-Key": idem},
    )
    assert r.status_code == 200
    order = r.json()
    assert (
        client.post("/portal/v1/recharges/" + order["id"] + "/mock-confirm").status_code
        == 200
    )
    return order


def quote(
    client,
    headers,
    model="demo/cosyvoice-characters",
    outcome="succeeded",
    quantity=1200,
):
    inputs = (
        {"roles": quantity, "demo_outcome": outcome}
        if model == "demo/avatar-role"
        else {"text": "海" * quantity, "demo_outcome": outcome}
    )
    response = client.post(
        "/v2/quotes",
        headers=headers,
        json={
            "model": model,
            "input": inputs,
            "project_ref": "=unsafe-spreadsheet-formula",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def submit(
    client, headers, q, idem="job-request-0001", intent="intent-0001", ceiling=None
):
    return client.post(
        "/v2/jobs",
        headers={**headers, "Idempotency-Key": idem},
        json={
            "quote_id": q["id"],
            "max_charge_micros": ceiling or q["max_charge_micros"],
            "call_intent_id": intent,
            "currency": "CNY",
            "confirmed": True,
        },
    )


def test_payment_replay_and_transactional_ledger(env):
    store, _, c, _, _, _, _ = env
    order = pay(c)
    for _ in range(3):
        assert (
            c.post(f"/portal/v1/recharges/{order['id']}/mock-confirm").status_code
            == 200
        )
    assert c.get("/portal/v1/wallet").json()["available_micros"] == "100000000"
    same = c.post(
        "/portal/v1/recharges",
        headers={"Idempotency-Key": "recharge-0001"},
        json={"amount_fen": 10000},
    )
    assert same.json()["id"] == order["id"]
    assert (
        c.post(
            "/portal/v1/recharges",
            headers={"Idempotency-Key": "recharge-0001"},
            json={"amount_fen": 20000},
        ).status_code
        == 409
    )
    assert len(c.get("/portal/v1/ledger").json()["items"]) == 1
    assert domain.verify_ledger(store)["ok"]
    with store.write() as db, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute("UPDATE postings SET amount=0")


def test_quote_acceptance_idempotency_and_rotation(env):
    store, _, c, _, _, _, _ = env
    pay(c)
    headers, old_key = key(c)
    q = quote(c, headers)
    first = submit(c, headers, q)
    assert first.status_code == 200
    assert submit(c, headers, q).json()["id"] == first.json()["id"]
    assert submit(c, headers, q, ceiling="200000").status_code == 409
    assert (
        submit(
            c, headers, q, idem="different-0001", intent="different-intent"
        ).status_code
        == 409
    )
    c.post(f"/portal/v1/api-keys/{old_key['key']['id']}/revoke")
    assert submit(c, headers, q).status_code == 401
    fresh, _ = key(c)
    assert submit(c, fresh, q).json()["id"] == first.json()["id"]
    assert (
        c.get("/v2/requests/job-request-0001", headers=fresh).json()["id"]
        == first.json()["id"]
    )
    assert c.get("/portal/v1/wallet").json()["reserved_micros"] == "124800"
    assert domain.verify_ledger(store)["ok"]


def test_settle_uses_locked_price_not_current_price(env):
    store, admin, c, _, _, _, _ = env
    pay(c)
    h, _ = key(c)
    q = quote(c, h)
    changed = {**RULE, "multiplier": "2"}
    price = admin.post(
        "/admin/v1/price-versions", json={"model": q["model"], "rule": changed}
    ).json()
    assert (
        admin.post(f"/admin/v1/price-versions/{price['id']}/publish").status_code == 200
    )
    job = submit(c, h, q).json()
    assert quote(c, h)["max_charge_micros"] == "192000"
    assert claim(store) == job["id"]
    complete_simulation(store, job["id"])
    bill = c.get(f"/portal/v1/bills/{job['id']}").json()
    assert bill["charged_micros"] == "124800"
    assert bill["price"]["version"] == 1
    assert bill["result"]["media_generated"] is False
    assert "cost_micros" not in json.dumps(bill)
    assert c.get("/portal/v1/wallet").json()["available_micros"] == "99875200"
    assert domain.verify_ledger(store)["ok"]


def test_concurrent_reservations_cannot_bypass_budget(env):
    store, _, c, _, _, _, _ = env
    pay(c)
    h, _ = key(c, "10000000")
    quotes = [quote(c, h, model="demo/avatar-role", quantity=2) for _ in range(5)]
    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(
            pool.map(
                lambda pair: submit(
                    c,
                    h,
                    pair[1],
                    idem=f"parallel-{pair[0]:04}",
                    intent=f"parallel-intent-{pair[0]}",
                ),
                enumerate(quotes),
            )
        )
    assert [r.status_code for r in responses].count(200) == 1
    assert [r.status_code for r in responses].count(409) == 4
    wallet = c.get("/portal/v1/wallet").json()
    assert (wallet["available_micros"], wallet["reserved_micros"]) == (
        "90000000",
        "10000000",
    )
    assert domain.verify_ledger(store)["ok"]


@pytest.mark.parametrize("outcome", ["failed", "succeeded"])
def test_unknown_submission_holds_until_verified_resolution(env, outcome):
    store, admin, c, _, _, _, _ = env
    pay(c)
    h, _ = key(c)
    q = quote(c, h, outcome="submission_unknown")
    job = submit(c, h, q).json()
    claim(store)
    complete_simulation(store, job["id"])
    assert c.get("/portal/v1/wallet").json()["reserved_micros"] == "124800"
    assert (
        c.post(f"/v2/jobs/{job['id']}/cancel", headers=h).json()["status"]
        == "cancel_pending"
    )
    recover_interrupted(store)
    assert claim(store) is None
    assert c.get("/portal/v1/wallet").json()["reserved_micros"] == "124800"
    path = f"/admin/v1/reconciliation/{job['id']}/mock-resolve"
    bill = admin.post(path, json={"outcome": outcome}).json()
    assert bill["charged_micros"] == ("124800" if outcome == "succeeded" else "0")
    assert admin.post(path, json={"outcome": outcome}).status_code == 409
    assert c.get("/portal/v1/wallet").json()["reserved_micros"] == "0"
    assert domain.verify_ledger(store)["ok"]


def test_worker_restart_never_blindly_resubmits(env):
    store, _, c, _, _, _, _ = env
    pay(c)
    h, _ = key(c)
    job = submit(c, h, quote(c, h)).json()
    assert claim(store) == job["id"]
    recover_interrupted(store)
    assert claim(store) is None
    bill = c.get(f"/portal/v1/bills/{job['id']}").json()
    assert (bill["status"], bill["funds_status"]) == (
        "submission_unknown",
        "reconciliation_pending",
    )
    assert bill["reserved_micros"] == "124800"


def test_key_revocation_does_not_abort_accepted_job(env):
    store, _, c, _, _, _, _ = env
    pay(c)
    h, k = key(c)
    job = submit(c, h, quote(c, h)).json()
    c.post(f"/portal/v1/api-keys/{k['key']['id']}/revoke")
    assert c.get("/v2/account/summary", headers=h).status_code == 401
    claim(store)
    complete_simulation(store, job["id"])
    assert c.get(f"/portal/v1/bills/{job['id']}").json()["charged_micros"] == "124800"


def test_cross_account_access_and_role_boundaries(env):
    _, admin, c, other, _, _, _ = env
    order = pay(c)
    h, k = key(c)
    other_h, _ = key(other)
    q = quote(c, h)
    job = submit(c, h, q).json()
    assert (
        other.post(f"/portal/v1/recharges/{order['id']}/mock-confirm").status_code
        == 404
    )
    assert other.post(f"/portal/v1/api-keys/{k['key']['id']}/revoke").status_code == 404
    assert other.get(f"/portal/v1/bills/{job['id']}").status_code == 404
    assert other.get(f"/v2/jobs/{job['id']}", headers=other_h).status_code == 404
    assert submit(other, other_h, q).status_code == 404
    assert c.get("/admin/v1/ledger-check").status_code == 403
    app = admin.app
    no_session = TestClient(app, base_url=BASE, headers=HEADERS)
    assert no_session.get("/portal/v1/api-keys", headers=h).status_code == 401
    assert no_session.get("/admin/v1/ledger-check", headers=h).status_code == 401
    assert c.get("/v2/account/usage", headers=h).json()["items"][0]["id"] == job["id"]
    assert other.get("/v2/account/usage", headers=other_h).json()["items"] == []
    no_session.close()


def test_origin_csrf_input_and_secret_protection(env):
    _, _, c, _, _, _, _ = env
    body = {"name": "not-created", "daily_limit_micros": "1000000"}
    assert (
        c.post(
            "/portal/v1/api-keys", json=body, headers={"Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/portal/v1/api-keys", json=body, headers={"X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    bad = c.post(
        "/portal/v1/login",
        json={"username": "   ", "password": "Do-not-echo-this-password"},
    )
    assert bad.status_code == 422
    assert "Do-not-echo" not in bad.text
    assert (
        c.post(
            "/portal/v1/recharges",
            json={"amount_fen": 1.5},
            headers={"Idempotency-Key": "invalid-0001"},
        ).status_code
        == 422
    )
    h, k = key(c)
    assert k["secret"] not in c.get("/portal/v1/api-keys").text
    assert (
        c.post(
            "/v2/quotes",
            headers=h,
            json={
                "model": "demo/cosyvoice-characters",
                "input": {"text": "hi", "demo_outcome": "succeeded"},
                "user_id": "spoofed",
            },
        ).status_code
        == 422
    )


def test_cancel_before_submission_releases_once_and_failed_task_releases(env):
    store, _, c, _, _, _, _ = env
    pay(c)
    h, _ = key(c)
    job = submit(c, h, quote(c, h)).json()
    path = f"/v2/jobs/{job['id']}/cancel"
    assert c.post(path, headers=h).json()["funds_status"] == "released"
    assert c.post(path, headers=h).json()["funds_status"] == "released"
    assert claim(store) is None
    q2 = quote(c, h, outcome="failed")
    j2 = submit(c, h, q2, idem="second-request", intent="second-intent").json()
    claim(store)
    complete_simulation(store, j2["id"])
    wallet = c.get("/portal/v1/wallet").json()
    assert (wallet["available_micros"], wallet["reserved_micros"]) == ("100000000", "0")
    assert domain.verify_ledger(store)["ok"]


def test_budget_settles_into_acceptance_period(env, monkeypatch):
    store, _, c, _, _, _, _ = env
    pay(c)
    h, k = key(c)
    monkeypatch.setattr(domain, "period_now", lambda: "2026-10-12")
    job = submit(c, h, quote(c, h)).json()
    monkeypatch.setattr(domain, "period_now", lambda: "2026-10-13")
    claim(store)
    complete_simulation(store, job["id"])
    with store.read() as db:
        budget = db.execute(
            "SELECT * FROM budgets WHERE key_id=?", (k["key"]["id"],)
        ).fetchone()
        assert (budget["period"], budget["reserved"], budget["spent"]) == (
            "2026-10-12",
            0,
            124800,
        )


def test_insufficient_funds_does_not_leave_partial_records(env):
    store, _, c, _, _, _, _ = env
    h, k = key(c)
    q = quote(c, h)
    assert submit(c, h, q).status_code == 409
    assert c.get("/portal/v1/bills").json()["items"] == []
    assert c.get("/portal/v1/ledger").json()["items"] == []
    with store.read() as db:
        assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 0
        assert (
            db.execute(
                "SELECT count(*) FROM budgets WHERE key_id=?", (k["key"]["id"],)
            ).fetchone()[0]
            == 0
        )
    pay(c)
    assert submit(c, h, q).status_code == 200


def test_exact_margin_preview_and_csv_formula_escaping(env):
    store, admin, c, _, _, _, _ = env
    r = admin.post(
        "/admin/v1/price-versions/preview",
        json={"model": "demo/cosyvoice-characters", "quantity": 1200, "rule": RULE},
    )
    assert r.json()["charge_micros"] == "124800"
    r = admin.post(
        "/admin/v1/price-versions/preview",
        json={
            "model": "demo/cosyvoice-characters",
            "quantity": 1200,
            "rule": {**RULE, "mode": "margin"},
        },
    )
    assert r.json()["charge_micros"] == "137143"
    pay(c)
    h, _ = key(c)
    submit(c, h, quote(c, h))
    exported = c.get("/portal/v1/bills/export")
    assert "'=unsafe-spreadsheet-formula" in exported.text
    assert domain.verify_ledger(store)["ok"]
