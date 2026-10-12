"""Contract tests for model selection across short and long scene timelines."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from backlot.autonomous_material_selection import (
    MaterialSelectionError,
    build_selection_plan,
    prepare_selection_request,
)
from backlot.media_index import media_content_fingerprint
from backlot import workbench
from backlot import ai_vision
from backlot.ai_text import TextAIError
from backlot import server as server_mod
from backlot import state as state_mod
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.material_catalog_import import MaterialCatalogError, read_material_catalog
from backlot.visual_need_plan import VisualNeedError, build_visual_need_plan, prepare_visual_need_task


def _shot(number: int, start: float, end: float, *, text: list[str] | None = None, blur: str = "low") -> dict:
    return {
        "shot_id": f"SHOT-{number:04d}", "start_seconds": start, "end_seconds": end,
        "frames": [{"frame_id": f"FRAME-{number:05d}", "selected_for_vision": True}],
        "description": {
            "summary": f"芯片生产与产品展示镜头 {number}",
            "entities": [{"name": "芯片"}], "actions": [{"name": "展示"}],
            "screen_text": text or [], "quality": {"blur": blur, "notes": "画面清晰"},
            "unknowns": [],
        },
    }


def _index(shots: list[dict]) -> dict:
    return {
        "signature": "a" * 64, "status": "completed",
        "source": {"fingerprint": "b" * 64}, "vision": {"status": "completed", "model": "gpt-6-sol"},
        "overview_gate": {"signature": "c" * 64, "model": "gpt-6-sol", "ranges": [{"start_seconds": 0, "end_seconds": 30, "cell_ids": ["SHEET-0001:R1C1"]}]},
        "shots": shots,
    }


def _state(scene_duration: float, provider: str = "Douyin") -> dict:
    return {
        "assets": [{
            "id": "A-1", "type": "video", "name": "芯片实拍", "resolution": "1080x1920",
            "duration_seconds": 30,
            "provenance": {"provider": provider, "source_tool": provider.lower(),
                           "source_url": "https://www.douyin.com/video/123" if provider == "Douyin" else "https://www.pexels.com/video/123",
                           "license": "待核验"},
        }],
        "scenes": [{"id": "scene-1", "start_seconds": 0, "end_seconds": scene_duration,
                    "title": "芯片生产", "description": "展示芯片生产现场"}],
    }


def test_short_and_long_scenes_use_verified_variable_duration_windows():
    short = prepare_selection_request(_state(9), {"A-1": _index([_shot(1, 0, 4), _shot(2, 4, 9)])}, required_platform="douyin")
    short_plan = build_selection_plan(short, {"scenes": [{"scene_id": "scene-1", "clips": [
        {"capability_id": "LMC-001", "source_in_seconds": 0, "duration_seconds": 4},
        {"capability_id": "LMC-002", "source_in_seconds": 4, "duration_seconds": 5},
    ]}]}, model="gpt-6-sol")
    assert short_plan["status"] == "ready"
    assert short_plan["publish_rights_status"] == "review_required"
    assert [item["display_end_seconds"] - item["display_start_seconds"] for item in short_plan["sequences"]] == [4, 5]

    long = prepare_selection_request(_state(24), {"A-1": _index([_shot(1, 0, 11), _shot(2, 11, 20), _shot(3, 20, 30)])}, required_platform="douyin")
    long_plan = build_selection_plan(long, {"scenes": [{"scene_id": "scene-1", "clips": [
        {"capability_id": "LMC-001", "source_in_seconds": 0, "duration_seconds": 8},
        {"capability_id": "LMC-002", "source_in_seconds": 11, "duration_seconds": 7},
        {"capability_id": "LMC-003", "source_in_seconds": 20, "duration_seconds": 9},
    ]}]}, model="gpt-6-sol")
    assert long_plan["status"] == "ready"
    assert [item["display_start_seconds"] for item in long_plan["sequences"]] == [0, 8, 15]
    assert long_plan["sequences"][-1]["display_end_seconds"] == 24
    assert all(item["playback_rate"] == 1 and item["muted"] for item in long_plan["sequences"])


def test_visual_targets_are_planned_before_search_and_only_real_gaps_trigger_acquisition():
    state = _state(9)
    state["assets"].append({
        **copy.deepcopy(state["assets"][0]), "id": "A-2", "name": "另一条抖音原片",
        "provenance": {**state["assets"][0]["provenance"], "source_url": "https://www.douyin.com/video/456"},
    })
    task = prepare_visual_need_task(state, model="gpt-6-sol")
    plan = build_visual_need_plan(task, {"scenes": [{"scene_id": "scene-1", "segments": [
        {"start_seconds": 0, "end_seconds": 4, "mode": "material", "visual_intent": "展示芯片实物",
         "query_terms": ["芯片实物"], "must_show": ["芯片"], "match_policy": "exact"},
        {"start_seconds": 4, "end_seconds": 9, "mode": "material", "visual_intent": "展示芯片生产过程",
         "query_terms": ["芯片生产"], "match_policy": "topic"},
    ]}]}, model="gpt-6-sol")
    state["visual_need_plan"] = plan
    request = prepare_selection_request(state, {
        "A-1": _index([_shot(1, 0, 4)]), "A-2": _index([_shot(1, 0, 5)]),
    }, required_platform="douyin", model="gpt-6-sol")
    assert [item["duration_seconds"] for item in request["targets"]] == [4, 5]
    first = {"capability_id": "LMC-001", "source_in_seconds": 0, "duration_seconds": 4,
             "match_reason": "画面中可见芯片", "semantic_confidence": .91}
    incomplete = build_selection_plan(request, {"targets": [
        {"target_id": "VT-001-001", "clips": [first]},
        {"target_id": "VT-001-002", "clips": []},
    ]}, model="gpt-6-sol")
    assert incomplete["status"] == "needs_more_material"
    assert incomplete["acquisition_requests"][0]["target_id"] == "VT-001-002"
    assert incomplete["acquisition_requests"][0]["missing_seconds"] == 5
    assert incomplete["acquisition_requests"][0]["query_terms"] == ["芯片生产"]
    ready = build_selection_plan(request, {"targets": [
        {"target_id": "VT-001-001", "clips": [first]},
        {"target_id": "VT-001-002", "clips": [{
            "capability_id": "LMC-002", "source_in_seconds": 0, "duration_seconds": 5,
            "match_reason": "生产动作清晰", "semantic_confidence": .9,
        }]},
    ]}, model="gpt-6-sol")
    assert ready["status"] == "ready"
    assert [item["display_end_seconds"] for item in ready["sequences"]] == [4, 9]
    assert not ready["acquisition_requests"]
    with pytest.raises(MaterialSelectionError, match="重复使用"):
        build_selection_plan(request, {"targets": [
            {"target_id": "VT-001-001", "clips": [first]},
            {"target_id": "VT-001-002", "clips": [{**first, "duration_seconds": 5}]},
        ]}, model="gpt-6-sol")
    duplicate_original = copy.deepcopy(request)
    duplicate_original["candidates"][1]["source_url"] = duplicate_original["candidates"][0]["source_url"]
    with pytest.raises(MaterialSelectionError, match="原视频.*重复使用"):
        build_selection_plan(duplicate_original, {"targets": [
            {"target_id": "VT-001-001", "clips": [first]},
            {"target_id": "VT-001-002", "clips": [{
                "capability_id": "LMC-002", "source_in_seconds": 0, "duration_seconds": 5,
                "match_reason": "重复原视频的另一份拷贝", "semantic_confidence": .9,
            }]},
        ]}, model="gpt-6-sol")


def test_presenter_only_needs_verified_fullscreen_base_and_no_footage():
    state = _state(24)
    state["project"] = {"pipeline_type": "avatar-spokesperson"}
    state["scenes"][0]["presenter"] = {"treatment": "fullscreen", "source_path": "assets/avatar/master.mp4"}
    task = prepare_visual_need_task(state, model="gpt-6-sol")
    plan = build_visual_need_plan(task, {"scenes": [{"scene_id": "scene-1", "segments": [
        {"start_seconds": 0, "end_seconds": 24, "mode": "presenter", "reason": "解释段由主持人承接"},
    ]}]}, model="gpt-6-sol")
    state["visual_need_plan"] = plan
    request = prepare_selection_request(state, {}, required_platform="douyin", model="gpt-6-sol")
    result = build_selection_plan(request, {"targets": []}, model="gpt-6-sol")
    assert result["status"] == "ready"
    assert result["sequences"] == []
    assert result["scene_plans"][0]["covered_seconds"] == 24
    state["scenes"][0]["presenter"]["treatment"] = "pip_top_left"
    with pytest.raises(VisualNeedError, match="可单独承接"):
        build_visual_need_plan(prepare_visual_need_task(state, model="gpt-6-sol"), {
            "scenes": [{"scene_id": "scene-1", "segments": [{"start_seconds": 0, "end_seconds": 24, "mode": "presenter"}]}]
        }, model="gpt-6-sol")


def test_visual_need_plan_rejects_stale_scene_and_preserve_without_source():
    state = _state(9)
    task = prepare_visual_need_task(state, model="gpt-6-sol")
    with pytest.raises(VisualNeedError, match="完整主体画面"):
        build_visual_need_plan(task, {"scenes": [{"scene_id": "scene-1", "segments": [
            {"start_seconds": 0, "end_seconds": 9, "mode": "preserve"},
        ]}]}, model="gpt-6-sol")
    with pytest.raises(VisualNeedError, match="无重叠、无空白"):
        build_visual_need_plan(task, {"scenes": [{"scene_id": "scene-1", "segments": [
            {"start_seconds": 0, "end_seconds": 4, "mode": "material", "visual_intent": "芯片",
             "query_terms": ["芯片"], "match_policy": "topic"},
            {"start_seconds": 4.5, "end_seconds": 9, "mode": "material", "visual_intent": "生产",
             "query_terms": ["生产"], "match_policy": "topic"},
        ]}]}, model="gpt-6-sol")
    with pytest.raises(VisualNeedError, match="必须是列表"):
        build_visual_need_plan(task, {"scenes": [{"scene_id": "scene-1", "segments": [{
            "start_seconds": 0, "end_seconds": 9, "mode": "material", "visual_intent": "芯片",
            "query_terms": "芯片", "match_policy": "topic",
        }]}]}, model="gpt-6-sol")


def test_source_policy_rejects_bad_sources_and_screen_text_waits_for_crop_qa():
    state = _state(9, provider="Pexels")
    index = _index([_shot(1, 0, 5), _shot(2, 5, 9, text=["来源视频字幕"]), _shot(3, 9, 14, blur="high")])
    request = prepare_selection_request(state, {"A-1": index}, required_platform="douyin")
    assert request["candidates"] == []
    assert len(request["rejected_candidates"]) == 3
    assert any("来源" in reason for reason in request["rejected_candidates"][0]["reasons"])
    state = _state(9)
    request = prepare_selection_request(state, {"A-1": index}, required_platform="douyin")
    # Text is an observation, not a whole-shot veto: the final source-window
    # review decides whether it is a retained product label or removable caption.
    assert [item["capability_id"] for item in request["candidates"]] == ["LMC-001", "LMC-002"]
    with pytest.raises(MaterialSelectionError, match="未通过证据"):
        build_selection_plan(request, {"scenes": [{"scene_id": "scene-1", "clips": [
            {"capability_id": "LMC-003", "source_in_seconds": 9, "duration_seconds": 4},
        ]}]}, model="gpt-6-sol")
    state["assets"][0]["generation"] = {"rights_status": "reference_only"}
    request = prepare_selection_request(state, {"A-1": index}, required_platform="douyin")
    assert request["candidates"] == []
    assert any("仅可参考" in reason for reason in request["rejected_candidates"][0]["reasons"])


def test_overview_only_is_not_adoptable_and_model_cannot_invent_timecodes():
    overview = {
        "signature": "c" * 64, "status": "overview_completed", "source": {"fingerprint": "d" * 64},
        "overview": {"status": "completed", "chapters": [{
            "chapter_id": "CHAPTER-01", "summary": "芯片展示", "subjects": [{"name": "芯片"}],
            "actions": [], "usable_ranges": [{"start_seconds": 0, "end_seconds": 9,
                                          "evidence_cell_ids": ["SHEET-0001:R1C1"]}],
        }]},
    }
    request = prepare_selection_request(_state(9), {"A-1": overview}, required_platform="douyin")
    assert not request["candidates"]
    assert "仅有多宫格概览" in request["rejected_candidates"][0]["reasons"][0]
    request = prepare_selection_request(_state(9), {"A-1": _index([_shot(1, 0, 9)])}, required_platform="douyin")
    with pytest.raises(MaterialSelectionError, match="超出场景或已验证"):
        build_selection_plan(request, {"scenes": [{"scene_id": "scene-1", "clips": [
            {"capability_id": "LMC-001", "source_in_seconds": 8, "duration_seconds": 9},
        ]}]}, model="gpt-6-sol")


def test_contact_sheet_windows_bound_a_longer_verified_shot():
    index = _index([_shot(1, 0, 12)])
    index["overview_gate"]["ranges"] = [
        {"start_seconds": 2, "end_seconds": 5, "cell_ids": ["SHEET-0001:R1C2"]},
        {"start_seconds": 8, "end_seconds": 11, "cell_ids": ["SHEET-0001:R1C5"]},
    ]
    request = prepare_selection_request(_state(6), {"A-1": index}, required_platform="douyin", model="gpt-6-sol")
    assert [(item["capability_id"], item["source_in_seconds"], item["source_out_seconds"]) for item in request["candidates"]] == [
        ("LMC-001:R01", 2, 5), ("LMC-001:R02", 8, 11),
    ]
    plan = build_selection_plan(request, {"scenes": [{"scene_id": "scene-1", "clips": [
        {"capability_id": "LMC-001:R01", "source_in_seconds": 2, "duration_seconds": 3},
        {"capability_id": "LMC-001:R02", "source_in_seconds": 8, "duration_seconds": 3},
    ]}]}, model="gpt-6-sol")
    assert plan["status"] == "ready"
    assert plan["sequences"][1]["evidence"]["overview"]["cell_ids"] == ["SHEET-0001:R1C5"]


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "film"
    (project / "artifacts").mkdir(parents=True)
    (project / "assets" / "video").mkdir(parents=True)
    (project / "assets" / "video" / "chip.mp4").write_bytes(b"fixture-video")
    (project / "project.json").write_text(json.dumps({"project_id": "film", "title": "芯片", "render_profile": {"width": 1080, "height": 1920}}), encoding="utf-8")
    (project / "artifacts" / "script.json").write_text(json.dumps({"title": "芯片", "sections": [{"id": "s1", "text": "芯片生产现场", "start_seconds": 0, "end_seconds": 9}]}), encoding="utf-8")
    (project / "artifacts" / "scene_plan.json").write_text(json.dumps({"scenes": [{"id": "scene-1", "title": "芯片生产现场", "description": "芯片生产现场", "start_seconds": 0, "end_seconds": 9, "script_section_id": "s1"}]}), encoding="utf-8")
    (project / "artifacts" / "asset_manifest.json").write_text(json.dumps({"assets": [{"id": "chip", "type": "video", "path": "assets/video/chip.mp4", "scene_id": "scene-1", "provider": "Douyin", "source_tool": "douyin_cookie", "source_url": "https://www.douyin.com/video/123", "duration_seconds": 9, "resolution": "1080x1920"}]}), encoding="utf-8")
    return project


def test_existing_v900_style_manifest_is_visible_to_target_planning(tmp_path: Path):
    project = _project(tmp_path)
    (project / "artifacts" / "asset_manifest.json").write_text(json.dumps({"assets": [{
        "asset_id": "douyin-v900-cue-001", "asset_type": "video", "role": "scene_broll",
        "scene_id": "scene-1", "path": "assets/video/chip.mp4", "duration_seconds": 9,
        "source_platform": "douyin", "source_video_id": "7688397730602938281",
        "source_url": "https://www.douyin.com/video/7688397730602938281",
        "rights_status": "review_required", "acquired_via": "douyin_cookie",
    }]}), encoding="utf-8")
    state = workbench.bootstrap_workbench(project)
    assert len(state["assets"]) == 1
    asset = state["assets"][0]
    assert asset["type"] == "video"
    assert asset["source_type"] == "web_download"
    assert asset["provenance"]["provider"] == "douyin"
    assert asset["generation"]["video_id"] == "7688397730602938281"
    assert workbench.read_agent_visual_need_task(project, {"model": "gpt-6-sol"})["scenes"][0]["scene_id"] == "scene-1"


def _attach_index(project: Path, state: dict) -> None:
    asset = next(item for item in state["assets"] if item["type"] == "video")
    source = project / asset["path"]
    index = _index([_shot(1, 0, 4), _shot(2, 4, 9)])
    index["source"]["fingerprint"] = media_content_fingerprint(source)
    path = project / "artifacts" / "media-index" / asset["id"] / "vision.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(index), encoding="utf-8")
    overview_path = project / "artifacts" / "media-index" / asset["id"] / "overview.json"
    overview_path.write_text(json.dumps({
        "version": 1, "status": "overview_completed", "signature": "c" * 64,
        "source": {"path": str(source), "fingerprint": index["source"]["fingerprint"]},
        "frames": [{"frame_id": "FRAME-00001", "selected_for_overview": True}],
        "cells": [{"cell_id": "SHEET-0001:R1C1", "frame_id": "FRAME-00001"}],
        "overview": {"status": "completed", "vision": {"model": "gpt-6-sol"}, "chapters": [{"chapter_id": "CHAPTER-01", "summary": "芯片生产",
            "usable_ranges": [{"start_seconds": 0, "end_seconds": 9, "evidence_cell_ids": ["SHEET-0001:R1C1"]}]}]},
    }), encoding="utf-8")
    asset["media_index"] = {
        "vision_index_path": str(path.relative_to(project)).replace("\\", "/"),
        "overview_index_path": str(overview_path.relative_to(project)).replace("\\", "/"),
        "status": "completed",
    }
    workbench._save(project, state)


def _mark_agent_indexes(project: Path) -> None:
    state = workbench.read_workbench(project)
    asset = next(item for item in state["assets"] if item["type"] == "video")
    for key, section in (("vision_index_path", "vision"), ("overview_index_path", "overview")):
        path = project / asset["media_index"][key]
        index = json.loads(path.read_text(encoding="utf-8"))
        index[section]["provider" if section == "vision" else "vision"] = (
            "agent" if section == "vision" else {**index[section]["vision"], "provider": "agent"}
        )
        path.write_text(json.dumps(index), encoding="utf-8")


def test_agent_selection_is_default_and_never_calls_relay(tmp_path: Path, monkeypatch):
    project = _project(tmp_path)
    state = workbench.bootstrap_workbench(project)
    _attach_index(project, state)
    proposal = {"scenes": [{"scene_id": "scene-1", "clips": [
        {"capability_id": "LMC-001", "source_in_seconds": 0, "duration_seconds": 4},
        {"capability_id": "LMC-002", "source_in_seconds": 4, "duration_seconds": 5},
    ]}]}
    with pytest.raises(workbench.WorkbenchError, match="agent.*方案"):
        workbench.prepare_autonomous_material_selection_job(project, {"required_platform": "douyin", "model": "gpt-6-sol"})
    _mark_agent_indexes(project)
    task = workbench.read_agent_material_selection_task(project, {"required_platform": "douyin", "model": "gpt-6-sol"})
    assert task["execution_mode"] == "agent"
    assert len(task["candidates"]) == 2
    monkeypatch.setattr(workbench, "select_verified_materials", lambda _request: pytest.fail("relay must not be called"))
    parent = workbench.prepare_autonomous_material_selection_job(project, {
        "required_platform": "douyin", "model": "gpt-6-sol", "proposal": proposal,
    })
    alternate = {"scenes": [{"scene_id": "scene-1", "clips": list(reversed(proposal["scenes"][0]["clips"]))}]}
    second_parent = workbench.prepare_autonomous_material_selection_job(project, {
        "required_platform": "douyin", "model": "gpt-6-sol", "proposal": alternate,
    })
    assert second_parent["job_id"] != parent["job_id"]
    result = workbench.run_autonomous_material_selection(project, {
        "required_platform": "douyin", "model": "gpt-6-sol", "proposal": proposal,
        "request_fingerprint": parent["request_fingerprint"],
    })
    assert result["material_selection_plan"]["status"] == "adopted"
    assert result["material_selection_plan"]["execution_mode"] == "agent"
    assert [block["end_seconds"] for block in result["scenes"][0]["visual_timeline"]["blocks"]] == [4, 9]


def test_visual_need_http_task_persists_and_selection_preserves_old_footage(tmp_path: Path, monkeypatch):
    projects = tmp_path / "projects"
    projects.mkdir()
    project = _project(projects)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg unavailable")
    subprocess.run([
        ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x568:r=30",
        "-t", "9", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(project / "assets" / "video" / "chip.mp4"),
    ], check=True, capture_output=True, timeout=40)
    state = workbench.bootstrap_workbench(project)
    old_asset = next(item for item in state["assets"] if item["type"] == "video")
    workbench.update_scene_visual_timeline(project, "scene-1", {"blocks": [{
        "start_seconds": 0, "end_seconds": 9, "asset_id": old_asset["id"],
        "source_in_seconds": 0, "source_out_seconds": 9,
    }]})
    state = workbench.read_workbench(project)
    fresh = project / "assets" / "video" / "new-chip.mp4"
    subprocess.run([
        ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=320x568:r=30",
        "-t", "9", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(fresh),
    ], check=True, capture_output=True, timeout=40)
    new_asset = workbench._append_asset(project, state, {
        "name": "新芯片镜头", "type": "video", "source_type": "web_download",
        "path": "assets/video/new-chip.mp4", "duration_seconds": 9,
        "provider": "Douyin", "source_tool": "copy_skill_material_catalog_v1",
        "source_url": "https://www.douyin.com/video/456", "license": "待核验",
    })
    workbench._save(project, state)
    _attach_index(project, workbench.read_workbench(project))
    _mark_agent_indexes(project)
    state = workbench.read_workbench(project)
    index = _index([_shot(1, 0, 4)])
    index["source"]["fingerprint"] = media_content_fingerprint(fresh)
    index["vision"]["provider"] = "agent"
    index["overview_gate"]["provider"] = "agent"
    index_path = project / "artifacts" / "media-index" / new_asset["id"] / "vision.json"
    index_path.parent.mkdir(parents=True)
    index_path.write_text(json.dumps(index), encoding="utf-8")
    new_asset_state = next(item for item in state["assets"] if item["id"] == new_asset["id"])
    new_asset_state["media_index"] = {"vision_index_path": str(index_path.relative_to(project)).replace("\\", "/"), "status": "completed"}
    workbench._save(project, state)
    monkeypatch.setattr(state_mod, "PROJECTS_DIR", projects)
    monkeypatch.setattr(server_mod, "PROJECTS_DIR", projects)
    monkeypatch.setattr(server_mod, "_summary_cache", {})
    monkeypatch.setattr(server_mod, "_PROJECTS_ROOT_STR", __import__("os").path.normcase(str(projects.resolve())))

    async def no_watch():
        return None

    monkeypatch.setattr(server_mod, "_watch_projects", no_watch)
    app = server_mod.create_app()
    with TestClient(app) as client:
        task_response = client.post("/api/project/film/workbench/material-needs/agent-task", json={"model": "gpt-6-sol"})
        assert task_response.status_code == 200, task_response.text
        task = task_response.json()
        assert task["scenes"][0]["existing_visual_timeline_ready"] is True
        proposal = {"scenes": [{"scene_id": "scene-1", "segments": [
            {"start_seconds": 0, "end_seconds": 4, "mode": "material", "visual_intent": "芯片展示",
             "query_terms": ["芯片 展示"], "must_show": ["芯片"], "match_policy": "exact"},
            {"start_seconds": 4, "end_seconds": 9, "mode": "preserve", "reason": "保留已有画面"},
        ]}]}
        submitted = client.post("/api/project/film/workbench/material-needs/agent-submit", json={
            "model": "gpt-6-sol", "task_fingerprint": task["task_fingerprint"], "proposal": proposal,
        })
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["visual_need_plan"]["scenes"][0]["targets"][1]["mode"] == "preserve"
        acquisition = client.post("/api/project/film/workbench/material-acquisition/agent-task", json={
            "model": "gpt-6-sol", "required_platform": "douyin",
        })
        assert acquisition.status_code == 200, acquisition.text
        assert acquisition.json()["status"] == "match_required"
        assert not acquisition.json()["gaps"]
    request = workbench.read_agent_material_selection_task(project, {"required_platform": "douyin", "model": "gpt-6-sol"})
    candidate = next(item for item in request["candidates"] if item["asset_id"] == new_asset["id"])
    selection = {"targets": [{"target_id": "VT-001-001", "clips": [{
        "capability_id": candidate["capability_id"], "source_in_seconds": 0, "duration_seconds": 4,
        "match_reason": "画面可见芯片展示", "semantic_confidence": .93,
    }]}]}
    with pytest.raises(workbench.WorkbenchError, match="实际源区间宫格"):
        workbench.run_autonomous_material_selection(project, {
            "required_platform": "douyin", "model": "gpt-6-sol", "proposal": selection,
            "request_fingerprint": request["request_fingerprint"],
        })
    with TestClient(server_mod.create_app()) as client:
        qa_response = client.post("/api/project/film/workbench/material-selection/window-qa-task", json={
            "required_platform": "douyin", "model": "gpt-6-sol", "proposal": selection,
            "request_fingerprint": request["request_fingerprint"],
        })
    assert qa_response.status_code == 200, qa_response.text
    qa_task = qa_response.json()
    assert len(qa_task["sequences"]) == 2
    assert {item["sequence_id"] for item in qa_task["sequences"]} == {"LMS-001", "LMP-001"}
    assert all((project / sheet["path"]).is_file() for item in qa_task["sequences"] for sheet in item["sheets"])
    window_qa = {"task_fingerprint": qa_task["task_fingerprint"], "checks": [
        {"sequence_id": item["sequence_id"], "clean": True, "relevant": True,
         "observation": "源画面中心裁切区为纯色测试画面，无原字幕、水印或贴纸。"}
        for item in qa_task["sequences"]
    ]}
    with pytest.raises(workbench.WorkbenchError, match="不干净"):
        workbench.run_autonomous_material_selection(project, {
            "required_platform": "douyin", "model": "gpt-6-sol", "proposal": selection,
            "window_qa": {**window_qa, "checks": [{**window_qa["checks"][0], "clean": False}, window_qa["checks"][1]]},
            "request_fingerprint": request["request_fingerprint"],
        })
    with pytest.raises(workbench.WorkbenchError, match="已变化"):
        workbench.prepare_autonomous_material_selection_job(project, {
            "required_platform": "douyin", "model": "gpt-6-sol", "proposal": selection,
            "window_qa": {**window_qa, "task_fingerprint": "wrong"},
        })
    prepared = workbench.prepare_autonomous_material_selection_job(project, {
        "required_platform": "douyin", "model": "gpt-6-sol", "proposal": selection,
        "window_qa": window_qa,
    })
    assert prepared["window_qa_fingerprint"] == qa_task["task_fingerprint"]
    result = workbench.run_autonomous_material_selection(project, {
        "required_platform": "douyin", "model": "gpt-6-sol", "proposal": selection,
        "window_qa": window_qa,
        "request_fingerprint": request["request_fingerprint"],
    })
    assert result["material_selection_plan"]["window_qa"]["status"] == "passed"
    blocks = result["scenes"][0]["visual_timeline"]["blocks"]
    assert [(item["asset_id"], item["start_seconds"], item["end_seconds"]) for item in blocks] == [
        (new_asset["id"], 0, 4), (old_asset["id"], 4, 9),
    ]
    assert blocks[1]["source_in_seconds"] == 4
    assert blocks[1]["source_out_seconds"] == 9
    output = workbench._materialize_scene_visual_timeline(project, result, result["scenes"][0], ffmpeg)
    assert workbench._probe_duration_seconds(output, ffmpeg, 0) == pytest.approx(9, abs=.12)
    assert workbench.read_agent_material_acquisition_task(project, {
        "model": "gpt-6-sol", "required_platform": "douyin",
    })["status"] == "ready"


def test_long_avatar_presenter_only_adopts_without_search_or_visual_rewrite(tmp_path: Path):
    project = _project(tmp_path)
    metadata = json.loads((project / "project.json").read_text(encoding="utf-8"))
    metadata["pipeline_type"] = "avatar-spokesperson"
    (project / "project.json").write_text(json.dumps(metadata), encoding="utf-8")
    script = json.loads((project / "artifacts" / "script.json").read_text(encoding="utf-8"))
    script["sections"][0]["end_seconds"] = 24
    (project / "artifacts" / "script.json").write_text(json.dumps(script), encoding="utf-8")
    scenes = json.loads((project / "artifacts" / "scene_plan.json").read_text(encoding="utf-8"))
    scenes["scenes"][0]["end_seconds"] = 24
    (project / "artifacts" / "scene_plan.json").write_text(json.dumps(scenes), encoding="utf-8")
    avatar = project / "assets" / "video" / "presenter.mp4"
    avatar.write_bytes(b"existing-presenter")
    state = workbench.bootstrap_workbench(project)
    state["scenes"][0]["presenter"].update({"treatment": "fullscreen", "source_path": "assets/video/presenter.mp4"})
    workbench._save(project, state)
    before = copy.deepcopy(workbench.read_workbench(project)["scenes"][0]["visual_timeline"])
    task = workbench.read_agent_visual_need_task(project, {"model": "gpt-6-sol"})
    workbench.submit_agent_visual_need_plan(project, {
        "model": "gpt-6-sol", "task_fingerprint": task["task_fingerprint"],
        "proposal": {"scenes": [{"scene_id": "scene-1", "segments": [{
            "start_seconds": 0, "end_seconds": 24, "mode": "presenter",
            "reason": "解释部分由已就绪全屏数字人承接",
        }]}]},
    })
    acquisition = workbench.read_agent_material_acquisition_task(project, {
        "model": "gpt-6-sol", "required_platform": "douyin",
    })
    assert acquisition["status"] == "ready"
    assert acquisition["gaps"] == []
    selection = workbench.read_agent_material_selection_task(project, {
        "model": "gpt-6-sol", "required_platform": "douyin",
    })
    result = workbench.run_autonomous_material_selection(project, {
        "model": "gpt-6-sol", "required_platform": "douyin",
        "request_fingerprint": selection["request_fingerprint"], "proposal": {"targets": []},
    })
    assert result["material_selection_plan"]["status"] == "adopted"
    assert result["material_selection_plan"]["sequences"] == []
    assert result["scenes"][0]["visual_timeline"] == before


def test_agent_visual_evidence_prepares_and_accepts_native_results_without_relay(tmp_path: Path, monkeypatch):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg unavailable")
    project = _project(tmp_path)
    source = project / "assets" / "video" / "chip.mp4"
    subprocess.run([
        ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x480:r=15",
        "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
    ], check=True, capture_output=True)
    state = workbench.bootstrap_workbench(project)
    asset_id = next(asset["id"] for asset in state["assets"] if asset["type"] == "video")
    base = workbench.build_material_overview_index(
        source, project / "artifacts" / "media-index" / asset_id,
        ffmpeg=ffmpeg, ffprobe=shutil.which("ffprobe") or "ffprobe",
    )
    base["status"] = "overview_completed"
    base["overview"] = {"status": "completed", "chapters": [], "vision": {"provider": "default", "model": "gpt-5.6-terra"}}
    workbench.write_material_overview_index(base)
    monkeypatch.setattr(workbench, "test_vision_ai_connection", lambda **_kw: pytest.fail("relay preflight must not run"))
    monkeypatch.setattr(workbench, "describe_contact_sheets", lambda *_a, **_kw: pytest.fail("relay overview must not run"))
    monkeypatch.setattr(workbench, "describe_shots", lambda *_a, **_kw: pytest.fail("relay V2 must not run"))

    started = workbench.start_asset_media_index(project, asset_id, {
        "stage": "overview", "execution_mode": "agent", "model": "gpt-6-luna", "recognize_audio": False,
    })
    job_id = started["automation"]["media_index"]["job_id"]
    workbench.generate_asset_media_index(project, job_id)
    task = workbench.read_agent_material_vision_task(project, asset_id, "overview")
    assert task["status"] == "sheets_ready"
    assert task["model"] == "gpt-6-luna"
    assert all(Path(sheet["path"]).is_file() for sheet in task["sheets"])
    assert json.loads(Path(base["index_path"]).read_text(encoding="utf-8"))["overview"]["vision"]["model"] == "gpt-5.6-terra"
    chapter_rows = []
    for chapter in task["chapters"]:
        cell_ids = [cell["cell_id"] for cell in task["cells"] if cell["chapter_id"] == chapter["chapter_id"]]
        chapter_rows.append({
            "chapter_id": chapter["chapter_id"], "summary": "蓝色画面", "subjects": [], "actions": [],
            "quality": {"blur": "low", "notes": "清晰"},
            "usable_ranges": [{"label": "蓝色背景", "confidence": .9, "evidence_cell_ids": cell_ids}],
            "detail_candidates": [], "unknowns": [],
        })
    overview_payload = {"model": "gpt-6-luna", "task_fingerprint": task["task_fingerprint"],
                        "proposal": {"chapters": chapter_rows}}
    with pytest.raises(workbench.WorkbenchConflict, match="任务或模型"):
        workbench.submit_agent_material_vision(project, asset_id, "overview", {**overview_payload, "task_fingerprint": "stale"})
    workbench.submit_agent_material_vision(project, asset_id, "overview", overview_payload)
    assert workbench.read_agent_material_vision_task(project, asset_id, "overview")["status"] == "overview_completed"

    started = workbench.start_asset_media_index(project, asset_id, {
        "stage": "vision", "execution_mode": "agent", "model": "gpt-6-luna",
    })
    workbench.generate_asset_media_index(project, started["automation"]["media_index"]["job_id"])
    task = workbench.read_agent_material_vision_task(project, asset_id, "vision")
    assert task["status"] == "frames_ready"
    assert all(Path(frame["path"]).is_file() for shot in task["shots"] for frame in shot["frames"])
    rows = [{
        "shot_id": shot["shot_id"], "summary": "蓝色画面", "entities": [], "actions": [],
        "environment": "室内", "shot_type": "静态", "camera_motion": "无", "state_changes": [],
        "screen_text": [], "quality": {"blur": "low", "occlusion": "无", "notes": "清晰"},
        "unknowns": [], "overall_confidence": .9,
    } for shot in task["shots"]]
    with pytest.raises(workbench.WorkbenchError, match="镜头"):
        workbench.submit_agent_material_vision(project, asset_id, "vision", {
            "model": "gpt-6-luna", "task_fingerprint": task["task_fingerprint"],
            "proposal": {"shots": [{**rows[0], "shot_id": "INVENTED"}]},
        })
    workbench.submit_agent_material_vision(project, asset_id, "vision", {
        "model": "gpt-6-luna", "task_fingerprint": task["task_fingerprint"], "proposal": {"shots": rows},
    })
    assert workbench.read_agent_material_vision_task(project, asset_id, "vision")["status"] == "completed"


def test_agent_batch_prepares_both_visual_stages_without_relay(tmp_path: Path, monkeypatch):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg unavailable")
    project = _project(tmp_path)
    source = project / "assets" / "video" / "chip.mp4"
    subprocess.run([
        ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x480:r=15",
        "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
    ], check=True, capture_output=True)
    state = workbench.bootstrap_workbench(project)
    asset_id = next(asset["id"] for asset in state["assets"] if asset["type"] == "video")
    monkeypatch.setattr(workbench, "test_vision_ai_connection", lambda **_kw: pytest.fail("relay preflight must not run"))
    monkeypatch.setattr(workbench, "describe_contact_sheets", lambda *_a, **_kw: pytest.fail("relay overview must not run"))
    monkeypatch.setattr(workbench, "describe_shots", lambda *_a, **_kw: pytest.fail("relay V2 must not run"))
    for stage in ("overview", "vision"):
        started = workbench.start_asset_media_index_batch(project, {
            "stage": stage, "execution_mode": "agent", "model": "gpt-6-luna",
            "asset_ids": [asset_id], "recognize_audio": False,
        })
        batch_id = started["automation"]["media_index_batch"]["job_id"]
        finished = workbench.generate_asset_media_index_batch(project, batch_id)
        assert not finished["automation"]["media_index_batch"]["failed_assets"], (stage, ascii(finished["automation"]["media_index_batch"]["failed_assets"]), next(asset["media_index"] for asset in finished["assets"] if asset["id"] == asset_id))
        assert finished["automation"]["media_index_batch"]["status"] == "completed"
        task = workbench.read_agent_material_vision_task(project, asset_id, stage)
        assert task["status"] == ("sheets_ready" if stage == "overview" else "frames_ready")


def test_workbench_adopts_all_or_none_and_rejects_locked_scene(tmp_path: Path, monkeypatch):
    project = _project(tmp_path)
    state = workbench.bootstrap_workbench(project)
    _attach_index(project, state)
    monkeypatch.setattr(workbench, "select_verified_materials", lambda request: ({"scenes": [{"scene_id": "scene-1", "clips": [
        {"capability_id": "LMC-001", "source_in_seconds": 0, "duration_seconds": 4},
        {"capability_id": "LMC-002", "source_in_seconds": 4, "duration_seconds": 5},
    ]}]}, "gpt-6-sol"))
    adopted = workbench.run_autonomous_material_selection(project, {"required_platform": "douyin", "model": "gpt-6-sol", "execution_mode": "relay"})
    assert adopted["material_selection_plan"]["status"] == "adopted"
    assert [block["end_seconds"] for block in adopted["scenes"][0]["visual_timeline"]["blocks"]] == [4, 9]
    assert (project / "artifacts" / "material_selection_plan.json").is_file()

    changed = workbench._load_for_write(project)
    changed["scenes"][0]["visual_timeline"]["blocks"][0]["locked"] = True
    workbench._save(project, changed)
    before = copy.deepcopy(workbench.read_workbench(project)["scenes"][0]["visual_timeline"])
    with pytest.raises(workbench.WorkbenchError, match="锁定"):
        workbench.run_autonomous_material_selection(project, {"required_platform": "douyin", "model": "gpt-6-sol", "execution_mode": "relay"})
    assert workbench.read_workbench(project)["scenes"][0]["visual_timeline"] == before


def test_workbench_incomplete_plan_never_changes_timeline(tmp_path: Path, monkeypatch):
    project = _project(tmp_path)
    state = workbench.bootstrap_workbench(project)
    _attach_index(project, state)
    before = copy.deepcopy(workbench.read_workbench(project)["scenes"][0]["visual_timeline"])
    monkeypatch.setattr(workbench, "select_verified_materials", lambda request: ({"scenes": [{"scene_id": "scene-1", "clips": [
        {"capability_id": "LMC-001", "source_in_seconds": 0, "duration_seconds": 4},
    ]}]}, "gpt-6-sol"))
    result = workbench.run_autonomous_material_selection(project, {"required_platform": "douyin", "model": "gpt-6-sol", "execution_mode": "relay"})
    assert result["material_selection_plan"]["status"] == "needs_more_material"
    assert result["material_selection_plan"]["scene_plans"][0]["missing_seconds"] == 5
    assert result["scenes"][0]["visual_timeline"] == before


def test_selected_model_failure_does_not_fall_back_or_adopt(tmp_path: Path, monkeypatch):
    project = _project(tmp_path)
    state = workbench.bootstrap_workbench(project)
    _attach_index(project, state)
    before = copy.deepcopy(workbench.read_workbench(project)["scenes"][0]["visual_timeline"])

    def unavailable(request):
        assert request["model"] == "gpt-6-sol"
        raise TextAIError("接口或模型不存在")

    monkeypatch.setattr(workbench, "select_verified_materials", unavailable)
    with pytest.raises(workbench.WorkbenchError, match="接口或模型不存在"):
        workbench.run_autonomous_material_selection(project, {"required_platform": "douyin", "model": "gpt-6-sol", "execution_mode": "relay"})
    current = workbench.read_workbench(project)
    assert current["scenes"][0]["visual_timeline"] == before
    assert not current.get("material_selection_plan")


def test_source_provenance_change_during_model_call_aborts_adoption(tmp_path: Path, monkeypatch):
    project = _project(tmp_path)
    state = workbench.bootstrap_workbench(project)
    _attach_index(project, state)
    before = copy.deepcopy(workbench.read_workbench(project)["scenes"][0]["visual_timeline"])

    def changed_source(_request):
        latest = workbench._load_for_write(project)
        latest["assets"][0]["provenance"]["source_url"] = "https://www.pexels.com/video/123"
        workbench._save(project, latest)
        return {"scenes": [{"scene_id": "scene-1", "clips": [
            {"capability_id": "LMC-001", "source_in_seconds": 0, "duration_seconds": 4},
            {"capability_id": "LMC-002", "source_in_seconds": 4, "duration_seconds": 5},
        ]}]}, "gpt-6-sol"

    monkeypatch.setattr(workbench, "select_verified_materials", changed_source)
    with pytest.raises(workbench.WorkbenchConflict, match="素材索引|素材合同"):
        workbench.run_autonomous_material_selection(project, {"required_platform": "douyin", "model": "gpt-6-sol", "execution_mode": "relay"})
    assert workbench.read_workbench(project)["scenes"][0]["visual_timeline"] == before


def test_unified_queue_runs_selection_and_records_a_stable_result(tmp_path: Path, monkeypatch):
    projects = tmp_path / "projects"
    projects.mkdir()
    project = _project(projects)
    state = workbench.bootstrap_workbench(project)
    _attach_index(project, state)
    monkeypatch.setattr(workbench, "select_verified_materials", lambda request: ({"scenes": [{"scene_id": "scene-1", "clips": [
        {"capability_id": "LMC-001", "source_in_seconds": 0, "duration_seconds": 4},
        {"capability_id": "LMC-002", "source_in_seconds": 4, "duration_seconds": 5},
    ]}]}, "gpt-6-sol"))
    parent = workbench.prepare_autonomous_material_selection_job(project, {"required_platform": "douyin", "model": "gpt-6-sol", "execution_mode": "relay"})
    queue = ProductionQueue(tmp_path / "queue.sqlite3", projects)
    submitted = queue.submit(
        project_id="film", kind="material_selection", source="codex", priority="normal",
        parent_job_id=parent["job_id"],
        frozen_request={"required_platform": "douyin", "model": "gpt-6-sol", "execution_mode": "relay", "request_fingerprint": parent["request_fingerprint"]},
    )
    completed = ProductionQueueWorker(queue, projects).run_once()
    assert completed["job_id"] == submitted["job_id"]
    assert completed["status"] == "completed"
    assert completed["result"]["sequence_count"] == 2
    assert workbench.read_workbench(project)["material_selection_plan"]["status"] == "adopted"


def test_two_selected_windows_materialize_without_looping(tmp_path: Path, monkeypatch):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg unavailable")
    project = _project(tmp_path)
    source = project / "assets" / "video" / "chip.mp4"
    subprocess.run([
        ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc2=size=320x568:rate=30",
        "-t", "10", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
    ], check=True, capture_output=True, timeout=40)
    state = workbench.bootstrap_workbench(project)
    _attach_index(project, state)
    monkeypatch.setattr(workbench, "select_verified_materials", lambda request: ({"scenes": [{"scene_id": "scene-1", "clips": [
        {"capability_id": "LMC-001", "source_in_seconds": 0, "duration_seconds": 4},
        {"capability_id": "LMC-002", "source_in_seconds": 4, "duration_seconds": 5},
    ]}]}, "gpt-6-sol"))
    result = workbench.run_autonomous_material_selection(project, {"required_platform": "douyin", "model": "gpt-6-sol", "execution_mode": "relay"})
    output = workbench._materialize_scene_visual_timeline(project, result, result["scenes"][0], ffmpeg)
    assert output.is_file()
    assert workbench._probe_duration_seconds(output, ffmpeg, 0) == pytest.approx(9, abs=.12)


def test_copy_skill_catalog_import_is_strict_and_idempotent(tmp_path: Path, monkeypatch):
    from backlot import material_library
    monkeypatch.setenv("OPENMONTAGE_MATERIAL_LIBRARY_DIR", str(tmp_path / "shared-library"))
    monkeypatch.setattr(material_library, "probe", lambda path: {"duration": 9, "width": 320, "height": 568})
    project = _project(tmp_path)
    workbench.bootstrap_workbench(project)
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    footage = delivery / "chip.mp4"
    footage.write_bytes(b"source-video")
    catalog = delivery / "00-素材目录.json"
    catalog.write_text(json.dumps({"schema_version": 1, "entries": [{
        "material_id": "main-01", "file_path": "chip.mp4", "file_bytes": footage.stat().st_size,
        "duration_seconds": 9, "source_platform": "douyin",
        "source_url": "https://www.douyin.com/video/123", "title": "芯片实拍",
        "rights_status": "review_required", "video_id": "123",
    }]}), encoding="utf-8")
    monkeypatch.setattr(workbench, "REPO_ROOT", tmp_path / "Haike_video")
    first = workbench.import_copy_skill_material_catalog(project, {"catalog_path": str(catalog), "required_platform": "douyin"})
    second = workbench.import_copy_skill_material_catalog(project, {"catalog_path": str(catalog), "required_platform": "douyin"})
    assert len(first["material_catalog_import"]["imported_asset_ids"]) == 1
    assert len(first["material_catalog_import"]["library_media_ids"]) == 1
    assert second["material_catalog_import"]["imported_asset_ids"] == []
    assert len(second["material_catalog_import"]["reused_asset_ids"]) == 1
    assert len(second["assets"]) == len(first["assets"])
    imported = next(item for item in first["assets"] if (item.get("generation") or {}).get("material_id") == "main-01")
    assert imported["provenance"]["source_url"] == "https://www.douyin.com/video/123"
    assert (project / imported["path"]).read_bytes() == footage.read_bytes()

    bad = json.loads(catalog.read_text(encoding="utf-8"))
    bad["entries"][0]["file_path"] = "../chip.mp4"
    catalog.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(MaterialCatalogError, match="越界"):
        read_material_catalog(catalog, workspace_root=tmp_path, required_platform="douyin")


def test_download_only_manifest_imports_the_whole_source_not_short_clips(tmp_path: Path, monkeypatch):
    from backlot import material_library
    monkeypatch.setenv("OPENMONTAGE_MATERIAL_LIBRARY_DIR", str(tmp_path / "shared-library"))
    monkeypatch.setattr(material_library, "probe", lambda path: {"duration": 37.5, "width": 320, "height": 568})
    project = _project(tmp_path)
    workbench.bootstrap_workbench(project)
    delivery = tmp_path / "raw-delivery"
    source_dir = delivery / "04-原片"
    source_dir.mkdir(parents=True)
    source = source_dir / "original.mp4"
    source.write_bytes(b"a-whole-source-video")
    manifest = delivery / "清单.json"
    manifest.write_text(json.dumps({"schema_version": 1, "mode": "download_only", "downloads": [{
        "video_id": "123", "title": "芯片原片", "file": "04-原片/original.mp4",
        "size_bytes": source.stat().st_size, "duration_seconds": 37.5,
        "source_url": "https://www.douyin.com/video/123",
    }]}), encoding="utf-8")
    monkeypatch.setattr(workbench, "REPO_ROOT", tmp_path / "Haike_video")
    result = workbench.import_copy_skill_material_catalog(project, {"catalog_path": str(manifest), "required_platform": "douyin"})
    imported = next(item for item in result["assets"] if (item.get("generation") or {}).get("video_id") == "123")
    assert imported["duration_seconds"] == 37.5
    assert (project / imported["path"]).read_bytes() == source.read_bytes()


def test_acquisition_round_is_logged_deduplicated_and_requires_rematch(tmp_path: Path, monkeypatch):
    from backlot import material_library
    monkeypatch.setenv("OPENMONTAGE_MATERIAL_LIBRARY_DIR", str(tmp_path / "shared-library"))
    monkeypatch.setattr(material_library, "probe", lambda path: {"duration": 17, "width": 320, "height": 568})
    project = _project(tmp_path)
    workbench.bootstrap_workbench(project)
    task = workbench.read_agent_visual_need_task(project, {"model": "gpt-6-sol"})
    workbench.submit_agent_visual_need_plan(project, {
        "model": "gpt-6-sol", "task_fingerprint": task["task_fingerprint"],
        "proposal": {"scenes": [{"scene_id": "scene-1", "segments": [{
            "start_seconds": 0, "end_seconds": 9, "mode": "material",
            "visual_intent": "芯片产品与生产现场", "query_terms": ["芯片现场"], "match_policy": "topic",
        }]}]},
    })
    acquisition = workbench.read_agent_material_acquisition_task(project, {
        "model": "gpt-6-sol", "required_platform": "douyin",
    })
    assert acquisition["status"] == "search_required"
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    original = delivery / "original.mp4"
    original.write_bytes(b"first source")
    manifest = delivery / "清单.json"
    manifest.write_text(json.dumps({"schema_version": 1, "mode": "download_only", "downloads": [{
        "video_id": "456", "title": "芯片现场", "file": "original.mp4",
        "size_bytes": original.stat().st_size, "duration_seconds": 17,
        "source_url": "https://www.douyin.com/video/456",
    }]}), encoding="utf-8")
    monkeypatch.setattr(workbench, "REPO_ROOT", tmp_path / "Haike_video")
    imported = workbench.import_copy_skill_material_catalog(project, {
        "catalog_path": str(manifest), "required_platform": "douyin",
        "target_id": "VT-001-001", "search_query": "芯片现场",
        "acquisition_task_fingerprint": acquisition["task_fingerprint"],
    })
    assert imported["material_acquisition"]["rounds"][0]["status"] == "imported"
    assert len(imported["material_catalog_import"]["imported_asset_ids"]) == 1
    pending_index = workbench.read_agent_material_acquisition_task(project, {
        "model": "gpt-6-sol", "required_platform": "douyin",
    })
    assert pending_index["status"] == "index_required"
    assert len(pending_index["assets_to_index"]) == 1
    indexed_state = workbench.read_workbench(project)
    new_asset = next(item for item in indexed_state["assets"] if item["id"] == pending_index["assets_to_index"][0])
    index = _index([_shot(1, 0, 9)])
    index["source"]["fingerprint"] = media_content_fingerprint(project / new_asset["path"])
    index["vision"]["provider"] = "agent"
    index["overview_gate"]["provider"] = "agent"
    index_path = project / "artifacts" / "media-index" / new_asset["id"] / "vision.json"
    index_path.parent.mkdir(parents=True)
    index_path.write_text(json.dumps(index), encoding="utf-8")
    new_asset["media_index"] = {"vision_index_path": str(index_path.relative_to(project)).replace("\\", "/"), "status": "completed"}
    workbench._save(project, indexed_state)
    assert workbench.read_agent_material_acquisition_task(project, {
        "model": "gpt-6-sol", "required_platform": "douyin",
    })["status"] == "rematch_required"
    selection_task = workbench.read_agent_material_selection_task(project, {
        "model": "gpt-6-sol", "required_platform": "douyin",
    })
    workbench.run_autonomous_material_selection(project, {
        "model": "gpt-6-sol", "required_platform": "douyin",
        "request_fingerprint": selection_task["request_fingerprint"],
        "proposal": {"targets": [{"target_id": "VT-001-001", "clips": [], "reason": "镜头仍需核对"}]},
    })
    gap_task = workbench.read_agent_material_acquisition_task(project, {
        "model": "gpt-6-sol", "required_platform": "douyin",
    })
    assert gap_task["status"] == "search_required"
    assert [item["target_id"] for item in gap_task["gaps"]] == ["VT-001-001"]
    original.write_bytes(b"same video, different bytes")
    manifest.write_text(json.dumps({"schema_version": 1, "mode": "download_only", "downloads": [{
        "video_id": "456", "title": "芯片现场", "file": "original.mp4",
        "size_bytes": original.stat().st_size, "duration_seconds": 17,
        "source_url": "https://www.douyin.com/video/456",
    }]}), encoding="utf-8")
    again = workbench.import_copy_skill_material_catalog(project, {
        "catalog_path": str(manifest), "required_platform": "douyin",
    })
    assert not again["material_catalog_import"]["imported_asset_ids"]
    assert len(again["material_catalog_import"]["reused_asset_ids"]) == 1


def test_http_queue_accepts_frozen_model_and_source_policy(tmp_path: Path, monkeypatch):
    projects = tmp_path / "projects"
    projects.mkdir()
    project = _project(projects)
    state = workbench.bootstrap_workbench(project)
    _attach_index(project, state)
    monkeypatch.setattr(state_mod, "PROJECTS_DIR", projects)
    monkeypatch.setattr(server_mod, "PROJECTS_DIR", projects)
    monkeypatch.setattr(server_mod, "_summary_cache", {})
    monkeypatch.setattr(server_mod, "_PROJECTS_ROOT_STR", __import__("os").path.normcase(str(projects.resolve())))

    async def no_watch():
        return None

    monkeypatch.setattr(server_mod, "_watch_projects", no_watch)
    with TestClient(server_mod.create_app()) as client:
        missing_model = client.post("/api/production-queue/jobs", json={
            "project_id": "film", "kind": "material_selection", "priority": "normal",
            "request": {"required_platform": "douyin"},
        })
        missing_agent_proposal = client.post("/api/production-queue/jobs", json={
            "project_id": "film", "kind": "material_selection", "priority": "normal",
            "request": {"required_platform": "douyin", "model": "gpt-6-sol"},
        })
        response = client.post("/api/production-queue/jobs", json={
            "project_id": "film", "kind": "material_selection", "priority": "normal",
            "request": {"required_platform": "douyin", "model": "gpt-6-sol", "execution_mode": "relay"},
        })
    assert missing_model.status_code == 422
    assert missing_agent_proposal.status_code == 422
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["queue_job"]["kind"] == "material_selection"
    assert body["parent"]["model"] == "gpt-6-sol"


def test_http_agent_task_and_default_queue_use_native_proposal(tmp_path: Path, monkeypatch):
    projects = tmp_path / "projects"
    projects.mkdir()
    project = _project(projects)
    state = workbench.bootstrap_workbench(project)
    _attach_index(project, state)
    _mark_agent_indexes(project)
    monkeypatch.setattr(state_mod, "PROJECTS_DIR", projects)
    monkeypatch.setattr(server_mod, "PROJECTS_DIR", projects)
    monkeypatch.setattr(server_mod, "_summary_cache", {})
    monkeypatch.setattr(server_mod, "_PROJECTS_ROOT_STR", __import__("os").path.normcase(str(projects.resolve())))

    async def no_watch():
        return None

    monkeypatch.setattr(server_mod, "_watch_projects", no_watch)
    with TestClient(server_mod.create_app()) as client:
        task = client.post("/api/project/film/workbench/material-selection/agent-task", json={
            "required_platform": "douyin", "model": "gpt-6-sol",
        })
        assert task.status_code == 200, task.text
        assert task.json()["execution_mode"] == "agent"
        response = client.post("/api/production-queue/jobs", json={
            "project_id": "film", "kind": "material_selection", "priority": "normal",
            "request": {"required_platform": "douyin", "model": "gpt-6-sol", "proposal": {
                "scenes": [{"scene_id": "scene-1", "clips": [
                    {"capability_id": "LMC-001", "source_in_seconds": 0, "duration_seconds": 4},
                    {"capability_id": "LMC-002", "source_in_seconds": 4, "duration_seconds": 5},
                ]}],
            }},
        })
    assert response.status_code == 200, response.text
    assert response.json()["parent"]["execution_mode"] == "agent"


def test_batch_visual_index_does_not_reuse_another_models_evidence(tmp_path: Path):
    project = _project(tmp_path)
    state = workbench.bootstrap_workbench(project)
    _attach_index(project, state)
    current = workbench.read_workbench(project)
    asset = next(item for item in current["assets"] if item["type"] == "video")
    path = asset["media_index"]["vision_index_path"]
    assert workbench._batch_visual_index_matches_model(project, asset, path, "vision", "gpt-6-sol")
    assert not workbench._batch_visual_index_matches_model(project, asset, path, "vision", "gpt-6-luna")
    queued = workbench.start_asset_media_index_batch(project, {
        "stage": "vision", "model": "gpt-6-luna", "remote_vision_confirmed": True,
        "asset_ids": [asset["id"]],
    })
    assert queued["automation"]["media_index_batch"]["asset_ids"] == [asset["id"]]


def test_visual_model_override_is_the_frozen_model_sent_to_provider(monkeypatch):
    monkeypatch.setattr(ai_vision, "_resolved_credentials", lambda provider: ("fake-key", "https://example.invalid/v1", "old-model"))
    monkeypatch.setattr(ai_vision, "_read_env_file", lambda path: ([], {}))
    observed = {}

    class Response:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"sequence": [
                {"code": "K7", "color": "red"}, {"code": "M4", "color": "green"}, {"code": "R9", "color": "blue"},
            ]})}}]}

    def post(_url, **kwargs):
        observed.update(kwargs["json"])
        return Response()

    result = ai_vision.test_vision_ai_connection(post=post, model_override="gpt-6-sol")
    assert observed["model"] == "gpt-6-sol"
    assert result["model"] == "gpt-6-sol"
