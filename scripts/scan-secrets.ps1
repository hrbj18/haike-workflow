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
Push-Location $workflowRoot
try {
    & $executable dir . --redact --no-banner --gitleaks-ignore-path .gitleaksignore
    if ($LASTEXITCODE -ne 0) { throw 'Secret scan failed; review redacted findings before upload.' }
} finally { Pop-Location }
