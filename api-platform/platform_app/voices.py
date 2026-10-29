"""Account-owned voice catalogue and frozen synthesis choices; never keyed by API Key."""

import json
import math
import re

from .store import Problem, audit, now, owned, uid

PUBLIC_MODEL = "haike/cosyvoice-public"
CLONE_MODEL = "haike/voice-clone"
PRIVATE_MODEL = "haike/cosyvoice"
PUBLIC_TARGET = "cosyvoice-v3-flash"
PRIVATE_TARGET = "cosyvoice-v3.5-flash"
SOURCE = "https://help.aliyun.com/zh/model-studio/cosyvoice-voice-list"

# Official v3-flash candidates. v3.5 explicitly does not support system voices.
# Catalogue readiness is not evidence of a successful paid synthesis.
PUBLIC_VOICES = {
    "pub_" + upstream: {
        "id": "pub_" + upstream,
        "name": name,
        "gender": gender,
        "upstream_voice_id": upstream,
        "target_model": PUBLIC_TARGET,
    }
    for upstream, name, gender in (
        ("longanyang", "龙安洋", "male"),
        ("longanlang_v3", "龙安朗", "male"),
        ("longshuo_v3", "龙硕", "male"),
        ("longanhuan_v3", "龙安欢", "female"),
        ("longanwen_v3", "龙安温", "female"),
        ("longyue_v3", "龙悦", "female"),
    )
}


def resolve(db, user_id, voice_id, *, allow_disabled=False):
    if not isinstance(voice_id, str):
        raise Problem(422, "voice_invalid", "请选择音色库中的音色")
    if voice_id in PUBLIC_VOICES:
        return {**PUBLIC_VOICES[voice_id], "kind": "public", "model": PUBLIC_MODEL}
    row = db.execute(
        "SELECT * FROM account_voices WHERE id=? AND user_id=?", (voice_id, user_id)
    ).fetchone()
    if not row:
        raise Problem(404, "voice_missing", "音色不存在或不属于当前账户")
    if row["disabled_at"] and not allow_disabled:
        raise Problem(409, "voice_disabled", "该音色已停用，已确认的原任务仍可恢复")
    return {**dict(row), "kind": "cloned", "gender": "custom", "model": PRIVATE_MODEL}


def preferences(db, user_id, voice_id):
    row = db.execute(
        "SELECT speech_rate,image_file_id FROM account_voice_preferences WHERE user_id=? AND voice_id=?",
        (user_id, voice_id),
    ).fetchone()
    return dict(row) if row else {"speech_rate": 1.0, "image_file_id": None}


def default_voice(db, user_id):
    row = db.execute(
        "SELECT voice_id FROM account_voice_defaults WHERE user_id=?", (user_id,)
    ).fetchone()
    return row["voice_id"] if row else None


def public_voice(db, user_id, voice, model_status=None):
    disabled = bool(voice.get("disabled_at"))
    ready = model_status == "available" and not disabled
    return {
        "id": voice["id"],
        "name": voice["name"],
        "gender": voice["gender"],
        "kind": voice["kind"],
        "model": voice["model"],
        "compatible_models": [voice["target_model"]],
        "status": "disabled" if disabled else "available" if ready else "blocked",
        "available": ready,
        "verification": "candidate_unverified"
        if voice["kind"] == "public"
        else "enrollment_confirmed",
        "blocked_reason": None
        if ready or disabled
        else "兼容模型、供应商或采购价格尚未开通",
        "preferences": preferences(db, user_id, voice["id"]),
        "source": SOURCE if voice["kind"] == "public" else None,
    }


def catalogue(store, vault, user_id):
    from . import providers

    statuses = {
        item["model"]: item["status"] for item in providers.catalogue(store, vault)
    }
    with store.read() as db:
        ids = list(PUBLIC_VOICES) + [
            r["id"]
            for r in db.execute(
                "SELECT id FROM account_voices WHERE user_id=? ORDER BY created_at",
                (user_id,),
            )
        ]
        items = [
            public_voice(
                db,
                user_id,
                resolve(db, user_id, identifier, allow_disabled=True),
                statuses.get(
                    PUBLIC_MODEL if identifier in PUBLIC_VOICES else PRIVATE_MODEL
                ),
            )
            for identifier in ids
        ]
        return {
            "items": items,
            "preferences": {"voice_id": default_voice(db, user_id)},
            "clone_model": CLONE_MODEL,
            "clone_status": statuses.get(CLONE_MODEL, "blocked"),
        }


