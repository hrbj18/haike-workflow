"""Small account-scoped avatar presets; resolving never starts production."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
import re

from backlot.studio import TEMPLATES, atomic_private
from backlot.studio_audio import TTS_MODELS, identifier
from backlot.work_catalog import WorkError
from lib import bailian_speech as records

LEGACY_FIELDS = ("portrait_file_id", "voice_id", "speech_rate", "template_id",
                 "target_duration_seconds", "max_charge_micros", "allow_graphic_fallback")
FIELDS = LEGACY_FIELDS + ("network_materials_enabled",)
SUPPORTED = tuple(item for item in TEMPLATES if item["kind"] == "avatar"
                  and item.get("adapter_version") in {"studio-avatar-v1", "avatar-deepblue-n1-v1", "avatar-investment-a-v6"})


def _available(voice):
    status = voice.get("status")
    return voice.get("available") is not False and (not status or str(status).lower() in {
        "ready", "available", "active", "ok", "completed"})


def _values(data):
    if not isinstance(data, dict) or set(data) - set(FIELDS):
        raise WorkError("口播默认设置包含不支持的字段")
    clean = dict(data)
    for key, value in clean.items():
        if value is None:
            continue
        if key in {"portrait_file_id", "voice_id"}:
            identifier(value)
        elif key == "template_id":
            if not isinstance(value, str) or value not in {item["id"] for item in SUPPORTED}:
                raise WorkError("请选择现有口播模板1/2/3或深蓝视窗N1")
        elif key in {"speech_rate", "target_duration_seconds"}:
            low, high = (.5, 2) if key == "speech_rate" else (1, 120)
            if type(value) not in {int, float} or not math.isfinite(value) or not low <= value <= high:
                raise WorkError("倍速需为0.5至2，目标时长需为1至120秒")
            clean[key] = int(value) if int(value) == value else value
        elif key == "max_charge_micros":
            if type(value) is not int or not 1 <= value <= 1_000_000_000:
                raise WorkError("每条预算需为正整数微元，最高1,000元；未设置请留空")
        elif type(value) is not bool:
            raise WorkError("联网素材与图文降级设置需明确选择开启或关闭")
    return clean


def _checksum(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def validate_snapshot(value):
    """Validate a self-contained creation snapshot without loading today's defaults."""
    fields = {"schema_version", "scope_id", "preset_revision", "values", "origins", "voice_model", "fingerprint"}
    if (not isinstance(value, dict) or set(value) != fields or type(value.get("schema_version")) is not int or value["schema_version"] not in {1, 2}
            or type(value.get("preset_revision")) is not int or value["preset_revision"] < 0
            or not isinstance(value.get("scope_id"), str) or not re.fullmatch(r"[a-f0-9]{64}", value["scope_id"])
            or value.get("voice_model") not in TTS_MODELS):
        raise WorkError("口播预设快照格式无效")
    try:
        values = _values(value["values"])
    except WorkError:
        raise WorkError("口播预设快照参数无效") from None
    # A caller may supply an owned local portrait in the task input. It is not
    # an audio-centre file ID and must not be copied into account preferences.
    expected = set(LEGACY_FIELDS if value["schema_version"] == 1 else FIELDS)
    if set(values) != expected or any(item is None for key, item in values.items() if key != "portrait_file_id"):
        raise WorkError("口播预设快照尚未配置完整")
    if (not isinstance(value["origins"], dict) or set(value["origins"]) != expected
            or any(item not in {"explicit", "saved", "voice_preferences", "unset", "default"} for item in value["origins"].values())):
        raise WorkError("口播预设快照来源无效")
    fingerprint = value["fingerprint"]
    if (not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint)
            or not hmac.compare_digest(fingerprint, _checksum({key: item for key, item in value.items() if key != "fingerprint"}))):
        raise WorkError("口播预设快照已变化，请重新解析")
    return deepcopy(value)


