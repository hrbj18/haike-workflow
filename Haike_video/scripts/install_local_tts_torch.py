"""Install the official Windows CUDA runtime only in the local TTS environment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

CUDA_WHEELS = (
    "https://download-r2.pytorch.org/whl/cu128/torch-2.11.0%2Bcu128-cp312-cp312-win_amd64.whl#sha256=7c78215c3af4f62e63f2b2e360f1722fc719b0853c7ac22666483d9810613a4c",
    "https://download-r2.pytorch.org/whl/cu128/torchaudio-2.11.0%2Bcu128-cp312-cp312-win_amd64.whl#sha256=e0203d44b6dcf4c59f2ce38f997616e663b2a23a9e0b20ebb90ea0c787b5e86a",
)


def select_backend(requested: str) -> str:
    if requested == "cpu":
        return "cpu"
    executable = shutil.which("nvidia-smi")
    detected = False
    if executable:
        result = subprocess.run(
            [executable, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=20,
        )
        detected = result.returncode == 0 and bool(result.stdout.strip())
    if requested == "cuda" and not detected:
        raise RuntimeError("未检测到可用 NVIDIA 驱动；本次要求显卡推理，不会自动改成 CPU")
    return "cuda" if detected else "cpu"


def install(python: Path, backend: str, uv: Path | None = None) -> None:
    if backend == "cpu":
        print("[本地配音] 未选择 NVIDIA CUDA；沿用 CPU 依赖安装路径", flush=True)
        return
    if sys.platform != "win32":
        raise RuntimeError("此 CUDA 增补安装器适用于 Windows x64 / Python 3.12")
    print("[本地配音] 安装官方 CUDA 12.8 版 PyTorch 2.11 与匹配 Torchaudio", flush=True)
    # Ordinary dependencies are subsequently resolved from requirements-tts.
    # Direct, hashed wheels avoid probing PyTorch's index for PyPI packages.
    command = ([str(uv), "pip", "install", "--python", str(python), "--no-deps", "--no-index"]
               if uv else [str(python), "-m", "pip", "install", "--no-deps", "--no-index"])
    subprocess.run(command + list(CUDA_WHEELS), check=True)


def verify(python: Path, backend: str) -> dict:
    code = (
        "import json, torch; "
        "ok=torch.cuda.is_available(); "
        "info={'torch_version':torch.__version__,'cuda_version':torch.version.cuda,'cuda_available':ok}; "
        "info.update({'gpu':torch.cuda.get_device_name(0)} if ok else {}); "
        "print(json.dumps(info))"
    )
    result = subprocess.run([str(python), "-B", "-c", code],
                            capture_output=True, text=True, timeout=90, check=True)
    info = json.loads(result.stdout.strip().splitlines()[-1])
    if backend == "cuda" and not info.get("cuda_available"):
        raise RuntimeError("CUDA 依赖已安装，但显卡不可用；请检查 NVIDIA 驱动与运行环境，不会回退 CPU")
    print(json.dumps(info, ensure_ascii=False), flush=True)
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--uv", type=Path)
    parser.add_argument("--backend", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        backend = select_backend(args.backend)
        if args.check_only:
            verify(args.python.resolve(), backend)
        else:
            install(args.python.resolve(), backend, args.uv.resolve() if args.uv else None)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print("本地配音显卡环境配置失败：" + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
