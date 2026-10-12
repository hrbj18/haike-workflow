[CmdletBinding()]
param(
    [ValidateRange(1, 300)]
    [int]$TimeoutSeconds = 45,
    [switch]$Restart
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot '.backlot\tts-runtime\.venv\Scripts\python.exe'
$dataDir = Join-Path $repoRoot '.backlot\tts'
$logDir = Join-Path $dataDir 'logs'
$baseUrl = 'http://127.0.0.1:17494'

function Repair-ProcessPathEnvironment {
    $environment = [Environment]::GetEnvironmentVariables('Process')
    $pathKeys = @($environment.Keys | Where-Object { [string]$_ -ieq 'Path' })
    if ($pathKeys.Count -lt 2) { return }

    $orderedKeys = @($pathKeys | Sort-Object {
        if ([string]$_ -ceq 'Path') { 0 }
        elseif ([string]$_ -ceq 'PATH') { 1 }
        else { 2 }
    })
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $parts = New-Object System.Collections.Generic.List[string]
    foreach ($key in $orderedKeys) {
        foreach ($part in ([string]$environment[$key] -split ';')) {
            $trimmed = $part.Trim()
            if ($trimmed -and $seen.Add($trimmed)) {
                [void]$parts.Add($trimmed)
            }
        }
    }
    $mergedPath = $parts -join ';'
    [Environment]::SetEnvironmentVariable('Path', $mergedPath, 'Process')
    [Environment]::SetEnvironmentVariable('PATH', $mergedPath, 'Process')
}

Repair-ProcessPathEnvironment

function Read-LocalEnvValue([string]$Name, [string]$DefaultValue = '') {
    foreach ($path in @(
        (Join-Path $repoRoot '.env.secrets.local'),
        (Join-Path $repoRoot '.env.local'),
        (Join-Path $repoRoot '.env')
    )) {
        if (-not (Test-Path -LiteralPath $path)) { continue }
        foreach ($line in (Get-Content -LiteralPath $path -Encoding UTF8)) {
            if ($line -match "^\s*$([regex]::Escape($Name))\s*=\s*(.*)$") {
                $value = $matches[1].Trim().Trim('"').Trim("'")
                if ($value) { return $value }
            }
        }
    }
    return $DefaultValue
}

function Resolve-TTSPath([string]$Value) {
    if (-not [IO.Path]::IsPathRooted($Value)) {
        $Value = Join-Path $repoRoot $Value
    }
    return [IO.Path]::GetFullPath($Value).TrimEnd('\', '/')
}

function New-LocalHealthRequest([string]$Url) {
    $request = [Net.HttpWebRequest]::Create($Url)
    # Windows PowerShell 5.1 has no -NoProxy switch. Local probes must stay
    # local even when Windows or the parent shell has configured a proxy.
    $request.Proxy = $null
    $request.Method = 'GET'
    $request.Timeout = 5000
    $request.ReadWriteTimeout = 5000
    $request.AllowAutoRedirect = $false
    return $request
}

function Get-TTSHealth {
    $request = New-LocalHealthRequest "$baseUrl/health"
    $response = $null
    $reader = $null
    try {
        $response = $request.GetResponse()
        $reader = New-Object IO.StreamReader ($response.GetResponseStream(), [Text.Encoding]::UTF8)
        return ($reader.ReadToEnd() | ConvertFrom-Json)
    } finally {
        if ($reader) { $reader.Dispose() }
        if ($response) { $response.Dispose() }
    }
}

function Assert-MatchingTTSService($Health) {
    if ($Health.service -ne 'openmontage-local-tts') {
        throw "端口 $($baseUri.Port) 被其他服务占用，未启动第二个本地配音服务。"
    }
    if (-not $Health.data_dir -or (Resolve-TTSPath ([string]$Health.data_dir)) -ine $dataDir) {
        throw "端口 $($baseUri.Port) 上的本地配音属于其他数据目录，未复用或停止：$($Health.data_dir)；本次目录：$dataDir"
    }
}

$baseUrl = (Read-LocalEnvValue 'OPENMONTAGE_TTS_BASE_URL' $baseUrl).TrimEnd('/')
$baseUri = [Uri]$baseUrl
if ($baseUri.Scheme -ne 'http' -or -not $baseUri.IsLoopback) {
    throw "OPENMONTAGE_TTS_BASE_URL 必须是本机 HTTP 地址：$baseUrl"
}
if (-not (Test-Path -LiteralPath $python)) {
    throw 'OpenMontage 本地配音尚未安装。请先运行 scripts\setup_local_tts.ps1。'
}

$dataDir = Resolve-TTSPath (Read-LocalEnvValue 'OPENMONTAGE_TTS_DATA_DIR' $dataDir)
$logDir = Join-Path $dataDir 'logs'
$env:OPENMONTAGE_TTS_DATA_DIR = $dataDir
$env:OPENMONTAGE_TTS_MODEL_CACHE = Resolve-TTSPath (Read-LocalEnvValue 'OPENMONTAGE_TTS_MODEL_CACHE' (Join-Path $dataDir 'models'))
$env:HF_HUB_CACHE = $env:OPENMONTAGE_TTS_MODEL_CACHE
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'
$runtimeDefaults = @{
    OPENMONTAGE_TTS_DEVICE = 'auto'
    OPENMONTAGE_TTS_BASE_MODEL = 'Qwen/Qwen3-TTS-12Hz-1.7B-Base'
    OPENMONTAGE_TTS_CUSTOM_MODEL = 'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice'
    OPENMONTAGE_TTS_CPU_DTYPE = 'bfloat16'
    OPENMONTAGE_TTS_OFFLINE = '0'
    OPENMONTAGE_TTS_SEED = '42'
    OPENMONTAGE_TTS_MAX_CHARS = '500'
    OPENMONTAGE_TTS_MAX_LOADED_MODELS = '1'
}
foreach ($name in $runtimeDefaults.Keys) {
    $inherited = [Environment]::GetEnvironmentVariable($name, 'Process')
    $fallback = if ($inherited) { $inherited } else { $runtimeDefaults[$name] }
    [Environment]::SetEnvironmentVariable($name, (Read-LocalEnvValue $name $fallback), 'Process')
}
$configuredEndpoint = Read-LocalEnvValue 'HF_ENDPOINT' ([Environment]::GetEnvironmentVariable('HF_ENDPOINT', 'Process'))
if ($configuredEndpoint) { $env:HF_ENDPOINT = $configuredEndpoint }

$health = $null
try {
    $health = Get-TTSHealth
} catch {
    $lastError = $_.Exception.Message
}
if ($health) {
    Assert-MatchingTTSService $health
    if (-not $Restart) {
        if ($health.status -ne 'healthy') {
            throw "本次本地配音服务依赖不完整：$($health.missing_dependencies -join ', ')；请先修复依赖或使用 -Restart。"
        }
        Write-Host '[OK] OpenMontage 本地配音服务已经运行'
        exit 0
    }
}

$listeners = @(Get-NetTCPConnection -LocalPort $baseUri.Port -State Listen -ErrorAction SilentlyContinue)
if ($Restart) {
    foreach ($ownerId in @($listeners.OwningProcess | Select-Object -Unique)) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerId" -ErrorAction SilentlyContinue
        if (-not $process -or $process.CommandLine -notmatch 'tools\.audio\.openmontage_tts_server') {
            throw "端口 $($baseUri.Port) 被非 OpenMontage 本地配音程序占用，未执行停止。"
        }
        # If health is unavailable, the command line must still prove which
        # private directory this process owns before a forced restart.
        $escapedData = [regex]::Escape($dataDir)
        if (-not $health -and $process.CommandLine -notmatch "--data-dir\s+(?:`"$escapedData`"|$escapedData)(?:\s|$)") {
            throw "端口 $($baseUri.Port) 的配音进程无法确认属于本次数据目录，未执行停止。"
        }
        Stop-Process -Id $ownerId -Force -ErrorAction Stop
    }
    if ($listeners.Count) { Start-Sleep -Milliseconds 700 }
} elseif ($listeners.Count) {
    throw "端口 $($baseUri.Port) 已被占用且未通过本次数据目录的健康检查，未启动第二个本地配音服务。"
}

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$serverArgs = @(
    '-m', 'tools.audio.openmontage_tts_server',
    '--host', '127.0.0.1',
    '--port', [string]$baseUri.Port,
    '--data-dir', ('"' + $env:OPENMONTAGE_TTS_DATA_DIR + '"')
)
Start-Process -FilePath $python -ArgumentList $serverArgs -WorkingDirectory $repoRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir 'server.out.log') `
    -RedirectStandardError (Join-Path $logDir 'server.err.log') | Out-Null

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Milliseconds 500
    $health = $null
    try {
        $health = Get-TTSHealth
    } catch {
        $lastError = $_.Exception.Message
    }
    if ($health) {
        Assert-MatchingTTSService $health
        if ($health.status -ne 'healthy') {
            $missing = ($health.missing_dependencies -join ', ')
            throw "本地配音服务已启动，但依赖不完整：$missing"
        }
        Write-Host '[OK] OpenMontage 本地配音服务启动成功'
        exit 0
    }
} while ((Get-Date) -lt $deadline)

$errorLog = Join-Path $logDir 'server.err.log'
$detail = if (Test-Path -LiteralPath $errorLog) { (Get-Content -LiteralPath $errorLog -Tail 12) -join ' | ' } else { $lastError }
throw "OpenMontage 本地配音未能在 $TimeoutSeconds 秒内启动：$detail；日志：$errorLog"
