@echo off
title AutoMovie Pro - Industrial AI Automation
color 0B
echo ===============================================================================
echo                AUTOMOVIE PRO - SAAS DESKTOP EDITION
echo           Automated Multi-Channel AI Video Production & Publisher
echo ===============================================================================
echo.
echo [1/3] Checking environment & dependencies...
cd /d "%~dp0"

set PYTHON_CMD=venv\Scripts\python.exe
if not exist "%PYTHON_CMD%" (
    echo [INFO] Python virtual environment not found in local folder. Checking system python...
    set PYTHON_CMD=python
)

echo [2/3] Initializing Audio Engine & Local Cache...
if not exist "assets\audio\voice_cues\chime_ready.wav" (
    %PYTHON_CMD% scripts\generate_voice_cues.py
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

%PYTHON_CMD% -m app.main

pause

