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

# kernel32: 进程监控
CreateToolhelp32Snapshot = kernel32.CreateToolhelp32Snapshot
CreateToolhelp32Snapshot.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
CreateToolhelp32Snapshot.restype = ctypes.wintypes.HANDLE

Process32FirstW = kernel32.Process32FirstW
Process32FirstW.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p]
Process32FirstW.restype = ctypes.wintypes.BOOL

Process32NextW = kernel32.Process32NextW
Process32NextW.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p]
Process32NextW.restype = ctypes.wintypes.BOOL

WaitForMultipleObjects = kernel32.WaitForMultipleObjects
WaitForMultipleObjects.argtypes = [ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
WaitForMultipleObjects.restype = ctypes.wintypes.DWORD

ShutdownBlockReasonCreate = user32.ShutdownBlockReasonCreate
ShutdownBlockReasonCreate.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPCWSTR]
ShutdownBlockReasonCreate.restype = ctypes.wintypes.BOOL

ShutdownBlockReasonDestroy = user32.ShutdownBlockReasonDestroy
ShutdownBlockReasonDestroy.argtypes = [ctypes.wintypes.HWND]
ShutdownBlockReasonDestroy.restype = ctypes.wintypes.BOOL

SetLayeredWindowAttributes = user32.SetLayeredWindowAttributes
SetLayeredWindowAttributes.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.COLORREF, ctypes.c_byte, ctypes.wintypes.DWORD]
SetLayeredWindowAttributes.restype = ctypes.wintypes.BOOL

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
            creationflags=subprocess.CREATE_NO_WINDOW,
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
# Daemon: 进程句柄监听（WaitForMultipleObjects，零轮询零日志污染）
# ============================================================
SCAN_INTERVAL = 3  # 没找到进程时重新扫描的间隔（秒）


