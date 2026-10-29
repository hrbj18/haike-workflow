from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backlot import material_library as lib
from backlot import material_library_evidence as ev
from backlot import material_library_selection as sel
from backlot.material_crop import normalize_crop, template_filter
from backlot.material_library_template import indexed_pick, text_is_approved, validate_spec, product_region_is_approved
from backlot.material_library_api import router
from lib.ffmpeg_locator import resolve_ffmpeg_pair


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    path = tmp_path_factory.mktemp("media") / "fixture.mp4"
    pair = resolve_ffmpeg_pair()
    if not pair: pytest.skip("FFmpeg unavailable")
    # Green subject, red caption band: cropping must remove red without losing
    # the subject. Real decode fixtures exercise the media boundary.
    subprocess.run([pair[0], "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240:r=30",
                    "-vf", "drawbox=x=0:y=200:w=320:h=40:color=red:t=fill", "-t", "12", "-an",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True, timeout=40)
    return path


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENMONTAGE_MATERIAL_LIBRARY_DIR", str(tmp_path / "library"))
    return tmp_path / "library/library.sqlite3"


def media(video, db):
    return lib.register_file(video, {"platform": "douyin", "source_url": "https://www.douyin.com/video/123", "video_id": "123"}, db_path=db)["media_ids"][0]


def confirmed(video, db, *, windows=None, brands=None, entities=None, quality=70):
    mid = media(video, db)
    windows = windows or [{"media_id": mid, "start": start, "end": start + 3,
                           "crop": {"x": 0, "y": 0, "w": 1, "h": .8}} for start in (0, 3, 6)]
    task = ev.prepare_task({"model": "test-reviewer", "windows": windows}, db_path=db)
    submission = copy.deepcopy(task["submission_template"])
    for review in submission["reviews"]:
        review.update({"observation": "芯片设备", "brands": brands if brands is not None else ["华为"],
                       "entities": entities if entities is not None else ["昇腾950"], "series": ["昇腾"],
                       "domains": ["算力"], "usable": True, "subject_retained": True,
                       "captions_obscure_subject": False, "identity_basis": "测试画面证据", "quality": quality})
    return task, submission, ev.submit_task(submission, db_path=db)


def test_registry_deduplicates_content_preserves_origins_and_multiple_roots(video, db, tmp_path):
    other = tmp_path / "second/video.mp4"; other.parent.mkdir(); shutil.copyfile(video, other)
    a = lib.register_file(video, {"platform": "local"}, db_path=db)
    b = lib.register_file(other, {"platform": "douyin", "source_url": "https://www.douyin.com/video/123"}, db_path=db)
    assert a["media_ids"] == b["media_ids"]
    lib.register_file(other, {"platform": "douyin", "source_url": "https://www.douyin.com/video/123"}, db_path=db)
    assert lib.summary(db_path=db)["media"] == 1
    record = lib.get_media(a["media_ids"][0], db_path=db)
    assert len(record["locations"]) == 2 and len(record["origins"]) == 2
    other.unlink()
    assert lib.resolve_media(record["id"], db_path=db) == video.resolve()


def test_same_size_replacement_cannot_use_old_evidence(video, db, tmp_path):
    path = tmp_path / "copy.mp4"; shutil.copyfile(video, path)
    mid = media(path, db); stat = path.stat()
    data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(lib.MaterialLibraryError, match="变化"): lib.resolve_media(mid, db_path=db)


def catalog(video, tmp_path):
    delivery = tmp_path / "delivery"; delivery.mkdir(exist_ok=True)
    path = delivery / "video.mp4"; shutil.copyfile(video, path)
    manifest = delivery / "清单.json"
    manifest.write_text(json.dumps({"schema_version": 1, "mode": "download_only", "downloads": [{
        "video_id": "123", "title": "950现场", "source_url": "https://www.douyin.com/video/123",
        "file": "video.mp4", "size_bytes": path.stat().st_size, "duration_seconds": 12}]}), encoding="utf-8")
    return manifest


def test_catalog_ingest_idempotent_atomic_invalid_batch(video, db, tmp_path):
    path = catalog(video, tmp_path)
    assert lib.ingest_catalog(path, workspace_root=tmp_path, db_path=db)["registered"] == 1
    assert lib.ingest_catalog(path, workspace_root=tmp_path, db_path=db)["registered"] == 1
    assert lib.summary(db_path=db)["media"] == 1
    raw = json.loads(path.read_text()); raw["downloads"].append({**raw["downloads"][0], "video_id": "456", "file": "missing.mp4"})
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError): lib.ingest_catalog(path, workspace_root=tmp_path, db_path=db)
    assert lib.summary(db_path=db)["media"] == 1


