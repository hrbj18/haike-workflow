"""The explicit learning CLI cannot authorize production or silently repeat a run."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot import material_library, material_library_api, material_library_manage_api
from backlot import studio_avatar, studio_render, studio_storyboard
from backlot import studio_douyin_learning as learning
from backlot.studio import Studio, atomic_private
from backlot.work_catalog import WorkError


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("HAIKE_LOCAL_LEARNING_TEST", "1")
    monkeypatch.setenv("OPENMONTAGE_MATERIAL_LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setattr(material_library, "ROOT", tmp_path / "Haike_video")
    monkeypatch.setattr(material_library, "probe", lambda path: {"duration": 8, "width": 1280, "height": 720})
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "copy_skill/copy_skill-main/src"))
    from douyin_intelligence.sources.douyin import DouyinSource
    studio = Studio(tmp_path / "projects")
    atomic_private(studio.private / "studio-ai/relay.json", {"douyin_commercial_authorized": False})
    monkeypatch.setattr(learning, "download_account", lambda s: (17, None, {"status": "ready"}))
    monkeypatch.setattr(learning, "crawler_config", lambda s, out: {"media_crawler": {"download_account_id": 17}})
    candidate = SimpleNamespace(video_id="7686317511540821299", title="机器人示例", author="fixture",
                                duration_seconds=8, media_is_audio=False)
    searches, downloads, api_calls = [], [], []

    def search(self, keywords, budget, **kwargs):
        searches.append((keywords, budget, kwargs))
        return SimpleNamespace(status="success", candidates=[candidate])

    def download(url, path, **kwargs):
        downloads.append((url, path, kwargs))
        path.write_bytes(b"new-test-video")

    monkeypatch.setattr(DouyinSource, "search", search)
    monkeypatch.setattr(DouyinSource, "resolve_media_url", lambda s, item: "https://cdn.example/video?signature=PRIVATE_SIGNED_URL")
    monkeypatch.setattr(studio_avatar, "download_result", download)
    monkeypatch.setattr(studio_render, "media_probe", lambda path: {"video": {"width": 1280}, "duration": 8})
    app = FastAPI()
    app.include_router(material_library_api.router)
    app.include_router(material_library_manage_api.router)

    @app.post("/api/studio/download-sessions/{account_id}/check")
    def check(account_id: int):
        return {"ok": True, "account": {"id": account_id, "platform": "douyin", "download_status": "available"}}

    with TestClient(app) as client:
        def api(base, path, payload=None, *, allow_missing=False):
            api_calls.append(path)
            response = client.get(path) if payload is None else client.post(path, json=payload)
            if allow_missing and response.status_code == 404:
                return None
            if response.status_code >= 400:
                raise WorkError("fixture API rejected operation")
            return response.json()
        monkeypatch.setattr(learning, "local_api", api)
        yield SimpleNamespace(studio=studio, candidate=candidate, searches=searches, downloads=downloads,
                              api_calls=api_calls, api=api, client=client, root=tmp_path)


def run(fixture, run_id="test-run", **kwargs):
    return learning.run_learning_test(fixture.studio, run_id=run_id,
                                      purpose="learning_test", confirmed=True, **kwargs)


def test_learning_is_default_off_and_requires_explicit_scope_and_confirmation(fixture, monkeypatch):
    monkeypatch.delenv("HAIKE_LOCAL_LEARNING_TEST")
    with pytest.raises(WorkError, match="默认关闭"):
        run(fixture)
    monkeypatch.setenv("HAIKE_LOCAL_LEARNING_TEST", "1")
    for purpose, confirm in (("commercial", True), ("learning_test", False), ("learning_test", 1)):
        with pytest.raises(WorkError, match="默认关闭"):
            learning.run_learning_test(fixture.studio, run_id="no-run", purpose=purpose, confirmed=confirm)
    assert not fixture.searches and not fixture.api_calls


def test_one_real_registration_api_path_preserves_learning_rights_and_safe_candidates(fixture):
    result = run(fixture)
    assert result["status"] == "completed" and result["new_file"] is True
    assert result["new_library_media"] is True and len(fixture.downloads) == 1
    assert fixture.searches[0][:2] == (["机器人"], 10)
    assert fixture.downloads[0][2] == {"referer": "https://www.douyin.com/", "max_bytes": 50 * 1024 * 1024}
    detail = fixture.client.get("/api/material-library/manage/media/" + result["media_id"]).json()
    assert detail["origins"][0]["rights_status"] == "local_learning_only"
    assert "学习测试" in detail["metadata"]["tags"]
    assert detail["origins"][0]["source_url"] == "https://www.douyin.com/video/7686317511540821299"
    folder = fixture.studio.private / "local-learning/douyin/test-run"
    for path in folder.glob("*.json"):
        assert "PRIVATE_SIGNED_URL" not in path.read_text(encoding="utf-8")
    assert studio_storyboard.configuration(fixture.studio)["douyin_commercial_authorized"] is False


def test_same_sha_adds_new_location_but_never_claims_a_second_library_asset(fixture):
    first = run(fixture, "first")
    media_id = first["media_id"]
    fixture.client.post("/api/material-library/manage/metadata", json={
        "items": [{"media_id": media_id, "expected_revision": 1}],
        "patch": {"tags": ["existing-user-tag"], "notes": "user note", "archived": True},
    }).raise_for_status()
    second = run(fixture, "second")
    assert second["media_id"] == media_id
    assert second["new_file"] is True and second["new_library_media"] is False
    assert second["baseline"]["preexisting_media"] is True
    assert second["baseline"]["prior_locations"] == [first["artifact"]["path"]]
    detail = fixture.client.get("/api/material-library/manage/media/" + media_id).json()
    assert len(detail["locations"]) == 2
    assert detail["metadata"]["archived"] is True
    assert "existing-user-tag" in detail["metadata"]["tags"]
    assert detail["metadata"]["notes"].startswith("user note")


def test_registration_retry_reuses_exact_file_without_search_or_download(fixture, monkeypatch):
    def failing_import(base, path, payload=None, **kwargs):
        if path == "/api/material-library/import":
            raise WorkError("fixture registration unavailable")
        return fixture.api(base, path, payload, **kwargs)
    monkeypatch.setattr(learning, "local_api", failing_import)
    with pytest.raises(WorkError, match="registration unavailable"):
        run(fixture)
    monkeypatch.setattr(learning, "local_api", fixture.api)
    result = run(fixture, register_only=True)
    assert result["status"] == "completed"
    assert len(fixture.searches) == len(fixture.downloads) == 1
    assert result["baseline"]["preexisting_media"] is False
    with pytest.raises(WorkError, match="未重复采集"):
        run(fixture)


def test_registration_rejects_changed_catalog_or_video(fixture, monkeypatch):
    original = fixture.api
    monkeypatch.setattr(learning, "local_api", lambda base, path, payload=None, **kwargs:
                        (_ for _ in ()).throw(WorkError("stop"))
                        if path == "/api/material-library/import" else original(base, path, payload, **kwargs))
    with pytest.raises(WorkError):
        run(fixture)
    folder = fixture.studio.private / "local-learning/douyin/test-run"
    catalog = folder / "00-素材目录.json"
    body = json.loads(catalog.read_text(encoding="utf-8"))
    body["entries"][0]["rights_status"] = "confirmed"
    atomic_private(catalog, body)
    monkeypatch.setattr(learning, "local_api", original)
    with pytest.raises(WorkError, match="摘要已变化"):
        run(fixture, register_only=True)
    assert len(fixture.searches) == len(fixture.downloads) == 1


def test_search_only_and_out_of_budget_candidates_never_download(fixture):
    result = run(fixture, "search", search_only=True)
    assert result["status"] == "searched" and result["candidate_count"] == 1
    assert not fixture.downloads
    fixture.candidate.duration_seconds = 61
    with pytest.raises(WorkError, match="5至60秒"):
        run(fixture, "too-long")
    assert not fixture.downloads
    assert "/api/material-library/import" not in fixture.api_calls


def test_learning_flag_does_not_authorize_production_sources_or_login(fixture):
    with pytest.raises(WorkError, match="商用授权"):
        studio_storyboard.Sources(fixture.studio, None, None, None).douyin({"query": "机器人"})
    with pytest.raises(WorkError, match="商用授权"):
        studio_storyboard.login_prepare(fixture.studio)
    assert not fixture.searches


def test_human_verification_stops_without_download_or_private_error(fixture, monkeypatch):
    from douyin_intelligence.sources.douyin import DouyinSource
    monkeypatch.setattr(DouyinSource, "search", lambda *args, **kwargs: SimpleNamespace(
        status="failed", candidates=[], report={"needs_human_verification": True,
                                                 "error": "PRIVATE_UPSTREAM_DETAIL"}))
    with pytest.raises(WorkError, match="需要人工确认") as result:
        run(fixture)
    assert "PRIVATE_UPSTREAM_DETAIL" not in str(result.value)
    assert not fixture.downloads
    assert "/api/material-library/import" not in fixture.api_calls


def test_learning_api_never_connects_to_non_loopback_or_redirected_host(monkeypatch):
    monkeypatch.setattr(learning.request, "build_opener", lambda *_:
                        pytest.fail("must reject URL before network opener"))
    for base in ("https://127.0.0.1:14756", "http://outside.example", "http://user:secret@127.0.0.1",
                 "http://127.0.0.1/path", "http://127.0.0.1?key=fixture"):
        with pytest.raises(WorkError, match="回环地址"):
            learning.local_api(base, "/api/material-library/status")
