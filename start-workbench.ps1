[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 14756,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$workflowFfmpeg = Join-Path $PSScriptRoot 'runtime\ffmpeg'
if (Test-Path -LiteralPath $workflowFfmpeg) { $env:PATH = "$workflowFfmpeg;$env:PATH" }
$portableEnvironment = Join-Path $PSScriptRoot 'portable\portable-env.ps1'
if (Test-Path -LiteralPath $portableEnvironment) { . $portableEnvironment }
$starter = Join-Path $PSScriptRoot 'Haike_video\scripts\start_backlot.ps1'
if (-not (Test-Path -LiteralPath $starter)) {
    Write-Host 'Cannot find Haike_video\scripts\start_backlot.ps1. Keep this launcher in the workspace root.' -ForegroundColor Red
    exit 1
}

function Read-PublisherFingerprint {
    param([string]$BaseUrl)
    $response = $null
    try {
        $request = [System.Net.HttpWebRequest]::Create($BaseUrl + '/api/download-sessions')
        $request.Proxy = $null
        $request.AllowAutoRedirect = $false
        $request.Timeout = 1500
        $request.ReadWriteTimeout = 1500
        $response = $request.GetResponse()
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        try { $payload = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        $fingerprint = [string]$payload.service_fingerprint
        return @{ Responded = $true; Fingerprint = $fingerprint }
    } catch {
        if (-not $response -and $_.Exception.Response) { $response = $_.Exception.Response }
        return @{ Responded = ($null -ne $response); Fingerprint = '' }
    } finally {
        if ($response) { $response.Dispose() }
    }
}

function Test-PublisherPortListening {
    param([string]$TargetHost, [int]$TargetPort)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connection = $client.ConnectAsync($TargetHost, $TargetPort)
        if (-not $connection.Wait(500)) { return $false }
        return $client.Connected
    } catch { return $false } finally { $client.Dispose() }
}

function Ensure-LocalPublisher {
    $publisherRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'creatorhub')).ProviderPath
    $publisherPython = Join-Path $publisherRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $publisherPython -PathType Leaf)) {
        throw '账号服务尚未初始化，请先运行 scripts/setup.ps1；启动器不会下载依赖或复制账号。'
    }
    $publisherAddress = if ([string]::IsNullOrWhiteSpace($env:HAIKE_CREATORHUB_URL)) {
        'http://127.0.0.1:8000'
    } else { $env:HAIKE_CREATORHUB_URL.Trim() }
    [uri]$publisherUri = $null
    if (-not [uri]::TryCreate($publisherAddress, [UriKind]::Absolute, [ref]$publisherUri) -or
            $publisherUri.Scheme -ne 'http' -or
            $publisherUri.DnsSafeHost -notin @('127.0.0.1', 'localhost', '::1') -or
            $publisherUri.UserInfo -or $publisherUri.Query -or $publisherUri.Fragment -or
            $publisherUri.AbsolutePath -ne '/') {
        throw 'HAIKE_CREATORHUB_URL 必须是无账号密码的本机 HTTP 根地址，例如 http://127.0.0.1:8000。'
    }
    $publisherBase = $publisherUri.GetLeftPart([UriPartial]::Authority)
    # Match Python Path.resolve()/casefold() exactly, including Unicode paths.
    # Import runtime dependencies without importing the application or its DB.
    $fingerprintCode = 'import hashlib,sys;from pathlib import Path;import fastapi,uvicorn;print(hashlib.sha256(str(Path(sys.argv[1]).resolve()).replace(chr(92),chr(47)).casefold().encode()).hexdigest())'
    $fingerprintOutput = @(& $publisherPython -X utf8 -c $fingerprintCode $publisherRoot 2>$null)
    if ($LASTEXITCODE -ne 0 -or $fingerprintOutput.Count -ne 1 -or
            [string]$fingerprintOutput[0] -notmatch '^[0-9a-f]{64}$') {
        throw '本副本的账号服务 Python 或依赖不可用，请先运行 scripts/setup.ps1。'
    }
    $expectedFingerprint = [string]$fingerprintOutput[0]
    $env:HAIKE_CREATORHUB_URL = $publisherBase
    $identity = Read-PublisherFingerprint -BaseUrl $publisherBase
    if ($identity.Fingerprint -eq $expectedFingerprint) {
        Write-Host "已复用本副本账号服务：$publisherBase"
        return
    }
    if ($identity.Responded -or (Test-PublisherPortListening -TargetHost $publisherUri.DnsSafeHost -TargetPort $publisherUri.Port)) {
        throw "账号服务地址 $publisherBase 已被其他副本、旧版服务或其他程序占用，未停止任何进程。请为本副本设置空闲的 HAIKE_CREATORHUB_URL 端口后重试。"
    }

    $logRoot = Join-Path $PSScriptRoot '.local\launcher'
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $logStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $standardLog = Join-Path $logRoot "creatorhub-$logStamp.stdout.log"
    $errorLog = Join-Path $logRoot "creatorhub-$logStamp.stderr.log"
    $previousConfig = $env:CREATORHUB_CONFIG_PATH
    $previousUtf8 = $env:PYTHONUTF8
    try {
        # Child configuration always belongs to this checkout. No account data
        # is copied, and no publish/login/download operation is submitted.
        $env:CREATORHUB_CONFIG_PATH = Join-Path $publisherRoot 'config.yaml'
        $env:PYTHONUTF8 = '1'
        $publisherProcess = Start-Process -FilePath $publisherPython -WorkingDirectory $publisherRoot `
            -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', $publisherUri.DnsSafeHost, '--port', [string]$publisherUri.Port) `
            -WindowStyle Hidden -RedirectStandardOutput $standardLog -RedirectStandardError $errorLog -PassThru
    } finally {
        $env:CREATORHUB_CONFIG_PATH = $previousConfig
        $env:PYTHONUTF8 = $previousUtf8
    }
    Write-Host "正在启动本副本账号服务：$publisherBase"
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    while ([DateTime]::UtcNow -lt $deadline) {
        $identity = Read-PublisherFingerprint -BaseUrl $publisherBase
        if ($identity.Fingerprint -eq $expectedFingerprint) {
            Write-Host "账号服务已就绪；启动日志：$logRoot"
            return
        }
        if ($identity.Responded) {
            throw "端口 $($publisherUri.Port) 的服务身份与当前副本不符，未停止任何进程。请检查 $errorLog。"
        }
        if ($publisherProcess.HasExited) {
            throw "账号服务启动未完成（退出码 $($publisherProcess.ExitCode)），请查看 $errorLog。"
        }
        Start-Sleep -Milliseconds 500
    }
    throw "账号服务在60秒内尚未就绪，已保留启动进程及日志，请查看 $errorLog 后重试；未停止任何进程。"
}

try { Ensure-LocalPublisher } catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
if ($env:BACKLOT_NO_BROWSER -eq '1') { $NoBrowser = $true }
& $starter -Port $Port -NoBrowser:$NoBrowser -SkipLocalTts
exit $LASTEXITCODE
