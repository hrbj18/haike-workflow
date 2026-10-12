"""Strict cover package and durable submission checks; no live browser."""
import asyncio
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from pathlib import Path

import httpx
from PIL import Image
from sqlmodel import select
from unittest.mock import AsyncMock, patch

import app.db as db
import app.main as main
from app.models import DouyinAccount, PublishTask
from app.engine.monitor import MonitorEngine
from app.publish_contract import file_sha256
from tests.douyin_cover_fakes import run_publish as run_douyin_fake
from test_kuaishou_cover import _run_publish as run_kuaishou_fake
from app.platforms.channels import publish as channels
from test_project_optimizations import local_project, store


def _image(path, size=(600, 800)):
    Image.new("RGB", size, "#193043").save(path, "JPEG")


def _proof(root, cover):
    source = root / "generated-source.png"
    Image.new("RGB", (800, 800), "#193043").save(source, "PNG")
    proof = root / "cover-proof.json"
    proof.write_text(json.dumps({
        "kind": "ai_generated", "model": "fixture-model",
        "source_image_path": str(source),
        "source_image_sha256": file_sha256(source),
        "final_cover_sha256": file_sha256(cover),
    }), encoding="utf-8")
    return proof


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                             base_url="http://127.0.0.1")


def test_v2_required_cover_and_package_dedupe(local_project):
    account = store(DouyinAccount(platform="douyin", storage_state="{}"))
    video = local_project.root / "clip.mp4"
    video.write_bytes(b"video fixture")
    cover = local_project.root / "cover.jpg"
    _image(cover)
    proof = _proof(local_project.root, cover)
    body = {"account_id": account, "media_type": "video", "media_paths": [str(video)],
            "cover_path": str(cover), "title": "fixture", "contract_version": 2,
            "expected_platform": "douyin", "package_id": "fixture-package-0001",
            "package_revision": 1, "cover_policy": "required",
            "cover_origin": "generated_ai", "video_sha256": file_sha256(video),
            "cover_sha256": file_sha256(cover), "location_mode": "keep",
            "cover_proof_path": str(proof), "cover_proof_sha256": file_sha256(proof),
            "source_rights_status": "confirmed"}

    async def scenario():
        async with _client() as http:
            assert (await http.get("/api/publish/capabilities")).json()["contract_version"] == 2
            missing = await http.post("/api/publish", json={**body, "cover_path": ""})
            assert missing.status_code == 422
            unproven = await http.post("/api/publish", json={**body, "cover_proof_path": ""})
            assert unproven.status_code == 422
            rights_unknown = await http.post("/api/publish", json={**body, "source_rights_status": "unknown"})
            assert rights_unknown.status_code == 422
            optional_ai = await http.post("/api/publish", json={**body, "cover_policy": "optional"})
            assert optional_ai.status_code == 422
            first = await http.post("/api/publish", json=body,
                                    headers={"Idempotency-Key": "fixture-publish-v2-0001"})
            assert first.status_code == 200, first.text
            assert first.json()["cover_status"] == "pending"
            assert first.json()["acceptance_status"] == "pending"
            assert (await http.delete(f"/api/publish/{first.json()['id']}")).status_code == 409
            replay = await http.post("/api/publish", json=body,
                                     headers={"Idempotency-Key": "fixture-publish-v2-0001"})
            assert replay.status_code == 200 and replay.json()["id"] == first.json()["id"]
            new_key = await http.post("/api/publish", json=body,
                                      headers={"Idempotency-Key": "fixture-publish-v2-0002"})
            assert new_key.status_code == 200 and new_key.json()["id"] == first.json()["id"]
            conflict = await http.post("/api/publish", json={**body, "title": "changed"},
                                       headers={"Idempotency-Key": "fixture-publish-v2-0003"})
            assert conflict.status_code == 409
            cover.write_bytes(b"bad image")
            changed = await http.post("/api/publish", json={**body, "package_revision": 2},
                                      headers={"Idempotency-Key": "fixture-publish-v2-0004"})
            assert changed.status_code == 422
            with db.get_session() as session:
                task = session.get(PublishTask, first.json()["id"])
                task.status = "done"
                session.add(task); session.commit()
            evidence = local_project.root / "evidence.png"
            Image.new("RGB", (400, 300), "white").save(evidence, "PNG")
            review = await http.put(f"/api/publish/{first.json()['id']}/acceptance", json={
                "work_id": "unique-work-1", "evidence_path": str(evidence),
                "unique_work": True, "video_matches": True,
                "title_matches": True, "cover_matches": False})
            assert review.status_code == 200
            assert review.json()["acceptance_status"] == "needs_review"
            assert review.json()["cover_status"] == "failed"
            with db.get_session() as session:
                assert len(session.exec(select(PublishTask)).all()) == 1
    asyncio.run(scenario())


