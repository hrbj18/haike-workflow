"""Private service routing and explicitly gated internal supplier configuration.

Production mode and administration are separate: an internal-mode workbench can
execute jobs but cannot read/write supplier settings. Only the separate loopback
administration instance receives the startup-only administration attributes.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import threading
from urllib.parse import urlsplit

from backlot import ai_text
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError

_LOCK = threading.RLock()


def field(name, env, label, *, secret=False, default=""):
    return {
        "name": name,
        "env": env,
        "label": label,
        "secret": secret,
        "default": default,
    }


PROVIDERS = {
    "bailian": {
        "name": "阿里云百炼",
        "reader": ("bailian_config", "read_bailian_config"),
        "writer": ("bailian_config", "save_bailian_config"),
        "required": ["api_key"],
        "fields": [
            field("api_key", "DASHSCOPE_API_KEY", "API Key", secret=True),
            field("workspace_id", "DASHSCOPE_WORKSPACE_ID", "业务空间"),
            field(
                "asr_storage",
                "BAILIAN_ASR_STORAGE",
                "识别音频暂存",
                default="temporary",
            ),
            field("oss_endpoint", "BAILIAN_OSS_ENDPOINT", "OSS Endpoint"),
            field("oss_bucket", "BAILIAN_OSS_BUCKET", "OSS Bucket"),
            field(
                "oss_access_key_id",
                "BAILIAN_OSS_ACCESS_KEY_ID",
                "OSS AccessKey ID",
                secret=True,
            ),
            field(
                "oss_access_key_secret",
                "BAILIAN_OSS_ACCESS_KEY_SECRET",
                "OSS Secret",
                secret=True,
            ),
        ],
    },
    "tencent": {
        "name": "腾讯云配音与识别",
        "reader": ("tencent_config", "read_tencent_config"),
        "writer": ("tencent_config", "save_tencent_config"),
        "required": ["secret_id", "secret_key"],
        "fields": [
            field("secret_id", "TENCENT_SECRET_ID", "SecretId", secret=True),
            field("secret_key", "TENCENT_SECRET_KEY", "SecretKey", secret=True),
            field(
                "tts_region", "TENCENT_TTS_REGION", "配音地域", default="ap-guangzhou"
            ),
            field(
                "asr_region", "TENCENT_ASR_REGION", "识别地域", default="ap-guangzhou"
            ),
        ],
    },
    "runninghub": {
        "name": "RunningHub 数字人",
        "reader": ("runninghub_config", "read_runninghub_config"),
        "writer": ("runninghub_config", "save_runninghub_config"),
        "required": ["api_key", "workflow_id"],
        "fields": [
            field("api_key", "RUNNINGHUB_API_KEY", "API Key", secret=True),
            field(
                "base_url",
                "RUNNINGHUB_BASE_URL",
                "API 地址",
                default="https://www.runninghub.cn",
            ),
            field(
                "workflow_id",
                "RUNNINGHUB_WORKFLOW_ID",
                "已发布工作流",
                default="2094449979141218305",
            ),
            field(
                "workflow_profile",
                "RUNNINGHUB_WORKFLOW_PROFILE",
                "工作流规格",
                default="infinitetalk_448x560_exact_clock_v2",
            ),
            field(
                "workflow_template",
                "RUNNINGHUB_WORKFLOW_TEMPLATE",
                "源码工作流模板",
                default="config/runninghub/workflow-2094449979141218305.api.json",
            ),
        ],
    },
    "text-ai": {
        "name": "AI 文本与视觉",
        "reader": ("ai_text", "read_text_ai_config"),
        "writer": ("ai_text", "save_text_ai_config"),
        "required": ["api_key"],
        "fields": [
            field("api_key", "OPENAI_API_KEY", "API Key", secret=True),
            field(
                "base_url",
                "OPENAI_BASE_URL",
                "兼容 API 地址",
                default="https://api.openai.com/v1",
            ),
            field(
                "model",
                "OPENAI_TEXT_MODEL",
                "文本模型",
                default=ai_text.DEFAULT_TEXT_MODEL,
            ),
        ],
    },
    "doubao-text": {
        "name": "豆包文本",
        "reader": ("ai_text", "read_doubao_text_ai_config"),
        "writer": ("ai_text", "save_doubao_text_ai_config"),
        "required": ["api_key"],
        "fields": [
            field("api_key", "DOUBAO_API_KEY", "API Key", secret=True),
            field(
                "base_url",
                "DOUBAO_BASE_URL",
                "火山方舟地址",
                default="https://ark.cn-beijing.volces.com/api/v3",
            ),
            field(
                "model",
                "DOUBAO_TEXT_MODEL",
                "文本模型",
                default="doubao-seed-2-1-pro-260628",
            ),
        ],
    },
    "doubao-speech": {
        "name": "豆包语音合成",
        "required": ["api_key"],
        "fields": [
            field("api_key", "DOUBAO_SPEECH_API_KEY", "Speech API Key", secret=True),
            field("voice_type", "DOUBAO_SPEECH_VOICE_TYPE", "默认音色"),
            field(
                "resource_id",
                "DOUBAO_SPEECH_PUBLIC_RESOURCE_ID",
                "公开音色资源",
                default="seed-tts-2.0",
            ),
        ],
    },
    "doubao-asr": {
        "name": "豆包语音识别",
        "reader": ("doubao_asr", "read_doubao_asr_config"),
        "required": ["api_key"],
        "fields": [
            field("api_key", "DOUBAO_ASR_API_KEY", "ASR API Key", secret=True),
            field("mode", "DOUBAO_ASR_MODE", "识别方式", default="flash"),
            field(
                "flash_resource_id",
                "DOUBAO_ASR_FLASH_RESOURCE_ID",
                "极速版资源",
                default="volc.bigasr.auc_turbo",
            ),
            field(
                "standard_resource_id",
                "DOUBAO_ASR_STANDARD_RESOURCE_ID",
                "录音版资源",
                default="volc.seedasr.auc",
            ),
            field("public_base_url", "BACKLOT_PUBLIC_BASE_URL", "本实例公开音频地址"),
            field(
                "media_signing_secret",
                "DOUBAO_ASR_MEDIA_SIGNING_SECRET",
                "音频签名密钥",
                secret=True,
            ),
        ],
    },
    "pexels": {
        "name": "Pexels 素材",
        "required": ["api_key"],
        "fields": [field("api_key", "PEXELS_API_KEY", "API Key", secret=True)],
    },
    "pixabay": {
        "name": "Pixabay 素材",
        "required": ["api_key"],
        "fields": [field("api_key", "PIXABAY_API_KEY", "API Key", secret=True)],
    },
}
ENV_WHITELIST = frozenset(
    item["env"] for provider in PROVIDERS.values() for item in provider["fields"]
) | {
    "OPENAI_SCRIPT_MODEL",
    "OPENAI_VISION_MODEL",
    "DOUBAO_ASR_RESOURCE_ID",
    *{
        f"DOUBAO_SPEECH_{role}_{suffix}"
        for role in ("YAYA", "MENGMENG", "PUBLIC", "PUBLIC_MALE")
        for suffix in ("VOICE_TYPE", "RESOURCE_ID", "ENABLED")
    },
}
_BUDGET_MODELS = {
    "haike/text",
    "haike/avatar",
    "haike/tencent-asr",
    "haike/doubao-asr",
    "haike/bailian-asr",
}


def refresh_private_environment():
    """Refresh only supplier fields after a save from the separate admin process."""
    with _LOCK:
        _, current = ai_text._read_env_file(ai_text._secrets_path())
        for name in ENV_WHITELIST:
            if name in current:
                if current[name]:
                    os.environ[name] = current[name]
                else:
                    os.environ.pop(name, None)


def service_mode(studio):
    path = studio.private / "service-mode.json"
    if not path.is_file():
        return "gateway"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("mode") not in {"gateway", "internal"}:
            raise ValueError()
        return value["mode"]
    except (ValueError, AttributeError, OSError):
        raise WorkError("服务模式私有文件无效，请由本机管理员修复") from None


def audio_mode(studio):
    """Only local operations may enable direct audio on a gateway instance."""
    mode = service_mode(studio)
    path = studio.private / "service-mode.json"
    if not path.is_file():
        return mode
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("audio_mode", mode)
        if value not in {"gateway", "internal"}:
            raise ValueError()
        return value
    except (ValueError, AttributeError, OSError):
        raise WorkError("配音服务模式私有文件无效，请由本机管理员修复") from None


def require_internal_admin(studio):
    if getattr(studio, "internal_admin_enabled", False) is not True or getattr(
        studio, "internal_bind_host", None
    ) not in {"127.0.0.1", "localhost", "::1"}:
        raise WorkError("供应商配置仅允许独立的本机内部管理入口访问", "forbidden")


def _effective(item, current):
    value = ai_text._effective_value(item["env"], current)
    if not value and item["env"] == "OPENAI_TEXT_MODEL":
        value = ai_text._effective_value("OPENAI_SCRIPT_MODEL", current)
    if not value and item["env"] == "DOUBAO_ASR_API_KEY":
        value = ai_text._effective_value("DOUBAO_SPEECH_API_KEY", current)
    return value or item["default"]


def _provider(provider_id):
    if provider_id not in PROVIDERS:
        raise WorkError("未接入该内部供应商", "not_found")
    return PROVIDERS[provider_id]


def _read(provider_id, current):
    provider = _provider(provider_id)
    fields = []
    values = {item["name"]: _effective(item, current) for item in provider["fields"]}
    configured = all(values[name] for name in provider["required"])
    # The legacy Bailian page required optional ASR/OSS storage as well. TTS
    # only needs its API key; missing ASR storage must not disable all audio.
    if provider.get("reader") and provider_id != "bailian":
        module, name = provider["reader"]
        try:
            configured = bool(
                getattr(importlib.import_module("backlot." + module), name)().get(
                    "configured"
                )
            )
        except Exception:  # noqa: BLE001 -- old readers may contain private provider error details
            configured = False
    for item in provider["fields"]:
        public = {
            "name": item["name"],
            "label": item["label"],
            "secret": item["secret"],
            "configured": bool(values[item["name"]]),
        }
        if not item["secret"]:
            public["value"] = values[item["name"]]
        fields.append(public)
    secret_items = [
        item
        for item in provider["fields"]
        if item["secret"] and item["name"] in provider["required"]
    ]
    return {
        "id": provider_id,
        "name": provider["name"],
        "configured": bool(configured),
        "has_key": all(bool(values[item["name"]]) for item in secret_items),
        "fields": fields,
    }


def settings(studio):
    require_internal_admin(studio)
    with _LOCK:
        _, current = ai_text._read_env_file(ai_text._secrets_path())
        return {
            "service_mode": service_mode(studio),
            "internal_enabled": True,
            "providers": [_read(identifier, current) for identifier in PROVIDERS],
            "budget_policy": budget_policy(studio),
            "storage": ".env.secrets.local",
        }


def _validate(values, provider_id):
    for name, value in values.items():
        if len(value) > 2048 or any(ord(c) < 32 for c in value):
            raise WorkError("配置不能包含换行、控制字符或超长内容")
        if name in {
            "api_key",
            "secret_id",
            "secret_key",
            "oss_access_key_id",
            "oss_access_key_secret",
            "media_signing_secret",
        } and any(c.isspace() for c in value):
            raise WorkError("密钥不能包含空格或换行")
        if name.endswith("base_url") or name in {"base_url", "oss_endpoint"}:
            if not value:
                continue
            try:
                parsed = urlsplit(value)
                valid = bool(
                    parsed.hostname
                    and parsed.username is None
                    and parsed.password is None
                    and not parsed.query
                    and not parsed.fragment
                    and (
                        parsed.scheme == "https"
                        or (
                            parsed.scheme == "http"
                            and (provider_id == "text-ai" or parsed.hostname in {"127.0.0.1", "localhost", "::1"})
                        )
                    )
                )
                _ = parsed.port
            except ValueError:
                valid = False
            if not valid:
                message = (
                    "文本中转接口需要 HTTP(S)，地址中不能包含凭据、查询参数或片段"
                    if provider_id == "text-ai" else
                    "接口地址需要 HTTPS；本机模型可使用回环 HTTP，地址中不能包含凭据、查询参数或片段"
                )
                raise WorkError(message)
    if provider_id == "doubao-asr" and (
        values["mode"] not in {"flash", "standard_url"}
        or values["flash_resource_id"] != "volc.bigasr.auc_turbo"
        or values["standard_resource_id"] != "volc.seedasr.auc"
    ):
        raise WorkError("豆包 ASR 模式或资源编号不正确")


def _write_generic(provider, values):
    path = ai_text._secrets_path()
    lines, _ = ai_text._read_env_file(path)
    updates = {item["env"]: values[item["name"]] for item in provider["fields"]}
    pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
    output = [
        line
        for line in lines
        if not ((match := pattern.match(line)) and match.group(1) in updates)
    ]
    output.extend(
        name + "=" + ai_text._quote_env_value(value) for name, value in updates.items()
    )
    ai_text._atomic_write_text(path, "\n".join(output).rstrip() + "\n")
    os.environ.update(updates)


def update_provider(studio, provider_id, payload):
    require_internal_admin(studio)
    provider = _provider(provider_id)
    allowed = {item["name"] for item in provider["fields"]}
    if (
        not isinstance(payload, dict)
        or set(payload) - allowed
        or any(not isinstance(v, str) for v in payload.values())
    ):
        raise WorkError("内部供应商配置字段不正确")
    with _LOCK:
        _, current = ai_text._read_env_file(ai_text._secrets_path())
        values = {
            item["name"]: (
                payload[item["name"]].strip()
                if item["name"] in payload
                and (payload[item["name"]].strip() or not item["secret"])
                else _effective(item, current)
            )
            for item in provider["fields"]
        }
        _validate(values, provider_id)
        try:
            if provider.get("writer"):
                module, name = provider["writer"]
                getattr(importlib.import_module("backlot." + module), name)(values)
            else:
                _write_generic(provider, values)
        except Exception:  # noqa: BLE001 -- provider validators must not echo raw credentials
            raise WorkError(
                "保存供应商配置失败，请检查必填项和配置格式；未执行真实调用"
            ) from None
        _, current = ai_text._read_env_file(ai_text._secrets_path())
        return _read(provider_id, current)


def budget_policy(studio):
    path = studio.private / "internal-services/budget-policy.json"
    try:
        return (
            json.loads(path.read_text(encoding="utf-8"))
            if path.is_file()
            else {"per_call_micros": {}, "daily_limit_micros": "0", "audio_pricing": {}}
        )
    except (OSError, ValueError):
        raise WorkError("内部预算私有配置无效，请由本机管理员修复") from None


def update_budget_policy(studio, payload):
    require_internal_admin(studio)
    if (
        not isinstance(payload, dict)
        or set(payload) - {"per_call_micros", "daily_limit_micros", "audio_pricing"}
        or not {"per_call_micros", "daily_limit_micros"} <= set(payload)
        or not isinstance(payload["per_call_micros"], dict)
    ):
        raise WorkError("请提供每次采购预算与本机每日预算")
    limits, daily = payload["per_call_micros"], payload["daily_limit_micros"]
    if set(limits) - _BUDGET_MODELS:
        raise WorkError("预算包含未接入的内部模型")
    if any(
        not isinstance(v, str) or not re.fullmatch(r"[1-9][0-9]{0,9}", v)
        for v in [*limits.values(), daily]
    ):
        raise WorkError("内部预算需要正整数微元，不得将未知采购费用设为免费")
    pricing = payload.get(
        "audio_pricing", budget_policy(studio).get("audio_pricing", {})
    )
    if not isinstance(pricing, dict) or len(pricing) > 50:
        raise WorkError("内部声音费用估算配置无效")
    for name, tariff in pricing.items():
        if (
            not re.fullmatch(
                r"(?:tts|clone):(?:bailian|tencent|doubao):[A-Za-z0-9_.:-]{1,100}", name
            )
            or not isinstance(tariff, dict)
            or set(tariff) - {"fixed_micros", "per_character_micros", "free_confirmed"}
        ):
            raise WorkError("声音费用估算需绑定具体供应商与上游型号")
        if any(
            type(tariff.get(k, 0)) is not int or not 0 <= tariff.get(k, 0) <= 10**9
            for k in ("fixed_micros", "per_character_micros")
        ):
            raise WorkError("声音费用估算需为非负整数微元")
        if "free_confirmed" in tariff and type(tariff["free_confirmed"]) is not bool:
            raise WorkError("免费创建必须明确确认")
        if (
            not tariff.get("fixed_micros", 0)
            and not tariff.get("per_character_micros", 0)
            and tariff.get("free_confirmed") is not True
        ):
            raise WorkError("未知采购费用不能当作免费")
    clean = {
        "per_call_micros": dict(limits),
        "daily_limit_micros": daily,
        "audio_pricing": pricing,
    }
    atomic_private(studio.private / "internal-services/budget-policy.json", clean)
    return clean