def test_corrupt_media_not_registered(db, tmp_path):
    bad = tmp_path / "bad.mp4"; bad.write_bytes(b"invalid video")
    result = lib.scan_folder(tmp_path, db_path=db)
    assert result["registered"] == 0 and result["failures"]
    assert lib.summary(db_path=db)["media"] == 0


@pytest.mark.parametrize("crop", [{"x": 0, "y": 0, "w": 1.1, "h": 1}, {"x": .5, "y": 0, "w": .8, "h": 1},
                                   {"x": 0, "y": 0, "w": float("nan"), "h": 1}, {"x": 0, "y": 0, "w": True, "h": 1},
                                   {"x": 0, "y": 0, "w": 1, "h": .01}])
def test_invalid_crops_rejected(crop):
    with pytest.raises(lib.MaterialLibraryError): normalize_crop(crop)


def test_evidence_cached_cropped_subject_and_submission_immutable(video, db):
    task, submission, saved = confirmed(video, db)
    assert len(task["windows"][0]["sheets"]) == 3  # 9 cropped frames / 6 per page + source context
    repeated = ev.prepare_task({"model": "test-reviewer", "windows": task["identity"]["windows"]}, db_path=db)
    assert repeated["cached"]
    assert ev.submit_task(submission, db_path=db) == saved
    revised = ev.prepare_task({"model": "test-reviewer", "review_revision": "复核2", "windows": task["identity"]["windows"]}, db_path=db)
    assert revised["id"] != task["id"] and not revised.get("completed", False)
    assert ev.read_task(task["id"], db_path=db)["review_result"] == submission
    crop_image = ev.task_directory(task["id"], db) / task["windows"][0]["sheets"][0]["file"]
    with Image.open(crop_image) as image:
        pixels = list(image.crop((0, 31, 384, 250)).getdata())
        assert not any(r > 150 and g < 80 for r, g, b in pixels), "caption red must be outside rendered crop"
    submission["reviews"][0]["observation"] = "different"
    with pytest.raises(lib.MaterialLibraryError, match="覆盖"): ev.submit_task(submission, db_path=db)


def test_tampered_evidence_and_missing_review_rejected(video, db):
    mid = media(video, db)
    task = ev.prepare_task({"model": "r", "windows": [{"media_id": mid, "start": 0, "end": 3}]}, db_path=db)
    submission = task["submission_template"]
    submission["reviews"][0].update({"observation": "设备", "quality": 50})
    submission["reviews"][0]["reviewed_sheets"] = []
    with pytest.raises(lib.MaterialLibraryError, match="查看"): ev.submit_task(submission, db_path=db)
    path = ev.task_directory(task["id"], db) / task["windows"][0]["sheets"][0]["file"]
    path.write_bytes(b"changed")
    with pytest.raises(lib.MaterialLibraryError, match="修改"): ev.submit_task(submission, db_path=db)


def test_subject_lost_and_caption_remaining_cannot_be_usable(video, db):
    mid = media(video, db)
    task = ev.prepare_task({"model": "r", "windows": [{"media_id": mid, "start": 0, "end": 3}]}, db_path=db)
    s = copy.deepcopy(task["submission_template"])
    s["reviews"][0].update({"observation": "字幕仍压住设备", "quality": 50, "usable": True})
    with pytest.raises(lib.MaterialLibraryError, match="主体"): ev.submit_task(s, db_path=db)


def test_grade_is_topic_relative_not_title_and_conflicting_brand_excluded():
    plan = sel.default_plan("昇腾950")
    c = {"review_status": "confirmed", "metadata": {"usable": True, "entities": ["昇腾950"], "brands": ["华为"],
                                                   "identity_basis": "展台标识", "domains": ["算力"], "series": ["昇腾"]}}
    assert sel.grade(c, plan)[0] == "A"
    c["metadata"]["entities"] = ["昇腾910"]
    assert sel.grade(c, plan)[0] == "B"
    c["metadata"]["series"] = []
    assert sel.grade(c, plan)[0] == "C"
    c["metadata"]["brands"] = ["曙光"]
    assert sel.grade(c, plan)[0] == "conflict"
    c["metadata"]["brands"] = []; c["metadata"]["entities"] = []
    assert sel.grade(c, plan)[0] == "D"
    c["review_status"] = "candidate"
    assert sel.grade(c, plan)[0] == "unknown"
    c["review_status"] = "confirmed"; c["metadata"].update({"brands": ["华为"], "domains": ["手机"]})
    assert sel.grade(c, plan)[0] == "unknown"
    c["metadata"]["tags"] = ["brand_logo"]
    assert sel.grade(c, plan)[0] == "C"