def rate(value):
    if (
        type(value) not in {float, int}
        or not math.isfinite(value)
        or not 0.5 <= value <= 2
    ):
        raise Problem(422, "speech_rate_invalid", "语速倍率需在 0.5–2.0 之间")
    return float(value)


def set_preferences(store, user_id, voice_id, values):
    with store.write() as db:
        resolve(db, user_id, voice_id)
        previous = preferences(db, user_id, voice_id)
        speed = rate(values.get("speech_rate", previous["speech_rate"]))
        image = values.get("image_file_id", previous["image_file_id"])
        if image is not None:
            row = db.execute(
                "SELECT id FROM gateway_files WHERE id=? AND user_id=? AND kind='image'",
                (image, user_id),
            ).fetchone()
            if not row:
                raise Problem(404, "file_missing", "人物图不存在或不属于当前账户")
        db.execute(
            "INSERT INTO account_voice_preferences VALUES(?,?,?,?,?) ON CONFLICT(user_id,voice_id) "
            "DO UPDATE SET speech_rate=excluded.speech_rate,image_file_id=excluded.image_file_id,updated_at=excluded.updated_at",
            (user_id, voice_id, speed, image, now()),
        )
        return {"voice_id": voice_id, **preferences(db, user_id, voice_id)}


def set_default(store, user_id, voice_id):
    with store.write() as db:
        if voice_id is not None:
            resolve(db, user_id, voice_id)
        db.execute(
            "INSERT INTO account_voice_defaults VALUES(?,?,?) ON CONFLICT(user_id) "
            "DO UPDATE SET voice_id=excluded.voice_id,updated_at=excluded.updated_at",
            (user_id, voice_id, now()),
        )
        return {"voice_id": voice_id}


def disable(store, user_id, voice_id):
    with store.write() as db:
        voice = resolve(db, user_id, voice_id, allow_disabled=True)
        if voice["kind"] == "public":
            raise Problem(422, "public_voice", "公共音色不能删除，可切换默认音色")
        db.execute(
            "UPDATE account_voices SET disabled_at=coalesce(disabled_at,?) WHERE id=? AND user_id=?",
            (now(), voice_id, user_id),
        )
        db.execute(
            "UPDATE account_voice_defaults SET voice_id=NULL,updated_at=? WHERE user_id=? AND voice_id=?",
            (now(), user_id, voice_id),
        )
        return {"id": voice_id, "status": "disabled"}


def clean_tts(db, user_id, model, value, info):
    selected = value.get("voice_id") or default_voice(db, user_id)
    if selected is None and model == PUBLIC_MODEL:
        selected = next(iter(PUBLIC_VOICES))
    if selected is None:
        # Backward compatibility for the administrator-provisioned platform default.
        # It is never exposed as an account-owned clone or imported into a user's library.
        return {
            "text": value["text"],
            "speech_rate": rate(value.get("speech_rate", 1.0)),
        }
    voice = resolve(db, user_id, selected)
    if voice["model"] != model or voice["target_model"] != info["target_model"]:
        raise Problem(
            422,
            "voice_model_mismatch",
            "音色与所选配音模型不兼容，请使用音色返回的 model 重新报价",
        )
    prefs = preferences(db, user_id, selected)
    speed = rate(value.get("speech_rate", prefs["speech_rate"]))
    return {
        "text": value["text"],
        "voice_id": selected,
        "speech_rate": speed,
        "_voice_upstream": voice["upstream_voice_id"],
        "_voice_selection": {
            "voice_id": selected,
            "name": voice["name"],
            "kind": voice["kind"],
            "speech_rate": speed,
            "image_file_id": prefs["image_file_id"],
            "model": model,
            "upstream_model": voice["target_model"],
        },
    }


