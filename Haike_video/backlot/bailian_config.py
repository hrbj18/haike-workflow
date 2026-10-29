"""Local Bailian credentials, independent service health and explicit self-tests."""
from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timezone
from uuid import uuid4

from backlot.ai_text import _atomic_write_text, _read_env_file, _secrets_path, _quote_env_value
from backlot.state import REPO_ROOT
from lib import bailian_speech as api

BailianConfigError = api.BailianSpeechError
CONFIG_FIELDS = {
    "api_key": "DASHSCOPE_API_KEY", "workspace_id": "DASHSCOPE_WORKSPACE_ID",
    "asr_storage": "BAILIAN_ASR_STORAGE", "oss_endpoint": "BAILIAN_OSS_ENDPOINT",
    "oss_bucket": "BAILIAN_OSS_BUCKET", "oss_access_key_id": "BAILIAN_OSS_ACCESS_KEY_ID",
    "oss_access_key_secret": "BAILIAN_OSS_ACCESS_KEY_SECRET",
}
SECRET_FIELDS = {"api_key", "oss_access_key_id", "oss_access_key_secret"}
HEALTH_FILE = REPO_ROOT / ".backlot" / "audio" / "bailian-health.json"
SELFTEST_DIR = REPO_ROOT / ".backlot" / "audio" / "bailian-tests"
_LOCK = threading.RLock()
_TEST_LOCK = threading.Lock()


def _config_identity():
    return api.fingerprint({name: os.environ.get(env, "") for name, env in CONFIG_FIELDS.items()})


def read_bailian_config():
    health = api.read_record(HEALTH_FILE)
    if health.get("config_identity") != _config_identity():
        health = {}
    return {
        "configured": api.configured(), "api_key_configured": api.configured(),
        "workspace_id": os.environ.get("DASHSCOPE_WORKSPACE_ID", ""), "region": "cn-beijing",
        "tts_model": api.TTS_MODEL, "tts_models": list(api.TTS_MODELS), "asr_model": api.ASR_MODEL,
        "asr_storage": os.environ.get("BAILIAN_ASR_STORAGE", "temporary"),
        "oss_endpoint": os.environ.get("BAILIAN_OSS_ENDPOINT", ""), "oss_bucket": os.environ.get("BAILIAN_OSS_BUCKET", ""),
        "oss_access_key_id_configured": bool(os.environ.get("BAILIAN_OSS_ACCESS_KEY_ID")),
        "oss_access_key_secret_configured": bool(os.environ.get("BAILIAN_OSS_ACCESS_KEY_SECRET")),
        "health": {name: health.get(name, {"status": "untested"}) for name in ("tts", "asr")},
        "console_url": "https://bailian.console.aliyun.com/", "storage": ".env.secrets.local",
    }


def save_bailian_config(payload):
    with _LOCK:
        path = _secrets_path()
        lines, current = _read_env_file(path)
        updates = {}
        for field, env in CONFIG_FIELDS.items():
            if field not in payload:
                continue
            value = str(payload[field] or "").strip()
            if field in SECRET_FIELDS and not value:
                continue
            if len(value) > 1024 or any(c.isspace() for c in value):
                raise BailianConfigError("百炼配置不能包含空格、换行或超长内容")
            updates[env] = value
        merged = {**current, **{env: os.environ[env] for env in CONFIG_FIELDS.values() if env in os.environ}, **updates}
        if not merged.get("DASHSCOPE_API_KEY"):
            raise BailianConfigError("请填写阿里云百炼 API Key")
        workspace = merged.get("DASHSCOPE_WORKSPACE_ID", "")
        if workspace and not re.fullmatch(r"[A-Za-z0-9-]{1,80}", workspace):
            raise BailianConfigError("百炼业务空间 ID 格式无效")
        if merged.get("BAILIAN_ASR_STORAGE", "temporary") not in {"temporary", "oss"}:
            raise BailianConfigError("ASR 存储方式只能为 temporary 或 oss")
        if merged.get("BAILIAN_ASR_STORAGE") == "oss":
            if not re.fullmatch(r"https://oss-[a-z0-9-]+\.aliyuncs\.com", merged.get("BAILIAN_OSS_ENDPOINT", "")):
                raise BailianConfigError("OSS 地址应类似 https://oss-cn-beijing.aliyuncs.com")
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", merged.get("BAILIAN_OSS_BUCKET", "")):
                raise BailianConfigError("请填写有效的 OSS Bucket 名称")
            if not all(merged.get(k) for k in ("BAILIAN_OSS_ACCESS_KEY_ID", "BAILIAN_OSS_ACCESS_KEY_SECRET")):
                raise BailianConfigError("自有 OSS 模式需要填写 OSS AccessKey ID 和 Secret")
        pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
        output = [line for line in lines if not ((m := pattern.match(line)) and m.group(1) in updates)]
        output.extend(f"{env}={_quote_env_value(value)}" for env, value in updates.items())
        _atomic_write_text(path, "\n".join(output).rstrip() + "\n")
        os.environ.update(updates)
        return read_bailian_config()


def clear_bailian_config():
    with _LOCK:
        path = _secrets_path()
        lines, _ = _read_env_file(path)
        names = {CONFIG_FIELDS[f] for f in SECRET_FIELDS}
        pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
        _atomic_write_text(path, "\n".join(line for line in lines if not ((m := pattern.match(line)) and m.group(1) in names)).rstrip() + "\n")
        for name in names:
            os.environ.pop(name, None)
        return read_bailian_config()


def test_bailian_connection(service):
    if service not in {"tts", "asr"}:
        raise BailianConfigError("请选择 TTS 或 ASR 测试")
    if not _TEST_LOCK.acquire(blocking=False):
        raise BailianConfigError("百炼测试正在执行，请等待完成")
    identity = _config_identity()
    status = {"status": "failed", "error": "测试被中断"}
    try:
        from tools.audio.bailian_tts import BailianTTS
        from backlot.bailian_asr import transcribe_file
        test_id = uuid4().hex
        output = SELFTEST_DIR / test_id / "sample.wav"
        result = BailianTTS().execute({"text": "你好，欢迎体验这段语音合成。", "voice_id": api.TEST_VOICE,
            "model": api.TTS_MODEL, "rate": 1.0, "output_path": str(output)})
        if not result.success:
            raise BailianConfigError(result.error)
        response = {"ok": True, "service": service, "audio_duration_seconds": result.data["audio_duration_seconds"],
                    "audio_url": f"/api/bailian/test-audio/{test_id}", "tts_usage": result.data["usage"],
                    "model": api.TTS_MODEL, "voice_id": api.TEST_VOICE}
        if service == "asr":
            text, rows, metadata = transcribe_file(output, artifact_dir=output.parent)
            if not text.strip() or not rows:
                raise BailianConfigError("百炼 ASR 未返回可用文字和时间戳，请检查识别结果")
            response.update({"recognized_text": text, "segment_count": len(rows), "asr_usage": metadata["usage"],
                             "model": api.ASR_MODEL, "task_id": metadata["task_id"]})
        status = {"status": "passed", "tested_at": datetime.now(timezone.utc).isoformat(), "result": response}
        return response
    except Exception as exc:
        status = {"status": "failed", "tested_at": datetime.now(timezone.utc).isoformat(), "error": api.safe_error(exc)}
        raise BailianConfigError(api.safe_error(exc)) from exc
    finally:
        try:
            with _LOCK:
                health = api.read_record(HEALTH_FILE)
                if health.get("config_identity") != identity:
                    health = {"config_identity": identity}
                health[service] = status
                api.write_record(HEALTH_FILE, health)
        finally:
            _TEST_LOCK.release()
