"""Customer funding. Redeem codes and credits share a serialized ledger transaction."""

import secrets
import sqlite3

from . import funding
from .auth import ensure_active, password_hash, public_user
from .store import Problem, audit, canonical, digest, later, now, post, uid


def commercial(db, user_id):
    db.execute(
        "INSERT OR IGNORE INTO commercial_wallets(user_id) VALUES(?)", (user_id,)
    )
    return db.execute(
        "SELECT * FROM commercial_wallets WHERE user_id=?", (user_id,)
    ).fetchone()


def fund(db, user_id, amount, event, kind, reference):
    commercial(db, user_id)
    voucher = post(
        db,
        user_id,
        event,
        kind,
        reference,
        {"available": amount, "merchant_credit": -amount},
    )
    db.execute(
        "UPDATE commercial_wallets SET available=available+? WHERE user_id=?",
        (amount, user_id),
    )
    return voucher


def create_customer(store, actor, email, name, password):
    email = email.strip().lower()
    name = name or email
    hashed = password_hash(password)
    with store.write() as db:
        user_id = uid("usr")
        try:
            db.execute(
                "INSERT INTO users VALUES(?,?,?,?,?,?)",
                (user_id, email, name, hashed, "customer", now()),
            )
        except sqlite3.IntegrityError:
            raise Problem(409, "username_exists", "用户名已被使用") from None
        db.execute("INSERT INTO wallets(user_id) VALUES(?)", (user_id,))
        commercial(db, user_id)
        db.execute(
            "INSERT INTO user_access(user_id,must_change_password) VALUES(?,1)",
            (user_id,),
        )
        audit(db, actor, "create_customer", user_id)
        created = dict(
            db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        )
        return public_user({**created, "must_change_password": 1})


def credit(
    store, actor, user_id, amount, note, idem, channel="private", payment_ref=""
):
    body = {"user": user_id, "amount": amount, "note": note}
    if channel != "private" or payment_ref:
        body.update(channel=channel, payment_ref=payment_ref)
    body_hash = digest(canonical(body))
    with store.write() as db:
        prior = db.execute(
            "SELECT * FROM idempotency WHERE user_id=? AND operation='admin_credit' AND idem_key=?",
            (actor, idem),
        ).fetchone()
        if prior:
            if prior["body_hash"] != body_hash:
                raise Problem(409, "idempotency_conflict", "同一请求不能改变充值内容")
            return dict(
                db.execute(
                    "SELECT * FROM credit_grants WHERE id=?", (prior["resource_id"],)
                ).fetchone()
            )
        if not db.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone():
            raise Problem(404, "not_found", "用户不存在")
        ensure_active(db, user_id)
        receipt_id = funding.receipt(
            db, actor, user_id, "manual", amount, channel, payment_ref, note
        )
        grant = uid("credit")
        voucher = fund(db, user_id, amount, "credit:" + grant, "admin_credit", grant)
        db.execute(
            "INSERT INTO credit_grants VALUES(?,?,?,?,?,?,?)",
            (grant, user_id, actor, amount, note, now(), voucher),
        )
        db.execute(
            "INSERT INTO idempotency VALUES(?,?,?,?,?)",
            (actor, "admin_credit", idem, body_hash, grant),
        )
        funding.link(db, grant, receipt_id)
        audit(db, actor, "credit_customer", grant)
        return dict(
            db.execute("SELECT * FROM credit_grants WHERE id=?", (grant,)).fetchone()
        )


def code_public(row):
    result = {
        k: str(row[k]) if k == "amount" else row[k]
        for k in (
            "id",
            "prefix",
            "amount",
            "batch",
            "created_at",
            "expires_at",
            "bound_user_id",
            "redeemed_by",
            "redeemed_at",
            "revoked_at",
        )
    }
    result["replacement_id"] = dict(row).get("replacement_id")
    return result


def reissue_code(store, actor, code_id):
    with store.write() as db:
        old = db.execute("SELECT * FROM redeem_codes WHERE id=?", (code_id,)).fetchone()
        if not old:
            raise Problem(404, "not_found", "兑换码不存在")
        prior = db.execute(
            "SELECT new_code_id FROM redeem_replacements WHERE old_code_id=?",
            (code_id,),
        ).fetchone()
        if prior:
            row = db.execute(
                "SELECT * FROM redeem_codes WHERE id=?", (prior["new_code_id"],)
            ).fetchone()
            return {"items": [code_public(row)], "show_once": False, "replayed": True}
        if old["redeemed_at"] or old["revoked_at"] or old["expires_at"] <= now():
            raise Problem(
                409, "code_inactive", "只可重新签发未使用、未作废且未过期的兑换码"
            )
        if old["bound_user_id"]:
            ensure_active(db, old["bound_user_id"])
        secret, new_id = "HK-" + secrets.token_hex(16).upper(), uid("redeem")
        db.execute(
            "INSERT INTO redeem_codes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                new_id,
                digest(secret),
                secret[:10],
                old["amount"],
                old["batch"],
                actor,
                now(),
                old["expires_at"],
                old["bound_user_id"],
                None,
                None,
                None,
            ),
        )
        db.execute("UPDATE redeem_codes SET revoked_at=? WHERE id=?", (now(), code_id))
        db.execute("INSERT INTO redeem_replacements VALUES(?,?)", (code_id, new_id))
        source = db.execute(
            "SELECT receipt_id FROM funding_sources WHERE resource_id=?", (code_id,)
        ).fetchone()
        if source:
            funding.link(db, new_id, source["receipt_id"])
        audit(db, actor, "reissue_redeem_code", code_id + ":" + new_id)
        row = db.execute("SELECT * FROM redeem_codes WHERE id=?", (new_id,)).fetchone()
        return {"items": [{**code_public(row), "code": secret}], "show_once": True}


