@echo off
title AutoMovie Pro - Setup & Launcher Wizard
color 0A
cd /d "%~dp0"

set PYTHON_CMD=venv\Scripts\python.exe
if not exist "%PYTHON_CMD%" (
    set PYTHON_CMD=python
)

%PYTHON_CMD% scripts\installer_gui.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [INFO] GUI wizard closed or Python not found. Launching standard launcher...
    call Start_AutoMovie_Pro.bat
)
