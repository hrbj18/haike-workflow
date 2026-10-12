"""End-to-end queued commentary recovery through shared-library management."""
from copy import deepcopy
import subprocess

import pytest

from backlot import commentary_evidence as evidence
from backlot import material_commentary as flow
from backlot import material_library as library
from backlot import material_library_management as management
from backlot import material_library_refs as refs
from backlot.commentary_common import CommentaryError, digest, file_sha256, project_dir, read_json
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from lib.ffmpeg_locator import resolve_ffmpeg_pair


def test_queued_frozen_version_survives_relink_and_archive_but_new_version_is_blocked(tmp_path, monkeypatch):
    pair = resolve_ffmpeg_pair()
    if not pair:
        pytest.skip("FFmpeg unavailable")
    monkeypatch.setenv("OPENMONTAGE_MATERIAL_LIBRARY_DIR", str(tmp_path / "library"))
    projects = tmp_path / "projects"
    projects.mkdir()
    source = tmp_path / "source.mp4"
    subprocess.run([
        pair[0], "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=6",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6",
        "-c:v", "libx264", "-threads", "2", "-c:a", "aac", "-t", "6", str(source),
    ], check=True, capture_output=True)
    media_id = library.register_file(source, {
        "title": "重定位与归档恢复合成夹具", "rights_status": "generated-test-fixture",
    })["media_ids"][0]
    draft = flow.create("素材库与解说队列贯穿验证", projects_root=projects)
    project = project_dir(draft["id"], projects)
    observed = evidence.prepare(project, {"media_id": media_id, "start": 0, "end": 5.5})
    evidence.review(project, observed["id"], {
        "reviewer": "test-fixture", "viewed": True, "usable": True,
        "observation": "合成测试图案，音轨为稳定正弦波",
        "context": "仅验证工程合同；不构成电影或直播内容语义验收",
        "source_subtitles": "none", "source_music": "none", "audio_reviewed": False,
    })
    rows = [{
        "id": "recall", "mode": "original", "text": "", "purpose": "回看已观察动作",
        "basis": "使用两个已核验窗口，次序由本次素材组织决定", "subtitle_mode": "none",
        "shots": [{"evidence_id": observed["id"], "start": 2.5, "end": 3.5},
                  {"evidence_id": observed["id"], "start": .5, "end": 1.5}],
    }, {
        "id": "answer", "mode": "original", "text": "", "purpose": "保留后续片段",
        "basis": "此窗口与前两镜处于同一已确认素材区间", "subtitle_mode": "none",
        "shots": [{"evidence_id": observed["id"], "start": 4, "end": 5}],
    }]
    draft = flow.save(draft["id"], {**draft, "payload": {
        **draft["payload"], "format": "landscape", "content_kind": "工程合成夹具",
        "intent": "验证素材追溯及冻结恢复", "structure": "素材决定镜头次序与数量", "segments": rows,
    }}, projects_root=projects)
    queue = ProductionQueue(tmp_path / "queue.sqlite3", projects)
    job = flow.submit(draft["id"], draft["revision"], queue, projects_root=projects)
    signature = job["parent_job_id"]
    version = flow.version_dir(draft["id"], signature, projects_root=projects)
    request_path = version / "request.json"
    frozen = read_json(request_path)
    request_hash = file_sha256(request_path)
    assert digest(frozen) == signature
    assert not (version / "preview.mp4").exists()

    usages = refs.list_usage(project_id=draft["id"])
    assert len(usages) == 3
    assert {(row["scene_id"], row["slot_id"], row["project_version"]) for row in usages} == {
        ("recall", "shot-001", signature), ("recall", "shot-002", signature), ("answer", "shot-001", signature),
    }
    shot_refs = {shot["library_ref_id"] for segment in frozen["segments"] for shot in segment["shots"]}
    assert shot_refs == {row["ref_id"] for row in usages}
    assert {(row["reference"]["source_in"], row["reference"]["source_out"]) for row in usages} == {
        (2.5, 3.5), (.5, 1.5), (4, 5),
    }

    moved = tmp_path / "relocated-source.mp4"
    source.rename(moved)
    management.relink(media_id, moved)
    assert evidence.confirmed(project, observed["id"], check_files=True)["media_id"] == media_id
    metadata = management.get_metadata(media_id)
    management.update_metadata({"items": [{"media_id": media_id, "expected_revision": metadata["revision"]}],
                                "patch": {"archived": True}})
    repeated = flow.submit(draft["id"], draft["revision"], queue, projects_root=projects)
    assert repeated["job_id"] == job["job_id"] and repeated["parent_job_id"] == signature
    assert refs.list_usage(project_id=draft["id"]) == usages

    # No cached render exists: the queue must read the relocated, now archived
    # original by its registered content identity to produce this first preview.
    outcome = ProductionQueueWorker(queue, projects).run_once()
    assert outcome["status"] == "completed", outcome
    output = flow.output_path(draft["id"], signature, projects_root=projects)
    assert output.is_file()
    result = flow.versions(draft["id"], projects_root=projects)[0]
    assert result["review_status"] == "pending_review" and all(result["qa"]["checks"].values())
    assert result["qa"]["loudness"]["acceptance_status"] == "passed"
    assert all(not row["hit"] for row in result["cache"])
    assert file_sha256(request_path) == request_hash
    assert read_json(request_path)["sources"][media_id]["path"] == str(source)

    changed = deepcopy(draft)
    changed["payload"]["segments"][0]["shots"][0]["start"] = 2.7
    newer = flow.save(draft["id"], changed, projects_root=projects)
    assert newer["revision"] > draft["revision"]
    with pytest.raises(CommentaryError, match="归档"):
        flow.submit(draft["id"], newer["revision"], queue, projects_root=projects)
    assert refs.list_usage(project_id=draft["id"]) == usages
    assert len(flow.versions(draft["id"], projects_root=projects)) == 1
    assert flow.output_path(draft["id"], signature, projects_root=projects) == output
