@echo off
title AutoMovie Pro - 1-Click Portable Runtime Setup
color 0A
cd /d "%~dp0"

echo ===============================================================================
echo                AUTOMOVIE PRO - PORTABLE RUNTIME SETUP
echo               Automated 1-Click Non-Tech Environment Builder
echo ===============================================================================
echo.

:: 1. Check if local venv already exists
if exist "venv\Scripts\python.exe" (
    echo [OK] Virtual environment already exists at venv\Scripts\python.exe.
    echo Verifying core packages and bootstrap tools...
    venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
    venv\Scripts\python.exe -m app.bootstrap_runtime
    echo.
    echo [COMPLETE] AutoMovie Pro environment is verified and ready.
    goto FINISH
)

:: 2. Check if python_embedded exists
if exist "python_embedded\python.exe" (
    echo [OK] Embedded standalone Python detected at python_embedded\python.exe.
    python_embedded\python.exe -m app.bootstrap_runtime
    echo.
    echo [COMPLETE] Portable runtime ready.
    goto FINISH
)

:: 3. Check if system python is available
set SYSTEM_PY=
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set SYSTEM_PY=python
    )
)

if not defined SYSTEM_PY (
    where py >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        py -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
        if %ERRORLEVEL% EQU 0 (
            set SYSTEM_PY=py
        )
    )
)

if defined SYSTEM_PY (
    echo [STEP 1/3] System Python detected (%SYSTEM_PY%).
    echo Creating isolated local virtual environment in .\venv ...
    %SYSTEM_PY% -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment with %SYSTEM_PY%.
        goto EMBEDDED_FALLBACK
    )
    echo [STEP 2/3] Installing and upgrading dependencies from requirements.txt...
    venv\Scripts\python.exe -m pip install --upgrade pip
    venv\Scripts\python.exe -m pip install -r requirements.txt
    echo [STEP 3/3] Initializing customer tools & bootstrap assets...
    venv\Scripts\python.exe -m app.bootstrap_runtime
    echo.
    echo [SUCCESS] Environment successfully installed!
    goto FINISH
)

:EMBEDDED_FALLBACK
echo [INFO] No system Python detected. Preparing self-contained portable runtime...
echo Downloading standalone Python 3.11 embeddable package...
set "TEMP_ZIP=%TEMP%\amp_py_embed.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Write-Host 'Downloading embedded Python...'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile '%TEMP_ZIP%'"
if not exist "%TEMP_ZIP%" (
    echo [ERROR] Download failed. Please check internet connection or install Python manually.
    powershell -NoProfile -WindowStyle Hidden -Command "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; [System.Windows.Forms.MessageBox]::Show('Could not auto-download Python runtime. Please ensure your internet is connected or download Python 3.11 from python.org', 'AutoMovie Pro Setup', 0, 16)" >nul 2>&1
    pause
    exit /b 1
)

echo Extracting portable Python into .\python_embedded ...
if not exist "python_embedded" mkdir python_embedded
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%TEMP_ZIP%' -DestinationPath 'python_embedded' -Force"
del /f /q "%TEMP_ZIP%" >nul 2>&1

:: Enable site-packages in python311._pth
powershell -NoProfile -ExecutionPolicy Bypass -Command "$pth = Get-ChildItem -Path 'python_embedded\*._pth'; if ($pth) { (Get-Content $pth.FullName) -replace '#import site', 'import site' | Set-Content $pth.FullName; Add-Content -Path $pth.FullName -Value '..\'; Add-Content -Path $pth.FullName -Value 'Lib\site-packages' }"

echo Downloading get-pip.py...
set "GET_PIP=%TEMP%\get-pip.py"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%GET_PIP%'"
if exist "%GET_PIP%" (
    python_embedded\python.exe "%GET_PIP%" --no-warn-script-location
    del /f /q "%GET_PIP%" >nul 2>&1
    python_embedded\python.exe -m pip install --upgrade -r requirements.txt
    python_embedded\python.exe -m app.bootstrap_runtime
)

:FINISH
echo.
echo ===============================================================================
echo AutoMovie Pro Setup is complete!
echo You can now run Start_AutoMovie_Pro.bat or Start_AutoMovie_Pro.vbs.
echo ===============================================================================
powershell -NoProfile -WindowStyle Hidden -Command "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; [System.Windows.Forms.MessageBox]::Show('AutoMovie Pro portable environment is ready!`n`nYou can now launch AutoMovie Pro.', 'AutoMovie Pro Setup Complete', 0, 64)" >nul 2>&1
pause
exit /b 0
