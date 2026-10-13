"""Private provider configuration, public capability registry and versioned tariffs."""

import json
import os
import re
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

from .store import Problem, audit, canonical, now, uid


def bailian_tts_characters(text):
    """Quote Han as two characters; punctuation, kana and Hangul letters as one.

    Supplementary CJK blocks include reserved extension codepoints so new Han
    additions cannot underquote. SSML markup stays in the quote upper bound;
    settlement uses the supplier receipt, which excludes markup.
    """
    return sum(
        2
        if (
            0x3400 <= ord(char) <= 0x4DBF
            or 0x4E00 <= ord(char) <= 0x9FFF
            or 0xF900 <= ord(char) <= 0xFAFF
            or 0x20000 <= ord(char) <= 0x3FFFF
            or char == "〇"
        )
        else 1
        for char in text
    )


PROVIDERS = {
    "openai": {
        "name": "OpenAI 兼容中转",
        "secrets": ["api_key"],
        "base_url": "https://api.openai.com/v1",
    },
    "bailian": {
        "name": "阿里云百炼",
        "secrets": ["api_key"],
        "base_url": "https://dashscope.aliyuncs.com/api/v1",
    },
    "tencent": {
        "name": "腾讯云",
        "secrets": ["secret_id", "secret_key"],
        "region": "ap-guangzhou",
    },
    "runninghub": {
        "name": "RunningHub",
        "secrets": ["api_key"],
        "base_url": "https://www.runninghub.cn",
        "workflow_id": "2094449979141218305",
    },
    "pexels": {
        "name": "Pexels 素材",
        "secrets": ["api_key"],
        "base_url": "https://api.pexels.com",
    },
}
MODELS = {
    "haike/text": {
        "name": "文本与视觉 · GPT",
        "provider": "openai",
        "target_model": "gpt-6-luna",
        "capability": "chat",
        "meters": {"input_tokens": 1000000, "output_tokens": 1000000},
    },
    "haike/cosyvoice": {
        "name": "CosyVoice Flash 配音",
        "provider": "bailian",
        "target_model": "cosyvoice-v3.5-flash",
        "capability": "tts",
        "meters": {"characters": 10000},
    },
    "haike/tencent-tts": {
        "name": "腾讯精品配音",
        "provider": "tencent",
        "target_model": "TextToVoice/1001",
        "capability": "tts",
        "meters": {"characters": 10000},
    },
    "haike/tencent-asr": {
        "name": "腾讯录音识别",
        "provider": "tencent",
        "target_model": "16k_zh_en",
        "capability": "asr",
        "meters": {"seconds": 3600},
    },
    "haike/avatar": {
        "name": "RunningHub 数字人",
        "provider": "runninghub",
        "target_model": "2094449979141218305",
        "capability": "avatar",
        "meters": {"tasks": 1},
    },
    "haike/assets": {
        "name": "Pexels 素材检索",
        "provider": "pexels",
        "target_model": "pexels-search",
        "capability": "assets",
        "meters": {"requests": 1},
    },
    "haike/illustration": {
        "name": "AI 插画 · GPT Image",
        "provider": "openai",
        "target_model": "gpt-image-2",
        "capability": "image",
        "meters": {"input_tokens": 1000000, "output_tokens": 1000000},
    },
}
UNITS = {
    "characters": "字符",
    "seconds": "秒",
    "input_tokens": "输入 Token",
    "output_tokens": "输出 Token",
    "tasks": "任务",
    "requests": "次",
}
SOURCES = {
    "haike/cosyvoice": (
        "800000",
        "https://help.aliyun.com/zh/model-studio/cosyvoice-v3-5-flash",
    ),
    "haike/tencent-tts": (
        "300000",
        "https://cloud.tencent.com/document/product/1073/34112",
    ),
    "haike/tencent-asr": (
        "1750000",
        "https://cloud.tencent.com/document/product/1093/35686",
    ),
    "haike/assets": ("0", "https://www.pexels.com/api/"),
}


