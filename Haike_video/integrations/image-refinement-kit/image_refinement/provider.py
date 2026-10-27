"""Single-attempt Responses transport. Never retry an uncertain paid request."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field


class RefinementError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_request",
        uncertain: bool = False,
        metadata: dict | None = None,
    ):
        super().__init__(message)
        self.code, self.uncertain = code, uncertain
        self.metadata = metadata or {}


@dataclass(frozen=True)
class Settings:
    base_url: str = "http://8.212.174.130:8080/v1"
    api_key: str = field(default="", repr=False)
    text_model: str = "gpt-5.6"
    image_model: str = "gpt-image-2"
    timeout: int = 600
    daily_limit: int = 100

    @classmethod
    def from_env(cls):
        return cls(
            base_url=os.getenv("IMAGE_REFINEMENT_BASE_URL") or cls.base_url,
            api_key=os.getenv("IMAGE_REFINEMENT_API_KEY", ""),
            text_model=os.getenv("IMAGE_REFINEMENT_TEXT_MODEL") or cls.text_model,
            image_model=os.getenv("IMAGE_REFINEMENT_MODEL") or cls.image_model,
            timeout=max(
                10, min(600, int(os.getenv("IMAGE_REFINEMENT_TIMEOUT", "600")))
            ),
            daily_limit=max(1, int(os.getenv("IMAGE_REFINEMENT_DAILY_LIMIT", "100"))),
        )

    def public(self):
        return {
            "configured": bool(self.api_key),
            "provider": "relay_responses",
            "image_model": self.image_model,
            "text_model": self.text_model,
            "daily_limit": self.daily_limit,
            "automatic_retries": False,
        }


class ResponsesProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def edit(self, image: bytes, mime: str, prompt: str) -> tuple[bytes, dict]:
        s = self.settings
        if not s.api_key:
            raise RefinementError(
                "图片精修未配置密钥：请在服务端设置 IMAGE_REFINEMENT_API_KEY 后重试。",
                code="not_configured",
            )
        payload = {
            "model": s.text_model,
            "stream": False,
            "store": False,
            "tools": [
                {
                    "type": "image_generation",
                    "model": s.image_model,
                    "size": "1024x1280",
                }
            ],
            # This relay rejects max_tool_calls. A single HTTP submission does
            # not imply a single upstream tool call; record the actual calls.
            "tool_choice": {"type": "image_generation"},
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Edit the attached image. Call image_generation once and return the image.\n\n"
                            + prompt,
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{mime};base64,"
                            + base64.b64encode(image).decode("ascii"),
                        },
                    ],
                }
            ],
        }
        request = urllib.request.Request(
            s.base_url.rstrip("/") + "/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + s.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(NoRedirect())
        try:
            with opener.open(request, timeout=s.timeout) as response:
                raw = response.read(64 * 1024 * 1024 + 1)
                if len(raw) > 64 * 1024 * 1024:
                    raise RefinementError(
                        "中转返回内容过大，请核对本次任务和账单后再操作。",
                        code="response_too_large",
                        uncertain=True,
                    )
                value = json.loads(raw)
        except urllib.error.HTTPError as exc:
            # Never return raw upstream bodies: they can contain secrets or image data.
            if exc.code in (401, 403):
                raise RefinementError(
                    "中转密钥无效或没有生图权限，请检查服务端配置。",
                    code="authentication",
                ) from None
            if exc.code == 503 and b"No available compatible accounts" in exc.read(
                4096
            ):
                raise RefinementError(
                    "中转当前没有可用的兼容生图账号，请检查中转配置后手动重试。",
                    code="provider_unavailable",
                ) from None
            raise RefinementError(
                f"图片精修接口返回 HTTP {exc.code}，未自动重试；请核对中转任务后再操作。",
                code=f"http_{exc.code}",
                uncertain=exc.code >= 500 or exc.code in (408, 429),
            ) from None
        except (TimeoutError, OSError, ValueError):
            raise RefinementError(
                "中转请求超时、连接中断或响应无法读取，结果及扣费状态不确定。请先核对中转记录，系统不会自动重发。",
                code="transport_unknown",
                uncertain=True,
            ) from None
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("output"), list)
            or any(not isinstance(item, dict) for item in value["output"])
        ):
            raise RefinementError(
                "中转响应格式异常，请核对原任务与账单。",
                code="response_invalid",
                uncertain=True,
            )
        calls = [
            item
            for item in value["output"]
            if item.get("type") == "image_generation_call"
        ]
        metadata = {
            "response_id": value.get("id"),
            "usage": value.get("usage"),
            "response_status": value.get("status"),
            "output_types": [
                str(item.get("type", "unknown")) for item in value.get("output", [])
            ],
            "tool_ids": [str(item.get("id", "")) for item in calls],
            "tool_statuses": [str(item.get("status", "unknown")) for item in calls],
        }
        for item in reversed(calls):
            if item.get("status") in ("completed", "succeeded") and isinstance(
                item.get("result"), str
            ):
                try:
                    image = base64.b64decode(item["result"], validate=True)
                except ValueError:
                    continue
                if image:
                    metadata.update(
                        {
                            k: item[k]
                            for k in ("size", "quality", "output_format", "action")
                            if k in item
                        }
                    )
                    if len(calls) > 1:
                        metadata["warning"] = (
                            "上游返回了多次生图工具记录，请核对中转账单；本服务没有重发请求。"
                        )
                    if value.get("status") not in ("completed", "succeeded"):
                        metadata["warning"] = (
                            "图片已返回，但上游整体状态未完成，请核对账单。"
                        )
                    return image, metadata
        raise RefinementError(
            "中转未返回可用图片。请先核对本次任务和账单，再决定重试或使用原图。",
            code="no_image",
            uncertain=True,
            metadata=metadata,
        )
