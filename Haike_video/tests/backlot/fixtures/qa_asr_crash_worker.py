"""Offline child for the ASR hard-kill journal regression test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backlot import tencent_asr as asr  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--mode", choices=("crash", "restart"), required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    asr.REC_TASK_MAX_BYTES = 1024
    asr._ffmpeg_tools = lambda _fallback: ("ffmpeg-fake", "ffprobe-fake")
    asr.probe_audio_seconds = lambda _path, _probe: asr.CHUNK_SECONDS * 2
    asr._cut_audio_chunk = lambda _ffmpeg, _source, target, start, _span: target.write_bytes(
        f"FAKECHUNK:{start:.3f}".encode("ascii")
    )
    submit_count = 0

    def transcribe(data, *, audio_format, duration_seconds=None, timeout_seconds, requests_module):
        nonlocal submit_count
        submit_count += 1
        index = int(round(float(data.split(b":", 1)[1]) / asr.CHUNK_SECONDS))
        if index == 1 and args.mode == "crash":
            time.sleep(3600)  # The parent terminates this process after both journal entries exist.
        return (
            f"第{index + 1}片文本",
            [{"start": 5.0, "end": 9.0, "text": f"第{index + 1}片"}],
            {"provider": "tencent-asr-rec-task", "task_id": f"task-{index + 1}"},
        )

    asr.transcribe_audio_bytes = transcribe
    try:
        asr.transcribe_file(args.audio, concurrency=2)
        outcome = {"outcome": "completed", "submit_count": submit_count}
    except Exception as exc:  # The restart must report ambiguous instead of paying again.
        outcome = {
            "outcome": "raised", "error_type": type(exc).__name__,
            "status": getattr(exc, "status", None), "retryable": getattr(exc, "retryable", None),
            "submit_count": submit_count,
        }
    args.result.write_text(json.dumps(outcome), encoding="utf-8")


if __name__ == "__main__":
    main()
