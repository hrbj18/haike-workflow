"""Connect commentary evidence and immutable versions to the shared media library.

New selections require active media. Recovery resolves a previously frozen source
by content identity and may use archived media. A reviewed commentary crop grants
no approval to another crop, output profile, or the legacy central-band template.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from backlot import material_library as library
from backlot import material_library_management as management
from backlot import material_library_refs as refs
from backlot.commentary_common import (
    CommentaryError, WORKFLOW, crop_value, digest, file_sha256, identifier,
    text, verified,
)


def ensure_available(media_id, *, db_path=None):
    """Return registered metadata; reject archived media for new evidence/use."""
    try:
        media = library.get_media(media_id, db_path=db_path)
        if management.get_metadata(media_id, db_path=db_path)["archived"]:
            raise CommentaryError("素材已归档，不能新建取证或用于新版本；已有冻结版本仍可恢复")
        return media
    except library.MaterialLibraryError as exc:
        raise CommentaryError(str(exc)) from exc


def resolve_source(media_id, sha256, *, db_path=None):
    """Return a verified current Path, allowing archived history and same-SHA moves."""
    try:
        media = library.get_media(media_id, db_path=db_path)
        if media["sha256"] != sha256:
            raise CommentaryError("冻结原片与素材库内容不一致，旧证据不可沿用")
        return library.resolve_media(media_id, db_path=db_path, verify_hash=True)
    except library.MaterialLibraryError as exc:
        raise CommentaryError(str(exc)) from exc


def search(query="", *, limit=12, db_path=None):
    """Return active media rows, including tag/collection/observation matches."""
    return management.search({"query": query, "page_size": limit, "archived": "active"},
                             db_path=db_path)["items"]


def _scope(frozen, crop):
    # Rendering contains the reviewed crop inside this exact output profile.
    # The scope describes that adaptation, never a global source-content grant.
    profile = {"format": frozen["format"], "profile": frozen["profile"],
               "crop": crop_value(crop), "fit": "contain"}
    return f"{WORKFLOW}-v1:{digest(profile)}"


def _shots(project_id, frozen):
    text(project_id, "项目编号", 160)
    if frozen.get("project_id") != project_id:
        raise CommentaryError("冻结版本与项目身份不一致")
    seen = set()
    for segment in frozen["segments"]:
        scene = identifier(segment["id"])
        if scene in seen:
            raise CommentaryError("冻结版本的段落编号重复")
        seen.add(scene)
        for index, shot in enumerate(segment["shots"], 1):
            yield segment, f"shot-{index:03d}", shot
        for index, clip in enumerate(segment.get("source_audio", []), 1):
            yield segment, f"audio-{index:03d}", clip


def _observation(project, frozen, shot, *, db_path=None):
    # Import locally because the evidence producer itself uses ensure_available.
    from backlot import commentary_evidence as evidence

    identity = shot["evidence_id"]
    item = evidence.read(project, identity)
    if item != frozen["evidence"].get(identity) or digest(item) != shot["evidence_digest"]:
        raise CommentaryError("素材观察与冻结镜头不一致，请重新编排并提交")
    review = item.get("review")
    if not review or review.get("viewed") is not True or review.get("usable") is not True:
        raise CommentaryError("镜头尚未完成查看和确认，不能登记为已审核引用")
    reviewer = text(review.get("reviewer"), "审核者", 160)
    media_id = shot["media_id"]
    media = ensure_available(media_id, db_path=db_path)
    source = frozen["sources"][media_id]
    if (item["media_id"] != media_id or item["sha256"] != media["sha256"]
            or source["sha256"] != media["sha256"] or shot["crop"] != item["crop"]):
        raise CommentaryError("镜头、裁切或原片内容与观察不一致")
    resolve_source(media_id, item["sha256"], db_path=db_path)
    start = library.number(shot["start"], "镜头起点", item["start"], item["end"])
    end = library.number(shot["end"], "镜头终点", start, item["end"])
    if end <= start:
        raise CommentaryError("镜头终点必须晚于起点")
    target = evidence.directory(project, identity)
    files = []
    for name, sha in item["files"].items():
        # Evidence filenames are producer-owned; do not accept traversal from a
        # modified project manifest even when the requested file hash matches.
        if name not in {"source.mp4", "sheet.jpg"}:
            raise CommentaryError("素材证据文件名无效")
        files.append({"path": str(verified(target / name, sha).resolve()), "sha256": sha})
    if set(item["files"]) != {"source.mp4", "sheet.jpg"}:
        raise CommentaryError("素材证据缺少连续片段或代表帧")
    for name in ("evidence.json", "review.json"):
        path = (target / name).resolve()
        files.append({"path": str(path), "sha256": file_sha256(path)})
    # Recheck the JSON evidence after hashing so the registry never confirms a
    # different review from the one checked above.
    if evidence.read(project, identity) != item:
        raise CommentaryError("素材观察正在变化，请重新提交")
    facts = {"subtitles": {"none": False, "present": True, "unknown": "unknown"}[
        review["source_subtitles"]]}
    if review.get("audio_reviewed") is True and review.get("transcript"):
        facts["source_audio"] = review["transcript"]
    description = (f"{review['observation']}\n前后文：{review['context']}\n"
                   f"未确认：{review.get('unknowns', '')}\n"
                   "本观察仅覆盖已查看的裁切区域；其他裁切或模板须另行审核。")
    return {"media_id": media_id, "source_in": item["start"], "source_out": item["end"],
            "scope": _scope(frozen, shot["crop"]), "observation": description,
            "facts": facts, "review_status": "confirmed", "reviewer": reviewer, "evidence": files}


def bind_references(project_id, frozen, *, project_dir, db_path=None):
    """Return a copy with per-shot library_ref_id, before computing its signature.

