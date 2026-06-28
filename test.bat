@echo off
chcp 65001 >nul
title 雷神监控 - 开发测试
cd /d "%~dp0"

echo.
echo ═══════════════════════════════════════════
echo   雷神加速器监控 - 开发测试
echo ═══════════════════════════════════════════
echo.
echo   [1] 运行 GUI 管理界面
echo   [2] 运行 daemon (控制台模式)
echo   [3] 检测加速器是否在运行
echo   [0] 退出
echo.
set /p choice="> "

if "%choice%"=="1" goto gui
if "%choice%"=="2" goto daemon
if "%choice%"=="3" goto check
if "%choice%"=="0" goto end
goto end

:gui
    python "%~dp0leishen_monitor.pyw"
    goto end

:daemon
    echo 启动 daemon 模式 (Ctrl+C 停止)...
    python "%~dp0leishen_monitor.pyw" --daemon
    goto end

:check
    python -c "import subprocess; r=subprocess.run(['tasklist','/fi','STATUS eq RUNNING','/fo','csv','/nh'],capture_output=True,text=True); lines=[l for l in r.stdout.lower().splitlines() if 'leigod' in l]; print('leigod.exe 运行中' if lines else 'leigod.exe 未运行')"
    echo.
    pause
    goto end

:end
