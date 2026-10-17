"""Bailian file transcription with durable submit/poll/download recovery."""
from __future__ import annotations

import os
import re
import math
import subprocess
import time
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import requests

from lib import bailian_speech as api
from lib.ffmpeg_locator import resolve_ffmpeg

BailianASRError = api.BailianSpeechError
BailianASRAmbiguous = api.BailianAmbiguous


def storage_mode():
    value = os.environ.get("BAILIAN_ASR_STORAGE", "temporary").strip()
    if value not in {"temporary", "oss"}:
        raise BailianASRError("阿里云 ASR 存储方式无效")
    return value


def _oss_bucket():
    try:
        import oss2
    except ImportError as exc:
        raise BailianASRError("自有 OSS 模式需要 oss2，请安装项目 requirements-asr.txt 中的依赖") from exc
    endpoint = os.environ.get("BAILIAN_OSS_ENDPOINT", "").strip()
    bucket = os.environ.get("BAILIAN_OSS_BUCKET", "").strip()
    if not re.fullmatch(r"https://oss-[a-z0-9-]+\.aliyuncs\.com", endpoint) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket):
        raise BailianASRError("请填写有效的 OSS HTTPS 地域地址和私有 Bucket 名称")
    access_id = os.environ.get("BAILIAN_OSS_ACCESS_KEY_ID", "").strip()
    secret = os.environ.get("BAILIAN_OSS_ACCESS_KEY_SECRET", "").strip()
    if not access_id or not secret:
        raise BailianASRError("请配置自有 OSS 的 AccessKey ID 和 Secret")
    return oss2.Bucket(oss2.Auth(access_id, secret), endpoint, bucket, connect_timeout=30)


def assert_bailian_asr_ready():
    api.headers()
    api.api_base()
    if storage_mode() == "oss":
        _oss_bucket()


def bailian_asr_runtime_identity():
    return f"bailian:{api.ASR_MODEL}:{api.api_base()}:mono16k-v1"


def upload_audio(path: Path, mode: str, *, model: str = api.ASR_MODEL) -> dict:
    if path.stat().st_size > 1024 ** 3:
        raise BailianASRError("待识别音轨超过 1 GB，请先分割素材")
    if mode == "oss":
        bucket = _oss_bucket()
        key = f"haike-asr/{uuid4().hex}{path.suffix.lower()}"
        bucket.put_object_from_file(key, str(path), headers={"x-oss-object-acl": "private"})
        return {"file_url": bucket.sign_url("GET", key, 172800), "oss_key": key, "storage": mode,
                "oss_bucket": os.environ.get("BAILIAN_OSS_BUCKET", ""),
                "oss_endpoint": os.environ.get("BAILIAN_OSS_ENDPOINT", "")}
    policy = api.response_json(requests.get(api.api_base() + "/uploads",
        params={"action": "getPolicy", "model": model}, headers=api.headers(), timeout=(15, 45)))
    policy = policy.get("data") or policy
    host = str(policy.get("upload_host") or "")
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+\.aliyuncs\.com/?", host):
        raise BailianASRError("百炼上传授权未返回有效的阿里云 HTTPS 地址")
    key = str(policy["upload_dir"]).rstrip("/") + "/" + uuid4().hex + path.suffix.lower()
    fields = {"OSSAccessKeyId": policy["oss_access_key_id"], "Signature": policy["signature"],
              "policy": policy["policy"], "key": key, "success_action_status": "200",
              "x-oss-object-acl": policy.get("x_oss_object_acl", "private"),
              "x-oss-forbid-overwrite": "true"}
    with path.open("rb") as stream:
        response = requests.post(host, data=fields, files={"file": ("audio" + path.suffix.lower(), stream)}, timeout=(15, 300), allow_redirects=False)
    if response.status_code not in {200, 201, 204}:
        raise BailianASRError(f"百炼临时音轨上传失败（HTTP {response.status_code}）")
    return {"file_url": "oss://" + key, "storage": mode}


def _cleanup_upload(record: dict, record_path: Path):
    if record.get("storage") != "oss" or not record.get("oss_key") or record.get("upload_deleted"):
        return
    try:
        if any(record.get(field) != os.environ.get(env, "") for field, env in
               (("oss_bucket", "BAILIAN_OSS_BUCKET"), ("oss_endpoint", "BAILIAN_OSS_ENDPOINT"))):
            raise BailianASRError("OSS 配置已变化，保留原存储中的音轨供生命周期清理")
        _oss_bucket().delete_object(record["oss_key"])
        record["upload_deleted"] = True
        record.pop("cleanup_warning", None)
    except Exception:
        record["cleanup_warning"] = "自有 OSS 临时音轨清理失败，请按 Bucket 生命周期清理 haike-asr/ 前缀"
    api.write_record(record_path, record)


