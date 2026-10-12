"""Read a CopySkill video catalog as an untrusted, local source pool."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


class MaterialCatalogError(ValueError):
    pass


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_material_catalog(catalog_path: Path, *, workspace_root: Path, required_platform: str = "any") -> list[dict[str, Any]]:
    """Validate every entry before a caller copies or registers any asset."""
    if required_platform not in {"any", "douyin", "pexels", "bilibili"}:
        raise MaterialCatalogError("素材来源策略无效")
    catalog_path = catalog_path.resolve()
    workspace_root = workspace_root.resolve()
    try:
        catalog_path.relative_to(workspace_root)
    except ValueError as exc:
        raise MaterialCatalogError("素材目录不在当前工作区内") from exc
    if catalog_path.name not in {"00-素材目录.json", "清单.json"} or not catalog_path.is_file():
        raise MaterialCatalogError("缺少 CopySkill 标准素材目录或原片清单")
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterialCatalogError("素材目录无法读取") from exc
    if not isinstance(catalog, dict):
        raise MaterialCatalogError("素材目录版本或条目格式无效")
    if catalog_path.name == "清单.json":
        if catalog.get("schema_version") != 1 or catalog.get("mode") != "download_only" or not isinstance(catalog.get("downloads"), list):
            raise MaterialCatalogError("原片清单不是 CopySkill 的 download_only 交付")
        entries = [
            {
                "material_id": str(item.get("video_id") or ""),
                "file_path": item.get("file"),
                "file_bytes": item.get("size_bytes"),
                "duration_seconds": item.get("duration_seconds"),
                "source_platform": "douyin" if re.search(r"^https://(?:[\w-]+\.)*(?:douyin\.com|iesdouyin\.com)/", str(item.get("source_url") or ""), re.I) else "unknown",
                "source_url": item.get("source_url"),
                "title": item.get("title"),
                "rights_status": "review_required",
                "video_id": item.get("video_id"),
            }
            for item in catalog["downloads"] if isinstance(item, dict)
        ]
    elif catalog.get("schema_version") == 1 and isinstance(catalog.get("entries"), list):
        entries = catalog["entries"]
    else:
        raise MaterialCatalogError("素材目录版本或条目格式无效")
    if len(entries) > 100:
        raise MaterialCatalogError("素材目录条目过多")
    root = catalog_path.parent
    prepared: list[dict[str, Any]] = []
    seen: set[str] = set()
    total = 0
    for raw in entries:
        if not isinstance(raw, dict):
            raise MaterialCatalogError("素材目录含无效条目")
        relative = Path(str(raw.get("file_path") or ""))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts or relative.suffix.lower() != ".mp4":
            raise MaterialCatalogError("素材目录含越界或非视频文件")
        source = (root / relative).resolve()
        try:
            source.relative_to(root)
        except ValueError as exc:
            raise MaterialCatalogError("素材文件路径越界") from exc
        if not source.is_file() or source.stat().st_size != int(raw.get("file_bytes") or -1):
            raise MaterialCatalogError(f"素材文件缺失或字节数变化：{relative.name}")
        total += source.stat().st_size
        if total > 2 * 1024 * 1024 * 1024:
            raise MaterialCatalogError("本次素材池超过 2 GiB")
        platform = str(raw.get("source_platform") or "unknown").strip().lower()
        source_url = str(raw.get("source_url") or "").strip()
        if required_platform != "any" and platform != required_platform:
            raise MaterialCatalogError(f"素材 {relative.name} 的来源不符合 {required_platform} 策略")
        if platform == "douyin" and not re.search(r"^https://(?:[\w-]+\.)*(?:douyin\.com|iesdouyin\.com)/", source_url, re.I):
            raise MaterialCatalogError(f"素材 {relative.name} 缺少抖音原视频链接")
        duration = raw.get("duration_seconds")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < .4:
            raise MaterialCatalogError(f"素材 {relative.name} 缺少可用时长")
        material_id = str(raw.get("material_id") or "")
        if not material_id or material_id in seen:
            raise MaterialCatalogError("素材 ID 缺失或重复")
        seen.add(material_id)
        prepared.append({
            "material_id": material_id,
            "source": source,
            "sha256": file_sha256(source),
            "bytes": source.stat().st_size,
            "duration_seconds": round(float(duration), 3),
            "platform": platform,
            "source_url": source_url,
            "title": str(raw.get("title") or material_id)[:160],
            "rights_status": str(raw.get("rights_status") or "unknown")[:80],
            "video_id": str(raw.get("video_id") or "")[:100],
        })
    return prepared
