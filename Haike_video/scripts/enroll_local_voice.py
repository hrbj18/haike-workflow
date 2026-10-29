"""Enroll an owner-supplied reference in the existing private Qwen3-TTS store."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
import wave


def enroll(data_dir: Path, audio: Path, text: str, name: str, ffmpeg: str) -> dict:
    text, name = text.strip(), name.strip()
    if not text or not name:
        raise ValueError("音色名称与录音逐字原文不能为空")
    if not audio.is_file() or audio.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("参考音频不存在或超过 100 MB")
    data_dir.mkdir(parents=True, exist_ok=True)
    # Do not repair or silently overwrite a corrupt/private catalogue.
    lock = data_dir / "enroll.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ValueError("另一个录入任务持有 enroll.lock；确认任务已结束后再移除该锁") from exc
    try:
        with handle:
            handle.write(str(os.getpid()))
        catalog = data_dir / "profiles.json"
        record = json.loads(catalog.read_text(encoding="utf-8-sig")) if catalog.exists() else {"profiles": []}
        if not isinstance(record, dict) or not isinstance(record.get("profiles"), list):
            raise ValueError("私有音色目录格式无效，未覆盖")
        with tempfile.TemporaryDirectory(prefix="enroll-", dir=data_dir) as scratch:
            wav = Path(scratch) / "reference.wav"
            subprocess.run([
                ffmpeg, "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
                "-format_whitelist", "wav,mp3,mov,flac,ogg,aac,matroska,webm,asf",
                "-i", str(audio.resolve()), "-t", "61", "-vn", "-ac", "1", "-ar", "24000",
                "-c:a", "pcm_s16le", str(wav),
            ], check=True, timeout=90, capture_output=True)
            with wave.open(str(wav), "rb") as stream:
                seconds = stream.getnframes() / stream.getframerate()
                if not 1 <= seconds <= 60:
                    raise ValueError("本录入工具接受 1–60 秒录音；请先准备一段清晰、单人、无配乐的参考录音")
            digest = hashlib.sha256(wav.read_bytes() + text.encode("utf-8") + name.encode("utf-8")).hexdigest()
            profile_id = "local-clone-" + digest[:24]
            existing = next((p for p in record["profiles"] if isinstance(p, dict) and p.get("id") == profile_id), None)
            if existing:
                return existing
            relative = Path("profiles") / profile_id / "reference.wav"
            destination = data_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if destination.read_bytes() != wav.read_bytes():
                    raise ValueError("目标录音已存在且内容不同，未覆盖")
            else:
                shutil.copyfile(wav, destination)
            profile = {"id": profile_id, "name": name, "language": "zh", "voice_type": "cloned",
                       "default_engine": "qwen", "preferred_sample_id": "reference",
                       "samples": [{"id": "reference", "audio_path": relative.as_posix(), "reference_text": text}]}
            record["profiles"].append(profile)
            staged = catalog.with_name("profiles." + uuid.uuid4().hex + ".tmp")
            try:
                staged.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                os.replace(staged, catalog)
            finally:
                staged.unlink(missing_ok=True)
            return profile
    finally:
        lock.unlink(missing_ok=True)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="录入自己的参考音频与逐字原文，用于本地声音克隆")
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--text-file", type=Path, help="UTF-8 录音逐字原文")
    parser.add_argument("--name")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("OPENMONTAGE_TTS_DATA_DIR") or root / ".backlot/tts"))
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or str(root.parent / "runtime/ffmpeg/ffmpeg.exe"))
    args = parser.parse_args()
    audio = args.audio or Path(input("自己的参考录音完整路径：").strip().strip('"'))
    text = args.text_file.read_text(encoding="utf-8-sig") if args.text_file else input("录音逐字原文：")
    name = args.name or input("音色名称（例如：张老师）：")
    profile = enroll(args.data_dir.resolve(), audio, text, name, args.ffmpeg)
    print("录入成功：" + profile["name"] + "，ID：" + profile["id"])
    print("刷新配音中心，选择此本地音色，先生成一段短句试听。录音与原文只保存于本机。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print("录入失败：" + str(exc))
        raise SystemExit(1)
