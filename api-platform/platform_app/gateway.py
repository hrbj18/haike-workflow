"""Unified provider gateway: frozen quotes, commercial funding and recoverable tasks."""

import asyncio
import io
import json
import math
import wave
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from . import adapters, commerce, providers
from .auth import require_key
from .domain import period_now
from .store import Problem, audit, canonical, digest, later, now, owned, post, uid


def upload(store, user_id, kind, data):
    if kind not in {"audio", "image"} or not data or len(data) > 5 * 1024 * 1024:
        raise Problem(422, "file_invalid", "支持 5MB 内的 WAV 音频、PNG/JPEG 图像")
    seconds, frames = None, None
    if kind == "audio":
        try:
            with wave.open(io.BytesIO(data)) as wav:
                if (
                    wav.getnchannels() != 1
                    or wav.getsampwidth() != 2
                    or wav.getframerate() not in {16000, 24000, 32000, 48000}
                ):
                    raise ValueError()
                count, rate = wav.getnframes(), wav.getframerate()
                samples = wav.readframes(count)
                if count <= 0 or len(samples) != count * 2:
                    raise ValueError()
                seconds, frames = math.ceil(count / rate), math.ceil(count * 25 / rate)
                aligned_count = frames * (rate // 25)
                if aligned_count != count:
                    buffer = io.BytesIO()
                    with wave.open(buffer, "wb") as aligned:
                        aligned.setnchannels(1)
                        aligned.setsampwidth(2)
                        aligned.setframerate(rate)
                        aligned.writeframes(samples + b"\0\0" * (aligned_count - count))
                    data = buffer.getvalue()
        except (wave.Error, EOFError, ValueError):
            raise Problem(
                422, "audio_invalid", "请上传完整的单声道 16 位 PCM WAV 音频"
            ) from None
        if len(data) > 5 * 1024 * 1024:
            raise Problem(422, "file_invalid", "音频帧时钟对齐后超过 5MB，请缩短音频")
    elif not data.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
        raise Problem(422, "image_invalid", "图片需要 PNG 或 JPEG 格式")
    file_id = uid("file")
    with store.write() as db:
        total = db.execute(
            "SELECT coalesce(sum(size),0) FROM gateway_files WHERE user_id=?",
            (user_id,),
        ).fetchone()[0]
        if total + len(data) > 100 * 1024 * 1024:
            raise Problem(409, "file_quota", "本地上传额度已用完，请联系管理员清理")
        directory = store.path.parent / "files"
        directory.mkdir(exist_ok=True)
        path = directory / file_id
        path.write_bytes(data)
        path.chmod(0o600)
        db.execute(
            "INSERT INTO gateway_files VALUES(?,?,?,?,?,?,?)",
            (file_id, user_id, kind, len(data), seconds, frames, now()),
        )
    return {"id": file_id, "kind": kind, "seconds": seconds, "total_frames": frames}


def clean_input(db, user_id, model, value, info=None):
    capability = (info or providers.MODELS[model])["capability"]
    value = dict(value)
    if capability == "image":
        if set(value) != {"prompt"} or not isinstance(value.get("prompt"), str) or not 1 <= len(value["prompt"]) <= 4000:
            raise Problem(422, "input_invalid", "插画接口仅接收1至4,000字的prompt，一次生成一张竖屏插画")
        return value, {"input_tokens": len(value["prompt"].encode()) * 2 + 1024, "output_tokens": 32768}
    if capability == "chat":
        if set(value) - {"messages", "max_output_tokens"}:
            raise Problem(
                422, "input_invalid", "文本接口只接收 messages 和 max_output_tokens"
            )
        messages, maximum = value.get("messages"), value.get("max_output_tokens", 2048)
        if (
            not isinstance(messages, list)
            or not 1 <= len(messages) <= 60
            or type(maximum) is not int
            or not 1 <= maximum <= 8192
        ):
            raise Problem(422, "input_invalid", "对话参数不正确")
        images = 0
        for message in messages:
            if (
                not isinstance(message, dict)
                or set(message) != {"role", "content"}
                or message["role"] not in {"system", "user", "assistant"}
            ):
                raise Problem(422, "input_invalid", "对话消息格式不正确")
            content = message["content"]
            if isinstance(content, str):
                continue
            if not isinstance(content, list) or not 1 <= len(content) <= 10:
                raise Problem(
                    422, "input_invalid", "支持文本，或 text/image_file 内容数组"
                )
            for part in content:
                if not isinstance(part, dict):
                    raise Problem(422, "input_invalid", "消息内容格式不正确")
                if (
                    part.get("type") == "text"
                    and set(part) == {"type", "text"}
                    and isinstance(part["text"], str)
                ):
                    continue
                if (
                    part.get("type") != "image_file"
                    or set(part) != {"type", "file_id"}
                    or not isinstance(part["file_id"], str)
                ):
                    raise Problem(
                        422, "input_invalid", "视觉消息需要当前账户上传的图片编号"
                    )
                if not db.execute(
                    "SELECT id FROM gateway_files WHERE id=? AND user_id=? AND kind='image'",
                    (part["file_id"], user_id),
                ).fetchone():
                    raise Problem(404, "file_missing", "图片不存在或不属于当前账户")
                images += 1
        if images > 4:
            raise Problem(422, "input_invalid", "单次视觉调用最多 4 张图片")
        size = len(canonical(messages).encode())
        if size > 60000:
            raise Problem(422, "input_invalid", "对话文本过长")
        # A conservative byte bound; settlement always uses the upstream token receipt.
        return {"messages": messages, "max_output_tokens": maximum}, {
            "input_tokens": size * 2 + 1024 + images * 32768,
            "output_tokens": maximum,
        }
    if capability == "tts":
        text = value.get("text")
        maximum = 150 if model == "haike/tencent-tts" else 5000
        if (
            set(value) != {"text"}
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > maximum
        ):
            raise Problem(422, "input_invalid", f"请输入 1–{maximum} 个字符的配音文本")
        characters = (
            providers.bailian_tts_characters(text)
            if model == "haike/cosyvoice"
            else len(text)
        )
        return value, {"characters": characters}
    if capability == "assets":
        if (
            set(value) - {"query", "media", "per_page"}
            or not isinstance(value.get("query"), str)
            or not 1 <= len(value["query"]) <= 100
        ):
            raise Problem(422, "input_invalid", "请输入素材关键词")
        media, per_page = value.get("media", "videos"), value.get("per_page", 10)
        if (
            media not in {"videos", "photos"}
            or type(per_page) is not int
            or not 1 <= per_page <= 30
        ):
            raise Problem(422, "input_invalid", "素材筛选条件不正确")
        return {"query": value["query"], "media": media, "per_page": per_page}, {
            "requests": 1
        }
    fields = {"audio_file"} if capability == "asr" else {"audio_file", "image_file"}
    if set(value) != fields:
        raise Problem(
            422, "input_invalid", "请先通过 /v2/files 上传文件，再提交文件编号"
        )
    for field in fields:
        file = db.execute(
            "SELECT * FROM gateway_files WHERE id=? AND user_id=? AND kind=?",
            (value[field], user_id, field.split("_")[0]),
        ).fetchone()
        if not file:
            raise Problem(404, "file_missing", "文件不存在或不属于当前账户")
        if field == "audio_file":
            value["seconds"], value["total_frames"] = (
                file["duration_seconds"],
                file["total_frames"],
            )
    return value, {"seconds": value["seconds"]} if capability == "asr" else {"tasks": 1}


def create_quote(store, vault, user, model, inputs, project):
    info = vault.models().get(model)
    if not info:
        raise Problem(404, "model_missing", "模型不存在")
    current = next(r for r in providers.catalogue(store, vault) if r["model"] == model)
    if current["status"] != "available":
        raise Problem(409, "model_unavailable", "模型尚未开通或成本价格尚未确认")
    with store.write() as db:
        inputs, usage = clean_input(db, user["id"], model, inputs, info)
        price = providers.latest(db, model)
        _, amount = providers.calculate(model, json.loads(price["rule"]), usage, info)
        if amount > 10**12:
            raise Problem(422, "quote_limit", "报价超过单次限额")
        quote_id = uid("gquote")
        snapshot = {
            "price": providers.price_public(model, price, info),
            "model_info": info,
            "rule": json.loads(price["rule"]),
            "usage": usage,
            "provider_config": {
                k: v
                for k, v in vault.load().get(info["provider"], {}).items()
                if k
                in {
                    "base_url",
                    "region",
                    "text_model",
                    "image_model",
                    "voice",
                    "workflow_id",
                    "workflow_profile",
                }
            },
        }
        if model not in providers.MODELS:
            snapshot["provider_config"]["text_model"] = info["target_model"]
        db.execute(
            "INSERT INTO gateway_quotes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                quote_id,
                user["id"],
                model,
                canonical(inputs),
                price["id"],
                canonical(snapshot),
                amount,
                project,
                now(),
                later(600),
                None,
            ),
        )
        return quote_public(
            db.execute(
                "SELECT * FROM gateway_quotes WHERE id=?", (quote_id,)
            ).fetchone()
        )


