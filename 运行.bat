@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0data\launcher.ps1"
pause