"""Workbench voice enrollment, with durable boundaries around cloud creation.

CosyVoice uses model-bound temporary upload or a configured private OSS object.
An accepted voice is persisted before registration, so recovery never creates it again.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import re
import subprocess
import tempfile
import wave

import requests

from backlot import audio_center as center
from backlot.bailian_asr import _oss_bucket, upload_audio
from lib import bailian_speech as api
from lib.ffmpeg_locator import resolve_ffmpeg

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ENROLLMENT_MODEL = "voice-enrollment"
MODELS = (api.COSYVOICE_TTS_MODEL, api.TTS_MODEL)


def _root() -> Path:
    return center.AUDIO_CENTER_DIR / "bailian-clones"


def _storage_mode() -> str:
    required = ("BAILIAN_OSS_ENDPOINT", "BAILIAN_OSS_BUCKET",
                "BAILIAN_OSS_ACCESS_KEY_ID", "BAILIAN_OSS_ACCESS_KEY_SECRET")
    return "oss" if all(os.environ.get(k, "").strip() for k in required) else "temporary"


def readiness() -> dict:
    required = ("BAILIAN_OSS_ENDPOINT", "BAILIAN_OSS_BUCKET",
                "BAILIAN_OSS_ACCESS_KEY_ID", "BAILIAN_OSS_ACCESS_KEY_SECRET")
    mode = _storage_mode()
    try:
        import oss2  # noqa: F401
        dependency = True
    except ImportError:
        dependency = False
    dependency_ready = mode == "temporary" or dependency
    capability = {"ready": api.configured() and dependency_ready, "requires_oss": mode == "oss",
                  "detail": "请先在 API 管理中保存阿里云百炼 API Key。" if not api.configured() else
                            ("使用百炼临时上传创建 CosyVoice 音色，无需自有 OSS。" if mode == "temporary" else
                             ("使用已配置的私有 OSS 上传录音。" if dependency else "请安装 oss2 云端上传依赖。"))}
    return {"configured": api.configured(), "dependency_ready": dependency_ready, "storage_mode": mode,
            "ready": capability["ready"], "models": list(MODELS), "detail": capability["detail"],
            "model_readiness": {model: capability for model in MODELS}}


def validate_fields(name: object, model: object, consent: object) -> tuple[str, str]:
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 48 or any(ord(c) < 32 for c in name):
        raise center.AudioCenterError("请填写 1–48 字的音色名称，不含换行或控制字符")
    if model not in MODELS:
        raise center.AudioCenterError("请选择已接入的百炼配音模型")
    if consent != "yes":
        raise center.AudioCenterError("请确认有权使用该录音，并同意上传阿里云进行声音复刻")
    return name.strip(), model


def _account() -> str:
    # Persist a hash only: a changed account/endpoint cannot reuse another account's voice.
    return api.fingerprint([api.api_base(), os.environ.get("DASHSCOPE_API_KEY", "")])


def _preflight_name(name: str) -> None:
    records = center._custom_cloud_profile_records(center._load())
    if len(records) >= center.MAX_CUSTOM_CLOUD_PROFILES:
        raise center.AudioCenterError("自定义云端音色已达上限，请先移除不再使用的音色")
    if any(r["name"] == name for r in records):
        raise center.AudioCenterError("已有同名自定义音色，请换一个显示名称")


def _normalize(source: Path, target: Path) -> dict:
    binary = resolve_ffmpeg()
    if not binary:
        raise center.AudioCenterError("未找到 FFmpeg，请先完成项目基础初始化")
    try:
        command = [binary, "-nostdin", "-y", "-v", "error", "-protocol_whitelist", "file,pipe",
                        "-format_whitelist", "wav,mp3,mov", "-i", str(source.resolve()),
                        "-t", "61", "-vn", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(target)]
        subprocess.run(command,
                       check=True, timeout=90, capture_output=True)
        with wave.open(str(target), "rb") as stream:
            duration = stream.getnframes() / stream.getframerate()
        trimmed = duration > 60
        if trimmed:
            command[command.index("-t") + 1] = "20"
            subprocess.run(command, check=True, timeout=90, capture_output=True)
            with wave.open(str(target), "rb") as stream:
                duration = stream.getnframes() / stream.getframerate()
        if duration < 5:
            raise center.AudioCenterError("参考录音至少需要 5 秒，推荐 10–20 秒清晰单人朗读")
        return {"reference_duration_seconds": duration, "reference_trimmed": trimmed}
    except (subprocess.SubprocessError, OSError, wave.Error) as exc:
        raise center.AudioCenterError("无法解码参考录音，请上传有效的 WAV、MP3 或 M4A 文件") from exc


def public_job(record: dict) -> dict:
    return {key: record[key] for key in ("id", "name", "model_id", "status", "voice_id", "profile_id",
                                        "error", "cleanup_warning", "reference_duration_seconds", "reference_trimmed", "updated_at") if key in record}


def list_jobs() -> dict:
    paths = sorted(_root().glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:12]
    return {"service": readiness(), "jobs": [public_job(api.read_record(p)) for p in paths]}


def _path(job_id: str) -> Path:
    if not re.fullmatch(r"BC-[0-9a-f]{32}", job_id):
        raise center.AudioCenterError("云端克隆任务编号无效")
    return _root() / job_id / "job.json"


def _storage_identity() -> str:
    return api.fingerprint([os.environ.get(k, "") for k in
                           ("BAILIAN_OSS_ENDPOINT", "BAILIAN_OSS_BUCKET", "BAILIAN_OSS_ACCESS_KEY_ID")])


def _cleanup(record: dict, path: Path, bucket=None) -> None:
    if not record.get("oss_key") or record.get("upload_deleted"):
        return
    try:
        if record.get("storage") != _storage_identity():
            raise center.AudioCenterError("原 OSS 配置已变化")
        if bucket is None:
            bucket = _oss_bucket()
        bucket.delete_object(record["oss_key"])
        record["upload_deleted"] = True
        record.pop("cleanup_warning", None)
    except Exception:
        record["cleanup_warning"] = "临时录音清理失败，请检查私有 OSS 的 haike-voice-clones/ 生命周期"
    api.write_record(path, record)


def _register(record: dict) -> None:
    # Also serialize registrations from different enrollment jobs/processes.
    with api.operation_lock(_root() / "catalog"):
        records = center._custom_cloud_profile_records(center._load())
        existing = next((r for r in records if r.get("provider_id") == "bailian"
                         and r.get("voice_id") == record["voice_id"] and r.get("model_id") == record["model_id"]), None)
        if existing:
            record["profile_id"] = existing["id"]
            return
        _preflight_name(record["name"])
        center.add_custom_cloud_voice({"provider": "bailian", "name": record["name"],
                                       "voice_id": record["voice_id"], "model_id": record["model_id"], "playback_rate": 1.0})
        records = center._custom_cloud_profile_records(center._load())
        record["profile_id"] = next(r["id"] for r in records if r["voice_id"] == record["voice_id"])


def _execute(record: dict, path: Path, audio: Path | None) -> dict:
    if record["account"] != _account():
        raise center.AudioCenterError("百炼账号或业务空间已变化，请恢复创建该任务时的配置")
    if record.get("status") in {"submitting", "ambiguous"} and not record.get("voice_id"):
        record.update(status="ambiguous", error="上次创建的受理结果不明，已停止重发；请核对百炼音色列表后按已有 ID 添加。")
        api.write_record(path, record)
        return public_job(record)
    bucket = None
    try:
        if not record.get("voice_id"):
            if audio is None:
                raise center.AudioCenterError("录音未提交到云端，请重新上传原录音继续")
            _preflight_name(record["name"])
            mode = record.get("upload_storage") or ("oss" if record.get("oss_key") else _storage_mode())
            record.update(status="uploading", upload_storage=mode, updated_at=center._now())
            api.write_record(path, record)
            request_headers = api.headers()
            if mode == "oss":
                storage = _storage_identity()
                if record.get("storage") and storage != record["storage"]:
                    raise center.AudioCenterError("OSS 配置已变化，请恢复原存储配置后继续上传")
                bucket = _oss_bucket()
                record.update(storage=storage)
                # Save the key before upload, retaining lifecycle cleanup after interruption.
                record.setdefault("oss_key", f"haike-voice-clones/{record['id']}/reference.wav")
                record["upload_deleted"] = False
                api.write_record(path, record)
                bucket.put_object_from_file(record["oss_key"], str(audio), headers={"x-oss-object-acl": "private"})
                url = bucket.sign_url("GET", record["oss_key"], 3600, slash_safe=True)
            else:
                # The upload policy must bind the request model, not the target TTS model.
                uploaded = upload_audio(audio, "temporary", model=ENROLLMENT_MODEL)
                url = uploaded["file_url"]
                request_headers["X-DashScope-OssResourceResolve"] = "enable"
            record.update(status="submitting", updated_at=center._now())
            api.write_record(path, record)
            # No automatic retries: create_voice is not idempotent upstream.
            response = requests.post(api.api_base() + "/services/audio/tts/customization",
                headers=request_headers, json={"model": ENROLLMENT_MODEL, "input": {
                    "action": "create_voice", "target_model": record["model_id"], "prefix": "haike", "url": url}},
                timeout=(15, 120), allow_redirects=False)
            if response.status_code >= 500 or 300 <= response.status_code < 400:
                raise api.BailianAmbiguous("云端创建返回异常，受理结果不明；已停止自动重发")
            try:
                data = api.response_json(response)
            except api.BailianSpeechError:
                if 400 <= response.status_code < 500:
                    record["status"] = "rejected"
                raise
            voice_id = (data.get("output") or {}).get("voice_id")
            if not isinstance(voice_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", voice_id) or not voice_id.startswith(record["model_id"] + "-"):
                raise api.BailianAmbiguous("云端未返回有效的音色 ID，受理结果不明；已停止重发")
            record.update(voice_id=voice_id, status="checking", request_id=data.get("request_id"))
            api.write_record(path, record)
        # Querying an accepted voice does not need its original storage credentials.
        data = api.response_json(requests.post(api.api_base() + "/services/audio/tts/customization",
            headers=api.headers(), json={"model": ENROLLMENT_MODEL,
                "input": {"action": "query_voice", "voice_id": record["voice_id"]}},
            timeout=(15, 45), allow_redirects=False))
        output = data.get("output") or {}
        if output.get("target_model") and output["target_model"] != record["model_id"]:
            record.update(status="failed", error="云端音色绑定模型不一致，已保留 ID 并停止登记")
        else:
            status = str(output.get("status") or "").upper()
            if status == "OK":
                _register(record)
                record.update(status="completed", error="")
            elif status in {"UNDEPLOYED", "FAILED"}:
                record.update(status="failed", error="百炼音色未部署或处理失败，请检查录音质量和云端音色状态")
            else:
                record.update(status="checking", error="音色 ID 已保存，正在查询云端状态；可继续查询，不会重复创建。")
    except Exception as exc:
        if record.get("voice_id"):
            record["status"] = "checking"
        elif record.get("status") == "submitting":
            record["status"] = "ambiguous"
        elif record.get("status") != "rejected":
            record["status"] = "failed"
        hint = api.safe_error(exc) if isinstance(exc, (center.AudioCenterError, api.BailianSpeechError)) else (
            "连接云端失败，请检查网络并查询已保存的任务。" if isinstance(exc, requests.RequestException)
            else "录音上传或音色保存失败，请检查上传权限、本机空间与音色名称。")
        record["error"] = ("创建受理结果不明，禁止重复提交；请核对云端记录。" if record["status"] == "ambiguous" else "") + hint
    record["updated_at"] = center._now()
    api.write_record(path, record)
    if record["status"] in {"completed", "rejected", "failed"}:
        _cleanup(record, path, bucket)
    return public_job(record)


def create_voice(name: str, model: str, source: Path, consent: str) -> dict:
    name, model = validate_fields(name, model, consent)
    api.headers()
    # Validate storage and local audio before any reference upload/creation.
    if _storage_mode() == "oss":
        _oss_bucket()
    if not source.is_file() or not 0 < source.stat().st_size <= MAX_UPLOAD_BYTES:
        raise center.AudioCenterError("参考录音不能为空，且不能超过 10 MB")
    with tempfile.TemporaryDirectory(prefix="haike-bailian-reference-") as scratch:
        normalized = Path(scratch) / "reference.wav"
        reference = _normalize(source, normalized)
        job_id = "BC-" + api.fingerprint([sha256(normalized.read_bytes()).hexdigest(), model, _account()])[:32]
        path = _path(job_id)
        with api.operation_lock(path.parent):
            record = api.read_record(path)
            if record and record["name"] != name:
                raise center.AudioCenterError("这份录音已有同模型克隆任务，请使用原名称查询；无需重复创建")
            if not record:
                _preflight_name(name)
                record = {"id": job_id, "name": name, "model_id": model, "account": _account(), "status": "queued", **reference}
                api.write_record(path, record)
            if record.get("status") == "completed":
                return public_job(record)
            return _execute(record, path, normalized)


def resume_voice(job_id: str) -> dict:
    path = _path(job_id)
    if not path.is_file():
        raise center.AudioCenterError("未找到云端克隆任务")
    with api.operation_lock(path.parent):
        record = api.read_record(path)
        if not record.get("voice_id"):
            raise center.AudioCenterError("没有可查询的音色 ID；结果不明时请核对云端，不要重复创建")
        return _execute(record, path, None)
