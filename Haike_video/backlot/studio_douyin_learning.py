"""Explicit local learning test; this module is never a production queue handler."""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from urllib import error, request
from urllib.parse import urlsplit

from backlot.studio import atomic_private, timestamp
from backlot.studio_storyboard import crawler_config, download_account
from backlot.work_catalog import WorkError, sha

PURPOSE = "learning_test"
KEYWORD = "机器人"
MAX_BYTES = 50 * 1024 * 1024


def require_learning_scope(purpose, confirmed):
    if (os.environ.get("HAIKE_LOCAL_LEARNING_TEST") != "1"
            or purpose != PURPOSE or confirmed is not True):
        raise WorkError("本地学习测试默认关闭；需要本进程学习开关、learning_test用途和明确确认")


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_api(base_url, path, payload=None, *, allow_missing=False):
    parsed = urlsplit(base_url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise WorkError("学习测试只连接本机工作台回环地址")
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    req = request.Request(base_url.rstrip("/") + path, data=data,
                          headers={"Content-Type": "application/json"})
    try:
        opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())
        with opener.open(req, timeout=75) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError()
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except error.HTTPError as exc:
        if allow_missing and exc.code == 404:
            return None
        raise WorkError("工作台未完成本次学习测试操作；请检查本机服务或账号状态，原文件保留") from None
    except (error.URLError, OSError, TimeoutError, ValueError):
        raise WorkError("工作台响应暂不可确认；请检查本机服务，已有文件无需重新采集") from None


def _safe_candidate(candidate):
    ident = str(candidate.video_id)
    if not re.fullmatch(r"[0-9]{10,24}", ident):
        return None
    duration = candidate.duration_seconds
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration):
        duration = 0
    return {"video_id": ident, "title": str(candidate.title)[:160],
            "author": str(candidate.author)[:80], "duration_seconds": duration,
            "source_url": "https://www.douyin.com/video/" + ident}


def register_learning_result(folder, manifest, workbench_url):
    """Idempotent API-only registration, preserving pre-existing metadata and paths."""
    folder = Path(folder).resolve()
    path = folder / "learning-test-机器人.mp4"
    catalog = folder / "00-素材目录.json"
    artifact = manifest.get("artifact") or {}
    if (manifest.get("purpose") != PURPOSE or artifact.get("path") != str(path)
            or path.is_symlink() or not path.is_file() or catalog.is_symlink() or not catalog.is_file()
            or path.stat().st_size != artifact.get("bytes") or sha(path) != artifact.get("sha256")
            or sha(catalog) != manifest.get("catalog_sha256")):
        raise WorkError("本次学习测试文件或摘要已变化，不能恢复登记")
    media_id = "MAT-" + artifact["sha256"]
    detail_path = "/api/material-library/manage/media/" + media_id
    if "baseline" not in manifest:
        # The detail API uses 422 for missing assets. Search has an explicit
        # empty-list contract and must include archived assets in this baseline.
        found = local_api(workbench_url,
                          "/api/material-library/manage/search?query=" + media_id + "&archived=all")
        exists = any(item.get("id") == media_id for item in found.get("items", []))
        existing = local_api(workbench_url, detail_path) if exists else None
        manifest["baseline"] = {
            "media_id": media_id, "preexisting_media": existing is not None,
            "prior_locations": [item["path"] for item in (existing or {}).get("locations", [])],
        }
    manifest["status"] = "registering"
    atomic_private(folder / "manifest.json", manifest)
    registered = local_api(workbench_url, "/api/material-library/import",
                           {"kind": "catalog", "path": str(catalog)})
    if registered.get("media_ids") != [media_id]:
        raise WorkError("素材登记结果与本次文件不一致，请核对原登记，不重新下载")
    detail = local_api(workbench_url, detail_path)
    metadata = detail["metadata"]
    note = "本地学习测试：" + manifest["run_id"] + "；仅学习用途，不构成商用素材授权。"
    tags = list(dict.fromkeys([*metadata["tags"], "学习测试", KEYWORD, "MediaCrawler"]))
    notes = metadata["notes"] if note in metadata["notes"] else (metadata["notes"] + "\n" + note).strip()
    patch = {"tags": tags}
    if len(notes) <= 4000:
        patch["notes"] = notes
    if any(metadata[key] != value for key, value in patch.items()):
        local_api(workbench_url, "/api/material-library/manage/metadata", {
            "items": [{"media_id": media_id, "expected_revision": metadata["revision"]}],
            "patch": patch,
        })
    manifest.update(status="completed", media_id=media_id, completed_at=timestamp(),
                    new_file=True, new_library_media=not manifest["baseline"]["preexisting_media"])
    atomic_private(folder / "manifest.json", manifest)
    return manifest


