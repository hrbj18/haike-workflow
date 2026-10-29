"""Transactional money/task boundary. All amounts are integer CNY micros."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from .auth import require_key
from .pricing import MODELS, calculate, normalize_rule, public_price
from .store import Problem, audit, canonical, digest, later, now, owned, post, uid


def period_now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def wallet(store, user_id):
    with store.read() as db:
        row = db.execute("SELECT * FROM wallets WHERE user_id=?", (user_id,)).fetchone()
        commercial = db.execute(
            "SELECT * FROM commercial_wallets WHERE user_id=?", (user_id,)
        ).fetchone()
        month = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m")
        spent = 0
        commercial_spent = 0
        for job in db.execute(
            "SELECT charge,created_at FROM jobs WHERE user_id=? AND funds_status='settled' UNION ALL SELECT charge,created_at FROM gateway_jobs WHERE user_id=? AND status='succeeded'",
            (user_id, user_id),
        ):
            if (
                datetime.fromisoformat(job["created_at"])
                .astimezone(ZoneInfo("Asia/Shanghai"))
                .strftime("%Y-%m")
                == month
            ):
                spent += job["charge"]
        for job in db.execute(
            "SELECT charge,updated_at FROM gateway_jobs WHERE user_id=? AND status='succeeded'",
            (user_id,),
        ):
            if (
                datetime.fromisoformat(job["updated_at"])
                .astimezone(ZoneInfo("Asia/Shanghai"))
                .strftime("%Y-%m")
                == month
            ):
                commercial_spent += job["charge"]
    return {
        "currency": "CNY",
        "available_micros": str(row["available"]),
        "reserved_micros": str(row["reserved"]),
        "commercial_available_micros": str(
            min(row["available"], commercial["available"])
        )
        if commercial
        else "0",
        "simulation_available_micros": str(
            row["available"] - (commercial["available"] if commercial else 0)
        ),
        "month_spent_micros": str(spent),
        "commercial_reserved_micros": str(commercial["reserved"])
        if commercial
        else "0",
        "commercial_month_spent_micros": str(commercial_spent),
        "simulation": False,
        "timezone": "Asia/Shanghai",
    }


def create_order(store, user_id, amount_fen, idem):
    body_hash = digest(canonical({"amount_fen": amount_fen}))
    with store.write() as db:
        old = db.execute(
            "SELECT * FROM idempotency WHERE user_id=? AND operation='recharge' AND idem_key=?",
            (user_id, idem),
        ).fetchone()
        if old:
            if old["body_hash"] != body_hash:
                raise Problem(409, "idempotency_conflict", "同一幂等键不能改变充值金额")
            return order_public(owned(db, "orders", old["resource_id"], user_id))
        order_id = uid("ord")
        db.execute(
            "INSERT INTO orders VALUES(?,?,?,?,?,?,?)",
            (order_id, user_id, amount_fen, "pending", now(), None, None),
        )
        db.execute(
            "INSERT INTO idempotency VALUES(?,?,?,?,?)",
            (user_id, "recharge", idem, body_hash, order_id),
        )
        return order_public(owned(db, "orders", order_id, user_id))


def order_public(row):
    return {
        **dict(row),
        "currency": "CNY",
        "payment_provider": "local_mock",
        "simulation": True,
    }


def mock_pay(store, user_id, order_id):
    with store.write() as db:
        order = owned(db, "orders", order_id, user_id)
        if order["state"] == "paid":
            return order_public(order)
        # Deterministic mock transaction ID + event uniqueness protects repeated confirmations.
        transaction = "mock:" + order_id
        amount = order["amount_fen"] * 10000
        post(
            db,
            user_id,
            transaction,
            "recharge",
            order_id,
            {"available": amount, "payment_clearing": -amount},
        )
        db.execute(
            "UPDATE orders SET state='paid',paid_at=?,provider_tx=? WHERE id=?",
            (now(), transaction, order_id),
        )
        audit(db, user_id, "mock_payment_confirmed", order_id)
        return order_public(owned(db, "orders", order_id, user_id))


def create_quote(store, actor, model, inputs, project_ref):
    if model not in MODELS:
        raise Problem(422, "unknown_model", "模型未开通")
    if model == "demo/cosyvoice-characters":
        if (
            set(inputs) != {"text", "demo_outcome"}
            or not isinstance(inputs["text"], str)
            or not inputs["text"].strip()
            or not 1 <= len(inputs["text"]) <= 20000
        ):
            raise Problem(422, "invalid_input", "配音需要 1–20000 字符文本和演示结果")
        quantity = len(inputs["text"])
    else:
        if (
            set(inputs) != {"roles", "demo_outcome"}
            or type(inputs["roles"]) is not int
            or inputs["roles"] not in (1, 2)
        ):
            raise Problem(422, "invalid_input", "数字人演示支持 1 或 2 个角色")
        quantity = inputs["roles"]
    if not isinstance(inputs["demo_outcome"], str) or inputs["demo_outcome"] not in {
        "succeeded",
        "failed",
        "submission_unknown",
    }:
        raise Problem(422, "invalid_input", "未知的演示结果")
    with store.write() as db:
        require_key(db, key_id=actor["key_id"])
        price = db.execute(
            "SELECT * FROM prices WHERE model=? AND state='published' ORDER BY version DESC LIMIT 1",
            (model,),
        ).fetchone()
        rule = json.loads(price["rule"])
        estimate = calculate(model, rule, quantity)
        quote_id, expires = uid("qte"), later(600)
        # Costs stay internal; the client gets only the published customer tariff.
        snapshot = {"rule": rule, "price": public_price(price), "quantity": quantity}
        db.execute(
            "INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                quote_id,
                actor["id"],
                model,
                canonical(inputs),
                digest(canonical(inputs)),
                project_ref,
                price["id"],
                canonical(snapshot),
                int(estimate["charge_micros"]),
                now(),
                expires,
                None,
            ),
        )
        return quote_public(owned(db, "quotes", quote_id, actor["id"]))


def quote_public(row):
    snapshot = json.loads(row["snapshot"])
    return {
        "id": row["id"],
        "model": row["model"],
        "input_hash": row["input_hash"],
        "project_ref": row["project_ref"],
        "price": snapshot["price"],
        "quantity": snapshot["quantity"],
        "max_charge_micros": str(row["amount"]),
        "currency": "CNY",
        "expires_at": row["expires_at"],
        "simulation": True,
    }


def accept_job(store, actor, quote_id, max_charge, intent_id, idem):
    body = {
        "quote_id": quote_id,
        "max_charge_micros": str(max_charge),
        "call_intent_id": intent_id,
        "currency": "CNY",
        "confirmed": True,
    }
    body_hash = digest(canonical(body))
    with store.write() as db:
        key = require_key(db, key_id=actor["key_id"])
        old = db.execute(
            "SELECT * FROM idempotency WHERE user_id=? AND operation='job' AND idem_key=?",
            (actor["id"], idem),
        ).fetchone()
        if old:
            if old["body_hash"] != body_hash:
                raise Problem(409, "idempotency_conflict", "同一幂等键对应的参数已改变")
            return job_public(db, owned(db, "jobs", old["resource_id"], actor["id"]))
        intent = db.execute(
            "SELECT * FROM jobs WHERE user_id=? AND intent_id=?",
            (actor["id"], intent_id),
        ).fetchone()
        if intent:
            if intent["request_hash"] != body_hash:
                raise Problem(409, "intent_conflict", "调用意图已用于其他参数")
            db.execute(
                "INSERT INTO idempotency VALUES(?,?,?,?,?)",
                (actor["id"], "job", idem, body_hash, intent["id"]),
            )
            return job_public(db, intent)
        quote = owned(db, "quotes", quote_id, actor["id"])
        if quote["accepted_job_id"]:
            raise Problem(409, "quote_already_accepted", "该报价已接受，请查询原任务")
        if quote["expires_at"] <= now():
            raise Problem(409, "quote_expired", "报价已过期，请重新报价")
        hold = quote["amount"]
        real = db.execute(
            "SELECT available FROM commercial_wallets WHERE user_id=?", (actor["id"],)
        ).fetchone()
        available = db.execute(
            "SELECT available FROM wallets WHERE user_id=?", (actor["id"],)
        ).fetchone()[0]
        if available - (real["available"] if real else 0) < hold:
            raise Problem(
                409,
                "simulation_balance_low",
                "演示任务只能使用模拟额度，不能扣除商业额度",
            )
        if max_charge < hold:
            raise Problem(409, "ceiling_too_low", "确认上限低于报价")
        period = period_now()
        db.execute(
            "INSERT OR IGNORE INTO budgets(key_id,period) VALUES(?,?)",
            (key["id"], period),
        )
        budget = db.execute(
            "SELECT * FROM budgets WHERE key_id=? AND period=?", (key["id"], period)
        ).fetchone()
        if budget["spent"] + budget["reserved"] + hold > key["daily_limit"]:
            raise Problem(
                409, "daily_budget_exceeded", "Key 当日预算不足，冻结额度也计入预算"
            )
        job_id, timestamp = uid("job"), now()
        post(
            db,
            actor["id"],
            "reserve:" + job_id,
            "reserve",
            job_id,
            {"available": -hold, "reserved": hold},
        )
        db.execute(
            "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                actor["id"],
                key["id"],
                quote_id,
                intent_id,
                body_hash,
                period,
                "queued",
                "reserved",
                hold,
                0,
                timestamp,
                timestamp,
                None,
                None,
                None,
            ),
        )
        db.execute(
            "UPDATE budgets SET reserved=reserved+? WHERE key_id=? AND period=?",
            (hold, key["id"], period),
        )
        db.execute("UPDATE quotes SET accepted_job_id=? WHERE id=?", (job_id, quote_id))
        db.execute(
            "UPDATE api_keys SET last_used_at=? WHERE id=?", (timestamp, key["id"])
        )
        db.execute(
            "INSERT INTO idempotency VALUES(?,?,?,?,?)",
            (actor["id"], "job", idem, body_hash, job_id),
        )
        db.execute("INSERT INTO outbox VALUES(?,?)", (job_id, timestamp))
        return job_public(db, owned(db, "jobs", job_id, actor["id"]))


def job_public(db, job):
    quote = owned(db, "quotes", job["quote_id"], job["user_id"])
    snapshot = json.loads(quote["snapshot"])
    key_name = db.execute(
        "SELECT name FROM api_keys WHERE id=?", (job["key_id"],)
    ).fetchone()[0]
    result = json.loads(job["result"]) if job["result"] else None
    return {
        "id": job["id"],
        "quote_id": job["quote_id"],
        "call_intent_id": job["intent_id"],
        "key_id": job["key_id"],
        "key_name": key_name,
        "model": quote["model"],
        "model_name": MODELS[quote["model"]]["name"],
        "project_ref": quote["project_ref"],
        "status": job["status"],
        "funds_status": job["funds_status"],
        "reserved_micros": str(
            job["hold"]
            if job["funds_status"] in {"reserved", "reconciliation_pending"}
            else 0
        ),
        "max_charge_micros": str(job["hold"]),
        "charged_micros": str(job["charge"]),
        "price": snapshot["price"],
        "quantity": result["usage"]["quantity"] if result else snapshot["quantity"],
        "quoted_quantity": snapshot["quantity"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "error": job["error"],
        "result": result,
        "currency": "CNY",
        "cost_status": "estimated",
        "simulation": True,
    }


def list_jobs(store, actor, model=None, status=None):
    with store.read() as db:
        rows = db.execute(
            "SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 500",
            (actor["id"],),
        ).fetchall()
        return [
            job_public(db, r)
            for r in rows
            if (not actor.get("key_id") or r["key_id"] == actor["key_id"])
            and (
                not model
                or owned(db, "quotes", r["quote_id"], actor["id"])["model"] == model
            )
            and (not status or r["status"] == status)
        ]


def get_job(store, actor, job_id):
    with store.read() as db:
        return job_public(db, owned(db, "jobs", job_id, actor["id"]))


def finalize(db, job, outcome):
    if job["funds_status"] not in {"reserved", "reconciliation_pending"}:
        return
    quote = owned(db, "quotes", job["quote_id"], job["user_id"])
    snapshot = json.loads(quote["snapshot"])
    hold, user_id = job["hold"], job["user_id"]
    if outcome == "succeeded":
        quantity = snapshot["quantity"]
        if quote["model"] == "demo/cosyvoice-characters":
            # Simulator's meter excludes whitespace, solely to exercise unused-hold release.
            # Real CosyVoice must use the provider's usage.characters receipt instead.
            quantity = sum(
                not c.isspace() for c in json.loads(quote["input_json"])["text"]
            )
        actual = int(
            calculate(quote["model"], snapshot["rule"], quantity)["charge_micros"]
        )
        if actual > hold:
            raise ValueError("settlement exceeds accepted ceiling")
        post(
            db,
            user_id,
            "settle:" + job["id"],
            "settle",
            job["id"],
            {"reserved": -hold, "available": hold - actual, "service_revenue": actual},
        )
        result = {
            "simulation": True,
            "artifact_type": "simulation_receipt",
            "media_generated": False,
            "provider_request_id": job["submission_id"],
            "input_hash": quote["input_hash"],
            "usage": {"quantity": quantity, "unit": MODELS[quote["model"]]["unit"]},
            "message": "模拟适配器回执。没有调用第三方，也没有生成音频或视频。",
        }
        status, funds, error = "succeeded", "settled", None
    else:
        actual, result = 0, None
        post(
            db,
            user_id,
            "release:" + job["id"],
            "release",
            job["id"],
            {"reserved": -hold, "available": hold},
        )
        status, funds = outcome, "released"
        error = "模拟任务确定失败，冻结额度已释放" if outcome == "failed" else None
    db.execute(
        "UPDATE budgets SET reserved=reserved-?,spent=spent+? WHERE key_id=? AND period=?",
        (hold, actual, job["key_id"], job["period"]),
    )
    db.execute(
        "UPDATE jobs SET status=?,funds_status=?,charge=?,updated_at=?,result=?,error=? WHERE id=?",
        (
            status,
            funds,
            actual,
            now(),
            canonical(result) if result else None,
            error,
            job["id"],
        ),
    )
    db.execute("DELETE FROM outbox WHERE job_id=?", (job["id"],))


def cancel_job(store, actor, job_id):
    with store.write() as db:
        job = owned(db, "jobs", job_id, actor["id"])
        if job["status"] == "queued":
            finalize(db, job, "cancelled")
        elif job["funds_status"] in {"reserved", "reconciliation_pending"}:
            db.execute(
                "UPDATE jobs SET status='cancel_pending',updated_at=? WHERE id=?",
                (now(), job_id),
            )
        return job_public(db, owned(db, "jobs", job_id, actor["id"]))


def reconcile(store, admin_id, job_id, outcome):
    with store.write() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise Problem(404, "not_found", "任务不存在")
        if job["status"] not in {
            "submission_unknown",
            "reconciliation_pending",
            "cancel_pending",
        }:
            raise Problem(409, "not_pending", "此任务无需核对")
        # Only the simulator supports manual outcomes. Real adapters need verified provider evidence.
        finalize(db, job, outcome)
        audit(db, admin_id, "mock_reconcile_" + outcome, job_id)
        return job_public(db, owned(db, "jobs", job_id, job["user_id"]))


def ledger(store, user_id):
    with store.read() as db:
        rows = db.execute(
            "SELECT * FROM vouchers WHERE user_id=? ORDER BY created_at DESC LIMIT 500",
            (user_id,),
        ).fetchall()
        items = []
        for row in rows:
            entries = {
                r["account"]: str(r["amount"])
                for r in db.execute(
                    "SELECT * FROM postings WHERE voucher_id=?", (row["id"],)
                )
            }
            items.append(
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "reference": row["reference"],
                    "created_at": row["created_at"],
                    "available_after_micros": str(row["available_after"]),
                    "reserved_after_micros": str(row["reserved_after"]),
                    "postings": entries,
                }
            )
        return items


def verify_ledger(store):
    with store.read() as db:
        unbalanced = db.execute(
            "SELECT v.id FROM vouchers v JOIN postings p ON p.voucher_id=v.id GROUP BY v.id HAVING sum(p.amount)<>0"
        ).fetchall()
        mismatches = []
        for wallet_row in db.execute("SELECT * FROM wallets"):
            balances = dict(
                db.execute(
                    "SELECT p.account,sum(p.amount) FROM postings p JOIN vouchers v ON v.id=p.voucher_id "
                    "WHERE v.user_id=? GROUP BY p.account",
                    (wallet_row["user_id"],),
                ).fetchall()
            )
            if any(
                wallet_row[k] != balances.get(k, 0) for k in ("available", "reserved")
            ):
                mismatches.append(wallet_row["user_id"])
        commercial_mismatches = []
        for commercial_row in db.execute("SELECT * FROM commercial_wallets"):
            balances = dict(
                db.execute(
                    "SELECT p.account,sum(p.amount) FROM postings p JOIN vouchers v ON v.id=p.voucher_id "
                    "WHERE v.user_id=? AND (v.kind IN ('admin_credit','redeem_credit') OR EXISTS "
                    "(SELECT 1 FROM gateway_jobs g WHERE g.id=v.reference)) GROUP BY p.account",
                    (commercial_row["user_id"],),
                ).fetchall()
            )
            if any(
                commercial_row[k] != balances.get(k, 0)
                for k in ("available", "reserved")
            ):
                commercial_mismatches.append(commercial_row["user_id"])
        return {
            "ok": not unbalanced and not mismatches and not commercial_mismatches,
            "unbalanced_vouchers": len(unbalanced),
            "wallet_mismatches": len(mismatches),
            "commercial_wallet_mismatches": len(commercial_mismatches),
            "simulation": False,
        }


def save_price(store, admin_id, model, rule):
    clean = normalize_rule(model, rule)
    with store.write() as db:
        version = db.execute(
            "SELECT coalesce(max(version),0)+1 FROM prices WHERE model=?", (model,)
        ).fetchone()[0]
        price_id = uid("prc")
        db.execute(
            "INSERT INTO prices VALUES(?,?,?,?,?,?,?,?)",
            (
                price_id,
                model,
                version,
                "draft",
                canonical(clean),
                now(),
                None,
                admin_id,
            ),
        )
        audit(db, admin_id, "draft_price", price_id)
        return {
            "id": price_id,
            "version": version,
            "state": "draft",
            "model": model,
            "rule": clean,
        }


def publish_price(store, admin_id, price_id):
    with store.write() as db:
        price = db.execute("SELECT * FROM prices WHERE id=?", (price_id,)).fetchone()
        if not price:
            raise Problem(404, "not_found", "价格草稿不存在")
        if price["state"] == "published":
            return public_price(price)
        latest = (
            db.execute(
                "SELECT max(version) FROM prices WHERE model=? AND state='published'",
                (price["model"],),
            ).fetchone()[0]
            or 0
        )
        if price["version"] < latest:
            raise Problem(409, "superseded_draft", "已有更高版本发布，请创建新草稿")
        db.execute(
            "UPDATE prices SET state='published',published_at=? WHERE id=?",
            (now(), price_id),
        )
        audit(db, admin_id, "publish_price", price_id)
        return public_price(
            db.execute("SELECT * FROM prices WHERE id=?", (price_id,)).fetchone()
        )
