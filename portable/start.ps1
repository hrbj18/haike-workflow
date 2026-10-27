[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 14756,
    [ValidateRange(1024, 65535)][int]$PublisherPort = 8000,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'portable-env.ps1')
Set-Location -LiteralPath $bundleRoot
$portableArguments = @('start', '--port', [string]$Port, '--publisher-port', [string]$PublisherPort)
if ($NoBrowser) { $portableArguments += '--no-browser' }
Invoke-Portable -Arguments $portableArguments
exit $LASTEXITCODE
