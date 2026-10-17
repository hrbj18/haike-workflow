"""Isolated, offline-only Whisper worker for the native production queue."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.ffmpeg_locator import resolve_ffmpeg
from lib.subprocess_window import no_window_kwargs


def decode_for_whisper(audio):
    """Read bounded local PCM, bypassing PyAV's version-dependent file API."""
    import numpy as np
    binary = resolve_ffmpeg()
    if not binary or not Path(audio).is_file():
        raise RuntimeError("本地音轨或FFmpeg不可用")
    try:
        result = subprocess.run([binary, "-hide_banner", "-nostdin", "-v", "error", "-i", str(audio),
            "-vn", "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-t", "121",
            "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"],
            capture_output=True, timeout=60, **no_window_kwargs())
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("本地音轨解码未完成，已停止识别") from None
    # Decode one extra second solely to detect overlong input, never silently
    # truncate it into a plausible shorter recognition result.
    if (result.returncode or not result.stdout or len(result.stdout) % 4
            or len(result.stdout) > int(120.25 * 16000) * 4):
        raise RuntimeError("本地音轨无效或超过120秒，已停止识别")
    samples = np.frombuffer(result.stdout, dtype="<f4").copy()
    if not np.isfinite(samples).all():
        raise RuntimeError("本地音轨包含无效采样，已停止识别")
    return samples


def main():
    parser = argparse.ArgumentParser()
    for name in ("model-dir", "audio", "output"): parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    samples = decode_for_whisper(args.audio)
    from faster_whisper import WhisperModel
    model = WhisperModel(str(args.model_dir), device="cpu", compute_type="int8",
                         cpu_threads=4, local_files_only=True)
    segments, _ = model.transcribe(samples, language="zh", word_timestamps=True,
                                  beam_size=5, vad_filter=True, initial_prompt="海客科技。")
    data = {"segments": [{"start": s.start, "end": s.end, "text": s.text,
                          "words": [{"start": w.start, "end": w.end, "text": w.word,
                                     "probability": w.probability} for w in s.words or []]}
                         for s in segments]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False)
    temp.replace(args.output)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("本地字幕识别未完成。音频已保留，请检查离线模型与本机FFmpeg。", file=sys.stderr)
        raise SystemExit(1) from None
