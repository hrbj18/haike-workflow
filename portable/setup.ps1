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
$sourceRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot 'PACKAGE-MANIFEST.json'))) {
    & (Join-Path $sourceRoot 'scripts\setup.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($ConfigDocument) {
        $sourcePython = Join-Path $sourceRoot 'Haike_video\.venv\Scripts\python.exe'
        $sourceConfigArgs = @('--file', (Resolve-Path -LiteralPath $ConfigDocument).Path, '--root', $sourceRoot)
        if ($ReplaceConfig) { $sourceConfigArgs += '--replace' }
        foreach ($sourceConfigStep in @('plan', 'apply', 'check')) {
            & $sourcePython (Join-Path $sourceRoot 'scripts\configure-user.py') $sourceConfigStep @sourceConfigArgs
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    }
    exit 0
}
$privateDocument = if ($ConfigDocument) {
    (Resolve-Path -LiteralPath $ConfigDocument -ErrorAction Stop).Path
}
$releaseIdentity = Join-Path (Split-Path -Parent $PSScriptRoot) 'RELEASE.json'
if ((Test-Path -LiteralPath $releaseIdentity) -and
    ((Get-Content -LiteralPath $releaseIdentity -Raw -Encoding UTF8 | ConvertFrom-Json).distribution -eq 'online')) {
    & (Join-Path $PSScriptRoot 'setup-online.ps1')
}
. (Join-Path $PSScriptRoot 'portable-env.ps1')
Set-Location -LiteralPath $bundleRoot
if (-not $privateDocument -and (Test-Path -LiteralPath (Join-Path $bundleRoot 'private-profile\PROFILE-MANIFEST.json'))) {
    Invoke-Portable -Arguments @('prepare')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $bundlePython -s (Join-Path $bundleRoot 'scripts\install-private-profile.py') --root $bundleRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
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
