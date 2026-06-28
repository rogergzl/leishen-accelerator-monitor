@echo off
setlocal enabledelayedexpansion
title Cleanup LeiShen Monitor
cd /d "%~dp0"

:: Auto-elevate if not admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting admin privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================
echo   LeiShen Monitor - Force Cleanup
echo ============================================
echo.

echo [1] Killing daemon process...
if exist ".daemon.pid" (
    set /p PID=<".daemon.pid"
    echo   PID found: !PID!
    taskkill /PID !PID! /F 2>nul
    del ".daemon.pid" 2>nul
) else (
    echo   No PID file, killing all pythonw.exe...
    taskkill /f /im pythonw.exe 2>nul
)
taskkill /f /im LeiShenMonitor.exe 2>nul
echo   Done.

echo [2] Removing scheduled task...
schtasks /end /tn "LeiShenMonitor" 2>nul
schtasks /delete /tn "LeiShenMonitor" /f 2>nul
echo   Done.

echo [3] Final check...
schtasks /query /tn "LeiShenMonitor" >nul 2>&1 && (
    echo   WARNING: Task still exists! Running schtasks /delete again...
    schtasks /delete /tn "LeiShenMonitor" /f
) || (
    echo   Task removed OK.
)
tasklist /fi "IMAGENAME eq pythonw.exe" /nh 2>nul | findstr "pythonw" >nul 2>&1 && (
    echo   WARNING: pythonw.exe still running!
) || (
    echo   No pythonw.exe running.
)
tasklist /fi "IMAGENAME eq LeiShenMonitor.exe" /nh 2>nul | findstr "LeiShenMonitor" >nul 2>&1 && (
    echo   WARNING: LeiShenMonitor.exe still running!
) || (
    echo   No LeiShenMonitor.exe running.
)

echo.
echo ============================================
echo   Cleanup complete. Ready for fresh install.
echo ============================================
pause
