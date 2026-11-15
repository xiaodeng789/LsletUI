#!/usr/bin/env python3
"""LsletUI - 液态玻璃桥接层

通过 ctypes 加载 native/liquid_glass 编译出的 liquid_glass.dll，
为任意 QMainWindow 在窗口正下方渲染实时折射玻璃层。

加载失败（缺 DLL / 系统版本不够）时静默降级，不影响 Acrylic 兜底。
"""
import ctypes
import ctypes.wintypes as wintypes
import sys
import weakref
from pathlib import Path

from PySide6.QtCore import QObject, QEvent, QTimer

# DLL 搜索路径：与本文件同目录（源码运行）/ exe 同级目录（Nuitka 打包）
_DLL_DIR = Path(__file__).resolve().parent

# 存活的桥接（弱引用）。进程退出时由 shutdown_all() 统一收尾，
# 保证渲染线程在 Qt/DWM 拆掉之前先停下来。
_LIVE_BRIDGES = []


def _interpreter_finalizing():
    """解释器正在收尾时不要再去碰 ctypes/DLL。"""
    try:
        return bool(sys.is_finalizing())
    except Exception:
        return False

# 独立调试日志：绕过 main.py 的 Tee 重定向，直接写文件
import tempfile
_DEBUG_LOG = Path(tempfile.gettempdir()) / "liquid_glass_debug.log"

def log_diag(tag, msg):
    """诊断日志：始终写 liquid_glass_debug.log；开启调试开关时同时写 %TEMP%\\lsletui_debug.log

    用于定位「实机上看起来没生效」这类问题：窗口样式、ex-style、DLL 加载、
    面板创建等关键节点都由调用方传入 tag（Glass / MainWindow）落盘。
    """
    line = f"[{tag}] {msg}"
    try:
        _DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] {line}\n")
    except Exception:
        pass
    try:
        from capsule_app.debug_log import dlog
        dlog(tag, msg)
    except Exception:
        pass


def _dbg(msg):
    """写独立调试日志 + 尝试 print（双保险）"""
    log_diag("Glass", msg)
    print(msg)


class _LgParams(ctypes.Structure):
    _fields_ = [
        ("cornerRadius", ctypes.c_float),
        ("blurSigma", ctypes.c_float),
        ("displacementScale", ctypes.c_float),
        ("aberrationIntensity", ctypes.c_float),
        ("saturation", ctypes.c_float),
    ]