def quote_public(row):
    snapshot = json.loads(row["snapshot"])
    return {
        "id": row["id"],
        "model": row["model"],
        "price": snapshot["price"],
        "quantity": sum(snapshot["usage"].values()),
        "quoted_usage": snapshot["usage"],
        "max_charge_micros": str(row["amount"]),
        "expires_at": row["expires_at"],
        "simulation": False,
    }


def renew_quote(store, vault, user, quote_id):
    """Extend only the acceptance clock, retaining the exact tariff/provider snapshot.

    An accepted quote returns unchanged so callers recover the original intent.
    Never clone a quote (quote_id is unique in jobs); never prolong beyond 24h.
    """
    with store.write() as db:
        row = owned(db, "gateway_quotes", quote_id, user["id"])
        if row["accepted_job_id"]:
            return quote_public(row)
        current = next((r for r in providers.catalogue(store, vault) if r["model"] == row["model"]), None)
        if not current or current["status"] != "available":
            raise Problem(409, "model_unavailable", "原模型尚未开通，不能续期")
        deadline = datetime.fromisoformat(row["created_at"]) + timedelta(hours=24)
        if datetime.fromisoformat(now()) >= deadline:
            raise Problem(409, "quote_too_old", "原报价超过24小时，请重新确认制作费用，已完成产物保留")
        expiry = min(datetime.fromisoformat(later(600)), deadline).isoformat(timespec="microseconds")
        db.execute("UPDATE gateway_quotes SET expires_at=? WHERE id=?", (expiry, quote_id))
        audit(db, user["id"], "renew_gateway_quote", quote_id)
        return quote_public(db.execute("SELECT * FROM gateway_quotes WHERE id=?", (quote_id,)).fetchone())


