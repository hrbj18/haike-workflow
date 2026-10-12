from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
import shutil

import pytest

from backlot import material_library as lib
from backlot import material_library_refs as refs


@pytest.fixture
def registry(tmp_path, monkeypatch):
    # Media decode is already covered by test_material_library. These fixtures
    # exercise real file hashes, SQLite transactions, source moves and conflicts.
    monkeypatch.setattr(lib, "probe", lambda path: {"duration": 180.0, "width": 1920, "height": 1080})
    source = tmp_path / "source.mp4"
    source.write_bytes(b"test source bytes for immutable content identity")
    db = tmp_path / "library.sqlite3"
    return db, source


def project(source, **overrides):
    result = {"project_id": "test-project", "project_version": "v1", "sources": [{
        "asset_id": "S-001", "path": str(source), "expected_sha256": lib.file_sha256(source),
        "metadata": {"title": "现场原片", "platform": "local"},
        "aliases": [{"namespace": "published", "external_id": "VID-1"}]}]}
    result.update(overrides)
    return result


def register(registry):
    db, source = registry
    return refs.import_project(project(source), db_path=db)["media_ids"][0]


def observation(mid, **overrides):
    result = {"media_id": mid, "source_in": 5, "source_out": 90,
              "observation": "人物与机器狗互动，原片保留现场对话。",
              "facts": {"text": ["现场标牌"], "source_audio": "现场对话", "subtitles": True}}
    result.update(overrides)
    return result


def reference(mid, **overrides):
    result = {"media_id": mid, "source_in": 5, "source_out": 80, "usage_intent": "现场解说穿插原声"}
    result.update(overrides)
    return result


def usage(ref_id, **overrides):
    result = {"project_id": "test-project", "project_version": "v1", "asset_id": "S-001",
              "scene_id": "scene-1", "slot_id": "shot-1", "ref_id": ref_id}
    result.update(overrides)
    return result


def test_project_import_deduplicates_paths_aliases_and_existing_registry(registry, tmp_path):
    db, source = registry
    original = lib.register_file(source, {"platform": "file"}, db_path=db)["media_ids"][0]
    first = refs.import_project(project(source), db_path=db)
    assert first == refs.import_project(project(source), db_path=db)
    assert first["media_ids"] == [original]
    assert refs.lookup_alias("published", "VID-1", db_path=db)["media_id"] == original
    assert refs.lookup_alias("project:test-project:v1", "S-001", db_path=db)["media_id"] == original
    alternate = tmp_path / "copy.mp4"
    shutil.copyfile(source, alternate)
    second = project(alternate, project_id="another-project")
    assert refs.import_project(second, db_path=db)["media_ids"] == [original]
    record = lib.get_media(original, db_path=db)
    assert len(record["locations"]) == 2
    assert len(record["origins"]) == 2
    with lib.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ml_ref_project_sources").fetchone()[0] == 2
        assert conn.execute("SELECT value FROM library_meta WHERE key='version'").fetchone()[0] == "1"


def test_whole_import_prevalidation_leaves_no_partial_sources(registry, tmp_path):
    db, source = registry
    manifest = project(source)
    manifest["sources"].append({**manifest["sources"][0], "asset_id": "S-002", "path": str(tmp_path / "missing.mp4")})
    with pytest.raises(ValueError, match="缺失"):
        refs.import_project(manifest, db_path=db)
    assert lib.summary(db_path=db)["media"] == 0


def test_alias_conflict_rolls_back_all_new_media_and_paths(registry, tmp_path):
    db, source = registry
    mid = register(registry)
    different = tmp_path / "different.mp4"
    different.write_bytes(b"different source bytes")
    with pytest.raises(refs.MaterialReferenceConflictError, match="另一份"):
        refs.import_project(project(different, project_version="v2"), db_path=db)
    assert lib.summary(db_path=db)["media"] == 1
    assert refs.lookup_alias("published", "VID-1", db_path=db)["media_id"] == mid
    with pytest.raises(ValueError, match="映射不存在"):
        refs.lookup_alias("project:test-project:v2", "S-001", db_path=db)


