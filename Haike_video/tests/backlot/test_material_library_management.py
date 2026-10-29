from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import threading

import pytest

from backlot import material_library as lib
from backlot import material_library_management as management


@pytest.fixture
def db(tmp_path):
    return tmp_path / "library.sqlite3"


def asset(tmp_path, db, name="source", *, width=1920, height=1080, duration=60, platform="local"):
    # Codec decoding belongs to the existing registry integration tests. Here
    # bytes are real so health checks exercise hashing, movement and corruption.
    path = tmp_path / f"{name}.mp4"
    path.write_bytes((name + "-original-content").encode())
    sha = lib.file_sha256(path)
    item = {"id": "MAT-" + sha, "sha256": sha, "path": str(path), "bytes": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns, "title": name, "duration": duration,
            "width": width, "height": height,
            "origin": {"platform": platform, "source_url": "https://example.test/video",
                       "video_id": "source-" + name, "rights_status": "unknown", "catalog": "fixture"}}
    lib.register_prepared([item], db_path=db)
    return item["id"], path


def update(db, media_id, revision=0, **patch):
    return management.update_metadata({"items": [{"media_id": media_id, "expected_revision": revision}],
                                       "patch": patch}, db_path=db)


def old_clip(db, media_id, clip_id, *, start=0, end=3, status="confirmed", observation="旧裁切观察"):
    with lib.connect(db) as conn:
        conn.execute("INSERT INTO clips VALUES(?,?,?,?,?,?,?,?,?)",
                     (clip_id, media_id, start, end, observation, status,
                      json.dumps({"usable": False, "tags": ["旧模板"]}, ensure_ascii=False), "task", lib.now()))


def generic_observation(db, media_id, obs_id, *, start=0, end=3, status="candidate", text="现场原声"):
    # Exercise the public additive table contract without requiring module init
    # order or a dependency on the other implementation's constructors.
    with management.connect(db) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS ml_ref_observations(id TEXT PRIMARY KEY,media_id TEXT,"
                     "source_in REAL,source_out REAL,review_status TEXT,scope TEXT,payload TEXT,created_at TEXT)")
        conn.execute("INSERT INTO ml_ref_observations VALUES(?,?,?,?,?,?,?,?)",
                     (obs_id, media_id, start, end, status, "source-content-v1",
                      json.dumps({"observation": text, "facts": {"subtitles": "保留字幕"}}, ensure_ascii=False), lib.now()))


def test_additive_schema_defaults_preserve_library_version(db, tmp_path):
    mid, _ = asset(tmp_path, db)
    old_clip(db, mid, "legacy")
    assert management.get_metadata(mid, db_path=db) == {
        "media_id": mid, "tags": [], "collections": [], "notes": "", "archived": False,
        "revision": 0, "updated_at": None}
    with management.connect(db) as conn:
        assert conn.execute("SELECT value FROM library_meta WHERE key='version'").fetchone()[0] == "1"
        assert conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0] == 1
    assert management.detail(mid, db_path=db)["clips"][0]["metadata"]["usable"] is False


def test_metadata_normalization_and_archive_do_not_modify_review(db, tmp_path):
    mid, _ = asset(tmp_path, db)
    old_clip(db, mid, "legacy")
    saved = update(db, mid, tags=["  粤仔  ", "粤仔"], collections=["主题二剪"], notes="带现场声", archived=True)
    assert saved["updated"] == 1
    assert saved["items"][0]["tags"] == ["粤仔"]
    assert saved["items"][0]["revision"] == 1
    assert management.search({}, db_path=db)["total"] == 0
    assert management.search({"archived": "archived"}, db_path=db)["total"] == 1
    assert management.summary(db_path=db)["active"] == 0
    assert lib.list_media(db_path=db)[0]["id"] == mid  # Existing V1 API unchanged.
    assert lib.get_media(mid, db_path=db)["clips"][0]["metadata"]["usable"] is False
    update(db, mid, revision=1, archived=False)
    assert management.get_metadata(mid, db_path=db)["tags"] == ["粤仔"]


def test_batch_conflict_rolls_back_every_item(db, tmp_path):
    first, _ = asset(tmp_path, db, "first")
    second, _ = asset(tmp_path, db, "second")
    update(db, second, notes="已保存")
    with pytest.raises(management.MaterialConflictError, match="均未保存"):
        management.update_metadata({"items": [{"media_id": first, "expected_revision": 0},
                                               {"media_id": second, "expected_revision": 0}],
                                    "patch": {"notes": "不可部分保存"}}, db_path=db)
    assert management.get_metadata(first, db_path=db)["revision"] == 0
    assert management.get_metadata(second, db_path=db)["notes"] == "已保存"