class AvatarDefaults:
    def __init__(self, center):
        self.center = center
        self.path = center.directory / "avatar-defaults.json"
        self.scope_id = hashlib.sha256(str(center.account).encode("utf-8")).hexdigest()

    def _saved(self):
        if self.path.is_symlink():
            raise WorkError("口播默认设置文件不可用")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"revision": 0, "values": {}, "updated_at": None}
        except (ValueError, OSError):
            raise WorkError("口播默认设置无法读取，请先修复原记录") from None
        if (not isinstance(value, dict) or value.get("schema_version") != 1
                or type(value.get("revision")) is not int or value["revision"] < 1):
            raise WorkError("口播默认设置记录无效")
        _values(value.get("values"))
        return value

    def _resolved(self, saved, catalog, overrides=None):
        explicit = _values({} if overrides is None else overrides)
        stored = saved["values"]
        voices = {item["id"]: item for item in catalog.get("items", []) if isinstance(item, dict) and item.get("id")}
        voice_id = explicit.get("voice_id", stored.get("voice_id", catalog.get("preferences", {}).get("voice_id")))
        voice = voices.get(voice_id, {})
        prefs = voice.get("preferences", {})
        inherited = {"voice_id": catalog.get("preferences", {}).get("voice_id"),
                     "speech_rate": prefs.get("speech_rate", 1) if voice else None,
                     "portrait_file_id": prefs.get("image_file_id")}
        values, origins = {}, {}
        for key in FIELDS:
            if key == "network_materials_enabled" and key not in explicit and key not in stored:
                values[key], origins[key] = False, "default"
                continue
            source = "explicit" if key in explicit else "saved" if key in stored else "voice_preferences" if inherited.get(key) is not None else "unset"
            values[key] = explicit[key] if key in explicit else stored[key] if key in stored else inherited.get(key)
            origins[key] = source
        values = _values(values)
        missing = [key for key in FIELDS if values[key] is None]
        if not voice or not _available(voice) or not voice.get("model"):
            if "voice_id" not in missing:
                missing.append("voice_id")
        snapshot = {"schema_version": 2, "scope_id": self.scope_id, "preset_revision": saved["revision"],
                    "values": deepcopy(values), "origins": dict(origins), "voice_model": voice.get("model")}
        snapshot["fingerprint"] = _checksum(snapshot)
        return {"revision": saved["revision"], "scope_id": self.scope_id, "updated_at": saved.get("updated_at"),
                "scope_type": "local_machine" if self.center.account == "internal-local-machine" else "haike_account",
                "mode": catalog.get("mode", "gateway"), "values": values, "origins": origins,
                "voice_model": voice.get("model"), "missing_fields": missing, "ready": not missing,
                "snapshot": snapshot,
                "templates": [{"id": item["id"], "name": item["name"]} for item in SUPPORTED],
                "voices": [{"id": item["id"], "name": item.get("name", "未命名音色"),
                            "available": _available(item),
                            "image_file_id": item.get("preferences", {}).get("image_file_id")}
                           for item in voices.values()]}

    def read(self):
        # The existing centre authorizes the current account before exposing its catalog.
        catalog = self.center.voices()
        return self._resolved(self._saved(), catalog)

    def save(self, data):
        if (not isinstance(data, dict) or set(data) != {"expected_revision", "expected_scope_id", "values"}
                or type(data["expected_revision"]) is not int or data["expected_revision"] < 0):
            raise WorkError("请先读取口播默认设置并提供当前版本")
        if data["expected_scope_id"] != self.scope_id:
            raise WorkError("海客账号已变化，请重新打开默认设置", "conflict")
        values = _values(data["values"])
        catalog = self.center.voices()
        if values.get("voice_id") is not None and not any(
                item.get("id") == values["voice_id"] for item in catalog.get("items", [])):
            raise WorkError("当前账号没有这款音色，请重新选择")
        if values.get("portrait_file_id") is not None:
            _, mime = self.center.media(values["portrait_file_id"])
            if mime not in {"image/png", "image/jpeg", "image/webp"}:
                raise WorkError("默认形象需要当前账号的有效人物图片")
        try:
            with records.operation_lock(self.path.parent / "avatar-defaults-lock"):
                saved = self._saved()
                if saved["revision"] != data["expected_revision"]:
                    raise WorkError("口播默认设置已更新，请重新读取后保存", "conflict")
                saved = {"schema_version": 1, "revision": saved["revision"] + 1,
                         "values": {**saved["values"], **values},
                         "updated_at": datetime.now(timezone.utc).isoformat()}
                atomic_private(self.path, saved)
        except records.BailianSpeechError:
            raise WorkError("口播默认设置正在保存，请稍后重试", "conflict") from None
        return self._resolved(saved, catalog)

    def resolve(self, data):
        if not isinstance(data, dict) or set(data) != {"overrides"}:
            raise WorkError("请提供明确覆盖的参数，未指定的参数使用口播默认设置")
        catalog = self.center.voices()
        return self._resolved(self._saved(), catalog, _values(data["overrides"]))
