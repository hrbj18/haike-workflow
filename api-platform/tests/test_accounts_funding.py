import csv
import io
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from test_commerce import Success, enable, real_quote
from test_platform import key, submit

from platform_app import commerce, domain, gateway


def test_lost_code_reissue_reuses_receipt_and_revokes_original(env):
    store, admin, client, _, actor, user, _ = env
    result = admin.post(
        "/admin/v1/redeem-codes",
        headers={"Idempotency-Key": "reissue-original-batch"},
        json={
            "amount_micros": "30000000",
            "count": 1,
            "batch": "已付款测试",
            "bound_user_id": user["id"],
            "payment_ref": "receipt-reissue-01",
        },
    ).json()
    old = result["items"][0]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: commerce.reissue_code(store, actor["id"], old["id"]), range(4)
            )
        )
    assert len({r["items"][0]["id"] for r in results}) == 1
    fresh = next(r["items"][0] for r in results if r["show_once"])
    replay = commerce.issue_codes(
        store,
        actor["id"],
        30000000,
        1,
        30,
        "已付款测试",
        user["id"],
        payment_ref="receipt-reissue-01",
        idem="reissue-original-batch",
    )
    assert len(replay["items"]) == 1 and replay["items"][0]["id"] == fresh["id"]
    assert "code" not in replay["items"][0]
    assert fresh["amount"] == old["amount"] and fresh["expires_at"] == old["expires_at"]
    assert (
        client.post(
            "/portal/v1/redeem-codes/redeem", json={"code": old["code"]}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/portal/v1/redeem-codes/redeem", json={"code": fresh["code"]}
        ).status_code
        == 200
    )
    assert (
        admin.post("/admin/v1/redeem-codes/" + fresh["id"] + "/reissue").status_code
        == 409
    )
    history = admin.get("/admin/v1/funding-history").json()
    assert len(history["receipts"]) == 1
    assert (
        history["receipts"][0]["code_count"]
        == history["receipts"][0]["redeemed_count"]
        == 1
    )
    assert domain.wallet(store, user["id"])["commercial_available_micros"] == "30000000"
    assert domain.verify_ledger(store)["ok"]


def credit(admin, user, receipt="WX-20261013-01", idem="private-credit-01"):
    return admin.post(
        "/admin/v1/users/" + user["id"] + "/credits",
        headers={"Idempotency-Key": idem},
        json={
            "amount_micros": "100000000",
            "note": "私域已收款",
            "payment_ref": receipt,
            "channel": "wechat",
            "received_confirmed": True,
        },
    )


def test_admin_created_customer_requires_personal_password(env):
    _, admin, client, _, _, _, _ = env
    r = admin.post(
        "/admin/v1/users",
        json={
            "email": "initial@example.test",
            "name": "私域用户",
            "password": "Initial-password-123",
        },
    )
    assert r.json()["must_change_password"] is True
    login = client.post(
        "/portal/v1/login",
        json={"email": "initial@example.test", "password": "Initial-password-123"},
    ).json()
    client.headers["X-CSRF-Token"] = login["csrf"]
    assert login["user"]["must_change_password"]
    assert (
        client.get("/portal/v1/wallet").json()["error"]["code"]
        == "password_change_required"
    )
    assert (
        client.post(
            "/portal/v1/api-keys", json={"name": "x", "daily_limit_micros": "1000000"}
        ).status_code
        == 403
    )
    changed = client.post(
        "/portal/v1/password",
        json={
            "current_password": "Initial-password-123",
            "new_password": "Personal-password-456",
        },
    )
    assert changed.status_code == 200
    client.headers["X-CSRF-Token"] = changed.json()["csrf"]
    assert changed.json()["user"]["must_change_password"] is False
    assert client.get("/portal/v1/wallet").status_code == 200


