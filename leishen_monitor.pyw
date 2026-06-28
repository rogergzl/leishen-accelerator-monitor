#!/usr/bin/env python3
"""
雷神加速器 时长监控助手
  双击运行 → 管理界面（安装/停止/卸载）
  由计划任务带 --daemon 启动 → 后台监控

打包: pyinstaller --onefile --windowed --name LeiShenMonitor leishen_monitor.pyw
"""

import sys
import os
import time
import subprocess
import threading
import ctypes
import ctypes.wintypes
from datetime import datetime

# ============================================================
# 配置
# ============================================================
PROCESS_NAMES = [
    "leigod.exe",
]

# 支持通过环境变量覆盖：LEISHEN_PROCESS_NAMES=leigod.exe,xxx.exe
_env_names = os.environ.get("LEISHEN_PROCESS_NAMES", "")
if _env_names:
    PROCESS_NAMES = [n.strip() for n in _env_names.split(",") if n.strip()]

TASK_NAME = "LeiShenMonitor"
EXIT_COOLDOWN = 5
FULLSCREEN_GRACE = 3
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.log")

# 运行时自动获取自己的路径（兼容打包后）
if getattr(sys, 'frozen', False):
    SELF_PATH = sys.executable
    _BASE_DIR = sys._MEIPASS
else:
    SELF_PATH = os.path.abspath(__file__)
    _BASE_DIR = os.path.dirname(SELF_PATH)


def _resolve_path(relative_path: str) -> str:
    """解析资源文件路径（兼容 PyInstaller 打包）"""
    return os.path.join(_BASE_DIR, relative_path)


def _short_path(path: str) -> str:
    """获取 Windows 8.3 短路径，避免 schtasks 编码中文路径时出错"""
    try:
        buf = ctypes.create_unicode_buffer(512)
        length = ctypes.windll.kernel32.GetShortPathNameW(path, buf, 512)
        if length > 0:
            return buf.value
    except Exception:
        pass
    return path


def log(msg: str):
    text = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    if LOG_FILE:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass


# ============================================================
# Windows API
# ============================================================
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
WM_QUERYENDSESSION = 0x0011

ShutdownBlockReasonCreate = user32.ShutdownBlockReasonCreate
ShutdownBlockReasonCreate.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPCWSTR]
ShutdownBlockReasonCreate.restype = ctypes.wintypes.BOOL

ShutdownBlockReasonDestroy = user32.ShutdownBlockReasonDestroy
ShutdownBlockReasonDestroy.argtypes = [ctypes.wintypes.HWND]
ShutdownBlockReasonDestroy.restype = ctypes.wintypes.BOOL

EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_DESTROY = 0x8001
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002

WINEVENTPROC = ctypes.WINFUNCTYPE(
    None,
    ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD, ctypes.wintypes.HWND,
    ctypes.wintypes.LONG, ctypes.wintypes.LONG,
    ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
)

SetWinEventHook = user32.SetWinEventHook
SetWinEventHook.argtypes = [
    ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
    ctypes.wintypes.HMODULE, WINEVENTPROC,
    ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
]
SetWinEventHook.restype = ctypes.wintypes.HANDLE
UnhookWinEvent = user32.UnhookWinEvent
UnhookWinEvent.argtypes = [ctypes.wintypes.HANDLE]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.wintypes.DWORD), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", ctypes.wintypes.DWORD)]


# ============================================================
# 工具函数
# ============================================================
def is_accelerator_running() -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/fi", "STATUS eq RUNNING", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.lower().splitlines():
            for name in PROCESS_NAMES:
                if name.lower() in line:
                    return True
        return False
    except Exception:
        return False


def is_fullscreen_window(hwnd: int) -> bool:
    try:
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        if not user32.IsWindowVisible(hwnd):
            return False

        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value in ("LeiShenMonitor",):
            return False

        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        if not title.value or title.value in (
            "Program Manager", "", "Windows Shell Experience Host",
        ):
            return False

        monitor = user32.MonitorFromWindow(hwnd, 2)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
            return False

        mw = mi.rcMonitor.right - mi.rcMonitor.left
        mh = mi.rcMonitor.bottom - mi.rcMonitor.top
        ww = rect.right - rect.left
        wh = rect.bottom - rect.top
        return ww >= mw and wh >= mh
    except Exception:
        return False


# ============================================================
# 弹窗（daemon 模式使用）
# ============================================================
_ROOT = None  # tk.Tk 实例