def issue_codes(
    store,
    actor,
    amount,
    count,
    days,
    batch,
    bound_user,
    channel="private",
    payment_ref="",
    note="",
    idem=None,
):
    with store.write() as db:
        body_hash = digest(
            canonical(
                [amount, count, days, batch, bound_user, channel, payment_ref, note]
            )
        )
        if idem:
            prior = db.execute(
                "SELECT * FROM idempotency WHERE user_id=? AND operation='issue_codes' AND idem_key=?",
                (actor, idem),
            ).fetchone()
            if prior:
                if prior["body_hash"] != body_hash:
                    raise Problem(
                        409, "idempotency_conflict", "同一请求不能改变发码内容"
                    )
                rows = db.execute(
                    "SELECT c.* FROM redeem_codes c JOIN funding_sources s ON s.resource_id=c.id WHERE s.receipt_id=? AND NOT EXISTS(SELECT 1 FROM redeem_replacements r WHERE r.old_code_id=c.id)",
                    (prior["resource_id"],),
                ).fetchall()
                return {
                    "items": [code_public(r) for r in rows],
                    "show_once": False,
                    "replayed": True,
                }
        if (
            bound_user
            and not db.execute(
                "SELECT id FROM users WHERE id=?", (bound_user,)
            ).fetchone()
        ):
            raise Problem(404, "not_found", "绑定用户不存在")
        if bound_user:
            ensure_active(db, bound_user)
        receipt_id = funding.receipt(
            db,
            actor,
            bound_user,
            "codes",
            amount * count,
            channel,
            payment_ref,
            note or batch,
        )
        result = []
        for _ in range(count):
            secret, code_id = "HK-" + secrets.token_hex(16).upper(), uid("redeem")
            db.execute(
                "INSERT INTO redeem_codes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    code_id,
                    digest(secret),
                    secret[:10],
                    amount,
                    batch,
                    actor,
                    now(),
                    later(days * 86400),
                    bound_user,
                    None,
                    None,
                    None,
                ),
            )
            result.append(
                {
                    **code_public(
                        db.execute(
                            "SELECT * FROM redeem_codes WHERE id=?", (code_id,)
                        ).fetchone()
                    ),
                    "code": secret,
                }
            )
            funding.link(db, code_id, receipt_id)
        if idem:
            db.execute(
                "INSERT INTO idempotency VALUES(?,?,?,?,?)",
                (actor, "issue_codes", idem, body_hash, receipt_id),
            )
        audit(db, actor, "issue_redeem_codes", batch)
        return {"items": result, "show_once": True}


def validate_code(db, user_id, secret, redeemed_ok=False):
    row = db.execute(
        "SELECT * FROM redeem_codes WHERE code_hash=?",
        (digest(secret.strip().upper()),),
    ).fetchone()
    if not row or (row["bound_user_id"] and row["bound_user_id"] != user_id):
        raise Problem(404, "invalid_code", "兑换码不存在或不属于当前账户")
    if row["redeemed_by"]:
        if redeemed_ok and row["redeemed_by"] == user_id:
            return row
        raise Problem(409, "code_used", "兑换码已被领取")
    if row["revoked_at"] or row["expires_at"] <= now():
        raise Problem(409, "code_inactive", "兑换码已作废或过期")
    return row


def redeem(store, user_id, secret, preview=False):
    with store.write() as db:
        ensure_active(db, user_id, api=True)
        row = validate_code(db, user_id, secret, redeemed_ok=not preview)
        if not preview and not row["redeemed_by"]:
            fund(
                db,
                user_id,
                row["amount"],
                "redeem:" + row["id"],
                "redeem_credit",
                row["id"],
            )
            db.execute(
                "UPDATE redeem_codes SET redeemed_by=?,redeemed_at=? WHERE id=?",
                (user_id, now(), row["id"]),
            )
            audit(db, user_id, "redeem_credit", row["id"])
        return {
            "amount_micros": str(row["amount"]),
            "expires_at": row["expires_at"],
            "redeemed": not preview,
        }


def users(store, search=""):
    with store.read() as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT u.id,u.email,u.name,u.role,u.created_at,coalesce(x.status,'active') status,coalesce(x.must_change_password,0) must_change_password,CAST(w.available AS TEXT) available_micros,CAST(coalesce(c.reserved,0) AS TEXT) reserved_micros,CAST(coalesce(c.available,0) AS TEXT) commercial_available_micros FROM users u JOIN wallets w ON w.user_id=u.id LEFT JOIN commercial_wallets c ON c.user_id=u.id LEFT JOIN user_access x ON x.user_id=u.id WHERE instr(lower(u.email || ' ' || u.name || ' ' || u.id),lower(?))>0 ORDER BY u.created_at DESC LIMIT 500",
                (search.strip(),),
            )
        ]
