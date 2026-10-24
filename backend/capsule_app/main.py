#!/usr/bin/env python3
"""
LsletUI - 轻量级灵动岛应用
主应用模块
"""

import sys
import os
import threading
from pathlib import Path

# 原生崩溃（0xC0000005 等）时把 Python 调用栈 dump 到 stderr（随日志文件落盘）
import faulthandler
faulthandler.enable()

# 尝试导入PySide6，如果失败则使用tkinter
try:
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 导入资源路径兼容模块
import sys as _sys
if not getattr(_sys, 'frozen', False):
    # 开发模式
    sys.path.insert(0, str(PROJECT_ROOT))
from resource_path import get_resource_path

APP_ICON_CANDIDATES = [
    get_resource_path("img/default_icon.svg"),
]


def show_toast(title, message, duration=3):
    """
    显示一个非阻塞的 Toast 通知。
    这是从外部模块触发通知的公共接口。
    """
    # 在单独的线程中运行 _show_toast 以避免阻塞
    thread = threading.Thread(target=_show_toast, args=(title, message, duration), daemon=True)
    thread.start()


def _show_toast(title, message, duration=3):
    """显示系统 Toast 通知。"""
    # win11toast 内部通过 winrt/comtypes 创建 COM 对象，必须在本线程
    # 初始化 COM 套间并在退出前回收干净，否则其他线程的 gc.collect()
    # 会跨套间 Release 这些指针 → 0xC0000005 访问违例闪退。
    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except ImportError:
            pass

        icon_path = None
        for candidate in APP_ICON_CANDIDATES:
            if candidate.suffix.lower() == ".ico" and candidate.exists():
                icon_path = str(candidate)
                break

        try:
            from win11toast import toast

            toast(title, message, icon=icon_path or "")
            print(f"[Toast] 已通过 win11toast 发送通知: {title} - {message} (图标: {icon_path or '无'})")
            return
        except ImportError:
            pass
        except Exception as e:
            print(f"[Toast] win11toast 发送失败: {e}")

        try:
            from win10toast import ToastNotifier

            toaster = ToastNotifier()
            toaster.show_toast(
                title,
                message,
                icon_path=icon_path,
                duration=duration,
                threaded=True,
            )
            print(f"[Toast] 已通过 win10toast 发送通知: {title} - {message} (图标: {icon_path})")
        except ImportError:
            print(f"[Toast] 未安装 win11toast / win10toast，跳过通知: {message}")
        except Exception as e:
            print(f"[Toast] win10toast 发送失败: {e}")
    finally:
        # 绝不能 gc.collect()：GC 回收进程级垃圾链，会把其他 COM 线程
        # （蓝牙等）的对象跨套间 Release → 0xC0000005 杀死进程。
        # 本线程创建的 COM 对象均为局部变量，引用计数确定性释放。
        # 不调用 CoUninitialize()：它会销毁进程级 COM 状态，
        # 导致其他线程的 ctypes.windll 缓存失效 → _ctypes.pyd 0xC0000005
        pass


def _load_app_icon():
    if PYSIDE6_AVAILABLE:
        for icon_path in APP_ICON_CANDIDATES:
            if icon_path.exists():
                return QIcon(str(icon_path))
        return QIcon()
    return None


def run():
    """运行应用 - 强制使用 PySide6 以获得 iPhone 灵动岛效果"""
    if PYSIDE6_AVAILABLE:
        print("使用PySide6后端")
        return run_pyside6()

    # PySide6 不可用时才回退到 tkinter
    try:
        import tkinter
        print("PySide6 不可用，回退到 tkinter 后端")
        return run_tkinter()
    except ImportError:
        pass

    print("错误：没有可用的UI后端")
    return 1


