"""Keep pytest collection and default application lifespans off real projects."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

import pytest


_PROVIDER_ENV_PREFIXES = (
    "OPENAI_", "FAL_", "REPLICATE_", "HIGGSFIELD_", "KLING_", "GOOGLE_",
    "GEMINI_", "ELEVENLABS_", "DOUBAO_", "DASHSCOPE_", "BAILIAN_", "TENCENT_",
    "RUNNINGHUB_", "SUNO_", "DOUYIN_", "HEYGEN_", "RUNWAY_", "VOLC_",
    "VIDEO_GEN_LOCAL_", "MODAL_LTX2_", "PEXELS_", "PIXABAY_", "UNSPLASH_",
    "HF_", "AZURE_SPEECH_", "XAI_", "HAIKE_API_", "VOICEBOX_", "OPENMONTAGE_TTS_",
)


def pytest_configure(config):
    # lib.paths freezes its defaults during import, before ordinary fixtures run.
    # Set these first so an uncustomized TestClient cannot recover real jobs or
    # import credentials through the repository's dotenv files.
    temporary = tempfile.TemporaryDirectory(prefix="haike-tests-")
    projects = Path(temporary.name) / "projects"
    projects.mkdir()
    replacements = {
        "OPENMONTAGE_PROJECTS_DIR": str(projects),
        "PYTHON_DOTENV_DISABLED": "1",
        "HAIKE_DOWNLOAD_CREDENTIALS_DIR": str(Path(temporary.name) / "download-credentials"),
    }
    inherited = {key: value for key, value in os.environ.items() if key.startswith(_PROVIDER_ENV_PREFIXES)}
    previous = {key: os.environ.get(key) for key in {*replacements, *inherited}}
    for key in inherited:
        os.environ.pop(key, None)
    os.environ.update(replacements)

    def cleanup():
        for key in tuple(os.environ):
            if key.startswith(_PROVIDER_ENV_PREFIXES):
                os.environ.pop(key, None)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        temporary.cleanup()

    config.add_cleanup(cleanup)


@pytest.fixture(autouse=True)
def isolate_private_configuration(tmp_path, monkeypatch):
    # The UI's config readers also read the secrets file directly, without
    # python-dotenv. Their shared path function follows CONFIG_ROOT at call time.
    # Test-specific fixtures may replace these defaults with their own files.
    from backlot import ai_text, audio_center, avatar_roles, bailian_config

    monkeypatch.setattr(ai_text, "CONFIG_ROOT", tmp_path / "private-config")
    audio = tmp_path / "audio"
    monkeypatch.setattr(audio_center, "AUDIO_CENTER_DIR", audio)
    monkeypatch.setattr(audio_center, "AUDIO_CENTER_FILE", audio / "audio_center.json")
    monkeypatch.setattr(audio_center, "PREVIEW_DIRECTORY", audio / "previews")
    monkeypatch.setattr(bailian_config, "HEALTH_FILE", audio / "bailian-health.json")
    monkeypatch.setattr(bailian_config, "SELFTEST_DIR", audio / "bailian-tests")
    roles = tmp_path / "avatar-roles"
    monkeypatch.setattr(avatar_roles, "ROLE_DIRECTORY", roles)
    monkeypatch.setattr(avatar_roles, "ROLE_FILE", roles / "roles.json")
    monkeypatch.setattr(avatar_roles, "ROLE_ASSET_DIRECTORY", roles / "assets")
