@echo off
title LeiShen Monitor Test
cd /d "%~dp0"

:menu
cls
echo.
echo ============================================
echo   LeiShen Monitor - Dev Test
echo ============================================
echo.
echo   [1] Run GUI
echo   [2] Run daemon (console mode, Ctrl+C stop)
echo   [3] Check if leigod.exe is running
echo   [0] Exit
echo.
set /p choice="> "

if "%choice%"=="1" goto gui
if "%choice%"=="2" goto daemon
if "%choice%"=="3" goto check
if "%choice%"=="0" goto end
goto menu

:gui
    python "%~dp0leishen_monitor.pyw"
    goto end

:daemon
    echo Starting daemon mode...
    echo Press Ctrl+C to stop
    echo.
    python "%~dp0leishen_monitor.pyw" --daemon
    goto end

:check
    python "%~dp0leishen_monitor.pyw" --check
    pause
    goto menu

:end