def billing_detail(snapshot, usage, job, admin=False):
    """Derive auditable line items from the immutable tariff, never today's price."""
    rule = snapshot["rule"]
    settled = job["status"] == "succeeded"
    lines, exact_total = [], Decimal(0)
    for rate in snapshot["price"]["rates"]:
        meter, included = rate["meter"], rate["included_units"]
        unit_price = Decimal(rule["costs"][meter]) * Decimal(rule["multiplier"])
        quantity = usage.get(meter) if settled else None
        subtotal = unit_price * quantity / included if quantity is not None else None
        amount = (
            int(subtotal.to_integral_value(rounding=ROUND_CEILING))
            if subtotal is not None
            else None
        )
        line = {
            "meter": meter,
            "unit": rate["unit"],
            "quantity": quantity,
            "included_units": included,
            "unit_price_micros": format(unit_price, "f"),
            "amount_micros": str(amount) if amount is not None else None,
        }
        if admin:
            line["unit_cost_micros"] = rule["costs"][meter]
        lines.append(line)
        if subtotal is not None:
            exact_total += subtotal
    total = (
        int(
            (exact_total + int(rule["fee_micros"])).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        if settled
        else 0
    )
    return {
        "multiplier": rule["multiplier"],
        "lines": lines,
        "fee_micros": rule["fee_micros"],
        "calculated_micros": str(total),
        "rounding_adjustment_micros": str(
            total
            - int(rule["fee_micros"])
            - sum(int(r["amount_micros"] or 0) for r in lines)
        )
        if settled
        else "0",
        "ceiling_discount_micros": str(max(0, total - job["charge"])),
        "released_micros": str(job["hold"] - job["charge"])
        if job["status"] in {"succeeded", "failed", "cancelled"}
        else "0",
        "rounding": "逐项展示向上取整至微元；合计仅舍入一次，差额单列",
        "usage_status": "confirmed"
        if settled
        else "released"
        if job["status"] in {"failed", "cancelled"}
        else "pending",
    }


def public_job(db, job, admin=False):
    quote = owned(db, "gateway_quotes", job["quote_id"], job["user_id"])
    snapshot = json.loads(quote["snapshot"])
    info = snapshot.get("model_info") or providers.MODELS[quote["model"]]
    key = db.execute(
        "SELECT name FROM api_keys WHERE id=?", (job["key_id"],)
    ).fetchone()
    usage = json.loads(job["usage_json"]) if job["usage_json"] else {}
    terminal = job["status"] in {"succeeded", "failed", "cancelled"}
    item = {
        "id": job["id"],
        "model": quote["model"],
        "model_name": info["name"],
        "key_name": key["name"],
        "project_ref": quote["project_ref"],
        "status": job["status"],
        "funds_status": "settled"
        if job["status"] == "succeeded"
        else "released"
        if terminal
        else "reconciliation_pending"
        if job["status"] == "submission_unknown"
        else "reserved",
        "quantity": sum(usage.values()) if usage else sum(snapshot["usage"].values()),
        "usage": usage,
        "quoted_usage": snapshot["usage"],
        "price": snapshot["price"],
        "max_charge_micros": str(job["hold"]),
        "reserved_micros": "0" if terminal else str(job["hold"]),
        "charged_micros": str(job["charge"]),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "upstream_id": job["upstream_id"],
        "result": json.loads(job["result_json"]) if job["result_json"] else None,
        "error": job["error"],
        "simulation": False,
        "cost_status": "estimated",
        "media_artifact_available": bool(job["result_json"])
        and info["capability"] in {"tts", "avatar"},
    }
    item["billing"] = billing_detail(snapshot, usage, job, admin)
    item["ledger"] = [
        {
            "id": row["id"],
            "kind": row["kind"],
            "created_at": row["created_at"],
            "available_after_micros": str(row["available_after"]),
            "reserved_after_micros": str(row["reserved_after"]),
            "postings": {
                p["account"]: str(p["amount"])
                for p in db.execute(
                    "SELECT account,amount FROM postings WHERE voucher_id=?",
                    (row["id"],),
                )
            },
        }
        for row in db.execute(
            "SELECT * FROM vouchers WHERE user_id=? AND reference=? ORDER BY rowid",
            (job["user_id"], job["id"]),
        )
    ]
    if admin:
        account = db.execute(
            "SELECT email,name FROM users WHERE id=?", (job["user_id"],)
        ).fetchone()
        item["account_email"], item["account_name"] = account["email"], account["name"]
        item["estimated_cost_micros"] = (
            str(job["cost"]) if job["cost"] is not None else None
        )
        item["estimated_profit_micros"] = (
            str(job["charge"] - job["cost"]) if job["cost"] is not None else None
        )
        item["cost_basis"] = snapshot["rule"]["cost_basis"]
    return item


def get_job(store, user, job_id, admin=False):
    with store.read() as db:
        row = db.execute(
            "SELECT * FROM gateway_jobs WHERE id=?"
            + ("" if admin else " AND user_id=?"),
            (job_id,) if admin else (job_id, user["id"]),
        ).fetchone()
        if not row:
            raise Problem(404, "not_found", "任务不存在")
        return public_job(db, row, admin)


def list_jobs(store, user, model=None, status=None, admin=False):
    with store.read() as db:
        conditions, args = [], []
        if not admin:
            conditions.append("j.user_id=?")
            args.append(user["id"])
        if model:
            conditions.append("q.model=?")
            args.append(model)
        if status:
            conditions.append("j.status=?")
            args.append(status)
        rows = db.execute(
            "SELECT j.* FROM gateway_jobs j JOIN gateway_quotes q ON q.id=j.quote_id"
            + (" WHERE " + " AND ".join(conditions) if conditions else "")
            + " ORDER BY j.created_at DESC, j.rowid DESC LIMIT 500",
            args,
        ).fetchall()
        items = [public_job(db, r, admin) for r in rows]
    return [
        j
        for j in items
        if (not model or j["model"] == model) and (not status or j["status"] == status)
    ]


def accept(store, vault, user, quote_id, maximum, intent, idem):
    body_hash = digest(
        canonical(
            {
                "quote_id": quote_id,
                "max_charge_micros": str(maximum),
                "call_intent_id": intent,
                "currency": "CNY",
                "confirmed": True,
            }
        )
    )
    with store.write() as db:
        require_key(db, key_id=user["key_id"])
        prior = db.execute(
            "SELECT * FROM idempotency WHERE user_id=? AND operation='job' AND idem_key=?",
            (user["id"], idem),
        ).fetchone()
        previous = db.execute(
            "SELECT * FROM gateway_jobs WHERE user_id=? AND intent_id=?",
            (user["id"], intent),
        ).fetchone()
        if prior or previous:
            expected = prior["body_hash"] if prior else previous["body_hash"]
            if expected != body_hash:
                raise Problem(409, "idempotency_conflict", "请求编号已用于其他参数")
            result_id = prior["resource_id"] if prior else previous["id"]
            if not prior:
                db.execute(
                    "INSERT INTO idempotency VALUES(?,?,?,?,?)",
                    (user["id"], "job", idem, body_hash, result_id),
                )
            return public_job(db, owned(db, "gateway_jobs", result_id, user["id"]))
        quote = owned(db, "gateway_quotes", quote_id, user["id"])
        if quote["accepted_job_id"] or quote["expires_at"] <= now():
            raise Problem(409, "quote_inactive", "报价已使用或已过期，请重新报价")
        snapshot = json.loads(quote["snapshot"])
        info = snapshot.get("model_info") or providers.MODELS[quote["model"]]
        config = vault.load().get(info["provider"], {})
        current = vault.models().get(quote["model"], {})
        if not config.get("enabled", False) or not current.get("enabled", True):
            raise Problem(409, "provider_disabled", "供应商已暂停调用")
        hold = quote["amount"]
        if maximum < hold:
            raise Problem(409, "maximum_low", "费用上限低于本次报价")
        funds = commerce.commercial(db, user["id"])
        if funds["available"] < hold:
            raise Problem(
                409,
                "commercial_balance_low",
                "商业额度不足，请由管理员充值或兑换额度；模拟额度不能支付真实调用",
            )
        period = period_now()
        key = require_key(db, key_id=user["key_id"])
        db.execute(
            "INSERT OR IGNORE INTO budgets(key_id,period) VALUES(?,?)",
            (user["key_id"], period),
        )
        budget = db.execute(
            "SELECT * FROM budgets WHERE key_id=? AND period=?",
            (user["key_id"], period),
        ).fetchone()
        if budget["reserved"] + budget["spent"] + hold > key["daily_limit"]:
            raise Problem(409, "daily_limit", "调用超过 Key 的每日预算")
        job_id = uid("gj")
        post(
            db,
            user["id"],
            "reserve:" + job_id,
            "reserve",
            job_id,
            {"available": -hold, "reserved": hold},
        )
        db.execute(
            "UPDATE commercial_wallets SET available=available-?,reserved=reserved+? WHERE user_id=?",
            (hold, hold, user["id"]),
        )
        db.execute(
            "UPDATE budgets SET reserved=reserved+? WHERE key_id=? AND period=?",
            (hold, user["key_id"], period),
        )
        db.execute(
            "INSERT INTO gateway_jobs(id,user_id,key_id,quote_id,intent_id,body_hash,period,status,hold,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                user["id"],
                user["key_id"],
                quote_id,
                intent,
                body_hash,
                period,
                "queued",
                hold,
                now(),
                now(),
            ),
        )
        db.execute(
            "UPDATE gateway_quotes SET accepted_job_id=? WHERE id=?", (job_id, quote_id)
        )
        db.execute(
            "INSERT INTO idempotency VALUES(?,?,?,?,?)",
            (user["id"], "job", idem, body_hash, job_id),
        )
        db.execute(
            "UPDATE api_keys SET last_used_at=? WHERE id=?", (now(), user["key_id"])
        )
        return public_job(db, owned(db, "gateway_jobs", job_id, user["id"]))