def test_strict_douyin_and_kuaishou_never_click_after_cover_failure(local_project):
    media = local_project.root / "fixture.mp4"
    media.write_bytes(b"video fixture")
    cover = local_project.root / "cover.jpg"
    _image(cover)

    async def bad_cover(*_args):
        return "预览未确认"

    async def scenario():
        for runner in (run_douyin_fake, run_kuaishou_fake):
            marked = []
            result = await runner(str(media), str(cover), bad_cover,
                                  cover_required=True,
                                  on_submit=lambda: marked.append("submit"))
            assert not result["ok"]
            assert result["btn"].clicked == 0
            assert marked == []
            async def good_cover(*_args):
                return ""
            def marker_fails():
                raise RuntimeError("database unavailable")
            unmarked = await runner(str(media), str(cover), good_cover,
                                    cover_required=True, on_submit=marker_fails)
            assert not unmarked["ok"]
            assert unmarked["btn"].clicked == 0
            marked = []
            ambiguous = await runner(str(media), str(cover), good_cover,
                                     cover_required=True, click_error=True,
                                     on_submit=lambda: marked.append("submit"))
            assert not ambiguous["ok"]
            assert "write_uncertain:" in ambiguous["err"]
            assert ambiguous["btn"].clicked == 1
            assert marked == ["submit"]
    asyncio.run(scenario())


def test_strict_channels_never_click_after_cover_failure(local_project):
    media = local_project.root / "fixture.mp4"
    media.write_bytes(b"video fixture")
    cover = local_project.root / "cover.jpg"
    _image(cover)
    clicked = []

    class Field:
        value = ""
        async def set_input_files(self, *_args, **_kwargs):
            return None
        async def fill(self, value):
            self.value = value
        async def input_value(self):
            return self.value
        async def click(self, **_kwargs):
            clicked.append("field")
    class Page:
        url = ""
        keyboard = type("Keyboard", (), {"type": AsyncMock()})()
        async def goto(self, url, **_kwargs):
            self.url = url
        async def wait_for_timeout(self, *_args):
            return None
        async def close(self):
            return None
    class Context:
        async def new_page(self):
            return Page()
        async def close(self):
            return None
    class Manager:
        async def open_background(self, _identity):
            return Context()
        async def stop_minimize_hold(self, _identity):
            return None
    field = Field()
    button = Field()
    async def find(_page, selectors):
        if selectors is channels._PUBLISH_BTN:
            return button, None
        return field, None
    with patch.object(channels, "_verify_on_post_list", AsyncMock(return_value=(False, ""))), \
         patch.object(channels, "_wait_create_ready", AsyncMock(return_value=True)), \
         patch.object(channels, "_dismiss_overlays", AsyncMock()), \
         patch.object(channels, "_wait_video_ready", AsyncMock(return_value=True)), \
         patch.object(channels, "_find_in_frames", find), \
         patch.object(channels, "_clear_location", AsyncMock(return_value="")), \
         patch.object(channels, "_set_cover", AsyncMock(return_value="预览未确认")), \
         patch.object(channels, "_dump", AsyncMock(return_value="fixture.png")):
        result = asyncio.run(channels.publish_channels(
            Manager(), None, "", "video", "阿里真武V900", "description",
            [str(media)], cover_path=str(cover), cover_required=True,
            location_mode="clear", on_submit=lambda: clicked.append("submit")))
    assert not result[0]
    assert clicked == ["field"]


