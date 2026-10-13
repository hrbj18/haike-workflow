from test_platform import key, pay, submit

from platform_app import domain
from platform_app.worker import claim, complete_simulation


def test_unused_hold_is_released_using_simulated_receipt(env):
    store, _, customer, _, _, _, _ = env
    pay(customer)
    headers, _ = key(customer)
    response = customer.post(
        "/v2/quotes",
        headers=headers,
        json={
            "model": "demo/cosyvoice-characters",
            "input": {"text": "海" * 1200 + " " * 300, "demo_outcome": "succeeded"},
        },
    )
    quote = response.json()
    assert quote["max_charge_micros"] == "156000"
    job = submit(customer, headers, quote).json()
    claim(store)
    complete_simulation(store, job["id"])
    bill = customer.get("/portal/v1/bills/" + job["id"]).json()
    assert (bill["quoted_quantity"], bill["quantity"], bill["charged_micros"]) == (
        1500,
        1200,
        "124800",
    )
    settlement = customer.get("/portal/v1/ledger").json()["items"][0]
    assert settlement["postings"]["available"] == "31200"
    assert domain.verify_ledger(store)["ok"]