def test_simultaneous_editors_have_one_winner(db, tmp_path):
    mid, _ = asset(tmp_path, db)
    management.get_metadata(mid, db_path=db)
    barrier = threading.Barrier(2)

    def attempt(note):
        barrier.wait(timeout=5)
        try:
            update(db, mid, notes=note)
            return "saved", note
        except management.MaterialConflictError:
            return "conflict", note

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, ["甲编辑", "乙编辑"]))
    assert sorted(state for state, _ in results) == ["conflict", "saved"]
    meta = management.get_metadata(mid, db_path=db)
    assert meta["revision"] == 1
    assert meta["notes"] == next(note for state, note in results if state == "saved")


@pytest.mark.parametrize("payload", [
    {"items": [], "patch": {"tags": []}},
    {"items": [{"media_id": "A", "expected_revision": 0}], "patch": {"review_status": "confirmed"}},
    {"items": [{"media_id": "A", "expected_revision": True}], "patch": {"tags": []}},
    {"items": [{"media_id": "A", "expected_revision": 0.5}], "patch": {"tags": []}},
    {"items": [{"media_id": "A", "expected_revision": 0}], "patch": {"archived": "false"}},
    {"items": [{"media_id": "A", "expected_revision": 0}], "patch": {"tags": [""]}},
    {"items": [{"media_id": "A", "expected_revision": 0}], "patch": {"notes": "x" * 4001}},
    {"items": [{"media_id": "A", "expected_revision": 0}] * 2, "patch": {"tags": []}},
])
def test_invalid_updates_rejected_without_rows(db, payload):
    with pytest.raises(lib.MaterialLibraryError):
        management.update_metadata(payload, db_path=db)


def test_search_filters_keywords_and_stable_pagination(db, tmp_path):
    portrait, _ = asset(tmp_path, db, "粤仔 100%_真实", width=720, height=1280, duration=42, platform="douyin")
    landscape, _ = asset(tmp_path, db, "电影", duration=180)
    square, _ = asset(tmp_path, db, "访谈", width=1080, height=1080, duration=20)
    update(db, portrait, tags=["粤仔"], collections=["朋友"], notes="舞台互动")
    old_clip(db, portrait, "p1", observation="外国朋友拥抱")
    generic_observation(db, landscape, "g1", text="电影中的城市")
    combined = management.search({"tag": "粤仔", "collection": "朋友", "platform": "douyin",
                                  "aspect": "portrait", "review_status": "confirmed", "query": "拥抱",
                                  "min_duration": 40, "max_duration": 50}, db_path=db)
    assert [item["id"] for item in combined["items"]] == [portrait]
    assert combined["items"][0]["platforms"] == ["douyin"]
    for query in ("100%_", "舞台互动", "朋友", "source-粤仔"):
        assert management.search({"query": query}, db_path=db)["total"] == 1
    assert management.search({"query": "%_"}, db_path=db)["total"] == 1  # Literal LIKE escaping.
    assert management.search({"query": "城市"}, db_path=db)["items"][0]["id"] == landscape
    assert management.search({"query": "保留字幕"}, db_path=db)["items"][0]["id"] == landscape
    assert management.search({"aspect": "square", "review_status": "unreviewed"}, db_path=db)["items"][0]["id"] == square
    assert management.search({"review_status": "candidate"}, db_path=db)["items"][0]["id"] == landscape
    full = management.search({}, db_path=db)["items"]
    paged = [management.search({"page": page, "page_size": 1}, db_path=db)["items"][0]["id"] for page in (1, 2, 3)]
    assert paged == [item["id"] for item in full]
    assert len(set(paged)) == 3
    assert management.search({"page": 4, "page_size": 1}, db_path=db)["items"] == []


def test_counts_distinguish_intervals_versions_and_generations(db, tmp_path):
    mid, _ = asset(tmp_path, db)
    old_clip(db, mid, "crop-v1")
    old_clip(db, mid, "crop-v2")
    generic_observation(db, mid, "content-v1")  # Same original seconds; third independent version.
    generic_observation(db, mid, "content-v2", start=3, end=40, status="confirmed")
    expected = {"intervals": 2, "review_versions": 4, "confirmed_versions": 3,
                "candidate_versions": 1, "locations": 1}
    assert management.detail(mid, db_path=db)["counts"] == expected
    summary = management.summary(db_path=db)
    assert {key: summary[key] for key in expected} == expected
    assert summary["media"] == 1


