"""Explicit local-machine audio profile, using provider credentials only on the server.

This is not a relay account or a charging ledger. Quotes are provider-cost
estimates; the upstream APIs do not enforce the displayed application budget.
An exclusive durable intent precedes every call that may spend money. Unknown
submissions are never retried, including after another quote or process restart.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import tempfile
import wave
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from contextlib import nullcontext
from functools import wraps
from pathlib import Path
from types import SimpleNamespace

from backlot.work_catalog import WorkError
from lib import bailian_speech as records

MODE = "internal_local"
TTS_MODEL = "haike/internal-tts"
CLONE_MODEL = "haike/voice-clone"
PUBLIC_TARGET = "cosyvoice-v3-flash"
PRIVATE_TARGET = "cosyvoice-v3.5-flash"
ID = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
OPERATION = re.compile(r"call_[a-f0-9]{32}")
FILE = re.compile(r"if_[a-f0-9]{32}")
QUOTE = re.compile(r"iq_[a-f0-9]{32}")
PUBLIC = (
    ("longanyang", "龙安洋", "male"), ("longanlang_v3", "龙安朗", "male"),
    ("longshuo_v3", "龙硕", "male"), ("longanhuan_v3", "龙安欢", "female"),
    ("longanwen_v3", "龙安温", "female"), ("longyue_v3", "龙悦", "female"),
)
PUBLIC_IDS = frozenset("pub_" + voice[0] for voice in PUBLIC)


def _platform():
    root = str(Path(__file__).resolve().parents[2] / "api-platform")
    if root not in sys.path:
        sys.path.insert(0, root)
    from platform_app import adapters, providers
    return adapters, providers


def _id(value, pattern=ID):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise WorkError("本机音色、文件或操作编号无效")
    return value


def _integer(value):
    if type(value) is bool or not re.fullmatch(r"[0-9]{1,10}", str(value)) or int(value) > 1_000_000_000:
        raise WorkError("费用上限需为整数微元，最高1,000元")
    return int(value)


def _rate(value):
    if type(value) is bool or not isinstance(value, (int, float)) or not math.isfinite(value) or not .5 <= value <= 2:
        raise WorkError("配音倍率需在0.5至2.0之间")
    return round(float(value), 2)


def _scope():
    return {"mode": MODE, "account_scope": "local-machine", "relay_authenticated": False,
            "billing_mode": "provider_direct_estimate", "estimate_only": True,
            "provider_budget_enforced": False}


def _environment_guard():
    try:
        from backlot.studio_services import _LOCK
        return _LOCK
    except ImportError:
        return nullcontext()


def _authenticated(method):
    """Recheck a cached centre's account before every public operation, once per call tree."""
    @wraps(method)
    def guarded(self, *args, **kwargs):
        depth = self._scope_depth.get()
        if not depth:
            self._verify_account()
        token = self._scope_depth.set(depth + 1)
        try:
            return method(self, *args, **kwargs)
        finally:
            self._scope_depth.reset(token)
    return guarded


def _gateway_identity(client):
    try:
        summary = client.request("/account/summary")
        if not isinstance(summary, dict) or summary.get("mode") == "internal_local":
            raise ValueError()
        account = summary.get("account_id") or summary.get("account_name")
        base = client.base_url
        if (not isinstance(account, str) or not account or account != account.strip()
                or len(account) > 512 or any(ord(char) < 32 for char in account)
                or not isinstance(base, str) or not base):
            raise ValueError()
        return "relay_" + records.fingerprint([base.rstrip("/"), account])
    except Exception:
        raise WorkError("无法核验当前海客账号，已停止读取本机私有音色与设置；请恢复账号连接后重试", "unavailable") from None


