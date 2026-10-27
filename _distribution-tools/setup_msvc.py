"""Verify native imports and optionally install an explicit, signed local VC runtime.

No binaries are downloaded and the system runtime is never modified. The source
directory must contain the three Microsoft x64 redistributable DLLs together.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DLL_NAMES = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")
NATIVE_VENVS = ("Haike_video/.venv", "copy_skill/copy_skill-main/.venv")
MINIMUM_VERSION = (14, 44)
OFFICIAL_RUNTIME = "https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist"
_INSPECT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
$results = foreach ($name in @('vcruntime140.dll','vcruntime140_1.dll','msvcp140.dll')) {
    $path = Join-Path $env:HAIKE_MSVC_SOURCE_DIR $name
    $file = Get-Item -LiteralPath $path
    $signature = Get-AuthenticodeSignature -LiteralPath $path
    [pscustomobject]@{
        name = $name
        version = $file.VersionInfo.FileVersion
        status = [string]$signature.Status
        signer = [string]$signature.SignerCertificate.Subject
    }
}
ConvertTo-Json -InputObject @($results) -Compress
"""
_NATIVE_SCRIPT = """
import ctypes, os
if os.name == 'nt':
    ctypes.windll.kernel32.SetErrorMode(0x8003)
import site
site.main()
import onnxruntime, ctranslate2
from faster_whisper.vad import get_speech_timestamps
assert callable(get_speech_timestamps)
"""


def _x64_dll(path: Path) -> bool:
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            return False
        stream.seek(struct.unpack_from("<I", header, 60)[0])
        signature = stream.read(6)
    return signature == b"PE\0\0\x64\x86"


def inspect_runtime(source: Path) -> tuple[int, ...]:
    """Read PE headers, trusted signatures and versions without loading DLLs."""
    for name in DLL_NAMES:
        if not _x64_dll(source / name):
            raise ValueError(f"Expected an x64 PE DLL: {name}")
    child_env = {key: value for key, value in os.environ.items() if key.upper() not in {"PSMODULEPATH", "PSHOME"}}
    child_env["HAIKE_MSVC_SOURCE_DIR"] = str(source)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _INSPECT_SCRIPT],
        env=child_env,
        capture_output=True, text=True, encoding="utf-8-sig", errors="replace",
        timeout=15, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    records = json.loads(result.stdout)
    if not isinstance(records, list) or {item["name"] for item in records} != set(DLL_NAMES):
        raise ValueError("Incomplete Microsoft runtime verification")
    versions = set()
    for item in records:
        if item["status"] != "Valid" or "O=Microsoft Corporation" not in item["signer"]:
            raise ValueError(f"A valid Microsoft signature is required: {item['name']}")
        version = tuple(int(part) for part in item["version"].split(" ")[0].split("."))
        versions.add(version)
    if len(versions) != 1 or next(iter(versions))[:2] < MINIMUM_VERSION:
        raise ValueError("Use a matching Microsoft VC runtime set, version 14.44 or newer")
    return next(iter(versions))


