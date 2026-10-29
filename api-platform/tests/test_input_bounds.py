from test_platform import RULE, key


def test_nested_input_and_quantity_are_validated(env):
    _, admin, customer, _, _, _, _ = env
    headers, _ = key(customer)
    response = customer.post(
        "/v2/quotes",
        headers=headers,
        json={
            "model": "demo/cosyvoice-characters",
            "input": {"text": "海", "demo_outcome": []},
        },
    )
    assert response.status_code == 422
    response = customer.post(
        "/v2/quotes",
        headers=headers,
        json={
            "model": "demo/cosyvoice-characters",
            "input": {"text": "海" + " " * 20000, "demo_outcome": "succeeded"},
        },
    )
    assert response.status_code == 422
    response = admin.post(
        "/admin/v1/price-versions/preview",
        json={
            "model": "demo/avatar-role",
            "quantity": 1200,
            "rule": RULE,
        },
    )
    assert response.status_code == 422