@pytest.mark.parametrize("payload", [{"page": 0}, {"page_size": 101}, {"page": 1.5}, {"page": True},
                                       {"min_duration": float("nan")}, {"max_duration": float("inf")},
                                       {"min_duration": 50, "max_duration": 20}, {"aspect": "vertical"},
                                       {"health": []}, {"query": None}, {"tag": ["粤仔"]}])
def test_invalid_search_inputs_rejected(db, payload):
    with pytest.raises(lib.MaterialLibraryError):
        management.search(payload, db_path=db)


def test_full_hash_detects_same_size_and_timestamp_corruption(db, tmp_path):
    mid, path = asset(tmp_path, db)
    before = path.stat()
    assert management.detail(mid, db_path=db)["health"]["status"] == "unchecked"
    assert management.check_health(mid, db_path=db)["status"] == "valid"
    data = bytearray(path.read_bytes())
    data[0] ^= 1
    path.write_bytes(data)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert management.check_health(mid, db_path=db)["status"] == "changed"
    assert management.search({"health": "changed"}, db_path=db)["total"] == 1
    assert management.search({"health": "valid"}, db_path=db)["total"] == 0
    with pytest.raises(lib.MaterialLibraryError, match="校验不一致"):
        management.relink(mid, path, db_path=db)


def test_relink_moved_asset_and_valid_copy_survive_bad_locations(db, tmp_path):
    mid, original = asset(tmp_path, db)
    moved = tmp_path / "moved.mp4"
    original.rename(moved)
    assert management.check_health(mid, db_path=db)["status"] == "missing"
    result = management.relink(mid, moved, db_path=db)
    assert result["health"]["status"] == "valid"
    assert sorted(row["status"] for row in result["health"]["locations"]) == ["missing", "valid"]
    assert lib.resolve_media(mid, db_path=db) == moved
    assert management.summary(db_path=db)["media"] == 1
    assert management.summary(db_path=db)["locations"] == 2
    assert management.check_health(mid, db_path=db)["status"] == "valid"
    assert management.relink(mid, moved, db_path=db)["path"] == str(moved)
    assert management.summary(db_path=db)["locations"] == 2


def test_health_read_error_is_explicit_and_does_not_hide_valid_copy(db, tmp_path, monkeypatch):
    mid, original = asset(tmp_path, db)
    backup = tmp_path / "backup.mp4"
    backup.write_bytes(original.read_bytes())
    management.relink(mid, backup, db_path=db)
    sha = lib.file_sha256

    def denied(path):
        if Path(path) == original:
            raise PermissionError("no access")
        return sha(path)

    monkeypatch.setattr(lib, "file_sha256", denied)
    health = management.check_health(mid, db_path=db)
    assert health["status"] == "valid"
    assert sorted(row["status"] for row in health["locations"]) == ["error", "valid"]
    assert all(row["checked_at"] for row in health["locations"])


def test_search_and_detail_do_not_hash_files(db, tmp_path, monkeypatch):
    mid, _ = asset(tmp_path, db)

    def unexpected(_):
        raise AssertionError("Search must only read recorded health")

    monkeypatch.setattr(lib, "file_sha256", unexpected)
    assert management.search({"health": "unchecked"}, db_path=db)["items"][0]["id"] == mid
    assert management.detail(mid, db_path=db)["health"]["checked_at"] is None


def test_unknown_asset_and_bad_relink_leave_registry_untouched(db, tmp_path):
    mid, path = asset(tmp_path, db)
    with pytest.raises(lib.MaterialLibraryError, match="不存在"):
        management.check_health("unknown", db_path=db)
    with pytest.raises(lib.MaterialLibraryError, match="不存在"):
        management.get_metadata("unknown", db_path=db)
    different = tmp_path / "different.mp4"
    different.write_bytes(b"totally different")
    with pytest.raises(lib.MaterialLibraryError, match="校验不一致"):
        management.relink(mid, different, db_path=db)
    assert lib.resolve_media(mid, db_path=db) == path
    assert management.summary(db_path=db)["locations"] == 1