def show_accelerator_exit():
    if _ROOT is None:
        return
    import tkinter.messagebox as mb
    _ROOT.attributes("-topmost", True)
    _ROOT.lift()
    _ROOT.focus_force()
    mb.showwarning(
        "雷神加速器已退出",
        "检测到雷神加速器已经退出！\n\n"
        "请确认是否已【暂停加速时长】？\n"
        "如果忘记暂停，时长会继续消耗！",
        parent=_ROOT,
    )


def show_fullscreen_exit(title_text: str = ""):
    label = f"「{title_text}」" if title_text else "全屏程序"
    if _ROOT is None:
        return
    import tkinter.messagebox as mb
    _ROOT.attributes("-topmost", True)
    _ROOT.lift()
    _ROOT.focus_force()
    mb.showwarning(
        "全屏程序已退出",
        f"检测到 {label} 已退出。\n\n"
        "雷神加速器的时长可能还在消耗中！\n"
        "别忘了暂停加速时长哦～",
        parent=_ROOT,
    )


def show_shutdown_block(reason: str = "") -> bool:
    if _ROOT is None:
        return False
    import tkinter.messagebox as mb
    _ROOT.attributes("-topmost", True)
    _ROOT.lift()
    _ROOT.focus_force()
    return mb.askyesno(
        reason or "雷神加速器仍在运行！",
        "检测到雷神加速器可能仍在后台消耗时长！\n\n"
        "→ 点击 [是] 取消关机，先去暂停加速时长\n"
        "→ 点击 [否] 我已暂停了，继续关机",
        parent=_ROOT,
    )


# ============================================================
# Daemon: WMI 进程监听
# ============================================================
class WMIWatcher:
    def __init__(self, names, on_exit):
        self._names = names
        self._cb = on_exit
        self._running = False
        self._last = 0.0

    def start(self):
        self._running = True
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def _run(self):
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
            wmi = locator.ConnectServer(".", "root\\cimv2")
            conds = " OR ".join(f"TargetInstance.ProcessName = '{n}'" for n in self._names)
            q = f"SELECT * FROM Win32_ProcessStopTrace WHERE ({conds})"
            events = wmi.ExecNotificationQuery(q)
            log("WMI 就绪")
            while self._running:
                try:
                    evt = events.NextEvent(1000)
                    if evt is None:
                        continue
                    name = evt.Properties_["ProcessName"].Value
                    log(f"进程退出: {name}")
                    now = time.time()
                    if now - self._last > EXIT_COOLDOWN:
                        self._last = now
                        self._cb(name)
                except Exception as e:
                    s = str(e)
                    if "0x80043001" not in s and "timeout" not in s.lower():
                        log(f"WMI err: {e}")
                    time.sleep(0.5)
        except Exception as e:
            log(f"WMI init err: {e}")
        finally:
            pythoncom.CoUninitialize()


# ============================================================
# Daemon: 全屏监听
# ============================================================
class FullscreenWatcher:
    def __init__(self, on_exit):
        self._on_exit = on_exit
        self._running = False
        self._fs_hwnd = 0
        self._fs_title = ""
        self._h_fg = 0
        self._h_destroy = 0
        self._last = 0.0

    @property
    def active(self) -> bool:
        return self._fs_hwnd != 0

    def start(self):
        self._running = True
        fg = user32.GetForegroundWindow()
        if fg and is_fullscreen_window(fg):
            self._set_fs(fg)
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def stop(self):
        self._running = False
        if self._h_fg:
            UnhookWinEvent(self._h_fg)
        if self._h_destroy:
            UnhookWinEvent(self._h_destroy)

    def _set_fs(self, hwnd):
        self._fs_hwnd = hwnd
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        self._fs_title = title.value or "(未知)"
        log(f"全屏进入: [{self._fs_title}]")

    def _clear_fs(self):
        if self._fs_hwnd:
            title = self._fs_title
            log(f"全屏退出: [{title}]")
            self._fs_hwnd = 0
            self._fs_title = ""
            now = time.time()
            if now - self._last > EXIT_COOLDOWN:
                self._last = now
                self._on_exit(title)

    def _run(self):
        import pythoncom
        pythoncom.CoInitialize()

        @WINEVENTPROC
        def on_fg(hook, event, hwnd, idObj, idChild, thread, time_ms):
            if hwnd == 0:
                return
            if is_fullscreen_window(hwnd):
                if hwnd != self._fs_hwnd:
                    if self._fs_hwnd:
                        self._clear_fs()
                    self._set_fs(hwnd)
            else:
                if self._fs_hwnd and hwnd != self._fs_hwnd:
                    if not user32.IsWindow(self._fs_hwnd):
                        self._clear_fs()

        @WINEVENTPROC
        def on_destroy(hook, event, hwnd, idObj, idChild, thread, time_ms):
            if hwnd == self._fs_hwnd:
                self._clear_fs()

        self._h_fg = SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND,
            0, on_fg, 0, 0, WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        )
        self._h_destroy = SetWinEventHook(
            EVENT_OBJECT_DESTROY, EVENT_OBJECT_DESTROY,
            0, on_destroy, 0, 0, WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        )
        log("WinEvent 就绪")
        while self._running:
            time.sleep(0.5)
        UnhookWinEvent(self._h_fg)
        UnhookWinEvent(self._h_destroy)
        pythoncom.CoUninitialize()


