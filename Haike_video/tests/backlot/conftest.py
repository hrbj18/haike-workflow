"""Shared fixtures for the backlot suite.

Why ``local_tts_catalog`` exists
-------------------------------

The local narration path is served by OpenMontage's own Qwen3-TTS service on
``http://127.0.0.1:17494``.  The class is still called ``VoiceboxTTS`` and the
provider id is still ``voicebox_tts`` purely as compatibility labels — the
external Voicebox project is gone (see ``docs/handoff/DECISIONS.md``).

Several audition tests deliberately force the local provider to look *available*
(they patch ``get_status``) so they can exercise the local-take state machine.
``audio_center._local_profiles()`` then asks the tool for its catalog, which is a
real HTTP call — so those tests silently required a running background service.
On a machine without it they failed with ``TTSServiceUnavailable`` for reasons
that had nothing to do with what they assert.

Stubbing the catalog keeps them hermetic.  Nothing about the production path
changes: with the service down, ``get_status()`` correctly reports unavailable
and ``_local_profiles()`` returns an empty list without touching the socket.
"""

from __future__ import annotations

import pytest

# Same shape the built-in service returns for its two private cloned voices.
LOCAL_TTS_CATALOG = (
    {"id": "voice-yaya", "name": "雅雅", "available": True},
    {"id": "voice-mengmeng", "name": "檬檬", "available": True},
)


@pytest.fixture(autouse=True)
def unavailable_optional_local_tts(monkeypatch):
    """Backlot contracts have no dependency on a developer's running TTS host.

    Local-voice scenarios explicitly override availability and the catalog.
    Transport/status protocol tests live under tests/tools and retain the real
    method because this function-scoped fixture applies only to this subtree.
    """
    from tools.audio.voicebox_tts import VoiceboxTTS
    from tools.base_tool import ToolStatus

    monkeypatch.setattr(VoiceboxTTS, "get_status", classmethod(lambda cls: ToolStatus.UNAVAILABLE))


@pytest.fixture
def internal_supplier_mode(monkeypatch):
    """Opt a specific supplier API test into the retained internal service.

    Ordinary TestClient applications keep the customer boundary. This fixture
    must run before create_app(), which freezes the internal-mode decision.
    """
    monkeypatch.setenv("HAIKE_INTERNAL_TESTING", "1")


@pytest.fixture
def local_tts_catalog(monkeypatch):
    """Serve the local TTS profile list without a running service."""
    from tools.audio.voicebox_tts import VoiceboxTTS

    def list_profiles(_cls):
        return [dict(row) for row in LOCAL_TTS_CATALOG]

    monkeypatch.setattr(VoiceboxTTS, "list_profiles", classmethod(list_profiles))
    return [dict(row) for row in LOCAL_TTS_CATALOG]