def finish(db, job, response):
    if job["status"] in {"succeeded", "failed", "cancelled"}:
        return
    quote = owned(db, "gateway_quotes", job["quote_id"], job["user_id"])
    snapshot = json.loads(quote["snapshot"])
    info = snapshot.get("model_info") or providers.MODELS[quote["model"]]
    usage = response.get("usage", {})
    failed = response.get("failed", False) or response.get("cancelled", False)
    if not failed and set(usage) != set(info["meters"]):
        raise Problem(409, "receipt_incomplete", "供应商用量回执不完整，等待核对")
    cost, charge = (
        (None, 0)
        if failed
        else providers.calculate(quote["model"], snapshot["rule"], usage, info)
    )
    # Provider overrun is the merchant's risk: customer cannot exceed their frozen quote.
    charge = min(charge, job["hold"])
    post(
        db,
        job["user_id"],
        "final:" + job["id"],
        "release" if failed else "settle",
        job["id"],
        {
            "reserved": -job["hold"],
            "available": job["hold"] - charge,
            "service_revenue": charge,
        },
    )
    db.execute(
        "UPDATE commercial_wallets SET reserved=reserved-?,available=available+? WHERE user_id=?",
        (job["hold"], job["hold"] - charge, job["user_id"]),
    )
    db.execute(
        "UPDATE budgets SET reserved=reserved-?,spent=spent+? WHERE key_id=? AND period=?",
        (job["hold"], charge, job["key_id"], job["period"]),
    )
    status = (
        "cancelled"
        if response.get("cancelled")
        else "failed"
        if failed
        else "succeeded"
    )
    db.execute(
        "UPDATE gateway_jobs SET status=?,charge=?,cost=?,usage_json=?,result_json=?,upstream_id=coalesce(?,upstream_id),error=?,updated_at=? WHERE id=?",
        (
            status,
            charge,
            cost,
            canonical(usage),
            canonical(response["result"]) if "result" in response else None,
            response.get("upstream_id"),
            "供应商确认失败，冻结额度已释放" if failed else None,
            now(),
            job["id"],
        ),
    )


