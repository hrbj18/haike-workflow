"""The default test application must never recover an operator's real jobs."""

import os
from pathlib import Path


def test_default_projects_are_isolated_before_application_import():
    from lib.paths import PROJECTS_DIR
    from backlot import server, state

    projects = Path(os.environ["OPENMONTAGE_PROJECTS_DIR"])
    assert projects.parent.name.startswith("haike-tests-")
    assert PROJECTS_DIR == projects
    assert state.PROJECTS_DIR == projects
    assert server.PROJECTS_DIR == projects


def test_repository_dotenv_loading_is_disabled_in_the_test_host():
    assert os.environ["PYTHON_DOTENV_DISABLED"] == "1"


def test_importing_screenshot_stage_preserves_the_hosts_projects_root(monkeypatch):
    import runpy
    import sys

    from lib.paths import PROJECTS_DIR

    projects = os.environ["OPENMONTAGE_PROJECTS_DIR"]
    # Execute a fresh module namespace even when collection already imported it.
    monkeypatch.setattr(sys, "path", list(sys.path))
    script = Path(__file__).resolve().parents[1] / "scripts/backlot_screenshot_stage.py"
    namespace = runpy.run_path(str(script), run_name="screenshot_stage_import_probe")

    assert os.environ["OPENMONTAGE_PROJECTS_DIR"] == projects
    assert PROJECTS_DIR == Path(projects)
    assert namespace["STAGE_DIR"] == script.parents[1] / ".backlot/screenshot-stage"


def test_ui_config_readers_share_the_isolated_secrets_path(tmp_path):
    from backlot import ai_text, ai_vision, bailian_config, runninghub_config, tencent_config

    paths = [module._secrets_path() for module in (
        ai_text, ai_vision, bailian_config, runninghub_config, tencent_config
    )]
    assert paths == [tmp_path / "private-config/.env.secrets.local"] * 5
    assert not paths[0].exists()


def test_voice_removal_uses_an_isolated_avatar_role_store(tmp_path):
    from backlot import avatar_roles

    assert avatar_roles.ROLE_DIRECTORY == tmp_path / "avatar-roles"
    assert avatar_roles.ROLE_FILE == tmp_path / "avatar-roles/roles.json"
    assert avatar_roles.ROLE_ASSET_DIRECTORY == tmp_path / "avatar-roles/assets"
    assert not avatar_roles.ROLE_FILE.exists()
