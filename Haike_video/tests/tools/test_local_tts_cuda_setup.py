"""GPU installation must not report success with a CPU-only runtime."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import install_local_tts_torch as setup


def test_cuda_request_refuses_missing_driver(monkeypatch):
    monkeypatch.setattr(setup.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="不会自动改成 CPU"):
        setup.select_backend("cuda")


def test_nvidia_auto_selects_cuda(monkeypatch):
    monkeypatch.setattr(setup.shutil, "which", lambda _name: "nvidia-smi")
    monkeypatch.setattr(setup.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="RTX 3050\n"))
    assert setup.select_backend("auto") == "cuda"


def test_cuda_validation_rejects_cpu_torch(monkeypatch):
    monkeypatch.setattr(setup.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout='{"torch_version":"2.11.0+cpu","cuda_available":false}'))
    with pytest.raises(RuntimeError, match="不会回退 CPU"):
        setup.verify(Path("private-tts/python.exe"), "cuda")
