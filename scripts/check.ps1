$ErrorActionPreference = 'Stop'
$workflowRoot = Split-Path $PSScriptRoot -Parent
function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Check failed ($LASTEXITCODE): $Executable" }
}
Invoke-Checked python @((Join-Path $PSScriptRoot 'check.py'))
$ffmpegRoot = Join-Path $workflowRoot 'runtime\ffmpeg'
if (Test-Path -LiteralPath $ffmpegRoot) { $env:PATH = "$ffmpegRoot;$env:PATH" }
$env:VIDEOHUB_ROOT = $workflowRoot
$haikePython = Join-Path $workflowRoot 'Haike_video\.venv\Scripts\python.exe'
foreach ($module in @('Haike_video','creatorhub','copy_skill\copy_skill-main')) {
    $modulePython = Join-Path $workflowRoot "$module\.venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $modulePython)) { throw "Missing environment: $module. Run setup.ps1." }
    Invoke-Checked $modulePython @('-c','import sys; assert sys.version_info[:2] == (3,12)')
}
Invoke-Checked $haikePython @((Join-Path $workflowRoot 'Haike-Videohub\verify\make_fixtures.py'))
Invoke-Checked $haikePython @((Join-Path $workflowRoot 'Haike-Videohub\verify\check_all.py'),'--all','--root',$workflowRoot)
