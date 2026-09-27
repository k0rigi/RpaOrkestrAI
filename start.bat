@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Sanal ortam bulunamadi. README.md kurulum adimlarini tamamlayin.
  pause
  exit /b 1
)
echo RpaOrkestrAI masaustu penceresi aciliyor...
".venv\Scripts\python.exe" -u launch.py --native
if errorlevel 1 pause
