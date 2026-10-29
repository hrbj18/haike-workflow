"""Additive asset management; management labels never constitute visual review.

Health results are cached, explicitly dated observations. Search never hashes files;
``check_health`` and ``relink`` are the explicit full-content verification boundary.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path

from backlot import material_library as lib


class MaterialConflictError(ValueError):
    """An edit lost its revision race; callers should return HTTP 409."""


@contextmanager
def connect(db_path=None):
    with lib.connect(db_path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS ml_metadata (
              media_id TEXT PRIMARY KEY REFERENCES media(id),
              tags TEXT NOT NULL DEFAULT '[]',collections TEXT NOT NULL DEFAULT '[]',
              notes TEXT NOT NULL DEFAULT '',archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
              revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0),updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ml_location_health (
              path TEXT PRIMARY KEY,media_id TEXT NOT NULL REFERENCES media(id),
              status TEXT NOT NULL CHECK(status IN ('valid','missing','changed','error')),
              checked_at TEXT NOT NULL,reason TEXT NOT NULL,observed_sha256 TEXT,
              bytes INTEGER,mtime_ns INTEGER);
            CREATE INDEX IF NOT EXISTS ml_location_health_media ON ml_location_health(media_id);
        """)
        yield db


def _media(db, media_id):
    if not isinstance(media_id, str) or not media_id:
        raise lib.MaterialLibraryError("素材ID无效")
    row = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    if row is None:
        raise lib.MaterialLibraryError("素材ID不存在")
    return dict(row)


def _metadata(db, media_id):
    row = db.execute("SELECT * FROM ml_metadata WHERE media_id=?", (media_id,)).fetchone()
    if row is None:
        return {"media_id": media_id, "tags": [], "collections": [], "notes": "",
                "archived": False, "revision": 0, "updated_at": None}
    item = dict(row)
    item.update(tags=json.loads(item["tags"]), collections=json.loads(item["collections"]),
                archived=bool(item["archived"]))
    return item


def get_metadata(media_id, *, db_path=None):
    with connect(db_path) as db:
        _media(db, media_id)
        return _metadata(db, media_id)


def _integer(value, label, minimum, maximum):
    number = lib.number(value, label, minimum, maximum)
    if number != int(number):
        raise lib.MaterialLibraryError(f"{label}必须为整数")
    return int(number)


def update_metadata(payload, *, db_path=None):
    """Replace supplied fields on up to 200 assets, atomically and with CAS."""
    if not isinstance(payload, dict):
        raise lib.MaterialLibraryError("管理更新必须为对象")
    items, patch = payload.get("items"), payload.get("patch")
    if not isinstance(items, list) or not 1 <= len(items) <= 200:
        raise lib.MaterialLibraryError("每批请选择1至200份素材")
    if not isinstance(patch, dict) or not patch or set(patch) - {"tags", "collections", "notes", "archived"}:
        raise lib.MaterialLibraryError("更新字段仅支持标签、集合、备注和归档，且不能为空")
    changes = dict(patch)
    for field in ("tags", "collections"):
        if field in changes:
            changes[field] = lib.words(changes[field], "标签" if field == "tags" else "集合", limit=64)
    if "notes" in changes and (not isinstance(changes["notes"], str) or len(changes["notes"]) > 4000):
        raise lib.MaterialLibraryError("备注必须为不超过4000字的文字")
    if "archived" in changes and not isinstance(changes["archived"], bool):
        raise lib.MaterialLibraryError("归档状态必须为布尔值")
    normalized, seen = [], set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("media_id"), str) or not item["media_id"]:
            raise lib.MaterialLibraryError("待更新素材ID无效")
        if item["media_id"] in seen:
            raise lib.MaterialLibraryError("同一批次不能重复提交同一素材")
        seen.add(item["media_id"])
        normalized.append((item["media_id"], _integer(item.get("expected_revision"), "版本号", 0, 2147483647)))
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        current = []
        for media_id, revision in normalized:
            _media(db, media_id)
            meta = _metadata(db, media_id)
            if meta["revision"] != revision:
                raise MaterialConflictError("素材已被其他操作更新，请刷新后重试；本批修改均未保存")
            current.append(meta)
        for meta in current:
            meta.update(changes)
            meta["revision"] += 1
            meta["updated_at"] = lib.now()
            db.execute("INSERT INTO ml_metadata VALUES(?,?,?,?,?,?,?) ON CONFLICT(media_id) DO UPDATE SET "
                       "tags=excluded.tags,collections=excluded.collections,notes=excluded.notes,"
                       "archived=excluded.archived,revision=excluded.revision,updated_at=excluded.updated_at",
                       (meta["media_id"], json.dumps(meta["tags"], ensure_ascii=False),
                        json.dumps(meta["collections"], ensure_ascii=False), meta["notes"],
                        int(meta["archived"]), meta["revision"], meta["updated_at"]))
        return {"items": current, "updated": len(current)}


