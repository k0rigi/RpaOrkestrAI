@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Sanal ortam bulunamadi. README.md kurulum adimlarini tamamlayin.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m rpa_orkestrai --native
if errorlevel 1 pause
