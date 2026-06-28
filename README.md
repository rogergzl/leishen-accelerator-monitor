# LeiShenMonitor

雷神加速器进程监控 + 关机拦截 daemon。

## 架构

```
test.bat → test.ps1 → pythonw gui_main()     # GUI管理面板 (安装/停止/卸载)
                              ↓
              schtasks ONLOGON → pythonw --daemon  # 后台守护进程
```

- **GUI**: tkinter, 仅管理用, 关闭不影响监控
- **Daemon**: schtasks 注册, `ONLOGON` 触发, 无控制台, 1x1透明窗口接收 `WM_QUERYENDSESSION`
- **通信**: PID 文件 (`.daemon.pid`) 用于卸载时精确定位进程

## 进程监控

```
CreateToolhelp32Snapshot → 枚举 leigod.exe PID
        ↓
OpenProcess(SYNCHRONIZE) → 打开进程句柄
        ↓
WaitForMultipleObjects → 内核级阻塞等待退出, CPU=0
        ↓
MessageBoxW(MB_TOPMOST) → 置顶弹窗
```

- 未找到进程: 每3s `CreateToolhelp32Snapshot` 重扫 (微秒级, 无子进程)
- 找到进程后: `WaitForMultipleObjects` 阻塞 (零CPU)
- 全屏中加速器退出: 暂缓弹窗, `_accel_exit_pending` 标记, 全屏退出后补弹

## 全屏检测

`is_fullscreen_window()`: `GetWindowRect` == `MonitorFromWindow` 尺寸, 覆盖无边框全屏与独占全屏。WinEvent hook 监听 `EVENT_SYSTEM_FOREGROUND` + `EVENT_OBJECT_DESTROY`。

## 关机拦截

```
WM_TIMER(30s) → is_accelerator_running()
    ├─ true  → ShutdownBlockReasonCreate(hwnd, reason)
    └─ false → ShutdownBlockReasonDestroy(hwnd)

WM_QUERYENDSESSION
    ├─ _shutdown_blocked_this_session → return 1 (放行)
    └─ 弹窗 MB_YESNO → IDYES=return 0(阻止), IDNO=return 1(放行)
```

每开机周期仅拦截一次。窗口 `WS_EX_LAYERED|WS_EX_TRANSPARENT`, `SetLayeredWindowAttributes(alpha=1)`, 完全透明+鼠标穿透。

## 入口

| 参数 | 行为 |
|------|------|
| *(无)* | GUI 管理面板 |
| `--daemon` | 守护进程 (schtasks 调用) |
| `--console` | 控制台交互 (1启用/2停止/3卸载) |
| `--gui-action install\|stop\|uninstall` | 提权后自动执行, 然后进入 GUI |
| `--check` | 输出 leigod.exe 进程状态 |

## 环境变量

`LEISHEN_PROCESS_NAMES`: 逗号分隔进程名, 默认 `leigod.exe`

## 打包

```bash
pyinstaller --onefile --windowed --name LeiShenMonitor leishen_monitor.pyw
```
