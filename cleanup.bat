@echo off
title Cleanup LeiShen Monitor
cd /d "%~dp0"

echo ============================================
echo   LeiShen Monitor - Force Cleanup
echo ============================================
echo.

echo [1] Killing processes...
taskkill /f /im LeiShenMonitor.exe 2>nul
taskkill /f /im pythonw.exe /fi "WINDOWTITLE eq LeiShenMonitor" 2>nul
echo Done.

echo [2] Removing scheduled tasks...
schtasks /delete /tn "LeiShenAcceleratorMonitor" /f 2>nul
schtasks /delete /tn "LeiShenMonitor" /f 2>nul

for /f "tokens=1 delims=," %%a in ('schtasks /query /fo csv /nh 2^>nul') do (
    echo %%a | findstr /i "LeiShen leigod" >nul 2>&1
    if not errorlevel 1 (
        echo   Removing: %%a
        schtasks /delete /tn %%a /f 2>nul
    )
)
echo Done.

echo [3] All tasks in scheduler:
schtasks /query /fo list /nh 2>nul | findstr /i "TaskName"

echo.
echo ============================================
echo Cleanup complete.
echo Now download the latest LeiShenMonitor.exe
echo Put it in an English-only path (e.g. C:\Tools\)
echo Then double-click to run.
echo ============================================
pause
