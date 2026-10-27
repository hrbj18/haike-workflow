"""SQLite-backed queue, source provenance, crash recovery and fixed PNG delivery."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from .presets import HEIGHT, PRESET_VERSION, PROMPT, WIDTH
from .provider import RefinementError, ResponsesProvider, Settings

MAX_BYTES = 25 * 1024 * 1024
ACTIVE = {"queued", "running", "normalizing"}


def inspect_image(raw: bytes) -> dict:
    if not raw or len(raw) > MAX_BYTES:
        raise RefinementError("图片不能为空且不能超过25MB。")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            width, height = image.size
            if (
                image.format not in {"PNG", "JPEG", "WEBP"}
                or min(width, height) < 64
                or max(width, height) > 7000
            ):
                raise RefinementError(
                    "请上传长宽至少64像素、最长边不超过7000像素的PNG、JPEG或WEBP图片。"
                )
            image.verify()
            return {"width": width, "height": height, "mime": Image.MIME[image.format]}
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise RefinementError("图片损坏或无法读取，请重新选择图片。") from None


def normalize(raw: bytes) -> tuple[bytes, dict]:
    info = inspect_image(raw)
    with Image.open(io.BytesIO(raw)) as loaded:
        image = ImageOps.exif_transpose(loaded).convert("RGBA")
        oriented_width, oriented_height = image.size
        background = Image.new("RGBA", image.size, "white")
        background.alpha_composite(image)
        image = ImageOps.fit(
            background.convert("RGB"),
            (WIDTH, HEIGHT),
            Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        output = io.BytesIO()
        image.save(output, "PNG")
    return output.getvalue(), {
        "raw_width": info["width"],
        "raw_height": info["height"],
        "width": WIDTH,
        "height": HEIGHT,
        "oriented_width": oriented_width,
        "oriented_height": oriented_height,
        "upscaled": oriented_width < WIDTH or oriented_height < HEIGHT,
        "fit": "center_crop_lanczos",
    }


def atomic_bytes(path: Path, raw: bytes):
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)


class RefinementService:
    def __init__(
        self,
        root: Path,
        *,
        settings: Settings | None = None,
        provider=None,
        prompt: str = PROMPT,
        preset_version: str = PRESET_VERSION,
    ):
        if (
            not isinstance(prompt, str)
            or not 1 <= len(prompt) <= 8000
            or not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,120}", preset_version)
        ):
            raise RefinementError("预设需要有效版本编号和1至8000字提示词。")
        self.prompt, self.preset_version = prompt, preset_version
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings = settings or Settings.from_env()
        self.provider = provider or ResponsesProvider(self.settings)
        self.db = self.root / "jobs.sqlite3"
        self.wake, self.stopping = threading.Event(), threading.Event()
        self.thread = None
        self.guard = threading.Lock()
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, namespace TEXT NOT NULL, dedupe TEXT NOT NULL,
                status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                source_sha256 TEXT NOT NULL, mime TEXT NOT NULL, config TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '', error_code TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}', dispatched REAL,
                UNIQUE(namespace, dedupe))""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def validate_namespace(namespace: str):
        if not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,160}", namespace):
            raise RefinementError("项目命名空间无效。")

    def directory(self, job_id: str) -> Path:
        if not re.fullmatch(r"IR-[a-f0-9]{32}", job_id):
            raise RefinementError("图片任务编号无效。", code="not_found")
        return self.root / job_id

    def _row(self, job_id: str, namespace: str):
        self.validate_namespace(namespace)
        self.directory(job_id)
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE id=? AND namespace=?", (job_id, namespace)
            ).fetchone()
        if not row:
            raise RefinementError("图片任务不存在或不属于当前项目。", code="not_found")
        return row

    def get(self, job_id: str, namespace: str) -> dict:
        self.recover()
        row = self._row(job_id, namespace)
        return {
            key: row[key]
            for key in (
                "id",
                "namespace",
                "status",
                "created",
                "updated",
                "source_sha256",
                "error",
                "error_code",
            )
        } | {
            "config": json.loads(row["config"]),
            "metadata": json.loads(row["metadata"]),
            "can_retry": row["status"] in {"failed", "ambiguous", "succeeded"},
        }

    def submit(
        self,
        raw: bytes,
        namespace: str,
        *,
        confirmed: bool = False,
        retry_of: str | None = None,
        acknowledge_uncertain: bool = False,
    ) -> dict:
        if confirmed is not True:
            raise RefinementError(
                "请先确认本次修图可能产生中转费用。", code="confirmation_required"
            )
        self.validate_namespace(namespace)
        info = inspect_image(raw)
        digest = hashlib.sha256(raw).hexdigest()
        config = {
            "preset_version": self.preset_version,
            "prompt": self.prompt,
            "width": WIDTH,
            "height": HEIGHT,
            "image_model": self.settings.image_model,
            "text_model": self.settings.text_model,
            "base_url": self.settings.base_url,
            "credential_fingerprint": hashlib.sha256(
                self.settings.api_key.encode()
            ).hexdigest(),
        }
        if retry_of:
            previous = self.get(retry_of, namespace)
            config = previous["config"]
            if previous["source_sha256"] != digest:
                raise RefinementError("重试图片与原任务不一致。", code="conflict")
            if previous["status"] in ACTIVE:
                return previous
            if previous["status"] == "ambiguous" and not acknowledge_uncertain:
                raise RefinementError(
                    "上次结果或扣费不确定，请先核对中转记录并明确确认后再重新提交。",
                    code="confirmation_required",
                )
            if (self.directory(retry_of) / "raw").is_file() and previous[
                "status"
            ] != "succeeded":
                self._update(retry_of, status="normalizing", error="", error_code="")
                self.wake.set()
                return self.get(retry_of, namespace)
            dedupe = "retry:" + retry_of
        else:
            dedupe = hashlib.sha256(
                (digest + json.dumps(config, sort_keys=True)).encode()
            ).hexdigest()
        job_id = "IR-" + uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT id FROM jobs WHERE namespace=? AND dedupe=?",
                (namespace, dedupe),
            ).fetchone()
            if existing:
                job_id = existing["id"]
            else:
                pending = db.execute(
                    "SELECT count(*) FROM jobs WHERE status IN ('queued','running','normalizing')"
                ).fetchone()[0]
                if pending >= 100:
                    raise RefinementError(
                        "精修队列已满，请稍后重试或使用原图。", code="queue_full"
                    )
                directory = self.directory(job_id)
                directory.mkdir()
                atomic_bytes(directory / "source", raw)
                now = time.time()
                db.execute(
                    "INSERT INTO jobs(id,namespace,dedupe,status,created,updated,source_sha256,mime,config) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        job_id,
                        namespace,
                        dedupe,
                        "queued",
                        now,
                        now,
                        digest,
                        info["mime"],
                        json.dumps(config, ensure_ascii=False),
                    ),
                )
        self.wake.set()
        return self.get(job_id, namespace)

    def _update(self, job_id: str, **fields):
        assert set(fields) <= {
            "status",
            "error",
            "error_code",
            "metadata",
            "dispatched",
        }
        fields["updated"] = time.time()
        with self.connect() as db:
            db.execute(
                "UPDATE jobs SET "
                + ",".join(key + "=?" for key in fields)
                + " WHERE id=?",
                (*fields.values(), job_id),
            )

    def recover(self):
        # A different worker/process may still own a live call. Only an expired
        # lease is recoverable, and a sent request is NEVER automatically resent.
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,config,updated FROM jobs WHERE status='running'"
            ).fetchall()
            for row in rows:
                if time.time() - row["updated"] <= 660:
                    continue
                has_raw = (self.directory(row["id"]) / "raw").is_file()
                db.execute(
                    "UPDATE jobs SET status=?,error=?,error_code=?,updated=? WHERE id=? AND status='running' AND updated=?",
                    (
                        "normalizing" if has_raw else "ambiguous",
                        ""
                        if has_raw
                        else "服务中断，已提交请求的结果和扣费状态不确定；请先核对中转记录。",
                        "" if has_raw else "interrupted",
                        time.time(),
                        row["id"],
                        row["updated"],
                    ),
                )

    def process_one(self) -> bool:
        self.recover()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM jobs WHERE status='running'").fetchone():
                return False
            row = db.execute(
                "SELECT * FROM jobs WHERE status IN ('queued','normalizing') ORDER BY created LIMIT 1"
            ).fetchone()
            if not row:
                return False
            has_raw = (self.directory(row["id"]) / "raw").is_file()
            today = time.gmtime()
            import calendar

            day_start = calendar.timegm(
                (today.tm_year, today.tm_mon, today.tm_mday, 0, 0, 0)
            )
            count = db.execute(
                "SELECT count(*) FROM jobs WHERE dispatched>=?", (day_start,)
            ).fetchone()[0]
            if not has_raw and count >= self.settings.daily_limit:
                db.execute(
                    "UPDATE jobs SET status='failed',error=?,error_code='daily_limit',updated=? WHERE id=?",
                    (
                        "已达到服务每日提交次数上限，可明日手动重试或使用原图。",
                        time.time(),
                        row["id"],
                    ),
                )
                return True
            db.execute(
                "UPDATE jobs SET status='running',updated=?,dispatched=CASE WHEN ? THEN dispatched ELSE ? END WHERE id=?",
                (time.time(), has_raw, time.time(), row["id"]),
            )
        directory = self.directory(row["id"])
        try:
            config = json.loads(row["config"])
            if not has_raw:
                if (
                    config["base_url"] != self.settings.base_url
                    or config.get("credential_fingerprint")
                    != hashlib.sha256(self.settings.api_key.encode()).hexdigest()
                ):
                    raise RefinementError(
                        "中转地址或账户凭据已变化，请核对原任务；旧任务不会换源提交。",
                        code="configuration_changed",
                    )
                # Model and prompt are frozen at submission, even across upgrades.
                provider = self.provider
                if isinstance(provider, ResponsesProvider):
                    from dataclasses import replace

                    provider = ResponsesProvider(
                        replace(
                            self.settings,
                            image_model=config["image_model"],
                            text_model=config["text_model"],
                        )
                    )
                raw, metadata = provider.edit(
                    (directory / "source").read_bytes(), row["mime"], config["prompt"]
                )
                atomic_bytes(
                    directory / "provider.json",
                    json.dumps(metadata, ensure_ascii=False).encode(),
                )
                atomic_bytes(directory / "raw", raw)
            else:
                raw = (directory / "raw").read_bytes()
                metadata_path = directory / "provider.json"
                metadata = (
                    json.loads(metadata_path.read_text(encoding="utf-8"))
                    if metadata_path.is_file()
                    else {}
                )
            result, dimensions = normalize(raw)
            atomic_bytes(directory / "result.png", result)
            metadata.update(dimensions)
            self._update(
                row["id"],
                status="succeeded",
                metadata=json.dumps(metadata, ensure_ascii=False),
                error="",
                error_code="",
            )
        except RefinementError as exc:
            self._update(
                row["id"],
                status="ambiguous" if exc.uncertain else "failed",
                error=str(exc),
                error_code=exc.code,
                metadata=json.dumps(exc.metadata, ensure_ascii=False),
            )
        except Exception:
            self._update(
                row["id"],
                status="failed" if (directory / "raw").is_file() else "ambiguous",
                error="图片处理未完成；已保留原图和收到的结果。可手动重试，本地处理重试会复用已收到的图片。",
                error_code="processing_error",
            )
        return True

    def file(self, job_id: str, namespace: str, kind: str) -> bytes:
        job = self.get(job_id, namespace)
        names = {"source": "source", "raw": "raw", "result": "result.png"}
        if kind not in names or (kind == "result" and job["status"] != "succeeded"):
            raise RefinementError("图片结果尚未就绪。", code="not_found")
        path = self.directory(job_id) / names[kind]
        if not path.is_file():
            raise RefinementError("图片文件不存在。", code="not_found")
        return path.read_bytes()

    def start(self):
        with self.guard:
            if self.thread and self.thread.is_alive():
                return
            self.stopping.clear()
            self.thread = threading.Thread(
                target=self._loop, daemon=True, name="image-refinement"
            )
            self.thread.start()

    def _loop(self):
        while not self.stopping.is_set():
            try:
                if self.process_one():
                    continue
            except sqlite3.Error:
                pass
            self.wake.wait(2)
            self.wake.clear()

    def close(self):
        self.stopping.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=2)
