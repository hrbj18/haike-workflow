from pathlib import Path

from backlot import avatar_import


def test_bundle_model_is_found_after_workspace_move(tmp_path, monkeypatch):
    workspace = tmp_path / "新电脑 空格" / "Haike_videoflow"
    model = workspace / "runtime/models/whisper-small/revision-test"
    model.mkdir(parents=True)
    (model / "model.bin").write_bytes(b"model")
    monkeypatch.setattr(avatar_import, "__file__", str(workspace / "Haike_video/backlot/avatar_import.py"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty-profile")
    assert avatar_import._cached_whisper_model() == str(model)
    assert avatar_import.list_local_whisper_models() == [
        {"id": str(model), "label": "faster-whisper-small", "path": str(model)}
    ]


def test_bundle_default_preserves_existing_user_model_choices(tmp_path, monkeypatch):
    workspace = tmp_path / "Haike_videoflow"
    bundled = workspace / "runtime/models/whisper-small/revision-bundle"
    cached = tmp_path / "profile/.cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots/revision-user"
    for model in (bundled, cached):
        model.mkdir(parents=True)
        (model / "model.bin").write_bytes(b"model")
    monkeypatch.setattr(avatar_import, "__file__", str(workspace / "Haike_video/backlot/avatar_import.py"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "profile")
    assert avatar_import._cached_whisper_model() == str(bundled)
    assert [item["id"] for item in avatar_import.list_local_whisper_models()] == [str(bundled), str(cached)]


def test_source_checkout_keeps_legacy_cache_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(avatar_import, "__file__", str(tmp_path / "workspace/Haike_video/backlot/avatar_import.py"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "profile")
    cached = Path.home() / ".cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots/revision-user"
    cached.mkdir(parents=True)
    assert avatar_import._cached_whisper_model() == str(cached)
