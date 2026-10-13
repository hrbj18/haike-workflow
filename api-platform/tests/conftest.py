import pytest
from fastapi.testclient import TestClient

from platform_app.app import create_app

BASE = "http://127.0.0.1"
HEADERS = {"Origin": BASE}


def signed_in(client, path, email, name="测试账户"):
    body = {"email": email, "password": "Test-only-password-123"}
    if path != "login":
        body["name"] = name
    response = client.post("/portal/v1/" + path, json=body)
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return response.json()["user"]


@pytest.fixture
def env(tmp_path):
    app = create_app(tmp_path / "platform.sqlite3", worker_enabled=False, testing=True)
    with TestClient(app, base_url=BASE, headers=HEADERS) as admin:
        admin_user = signed_in(admin, "setup", "admin@example.test", "本地管理员")
        customer = TestClient(app, base_url=BASE, headers=HEADERS)
        user = signed_in(customer, "register", "customer@example.test")
        outsider = TestClient(app, base_url=BASE, headers=HEADERS)
        other = signed_in(outsider, "register", "other@example.test")
        yield app.state.store, admin, customer, outsider, admin_user, user, other
        customer.close()
        outsider.close()