class LiquidGlassBridge(QObject):
    """液态玻璃面板桥接（内部持有 liquid_glass.dll 句柄）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dll = None
        self._panel = None
        self._anchor_hwnd = None
        self._enabled = False
        self._dpr = 0.0
        self._shutting_down = False
        self._load_dll()

        # 几何同步节流：Move/Resize 在动画过程中每秒能推几十次，
        # 合并成一个待落地请求，由定时器在帧边界统一提交给渲染线程。
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(8)
        self._sync_timer.timeout.connect(self._flush_geometry)

        _LIVE_BRIDGES.append(weakref.ref(self))

        # 隐藏/最小化时暂停渲染循环，节省 GPU
        if parent is not None:
            try:
                parent.installEventFilter(self)
            except Exception:
                pass
            # 窗口销毁时一定收尾：不能依赖 __del__，GC 可能在别的线程触发，
            # 那会跨线程 DestroyWindow 并与渲染线程抢 D3D 对象 → 驱动内 AV。
            try:
                parent.destroyed.connect(self._on_parent_destroyed)
            except Exception:
                pass

    def _on_parent_destroyed(self, *_a):
        self.shutdown()

    # --- 加载 ---
    def _load_dll(self):
        _dbg("[LiquidGlass] _load_dll 开始")
        # 进程自证：确认实机运行时加载的确实是这份代码与这个 DLL
        try:
            log_diag("Glass",
                     f"运行环境 python={sys.executable} cwd={Path.cwd()} "
                     f"module={Path(__file__).resolve()}")
        except Exception:
            pass
        # 硬件预检（启动时一次性）：不达标则不加载 DLL，节省 DXGI/D3D 初始化开销
        try:
            from capsule_app.hw_precheck import HwPrecheck
            hw = HwPrecheck.instance().result()
            _dbg(f"[LiquidGlass] 硬件预检结果: supported={hw.get('supported')}, reason={hw.get('reason')}")
            if not hw.get("supported", False):
                _dbg(f"[LiquidGlass] 硬件预检未通过，不加载渲染管线")
                return
        except Exception as e:
            _dbg(f"[LiquidGlass] 硬件预检异常: {e}")
            return

        dll_path = _DLL_DIR / "liquid_glass.dll"
        _dbg(f"[LiquidGlass] DLL 路径: {dll_path}, exists={dll_path.exists()}")
        if not dll_path.exists():
            _dbg(f"[LiquidGlass] 未找到 {dll_path}，玻璃层禁用")
            return
        try:
            dll = ctypes.CDLL(str(dll_path))
            dll.lg_is_supported.restype = ctypes.c_int
            dll.lg_default_params.argtypes = [ctypes.POINTER(_LgParams)]
            dll.lg_create.restype = ctypes.c_void_p
            dll.lg_create.argtypes = [ctypes.POINTER(_LgParams)]
            dll.lg_attach.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            dll.lg_set_bounds.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_int, ctypes.c_int]
            dll.lg_set_params.argtypes = [ctypes.c_void_p, ctypes.POINTER(_LgParams)]
            dll.lg_show.argtypes = [ctypes.c_void_p, ctypes.c_int]
            dll.lg_hide.argtypes = [ctypes.c_void_p, ctypes.c_int]
            dll.lg_destroy.argtypes = [ctypes.c_void_p]
            # lg_shutdown_engine 只有新版 DLL 才有，声明失败不影响渲染
            try:
                dll.lg_shutdown_engine.argtypes = []
                dll.lg_shutdown_engine.restype = None
            except AttributeError:
                _dbg("[LiquidGlass] DLL 无 lg_shutdown_engine（旧版），退出时不做引擎收尾")

            supported = dll.lg_is_supported()
            _dbg(f"[LiquidGlass] lg_is_supported() = {supported}")
            if not supported:
                _dbg("[LiquidGlass] 系统版本低于 Win10 19041，玻璃层禁用")
                return
            self._dll = dll
            _dbg("[LiquidGlass] DLL 加载成功")
        except Exception as e:
            _dbg(f"[LiquidGlass] DLL 加载失败: {e}")

    @property
    def available(self):
        return self._dll is not None

    @property
    def enabled(self):
        return self._enabled and self._panel is not None

    # --- 生命周期 ---
    def set_anchor(self, win_id):
        """绑定窗口句柄，首次调用时创建玻璃面板"""
        _dbg(f"[LiquidGlass] set_anchor called, win_id={win_id}, _dll={self._dll is not None}, _panel={self._panel}")
        if self._shutting_down:
            return
        if not self._dll or self._panel is not None:
            _dbg(f"[LiquidGlass] set_anchor 跳过: _dll={self._dll is not None}, _panel={self._panel}")
            return
        hwnd = int(win_id)
        if hwnd == 0:
            _dbg("[LiquidGlass] winId 尚未就绪，跳过")
            return
        params = _LgParams()
        self._dll.lg_default_params(ctypes.byref(params))
        _dbg(f"[LiquidGlass] lg_create params: corner={params.cornerRadius}, blur={params.blurSigma}, disp={params.displacementScale}, aberr={params.aberrationIntensity}, sat={params.saturation}")
        self._panel = self._dll.lg_create(ctypes.byref(params))
        if not self._panel:
            err = ctypes.get_last_error() if hasattr(ctypes, 'get_last_error') else 0
            _dbg(f"[LiquidGlass] 玻璃面板创建失败 (last_error=0x{err:08X})")
            return
        self._anchor_hwnd = hwnd
        self._dll.lg_attach(self._panel, ctypes.c_void_p(hwnd))
        _dbg(f"[LiquidGlass] 玻璃面板已创建, panel={self._panel}, hwnd=0x{hwnd:X}")
        # 面板圆角是物理像素，QSS 的 border-radius 是逻辑像素；
        # 高 DPI 下必须按缩放比放大，否则窗口的圆角会比玻璃大，四角露出玻璃月牙
        self._sync_corner_radius()
        # 面板创建后按当前开关状态补齐一次显示（设置可能在面板创建前已应用）
        if self._enabled:
            visible = True
            try:
                p = self.parent()
                visible = p is None or (p.isVisible() and not p.isMinimized())
            except Exception:
                pass
            if visible:
                self._apply_bounds()
                self._dll.lg_show(self._panel, 0)
                # 首次创建时窗口可能已经 show 过（Show 事件已错过），补一次定位
                QTimer.singleShot(0, self._on_anchor_shown)
                QTimer.singleShot(150, self.reassert_zorder)

    def set_enabled(self, enabled):
        """开关：True 显示玻璃层，False 隐藏"""
        enabled = bool(enabled)
        if enabled == self._enabled and self._panel is not None:
            return
        self._enabled = enabled
        if not self._panel:
            return
        if self._enabled:
            self._apply_bounds()
            visible = True
            try:
                p = self.parent()
                visible = p is None or (p.isVisible() and not p.isMinimized())
            except Exception:
                pass
            if visible:
                self._dll.lg_show(self._panel, 0)
                QTimer.singleShot(0, self._on_anchor_shown)
        else:
            self._dll.lg_hide(self._panel, 0)

    def bind_settings(self, settings_backend):
        """跟随全局 liquid_glass_enabled 设置（信号驱动，无需窗口各自监听）"""
        try:
            enabled = bool(settings_backend.get_settings().get("liquid_glass_enabled", True))
        except Exception:
            enabled = True
        self.set_enabled(enabled)
        settings_backend.settings_changed.connect(self._on_settings_changed)

    def _on_settings_changed(self, settings):
        self.set_enabled(bool(settings.get("liquid_glass_enabled", True)))

    # --- 内部：跟随宿主窗口显隐，隐藏时暂停渲染 ---
    def eventFilter(self, obj, event):
        if obj is self.parent() and self._panel and not self._shutting_down:
            et = event.type()
            if et in (QEvent.Hide, QEvent.WindowStateChange):
                hidden = False
                try:
                    hidden = obj.isHidden() or obj.isMinimized()
                except Exception:
                    pass
                if hidden:
                    # 隐藏后不再需要新内容：停掉待落地的几何，渲染线程随之空载
                    self._sync_timer.stop()
                    self._dll.lg_hide(self._panel, 0)
                elif self._enabled:
                    self._apply_bounds()
                    self._dll.lg_show(self._panel, 0)
            elif et in (QEvent.Show, QEvent.Resize, QEvent.Move):
                if self._enabled:
                    self.sync_geometry()
                if et == QEvent.Show:
                    # show() 之后 Qt 还会 raise_/activateWindow，稍后再钉一次 z-order
                    QTimer.singleShot(0, self._on_anchor_shown)
                    QTimer.singleShot(150, self.reassert_zorder)
        return False

    def _sync_corner_radius(self):
        """把玻璃面板圆角按窗口 DPI 缩放对齐 QSS 的 20px 逻辑圆角。"""
        if not (self._dll and self._panel):
            return
        try:
            dpr = float(self.parent().devicePixelRatioF()) if self.parent() else 1.0
        except Exception:
            dpr = 1.0
        if abs(dpr - self._dpr) < 0.01:
            return
        self._dpr = dpr
        params = _LgParams()
        self._dll.lg_default_params(ctypes.byref(params))
        params.cornerRadius *= dpr
        self._dll.lg_set_params(self._panel, ctypes.byref(params))
        _dbg(f"[LiquidGlass] 圆角按 DPI 对齐: dpr={dpr} radius={params.cornerRadius}")

    def sync_geometry(self):
        """请求一次几何同步（合并到帧边界）。

        灵动岛展开/收起动画与窗口拖动会在一秒内推几十次 Resize/Move，
        每次都直接进 DLL 会与渲染线程落地尺寸的节奏打架，这里合并成一次。
        """
        if self._shutting_down or not self._panel:
            return
        self._sync_timer.start()

    def _flush_geometry(self):
        """QTimer 回调：真正落地一次几何。"""
        self._apply_bounds()

    def _apply_bounds(self):
        """立即用 Win32 GetWindowRect 读取锚点窗口的真实物理矩形并交给 DLL。
        Qt 逻辑坐标在高 DPI 下与 Win32 物理坐标不一致，直接读 Win32 最准。"""
        if self._shutting_down:
            return
        self._sync_timer.stop()
        if not self._panel or not self._enabled or not self._anchor_hwnd:
            return
        rect = wintypes.RECT()
        if ctypes.windll.user32.GetWindowRect(self._anchor_hwnd, ctypes.byref(rect)):
            self._dll.lg_set_bounds(self._panel, rect.left, rect.top,
                                    rect.right - rect.left, rect.bottom - rect.top)

    # --- z-order ---
    def _panel_hwnds(self):
        """枚举 DLL 创建的面板顶层窗口（class=LsletUI_LiquidGlassPanel）。"""
        u = ctypes.windll.user32
        found = []
        proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, _lparam):
            buf = ctypes.create_unicode_buffer(128)
            u.GetClassNameW(hwnd, buf, 128)
            if buf.value == "LsletUI_LiquidGlassPanel":
                found.append(int(hwnd))
            return True

        u.EnumWindows(proc_type(_cb), 0)
        return found

    def _zorder_list(self):
        u = ctypes.windll.user32
        order, h = [], u.GetTopWindow(None)
        while h:
            order.append(int(h))
            h = u.GetWindow(wintypes.HWND(h), 2)   # GW_HWNDNEXT
        return order

    def reassert_zorder(self):
        """把玻璃面板重新插回锚点窗口正下方。

        lg_attach 只在创建时调用一次，控制台又是普通窗口：之后的 show()/raise_()
        会把锚点提到最前，而面板还留在原来的 z 位置，可能被其他应用窗口压住，
        视觉上就只剩「半透明」而没有折射模糊。所以显示/激活时都要重新插入一次。
        """
        if not (self._dll and self._panel and self._anchor_hwnd):
            return
        self._dll.lg_attach(self._panel, ctypes.c_void_p(self._anchor_hwnd))

    def log_panel_state(self, why):
        """记录面板窗口的可见性、矩形与 z-order（实机排查「没有模糊」用）。

        同时记录锚点窗口矩形与「面板 - 锚点」差值：差值为 0 表示面板与窗口
        严格重合（无外扩 → 无外发光/暗边投影），用于验收阴影是否被去掉。
        """
        try:
            u = ctypes.windll.user32
            order = self._zorder_list()
            panels = self._panel_hwnds()
            ai = order.index(self._anchor_hwnd) if self._anchor_hwnd in order else -1
            ar = wintypes.RECT()
            if self._anchor_hwnd:
                u.GetWindowRect(wintypes.HWND(self._anchor_hwnd), ctypes.byref(ar))
            parts = []
            for ph in panels:
                r = wintypes.RECT()
                u.GetWindowRect(wintypes.HWND(ph), ctypes.byref(r))
                parts.append(
                    f"panel=0x{ph:X} idx={order.index(ph) if ph in order else -1} "
                    f"visible={bool(u.IsWindowVisible(wintypes.HWND(ph)))} "
                    f"rect=({r.left},{r.top},{r.right},{r.bottom}) "
                    f"delta=({r.left - ar.left},{r.top - ar.top},"
                    f"{r.right - ar.right},{r.bottom - ar.bottom})")
            log_diag("Glass",
                     f"{why}: anchor=0x{(self._anchor_hwnd or 0):X} idx={ai} "
                     f"anchor_rect=({ar.left},{ar.top},{ar.right},{ar.bottom}) "
                     f"panels={len(panels)} " + "; ".join(parts))
        except Exception as e:
            log_diag("Glass", f"{why}: 面板状态记录失败 {e!r}")

    def _on_anchor_shown(self):
        """锚点显示/激活后：同步几何 + 重新插入到锚点正下方。"""
        if self._shutting_down or not self._enabled:
            return
        self._sync_corner_radius()
        self._apply_bounds()
        self.reassert_zorder()
        self.log_panel_state("anchor_shown")

    def shutdown(self):
        """收尾：先隐藏再销毁面板。可重复调用。

        面板句柄必须在 DLL 还活着的时候销毁，否则渲染线程会在对象拆完
        之后继续调驱动。__del__ 不可靠（GC 可能在别的线程触发），
        所以这里由窗口的 destroyed 信号 / closeEvent / aboutToQuit 显式驱动。
        """
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            self._sync_timer.stop()
        except Exception:
            pass
        panel, self._panel = self._panel, None
        if not (self._dll and panel):
            return
        if _interpreter_finalizing():
            # 收尾阶段不再跨 DLL 调用，面板窗口随进程一起回收
            return
        try:
            self._dll.lg_hide(panel, 0)
            self._dll.lg_destroy(panel)
            _dbg("[LiquidGlass] 面板已销毁")
        except Exception as e:
            log_diag("Glass", f"shutdown 失败: {e!r}")


def shutdown_all():
    """进程退出前统一收尾：销毁全部面板，再停掉共享渲染引擎。

    挂在 QApplication.aboutToQuit 上。此时 Qt/DWM/D3D 都还正常，
    渲染线程能干净地 join；留到解释器拆完再收尾就会在驱动里崩。
    """
    bridges = []
    for ref in list(_LIVE_BRIDGES):
        b = ref()
        try:
            _LIVE_BRIDGES.remove(ref)
        except ValueError:
            pass
        if b is not None:
            bridges.append(b)

    dll = None
    for b in bridges:
        if dll is None:
            dll = b._dll
        try:
            b.shutdown()
        except Exception as e:
            log_diag("Glass", f"shutdown_all 单桥接失败: {e!r}")

    if dll is not None and not _interpreter_finalizing():
        try:
            dll.lg_shutdown_engine()
            log_diag("Glass", "共享渲染引擎已停止")
        except Exception as e:
            log_diag("Glass", f"lg_shutdown_engine 失败: {e!r}")


def setup_liquid_glass(window, settings_backend):
    """给任意 QMainWindow 挂液态玻璃背景（几何/显隐/设置跟随全自动）。

    用法（窗口 __init__ 末尾调用一次即可）：
        self._liquid_glass = setup_liquid_glass(self, settings_backend)
    bridge 作为 window 的子 QObject；面板销毁由窗口的 destroyed 信号、
    closeEvent 里的 shutdown() 以及退出时的 shutdown_all() 共同保证。
    """
    _dbg(f"[LiquidGlass] setup_liquid_glass called, window={type(window).__name__}, settings_backend={settings_backend is not None}")
    if sys.platform != "win32" or settings_backend is None:
        _dbg("[LiquidGlass] 平台不支持或 settings_backend 为 None，返回 None")
        return None
    _dbg("[LiquidGlass] 创建 LiquidGlassBridge...")
    bridge = LiquidGlassBridge(window)
    if not bridge.available:
        _dbg("[LiquidGlass] Bridge 不可用（DLL 加载失败），返回 None")
        bridge.deleteLater()
        return None
    _dbg("[LiquidGlass] Bridge 创建成功，注册定时初始化")

    def _init():
        _dbg(f"[LiquidGlass] _init 执行，winId={int(window.winId())}")
        bridge.set_anchor(int(window.winId()))
        bridge.bind_settings(settings_backend)

    QTimer.singleShot(0, _init)
    return bridge
