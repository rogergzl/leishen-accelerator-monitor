@echo off
title Build LeiShenMonitor Distribution
cd /d "%~dp0"

echo ============================================
echo   LeiShenMonitor - Prepare Distribution
echo ============================================
echo.

set "DIST=dist\LeiShenMonitor"
set "DATA=%DIST%\data"

echo [1] Creating distribution folder...
if exist "%DIST%" rd /s /q "%DIST%"
mkdir "%DATA%" 2>nul
echo   %DIST%
echo   %DATA%

echo [2] Copying files...
copy /y "data\leishen_monitor.pyw" "%DATA%\" >nul
copy /y "data\launcher.ps1" "%DATA%\" >nul
copy /y "运行.bat" "%DIST%\" >nul
copy /y "完全卸载.bat" "%DIST%\" >nul
echo   OK

echo.
echo ============================================
echo   Distribution ready: %DIST%
echo.
echo   Files:
echo     %DIST%\运行.bat          (Run)
echo     %DIST%\完全卸载.bat       (Uninstall)
echo     %DIST%\data\...          (Core files)
echo ============================================
pause