def run_learning_test(studio, *, run_id, purpose, confirmed, workbench_url="http://127.0.0.1:14756",
                      search_only=False, register_only=False):
    require_learning_scope(purpose, confirmed)
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id):
        raise WorkError("学习测试编号需要1至64位字母、数字、下划线或短横线")
    if search_only and register_only:
        raise WorkError("只搜索与恢复登记不能同时选择")
    base = studio.private.resolve() / "local-learning/douyin"
    folder = base / run_id
    if folder.is_symlink() or folder.resolve().parent != base.resolve():
        raise WorkError("学习测试目录位置无效")
    if register_only:
        try:
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise WorkError("此编号没有可恢复的学习测试记录") from None
        return register_learning_result(folder, manifest, workbench_url)
    try:
        folder.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise WorkError("此编号已使用，未重复采集；已有文件请用--register-only恢复登记") from None
    manifest = {"purpose": PURPOSE, "run_id": run_id, "keyword": KEYWORD, "status": "preflight",
                "created_at": timestamp(), "max_candidates": 10, "max_downloads": 1,
                "max_bytes": MAX_BYTES, "duration_range_seconds": [5, 60]}
    atomic_private(folder / "manifest.json", manifest)
    try:
        account_id, _, _ = download_account(studio)
        if account_id is None:
            raise WorkError("请先在统一下载登录中选择抖音账号")
        checked = local_api(workbench_url, f"/api/studio/download-sessions/{account_id}/check", {})
        account = checked.get("account") or {}
        if (checked.get("ok") is not True or account.get("id") != account_id
                or account.get("platform") != "douyin" or account.get("download_status") not in {"ready", "available"}):
            raise WorkError("抖音下载登录未检查通过，请先在工作台处理登录或验证")
        config = crawler_config(studio, folder / "crawler-runs")
        if config["media_crawler"].get("download_account_id") != account_id:
            raise WorkError("下载账号已切换，未使用另一个账号采集")
        manifest.update(account_id=account_id, status="searching")
        atomic_private(folder / "manifest.json", manifest)
        from douyin_intelligence.sources.douyin import DouyinSource
        source = DouyinSource()
        result = source.search([KEYWORD], 10, config=config, run_id=run_id)
        if getattr(result, "report", {}).get("needs_human_verification") is True:
            raise WorkError("抖音登录需要人工确认，请在工作台处理后恢复；未自动处理验证码")
        if result.status == "failed" or not result.candidates:
            raise WorkError("本次机器人搜索未取得候选，请检查账号和采集器，不自动重新采集")
        candidates = [(item, _safe_candidate(item)) for item in result.candidates[:10]]
        safe = [item for _, item in candidates if item]
        if not safe:
            raise WorkError("本次搜索没有可安全保存的候选，未执行下载")
        atomic_private(folder / "candidates.json", {"purpose": PURPOSE, "items": safe})
        manifest.update(status="searched", candidate_count=len(safe))
        atomic_private(folder / "manifest.json", manifest)
        if search_only:
            return manifest
        chosen = next(((item, safe_item) for item, safe_item in candidates if safe_item
                       and 5 <= safe_item["duration_seconds"] <= 60 and not item.media_is_audio
                       and source.resolve_media_url(item)), None)
        if chosen is None:
            raise WorkError("本页没有5至60秒的可下载视频；候选已保存，不扩大搜索或下载数量")
        candidate, selected = chosen
        manifest.update(status="downloading", selected=selected)
        atomic_private(folder / "manifest.json", manifest)
        from backlot.studio_avatar import download_result
        from backlot.studio_render import media_probe
        path = folder / "learning-test-机器人.mp4"
        download_result(source.resolve_media_url(candidate), path,
                        referer=source.download_referer, max_bytes=MAX_BYTES)
        info = media_probe(path)
        if not info.get("video") or not 5 <= info["duration"] <= 60 or path.stat().st_size > MAX_BYTES:
            raise WorkError("本次文件不符合学习测试的视频、时长或大小限制；原文件保留，未登记")
        artifact = {"path": str(path), "sha256": sha(path), "bytes": path.stat().st_size,
                    "duration_seconds": info["duration"]}
        atomic_private(folder / "00-素材目录.json", {"schema_version": 1, "entries": [{
            "material_id": "learning-" + selected["video_id"], "file_path": path.name,
            "file_bytes": artifact["bytes"], "duration_seconds": info["duration"],
            "source_platform": "douyin", "source_url": selected["source_url"],
            "video_id": selected["video_id"], "title": "学习测试·机器人·" + selected["title"],
            "rights_status": "local_learning_only",
        }]})
        manifest.update(status="downloaded", artifact=artifact,
                        catalog_sha256=sha(folder / "00-素材目录.json"))
        atomic_private(folder / "manifest.json", manifest)
        return register_learning_result(folder, manifest, workbench_url)
    except Exception:
        manifest["status"] = "registration_pending" if "artifact" in manifest else "stopped"
        manifest["message"] = "原学习测试记录已保留；有文件时仅恢复登记，不自动重采"
        atomic_private(folder / "manifest.json", manifest)
        raise