def _observation_sql(db):
    # The optional refs module owns this additive table. Neither module must be
    # initialized first; UNION ALL preserves independently reviewed versions.
    sql = "SELECT media_id,start,end,review_status,observation AS text,metadata AS payload FROM clips"
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ml_ref_observations'").fetchone():
        sql += (" UNION ALL SELECT media_id,source_in,source_out,review_status,"
                "COALESCE(json_extract(payload,'$.observation'),''),payload FROM ml_ref_observations")
    return sql


def _counts(db, media_id=None):
    obs = _observation_sql(db)
    where, params = (" WHERE media_id=?", (media_id,)) if media_id else ("", ())
    versions = db.execute(f"SELECT COUNT(*),SUM(review_status='confirmed'),SUM(review_status='candidate') "
                          f"FROM ({obs}){where}", params).fetchone()
    intervals = db.execute(f"SELECT COUNT(*) FROM (SELECT media_id,start,end FROM ({obs}){where} "
                           "GROUP BY media_id,start,end)", params).fetchone()[0]
    return {"intervals": intervals, "review_versions": versions[0],
            "confirmed_versions": versions[1] or 0, "candidate_versions": versions[2] or 0,
            "locations": db.execute("SELECT COUNT(*) FROM locations" + where, params).fetchone()[0]}


def _summary(db):
    count = db.execute("SELECT COUNT(*) FROM media").fetchone()[0]
    archived = db.execute("SELECT COUNT(*) FROM ml_metadata WHERE archived=1").fetchone()[0]
    return {"schema_version": 1, "media": count, "active": count - archived,
            "archived": archived, **_counts(db)}


def summary(*, db_path=None):
    """Global counts include archived assets and both evidence generations."""
    with connect(db_path) as db:
        return _summary(db)


_HEALTH_SQL = """CASE
 WHEN EXISTS(SELECT 1 FROM locations l JOIN ml_location_health h ON h.path=l.path AND h.media_id=l.media_id
             WHERE l.media_id=m.id AND h.status='valid') THEN 'valid'
 WHEN NOT EXISTS(SELECT 1 FROM locations l WHERE l.media_id=m.id)
   OR EXISTS(SELECT 1 FROM locations l LEFT JOIN ml_location_health h ON h.path=l.path AND h.media_id=l.media_id
             WHERE l.media_id=m.id AND h.path IS NULL) THEN 'unchecked'
 WHEN EXISTS(SELECT 1 FROM locations l JOIN ml_location_health h ON h.path=l.path AND h.media_id=l.media_id
             WHERE l.media_id=m.id AND h.status='changed') THEN 'changed'
 WHEN EXISTS(SELECT 1 FROM locations l JOIN ml_location_health h ON h.path=l.path AND h.media_id=l.media_id
             WHERE l.media_id=m.id AND h.status='error') THEN 'error'
 ELSE 'missing' END"""


def _health(db, media_id):
    rows = [dict(row) for row in db.execute(
        "SELECT l.path,COALESCE(h.status,'unchecked') status,h.checked_at,"
        "COALESCE(h.reason,'尚未检查') reason,h.observed_sha256,h.bytes,h.mtime_ns "
        "FROM locations l LEFT JOIN ml_location_health h ON h.path=l.path AND h.media_id=l.media_id "
        "WHERE l.media_id=? ORDER BY l.path", (media_id,))]
    status = db.execute(f"SELECT {_HEALTH_SQL} FROM media m WHERE m.id=?", (media_id,)).fetchone()[0]
    dates = [row["checked_at"] for row in rows if row["checked_at"]]
    return {"status": status, "checked_at": max(dates) if dates else None, "locations": rows}


def _enrich(db, item):
    return {**item, "metadata": _metadata(db, item["id"]), "counts": _counts(db, item["id"]),
            "health": _health(db, item["id"]), "platforms": [row[0] for row in db.execute(
                "SELECT DISTINCT platform FROM origins WHERE media_id=? AND platform!='' ORDER BY platform",
                (item["id"],))]}