def test_manifest_hash_and_internal_alias_conflict_rejected(registry, tmp_path):
    db, source = registry
    manifest = project(source)
    manifest["sources"][0]["expected_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="变化"):
        refs.import_project(manifest, db_path=db)
    other = tmp_path / "other.mp4"
    other.write_bytes(b"different")
    manifest = project(source)
    manifest["sources"].append({**project(other)["sources"][0], "asset_id": "S-002"})
    with pytest.raises(refs.MaterialReferenceConflictError, match="同批"):
        refs.import_project(manifest, db_path=db)
    assert lib.summary(db_path=db)["media"] == 0


def test_observation_long_interval_candidate_and_immutable_versions(registry):
    db, _ = registry
    mid = register(registry)
    first = refs.save_observation(observation(mid), db_path=db)
    assert first["source_out"] - first["source_in"] == 85
    assert first["review_status"] == "candidate"
    assert first == refs.save_observation(observation(mid), db_path=db)
    second = refs.save_observation(observation(mid, observation="新的复核描述"), db_path=db)
    assert second["id"] != first["id"]
    assert len(refs.list_observations(mid, db_path=db)) == 2
    with lib.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0] == 0
    saved = refs.freeze_reference(reference(mid, observation_id=first["id"]), db_path=db)
    assert saved["review_status"] == "candidate"
    assert saved["evidence_snapshot"] == first


def test_confirmed_observation_requires_verified_local_evidence_and_reviewer(registry, tmp_path):
    db, _ = registry
    mid = register(registry)
    payload = observation(mid, review_status="confirmed")
    with pytest.raises(ValueError, match="审核者"):
        refs.save_observation(payload, db_path=db)
    payload["reviewer"] = "人工审阅"
    with pytest.raises(ValueError, match="本地证据"):
        refs.save_observation(payload, db_path=db)
    evidence = tmp_path / "contact-sheet.txt"
    evidence.write_text("已审阅现场对话区间的抽帧证据", encoding="utf-8")
    payload["evidence"] = [{"path": str(evidence), "sha256": "a" * 64}]
    with pytest.raises(ValueError, match="变化"):
        refs.save_observation(payload, db_path=db)
    payload["evidence"][0]["sha256"] = lib.file_sha256(evidence)
    first = refs.save_observation(payload, db_path=db)
    assert first["review_status"] == "confirmed"
    frozen = refs.freeze_reference(reference(mid, observation_id=first["id"]), db_path=db)
    evidence.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="证据.*变化"):
        refs.resolve_reference(frozen["id"], db_path=db)
    with pytest.raises(ValueError, match="证据.*变化"):
        refs.freeze_reference(reference(mid, observation_id=first["id"], source_in=6), db_path=db)


@pytest.mark.parametrize("fields", [
    {"source_in": float("nan")}, {"source_out": float("inf")}, {"source_in": True},
    {"source_in": -1}, {"source_out": 181}, {"source_in": 10, "source_out": 10},
    {"source_in": 11, "source_out": 10},
])
def test_invalid_intervals_rejected_by_observations_and_references(registry, fields):
    db, _ = registry
    mid = register(registry)
    with pytest.raises(ValueError):
        refs.save_observation(observation(mid, **fields), db_path=db)
    with pytest.raises(ValueError):
        refs.freeze_reference(reference(mid, **fields), db_path=db)


