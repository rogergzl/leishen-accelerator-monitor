@echo off
title Build LeiShenMonitor
cd /d "%~dp0"

echo ============================================
echo   LeiShenMonitor - Build
echo ============================================
echo.

echo [1] Checking pyinstaller...
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo   Installing pyinstaller...
    pip install pyinstaller -q
)
echo   OK

echo [2] Building single-file exe...
pyinstaller --onefile --windowed --icon tu.ico --add-data "tu.ico;." --name LeiShenMonitor leishen_monitor.pyw
if errorlevel 1 (
    echo   FAILED
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Build complete: dist\LeiShenMonitor.exe
echo ============================================
pause