def cancel(store, user, job_id):
    with store.write() as db:
        job = owned(db, "gateway_jobs", job_id, user["id"])
        if job["status"] == "queued":
            finish(db, job, {"cancelled": True})
        elif job["status"] not in {"succeeded", "failed", "cancelled"}:
            raise Problem(
                409,
                "already_submitted",
                "已提交供应商，不能直接释放额度；请等待结果或管理员核对",
            )
        return public_job(db, owned(db, "gateway_jobs", job_id, user["id"]))


def recover(store):
    with store.write() as db:
        db.execute(
            "UPDATE gateway_jobs SET status=CASE WHEN upstream_id IS NOT NULL THEN 'running' ELSE 'submission_unknown' END,error='服务中断；有任务编号则继续查询，否则等待核对' WHERE status IN ('submitting','polling')"
        )


def execute_one(store, adapter):
    with store.write() as db:
        job = db.execute(
            "SELECT * FROM gateway_jobs WHERE status IN ('queued','running') ORDER BY updated_at LIMIT 1"
        ).fetchone()
        if not job:
            return False
        quote = owned(db, "gateway_quotes", job["quote_id"], job["user_id"])
        model, inputs = quote["model"], json.loads(quote["input_json"])
        snapshot = json.loads(quote["snapshot"])
        inputs["_model_info"] = snapshot.get("model_info") or providers.MODELS[model]
        inputs["_provider_config"] = snapshot.get("provider_config", {})
        db.execute(
            "UPDATE gateway_jobs SET status=?,updated_at=? WHERE id=?",
            ("polling" if job["upstream_id"] else "submitting", now(), job["id"]),
        )

    def checkpoint(upstream_id):
        with store.write() as db:
            db.execute(
                "UPDATE gateway_jobs SET upstream_id=? WHERE id=?",
                (upstream_id, job["id"]),
            )

    try:
        response = adapter.execute(model, inputs, checkpoint, job["upstream_id"])
        with store.write() as db:
            current = db.execute(
                "SELECT * FROM gateway_jobs WHERE id=?", (job["id"],)
            ).fetchone()
            if response.get("pending"):
                db.execute(
                    "UPDATE gateway_jobs SET status='running',updated_at=? WHERE id=?",
                    (now(), job["id"]),
                )
            else:
                finish(db, current, response)
    except adapters.ReceiptMissing as error:
        with store.write() as db:
            db.execute(
                "UPDATE gateway_jobs SET status='submission_unknown',upstream_id=?,result_json=?,error='结果已返回，用量回执待核对，未重复提交',updated_at=? WHERE id=?",
                (
                    error.upstream_id or None,
                    canonical(error.result) if error.result else None,
                    now(),
                    job["id"],
                ),
            )
    except adapters.Rejected:
        with store.write() as db:
            current = db.execute(
                "SELECT * FROM gateway_jobs WHERE id=?", (job["id"],)
            ).fetchone()
            if current["upstream_id"]:
                db.execute(
                    "UPDATE gateway_jobs SET status='running',updated_at=? WHERE id=?",
                    (now(), job["id"]),
                )
            else:
                finish(db, current, {"failed": True})
    except Exception:  # noqa: BLE001 -- all supplier exceptions cross a financial uncertainty boundary
        # No supplier exception text is persisted: it may contain keys, signatures or URLs.
        with store.write() as db:
            current = db.execute(
                "SELECT * FROM gateway_jobs WHERE id=?", (job["id"],)
            ).fetchone()
            db.execute(
                "UPDATE gateway_jobs SET status=?,error='供应商结果或用量待核对，未重复提交',updated_at=? WHERE id=?",
                (
                    "running" if current["upstream_id"] else "submission_unknown",
                    now(),
                    job["id"],
                ),
            )
    return True


