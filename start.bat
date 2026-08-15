@echo off
REM Receipts launcher for running from source (Windows).
REM Most people should install the packaged app instead - see the Releases page.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required. Install it from https://python.org and run this again.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo First run - setting things up ^(one minute^)...
  python -m venv .venv
)
call .venv\Scripts\pip.exe install -q -r requirements.txt
start "" .venv\Scripts\pythonw.exe launch.py