# ============================================================
# Daemon: 主控
# ============================================================
class Daemon:
    def __init__(self):
        self._running = True
        self._shutdowning = False
        self._shutdown_blocked_this_session = False  # 本开机周期内已拦截过一次
        self._hwnd = 0
        self._wmi = None
        self._fs = None
        self._fs_just_exited = False
        self._fs_grace_until = 0.0

    def _on_accel_exit(self, name):
        log(f"加速器退出: {name}")
        if not self._shutdowning:
            threading.Thread(target=lambda: user32.MessageBoxW(0, "检测到雷神加速器已经退出！\n\n请确认是否已暂停加速时长？\n如果忘记暂停，时长会继续消耗！", "雷神加速器已退出", 0x30), daemon=True).start()

    def _on_fs_exit(self, title):
        label = f"「{title}」" if title else "全屏程序"
        log(f"全屏退出: {label}")
        self._fs_just_exited = True
        self._fs_grace_until = time.time() + FULLSCREEN_GRACE
        if not self._shutdowning:
            threading.Thread(target=lambda: user32.MessageBoxW(0, f"检测到 {label} 已退出。\n\n雷神加速器的时长可能还在消耗中！\n别忘了暂停加速时长哦～", "全屏程序已退出", 0x30), daemon=True).start()

    def _shutdown_hook(self):
        GWLP_WNDPROC = -4
        orig = user32.GetWindowLongPtrW(self._hwnd, GWLP_WNDPROC)
        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_longlong, ctypes.wintypes.HWND, ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
        )

        def proc(hwnd, msg, wparam, lparam):
            if msg == WM_QUERYENDSESSION:
                log("WM_QUERYENDSESSION")
                if self._shutdown_blocked_this_session:
                    log("本周期已拦截过，放行")
                    return 1

                block = False
                reason = ""
                if is_accelerator_running():
                    block = True
                    reason = "雷神加速器仍在运行！"
                elif self._fs_just_exited and time.time() < self._fs_grace_until:
                    block = True
                    reason = "你刚退出全屏程序，加速时长可能还在消耗！"

                if block:
                    self._shutdowning = True
                    self._shutdown_blocked_this_session = True
                    rc = user32.MessageBoxW(
                        hwnd,
                        "检测到雷神加速器可能仍在后台消耗时长！\n\n点[是]取消关机，先去暂停加速时长\n点[否]我已暂停了，继续关机",
                        reason,
                        0x24,  # MB_YESNO | MB_ICONQUESTION
                    )
                    self._shutdowning = False
                    if rc == 6:  # IDYES
                        log("用户取消关机")
                        return 0
                    log("用户放行关机")
                    self._fs_just_exited = False
                    ShutdownBlockReasonDestroy(self._hwnd)
                    return 1
            return user32.CallWindowProcW(orig, hwnd, msg, wparam, lparam)

        self._newproc = WNDPROC(proc)
        user32.SetWindowLongPtrW(self._hwnd, GWLP_WNDPROC, self._newproc)

    def _update_block(self):
        if not self._running:
            return
        try:
            need = (
                is_accelerator_running()
                or (self._fs_just_exited and time.time() < self._fs_grace_until)
            )
            if need:
                ShutdownBlockReasonCreate(self._hwnd, "雷神加速器仍在运行，请先暂停加速时长再关机")
            else:
                ShutdownBlockReasonDestroy(self._hwnd)
        except Exception:
            pass
        # 30秒后再检查
        if self._hwnd:
            user32.SetTimer(self._hwnd, 1, 30000, None)

    def run(self):
        global _daemon_instance
        _daemon_instance = self
        log(f"Daemon 启动, 加速器={'运行中' if is_accelerator_running() else '未运行'}")

        self._hwnd = _create_message_window()
        log(f"消息窗口创建: {self._hwnd}")

        self._fs = FullscreenWatcher(self._on_fs_exit)
        self._fs.start()
        self._wmi = WMIWatcher(PROCESS_NAMES, self._on_accel_exit)
        self._wmi.start()

        self._shutdown_hook()
        self._update_block()

        log("进入消息循环")
        _message_pump()

    def stop(self):
        self._running = False
        if self._wmi:
            self._wmi.stop()
        if self._fs:
            self._fs.stop()
        try:
            ShutdownBlockReasonDestroy(self._hwnd)
        except Exception:
            pass
        if self._hwnd:
            user32.PostMessageW(self._hwnd, 0x0010, 0, 0)  # WM_CLOSE