def _cleanup_webengine_locks():
    """清理 QWebEngine 残留的锁文件，防止崩溃后重启失败"""
    import shutil
    profile_dirs = [
        Path.home() / ".pyisland_lite" / "webengine_profile",
        Path.home() / ".pyisland_lite" / "side_panel_webengine",
    ]
    lock_names = ["SingletonLock", "SingletonSocket", "SingletonCookie"]
    for profile_dir in profile_dirs:
        if not profile_dir.exists():
            continue
        for lock_name in lock_names:
            lock_file = profile_dir / lock_name
            try:
                if lock_file.exists() or lock_file.is_symlink():
                    lock_file.unlink()
                    print(f"[Main] 已清理残留锁文件: {lock_file}")
            except Exception as e:
                print(f"[Main] 清理锁文件失败 {lock_file}: {e}")
        # 如果 profile 目录存在 SingletonLock，也可能整个 Chromium 缓存损坏
        # 但不主动删除整个目录，避免丢失用户数据


def _acquire_singleton_lock():
    """获取单实例锁，防止多开。返回 (handle, True) 或 (None, False)"""
    if sys.platform != "win32":
        return None, True
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32")
        # 创建命名互斥体
        mutex_name = "Global\\LsletUI_Singleton_Mutex_v0.1.0"
        CREATE_NEW_MUTEX = 0x00000001
        handle = kernel32.CreateMutexW(None, True, mutex_name)
        if handle == 0:
            print("[Main] 创建互斥体失败")
            return None, False
        ERROR_ALREADY_EXISTS = 183
        last_error = kernel32.GetLastError()
        if last_error == ERROR_ALREADY_EXISTS:
            print("[Main] 检测到已有实例运行，退出")
            kernel32.CloseHandle(handle)
            return None, False
        print("[Main] 单实例锁已获取")
        return handle, True
    except Exception as e:
        print(f"[Main] 单实例锁获取失败: {e}")
        return None, True  # 失败时不阻止启动


def _release_singleton_lock(handle):
    """释放单实例锁"""
    if handle is None:
        return
    try:
        import ctypes
        ctypes.WinDLL("kernel32").CloseHandle(handle)
        print("[Main] 单实例锁已释放")
    except Exception as e:
        print(f"[Main] 释放单实例锁失败: {e}")


