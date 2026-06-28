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

TASK_NAME = "雷神加速器时长监控"
EXIT_COOLDOWN = 5
FULLSCREEN_GRACE = 3
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.log")

# 运行时自动获取自己的路径（兼容打包后）
if getattr(sys, 'frozen', False):
    SELF_PATH = sys.executable
else:
    SELF_PATH = os.path.abspath(__file__)


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
        self._root = None
        self._hwnd = 0
        self._wmi = None
        self._fs = None
        self._fs_just_exited = False
        self._fs_grace_until = 0.0

    def _on_accel_exit(self, name):
        if self._root and not self._shutdowning:
            self._root.after(0, lambda: show_accelerator_exit())

    def _on_fs_exit(self, title):
        self._fs_just_exited = True
        self._fs_grace_until = time.time() + FULLSCREEN_GRACE
        if self._root and not self._shutdowning:
            self._root.after(0, lambda: show_fullscreen_exit(title))

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
                block = False
                reason = ""

                # 本周期内只拦截一次 — 已经拦过了就放行
                if self._shutdown_blocked_this_session:
                    log("本周期已拦截过，放行")
                    return 1  # TRUE → 允许关机

                if is_accelerator_running():
                    block = True
                    reason = "雷神加速器仍在运行！"
                elif self._fs_just_exited and time.time() < self._fs_grace_until:
                    block = True
                    reason = "你刚退出全屏程序，加速时长可能还在消耗！"

                if block:
                    self._shutdowning = True
                    cancel = show_shutdown_block(reason)
                    self._shutdowning = False
                    self._shutdown_blocked_this_session = True  # 标记已拦截
                    if cancel:
                        log("用户取消关机（本周期不再拦截）")
                        return 0
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
        if self._root:
            self._root.after(15000, self._update_block)

    def run(self):
        global _ROOT
        import tkinter as tk

        acc = is_accelerator_running()
        log(f"Daemon 启动, 加速器={'运行中' if acc else '未运行'}")

        self._root = tk.Tk()
        self._root.withdraw()
        self._root.title("LeiShenMonitor")
        _ROOT = self._root
        self._hwnd = self._root.winfo_id()

        self._fs = FullscreenWatcher(self._on_fs_exit)
        self._fs.start()
        self._wmi = WMIWatcher(PROCESS_NAMES, self._on_accel_exit)
        self._wmi.start()

        self._shutdown_hook()
        self._update_block()

        log("进入消息循环")
        self._root.mainloop()

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
        if self._root:
            try:
                self._root.quit()
            except Exception:
                pass


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


def _relaunch_as_admin():
    """提权重启"""
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", SELF_PATH, "", None, 5  # SW_SHOW
    )
    sys.exit(0)


def _run_schtask(action: str):
    """执行计划任务管理操作，失败时弹窗提示"""
    import tkinter.messagebox as mb

    if action == "install":
        # 按需提权
        if not _ensure_admin():
            _relaunch_as_admin()
            return

        # 如果存在先删再建
        if _task_exists():
            _schtasks("/delete", "/tn", TASK_NAME, "/f")
        r = _schtasks(
            "/create", "/tn", TASK_NAME,
            "/tr", f'"{SELF_PATH}" --daemon',
            "/sc", "ONLOGON",
            "/ru", os.environ.get("USERNAME", ""),
            "/rl", "HIGHEST",
            "/f",
        )
        if r.returncode != 0:
            mb.showerror("错误", f"计划任务创建失败:\n{r.stderr}")
            return
        _schtasks("/run", "/tn", TASK_NAME)
        return "installed"

    elif action == "stop":
        if not _ensure_admin():
            _relaunch_as_admin()
            return
        _schtasks("/end", "/tn", TASK_NAME)
        _schtasks("/change", "/tn", TASK_NAME, "/disable")
        # 杀残留
        subprocess.run(
            ["taskkill", "/fi", "IMAGENAME eq LeiShenMonitor.exe", "/f"],
            capture_output=True,
        )
        subprocess.run(
            ["taskkill", "/fi", "IMAGENAME eq pythonw.exe", "/fi", "WINDOWTITLE eq LeiShenMonitor", "/f"],
            capture_output=True,
        )
        return "stopped"

    elif action == "uninstall":
        if not _ensure_admin():
            _relaunch_as_admin()
            return
        _schtasks("/end", "/tn", TASK_NAME)
        _schtasks("/delete", "/tn", TASK_NAME, "/f")
        subprocess.run(
            ["taskkill", "/fi", "IMAGENAME eq LeiShenMonitor.exe", "/f"],
            capture_output=True,
        )
        subprocess.run(
            ["taskkill", "/fi", "IMAGENAME eq pythonw.exe", "/fi", "WINDOWTITLE eq LeiShenMonitor", "/f"],
            capture_output=True,
        )
        return "uninstalled"


def gui_main():
    """管理界面入口"""
    import tkinter as tk
    import tkinter.messagebox as mb

    root = tk.Tk()
    root.title("雷神加速器 - 时长监控助手")
    root.resizable(False, False)

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
        running = _task_running() if exists else False

        if running:
            set_status("● 监控运行中", green)
        elif exists:
            set_status("○ 已注册但未运行", yellow)
        else:
            set_status("○ 未安装", red)

    # ---- 操作 ----
    def do_install():
        result = _run_schtask("install")
        root.after(800, refresh_status)

    def do_stop():
        _run_schtask("stop")
        root.after(800, refresh_status)

    def do_uninstall():
        if not mb.askyesno("确认卸载", "确定要完全卸载监控服务吗？", parent=root):
            return
        _run_schtask("uninstall")
        root.after(800, refresh_status)

    make_btn("▶  注册并启动服务", do_install, green)
    make_btn("⏸  停止服务", do_stop, yellow)
    make_btn("✕  卸载服务", do_uninstall, red)

    # ---- 底部提示 ----
    tk.Label(
        root, text="开机自启 · 退出提醒 · 关机拦截 · 全屏检测",
        font=("Microsoft YaHei UI", 8),
        bg=bg, fg="#585b70",
    ).pack(side="bottom", pady=(2, 10))

    # ---- 初始化 ----
    refresh_status()

    # 如果未安装，弹窗询问是否一键安装
    if not _task_exists():
        root.after(500, lambda: (
            mb.askyesno(
                "首次使用",
                "监控服务尚未安装。\n\n是否立即注册并启动？\n（将设为开机自启）",
                parent=root,
            ) and do_install()
        ))

    root.mainloop()


# ============================================================
# 入口
# ============================================================
def main():
    # 单实例保护
    mutex = kernel32.CreateMutexW(None, False, "Global\\LeiShenAcceleratorMonitorGUI")
    if kernel32.GetLastError() == 183:
        # GUI 已有实例 → 如果是 --daemon，说明 daemon 已在运行，静默退出
        if "--daemon" in sys.argv:
            kernel32.CloseHandle(mutex)
            sys.exit(0)
        # GUI 双击 → 弹提示
        import tkinter as tk
        import tkinter.messagebox as mb
        t = tk.Tk()
        t.withdraw()
        mb.showinfo("提示", "管理界面已在运行中，请查看任务栏！")
        t.destroy()
        sys.exit(0)

    if "--daemon" in sys.argv:
        # Daemon 模式：后台监控
        daemon = Daemon()
        try:
            daemon.run()
        except KeyboardInterrupt:
            pass
        finally:
            daemon.stop()
    else:
        # GUI 模式：管理界面
        gui_main()

    kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
