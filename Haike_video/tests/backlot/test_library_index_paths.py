from pathlib import Path

from backlot.library_index import _source_records, read_index


def record(identity, paths):
    return {"id": identity, "media_paths": paths, "platform": "douyin", "account_id": 1,
            "status": "done", "done_at": None, "created_at": None, "result_url": ""}


def test_request_path_index_preserves_containment_and_deduplication(tmp_path):
    project = tmp_path / "film"
    sibling = tmp_path / "film-other"
    project.mkdir(); sibling.mkdir()
    first, second = project / "one.mp4", project / "two.mp4"
    for path in [first, second, sibling / "outside.mp4"]:
        path.write_bytes(b"video")
    snapshot = {"records": [record(1, [str(first), str(second)]),
                             record(2, [str(sibling / "outside.mp4")]), record(3, ["relative.mp4"])]}
    result = _source_records(project, snapshot)
    assert len(result) == 1 and result[0]["version_path"] == "one.mp4"
    grouped = snapshot["_records_by_directory"]
    assert _source_records(project, snapshot) == result
    assert snapshot["_records_by_directory"] is grouped
    assert len(_source_records(sibling, snapshot)) == 1
    detail = read_index(project, board={}, snapshot=snapshot)
    assert "_records_by_directory" not in detail["sync"]
    assert detail["current_version"]["path"] == "one.mp4"


def test_same_prefix_outside_path_never_matches(tmp_path):
    project = tmp_path / "film"
    project.mkdir()
    snapshot = {"records": [record(1, [str(tmp_path / "film-outside" / "x.mp4")]),
                             record(2, [str(project / ".." / "outside.mp4")])]}
    assert not _source_records(project, snapshot)
