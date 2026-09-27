@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Sanal ortam bulunamadi. Ilk kurulum icin setup-windows.bat dosyasini calistirin.
  echo GitHub indirmesi Python ortamini icermez; her bilgisayarda bir kez kurulum gerekir.
  if /i not "%~1"=="--no-pause" pause
  exit /b 1
)
echo RpaOrkestrAI masaustu penceresi aciliyor...
".venv\Scripts\python.exe" -u launch.py --native
set "rpa_exit_code=%errorlevel%"
if not "%rpa_exit_code%"=="0" (
  echo Masaustu penceresi acilmiyorsa start-browser.bat ile tarayicida deneyebilirsiniz.
  if /i not "%~1"=="--no-pause" pause
)
exit /b %rpa_exit_code%