def test_password_reset_revokes_sessions_and_blocks_keys_until_changed(env):
    store, admin, client, _, actor, user, _ = env
    headers, _ = key(client)
    assert (
        admin.post(
            "/admin/v1/users/" + actor["id"] + "/password",
            json={"password": "Temporary-password-123"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/admin/v1/users/" + user["id"] + "/password",
            json={"password": "Temporary-password-123"},
        ).status_code
        == 403
    )
    assert (
        admin.post(
            "/admin/v1/users/" + user["id"] + "/password",
            json={"password": "Temporary-password-123"},
        ).status_code
        == 200
    )
    assert client.get("/portal/v1/me").status_code == 401
    assert client.get("/v2/account/summary", headers=headers).status_code == 403
    assert (
        client.post(
            "/portal/v1/login",
            json={"email": user["email"], "password": "Test-only-password-123"},
        ).status_code
        == 401
    )
    r = client.post(
        "/portal/v1/login",
        json={"email": user["email"], "password": "Temporary-password-123"},
    ).json()
    client.headers["X-CSRF-Token"] = r["csrf"]
    changed = client.post(
        "/portal/v1/password",
        json={
            "current_password": "Temporary-password-123",
            "new_password": "Personal-new-password-456",
        },
    )
    assert changed.status_code == 200
    assert client.get("/v2/account/summary", headers=headers).status_code == 200
    with store.read() as db:
        events = db.execute("SELECT action,resource_id FROM audit").fetchall()
        assert "Temporary-password" not in str([tuple(r) for r in events])


def test_own_password_change_invalidates_other_browser_sessions(env):
    store, _, client, _, _, user, _ = env
    second = TestClient(
        client.app, base_url="http://127.0.0.1", headers={"Origin": "http://127.0.0.1"}
    )
    try:
        second.post(
            "/portal/v1/login",
            json={"email": user["email"], "password": "Test-only-password-123"},
        )
        headers, _ = key(client)
        invalid = client.post(
            "/portal/v1/password",
            json={
                "current_password": "Incorrect-password-123",
                "new_password": "Updated-password-123",
            },
        )
        assert (
            invalid.status_code == 401
            and second.get("/portal/v1/me").status_code == 200
        )
        result = client.post(
            "/portal/v1/password",
            json={
                "current_password": "Test-only-password-123",
                "new_password": "Updated-password-123",
            },
        )
        assert (
            result.status_code == 200 and second.get("/portal/v1/me").status_code == 401
        )
        assert client.get("/portal/v1/me").status_code == 200
        assert client.get("/v2/account/summary", headers=headers).status_code == 200
        with store.read() as db:
            assert (
                db.execute(
                    "SELECT count(*) FROM sessions WHERE user_id=?", (user["id"],)
                ).fetchone()[0]
                == 1
            )
    finally:
        second.close()


def test_disabled_account_blocks_new_calls_but_settles_accepted_jobs(env):
    store, admin, client, _, actor, user, _ = env
    enable(store)
    assert credit(admin, user).status_code == 200
    headers, _ = key(client)
    job = submit(client, headers, real_quote(client, headers)).json()
    path = "/admin/v1/users/" + user["id"] + "/status"
    assert admin.post(path, json={"status": "disabled"}).status_code == 200
    assert (
        admin.post(
            "/admin/v1/users/" + actor["id"] + "/status", json={"status": "disabled"}
        ).status_code
        == 403
    )
    assert client.get("/portal/v1/me").status_code == 401
    assert client.get("/v2/account/summary", headers=headers).status_code == 403
    assert (
        client.post(
            "/v2/quotes",
            headers=headers,
            json={"model": "haike/cosyvoice", "input": {"text": "a"}},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/portal/v1/login",
            json={"email": user["email"], "password": "Test-only-password-123"},
        ).status_code
        == 403
    )
    assert credit(admin, user, "new-receipt", "disabled-credit-01").status_code == 403
    gateway.execute_one(store, Success())
    settled = gateway.get_job(store, user, job["id"])
    assert settled["status"] == "succeeded" and settled["charged_micros"] == "240000"
    assert admin.post(path, json={"status": "active"}).status_code == 200
    assert client.get("/v2/account/summary", headers=headers).status_code == 200
    assert client.get("/portal/v1/me").status_code == 401
    assert domain.verify_ledger(store)["ok"]


def test_private_receipt_cannot_fund_twice_across_manual_and_code_paths(env):
    store, admin, client, outsider, _, user, _ = env
    first = credit(admin, user)
    assert first.status_code == 200
    assert credit(admin, user).json()["id"] == first.json()["id"]
    assert (
        credit(admin, user, idem="different-credit-01").json()["error"]["code"]
        == "payment_already_recorded"
    )
    codes = {
        "amount_micros": "50000000",
        "count": 2,
        "expires_days": 30,
        "batch": "私域实收",
        "bound_user_id": user["id"],
        "channel": "wechat",
        "payment_ref": "WX-20261013-01",
        "note": "第二笔私域付款",
    }
    assert admin.post("/admin/v1/redeem-codes", json=codes).status_code == 409
    codes["payment_ref"] = "WX-CODES-02"
    issued = admin.post(
        "/admin/v1/redeem-codes",
        json=codes,
        headers={"Idempotency-Key": "issue-private-codes-01"},
    ).json()
    replay = admin.post(
        "/admin/v1/redeem-codes",
        json=codes,
        headers={"Idempotency-Key": "issue-private-codes-01"},
    ).json()
    assert replay["replayed"] and all("code" not in r for r in replay["items"])
    assert credit(admin, user, "WX-CODES-02", "different-credit-02").status_code == 409
    assert (
        domain.wallet(store, user["id"])["commercial_available_micros"] == "100000000"
    )
    code = issued["items"][0]["code"]
    assert (
        outsider.post("/portal/v1/redeem-codes/redeem", json={"code": code}).status_code
        == 404
    )
    for _ in range(2):
        assert (
            client.post(
                "/portal/v1/redeem-codes/redeem", json={"code": code}
            ).status_code
            == 200
        )
    assert (
        domain.wallet(store, user["id"])["commercial_available_micros"] == "150000000"
    )
    history = client.get("/portal/v1/funding-history").json()["items"]
    assert len(history) == 2 and {h["kind"] for h in history} == {
        "admin_credit",
        "redeem_credit",
    }
    assert all("payment_ref" not in h and "note" not in h for h in history)
    assert outsider.get("/portal/v1/funding-history").json()["items"] == []
    admin_history = admin.get("/admin/v1/funding-history").json()
    assert len(admin_history["receipts"]) == 2
    assert sum(r["redeemed_count"] for r in admin_history["receipts"]) == 1
    assert domain.verify_ledger(store)["ok"]


def test_recharge_config_permissions_proof_confirmation_and_csv(env):
    _, admin, client, _, _, user, _ = env
    info = {"contact": "微信：test-private", "instructions": "付款后提供注册邮箱。"}
    assert client.post("/admin/v1/funding-info", json=info).status_code == 403
    assert admin.post("/admin/v1/funding-info", json=info).status_code == 200
    assert client.get("/portal/v1/funding-info").json() == info
    invalid = admin.post(
        "/admin/v1/users/" + user["id"] + "/credits",
        headers={"Idempotency-Key": "unconfirmed-credit"},
        json={
            "amount_micros": "100000000",
            "note": "未收款",
            "received_confirmed": False,
        },
    )
    assert invalid.status_code == 422
    assert credit(admin, user, "=FORMULA").status_code == 200
    export = admin.get("/admin/v1/funding-history/export")
    records = list(csv.reader(io.StringIO(export.text.lstrip("\ufeff"))))
    assert records[1][6] == "'=FORMULA" and records[1][4] == "100000000"
    assert client.get("/admin/v1/funding-history/export").status_code == 403
    assert (
        admin.get("/admin/v1/users?search=customer@example.test").json()["items"][0][
            "id"
        ]
        == user["id"]
    )


def test_manual_credit_needs_only_amount_and_records_operator_once(env):
    store, admin, client, _, actor, user, _ = env
    path = "/admin/v1/users/" + user["id"] + "/credits"
    body = {"amount_micros": "20000000"}
    headers = {"Idempotency-Key": "simple-manual-credit-01"}
    assert client.post(path, json=body, headers=headers).status_code == 403
    first = admin.post(path, json=body, headers=headers)
    assert first.status_code == 200, first.text
    replay = admin.post(path, json=body, headers=headers)
    assert replay.status_code == 200 and replay.json()["id"] == first.json()["id"]
    assert domain.wallet(store, user["id"])["commercial_available_micros"] == "20000000"
    assert admin.post(path, json={"amount_micros": "10000000"}, headers=headers).status_code == 409
    history = admin.get("/admin/v1/funding-history").json()
    assert len(history["receipts"]) == len(history["items"]) == 1
    receipt = history["receipts"][0]
    assert receipt["operator"] == actor["name"] and receipt["email"] == user["email"]
    assert receipt["amount_micros"] == "20000000"
    assert receipt["note"] == "管理员手动充值"
    assert receipt["channel"] == "private" and not receipt["payment_ref"]
    assert receipt["created_at"] and receipt["operator"]
    assert len(client.get("/portal/v1/funding-history").json()["items"]) == 1
    assert domain.verify_ledger(store)["ok"]