def test_scope_and_evidence_window_cannot_be_promoted(registry):
    db, _ = registry
    mid = register(registry)
    scoped = refs.save_observation(observation(mid, scope="vertical-full-frame-v1"), db_path=db)
    with pytest.raises(ValueError, match="作用域"):
        refs.freeze_reference(reference(mid, observation_id=scoped["id"]), db_path=db)
    frozen = refs.freeze_reference(reference(mid, scope="vertical-full-frame-v1", observation_id=scoped["id"]), db_path=db)
    assert frozen["scope"] == "vertical-full-frame-v1"
    with pytest.raises(ValueError, match="覆盖范围"):
        refs.freeze_reference(reference(mid, scope="vertical-full-frame-v1", observation_id=scoped["id"], source_out=91), db_path=db)
    with pytest.raises(ValueError, match="全局"):
        refs.save_observation(observation(mid, scope="all"), db_path=db)
    with pytest.raises(ValueError, match="usable"):
        refs.save_observation(observation(mid, usable=True), db_path=db)
    with pytest.raises(ValueError, match="观察状态"):
        refs.save_observation(observation(mid, review_status=[]), db_path=db)


def test_legacy_central_band_clip_cannot_be_claimed_as_source_content(registry):
    db, _ = registry
    mid = register(registry)
    with lib.connect(db) as conn:
        conn.execute("INSERT INTO clips VALUES(?,?,?,?,?,?,?,?,?)",
                     ("legacy-candidate", mid, 5, 90, "旧候选", "candidate", "{}", "", lib.now()))
    with pytest.raises(ValueError, match="中央带"):
        refs.freeze_reference(reference(mid, legacy_clip_id="legacy-candidate"), db_path=db)
    frozen = refs.freeze_reference(reference(mid, legacy_clip_id="legacy-candidate", scope="template-band-v1"), db_path=db)
    assert frozen["review_status"] == "candidate"
    assert frozen["evidence_snapshot"]["scope"] == "template-band-v1"
    assert frozen["evidence_snapshot"]["id"] == "legacy-candidate"


def test_reference_immutable_under_management_changes_and_archiving(registry):
    db, _ = registry
    mid = register(registry)
    frozen = refs.freeze_reference(reference(mid), db_path=db)
    with lib.connect(db) as conn:
        conn.execute("CREATE TABLE ml_metadata(media_id TEXT PRIMARY KEY,archived INTEGER,tags TEXT)")
        conn.execute("INSERT INTO ml_metadata VALUES(?,1,?)", (mid, '["changed"]'))
    assert refs.get_reference(frozen["id"], db_path=db) == frozen
    assert refs.resolve_reference(frozen["id"], db_path=db)["source_in"] == 5
    assert refs.freeze_reference(reference(mid), db_path=db) == frozen  # Retry of same reference.
    with pytest.raises(ValueError, match="归档"):
        refs.freeze_reference(reference(mid, source_in=6), db_path=db)


def test_source_change_blocks_frozen_reference_even_if_size_and_mtime_equal(registry):
    db, source = registry
    mid = register(registry)
    frozen = refs.freeze_reference(reference(mid), db_path=db)
    stat = source.stat()
    source.write_bytes(b"x" * stat.st_size)
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(ValueError, match="变化"):
        refs.resolve_reference(frozen["id"], db_path=db)
    # Historical metadata remains inspectable for diagnosis.
    assert refs.get_reference(frozen["id"], db_path=db) == frozen


def test_source_move_and_an_invalid_copy_do_not_break_frozen_reference(registry, tmp_path):
    db, source = registry
    mid = register(registry)
    frozen = refs.freeze_reference(reference(mid), db_path=db)
    moved = tmp_path / "moved.mp4"
    source.rename(moved)
    refs.import_project(project(moved), db_path=db)
    assert refs.resolve_reference(frozen["id"], db_path=db)["path"] == str(moved.resolve())
    source.write_bytes(b"z" * moved.stat().st_size)
    assert refs.resolve_reference(frozen["id"], db_path=db)["path"] == str(moved.resolve())