def test_grade_beats_quality_and_conflict_has_no_coverage(video, db):
    task, submission, saved = confirmed(video, db, quality=10)
    plan = sel.default_plan("昇腾950")
    assert sel.select(plan, db_path=db)["status"] == "ready"
    with lib.connect(db) as conn:
        row = conn.execute("SELECT * FROM clips LIMIT 1").fetchone(); meta = json.loads(row["metadata"])
        meta.update({"brands": [], "entities": [], "series": [], "quality": 100})
        conn.execute("INSERT INTO clips VALUES(?,?,?,?,?,?,?,?,?)", ("industry",row["media_id"],9,12,"通用机房","confirmed",json.dumps(meta),row["task_id"],lib.now()))
    candidates = sel.compact_candidates(plan, db_path=db)
    assert [c["grade"] for c in candidates["candidates"]] == ["A", "A", "A", "D"]
    assert len(json.dumps(candidates, ensure_ascii=False)) < 12000


def test_acquisition_reentrant_bounded_and_existing_library_first(video, db):
    plan = sel.default_plan("昇腾950")
    first = sel.acquisition_request(plan, db_path=db)
    assert first["round"] == 1 and first["layers"][0]["grade"] == "A"
    assert sel.acquisition_request(plan, db_path=db)["id"] == first["id"]
    report = {"status": "search_no_results", "queries_used": ["昇腾950 真机"], "detail": "本轮未返回候选"}
    done = sel.finish_acquisition(first["id"], report, db_path=db)
    assert sel.finish_acquisition(first["id"], report, db_path=db) == done
    second = sel.acquisition_request(plan, db_path=db)
    assert any("华为" in q for layer in second["layers"] for q in layer["queries"])
    sel.finish_acquisition(second["id"], {**report, "status": "download_limited"}, db_path=db)
    assert sel.acquisition_request(plan, db_path=db)["status"] == "budget_exhausted"
    old = sel.selection_history(plan["id"], db_path=db)
    confirmed(video, db)
    new = sel.select(plan, db_path=db)
    assert new["status"] == "ready" and old[0]["status"] == "needs_material"
    assert sel.acquisition_request(plan, db_path=db)["status"] == "not_required"


def test_indexed_spec_matches_evidence_and_old_specs_remain_compatible(video, db, tmp_path):
    confirmed(video, db)
    result = indexed_pick("t25", "昇腾950", [], tmp_path / "out", db_path=db)
    spec = json.loads(Path(result["spec_path"]).read_text(encoding="utf-8"))
    assert validate_spec(spec, db_path=db)
    assert spec[0]["render_transform"] == template_filter(spec[0]["source_crop"])
    assert len(spec) == 3 and {c["grade"] for c in spec} == {"A"}
    spec[0]["source_in"] += .5
    with pytest.raises(lib.MaterialLibraryError, match="冻结"): validate_spec(spec, db_path=db)
    assert not validate_spec([{"cue": str(i)} for i in range(3)], db_path=db)
    assert text_is_approved("昇腾 950", ["昇腾950"])
    assert text_is_approved("升腾950超节点A", ["昇腾950超节点 Atlas950 SuperPoD"])
    assert not text_is_approved("950", ["昇腾950超节点 Atlas950"])
    assert not text_is_approved("关注我了解昇腾950", ["昇腾950"])


def test_api_status_query_crop_errors_and_evidence_scoping(video, db):
    confirmed(video, db)
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/material-library").status_code == 200
        assert client.get("/api/material-library/status").json()["clips"] == 3
        assert len(client.get("/api/material-library/search?query=芯片").json()["clips"]) == 3
        result = client.post("/api/material-library/candidates", json=sel.default_plan("昇腾950"))
        assert result.status_code == 200 and result.json()["candidates"][0]["grade"] == "A"
        assert client.post("/api/material-library/evidence", json={"windows": []}).status_code == 422
        assert client.get("/api/material-library/media/nonexistent/video").status_code == 422
        assert client.get("/api/material-library/evidence/nonexistent/images/secrets.txt").status_code == 422


