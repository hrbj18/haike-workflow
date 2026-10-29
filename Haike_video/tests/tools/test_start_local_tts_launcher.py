"""Exercise the Windows launcher with process/health replacements, never a server."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "scripts/start_local_tts.ps1"
POWERSHELL = shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell required")


def _run(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *arguments],
        capture_output=True, encoding="utf-8", errors="replace", timeout=30,
    )


def test_health_request_is_direct_and_directory_identity_is_checked(tmp_path: Path) -> None:
    # Load only function definitions through PowerShell's own parser. The
    # production launcher body (and its process effects) is never evaluated.
    probe = tmp_path / "probe.ps1"
    probe.write_text(
        """$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($args[0], [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors -join '; ') }
foreach ($statement in $ast.EndBlock.Statements) {
    if ($statement -is [Management.Automation.Language.FunctionDefinitionAst]) {
        Invoke-Expression $statement.Extent.Text
    }
}
$repoRoot = $args[1]
$dataDir = Resolve-TTSPath '.backlot/tts'
$baseUri = [Uri]'http://127.0.0.1:17494'
$request = New-LocalHealthRequest 'http://127.0.0.1:17494/health'
if ($null -ne $request.Proxy -or $request.AllowAutoRedirect -or $request.Timeout -ne 5000) {
    throw 'Probe could use a proxy, redirect, or an unexpected timeout'
}
Assert-MatchingTTSService @{service='openmontage-local-tts';data_dir=($dataDir.ToUpperInvariant() + '\\')}
foreach ($health in @(
    @{service='other';data_dir=$dataDir},
    @{service='openmontage-local-tts';data_dir=(Join-Path $repoRoot 'other')},
    @{service='openmontage-local-tts'}
)) {
    $rejected = $false
    try { Assert-MatchingTTSService $health } catch { $rejected = $true }
    if (-not $rejected) { throw 'Foreign or unidentifiable service was accepted' }
}
'TEST_PASS'
""",
        encoding="utf-8-sig",
    )
    result = _run(probe, str(LAUNCHER), str(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "TEST_PASS" in result.stdout


def _isolated_launcher(tmp_path: Path, health: str, listeners: str = "@()") -> Path:
    repo = tmp_path / "test repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    runtime = repo / ".backlot/tts-runtime/.venv/Scripts"
    runtime.mkdir(parents=True)
    (runtime / "python.exe").touch()
    (repo / ".env.local").write_text(
        "\n".join([
            "OPENMONTAGE_TTS_MODEL_CACHE=cache-models",
            "OPENMONTAGE_TTS_DEVICE=cpu",
            "OPENMONTAGE_TTS_BASE_MODEL=example/Base",
            "OPENMONTAGE_TTS_CUSTOM_MODEL=example/Custom",
            "OPENMONTAGE_TTS_CPU_DTYPE=float32",
            "OPENMONTAGE_TTS_OFFLINE=1",
            "OPENMONTAGE_TTS_SEED=123",
            "OPENMONTAGE_TTS_MAX_CHARS=100",
            "OPENMONTAGE_TTS_MAX_LOADED_MODELS=2",
            "HF_ENDPOINT=https://model-mirror.example",
        ]), encoding="utf-8",
    )
    # Production function boundaries are identified by the real parser rather
    # than a regex that could accidentally cut nested try/finally blocks.
    transform = tmp_path / "transform.ps1"
    transform.write_text(
        """$ErrorActionPreference = 'Stop'
$source = [IO.File]::ReadAllText($args[0])
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors -join '; ') }
$function = $ast.EndBlock.Statements | Where-Object { $_.Name -eq 'Get-TTSHealth' }
$source = $source.Replace($function.Extent.Text, [IO.File]::ReadAllText($args[1]))
$source = $source.Replace("`$ErrorActionPreference = 'Stop'", [IO.File]::ReadAllText($args[2]))
[IO.File]::WriteAllText($args[3], $source, (New-Object Text.UTF8Encoding $true))
""", encoding="utf-8-sig",
    )
    health_file = tmp_path / "health.txt"
    health_file.write_text("function Get-TTSHealth { " + health + " }", encoding="utf-8-sig")
    replacements = tmp_path / "replacements.txt"
    replacements.write_text(
        """$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