class Vault:
    def __init__(self, directory):
        self.directory = directory
        self.path = directory / "providers.encrypted"
        self.key_path = directory / "providers.master.key"

    def cipher(self):
        if not self.key_path.exists():
            fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(Fernet.generate_key())
        return Fernet(self.key_path.read_bytes())

    def load(self):
        return (
            json.loads(self.cipher().decrypt(self.path.read_bytes()))
            if self.path.exists()
            else {}
        )

    def write(self, value):
        temporary = self.path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(self.cipher().encrypt(canonical(value).encode()))
        temporary.replace(self.path)

    def public(self):
        data = self.load()
        return [
            {
                "id": k,
                "name": v["name"],
                "configured": all(data.get(k, {}).get(s) for s in v["secrets"]),
                "verification": "未进行付费连通测试",
                "config": {
                    a: b
                    for a, b in data.get(k, v).items()
                    if a not in v["secrets"]
                    and a not in {"secrets", "name", "protocol"}
                },
                "secret_fields": v["secrets"],
            }
            for k, v in self.definitions(data).items()
        ]

    def definitions(self, data=None):
        data = self.load() if data is None else data
        return {
            **PROVIDERS,
            **{
                k: {
                    "name": v["name"],
                    "secrets": ["api_key"],
                    "base_url": v["base_url"],
                }
                for k, v in data.items()
                if k.startswith("channel/")
            },
        }

    def models(self):
        return {**MODELS, **self.load().get("_models", {})}

    def add_channel(self, channel_id, name, base_url, api_key):
        if not re.fullmatch(r"channel/[a-z0-9][a-z0-9-]{0,39}", channel_id):
            raise Problem(
                422, "channel_invalid", "渠道编号需为 channel/ 加小写字母、数字或连字符"
            )
        data = self.load()
        if channel_id in data:
            raise Problem(409, "channel_exists", "渠道已存在，请在配置中修改")
        # Reuse URL and field validation before persisting any credential.
        self.validate_url(base_url)
        data[channel_id] = {
            "name": name,
            "base_url": base_url,
            "api_key": api_key,
            "protocol": "openai",
            "enabled": False,
        }
        self.write(data)

    @staticmethod
    def validate_url(value):
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.query
            or parsed.fragment
        ):
            raise Problem(422, "url_invalid", "供应商地址格式不正确")

    def save_model(self, model, name, provider, target_model, enabled):
        if not re.fullmatch(r"haike/[a-z0-9][a-z0-9-]{0,59}", model) or model in MODELS:
            raise Problem(
                422, "model_invalid", "使用新的 haike/ 模型编号，不能覆盖内置档位"
            )
        data = self.load()
        if provider != "openai" and provider not in self.definitions(data):
            raise Problem(422, "channel_missing", "请先添加上游渠道")
        if provider != "openai" and not provider.startswith("channel/"):
            raise Problem(422, "protocol_invalid", "新模型仅支持 OpenAI 兼容渠道")
        models = data.setdefault("_models", {})
        models[model] = {
            "name": name,
            "provider": provider,
            "target_model": target_model,
            "capability": "chat",
            "enabled": enabled,
            "meters": {"input_tokens": 1000000, "output_tokens": 1000000},
        }
        self.write(data)

    def update(self, provider, config):
        definitions = self.definitions()
        if provider not in definitions:
            raise Problem(404, "provider_missing", "供应商不存在")
        allowed = (
            (set(definitions[provider]) - {"secrets"})
            | set(definitions[provider]["secrets"])
            | {"voice", "enabled", "text_model", "image_model", "workflow_profile"}
        )
        if set(config) - allowed or any(
            type(v) is not bool if k == "enabled" else not isinstance(v, str)
            for k, v in config.items()
        ):
            raise Problem(422, "config_invalid", "配置字段不正确")
        if "base_url" in config:
            self.validate_url(config["base_url"])
        data = self.load()
        current = {
            a: b
            for a, b in definitions[provider].items()
            if a not in {"name", "secrets"}
        }
        current.update(data.get(provider, {}))
        current.update({k: v for k, v in config.items() if v != ""})
        data[provider] = current
        self.write(data)

    def import_file(self, path):
        # Attachment is data. Only these named values are used; never execute its contents.
        text = path.read_text(encoding="utf-8-sig")
        pairs = dict(
            re.findall(r"^\s*([A-Z][A-Z0-9_]+)\s*=\s*(.*?)\s*$", text, re.MULTILINE)
        )
        mapping = {
            "openai": {
                "api_key": "OPENAI_API_KEY",
                "base_url": "OPENAI_BASE_URL",
                "text_model": "OPENAI_TEXT_MODEL",
            },
            "bailian": {"api_key": "DASHSCOPE_API_KEY"},
            "tencent": {
                "secret_id": "TENCENT_SECRET_ID",
                "secret_key": "TENCENT_SECRET_KEY",
                "region": "TENCENT_TTS_REGION",
            },
            "runninghub": {
                "api_key": "RUNNINGHUB_API_KEY",
                "base_url": "RUNNINGHUB_BASE_URL",
                "workflow_id": "RUNNINGHUB_WORKFLOW_ID",
                "workflow_profile": "RUNNINGHUB_WORKFLOW_PROFILE",
            },
            "pexels": {"api_key": "PEXELS_API_KEY"},
        }
        for provider, fields in mapping.items():
            config = {
                k: pairs[v].strip("\"'") for k, v in fields.items() if pairs.get(v)
            }
            if provider == "bailian":
                match = re.search(r"(cosyvoice-v[\w.-]+-[a-z0-9]{8,})", text)
                if match:
                    config["voice"] = match.group(1)
            self.update(provider, config)
        return [{"id": r["id"], "configured": r["configured"]} for r in self.public()]


def seed(store):
    with store.write() as db:
        for model, (cost, source) in SOURCES.items():
            if db.execute(
                "SELECT id FROM gateway_prices WHERE model=?", (model,)
            ).fetchone():
                continue
            rule = {
                "costs": {next(iter(MODELS[model]["meters"])): cost},
                "multiplier": "1.5",
                "fee_micros": "0",
                "source": source,
                "cost_basis": "公开标价，采购账单待核对",
                "confirmed": True,
            }
            db.execute(
                "INSERT INTO gateway_prices VALUES(?,?,?,?,?,?)",
                (uid("gprice"), model, 1, canonical(rule), None, now()),
            )


