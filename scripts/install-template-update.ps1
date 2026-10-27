param([string]$Target, [switch]$Check)
$ErrorActionPreference = 'Stop'
if (-not $Target) { $Target = Read-Host '输入旧版海客项目根目录（不要输入 Haike_video 子目录）' }
$Target = (Resolve-Path -LiteralPath $Target.Trim('"')).Path
$updatePython = @(
    (Join-Path $Target 'runtime/python/python.exe'),
    (Join-Path $Target 'Haike_video/.venv/Scripts/python.exe')
) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $updatePython) { throw '目标目录没有海客 Python 运行时，请核对目录或使用完整新版包。' }
$updateArguments = @('-s', (Join-Path $PSScriptRoot 'install-template-update.py'), '--target', $Target, '--bundle', $PSScriptRoot)
if ($Check) { $updateArguments += '--check' }
$env:PYTHONUTF8 = '1'
& $updatePython @updateArguments
if ($LASTEXITCODE -ne 0) { throw '更新未完成，请保留上方错误信息。' }