def test_real_template_crop_encoded_without_caption_red(video, tmp_path):
    pair = resolve_ffmpeg_pair(); out = tmp_path / "crop.mp4"
    subprocess.run([pair[0], "-v", "error", "-y", "-i", str(video), "-t", "3", "-an", "-vf",
                    template_filter({"x": 0, "y": 0, "w": 1, "h": .8}), "-c:v", "libx264", str(out)],
                   check=True, capture_output=True, timeout=60)
    info = lib.probe(out)
    assert (info["width"], info["height"], info["duration"]) == (1080,1920,3)
    img = tmp_path / "frame.png"
    subprocess.run([pair[0], "-v", "error", "-i", str(out), "-frames:v", "1", str(img)], check=True, capture_output=True, timeout=30)
    with Image.open(img) as image:
        r,g,b = image.getpixel((540,950)); assert g > r + 30
        r,g,b = image.getpixel((540,1270)); assert not (r > 150 and g < 80)


def test_selection_does_not_report_shortage_when_greedy_high_grade_blocks_three_windows():
    pool = [{"clip_id": str(i), "media_id": "one", "start": start, "end": start + 3,
             "grade": grade, "quality": 70} for i, (start, grade) in enumerate([(1.5, "A"), (0, "B"), (3, "B"), (6, "B")])]
    picked = sel._pick(pool)
    assert [c["start"] for c in picked] == [0, 3, 6]


def test_industry_only_has_zero_related_coverage_and_overlaps_cannot_render(video, db):
    task, submission, saved = confirmed(video, db, brands=[], entities=[])
    with lib.connect(db) as conn:
        for row in conn.execute("SELECT * FROM clips").fetchall():
            metadata = json.loads(row["metadata"]); metadata["series"] = []
            conn.execute("UPDATE clips SET metadata=? WHERE id=?", (json.dumps(metadata), row["id"]))
    result = sel.select(sel.default_plan("昇腾950"), db_path=db)
    assert result["status"] == "needs_material" and result["related_seconds"] == 0
    assert result["gaps"][0]["missing_related_seconds"] == 3
    with pytest.raises(lib.MaterialLibraryError, match="缺口"): sel.to_template_spec(result, "t25", db_path=db)
    # Reset this fixture to overlapping confirmed windows on a different model task.
    mid = saved and media(video, db)
    with lib.connect(db) as conn: conn.execute("DELETE FROM clips")
    _, _, saved = confirmed(video, db, windows=[{"media_id": mid, "start": t, "end": t+3} for t in (0, 1.5, 6)])
    assert sel.select(sel.default_plan("昇腾950"), db_path=db)["status"] == "needs_material"
    with pytest.raises(lib.MaterialLibraryError, match="重叠"):
        sel.select(sel.default_plan("昇腾950"), clip_ids=saved["clip_ids"], db_path=db)


def test_single_source_requires_explicit_relaxation(video, db, tmp_path):
    one = media(video, db)
    confirmed(video, db, windows=[{"media_id": one, "start": t, "end": t+3} for t in (0, 3)])
    second = tmp_path / "second.mp4"; second.write_bytes(video.read_bytes() + b"other source")
    two = media(second, db)
    confirmed(second, db, windows=[{"media_id": two, "start": 6, "end": 9}])
    plan = sel.default_plan("昇腾950")
    assert sel.select(plan, db_path=db)["status"] == "needs_material"
    relaxed = sel.select({**plan, "single_source": False}, db_path=db)
    assert relaxed["status"] == "ready" and len({c["media_id"] for c in relaxed["clips"]}) == 2


def test_acquisition_import_is_idempotent_and_requires_new_interval_review(video, db, tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "ROOT", tmp_path / "haike")
    plan = sel.default_plan("昇腾950"); before = sel.select(plan, db_path=db)
    request = sel.acquisition_request(plan, db_path=db)
    manifest = catalog(video, tmp_path)
    report = {"status": "imported", "queries_used": ["昇腾950 真机"], "detail": "已交付本地清单", "catalog_path": str(manifest)}
    imported = sel.finish_acquisition(request["id"], report, db_path=db)
    assert imported["result"]["registered"]["registered"] == 1
    assert sel.finish_acquisition(request["id"], report, db_path=db) == imported
    assert sel.select(plan, db_path=db)["status"] == "needs_material", "download title is not visual evidence"
    confirmed(video, db)
    after = sel.select(plan, db_path=db)
    assert after["status"] == "ready" and after["id"] != before["id"]
    assert any(row["id"] == before["id"] for row in sel.selection_history(plan["id"], db_path=db))


