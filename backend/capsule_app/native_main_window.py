#!/usr/bin/env python3
"""LsletUI - Windows 原生主界面（点击灵动岛打开）。"""

import json
import os
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QTimer, QUrl, Signal, QSize, QDateTime
from PySide6.QtGui import QDesktopServices, QFontMetrics, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox,
    QDateTimeEdit, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from capsule_app.bluetooth_backend import BluetoothBackend
from capsule_app.liquid_glass import setup_liquid_glass, log_diag
from capsule_app.native_ui import apply_windows_ui, tr, _load_svg_icon
from capsule_app.settings_backend import SettingsBackend
from capsule_app.smtc_monitor_backend import SMTCMonitorBackend

TODO_FILE = Path.home() / ".pyisland_lite" / "todos.json"
LINKS = (
    ("wait.website", "https://lsletuiapp.xiaodeng123.cn/"),
    ("GitHub", "https://github.com/xiaodeng789/LsletUI"),
)


def _card():
    frame = QFrame()
    frame.setObjectName("card")
    return frame


class _ElidedLabel(QLabel):
    """自适应宽度的省略标签（长文件名/路径不撑破布局）"""

    def __init__(self, text="", mode=Qt.ElideMiddle, parent=None):
        super().__init__(parent)
        self._full = text
        self._mode = mode
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def resizeEvent(self, event):
        metrics = QFontMetrics(self.font())
        self.setText(metrics.elidedText(self._full, self._mode, max(0, self.width())))
        super().resizeEvent(event)


