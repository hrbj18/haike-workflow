"""Shared pre-submit checks for versioned video publish packages."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image, UnidentifiedImageError


PACKAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
IMAGE_FORMATS = {"JPEG", "PNG"}


class PublishContractError(ValueError):
    """A publish package is incomplete before any platform write."""


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def validate_required_media(
    video_path: str | Path,
    cover_path: str | Path,
    *,
    video_sha256: str,
    cover_sha256: str,
) -> None:
    """Validate both files; callers repeat this immediately before browser upload."""
    video = Path(video_path)
    cover = Path(cover_path)
    if not video.is_file() or video.stat().st_size == 0:
        raise PublishContractError("成片不存在或为空")
    if not cover.is_file() or cover.stat().st_size == 0:
        raise PublishContractError("必需封面不存在或为空")
    if not re.fullmatch(r"[0-9A-Fa-f]{64}", video_sha256 or ""):
        raise PublishContractError("缺少有效的成片 SHA-256")
    if not re.fullmatch(r"[0-9A-Fa-f]{64}", cover_sha256 or ""):
        raise PublishContractError("缺少有效的封面 SHA-256")
    if file_sha256(video) != video_sha256.upper():
        raise PublishContractError("成片已与发布包记录不一致")
    if file_sha256(cover) != cover_sha256.upper():
        raise PublishContractError("封面已与发布包记录不一致")
    try:
        with Image.open(cover) as image:
            image.verify()
        with Image.open(cover) as image:
            width, height = image.size
            fmt = image.format
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise PublishContractError(f"封面无法解码: {exc}") from exc
    if fmt not in IMAGE_FORMATS:
        raise PublishContractError("封面只支持 JPEG 或 PNG")
    if width < 600 or height < 800 or abs(width / height - 0.75) > 0.01:
        raise PublishContractError("封面须为至少 600×800 的 3:4 图片")


def validate_cover_proof(proof_path: str | Path, *, proof_sha256: str,
                         cover_sha256: str, video_path: str | Path) -> None:
    """Require a traceable original AI image for a generated cover claim."""
    proof_file = Path(proof_path)
    if not proof_file.is_file() or file_sha256(proof_file) != proof_sha256.upper():
        raise PublishContractError("AI 封面生成证据缺失或哈希变化")
    try:
        proof = json.loads(proof_file.read_text(encoding="utf-8"))
        source = Path(proof["source_image_path"])
        if (proof.get("kind") != "ai_generated" or not proof.get("model")
                or proof.get("final_cover_sha256", "").upper() != cover_sha256.upper()
                or not source.is_file() or source.resolve() == Path(video_path).resolve()
                or file_sha256(source) != proof.get("source_image_sha256", "").upper()):
            raise PublishContractError("AI 封面生成证据与原图或最终图片不一致")
        with Image.open(source) as original:
            original.verify()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, PublishContractError):
            raise
        raise PublishContractError(f"AI 封面生成证据无效: {exc}") from exc