def test_stale_evidence_removes_candidates_and_saved_review_is_retrievable(video, db):
    task, submission, _ = confirmed(video, db)
    assert ev.read_task(task["id"], db_path=db)["review_result"] == submission
    sheet = ev.task_directory(task["id"], db) / task["windows"][0]["sheets"][0]["file"]
    sheet.write_bytes(b"changed")
    result = sel.compact_candidates(sel.default_plan("昇腾950"), db_path=db)
    assert not result["candidates"] and len(result["rejected"]) == 3
    assert sel.select(sel.default_plan("昇腾950"), db_path=db)["status"] == "needs_material"


def test_cli_contract_and_failed_selection_preserves_prior_spec(video, db, tmp_path):
    from scripts.material_library_cli import main
    output = tmp_path / "plan.json"
    assert main(["--db", str(db), "--output", str(output), "plan", "昇腾950"]) == 0
    plan = json.loads(output.read_text(encoding="utf-8"))
    assert main(["--db", str(db), "select", str(output)]) == 2
    confirmed(video, db)
    result = indexed_pick("t25", plan["topic"], [], tmp_path / "out", db_path=db)
    destination = Path(result["spec_path"]); previous = destination.read_bytes()
    with lib.connect(db) as conn: conn.execute("DELETE FROM clips")
    gap = indexed_pick("t25", plan["topic"], [], destination.parent, db_path=db)
    assert gap["status"] == "needs_material" and destination.read_bytes() == previous


def test_product_label_regions_are_spatially_time_scoped_and_frozen(video, db, tmp_path):
    mid = media(video, db)
    task = ev.prepare_task({"model": "label-review", "windows": [
        {"media_id": mid, "start": t, "end": t+3, "crop": {"x":0,"y":0,"w":1,"h":.8}} for t in (0,3,6)]}, db_path=db)
    submission = copy.deepcopy(task["submission_template"])
    for review in submission["reviews"]:
        review.update(observation="设备和实体展台标识",usable=True,subject_retained=True,captions_obscure_subject=False,
                      entities=["昇腾950"],identity_basis="实体标识",quality=80)
    region = {"x":.2,"y":0,"w":.6,"h":.4,"start":0,"end":1,"reason":"展台横梁上的实体产品标识"}
    submission["reviews"][0]["product_text_regions"] = [region]
    too_large = copy.deepcopy(submission)
    too_large["reviews"][0]["product_text_regions"][0].update(x=0,w=1,h=1)
    with pytest.raises(lib.MaterialLibraryError, match="40%"):
        ev.submit_task(too_large,db_path=db)
    too_long = copy.deepcopy(submission);too_long["reviews"][0]["product_text_regions"][0]["end"] = 4
    with pytest.raises(lib.MaterialLibraryError,match="范围"):
        ev.submit_task(too_long,db_path=db)
    ev.submit_task(submission,db_path=db)
    result=indexed_pick("t25","昇腾950",[],tmp_path/'out',db_path=db)
    spec=json.loads(Path(result["spec_path"]).read_text(encoding='utf-8'))
    cue=next(c for c in spec if c["source_in"] == 0)
    assert cue["product_text_regions"] == [region] and validate_spec(spec,db_path=db)
    label_box=[[30,5],[60,5],[60,20],[30,20]]
    assert product_region_is_approved(label_box,[region],.5,100,100)
    assert not product_region_is_approved(label_box,[region],1,100,100)
    assert not product_region_is_approved([[30,70],[60,70],[60,90],[30,90]],[region],.5,100,100), "lower burned caption remains a risk"
    cue["product_text_regions"][0]["end"] = 2
    with pytest.raises(lib.MaterialLibraryError,match="冻结"):
        validate_spec(spec,db_path=db)


def test_crop_versions_do_not_crowd_out_bounded_candidates(video, db):
    for i in range(5):
        mid=media(video,db)
        confirmed(video,db,windows=[{"media_id":mid,"start":t,"end":t+3,"crop":{"x":0,"y":0,"w":1,"h":.7+i*.02}} for t in (0,3,6)])
    result=sel.compact_candidates(sel.default_plan("昇腾950"),db_path=db)
    assert lib.summary(db_path=db)["clips"] == 15
    assert result["available_count"] == 3 and len(result["candidates"]) == 3
    assert sel.select(sel.default_plan("昇腾950"),db_path=db)["status"] == "ready"
