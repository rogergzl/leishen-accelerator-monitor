@echo off
chcp 65001 >nul
title 雷神加速器 - 时长监控助手

:: ============================================================
:: 雷神加速器 时长监控助手 - 管理菜单
:: 双击运行即可管理监控服务
:: ============================================================

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%leishen_monitor.pyw"
set "TASK_NAME=雷神加速器时长监控"
set "CURRENT_USER=%USERNAME%"

:: ---- 检查管理员权限 ----
net session >nul 2>&1
if errorlevel 1 (
    echo [⚠] 需要管理员权限才能管理计划任务
    echo     请右键此文件 → 以管理员身份运行
    echo.
    pause
    exit /b 1
)

:menu
cls
echo.
echo ╔══════════════════════════════════════════╗
echo ║     雷神加速器 - 时长监控助手          ║
echo ╠══════════════════════════════════════════╣
echo ║                                          ║
echo ║   [1] 注册并启动服务（开机自启）        ║
echo ║   [2] 停止服务（禁用，选 [1] 重新启用）  ║
echo ║   [3] 删除服务（完全卸载）              ║
echo ║   [0] 退出                              ║
echo ║                                          ║
echo ╚══════════════════════════════════════════╝
echo.
set /p choice="请输入选项 [1/2/3/0]: "

if "%choice%"=="1" goto install
if "%choice%"=="2" goto stop
if "%choice%"=="3" goto uninstall
if "%choice%"=="0" goto end
echo 无效选项
timeout /t 2 >nul
goto menu

:: ============================================================
:: 1. 注册并启动
:: ============================================================
:install
cls
echo.
echo ═══════════════════════════════════════════
echo   注册并启动服务
echo ═══════════════════════════════════════════
echo.

:: 检查脚本文件
if not exist "%SCRIPT_PATH%" (
    echo [✗] 找不到脚本: %SCRIPT_PATH%
    echo     请确保 leishen_monitor.pyw 与本文件在同一目录
    pause
    goto menu
)

:: 查找 Python
call :find_python
if errorlevel 1 ( goto menu )

:: 检查/安装依赖模块
echo [*] 检查依赖模块...
python -c "import psutil, tkinter, pythoncom, win32com.client" >nul 2>&1
if errorlevel 1 (
    echo [!] 正在安装缺失模块 (psutil, pywin32) ...
    pip install psutil pywin32 -q 2>&1
    if errorlevel 1 (
        echo [✗] 模块安装失败，请检查网络后重试
        pause
        goto menu
    )
)
echo [✓] 依赖模块就绪

:: 检查任务是否已存在
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if errorlevel 1 (
    :: 不存在 → 创建
    echo [*] 创建计划任务: "%TASK_NAME%" ...
    schtasks /create ^
        /tn "%TASK_NAME%" ^
        /tr "\"%PYTHONW%\" \"%SCRIPT_PATH%\" --daemon" ^
        /sc ONLOGON ^
        /ru "%CURRENT_USER%" ^
        /rl HIGHEST ^
        /f >nul 2>&1

    if errorlevel 1 (
        echo [✗] 计划任务创建失败！请以管理员身份运行
        pause
        goto menu
    )
    echo [✓] 计划任务创建成功
) else (
    :: 已存在 → 确保启用
    echo [*] 任务已存在，正在启用...
    schtasks /change /tn "%TASK_NAME%" /enable >nul 2>&1
    echo [✓] 任务已启用
)

:: 立即启动
echo [*] 启动监控进程...
schtasks /run /tn "%TASK_NAME%" >nul 2>&1
if errorlevel 1 (
    echo [!] 任务已就绪但启动失败，重启后会自动运行
) else (
    echo [✓] 监控已启动
)

echo.
echo ╔══════════════════════════════════════════╗
echo ║          ✅ 安装成功                    ║
echo ╠══════════════════════════════════════════╣
echo ║  • 开机自动启动                         ║
echo ║  • 加速器退出时弹窗提醒                 ║
echo ║  • 全屏程序退出时弹窗提醒               ║
echo ║  • 关机时若加速器运行则拦截提醒         ║
echo ║                                        ║
echo ║  编辑 PROCESS_NAMES 可修改监控的进程名  ║
echo ╚══════════════════════════════════════════╝
echo.
pause
goto menu

:: ============================================================
:: 2. 停止服务
:: ============================================================
:stop
cls
echo.
echo ═══════════════════════════════════════════
echo   停止服务
echo ═══════════════════════════════════════════
echo.

:: 结束正在运行的任务
echo [*] 停止监控进程...
schtasks /end /tn "%TASK_NAME%" >nul 2>&1
taskkill /fi "IMAGENAME eq pythonw.exe" /fi "WINDOWTITLE eq LeiShenMonitor" >nul 2>&1

:: 禁用任务（不清除注册，下次开机还会启动）
schtasks /change /tn "%TASK_NAME%" /disable >nul 2>&1

echo.
echo [✓] 监控已停止，任务已禁用
echo     下次开机不会自动启动
echo     如需重新启用，请选 [1]
echo.
pause
goto menu

:: ============================================================
:: 3. 完全卸载
:: ============================================================
:uninstall
cls
echo.
echo ═══════════════════════════════════════════
echo   删除服务
echo ═══════════════════════════════════════════
echo.

:: 结束进程
echo [*] 停止监控进程...
schtasks /end /tn "%TASK_NAME%" >nul 2>&1
taskkill /fi "IMAGENAME eq pythonw.exe" /fi "WINDOWTITLE eq LeiShenMonitor" >nul 2>&1

:: 删除计划任务
echo [*] 删除计划任务...
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

echo.
echo [✓] 已完全卸载，监控已停止
echo     如需重新安装，请选 [1]
echo.
pause
goto menu

:: ============================================================
:: 子程序: 查找 Python
:: ============================================================
:find_python
:: 尝试1: 直接用 python
python --version >nul 2>&1
if not errorlevel 1 (
    goto :find_pythonw
)

:: 尝试2: 常见安装路径
for %%d in (
    "%LOCALAPPDATA%\Programs\Python\Python313"
    "%LOCALAPPDATA%\Programs\Python\Python312"
    "%LOCALAPPDATA%\Programs\Python\Python311"
    "%LOCALAPPDATA%\Programs\Python\Python310"
    "%PROGRAMFILES%\Python313"
    "%PROGRAMFILES%\Python312"
    "%PROGRAMFILES%\Python311"
    "C:\Python313" "C:\Python312" "C:\Python311"
) do (
    if exist "%%~d\python.exe" (
        set "PATH=%%~d;%PATH%"
        python --version >nul 2>&1
        if not errorlevel 1 goto :find_pythonw
    )
)

echo [✗] 未找到 Python 3
echo     请安装 Python 3.10+: https://www.python.org/downloads/
echo     安装时务必勾选 "Add Python to PATH"
pause
exit /b 1

:find_pythonw
for /f "delims=" %%i in ('python -c "import sys,os; print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set "PYTHONW=%%i"
if not exist "%PYTHONW%" (
    echo [✗] 找不到 pythonw.exe (在 %PYTHONW%)
    pause
    exit /b 1
)
echo [✓] Python: %PYTHONW%
exit /b 0

:end
echo.
exit /b 0
