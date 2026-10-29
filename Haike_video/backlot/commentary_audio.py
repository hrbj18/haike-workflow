"""Project-owned PCM takes and an at-most-once provider ledger."""
from __future__ import annotations

import wave
from pathlib import Path
from uuid import uuid4

from backlot.commentary_common import (
    CommentaryConflict, CommentaryError, RATE, atomic, digest, file_sha256,
    identifier, immutable, media_tools, number, read_json, run, text, verified,
)


def directory(project, identity):
    identifier(identity, "AU-")
    return Path(project) / "assets/audio/commentary" / identity[:27]


def read(project, identity):
    target = directory(project, identity)
    value = read_json(target / "audio.json")
    verified(target / "audio.wav", value["sha256"])
    if value.get("id") != identity:
        raise CommentaryError("配音身份不匹配")
    return value


def import_audio(project, path, *, narration_text="", kind="narration", provenance="用户导入"):
    if kind not in {"narration", "music"}:
        raise CommentaryError("音频用途必须是 narration 或 music")
    narration_text = text(narration_text, "配音文案", 10000, empty=kind == "music")
    provenance = text(provenance, "音频来源", 2000)
    source = Path(path).resolve()
    if not source.is_file() or source.suffix.lower() not in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}:
        raise CommentaryError("音频不存在或格式不支持")
    source_sha = file_sha256(source)
    identity = "AU-" + digest({"source_sha256": source_sha, "text": narration_text, "kind": kind})
    target = directory(project, identity)
    if (target / "audio.json").is_file():
        return read(project, identity)
    target.mkdir(parents=True, exist_ok=True)
    staging = target / (uuid4().hex[:8] + ".wav")
    try:
        run([media_tools()[0], "-v", "error", "-nostdin", "-y", "-i", source, "-vn", "-ar", RATE,
             "-ac", "2", "-c:a", "pcm_s16le", staging])
        with wave.open(str(staging), "rb") as wav:
            samples = wav.getnframes()
        if not RATE // 10 <= samples <= RATE * 3600:
            raise CommentaryError("音轨须为0.1秒至一小时")
        verified(source, source_sha)
        staging.replace(target / "audio.wav")
        value = {"id": identity, "kind": kind, "text": narration_text, "text_sha256": digest(narration_text),
                 "samples": samples, "sample_rate": RATE, "duration": samples / RATE,
                 "sha256": file_sha256(target / "audio.wav"), "source_sha256": source_sha,
                 "provenance": provenance, "path": str(target / "audio.wav")}
        immutable(target / "audio.json", value)
        return value
    finally:
        staging.unlink(missing_ok=True)


def list_audio(project):
    base = Path(project) / "assets/audio/commentary"
    return [read(project, read_json(p)["id"]) for p in sorted(base.glob("AU-*/audio.json"))]


def _aligned_take(project, take, target):
    metadata = target / "take.wav.tencent.json"
    if metadata.is_file():
        from backlot.commentary_alignment import import_alignment
        try:
            record = import_alignment(project, {"audio_id": take["id"], "tencent_metadata_path": str(metadata)})
            return {**take, "alignment_id": record["id"]}
        except (ValueError, KeyError, OSError):
            return {**take, "alignment_warning": "配音已保存，时间戳未能自动对齐；请核对后导入，勿重复生成配音"}
    return take


def quote(payload):
    from backlot.audio_center import get_voice_profile, freeze_voice_profile
    from backlot.tts_runtime import TENCENT_PROVIDER_ID, CLOUD_PROVIDER_ID, LOCAL_PROVIDER_ID, BAILIAN_PROVIDER_ID
    from tools.audio.tencent_tts import TencentTTS
    from tools.audio.doubao_tts import DoubaoTTS
    from tools.audio.bailian_tts import BailianTTS
    from tools.audio.voicebox_tts import VoiceboxTTS
    narration = text(payload.get("text"), "配音文案", 2000)
    profile = get_voice_profile(str(payload.get("profile_id") or ""))
    if not profile:
        raise CommentaryError("请选择配音中心已有音色")
    frozen = freeze_voice_profile(profile)
    provider = frozen.get("provider_id")
    tool_type = {TENCENT_PROVIDER_ID: TencentTTS, CLOUD_PROVIDER_ID: DoubaoTTS,
                 LOCAL_PROVIDER_ID: VoiceboxTTS, BAILIAN_PROVIDER_ID: BailianTTS}.get(provider)
    if tool_type is None:
        raise CommentaryError("该音色尚未接入配音运行时")
    estimate = float(tool_type().estimate_cost({"text": narration, "model": frozen.get("model_id")}))
    request = {"text": narration, "profile": frozen, "estimated_cost_usd": estimate,
               "characters": len(narration)}
    return {**request, "signature": digest(request), "billing_note": "估算不是账单；零估算不代表免费。"}


def synthesize(project, payload):
    """No fallback and no automatic retry after a provider request may have started."""
    from backlot.tts_runtime import generate_voice_audio
    from backlot.audio_center import _safe_error
    request = quote(payload)
    if payload.get("quote_signature") != request["signature"] or payload.get("confirmed") is not True:
        raise CommentaryConflict("请先核对本次音色、模型、语速和费用估算，再确认生成")
    max_characters = number(payload.get("max_characters"), "单次字数上限", 1, 2000)
    maximum = number(payload.get("max_estimated_cost_usd"), "估算费用上限", 0, 10)
    if request["characters"] > max_characters or request["estimated_cost_usd"] > maximum:
        raise CommentaryError("本次配音超过已确认字数或估算费用上限")
    target = Path(project) / "artifacts/commentary/tts" / request["signature"][:24]
    target.mkdir(parents=True, exist_ok=True)
    ledger = target / "ledger.json"
    if ledger.is_file():
        saved = read_json(ledger)
        if saved.get("signature") != request["signature"]:
            raise CommentaryConflict("配音账本身份不匹配，拒绝覆盖")
        if saved["status"] == "completed":
            return _aligned_take(project, read(project, saved["audio_id"]), target)
        if saved["status"] == "generated":
            audio = import_audio(project, target / "take.wav", narration_text=request["text"],
                                 provenance="配音中心：" + str(request["profile"].get("name")))
            atomic(ledger, {**saved, "status": "completed", "audio_id": audio["id"]})
            return _aligned_take(project, audio, target)
        raise CommentaryConflict("该配音请求可能已受理，请核对原任务或导入已有音轨；不会自动重复付费")
    # The exclusive ledger is the durable submission boundary across UI/CLI processes.
    try:
        with ledger.open("x", encoding="utf-8") as stream:
            import json
            json.dump({**request, "status": "submitting", "max_characters": max_characters,
                       "max_estimated_cost_usd": maximum}, stream, ensure_ascii=False)
    except FileExistsError as exc:
        raise CommentaryConflict("同一配音正在处理，请读取已有记录") from exc
    try:
        result = generate_voice_audio(text=request["text"], profile=request["profile"], output_path=target / "take.wav")
        if not result.success or not (target / "take.wav").is_file():
            raise CommentaryError("配音未取得可用音轨，请核对供应商原任务")
        atomic(ledger, {**request, "status": "generated", "reported_cost_usd": result.cost_usd})
    except Exception as exc:
        atomic(ledger, {**request, "status": "ambiguous", "error": _safe_error(exc)})
        raise CommentaryConflict("配音结果尚未确认，已保留账本并停止自动重发") from exc
    return synthesize(project, payload)