class _TitleBar(QWidget):
    """无边框控制台的自绘标题栏：拖动窗口、双击最大化 + 三个窗口按钮。

    为什么控制台必须无边框：Windows 上 Qt 只对无边框窗口创建 WS_EX_LAYERED，
    带原生标题栏的 QMainWindow 无法把 Alpha 交给 DWM，半透明区域会被渲染成
    纯黑，下方的 liquid_glass 折射层就完全看不见。
    """

    def __init__(self, host, title, icon: QIcon, parent=None):
        super().__init__(parent)
        self._host = host
        self.setObjectName("titleBar")
        self.setFixedHeight(38)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 6, 0)
        lay.setSpacing(8)

        self._icon = QLabel()
        self._icon.setObjectName("titleBarIcon")
        self._icon.setFixedSize(16, 16)
        if not icon.isNull():
            self._icon.setPixmap(icon.pixmap(16, 16))
        # 图标与文字不拦截鼠标，保证拖拽区域连续
        self._icon.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self._icon)

        self._text = QLabel(title)
        self._text.setObjectName("titleBarText")
        self._text.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self._text)
        lay.addStretch(1)

        self._btn_min = self._make_button("min", "—", self._on_min)
        self._btn_max = self._make_button("max", "□", self._on_max)
        self._btn_close = self._make_button("close", "✕", self._on_close)
        for btn in (self._btn_min, self._btn_max, self._btn_close):
            lay.addWidget(btn)

    def _make_button(self, kind, glyph, slot):
        btn = QPushButton(glyph)
        btn.setObjectName("winCloseBtn" if kind == "close" else "winBtn")
        btn.setFixedSize(42, 28)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.clicked.connect(slot)
        return btn

    def set_title(self, text):
        self._text.setText(text)

    def set_maximized(self, maximized):
        self._btn_max.setText("❐" if maximized else "□")

    def _on_min(self):
        self._host.showMinimized()

    def _on_max(self):
        self._host._toggle_maximize()

    def _on_close(self):
        self._host.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle = self._host.windowHandle()
            if handle is not None:
                # 交给系统做原生拖动（支持贴边分屏与多屏拖拽）
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._host._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class NativeMainWindow(QMainWindow):
    open_clipboard_requested = Signal()
    clear_clipboard_requested = Signal()
    open_settings_requested = Signal()

    def __init__(self, parent=None, smtc=None, settings=None):
        super().__init__(parent)
        self._external_smtc = smtc
        self._owns_smtc = smtc is None
        self._external_settings = settings
        self._owns_settings = settings is None
        self._shutting_down = False

        if self._external_smtc is not None:
            self.smtc_monitor = self._external_smtc
        else:
            self.smtc_monitor = SMTCMonitorBackend()
        if self._external_settings is not None:
            self.settings_backend = self._external_settings
        else:
            self.settings_backend = SettingsBackend()

        self.bluetooth_backend = BluetoothBackend()
        self._lang = self.settings_backend.get_settings().get("language", "zh")
        self._theme = self.settings_backend.get_settings().get("theme", "dark")
        self._todo_items = []
        self._todo_filter = "all"

        apply_windows_ui(self, self._theme)
        # 无边框：Windows 上 Qt 只有对无边框窗口才创建 WS_EX_LAYERED，才能把
        # 半透明 Alpha 交给 DWM 合成；带原生标题栏时透明区域会渲染成纯黑。
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        # 液态玻璃：窗口自身必须半透明，下方才能露出 liquid_glass.dll 的折射层。
        # 该属性只能在 show() 之前设置，所以这里一次性开启；关闭玻璃时靠
        # apply_windows_ui(..., glass=False) 把根容器重新涂成不透明实色。
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._glass_on = False
        self._glass_style_applied = False
        self._liquid_glass = None
        # 尺寸 = 原 920x640 内容区 + 38px 自绘标题栏，保证内容区布局不变
        self.resize(920, 678)
        self.setMinimumSize(760, 558)
        self._build()
        self._wire_backends()
        self.settings_backend.settings_changed.connect(self._on_settings_changed)
        self._retranslate()

        # 挂液态玻璃层（硬件不达标 / DLL 缺失时返回 None，自动回退不透明样式）
        self._init_liquid_glass()

        # 去除 Windows DWM 系统阴影（无边框窗口默认带阴影）
        self._remove_system_shadow()

        # 启用 Windows 毛玻璃/Mica 效果（winId 需在窗口显示后才创建）
        QTimer.singleShot(0, self._enable_backdrop)

    def _init_liquid_glass(self):
        """创建液态玻璃桥接，并按当前开关状态应用样式。"""
        try:
            self._liquid_glass = setup_liquid_glass(self, self.settings_backend)
        except Exception as e:
            import traceback
            log_diag("MainWindow",
                     f"液态玻璃初始化异常: {e!r}\n{traceback.format_exc()}")
            self._liquid_glass = None
        enabled = False
        if self._liquid_glass is not None:
            try:
                enabled = bool(
                    self.settings_backend.get_settings().get(
                        "liquid_glass_enabled", True))
            except Exception:
                enabled = True
        else:
            # DLL 缺失 / 硬件预检不通过时 setup 返回 None：明确记录已回退，
            # 避免实机上只看到「没变化」却不知道原因（具体原因见同时刻 Glass 日志）
            log_diag("MainWindow",
                     "液态玻璃不可用，已回退为不透明皮肤（原因见同时间 Glass 日志）")
        self._apply_glass_style(enabled)

    def _apply_glass_style(self, enabled):
        """切换半透明玻璃样式 / 不透明兜底样式（不重建窗口）。"""
        enabled = bool(enabled) and self._liquid_glass is not None
        if self._glass_style_applied and enabled == self._glass_on:
            return
        self._glass_on = enabled
        self._glass_style_applied = True
        apply_windows_ui(self, self._theme, glass=enabled)
        # 日志区配色已在 QSS 里，这里只需切换它的绘制属性
        if hasattr(self, "_console"):
            self._console._apply_theme()
        if self._liquid_glass is not None:
            self._liquid_glass.set_enabled(enabled)
        self._log_glass_state("apply")

    def _log_glass_state(self, where):
        """把玻璃链路的真实状态写入诊断日志（实机定位「看起来没变化」用）。

        记录：窗口类/句柄、是否无边框、ex-style 是否含 WS_EX_LAYERED、
        是否半透明、设置值、桥接与面板状态、最终 QSS 长度及是否含玻璃段、
        根容器 objectName 是否与 QSS 选择器一致。
        """
        try:
            import ctypes
            # internalWinId 不会强制创建原生窗口（__init__ 阶段还没 show）
            hwnd = int(self.internalWinId() or 0)
            ex = (ctypes.WinDLL("user32").GetWindowLongW(
                ctypes.c_void_p(hwnd), -20) if hwnd else 0)
            try:
                setting = self.settings_backend.get_settings().get(
                    "liquid_glass_enabled", True)
            except Exception:
                setting = "?"
            bridge = self._liquid_glass
            qss = self.styleSheet()
            root = self.centralWidget()
            log_diag(
                "MainWindow",
                f"{where}: class={type(self).__name__} hwnd=0x{hwnd:X} "
                f"frameless={bool(self.windowFlags() & Qt.FramelessWindowHint)} "
                f"exstyle=0x{ex & 0xFFFFFFFF:08X} layered={bool(ex & 0x80000)} "
                f"translucent={self.testAttribute(Qt.WA_TranslucentBackground)} "
                f"setting={setting} bridge={bridge is not None} "
                f"dll={getattr(bridge, 'available', False)} "
                f"panel={getattr(bridge, '_panel', None)} "
                f"glass_on={self._glass_on} qss_len={len(qss)} "
                f"glass_qss={'lsletui-glass' in qss} "
                f"root={root.objectName() if root is not None else 'None'}")
        except Exception as e:
            log_diag("MainWindow", f"{where}: 诊断日志写入失败 {e!r}")

    def _enable_backdrop(self):
        """为原生主界面启用 Windows 11 Mica/亚克力毛玻璃。"""
        import sys
        # 玻璃模式下窗口是分层的半透明窗口，Mica 不会生效，跳过避免 DWM 冲突
        if sys.platform != "win32" or self._glass_on:
            return
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.winId())

            # Windows 11 22H2+ Mica 背景
            DWMWA_SYSTEMBACKDROP_TYPE = 38
            DWMSBT_MAINWINDOW = 2  # Mica（主窗口风格）
            value = ctypes.c_int(DWMSBT_MAINWINDOW)
            result = ctypes.WinDLL("dwmapi").DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(DWMWA_SYSTEMBACKDROP_TYPE),
                ctypes.byref(value),
                ctypes.sizeof(value)
            )
            if result == 0:
                # Mica 背景让桌面透过，配合深色主题有质感
                pass
            else:
                # 回退：旧版亚克力
                class AccentPolicy(ctypes.Structure):
                    _fields_ = [
                        ("AccentState", ctypes.c_int),
                        ("AccentFlags", ctypes.c_int),
                        ("GradientColor", ctypes.c_ulong),
                        ("AnimationId", ctypes.c_int),
                    ]

                class WCAD(ctypes.Structure):
                    _fields_ = [
                        ("Attribute", ctypes.c_int),
                        ("Data", ctypes.c_void_p),
                        ("SizeOfData", ctypes.c_size_t),
                    ]

                accent = AccentPolicy()
                accent.AccentState = 4  # ACCENT_ENABLE_ACRYLICBLURBEHIND
                accent.GradientColor = 0x30000000  # ABGR：黑色 48% alpha

                data = WCAD()
                data.Attribute = 19  # WCA_ACCENT_POLICY
                data.Data = ctypes.cast(ctypes.byref(accent), ctypes.c_void_p)
                data.SizeOfData = ctypes.sizeof(accent)

                ctypes.WinDLL("user32").SetWindowCompositionAttribute(
                    wintypes.HWND(hwnd), ctypes.byref(data))
        except Exception:
            pass

    def _remove_system_shadow(self):
        """去除 Windows DWM 系统阴影（无边框窗口默认带阴影）"""
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = int(self.winId())
            if hwnd == 0:
                return
            # DWMWA_NCRENDERING_POLICY = 2
            # DWMNCRP_DISABLED = 1
            DWMWA_NCRENDERING_POLICY = 2
            DWMNCRP_DISABLED = 1
            value = ctypes.c_int(DWMNCRP_DISABLED)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(DWMWA_NCRENDERING_POLICY),
                ctypes.byref(value),
                ctypes.sizeof(value)
            )
        except Exception:
            pass

    def _t(self, key, **kwargs):
        return tr(self._lang, key, **kwargs)

    # --- 无边框窗口：四边/四角原生缩放 + 最大化 ---
    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            try:
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084:  # WM_NCHITTEST
                    code = self._hit_test_border(msg)
                    if code:
                        return True, code
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def _hit_test_border(self, msg):
        """命中窗口边缘时返回 HT* 热区代码，让系统完成无边框缩放。"""
        if self.isMaximized() or self.isFullScreen():
            return 0
        import ctypes
        from ctypes import wintypes

        hwnd = wintypes.HWND(int(self.winId()))
        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        pt = wintypes.POINT(x, y)
        ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(pt))
        rect = wintypes.RECT()
        ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))
        w, h = rect.right, rect.bottom
        b = max(5, int(6 * self.devicePixelRatioF()))  # 物理像素热区宽度
        left = pt.x < b
        right = pt.x >= w - b
        top = pt.y < b
        bottom = pt.y >= h - b
        if top and left:
            return 13  # HTTOPLEFT
        if top and right:
            return 14  # HTTOPRIGHT
        if bottom and left:
            return 16  # HTBOTTOMLEFT
        if bottom and right:
            return 17  # HTBOTTOMRIGHT
        if left:
            return 10  # HTLEFT
        if right:
            return 11  # HTRIGHT
        if top:
            return 12  # HTTOP
        if bottom:
            return 15  # HTBOTTOM
        return 0

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        if hasattr(self, "_titlebar"):
            self._titlebar.set_maximized(self.isMaximized())

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, "_titlebar"):
            self._titlebar.set_maximized(self.isMaximized())

    def showEvent(self, event):
        super().showEvent(event)
        # 显示后才是真实合成状态：记录一次 ex-style / QSS / 面板状态
        QTimer.singleShot(0, lambda: self._log_glass_state("show"))

    def _build(self):
        root = QWidget()
        root.setObjectName("winRoot")
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 自绘标题栏（无边框窗口的拖动/窗口按钮入口）
        icon = self.windowIcon()
        if icon.isNull():
            icon = QApplication.windowIcon()
        self._titlebar = _TitleBar(self, self._t("app.title"), icon)
        outer.addWidget(self._titlebar)

        body = QWidget()
        body.setObjectName("bodyRoot")
        outer.addWidget(body, 1)

        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._nav = QListWidget()
        self._nav.setObjectName("navList")
        self._nav.setFixedWidth(200)
        self._nav.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self._nav)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)

        self._home_page = self._build_music_page()
        self._log_page = self._build_log_page()
        self._bt_page = self._build_bt_page()
        self._settings_page = self._build_settings_page()
        self._todo_page = self._build_todo_page()
        self._links_page = self._build_links_page()
        self._about_page = self._build_about_page()

        for page in (self._home_page, self._log_page, self._bt_page,
                     self._settings_page,
                     self._todo_page, self._links_page, self._about_page):
            self._stack.addWidget(page)

        self._nav.currentRowChanged.connect(self._on_nav)
        self._fill_nav()
        self._nav.setCurrentRow(0)

    # 侧边栏导航顺序（与 _stack 页面一一对应）
    NAV_KEYS = (
        "nav.home", "nav.log", "nav.bluetooth",
        "nav.settings", "nav.todo", "nav.links", "nav.about",
    )

    def _fill_nav(self):
        keys = self.NAV_KEYS
        # 每个 nav key 对应的图标文件（相对于 backend/img/）
        icons = {
            "nav.home":     "界面.svg",
            "nav.log":      "代码.svg",
            "nav.bluetooth": "bluetooth-BtTQvFRP.png",
            "nav.settings": "设置.svg",
            "nav.todo":     "提醒.svg",
            "nav.links":    "链接.svg",
            "nav.about":    "default_icon.svg",
        }
        from capsule_app.native_ui import _IMG_DIR, _CURRENT_THEME
        # Qt 不会把 QSS 的 color 传给 SVG 的 currentColor，
        # 需要根据主题显式指定 SVG 填充色
        svg_color = "#a8a8b8" if _CURRENT_THEME == "dark" else "#5a5a66"
        self._nav.blockSignals(True)
        row = self._nav.currentRow()
        self._nav.clear()
        for key in keys:
            item = QListWidgetItem(self._t(key))
            icon_name = icons.get(key, "")
            if icon_name:
                icon_path = _IMG_DIR / icon_name
                if icon_path.exists():
                    if icon_path.suffix.lower() == ".svg":
                        item.setIcon(_load_svg_icon(icon_path, svg_color))
                    else:
                        item.setIcon(QIcon(str(icon_path)))
            item.setSizeHint(item.sizeHint() + QSize(0, 6))  # 行高更宽松
            self._nav.addItem(item)
        self._nav.setCurrentRow(max(0, row))
        self._nav.blockSignals(False)

    def _on_nav(self, row):
        if row < 0:
            return
        self._stack.setCurrentIndex(row)

    def select_page(self, key):
        """供外部（如托盘"控制台"入口）跳转到指定页面，如 "nav.log"。"""
        try:
            row = self.NAV_KEYS.index(key)
        except ValueError:
            return
        self._nav.setCurrentRow(row)

    def _page_layout(self, title_attr):
        page = QWidget()
        # 与根容器区分：根容器负责玻璃遮罩，页面自身保持透明避免遮罩叠加变黑
        page.setObjectName("pageRoot")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        title = QLabel()
        title.setObjectName("pageTitle")
        setattr(self, title_attr, title)
        lay.addWidget(title)
        return page, lay

    def _build_bt_page(self):
        page, lay = self._page_layout("_bt_title")
        self._bt_status = QLabel()
        self._bt_status.setObjectName("hint")
        lay.addWidget(self._bt_status)
        card = _card()
        card_lay = QVBoxLayout(card)
        self._bt_list = QListWidget()
        self._bt_list.setMinimumHeight(280)
        card_lay.addWidget(self._bt_list)
        lay.addWidget(card, 1)
        return page

    def _build_music_page(self):
        page, lay = self._page_layout("_music_title")
        self._music_sub = QLabel()
        self._music_sub.setObjectName("hint")
        lay.addWidget(self._music_sub)
        card = _card()
        card_lay = QHBoxLayout(card)
        card_lay.setContentsMargins(16, 16, 16, 16)
        self._cover = QLabel()
        self._cover.setFixedSize(120, 120)
        self._cover.setAlignment(Qt.AlignCenter)
        self._cover.setStyleSheet("background:#e8e8e8; border-radius:6px;")
        card_lay.addWidget(self._cover)
        info = QVBoxLayout()
        self._track = QLabel()
        self._track.setStyleSheet("font-size:16px; font-weight:600;")
        self._artist = QLabel()
        self._artist.setObjectName("hint")
        self._music_state = QLabel()
        btns = QHBoxLayout()
        self._prev_btn = QPushButton()
        self._play_btn = QPushButton()
        self._next_btn = QPushButton()
        self._prev_btn.clicked.connect(lambda: self.smtc_monitor.handle_command("prev"))
        self._play_btn.clicked.connect(lambda: self.smtc_monitor.handle_command("playpause"))
        self._next_btn.clicked.connect(lambda: self.smtc_monitor.handle_command("next"))
        btns.addWidget(self._prev_btn)
        btns.addWidget(self._play_btn)
        btns.addWidget(self._next_btn)
        btns.addStretch(1)
        info.addWidget(self._track)
        info.addWidget(self._artist)
        info.addWidget(self._music_state)
        info.addStretch(1)
        info.addLayout(btns)
        card_lay.addLayout(info, 1)
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _build_log_page(self):
        page, lay = self._page_layout("_log_title")
        from capsule_app.console_widget import ConsoleWidget
        self._console = ConsoleWidget(lang=self._lang)
        lay.addWidget(self._console, 1)
        return page

    def _build_settings_page(self):
        page, lay = self._page_layout("_settings_title")
        from capsule_app.settings_page import SettingsPageWidget
        self._settings_widget = SettingsPageWidget(self.settings_backend)
        lay.addWidget(self._settings_widget, 1)
        return page

    def _build_todo_page(self):
        page, lay = self._page_layout("_todo_title")

        # 输入行：主按钮紧贴输入框，与批量操作按钮同规格
        row = QHBoxLayout()
        row.setSpacing(8)
        self._todo_input = QLineEdit()
        self._todo_input.setClearButtonEnabled(True)
        self._todo_add = QPushButton()
        self._todo_add.setObjectName("convPrimary")
        self._todo_add.clicked.connect(self._add_todo)
        self._todo_input.returnPressed.connect(self._add_todo)
        row.addWidget(self._todo_input, 1)
        row.addWidget(self._todo_add)
        lay.addLayout(row)

        # 三个筛选是互斥状态切换，用日志页同款胶囊；
        # 「清空已完成」是动作，靠右单独放，避免和筛选混成一组看不出谁可选
        filt = QHBoxLayout()
        filt.setSpacing(8)
        self._todo_all = QPushButton()
        self._todo_active = QPushButton()
        self._todo_done = QPushButton()
        self._todo_filter_btns = {
            "all": self._todo_all,
            "active": self._todo_active,
            "done": self._todo_done,
        }
        self._todo_filter_group = QButtonGroup(self)
        self._todo_filter_group.setExclusive(True)
        for key, btn in self._todo_filter_btns.items():
            btn.setObjectName("logToggle")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, k=key: self._set_todo_filter(k))
            self._todo_filter_group.addButton(btn)
            filt.addWidget(btn)
        self._todo_all.setChecked(True)
        filt.addStretch(1)
        self._todo_clear = QPushButton()
        self._todo_clear.setObjectName("convBtn")
        self._todo_clear.clicked.connect(self._clear_done_todos)
        filt.addWidget(self._todo_clear)
        lay.addLayout(filt)

        # 列表：滚动区 + 卡片行（与批量列表一致）。
        # 不用 QListWidget+setItemWidget：行内控件的宽度与悬停态都受列表项尺寸牵制
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        host = QWidget()
        self._todo_lay = QVBoxLayout(host)
        self._todo_lay.setContentsMargins(0, 2, 6, 0)
        self._todo_lay.setSpacing(8)
        self._todo_empty = QLabel()
        self._todo_empty.setObjectName("hint")
        self._todo_empty.setAlignment(Qt.AlignCenter)
        self._todo_empty.setMinimumHeight(120)
        self._todo_lay.addWidget(self._todo_empty)
        self._todo_lay.addStretch(1)
        scroll.setWidget(host)
        lay.addWidget(scroll, 1)

        self._todo_row_widgets = []
        self._todo_rows = {}
        self._load_todos()
        return page

    def _build_links_page(self):
        page, lay = self._page_layout("_links_title")
        self._link_btns = []
        for name, url in LINKS:
            btn = QPushButton()
            btn.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            self._link_btns.append((btn, name))
            lay.addWidget(btn)
        self._thanks = QLabel()
        self._thanks.setObjectName("hint")
        lay.addWidget(self._thanks)
        lay.addStretch(1)
        return page

    def _build_about_page(self):
        page, lay = self._page_layout("_about_title")
        self._about_ver = QLabel("LsletUI Free v0.2.0")
        lay.addWidget(self._about_ver)
        self._about_hint = QLabel()
        self._about_hint.setObjectName("hint")
        self._about_hint.setWordWrap(True)
        lay.addWidget(self._about_hint)
        row = QHBoxLayout()
        self._help_btn = QPushButton()
        self._hist_btn = QPushButton()
        self._bug_btn = QPushButton()
        self._help_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://lsletui.xiaodeng123.cn")))
        self._hist_btn.clicked.connect(self.open_clipboard_requested.emit)
        self._bug_btn.clicked.connect(self._report_bug)
        row.addWidget(self._help_btn)
        row.addWidget(self._hist_btn)
        row.addWidget(self._bug_btn)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return page

    def _wire_backends(self):
        self.bluetooth_backend.devices_updated.connect(self._on_bt_devices)
        self.bluetooth_backend.bt_status_changed.connect(self._on_bt_status)
        self.bluetooth_backend.countdown_updated.connect(self._on_bt_countdown)
        self.smtc_monitor.music_info_updated.connect(self._on_music)
        info = self.smtc_monitor.get_last_info()
        if info:
            self._on_music(info)
        else:
            self._on_music({})
        self._on_bt_devices(self.bluetooth_backend.connected_devices)
        self._on_bt_status(self.bluetooth_backend.bt_enabled)

    def _on_settings_changed(self, settings):
        lang = settings.get("language", "zh")
        if lang != self._lang:
            self._lang = lang
            self._retranslate()
        # 液态玻璃开关：跟随设置实时切换（关闭后回退不透明样式）
        if self._liquid_glass is not None:
            glass_wanted = bool(settings.get("liquid_glass_enabled", True))
            if glass_wanted != self._glass_on:
                self._apply_glass_style(glass_wanted)
        theme = settings.get("theme", "dark")
        if theme != self._theme:
            self._theme = theme
            apply_windows_ui(self, theme, glass=self._glass_on)
            # 刷新导航图标颜色以匹配新主题
            self._fill_nav()

    def _retranslate(self):
        self.setWindowTitle(self._t("app.title"))
        if hasattr(self, "_titlebar"):
            self._titlebar.set_title(self._t("app.title"))
        self._fill_nav()
        self._bt_title.setText(self._t("bt.title"))
        self._music_title.setText(self._t("music.title"))
        self._music_sub.setText(self._t("music.subtitle"))
        self._prev_btn.setText(self._t("music.prev"))
        self._play_btn.setText(self._t("music.play"))
        self._next_btn.setText(self._t("music.next"))
        self._todo_title.setText(self._t("todo.title"))
        self._todo_input.setPlaceholderText(self._t("todo.placeholder"))
        self._todo_add.setText(self._t("todo.add"))
        self._todo_all.setText(self._t("todo.filter_all"))
        self._todo_active.setText(self._t("todo.filter_active"))
        self._todo_done.setText(self._t("todo.filter_done"))
        self._todo_clear.setText(self._t("todo.clearDone"))
        self._todo_empty.setText(self._t("todo.empty"))
        self._log_title.setText(self._t("nav.log"))
        self._settings_title.setText(self._t("nav.settings"))
        self._links_title.setText(self._t("wait.title"))
        for btn, name in self._link_btns:
            btn.setText(self._t(name) if name.startswith("wait.") else name)
        self._thanks.setText(self._t("wait.thanks"))
        self._about_title.setText(self._t("about.title"))
        self._about_hint.setText(self._t("about.settingsHint"))
        self._help_btn.setText(self._t("about.help"))
        self._hist_btn.setText(self._t("about.history"))
        self._bug_btn.setText(self._t("about.bug"))
        # 同步刷新嵌入的子页面（设置页 / 日志页）
        if hasattr(self, "_settings_widget"):
            self._settings_widget.retranslate(self._lang)
        if hasattr(self, "_console"):
            self._console.retranslate(self._lang)
        self._refresh_bt_status_text()
        self._on_music(self.smtc_monitor.get_last_info() or {})
        self._render_todos()

    def _refresh_bt_status_text(self, seconds=None):
        enabled = self.bluetooth_backend.bt_enabled
        if enabled is False:
            self._bt_status.setText(self._t("bt.offHint"))
        elif enabled is True:
            s = self.bluetooth_backend._countdown_remaining if seconds is None else seconds
            self._bt_status.setText(self._t("bt.scanning", s=s))
        else:
            self._bt_status.setText(self._t("bt.detecting"))

    def _on_bt_devices(self, devices):
        self._bt_list.clear()
        if self.bluetooth_backend.bt_enabled is False:
            self._bt_list.addItem(self._t("bt.offHint"))
            return
        if not devices:
            self._bt_list.addItem(self._t("bt.noDevices"))
            return
        for d in devices:
            name = d.get("name") or "—"
            bat = d.get("battery")
            extra = self._t("bt.battery", n=bat) if isinstance(bat, (int, float)) else ""
            self._bt_list.addItem(f"{name}    {extra}".rstrip())

    def _on_bt_status(self, _enabled):
        self._refresh_bt_status_text()
        self._on_bt_devices(self.bluetooth_backend.connected_devices)

    def _on_bt_countdown(self, seconds):
        self._refresh_bt_status_text(seconds)

    def _on_music(self, info):
        info = info or {}
        title = info.get("title")
        if not title:
            self._track.setText(self._t("music.noMusic"))
            self._artist.setText(self._t("music.noMusicHint"))
            self._music_state.setText(self._t("music.notPlaying"))
            self._cover.setPixmap(QPixmap())
            self._cover.setText("♪")
            return
        self._track.setText(title)
        self._artist.setText(info.get("artist") or self._t("music.unknownArtist"))
        playing = bool(info.get("playing"))
        self._music_state.setText(
            self._t("music.playing") if playing else self._t("music.notPlaying"))
        thumb = info.get("thumbnail")
        if thumb:
            import base64
            try:
                raw = base64.b64decode(thumb)
                pm = QPixmap()
                pm.loadFromData(raw)
                self._cover.setPixmap(
                    pm.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self._cover.setText("")
            except Exception:
                self._cover.setText("♪")
        else:
            self._cover.setText("♪")

    def _load_todos(self):
        self._todo_items = []
        try:
            if TODO_FILE.exists():
                data = json.loads(TODO_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self._todo_items = data
        except Exception:
            self._todo_items = []
        self._render_todos()

    def _save_todos(self):
        try:
            TODO_FILE.parent.mkdir(parents=True, exist_ok=True)
            TODO_FILE.write_text(
                json.dumps(self._todo_items, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as e:
            print(f"[Todo] 保存失败: {e}")
            return
        # 提醒调度器立即看到新的 remindAt，不用等下一个轮询周期
        try:
            from capsule_app.todo_backend import TodoReminderBackend
            TodoReminderBackend.instance().set_todos(self._todo_items)
        except Exception as e:
            print(f"[Todo] 提醒调度同步失败: {e}")

    def _set_todo_filter(self, name):
        self._todo_filter = name
        btn = self._todo_filter_btns.get(name)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
        self._render_todos()

    def _add_todo(self):
        text = self._todo_input.text().strip()
        if not text:
            return
        self._todo_items.append({
            "id": int(datetime.now().timestamp() * 1000),
            "text": text,
            "completed": False,
        })
        self._todo_input.clear()
        self._save_todos()
        self._render_todos()

    def _clear_done_todos(self):
        self._todo_items = [t for t in self._todo_items if not t.get("completed")]
        self._save_todos()
        self._render_todos()

    def _filtered_todos(self):
        if self._todo_filter == "active":
            return [t for t in self._todo_items if not t.get("completed")]
        if self._todo_filter == "done":
            return [t for t in self._todo_items if t.get("completed")]
        return list(self._todo_items)

    def _render_todos(self):
        for w in self._todo_row_widgets:
            # 先 hide 再 deleteLater：延迟销毁要等事件循环，中间这几帧旧行会
            # 以脱离布局的姿态继续绘制，切筛选/切语言时就会闪出残影行
            w.hide()
            self._todo_lay.removeWidget(w)
            w.deleteLater()
        self._todo_row_widgets = []
        self._todo_rows = {}

        items = self._filtered_todos()
        self._todo_empty.setVisible(not items)
        self._todo_clear.setEnabled(
            any(t.get("completed") for t in self._todo_items))
        for todo in items:
            card = self._make_todo_row(todo)
            # 插到尾部 stretch 之前，空态提示与留白的顺序才稳定
            self._todo_lay.insertWidget(self._todo_lay.count() - 1, card)
            self._todo_row_widgets.append(card)

    def _make_todo_row(self, todo):
        """待办行卡片：勾选 + 内容 + 提醒时间 + 提醒菜单 + 删除"""
        done = bool(todo.get("completed"))
        card = QFrame()
        card.setObjectName("convRow")
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(10)

        check = QCheckBox()
        check.setChecked(done)
        check.toggled.connect(lambda on, t=todo: self._set_todo_done(t, on))

        name = _ElidedLabel(str(todo.get("text") or ""), Qt.ElideRight)
        if done:
            font = name.font()
            font.setStrikeOut(True)
            name.setFont(font)
        name.setObjectName("convNameDone" if done else "convName")

        badge = QLabel(self._remind_badge_text(todo))
        badge.setObjectName("convStatus")

        remind = QPushButton(self._t("todo.remind"))
        remind.setObjectName("convBtn")
        remind.setMenu(self._build_remind_menu(todo))

        remove = QPushButton("×")
        remove.setObjectName("convRemove")
        remove.setFixedSize(26, 26)
        remove.setToolTip(self._t("todo.delete"))
        remove.clicked.connect(lambda _=False, t=todo: self._drop_todo(t))

        lay.addWidget(check)
        lay.addWidget(name, 1)
        lay.addWidget(badge)
        lay.addWidget(remind)
        lay.addWidget(remove)

        self._todo_rows[todo.get("id")] = {
            "todo": todo, "card": card, "name": name, "badge": badge}
        return card

    def _build_remind_menu(self, todo):
        """提醒菜单：三个常用预设 + 自定义时间 + 清除"""
        menu = QMenu(self)
        now = datetime.now()
        menu.addAction(
            self._t("todo.remindIn10"),
            lambda: self._set_remind(todo, int((now + timedelta(minutes=10))
                                               .timestamp() * 1000)))
        menu.addAction(
            self._t("todo.remindIn60"),
            lambda: self._set_remind(todo, int((now + timedelta(hours=1))
                                               .timestamp() * 1000)))
        tomorrow_9 = (now + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0)
        menu.addAction(
            self._t("todo.remindTomorrow"),
            lambda: self._set_remind(todo, int(tomorrow_9.timestamp() * 1000)))
        menu.addSeparator()
        menu.addAction(self._t("todo.remindCustom"),
                       lambda: self._pick_remind_datetime(todo))
        clear = menu.addAction(self._t("todo.remindClear"),
                               lambda: self._set_remind(todo, None))
        clear.setEnabled(bool(todo.get("remindAt")))
        return menu

    def _remind_badge_text(self, todo):
        """徽标文案：当天只显示时分，其它日期带月日，已过点显示「已提醒」"""
        ts = todo.get("remindAt")
        if not ts:
            return ""
        try:
            dt = datetime.fromtimestamp(int(ts) / 1000)
        except (TypeError, ValueError, OSError):
            return ""
        if dt <= datetime.now():
            return self._t("todo.reminded")
        if dt.date() == datetime.now().date():
            return dt.strftime("%H:%M")
        return dt.strftime("%m-%d %H:%M")

    def _set_remind(self, todo, ts):
        todo["remindAt"] = int(ts) if ts else None
        self._save_todos()
        # 菜单动作回调里不能同步重建行（会删掉正在派发消息的按钮/菜单）
        QTimer.singleShot(0, self._render_todos)

    def _pick_remind_datetime(self, todo):
        dlg = QDialog(self)
        dlg.setWindowTitle(self._t("todo.remindCustom"))
        lay = QVBoxLayout(dlg)
        edit = QDateTimeEdit()
        edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        edit.setCalendarPopup(True)
        edit.setMinimumDateTime(QDateTime.currentDateTime())
        cur = todo.get("remindAt")
        base = (datetime.fromtimestamp(int(cur) / 1000) if cur
                else datetime.now() + timedelta(minutes=30))
        edit.setDateTime(QDateTime(base.year, base.month, base.day,
                                   base.hour, base.minute))
        lay.addWidget(edit)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        lay.addWidget(box)
        if dlg.exec() != QDialog.Accepted:
            return
        self._set_remind(todo, edit.dateTime().toMSecsSinceEpoch())

    def _set_todo_done(self, todo, on):
        todo["completed"] = bool(on)
        self._save_todos()
        # 行不再属于当前筛选：延迟整表重建，勾选框还在派发消息时不能删自己
        matches = (self._todo_filter == "all"
                   or (self._todo_filter == "done") == bool(on))
        if not matches:
            QTimer.singleShot(0, self._render_todos)
            return
        refs = self._todo_rows.get(todo.get("id"))
        if refs is not None:
            self._apply_todo_row_state(refs, bool(on))
        self._todo_clear.setEnabled(
            any(t.get("completed") for t in self._todo_items))

    def _apply_todo_row_state(self, refs, done):
        """就地切换一行的完成观感（置灰 + 删除线）"""
        name = refs["name"]
        name.setObjectName("convNameDone" if done else "convName")
        font = name.font()
        font.setStrikeOut(bool(done))
        name.setFont(font)
        style = name.style()
        style.unpolish(name)
        style.polish(name)
        refs["badge"].setText(self._remind_badge_text(refs["todo"]))

    def _drop_todo(self, todo):
        """删除单条待办（连同它的提醒时间一起消失）"""
        self._todo_items = [
            t for t in self._todo_items if t.get("id") != todo.get("id")]
        self._save_todos()
        QTimer.singleShot(0, self._render_todos)

    def _report_bug(self):
        threading.Thread(target=self._generate_bug_report, daemon=True).start()

    def _generate_bug_report(self):
        import platform
        import sys as _sys
        lines = [
            "LsletUI Bug 反馈日志",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"系统: {platform.platform()}",
            f"Python: {_sys.version}",
        ]
        try:
            s = self.settings_backend.get_settings()
            lines.append("设置: " + json.dumps(s, ensure_ascii=False))
        except Exception:
            pass
        log_file = Path.home() / ".pyisland_lite" / "logs" / "lsletui.log"
        if log_file.exists():
            try:
                content = log_file.read_text(encoding="utf-8", errors="replace")
                lines.append("--- 最近日志 ---")
                lines.extend(content.splitlines()[-400:])
            except Exception as e:
                lines.append(f"读取日志失败: {e}")
        report = "\n".join(lines)
        error = None
        path = None
        try:
            download_dir = Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads"
            download_dir.mkdir(parents=True, exist_ok=True)
            path = download_dir / f"lsletui_bug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            path.write_text(report, encoding="utf-8")
        except Exception as e:
            error = str(e)

        def notify():
            if path:
                QMessageBox.information(
                    self, self._t("about.bug"),
                    self._t("about.bug.saved", path=str(path)))
            else:
                QMessageBox.warning(
                    self, self._t("about.bug"),
                    self._t("about.bug.fail", err=error or "unknown"))

        QTimer.singleShot(0, notify)

    def show_with_animation(self, _origin=None):
        self.show()
        self.raise_()
        self.activateWindow()

    def shutdown(self):
        self._shutting_down = True
        if self._liquid_glass is not None:
            try:
                self._liquid_glass.shutdown()
            except Exception:
                pass
            self._liquid_glass = None
        try:
            self.bluetooth_backend.stop()
        except Exception:
            pass
        if self._owns_smtc:
            try:
                self.smtc_monitor.stop()
            except Exception:
                pass
        self.close()

    def closeEvent(self, event):
        if self._shutting_down:
            event.accept()
            return
        event.ignore()
        self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)
