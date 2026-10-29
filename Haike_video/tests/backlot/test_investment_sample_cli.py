"""Private sample CLI contracts: no account, provider, browser, or render calls."""
import importlib.util
import io
import json
from pathlib import Path

import pytest


@pytest.fixture
def sample():
    path = Path(__file__).resolve().parents[2] / "scripts/avatar_investment_sample.py"
    spec = importlib.util.spec_from_file_location("investment_sample_cli_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sample_is_frozen_as_silent_no_cloud_request(sample):
    from backlot.studio_investment import settings, semantic_events
    inputs = sample.sample_input()
    draft = {"id": "studio-" + "a" * 16, "title": "开发样片", "input": inputs}
    assert inputs["soundMode"] == "audio" and inputs["subtitles"] is False
    assert inputs["ai"] == {"enabled": False} and inputs["network_materials_enabled"] is False
    request = sample.make_request(draft, {"duration": 12, "audio_path": "local/silent.wav"}, "local-scope", "sample")
    assert request["quotes"] == {} and request["max_charge_micros"] == 0
    assert request["development_sample"]["silent"] is True
    assert request["development_sample"]["label"] == "版式与动效演示"
    cues = sample.manual_cues()
    assert max(len(cue["text"]) for cue in cues) <= 18
    assert all(0 <= cue["startMs"] < cue["endMs"] <= 12000 for cue in cues)
    events, unmatched = semantic_events(settings(draft), cues, 12)
    assert not unmatched and {event["kind"] for event in events} == {"sticker", "card"}


def test_evidence_paths_cannot_escape_ignored_workspace(sample, tmp_path, monkeypatch):
    workspace = tmp_path / "checkout"
    monkeypatch.setattr(sample, "WORKSPACE", workspace)
    monkeypatch.setattr(sample, "HAIKE", workspace / "Haike_video")
    for allowed in (workspace / ".local/sample", workspace / "Haike_video/.backlot/sample"):
        assert sample.validate_evidence_dir(allowed) == allowed.resolve()
    for forbidden in (tmp_path / "elsewhere", workspace / "Haike_video/templates/sample", workspace / ".local/../../escape"):
        with pytest.raises(ValueError, match="开发证据目录"):
            sample.validate_evidence_dir(forbidden)


def test_workspace_must_be_local_and_exact_before_any_data_access(sample, monkeypatch):
    responses = {"health": {"edition": "haike-workflow-2", "workspace": str(sample.WORKSPACE)},
                 "templates": {"templates": [{"id": sample.TEMPLATE_ID}]}}
    calls = []
    def urlopen(url, **kwargs):
        calls.append(url)
        data = responses["health" if url.endswith("/health") else "templates"]
        return io.BytesIO(json.dumps(data).encode())
    monkeypatch.setattr(sample.urllib.request, "urlopen", urlopen)
    sample.check_workspace("http://127.0.0.1:14756")
    assert len(calls) == 2
    for bad in ("https://127.0.0.1:14756", "http://example.com", "http://localhost:14756/?token=x"):
        with pytest.raises(ValueError): sample.check_workspace(bad)
    assert len(calls) == 2
    responses["health"]["workspace"] = str(sample.WORKSPACE.parent)
    with pytest.raises(ValueError, match="不是本源码工作区"):
        sample.check_workspace("http://127.0.0.1:14756")
