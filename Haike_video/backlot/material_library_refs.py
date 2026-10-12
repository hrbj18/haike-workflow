"""Versioned source facts and project references, independent of video templates.

All intervals use source seconds and are half-open: [source_in, source_out).
Observations describe facts; neither an observation nor a reference grants a
template permission to use a crop, and candidate records remain candidates.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
from urllib.parse import quote

from backlot import material_library as lib


class MaterialReferenceConflictError(lib.MaterialLibraryError):
    """An immutable identity or usage key already refers to different content."""


@contextmanager
def _connect(db_path=None):
    with lib.connect(db_path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS ml_ref_aliases (
              namespace TEXT NOT NULL, external_id TEXT NOT NULL,
              media_id TEXT NOT NULL REFERENCES media(id), created_at TEXT NOT NULL,
              PRIMARY KEY(namespace, external_id));
            CREATE INDEX IF NOT EXISTS ml_ref_aliases_media ON ml_ref_aliases(media_id);
            CREATE TABLE IF NOT EXISTS ml_ref_project_sources (
              project_id TEXT NOT NULL, project_version TEXT NOT NULL, asset_id TEXT NOT NULL,
              media_id TEXT NOT NULL REFERENCES media(id), payload TEXT NOT NULL,
              created_at TEXT NOT NULL, PRIMARY KEY(project_id,project_version,asset_id));
            CREATE TABLE IF NOT EXISTS ml_ref_observations (
              id TEXT PRIMARY KEY, media_id TEXT NOT NULL REFERENCES media(id),
              source_in REAL NOT NULL, source_out REAL NOT NULL, review_status TEXT NOT NULL,
              scope TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ml_ref_observations_media ON ml_ref_observations(media_id,source_in,source_out);
            CREATE TABLE IF NOT EXISTS ml_ref_references (
              id TEXT PRIMARY KEY, media_id TEXT NOT NULL REFERENCES media(id),
              payload TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ml_ref_usage (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL, project_version TEXT NOT NULL,
              asset_id TEXT NOT NULL, scene_id TEXT NOT NULL, slot_id TEXT NOT NULL,
              ref_id TEXT NOT NULL REFERENCES ml_ref_references(id),
              media_id TEXT NOT NULL REFERENCES media(id), created_at TEXT NOT NULL,
              source_asset_id TEXT NOT NULL DEFAULT '',
              project_asset_media_id TEXT NOT NULL DEFAULT '',
              UNIQUE(project_id,project_version,scene_id,slot_id));
            CREATE INDEX IF NOT EXISTS ml_ref_usage_media ON ml_ref_usage(media_id);
            CREATE INDEX IF NOT EXISTS ml_ref_usage_project ON ml_ref_usage(project_id,project_version);
        """)
        # Additive migration for development databases created by the initial
        # V1.1 schema; legacy media and template tables are never rewritten.
        usage_columns = {row["name"] for row in db.execute("PRAGMA table_info(ml_ref_usage)")}
        for field in ("source_asset_id", "project_asset_media_id"):
            if field not in usage_columns:
                db.execute(f"ALTER TABLE ml_ref_usage ADD COLUMN {field} TEXT NOT NULL DEFAULT ''")
        db.commit()
        yield db


def _object(value, label):
    if not isinstance(value, dict):
        raise lib.MaterialLibraryError(f"{label}必须为对象")
    return value


def _text(value, label, maximum=250, *, optional=False):
    if optional and value is None:
        return ""
    if not isinstance(value, str) or len(value) > maximum or (not optional and not value.strip()):
        raise lib.MaterialLibraryError(f"{label}须为不超过{maximum}字的有效文字")
    return value.strip()


def _sha(value, label="SHA256"):
    if not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", value):
        raise lib.MaterialLibraryError(f"{label}须为64位十六进制文件哈希")
    return value.lower()


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise lib.MaterialLibraryError("数据含有无法保存的内容或无效数字") from exc


def _interval(payload, media):
    start = lib.number(payload.get("source_in"), "源区间开始", 0, media["duration"])
    end = lib.number(payload.get("source_out"), "源区间结束", 0, media["duration"])
    if end <= start:
        raise lib.MaterialLibraryError("源区间结束必须晚于开始")
    return start, end