def transcribe_file(audio: Path, *, artifact_dir: Path, on_accepted=None, on_submitting=None,
                    timeout_seconds=900, poll_seconds=3):
    """Preserve the accepted-task boundary on every downstream failure."""
    accepted_task = None

    def remember(task_id):
        nonlocal accepted_task
        accepted_task = task_id
        if on_accepted:
            on_accepted(task_id)

    try:
        return _transcribe_file(audio, artifact_dir=artifact_dir, on_accepted=remember,
            on_submitting=on_submitting, timeout_seconds=timeout_seconds, poll_seconds=poll_seconds)
    except BailianASRError as exc:
        if accepted_task:
            exc.accepted, exc.task_id, exc.definitive = True, accepted_task, False
        raise
    except Exception:
        raise BailianASRError(
            "百炼转写未完成，请保留原任务后重试" if not accepted_task else
            "百炼转写中断，原任务已保存；请恢复查询，不要重新提交",
            accepted=bool(accepted_task), task_id=accepted_task) from None


def _transcribe_file(audio: Path, *, artifact_dir: Path, on_accepted, on_submitting,
                     timeout_seconds, poll_seconds):
    digest = sha256()
    with audio.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    identity = api.fingerprint({"audio": digest.hexdigest(), "runtime": bailian_asr_runtime_identity()})
    directory = artifact_dir / "bailian" / identity[:24]
    with api.operation_lock(directory):
        record_path, result_path = directory / "task.json", directory / "transcript.json"
        record = api.read_record(record_path)
        if record.get("task_id"):
            on_accepted(record["task_id"])
        assert_bailian_asr_ready()
        if record.get("status") == "submitting":
            raise BailianASRAmbiguous("百炼 ASR 上次提交结果不明，可能已计费；请核对云端记录，系统不会重复提交")
        if not record.get("task_id"):
            if not record.get("file_url") or time.time() > record.get("uploaded_at", 0) + 160000:
                record = {**upload_audio(audio, storage_mode()), "uploaded_at": time.time(), "status": "uploaded"}
                api.write_record(record_path, record)
            request_headers = api.headers(**{"X-DashScope-Async": "enable"})
            if record["file_url"].startswith("oss://"):
                request_headers["X-DashScope-OssResourceResolve"] = "enable"
            record.update({"status": "submitting", "model": api.ASR_MODEL, "audio_sha256": digest.hexdigest()})
            api.write_record(record_path, record)
            if on_submitting:
                on_submitting(identity)
            try:
                response = requests.post(api.api_base() + "/services/audio/asr/transcription",
                    headers=request_headers, json={"model": api.ASR_MODEL,
                    "input": {"file_urls": [record["file_url"]]}, "parameters": {"channel_id": [0]}}, timeout=(15, 60))
            except requests.RequestException as exc:
                raise BailianASRAmbiguous("百炼 ASR 提交连接中断，受理状态不明；已停止自动重发") from exc
            if response.status_code >= 500:
                raise BailianASRAmbiguous("百炼 ASR 服务端异常，受理状态不明；请核对云端记录",
                                         http_status=response.status_code)
            try:
                data = api.response_json(response)
            except BailianASRError as exc:
                if exc.definitive:
                    record["status"] = "rejected"
                    api.write_record(record_path, record)
                raise
            task_id = (data.get("output") or {}).get("task_id")
            if not task_id:
                raise BailianASRAmbiguous("百炼 ASR 未返回任务 ID，受理状态不明")
            record.update({"status": "accepted", "task_id": task_id, "request_id": data.get("request_id")})
            api.write_record(record_path, record)
            on_accepted(record["task_id"])
        deadline = time.monotonic() + timeout_seconds
        while not result_path.exists():
            if not record.get("transcription_url"):
                if time.monotonic() >= deadline:
                    raise BailianASRError("百炼 ASR 仍在处理；任务 ID 已保存，重新运行会继续查询，不会重复提交")
                data = api.response_json(requests.get(api.api_base() + "/tasks/" + record["task_id"],
                    headers=api.headers(), timeout=(15, 60)))
                output = data.get("output") or {}
                status = output.get("task_status")
                if status in {"FAILED", "CANCELED"}:
                    record.update({"status": "failed", "error": api.safe_error(output.get("message") or output.get("code"))})
                    api.write_record(record_path, record)
                    _cleanup_upload(record, record_path)
                    raise api.provider_error("百炼 ASR 云端任务失败：" + record["error"],
                        provider_code=output.get("code"), accepted=True, task_id=record["task_id"])
                if status != "SUCCEEDED":
                    time.sleep(poll_seconds)
                    continue
                results = output.get("results") or []
                item = results[0] if results else {}
                if item.get("subtask_status") == "FAILED" or not item.get("transcription_url"):
                    raise api.provider_error("百炼 ASR 任务未返回有效转写结果：" + api.safe_error(item.get("message", "")),
                        provider_code=item.get("code"), accepted=True, task_id=record["task_id"])
                record.update({"status": "succeeded", "transcription_url": item["transcription_url"], "usage": data.get("usage", {})})
                api.write_record(record_path, record)
            api.download(record["transcription_url"], result_path)
        data = api.read_record(result_path)
        text_parts, segments, words = [], [], []
        for transcript in data.get("transcripts", []):
            text_parts.append(str(transcript.get("text") or ""))
            for sentence in transcript.get("sentences", []):
                start, end = float(sentence["begin_time"]) / 1000, float(sentence["end_time"]) / 1000
                if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
                    raise BailianASRError("百炼 ASR 返回的时间戳无效")
                sentence_words = []
                for word in sentence.get("words") or []:
                    a, b = float(word["begin_time"]) / 1000, float(word["end_time"]) / 1000
                    if not math.isfinite(a) or not math.isfinite(b) or a < 0 or b < a:
                        raise BailianASRError("百炼 ASR 返回的词级时间戳无效")
                    sentence_words.append({"start": a, "end": b, "text": str(word.get("text") or "")})
                words.extend(sentence_words)
                segments.append({"start": start, "end": end, "text": str(sentence.get("text") or ""),
                                 "words": sentence_words,
                                 **({"speaker_id": sentence["speaker_id"]} if "speaker_id" in sentence else {})})
        text = "\n".join(text_parts).strip() or "\n".join(s["text"] for s in segments)
        record["status"] = "completed"
        api.write_record(record_path, record)
        _cleanup_upload(record, record_path)
        return text, segments, {"provider": "bailian", "model": api.ASR_MODEL, "task_id": record["task_id"],
            "request_id": record.get("request_id"), "usage": record.get("usage", {}), "words": words,
            "timestamp_unit": "seconds", "remote": True, "billing_unit": "tokens",
            "estimated_cost_cny": api.token_cost(record.get("usage", {}), tts=False),
            "cleanup_warning": record.get("cleanup_warning"), "transcript_path": str(result_path)}


