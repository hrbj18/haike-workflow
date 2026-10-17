"""Bailian Qwen-Audio/CosyVoice TTS over the SpeechSynthesizer HTTP API."""
from __future__ import annotations

import re
import subprocess
import wave
from pathlib import Path

import requests

from lib import bailian_speech as api
from lib.ffmpeg_locator import resolve_ffmpeg
from tools.base_tool import BaseTool, ToolResult, ToolStatus, ToolTier


def split_text(text: str, limit: int = 400) -> list[str]:
    pieces, current = [], ""
    for sentence in re.findall(r"[^。！？!?\n]+[。！？!?\n]*|[。！？!?\n]+", text):
        while len(sentence) > limit:
            if current:
                pieces.append(current)
                current = ""
            cut = max(sentence.rfind(mark, 0, limit) for mark in "，,；; ") + 1
            cut = cut if cut > limit // 2 else limit
            pieces.append(sentence[:cut])
            sentence = sentence[cut:]
        if len(current) + len(sentence) > limit:
            pieces.append(current)
            current = ""
        current += sentence
    if current:
        pieces.append(current)
    return pieces


class BailianTTS(BaseTool):
    name = "bailian_tts"
    provider = "bailian"
    capability = "tts"
    tier = ToolTier.VOICE
    agent_skills = ["dashscope"]
    input_schema = {"type": "object", "required": ["text", "voice_id"], "properties": {
        "text": {"type": "string"}, "voice_id": {"type": "string"},
        "model": {"type": "string", "enum": list(api.TTS_MODELS)},
        "rate": {"type": "number", "minimum": 0.5, "maximum": 2},
        "output_path": {"type": "string"},
    }}

    def get_status(self):
        return ToolStatus.AVAILABLE if api.configured() else ToolStatus.UNAVAILABLE

    def execute(self, inputs):
        try:
            return self._execute(inputs)
        except Exception as exc:
            return ToolResult(success=False, error=api.safe_error(exc), data={"status": getattr(exc, "status", "failed")})

    def _execute(self, inputs):
        text = str(inputs.get("text") or "").strip()
        voice = str(inputs.get("voice_id") or "").strip()
        model = str(inputs.get("model") or api.TTS_MODEL)
        rate = float(inputs.get("rate", 1))
        if not text or len(text) > 20000:
            raise api.BailianSpeechError("百炼配音文本应为 1–20000 个字符")
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", voice):
            raise api.BailianSpeechError("百炼音色 ID 格式无效，请保留原始大小写")
        api.validate_tts_voice(model, voice)
        if not 0.5 <= rate <= 2:
            raise api.BailianSpeechError("百炼语速不受支持")
        binary = resolve_ffmpeg()
        if not binary:
            raise api.BailianSpeechError("请先安装 FFmpeg，以规范化百炼音频")
        target = Path(inputs.get("output_path") or "bailian_tts.wav")
        if target.suffix.lower() != ".wav":
            raise api.BailianSpeechError("百炼配音输出须使用 .wav 格式")
        identity = {"text": text, "voice": voice, "model": model, "rate": rate, "sample_rate": 24000,
                    "endpoint": api.api_base(), "format": "wav", "adapter": 1}
        directory = target.parent / ("." + target.name + ".bailian") / api.fingerprint(identity)[:24]
        with api.operation_lock(directory):
            paths, records = [], []
            for index, chunk in enumerate(split_text(text)):
                record_path = directory / f"{index:04d}.json"
                raw = directory / f"{index:04d}.raw.wav"
                pcm = directory / f"{index:04d}.wav"
                record = api.read_record(record_path)
                if record.get("status") == "submitting":
                    raise api.BailianAmbiguous("上一条百炼配音提交结果不明，可能已计费；请核对控制台后使用新的试听或任务，系统不会自动重发")
                if not record.get("audio_url") and not pcm.exists():
                    request_headers = api.headers()
                    api.write_record(record_path, {"status": "submitting", "model": model, "voice": voice})
                    try:
                        response = requests.post(api.api_base() + "/services/audio/tts/SpeechSynthesizer",
                            headers=request_headers, json={"model": model, "input": {
                                "text": chunk, "voice": voice, "rate": rate, "format": "wav", "sample_rate": 24000}},
                            timeout=(15, 180), allow_redirects=False)
                    except requests.RequestException as exc:
                        raise api.BailianAmbiguous("百炼配音提交连接中断，受理状态不明；已保留记录，禁止自动重复提交") from exc
                    if response.status_code >= 500 or 300 <= response.status_code < 400:
                        raise api.BailianAmbiguous("百炼服务端异常，配音受理状态不明；请核对控制台后处理")
                    try:
                        data = api.response_json(response)
                    except api.BailianSpeechError:
                        if response.status_code >= 400:
                            api.write_record(record_path, {"status": "rejected"})
                        raise
                    audio_url = (data.get("output") or {}).get("audio", {}).get("url")
                    if not audio_url:
                        raise api.BailianAmbiguous("百炼已响应但未返回音频地址，已停止自动重试")
                    record = {"status": "accepted", "request_id": data.get("request_id"),
                              "usage": data.get("usage", {}), "audio_url": audio_url}
                    api.write_record(record_path, record)
                if not pcm.exists():
                    if not raw.exists():
                        api.download(record["audio_url"], raw)
                    normalizing = pcm.with_name(pcm.stem + ".normalizing.wav")
                    completed = subprocess.run([binary, "-y", "-v", "error", "-i", str(raw),
                        "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(normalizing)],
                        capture_output=True, timeout=120)
                    if completed.returncode:
                        normalizing.unlink(missing_ok=True)
                        raise api.BailianSpeechError("百炼配音已生成，但音频规范化失败；原音频已保留，重试将复用")
                    normalizing.replace(pcm)
                with wave.open(str(pcm), "rb") as reader:
                    if reader.getnframes() <= 0:
                        raise api.BailianSpeechError("百炼返回了空音频")
                record["status"] = "completed"
                api.write_record(record_path, record)
                paths.append(pcm)
                records.append({k: v for k, v in record.items() if k != "audio_url"})
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".assembling")
            with wave.open(str(temporary), "wb") as writer:
                writer.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                for path in paths:
                    with wave.open(str(path), "rb") as reader:
                        writer.writeframes(reader.readframes(reader.getnframes()))
            temporary.replace(target)
            with wave.open(str(target), "rb") as reader:
                duration = reader.getnframes() / reader.getframerate()
            usage = {key: sum(int(r.get("usage", {}).get(key) or 0) for r in records)
                     for key in ("input_tokens", "output_tokens", "total_tokens", "characters")}
            metadata = {**identity, "provider": "bailian", "usage": usage, "requests": records,
                        "chunk_count": len(paths), "audio_duration_seconds": duration,
                        "estimated_cost_cny": api.tts_cost(usage, model), "billing_unit": api.tts_billing_unit(model)}
            metadata_path = target.with_suffix(".wav.bailian.json")
            api.write_record(metadata_path, metadata)
            return ToolResult(success=True, data={**metadata, "output": str(target), "metadata_path": str(metadata_path)},
                              artifacts=[str(target), str(metadata_path)], model=model)
