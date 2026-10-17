"""Explicit audio routing; gateway errors never switch a frozen call to a supplier."""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from uuid import uuid4

from backlot import studio_services as services
from backlot.work_catalog import WorkError
from lib import bailian_speech as records


def _intent(value):
    if not isinstance(value, str) or not re.fullmatch(r"call_[a-f0-9]{32}", value):
        raise WorkError("调用意图编号无效")
    return value


class GatewayRoutingClient:
    """Keep ordinary SDK operations on the relay and one explicit TTS model local."""

    def __init__(self, studio, gateway, *, state_dir=None, internal_factory=None, internal_asr_factory=None):
        self.studio, self.gateway = studio, gateway
        self.directory = (
            Path(state_dir) if state_dir else studio.private / "haike-api/routing"
        )
        self.state_dir = gateway.state_dir
        self.internal_factory = internal_factory
        self._audio = None
        self.internal_asr_factory = internal_asr_factory
        self._asr = None

    def _internal(self):
        if self._audio is None:
            if self.internal_factory:
                self._audio = self.internal_factory()
            else:
                from backlot.studio_internal_gateway import InternalClient

                self._audio = InternalClient(self.studio, audio_only=True)
        self._audio.verify_scope()
        return self._audio

    def _directory(self, internal=False):
        if internal == "internal_asr":
            return self._internal_asr().directory / "routing"
        return self._internal().directory / "routing" if internal else self.directory

    def _internal_asr(self):
        if self._asr is None:
            if self.internal_asr_factory:
                self._asr = self.internal_asr_factory()
            else:
                from backlot.studio_internal_gateway import InternalClient
                self._asr = InternalClient(self.studio, asr_only=True)
        self._asr.verify_scope()
        return self._asr

    @staticmethod
    def _backend(model):
        return "internal_audio" if model == "haike/internal-tts" else "internal_asr" if model == "haike/bailian-asr" else "gateway"

    def _routed_client(self, backend):
        return self._internal_asr() if backend == "internal_asr" else self._internal() if backend == "internal_audio" else self.gateway

    @staticmethod
    def _private_backend(backend):
        return backend if backend in {"internal_audio", "internal_asr"} else False

    def _quote_path(self, identifier, internal=False):
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 256:
            raise WorkError("报价编号无效")
        return (
            self._directory(internal)
            / "quotes"
            / (hashlib.sha256(identifier.encode()).hexdigest() + ".json")
        )

    def _intent_path(self, identifier, internal=False):
        return self._directory(internal) / "intents" / (_intent(identifier) + ".json")

    def _binding_path(self, identifier):
        # Routing tombstones contain no quote, model, text, file or supplier credential.
        return self.directory / "bindings" / (_intent(identifier) + ".json")

    def upload(self, path, kind):
        return self.gateway.upload(path, kind)

    def prepare_asr_audio(self, audio_path):
        # Internal Python seam only. No public endpoint accepts a local path.
        return self._internal_asr().prepare_asr_audio(audio_path)

    def quote(self, model, inputs, project_ref=""):
        backend = self._backend(model)
        if backend == "internal_audio":
            if services.audio_mode(self.studio) != "internal":
                raise WorkError(
                    "本机未启用备用配音，请使用已配置的海客配音模型", "unavailable"
                )
            quote = self._internal().quote(model, inputs, project_ref)
        elif backend == "internal_asr":
            quote = self._internal_asr().quote(model, inputs, project_ref)
        else:
            quote = self.gateway.quote(model, inputs, project_ref)
        value = {**quote, "backend": backend}
        records.write_record(
            self._quote_path(value["id"], self._private_backend(backend)),
            {"backend": backend, "quote": value},
        )
        return value

    def confirm(self, quote, max_charge_micros, intent_id=None):
        expected_backend = self._backend(quote.get("model"))
        internal = self._private_backend(expected_backend)
        route = records.read_record(self._quote_path(quote.get("id"), internal))
        if route:
            if any(
                route["quote"].get(k) != quote.get(k)
                for k in ("id", "model", "operation_id", "max_charge_micros", "backend")
            ):
                raise WorkError(
                    "原报价或服务来源已变化，请恢复已确认的原报价", "conflict"
                )
            backend = route["backend"]
        else:
            # Existing gateway drafts remain resumable after installing the wrapper.
            if (
                expected_backend != "gateway"
                or quote.get("backend") not in {None, "gateway"}
                or str(quote["id"]).startswith(("iq_", "ibq_"))
            ):
                raise WorkError("缺少原配音路由记录，请重新读取报价", "missing")
            backend = "gateway"
        identifier = _intent(intent_id or "call_" + uuid4().hex)
        value = {
            "backend": backend,
            "quote_id": quote["id"],
            "model": quote.get("model"),
            "max_charge_micros": quote["max_charge_micros"],
        }
        internal = self._private_backend(backend)
        client = self._routed_client(backend)
        binding = {
            "backend": backend,
            "scope": client.account if internal else "gateway",
        }
        path = self._intent_path(identifier, internal)
        with records.operation_lock(self.directory / "locks" / identifier):
            previous_binding = records.read_record(self._binding_path(identifier))
            if previous_binding and previous_binding != binding:
                raise WorkError("原调用意图已绑定服务或账号，不能更换", "conflict")
            previous = records.read_record(path)
            if previous and previous != value:
                raise WorkError("原调用意图已绑定服务和报价，不能更换", "conflict")
            # Persist the selected backend before either SDK prepares its journal.
            if not previous_binding:
                records.write_record(self._binding_path(identifier), binding)
            if not previous:
                records.write_record(path, value)
            returned = client.confirm(quote, max_charge_micros, identifier)
            if returned != identifier:
                raise WorkError("调用意图保存不一致，未提交任务", "conflict")
        return identifier

    def resume(self, intent_id):
        identifier = _intent(intent_id)
        binding = records.read_record(self._binding_path(identifier))
        if binding and binding.get("backend") in {"internal_audio", "internal_asr"}:
            backend = binding["backend"]
            client = self._routed_client(backend)
            if client.account != binding.get("scope"):
                raise WorkError("原内部调用属于其他海客账号", "conflict")
            if not records.read_record(self._intent_path(identifier, self._private_backend(backend))):
                raise WorkError("没有该账号的原配音路由记录", "missing")
            return client.resume(identifier)
        if binding and binding.get("backend") != "gateway":
            raise WorkError("原调用服务记录无效", "conflict")
        route = records.read_record(self._intent_path(identifier))
        if route and route.get("backend") in {"internal_audio", "internal_asr"}:
            raise WorkError("旧配音路由尚未隔离账号，已停止读取原私有任务", "conflict")
        if not route:
            # A legacy relay SDK journal is affirmative evidence of its original backend.
            legacy = records.read_record(
                Path(self.gateway.state_dir) / (identifier + ".json")
            )
            if not legacy or legacy.get("body", {}).get("call_intent_id") != identifier:
                raise WorkError("没有该调用的原服务记录，未重新提交", "missing")
            backend = "gateway"
        else:
            backend = route.get("backend")
        if backend == "gateway":
            return self.gateway.resume(identifier)
        raise WorkError("原调用服务记录无效，未重新提交", "conflict")

    def wait(self, intent_id, timeout=300):
        deadline = time.monotonic() + timeout
        while True:
            job = self.resume(intent_id)
            if (
                job["status"]
                in {"succeeded", "failed", "cancelled", "submission_unknown"}
                or time.monotonic() >= deadline
            ):
                return job
            time.sleep(2)

    def request(
        self, path, body=None, idem=None, raw=None, *, method=None, response_bytes=False
    ):
        match = re.fullmatch(r"/quotes/((?:iq|ibq)_[a-f0-9]{32})/renew", path)
        if match:
            backend = "internal_asr" if match.group(1).startswith("ibq_") else "internal_audio"
            route_path = self._quote_path(match.group(1), self._private_backend(backend))
            route = records.read_record(route_path)
            if not route or route.get("backend") != backend:
                raise WorkError("没有该报价的原配音服务记录", "missing")
            value = self._routed_client(backend).request(
                path, body, idem, raw, method=method, response_bytes=response_bytes
            )
            value = {**value, "backend": backend}
            records.write_record(
                route_path, {"backend": backend, "quote": value}
            )
            return value
        return self.gateway.request(
            path, body, idem, raw, method=method, response_bytes=response_bytes
        )
