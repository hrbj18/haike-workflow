"""Bailian speech transport and durable, secret-free operation records."""
from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests

TTS_MODEL = "qwen-audio-3.1-tts-flash"
COSYVOICE_TTS_MODEL = "cosyvoice-v3.5-flash"
ASR_MODEL = "qwen-audio-3.1-asr-flash-filetrans"
TEST_VOICE = "longanyuanfei_v3.1"
TTS_MODELS = (TTS_MODEL, COSYVOICE_TTS_MODEL)


def validate_tts_voice(model: str, voice: str) -> None:
    if model not in TTS_MODELS:
        raise BailianSpeechError("当前尚未接入该百炼配音模型，请选择已支持的模型")
    if voice.startswith("cosyvoice-") and not voice.startswith(model + "-"):
        raise BailianSpeechError("复刻音色与配音模型不一致，请选择创建该音色时使用的模型")


def tts_billing_unit(model: str) -> str:
    return "characters" if model == COSYVOICE_TTS_MODEL else "tokens"


class BailianSpeechError(RuntimeError):
    required = True


class BailianAmbiguous(BailianSpeechError):
    status = "ambiguous"


def safe_error(value: object) -> str:
    message = str(value)
    for name in ("DASHSCOPE_API_KEY", "BAILIAN_OSS_ACCESS_KEY_ID", "BAILIAN_OSS_ACCESS_KEY_SECRET"):
        secret = os.environ.get(name, "")
        if secret:
            message = message.replace(secret, "[已隐藏]")
    message = re.sub(r"https?://[^\s\"']+", "[云端地址已隐藏]", message)
    return message[:800]


def configured() -> bool:
    return bool(os.environ.get("DASHSCOPE_API_KEY", "").strip())


def api_base() -> str:
    workspace = os.environ.get("DASHSCOPE_WORKSPACE_ID", "").strip()
    if workspace and not re.fullmatch(r"[A-Za-z0-9-]{1,80}", workspace):
        raise BailianSpeechError("百炼业务空间 ID 格式无效")
    host = f"{workspace}.cn-beijing.maas.aliyuncs.com" if workspace else "dashscope.aliyuncs.com"
    return f"https://{host}/api/v1"


def headers(**extra) -> dict:
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not key:
        raise BailianSpeechError("请先在配音中心保存阿里云百炼 API Key")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **extra}


def response_json(response) -> dict:
    try:
        data = response.json()
    except ValueError as exc:
        raise BailianSpeechError(f"百炼返回无效响应（HTTP {response.status_code}）") from exc
    if not response.ok or data.get("code"):
        code = str(data.get("code") or response.status_code)
        hint = {
            401: "API Key 无效或与业务空间不匹配，请检查密钥",
            403: "账号没有该模型或音色的调用权限，请在百炼控制台检查授权与余额",
            429: "请求频率超限，请稍后手动重试",
        }.get(response.status_code, "请检查模型、音色 ID、账号额度及请求参数")
        raise BailianSpeechError(f"阿里云百炼调用失败：{hint}（{code}）：{safe_error(data.get('message', ''))}")
    return data


def fingerprint(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def read_record(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise BailianSpeechError("本地云端调用记录无法读取，已停止以避免重复计费") from exc


def write_record(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".bailian-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def operation_lock(directory: Path):
    """An OS lock releases on process death; a second worker cannot submit twice."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise BailianSpeechError("同一条百炼任务正在执行，请等待完成") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def download(url: str, target: Path) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or not parts.hostname.endswith(".aliyuncs.com"):
        raise BailianSpeechError("百炼返回了非阿里云下载地址，已停止下载")
    secure_url = urlunsplit(("https", parts.netloc, parts.path, parts.query, ""))
    response = requests.get(secure_url, timeout=(15, 180), allow_redirects=False)
    if response.status_code != 200 or not response.content:
        raise BailianSpeechError(f"百炼结果下载失败（HTTP {response.status_code}）；已保留调用记录，可恢复下载")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".download")
    temporary.write_bytes(response.content)
    temporary.replace(target)


def token_cost(usage: dict, *, tts: bool) -> float:
    """CNY list-price estimate, not the account's actual bill or free quota."""
    incoming, outgoing = (1.5, 12.0) if tts else (0.8, 2.7)
    return round((float(usage.get("input_tokens") or 0) * incoming
                  + float(usage.get("output_tokens") or 0) * outgoing) / 1_000_000, 8)


def tts_cost(usage: dict, model: str) -> float:
    """CNY list-price estimate from provider usage, not the account's bill."""
    if model == COSYVOICE_TTS_MODEL:
        return round(float(usage.get("characters") or 0) * 0.8 / 10_000, 8)
    return token_cost(usage, tts=True)