project_dir is the resolved commentary project directory. No version signature
is embedded in a reference, avoiding a reference/signature hash cycle.
"""
    bound = deepcopy(frozen)
    project = Path(project_dir).resolve()
    prepared = [(segment, shot, _observation(project, bound, shot, db_path=db_path))
                for segment, _, shot in _shots(project_id, bound)]
    # Validate the complete batch first, so one bad/archived shot cannot leave
    # other shots looking like a successfully bound commentary version.
    for segment, shot, observation in prepared:
        saved = refs.save_observation(observation, db_path=db_path)
        reference = refs.freeze_reference({"media_id": shot["media_id"],
            "source_in": shot["start"], "source_out": shot["end"],
            "observation_id": saved["id"], "scope": saved["scope"],
            "usage_intent": f"素材解说 {project_id} / {segment['id']}：{segment['purpose']}"}, db_path=db_path)
        shot["library_ref_id"] = reference["id"]
    return bound


def record_usages(project_id, signature, frozen, *, db_path=None):
    """Record MUSE for every actual shot/version and return the ledger rows.

Existing identical ledger entries may recover archived history. A new version
or new shot requires active media even if it reuses an older MREF. The caller
persists the bound frozen request and hashes it before calling this function.
"""
    if signature != digest(frozen):
        raise CommentaryError("版本签名与冻结编排不一致，不能登记素材使用")
    previous = {(row["scene_id"], row["slot_id"]): row
                for row in refs.list_usage(project_id=project_id, db_path=db_path)
                if row["project_version"] == signature}
    prepared = []
    for segment, slot, shot in _shots(project_id, frozen):
        reference = refs.resolve_reference(shot.get("library_ref_id"), db_path=db_path)
        source = frozen["sources"][shot["media_id"]]
        if (reference["media_id"] != shot["media_id"] or reference["source_sha256"] != source["sha256"]
                or reference["source_in"] != shot["start"] or reference["source_out"] != shot["end"]
                or reference["scope"] != _scope(frozen, shot["crop"])
                or reference["review_status"] != "confirmed"):
            raise CommentaryError("冻结素材引用与镜头或审核作用域不一致")
        old = previous.get((segment["id"], slot))
        if old:
            if old["ref_id"] != reference["id"] or old["asset_id"] != shot["media_id"]:
                raise refs.MaterialReferenceConflictError("同一版本的镜头使用已冻结，不能替换")
        else:
            ensure_available(shot["media_id"], db_path=db_path)
        prepared.append({"project_id": project_id, "project_version": signature,
            "asset_id": shot["media_id"], "scene_id": segment["id"], "slot_id": slot,
            "ref_id": reference["id"]})
    return [refs.record_usage(payload, db_path=db_path) for payload in prepared]
