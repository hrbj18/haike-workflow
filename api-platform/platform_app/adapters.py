"""No automatic paid retries. Only allow-listed provider protocols receive credentials."""

import base64
import json
import math
import urllib.error
import urllib.parse
import urllib.request


class Rejected(Exception):
    """A request definitively rejected before execution."""


class Uncertain(Exception):
    """Submission or usage cannot be established; preserve the hold."""


class ReceiptMissing(Uncertain):
    def __init__(self, upstream_id, result=None):
        self.upstream_id, self.result = upstream_id, result


def tencent_call(client, method, request):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
        TencentCloudSDKException,
    )

    try:
        return getattr(client, method)(request)
    except TencentCloudSDKException as error:
        if str(error.get_code()).startswith(
            (
                "AuthFailure",
                "InvalidParameter",
                "MissingParameter",
                "UnauthorizedOperation",
                "LimitExceeded",
            )
        ):
            raise Rejected() from None
        raise Uncertain() from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http(url, headers, body=None, raw=None, method=None):
    request = urllib.request.Request(
        url,
        data=raw
        if raw is not None
        else json.dumps(body).encode()
        if body is not None
        else None,
        headers=headers,
        method=method,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=120) as response:
            value = response.read(16 * 1024 * 1024 + 1)
        if len(value) > 16 * 1024 * 1024:
            raise Uncertain()
        return json.loads(value)
    except urllib.error.HTTPError as error:
        if error.code in {400, 401, 403, 404, 422, 429}:
            raise Rejected() from None
        raise Uncertain() from None
    except (urllib.error.URLError, ValueError, TimeoutError):
        raise Uncertain() from None


def safe_url(value):
    # Returned artifact URLs contain no supplier credential and are not fetched by this server.
    parsed = urllib.parse.urlsplit(str(value))
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username:
        raise Uncertain()
    return value


