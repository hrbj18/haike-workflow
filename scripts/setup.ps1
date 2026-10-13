[CmdletBinding()]
param([ValidateSet('skip','install')][string]$LocalTts = 'skip', [switch]$IncludeExamples, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$workflowRoot = Split-Path $PSScriptRoot -Parent
function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Executable" }
}
foreach ($name in @('python','uv','node','npm.cmd','git')) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "Install $name and add it to PATH, then rerun setup." }
}
Invoke-Checked python @('-c', "import struct,sys; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8, '64-bit Python 3.12 required'")
Invoke-Checked node @('-e', "if (Number(process.versions.node.split('.')[0]) < 22) process.exit(1)")
Invoke-Checked python @((Join-Path $PSScriptRoot 'check.py'))
if ($CheckOnly) { Write-Output 'Prerequisites and source checks passed. No dependencies installed.'; exit 0 }
Push-Location $workflowRoot
try {
    foreach ($module in @('Haike_video','creatorhub')) {
        $moduleRoot = Join-Path $workflowRoot $module
        $modulePython = Join-Path $moduleRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $modulePython)) {
            Invoke-Checked uv @('venv','--python','3.12',(Join-Path $moduleRoot '.venv'))
        }
        Invoke-Checked $modulePython @('-c','import sys; assert sys.version_info[:2] == (3,12)')
        Invoke-Checked uv @('pip','sync','--python',$modulePython,(Join-Path $workflowRoot "_distribution-tools\locks\$module.txt"))
        Invoke-Checked uv @('pip','check','--python',$modulePython)
    }
    Invoke-Checked uv @('pip','install','--python',(Join-Path $workflowRoot 'Haike_video\.venv\Scripts\python.exe'),'-r',(Join-Path $workflowRoot 'Haike_video\requirements-dev.txt'))
    Push-Location (Join-Path $workflowRoot 'copy_skill\copy_skill-main')
    try { Invoke-Checked uv @('sync','--locked','--dev','--python','3.12') } finally { Pop-Location }
    Invoke-Checked python @((Join-Path $PSScriptRoot 'configure.py'))
    Invoke-Checked python @((Join-Path $workflowRoot '_distribution-tools\portable.py'),'runtime')
    $frontends = @('Haike_video\remotion-composer','creatorhub')
    if ($IncludeExamples) { $frontends += 'Haike_video\remotion-composer\a2e' }
    foreach ($frontend in $frontends) {
        Push-Location (Join-Path $workflowRoot $frontend)
        try {
            Invoke-Checked npm.cmd @('ci','--no-audit','--no-fund')
            if ($frontend -eq 'creatorhub') { Invoke-Checked npm.cmd @('run','build:ui') }
            else { Invoke-Checked npx.cmd @('--no-install','remotion','browser','ensure') }
        } finally { Pop-Location }
    }
    if ($LocalTts -eq 'install') {
        # Optional local models remain separate from the frontend build.
        Invoke-Checked powershell.exe @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $workflowRoot 'Haike_video\scripts\setup_local_tts.ps1'))
    }
    Invoke-Checked python @((Join-Path $PSScriptRoot 'build-studio.py'))
    Invoke-Checked powershell.exe @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'check.ps1'))
    Write-Output 'Setup completed. Configure your own cloud credentials and platform accounts as needed.'
} finally { Pop-Location }
