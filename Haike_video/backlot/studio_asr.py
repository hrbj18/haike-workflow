"""Optional offline speech clock. New quotes freeze the engine; old jobs keep theirs."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, sha


def configuration(studio):
    path = studio.private / "studio-asr/config.json"
    return json.loads(path.read_text()) if path.is_file() else {"provider": "gateway"}


def identity(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def status(studio):
    c = configuration(studio)
    ready = (c.get("provider") == "local-whisper" and c.get("verified") is True
             and Path(c.get("python", "")).is_file()
             and all((Path(c.get("model_dir", "")) / name).is_file()
                     for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")))
    return {"provider": c.get("provider", "gateway"), "ready": ready,
            "name": "本地 Whisper · 词级时间轴" if ready else "网关语音识别",
            "customer_charge_micros": "0" if ready else None,
            "clock": "audio-word-timestamps" if ready else None}


def snapshot(studio):
    c = configuration(studio)
    if c.get("provider") == "gateway": return {"provider": "gateway"}
    if not status(studio)["ready"]: raise WorkError("本地字幕引擎尚未验收，请联系管理员")
    return {"provider": "local-whisper", "identity": identity(c)}


def validate_result(result, duration):
    """Reject absent, overlapping, or non-finite clocks rather than invent timing."""
    segments = result.get("segments") if isinstance(result, dict) else None
    if not isinstance(segments, list) or not segments: raise WorkError("本地识别未返回语音，请核对音频")
    clean, cursor = [], 0.0
    for s in segments:
        try:
            start, end = float(s["start"]), float(s["end"])
            text = str(s["text"]).strip()
            if not all(map(math.isfinite, (start, end))) or not cursor <= start < end <= duration + .08 or not text: raise ValueError()
            words, word_cursor = [], start
            for w in s["words"]:
                a, b = float(w["start"]), float(w["end"])
                t = str(w["text"])
                if not all(map(math.isfinite, (a, b))) or not word_cursor <= a <= b <= end + .08 or not t.strip(): raise ValueError()
                # Zero-length punctuation does not constitute an observed word clock.
                if a < b:
                    words.append({"start": a, "end": min(b, duration), "text": t,
                                  "probability": w.get("probability")})
                word_cursor = b
            if not words: raise ValueError()
            clean.append({"start": start, "end": min(end, duration), "text": text, "words": words})
            cursor = end
        except (KeyError, TypeError, ValueError):
            raise WorkError("本地识别的真实时间戳无效，未使用文案估算时间") from None
    return {"segments": clean, "clock": "audio-word-timestamps", "provider": "local-whisper"}


def transcribe(studio, frozen, audio, folder, duration):
    c = configuration(studio)
    if frozen.get("identity") != identity(c) or not status(studio)["ready"]:
        raise WorkError("字幕引擎已改变，请恢复原配置后继续原任务")
    if sha(Path(c["model_dir"]) / "model.bin") != c["model_sha256"]:
        raise WorkError("字幕模型文件已改变，请重新验收新任务")
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    fingerprint = {"audio_sha256": sha(Path(audio)), "engine_identity": frozen["identity"]}
    cached = folder / "local-asr.json"
    if cached.is_file():
        data = json.loads(cached.read_text())
        if data["fingerprint"] != fingerprint: raise WorkError("原字幕音频或引擎已改变，不能覆盖旧回执")
        return validate_result(data["result"], duration)
    output = folder / "local-asr-worker.json"
    worker = Path(__file__).resolve().parents[1] / "scripts/studio_asr_worker.py"
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"}
    try:
        run = subprocess.run([c["python"], str(worker), "--model-dir", c["model_dir"],
                              "--audio", str(audio), "--output", str(output)],
                             capture_output=True, timeout=300, env=env)
        if run.returncode: raise ValueError()
        result = validate_result(json.loads(output.read_text()), duration)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise WorkError("本地语音识别未完成，音频已保留；未调用收费识别服务", "unavailable") from None
    atomic_private(cached, {"fingerprint": fingerprint, "result": result, "customer_charge_micros": "0"})
    return result