def detail(media_id, *, db_path=None):
    item = lib.get_media(media_id, db_path=db_path)
    with connect(db_path) as db:
        return _enrich(db, item)


def _text(value, label, limit=200):
    if not isinstance(value, str) or len(value) > limit:
        raise lib.MaterialLibraryError(f"{label}必须为不超过{limit}字的文字")
    return value.strip()


def search(payload=None, *, db_path=None):
    """Search cached facts; pagination is stable by created_at DESC, id ASC."""
    payload = {} if payload is None else payload
    if not isinstance(payload, dict):
        raise lib.MaterialLibraryError("检索条件必须为对象")
    query = _text(payload.get("query", ""), "关键词")
    exact = {field: _text(payload.get(field, ""), "筛选值", 160) for field in ("tag", "collection", "platform")}
    enums = {"aspect": {"all", "portrait", "landscape", "square"},
             "review_status": {"all", "candidate", "confirmed", "unreviewed"},
             "health": {"all", "valid", "missing", "changed", "error", "unchecked"},
             "archived": {"active", "archived", "all"}}
    options = {}
    for key, allowed in enums.items():
        options[key] = payload.get(key, "active" if key == "archived" else "all")
        if not isinstance(options[key], str) or options[key] not in allowed:
            raise lib.MaterialLibraryError(f"筛选条件 {key} 无效")
    page = _integer(payload.get("page", 1), "页码", 1, 1000000)
    page_size = _integer(payload.get("page_size", 30), "每页数量", 1, 100)
    bounds = {field: lib.number(payload[field], "时长", 0, 864000) for field in ("min_duration", "max_duration")
              if payload.get(field) is not None and payload[field] != ""}
    if bounds.get("min_duration", 0) > bounds.get("max_duration", 864000):
        raise lib.MaterialLibraryError("最小时长不能大于最大时长")
    with connect(db_path) as db:
        observations = _observation_sql(db)
        clauses, args = [], []
        if options["archived"] != "all":
            clauses.append("COALESCE(md.archived,0)=?")
            args.append(int(options["archived"] == "archived"))
        for key, column in (("tag", "tags"), ("collection", "collections")):
            if exact[key]:
                clauses.append(f"EXISTS(SELECT 1 FROM json_each(COALESCE(md.{column},'[]')) WHERE value=?)")
                args.append(exact[key])
        if exact["platform"]:
            clauses.append("EXISTS(SELECT 1 FROM origins o WHERE o.media_id=m.id AND o.platform=?)")
            args.append(exact["platform"])
        if options["aspect"] != "all":
            operator = {"portrait": "<", "landscape": ">", "square": "="}[options["aspect"]]
            clauses.append(f"m.width {operator} m.height")
        for key, operator in (("min_duration", ">="), ("max_duration", "<=")):
            if key in bounds:
                clauses.append(f"m.duration {operator} ?")
                args.append(bounds[key])
        if options["review_status"] == "unreviewed":
            clauses.append(f"NOT EXISTS(SELECT 1 FROM ({observations}) ob WHERE ob.media_id=m.id)")
        elif options["review_status"] != "all":
            clauses.append(f"EXISTS(SELECT 1 FROM ({observations}) ob WHERE ob.media_id=m.id AND ob.review_status=?)")
            args.append(options["review_status"])
        if options["health"] != "all":
            clauses.append(f"({_HEALTH_SQL})=?")
            args.append(options["health"])
        if query:
            like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            clauses.append("(m.title LIKE ? ESCAPE '\\' OR m.id LIKE ? ESCAPE '\\' "
                           "OR EXISTS(SELECT 1 FROM origins o WHERE o.media_id=m.id AND "
                           "(o.title || ' ' || o.platform || ' ' || o.source_url || ' ' || o.video_id) LIKE ? ESCAPE '\\') "
                           "OR (COALESCE(md.notes,'') || ' ' || COALESCE(md.tags,'') || ' ' || COALESCE(md.collections,'')) "
                           "LIKE ? ESCAPE '\\' "
                           f"OR EXISTS(SELECT 1 FROM ({observations}) ob WHERE ob.media_id=m.id AND "
                           "(ob.text || ' ' || ob.payload) LIKE ? ESCAPE '\\'))")
            args.extend([like] * 5)
        source = "FROM media m LEFT JOIN ml_metadata md ON md.media_id=m.id"
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        total = db.execute(f"SELECT COUNT(*) {source}{where}", args).fetchone()[0]
        rows = db.execute(f"SELECT m.* {source}{where} ORDER BY m.created_at DESC,m.id ASC LIMIT ? OFFSET ?",
                          [*args, page_size, (page - 1) * page_size]).fetchall()
        return {"items": [_enrich(db, dict(row)) for row in rows], "total": total,
                "page": page, "page_size": page_size, "summary": _summary(db)}


