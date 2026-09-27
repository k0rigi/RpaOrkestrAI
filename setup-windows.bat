@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist "pyproject.toml" goto missing_project
if exist ".venv\Scripts\python.exe" goto install
if exist ".venv" goto invalid_environment

echo RpaOrkestrAI Windows kurulumu
echo Python 3.12 veya 3.11 ^(64 bit^) araniyor...
py -3.12 -c "import struct; raise SystemExit(0 if struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto python312
py -3.11 -c "import struct; raise SystemExit(0 if struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto python311
python -c "import sys, struct; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 goto python_path

echo Python bulunamadi. Python 3.12 veya 3.11 ^(64 bit^) kurun.
echo https://www.python.org/downloads/windows/
echo Kurulumdan sonra bu dosyayi yeniden calistirin.
goto failed

:python312
py -3.12 -m venv ".venv"
if errorlevel 1 goto failed
goto install

:python311
py -3.11 -m venv ".venv"
if errorlevel 1 goto failed
goto install

:python_path
python -m venv ".venv"
if errorlevel 1 goto failed

:install
".venv\Scripts\python.exe" -c "import sys, struct; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 goto invalid_environment
echo Gerekli paketler indiriliyor. Internet baglantisi gereklidir.
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install ".[native,automation]"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\create_windows_shortcut.py
if errorlevel 1 (
  echo Masaustu kisayolu olusturulamadi. Uygulamayi start.bat ile acabilirsiniz.
) else (
  echo Masaustundeki RpaOrkestrAI Studio kisayolu terminal acmadan calisir.
)
echo.
echo Kurulum tamamlandi. Masaustu kisayolunu kullanabilirsiniz; start.bat hata ayiklama icindir.
echo Masaustu penceresi acilmazsa start-browser.bat ile tarayicida test edebilirsiniz.
echo Web otomasyonu icin ek komut: .venv\Scripts\python.exe -m playwright install chromium
if /i "%~1"=="--no-pause" exit /b 0
pause
exit /b 0

:invalid_environment
echo Mevcut .venv eksik, tasinmis veya desteklenen Python surumunde degil.
echo Uygulamayi kapatin; yalniz .venv klasorunu yeniden adlandirip kurulumu tekrar deneyin.
echo data klasorunu ve .env dosyasini koruyun. Mac sanal ortami Windows'ta kullanilamaz.
goto failed

:missing_project
echo Proje dosyalari bulunamadi. GitHub ZIP dosyasini once tamamen cikartin.

:failed
echo.
echo Kurulum tamamlanamadi. Yukaridaki hata mesajini kontrol edin.
echo Sirket agi indirmeyi engelliyorsa bu hata mesajini BT ekibinizle paylasin.
if /i "%~1"=="--no-pause" exit /b 1
pause
exit /b 1
