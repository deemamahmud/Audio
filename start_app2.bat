@echo off
title Audio Loss & Distortion Monitor
echo ============================================
echo   Starting Audio Loss & Distortion Monitor
echo ============================================
echo.

REM --- Activate virtual environment if exists ---
if exist venv (
    echo Activating virtual environment...
    call venv\Scripts\activate
) else (
    echo No virtual environment found. Installing dependencies...
    python -m venv venv
    call venv\Scripts\activate
    pip install --upgrade pip
    pip install -r requirements.txt
)

echo.
echo --- Running monitor_audio.py ---
python monitor_audio.py --list-devices

echo.
set /p device_index="Enter the device number you want to monitor: "
echo.

python monitor_audio.py --device %device_index%

echo.
echo ============================================
echo   Monitoring stopped.
echo   Press any key to exit...
echo ============================================
pause >nul
