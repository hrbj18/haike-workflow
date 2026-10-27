"""Receipt-based RunningHub costing. Wallet money and RH coins are distinct."""
from decimal import ROUND_CEILING, Decimal, InvalidOperation


def number(value):
    if isinstance(value, bool) or value is None: raise ValueError("missing numeric receipt")
    try: value = Decimal(str(value))
    except InvalidOperation: raise ValueError("invalid numeric receipt") from None
    if not value.is_finite() or not 0 <= value <= Decimal(1000000):
        raise ValueError("out of range receipt")
    return value


def receipt_cost(usage, *, package_cny=None, package_coins=None):
    """Read documented task usage only; never use account balance deltas."""
    if not isinstance(usage, dict): raise TypeError("missing usage receipt")
    money, coins = usage.get("consumeMoney"), usage.get("consumeCoins")
    third = number(usage["thirdPartyConsumeMoney"]) if usage.get("thirdPartyConsumeMoney") is not None else Decimal(0)
    # Avoid guessing whether an extra provider fee is already included in consumeMoney.
    if third: raise ValueError("third party fee needs reconciliation")
    if money is not None:
        amount, basis = number(money), "provider_wallet_cny"
        if coins is not None and number(coins): raise ValueError("mixed wallet and coin receipt needs reconciliation")
        if amount * 1000000 != (amount * 1000000).to_integral_value(): raise ValueError("wallet receipt exceeds micro precision")
    elif coins is not None and package_cny is not None and package_coins is not None:
        count, price = number(package_coins), number(package_cny)
        if not count or not price: raise ValueError("invalid procurement package")
        amount, basis = number(coins) * price / count, "provider_coins_purchase_package"
    else: raise ValueError("receipt cost cannot be established")
    cost = int((amount * 1000000).to_integral_value(rounding=ROUND_CEILING))
    sale = int((amount * 1500000).to_integral_value(rounding=ROUND_CEILING))
    return {"cost_micros": str(cost), "sale_micros": str(sale), "basis": basis,
            "consume_money_cny": str(number(money)) if money is not None else None,
            "consume_coins": str(number(coins)) if coins is not None else None,
            "task_cost_seconds": str(number(usage["taskCostTime"])) if usage.get("taskCostTime") is not None else None,
            "multiplier": "1.5"}
