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
# 注意：PyInstaller windowed 模式下 sys.stderr 为 None，直接 enable 会抛异常，
# 导致双击启动时模块导入阶段就静默退出；这里仅作开发期兜底，失败无碍，
# 日志初始化后会以日志文件句柄重新 enable（见 _setup_logging）。
import faulthandler
try:
    faulthandler.enable()
except Exception:
    pass

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
        # （通话/蓝牙/日历）的对象跨套间 Release → 0xC0000005 杀死进程。
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
    # 控制台窗口数据源：stdout/stderr 同时进内存环形缓冲
    from capsule_app.log_bus import get_log_sink
    _console_sink = get_log_sink()
    # pythonw 模式下 sys.stdout / sys.stderr 为 None，需要过滤掉避免 _Tee 包装失败
    _stdout_streams = tuple(s for s in (sys.stdout, _log_fh, _console_sink) if s is not None)
    _stderr_streams = tuple(s for s in (sys.stderr, _log_fh, _console_sink) if s is not None)
    sys.stdout = _Tee(*_stdout_streams)
    sys.stderr = _Tee(*_stderr_streams)
    import atexit
    atexit.register(_log_fh.close)
    # faulthandler 在 C 层按 fd 直写，必须指向日志文件句柄才能落盘
    try:
        faulthandler.enable(_log_fh)
    except Exception:
        pass
    print(f"[Main] 日志文件: {log_file}")

    # 渲染稳定性：强制软件渲染路径（打包后 GPU 加速会出 GLES context 错误）
    os.environ["QT_QUICK_BACKEND"] = "software"
    os.environ["QSG_RENDER_LOOP"] = "basic"

    # 告诉 Qt 自身的 OpenGL 渲染也使用软件模式
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.setAttribute(Qt.AA_UseSoftwareOpenGL)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    # 启动依赖检测：WebView2 / VC++ 2015-2022 x64 运行库（与特效锁定独立）
    # 缺失则弹窗引导安装；仅启动时检测一次。
    try:
        from capsule_app.hw_precheck import HwPrecheck, WEBVIEW2_URL, VCREDIST_URL
        deps = HwPrecheck.instance().dependencies()
        missing = []
        if not deps.get("webview2", True):
            missing.append(("WebView2 Runtime", WEBVIEW2_URL))
        if not deps.get("vcredist", True):
            missing.append(("VC++ 2015-2022 x64 运行库", VCREDIST_URL))
        if missing:
            import webbrowser
            from PySide6.QtWidgets import QMessageBox
            names = "、".join(n for n, _ in missing)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("LsletUI - 缺少运行依赖")
            msg.setText(f"缺少必要运行依赖（{names}），请点击下载安装")
            msg.setInformativeText("软件可继续运行，但部分功能可能异常。建议安装后重启软件。")
            btn_download = msg.addButton("下载安装", QMessageBox.AcceptRole)
            msg.addButton("继续运行", QMessageBox.RejectRole)
            msg.exec()
            if msg.clickedButton() is btn_download:
                for _, url in missing:
                    webbrowser.open(url)
    except Exception as e:
        print(f"[Main] 依赖检测弹窗失败: {e}")

    # 注意：不在此处调用 gc.collect()。主线程 GC 可能跨套间 Release
    # COM 线程残留的指针 → 0xC0000005 闪退。各 COM 线程的 stop() 已
    # 在各自套间内清理并 join。

    app_icon = _load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    widget = CapsuleWidget()
    widget.show()

    # 延迟发送启动通知，避免窗口初始化冲突
    # 使用非 daemon 线程：确保退出时能 join 等待 COM 清理完成
    _toast_threads = []

    def show_toast_thread():
        _show_toast(
            "LsletUI",
            "轻量级灵动岛已启动，悬停灵动岛可展开详情，主界面请从系统托盘菜单进入"
        )

    def _start_toast():
        t = threading.Thread(target=show_toast_thread, daemon=False)
        _toast_threads.append(t)
        t.start()

    QTimer.singleShot(500, _start_toast)

    # 液态玻璃：事件循环结束、DWM/D3D 都还正常时先停掉原生渲染线程。
    # 本进程最后走 os._exit，不留这条钩子的话原生线程会一直提交帧到驱动里。
    try:
        from capsule_app.liquid_glass import shutdown_all as _glass_shutdown_all
        app.aboutToQuit.connect(_glass_shutdown_all)
    except Exception as e:
        print(f"[Main] 液态玻璃退出钩子注册失败: {e}")

    exit_code = app.exec()
    # 等待所有 toast 线程完成 COM 清理后再退出
    for t in _toast_threads:
        if t.is_alive():
            t.join(timeout=3.0)
    _release_singleton_lock(singleton_handle)
    # 强制结束进程：个别后台 COM/监控线程偶发卡死时，Python 退出阶段
    # 会无限等待非 daemon 线程，导致进程残留、单实例互斥锁不释放，
    # 下次启动被误判为"已有实例"而静默退出。锁已在上方显式释放，
    # 日志经 Tee 每次 write 均已落盘，这里直接结束进程。
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(exit_code)


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