def test_usage_idempotent_bidirectional_and_conflict_cannot_overwrite(registry):
    db, _ = registry
    mid = register(registry)
    first = refs.freeze_reference(reference(mid), db_path=db)
    second = refs.freeze_reference(reference(mid, source_in=6), db_path=db)
    saved = refs.record_usage(usage(first["id"]), db_path=db)
    assert saved == refs.record_usage(usage(first["id"]), db_path=db)
    assert refs.list_usage(media_id=mid, db_path=db) == [saved]
    assert refs.list_usage(project_id="test-project", db_path=db) == [saved]
    with pytest.raises(refs.MaterialReferenceConflictError, match="已冻结"):
        refs.record_usage(usage(second["id"]), db_path=db)
    with pytest.raises(refs.MaterialReferenceConflictError, match="已冻结"):
        refs.record_usage(usage(first["id"], asset_id="S-002"), db_path=db)
    assert refs.list_usage(media_id=mid, db_path=db) == [saved]
    new_version = refs.record_usage(usage(second["id"], project_version="v2"), db_path=db)
    assert new_version["id"] != saved["id"]


def test_usage_cannot_misattribute_a_registered_project_asset(registry, tmp_path):
    db, _ = registry
    register(registry)
    other = tmp_path / "other.mp4"
    other.write_bytes(b"other source")
    mid = lib.register_file(other, db_path=db)["media_ids"][0]
    frozen = refs.freeze_reference(reference(mid), db_path=db)
    with pytest.raises(refs.MaterialReferenceConflictError, match="映射不一致"):
        refs.record_usage(usage(frozen["id"]), db_path=db)
    assert refs.list_usage(db_path=db) == []


def test_later_project_import_cannot_rebind_previously_used_asset(registry, tmp_path):
    db, source = registry
    mid = lib.register_file(source, db_path=db)["media_ids"][0]
    frozen = refs.freeze_reference(reference(mid), db_path=db)
    refs.record_usage(usage(frozen["id"]), db_path=db)
    other = tmp_path / "other.mp4"
    other.write_bytes(b"different source")
    with pytest.raises(refs.MaterialReferenceConflictError, match="冻结使用记录"):
        refs.import_project(project(other), db_path=db)
    assert lib.summary(db_path=db)["media"] == 1
    assert refs.import_project(project(source), db_path=db)["media_ids"] == [mid]


def test_confirmed_legacy_clip_needs_matching_task_and_retains_evidence_scope(registry, tmp_path):
    db, _ = registry
    mid = register(registry)
    evidence_dir = tmp_path / "evidence" / "EV-test"
    evidence_dir.mkdir(parents=True)
    sheet = evidence_dir / "sheet.png"
    sheet.write_bytes(b"local evidence bytes")
    task = {"id": "EV-test", "identity": {"profile": "template-band-v1"}, "windows": [{
        "media_id": mid, "source_sha256": lib.get_media(mid, db_path=db)["sha256"],
        "start": 5, "end": 90, "sheets": [{"file": "sheet.png", "sha256": lib.file_sha256(sheet)}]}]}
    with lib.connect(db) as conn:
        conn.execute("INSERT INTO tasks VALUES(?,?,?)", ("EV-test", json.dumps(task), '{}'))
        conn.execute("INSERT INTO clips VALUES(?,?,?,?,?,?,?,?,?)",
                     ("legacy-confirmed", mid, 5, 90, "中央带已审", "confirmed", '{"usable":false}', "EV-test", lib.now()))
    frozen = refs.freeze_reference(reference(mid, legacy_clip_id="legacy-confirmed", scope="template-band-v1"), db_path=db)
    assert frozen["review_status"] == "confirmed"
    assert frozen["evidence_snapshot"]["metadata"]["usable"] is False
    assert frozen["scope"] == "template-band-v1"
    assert refs.resolve_reference(frozen["id"], db_path=db)
    sheet.write_bytes(b"modified")
    with pytest.raises(ValueError, match="证据.*变化"):
        refs.resolve_reference(frozen["id"], db_path=db)


