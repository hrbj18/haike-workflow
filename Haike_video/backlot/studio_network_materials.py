"""Small opt-in policy and safe receipts for network footage in avatar jobs."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from backlot.studio import atomic_private, timestamp
from backlot.work_catalog import WorkError


class MaterialSearchError(WorkError):
    def __init__(self, message, status="failed"):
        super().__init__(message, "unavailable")
        self.status = status


def enabled(draft):
    value = draft.get("input", {}).get("network_materials_enabled", False)
    if type(value) is not bool:
        raise WorkError("默认联网素材开关需要明确开启或关闭")
    return value


def needs_clock(draft):
    return (draft["input"].get("subtitles", True)
            or (draft["input"].get("ai") or {}).get("enabled") or enabled(draft))


def preflight(studio):
    """Check the same selected credential the existing crawler will consume."""
    from backlot.studio_storyboard import download_account
    from backlot.network_materials import creator_call
    try:
        account_id, _, _ = download_account(studio)
    except Exception:
        raise MaterialSearchError("无法读取素材账号，请到平台账号中检查并选择抖音素材账号", "login_required") from None
    if type(account_id) is not int or account_id <= 0:
        raise MaterialSearchError("联网搜索需要有效登录，请先在平台账号中选择并检查抖音素材账号", "login_required")
    try:
        result = creator_call(f"/api/download-sessions/{account_id}/check", {}, timeout=65)
    except Exception:
        raise MaterialSearchError("素材账号登录暂时无法检查，请到平台账号中重试检查后恢复原任务") from None
    account = result.get("account") if isinstance(result, dict) else None
    if (not isinstance(account, dict) or account.get("id") != account_id
            or account.get("platform") != "douyin"):
        raise MaterialSearchError("素材账号检查结果不匹配，请重新选择抖音素材账号后恢复原任务", "login_required")
    if account.get("download_status") not in {"ready", "available"} or result.get("ok") is not True:
        if account.get("download_status") in {"network_error", "unconfirmed", "unknown"}:
            raise MaterialSearchError("素材账号登录尚未确认，请重试检查或完成平台验证后恢复原任务")
        raise MaterialSearchError("素材账号登录已失效，请重新登录并检查后恢复原任务", "login_required")
    return {"account_id": account_id, "platform": "douyin", "checked_at": timestamp()}


def validate_preflight(studio, draft):
    """Make a quote-time login blocker visible before a queue job exists."""
    if not enabled(draft): return None
    folder = studio.projects_root / draft["id"] / "renders" / f"studio-{draft['revision']}"
    previous = public_result(folder, draft)
    preserve = previous["status"] in {"ready", "used"}
    if not preserve: write_result(folder, status="checking_login", message="正在检查素材账号登录")
    try:
        result = preflight(studio)
    except WorkError as exc:
        if not preserve: write_result(folder, status=getattr(exc, "status", "failed"), message=str(exc))
        raise
    if not preserve: write_result(folder, status="pending", message="素材账号登录已确认，等待联网搜索相关画面")
    return result


def _source_url(value, source):
    if not isinstance(value, str) or len(value) > 2000:
        return None
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower()
        if url.scheme not in {"http", "https"} or url.username or url.password or url.port:
            return None
        if source == "douyin" and host in {"www.douyin.com", "douyin.com"}:
            if not re.fullmatch(r"/video/[0-9]+/?", url.path): return None
        elif source == "pexels" and host in {"www.pexels.com", "pexels.com"}:
            if not re.fullmatch(r"/(?:[a-z]{2}-[a-z]{2}/)?video/[a-zA-Z0-9_-]+/?", url.path): return None
        else:
            return None
        return urlunsplit(("https", host, url.path, "", ""))
    except ValueError:
        return None


def _items(plan):
    items = []
    for scene in (plan or {}).get("scenes", []):
        asset = scene.get("asset") or {}
        provenance = asset.get("provenance") or {}
        source = provenance.get("source")
        if source not in {"douyin", "pexels", "user"}: continue
        ident = asset.get("id")
        if not isinstance(ident, str) or not re.fullmatch(r"[a-f0-9]{32}", ident): continue
        item = {"scene_id": str(scene.get("id", ""))[:80], "label": str(scene.get("label", ""))[:300],
                "name": str(asset.get("name", ""))[:300], "asset_id": ident,
                "kind": asset.get("kind") if asset.get("kind") in {"image", "video"} else "video", "source": source}
        for key in ("start", "end"):
            value = scene.get(key)
            if type(value) in {int, float} and math.isfinite(value): item[key] = value
        url = _source_url(provenance.get("source_url"), source)
        if url: item["source_url"] = url
        items.append(item)
    return items


def write_result(folder, *, status, message, plan=None, used=False):
    items = _items(plan)
    sources = list(dict.fromkeys(item["source"] for item in items))
    result = {"enabled": True, "status": status, "message": message,
              "used_count": len(items) if used else 0, "selected_count": len(items),
              "sources": sources, "items": items, "updated_at": timestamp()}
    atomic_private(Path(folder) / "network-materials.json", result)
    return result


def public_result(folder, draft=None):
    """Reads only the safe receipt; never projects provider/debug JSON."""
    path = Path(folder) / "network-materials.json"
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("enabled") is not True: raise ValueError()
            allowed = {"pending", "checking_login", "searching", "ready", "used", "login_required", "no_materials", "failed"}
            if raw.get("status") not in allowed: raise ValueError()
            # Rebuild item metadata so a tampered/private file cannot leak fields.
            plan = {"scenes": [{"id": item.get("scene_id"), "label": item.get("label"),
                               "start": item.get("start"), "end": item.get("end"),
                               "asset": {"id": item.get("asset_id"), "name": item.get("name"), "kind": item.get("kind"),
                                         "provenance": {"source": item.get("source"), "source_url": item.get("source_url")}}}
                              for item in raw.get("items", []) if isinstance(item, dict)]}
            items = _items(plan)
            return {"enabled": True, "status": raw["status"], "message": str(raw.get("message", ""))[:500],
                    "used_count": len(items) if raw["status"] == "used" else 0,
                    "selected_count": len(items), "sources": list(dict.fromkeys(i["source"] for i in items)), "items": items}
        except (OSError, ValueError, TypeError, AttributeError):
            return {"enabled": True, "status": "failed", "message": "联网素材结果暂时无法读取，请恢复原任务核对", "used_count": 0, "sources": [], "items": []}
    if (draft is not None and "network_materials_enabled" not in draft.get("input", {})
            and draft.get("input", {}).get("ai", {}).get("enabled") is True):
        return {"enabled": None, "status": "unknown", "message": "历史任务沿用原素材策略，未记录独立联网素材结果",
                "used_count": None, "sources": [], "items": []}
    active = enabled(draft) if draft is not None else False
    return {"enabled": active, "status": "pending" if active else "disabled",
            "message": "等待联网素材搜索" if active else "本任务未启用联网素材",
            "used_count": 0, "sources": [], "items": []}
