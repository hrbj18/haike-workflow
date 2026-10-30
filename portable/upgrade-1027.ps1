param([string]$Target, [string]$Resources, [switch]$Check, [string]$Rollback)
$ErrorActionPreference = 'Stop'
if (-not $Target) { $Target = Read-Host '请输入原1027工作台根目录（包含02-start.cmd）' }
$Target = $Target.Trim().Trim('"')
$Target = (Resolve-Path -LiteralPath $Target).Path
$python = Join-Path $Target 'runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw '目标目录缺少包内Python' }
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$upgradeArgs = @('-s', (Join-Path $PSScriptRoot 'legacy_upgrade.py'), '--target', $Target)
if ($Resources) { $upgradeArgs += @('--resources', $Resources.Trim('"')) }
if ($Check) { $upgradeArgs += '--check' }
if ($Rollback) { $upgradeArgs += @('--rollback', $Rollback.Trim('"')) }
& $python @upgradeArgs
exit $LASTEXITCODE
