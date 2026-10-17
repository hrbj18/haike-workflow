# This file may also be sourced by the normal source-checkout launcher.
$bundleRoot = Split-Path -Parent $PSScriptRoot
$bundlePython = Join-Path $bundleRoot 'runtime\python\python.exe'
if (Test-Path -LiteralPath $bundlePython -PathType Leaf) {
    $env:VIDEOHUB_ROOT = $bundleRoot
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONNOUSERSITE = '1'
    $env:HAIKE_PORTABLE_OFFLINE = '1'
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    $env:PYTHONPATH = ''
    $env:PIP_NO_INDEX = '1'
    $env:UV_OFFLINE = '1'
    $env:UV_PYTHON_DOWNLOADS = 'never'
    $env:npm_config_offline = 'true'
    $env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = '1'
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $bundleRoot 'runtime\playwright'
    $env:HF_HUB_OFFLINE = '1'
    $env:TRANSFORMERS_OFFLINE = '1'
    $env:TOKENIZERS_PARALLELISM = 'false'
    $env:DOUYIN_MSVC_RUNTIME_DIR = Join-Path $bundleRoot 'runtime\msvc'
    $env:FFMPEG_BINARY = Join-Path $bundleRoot 'runtime\ffmpeg\bin\ffmpeg.exe'
    $env:FFPROBE_BINARY = Join-Path $bundleRoot 'runtime\ffmpeg\bin\ffprobe.exe'
    $env:REMOTION_BROWSER_EXECUTABLE = Join-Path $bundleRoot 'runtime\browser\chrome-headless-shell.exe'
    $env:HYPERFRAMES_BROWSER_PATH = $env:REMOTION_BROWSER_EXECUTABLE
    $env:PRODUCER_HEADLESS_SHELL_PATH = $env:REMOTION_BROWSER_EXECUTABLE
    $env:HYPERFRAMES_FFMPEG_PATH = $env:FFMPEG_BINARY
    $env:HYPERFRAMES_FFPROBE_PATH = $env:FFPROBE_BINARY
    $env:HYPERFRAMES_NO_TELEMETRY = '1'
    $env:HYPERFRAMES_NO_AUTO_INSTALL = '1'
    $env:HYPERFRAMES_NO_UPDATE_CHECK = '1'
    $env:NO_PROXY = (@($env:NO_PROXY, 'localhost,127.0.0.1,::1') | Where-Object { $_ }) -join ','
    $toolPaths = @('runtime\python', 'runtime\node', 'runtime\ffmpeg\bin', 'runtime\hyperframes\node_modules\.bin') |
        ForEach-Object { Join-Path $bundleRoot $_ }
    $env:PATH = ($toolPaths + @((Join-Path $env:SystemRoot 'System32'), $env:PATH)) -join ';'
}

function Invoke-Portable {
    param([string[]]$Arguments)
    if (-not (Test-Path -LiteralPath $bundlePython -PathType Leaf)) {
        throw 'Offline Python is missing. Extract the complete portable bundle first.'
    }
    & $bundlePython -s (Join-Path $PSScriptRoot 'portable.py') @Arguments
}
