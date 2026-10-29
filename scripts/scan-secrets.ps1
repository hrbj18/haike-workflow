$ErrorActionPreference = 'Stop'
$workflowRoot = Split-Path $PSScriptRoot -Parent
$toolRoot = Join-Path $workflowRoot '.local\gitleaks-8.30.1'
$executable = Join-Path $toolRoot 'gitleaks.exe'
if (-not (Test-Path -LiteralPath $executable)) {
    New-Item -ItemType Directory -Path $toolRoot -Force | Out-Null
    $archive = Join-Path $toolRoot 'gitleaks.zip'
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 120 -Uri 'https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_windows_x64.zip' -OutFile $archive
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne 'D29144DEFF3A68AA93CED33DDDF84B7FDC26070ADD4AA0F4513094C8332AFC4E') { throw 'Gitleaks checksum mismatch.' }
    Expand-Archive -LiteralPath $archive -DestinationPath $toolRoot -Force
}
# Scan exactly the Git index that would be committed, not checkout credentials,
# ignored local databases, downloaded tools or generated test files.
$snapshot = Join-Path ([System.IO.Path]::GetTempPath()) ('haike-source-scan-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $snapshot | Out-Null
try {
    Push-Location $workflowRoot
    try {
        $prefix = ($snapshot.Replace('\', '/').TrimEnd('/') + '/')
        & git checkout-index --all "--prefix=$prefix"
        if ($LASTEXITCODE -ne 0) { throw 'Cannot export the Git index for credential scanning.' }
    } finally { Pop-Location }
    Push-Location $snapshot
    try {
        $report = Join-Path $toolRoot 'source-secrets.redacted.json'
        & $executable dir . --redact --no-banner --gitleaks-ignore-path .gitleaksignore --report-path $report
        $scanExit = $LASTEXITCODE
        if ($scanExit -ne 0) {
            if (Test-Path -LiteralPath $report) {
                Get-Content -LiteralPath $report -Raw | ConvertFrom-Json | ForEach-Object {
                    Write-Output "$($_.File):$($_.StartLine) [$($_.RuleID)]"
                }
            }
            throw 'Secret scan failed; review redacted findings before upload.'
        }
    } finally { Pop-Location }
} finally {
    Remove-Item -LiteralPath $snapshot -Recurse -Force
}
