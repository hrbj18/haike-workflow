"""Ten-minute provider-only reference URLs bound to an accepted enrollment job."""

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from urllib.parse import urlencode

from . import deployment
from .store import Problem

LIFETIME = 600
PREFIX = "/v2/voice-sources/"


class RedactSourceAccess(logging.Filter):
    def filter(self, record):
        if (
            isinstance(record.args, tuple)
            and len(record.args) >= 3
            and PREFIX in str(record.args[2])
        ):
            values = list(record.args)
            values[2] = PREFIX + "[private-reference]"
            record.args = tuple(values)
        return True


def configure_logging():
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactSourceAccess) for f in logger.filters):
        logger.addFilter(RedactSourceAccess())


def secret(store):
    path = store.path.parent / "voice_source.master.key"
    if not path.exists():
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(secrets.token_bytes(32))
        except FileExistsError:
            pass
    value = path.read_bytes()
    if len(value) != 32:
        raise Problem(
            503, "voice_source_unavailable", "样音签名服务暂不可用，请联系管理员"
        )
    return value


def accepted_reference(store, job_id):
    if not re.fullmatch(r"gj_[a-f0-9]{24}", job_id):
        raise Problem(404, "source_missing", "参考录音链接不可用")
    with store.read() as db:
        row = db.execute(
            "SELECT j.user_id,j.status,j.quote_id,q.input_json,q.snapshot,q.accepted_job_id "
            "FROM gateway_jobs j JOIN gateway_quotes q ON q.id=j.quote_id WHERE j.id=?",
            (job_id,),
        ).fetchone()
        if (
            not row
            or row["accepted_job_id"] != job_id
            or row["status"]
            not in {"submitting", "polling", "running", "submission_unknown"}
        ):
            raise Problem(404, "source_missing", "参考录音链接不可用")
        snapshot = json.loads(row["snapshot"])
        if snapshot["model_info"]["capability"] != "voice_clone":
            raise Problem(404, "source_missing", "参考录音链接不可用")
        file_id = json.loads(row["input_json"])["audio_file"]
        file = db.execute(
            "SELECT id FROM gateway_files WHERE id=? AND user_id=? AND kind='audio'",
            (file_id, row["user_id"]),
        ).fetchone()
        if not file:
            raise Problem(404, "source_missing", "参考录音链接不可用")
        return file_id


def signature(key, job_id, file_id, expires):
    message = "haike-voice-source-v1\n" + job_id + "\n" + file_id + "\n" + str(expires)
    return hmac.new(key, message.encode(), hashlib.sha256).hexdigest()


def issue_url(store, job_id, origin):
    origin = deployment.public_origin(origin)
    if not origin or origin != getattr(store, "public_origin", None):
        raise Problem(
            409, "voice_source_origin", "部署地址已变化，请联系管理员核对原任务"
        )
    file_id = accepted_reference(store, job_id)
    expires = int(time.time()) + LIFETIME
    token = signature(secret(store), job_id, file_id, expires)
    return (
        origin
        + PREFIX
        + job_id
        + "?"
        + urlencode({"expires": expires, "signature": token})
    )


def read_reference(store, job_id, expires, token):
    if not re.fullmatch(r"[0-9]{1,12}", expires or "") or not re.fullmatch(
        r"[a-f0-9]{64}", token or ""
    ):
        raise Problem(404, "source_missing", "参考录音链接不可用")
    clock = int(time.time())
    if not clock < int(expires) <= clock + LIFETIME:
        raise Problem(404, "source_missing", "参考录音链接不可用")
    file_id = accepted_reference(store, job_id)
    expected = signature(secret(store), job_id, file_id, int(expires))
    if not hmac.compare_digest(expected, token):
        raise Problem(404, "source_missing", "参考录音链接不可用")
    path = store.path.parent / "files" / file_id
    if not path.is_file():
        raise Problem(404, "source_missing", "参考录音链接不可用")
    return path.read_bytes()
