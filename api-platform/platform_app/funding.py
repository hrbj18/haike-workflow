"""Private-channel payment evidence, separate from API usage charges."""

import sqlite3

from .store import Problem, audit, now, uid

CHANNELS = {
    "wechat": "微信私域",
    "alipay": "支付宝",
    "bank": "银行转账",
    "private": "其他私域渠道",
}


def info(store):
    with store.read() as db:
        row = db.execute(
            "SELECT contact,instructions FROM funding_settings WHERE id=1"
        ).fetchone()
    return (
        dict(row)
        if row
        else {
            "contact": "请通过原私域渠道联系管理员",
            "instructions": "提供用户名和充值金额，完成线下付款后，由管理员确认收款并手动入账或发放兑换码。",
        }
    )


def configure(store, actor, contact, instructions):
    if not contact.strip() or not instructions.strip():
        raise Problem(422, "empty_funding_info", "请填写联系方式和充值说明")
    with store.write() as db:
        db.execute(
            "INSERT INTO funding_settings VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET contact=excluded.contact,instructions=excluded.instructions",
            (contact.strip(), instructions.strip()),
        )
        audit(db, actor, "update_funding_info", "funding_settings")
    return info(store)


def receipt(db, actor, user_id, kind, amount, channel, payment_ref, note):
    if channel not in CHANNELS or not note.strip():
        raise Problem(422, "invalid_funding", "请选择收款渠道并填写入账说明")
    receipt_id = uid("fund")
    try:
        db.execute(
            "INSERT INTO funding_receipts VALUES(?,?,?,?,?,?,?,?,?)",
            (
                receipt_id,
                actor,
                user_id,
                kind,
                amount,
                channel,
                payment_ref.strip() or None,
                note.strip(),
                now(),
            ),
        )
    except sqlite3.IntegrityError:
        raise Problem(
            409,
            "payment_already_recorded",
            "该收款凭证已用于充值或发码，请核对充值记录，不能再次入账",
        ) from None
    return receipt_id


def link(db, resource_id, receipt_id):
    db.execute("INSERT INTO funding_sources VALUES(?,?)", (resource_id, receipt_id))


def history(store, user_id=None):
    """Only actual credited vouchers appear in the customer's recharge history."""
    with store.read() as db:
        rows = db.execute(
            "SELECT v.id,v.reference,v.user_id,v.kind,v.created_at,CAST(p.amount AS TEXT) amount_micros,"
            "u.email,u.name,coalesce(f.channel,'private') channel,coalesce(f.payment_ref,'') payment_ref,"
            "coalesce(f.note,g.note,c.batch,'') note,coalesce(a.name,'管理员') operator "
            "FROM vouchers v JOIN postings p ON p.voucher_id=v.id AND p.account='available' "
            "JOIN users u ON u.id=v.user_id LEFT JOIN credit_grants g ON g.id=v.reference "
            "LEFT JOIN redeem_codes c ON c.id=v.reference LEFT JOIN funding_sources s ON s.resource_id=v.reference "
            "LEFT JOIN funding_receipts f ON f.id=s.receipt_id "
            "LEFT JOIN users a ON a.id=coalesce(g.actor_id,c.author_id) "
            "WHERE v.kind IN ('admin_credit','redeem_credit') AND (? IS NULL OR v.user_id=?) "
            "ORDER BY v.created_at DESC LIMIT 500",
            (user_id, user_id),
        ).fetchall()
    items = [dict(r) for r in rows]
    if user_id is not None:
        # The private-channel receipt belongs to the merchant; never expose bank references to customers.
        for item in items:
            item.pop("payment_ref")
            item.pop("note")
    return items


def receipts(store):
    with store.read() as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT f.id,f.kind,CAST(f.amount AS TEXT) amount_micros,f.channel,f.payment_ref,f.note,f.created_at,"
                "a.name operator,u.email,u.name,"
            "(SELECT count(*) FROM funding_sources s JOIN redeem_codes c ON c.id=s.resource_id WHERE s.receipt_id=f.id AND NOT EXISTS(SELECT 1 FROM redeem_replacements r WHERE r.old_code_id=c.id)) code_count,"
                "(SELECT count(*) FROM funding_sources s JOIN redeem_codes c ON c.id=s.resource_id WHERE s.receipt_id=f.id AND c.redeemed_at IS NOT NULL) redeemed_count "
                "FROM funding_receipts f JOIN users a ON a.id=f.actor_id LEFT JOIN users u ON u.id=f.user_id "
                "ORDER BY f.created_at DESC LIMIT 500"
            )
        ]
