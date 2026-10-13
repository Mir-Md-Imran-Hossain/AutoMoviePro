@echo off
title AutoMovie Pro - Industrial AI Automation
color 0B
echo ===============================================================================
echo                AUTOMOVIE PRO - SAAS DESKTOP EDITION
echo           Automated Multi-Channel AI Video Production & Publisher
echo ===============================================================================
echo.
cd /d "%~dp0"

:CHECK_RUNTIME
echo [1/3] Detecting runtime environment...

if exist "venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0venv\Scripts\python.exe"
    goto RUNTIME_FOUND
)

if exist "python_embedded\python.exe" (
    set "PYTHON_CMD=%~dp0python_embedded\python.exe"
    goto RUNTIME_FOUND
)

:: Check if system python is available and working
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python -c "import sys" >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set "PYTHON_CMD=python"
        goto RUNTIME_FOUND
    )
)

where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    py -c "import sys" >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set "PYTHON_CMD=py"
        goto RUNTIME_FOUND
    )
)

:: No Python found on the PC at all — Graceful Fallback (Zero Crash)
echo.
echo ===============================================================================
echo [ALERT] No Python runtime detected on this PC.
echo AutoMovie Pro requires an automated portable runtime to operate.
echo ===============================================================================
echo.
echo Launching 1-Click Automated Setup Wizard...

:: Show graphical dialog popup via PowerShell without crashing
powershell -NoProfile -WindowStyle Hidden -Command "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; [System.Windows.Forms.MessageBox]::Show('AutoMovie Pro requires the standalone portable runtime to be initialized.`n`nClick OK to start the 1-Click automated setup.', 'AutoMovie Pro - Setup Required', 0, 64)" >nul 2>&1

if exist "setup_portable_runtime.bat" (
    call setup_portable_runtime.bat
    if exist "venv\Scripts\python.exe" (
        set "PYTHON_CMD=%~dp0venv\Scripts\python.exe"
        goto RUNTIME_FOUND
    )
    if exist "python_embedded\python.exe" (
        set "PYTHON_CMD=%~dp0python_embedded\python.exe"
        goto RUNTIME_FOUND
    )
)

echo.
echo [ERROR] Setup could not locate or install a valid Python environment.
echo Please run setup_portable_runtime.bat directly or visit https://python.org to install Python 3.11+.
echo.
pause
exit /b 1

:RUNTIME_FOUND
echo [INFO] Python runtime detected: %PYTHON_CMD%
echo.

echo [2/3] Initializing Audio Engine & Local Cache...
if not exist "assets\audio\voice_cues\chime_ready.wav" (
    if exist "scripts\generate_voice_cues.py" (
        "%PYTHON_CMD%" scripts\generate_voice_cues.py
    )
)

echo.
echo [3/3] Launching AutoMovie Pro Local Server & Dashboard...
echo.
echo -------------------------------------------------------------------------------
echo Dashboard URL: http://127.0.0.1:8787
echo Login: ওয়েবসাইটে অর্ডার অনুমোদনের পর প্রাপ্ত Login ID ও Password দিন।
echo -------------------------------------------------------------------------------
echo.
echo Starting server and opening browser... Please do not close this console window.
echo.

"%PYTHON_CMD%" -m app.main
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [NOTICE] Server process exited with code %ERRORLEVEL%.
    pause
)
