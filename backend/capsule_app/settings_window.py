#!/usr/bin/env python3
"""LsletUI - 高级设置独立窗口

点击侧边栏"高级设置"按钮时弹出，加载前端 ?view=settings 视图。
与侧边栏共享同一 SettingsBackend 实例，设置变更双向同步。
"""
from pathlib import Path
import tempfile

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

# 导入资源路径兼容模块
import sys
if not getattr(sys, 'frozen', False):
    # 开发模式
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from resource_path import get_resource_path, get_frontend_path

# backend 目录：源码运行时即 backend/，打包后即 exe 所在目录
_BACKEND_ROOT = get_resource_path("")
# 前端资源路径（兼容打包模式）
FRONTEND_DIST_INDEX = get_frontend_path() / "index.html"


class _SettingsWebPage(QWebEnginePage):
    """捕获前端通过 console.log 发送的 PYISLAND_CMD 命令。"""

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.window = parent

    def javaScriptConsoleMessage(self, level, message, line, source):
        if message.startswith("[PYISLAND_CMD]"):
            command = message.replace("[PYISLAND_CMD]", "").strip()
            if self.window:
                self.window._handle_command(command)
            return
        if level in (QWebEnginePage.ErrorMessageLevel, QWebEnginePage.WarningMessageLevel):
            print(f"[SettingsWindow] {level}: {message} (line {line})")


class SettingsWindow(QMainWindow):
    """高级设置独立窗口（WebEngine 加载 ?view=settings）。"""

    def __init__(self, settings_backend, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LsletUI - 高级设置")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.resize(380, 600)

        self._settings_backend = settings_backend
        self.storage_dir = Path.home() / ".pyisland_lite"

        self._init_ui()
        self._center_on_screen()

    # --- UI ---
    def _init_ui(self):
        central = QWidget()
        central.setStyleSheet("background: #0a0a0c;")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central)

        # WebEngine
        self.web_view = QWebEngineView(self)
        self.web_view.setContextMenuPolicy(Qt.NoContextMenu)

        # 独立 Profile（缓存目录与侧边栏分开，避免锁定冲突）
        # ~/.pyisland_lite 不可写（沙箱）时回退到临时目录
        profile_dir = self.storage_dir / "webengine_profile_settings"
        try:
            profile_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            profile_dir = Path(tempfile.mkdtemp(prefix="pyisland_settings_"))
        self.web_profile = QWebEngineProfile("pyisland_lite_settings", self)
        self.web_profile.setPersistentStoragePath(str(profile_dir))
        self.web_profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)

        self.web_page = _SettingsWebPage(self.web_profile, self)
        self.web_view.setPage(self.web_page)
        self.web_view.page().setBackgroundColor(QColor(10, 10, 12, 255))
        layout.addWidget(self.web_view)

        # 关闭 WebEngine 不需要的功能，降低资源占用
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.PdfViewerEnabled, False)
        settings.setAttribute(QWebEngineSettings.PluginsEnabled, False)
        settings.setAttribute(QWebEngineSettings.DnsPrefetchEnabled, False)
        settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)

        # 加载前端 ?view=settings
        url = QUrl.fromLocalFile(str(FRONTEND_DIST_INDEX))
        url.setQuery("view=settings")
        self.web_view.load(url)
        self.web_view.loadFinished.connect(self._on_load_finished)

        # 注册 web_view 到设置后端（接收推送）
        self._settings_backend.set_web_view(self.web_view)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.center().x() - self.width() // 2
        y = geo.center().y() - self.height() // 2
        self.move(x, y)

    def _on_load_finished(self, ok):
        if ok:
            self._settings_backend.push_to_frontend()

    # --- 命令处理 ---
    def _handle_command(self, command):
        """处理前端命令：settings:get / settings:set:..."""
        if command == "settings:get":
            self._settings_backend.push_to_frontend()
            return

        if command.startswith("settings:set:"):
            parts = command.split(":", 3)
            # 形如 settings:set:autostart:true
            if len(parts) == 4:
                _, _, key, raw = parts
                if raw in ("true", "false"):
                    value = raw == "true"
                else:
                    try:
                        value = int(raw)
                    except ValueError:
                        value = raw
                self._settings_backend.set_setting(key, value)
            return

    # --- 清理 ---
    def closeEvent(self, event):
        """关闭时从设置后端注销 web_view，并安全销毁 WebEngine"""
        self._settings_backend.remove_web_view(self.web_view)
        # 安全销毁 WebEngine，释放 Chromium 渲染进程内存
        if hasattr(self, 'web_view') and self.web_view is not None:
            try:
                self.web_view.loadFinished.disconnect()
            except Exception:
                pass
            try:
                self.web_view.stop()
            except Exception:
                pass
            try:
                self.web_view.setPage(None)
            except Exception:
                pass
            self.web_view.deleteLater()
            self.web_view = None
        super().closeEvent(event)
