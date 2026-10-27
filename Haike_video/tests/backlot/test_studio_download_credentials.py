"""Studio must consume verified download accounts, never a login checkbox."""
import json
import os

import pytest

from backlot.studio import Studio, atomic_private
from backlot import studio_storyboard as storyboard


@pytest.fixture
def studio_account(tmp_path, monkeypatch):
    monkeypatch.setenv("HAIKE_DOWNLOAD_CREDENTIALS_DIR", str(tmp_path / "credentials"))
    studio = Studio(tmp_path / "projects")
    # The helper establishes copy_skill's package path without reading cookies.
    storyboard.download_account(studio)
    from douyin_intelligence.download_credentials_adapter import credential_store
    store = credential_store()
    cookie = {"name": "sessionid", "value": "studio-private-fixture", "domain": ".douyin.com", "path": "/", "expires": -1}
    store.save("douyin", 17, [cookie], verified=True)
    store.select("douyin", 17)
    crawler = tmp_path / "crawler"
    crawler.mkdir()
    (crawler / "main.py").write_text("# fixture")
    python = crawler / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("fixture")
    chrome = tmp_path / "chrome.exe"
    chrome.write_text("fixture")
    config = {"crawler_root": str(crawler), "chrome_path": str(chrome), "douyin_commercial_authorized": True}
    atomic_private(studio.private / "studio-ai/relay.json", config)
    return studio, store, config


def test_selected_ready_account_is_wired_to_real_crawler_config(studio_account, tmp_path):
    studio, store, config = studio_account
    result = storyboard.crawler_config(studio, tmp_path / "out")
    assert result["media_crawler"]["download_account_id"] == 17
    assert "studio-private-fixture" not in json.dumps(result)
    assert "studio-ai" in result["media_crawler"]["user_data_dir"]
    assert storyboard.status(studio)["douyin_login_confirmed"] is True


def test_old_login_confirmed_boolean_cannot_bypass_unverified_credentials(studio_account, tmp_path):
    studio, store, config = studio_account
    config["douyin_login_confirmed"] = True
    atomic_private(studio.private / "studio-ai/relay.json", config)
    store.update_status("douyin", 17, "unconfirmed")
    assert storyboard.status(studio)["douyin_login_confirmed"] is False
    with pytest.raises(storyboard.WorkError, match="已验证"):
        storyboard.crawler_config(studio, tmp_path / "out")


def test_explicit_studio_account_cannot_silently_fallback_to_selected(studio_account, tmp_path):
    studio, store, config = studio_account
    config["douyin_download_account_id"] = 999
    atomic_private(studio.private / "studio-ai/relay.json", config)
    with pytest.raises(storyboard.WorkError, match="已验证"):
        storyboard.crawler_config(studio, tmp_path / "out")
