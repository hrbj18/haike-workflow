[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$publisherRoot = Join-Path (Split-Path $PSScriptRoot -Parent) 'creatorhub'
$publisherPython = Join-Path $publisherRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $publisherPython)) { throw 'Run scripts/setup.ps1 first.' }
Push-Location $publisherRoot
try { & $publisherPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port; exit $LASTEXITCODE }
finally { Pop-Location }