def native_ready(python: Path) -> bool:
    spec = importlib.util.spec_from_file_location("haike_native_probe", ROOT / "Haike_video/lib/native_probe.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    # -S lets us suppress Windows fault dialogs before sitecustomize preloads DLLs.
    return probe._run_probe([str(python), "-S", "-c", _NATIVE_SCRIPT], timeout=10)


def _windows_attributes(path: Path) -> int:
    if os.name != "nt":
        return 0
    import ctypes
    from ctypes import wintypes

    get_attributes = ctypes.WinDLL("kernel32", use_last_error=True).GetFileAttributesW
    get_attributes.argtypes = (wintypes.LPCWSTR,)
    get_attributes.restype = wintypes.DWORD
    attributes = get_attributes(str(path))
    if attributes == 0xFFFFFFFF:
        error = ctypes.get_last_error()
        if error not in {2, 3}:  # Only an absent file/directory is safe to create.
            raise ctypes.WinError(error)
        return 0
    return attributes


def _safe_target(path: Path, boundary: Path) -> None:
    """Reject links/reparse points, including dangling links, before any write."""
    boundary = boundary.resolve()
    if not path.resolve().is_relative_to(boundary):
        raise ValueError("Local runtime target escapes the selected venv")
    current = path
    while True:
        # Some Windows filesystems return FILE_NOT_FOUND from lstat for a
        # dangling link while FindFirstFile/GetFileAttributes still expose its
        # reparse flag. Check that metadata before treating a target as absent.
        if _windows_attributes(current) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("Local runtime target contains a link or reparse point")
        try:
            info = current.lstat()
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError("Local runtime target contains a link or reparse point")
        # Compare canonical identities only after inspecting the original path.
        # Windows may spell the same directory as ADMINI~1 or Administrator.
        if current.resolve() == boundary:
            return
        if current.parent == current:
            raise ValueError("Local runtime target escapes the selected venv")
        current = current.parent


def configure(venv: Path, source: Path | None = None) -> str:
    _safe_target(venv.absolute(), ROOT.resolve())
    venv = venv.resolve()
    python = venv / "Scripts/python.exe"
    if not python.is_file():
        raise ValueError(f"Create {venv.relative_to(ROOT.resolve())} and install its locked dependencies first")
    destination = venv / "msvc"
    hook = venv / "Lib/site-packages/sitecustomize.py"
    for target in (destination, hook, *(destination / name for name in DLL_NAMES)):
        _safe_target(target, venv)
    template = (ROOT / "_distribution-tools/sitecustomize.py").read_bytes()
    if source is None:
        if destination.is_dir():
            source = destination
        elif native_ready(python):
            return "System VC runtime passed the native import check"
        else:
            raise ValueError(f"Native imports failed. Install the official x64 VC runtime ({OFFICIAL_RUNTIME}) "
                             "or rerun setup with -MsvcSource pointing to a matching signed DLL set")
    source = source.resolve()
    version = inspect_runtime(source)
    # Validate the entire plan before writing. Preserve any unrelated startup hook
    # and existing runtime that would require a deliberate upgrade or rollback.
    if hook.exists() and hook.read_bytes() != template:
        raise ValueError("Existing sitecustomize.py is not owned by this setup; no files changed")
    payloads = {name: (source / name).read_bytes() for name in DLL_NAMES}
    for name, content in payloads.items():
        target = destination / name
        if target.exists() and target.read_bytes() != content:
            raise ValueError(f"Existing local runtime differs: {name}; no files changed")
    for directory in (destination, hook.parent):
        directory.mkdir(parents=True, exist_ok=True)
    for name, content in payloads.items():
        target = destination / name
        if not target.exists():
            target.write_bytes(content)
        if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(content).digest():
            raise ValueError(f"Local runtime copy verification failed: {name}")
    if not hook.exists():
        hook.write_bytes(template)
    if not native_ready(python):
        raise ValueError("Local runtime installed, but the isolated native import check still failed")
    return f"Local Microsoft VC runtime {'.'.join(map(str, version))} verified; native imports passed"


def configure_all(source: Path | None = None) -> list[str]:
    """Install/check each native-capable business venv after dependency sync."""
    venvs = [ROOT / relative for relative in NATIVE_VENVS]
    if source is None:
        for venv in venvs:
            candidate = venv / "msvc"
            if all((candidate / name).is_file() for name in DLL_NAMES):
                _safe_target(candidate, ROOT.resolve())
                source = candidate
                break
    return [f"{relative}: {configure(venv, source)}" for relative, venv in zip(NATIVE_VENVS, venvs)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        print("MSVC setup applies only to Windows")
        return 0
    try:
        for result in configure_all(args.source_dir):
            print(result)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"MSVC setup failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
