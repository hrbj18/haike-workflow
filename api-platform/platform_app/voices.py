"""Account-owned CosyVoice identities and reusable, authenticated auditions."""

import base64
import hashlib
import json
import re
import secrets

from . import adapters, providers
from .store import Problem, canonical, digest, later, now, owned, uid

TTS_MODEL = "haike/cosyvoice"
CLONE_MODEL = "haike/voice-clone"
SAMPLE_TEXT = "你好，我是你的专属声音。愿每一次表达，都自然、清晰、有温度。"


def clone_prefix(job_id):
    return "h" + base64.b32encode(hashlib.sha256(job_id.encode()).digest()).decode().lower()[:8]


def scope(config):
    return digest(canonical([config.get("base_url"), config.get("api_key")]))


def sync_default(db, vault):
    config = vault.load().get("bailian", {})
    if not config.get("voice"):
        return None
    model = vault.models()[TTS_MODEL]["target_model"]
    provider_scope = scope(config)
    prior = db.execute("SELECT id FROM gateway_voices WHERE user_id IS NULL AND provider_voice_id=? AND target_model=? AND provider_scope=?", (config["voice"], model, provider_scope)).fetchone()
    if prior:
        return prior["id"]
    # A library ID denotes an immutable voice identity, never a mutable default alias.
    identity = "voice_" + digest(canonical([config["voice"], model, provider_scope]))[:24]
    db.execute(
        """INSERT INTO gateway_voices(id,user_id,name,provider_voice_id,target_model,
           provider_scope,language,tags_json,status,created_at)
           VALUES(?,NULL,'海客默认音色',?,?,?,'zh','["默认口播"]','ready',?)""",
        (identity, config["voice"], model, provider_scope, now()),
    )
    return identity


def resolve(db, user_id, voice_id, target_model=None, provider_scope=None):
    if not isinstance(voice_id, str) or not re.fullmatch(r"voice_[a-z0-9_]{1,64}", voice_id):
        raise Problem(422, "voice_id_invalid", "请选择音色库中的音色")
    row = db.execute(
        "SELECT * FROM gateway_voices WHERE id=? AND (user_id IS NULL OR user_id=?)",
        (voice_id, user_id),
    ).fetchone()
    if not row or row["status"] != "ready":
        raise Problem(404, "voice_missing", "音色不存在、已停用或不属于当前账户，请重新选择")
    if target_model and row["target_model"] != target_model:
        raise Problem(409, "voice_model_changed", "此音色与当前配音模型不兼容，请重新选择")
    if provider_scope and row["provider_scope"] != provider_scope:
        raise Problem(409, "voice_provider_changed", "音色所属百炼配置已变化，请联系管理员核对")
    return row


def public(db, row, compatible):
    sample = db.execute("SELECT status FROM gateway_jobs WHERE id=?", (row["sample_job_id"],)).fetchone()
    sample_status = "succeeded" if row["sample_file"] else sample["status"] if sample else "missing"
    return {"id": row["id"], "name": row["name"], "scope": "personal" if row["user_id"] else "system",
            "provider": "阿里百炼", "model": TTS_MODEL, "language": row["language"],
            "tags": json.loads(row["tags_json"]), "status": "ready" if compatible else "unavailable",
            "created_at": row["created_at"], "sample_status": sample_status,
            "sample_url": f"/v2/voices/{row['id']}/sample" if sample_status == "succeeded" else None}


def catalogue(store, vault, user):
    config = vault.load().get("bailian", {})
    current_scope = scope(config)
    model = vault.models()[TTS_MODEL]["target_model"]
    capability = next((c for c in providers.catalogue(store, vault) if c["model"] == TTS_MODEL), {})
    clone = next((c for c in providers.catalogue(store, vault) if c["model"] == CLONE_MODEL), {})
    with store.write() as db:
        default_voice_id = sync_default(db, vault)
        rows = db.execute("SELECT * FROM gateway_voices WHERE status='ready' AND (user_id IS NULL OR user_id=?) ORDER BY user_id IS NOT NULL,created_at DESC", (user["id"],)).fetchall()
        items = [public(db, r, r["provider_scope"] == current_scope and r["target_model"] == model and capability.get("status") == "available") for r in rows]
    return {"items": items, "default_voice_id": default_voice_id, "clone_ready": clone.get("status") == "available" and bool(getattr(vault, "public_origin", None)),
            "clone_price_micros": "0", "sample_text": SAMPLE_TEXT,
            "clone_hint": "" if getattr(vault, "public_origin", None) else "克隆服务需要管理员配置可供百炼读取录音的 HTTPS 地址"}


