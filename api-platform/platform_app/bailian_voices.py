"""Bailian enrollment with private OSS staging and a durable no-resubmit boundary."""

import re
from urllib.parse import urlsplit

from . import adapters
from .store import Problem


def validate_storage(config, *, partial=False):
    endpoint, bucket = config.get("oss_endpoint"), config.get("oss_bucket")
    if endpoint:
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.port
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or not re.fullmatch(r"oss-[a-z0-9-]+\.aliyuncs\.com", parsed.hostname or "")
        ):
            raise Problem(
                422, "storage_invalid", "OSS Endpoint 需为 HTTPS 阿里云标准区域地址"
            )
    if bucket and not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket):
        raise Problem(422, "storage_invalid", "OSS Bucket 格式不正确")
    if not partial and not all(
        config.get(k)
        for k in (
            "oss_endpoint",
            "oss_bucket",
            "oss_access_key_id",
            "oss_access_key_secret",
        )
    ):
        raise Problem(
            409, "clone_storage_missing", "私人克隆需要管理员在服务端配置私有 OSS"
        )


def storage(config):
    import oss2

    validate_storage(config)
    return oss2.Bucket(
        oss2.Auth(config["oss_access_key_id"], config["oss_access_key_secret"]),
        config["oss_endpoint"],
        config["oss_bucket"],
        connect_timeout=15,
    )


def execute(config, info, inputs, file_dir, checkpoint, upstream_id=None):
    """Only create once. Saved voice IDs are always queried, even after process death."""
    target = info["target_model"]
    endpoint = config["base_url"].rstrip("/") + "/services/audio/tts/customization"
    headers = {
        "Authorization": "Bearer " + config["api_key"],
        "Content-Type": "application/json",
    }
    signed_source = config.get("clone_staging") == "signed_source"
    bucket = None if signed_source else storage(config)
    operation = inputs["_job_id"]
    if not re.fullmatch(r"gj_[a-f0-9]{24}", operation):
        raise adapters.Rejected()
    object_key = "haike-api-voice-clones/" + operation + "/reference.wav"
    if not upstream_id:
        if signed_source:
            source = inputs.get("_source_url")
            if not isinstance(source, str) or not source.startswith(
                config["source_origin"] + "/v2/voice-sources/"
            ):
                raise adapters.Rejected()
        else:
            # Staging itself cannot have created a voice. An upload failure is definitive.
            try:
                bucket.put_object_from_file(
                    object_key,
                    str(file_dir / inputs["audio_file"]),
                    headers={"x-oss-object-acl": "private"},
                )
                source = bucket.sign_url("GET", object_key, 3600, slash_safe=True)
            except Exception:  # noqa: BLE001 -- staging failed before any non-idempotent provider call
                raise adapters.Rejected() from None
        try:
            response = adapters.http(
                endpoint,
                headers,
                {
                    "model": "voice-enrollment",
                    "input": {
                        "action": "create_voice",
                        "target_model": target,
                        "prefix": "haike",
                        "url": source,
                    },
                },
            )
        except adapters.Rejected:
            cleanup(bucket, object_key)
            raise
        output = response.get("output") or {}
        upstream_id = output.get("voice_id")
        if not isinstance(upstream_id, str) or not re.fullmatch(
            re.escape(target) + r"-[A-Za-z0-9_.:-]{1,220}", upstream_id
        ):
            raise adapters.Uncertain()
        # This commit precedes all later work and is the only recovery authority.
        checkpoint(upstream_id)
    response = adapters.http(
        endpoint,
        headers,
        {
            "model": "voice-enrollment",
            "input": {"action": "query_voice", "voice_id": upstream_id},
        },
    )
    output = response.get("output") or {}
    if output.get("target_model") not in {None, target}:
        raise adapters.Uncertain()
    status = str(output.get("status") or "").upper()
    if status in {"UNDEPLOYED", "FAILED"}:
        cleanup(bucket, object_key)
        return {"failed": True, "upstream_id": upstream_id}
    if status != "OK":
        return {"pending": True, "upstream_id": upstream_id}
    cleaned = cleanup(bucket, object_key)
    return {
        "usage": {"voices": 1},
        "upstream_id": upstream_id,
        "result": {
            "cleanup_warning": None
            if cleaned
            else "临时录音清理待管理员核对 OSS 生命周期"
        },
        "meter_basis": "供应商确认音色部署成功，按已确认每音色采购价结算；采购账单待核对",
    }


def cleanup(bucket, object_key):
    if bucket is None:
        return True  # Account source URLs expire and terminal job state revokes them immediately.
    try:
        bucket.delete_object(object_key)
        return True
    except Exception:  # noqa: BLE001 -- do not expose OSS signatures; lifecycle cleanup remains available
        return False
