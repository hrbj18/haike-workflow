"""Verify a local engine against real audio before enabling it for new quotes."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot.studio import Studio, atomic_private
from backlot.studio_asr import identity, status, transcribe
from backlot.studio_render import media_probe
from backlot.work_catalog import sha


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--projects-root", type=Path, default=Path(__file__).resolve().parents[1] / "projects")
    p.add_argument("--python", type=Path)
    p.add_argument("--model-dir", type=Path)
    p.add_argument("--test-audio", type=Path)
    p.add_argument("--gateway", action="store_true", help="新报价改用原网关识别；不改旧任务")
    a = p.parse_args(); s = Studio(a.projects_root); path = s.private / "studio-asr/config.json"
    if a.gateway: atomic_private(path, {"provider": "gateway"})
    else:
        if not a.python or not a.model_dir or not a.test_audio: p.error("需要已有Python、Whisper模型目录和真实测试音频；不会自动下载模型")
        c = {"provider": "local-whisper", "python": str(a.python.absolute()),
             "model_dir": str(a.model_dir.resolve()), "model_sha256": sha(a.model_dir / "model.bin"), "verified": True}
        old = json.loads(path.read_text()) if path.is_file() else {"provider": "gateway"}
        atomic_private(path, c)
        try:
            result = transcribe(s, {"identity": identity(c)}, a.test_audio.resolve(),
                                s.private / "studio-asr/verification" / identity(c), media_probe(a.test_audio)["duration"])
        except Exception:
            atomic_private(path, old); p.exit(1, "本地字幕验收未通过，原配置保持不变。\n")
        atomic_private(s.private / "studio-asr/verification.safe", {"engine_identity": identity(c),
                       "audio_sha256": sha(a.test_audio), "segments": len(result["segments"]), "clock": result["clock"]})
    print(json.dumps(status(s), ensure_ascii=False))


if __name__ == "__main__": main()
