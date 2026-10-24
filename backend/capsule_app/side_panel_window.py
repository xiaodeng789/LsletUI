#!/usr/bin/env python3
"""
LsletUI - 轻量级灵动岛应用
侧边栏面板组件
"""

import json
import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QPropertyAnimation, QEasingCurve, QPoint, QRect, QSize, QParallelAnimationGroup, QAbstractAnimation, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QGraphicsOpacityEffect, QToolButton

# 导入蓝牙后端
from capsule_app.bluetooth_backend import BluetoothBackend
# 导入进程监控后端
from capsule_app.process_monitor_backend import ProcessMonitorBackend
# 导入音乐播放器监控后端
from capsule_app.process_monitor_backend import MusicPlayerMonitorBackend
# 导入 SMTC 音乐监控后端
from capsule_app.smtc_monitor_backend import SMTCMonitorBackend
from capsule_app.settings_backend import SettingsBackend
from capsule_app.converter_backend import FormatConverter

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
MAX_IMAGE_SIZE_BYTES = 50 * 1024 * 1024


class CustomWebEnginePage(QWebEnginePage):
    """自定义 WebEnginePage，用于拦截前端的自定义协议请求，实现极简通信。"""
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.window = parent

    def javaScriptConsoleMessage(self, level, message, line, source):
        """重写控制台消息处理，捕获前端命令并过滤不必要的日志"""
        print(f"[WebEngine] 收到控制台消息: {message[:100]}")
        # 捕获 PYISLAND_CMD 命令
        if message.startswith('[PYISLAND_CMD]'):
            command = message.replace('[PYISLAND_CMD]', '').strip()
            print(f"[SidePanelWidget] 收到命令: {command}")
            if self.window:
                self.window._handle_console_command(command)
            return
        # 只显示错误和警告
        if level in (QWebEnginePage.ErrorMessageLevel, QWebEnginePage.WarningMessageLevel):
            print(f"[WebEngine] {level}: {message} (line {line})")


class SidePanelWebView(QWebEngineView):
    """自定义 WebEngineView，支持文件拖放。"""
    def __init__(self, on_file_drop=None, parent=None):
        super().__init__(parent)
        self._on_file_drop = on_file_drop
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        
        file_paths = []
        for url in urls:
            if url.isLocalFile():
                file_paths.append(url.toLocalFile())
        
        if file_paths and self._on_file_drop:
            self._on_file_drop(file_paths)
        
        event.acceptProposedAction()


