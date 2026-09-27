@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Sanal ortam bulunamadi. Once setup-windows.bat dosyasini calistirin.
  if /i not "%~1"=="--no-pause" pause
  exit /b 1
)
echo RpaOrkestrAI tarayicida aciliyor...
echo Bu terminal acik kalmalidir. Durdurmak icin Ctrl+C kullanin.
".venv\Scripts\python.exe" -u launch.py
set "rpa_exit_code=%errorlevel%"
if not "%rpa_exit_code%"=="0" if /i not "%~1"=="--no-pause" pause
exit /b %rpa_exit_code%
