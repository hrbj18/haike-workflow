@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0portable\check.ps1" %*
set "PORTABLE_RESULT=%errorlevel%"
if not "%PORTABLE_RESULT%"=="0" pause
exit /b %PORTABLE_RESULT%