def normalize(model, rule, info=None):
    info = info or MODELS.get(model)
    if not info or set(rule) != {
        "costs",
        "multiplier",
        "fee_micros",
        "source",
        "cost_basis",
        "confirmed",
    }:
        raise Problem(422, "price_invalid", "定价字段不正确")
    try:
        multiplier = Decimal(rule["multiplier"])
        if (
            not multiplier.is_finite()
            or multiplier != Decimal("1.5")
            or len(str(rule["multiplier"])) > 16
        ):
            raise ValueError()
        if set(rule["costs"]) != set(info["meters"]) or rule["fee_micros"] != "0":
            raise ValueError()
        for value in [*rule["costs"].values(), rule["fee_micros"]]:
            if (
                not isinstance(value, str)
                or not re.fullmatch(r"[0-9]{1,13}", value)
                or int(value) > 10**12
            ):
                raise ValueError()
        if (
            type(rule["confirmed"]) is not bool
            or not rule["confirmed"]
            or not rule["source"].strip()
            or not rule["cost_basis"].strip()
        ):
            raise ValueError()
        if len(rule["source"]) > 300 or len(rule["cost_basis"]) > 300:
            raise ValueError()
    except (ValueError, TypeError, InvalidOperation, AttributeError):
        raise Problem(
            422,
            "price_invalid",
            "请确认采购成本与计量单位；售价固定为成本 × 1.5，附加服务费为零",
        ) from None
    return rule


def calculate(model, rule, usage, info=None):
    cost = Decimal(0)
    for meter, included in (info or MODELS[model])["meters"].items():
        value = usage.get(meter, 0)
        if type(value) is not int or not 0 <= value <= 10**10:
            raise Problem(422, "usage_invalid", "用量回执不正确")
        cost += Decimal(rule["costs"][meter]) * value / included
    sale = cost * Decimal(rule["multiplier"]) + int(rule["fee_micros"])
    return int(cost.to_integral_value(rounding=ROUND_CEILING)), int(
        sale.to_integral_value(rounding=ROUND_CEILING)
    )


def price_public(model, row, info=None):
    rule = json.loads(row["rule"]) if row else None
    info = info or MODELS[model]
    meters = info["meters"]
    primary = next(iter(meters))
    return {
        "version": row["version"] if row else 0,
        "unit": UNITS[primary],
        "included_units": meters[primary],
        "unit_price_micros": format(
            (
                Decimal(rule["costs"][primary]) * Decimal(rule["multiplier"])
                + int(rule["fee_micros"])
            ).normalize(),
            "f",
        )
        if rule
        else "0",
        "fee_micros": rule["fee_micros"] if rule else "0",
        "rates": [
            {
                "meter": k,
                "unit": UNITS[k],
                "included_units": v,
                "price_micros": format(
                    (
                        Decimal(rule["costs"][k]) * Decimal(rule["multiplier"])
                    ).normalize(),
                    "f",
                )
                if rule
                else None,
            }
            for k, v in meters.items()
        ],
    }


def latest(db, model):
    return db.execute(
        "SELECT * FROM gateway_prices WHERE model=? ORDER BY version DESC LIMIT 1",
        (model,),
    ).fetchone()


def catalogue(store, vault, admin=False):
    config = vault.load()
    with store.read() as db:
        items = []
        for model, info in vault.models().items():
            row = latest(db, model)
            provider = config.get(info["provider"], {})
            configured = all(
                provider.get(k)
                for k in vault.definitions(config)[info["provider"]]["secrets"]
            )
            if model == "haike/cosyvoice":
                configured = configured and bool(provider.get("voice"))
            status = (
                "available"
                if row
                and configured
                and provider.get("enabled", False)
                and info.get("enabled", True)
                else "price_pending"
                if not row
                else "disabled"
            )
            item = {
                **info,
                "model": model,
                **price_public(model, row, info),
                "status": status,
                "description": "按公开售价结算；结果未知时冻结额度并等待核对",
                "simulation": False,
                "credential_configured": bool(configured),
                "media_artifact_available": info["capability"] in {"tts", "avatar"},
            }
            if admin:
                item["rule"] = json.loads(row["rule"]) if row else None
            else:
                for private in (
                    "provider",
                    "target_model",
                    "credential_configured",
                    "enabled",
                ):
                    item.pop(private, None)
            items.append(item)
        return items


def publish(store, actor, model, rule, vault=None):
    info = vault.models().get(model) if vault else MODELS.get(model)
    rule = normalize(model, rule, info)
    with store.write() as db:
        prior = latest(db, model)
        version = prior["version"] + 1 if prior else 1
        price_id = uid("gprice")
        db.execute(
            "INSERT INTO gateway_prices VALUES(?,?,?,?,?,?)",
            (price_id, model, version, canonical(rule), actor, now()),
        )
        audit(db, actor, "publish_gateway_price", price_id)
    return {"id": price_id, "version": version}