def create_project_transcript_provider(*, project_id, project_dir, asset_id, ffmpeg=None,
        resume_request_id=None, on_accepted=None, on_submitting=None, **_):
    assert_bailian_asr_ready()
    # Capture configuration identity now; do not switch models or endpoints mid-job.
    identity = bailian_asr_runtime_identity()
    directory = Path(project_dir) / "artifacts" / "asr" / str(asset_id)

    def transcribe(source):
        if bailian_asr_runtime_identity() != identity:
            raise BailianASRError("百炼 ASR 配置在任务启动后发生变化，请恢复原配置后继续")
        binary = ffmpeg or resolve_ffmpeg()
        if not binary:
            raise BailianASRError("本机未发现 FFmpeg，无法提取识别音轨")
        stat = source.stat()
        digest = api.fingerprint([str(source.resolve()), stat.st_size, stat.st_mtime_ns])[:24]
        directory.mkdir(parents=True, exist_ok=True)
        audio = directory / f"bailian-{digest}.mp3"
        if not audio.exists():
            temporary = audio.with_name(audio.stem + ".extracting.mp3")
            result = subprocess.run([binary, "-y", "-v", "error", "-i", str(source), "-vn", "-map", "0:a:0",
                "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "48k", str(temporary)],
                capture_output=True, timeout=1800)
            if result.returncode or not temporary.exists() or temporary.stat().st_size < 256:
                raise BailianASRError("素材没有可用音轨，或音轨提取失败")
            temporary.replace(audio)
        try:
            return transcribe_file(audio, artifact_dir=directory, on_accepted=on_accepted, on_submitting=on_submitting)
        except BailianASRError:
            raise
        except Exception as exc:
            raise BailianASRError("百炼转写未完成：" + api.safe_error(exc)) from exc
    return transcribe
