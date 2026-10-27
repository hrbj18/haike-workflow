[CmdletBinding()]
param(
    [switch]$Full,
    [string]$ConfigDocument,
    [switch]$ReplaceConfig
)
$ErrorActionPreference = 'Stop'
if ($ReplaceConfig -and -not $ConfigDocument) {
    throw 'ReplaceConfig requires ConfigDocument.'
}
$privateDocument = if ($ConfigDocument) {
    (Resolve-Path -LiteralPath $ConfigDocument -ErrorAction Stop).Path
}
. (Join-Path $PSScriptRoot 'portable-env.ps1')
Set-Location -LiteralPath $bundleRoot
if ($privateDocument) {
    Invoke-Portable -Arguments @('prepare')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $configurationArguments = @('--file', $privateDocument, '--root', $bundleRoot)
    if ($ReplaceConfig) { $configurationArguments += '--replace' }
    foreach ($configurationStep in @('plan', 'apply', 'check')) {
        & $bundlePython -s (Join-Path $bundleRoot 'scripts\configure-user.py') $configurationStep @configurationArguments
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}
$portableArguments = @('diagnose')
if ($Full) { $portableArguments += '--full' }
Invoke-Portable -Arguments $portableArguments
exit $LASTEXITCODE
