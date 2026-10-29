"""Real hashes/SQLite for the commentary to shared-library contract."""
from copy import deepcopy
import json

import pytest

from backlot import commentary_evidence as evidence
from backlot import commentary_library_bridge as bridge
from backlot import material_library as library
from backlot import material_library_management as management
from backlot import material_library_refs as refs
from backlot.commentary_common import CommentaryError, digest, file_sha256, immutable


@pytest.fixture
def registered(tmp_path, monkeypatch):
    # The tests below exercise the bridge and real hashes; decoding and rendered
    # output are exercised by the workflow integration tests.
    monkeypatch.setattr(library, "probe", lambda _: {"duration": 30, "width": 1280, "height": 720})
    db = tmp_path / "isolated.sqlite3"
    source = tmp_path / "original.mp4"
    source.write_bytes(b"commentary source identity")
    mid = library.register_file(source, {"title": "电影片段", "platform": "local"}, db_path=db)["media_ids"][0]
    pid = "commentary-0123456789abcdef"
    project = tmp_path / "projects" / pid
    request = {"version": 1, "media_id": mid, "sha256": file_sha256(source),
               "start": 2, "end": 20, "crop": {"x": .1, "y": 0, "w": .8, "h": 1}}
    eid = "EV-" + digest(request)
    folder = evidence.directory(project, eid)
    folder.mkdir(parents=True)
    for name in ("source.mp4", "sheet.jpg"):
        (folder / name).write_bytes(b"review fixture " + name.encode())
    item = {**request, "id": eid, "source_path": str(source), "title": "电影片段",
            "origins": [{"platform": "local"}], "samples": [3, 10, 19],
            "files": {name: file_sha256(folder / name) for name in ("source.mp4", "sheet.jpg")}}
    review = {"reviewer": "fixture-reviewer", "viewed": True, "usable": True,
              "observation": "已查看的人物从左侧进入画面", "context": "先听见问句，再进入画面回答",
              "unknowns": "未确认人物职业", "transcript": "你好", "audio_reviewed": True,
              "source_subtitles": "unknown", "source_music": "none"}
    immutable(folder / "evidence.json", item)
    immutable(folder / "review.json", review)
    item["review"] = review
    shot = {"evidence_id": eid, "media_id": mid, "start": 3, "end": 7,
            "crop": item["crop"], "evidence_digest": digest(item)}
    frozen = {"project_id": pid, "revision": 1, "format": "portrait",
              "profile": {"width": 720, "height": 1280, "fps": 30, "audio_rate": 48000},
              "sources": {mid: {"media_id": mid, "path": str(source), "sha256": item["sha256"]}},
              "evidence": {eid: item}, "segments": [
                  {"id": "answer", "purpose": "保留回答的前后文", "shots": [shot, {**shot, "start": 8, "end": 11}]},
                  {"id": "recall", "purpose": "回看素材确认的动作", "shots": [{**shot}]}]}
    return {"db": db, "source": source, "mid": mid, "pid": pid,
            "project": project, "folder": folder, "frozen": frozen}


def bind(registry):
    return bridge.bind_references(registry["pid"], registry["frozen"],
                                  project_dir=registry["project"], db_path=registry["db"])


def archive(registry, archived=True):
    metadata = management.get_metadata(registry["mid"], db_path=registry["db"])
    management.update_metadata({"items": [{"media_id": registry["mid"], "expected_revision": metadata["revision"]}],
                                "patch": {"archived": archived}}, db_path=registry["db"])


def record(registry, frozen):
    return bridge.record_usages(registry["pid"], digest(frozen), frozen, db_path=registry["db"])


def test_availability_requires_registered_active_media(registered):
    r = registered
    assert bridge.ensure_available(r["mid"], db_path=r["db"])["id"] == r["mid"]
    with pytest.raises(CommentaryError, match="不存在"):
        bridge.ensure_available("missing", db_path=r["db"])
    archive(r)
    with pytest.raises(CommentaryError, match="归档"):
        bridge.ensure_available(r["mid"], db_path=r["db"])
    with pytest.raises(CommentaryError, match="归档"):
        bind(r)
    assert refs.list_observations(r["mid"], db_path=r["db"]) == []


def test_bind_uses_checked_crop_scope_and_evidence_without_mutating_input(registered):
    r = registered
    frozen = bind(r)
    assert "library_ref_id" not in r["frozen"]["segments"][0]["shots"][0]
    assert frozen == bind(r)
    observations = refs.list_observations(r["mid"], db_path=r["db"])
    assert len(observations) == 1
    observation = observations[0]
    assert observation["review_status"] == "confirmed"
    assert observation["scope"].startswith("material-commentary-v1:")
    assert observation["scope"] not in {"source-content", "template-band-v1"}
    assert "usable" not in observation and "usable" not in observation["facts"]
    assert observation["facts"]["subtitles"] == "unknown"
    assert observation["facts"]["source_audio"] == "你好"
    assert {p["path"].split("\\")[-1].split("/")[-1] for p in observation["evidence"]} == {
        "source.mp4", "sheet.jpg", "evidence.json", "review.json"}
    shot = frozen["segments"][0]["shots"][0]
    reference = refs.get_reference(shot["library_ref_id"], db_path=r["db"])
    assert (reference["source_in"], reference["source_out"]) == (3, 7)
    assert reference["evidence_snapshot"]["id"] == observation["id"]
    assert refs.list_usage(project_id=r["pid"], db_path=r["db"]) == []


