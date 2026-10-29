"""Consumer-level management contracts; all data is isolated from the live library."""
import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backlot import material_library as library
from backlot.material_library_api import router
from scripts.material_library_manage_cli import main

BASE = "/api/material-library/manage"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENMONTAGE_MATERIAL_LIBRARY_DIR", str(tmp_path / "library"))
    path = tmp_path / "source.mp4"
    path.write_bytes(b"stable-media-contract-fixture")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    mid = "MAT-" + sha
    # Media decoding is exercised by the original library test suite. This fixture
    # isolates management/reference behavior and hashes actual bytes on disk.
    library.register_prepared([{"id": mid, "sha256": sha, "path": str(path),
        "bytes": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns,
        "title": "测试现场", "duration": 120, "width": 720, "height": 1280,
        "origin": {"platform": "local", "source_url": "", "video_id": "", "rights_status": "unknown", "catalog": "test"}}])
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        yield client, mid, path, tmp_path


def test_http_management_cas_and_old_routes(setup):
    client, mid, path, tmp = setup
    assert client.get("/material-library").status_code == 200
    assert client.get("/material-library/manage").status_code == 200
    assert client.get("/api/material-library/status").json()["media"] == 1
    result = client.get(BASE + "/search", params={"query": "测试", "aspect": "portrait"}).json()
    assert result["total"] == 1
    item = result["items"][0]
    patch = {"items": [{"media_id": mid, "expected_revision": item["metadata"]["revision"]}],
             "patch": {"tags": ["粤仔"], "collections": ["实片验收"]}}
    assert client.post(BASE + "/metadata", json=patch).status_code == 200
    assert client.post(BASE + "/metadata", json=patch).status_code == 409
    assert client.get(BASE + "/search", params={"tag": "粤仔"}).json()["total"] == 1
    assert client.get(BASE + "/search", params={"max_duration": -1}).status_code == 422
    assert client.post(BASE + f"/media/{mid}/health").status_code == 200
    assert client.get(BASE + f"/media/{mid}").json()["health"]["status"] == "valid"
    assert client.post(BASE + f"/media/{mid}/relink", json={"path": ""}).status_code == 422
    assert client.get(BASE + f"/media/{mid}").json()["usage"] == []


def test_independent_consumer_import_observation_freeze_usage_and_conflict(setup):
    client, mid, path, tmp = setup
    payload = {"project_id": "film-demo", "project_version": "v1", "sources": [{
        "asset_id": "S-001", "path": str(path), "expected_sha256": mid[4:],
        "metadata": {"platform": "local"}, "aliases": [{"namespace": "external-demo", "external_id": "one"}]}]}
    one = client.post(BASE + "/project-import", json=payload)
    assert one.status_code == 200, one.text
    two = client.post(BASE + "/project-import", json=payload)
    assert two.json() == one.json()
    assert client.get(BASE + "/aliases", params={"namespace": "external-demo", "external_id": "one"}).json()["media_id"] == mid
    observation = client.post(BASE + "/observations", json={"media_id": mid, "source_in": 10,
        "source_out": 60, "observation": "游客问答", "facts": {"text": "问答", "source_audio": "speech", "subtitles": "burned_in"},
        "review_status": "candidate", "scope": "source-content"})
    assert observation.status_code == 200, observation.text
    reference = client.post(BASE + "/references", json={"media_id": mid, "source_in": 20,
        "source_out": 55, "usage_intent": "直播问答原声", "observation_id": observation.json()["id"]})
    assert reference.status_code == 200, reference.text
    ref = reference.json()
    use = {"project_id": "film-demo", "project_version": "v1", "asset_id": "S-001",
           "scene_id": "answer", "slot_id": "shot-1", "ref_id": ref["id"]}
    first = client.post(BASE + "/usage", json=use)
    assert first.status_code == 200, first.text
    assert client.post(BASE + "/usage", json=use).json() == first.json()
    other = client.post(BASE + "/references", json={"media_id": mid, "source_in": 21,
        "source_out": 55, "usage_intent": "另一个版本"}).json()
    assert client.post(BASE + "/usage", json={**use, "ref_id": other["id"]}).status_code == 409
    assert len(client.get(BASE + "/usage", params={"project_id": "film-demo"}).json()) == 1
    detail = client.get(BASE + f"/media/{mid}").json()
    assert len(detail["observations"]) == len(detail["usage"]) == 1
    assert client.post(BASE + "/metadata", json={"items": [{"media_id": mid, "expected_revision": 0}], "patch": {"archived": True}}).status_code == 200
    assert client.get(BASE + "/search").json()["total"] == 0
    assert client.get(BASE + f"/references/{ref['id']}").json() == ref
    assert client.get(BASE + f"/references/{ref['id']}/resolve").status_code == 200
    path.write_bytes(b"tampered-content")
    assert client.get(BASE + f"/references/{ref['id']}/resolve").status_code == 422


def test_cli_and_http_share_results_and_conflict_exit_code(setup):
    client, mid, path, tmp = setup
    out = tmp / "out.json"
    assert main(["--output", str(out), "search", "--query", "测试"]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["total"] == 1
    payload = tmp / "update.json"
    payload.write_text(json.dumps({"items": [{"media_id": mid, "expected_revision": 0}],
                                  "patch": {"notes": "原声问答"}}), encoding="utf-8")
    assert main(["metadata", str(payload)]) == 0
    assert main(["metadata", str(payload)]) == 3
    assert main(["--output", str(out), "detail", mid]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["metadata"]["notes"] == "原声问答"