class Adapter:
    def __init__(self, vault, file_dir):
        self.vault, self.file_dir = vault, file_dir

    def execute(self, model, inputs, checkpoint, upstream_id=None):
        from .providers import MODELS

        info = inputs.get("_model_info") or MODELS[model]
        provider = info["provider"]
        config = dict(self.vault.load()[provider])
        if not upstream_id and not config.get("enabled", False):
            raise Rejected()
        config.update(inputs.get("_provider_config", {}))
        if provider == "openai" or provider.startswith("channel/"):
            if info["capability"] == "image":
                result = http(
                    config["base_url"].rstrip("/") + "/images/generations",
                    {"Authorization": "Bearer " + config["api_key"], "Content-Type": "application/json"},
                    {"model": config.get("image_model", info["target_model"]), "prompt": inputs["prompt"],
                     "n": 1, "size": "1024x1536", "quality": "medium"},
                )
                usage = result.get("usage", {})
                images = result.get("data", [])
                if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
                    raise Uncertain()
                item = images[0]
                media = {"image_base64": item["b64_json"]} if isinstance(item.get("b64_json"), str) else {"image_url": safe_url(item.get("url"))}
                media.update(generated=True, source=config.get("image_model", info["target_model"]), size="1024x1536", quality="medium")
                if any(type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens")):
                    raise ReceiptMissing(str(result.get("id", "")), media)
                return {"usage": {k: usage[k] for k in ("input_tokens", "output_tokens")}, "result": media,
                        "upstream_id": str(result.get("id", result.get("created", "")))}
            messages = json.loads(json.dumps(inputs["messages"]))
            for message in messages:
                if isinstance(message["content"], list):
                    for i, part in enumerate(message["content"]):
                        if part["type"] == "image_file":
                            image = (self.file_dir / part["file_id"]).read_bytes()
                            mime = (
                                "image/png"
                                if image.startswith(b"\x89PNG")
                                else "image/jpeg"
                            )
                            message["content"][i] = {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:"
                                    + mime
                                    + ";base64,"
                                    + base64.b64encode(image).decode()
                                },
                            }
            result = http(
                config["base_url"].rstrip("/") + "/chat/completions",
                {
                    "Authorization": "Bearer " + config["api_key"],
                    "Content-Type": "application/json",
                },
                {
                    "model": config.get("text_model", info["target_model"]),
                    "messages": messages,
                    "max_completion_tokens": inputs["max_output_tokens"],
                    "stream": False,
                },
            )
            usage = result.get("usage", {})
            if (
                type(usage.get("prompt_tokens")) is not int
                or type(usage.get("completion_tokens")) is not int
            ):
                raise ReceiptMissing(str(result.get("id", "")))
            # Do not persist a raw provider payload that could echo private request headers.
            choices = [
                {
                    "index": i,
                    "message": {
                        "role": "assistant",
                        "content": str(c.get("message", {}).get("content", "")),
                    },
                    "finish_reason": c.get("finish_reason"),
                }
                for i, c in enumerate(result.get("choices", []))
            ]
            if not choices:
                raise Uncertain()
            return {
                "usage": {
                    "input_tokens": usage["prompt_tokens"],
                    "output_tokens": usage["completion_tokens"],
                },
                "result": {"choices": choices},
                "upstream_id": str(result.get("id", "")),
            }
        if provider == "bailian":
            from dashscope.audio.http_tts.http_speech_synthesizer import (
                HttpSpeechSynthesizer,
            )

            result = HttpSpeechSynthesizer.call(
                model="cosyvoice-v3.5-flash",
                text=inputs["text"],
                voice=config["voice"],
                audio_format="wav",
                sample_rate=24000,
                api_key=config["api_key"],
                url=config["base_url"],
                stream=False,
            )
            if result.status_code in {400, 401, 403, 404, 422, 429}:
                raise Rejected()
            usage = result.usage or {}
            if type(usage.get("characters")) is not int:
                raise ReceiptMissing(
                    str(result.audio_id or result.request_id or ""),
                    {"audio_url": safe_url(result.audio_url)}
                    if result.audio_url
                    else None,
                )
            return {
                "usage": {"characters": usage["characters"]},
                "result": {"audio_url": safe_url(result.audio_url)},
                "upstream_id": str(result.audio_id or ""),
                "meter_basis": "供应商字符用量回执；采购账单待核对",
            }
        if provider == "tencent":
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile

            cred = credential.Credential(config["secret_id"], config["secret_key"])
            profile = ClientProfile()
            profile.httpProfile = HttpProfile(reqTimeout=120)
            if model == "haike/tencent-tts":
                import uuid

                from tencentcloud.tts.v20190823 import models, tts_client

                request = models.TextToVoiceRequest()
                request.from_json_string(
                    json.dumps(
                        {
                            "Text": inputs["text"],
                            "SessionId": str(uuid.uuid4()),
                            "VoiceType": 1001,
                            "Codec": "wav",
                            "SampleRate": 24000,
                        }
                    )
                )
                tts = tts_client.TtsClient(
                    cred, config.get("region", "ap-guangzhou"), profile
                )
                result = tencent_call(tts, "TextToVoice", request)
                if not result.Audio:
                    raise Uncertain()
                return {
                    "usage": {"characters": len(inputs["text"])},
                    "result": {"audio_base64": result.Audio, "format": "wav"},
                    "upstream_id": result.RequestId,
                    "meter_basis": "固定文本字符数；供应商账单待核对",
                }
            from tencentcloud.asr.v20190614 import asr_client, models

            client = asr_client.AsrClient(
                cred, config.get("region", "ap-guangzhou"), profile
            )
            if not upstream_id:
                request = models.CreateRecTaskRequest()
                data = (self.file_dir / inputs["audio_file"]).read_bytes()
                request.from_json_string(
                    json.dumps(
                        {
                            "EngineModelType": "16k_zh_en",
                            "ChannelNum": 1,
                            "ResTextFormat": 0,
                            "SourceType": 1,
                            "Data": base64.b64encode(data).decode(),
                            "DataLen": len(data),
                        }
                    )
                )
                response = tencent_call(client, "CreateRecTask", request)
                upstream_id = str(response.Data.TaskId)
                checkpoint(upstream_id)
            request = models.DescribeTaskStatusRequest()
            request.TaskId = int(upstream_id)
            response = tencent_call(client, "DescribeTaskStatus", request)
            if response.Data.Status == 3:
                return {"failed": True, "upstream_id": upstream_id}
            if response.Data.Status != 2:
                return {"pending": True, "upstream_id": upstream_id}
            if (
                not isinstance(response.Data.AudioDuration, (float, int))
                or not math.isfinite(response.Data.AudioDuration)
                or response.Data.AudioDuration <= 0
            ):
                raise ReceiptMissing(upstream_id, {"text": response.Data.Result})
            return {
                "usage": {"seconds": math.ceil(response.Data.AudioDuration)},
                "result": {"text": response.Data.Result},
                "upstream_id": upstream_id,
                "meter_basis": "上传 WAV 的实际采样时长向上取整；供应商账单待核对",
            }
        if provider == "pexels":
            query = urllib.parse.urlencode(
                {"query": inputs["query"], "per_page": inputs["per_page"]}
            )
            path = "/videos/search" if inputs["media"] == "videos" else "/v1/search"
            response = http(
                "https://api.pexels.com" + path + "?" + query,
                {"Authorization": config["api_key"]},
            )
            records = response.get(
                "videos" if inputs["media"] == "videos" else "photos", []
            )
            return {
                "usage": {"requests": 1},
                "result": {
                    "items": records,
                    "source": "Pexels",
                    "attribution_required": True,
                },
            }
        if provider == "runninghub":
            headers = {
                "Authorization": "Bearer " + config["api_key"],
                "Content-Type": "application/json",
            }
            base = config["base_url"].rstrip("/")
            if not upstream_id:
                uploaded = {}
                for field in ("image_file", "audio_file"):
                    boundary = "haike-upload-boundary"
                    data = (self.file_dir / inputs[field]).read_bytes()
                    kind = "image" if field == "image_file" else "audio"
                    suffix = (
                        ".wav"
                        if kind == "audio"
                        else ".png"
                        if data.startswith(b"\x89PNG")
                        else ".jpg"
                    )
                    body = (
                        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{inputs[field]}{suffix}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
                        + data
                        + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="fileType"\r\n\r\n{kind}\r\n--{boundary}--\r\n'.encode()
                    )
                    response = http(
                        base + "/openapi/v2/media/upload/binary",
                        {
                            "Authorization": headers["Authorization"],
                            "Content-Type": "multipart/form-data; boundary=" + boundary,
                        },
                        raw=body,
                    )
                    uploaded[field] = response.get("data", {}).get(
                        "fileName"
                    ) or response.get("fileName")
                    if not uploaded[field]:
                        raise Rejected()
                response = http(
                    base + "/task/openapi/create",
                    headers,
                    {
                        "apiKey": config["api_key"],
                        "workflowId": config["workflow_id"],
                        "instanceType": "plus",
                        "nodeInfoList": [
                            {
                                "nodeId": "36",
                                "fieldName": "image",
                                "fieldValue": uploaded["image_file"],
                            },
                            {
                                "nodeId": "34",
                                "fieldName": "audio",
                                "fieldValue": uploaded["audio_file"],
                            },
                            {
                                "nodeId": "35",
                                "fieldName": "value",
                                "fieldValue": inputs["total_frames"],
                            },
                            {
                                "nodeId": "24",
                                "fieldName": "trim_to_audio",
                                "fieldValue": True,
                            },
                        ],
                    },
                )
                upstream_id = str(response.get("data", {}).get("taskId") or "")
                if not upstream_id:
                    raise Uncertain()
                checkpoint(upstream_id)
            response = http(
                base + "/openapi/v2/query", headers, {"taskId": upstream_id}
            )
            data = (
                response.get("data")
                if isinstance(response.get("data"), dict)
                else response
            )
            status = str(
                data.get("status") or data.get("taskStatus", "RUNNING")
            ).upper()
            if status in {"FAILED", "FAIL", "ERROR", "CANCELLED", "CANCELED"}:
                return {"failed": True, "upstream_id": upstream_id}
            if status not in {
                "SUCCESS",
                "SUCCEEDED",
                "COMPLETED",
                "FINISH",
                "FINISHED",
            }:
                return {"pending": True, "upstream_id": upstream_id}
            videos = [
                r.get("url") or r.get("fileUrl")
                for r in data.get("results", data.get("outputs", []))
                if str(r.get("outputType", r.get("fileType", ""))).lower()
                in {"mp4", "video"}
            ]
            if not videos:
                raise Uncertain()
            return {
                "usage": {"tasks": 1},
                "result": {"video_url": safe_url(videos[0])},
                "upstream_id": upstream_id,
                "meter_basis": "每个成功工作流任务；供应商实际费用待核对",
            }
        raise Rejected()