def clean_clone(db, user_id, value):
    if (
        set(value) != {"name", "audio_file", "consent"}
        or value.get("consent") is not True
    ):
        raise Problem(
            422,
            "voice_consent_required",
            "请确认有权使用录音，并同意上传阿里云进行声音复刻",
        )
    name = value.get("name")
    if (
        not isinstance(name, str)
        or not 1 <= len(name.strip()) <= 48
        or any(ord(c) < 32 for c in name)
    ):
        raise Problem(422, "voice_name_invalid", "音色名称需为 1–48 字，不含控制字符")
    if not isinstance(value.get("audio_file"), str):
        raise Problem(422, "audio_invalid", "请上传自己的参考录音")
    audio = owned(db, "gateway_files", value["audio_file"], user_id)
    if audio["kind"] != "audio" or not 5 <= audio["duration_seconds"] <= 60:
        raise Problem(
            422, "audio_invalid", "参考录音需为 5–60 秒清晰单人朗读，推荐 10–20 秒"
        )
    count = db.execute(
        "SELECT count(*) FROM account_voices WHERE user_id=? AND disabled_at IS NULL",
        (user_id,),
    ).fetchone()[0]
    if count >= 50:
        raise Problem(409, "voice_quota", "自定义音色已达 50 个，请停用不再使用的音色")
    return {"name": name.strip(), "audio_file": audio["id"], "consent": True}, {
        "voices": 1
    }


def register_result(db, job, quote, response):
    """Register and settle in the same transaction; polling can never duplicate a voice."""
    snapshot = json.loads(quote["snapshot"])
    target = snapshot["model_info"]["target_model"]
    upstream = response.get("upstream_id") or job["upstream_id"]
    if not isinstance(upstream, str) or not re.fullmatch(
        re.escape(target) + r"-[A-Za-z0-9_.:-]{1,220}", upstream
    ):
        raise Problem(
            409, "voice_receipt_invalid", "音色回执与已确认模型不一致，等待核对"
        )
    existing = db.execute(
        "SELECT id FROM account_voices WHERE source_job_id=?", (job["id"],)
    ).fetchone()
    identifier = existing["id"] if existing else uid("voice")
    if not existing:
        db.execute(
            "INSERT INTO account_voices VALUES(?,?,?,?,?,?,?,NULL)",
            (
                identifier,
                job["user_id"],
                json.loads(quote["input_json"])["name"],
                upstream,
                target,
                job["id"],
                now(),
            ),
        )
    voice = resolve(db, job["user_id"], identifier, allow_disabled=True)
    result = {"voice": public_voice(db, job["user_id"], voice, "available")}
    if response.get("result", {}).get("cleanup_warning"):
        result["cleanup_warning"] = "临时录音清理待管理员核对 OSS 生命周期"
    return result


def attach_receipt(store, actor_id, job_id, upstream_voice_id, evidence):
    """Operator verifies a lost creation response, then resumes query-only work."""
    with store.write() as db:
        job = db.execute("SELECT * FROM gateway_jobs WHERE id=?", (job_id,)).fetchone()
        if not job or job["status"] != "submission_unknown" or job["upstream_id"]:
            raise Problem(409, "receipt_inactive", "仅可补录尚无上游编号的未知克隆任务")
        quote = owned(db, "gateway_quotes", job["quote_id"], job["user_id"])
        snapshot = json.loads(quote["snapshot"])
        info = snapshot["model_info"]
        if info["capability"] != "voice_clone" or not re.fullmatch(
            re.escape(info["target_model"]) + r"-[A-Za-z0-9_.:-]{1,220}",
            upstream_voice_id,
        ):
            raise Problem(
                422, "voice_receipt_invalid", "音色回执与原克隆任务型号不一致"
            )
        # Store verification evidence privately; never expose another account's voice ID.
        db.execute(
            "UPDATE gateway_jobs SET upstream_id=?,status='running',error=NULL,updated_at=? WHERE id=?",
            (upstream_voice_id, now(), job_id),
        )
        audit(db, actor_id, "attach_verified_voice_receipt", job_id)
        db.execute(
            "INSERT INTO voice_receipt_evidence VALUES(?,?,?,?)",
            (job_id, actor_id, evidence, now()),
        )
        return {"id": job_id, "status": "running", "recovery": "query_only"}
