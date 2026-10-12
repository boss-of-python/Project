@echo off
rem ============================================================
rem  THANS - Windows build: exe (PyInstaller) + installer (Inno)
rem  Run this from anywhere; it cds to the project root itself.
rem ============================================================
setlocal
cd /d "%~dp0..\.."

where python >nul 2>nul
if errorlevel 1 (
    echo [!] Python was not found on PATH. Install Python 3.10+ from python.org
    echo [!]     and tick "Add python.exe to PATH" during setup.
    exit /b 1
)

echo === [1/4] Installing dependencies ===
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt || exit /b 1
python -m pip install -r requirements-llm.txt || echo [!] LLM dependency failed (optional) - rule parser still works
python -m pip install -r requirements-build.txt || exit /b 1

echo === [2/4] Self-test ===
python -m thans --selftest || echo [!] tests failed - continuing anyway

echo === [3/4] Building THANS.exe ===
python scripts\build_installer.py || exit /b 1
if not exist dist\THANS.exe (
    echo [!] dist\THANS.exe not found after build.
    exit /b 1
)

echo === [4/4] Building installer (Inno Setup) ===
if not exist models\vosk-model-small-en-us-0.15 (
    echo [!] models\ not found - running the model downloader first...
    python scripts\download_models.py || echo [!] model download failed - installer will still build
)

set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if exist "%ISCC%" (
    "%ISCC%" installer\windows\setup.iss || exit /b 1
    echo.
    echo ============================================
    echo  DONE. Installer: installer\windows\Output\
    echo ============================================
) else (
    echo.
    echo ============================================
    echo  Portable build ready: dist\THANS.exe
    echo  (copy dist\THANS.exe + the models\ and scripts\
    echo   folders together - that IS the app)
    echo  For a wizard installer, install Inno Setup 6
    echo  from https://jrsoftware.org/isdl.php and
    echo  re-run this script.
    echo ============================================
)
endlocal