def clean_clone(db, user_id, value):
    if set(value) - {"audio_file", "name", "consent", "language", "tags"} or value.get("consent") is not True:
        raise Problem(422, "voice_consent", "请确认你拥有此声音素材的使用授权")
    name = str(value.get("name") or "").strip()
    language, tags = value.get("language", "zh"), value.get("tags", [])
    if not 1 <= len(name) <= 48 or language not in {"zh", "en", "yue"} or not isinstance(tags, list) or len(tags) > 4 or any(not isinstance(t, str) or not 1 <= len(t) <= 12 for t in tags):
        raise Problem(422, "voice_metadata", "音色名称需要1至48字，最多4个简短标签")
    sample = db.execute("SELECT * FROM gateway_files WHERE id=? AND user_id=? AND kind='audio'", (value.get("audio_file"), user_id)).fetchone()
    if not sample or not 125 <= sample["total_frames"] <= 1500:
        raise Problem(422, "voice_sample_invalid", "请上传5至60秒的清晰单人录音，推荐10至20秒")
    return {"audio_file": sample["id"], "name": name, "language": language, "tags": tags, "consent": True}, {"requests": 1}


def ticket(store, file_id, user_id, origin):
    if not origin or not origin.startswith("https://"):
        raise adapters.Rejected()
    token = secrets.token_urlsafe(32)
    with store.write() as db:
        owned(db, "gateway_files", file_id, user_id)
        db.execute("INSERT INTO gateway_voice_tickets VALUES(?,?,?,?)", (digest(token), file_id, user_id, later(600)))
    return origin.rstrip("/") + "/voice-reference/" + token + ".wav"


def reference(store, token):
    with store.read() as db:
        row = db.execute("SELECT file_id FROM gateway_voice_tickets WHERE token_hash=? AND expires_at>?", (digest(token), now())).fetchone()
    if not row:
        raise Problem(404, "sample_expired", "录音读取凭证已过期")
    path = store.path.parent / "files" / row["file_id"]
    if not path.is_file() or path.is_symlink():
        raise Problem(404, "sample_missing", "录音不存在")
    return path


def register_clone(db, job, quote, response):
    inputs = json.loads(quote["input_json"])
    snapshot = json.loads(quote["snapshot"])
    model = snapshot["model_info"]["target_model"]
    voice = response.get("result", {}).get("provider_voice_id", "")
    if not isinstance(voice, str) or not voice.startswith(model + "-") or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", voice):
        raise Problem(409, "voice_receipt_invalid", "百炼音色回执不完整，保留原任务等待核对")
    existing = db.execute("SELECT id FROM gateway_voices WHERE clone_job_id=?", (job["id"],)).fetchone()
    identity = existing["id"] if existing else uid("voice")
    if not existing:
        db.execute("""INSERT INTO gateway_voices(id,user_id,name,provider_voice_id,target_model,provider_scope,
                   language,tags_json,status,clone_job_id,created_at) VALUES(?,?,?,?,?,?,?,?,'ready',?,?)""",
                   (identity, job["user_id"], inputs["name"], voice, model, inputs["_provider_scope"],
                    inputs["language"], canonical(inputs["tags"]), job["id"], now()))
    response["result"] = {"voice_id": identity, "name": inputs["name"]}


def preview_quote(store, vault, user, voice_id):
    from . import gateway
    with store.read() as db:
        row = resolve(db, user["id"], voice_id, vault.models()[TTS_MODEL]["target_model"], scope(vault.load().get("bailian", {})))
        if row["sample_file"]:
            return {"sample_status": "succeeded", "cached": True}
        job = db.execute("SELECT status FROM gateway_jobs WHERE id=?", (row["sample_job_id"],)).fetchone()
        if job and job["status"] not in {"failed", "cancelled"}:
            return {"sample_status": job["status"], "cached": job["status"] == "succeeded"}
    return {"quote": gateway.create_quote(store, vault, user, TTS_MODEL, {"text": SAMPLE_TEXT, "voice_id": voice_id}, "voice-preview:" + voice_id), "sample_status": "missing", "cached": False}


