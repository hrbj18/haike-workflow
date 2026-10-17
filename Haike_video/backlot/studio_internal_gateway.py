"""SDK-compatible direct supplier execution with local budgets, never a relay ledger."""

from __future__ import annotations

import base64
import importlib.util
import math
import os
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from backlot import studio_services as services
from backlot.work_catalog import WorkError
from lib import bailian_speech as records

MODELS = ("haike/text", "haike/avatar", "haike/tencent-asr", "haike/bailian-asr", "haike/assets")
ASR_MODEL = "haike/bailian-asr"
PRIVATE_MODEL_INFO = {ASR_MODEL: {"name": "百炼语音识别", "provider": "bailian",
    "target_model": records.ASR_MODEL, "capability": "asr", "billing_unit": "tokens",
    "meters": {"input_tokens": 1000000, "output_tokens": 1000000}}}
PUBLIC_NAMES = {
    "haike/text": "AI文本与视觉",
    "haike/avatar": "数字人制作",
    "haike/tencent-asr": "语音识别",
    ASR_MODEL: "语音识别",
    "haike/assets": "素材检索",
}
AUDIO_MODELS = {
    "haike/internal-tts",
    "haike/voice-clone",
    "haike/cosyvoice",
    "haike/cosyvoice-public",
}
OPERATION = re.compile(r"call_[0-9a-f]{32}")
QUOTE = re.compile(r"ibq_[0-9a-f]{32}")


def _platform():
    root = str(Path(__file__).resolve().parents[2] / "api-platform")
    if root not in sys.path:
        sys.path.insert(0, root)
    from platform_app import adapters, gateway, providers

    return adapters, gateway, providers


def _scope():
    return {
        "mode": "internal_local",
        "billing_mode": "provider_direct_estimate",
        "pricing_scope": "internal_local_budget",
        "cloud_billing": False,
        "relay_authenticated": False,
        "estimate_only": True,
        "provider_budget_enforced": False,
    }


def _integer(value):
    if (
        type(value) is bool
        or not re.fullmatch(r"[0-9]{1,10}", str(value))
        or int(value) > 10**9
    ):
        raise WorkError("本机预算需为整数微元，单次最高1,000元")
    return int(value)


def _id(value, pattern=OPERATION):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise WorkError("本机调用编号无效")
    return value


def _now():
    return datetime.now(UTC).isoformat()


def _expiry():
    return (datetime.now(UTC) + timedelta(minutes=15)).isoformat()


class LocalVault:
    """Read existing private environment; never make another supplier credential store."""

    def load(self):
        services.refresh_private_environment()

        def env(name, default=""):
            return str(os.environ.get(name) or default).strip()

        result = {
            "openai": {
                "api_key": env("OPENAI_API_KEY"),
                "base_url": env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                "text_model": env(
                    "OPENAI_TEXT_MODEL", env("OPENAI_SCRIPT_MODEL", "gpt-5.6-luna")
                ),
            },
            "runninghub": {
                "api_key": env("RUNNINGHUB_API_KEY"),
                "base_url": env("RUNNINGHUB_BASE_URL", "https://www.runninghub.cn"),
                "workflow_id": env("RUNNINGHUB_WORKFLOW_ID", "2094449979141218305"),
                "workflow_profile": env(
                    "RUNNINGHUB_WORKFLOW_PROFILE", "infinitetalk_448x560_exact_clock_v2"
                ),
            },
            "tencent": {
                "secret_id": env("TENCENT_SECRET_ID"),
                "secret_key": env("TENCENT_SECRET_KEY"),
                "region": env("TENCENT_ASR_REGION", "ap-guangzhou"),
            },
            "bailian": {"api_key": env("DASHSCOPE_API_KEY"),
                "workspace_id": env("DASHSCOPE_WORKSPACE_ID"), "asr_model": records.ASR_MODEL,
                "asr_storage": env("BAILIAN_ASR_STORAGE", "temporary"),
                "oss_endpoint": env("BAILIAN_OSS_ENDPOINT"), "oss_bucket": env("BAILIAN_OSS_BUCKET"),
                "oss_access_key_id": env("BAILIAN_OSS_ACCESS_KEY_ID"),
                "oss_access_key_secret": env("BAILIAN_OSS_ACCESS_KEY_SECRET")},
            "pexels": {"api_key": env("PEXELS_API_KEY")},
        }
        for name, config in result.items():
            config["enabled"] = (
                all(
                    config.get(k)
                    for k in ("secret_id", "secret_key")
                    if name == "tencent"
                )
                if name == "tencent"
                else bool(config.get("api_key"))
            )
        return result