function Start-Process {
    param($FilePath, $ArgumentList, $WorkingDirectory, $WindowStyle, $RedirectStandardOutput, $RedirectStandardError)
    $environment = @{}
    foreach ($name in @('BASE_MODEL', 'CUSTOM_MODEL', 'DEVICE', 'CPU_DTYPE', 'OFFLINE', 'SEED', 'MAX_CHARS', 'MAX_LOADED_MODELS', 'MODEL_CACHE')) {
        $environment[$name] = [Environment]::GetEnvironmentVariable('OPENMONTAGE_TTS_' + $name)
    }
    $environment['HF_ENDPOINT'] = $env:HF_ENDPOINT
    $environment['HF_HUB_CACHE'] = $env:HF_HUB_CACHE
    Write-Host ('TEST_ENV=' + ($environment | ConvertTo-Json -Compress))
    throw 'TEST_CAPTURE'
}
function Stop-Process { throw 'TEST_STOP' }
function Get-CimInstance { return @{CommandLine='python.exe -m tools.audio.openmontage_tts_server --data-dir C:\\foreign'} }
function Get-NetTCPConnection { return """ + listeners + " }\n",
        encoding="utf-8-sig",
    )
    target = scripts / "start_local_tts.ps1"
    result = _run(transform, str(LAUNCHER), str(health_file), str(replacements), str(target))
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def test_local_model_settings_are_inherited_by_the_service(tmp_path: Path) -> None:
    target = _isolated_launcher(tmp_path, "throw 'TEST_UNREACHABLE'")
    result = _run(target)
    records = [line.removeprefix("TEST_ENV=") for line in result.stdout.splitlines() if line.startswith("TEST_ENV=")]
    assert len(records) == 1, result.stdout + result.stderr
    environment = json.loads(records[0])
    assert environment == {
        "BASE_MODEL": "example/Base", "CUSTOM_MODEL": "example/Custom", "DEVICE": "cpu",
        "CPU_DTYPE": "float32", "OFFLINE": "1", "SEED": "123", "MAX_CHARS": "100",
        "MAX_LOADED_MODELS": "2", "MODEL_CACHE": str(target.parents[1] / "cache-models"),
        "HF_ENDPOINT": "https://model-mirror.example", "HF_HUB_CACHE": str(target.parents[1] / "cache-models"),
    }
    assert "TEST_CAPTURE" in result.stderr


@pytest.mark.parametrize("restart", [False, True])
def test_other_workspaces_service_is_neither_reused_nor_stopped(tmp_path: Path, restart: bool) -> None:
    target = _isolated_launcher(
        tmp_path,
        "return @{status='healthy';service='openmontage-local-tts';data_dir=(Join-Path $repoRoot 'other')}",
        "@{OwningProcess=999}",
    )
    result = _run(target, *(["-Restart"] if restart else []))
    assert result.returncode != 0
    assert "其他数据目录" in result.stderr
    assert "TEST_ENV=" not in result.stdout
    assert "TEST_STOP" not in result.stderr


def test_unhealthy_foreign_process_is_not_stopped(tmp_path: Path) -> None:
    target = _isolated_launcher(tmp_path, "throw 'TEST_UNREACHABLE'", "@{OwningProcess=999}")
    result = _run(target, "-Restart")
    assert result.returncode != 0
    assert "无法确认属于本次数据目录" in result.stderr
    assert "TEST_ENV=" not in result.stdout
    assert "TEST_STOP" not in result.stderr


def test_healthy_current_service_is_reused(tmp_path: Path) -> None:
    target = _isolated_launcher(
        tmp_path, "return @{status='healthy';service='openmontage-local-tts';data_dir=$dataDir}",
        "@{OwningProcess=999}",
    )
    result = _run(target)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[OK]" in result.stdout
    assert "TEST_ENV=" not in result.stdout


def test_occupied_unhealthy_port_does_not_start_second_service(tmp_path: Path) -> None:
    target = _isolated_launcher(tmp_path, "throw 'TEST_UNREACHABLE'", "@{OwningProcess=999}")
    result = _run(target)
    assert result.returncode != 0
    assert "未启动第二个本地配音服务" in result.stderr
    assert "TEST_ENV=" not in result.stdout