def _scope(value):
    value = _text(value, "审核作用域", 160)
    if value in {"*", "all", "global", "any"}:
        raise lib.MaterialLibraryError("审核作用域须为 source-content 或具体画幅适配 profile，不能全局放行")
    return value


def _verify_file(path, expected, label):
    try:
        resolved = Path(_text(path, f"{label}路径", 4000)).resolve()
        if not resolved.is_file() or lib.file_sha256(resolved) != expected:
            raise lib.MaterialLibraryError(f"{label}文件缺失或内容已变化，请重新核验")
        return str(resolved)
    except OSError as exc:
        raise lib.MaterialLibraryError(f"{label}文件无法读取，请检查路径和权限") from exc


def _media(media_id, db_path):
    media = lib.get_media(_text(media_id, "素材ID"), db_path=db_path)
    # Never resolve by size/mtime alone: a replaced file cannot inherit evidence.
    lib.resolve_media(media["id"], db_path=db_path)
    return media


def _payload_row(row):
    return {**json.loads(row["payload"]), "id": row["id"], "created_at": row["created_at"]}


def _archived(db, media_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ml_metadata'").fetchone():
        return False
    row = db.execute("SELECT archived FROM ml_metadata WHERE media_id=?", (media_id,)).fetchone()
    return bool(row and row["archived"])


def lookup_alias(namespace, external_id, *, db_path=None):
    """Resolve a stable external identity; a missing identity is an explicit error."""
    namespace, external_id = _text(namespace, "来源命名空间", 500), _text(external_id, "来源编号")
    with _connect(db_path) as db:
        row = db.execute("SELECT * FROM ml_ref_aliases WHERE namespace=? AND external_id=?",
                         (namespace, external_id)).fetchone()
    if not row:
        raise lib.MaterialLibraryError("来源身份映射不存在，请先登记素材")
    return dict(row)


def import_project(payload, *, db_path=None):
    """Atomically register a fully validated explicit manifest and identity aliases."""
    payload = _object(payload, "项目导入清单")
    project_id = _text(payload.get("project_id"), "项目编号", 160)
    version = _text(payload.get("project_version"), "项目版本", 160)
    sources = payload.get("sources")
    if not isinstance(sources, list) or not 1 <= len(sources) <= 200:
        raise lib.MaterialLibraryError("每批项目导入须含1—200份显式来源")
    prepared, seen_assets, alias_targets = [], set(), {}
    for raw in sources:
        raw = _object(raw, "项目来源")
        asset_id = _text(raw.get("asset_id"), "项目素材编号")
        if asset_id in seen_assets:
            raise lib.MaterialLibraryError("同批项目素材编号不能重复")
        seen_assets.add(asset_id)
        expected = _sha(raw.get("expected_sha256"), "预期源 SHA256")
        metadata = _object(raw.get("metadata", {}), "来源元数据")
        _json(metadata)
        path = _verify_file(raw.get("path"), expected, "原片")
        item = lib.prepare_media(path, metadata, db_path=db_path)
        if item["sha256"] != expected:
            raise lib.MaterialLibraryError("登记时原片内容已变化，请重试")
        aliases = raw.get("aliases", [])
        if not isinstance(aliases, list) or len(aliases) > 50:
            raise lib.MaterialLibraryError("每份来源最多登记50个外部身份")
        aliases = [{"namespace": f"project:{quote(project_id, safe='')}:{quote(version, safe='')}", "external_id": asset_id}, *aliases]
        normalized = []
        for alias in aliases:
            alias = _object(alias, "来源身份")
            namespace = _text(alias.get("namespace"), "来源命名空间", 500)
            external_id = _text(alias.get("external_id"), "来源编号")
            key = (namespace, external_id)
            if key in alias_targets and alias_targets[key] != item["id"]:
                raise MaterialReferenceConflictError("同批来源身份指向不同原片，不能覆盖")
            alias_targets[key] = item["id"]
            value = {"namespace": namespace, "external_id": external_id, "media_id": item["id"]}
            if value not in normalized:
                normalized.append(value)
        prepared.append((item, asset_id, metadata, normalized))
    with _connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        # Check every identity before inserting media, locations, or provenance.
        for (namespace, external_id), media_id in alias_targets.items():
            row = db.execute("SELECT media_id FROM ml_ref_aliases WHERE namespace=? AND external_id=?",
                             (namespace, external_id)).fetchone()
            if row and row["media_id"] != media_id:
                raise MaterialReferenceConflictError("来源身份已绑定另一份原片，请使用新版本或新编号")
        for item, asset_id, metadata, aliases in prepared:
            row = db.execute("SELECT media_id FROM ml_ref_project_sources WHERE project_id=? AND project_version=? AND asset_id=?",
                             (project_id, version, asset_id)).fetchone()
            if row and row["media_id"] != item["id"]:
                raise MaterialReferenceConflictError("该项目版本的素材映射已冻结，不能替换原片")
            usage_conflict = db.execute(
                "SELECT 1 FROM ml_ref_usage WHERE project_id=? AND project_version=? AND "
                "((asset_id=? AND project_asset_media_id<>'' AND project_asset_media_id<>?) "
                "OR (source_asset_id=? AND media_id<>?)) LIMIT 1",
                (project_id, version, asset_id, item["id"], asset_id, item["id"])).fetchone()
            if usage_conflict:
                raise MaterialReferenceConflictError("该项目素材已有不同内容的冻结使用记录，不能重新绑定来源")
            path = Path(_verify_file(item["path"], item["sha256"], "原片"))
            stat = path.stat()
            # Same insert contract as material_library.register_prepared, within
            # this transaction so alias failures cannot leave partial imports.
            db.execute("INSERT OR IGNORE INTO media VALUES(?,?,?,?,?,?,?,?)",
                       (item["id"], item["sha256"], item["title"], item["bytes"], item["duration"],
                        item["width"], item["height"], lib.now()))
            db.execute("INSERT INTO locations VALUES(?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
                       "media_id=excluded.media_id,bytes=excluded.bytes,mtime_ns=excluded.mtime_ns,updated_at=excluded.updated_at",
                       (item["path"], item["id"], stat.st_size, stat.st_mtime_ns, lib.now()))
            origin = {**item["origin"], "media_id": item["id"], "title": item["title"]}
            db.execute("INSERT OR IGNORE INTO origins VALUES(?,?,?,?,?,?,?,?,?)",
                       (lib.digest(origin), item["id"], origin["platform"], origin["source_url"], origin["video_id"],
                        item["title"], origin["rights_status"] or "unknown", origin["catalog"], lib.now()))
            db.execute("DELETE FROM failures WHERE path=?", (item["path"],))
            db.execute("INSERT OR IGNORE INTO ml_ref_project_sources VALUES(?,?,?,?,?,?)",
                       (project_id, version, asset_id, item["id"], _json({"metadata": metadata, "source_sha256": item["sha256"]}), lib.now()))
        for (namespace, external_id), media_id in alias_targets.items():
            db.execute("INSERT OR IGNORE INTO ml_ref_aliases VALUES(?,?,?,?)",
                       (namespace, external_id, media_id, lib.now()))
    return {"schema_version": 1, "project_id": project_id, "project_version": version,
            "media_ids": list(dict.fromkeys(item["id"] for item, *_ in prepared)),
            "sources": [{"asset_id": asset, "media_id": item["id"], "source_sha256": item["sha256"], "aliases": aliases}
                        for item, asset, _, aliases in prepared]}


def save_observation(payload, *, db_path=None):
    """Save an immutable fact version; confirmation requires explicit evidence."""
    payload = _object(payload, "素材观察")
    if "usable" in payload or "usable" in _object(payload.get("facts", {}), "观察事实"):
        raise lib.MaterialLibraryError("通用观察不能使用全局 usable 标记，请记录事实及明确的审核作用域")
    media = _media(payload.get("media_id"), db_path)
    start, end = _interval(payload, media)
    facts = payload.get("facts", {})
    normalized_facts = {}
    for key, value in facts.items():
        if key not in {"text", "source_audio", "subtitles"}:
            raise lib.MaterialLibraryError("观察事实仅支持 text、source_audio、subtitles")
        if isinstance(value, bool) and key != "text":
            normalized_facts[key] = value
        elif isinstance(value, list):
            if len(value) > 100:
                raise lib.MaterialLibraryError("每种观察事实最多100条")
            normalized_facts[key] = [_text(v, "观察事实", 10000) for v in value]
        else:
            normalized_facts[key] = _text(value, "观察事实", 20000, optional=True)
    observation = _text(payload.get("observation", ""), "观察描述", 20000, optional=True)
    if not observation and not normalized_facts:
        raise lib.MaterialLibraryError("请提供观察描述或原片事实")
    status = payload.get("review_status", "candidate")
    if not isinstance(status, str) or status not in {"candidate", "confirmed"}:
        raise lib.MaterialLibraryError("观察状态必须为 candidate 或 confirmed")
    reviewer = _text(payload.get("reviewer", ""), "审核者", 200, optional=True)
    evidence = payload.get("evidence", [])
    if not isinstance(evidence, list) or len(evidence) > 100:
        raise lib.MaterialLibraryError("证据须为不超过100项的文件列表")
    normalized_evidence = []
    for item in evidence:
        item = _object(item, "观察证据")
        sha = _sha(item.get("sha256"), "证据 SHA256")
        normalized_evidence.append({"path": _verify_file(item.get("path"), sha, "证据"), "sha256": sha})
    if status == "confirmed" and (not reviewer or not normalized_evidence):
        raise lib.MaterialLibraryError("确认观察必须填写审核者并提供经哈希核验的本地证据")
    saved = {"schema_version": 1, "media_id": media["id"], "source_sha256": media["sha256"],
             "source_in": start, "source_out": end, "scope": _scope(payload.get("scope", "source-content")),
             "observation": observation, "facts": normalized_facts, "review_status": status,
             "reviewer": reviewer, "evidence": normalized_evidence}
    observation_id = "MOBS-" + lib.digest(saved)
    with _connect(db_path) as db:
        db.execute("INSERT OR IGNORE INTO ml_ref_observations VALUES(?,?,?,?,?,?,?,?)",
                   (observation_id, media["id"], start, end, status, saved["scope"], _json(saved), lib.now()))
        return _payload_row(db.execute("SELECT * FROM ml_ref_observations WHERE id=?", (observation_id,)).fetchone())


def list_observations(media_id, *, db_path=None):
    media_id = _text(media_id, "素材ID")
    with _connect(db_path) as db:
        return [_payload_row(row) for row in db.execute(
            "SELECT * FROM ml_ref_observations WHERE media_id=? ORDER BY source_in,source_out,created_at,id", (media_id,))]


def _get_observation(observation_id, db_path):
    with _connect(db_path) as db:
        row = db.execute("SELECT * FROM ml_ref_observations WHERE id=?", (observation_id,)).fetchone()
    if not row:
        raise lib.MaterialLibraryError("观察版本不存在")
    observation = _payload_row(row)
    identity = {k: v for k, v in observation.items() if k not in {"id", "created_at"}}
    if "MOBS-" + lib.digest(identity) != observation_id:
        raise lib.MaterialLibraryError("观察版本内容已变化，请重新核验")
    for item in observation["evidence"]:
        _verify_file(item["path"], item["sha256"], "证据")
    return observation


def freeze_reference(payload, *, db_path=None):
    """Freeze a freely sized source interval and the evidence's original scope."""
    payload = _object(payload, "素材引用")
    media = _media(payload.get("media_id"), db_path)
    start, end = _interval(payload, media)
    intent = _text(payload.get("usage_intent"), "使用目的", 1000)
    scope = _scope(payload.get("scope", "source-content"))
    observation_id = _text(payload.get("observation_id", ""), "观察编号", optional=True)
    legacy_id = _text(payload.get("legacy_clip_id", ""), "旧片段编号", optional=True)
    if observation_id and legacy_id:
        raise lib.MaterialLibraryError("单条引用只能冻结一份观察版本或一份旧片段证据")
    snapshot = None
    if observation_id:
        snapshot = _get_observation(observation_id, db_path)
        if snapshot["media_id"] != media["id"] or snapshot["source_sha256"] != media["sha256"]:
            raise lib.MaterialLibraryError("观察与引用的原片不一致")
        if snapshot["scope"] != scope:
            raise lib.MaterialLibraryError("引用与观察的审核作用域不一致，不能跨画幅放行")
        if start < snapshot["source_in"] or end > snapshot["source_out"]:
            raise lib.MaterialLibraryError("引用区间超出观察证据覆盖范围")
    elif legacy_id:
        with _connect(db_path) as db:
            row = db.execute("SELECT * FROM clips WHERE id=?", (legacy_id,)).fetchone()
        if not row or row["media_id"] != media["id"]:
            raise lib.MaterialLibraryError("旧片段不存在或与引用的原片不一致")
        if scope != "template-band-v1":
            raise lib.MaterialLibraryError("旧中央带片段仅适用于 template-band-v1，不能升级为全屏确认")
        if start < row["start"] or end > row["end"]:
            raise lib.MaterialLibraryError("引用区间超出旧片段证据覆盖范围")
        snapshot = {"kind": "legacy-clip", **lib.clip_row(row), "scope": "template-band-v1"}
        if row["review_status"] == "confirmed":
            from backlot import material_library_evidence as evidence
            task = evidence.read_task(row["task_id"], db_path=db_path)
            evidence.check_task(task, db_path=db_path)
            if not task["completed"] or task["identity"].get("profile") != "template-band-v1":
                raise lib.MaterialLibraryError("旧片段缺少完整的中央带审核证据")
            windows = [w for w in task["windows"] if w["media_id"] == media["id"]
                       and w["start"] == row["start"] and w["end"] == row["end"]]
            if not windows or any(w["source_sha256"] != media["sha256"] for w in windows):
                raise lib.MaterialLibraryError("旧片段与原始证据窗口不一致")
            snapshot["evidence"] = [{"path": str((evidence.task_directory(task["id"], db_path) / s["file"]).resolve()),
                                     "sha256": s["sha256"]} for w in windows for s in w["sheets"]]
    saved = {"schema_version": 1, "media_id": media["id"], "source_sha256": media["sha256"],
             "source_in": start, "source_out": end, "usage_intent": intent, "scope": scope,
             "observation_id": observation_id or None, "legacy_clip_id": legacy_id or None,
             "review_status": snapshot["review_status"] if snapshot else "unreviewed",
             "evidence_snapshot": snapshot}
    ref_id = "MREF-" + lib.digest(saved)
    with _connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT * FROM ml_ref_references WHERE id=?", (ref_id,)).fetchone()
        if existing:
            return _payload_row(existing)
        if _archived(db, media["id"]):
            raise lib.MaterialLibraryError("素材已归档，不能建立新引用；已有引用仍可解析")
        db.execute("INSERT INTO ml_ref_references VALUES(?,?,?,?)", (ref_id, media["id"], _json(saved), lib.now()))
        return _payload_row(db.execute("SELECT * FROM ml_ref_references WHERE id=?", (ref_id,)).fetchone())


def get_reference(ref_id, *, db_path=None):
    ref_id = _text(ref_id, "引用编号")
    with _connect(db_path) as db:
        row = db.execute("SELECT * FROM ml_ref_references WHERE id=?", (ref_id,)).fetchone()
    if not row:
        raise lib.MaterialLibraryError("素材引用不存在")
    return _validated_reference(row)


def _validated_reference(row):
    result = _payload_row(row)
    identity = {k: v for k, v in result.items() if k not in {"id", "created_at"}}
    if "MREF-" + lib.digest(identity) != row["id"]:
        raise lib.MaterialLibraryError("冻结引用内容已变化，请检查素材库完整性")
    return result


def resolve_reference(ref_id, *, db_path=None):
    """Resolve an existing snapshot; archive status never invalidates history."""
    result = get_reference(ref_id, db_path=db_path)
    media = lib.get_media(result["media_id"], db_path=db_path)
    if media["sha256"] != result["source_sha256"]:
        raise lib.MaterialLibraryError("冻结引用与当前原片哈希不一致")
    _interval(result, media)
    path = lib.resolve_media(media["id"], db_path=db_path)
    for evidence in (result["evidence_snapshot"] or {}).get("evidence", []):
        _verify_file(evidence["path"], evidence["sha256"], "冻结证据")
    return {**result, "path": str(path)}


def record_usage(payload, *, db_path=None):
    payload = _object(payload, "素材使用记录")
    values = {key: _text(payload.get(key), label) for key, label in (
        ("project_id", "项目编号"), ("project_version", "项目版本"), ("asset_id", "项目素材编号"),
        ("scene_id", "场景编号"), ("slot_id", "镜头位置"), ("ref_id", "引用编号"))}
    reference = resolve_reference(values["ref_id"], db_path=db_path)
    source_asset_id = _text(payload.get("source_asset_id", ""), "原片素材编号", optional=True)
    identity = {key: values[key] for key in ("project_id", "project_version", "scene_id", "slot_id")}
    usage_id = "MUSE-" + lib.digest(identity)
    with _connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        mapping = db.execute("SELECT media_id FROM ml_ref_project_sources WHERE project_id=? AND project_version=? AND asset_id=?",
                             (values["project_id"], values["project_version"], values["asset_id"])).fetchone()
        if source_asset_id:
            source_mapping = db.execute("SELECT media_id FROM ml_ref_project_sources WHERE project_id=? AND project_version=? AND asset_id=?",
                                        (values["project_id"], values["project_version"], source_asset_id)).fetchone()
            if not mapping or not source_mapping:
                raise lib.MaterialLibraryError("使用原片素材编号时，项目资产与原片资产均须先登记到该项目版本")
            if source_mapping["media_id"] != reference["media_id"]:
                raise MaterialReferenceConflictError("引用原片与原片素材编号的登记映射不一致")
        elif mapping and mapping["media_id"] != reference["media_id"]:
            raise MaterialReferenceConflictError("引用原片与该项目素材的登记映射不一致")
        project_asset_media_id = mapping["media_id"] if mapping else reference["media_id"]
        previous = db.execute("SELECT * FROM ml_ref_usage WHERE id=?", (usage_id,)).fetchone()
        if previous and (previous["asset_id"] != values["asset_id"] or previous["ref_id"] != values["ref_id"]
                         or previous["source_asset_id"] != source_asset_id
                         or (previous["project_asset_media_id"] and previous["project_asset_media_id"] != project_asset_media_id)):
            raise MaterialReferenceConflictError("同一项目版本的镜头使用已冻结，请建立新版本后替换")
        db.execute("INSERT OR IGNORE INTO ml_ref_usage VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (usage_id, values["project_id"], values["project_version"], values["asset_id"],
                    values["scene_id"], values["slot_id"], values["ref_id"], reference["media_id"], lib.now(),
                    source_asset_id, project_asset_media_id))
        result = dict(db.execute("SELECT * FROM ml_ref_usage WHERE id=?", (usage_id,)).fetchone())
    return {**result, "reference": get_reference(values["ref_id"], db_path=db_path)}


def list_usage(media_id="", project_id="", *, db_path=None):
    clauses, params = [], []
    for key, value in (("media_id", media_id), ("project_id", project_id)):
        if value:
            value = _text(value, "查询编号")
            clauses.append("(u.media_id=? OR u.project_asset_media_id=?)" if key == "media_id" else "u.project_id=?")
            params.extend([value, value] if key == "media_id" else [value])
    with _connect(db_path) as db:
        rows = db.execute("SELECT u.*,r.payload AS reference_payload,r.created_at AS reference_created_at "
                          "FROM ml_ref_usage u JOIN ml_ref_references r ON u.ref_id=r.id"
                          + (" WHERE " + " AND ".join(clauses) if clauses else "")
                          + " ORDER BY u.project_id,u.project_version,u.scene_id,u.slot_id,u.asset_id,u.id", params).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            reference = _validated_reference({"id": row["ref_id"], "payload": item.pop("reference_payload"),
                                              "created_at": item.pop("reference_created_at")})
            result.append({**item, "reference": reference})
    return result
