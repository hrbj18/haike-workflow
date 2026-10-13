import pytest
from fastapi.testclient import TestClient

from platform_app import domain
from platform_app.app import create_app

BASE = "http://127.0.0.1"
HEADERS = {"Origin": BASE}


@pytest.mark.parametrize("username", ["中", "工作室 A + 一"])
def test_register_with_only_username_and_short_password(env, username):
    store, admin, client, _, _, _, _ = env
    response = client.post(
        "/portal/v1/register", json={"username": username, "password": "1"}
    )
    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert user["username"] == username.lower()
    assert user["name"] == username.lower()
    assert not user["must_change_password"]
    assert "password" not in user and "password_hash" not in user
    credited = admin.post(
        "/admin/v1/users/" + user["id"] + "/credits",
        headers={"Idempotency-Key": "username-credit-01"},
        json={"amount_micros": "1000000", "note": "测试用户名充值"},
    )
    assert credited.status_code == 200
    logged_in = client.post(
        "/portal/v1/login", json={"username": username.upper(), "password": "1"}
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["id"] == user["id"]
    assert domain.wallet(store, user["id"])["commercial_available_micros"] == "1000000"


def test_duplicate_username_shared_by_register_and_admin_creation(env):
    _, admin, client, _, _, _, _ = env
    body = {"username": "  Studio  ", "password": "a"}
    first = client.post("/portal/v1/register", json=body)
    assert first.status_code == 200
    for requester, path in [(client, "/portal/v1/register"), (admin, "/admin/v1/users")]:
        duplicate = requester.post(path, json={"username": "STUDIO", "password": "b"})
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "username_exists"
    assert client.post(
        "/portal/v1/login", json={"username": "studio", "password": "a"}
    ).status_code == 200
    assert client.post(
        "/portal/v1/login", json={"username": "studio", "password": "b"}
    ).status_code == 401


def test_legacy_email_account_can_use_both_login_fields(env):
    store, _, client, _, _, user, _ = env
    for field in ["username", "email"]:
        result = client.post(
            "/portal/v1/login",
            json={field: "CUSTOMER@EXAMPLE.TEST", "password": "Test-only-password-123"},
        )
        assert result.status_code == 200
        assert result.json()["user"]["id"] == user["id"]
        assert result.json()["user"]["username"] == user["email"]
    assert domain.wallet(store, user["id"])["commercial_available_micros"] == "0"


def test_admin_short_password_creation_and_personal_change(env):
    _, admin, client, _, _, _, _ = env
    created = admin.post(
        "/admin/v1/users", json={"username": "新用户", "password": "1"}
    )
    assert created.status_code == 200
    assert created.json()["must_change_password"]
    result = client.post(
        "/portal/v1/login", json={"username": "新用户", "password": "1"}
    ).json()
    client.headers["X-CSRF-Token"] = result["csrf"]
    changed = client.post(
        "/portal/v1/password", json={"current_password": "1", "new_password": "2"}
    )
    assert changed.status_code == 200
    assert not changed.json()["user"]["must_change_password"]
    assert client.post(
        "/portal/v1/login", json={"username": "新用户", "password": "2"}
    ).status_code == 200


def test_setup_with_two_fields_and_required_values(tmp_path):
    app = create_app(tmp_path / "accounts.sqlite3", worker_enabled=False, testing=True)
    with TestClient(app, base_url=BASE, headers=HEADERS) as client:
        result = client.post(
            "/portal/v1/setup", json={"username": "管理员", "password": "1"}
        )
        assert result.status_code == 200
        assert result.json()["user"]["role"] == "admin"
        for body in [
            {"username": "   ", "password": "1"},
            {"username": "新用户", "password": ""},
            {"username": "新用户"},
        ]:
            assert client.post("/portal/v1/register", json=body).status_code == 422
