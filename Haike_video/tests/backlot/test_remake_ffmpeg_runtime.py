"""Sampling and transcription do not require avatar graph-file options."""

from __future__ import annotations

import pytest

from scripts import remake_material_screen as screen
from scripts import remake_reference_transcript as transcript


def test_material_screen_accepts_a_normal_ffmpeg_pair(tmp_path, monkeypatch):
    binary, probe = tmp_path / "ffmpeg.exe", tmp_path / "ffprobe.exe"
    binary.write_bytes(b"stub")
    probe.write_bytes(b"stub")
    monkeypatch.setattr(screen, "resolve_ffmpeg_pair", lambda: (str(binary), str(probe)))
    assert screen.resolve_ffmpeg() == (binary, probe)


def test_material_screen_requires_its_probe(tmp_path, monkeypatch):
    binary = tmp_path / "ffmpeg.exe"
    binary.write_bytes(b"stub")
    monkeypatch.setattr(screen, "resolve_ffmpeg_pair", lambda: (str(binary), str(tmp_path / "missing-probe.exe")))
    with pytest.raises(SystemExit, match="ffprobe"):
        screen.resolve_ffmpeg()


def test_material_screen_reports_missing_ffmpeg(monkeypatch):
    monkeypatch.setattr(screen, "resolve_ffmpeg_pair", lambda: None)
    with pytest.raises(SystemExit, match="ffmpeg"):
        screen.resolve_ffmpeg()


def test_reference_audio_accepts_a_normal_ffmpeg_pair(monkeypatch):
    monkeypatch.setattr(transcript, "resolve_ffmpeg_pair", lambda: ("ffmpeg", "ffprobe"))
    assert transcript.ffmpeg_bin() == "ffmpeg"


def test_reference_audio_reports_missing_ffmpeg(monkeypatch):
    monkeypatch.setattr(transcript, "resolve_ffmpeg_pair", lambda: None)
    with pytest.raises(SystemExit, match="ffmpeg"):
        transcript.ffmpeg_bin()