def bind_preview(db, user_id, quote, job_id):
    if not quote["project_ref"].startswith("voice-preview:"):
        return
    voice_id = quote["project_ref"].split(":", 1)[1]
    inputs = json.loads(quote["input_json"])
    if inputs.get("voice_id") != voice_id or inputs.get("text") != SAMPLE_TEXT:
        raise Problem(422, "preview_invalid", "试听内容与音色不一致")
    row = resolve(db, user_id, voice_id)
    if row["sample_file"]:
        raise Problem(409, "preview_exists", "已有试听音频，请直接播放，不要重复生成")
    prior = db.execute("SELECT status FROM gateway_jobs WHERE id=?", (row["sample_job_id"],)).fetchone()
    if prior and prior["status"] not in {"failed", "cancelled"}:
        raise Problem(409, "preview_exists", "已有试听任务，请播放或查询原试听，不要重复生成")
    db.execute("UPDATE gateway_voices SET sample_job_id=? WHERE id=?", (job_id, voice_id))


def sample_path(store, user, voice_id):
    with store.read() as db:
        row = resolve(db, user["id"], voice_id)
        job = db.execute("SELECT * FROM gateway_jobs WHERE id=?", (row["sample_job_id"],)).fetchone()
    if row["sample_file"]:
        path = store.path.parent / "voice-samples" / row["sample_file"]
        if not re.fullmatch(r"sample_[a-f0-9]{24}\.wav", row["sample_file"]) or not path.is_file() or path.is_symlink():
            raise Problem(404, "sample_missing", "已导入的试听文件暂不可读取，请联系管理员恢复")
        return path
    if not job or job["status"] != "succeeded":
        raise Problem(409, "sample_not_ready", "试听尚未生成，请先确认试听费用")
    path = store.path.parent / "voice-samples" / (job["id"] + ".wav")
    if path.is_file() and not path.is_symlink():
        return path
    result = json.loads(job["result_json"] or "{}")
    try:
        data = adapters.download_bailian_audio(result.get("audio_url"))
    except (adapters.Uncertain, OSError, ValueError, Problem):
        raise Problem(409, "sample_download_unavailable", "试听已生成，但原音频暂时无法下载；请重试读取原结果") from None
    path.parent.mkdir(exist_ok=True)
    temporary = path.with_suffix("." + secrets.token_hex(6) + ".tmp")
    temporary.write_bytes(data); temporary.chmod(0o600); temporary.replace(path)
    return path


def rename(store, user, voice_id, name):
    name = str(name or "").strip()
    if not 1 <= len(name) <= 48:
        raise Problem(422, "voice_name_invalid", "音色名称需要1至48字")
    with store.write() as db:
        owned(db, "gateway_voices", voice_id, user["id"])
        db.execute("UPDATE gateway_voices SET name=? WHERE id=?", (name, voice_id))
    return {"id": voice_id, "name": name}


