"""Contract regressions use synthetic inputs and temporary files; no media production."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from check_template_standards import HUB, check_package, check_spec, read_json, schema_errors
from install_workspace_agent_rules import install


class TemplateStandardsTests(unittest.TestCase):
    def spec(self, name: str = "graphic") -> dict:
        return read_json(HUB / f"agent-runbooks/template-standards/examples/{name}.json")

    def assert_rejected(self, spec: dict, phrase: str) -> None:
        errors = check_spec(spec)
        self.assertTrue(any(phrase in error for error in errors), errors)

    def ready_fixture(self, folder: Path) -> dict:
        spec = self.spec()
        spec.update(spec_kind="implementation", stage="ready")
        (folder / "runbook.md").write_text("Synthetic runbook fixture", encoding="utf-8")
        (folder / "implementation.py").write_text("# Synthetic implementation fixture", encoding="utf-8")
        report = folder / "qa.txt"
        report.write_text("Synthetic QA fixture; not a real video verification", encoding="utf-8")
        spec["authority"] = {"runbook": "runbook.md", "implementation_paths": ["implementation.py"], "parameter_source": "self"}
        spec["evidence"].append({
            "id": "fixture_qa", "source_kind": "measurement", "source": "Synthetic regression fixture",
            "locator": "qa.txt", "method": "Exercise file and hash binding only",
            "file": "qa.txt", "sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        })
        for gate in ("technical", "visual"):
            spec["validation"][gate] = {"status": "pass", "evidence_ids": ["fixture_qa"], "note": "Synthetic test declaration"}
        spec["operations"][0]["entrypoint"] = "manual: read the synthetic runbook"
        return spec

    def package_fixture(self, folder: Path) -> Path:
        hub = folder / "Haike-Videohub"
        manifest = read_json(HUB / "contracts/video-template-standard-v1.json")
        for relative in manifest["required_files"]:
            target = hub / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(HUB / relative, target)
        return hub

    def test_all_three_illustrative_examples_are_structurally_valid(self):
        for name in ("avatar", "graphic", "chart"):
            with self.subTest(name=name):
                path = HUB / f"agent-runbooks/template-standards/examples/{name}.json"
                self.assertEqual([], check_spec(read_json(path), path.parent))

    def test_missing_scene_element_is_rejected(self):
        spec = self.spec()
        spec["scenes"][0]["element_ids"].append("absent")
        self.assert_rejected(spec, "missing element")

    def test_duplicate_identity_is_rejected(self):
        spec = self.spec()
        spec["elements"].append(copy.deepcopy(spec["elements"][0]))
        self.assert_rejected(spec, "duplicate id")

    def test_timeline_gap_is_rejected(self):
        spec = self.spec()
        spec["scenes"][0]["start"] = 0.5
        self.assert_rejected(spec, "gap or overlap")

    def test_parent_cycle_is_rejected(self):
        spec = self.spec()
        spec["elements"][0]["parent_id"] = spec["elements"][1]["id"]
        spec["elements"][1]["parent_id"] = spec["elements"][0]["id"]
        self.assert_rejected(spec, "parent cycle")

    def test_slot_cannot_open_a_fixed_field(self):
        spec = self.spec()
        spec["slots"][0]["property"] = "layout.box"
        self.assert_rejected(spec, "fixed field")

    def test_embedded_text_cannot_become_a_text_slot(self):
        spec = self.spec()
        spec["assets"].append({"id": "screenshot", "kind": "image", "path": None, "source": "Synthetic screenshot", "embedded_content": ["baked text"], "rights_status": "Fixture"})
        spec["elements"][1]["content"].update(mode="embedded", asset_id="screenshot")
        self.assert_rejected(spec, "baked-in content")

    def test_transition_requires_existing_state(self):
        spec = self.spec()
        spec["elements"][1]["transitions"].append({"from": "absent", "to": "shown", "trigger": "scene_start", "start": 0, "end": 0.2, "properties": {"opacity": [0, 1]}, "easing": "linear"})
        self.assert_rejected(spec, "missing state")

    def test_reference_cannot_claim_ready(self):
        spec = self.spec()
        spec["stage"] = "ready"
        self.assert_rejected(spec, "requires implementation")

    def test_example_evidence_cannot_claim_a_pass(self):
        spec = self.spec()
        spec["validation"]["visual"].update(status="pass", evidence_ids=["example_design"])
        self.assert_rejected(spec, "does not prove")

    def test_registered_unknown_is_allowed_in_specification(self):
        self.assertEqual([], check_spec(self.spec("avatar")))

    def test_unknown_does_not_excuse_negative_known_start(self):
        marker = {"status": "unknown", "reason": "No end measured", "evidence_plan": "Measure the end"}
        for prefix in ("scene", "element"):
            with self.subTest(prefix=prefix):
                spec = self.spec()
                pointer = "/scenes/0/end" if prefix == "scene" else "/elements/0/timing/end"
                target = spec["scenes"][0] if prefix == "scene" else spec["elements"][0]["timing"]
                target.update(start=-1, end=marker)
                spec["unknowns"] = [{"path": pointer, "reason": "End pending", "evidence_plan": "Measure end", "blocks": ["execution"]}]
                self.assert_rejected(spec, "negative")

    def test_unregistered_unknown_is_rejected(self):
        spec = self.spec("avatar")
        spec["unknowns"] = []
        self.assert_rejected(spec, "unknowns record")

    def test_unknown_transition_end_does_not_excuse_an_invalid_known_start(self):
        spec = self.spec()
        marker = {"status": "unknown", "reason": "End not measured", "evidence_plan": "Measure end"}
        spec["elements"][1]["transitions"] = [{"from": "shown", "to": "shown", "trigger": "scene_start", "start": -1, "end": marker, "properties": {"opacity": [0, 1]}, "easing": "linear"}]
        spec["unknowns"] = [{"path": "/elements/1/transitions/0/end", "reason": "End pending", "evidence_plan": "Measure end", "blocks": ["execution"]}]
        self.assert_rejected(spec, "transition start outside")

    def test_unknown_pointer_must_refer_to_a_real_field(self):
        spec = self.spec("avatar")
        spec["unknowns"][0]["path"] = "/missing"
        self.assert_rejected(spec, "does not resolve")

    def test_unknown_marker_needs_a_completion_plan_in_free_form_extensions(self):
        spec = self.spec("avatar")
        del spec["extensions"]["avatar"]["face_crop"]["evidence_plan"]
        self.assert_rejected(spec, "required field missing")

    def test_schema_unsupported_keyword_cannot_hide_in_unused_branch(self):
        schemas = [
            {"anyOf": [{"type": "integer"}, {"oneOf": [{"type": "integer"}]}]},
            {"type": "object", "properties": {"absent": {"oneOf": [{"type": "integer"}]}}},
            {"$defs": {"n": {"type": "integer"}}, "$ref": "#/$defs/n", "minimum": 5},
        ]
        for schema in schemas:
            with self.subTest(schema=schema):
                value = {} if schema.get("type") == "object" else 1
                self.assertTrue(schema_errors(value, schema, schema))

    def test_ready_can_use_spec_as_sole_parameter_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            self.assertEqual([], check_spec(self.ready_fixture(path), path))

    def test_ready_requires_operation_entrypoints(self):
        with tempfile.TemporaryDirectory() as folder:
            spec = self.ready_fixture(Path(folder))
            spec["operations"][0]["entrypoint"] = None
            self.assert_rejected(spec, "entrypoint")

    def test_changed_evidence_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            spec = self.ready_fixture(path)
            (path / "qa.txt").write_text("Changed fixture", encoding="utf-8")
            self.assertTrue(any("hash mismatch" in error for error in check_spec(spec, path)))

    def test_source_snapshot_package_passes_without_sibling_repos(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual([], check_package(self.package_fixture(Path(folder))))

    def test_distribution_missing_standard_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            hub = self.package_fixture(Path(folder))
            (hub / "agent-runbooks/视频模板编写标准.md").unlink()
            self.assertTrue(any("missing agent-runbooks/视频模板编写标准.md" in error for error in check_package(hub)))

    def test_complete_workspace_requires_sibling_routes(self):
        with tempfile.TemporaryDirectory() as folder:
            hub = self.package_fixture(Path(folder))
            errors = check_package(hub, workspace=True)
            self.assertTrue(any("workspace route" in error for error in errors))

    def test_new_runbook_cannot_silently_use_the_legacy_format(self):
        with tempfile.TemporaryDirectory() as folder:
            hub = self.package_fixture(Path(folder))
            (hub / "agent-runbooks/new-template.md").write_text("# New template", encoding="utf-8")
            self.assertTrue(any("new runbook must declare" in error for error in check_package(hub)))

    def test_declared_video_template_needs_a_standard_version(self):
        with tempfile.TemporaryDirectory() as folder:
            hub = self.package_fixture(Path(folder))
            (hub / "agent-runbooks/new-template.md").write_text("# New template\n文档类型：video-template-runbook\n", encoding="utf-8")
            self.assertTrue(any("requires a standard version" in error for error in check_package(hub)))

    def test_root_installer_creates_missing_entry_and_preserves_different_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            source = path / "source.md"
            source.write_text("Distributed instructions\n", encoding="utf-8")
            workspace = path / "workspace"
            workspace.mkdir()
            self.assertTrue(install(source, workspace, create=True))
            self.assertFalse(install(source, workspace, create=True))
            target = workspace / "AGENTS.md"
            target.write_text("User instructions\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                install(source, workspace, create=True)
            self.assertEqual("User instructions\n", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
