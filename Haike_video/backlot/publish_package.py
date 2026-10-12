"""Create a versioned, inspectable three-platform publish package offline."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .publish_adapter import PublishIntent, build_publish_payload


PLATFORMS = ("douyin", "kuaishou", "shipinhao")


def build_package(project_id: str, intents: dict[str, PublishIntent],
                  source_rights: list[dict]) -> dict:
    if set(intents) != set(PLATFORMS):
        raise ValueError("发布包必须包含抖音、快手和视频号各一条意图")
    entries = {}
    package_ids = set()
    revisions = set()
    for platform in PLATFORMS:
        intent = intents[platform]
        if intent.platform != platform:
            raise ValueError(f"{platform} 的发布意图平台不一致")
        built = build_publish_payload(intent)
        if built.blocked:
            raise ValueError(f"{platform} 预检失败：{'；'.join(built.blocked)}")
        entries[platform] = {"payload": built.payload, "warnings": built.warnings}
        package_ids.add(built.payload["package_id"])
        revisions.add(built.payload["package_revision"])
    if len(package_ids) != 1:
        raise ValueError("三平台必须使用同一成片与封面版本")
    if len(revisions) != 1:
        raise ValueError("三平台发布包修订号必须一致")
    if not source_rights:
        raise ValueError("发布包必须记录来源素材授权状态")
    rights_ok = all(row.get("rights_status") in ("confirmed", "owned")
                    for row in source_rights)
    declared_ok = all(intents[platform].source_rights_status in ("confirmed", "owned")
                      for platform in PLATFORMS)
    if rights_ok != declared_ok:
        raise ValueError("逐片段来源授权状态与发布意图不一致")
    return {"schema_version": 1, "project_id": project_id,
            "package_id": package_ids.pop(), "package_revision":
            intents[PLATFORMS[0]].package_revision,
            "source_rights": source_rights, "platforms": entries}


def save_package(path: Path, package: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != package:
            raise ValueError("发布包文件内容已变化；请修订版本并使用新路径")
        return
    pending = path.with_suffix(path.suffix + ".tmp")
    with pending.open("w", encoding="utf-8") as stream:
        json.dump(package, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)
