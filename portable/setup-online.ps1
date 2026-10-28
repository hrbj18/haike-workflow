# Bootstrap only the application-local Python; no administrator or global PATH changes.
$ErrorActionPreference = 'Stop'
$onlineRoot = Split-Path -Parent $PSScriptRoot
$onlineSpec = Get-Content -LiteralPath (Join-Path $onlineRoot 'config\online-downloads.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$onlinePython = Join-Path $onlineRoot 'runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $onlinePython -PathType Leaf)) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $onlineCache = Join-Path $onlineRoot '.portable\downloads'
    New-Item -ItemType Directory -Path $onlineCache -Force | Out-Null
    $pythonArchive = Join-Path $onlineCache ($onlineSpec.python.sha256 + '.zip')
    $archiveOk = (Test-Path -LiteralPath $pythonArchive) -and ((Get-FileHash -LiteralPath $pythonArchive -Algorithm SHA256).Hash -eq $onlineSpec.python.sha256)
    if (-not $archiveOk) {
        foreach ($pythonUrl in $onlineSpec.python.urls) {
            try {
                Write-Host "Downloading Python: $pythonUrl"
                $ProgressPreference = 'SilentlyContinue'
                Invoke-WebRequest -UseBasicParsing -Uri $pythonUrl -OutFile ($pythonArchive + '.part') -TimeoutSec 120
                if ((Get-FileHash -LiteralPath ($pythonArchive + '.part') -Algorithm SHA256).Hash -ne $onlineSpec.python.sha256) {
                    throw 'Python checksum mismatch. Download was rejected.'
                }
                Move-Item -LiteralPath ($pythonArchive + '.part') -Destination $pythonArchive -Force
                $archiveOk = $true
                break
            } catch { Write-Warning $_.Exception.Message }
        }
    }
    if (-not $archiveOk) { throw 'Python download failed. See docs/ONLINE_INSTALL.md; rerun 01-setup.cmd to retry.' }
    # Fresh staging avoids leaving a runnable, partially extracted Python.
    $pythonStage = Join-Path $onlineCache ('python-' + [guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $pythonArchive -DestinationPath $pythonStage
    New-Item -ItemType Directory -Path (Join-Path $onlineRoot 'runtime') -Force | Out-Null
    Move-Item -LiteralPath $pythonStage -Destination (Join-Path $onlineRoot 'runtime\python')
}
& $onlinePython -s (Join-Path $PSScriptRoot 'online.py')
if ($LASTEXITCODE -ne 0) { throw 'Dependency setup failed. See .portable/logs/online-install.log, then rerun 01-setup.cmd.' }
