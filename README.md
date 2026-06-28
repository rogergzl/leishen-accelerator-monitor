# ⚡ 雷神加速器 · 时长监控助手

> 再也不会忘记暂停加速时长了！

一个轻量级的 Windows 后台监控工具，专门解决**雷神加速器退出后忘记暂停时长**导致时长空跑的痛点。同时支持检测全屏程序（游戏）退出提醒，以及关机时拦截确认。

---

## ✨ 功能

| 功能 | 说明 |
|------|------|
| 🚪 **加速器退出提醒** | 检测到雷神加速器进程退出时，弹窗提醒暂停时长 |
| 🎮 **全屏程序退出提醒** | 打完游戏退出全屏时，弹窗提醒检查加速时长 |
| 🔌 **关机拦截** | 关机时如果加速器还在后台运行，阻止关机并弹窗确认 |
| ⚡ **事件驱动** | 基于 WMI + WinEvent 内核事件，不轮询、不占 CPU、不脏日志 |
| 🖱️ **图形化管理** | 双击即出管理界面，一键安装/停止/卸载 |

## 🖥️ 管理界面

```
┌──────────────────────────────────────┐
│  ⚡ 雷神加速器 · 时长监控助手       │
│                                      │
│        ● 监控运行中                  │
│                                      │
│   [ ▶ 注册并启动服务 ]              │
│   [ ⏸ 停止服务 ]                    │
│   [ ✕ 卸载服务 ]                    │
└──────────────────────────────────────┘
```

## 📦 下载使用

1. 从 [Releases](../../releases) 下载 `雷神时长助手.exe`（约 13MB）
2. 双击运行 → 首次自动弹窗引导安装
3. 安装后开机自启，后台静默运行

## 🛠️ 技术细节

```
技术栈: Python 3 + tkinter + WMI + WinEvent + Win32 API
打包:   PyInstaller --onefile
大小:   ~13MB（tkinter 内置，无需额外运行时）
兼容:   Windows 7 / 8 / 10 / 11
```

### 监控原理

- **加速器退出**: 通过 WMI 订阅 `Win32_ProcessStopTrace` 事件，内核在进程退出时主动通知
- **全屏检测**: 通过 `SetWinEventHook` 监听前台窗口变化 + 窗口销毁，判断全屏→退出的转换
- **关机拦截**: 子类化 `WM_QUERYENDSESSION` 消息 + `ShutdownBlockReasonCreate` API

### 开发

```bash
# 运行管理界面
python leishen_monitor.pyw

# 后台 daemon 模式（由计划任务调用）
python leishen_monitor.pyw --daemon

# 打包
pip install pyinstaller
pyinstaller --onefile --windowed --name "雷神时长助手" leishen_monitor.pyw
```

### 自定义监控进程

编辑 `leishen_monitor.pyw` 顶部的 `PROCESS_NAMES` 列表：

```python
PROCESS_NAMES = [
    "leigod.exe",           # 雷神加速器
    "your_game_booster.exe", # 你的其他加速器
]
```

## 📄 License

MIT
