[CmdletBinding()]
param([switch]$Full)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'portable-env.ps1')
Set-Location -LiteralPath $bundleRoot
$portableArguments = @('diagnose')
if ($Full) { $portableArguments += '--full' }
Invoke-Portable -Arguments $portableArguments
exit $LASTEXITCODE