class ProcessWatcher:
    """用 WaitForMultipleObjects 等待进程退出，零CPU零轮询"""

    def __init__(self, names, on_exit):
        self._names = [n.lower() for n in names]
        self._cb = on_exit
        self._running = False
        self._last = 0.0

    def start(self):
        self._running = True
        # 初始扫描
        all_pids = []
        for name in self._names:
            all_pids.extend(self._find_pids(name))
        if all_pids:
            log(f"进程监控就绪 (句柄等待), 已发现目标: PID={all_pids}")
        else:
            log(f"进程监控就绪 (句柄等待), 目标未运行, 目标: {self._names}")
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    @staticmethod
    def _find_pids(name: str) -> list:
        """通过 toolhelp snapshot 查找进程 PID 列表"""
        pids = []
        try:
            TH32CS_SNAPPROCESS = 0x00000002
            h = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if h == -1:
                return pids

            class PROCESSENTRY32W(ctypes.Structure):
                _fields_ = [
                    ("dwSize", ctypes.wintypes.DWORD),
                    ("cntUsage", ctypes.wintypes.DWORD),
                    ("th32ProcessID", ctypes.wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.wintypes.ULONG)),
                    ("th32ModuleID", ctypes.wintypes.DWORD),
                    ("cntThreads", ctypes.wintypes.DWORD),
                    ("th32ParentProcessID", ctypes.wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", ctypes.wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260),
                ]

            pe = PROCESSENTRY32W()
            pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)

            if kernel32.Process32FirstW(h, ctypes.byref(pe)):
                while True:
                    exe = pe.szExeFile.lower()
                    if name.lower() in exe or exe == name.lower():
                        pids.append(pe.th32ProcessID)
                    if not kernel32.Process32NextW(h, ctypes.byref(pe)):
                        break
            kernel32.CloseHandle(h)
        except Exception as e:
            log(f"Process scan err: {e}")
        return pids

    def _run(self):
        was_monitoring = False  # 避免重复日志
        while self._running:
            # 找到所有目标进程
            all_pids = []
            for name in self._names:
                all_pids.extend(self._find_pids(name))

            if not all_pids:
                if was_monitoring:
                    log(f"目标进程已全部退出，{SCAN_INTERVAL}s 后重扫")
                    was_monitoring = False
                # 没找到进程，等 SCAN_INTERVAL 秒再扫
                for _ in range(SCAN_INTERVAL * 2):
                    if not self._running:
                        return
                    time.sleep(0.5)
                continue

            if not was_monitoring:
                log(f"监控 {len(all_pids)} 个目标进程 PID={all_pids}")
                was_monitoring = True

            # 打开进程句柄（只需 SYNCHRONIZE 权限）
            handles = []
            for pid in all_pids:
                h = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
                if h:
                    handles.append((h, pid))
                else:
                    log(f"OpenProcess(PID={pid}) 失败, err={kernel32.GetLastError()}")

            if not handles:
                log(f"无法打开任何进程句柄, {SCAN_INTERVAL}s 后重试")
                time.sleep(SCAN_INTERVAL)
                continue

            # 阻塞等待任意进程退出
            try:
                # WaitForMultipleObjects
                arr = (ctypes.wintypes.HANDLE * len(handles))()
                for i, (h, _) in enumerate(handles):
                    arr[i] = h
                ret = kernel32.WaitForMultipleObjects(
                    len(handles), arr, False, 30000  # 30s 超时，避免死等
                )
                idx = ret - 0  # WAIT_OBJECT_0 = 0
                if 0 <= idx < len(handles):
                    _, pid = handles[idx]
                    log(f"进程退出: PID={pid}")

                    # 关闭所有句柄
                    for h, _ in handles:
                        kernel32.CloseHandle(h)

                    # 通知
                    now = time.time()
                    if now - self._last > EXIT_COOLDOWN:
                        self._last = now
                        self._cb(self._names[0])

                    # 短暂等待后重扫
                    time.sleep(1)
                else:
                    # 超时或其他，关闭句柄重扫
                    for h, _ in handles:
                        kernel32.CloseHandle(h)
            except Exception as e:
                log(f"Wait err: {e}")
                for h, _ in handles:
                    kernel32.CloseHandle(h)


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
        self._shutdown_blocked_this_session = False
        self._hwnd = 0
        self._wmi = None
        self._fs = None
        self._fs_just_exited = False
        self._fs_grace_until = 0.0
        self._accel_exit_pending = False  # 全屏中加速器退出，待全屏退出后补弹窗

    def _on_accel_exit(self, name):
        log(f"加速器退出: {name}")
        if self._fs and self._fs.active:
            # 全屏中不弹窗，标记待处理
            self._accel_exit_pending = True
            log("全屏中，暂缓加速器退出弹窗")
        elif not self._shutdowning:
            threading.Thread(target=lambda: user32.MessageBoxW(0, "检测到雷神加速器已经退出！\n\n请确认是否已暂停加速时长？\n如果忘记暂停，时长会继续消耗！", "雷神加速器已退出", 0x40030), daemon=True).start()

    def _on_fs_exit(self, title):
        label = f"「{title}」" if title else "全屏程序"
        log(f"全屏退出: {label}")
        self._fs_just_exited = True
        self._fs_grace_until = time.time() + FULLSCREEN_GRACE

        if self._accel_exit_pending:
            # 全屏退出时补弹加速器退出提醒
            self._accel_exit_pending = False
            log("全屏退出，补弹加速器退出提醒")
            threading.Thread(target=lambda: user32.MessageBoxW(0, "检测到雷神加速器已经退出！\n\n请确认是否已暂停加速时长？\n如果忘记暂停，时长会继续消耗！", "雷神加速器已退出", 0x40030), daemon=True).start()
        elif not self._shutdowning:
            threading.Thread(target=lambda: user32.MessageBoxW(0, f"检测到 {label} 已退出。\n\n雷神加速器的时长可能还在消耗中！\n别忘了暂停加速时长哦～", "全屏程序已退出", 0x40030), daemon=True).start()

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
                        0x40024,  # MB_YESNO | MB_ICONQUESTION | MB_TOPMOST
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

        # 写 PID 文件，供卸载时精确杀进程
        try:
            pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".daemon.pid")
            with open(pid_file, "w") as f:
                f.write(str(os.getpid()))
        except Exception:
            pass

        self._fs = FullscreenWatcher(self._on_fs_exit)
        self._fs.start()
        self._wmi = ProcessWatcher(PROCESS_NAMES, self._on_accel_exit)
        self._wmi.start()

        try:
            self._hwnd = _create_message_window()
            log(f"消息窗口创建: {self._hwnd}")
            if self._hwnd:
                self._shutdown_hook()
                self._update_block()
                log("进入消息循环")
                _message_pump()
            else:
                log("消息窗口创建失败，仅运行进程监控（无关机拦截）")
                while self._running:
                    time.sleep(1)
        except Exception as e:
            log(f"Daemon 错误: {e}")
            import traceback
            log(traceback.format_exc())

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
    # 手动定义 WNDCLASSW（Python 3.14 从 ctypes.wintypes 中移除了）
    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", ctypes.wintypes.UINT),
            ("lpfnWndProc", _WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", ctypes.wintypes.HINSTANCE),
            ("hIcon", ctypes.wintypes.HICON),
            ("hCursor", ctypes.wintypes.HCURSOR),
            ("hbrBackground", ctypes.wintypes.HBRUSH),
            ("lpszMenuName", ctypes.wintypes.LPCWSTR),
            ("lpszClassName", ctypes.wintypes.LPCWSTR),
        ]

    hinst = kernel32.GetModuleHandleW(None)
    wnd_class = ctypes.create_unicode_buffer("LeiShenDaemon")
    wc = WNDCLASSW()
    wc.lpfnWndProc = _daemon_wndproc_ref
    wc.hInstance = hinst
    wc.lpszClassName = ctypes.addressof(wnd_class)
    user32.RegisterClassW(ctypes.byref(wc))

    hwnd = user32.CreateWindowExW(
        0x00000080 | 0x00080000 | 0x00000020,  # WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_TRANSPARENT
        wnd_class, "LeiShenDaemon", 0,
        0, 0, 1, 1, None, None, hinst, None,
    )
    if hwnd:
        # 设置完全透明 + 鼠标穿透（点击直接穿过，不影响游戏）
        SetLayeredWindowAttributes(hwnd, 0, 1, 0x00000002)  # LWA_ALPHA=2, alpha=1 几乎不可见
        user32.ShowWindow(hwnd, 7)  # SW_SHOWMINIMIZED — ShutdownBlockReasonCreate 需要窗口"可见"
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
# 服务管理接口（无 UI 依赖，返回结果 dict，GUI 和 console 共用）
# ============================================================
# 全局标志：当前是否在 console 模式（控制 log 是否同时输出到屏幕）
_CONSOLE_MODE = False


