[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 14754,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$workflowFfmpeg = Join-Path $PSScriptRoot 'runtime\ffmpeg'
if (Test-Path -LiteralPath $workflowFfmpeg) { $env:PATH = "$workflowFfmpeg;$env:PATH" }
$portableEnvironment = Join-Path $PSScriptRoot 'portable\portable-env.ps1'
if (Test-Path -LiteralPath $portableEnvironment) { . $portableEnvironment }
$starter = Join-Path $PSScriptRoot 'Haike_video\scripts\start_backlot.ps1'
if (-not (Test-Path -LiteralPath $starter)) {
    Write-Host 'Cannot find Haike_video\scripts\start_backlot.ps1. Keep this launcher in the workspace root.' -ForegroundColor Red
    exit 1
}
if ($env:BACKLOT_NO_BROWSER -eq '1') { $NoBrowser = $true }
& $starter -Port $Port -NoBrowser:$NoBrowser -SkipLocalTts
exit $LASTEXITCODE
