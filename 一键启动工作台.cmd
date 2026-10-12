@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-workbench.ps1" %*
set "START_RESULT=%errorlevel%"
if not "%START_RESULT%"=="0" (
  echo.
  echo Startup failed. Please keep this window for diagnostics.
  pause
)
exit /b %START_RESULT%
