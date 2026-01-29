@echo off
title Audio Loss Monitor
echo ============================================
echo   Starting Audio Loss Monitor
echo ============================================
echo.

REM --- Ensure script runs from its own directory ---
cd /d "%~dp0"

setlocal
set "APP_DIR=%~dp0"
set "PYTHON=%APP_DIR%python-embed\python.exe"

REM --- Check if Python exists ---
if not exist "%PYTHON%" (
    echo [ERROR] Embedded Python not found in "%PYTHON%"
    echo Please reinstall the application.
    pause
    exit /b 1
)

echo Setting up Python environment...
"%PYTHON%" -m ensurepip >nul 2>&1
"%PYTHON%" -m pip install --upgrade pip >nul 2>&1
"%PYTHON%" -m pip install -r "%APP_DIR%requirements.txt" >nul 2>&1

echo.
echo --- Running monitor_audio.py ---
echo.
"%PYTHON%" "%APP_DIR%monitor_audio.py"

echo.
echo ============================================
echo   Monitoring stopped.
echo   Press any key to exit...
echo ============================================
pause >nul
endlocal
