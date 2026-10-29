"""The same client contract supports embedded execution and a remote service."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .provider import RefinementError


class LocalClient:
    def __init__(self, service):
        self.service = service
        self.service.start()

    def submit(self, raw, namespace, *, confirmed=False):
        return self.service.submit(raw, namespace, confirmed=confirmed)

    def get(self, job_id, namespace):
        return self.service.get(job_id, namespace)

    def retry(self, job_id, namespace, *, confirmed=False, acknowledge_uncertain=False):
        return self.service.submit(
            self.file(job_id, namespace, "source"),
            namespace,
            confirmed=confirmed,
            retry_of=job_id,
            acknowledge_uncertain=acknowledge_uncertain,
        )

    def file(self, job_id, namespace, kind):
        return self.service.file(job_id, namespace, kind)

    def close(self):
        self.service.close()


class RemoteClient:
    def __init__(self, url: str, token: str):
        if not token:
            raise RefinementError("独立精修服务未配置访问令牌。", code="not_configured")
        self.url, self.token = url.rstrip("/"), token

    def _request(
        self,
        path,
        namespace,
        *,
        raw=None,
        json_body=None,
        method="GET",
        binary=False,
        confirmed=False,
    ):
        data = json.dumps(json_body).encode() if json_body is not None else raw
        request = urllib.request.Request(
            self.url
            + path
            + "?"
            + urllib.parse.urlencode(
                {"namespace": namespace, "confirmed": str(confirmed).lower()}
            ),
            data=data,
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json"
                if json_body is not None
                else "application/octet-stream",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                value = response.read(40 * 1024 * 1024 + 1)
            if len(value) > 40 * 1024 * 1024:
                raise RefinementError("精修服务返回内容过大。", code="service_error")
            return value if binary else json.loads(value)
        except urllib.error.HTTPError as exc:
            code = (
                "not_found"
                if exc.code == 404
                else "confirmation_required"
                if exc.code == 409
                else "service_error"
            )
            raise RefinementError(
                "精修服务请求未完成，请检查服务状态、访问令牌或原任务记录。", code=code
            ) from None
        except (OSError, ValueError):
            raise RefinementError(
                "无法连接精修服务；原图已保留。可手动重试连接或使用原图，不会自动重发生图请求。",
                code="service_unavailable",
            ) from None

    def submit(self, raw, namespace, *, confirmed=False):
        return self._request(
            "/v1/jobs", namespace, raw=raw, method="POST", confirmed=confirmed
        )

    def get(self, job_id, namespace):
        return self._request(
            "/v1/jobs/" + urllib.parse.quote(job_id, safe=""), namespace
        )

    def retry(self, job_id, namespace, *, confirmed=False, acknowledge_uncertain=False):
        return self._request(
            "/v1/jobs/" + urllib.parse.quote(job_id, safe="") + "/retry",
            namespace,
            json_body={
                "confirmed": confirmed,
                "acknowledge_uncertain": acknowledge_uncertain,
            },
            method="POST",
        )

    def file(self, job_id, namespace, kind):
        return self._request(
            "/v1/jobs/"
            + urllib.parse.quote(job_id, safe="")
            + "/files/"
            + urllib.parse.quote(kind, safe=""),
            namespace,
            binary=True,
        )

    def close(self):
        pass
