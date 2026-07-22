@echo off
rem Receipts launcher (Windows)
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required. Install it from https://python.org ^(check "Add to PATH"^) and run this again.
  pause
  exit /b 1
)
if not exist ".venv" (
  echo First run - setting things up, one minute...
  python -m venv .venv
)
.venv\Scripts\pip install -q -r requirements.txt
.venv\Scripts\python app.py
pause