def _identity(config):
    return records.fingerprint(config)


class DirectAdapter:
    """Use existing no-retry protocols; Tencent uses the repo's TC3 helper, not an extra SDK."""

    def __init__(self, vault, file_dir):
        self.vault, self.file_dir = vault, Path(file_dir)

    def execute(self, model, inputs, checkpoint, upstream_id=None):
        adapters, _, _ = _platform()
        config = (
            inputs.get("_runtime_provider_config")
            or self.vault.load()[inputs["_model_info"]["provider"]]
        )
        if model == ASR_MODEL:
            from backlot import bailian_asr
            # All application supplier-setting writers share this lock. Keep
            # the private env-based durable transport on its frozen credential
            # identity while it submits/polls; never rewrite process secrets.
            with services._LOCK:
                if _identity(self.vault.load()["bailian"]) != _identity(config):
                    raise WorkError("百炼配置已改变，请恢复原配置后继续原任务", "conflict")
                if not config.get("api_key") and not upstream_id:
                    raise records.BailianSpeechError("百炼识别Key缺失，未发起网络请求",
                        failure_kind="invalid_key", provider_code="LOCAL_KEY_MISSING", definitive=True)
                audio = self.file_dir / inputs["audio_file"]
                directory = self.file_dir.parent / "asr" / _id(inputs["_job_id"])
                text, segments, metadata = bailian_asr.transcribe_file(audio,
                    artifact_dir=directory, on_accepted=checkpoint,
                    timeout_seconds=30, poll_seconds=3)
            return {"usage": metadata.get("usage", {}), "upstream_id": metadata.get("task_id"),
                    "result": {"text": text, "segments": segments, "provider": "bailian",
                               "model": metadata.get("model", config["asr_model"]),
                               "words": metadata.get("words", []),
                               "timestamp_unit": metadata.get("timestamp_unit", "seconds")}}
        if model != "haike/tencent-asr":

            class FrozenVault:
                def load(self):
                    return {inputs["_model_info"]["provider"]: config}

            return adapters.Adapter(FrozenVault(), self.file_dir).execute(
                model, inputs, checkpoint, upstream_id
            )
        config = {**config, **inputs.get("_provider_config", {})}
        # Isolated helper globals keep frozen credentials stable during concurrent settings refreshes.
        path = Path(__file__).resolve().parents[1] / "lib/tencent_cloud.py"
        spec = importlib.util.spec_from_file_location(
            "lib._studio_internal_tencent", path
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        module.tencent_credentials = lambda: module.TencentCredentials(
            config["secret_id"], config["secret_key"]
        )

        def call(action, body):
            response = module.tc3_request(
                "asr",
                action,
                body,
                version=module.ASR_VERSION,
                region=config["region"],
                timeout=120,
            )
            error = module.response_error(response)
            if error:
                if str(error.get("Code", "")).startswith(
                    (
                        "AuthFailure",
                        "InvalidParameter",
                        "MissingParameter",
                        "UnauthorizedOperation",
                        "RequestLimitExceeded",
                        "LimitExceeded",
                    )
                ):
                    raise adapters.Rejected()
                raise adapters.Uncertain()
            return response.get("Response", {})

        if not upstream_id:
            audio = (self.file_dir / inputs["audio_file"]).read_bytes()
            response = call(
                "CreateRecTask",
                {
                    "EngineModelType": "16k_zh_en",
                    "ChannelNum": 1,
                    "ResTextFormat": 0,
                    "SourceType": 1,
                    "Data": base64.b64encode(audio).decode(),
                    "DataLen": len(audio),
                },
            )
            upstream_id = str(response.get("Data", {}).get("TaskId") or "")
            if not upstream_id:
                raise adapters.Uncertain()
            checkpoint(upstream_id)
        data = call("DescribeTaskStatus", {"TaskId": int(upstream_id)}).get("Data", {})
        if data.get("Status") == 3:
            return {"failed": True, "upstream_id": upstream_id}
        if data.get("Status") != 2:
            return {"pending": True, "upstream_id": upstream_id}
        duration = data.get("AudioDuration")
        if (
            type(duration) not in {int, float}
            or not math.isfinite(duration)
            or duration <= 0
        ):
            raise adapters.ReceiptMissing(upstream_id, {"text": data.get("Result", "")})
        return {
            "usage": {"seconds": math.ceil(duration)},
            "upstream_id": upstream_id,
            "result": {"text": data.get("Result", "")},
        }


class InternalClient:
    def __init__(
        self,
        studio,
        state_dir=None,
        *,
        adapter=None,
        audio_center=None,
        audio_only=False,
        asr_only=False,
    ):
        mode = services.service_mode(studio)
        from backlot.studio_asr import bailian_enabled
        if audio_only and asr_only:
            raise WorkError("配音与识别使用独立的内部路由", "forbidden")
        if (asr_only and not bailian_enabled(studio)) or (audio_only and services.audio_mode(studio) != "internal") or (
            not audio_only and not asr_only and mode != "internal"
        ):
            raise WorkError("本实例未启用内部备用服务", "forbidden")
        self.audio_only = audio_only
        self.asr_only = asr_only
        self.mixed_audio = audio_only and mode == "gateway"
        self.mixed_asr = asr_only and mode == "gateway"
        self.studio = studio
        machine_directory = studio.private / "internal-services"
        if audio_center is None:
            from backlot.studio_audio_internal import InternalAudioCenter

            audio_center = InternalAudioCenter(
                studio, pricing=services.budget_policy(studio).get("audio_pricing", {})
            )
        self.audio = audio_center
        self.account = (
            self.audio.verify_scope() if self.mixed_audio or self.mixed_asr else "internal-local-machine"
        )
        self.directory = (
            self.audio.directory / "sdk-asr" if self.mixed_asr else self.audio.directory / "sdk" if self.mixed_audio else machine_directory
        )
        if (
            (self.mixed_audio or self.mixed_asr)
            and state_dir is not None
            and not Path(state_dir).resolve().is_relative_to(self.directory.resolve())
        ):
            raise WorkError("混合配音意图必须保存在当前账号目录", "forbidden")
        self.directory.mkdir(parents=True, exist_ok=True)
        machine_directory.mkdir(parents=True, exist_ok=True)
        self.state_dir = (
            Path(state_dir)
            if state_dir
            else self.directory
            / ("intents" if self.mixed_audio or self.mixed_asr or not audio_only else "audio-intents")
        )
        # One machine procurement budget; private quote/file/intent records are account scoped.
        self.path = machine_directory / "local-budgets.sqlite3"
        self.vault = LocalVault()
        self.adapter = adapter or DirectAdapter(self.vault, self.directory / "files")
        with self.write() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS local_budget(operation TEXT PRIMARY KEY,day TEXT,amount INTEGER,status TEXT);"
                "CREATE TABLE IF NOT EXISTS gateway_files(id TEXT PRIMARY KEY,user_id TEXT,kind TEXT,size INTEGER,duration_seconds INTEGER,total_frames INTEGER,created_at TEXT);"
            )

    def verify_scope(self):
        if (self.mixed_audio or self.mixed_asr) and self.audio.verify_scope() != self.account:
            raise WorkError("当前海客账号已变化，不能读取原配音调用记录", "conflict")
        return self.account

    @contextmanager
    def write(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def read(self):
        return self.write()

    def _record(self, kind, identifier):
        pattern = (
            re.compile(r"(?:ibq|iq)_[0-9a-f]{32}") if kind == "quotes" else OPERATION
        )
        return self.directory / kind / (_id(identifier, pattern) + ".json")

    def upload(self, path, kind):
        if self.audio_only or self.asr_only:
            raise WorkError("混合配音不能接管网关文件上传", "forbidden")
        _, gateway, _ = _platform()
        return {
            **gateway.upload(
                self, "internal-local-machine", kind, Path(path).read_bytes()
            ),
            **_scope(),
        }

    def prepare_asr_audio(self, audio_path):
        """Python-only import of an owned audio path; no HTTP path endpoint."""
        self.verify_scope()
        from backlot.studio_asr import bailian_enabled
        if not bailian_enabled(self.studio):
            raise WorkError("本机尚未启用百炼识别候选服务", "forbidden")
        path = Path(audio_path)
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 5 * 1024 * 1024:
            raise WorkError("请提供5MB以内的本机完整PCM音轨")
        _, gateway, _ = _platform()
        # gateway.upload derives its file directory from path.parent. Its
        # transaction is still our sole machine-budget database, while files
        # live in this account's private SDK directory, not a shared file root.
        store = SimpleNamespace(path=self.directory / "file-location", write=self.write)
        value = gateway.upload(store, self.account, "audio", path.read_bytes())
        return {**value, "backend": "internal_asr"}

    def _model(self, model):
        _, _, providers = _platform()
        if model not in MODELS:
            raise WorkError("本机SDK尚未接入该模型")
        if model == ASR_MODEL:
            from backlot.studio_asr import bailian_enabled
            if not bailian_enabled(self.studio):
                raise WorkError("本机尚未启用百炼识别候选服务", "forbidden")
        info = dict(PRIVATE_MODEL_INFO[model] if model in PRIVATE_MODEL_INFO else providers.MODELS[model])
        config = self.vault.load()[info["provider"]]
        if not config.get("enabled") and model != ASR_MODEL:
            raise WorkError("此备用供应商尚未配置，请联系内部管理员", "unavailable")
        if model == "haike/text":
            info["target_model"] = config["text_model"]
        if config.get("base_url"):
            provider_id = "text-ai" if info["provider"] == "openai" else info["provider"]
            services._validate({"base_url": config["base_url"]}, provider_id)
        if model == "haike/avatar" and (
            config["workflow_id"] != "2094449979141218305"
            or config["workflow_profile"] != "infinitetalk_448x560_exact_clock_v2"
        ):
            raise WorkError(
                "当前SDK仅适配已冻结的RunningHub精确帧工作流，请恢复兼容规格",
                "unavailable",
            )
        return info, config

    def quote(self, model, inputs, project_ref=""):
        self.verify_scope()
        if self.asr_only and model != ASR_MODEL:
            raise WorkError("混合识别仅允许明确选定的百炼ASR模型", "forbidden")
        if self.audio_only and model != "haike/internal-tts":
            raise WorkError("此内部适配仅允许明确选定的配音模型", "forbidden")
        if model in AUDIO_MODELS:
            payload = dict(inputs)
            if model != "haike/voice-clone":
                payload["purpose"] = "production"
            elif str(payload.get("audio_file", "")).startswith("file_"):
                if not re.fullmatch(r"file_[a-f0-9]{24}", payload["audio_file"]):
                    raise WorkError("本机样音文件编号无效")
                path = self.directory / "files" / payload["audio_file"]
                payload["audio_file"] = self.audio.upload(
                    path.read_bytes(), "audio", "reference.wav"
                )["id"]
            value = self.audio.quote({"model": model, "input": payload})
            public = {**value, **_scope()}
            records.write_record(
                self._record("quotes", public["id"]),
                {"public": public, "audio_payload": {"model": model, "input": payload}},
            )
            return public
        _, gateway, _ = _platform()
        info, config = self._model(model)
        try:
            with self.write() as db:
                clean, usage = gateway.clean_input(
                    db, self.account, model, inputs, info
                )
        except gateway.Problem as exc:
            # The shared validator is HTTP-oriented. Keep its ownership checks,
            # but expose this SDK's safe domain error without echoing input paths.
            code = {403: "forbidden", 404: "missing", 409: "conflict"}.get(exc.status, "invalid")
            raise WorkError(
                "本机调用参数或文件无效，请使用当前海客账号准备的文件编号", code
            ) from None
        policy = services.budget_policy(self.studio)
        amount = (
            0
            if model == "haike/assets"
            else _integer(policy.get("per_call_micros", {}).get(model, 0))
        )
        if model != "haike/assets" and (
            not amount or not _integer(policy.get("daily_limit_micros", 0))
        ):
            raise WorkError(
                "该内部模型采购费用未知，请管理员先设置每次及每日预算", "unavailable"
            )
        snapshot = {
            "model": model,
            "input": clean,
            "info": info,
            "provider_config": {
                k: v
                for k, v in config.items()
                if k not in {"api_key", "secret_id", "secret_key", "enabled", "oss_access_key_id", "oss_access_key_secret"}
            },
            "credential_identity": _identity(config),
            "amount": amount,
            "project_ref": str(project_ref)[:160],
        }
        fingerprint = records.fingerprint(snapshot)
        quote_id, operation = "ibq_" + fingerprint[:32], "call_" + fingerprint[:32]
        public = {
            **_scope(),
            "id": quote_id,
            "operation_id": operation,
            "model": model,
            "provider": info["provider"],
            "provider_model": info["target_model"],
            "quoted_usage": usage,
            "max_charge_micros": str(amount),
            "expires_at": _expiry(),
            "actual_cost_status": "unconfirmed",
            "billing_note": "本机内部采购预算，非云端扣款；上游不执行本机费用硬封顶，实际采购以供应商回执为准。",
        }
        if model == ASR_MODEL:
            public["billing_unit"] = "tokens"
        records.write_record(
            self._record("quotes", quote_id), {"public": public, "snapshot": snapshot}
        )
        return public

    def confirm(self, quote, max_charge_micros, intent_id=None):
        self.verify_scope()
        if _integer(max_charge_micros) < _integer(quote["max_charge_micros"]):
            raise WorkError("本次内部预算低于原报价，未提交")
        path = self._record("quotes", quote["id"])
        frozen = records.read_record(path)
        if (
            (self.asr_only and frozen and frozen["public"].get("model") != ASR_MODEL)
            or (self.audio_only
            and frozen
            and frozen["public"].get("model") != "haike/internal-tts")
        ):
            raise WorkError("混合配音不能确认其他模型", "forbidden")
        if not frozen or any(
            frozen["public"].get(k) != quote.get(k)
            for k in ("id", "model", "operation_id", "max_charge_micros")
        ):
            raise WorkError("内部报价已改变，请核对原报价后继续")
        intent = _id(intent_id or "call_" + uuid4().hex)
        journal_path = self.state_dir / (intent + ".json")
        value = {
            "quote_id": quote["id"],
            "operation_id": quote["operation_id"],
            "max_charge_micros": quote["max_charge_micros"],
        }
        with records.operation_lock(self.state_dir / "locks" / intent):
            previous = records.read_record(journal_path)
            if previous and previous != value:
                raise WorkError("同一调用意图不能更换内部报价；请恢复原任务")
            if not previous:
                records.write_record(journal_path, value)
        return intent

    def _reserve(self, operation, amount):
        if not amount:
            return
        policy = services.budget_policy(self.studio)
        daily = _integer(policy.get("daily_limit_micros", 0))
        if not daily:
            raise WorkError(
                "请管理员先设置本机每日采购预算，未发起供应商调用", "unavailable"
            )
        day = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        with self.write() as db:
            existing = db.execute(
                "SELECT * FROM local_budget WHERE operation=?", (operation,)
            ).fetchone()
            if existing:
                if existing["amount"] != amount and existing["status"] == "reserved":
                    raise WorkError("原内部任务预算已冻结，不能更换")
                return
            used = db.execute(
                "SELECT coalesce(sum(amount),0) FROM local_budget WHERE day=? AND status IN ('reserved','completed')",
                (day,),
            ).fetchone()[0]
            if used + amount > daily:
                raise WorkError(
                    "本机当日已接受采购预算不足，未发起新调用", "budget_limit"
                )
            db.execute(
                "INSERT INTO local_budget VALUES(?,?,?,'reserved')",
                (operation, day, amount),
            )

    def _complete_budget(self, operation, status):
        if status not in {"succeeded", "failed", "cancelled"}:
            return
        with self.write() as db:
            db.execute(
                "UPDATE local_budget SET status=? WHERE operation=?",
                ("completed" if status == "succeeded" else "released", operation),
            )

    def _public(self, value):
        return {
            **_scope(),
            "id": value["id"],
            "operation_id": value["id"],
            "status": value["status"],
            "model": value["quote"]["model"],
            "result": value.get("result"),
            "error": value.get("error"),
            "charged_micros": None,
            "actual_cost_status": "unconfirmed",
            "usage": value.get("usage", {}),
            **{key: value[key] for key in ("failure_kind", "provider_code", "http_status", "definitive", "accepted", "upstream_id") if key in value},
        }

    def _resume_generic(self, frozen):
        adapters, _, _ = _platform()
        public, snapshot = frozen["public"], frozen["snapshot"]
        operation = public["operation_id"]
        path = self._record("operations", operation)
        with records.operation_lock(self.directory / "locks" / operation):
            value = records.read_record(path)
            if value and (
                value["status"] in {"succeeded", "failed", "cancelled"}
                or (
                    value["status"] == "submission_unknown"
                    and (
                        not value.get("upstream_id")
                        or snapshot["model"]
                        not in {"haike/avatar", "haike/tencent-asr", ASR_MODEL}
                    )
                )
            ):
                return self._public(value)
            _, config = self._model(snapshot["model"])
            if _identity(config) != snapshot["credential_identity"]:
                raise WorkError(
                    "原供应商配置已变化，请恢复原配置后继续原任务", "conflict"
                )
            if (
                value
                and value["status"] == "submitting"
                and not value.get("upstream_id")
            ):
                value.update(
                    status="submission_unknown",
                    error="上次受理结果不明，已停止重复提交，请核对原供应商凭证",
                )
                records.write_record(path, value)
                return self._public(value)
            if not value:
                if datetime.fromisoformat(public["expires_at"]) <= datetime.now(UTC):
                    raise WorkError("内部报价已过期，请续期原报价后恢复")
                self._reserve(operation, int(public["max_charge_micros"]))
                value = {
                    "id": operation,
                    "quote": public,
                    "status": "submitting",
                    "created_at": _now(),
                }
                records.write_record(path, value)

            def checkpoint(upstream_id):
                value["upstream_id"] = upstream_id
                records.write_record(path, value)

            inputs = {
                **snapshot["input"],
                "_model_info": snapshot["info"],
                "_provider_config": snapshot["provider_config"],
                "_job_id": operation,
                "_runtime_provider_config": config,
            }
            try:
                response = self.adapter.execute(
                    snapshot["model"], inputs, checkpoint, value.get("upstream_id")
                )
                if response.get("pending"):
                    value.update(status="processing")
                elif response.get("failed"):
                    value.update(
                        status="failed", error="供应商确认失败，原采购预算记录已释放"
                    )
                else:
                    value.update(
                        status="succeeded",
                        result=response.get("result"),
                        usage=response.get("usage", {}),
                    )
            except records.BailianSpeechError as error:
                accepted = bool(value.get("upstream_id") or getattr(error, "accepted", False) or getattr(error, "task_id", None))
                if getattr(error, "task_id", None):
                    value["upstream_id"] = str(error.task_id)
                definitive = bool(getattr(error, "definitive", False)) and not accepted
                kind = getattr(error, "failure_kind", "other")
                value.update(status="processing" if accepted else "failed" if definitive else "submission_unknown",
                    error="供应商明确拒绝本次识别请求" if definitive else "原识别受理或结果待核对，请恢复原任务，禁止重复提交",
                    failure_kind=kind if kind in {"invalid_key", "insufficient_balance", "other"} else "other",
                    provider_code=records.safe_error(getattr(error, "provider_code", "") or "")[:100] or None,
                    http_status=getattr(error, "http_status", None), definitive=definitive, accepted=accepted)
            except adapters.ReceiptMissing as error:
                value.update(
                    status="submission_unknown",
                    result=error.result,
                    error="原结果已保存，用量回执待核对；未重复提交",
                )
                if error.upstream_id:
                    value["upstream_id"] = error.upstream_id
            except adapters.Rejected:
                value.update(
                    status="processing" if value.get("upstream_id") else "failed",
                    error="供应商拒绝或原任务查询暂不可用",
                )
            except Exception:  # noqa: BLE001 -- never persist provider exception text/credentials
                value.update(
                    status="processing"
                    if value.get("upstream_id")
                    else "submission_unknown",
                    error="原供应商结果待核对；已保留意图，禁止重复提交",
                )
            records.write_record(path, value)
            self._complete_budget(operation, value["status"])
            return self._public(value)

    def resume(self, intent_id):
        self.verify_scope()
        journal = records.read_record(self.state_dir / (_id(intent_id) + ".json"))
        if not journal:
            raise WorkError("没有该内部调用意图", "missing")
        frozen = records.read_record(self._record("quotes", journal["quote_id"]))
        if not frozen:
            raise WorkError("原内部报价记录缺失，未重新创建调用")
        if self.audio_only and (
            "audio_payload" not in frozen
            or frozen["public"].get("model") != "haike/internal-tts"
        ):
            raise WorkError("混合配音不能恢复其他模型", "forbidden")
        if self.asr_only and frozen["public"].get("model") != ASR_MODEL:
            raise WorkError("混合识别不能恢复其他模型", "forbidden")
        if "audio_payload" not in frozen:
            return self._resume_generic(frozen)
        operation = journal["operation_id"]
        try:
            result = self.audio.job(operation)
        except WorkError as error:
            if error.code != "missing":
                raise
            self._reserve(operation, int(journal["max_charge_micros"]))
            result = self.audio.submit(
                {
                    "quote_id": journal["quote_id"],
                    "operation_id": operation,
                    "max_charge_micros": journal["max_charge_micros"],
                    "confirmed": True,
                }
            )
        self._complete_budget(operation, result["status"])
        if result["status"] == "succeeded" and result.get("result", {}).get(
            "audio_url"
        ):
            data = self.audio.preview(operation).read_bytes()
            result = {
                **result,
                "result": {
                    **result["result"],
                    "audio_base64": base64.b64encode(data).decode(),
                    "format": "wav",
                },
            }
        return result

    def wait(self, intent_id, timeout=300):
        deadline = time.monotonic() + timeout
        while True:
            result = self.resume(intent_id)
            if (
                result["status"]
                in {"succeeded", "failed", "cancelled", "submission_unknown"}
                or time.monotonic() >= deadline
            ):
                return result
            time.sleep(2)

    def request(
        self, path, body=None, idem=None, raw=None, *, method=None, response_bytes=False
    ):
        self.verify_scope()
        if self.asr_only and not re.fullmatch(r"/quotes/ibq_[a-f0-9]{32}/renew", path):
            raise WorkError("混合识别不能接管网关账户、模型或文件接口", "forbidden")
        if self.audio_only and not re.fullmatch(r"/quotes/iq_[a-f0-9]{32}/renew", path):
            raise WorkError("混合配音不能接管网关账户、模型或文件接口", "forbidden")
        if path == "/account/summary":
            return {
                **_scope(),
                "account_id": "internal-local-machine",
                "account_name": "本机内部服务",
                "available_micros": None,
                "commercial_available_micros": None,
                "commercial_reserved_micros": None,
            }
        if path in {"/capabilities", "/prices"}:
            items = []
            policy = services.budget_policy(self.studio)
            daily_ready = bool(_integer(policy.get("daily_limit_micros", 0)))
            for model in MODELS:
                try:
                    info, _ = self._model(model)
                    ready = model == "haike/assets" or (
                        daily_ready
                        and bool(policy.get("per_call_micros", {}).get(model))
                    )
                    status = "available" if ready else "budget_required"
                except WorkError:
                    info, status = PRIVATE_MODEL_INFO.get(model) or _platform()[2].MODELS[model], "unconfigured"
                items.append(
                    {
                        "model": model,
                        "name": PUBLIC_NAMES[model],
                        "capability": info["capability"],
                        "status": status,
                        "simulation": False,
                        "media_artifact_available": info["capability"] == "avatar",
                        **_scope(),
                    }
                )
            items.append(
                {
                    "model": "haike/internal-tts",
                    "name": "配音",
                    "capability": "tts",
                    "status": ("available" if daily_ready else "budget_required")
                    if any(v.get("available") for v in self.audio.voices()["items"])
                    else "unconfigured",
                    **_scope(),
                }
            )
            return {"items": items, **_scope()}
        if path == "/voices":
            return self.audio.voices()
        if re.fullmatch(r"/quotes/(?:ibq|iq)_[a-f0-9]{32}/renew", path) and body == {
            "confirmed": True
        }:
            identifier = path.split("/")[2]
            record_path = self._record("quotes", identifier)
            frozen = records.read_record(record_path)
            if not frozen:
                raise WorkError("原内部报价不存在", "missing")
            if (
                (self.asr_only and frozen["public"].get("model") != ASR_MODEL)
                or (self.audio_only
                and frozen["public"].get("model") != "haike/internal-tts"
                )
            ):
                raise WorkError("混合配音不能续期其他模型", "forbidden")
            if "audio_payload" in frozen:
                try:
                    self.audio.operation(frozen["public"]["operation_id"])
                except WorkError as error:
                    if error.code != "missing":
                        raise
                    renewed = self.audio.quote(frozen["audio_payload"])
                    if any(
                        renewed.get(k) != frozen["public"].get(k)
                        for k in ("id", "model", "max_charge_micros")
                    ):
                        raise WorkError(
                            "原供应商或估算已变化，请重新确认；未发起新调用"
                        )
            frozen["public"]["expires_at"] = _expiry()
            records.write_record(record_path, frozen)
            return frozen["public"]
        if path.startswith("/files/") and response_bytes:
            file_id = path.split("/")[-1]
            if not re.fullmatch(r"file_[a-f0-9]{24}", file_id):
                raise WorkError("本机文件编号无效")
            return (self.directory / "files" / file_id).read_bytes()
        raise WorkError("内部SDK不提供该云账户或后台接口", "unavailable")
