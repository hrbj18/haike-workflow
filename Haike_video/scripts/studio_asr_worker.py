"""Isolated, offline-only Whisper worker for the native production queue."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    for name in ("model-dir", "audio", "output"): parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    from faster_whisper import WhisperModel
    model = WhisperModel(str(args.model_dir), device="cpu", compute_type="int8",
                         cpu_threads=4, local_files_only=True)
    segments, _ = model.transcribe(str(args.audio), language="zh", word_timestamps=True,
                                  beam_size=5, vad_filter=True, initial_prompt="海客科技。")
    data = {"segments": [{"start": s.start, "end": s.end, "text": s.text,
                          "words": [{"start": w.start, "end": w.end, "text": w.word,
                                     "probability": w.probability} for w in s.words or []]}
                         for s in segments]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: json.dump(data, f, ensure_ascii=False)
    temp.replace(args.output)


if __name__ == "__main__": main()