def test_derived_project_asset_can_explicitly_trace_original_without_merging_identity(registry, tmp_path):
    db, source = registry
    derivative = tmp_path / "portrait-derived.mp4"
    derivative.write_bytes(b"portrait contain transform of source, different hash")
    manifest = project(source)
    manifest["sources"][0]["asset_id"] = "SRC-USA"
    manifest["sources"].append({"asset_id": "S-001", "path": str(derivative),
                                 "expected_sha256": lib.file_sha256(derivative)})
    result = refs.import_project(manifest, db_path=db)
    source_mid, derived_mid = result["media_ids"]
    assert source_mid != derived_mid
    frozen = refs.freeze_reference(reference(source_mid), db_path=db)
    saved = refs.record_usage(usage(frozen["id"], source_asset_id="SRC-USA"), db_path=db)
    assert saved["source_asset_id"] == "SRC-USA"
    assert saved["project_asset_media_id"] == derived_mid
    assert saved["media_id"] == saved["reference"]["media_id"] == source_mid
    assert saved == refs.record_usage(usage(frozen["id"], source_asset_id="SRC-USA"), db_path=db)
    assert refs.list_usage(media_id=source_mid, db_path=db) == [saved]
    assert refs.list_usage(media_id=derived_mid, db_path=db) == [saved]
    with pytest.raises(refs.MaterialReferenceConflictError, match="映射不一致"):
        refs.record_usage(usage(frozen["id"]), db_path=db)
    with pytest.raises(ValueError, match="均须先登记"):
        refs.record_usage(usage(frozen["id"], source_asset_id="unknown", slot_id="shot-2"), db_path=db)
    with pytest.raises(ValueError, match="均须先登记"):
        refs.record_usage(usage(frozen["id"], source_asset_id="SRC-USA", asset_id="unknown"), db_path=db)
    with pytest.raises(refs.MaterialReferenceConflictError, match="原片素材编号"):
        refs.record_usage(usage(frozen["id"], source_asset_id="S-001", slot_id="shot-2"), db_path=db)
    assert refs.list_usage(db_path=db) == [saved]


def test_project_alias_namespace_escapes_ambiguous_colons(registry):
    db, source = registry
    refs.import_project(project(source, project_id="a:b", project_version="c"), db_path=db)
    refs.import_project(project(source, project_id="a", project_version="b:c"), db_path=db)
    assert refs.lookup_alias("project:a%3Ab:c", "S-001", db_path=db)
    assert refs.lookup_alias("project:a:b%3Ac", "S-001", db_path=db)


def test_concurrent_usage_claims_have_one_winner(registry):
    db, _ = registry
    mid = register(registry)
    references = [refs.freeze_reference(reference(mid, source_in=i), db_path=db) for i in (5, 6)]

    def attempt(frozen):
        try:
            return refs.record_usage(usage(frozen["id"]), db_path=db)["ref_id"]
        except refs.MaterialReferenceConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, references))
    assert results.count("conflict") == 1
    saved = refs.list_usage(db_path=db)
    assert len(saved) == 1 and saved[0]["ref_id"] in results


def test_frozen_reference_and_observation_content_tampering_detected(registry):
    db, _ = registry
    mid = register(registry)
    observed = refs.save_observation(observation(mid), db_path=db)
    frozen = refs.freeze_reference(reference(mid), db_path=db)
    refs.record_usage(usage(frozen["id"]), db_path=db)
    with lib.connect(db) as conn:
        row = conn.execute("SELECT payload FROM ml_ref_references WHERE id=?", (frozen["id"],)).fetchone()
        payload = json.loads(row["payload"])
        payload["source_in"] = 7
        conn.execute("UPDATE ml_ref_references SET payload=? WHERE id=?", (json.dumps(payload), frozen["id"]))
        row = conn.execute("SELECT payload FROM ml_ref_observations WHERE id=?", (observed["id"],)).fetchone()
        payload = json.loads(row["payload"])
        payload["review_status"] = "confirmed"
        conn.execute("UPDATE ml_ref_observations SET payload=? WHERE id=?", (json.dumps(payload), observed["id"]))
    with pytest.raises(ValueError, match="内容已变化"):
        refs.get_reference(frozen["id"], db_path=db)
    with pytest.raises(ValueError, match="内容已变化"):
        refs.list_usage(db_path=db)
    with pytest.raises(ValueError, match="内容已变化"):
        refs.freeze_reference(reference(mid, observation_id=observed["id"]), db_path=db)