def import_system(store, vault, name, provider_voice_id, tags=None, verify=True):
    model = vault.models()[TTS_MODEL]["target_model"]
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 48 or not isinstance(provider_voice_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", provider_voice_id) or not provider_voice_id.startswith(model + "-"):
        raise Problem(422, "voice_import_invalid", "系统音色名称或百炼模型绑定无效")
    tags = tags or []
    if not isinstance(tags, list) or len(tags) > 4 or any(not isinstance(t, str) or not 1 <= len(t) <= 12 for t in tags):
        raise Problem(422, "voice_tags_invalid", "最多4个简短标签")
    config = vault.load().get("bailian", {})
    if verify:
        try:
            output = adapters.http(config["base_url"].rstrip("/") + "/services/audio/tts/customization",
                {"Authorization": "Bearer " + config["api_key"], "Content-Type": "application/json"},
                {"model": "voice-enrollment", "input": {"action": "query_voice", "voice_id": provider_voice_id}}).get("output", {})
        except (adapters.Rejected, adapters.Uncertain, KeyError, TypeError):
            raise Problem(409, "voice_verify_unavailable", "百炼音色状态暂时无法核对，未发布该音色") from None
        if output.get("status") != "OK" or output.get("target_model", model) != model:
            raise Problem(409, "voice_not_ready", "百炼音色未部署或与当前配音模型不兼容")
    with store.write() as db:
        prior = db.execute("SELECT id FROM gateway_voices WHERE user_id IS NULL AND provider_voice_id=? AND provider_scope=?", (provider_voice_id, scope(config))).fetchone()
        identity = prior["id"] if prior else uid("voice")
        if not prior:
            db.execute("""INSERT INTO gateway_voices(id,user_id,name,provider_voice_id,target_model,provider_scope,
                       language,tags_json,status,created_at) VALUES(?,NULL,?,?,?,?,'zh',?,'ready',?)""",
                       (identity, name.strip(), provider_voice_id, model, scope(config), canonical(tags), now()))
        else:
            db.execute("UPDATE gateway_voices SET name=?,tags_json=? WHERE id=?", (name.strip(), canonical(tags), identity))
    return {"id": identity, "name": name.strip()}


def import_sample(store, voice_id, data):
    import io
    import wave
    if not data or len(data) > 5 * 1024 * 1024:
        raise Problem(422, "sample_invalid", "系统试听需要5MB以内的WAV音频")
    try:
        with wave.open(io.BytesIO(data)) as audio:
            if not audio.getnframes() or audio.getnframes() / audio.getframerate() > 60:
                raise ValueError()
    except (wave.Error, EOFError, ValueError):
        raise Problem(422, "sample_invalid", "系统试听音频无法读取或超过60秒") from None
    with store.write() as db:
        row = db.execute("SELECT id FROM gateway_voices WHERE id=? AND user_id IS NULL", (voice_id,)).fetchone()
        if not row:
            raise Problem(404, "voice_missing", "只能为已登记的系统音色导入试听")
        name = uid("sample") + ".wav"
        folder = store.path.parent / "voice-samples"
        folder.mkdir(exist_ok=True)
        path = folder / name
        path.write_bytes(data); path.chmod(0o600)
        db.execute("UPDATE gateway_voices SET sample_file=? WHERE id=?", (name, voice_id))
    return {"id": voice_id, "sample_imported": True}


def query_clone(store, vault, user, job_id):
    from . import gateway
    with store.read() as db:
        job = owned(db, "gateway_jobs", job_id, user["id"])
        quote = owned(db, "gateway_quotes", job["quote_id"], user["id"])
        if quote["model"] != CLONE_MODEL:
            raise Problem(422, "clone_job_invalid", "此任务不是音色克隆")
        if job["status"] != "submission_unknown":
            return gateway.public_job(db, job)
        inputs, snapshot = json.loads(quote["input_json"]), json.loads(quote["snapshot"])
    config = vault.load().get("bailian", {})
    if scope(config) != inputs["_provider_scope"]:
        raise Problem(409, "voice_provider_changed", "请恢复创建原音色时的百炼配置后查询")
    model = snapshot["model_info"]["target_model"]
    prefix = clone_prefix(job_id)
    try:
        output = adapters.http(config["base_url"].rstrip("/") + "/services/audio/tts/customization",
            {"Authorization": "Bearer " + config["api_key"], "Content-Type": "application/json"},
            {"model": "voice-enrollment", "input": {"action": "list_voice", "prefix": prefix, "page_index": 0, "page_size": 10}}).get("output", {})
    except (adapters.Rejected, adapters.Uncertain, KeyError, TypeError):
        raise Problem(409, "voice_query_unavailable", "原克隆结果暂时无法查询，已停止重复创建") from None
    found = output.get("voice_list", [])
    if not isinstance(found, list) or len(found) != 1 or not isinstance(found[0], dict):
        raise Problem(409, "voice_result_unknown", "未能唯一确认原音色，请联系管理员核对；不要重复克隆")
    item = found[0]
    identity = item.get("voice_id", "")
    if not isinstance(identity, str) or not identity.startswith(model + "-" + prefix + "-") or item.get("target_model", model) != model:
        raise Problem(409, "voice_result_unknown", "原音色模型或任务标识不一致，请联系管理员核对")
    with store.write() as db:
        current = owned(db, "gateway_jobs", job_id, user["id"])
        if current["status"] == "submission_unknown":
            db.execute("UPDATE gateway_jobs SET upstream_id=?,status='running',error=NULL,updated_at=? WHERE id=?", (identity, now(), job_id))
        return gateway.public_job(db, owned(db, "gateway_jobs", job_id, user["id"]))
