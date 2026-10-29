"""Material presentation reads the original queue version, with no execution."""
import json
from copy import deepcopy
from io import BytesIO

from PIL import Image

from backlot.automation_task_center import LocalSources, TaskCenter
from backlot.production_queue import ProductionQueue
from backlot.studio import Studio
from backlot.studio_network_materials import write_result
from backlot.task_material_results import task_material_result


def test_task_materials_use_frozen_version_and_only_owned_safe_previews(tmp_path):
    studio = Studio(tmp_path / "projects")
    original = studio.save_draft({"template_id": "avatar-deepblue-n1-v1", "title": "网络画面", "text": "真实内容",
                                  "input": {"network_materials_enabled": True}})
    project = studio.projects_root / original["id"]
    project.mkdir(parents=True, exist_ok=True)
    (project / "project.json").write_text(json.dumps({"id": original["id"], "title": original["title"]}), encoding="utf-8")
    image = BytesIO();Image.new("RGB", (256, 320), "blue").save(image, format="PNG")
    asset = studio.save_asset(original["id"], "相关画面.png", "image", image.getvalue())
    queue = ProductionQueue(studio.private / "production-queue.sqlite3", studio.projects_root)
    job = queue.submit(project_id=original["id"], kind="studio_avatar", source="codex", priority="normal",
                       parent_job_id="studio-1", frozen_request={"draft": original, "render_id": "studio-1"})
    plan = {"scenes": [{"id": "scene-1", "label": "相关画面", "start": 0, "end": 2,
                         "asset": {**asset, "provenance": {"source": "pexels",
                              "source_url": "https://www.pexels.com/video/12345/?token=hidden"}}}]}
    folder = project / "renders/studio-1"
    write_result(folder, status="used", message="已用于成片", plan=plan, used=True)
    changed = deepcopy(original);changed["input"]["network_materials_enabled"] = False
    studio.save_draft(changed)
    # A newer draft must not relabel an older finished version as disabled.
    center = TaskCenter(studio.private / "task-center.sqlite3", sources=LocalSources(studio.projects_root))
    task = center.create({"client_id": "network-fixture", "title": "网络画面", "stage": "完成",
                          "links": {"project_id": original["id"], "draft_id": original["id"], "queue_job_id": job["job_id"]}})
    before = (studio.db_path.read_bytes(), queue.db_path.read_bytes())
    result = center.detail(task["id"])["sources"]["material_result"]
    assert result["status"] == "used" and result["enabled"] is True and result["used_count"] == 1
    assert result["items"][0]["preview_url"] == "/api/studio/assets/" + asset["id"]
    assert result["items"][0]["source_url"] == "https://www.pexels.com/video/12345/"
    assert "hidden" not in json.dumps(result) and str(tmp_path) not in json.dumps(result)
    assert before == (studio.db_path.read_bytes(), queue.db_path.read_bytes())
    # An unrelated draft cannot be substituted for this queue's material receipt.
    bad = task_material_result(studio.projects_root, studio.db_path, queue.db_path,
                               {"draft_id": "studio-" + "f" * 16, "queue_job_id": job["job_id"]})
    assert bad["status"] == "unavailable" and not bad["items"]
    conflict = task_material_result(studio.projects_root, studio.db_path, queue.db_path,
                                    {"draft_id": original["id"], "project_id": "studio-" + "f" * 16,
                                     "queue_job_id": job["job_id"]})
    assert conflict["status"] == "unavailable" and not conflict["items"]


def test_unsubmitted_draft_reports_pending_or_disabled_without_creating_evidence(tmp_path):
    studio = Studio(tmp_path / "projects")
    draft = studio.save_draft({"template_id": "avatar-full-width-v2", "title": "待搜索", "text": "内容",
                               "input": {"network_materials_enabled": True}})
    queue_path = studio.private / "not-created.sqlite3"
    value = task_material_result(studio.projects_root, studio.db_path, queue_path, {"draft_id": draft["id"]})
    assert value["status"] == "pending" and value["used_count"] == 0
    draft["input"] = {}
    studio.save_draft(draft)
    value = task_material_result(studio.projects_root, studio.db_path, queue_path, {"draft_id": draft["id"]})
    assert value["status"] == "disabled"
    old_ai = studio.draft(draft["id"])
    old_ai["input"] = {"ai": {"enabled": True}}
    studio.save_draft(old_ai)
    value = task_material_result(studio.projects_root, studio.db_path, queue_path, {"draft_id": draft["id"]})
    assert value["status"] == "unknown" and value["enabled"] is None and value["used_count"] is None
    assert not queue_path.exists() and not (studio.projects_root / draft["id"] / "renders").exists()


def test_material_record_failure_does_not_become_a_success_or_leak_raw_debug_data(tmp_path):
    studio = Studio(tmp_path / "projects")
    draft = studio.save_draft({"template_id": "avatar-full-width-v2", "title": "素材异常", "text": "内容",
                               "input": {"network_materials_enabled": True}})
    folder = studio.projects_root / draft["id"] / "renders/studio-1"
    folder.mkdir(parents=True)
    (folder / "network-materials.json").write_text('{"private_debug":"never-return",broken', encoding="utf-8")
    value = task_material_result(studio.projects_root, studio.db_path, studio.private / "absent.sqlite3", {"draft_id": draft["id"]})
    assert value["status"] == "failed" and value["used_count"] == 0
    assert "never-return" not in json.dumps(value)