# ============================================================
# Win32 消息窗口 + 消息泵（daemon 用，不依赖 tkinter）
# ============================================================
def _create_message_window() -> int:
    """创建纯 Win32 隐藏消息窗口"""
    hinst = kernel32.GetModuleHandleW(None)
    wnd_class = ctypes.create_unicode_buffer("LeiShenDaemon")
    wc = ctypes.wintypes.WNDCLASSW()
    wc.lpfnWndProc = _daemon_wndproc_ref
    wc.hInstance = hinst
    wc.lpszClassName = ctypes.addressof(wnd_class)
    user32.RegisterClassW(ctypes.byref(wc))

    hwnd = user32.CreateWindowExW(
        0, wnd_class, "LeiShenDaemon", 0,
        0, 0, 0, 0, None, None, hinst, None,
    )
    return hwnd


# 窗口过程回调类型
_WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong, ctypes.wintypes.HWND, ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
)

_daemon_instance = None  # Daemon 实例引用，窗口过程里用


@_WNDPROC
def _daemon_wndproc(hwnd, msg, wparam, lparam):
    if msg == 0x0113:  # WM_TIMER
        if _daemon_instance:
            _daemon_instance._update_block()
    elif msg == 0x0010:  # WM_CLOSE
        user32.DestroyWindow(hwnd)
    elif msg == 0x0002:  # WM_DESTROY
        user32.PostQuitMessage(0)
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


_daemon_wndproc_ref = _daemon_wndproc  # 防止 GC


def _message_pump():
    """Win32 消息循环"""
    msg = ctypes.wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


# ============================================================
# GUI 管理界面
# ============================================================
def _schtasks(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["schtasks"] + list(args),
        capture_output=True, text=True,
    )


def _task_exists() -> bool:
    return _schtasks("/query", "/tn", TASK_NAME).returncode == 0


def _task_running() -> bool:
    r = _schtasks("/query", "/tn", TASK_NAME, "/fo", "csv", "/v")
    return "Running" in r.stdout


