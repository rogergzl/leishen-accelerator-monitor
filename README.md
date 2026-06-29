# LeiShenMonitor

雷神加速器进程监控——退出时弹窗提醒暂停时长，零依赖纯 Python + Win32 API。

## 使用

1. 双击 `运行.bat`
2. 首次自动询问是否启用 → 输入 `y`
3. 之后开机自启，后台静默监控

## 菜单

| 选项 | 功能 |
|------|------|
| 1. 启用/重启 | 注册开机自启 + 启动监控 |
| 2. 停止 | 暂停监控 |
| 3. 卸载 | 完全清除 |
| 4. 日志 | 最近 20 条 |
| 0. 退出 | |

## 需管理员权限

右键 `运行.bat` → 以管理员身份运行，或直接双击（自动提权）。

## 无需安装 Python

启动脚本自动检测，未安装则从国内镜像下载 Python 3.12 embedded (~10MB)。

## 文件结构

```
运行.bat          入口
完全卸载.bat      强制清理
data/
  launcher.ps1    环境检测/下载
  leishen_monitor.pyw  核心
```

## 工作原理

- schtasks ONLOGON 注册开机自启
- WaitForMultipleObjects 零 CPU 监控 leigod.exe
- 加速器退出 → WTSSendMessage 弹窗提醒
- 全屏游戏时暂缓弹窗，退出全屏补弹

## 兼容

Windows 10+，Python 3.12+。
