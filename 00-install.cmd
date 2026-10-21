@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo 1. 原服务 API Key（默认）
echo 2. 海客中转站 API Key
choice /c 12 /n /t 15 /d 1 /m "请选择 [1/2]："
set "HAIKE_SETUP_ROUTE=direct"
if errorlevel 2 set "HAIKE_SETUP_ROUTE=gateway"
set "HAIKE_SETUP_DOC=%~dp0..\Haike_APIKeys\%HAIKE_SETUP_ROUTE%.private.md"
if not exist "%HAIKE_SETUP_DOC%" (
  echo 请先把 APIKey包解压到安装文件夹旁，保留 Haike_APIKeys 文件夹名称。
  pause
  exit /b 1
)
call "%~dp001-setup.cmd" -ConfigDocument "%HAIKE_SETUP_DOC%" -Full
set "HAIKE_SETUP_EXIT=%errorlevel%"
if not "%HAIKE_SETUP_EXIT%"=="0" echo 初始化未完成，请保留错误信息。
if "%HAIKE_SETUP_EXIT%"=="0" echo 安装完成，请双击 02-start.cmd。
pause
exit /b %HAIKE_SETUP_EXIT%
