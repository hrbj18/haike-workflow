"""Pure fixed-precision pricing. No provider billing estimate can mutate a wallet."""

import json
from decimal import ROUND_CEILING, Decimal, InvalidOperation

from .store import Problem, canonical, now, uid

MODELS = {
    "demo/cosyvoice-characters": {
        "name": "配音 · 字符计费演示",
        "capability": "tts",
        "unit": "字符",
        "target_model": "cosyvoice-v3.5-flash",
        "included_units": 10000,
        "description": "验证字符报价和账单；模拟回执，不生成音频。",
    },
    "demo/avatar-role": {
        "name": "数字人 · 固定角色档位演示",
        "capability": "avatar",
        "unit": "角色",
        "target_model": "RunningHub exact_clock_v2",
        "included_units": 1,
        "description": "验证每角色售价与任务恢复；模拟回执，不生成视频。",
    },
}


def amount_string(value, allow_zero=True):
    if (
        not isinstance(value, str)
        or not value.isascii()
        or not value.isdigit()
        or len(value) > 13
    ):
        raise Problem(422, "invalid_amount", "金额须为整数微元字符串")
    number = int(value)
    if number > 10**12 or (not allow_zero and number == 0):
        raise Problem(422, "invalid_amount", "金额超出演示范围")
    return number


def normalize_rule(model, rule):
    if model not in MODELS:
        raise Problem(422, "unknown_model", "模型未开通")
    if set(rule) != {
        "mode",
        "cost_micros",
        "multiplier",
        "margin",
        "fixed_micros",
        "fee_micros",
    }:
        raise Problem(422, "invalid_price", "定价字段不完整或包含未知字段")
    if rule["mode"] not in {"markup", "margin", "fixed"}:
        raise Problem(422, "invalid_price", "不支持的定价方式")
    for key in ("cost_micros", "fixed_micros", "fee_micros"):
        amount_string(rule[key])
    try:
        multiplier, margin = Decimal(rule["multiplier"]), Decimal(rule["margin"])
        if not multiplier.is_finite() or not margin.is_finite():
            raise ValueError()
        if not (Decimal("0.01") <= multiplier <= 100) or not (
            0 <= margin <= Decimal("0.95")
        ):
            raise ValueError()
        if multiplier.as_tuple().exponent < -6 or margin.as_tuple().exponent < -6:
            raise ValueError()
    except (InvalidOperation, ValueError, TypeError):
        raise Problem(
            422, "invalid_price", "系数需在 0.01–100，毛利率需在 0–0.95，最多六位小数"
        ) from None
    clean = dict(rule)
    clean["multiplier"], clean["margin"] = str(multiplier), str(margin)
    if customer_rate(clean) <= 0:
        raise Problem(422, "invalid_price", "客户单价须大于零")
    return clean


def customer_rate(rule):
    cost = Decimal(rule["cost_micros"])
    if rule["mode"] == "markup":
        return cost * Decimal(rule["multiplier"])
    if rule["mode"] == "margin":
        return cost / (1 - Decimal(rule["margin"]))
    return Decimal(rule["fixed_micros"])


def rounded(value):
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def calculate(model, rule, quantity):
    maximum = 2 if model == "demo/avatar-role" else 20000
    if type(quantity) is not int or not 1 <= quantity <= maximum:
        raise Problem(422, "invalid_quantity", "用量超出此档位范围")
    units = MODELS[model]["included_units"]
    charge = rounded(
        customer_rate(rule) * quantity / units + Decimal(rule["fee_micros"])
    )
    cost = rounded(Decimal(rule["cost_micros"]) * quantity / units)
    if charge > 10**12:
        raise Problem(422, "price_limit", "报价超出演示限额")
    return {
        "charge_micros": str(charge),
        "estimated_cost_micros": str(cost),
        "estimated_margin": str((Decimal(charge - cost) / charge) if charge else 0),
        "quantity": quantity,
        "unit": MODELS[model]["unit"],
    }


def seed_prices(store):
    with store.write() as db:
        for model in MODELS:
            if db.execute("SELECT 1 FROM prices WHERE model=?", (model,)).fetchone():
                continue
            rule = {
                "mode": "markup",
                "cost_micros": "800000",
                "multiplier": "1.3",
                "margin": "0.3",
                "fixed_micros": "1040000",
                "fee_micros": "0",
            }
            if model == "demo/avatar-role":
                rule.update(mode="fixed", cost_micros="3000000", fixed_micros="5000000")
            db.execute(
                "INSERT INTO prices VALUES(?,?,?,?,?,?,?,?)",
                (
                    uid("prc"),
                    model,
                    1,
                    "published",
                    canonical(rule),
                    now(),
                    now(),
                    None,
                ),
            )


def public_price(row):
    rule = json.loads(row["rule"])
    model = row["model"]
    return {
        "id": row["id"],
        "model": model,
        **MODELS[model],
        "version": row["version"],
        "state": "simulated",
        "currency": "CNY",
        "simulation": True,
        "unit_price_micros": format(customer_rate(rule).normalize(), "f"),
        "fee_micros": rule["fee_micros"],
        "rounding": "任务合计向上取整到微元",
        "published_at": row["published_at"],
    }


def catalogue(store):
    with store.read() as db:
        rows = db.execute(
            "SELECT p.* FROM prices p WHERE p.state='published' AND p.version="
            "(SELECT max(version) FROM prices WHERE model=p.model AND state='published')"
        ).fetchall()
    order = {model: i for i, model in enumerate(MODELS)}
    return [public_price(row) for row in sorted(rows, key=lambda r: order[r["model"]])]
