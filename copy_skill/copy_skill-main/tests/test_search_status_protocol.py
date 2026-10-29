from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from douyin_intelligence.search_collector import _human_verification_status, collect_search


def status_line(**values):
    payload = {"status": "needs_human_verification", "platform": "douyin",
               "reason": "login_or_verification_required", **values}
    return "COPY_SKILL_STATUS " + json.dumps(payload)


def test_only_owned_status_values_become_fixed_message():
    message = _human_verification_status("raw-secret\n" + status_line(message="private-signature") + "\n")
    assert "人工确认" in message
    assert "private" not in message and "raw-secret" not in message


@pytest.mark.parametrize("value", [None, "COPY_SKILL_STATUS not-json", "COPY_SKILL_STATUS []",
    "COPY_SKILL_STATUS {\"status\":\"needs_human_verification\"}",
    "noise " + status_line(), status_line(status="success"), status_line(platform="evil"),
    status_line(reason="different"), status_line(message="x" * 1024)])
def test_unrecognized_protocol_cannot_relay_output(value):
    assert _human_verification_status(value) is None


def test_search_distinguishes_human_verification_from_installation_failure(tmp_path, monkeypatch):
    from douyin_intelligence import search_collector as collector

    class Session:
        def __init__(self, *args):
            pass

        def prepare(self):
            return {"status": "ready"}

        def finish(self, status):
            assert status == "failed"

    config = {"media_crawler": {"runs_output": str(tmp_path), "root": str(tmp_path)},
              "jobs": {"inspiration": {}}}
    monkeypatch.setattr("douyin_intelligence.download_credentials_adapter.download_collection_config", lambda c: c)
    monkeypatch.setattr(collector, "BrowserSession", Session)
    monkeypatch.setattr(collector, "search_command", lambda *args, **kwargs: ["runner", "--download-account-id", "3"])
    monkeypatch.setattr(collector.subprocess, "run", lambda *args, **kwargs:
        SimpleNamespace(returncode=3, stdout="secret\n" + status_line(message="raw-secret"), stderr="secret-url"))
    result = collect_search(config, 10, run_id="manual", keywords=["机器人"])
    assert result["needs_human_verification"] is True
    assert "人工确认" in result["error"] and "doctor" not in result["error"]
    assert "secret" not in json.dumps(result)
