"""Exercise final mux clocks and immutable inputs without providers or user media."""
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import wave

import pytest

from backlot.studio_composition import mux_avatar_audio
from lib.ffmpeg_locator import resolve_ffmpeg_pair


def test_mux_finite_audio_preserves_video_and_driving_waveform(tmp_path):
    pair = resolve_ffmpeg_pair()
    if not pair:
        pytest.skip("No installed FFmpeg pair")
    ffmpeg, ffprobe = pair
    raw, audio, output = (tmp_path / name for name in ("render.mp4", "drive.wav", "preview.mp4"))
    # Deliberately round the visual clock down, as in the real 16.44s failure.
    seconds = 2.04
    with wave.open(str(audio), "wb") as stream:
        stream.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        stream.writeframes(b"".join(struct.pack("<h", round(8000 * math.sin(i * 2 * math.pi * 440 / 24000)))
                                  for i in range(round(seconds * 24000))))
    original = hashlib.sha256(audio.read_bytes()).hexdigest()
    def run(args, timeout=20):
        return subprocess.run([str(a) for a in args], capture_output=True, check=True, timeout=timeout)
    run([ffmpeg, "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "color=size=96x128:rate=30",
         "-i", audio, "-t", seconds, "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-aac_coder", "fast", raw])
    mux_avatar_audio(ffmpeg, raw, audio, output, 61 / 30)
    assert hashlib.sha256(audio.read_bytes()).hexdigest() == original
    info = json.loads(run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", output]).stdout)
    assert [s["codec_type"] for s in info["streams"]] == ["video", "audio"]
    assert abs(float(info["format"]["duration"]) - 61 / 30) < .12
    run([ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", output, "-f", "null", "-"])
    def picture_bytes(path):
        return run([ffmpeg, "-nostdin", "-v", "error", "-i", path, "-map", "0:v:0",
                    "-c:v", "copy", "-f", "h264", "-"]).stdout
    assert picture_bytes(raw) == picture_bytes(output)