def run_pyside6():
    """使用PySide6运行应用"""
    from capsule_app.capsule_window import CapsuleWidget
    import atexit

    # 单实例检查：防止多开导致资源冲突
    singleton_handle, acquired = _acquire_singleton_lock()
    if not acquired:
        # 已有实例运行，尝试激活其窗口（通过 Toast 提示用户）
        try:
            from win11toast import toast
            toast("LsletUI", "LsletUI 已在运行中，请检查系统托盘")
        except Exception:
            pass
        return 0

    # atexit 兜底：崩溃/异常退出时也释放互斥锁句柄
    atexit.register(_release_singleton_lock, singleton_handle)

    # 清理 QWebEngine 残留锁文件（崩溃后重启时常见）
    _cleanup_webengine_locks()

    # 将 stdout/stderr 同时输出到控制台和日志文件，供 Bug 反馈使用
    log_dir = Path.home() / ".pyisland_lite" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "lsletui.log"

    class _Tee:
        def __init__(self, *streams):
            self._streams = streams
        def write(self, data):
            for s in self._streams:
                try:
                    s.write(data)
                    s.flush()
                except Exception:
                    pass
        def flush(self):
            for s in self._streams:
                try:
                    s.flush()
                except Exception:
                    pass
        def fileno(self):
            for s in self._streams:
                try:
                    return s.fileno()
                except Exception:
                    continue
            raise OSError("no stream with fileno available")
        def isatty(self):
            try:
                return self._streams[0].isatty()
            except Exception:
                return False
        def readable(self): return False
        def writable(self): return True
        def seekable(self): return False
        @property
        def encoding(self):
            return getattr(self._streams[0], 'encoding', 'utf-8')
        @property
        def closed(self):
            return False
        def close(self):
            for s in self._streams:
                try: s.close()
                except Exception: pass

    _log_fh = open(log_file, "a", encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, _log_fh)
    sys.stderr = _Tee(sys.stderr, _log_fh)
    import atexit
    atexit.register(_log_fh.close)
    # faulthandler 在 C 层按 fd 直写，必须指向日志文件句柄才能落盘
    try:
        faulthandler.enable(_log_fh)
    except Exception:
        pass
    print(f"[Main] 日志文件: {log_file}")

    # QtWebEngine 稳定性：禁用 GPU 加速和沙箱
    # （侧边栏只渲染本地静态 HTML，不需要 GPU；沙箱在打包环境下容易出问题）
    # 注意：
    # - 不可加 --use-gl=swiftshader —— Chromium 138+（Qt 6.11 内置）已移除该
    #   GL 实现，传入无效值会在首个 QWebEngineProfile 创建时触发 CHECK fastfail
    # - 不可加 --ignore-gpu-blocklist —— 与 --disable-gpu 矛盾，会导致 GPU 进程
    #   初始化时触发 ContextResult::kFatalFailure → 0xe0000001 闪退
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS",
                          "--disable-gpu --no-sandbox")

    # 告诉 Qt 自身的 OpenGL 渲染也使用软件模式，与 WebEngine 的 --disable-gpu 保持一致
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.setAttribute(Qt.AA_UseSoftwareOpenGL)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    # 注意：不在此处调用 gc.collect()。主线程 GC 可能跨套间 Release
    # COM 线程残留的指针 → 0xC0000005 闪退。各 COM 线程的 stop() 已
    # 在各自套间内清理并 join。

    app_icon = _load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    # 预热 WebEngine：在用户交互之前初始化 Chromium 子进程
    # 避免在点击事件中首次初始化导致 0xe0000001 崩溃
    try:
        from PySide6.QtWebEngineCore import QWebEngineProfile
        QWebEngineProfile.defaultProfile()
        print("[Main] WebEngine 预热完成")
    except Exception as e:
        print(f"[Main] WebEngine 预热失败（侧边栏可能不可用）: {e}")

    widget = CapsuleWidget()
    widget.show()

    # 延迟发送启动通知，避免窗口初始化冲突
    # 使用非 daemon 线程：确保退出时能 join 等待 COM 清理完成
    _toast_threads = []

    def show_toast_thread():
        _show_toast(
            "LsletUI",
            "轻量级灵动岛正在启动，当屏幕左侧出现蓝色胶囊时，单击或拖动蓝色胶囊可打开侧边栏"
        )

    def _start_toast():
        t = threading.Thread(target=show_toast_thread, daemon=False)
        _toast_threads.append(t)
        t.start()

    QTimer.singleShot(500, _start_toast)

    exit_code = app.exec()
    # 等待所有 toast 线程完成 COM 清理后再退出
    for t in _toast_threads:
        if t.is_alive():
            t.join(timeout=3.0)
    _release_singleton_lock(singleton_handle)
    return exit_code


def run_tkinter():
    """使用tkinter运行应用（更轻量级）"""
    import tkinter as tk
    from tkinter import ttk
    
    # 创建主窗口
    root = tk.Tk()
    root.title("LsletUI")
    root.geometry("300x600")
    root.configure(bg='#1a1a1a')
    
    # 设置窗口透明度
    root.attributes('-alpha', 0.9)
    
    # 创建胶囊按钮
    capsule_frame = tk.Frame(root, bg='#4a90e2', width=60, height=120)
    capsule_frame.pack(side=tk.LEFT, padx=10, pady=10)
    capsule_frame.pack_propagate(False)
    
    # 胶囊标签
    capsule_label = tk.Label(capsule_frame, text="胶囊", fg='white', bg='#4a90e2', font=('Arial', 10))
    capsule_label.pack(expand=True)
    
    # 侧边栏内容
    content_frame = tk.Frame(root, bg='#2d2d2d')
    content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=10)
    
    # 标题
    title_label = tk.Label(content_frame, text="LsletUI", fg='white', bg='#2d2d2d', font=('Arial', 14, 'bold'))
    title_label.pack(pady=10)
    
    # 功能按钮
    features = ["蓝牙设备", "待办事项", "文件中转", "进程监控", "关于"]
    for feature in features:
        btn = tk.Button(content_frame, text=feature, fg='white', bg='#3d3d3d', 
                       font=('Arial', 10), relief=tk.FLAT, padx=20, pady=5)
        btn.pack(fill=tk.X, padx=10, pady=2)
    
    # 运行主循环
    root.mainloop()
    return 0


if __name__ == "__main__":
    run()