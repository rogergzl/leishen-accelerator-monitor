@echo off
chcp 65001 >nul
title 雷神监控 - 开发测试

echo.
echo ═══════════════════════════════════════════
echo   雷神加速器监控 - 开发测试模式
echo ═══════════════════════════════════════════
echo.
echo   [1] 运行 GUI 管理界面
echo   [2] 运行 daemon (控制台模式，可看日志)
echo   [3] 模拟关机拦截测试
echo   [0] 退出
echo.
set /p choice="> "

if "%choice%"=="1" goto gui
if "%choice%"=="2" goto daemon
if "%choice%"=="3" goto shutdown_test
if "%choice%"=="0" goto end
goto end

:gui
    python "%~dp0leishen_monitor.pyw"
    goto end

:daemon
    echo [*] 启动 daemon 模式 (Ctrl+C 停止)...
    echo     日志输出到控制台和 monitor.log
    echo.
    python "%~dp0leishen_monitor.pyw" --daemon
    goto end

:shutdown_test
    echo [*] 模拟: 如果现在关机，会触发拦截吗？
    echo.
    python -c "import sys; sys.path.insert(0, r'%~dp0'); exec(open(r'%~dp0leishen_monitor.pyw', encoding='utf-8').read().split('class Daemon')[0]); print('加速器运行中:' , is_accelerator_running())"
    echo.
    echo 如果上面显示 True，关机时会触发拦截弹窗。
    pause
    goto end

:end
