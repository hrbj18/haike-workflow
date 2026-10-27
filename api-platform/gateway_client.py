"""Copyable one-Key SDK. No provider keys, SDKs or paid retry policy on the customer side."""

import json
import secrets
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from client import save_private


class GatewayError(ValueError):
    def __init__(self, message, *, status=None, code="gateway_error"):
        self.status, self.code = status, code
        super().__init__(message)


class HaikeClient:
    def __init__(self, base_url, api_key, state_dir):
        parsed = urlsplit(base_url)
        if (
            parsed.path.rstrip("/") != "/v2"
            or parsed.username
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Base URL 应以 /v2 结尾")
        if parsed.scheme != "https" and not (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError("公网接入必须使用 HTTPS；本地可使用回环 HTTP")
        self.base_url, self.api_key = base_url.rstrip("/"), api_key
        self.state_dir = Path(state_dir)

    def request(self, path, body=None, idem=None, raw=None, *, method=None, response_bytes=False):
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or "\\" in path:
            raise GatewayError("API 路径必须是站内相对路径", code="path_invalid")
        parsed_path = urlsplit(path)
        if parsed_path.scheme or parsed_path.netloc or parsed_path.fragment:
            raise GatewayError("API 路径必须是站内相对路径", code="path_invalid")
        if method is not None and method not in {"GET", "POST", "PUT", "DELETE"}:
            raise GatewayError("不支持的 API 请求方式", code="method_invalid")
        headers = {"Authorization": "Bearer " + self.api_key}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if raw is not None:
            data = raw
            headers["Content-Type"] = "application/octet-stream"
        if idem:
            headers["Idempotency-Key"] = idem
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()
        )
        try:
            with opener.open(request, timeout=30) as response:
                if response_bytes:
                    value = response.read(5 * 1024 * 1024 + 1)
                    if len(value) > 5 * 1024 * 1024:
                        raise GatewayError("返回文件超过 5MB", code="response_too_large")
                    return value
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                value = json.load(error)
                problem = value.get("error", {})
                message = problem.get("message", "海客 API 请求失败")
                code = problem.get("code", "gateway_error")
            except (ValueError, AttributeError):
                message = "海客 API 请求失败"
                code = "gateway_error"
            message = str(message).replace(self.api_key, "[已隐藏]") if self.api_key else str(message)
            raise GatewayError(message[:500], status=error.code, code=str(code)[:100]) from None
        except urllib.error.URLError as error:
            if isinstance(error.reason, ssl.SSLCertVerificationError):
                raise GatewayError("中转站 HTTPS 证书无法验证，请联系管理员续期证书或修复证书链后重试", code="tls_certificate_invalid") from None
            raise GatewayError("海客 API 连接失败，请检查网络后恢复原任务", code="connection_failed") from None
        except ssl.SSLCertVerificationError:
            raise GatewayError("中转站 HTTPS 证书无法验证，请联系管理员续期证书或修复证书链后重试", code="tls_certificate_invalid") from None
        except (TimeoutError, OSError):
            raise GatewayError("海客 API 连接失败，请检查网络后恢复原任务", code="connection_failed") from None

    def upload(self, path, kind):
        if kind not in {"audio", "image"}:
            raise ValueError("文件类型需要 audio 或 image")
        if Path(path).stat().st_size > 5 * 1024 * 1024:
            raise ValueError("文件最多 5MB")
        return self.request("/files?kind=" + kind, raw=Path(path).read_bytes())

    def quote(self, model, inputs, project_ref=""):
        return self.request(
            "/quotes", {"model": model, "input": inputs, "project_ref": project_ref}
        )

    def confirm(self, quote, max_charge_micros, intent_id=None):
        if int(quote["max_charge_micros"]) > int(max_charge_micros):
            raise ValueError("报价超过授权上限，未提交、未扣款")
        intent_id = intent_id or "call_" + secrets.token_hex(16)
        if (
            not intent_id.startswith("call_")
            or len(intent_id) != 37
            or any(c not in "0123456789abcdef" for c in intent_id[5:])
        ):
            raise ValueError("调用意图编号格式不正确")
        path = self.state_dir / (intent_id + ".json")
        body = {
            "quote_id": quote["id"],
            "max_charge_micros": quote["max_charge_micros"],
            "call_intent_id": intent_id,
            "currency": "CNY",
            "confirmed": True,
        }
        if path.exists():
            journal = json.loads(path.read_text(encoding="utf-8"))
            if journal["body"] != body:
                raise ValueError("同一调用意图不能更换报价；请恢复原任务")
        else:
            save_private(path, {"body": body, "idempotency_key": intent_id})
        # Return the durable intent BEFORE network submission to the caller.
        return intent_id

    def resume(self, intent_id):
        if (
            not intent_id.startswith("call_")
            or len(intent_id) != 37
            or any(c not in "0123456789abcdef" for c in intent_id[5:])
        ):
            raise ValueError("调用意图编号格式不正确")
        path = self.state_dir / (intent_id + ".json")
        journal = json.loads(path.read_text(encoding="utf-8"))
        if journal.get("job_id"):
            return self.request("/jobs/" + journal["job_id"])
        job = self.request("/jobs", journal["body"], journal["idempotency_key"])
        journal["job_id"] = job["id"]
        save_private(path, journal)
        return job

    def wait(self, intent_id, timeout=300):
        deadline = time.monotonic() + timeout
        while True:
            job = self.resume(intent_id)
            if job["status"] in {
                "succeeded",
                "failed",
                "cancelled",
                "submission_unknown",
            }:
                return job
            if time.monotonic() >= deadline:
                return job  # Retain the intent; never create another paid request.
            time.sleep(3)
