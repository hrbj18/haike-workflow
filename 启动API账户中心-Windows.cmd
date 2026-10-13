@echo off
setlocal
cd /d "%~dp0api-platform"
where uv >nul 2>nul
if errorlevel 1 (
  echo Please install uv and Python 3.12 first.
  pause
  exit /b 1
)
uv sync --frozen
if errorlevel 1 (
  pause
  exit /b 1
)
uv run --frozen python launch.py
pause