def _isolated(name):
    """Private module globals avoid redirecting the old shared store in other threads."""
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location("backlot._internal_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LegacyAudioBackend:
    """Reuse mature catalogues, clone checkpoints and exact frozen voice execution."""
    def __init__(self, directory):
        self.center = _isolated("audio_center")
        self.center.AUDIO_CENTER_DIR = Path(directory) / "legacy"
        self.center.AUDIO_CENTER_FILE = self.center.AUDIO_CENTER_DIR / "audio_center.json"
        self.center.PREVIEW_DIRECTORY = self.center.AUDIO_CENTER_DIR / "previews"
        self.clone = _isolated("bailian_voice_clone")
        self.clone.center = self.center

    def identity(self, provider):
        names = {"bailian": ("DASHSCOPE_API_KEY", "DASHSCOPE_WORKSPACE_ID"),
                 "doubao": ("DOUBAO_SPEECH_API_KEY",),
                 "tencent": ("TENCENT_SECRET_ID", "TENCENT_SECRET_KEY", "TENCENT_TTS_REGION"),
                 "voicebox_tts": ("VOICEBOX_BASE_URL",)}.get(provider, ())
        return records.fingerprint([provider, *[os.environ.get(name, "") for name in names]])

    def catalog(self):
        # The new customer surface has exactly the agreed six public Ali voices.
        # Other suppliers' built-ins remain available through the old internal APIs.
        persisted = self.center._load()
        profiles = [profile for profile in [*self.center._doubao_profiles(persisted),
                    *self.center._tencent_profiles(persisted), *self.center._bailian_profiles(persisted)]
                    if profile.get("is_custom_cloud_voice") is True
                    and profile.get("provider_id") in {"bailian", "doubao", "tencent"}]
        try:
            from dashscope.audio.http_tts.http_speech_synthesizer import HttpSpeechSynthesizer  # noqa: F401
            supported = True
        except ImportError:
            supported = False
        profiles.extend({"id": "pub_" + upstream, "name": name, "gender": gender,
                         "provider_id": "bailian", "provider_name": "阿里云百炼",
                         "provider_voice_id": upstream, "model_id": PUBLIC_TARGET,
                         "voice_type": "preset", "kind": "public", "speech_rate": 1.0,
                         "verification": "candidate_unverified", "available": supported and records.configured()}
                        for upstream, name, gender in PUBLIC)
        return profiles

    def default(self):
        return self.center._load().get("default_profile_id")

    def freeze(self, profile, rate):
        return self.center._freeze_preview_profile(profile, rate)

    def delete(self, voice_id):
        self.center.remove_custom_cloud_voice(voice_id)

    def normalize_audio(self, source, target):
        if source.suffix.lower() == ".ogg":
            import subprocess
            from lib.ffmpeg_locator import resolve_ffmpeg
            converted = target.with_suffix(".decoded.wav")
            try:
                subprocess.run([resolve_ffmpeg(), "-nostdin", "-y", "-v", "error",
                                "-protocol_whitelist", "file,pipe", "-format_whitelist", "ogg",
                                "-i", str(source), "-t", "61", "-vn", "-ac", "1", "-ar", "24000",
                                "-c:a", "pcm_s16le", str(converted)], check=True, capture_output=True, timeout=90)
                return self.clone._normalize(converted, target)
            finally:
                converted.unlink(missing_ok=True)
        return self.clone._normalize(source, target)

    def _clone(self, request, folder, checkpoint, state, initial):
        if not initial:
            identity = state.get("legacy_job_id")
            if not identity or not self.clone._path(identity).is_file():
                return None
            saved = records.read_record(self.clone._path(identity))
            if saved.get("status") == "completed":
                result = self.clone.public_job(saved)
            elif saved.get("voice_id"):
                result = self.clone.resume_voice(identity)  # query_voice only; never create again
            else:
                return None
        else:
            name, model = self.clone.validate_fields(request["name"], request["model_id"], "yes")
            normalized = folder / "reference.wav"
            reference = self.clone._normalize(Path(request["audio_path"]), normalized)
            identity = "BC-" + records.fingerprint([
                hashlib.sha256(normalized.read_bytes()).hexdigest(), model, self.clone._account()])[:32]
            path = self.clone._path(identity)
            with records.operation_lock(path.parent):
                saved = records.read_record(path)
                if saved and saved["name"] != name:
                    raise WorkError("原录音已有克隆任务，请恢复原名称和任务", "conflict")
                if not saved:
                    self.clone._preflight_name(name)
                    saved = {"id": identity, "name": name, "model_id": model,
                             "account": self.clone._account(), "status": "queued", **reference}
                    records.write_record(path, saved)
                checkpoint({"legacy_job_id": identity})  # durable before _execute's cloud creation
                result = self.clone.public_job(saved) if saved.get("status") == "completed" else self.clone._execute(saved, path, normalized)
        if result.get("status") == "completed":
            return {"status": "succeeded", "result": {"voice": {"id": result["profile_id"],
                    "name": result["name"], "model": TTS_MODEL}}, "usage_verified": False}
        if result.get("status") == "checking" and result.get("voice_id"):
            return {"status": "processing", "accepted": True}
        if result.get("status") in {"rejected", "failed"}:
            return {"status": "failed", "accepted": result["status"] != "rejected",
                    "error": "百炼克隆未完成，请核对已保存的原音色任务"}
        return None

    def _bailian(self, request, folder, checkpoint, state, initial):
        adapters, _ = _platform()
        profile = request["profile"]
        from tools.audio.bailian_tts import split_text
        chunks = split_text(request["text"])
        saved = dict(state.get("bailian_chunks") or {})
        paths, verified = [], True
        for index, text in enumerate(chunks):
            key = str(index)
            entry = saved.get(key)
            if not entry:
                if not initial:
                    return None
                entry = {"status": "submitting"}
                saved[key] = entry
                checkpoint({"bailian_chunks": saved})  # before this non-idempotent synthesis
                config = {"enabled": True, "api_key": os.environ.get("DASHSCOPE_API_KEY", ""),
                          "base_url": records.api_base(), "voice": profile["provider_voice_id"],
                          "tts_model": profile["model_id"], "speech_rate": profile["speech_rate"]}
                vault = SimpleNamespace(load=lambda: {"bailian": config})
                try:
                    outcome = adapters.Adapter(vault, folder).execute("haike/cosyvoice", {
                        "text": text, "_model_info": {"provider": "bailian",
                        "target_model": profile["model_id"], "capability": "tts"}},
                        lambda identity: checkpoint({"upstream_id": identity}))
                except adapters.ReceiptMissing as error:
                    if not error.result:
                        return None
                    outcome = {"upstream_id": error.upstream_id, "result": error.result, "usage_verified": False}
                except adapters.Rejected:
                    return {"status": "failed", "accepted": bool(index), "error": "供应商明确拒绝本次配音，请核对原模型、音色和API配置；已完成片段继续保留"}
                entry = {"status": "accepted", "provider_result": outcome}
                saved[key] = entry
                checkpoint({"bailian_chunks": saved})  # URL/receipt precedes download.
            if entry["status"] != "accepted":
                return None  # Unknown segment has no safe synchronous resubmit/query.
            outcome = entry["provider_result"]
            url = (outcome.get("result") or {}).get("audio_url")
            if not url:
                return None
            pcm = folder / f"chunk-{index:04d}.wav"
            if not _wav(pcm):
                raw = folder / f"provider-{index:04d}.wav"
                if not raw.is_file():
                    records.download(url, raw)
                from backlot.tts_runtime import _convert_to_wav
                if _convert_to_wav(raw, pcm) or not _wav(pcm):
                    pcm.unlink(missing_ok=True)
                    return None
            paths.append(pcm)
            verified = verified and outcome.get("usage_verified", True)
        target = folder / "preview.wav"
        temporary = folder / "preview.assembling.wav"
        with wave.open(str(temporary), "wb") as writer:
            writer.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            for path in paths:
                with wave.open(str(path), "rb") as reader:
                    writer.writeframes(reader.readframes(reader.getnframes()))
        temporary.replace(target)
        return {"status": "succeeded", "result": {}, "usage_verified": verified}

    def _doubao(self, request, folder, checkpoint, state, initial):
        """Reuse the established wire codec, persisting task_id before any polling."""
        import uuid
        import requests
        from tools.audio.doubao_tts import DoubaoTTS
        from backlot.tts_runtime import _convert_to_wav
        from backlot.studio_avatar import download_result
        profile, tool = request["profile"], DoubaoTTS()
        key = os.environ.get("DOUBAO_SPEECH_API_KEY", "")
        if not key:
            return {"status": "failed", "accepted": False, "error": "请先配置豆包Speech API Key"}
        resource = profile.get("resource_id") or tool.DEFAULT_RESOURCE_ID
        task_id = state.get("doubao_task_id")
        if not task_id:
            if not initial:
                return None
            request_id = str(uuid.UUID(hex=folder.name.removeprefix("call_")))
            checkpoint({"doubao_request_id": request_id})
            inputs = {"text": request["text"], "format": "mp3", "sample_rate": 24000,
                      "speech_rate": int(round((profile["speech_rate"] - 1) * 100)), "enable_timestamp": True}
            response = requests.post(tool.SUBMIT_URL,
                headers=tool._headers(api_key=key, resource_id=resource, request_id=request_id, return_usage=True),
                json=tool._submit_body(inputs, voice_id=profile["provider_voice_id"], request_id=request_id),
                timeout=(10, 60), allow_redirects=False)
            if response.status_code in {400, 401, 403, 404, 422, 429}:
                return {"status": "failed", "accepted": False, "error": "豆包明确拒绝本次配音，请核对原配置"}
            value = tool._json_or_raise(response)
            tool._raise_for_doubao_error(response.status_code, value)
            task_id = (value.get("data") or {}).get("task_id")
            if not isinstance(task_id, str) or not 0 < len(task_id) <= 256:
                return None
            checkpoint({"doubao_task_id": task_id})
        value = state.get("doubao_result")
        if value is None:
            response = requests.post(tool.QUERY_URL,
                headers=tool._headers(api_key=key, resource_id=resource, request_id=str(uuid.uuid4()), return_usage=True),
                json={"task_id": task_id}, timeout=(10, 60), allow_redirects=False)
            value = tool._json_or_raise(response)
            tool._raise_for_doubao_error(response.status_code, value)
            status = (value.get("data") or {}).get("task_status")
            if status == 3:
                return {"status": "failed", "accepted": True, "error": "豆包原任务明确失败；请核对原任务与账单"}
            if status != 2:
                return {"status": "processing"}
            checkpoint({"doubao_result": value})
        url = (value.get("data") or {}).get("audio_url")
        if not url:
            return None
        raw, target = folder / "provider.mp3", folder / "preview.wav"
        if not _wav(target):
            if not raw.is_file():
                download_result(url, raw)
            if _convert_to_wav(raw, target) or not _wav(target):
                target.unlink(missing_ok=True)
                return None
        return {"status": "succeeded", "result": {}, "usage_verified": bool((value.get("data") or {}).get("usage"))}

    def _legacy_bailian(self, request, folder, initial):
        from tools.audio.bailian_tts import split_text
        from backlot.tts_runtime import generate_voice_audio
        target = folder / "preview.wav"
        if not initial:
            if _wav(target):
                return {"status": "succeeded", "result": {}, "usage_verified": False}
            journals = list((folder / ".preview.wav.bailian").glob("*/*.json"))
            if len(journals) != len(split_text(request["text"])):
                return None
            if any(not records.read_record(path).get("audio_url") for path in journals):
                return None  # No missing, rejected or unknown segment may trigger a new POST.
        result = generate_voice_audio(text=request["text"], profile=request["profile"], output_path=target,
                                      language="zh", sample_mode=request.get("purpose") != "production")
        return {"status": "succeeded", "result": {}, "usage_verified": False} if result.success and _wav(target) else None

    def execute(self, request, folder, checkpoint, state, *, initial):
        if request["kind"] == "clone":
            return self._clone(request, folder, checkpoint, state, initial)
        if request["profile"]["provider_id"] == "bailian":
            if request["profile"].get("model_id") not in {PUBLIC_TARGET, PRIVATE_TARGET}:
                return self._legacy_bailian(request, folder, initial)
            return self._bailian(request, folder, checkpoint, state, initial)
        if request["profile"]["provider_id"] == "doubao":
            return self._doubao(request, folder, checkpoint, state, initial)
        target = folder / "preview.wav"
        if not initial:
            return {"status": "succeeded", "result": {}} if _wav(target) else None
        from backlot.tts_runtime import generate_voice_audio
        result = generate_voice_audio(text=request["text"], profile=request["profile"],
                                      output_path=target, language="zh", sample_mode=request.get("purpose") != "production")
        if not result.success or not _wav(target):
            return None  # Mature legacy synchronous tools cannot safely re-submit an unknown request.
        if request["profile"]["provider_id"] == "voicebox_tts":
            error = self.center._apply_local_preview_tempo(target, request["profile"]["speech_rate"])
            if error:
                return None
        return {"status": "succeeded", "result": {}, "usage_verified": False}


def _wav(path):
    try:
        with wave.open(str(path), "rb") as audio:
            return (audio.getnframes() > 0 and audio.getsampwidth() == 2
                    and audio.getnchannels() == 1 and audio.getframerate() == 24000
                    and len(audio.readframes(audio.getnframes())) == audio.getnframes() * 2)
    except (OSError, wave.Error, EOFError):
        return False


class InternalAudioCenter:
    def __init__(self, studio, *, pricing=None, backend=None):
        if backend is None:
            from backlot.studio_services import refresh_private_environment
            refresh_private_environment()
        self.studio = studio
        self.root = studio.private / "audio-center-internal"
        self.gateway = None
        self._scope_depth = ContextVar("internal-audio-scope-depth", default=0)
        from backlot.studio_services import service_mode
        if service_mode(studio) == "internal":
            self.account = "internal-local-machine"
            namespace = "local-machine"
        else:
            try:
                # Explicit configuration returns the raw authenticated gateway,
                # not GatewayRoutingClient -> InternalClient -> this centre.
                self.gateway = studio.client(studio.configuration())
            except Exception:
                raise WorkError("请先连接可核验身份的海客账号，再使用备用音色中心", "unavailable") from None
            self.account = namespace = _gateway_identity(self.gateway)
        self.directory = self.root / namespace
        self.directory.mkdir(parents=True, exist_ok=True)
        self.backend = backend or LegacyAudioBackend(self.directory)
        self.pricing = {f"tts:bailian:{PUBLIC_TARGET}": {"per_character_micros": 100},
                        f"tts:bailian:{PRIVATE_TARGET}": {"per_character_micros": 80},
                        **(pricing or {})}

    def _verify_account(self):
        from backlot.studio_services import service_mode
        current_internal = service_mode(self.studio) == "internal"
        if current_internal != (self.gateway is None):
            raise WorkError("服务模式已变化，请重新打开当前模式的音色中心", "conflict")
        if self.gateway is None:
            return
        try:
            current = self.studio.client(self.studio.configuration())
        except Exception:
            raise WorkError("无法核验当前海客账号，已停止读取本机私有音色与设置", "unavailable") from None
        if _gateway_identity(current) != self.account:
            raise WorkError("当前海客账号已变化，请重新打开该账号的音色中心", "conflict")
        self.gateway = current  # A rotated Key for this same account inherits its namespace.

    def verify_scope(self):
        """Authorize SDK wrapper metadata access before reading its private journals."""
        self._verify_account()
        return self.account

    def _scope(self):
        return {**_scope(), "account_scope": self.account,
                "relay_account_verified": self.gateway is not None}

    def _verifications(self):
        private = records.read_record(self.directory / "verifications.json")
        # Only these six public candidates may inherit the original local test
        # evidence. Never move private profiles, preferences, files or intents.
        for path in (self.root / "local-machine" / "verifications.json",
                     self.root / "public-verifications.json"):
            shared = records.read_record(path)
            for voice_id in PUBLIC_IDS:
                if voice_id in shared:
                    private[voice_id] = {key: shared[voice_id].get(key)
                        for key in ("credential_identity", "model_id")}
        return private

    def _preferences(self):
        return records.read_record(self.directory / "preferences.json") or {"voices": {}}

    def _profile(self, voice_id):
        _id(voice_id)
        profile = next((p for p in self.backend.catalog() if p["id"] == voice_id), None)
        if not profile:
            raise WorkError("本机配置中没有此音色，请重新选择", "missing")
        return dict(profile)

    @_authenticated
    def runtime_profile(self, voice_id, speech_rate=None):
        profile = self._profile(voice_id)
        preference = self._preferences().get("voices", {}).get(voice_id, {})
        rate = _rate(speech_rate if speech_rate is not None else preference.get("speech_rate", profile.get("speech_rate", 1.0)))
        if profile.get("provider_id") == "tencent":
            rate = self.backend.center._snap_tencent_playback_rate(rate)
        frozen = self.backend.freeze(profile, rate)
        frozen["speech_rate"] = rate
        return frozen

    @_authenticated
    def voices(self):
        saved = self._preferences()
        verified = self._verifications()
        items = []
        for profile in self.backend.catalog():
            preferences = {"speech_rate": profile.get("speech_rate", 1.0),
                           **saved.get("voices", {}).get(profile["id"], {})}
            item = {key: profile.get(key) for key in ("id", "name", "gender", "description", "available", "verification")}
            item.update({"model": TTS_MODEL, "model_id": profile.get("model_id") or profile.get("resource_id") or profile.get("default_engine"),
                         "provider": profile.get("provider_id"), "kind": "cloned" if profile.get("is_custom_cloud_voice") or profile.get("voice_type") in {"cloned", "cloud_clone"} else "public",
                         "preferences": preferences})
            if item['kind'] == 'cloned':
                item['description'] = '当前账号的专属音色，可设置配音倍率并关联人物图。'
            verification = verified.get(profile["id"], {})
            if (verification.get("credential_identity") == self.backend.identity(profile.get("provider_id"))
                    and verification.get("model_id") == profile.get("model_id")):
                item["verification"] = "provider_verified"
            if preferences.get("image_file_id"):
                item["portrait_url"] = "/api/studio/audio-center/media/" + preferences["image_file_id"]
            items.append(item)
        default = saved.get("voice_id") or self.backend.default()
        visible = {item["id"] for item in items}
        return {**self._scope(), "items": items, "preferences": {"voice_id": default if default in visible else None,
                "default_unavailable": bool(default and default not in visible)}}

    @_authenticated
    def preferences(self, data, voice_id=None):
        fields = {"speech_rate", "image_file_id"} if voice_id else {"voice_id"}
        if not isinstance(data, dict) or not data or set(data) - fields:
            raise WorkError("本机音色设置包含不支持的字段")
        with records.operation_lock(self.directory / "catalog-lock"):
            saved = self._preferences()
            if not voice_id:
                self._profile(data["voice_id"])
                saved["voice_id"] = data["voice_id"]
            else:
                self._profile(voice_id)
                updated = dict(saved.setdefault("voices", {}).get(voice_id, {}))
                if "speech_rate" in data:
                    updated["speech_rate"] = self.runtime_profile(voice_id, data["speech_rate"])["speech_rate"]
                if "image_file_id" in data:
                    file_id = data["image_file_id"]
                    if file_id is not None and self._file(file_id)["kind"] != "image":
                        raise WorkError("请选择本机上传的人物图")
                    updated["image_file_id"] = file_id
                saved["voices"][voice_id] = updated
            records.write_record(self.directory / "preferences.json", saved)
        return self.voices()

    @_authenticated
    def delete(self, voice_id):
        profile = self._profile(voice_id)
        if not profile.get("is_custom_cloud_voice"):
            raise WorkError("公共或内置音色不能删除")
        with records.operation_lock(self.directory / "catalog-lock"):
            self.backend.delete(voice_id)
            saved = self._preferences()
            saved.get("voices", {}).pop(voice_id, None)
            if saved.get("voice_id") == voice_id:
                saved["voice_id"] = None
            records.write_record(self.directory / "preferences.json", saved)
        return self.voices()

    @_authenticated
    def upload(self, content, kind, filename):
        suffix = Path(filename).suffix.lower()
        accepted = {"audio": {".wav", ".mp3", ".m4a", ".ogg"}, "image": {".png", ".jpg", ".jpeg"}}
        if kind not in accepted or suffix not in accepted[kind] or not content or len(content) > 20 * 1024 * 1024:
            raise WorkError("请上传20MB内有效的参考录音或PNG、JPEG人物图")
        identity = "if_" + hashlib.sha256(kind.encode() + content).hexdigest()[:32]
        folder = self.directory / "files" / identity
        with records.operation_lock(folder):
            if (folder / "file.json").is_file():
                return {"id": identity, "kind": kind, **self._scope()}
            with tempfile.TemporaryDirectory(dir=folder, prefix="upload-") as temporary:
                source = Path(temporary) / ("source" + suffix)
                source.write_bytes(content)
                target = folder / ("sample.wav" if kind == "audio" else "portrait.jpg")
                if kind == "audio":
                    try:
                        self.backend.normalize_audio(source, target)
                    except Exception:
                        raise WorkError("录音无法读取，至少5秒；超过60秒将取前20秒用于克隆") from None
                else:
                    from PIL import Image, ImageOps
                    try:
                        with Image.open(source) as image:
                            if min(image.size) < 256 or image.width * image.height > 40_000_000:
                                raise ValueError()
                            image = ImageOps.exif_transpose(image).convert("RGB")
                            image.thumbnail((2048, 2048))
                            image.save(target, quality=92)
                    except Exception:
                        raise WorkError("人物图无法读取，宽高需至少256像素") from None
                records.write_record(folder / "file.json", {"id": identity, "kind": kind, "name": target.name,
                                     "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
        return {"id": identity, "kind": kind, **self._scope()}

    def _file(self, file_id):
        value = records.read_record(self.directory / "files" / _id(file_id, FILE) / "file.json")
        if not value or value.get("id") != file_id or value.get("name") not in {"sample.wav", "portrait.jpg"}:
            raise WorkError("本机文件不存在", "missing")
        path = self.directory / "files" / file_id / value["name"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != value.get("sha256"):
            raise WorkError("本机文件已改变，请重新上传", "conflict")
        return {**value, "path": path}

    @_authenticated
    def media(self, file_id):
        value = self._file(file_id)
        return value["path"].read_bytes(), "image/jpeg" if value["kind"] == "image" else "audio/wav"

    def _estimate(self, request):
        provider = request.get("profile", {}).get("provider_id", "bailian")
        model = request.get("profile", {}).get("model_id") or request.get("profile", {}).get("resource_id") or request.get("profile", {}).get("default_engine") or request.get("model_id")
        tariff = self.pricing.get(f"{request['kind']}:{provider}:{model}")
        if not isinstance(tariff, dict):
            raise WorkError("该供应商模型尚未确认本机费用估算，请管理员配置后再调用", "unavailable")
        characters = 0
        if request["kind"] == "tts":
            characters = _platform()[1].bailian_tts_characters(request["text"]) if provider == "bailian" else len(request["text"])
        maximum = _integer(tariff.get("fixed_micros", 0)) + characters * _integer(tariff.get("per_character_micros", 0))
        if not maximum and tariff.get("free_confirmed") is not True:
            raise WorkError("零估算尚未确认免费，已停止付费调用", "unavailable")
        return provider, model, _integer(maximum), characters

    @_authenticated
    def quote(self, data):
        with _environment_guard():
            return self._quote_in_environment(data)

    def _quote_in_environment(self, data):
        if not isinstance(data, dict) or set(data) != {"model", "input"} or not isinstance(data["input"], dict):
            raise WorkError("本机配音请求格式无效")
        inputs = data["input"]
        if data["model"] == CLONE_MODEL:
            if set(inputs) - {"name", "audio_file", "consent", "target_model"} or inputs.get("consent") is not True:
                raise WorkError("请确认有权使用该录音并同意上传百炼克隆")
            name = str(inputs.get("name") or "").strip()
            if not name or len(name) > 48 or any(ord(char) < 32 for char in name):
                raise WorkError("请填写1至48字音色名称")
            source = self._file(inputs.get("audio_file"))
            model = inputs.get("target_model", PRIVATE_TARGET)
            if source["kind"] != "audio" or model not in {PRIVATE_TARGET, records.TTS_MODEL}:
                raise WorkError("克隆录音或目标模型无效")
            request = {"kind": "clone", "name": name, "model_id": model,
                       "audio_path": str(source["path"]), "audio_sha256": source["sha256"]}
        elif data["model"] in {TTS_MODEL, "haike/cosyvoice", "haike/cosyvoice-public"}:
            if set(inputs) - {"voice_id", "text", "speech_rate", "purpose"}:
                raise WorkError("配音请求含不支持的字段")
            purpose = inputs.get("purpose", "preview")
            text = str(inputs.get("text") or "").strip()
            if purpose not in {"preview", "production"} or not text or len(text) > (20000 if purpose == "production" else 180):
                raise WorkError("试听需1至180字；生产配音单次需1至20000字")
            profile = self._profile(inputs.get("voice_id"))
            if profile.get("available") is False:
                raise WorkError("此音色或其供应商尚未配置可用，请先完成API设置", "unavailable")
            if (profile.get("provider_id") == "bailian" and profile.get("model_id") == PRIVATE_TARGET
                    and not str(profile.get("provider_voice_id") or "").startswith(PRIVATE_TARGET + "-")):
                raise WorkError("CosyVoice v3.5仅使用绑定该模型的复刻音色；公共音色请选择v3，不能替换模型")
            request = {"kind": "tts", "text": text, "purpose": purpose,
                       "profile": self.runtime_profile(profile["id"], inputs.get("speech_rate"))}
        else:
            raise WorkError("请选择本机配音或克隆服务")
        provider, model, maximum, characters = self._estimate(request)
        request["credential_identity"] = self.backend.identity(provider)
        if self.gateway is not None:
            request["audio_namespace"] = self.account
        identity_request = {key: value for key, value in request.items() if key != "audio_path"}
        signature = records.fingerprint(identity_request)
        quote_id, operation = "iq_" + signature[:32], "call_" + signature[:32]
        existing = records.read_record(self.directory / "operations" / operation / "operation.json")
        if existing.get("signature") == signature and existing.get("quote_public"):
            return existing["quote_public"]
        public = {**self._scope(), "id": quote_id, "operation_id": operation, "model": data["model"],
                  "provider": provider, "provider_model": model, "max_charge_micros": str(maximum),
                  "currency": "CNY",
                  "estimated_characters": characters, "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
                  "billing_note": "供应商直接调用的费用估算，非中转站扣费；真实采购账单可能有差异，上游不执行本机预算硬封顶。"}
        records.write_record(self.directory / "quotes" / (quote_id + ".json"), {"public": public, "request": request, "signature": signature})
        return public

    @_authenticated
    def operation(self, operation):
        value = records.read_record(self.directory / "operations" / _id(operation, OPERATION) / "operation.json")
        if not value or value.get("id") != operation:
            raise WorkError("操作不存在或不属于此本机配置", "missing")
        return value

    def _public(self, value):
        result = dict(value.get("result") or {})
        if value["status"] == "succeeded" and value["request"]["kind"] == "tts":
            result["audio_url"] = f"/api/studio/audio-center/jobs/{value['id']}/audio"
        return {**self._scope(), **{key: value[key] for key in ("id", "status", "accepted", "error", "usage_verified") if key in value},
                "operation_id": value["id"], "charged_micros": None, "result": result or None}

    def _recover(self, value, folder, *, initial=False):
        with _environment_guard():
            return self._recover_in_environment(value, folder, initial=initial)

    def _recover_in_environment(self, value, folder, *, initial=False):
        request = value["request"]
        provider = request.get("profile", {}).get("provider_id", "bailian")
        if self.backend.identity(provider) != request["credential_identity"]:
            raise WorkError("原供应商API配置已变化，请恢复原配置后查询原操作", "conflict")
        if value["status"] in {"succeeded", "failed"}:
            return self._public(value)
        def checkpoint(update):
            value.setdefault("provider_state", {}).update(update)
            records.write_record(folder / "operation.json", value)
        try:
            outcome = self.backend.execute(request, folder, checkpoint, value.get("provider_state", {}), initial=initial)
            if outcome:
                value.update(outcome)
                if outcome.get("status") in {"succeeded", "processing"}:
                    value.pop("error", None)
            if value.get("status") == "succeeded" and request["kind"] == "tts" and not _wav(folder / "preview.wav"):
                value.update(status="submission_unknown", result=None)
            if value.get("status") == "succeeded" and request["kind"] == "tts" and value.get("usage_verified") is True:
                public_voice = request["profile"]["id"] in PUBLIC_IDS
                lock = self.root / "public-verifications-lock" if public_voice else self.directory / "catalog-lock"
                with records.operation_lock(lock):
                    path = (self.root / "public-verifications.json") if public_voice else self.directory / "verifications.json"
                    verified = records.read_record(path)
                    verified[request["profile"]["id"]] = {"credential_identity": request["credential_identity"],
                        "model_id": request["profile"].get("model_id")}
                    records.write_record(path, verified)
            if value.get("status") not in {"succeeded", "failed", "processing"}:
                value.update(status="submission_unknown", error="原调用结果待核对；仅查询或恢复原任务，禁止重新创建付费调用")
        except Exception:
            value.update(status="submission_unknown", error="原任务或音频尚未核对，已保留意图并停止自动重发；请查询原任务")
        records.write_record(folder / "operation.json", value)
        return self._public(value)

    @_authenticated
    def submit(self, data):
        if not isinstance(data, dict) or set(data) != {"quote_id", "operation_id", "max_charge_micros", "confirmed"} or data["confirmed"] is not True:
            raise WorkError("请先查看具体供应商、模型和费用估算，再确认提交")
        maximum = _integer(data["max_charge_micros"])
        quote = records.read_record(self.directory / "quotes" / (_id(data["quote_id"], QUOTE) + ".json"))
        if not quote or quote["public"]["operation_id"] != _id(data["operation_id"], OPERATION):
            raise WorkError("报价与操作编号不一致")
        if maximum < int(quote["public"]["max_charge_micros"]):
            # Existing operations retain their original estimate and maximum.
            if not (self.directory / "operations" / data["operation_id"] / "operation.json").is_file():
                raise WorkError("本次费用上限低于估算，尚未提交")
        folder = self.directory / "operations" / data["operation_id"]
        with records.operation_lock(folder):
            path = folder / "operation.json"
            previous = records.read_record(path)
            if previous:
                if previous["signature"] != quote["signature"] or previous["maximum"] != maximum:
                    raise WorkError("原意图或费用上限已保存，请恢复原操作", "conflict")
                return self._recover(previous, folder)
            if datetime.fromisoformat(quote["public"]["expires_at"]) <= datetime.now(timezone.utc):
                raise WorkError("报价已过期，尚未提交，请重新获取报价", "conflict")
            if maximum < int(quote["public"]["max_charge_micros"]):
                raise WorkError("本次费用上限低于估算，尚未提交")
            value = {"id": data["operation_id"], "signature": quote["signature"], "maximum": maximum,
                     "quote_id": data["quote_id"], "quote_public": quote["public"],
                     "request": quote["request"], "status": "submitting"}
            records.write_record(path, value)  # committed before any provider call
            return self._recover(value, folder, initial=True)

    @_authenticated
    def job(self, operation):
        folder = self.directory / "operations" / _id(operation, OPERATION)
        with records.operation_lock(folder):
            return self._recover(self.operation(operation), folder)

    @_authenticated
    def preview(self, operation):
        value = self.operation(operation)
        target = self.directory / "operations" / operation / "preview.wav"
        if value["status"] != "succeeded" or not _wav(target):
            raise WorkError("原任务的试听音频尚未就绪", "missing")
        return target


AudioCenter = InternalAudioCenter