async def run_worker(store, vault):
    adapter = adapters.Adapter(vault, store.path.parent / "files")
    while True:
        await asyncio.to_thread(execute_one, store, adapter)
        await asyncio.sleep(3)


def reconcile(store, actor, job_id, outcome, usage, evidence):
    with store.write() as db:
        job = db.execute("SELECT * FROM gateway_jobs WHERE id=?", (job_id,)).fetchone()
        if not job or job["status"] != "submission_unknown":
            raise Problem(409, "reconcile_invalid", "只能核对提交结果或用量未知的任务")
        if outcome == "succeeded":
            quote = owned(db, "gateway_quotes", job["quote_id"], job["user_id"])
            snapshot = json.loads(quote["snapshot"])
            info = snapshot.get("model_info") or providers.MODELS[quote["model"]]
            if set(usage) != set(info["meters"]):
                raise Problem(422, "usage_invalid", "必须提供完整用量回执")
        finish(
            db,
            job,
            {
                "failed": outcome == "failed",
                "usage": usage,
                "result": {
                    **json.loads(job["result_json"] or "{}"),
                    "reconciliation_evidence": evidence,
                },
            },
        )
        audit(db, actor, "reconcile_gateway_job", job_id)
        return public_job(
            db,
            db.execute("SELECT * FROM gateway_jobs WHERE id=?", (job_id,)).fetchone(),
            True,
        )