def _inspect(path, media):
    result = {"path": str(path), "status": "error", "checked_at": lib.now(), "reason": "",
              "observed_sha256": None, "bytes": None, "mtime_ns": None}
    try:
        before = path.stat()
        if not path.is_file():
            result.update(status="missing", reason="登记路径已不是文件，请重新定位")
            return result
        result.update(bytes=before.st_size, mtime_ns=before.st_mtime_ns)
        sha = lib.file_sha256(path)
        after = path.stat()
        result["observed_sha256"] = sha
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            result.update(status="error", reason="检查期间文件正在变化，请稍后重试")
        elif sha != media["sha256"] or before.st_size != media["bytes"]:
            result.update(status="changed", reason="完整内容校验不一致，旧证据不可沿用")
        else:
            result.update(status="valid", reason="完整SHA256校验通过")
    except FileNotFoundError:
        result.update(status="missing", reason="文件不存在，请重新定位")
    except OSError:
        result.update(status="error", reason="无法读取文件，请检查权限或存储连接")
    return result


def _save_health(db, media_id, results):
    for item in results:
        db.execute("INSERT INTO ml_location_health VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
                   "media_id=excluded.media_id,status=excluded.status,checked_at=excluded.checked_at,"
                   "reason=excluded.reason,observed_sha256=excluded.observed_sha256,bytes=excluded.bytes,mtime_ns=excluded.mtime_ns",
                   (item["path"], media_id, item["status"], item["checked_at"], item["reason"],
                    item["observed_sha256"], item["bytes"], item["mtime_ns"]))


def check_health(media_id, *, db_path=None):
    with connect(db_path) as db:
        media = _media(db, media_id)
        paths = [Path(row[0]) for row in db.execute("SELECT path FROM locations WHERE media_id=? ORDER BY path", (media_id,))]
    results = [_inspect(path, media) for path in paths]
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        # A concurrent legacy re-registration may assign a path to a different
        # hash. Keep that path's new asset state, never overwrite it with this run.
        results = [item for item in results if db.execute(
            "SELECT 1 FROM locations WHERE path=? AND media_id=?", (item["path"], media_id)).fetchone()]
        _save_health(db, media_id, results)
        return {"media_id": media_id, **_health(db, media_id)}


def relink(media_id, path, *, db_path=None):
    """Add a content-identical location; retain old paths and all evidence."""
    if not isinstance(path, (str, Path)) or not str(path).strip():
        raise lib.MaterialLibraryError("请选择有效的素材文件路径")
    path = Path(path).resolve()
    with connect(db_path) as db:
        media = _media(db, media_id)
    inspected = _inspect(path, media)
    if inspected["status"] != "valid":
        raise lib.MaterialLibraryError("重新定位失败：" + inspected["reason"])
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT media_id FROM locations WHERE path=?", (str(path),)).fetchone()
        if existing and existing[0] != media_id:
            raise MaterialConflictError("该路径已登记为另一份素材，请先检查原登记；未替换素材位置")
        # Avoid recording an already stale verification after waiting for a lock.
        try:
            stat = path.stat()
        except OSError as exc:
            raise lib.MaterialLibraryError("重新定位时文件不可读，请重试") from exc
        if (stat.st_size, stat.st_mtime_ns) != (inspected["bytes"], inspected["mtime_ns"]):
            raise lib.MaterialLibraryError("重新定位期间文件正在变化，请稍后重试")
        db.execute("INSERT INTO locations VALUES(?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
                   "bytes=excluded.bytes,mtime_ns=excluded.mtime_ns,updated_at=excluded.updated_at",
                   (str(path), media_id, stat.st_size, stat.st_mtime_ns, lib.now()))
        _save_health(db, media_id, [inspected])
        db.execute("DELETE FROM failures WHERE path=?", (str(path),))
        return {"media_id": media_id, "path": str(path), "health": _health(db, media_id)}
