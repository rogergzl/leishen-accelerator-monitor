# LeiShenMonitor

雷神加速器进程监控——退出时弹窗提醒暂停时长，支持全屏不打扰和关机拦截。

## 快速开始

```bash
# 开发测试
python data/leishen_monitor.pyw --console

# 构建分发
setup.bat
```

## 文件

| 文件 | 用途 |
|------|------|
| `data/leishen_monitor.pyw` | 核心程序 |
| `data/launcher.ps1` | 启动器（检测/下载 Python） |
| `运行.bat` | 用户入口 |
| `完全卸载.bat` | 强制清理 |
| `setup.bat` | 构建分发文件夹 |

## 模式

| 参数 | 行为 |
|------|------|
| `--console` | 彩色控制台交互（1启用/2停止/3卸载/4日志/0退出） |
| `--daemon` | 后台守护进程（schtasks 调用） |
| `--check` | 输出 leigod.exe 进程状态 |

## 架构

```
运行.bat → data/launcher.ps1 → python --console  # 控制台管理
                                    ↓
                    schtasks ONLOGON → pythonw --daemon  # 后台监控
```

- **控制台**: 彩色 ANSI 终端，无需 tkinter
- **Daemon**: Win32 消息窗口 + `WaitForMultipleObjects` 零 CPU 监控
- **通信**: PID 文件 (`.daemon.pid`) + 安装路径记录 (`.install_path`)

## 零依赖

仅使用 Python 标准库 + `ctypes` Win32 API。无需 `pip install`。