def _print_log(msg: str):
    """同时输出到控制台（console 模式下）和日志文件"""
    if _CONSOLE_MODE:
        print(msg)
    log(msg)


def _ensure_admin() -> bool:
    """检查是否以管理员运行"""
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


def _schtasks(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["schtasks"] + list(args),
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def service_status() -> dict:
    """查询服务状态，返回 {exists, running, status_text}"""
    exists = _schtasks("/query", "/tn", TASK_NAME).returncode == 0
    running = False
    if exists:
        r = subprocess.run(
            ["tasklist", "/fi", "IMAGENAME eq LeiShenMonitor.exe", "/fo", "csv", "/nh"],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if "LeiShenMonitor" not in r.stdout:
            r = subprocess.run(
                ["tasklist", "/fi", "IMAGENAME eq pythonw.exe", "/fo", "csv", "/nh"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            running = "pythonw" in r.stdout
        else:
            running = True

    if running:
        status_text = "监控运行中"
    elif exists:
        status_text = "已注册但未运行"
    else:
        status_text = "未安装"

    return {"exists": exists, "running": running, "status_text": status_text}


def service_install() -> dict:
    """注册并启动计划任务。返回 {success, message}"""
    _print_log("=" * 50)
    _print_log("[安装] 开始注册计划任务...")

    # 0. 检查管理员权限
    if not _ensure_admin():
        _print_log("[安装] 失败: 需要管理员权限")
        return {"success": False, "message": "需要管理员权限，请以管理员身份运行。"}

    # 1. 如果已存在，先删除
    if _schtasks("/query", "/tn", TASK_NAME).returncode == 0:
        _print_log("[安装] 检测到已有任务，先删除...")
        r_del = _schtasks("/delete", "/tn", TASK_NAME, "/f")
        if r_del.returncode != 0:
            _print_log(f"[安装] 删除旧任务失败: {r_del.stderr.strip()}")
            return {"success": False, "message": f"删除旧任务失败:\n{r_del.stderr.strip()}"}
        _print_log("[安装] 旧任务已删除")

    # 2. 构建启动命令
    safe_path = _short_path(SELF_PATH)
    if not getattr(sys, 'frozen', False):
        import shutil
        pyw = shutil.which("pythonw") or "pythonw"
        cmd = f'"{pyw}" "{safe_path}" --daemon'
        _print_log(f"[安装] 非打包模式，使用 pythonw: {pyw}")
    else:
        cmd = f'"{safe_path}" --daemon'
    _print_log(f"[安装] 启动命令: {cmd}")

    # 3. 创建计划任务
    r = _schtasks(
        "/create", "/tn", TASK_NAME,
        "/tr", cmd,
        "/sc", "ONLOGON",
        "/ru", os.environ.get("USERNAME", ""),
        "/rl", "HIGHEST",
        "/f",
    )
    if r.returncode != 0:
        _print_log(f"[安装] 创建计划任务失败: {r.stderr.strip()}")
        return {"success": False, "message": f"计划任务创建失败:\n{r.stderr.strip()}"}
    _print_log("[安装] 计划任务创建成功")

    # 4. 立即启动
    r2 = _schtasks("/run", "/tn", TASK_NAME)
    if r2.returncode != 0:
        _print_log(f"[安装] 立即启动失败: {r2.stderr.strip()}")
        _print_log("[安装] 任务已注册，将在下次登录时自动启动")
        return {"success": True, "message": "任务已注册，但立即启动失败。重启电脑后会自动运行。"}
    _print_log("[安装] 任务已启动")

    # 5. 等待并验证
    _print_log("[安装] 等待进程启动...")
    time.sleep(2)
    status = service_status()
    if status["running"]:
        _print_log("[安装] 验证通过: 进程正在运行")
        return {"success": True, "message": "服务已启用并正在运行。"}
    else:
        _print_log("[安装] 警告: 任务已创建但进程未检测到运行")
        return {"success": True, "message": "任务已创建。如果未运行，请检查日志或重启电脑。"}


def service_stop() -> dict:
    """停止并禁用计划任务。返回 {success, message}"""
    _print_log("=" * 50)
    _print_log("[停止] 开始停止服务...")

    if not _ensure_admin():
        _print_log("[停止] 失败: 需要管理员权限")
        return {"success": False, "message": "需要管理员权限，请以管理员身份运行。"}

    # 1. 结束运行中的任务
    r_end = _schtasks("/end", "/tn", TASK_NAME)
    _print_log(f"[停止] 结束任务: {'成功' if r_end.returncode == 0 else '任务未运行或已结束'}")

    # 2. 禁用任务
    r = _schtasks("/change", "/tn", TASK_NAME, "/disable")
    if r.returncode != 0:
        _print_log(f"[停止] 禁用任务失败: {r.stderr.strip()}")
        return {"success": False, "message": f"计划任务禁用失败:\n{r.stderr.strip()}"}
    _print_log("[停止] 任务已禁用")

    # 3. 通过 PID 文件杀 daemon 进程
    try:
        pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".daemon.pid")
        if os.path.exists(pid_file):
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            _print_log(f"[停止] 杀掉 daemon 进程 PID={pid}")
            kernel32 = ctypes.windll.kernel32
            h = kernel32.OpenProcess(0x0001, False, pid)
            if h:
                kernel32.TerminateProcess(h, 0)
                kernel32.CloseHandle(h)
            os.remove(pid_file)
    except Exception as e:
        _print_log(f"[停止] PID 杀进程失败: {e}")

    # 4. 兜底清理（排除自身进程）
    _print_log("[停止] 清理残留进程（排除自身）")
    subprocess.run(
        ["taskkill", "/fi", "IMAGENAME eq pythonw.exe", "/fi", f"PID ne {os.getpid()}", "/f"],
        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    subprocess.run(["taskkill", "/fi", "IMAGENAME eq LeiShenMonitor.exe", "/f"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    _print_log("[停止] 残留进程已清理")

    return {"success": True, "message": "服务已停止。"}


def service_uninstall() -> dict:
    """卸载计划任务。返回 {success, message}"""
    _print_log("=" * 50)
    _print_log("[卸载] 开始卸载服务...")

    if not _ensure_admin():
        _print_log("[卸载] 失败: 需要管理员权限")
        return {"success": False, "message": "需要管理员权限，请以管理员身份运行。"}

    # 1. 结束运行中的任务
    _schtasks("/end", "/tn", TASK_NAME)
    _print_log("[卸载] 已发送停止信号")

    # 2. 通过 PID 文件精确杀掉 daemon 进程
    try:
        pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".daemon.pid")
        if os.path.exists(pid_file):
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            _print_log(f"[卸载] 杀掉 daemon 进程 PID={pid}")
            kernel32 = ctypes.windll.kernel32
            h = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
            if h:
                kernel32.TerminateProcess(h, 0)
                kernel32.CloseHandle(h)
            os.remove(pid_file)
    except Exception as e:
        _print_log(f"[卸载] PID 杀进程失败: {e}")

    # 3. 兜底：杀掉其他 pythonw.exe（排除自身）
    _print_log("[卸载] 清理残留进程（排除自身）")
    subprocess.run(
        ["taskkill", "/fi", "IMAGENAME eq pythonw.exe", "/fi", f"PID ne {os.getpid()}", "/f"],
        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    subprocess.run(
        ["taskkill", "/fi", "IMAGENAME eq LeiShenMonitor.exe", "/f"],
        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    _print_log("[卸载] 残留进程已清理")

    # 4. 删除计划任务
    time.sleep(1)  # 等进程完全退出
    r = _schtasks("/delete", "/tn", TASK_NAME, "/f")
    if r.returncode != 0:
        _print_log(f"[卸载] 删除任务失败: {r.stderr.strip()}")
        return {"success": False, "message": f"计划任务删除失败:\n{r.stderr.strip()}"}
    _print_log("[卸载] 任务已删除")

    return {"success": True, "message": "监控服务已完全卸载。"}


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
        s = service_status()
        if s["running"]:
            set_status("监控运行中", green)
        elif s["exists"]:
            set_status("已注册但未运行", yellow)
        else:
            set_status("未安装", red)

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
        result = service_install()
        if result["success"]:
            refresh_after_delay(3)
        else:
            mb.showerror("启用失败", result["message"])
            refresh_status()

    def do_stop():
        if not _ensure_admin():
            _relaunch_as_admin("stop")
            return
        set_status("⏳ 正在停止...", yellow)
        result = service_stop()
        if result["success"]:
            refresh_after_delay(1)
        else:
            mb.showerror("停止失败", result["message"])
            refresh_status()

    def do_uninstall():
        if not mb.askyesno("确认卸载", "确定要完全卸载监控服务吗？", parent=root):
            return
        if not _ensure_admin():
            _relaunch_as_admin("uninstall")
            return
        set_status("⏳ 正在卸载...", yellow)
        result = service_uninstall()
        if result["success"]:
            mb.showinfo("已卸载", result["message"])
            refresh_status()
        else:
            mb.showerror("卸载失败", result["message"])
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
    s = service_status()
    if not s["exists"]:
        root.after(500, lambda: (
            mb.askyesno(
                "首次使用",
                "监控服务尚未启用。\n\n是否立即启用？\n（将设为开机自启）",
                parent=root,
            ) and do_install()
        ))

    root.mainloop()


# ============================================================
# 控制台管理界面
# ============================================================
def console_main():
    """控制台交互式管理（--console）"""
    global _CONSOLE_MODE
    _CONSOLE_MODE = True

    print("=" * 50)
    print("  雷神加速器 · 时长监控助手 (控制台)")
    print("=" * 50)

    while True:
        s = service_status()
        print(f"\n当前状态: {s['status_text']}")
        print("-" * 30)
        print("  1. 启用服务（注册并启动）")
        print("  2. 停止服务")
        print("  3. 卸载服务")
        print("  4. 查看日志（最后20行）")
        print("  0. 退出")
        print("-" * 30)

        try:
            choice = input("请选择 [0-4]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            break

        if choice == "1":
            print("\n>>> 执行: 启用服务")
            result = service_install()
            print(f"\n{'[OK]' if result['success'] else '[FAIL]'} {result['message']}")

        elif choice == "2":
            print("\n>>> 执行: 停止服务")
            result = service_stop()
            print(f"\n{'[OK]' if result['success'] else '[FAIL]'} {result['message']}")

        elif choice == "3":
            confirm = input("\n确定要完全卸载监控服务吗？[y/N]: ").strip().lower()
            if confirm != 'y':
                print("已取消。")
                continue
            print("\n>>> 执行: 卸载服务")
            result = service_uninstall()
            print(f"\n{'[OK]' if result['success'] else '[FAIL]'} {result['message']}")

        elif choice == "4":
            print("\n--- monitor.log (最后20行) ---")
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in lines[-20:]:
                        print(f"  {line.rstrip()}")
            except FileNotFoundError:
                print("  (日志文件不存在)")
            print("--- 结束 ---")

        elif choice == "0":
            print("已退出。")
            break

        else:
            print("无效选择，请输入 0-4。")


# ============================================================
# 入口
# ============================================================
def main():
    # --console: 控制台交互模式
    if "--console" in sys.argv:
        console_main()
        sys.exit(0)

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
        import tkinter as tk
        import tkinter.messagebox as mb
        if not _ensure_admin():
            t = tk.Tk()
            t.withdraw()
            mb.showerror("权限不足", "需要管理员权限才能执行此操作。")
            t.destroy()
            sys.exit(1)
        # 使用新的 service 函数
        if gui_action == "install":
            result = service_install()
        elif gui_action == "stop":
            result = service_stop()
        elif gui_action == "uninstall":
            result = service_uninstall()
        else:
            result = {"success": False, "message": f"未知操作: {gui_action}"}

        if gui_action == "uninstall":
            if result["success"]:
                mb.showinfo("已卸载", result["message"])
            else:
                mb.showerror("卸载失败", result["message"])
            sys.exit(0)
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

    # --daemon: 后台监控（必须在互斥锁检查之前）
    if "--daemon" in sys.argv:
        daemon = Daemon()
        try:
            daemon.run()
        except KeyboardInterrupt:
            pass
        finally:
            daemon.stop()
        sys.exit(0)

    # 单实例保护（仅 GUI 模式）
    mutex = kernel32.CreateMutexW(None, False, "Global\\LeiShenAcceleratorMonitorGUI")
    if kernel32.GetLastError() == 183:
        import tkinter as tk
        import tkinter.messagebox as mb
        t = tk.Tk()
        t.withdraw()
        mb.showinfo("提示", "管理界面已在运行中，请查看任务栏！")
        t.destroy()
        sys.exit(0)

    # GUI 模式
    gui_main()

    kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
