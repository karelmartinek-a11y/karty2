@echo off
setlocal EnableExtensions

rem Spousti KajovoKarty z adresare, ve kterem tento soubor lezi.
cd /d "%~dp0"

rem Pip pouziva docasne soubory; ukladej je na disk s volnym mistem.
set "TMP=%~dp0.tmp"
set "TEMP=%~dp0.tmp"
if not exist "%TMP%" mkdir "%TMP%"

set "VENV_DIR=%~dp0.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

where py >nul 2>&1
if errorlevel 1 (
    echo [CHYBA] Nebyl nalezen Python Launcher ^(py^).
    echo Nainstalujte Python 3.12 a pri instalaci zapnete Python Launcher.
    pause
    exit /b 1
)

py -3.12 -c "import sys; print(sys.version)" >nul 2>&1
if errorlevel 1 (
    echo [CHYBA] Je vyzadovan Python 3.12.
    echo Nainstalujte Python 3.12 a spustte tento soubor znovu.
    pause
    exit /b 1
)

if not exist "%VENV_PYTHON%" (
    echo Vytvarim virtualni prostredi...
    py -3.12 -m venv "%VENV_DIR%"
    if errorlevel 1 goto :install_error
)

echo Kontroluji a doplnuji zavislosti...
"%VENV_PYTHON%" -m pip install --disable-pip-version-check --upgrade pip >nul
if errorlevel 1 goto :install_error

"%VENV_PYTHON%" -m pip install --disable-pip-version-check --editable .
if errorlevel 1 goto :install_error

echo Spoustim KajovoKarty...
"%VENV_PYTHON%" -m kajovokarty
set "EXIT_CODE=%errorlevel%"
if not "%EXIT_CODE%"=="0" (
    echo Program skoncil s kodem %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%

:install_error
echo [CHYBA] Nepodarilo se vytvorit venv nebo nainstalovat zavislosti.
echo Zkontrolujte pripojeni k internetu a chybovou zpravu vyse.
pause
exit /b 1