def test_each_shot_and_version_has_idempotent_actual_usage(registered):
    r = registered
    frozen = bind(r)
    first = record(r, frozen)
    assert len(first) == 3 and len({row["id"] for row in first}) == 3
    assert {(row["scene_id"], row["slot_id"]) for row in first} == {
        ("answer", "shot-001"), ("answer", "shot-002"), ("recall", "shot-001")}
    assert record(r, frozen) == first
    newer = {**frozen, "revision": 2}
    second = record(r, newer)
    assert {row["id"] for row in first}.isdisjoint(row["id"] for row in second)
    assert len(refs.list_usage(media_id=r["mid"], db_path=r["db"])) == 6


def test_archive_keeps_existing_version_but_blocks_new_version_and_new_bind(registered):
    r = registered
    frozen = bind(r)
    first = record(r, frozen)
    archive(r)
    assert record(r, frozen) == first
    with pytest.raises(CommentaryError, match="归档"):
        bind(r)
    with pytest.raises(CommentaryError, match="归档"):
        record(r, {**frozen, "revision": 2})
    assert len(refs.list_usage(project_id=r["pid"], db_path=r["db"])) == 3


def test_archive_between_binding_and_first_usage_is_rejected(registered):
    r = registered
    frozen = bind(r)
    archive(r)
    with pytest.raises(CommentaryError, match="归档"):
        record(r, frozen)
    assert refs.list_usage(project_id=r["pid"], db_path=r["db"]) == []


def test_relink_preserves_frozen_evidence_and_archived_history(registered, tmp_path):
    r = registered
    frozen = bind(r)
    first = record(r, frozen)
    moved = tmp_path / "moved.mp4"
    r["source"].rename(moved)
    management.relink(r["mid"], moved, db_path=r["db"])
    archive(r)
    assert bridge.resolve_source(r["mid"], frozen["sources"][r["mid"]]["sha256"], db_path=r["db"]) == moved
    reference = refs.resolve_reference(frozen["segments"][0]["shots"][0]["library_ref_id"], db_path=r["db"])
    assert reference["path"] == str(moved)
    assert record(r, frozen) == first
    assert frozen["sources"][r["mid"]]["path"] == str(r["source"])


def test_same_sha_move_also_allows_new_active_binding(registered, tmp_path):
    r = registered
    frozen = bind(r)
    moved = tmp_path / "active-move.mp4"
    r["source"].rename(moved)
    management.relink(r["mid"], moved, db_path=r["db"])
    assert bind(r) == frozen


@pytest.mark.parametrize("change", ["crop", "evidence", "file", "review"])
def test_binding_rejects_changed_crop_or_evidence(registered, change):
    r = registered
    if change == "crop":
        r["frozen"]["segments"][0]["shots"][0]["crop"] = {"x": 0, "y": 0, "w": 1, "h": 1}
    elif change == "evidence":
        r["frozen"]["evidence"][next(iter(r["frozen"]["evidence"]))]["sha256"] = "0" * 64
    elif change == "file":
        (r["folder"] / "sheet.jpg").write_bytes(b"changed frame evidence")
    else:
        review = json.loads((r["folder"] / "review.json").read_text(encoding="utf-8"))
        review["usable"] = False
        (r["folder"] / "review.json").write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(CommentaryError):
        bind(r)
    assert refs.list_observations(r["mid"], db_path=r["db"]) == []


def test_usage_does_not_accept_reference_for_different_output_profile(registered):
    r = registered
    frozen = bind(r)
    other = deepcopy(frozen)
    other["format"] = "landscape"
    other["profile"].update(width=1280, height=720)
    with pytest.raises(CommentaryError, match="作用域"):
        record(r, other)
    assert refs.list_usage(project_id=r["pid"], db_path=r["db"]) == []


def test_usage_requires_matching_signature_and_project(registered):
    r = registered
    frozen = bind(r)
    with pytest.raises(CommentaryError, match="签名"):
        bridge.record_usages(r["pid"], "0" * 64, frozen, db_path=r["db"])
    with pytest.raises(CommentaryError, match="身份"):
        bridge.record_usages("another-project", digest(frozen), frozen, db_path=r["db"])


def test_resolve_source_rejects_hash_mismatch_or_changed_content(registered):
    r = registered
    with pytest.raises(CommentaryError, match="不一致"):
        bridge.resolve_source(r["mid"], "0" * 64, db_path=r["db"])
    sha = file_sha256(r["source"])
    r["source"].write_bytes(b"different contents")
    with pytest.raises(CommentaryError, match="变化"):
        bridge.resolve_source(r["mid"], sha, db_path=r["db"])


def test_search_uses_management_tags_and_excludes_archived(registered):
    r = registered
    management.update_metadata({"items": [{"media_id": r["mid"], "expected_revision": 0}],
                                "patch": {"tags": ["问答上下文"], "collections": ["电影场景"]}}, db_path=r["db"])
    assert [item["id"] for item in bridge.search("问答上下文", limit=1, db_path=r["db"])] == [r["mid"]]
    assert [item["id"] for item in bridge.search("电影场景", db_path=r["db"])] == [r["mid"]]
    archive(r)
    assert bridge.search("", db_path=r["db"]) == []
