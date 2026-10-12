"""Real FFmpeg evidence must retain its V1 scope through generic references."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backlot import material_library as lib
from backlot import material_library_refs as refs
from backlot.material_library_template import indexed_pick, validate_spec
from tests.backlot.test_material_library import confirmed, db, video


def test_confirmed_template_evidence_reference_bridge_preserves_scope_and_spec(video, db, tmp_path):
    task, _, reviewed = confirmed(video, db)
    selection = indexed_pick("t25", "昇腾950", [], tmp_path / "legacy-spec", db_path=db)
    spec_path = Path(selection["spec_path"])
    spec_bytes = spec_path.read_bytes()
    spec = json.loads(spec_bytes)
    original_sha = lib.file_sha256(video)
    assert validate_spec(spec, db_path=db)
    assert len(spec) == 3
    assert {cue["clip_id"] for cue in spec} == set(reviewed["clip_ids"])

    frozen = []
    for cue in spec:
        request = {"media_id": cue["media_id"], "legacy_clip_id": cue["clip_id"],
                   "source_in": cue["source_in"], "source_out": cue["source_in"] + 3,
                   "scope": "template-band-v1", "usage_intent": "沿用已审核的中央带镜头"}
        reference = refs.freeze_reference(request, db_path=db)
        assert reference["review_status"] == "confirmed"
        assert reference["scope"] == "template-band-v1"
        snapshot = reference["evidence_snapshot"]
        assert snapshot["kind"] == "legacy-clip"
        assert snapshot["task_id"] == task["id"]
        assert snapshot["scope"] == "template-band-v1"
        assert snapshot["metadata"]["usable"] is True
        assert snapshot["evidence"]  # Real original/cropped sheets, not synthetic DB-only evidence.
        for evidence in snapshot["evidence"]:
            assert lib.file_sha256(Path(evidence["path"])) == evidence["sha256"]
        resolved = refs.resolve_reference(reference["id"], db_path=db)
        assert Path(resolved["path"]) == video.resolve()
        assert (resolved["source_in"], resolved["source_out"]) == (cue["source_in"], cue["source_in"] + 3)
        assert refs.freeze_reference(request, db_path=db) == reference
        with pytest.raises(lib.MaterialLibraryError, match="不能升级为全屏确认"):
            refs.freeze_reference({**request, "scope": "source-content"}, db_path=db)
        frozen.append(reference)

    # Creating generic references must not rewrite the old template selection,
    # crop contract, source video, or frozen specification.
    assert spec_path.read_bytes() == spec_bytes
    assert lib.file_sha256(video) == original_sha
    assert validate_spec(spec, db_path=db)

    evidence_file = Path(frozen[0]["evidence_snapshot"]["evidence"][0]["path"])
    evidence_bytes = evidence_file.read_bytes()
    corrupted = bytearray(evidence_bytes)
    corrupted[-1] ^= 1
    try:
        evidence_file.write_bytes(corrupted)
        with pytest.raises(lib.MaterialLibraryError, match="冻结证据.*内容已变化"):
            refs.resolve_reference(frozen[0]["id"], db_path=db)
        # Existing V1 validation independently enforces the same evidence gate.
        with pytest.raises(lib.MaterialLibraryError, match="分析证据.*修改"):
            validate_spec(spec, db_path=db)
    finally:
        evidence_file.write_bytes(evidence_bytes)

    assert validate_spec(spec, db_path=db)
    assert Path(refs.resolve_reference(frozen[0]["id"], db_path=db)["path"]) == video.resolve()
    assert spec_path.read_bytes() == spec_bytes
    assert lib.file_sha256(video) == original_sha