def test_v2_submit_marker_survives_restart_without_requeue(local_project):
    account = store(DouyinAccount(platform="douyin", status="active", storage_state="{}"))
    video = local_project.root / "fixture.mp4"
    video.write_bytes(b"video fixture")
    cover = local_project.root / "cover.jpg"
    _image(cover)
    task_id = store(PublishTask(
        platform="douyin", account_id=account, media_type="video",
        media_json=json.dumps([str(video)]), cover_path=str(cover),
        video_sha256=file_sha256(video), cover_sha256=file_sha256(cover),
        contract_version=2, cover_policy="required", status="pending"))
    class Browser:
        def lock_for(self, _key):
            return asyncio.Lock()
        def identity_for(self, _account):
            return None
    local_project.cfg.engine.quiet_hours_enabled = False
    engine = MonitorEngine(local_project.cfg, Browser())
    engine._native_write_environment_error = lambda *_args, **_kwargs: ""
    engine._proxy_bad = lambda *_args: False
    engine._task_deferral = lambda *_args: None
    engine._write_pause_error = lambda *_args: ""
    engine._in_active_window = lambda *_args: True
    engine.risk.preflight = lambda *_args: SimpleNamespace(allowed=True)
    calls = []
    async def ambiguous(*_args, **kwargs):
        calls.append(1)
        kwargs["on_submit"]()
        return False, "", "click timeout"
    with patch("app.engine.monitor.publish_douyin", ambiguous):
        result = asyncio.run(engine.publish_task(task_id))
        assert not result["ok"]
        with db.get_session() as session:
            assert session.get(PublishTask, task_id).status == "uncertain"
        db._engine.dispose()
        db.init_db(str(local_project.path))
        asyncio.run(engine._process_publish())
    assert calls == [1]
    with db.get_session() as session:
        assert session.get(PublishTask, task_id).acceptance_status == "needs_review"


def test_legacy_publish_row_migrates_without_claiming_cover_verified(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE publishtask (id INTEGER PRIMARY KEY, platform TEXT, account_id INTEGER, media_json TEXT, status TEXT, created_at DATETIME)")
        connection.execute("INSERT INTO publishtask VALUES (5, 'douyin', 1, '[\"legacy.mp4\"]', 'done', '2026-01-01 00:00:00')")
    previous = db._engine
    try:
        db.init_db(str(path))
        with db.get_session() as session:
            task = session.get(PublishTask, 5)
            assert task.status == "done"
            assert task.contract_version == 1
            assert task.cover_status == "not_checked"
            assert task.acceptance_status == "not_checked"
            assert json.loads(task.media_json) == ["legacy.mp4"]
    finally:
        db._engine.dispose()
        db._engine = previous


def test_v2_distinct_receipt_keys_race_to_one_task(local_project):
    account = store(DouyinAccount(platform="douyin", storage_state="{}"))
    video = local_project.root / "video.mp4"
    video.write_bytes(b"fixture video")
    cover = local_project.root / "cover.jpg"
    _image(cover)
    payload = {"account_id": account, "media_type": "video", "media_paths": [str(video)],
               "cover_path": str(cover), "title": "fixture", "contract_version": 2,
               "expected_platform": "douyin", "package_id": "fixture-race-package-001",
               "package_revision": 1, "cover_policy": "required",
               "cover_origin": "provided_image", "video_sha256": file_sha256(video),
               "cover_sha256": file_sha256(cover), "source_rights_status": "owned"}
    barrier = threading.Barrier(4)
    def worker(index):
        barrier.wait()
        async def call():
            async with _client() as http:
                response = await http.post("/api/publish", json=payload, headers={
                    "Idempotency-Key": f"fixture-race-receipt-{index:04d}"})
                return response.status_code, response.json()
        return asyncio.run(call())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(worker, range(4)))
    assert all(code == 200 for code, _ in results), results
    assert len({body["id"] for _, body in results}) == 1
    with db.get_session() as session:
        assert len(session.exec(select(PublishTask)).all()) == 1