def _ensure_admin() -> bool:
    """确保以管理员运行，否则用 ShellExecute runas 提权重启"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _relaunch_as_admin(action: str):
    """提权重启，并传递要执行的动作"""
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", SELF_PATH, f'--gui-action {action}', None, 5  # SW_SHOW
    )
    sys.exit(0)


def _run_schtask(action: str):
    """执行计划任务管理操作"""
    import tkinter.messagebox as mb

    if action == "install":
        existed = _task_exists()
        if existed:
            _schtasks("/delete", "/tn", TASK_NAME, "/f")

        # 使用短路径避免 schtasks 编码中文路径时出错
        safe_path = _short_path(SELF_PATH)
        # 非打包模式需要用 pythonw 显式调用
        if not getattr(sys, 'frozen', False):
            import shutil
            pyw = shutil.which("pythonw") or "pythonw"
            cmd = f'"{pyw}" "{safe_path}" --daemon'
        else:
            cmd = f'"{safe_path}" --daemon'
        r = _schtasks(
            "/create", "/tn", TASK_NAME,
            "/tr", cmd,
            "/sc", "ONLOGON",
            "/ru", os.environ.get("USERNAME", ""),
            "/rl", "HIGHEST",
            "/f",
        )
        if r.returncode != 0:
            mb.showerror("启用失败", f"计划任务创建失败:\n{r.stderr.strip()}")
            return "failed"

        r2 = _schtasks("/run", "/tn", TASK_NAME)
        if r2.returncode != 0:
            mb.showwarning("部分成功", "计划任务已创建，但立即启动失败。\n重启电脑后会自动运行。")
        else:
            mb.showinfo("启用成功", "监控服务已注册并启动！\n开机自启，后台静默运行。")
        return "installed"

    elif action == "stop":
        _schtasks("/end", "/tn", TASK_NAME)
        r = _schtasks("/change", "/tn", TASK_NAME, "/disable")
        subprocess.run(["taskkill", "/fi", "IMAGENAME eq LeiShenMonitor.exe", "/f"], capture_output=True)
        subprocess.run(["taskkill", "/fi", "IMAGENAME eq pythonw.exe", "/fi", "WINDOWTITLE eq LeiShenMonitor", "/f"], capture_output=True)

        if r.returncode != 0:
            mb.showerror("停止失败", "计划任务禁用失败，请尝试以管理员运行。")
            return "failed"
        mb.showinfo("已停止", '监控服务已停止，下次开机不会自动启动。\n如需重新启用，请点击"启用服务"。')
        return "stopped"

    elif action == "uninstall":
        _schtasks("/end", "/tn", TASK_NAME)
        r = _schtasks("/delete", "/tn", TASK_NAME, "/f")
        subprocess.run(["taskkill", "/fi", "IMAGENAME eq LeiShenMonitor.exe", "/f"], capture_output=True)
        subprocess.run(["taskkill", "/fi", "IMAGENAME eq pythonw.exe", "/fi", "WINDOWTITLE eq LeiShenMonitor", "/f"], capture_output=True)

        if r.returncode != 0:
            mb.showerror("卸载失败", "计划任务删除失败，请尝试以管理员运行。")
            return "failed"
        mb.showinfo("已卸载", "监控服务已完全卸载。")
        return "uninstalled"


def gui_main():
    """管理界面入口"""
    import tkinter as tk
    import tkinter.messagebox as mb

    root = tk.Tk()
    root.title("雷神加速器 - 时长监控助手")
    root.resizable(False, False)

    # 窗口图标
    try:
        ico_path = _resolve_path("tu.ico")
        root.iconbitmap(ico_path)
    except Exception:
        pass

    # 窗口居中
    w, h = 380, 280
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x, y = (sw - w) // 2, (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    # ---- 样式 ----
    bg = "#1e1e2e"
    fg = "#cdd6f4"
    accent = "#89b4fa"
    btn_bg = "#313244"
    green = "#a6e3a1"
    red = "#f38ba8"
    yellow = "#f9e2af"

    root.configure(bg=bg)

    # ---- 标题 ----
    tk.Label(
        root, text="⚡ 雷神加速器 · 时长监控助手",
        font=("Microsoft YaHei UI", 13, "bold"),
        bg=bg, fg=accent,
    ).pack(pady=(18, 4))

    # ---- 状态 ----
    status_var = tk.StringVar(value="正在检测状态...")
    status_label = tk.Label(
        root, textvariable=status_var,
        font=("Microsoft YaHei UI", 10),
        bg=bg, fg=fg,
    )
    status_label.pack(pady=(2, 6))

    # 指示灯
    indicator = tk.Canvas(root, width=14, height=14, bg=bg, highlightthickness=0)
    indicator.pack()

    def set_status(text, color):
        status_var.set(text)
        indicator.delete("all")
        indicator.create_oval(0, 0, 14, 14, fill=color, outline="")

    # ---- 按钮 ----
    btn_frame = tk.Frame(root, bg=bg)
    btn_frame.pack(pady=(10, 6))

    def make_btn(text, cmd, color):
        b = tk.Button(
            btn_frame, text=text, command=cmd,
            font=("Microsoft YaHei UI", 11),
            bg=btn_bg, fg=color,
            activebackground="#45475a", activeforeground=color,
            relief="flat", width=16, height=2,
            cursor="hand2",
        )
        b.pack(pady=4)
        return b

    # ---- 刷新状态 ----
    def refresh_status():
        exists = _task_exists()
        running = False
        if exists:
            r = subprocess.run(
                ["tasklist", "/fi", "IMAGENAME eq LeiShenMonitor.exe", "/fo", "csv", "/nh"],
                capture_output=True, text=True,
            )
            if "LeiShenMonitor" not in r.stdout:
                r = subprocess.run(
                    ["tasklist", "/fi", "IMAGENAME eq pythonw.exe", "/fo", "csv", "/nh"],
                    capture_output=True, text=True,
                )
                running = "pythonw" in r.stdout
            else:
                running = True

        if running:
            set_status("● 监控运行中", green)
        elif exists:
            set_status("○ 已注册但未运行", yellow)
        else:
            set_status("○ 未安装", red)

    def refresh_after_delay(seconds: int = 3):
        """延迟刷新状态，期间显示加载中"""
        set_status("⏳ 加载中...", yellow)
        root.after(seconds * 1000, refresh_status)

    # ---- 操作 ----
    def do_install():
        if not _ensure_admin():
            _relaunch_as_admin("install")
            return
        set_status("⏳ 正在启用...", yellow)
        result = _run_schtask("install")
        if result == "installed":
            refresh_after_delay(3)
        else:
            refresh_status()

    def do_stop():
        if not _ensure_admin():
            _relaunch_as_admin("stop")
            return
        set_status("⏳ 正在停止...", yellow)
        result = _run_schtask("stop")
        if result == "stopped":
            refresh_after_delay(1)
        else:
            refresh_status()

    def do_uninstall():
        if not mb.askyesno("确认卸载", "确定要完全卸载监控服务吗？", parent=root):
            return
        if not _ensure_admin():
            _relaunch_as_admin("uninstall")
            return
        set_status("⏳ 正在卸载...", yellow)
        result = _run_schtask("uninstall")
        if result == "uninstalled":
            refresh_status()
        else:
            refresh_status()

    make_btn("启用服务", do_install, green)
    make_btn("停止服务", do_stop, yellow)
    make_btn("卸载服务", do_uninstall, red)

    # ---- 底部提示 ----
    tk.Label(
        root, text="开机自启 · 退出提醒 · 关机拦截 · 全屏检测",
        font=("Microsoft YaHei UI", 8),
        bg=bg, fg="#585b70",
    ).pack(side="bottom", pady=(2, 10))

    # ---- 初始化 ----
    refresh_status()

    # 如果未安装，弹窗询问是否一键启用
    if not _task_exists():
        root.after(500, lambda: (
            mb.askyesno(
                "首次使用",
                "监控服务尚未启用。\n\n是否立即启用？\n（将设为开机自启）",
                parent=root,
            ) and do_install()
        ))

    root.mainloop()


# ============================================================
# 入口
# ============================================================
def main():
    # --gui-action: 提权后自动执行管理操作
    gui_action = None
    for arg in sys.argv[1:]:
        if arg.startswith("--gui-action"):
            if "=" in arg:
                gui_action = arg.split("=", 1)[1]
            elif sys.argv.index(arg) + 1 < len(sys.argv):
                gui_action = sys.argv[sys.argv.index(arg) + 1]
            break

    if gui_action:
        # 提权执行的快速路径：执行操作 → 弹结果
        import tkinter as tk
        import tkinter.messagebox as mb
        if not _ensure_admin():
            t = tk.Tk()
            t.withdraw()
            mb.showerror("权限不足", "需要管理员权限才能执行此操作。")
            t.destroy()
            sys.exit(1)
        _run_schtask(gui_action)
        if gui_action == "uninstall":
            sys.exit(0)  # 卸载后直接退出
        # install/stop 后进入 GUI 显示状态
        gui_main()
        sys.exit(0)

    # --check: 快速检测，无 GUI
    if "--check" in sys.argv:
        if is_accelerator_running():
            print("leigod.exe: RUNNING")
        else:
            print("leigod.exe: NOT RUNNING")
        sys.exit(0)

    # 单实例保护（仅 GUI 模式）
    mutex = kernel32.CreateMutexW(None, False, "Global\\LeiShenAcceleratorMonitorGUI")
    if kernel32.GetLastError() == 183:
        if "--daemon" in sys.argv:
            kernel32.CloseHandle(mutex)
            sys.exit(0)
        import tkinter as tk
        import tkinter.messagebox as mb
        t = tk.Tk()
        t.withdraw()
        mb.showinfo("提示", "管理界面已在运行中，请查看任务栏！")
        t.destroy()
        sys.exit(0)

    if "--daemon" in sys.argv:
        daemon = Daemon()
        try:
            daemon.run()
        except KeyboardInterrupt:
            pass
        finally:
            daemon.stop()
    else:
        gui_main()

    kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
