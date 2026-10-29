@echo off
setlocal
cd /d "%~dp0"
"%~dp0Haike_video\.venv\Scripts\python.exe" -X utf8 "%~dp0scripts\internal-services.py"