class SidePanelWidget(QMainWindow):
    """侧边栏面板组件（iPhone 灵动岛风格）"""

    # 前端"高级设置"按钮请求打开独立设置窗口
    open_settings_requested = Signal()

    def __init__(self, parent=None, smtc=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("LsletUI - 侧边栏")
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 注意：不能设置 WA_ShowWithoutActivating——未激活窗口中的
        # Qt WebEngine(Chromium) 不会绘制合成层，会导致面板内容区黑屏。
        # "点胶囊第一下只激活窗口"的问题由胶囊侧的切换防抖 + 面板叉号按钮解决。

        # 外部传入的共享 SMTC 实例（来自胶囊窗口），避免重复轮询
        self._external_smtc = smtc
        self._owns_smtc = smtc is None
        # 外部传入的共享设置实例
        self._external_settings = settings
        self._owns_settings = settings is None

        # 存储目录
        self.storage_dir = Path.home() / ".pyisland_lite"
        self.storage_dir.mkdir(exist_ok=True)

        # 动画相关
        self._show_animation = None

        # 初始化UI
        self._init_ui()

        # 初始化后端
        self._init_backends()

    def _init_ui(self):
        """初始化UI"""
        print("[SidePanel] _init_ui 开始")
        try:
            # 主容器
            self.central_widget = QWidget()
            self.central_widget.setObjectName("panelRoot")
            self.central_widget.setStyleSheet("""
                #panelRoot {
                    background: rgba(10, 10, 12, 200);
                    border: 1px solid rgba(255, 255, 255, 20);
                    border-radius: 16px;
                }
            """)
            self.setCentralWidget(self.central_widget)
            print("[SidePanel] central_widget 创建完成")

            # 主布局
            layout = QVBoxLayout(self.central_widget)
            layout.setContentsMargins(8, 8, 8, 8)
            print("[SidePanel] layout 创建完成")

            # 初始化 WebEngineView
            print("[SidePanel] 开始创建 WebEngineView")
            self.web_view = SidePanelWebView(self._handle_native_file_drop, self)
            print("[SidePanel] SidePanelWebView 创建完成")
            profile_dir = self.storage_dir / "webengine_profile"
            cache_dir = profile_dir / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)

            print("[SidePanel] 使用默认 QWebEngineProfile")
            # 使用默认profile而非创建新的，避免Chromium初始化崩溃
            self.web_profile = QWebEngineProfile.defaultProfile()
            print("[SidePanel] 默认 QWebEngineProfile 获取成功")
            # 使用内存存储而非磁盘，避免文件锁和GPU缓存问题
            print("[SidePanel] 设置 NoPersistentCookies")
            self.web_profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
            print("[SidePanel] QWebEngineProfile 配置完成（内存模式）")

            # 使用自定义的 Page 类
            print("[SidePanel] 创建 CustomWebEnginePage")
            self.web_page = CustomWebEnginePage(self.web_profile, self)
            self.web_view.setPage(self.web_page)
            print("[SidePanel] setPage 完成")
            self.web_view.setAttribute(Qt.WA_TranslucentBackground)
            self.web_view.setContextMenuPolicy(Qt.NoContextMenu)
            print("[SidePanel] 配置 WebEngine 属性")
            self._configure_webengine_for_low_memory(QWebEngineProfile, QWebEngineSettings)
            self.web_view.page().setBackgroundColor(QColor(0, 0, 0, 0))
            print("[SidePanel] 添加到 layout")
            layout.addWidget(self.web_view)
            self.web_view.resize(self.size())

            print("[SidePanel] 连接信号并加载页面")
            self.web_view.loadFinished.connect(self._on_web_view_load_finished)
            self.web_view.load(QUrl.fromLocalFile(str(FRONTEND_DIST_INDEX)))
            print(f"[SidePanelWidget] 使用本地持久化目录：{profile_dir}")

            # 右上角关闭按钮（原生控件浮在 WebView 之上，保证点击一定生效）
            print("[SidePanel] 创建关闭按钮")
            self._close_btn = self._create_close_button()
            print("[SidePanel] _init_ui 完成")
        except Exception as e:
            import traceback
            print(f"[SidePanel] _init_ui 失败: {e}")
            traceback.print_exc()
            # 降级方案：创建一个简单的错误提示界面
            if not hasattr(self, 'central_widget') or self.central_widget is None:
                self.central_widget = QWidget()
                self.setCentralWidget(self.central_widget)
            layout = QVBoxLayout(self.central_widget)
            from PySide6.QtWidgets import QLabel
            error_label = QLabel(f"侧边栏初始化失败:\n{e}\n\n请重启应用")
            error_label.setStyleSheet("color: white; padding: 20px;")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)

    def _create_close_button(self):
        """创建右上角叉号关闭按钮"""
        btn = QToolButton(self.central_widget)
        btn.setObjectName("panelCloseBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip("关闭")

        # 用叉号 SVG 生成白色图标（2x 渲染保证清晰）
        icon = self._build_close_icon()
        if icon is not None:
            btn.setIcon(icon)
            btn.setIconSize(QSize(16, 16))

        btn.setStyleSheet("""
            QToolButton#panelCloseBtn {
                background: rgba(255, 255, 255, 0.12);
                border: none;
                border-radius: 15px;
            }
            QToolButton#panelCloseBtn:hover {
                background: rgba(255, 255, 255, 0.24);
            }
            QToolButton#panelCloseBtn:pressed {
                background: rgba(255, 255, 255, 0.30);
            }
        """)
        btn.setFixedSize(30, 30)
        btn.clicked.connect(self.hide)
        btn.raise_()
        btn.show()
        return btn

    def _build_close_icon(self):
        """读取 backend/img/叉号.svg 并染成白色，返回 QIcon"""
        try:
            from PySide6.QtSvg import QSvgRenderer
            svg_path = _BACKEND_ROOT / "img" / "叉号.svg"
            xml = svg_path.read_text(encoding="utf-8").replace("currentColor", "#FFFFFF")
            renderer = QSvgRenderer(xml.encode("utf-8"))
            if not renderer.isValid():
                return None
            import sys
            dpr = max(1.0, float(self.devicePixelRatioF()))
            size = int(18 * dpr)
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            painter = QPainter(pm)
            renderer.render(painter)
            painter.end()
            pm.setDevicePixelRatio(dpr)
            return QIcon(pm)
        except Exception as e:
            print(f"[SidePanelWidget] 加载叉号图标失败: {e}")
            return None

    def resizeEvent(self, event):
        """窗口尺寸变化时把关闭按钮固定在右上角"""
        super().resizeEvent(event)
        if getattr(self, "_close_btn", None) is not None:
            self._close_btn.move(self.width() - self._close_btn.width() - 14, 12)

    def keyPressEvent(self, event):
        """按 Esc 关闭面板"""
        if event.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)
        
    def _init_backends(self):
        """初始化后端模块"""
        # 初始化蓝牙后端
        self.bluetooth_backend = BluetoothBackend()
        # 初始化进程监控后端
        self.process_monitor = ProcessMonitorBackend()
        # 初始化音乐播放器监控后端
        self.music_monitor = MusicPlayerMonitorBackend()
        # 初始化/复用 SMTC 音乐监控后端
        if self._external_smtc is not None:
            self.smtc_monitor = self._external_smtc
        else:
            self.smtc_monitor = SMTCMonitorBackend()

        # 初始化/复用设置后端
        if self._external_settings is not None:
            self.settings_backend = self._external_settings
        else:
            self.settings_backend = SettingsBackend()

        # 格式转换器（能力检测 + 异步转换）
        self.converter = FormatConverter()

        # 设置web_view引用
        self.bluetooth_backend.set_web_view(self.web_view)
        self.process_monitor.set_web_view(self.web_view)
        self.music_monitor.set_web_view(self.web_view)
        self.smtc_monitor.set_web_view(self.web_view)
        self.settings_backend.set_web_view(self.web_view)

        # 连接 SMTC 前端推送
        self.smtc_monitor.connect_frontend_callback()

        # 注册前端调用的媒体控制接口
        self._setup_media_command_bridge()

    def _setup_media_command_bridge(self):
        """让前端 JS 可以通过 console.log('[PYISLAND_CMD]', command) 发送媒体控制命令"""
        # CustomWebEnginePage.javaScriptConsoleMessage 会捕获并转发到 _handle_console_command
        pass

    def _handle_console_command(self, command):
        """处理前端通过 console.log 发送的命令"""
        print(f"[SidePanelWidget] _handle_console_command: {command}")
        if command in ("playpause", "next", "prev"):
            print(f"[SidePanelWidget] 收到前端媒体命令: {command}")
            self.smtc_monitor.handle_command(command)
            return

        # 打开高级设置独立窗口（"高级设置"按钮）
        if command == "open:settings":
            self.open_settings_requested.emit()
            return

        # 打开外部链接（"帮助"按钮等）：open:url:<url>
        if command.startswith("open:url:"):
            url = command[len("open:url:"):].strip()
            if url:
                print(f"[SidePanelWidget] 打开外部链接: {url}")
                QDesktopServices.openUrl(QUrl(url))
            return

        # 设置相关命令：settings:get / settings:set:<key>:<value>
        if command == "settings:get":
            self.settings_backend.push_to_frontend()
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
                result = self.settings_backend.set_setting(key, value)
                if result is None:
                    print(f"[SidePanelWidget] 非法设置项: {key}={raw}")
            return

        # 生成Bug反馈日志
        if command == "bug:report":
            import threading
            threading.Thread(target=self._generate_bug_report, daemon=True).start()
            return

        # --- 格式转换器 ---
        # 能力表（Pillow/ffmpeg/Office 检测结果，前端决定下拉可用性）
        if command == "convert:caps":
            self._push_convert_caps()
            return
        # 原生文件选择对话框（绕开 Chromium file input 拿不到路径的限制）
        if command == "convert:pick":
            self._pick_convert_files()
            return
        # 批量转换：convert:start:{json}，json = [{id, path, target}, ...]
        if command.startswith("convert:start:"):
            try:
                items = json.loads(command[len("convert:start:"):])
            except (ValueError, TypeError):
                return
            if isinstance(items, list) and items:
                self._start_conversions(items)
            return
        # 打开/定位转换结果：路径含冒号，用前缀切片而非 split
        for action in ("open", "reveal"):
            prefix = f"convert:{action}:"
            if command.startswith(prefix):
                path = command[len(prefix):].strip()
                self._handle_convert_action(action, path)
                return

    def _handle_convert_action(self, action, path):
        """打开/在资源管理器中定位转换产物"""
        if not path or not Path(path).is_file():
            return
        if action == "open":
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            import subprocess
            subprocess.Popen(["explorer", "/select,", path])

    def _push_convert_caps(self):
        """把能力表推给前端"""
        self._run_frontend_js(
            "window.handleConvertCaps && window.handleConvertCaps("
            f"{json.dumps(self.converter.caps())});")

    def _pick_convert_files(self):
        """原生多选文件对话框，选中后走与拖放相同的推送链路"""
        from PySide6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择要转换的文件", str(Path.home()))
        if paths:
            self._handle_native_file_drop(paths)

    def _handle_native_file_drop(self, file_paths):
        """原生文件拖放/选择 → 格式转换列表"""
        if not file_paths:
            return
        payload = []
        for p in file_paths:
            try:
                fp = Path(p)
                if fp.is_file():
                    payload.append({"path": str(fp), "name": fp.name,
                                    "size": fp.stat().st_size})
            except OSError:
                continue
        if not payload:
            return
        self._run_frontend_js(
            f"window.handleConvertPicked && window.handleConvertPicked("
            f"{json.dumps(payload, ensure_ascii=True)});")

    def _start_conversions(self, items):
        """启动批量转换；结果逐项经 GUI 线程推回前端"""
        clean = []
        for it in items:
            try:
                clean.append({"id": str(it["id"]),
                              "path": str(it["path"]),
                              "target": str(it["target"])})
            except (KeyError, TypeError):
                continue
        if not clean:
            return

        def on_result(result):
            # worker 线程回调：投递回 GUI 线程再 runJavaScript
            QTimer.singleShot(0, lambda: self._on_convert_result(result))

        self.converter.convert_batch(clean, on_result)

    def _on_convert_result(self, result):
        """单项转换完成（GUI 线程）：推送结果给前端"""
        self._run_frontend_js(
            "window.handleConvertResult && window.handleConvertResult("
            f"{json.dumps(result, ensure_ascii=True)});")

    def _run_frontend_js(self, js):
        if self.web_view and self.web_view.page():
            self.web_view.page().runJavaScript(js)

    def _generate_bug_report(self):
        """收集系统诊断信息，生成Bug日志并保存到下载目录"""
        import platform
        import sys
        import threading
        import subprocess
        import shutil
        from datetime import datetime

        lines = []
        sep = "=" * 70
        lines.append(sep)
        lines.append("  LsletUI Bug 反馈日志")
        lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(sep)

        # ── 1. 系统信息 ──
        lines.append("\n" + sep)
        lines.append("[1/12] 系统信息")
        lines.append(sep)
        lines.append(f"操作系统: {platform.system()} {platform.release()} {platform.version()}")
        lines.append(f"架构: {platform.machine()}")
        lines.append(f"处理器: {platform.processor() or 'N/A'}")
        lines.append(f"主机名: {platform.node()}")
        try:
            import ctypes
            free_bytes = ctypes.c_ulonglong(0)
            _kernel32 = ctypes.WinDLL("kernel32")
            free_bytes = ctypes.c_ulonglong(0)
            _kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p("C:\\"), None, None, ctypes.pointer(free_bytes))
            total_gb = shutil.disk_usage("C:\\").total / (1024**3)
            free_gb = free_bytes.value / (1024**3)
            lines.append(f"磁盘 C: 总计 {total_gb:.1f} GB, 可用 {free_gb:.1f} GB")
        except Exception as e:
            lines.append(f"磁盘信息获取失败: {e}")
        try:
            import psutil
            mem = psutil.virtual_memory()
            lines.append(f"内存: 总计 {mem.total / 1024**3:.1f} GB, 可用 {mem.available / 1024**3:.1f} GB, 使用率 {mem.percent}%")
        except ImportError:
            lines.append("内存信息: psutil 未安装，跳过")

        # ── 2. Python / Qt 环境 ──
        lines.append("\n" + sep)
        lines.append("[2/12] Python / Qt 环境")
        lines.append(sep)
        lines.append(f"Python: {sys.version}")
        lines.append(f"Python 路径: {sys.executable}")
        lines.append(f"PySide6: {__import__('PySide6').__version__}")
        app = QApplication.instance()
        lines.append(f"Qt 版本: {app and app.applicationVersion() or 'N/A'}")
        lines.append(f"Qt 库版本: {__import__('PySide6.QtCore', fromlist=['QtCore']).qVersion()}")
        lines.append(f"冻结模式(Nuitka/PyInstaller): {getattr(sys, 'frozen', False)}")
        if getattr(sys, 'frozen', False):
            lines.append(f"打包工具: {'Nuitka' if '__compiled__' in globals() else 'PyInstaller'}")

        # ── 3. 应用路径 ──
        lines.append("\n" + sep)
        lines.append("[3/12] 应用路径")
        lines.append(sep)
        lines.append(f"工作目录: {os.getcwd()}")
        lines.append(f"sys.path: {sys.path[:5]}")
        try:
            from resource_path import get_base_path, get_frontend_path, get_config_path
            lines.append(f"资源根目录: {get_base_path()}")
            lines.append(f"前端目录: {get_frontend_path()}")
            lines.append(f"配置文件: {get_config_path()}")
        except Exception as e:
            lines.append(f"路径获取失败: {e}")
        lines.append(f"存储目录: {Path.home() / '.pyisland_lite'}")
        lines.append(f"日志文件: {Path.home() / '.pyisland_lite' / 'logs' / 'lsletui.log'}")

        # ── 4. 存储目录内容 ──
        lines.append("\n" + sep)
        lines.append("[4/12] 存储目录 (~/.pyisland_lite)")
        lines.append(sep)
        storage = Path.home() / ".pyisland_lite"
        if storage.exists():
            for item in sorted(storage.rglob("*")):
                if item.is_file():
                    size = item.stat().st_size
                    size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
                    rel = item.relative_to(storage)
                    lines.append(f"  {rel}  ({size_str})")
        else:
            lines.append("  (目录不存在)")

        # ── 5. 蓝牙状态 ──
        lines.append("\n" + sep)
        lines.append("[5/12] 蓝牙状态")
        lines.append(sep)
        bt = self.bluetooth_backend
        lines.append(f"蓝牙开关: {'开启' if bt.bt_enabled else '关闭' if bt.bt_enabled is False else '未知'}")
        lines.append(f"扫描中: {bt.scanning}")
        lines.append(f"倒计时剩余: {bt._countdown_remaining}s")
        lines.append(f"已连接设备数: {len(bt.connected_devices)}")
        for d in bt.connected_devices:
            lines.append(f"  - {d.get('name', '未知')} | ID: {d.get('id', '')} | 电量: {d.get('battery', 'N/A')}")
        if not bt.connected_devices:
            lines.append("  (无已连接设备)")

        # ── 6. 进程监控状态 ──
        lines.append("\n" + sep)
        lines.append("[6/12] 进程监控 (eIsland)")
        lines.append(sep)
        pm = self.process_monitor
        lines.append(f"eIsland 运行中: {pm.is_eisland_running}")
        lines.append(f"扫描中: {pm.scanning}")

        # ── 7. 音乐播放器状态 ──
        lines.append("\n" + sep)
        lines.append("[7/12] 音乐播放器监控")
        lines.append(sep)
        mm = self.music_monitor
        lines.append(f"扫描中: {mm.scanning}")
        lines.append(f"检测到的播放器: {len(mm.player_status)} 个")
        for name, status in mm.player_status.items():
            lines.append(f"  - {name}: {status}")
        if not mm.player_status:
            lines.append("  (未检测到播放器)")

        # ── 8. SMTC 音乐信息 ──
        lines.append("\n" + sep)
        lines.append("[8/12] SMTC 系统媒体控制")
        lines.append(sep)
        smtc = self.smtc_monitor
        last_info = smtc.get_last_info() if hasattr(smtc, 'get_last_info') else None
        if last_info:
            for k, v in last_info.items():
                lines.append(f"  {k}: {v}")
        else:
            lines.append("  (无媒体播放信息)")
        lines.append(f"扫描中: {getattr(smtc, '_scanning', 'N/A')}")

        # ─ 9. 设置状态 ──
        lines.append("\n" + sep)
        lines.append("[9/12] 应用设置")
        lines.append(sep)
        sb = self.settings_backend
        if hasattr(sb, '_settings'):
            for k, v in sb._settings.items():
                lines.append(f"  {k}: {v}")
        else:
            lines.append("  (无法读取设置)")

        # ── 10. 线程信息 ──
        lines.append("\n" + sep)
        lines.append("[10/12] 线程信息")
        lines.append(sep)
        lines.append(f"活跃线程数: {threading.active_count()}")
        for t in threading.enumerate():
            lines.append(f"  - [{t.ident}] {t.name} (daemon={t.daemon}, alive={t.is_alive()})")

        # ── 11. 网络信息 ──
        lines.append("\n" + sep)
        lines.append("[11/12] 网络信息")
        lines.append(sep)
        try:
            import socket
            hostname = socket.gethostname()
            lines.append(f"主机名: {hostname}")
            try:
                ips = socket.getaddrinfo(hostname, None)
                unique_ips = set()
                for ip_info in ips:
                    ip = ip_info[4][0]
                    if ip not in unique_ips and not ip.startswith('127.'):
                        unique_ips.add(ip)
                        lines.append(f"IP 地址: {ip}")
            except Exception:
                pass
        except Exception as e:
            lines.append(f"网络信息获取失败: {e}")
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            result = subprocess.run(
                ["ping", "-n", "1", "8.8.8.8"],
                capture_output=True, timeout=5, startupinfo=si
            )
            lines.append(f"外网连通性 (8.8.8.8): {'正常' if result.returncode == 0 else '不通'}")
        except Exception as e:
            lines.append(f"外网连通性检测失败: {e}")

        # ── 12. 最近日志 ──
        lines.append("\n" + sep)
        lines.append("[12/12] 最近日志 (最后 500 行)")
        lines.append(sep)
        log_file = Path.home() / ".pyisland_lite" / "logs" / "lsletui.log"
        if log_file.exists():
            try:
                content = log_file.read_text(encoding="utf-8", errors="replace")
                all_lines = content.splitlines()
                lines.append(f"(日志文件共 {len(all_lines)} 行，显示最后 500 行)")
                lines.append("---")
                lines.extend(all_lines[-500:])
            except Exception as e:
                lines.append(f"读取日志失败: {e}")
        else:
            lines.append("(未找到日志文件，日志仅输出到控制台)")

        lines.append("\n" + sep)
        lines.append("  日志结束")
        lines.append(sep)

        report = "\n".join(lines)

        # 保存到下载目录
        try:
            download_dir = Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads"
            download_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = download_dir / f"lsletui_bug_{timestamp}.txt"
            report_path.write_text(report, encoding="utf-8")
            print(f"[BugReport] 日志已保存: {report_path}")

            result_path = str(report_path)
        except Exception as e:
            print(f"[BugReport] 保存日志失败: {e}")
            result_path = None
            self._bug_error = str(e)

        # 回到主线程通知前端
        def _notify():
            if self.web_view and self.web_view.page():
                if result_path:
                    js = f'window.handleBugReportResult && window.handleBugReportResult({json.dumps(result_path, ensure_ascii=True)});'
                else:
                    js = f'window.handleBugReportResult && window.handleBugReportResult(null, {json.dumps(getattr(self, "_bug_error", "未知错误"), ensure_ascii=True)});'
                self.web_view.page().runJavaScript(js)
        QTimer.singleShot(0, _notify)
        
    def _configure_webengine_for_low_memory(self, profile_cls, settings_cls):
        """关闭当前侧边栏不需要的 WebEngine 功能，降低资源占用并提高稳定性。"""
        if self.web_view is None:
            return

        page = self.web_view.page()
        profile = page.profile()
        profile.setHttpCacheType(profile_cls.NoCache)
        profile.setHttpCacheMaximumSize(0)
        profile.setPersistentCookiesPolicy(profile_cls.NoPersistentCookies)

        settings = self.web_view.settings()

        def set_attr(name, value):
            attr = getattr(settings_cls, name, None)
            if attr is not None:
                settings.setAttribute(attr, value)

        set_attr("LocalStorageEnabled", True)
        set_attr("LocalContentCanAccessFileUrls", True)
        set_attr("LocalContentCanAccessRemoteUrls", True)
        set_attr("PluginsEnabled", False)
        set_attr("FullScreenSupportEnabled", False)
        set_attr("PdfViewerEnabled", False)
        set_attr("DnsPrefetchEnabled", False)
        set_attr("JavascriptCanOpenWindows", False)
        set_attr("JavascriptCanAccessClipboard", False)
        set_attr("JavascriptCanPaste", False)
        set_attr("HyperlinkAuditingEnabled", False)
        set_attr("ScrollAnimatorEnabled", False)
        # 稳定性：禁用可能导致崩溃的功能
        set_attr("WebGLEnabled", False)
        set_attr("Accelerated2dCanvasEnabled", False)

    def showEvent(self, event):
        """窗口每次显示时重播前端入场动画。"""
        super().showEvent(event)
        QTimer.singleShot(0, self._play_frontend_entrance_animation)

    def hideEvent(self, event):
        """窗口隐藏后，让前端进入下一次入场动画的准备状态。"""
        super().hideEvent(event)
        QTimer.singleShot(0, self._prepare_frontend_entrance_animation)

    def show_with_animation(self, origin_point: QPoint):
        """显示动画（淡入 + 轻微上移）

        注意：不要使用 geometry 动画从小尺寸展开——WebEngine 渲染器
        在极小窗口尺寸下初始化会直接失败，导致前端加载失败。
        """
        # 停止旧动画（DeleteWhenStopped 会在停止后删除 C++ 对象，
        # 通过 destroyed 信号清空引用，避免下次打开时操作已删除对象崩溃）
        if self._show_animation is not None:
            self._show_animation.stop()
            self._show_animation = None

        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()

        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(240)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.destroyed.connect(lambda *_: setattr(self, '_show_animation', None))
        anim.start(QAbstractAnimation.DeleteWhenStopped)
        self._show_animation = anim

    def _play_frontend_entrance_animation(self):
        """播放前端入场动画（直接操作 class，不依赖 window 函数是否已定义）"""
        if self.web_view and self.web_view.page():
            self.web_view.page().runJavaScript(
                "document.documentElement.classList.remove('panel-hidden');"
                "document.documentElement.classList.add('panel-visible');"
            )

    def _prepare_frontend_entrance_animation(self):
        """准备前端入场动画（下次显示时重新播放）"""
        if self.web_view and self.web_view.page():
            self.web_view.page().runJavaScript(
                "document.documentElement.classList.add('panel-hidden');"
                "document.documentElement.classList.remove('panel-visible');"
            )

    def _on_web_view_load_finished(self, ok):
        """WebEngineView 加载完成后的回调。"""
        if not ok:
            print("[SidePanelWidget] 前端加载失败，尝试重新加载")
            self.web_view.load(QUrl.fromLocalFile(str(FRONTEND_DIST_INDEX)))
            return

        print("[SidePanelWidget] 前端加载完成")
        # 页面加载完成后强制确保内容可见（修复首次打开时 showEvent 的
        # 播放入场动画调用早于页面加载、被丢弃导致的永久黑屏）
        if self.isVisible():
            self._play_frontend_entrance_animation()
        # 立即补推当前音乐信息
        # （否则首次推送可能发生在 JS 注册回调之前，导致面板一直显示"暂无播放"）
        info = self.smtc_monitor.get_last_info()
        if info:
            self.smtc_monitor._push_to_frontend(info)
        # 同理补推当前设置
        self.settings_backend.push_to_frontend()

    def closeEvent(self, event):
        """关闭事件处理"""
        # 先停止后端任务
        if hasattr(self, 'bluetooth_backend'):
            self.bluetooth_backend.stop()
        if hasattr(self, 'process_monitor'):
            self.process_monitor.stop()
        if hasattr(self, 'music_monitor'):
            self.music_monitor.stop()
        if hasattr(self, 'smtc_monitor') and self._owns_smtc:
            self.smtc_monitor.stop()
        if hasattr(self, 'settings_backend'):
            self.settings_backend.stop()

        # 安全销毁 WebEngine：先停止加载、断开信号、清空页面，
        # 避免 Chromium 渲染进程在销毁中访问已释放内存 → Qt6WebEngineCore.dll 0xC0000005
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