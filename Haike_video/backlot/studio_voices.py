"""The studio uses account-owned voices through the same private Haike client."""

import json
import re
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from backlot.studio import timestamp
from backlot.studio_avatar import key_identity
from backlot.work_catalog import WorkError


def catalogue(studio):
    try:
        value = studio.client().request("/voices")
    except Exception as error:
        raise WorkError("音色库暂不可用，请先连接海客Key，并确认网关已更新音色库服务") from error
    for voice in value.get("items", []):
        if not isinstance(voice.get("id"), str) or not re.fullmatch(r"voice_[a-z0-9_]{1,64}", voice["id"]):
            raise WorkError("音色库返回了无效的音色标识，请联系管理员核对")
        if voice.get("sample_url"):
            voice["sample_url"] = "/api/studio/voices/" + voice["id"] + "/sample"
    return value


def sample(studio, voice_id):
    voice = next((v for v in catalogue(studio).get("items", []) if v["id"] == voice_id), None)
    if not voice or voice.get("sample_status") != "succeeded":
        raise WorkError("此音色尚无试听，请先生成试听音频")
    folder = studio.private / "voice-library" / key_identity(studio)
    path = folder / (voice_id + ".wav")
    if not path.is_file():
        try:
            data = studio.client().media("/voices/" + voice_id + "/sample")
        except Exception as error:
            raise WorkError("试听已生成，但原音频暂时无法下载；请重试播放，不要重复生成") from error
        if not data.startswith(b"RIFF") or len(data) > 5 * 1024 * 1024:
            raise WorkError("试听音频无法读取，请查询原试听任务")
        folder.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix("." + uuid4().hex + ".tmp")
        temporary.write_bytes(data); temporary.chmod(0o600); temporary.replace(path)
    if path.is_symlink():
        raise WorkError("试听文件路径不可用")
    return path


def upload_sample(studio, name, content):
    from backlot.studio_render import media_probe
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    suffix = Path(name).suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a"} or not content or len(content) > 10 * 1024 * 1024:
        raise WorkError("请上传10MB内的WAV、MP3或M4A录音")
    with tempfile.TemporaryDirectory(prefix="haike-voice-sample-") as temporary:
        source = Path(temporary) / ("source" + suffix)
        source.write_bytes(content); source.chmod(0o600)
        try:
            info = media_probe(source)
        except Exception:
            raise WorkError("无法读取录音，请检查音频格式") from None
        if not info.get("audio") or not 5 <= info["duration"] <= 60:
            raise WorkError("录音需要5至60秒，推荐10至20秒的清晰单人朗读")
        target = Path(temporary) / "reference.wav"
        ffmpeg, _ = resolve_ffmpeg_pair()
        try:
            result = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(source), "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(target)], capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            raise WorkError("录音转换未完成，请检查FFmpeg或更换音频文件") from None
        if result.returncode:
            raise WorkError("无法准备克隆录音，请更换音频文件")
        try:
            value = studio.client().upload(target, "audio")
        except Exception as error:
            raise WorkError("录音未能上传到音色服务，请核对连接后重试") from error
    return {"id": value["id"], "name": Path(name).name[:160], "duration": info["duration"]}


def _store(studio, data):
    with studio.db() as db:
        db.execute("INSERT INTO studio_voice_operations VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                   (data["id"], data["identity"], json.dumps(data, ensure_ascii=False)))


def _get(studio, operation_id):
    with studio.db() as db:
        row = db.execute("SELECT data FROM studio_voice_operations WHERE id=? AND identity=?", (operation_id, key_identity(studio))).fetchone()
    if not row:
        raise WorkError("音色任务不存在或当前海客Key已变化，请恢复原账户")
    return json.loads(row[0])


def public(data):
    return {k: data.get(k) for k in ("id", "kind", "name", "voice_id", "quote", "job", "created_at")}


def quote_clone(studio, data):
    if data.get("consent") is not True:
        raise WorkError("请确认你拥有此声音素材的使用授权，并同意提交阿里百炼进行克隆")
    try:
        quote = studio.client().quote("haike/voice-clone", {"audio_file": data.get("sample_id"),
            "name": data.get("name"), "consent": True, "language": data.get("language", "zh"), "tags": data.get("tags", [])}, "voice-library")
    except Exception as error:
        raise WorkError(str(error)) from None
    operation = {"id": "voiceop-" + uuid4().hex, "identity": key_identity(studio), "kind": "clone", "name": data.get("name"), "quote": quote, "created_at": timestamp()}
    _store(studio, operation)
    return public(operation)


def quote_preview(studio, voice_id):
    try:
        value = studio.client().request("/voices/" + voice_id + "/preview-quote", {})
    except Exception as error:
        raise WorkError(str(error)) from None
    if not value.get("quote"):
        return value
    item = next((v for v in catalogue(studio)["items"] if v["id"] == voice_id), None)
    if not item:
        raise WorkError("音色不存在或不属于当前账户")
    operation = {"id": "voiceop-" + uuid4().hex, "identity": key_identity(studio), "kind": "sample", "name": item["name"], "voice_id": voice_id, "quote": value["quote"], "created_at": timestamp()}
    _store(studio, operation)
    return {"operation": public(operation), "cached": False}


def confirm(studio, operation_id, confirmed):
    if confirmed is not True:
        raise WorkError("请先确认本次音色操作及费用")
    # The intent is persisted while SQLite serializes concurrent button clicks.
    with studio.db() as db:
        row = db.execute("SELECT data FROM studio_voice_operations WHERE id=? AND identity=?", (operation_id, key_identity(studio))).fetchone()
        if not row:
            raise WorkError("原音色报价不存在或海客Key已变化，请重新确认")
        data = json.loads(row[0])
        if not data.get("intent"):
            data["intent"] = studio.client().confirm(data["quote"], int(data["quote"]["max_charge_micros"]))
            db.execute("UPDATE studio_voice_operations SET data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), operation_id))
    return poll(studio, operation_id)


def poll(studio, operation_id):
    data = _get(studio, operation_id)
    if not data.get("intent"):
        return public(data)
    try:
        data["job"] = studio.client().resume(data["intent"])
    except Exception:
        raise WorkError("原任务进度暂不可读取，已保留请求编号；请稍后查询原任务") from None
    if data["kind"] == "clone" and data["job"]["status"] == "succeeded":
        data["voice_id"] = data["job"].get("result", {}).get("voice_id")
    _store(studio, data)
    return public(data)


def operations(studio):
    with studio.db() as db:
        rows = db.execute("SELECT data FROM studio_voice_operations WHERE identity=? ORDER BY rowid DESC LIMIT 30", (key_identity(studio),)).fetchall()
    items = [json.loads(row[0]) for row in rows if json.loads(row[0]).get("intent")]
    result = []
    for item in items:
        if item.get("job", {}).get("status") not in {"succeeded", "failed", "cancelled", "submission_unknown"}:
            try:
                result.append(poll(studio, item["id"]))
                continue
            except WorkError:
                pass
        result.append(public(item))
    return result


def query(studio, operation_id):
    data = _get(studio, operation_id)
    if data["kind"] == "clone" and data.get("job", {}).get("status") == "submission_unknown":
        try:
            data["job"] = studio.client().request("/voices/clone-jobs/" + data["job"]["id"] + "/query", {})
        except Exception as error:
            raise WorkError(str(error)) from None
        _store(studio, data)
    return poll(studio, operation_id)


def rename(studio, voice_id, name):
    try:
        return studio.client().request("/voices/" + voice_id + "/rename", {"name": name})
    except Exception as error:
        raise WorkError(str(error)) from None
