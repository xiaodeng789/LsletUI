#!/usr/bin/env python3
"""
PyIsland Lite - 剪贴板历史面板
点击灵动岛的剪贴板通知后弹出：查看历史、点击条目复制回贴、
链接一键打开、单条删除/清空。原生 Qt 实现，不依赖 Web 前端。
"""

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF, QUrl
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter,
                           QPainterPath, QPixmap, QDesktopServices)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget,
                               QFrame)

from capsule_app.clipboard_backend import normalize_url
from capsule_app.liquid_glass import setup_liquid_glass

# 导入资源路径兼容模块
import sys as _sys
if not getattr(_sys, 'frozen', False):
    # 开发模式
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from resource_path import get_resource_path

PROJECT_ROOT = get_resource_path("")
IMG_DIR = get_resource_path("img")

PANEL_WIDTH = 360
ROW_HEIGHT = 48
MAX_PANEL_HEIGHT = 460

KIND_LABEL = {"text": "文本", "url": "链接", "file": "文件", "image": "图片"}

ROW_BTN_STYLE = """
    QToolButton {
        background: rgba(255, 255, 255, 16);
        color: rgba(255, 255, 255, 200);
        border: none;
        border-radius: 12px;
        font-size: 11px;
    }
    QToolButton:hover { background: rgba(255, 255, 255, 32); }
    QToolButton:pressed { background: rgba(255, 255, 255, 46); }
"""

HEADER_BTN_STYLE = """
    QToolButton {
        background: rgba(255, 255, 255, 14);
        color: rgba(255, 255, 255, 210);
        border: none;
        border-radius: 13px;
        font-size: 11px;
    }
    QToolButton:hover { background: rgba(255, 255, 255, 30); }
    QToolButton:pressed { background: rgba(255, 255, 255, 44); }
"""


def _svg_pixmap(name, size):
    """读取 img/{name}.svg，染白后渲染为透明底 QPixmap"""
    try:
        from PySide6.QtSvg import QSvgRenderer
        svg_path = IMG_DIR / f"{name}.svg"
        xml = svg_path.read_text(encoding="utf-8").replace("currentColor", "#FFFFFF")
        renderer = QSvgRenderer(xml.encode("utf-8"))
        if not renderer.isValid():
            return None
        dpr = 2.0
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        renderer.render(painter)
        painter.end()
        pm.setDevicePixelRatio(dpr)
        return pm
    except Exception as e:
        print(f"[ClipboardPanel] 加载图标 {name} 失败: {e}")
        return None


def _fmt_ts(ts):
    """今天显示 HH:MM，否则 MM-DD HH:MM"""
    try:
        lt = time.localtime(ts)
        now = time.localtime()
        if (lt.tm_year, lt.tm_yday) == (now.tm_year, now.tm_yday):
            return time.strftime("%H:%M", lt)
        return time.strftime("%m-%d %H:%M", lt)
    except Exception:
        return ""


class ClipboardRow(QWidget):
    """单条历史记录：图标 + 预览/时间 +（链接）打开 + 删除；点整行复制回贴"""

    def __init__(self, entry, panel):
        super().__init__()
        self._entry = entry
        self._panel = panel
        self.setFixedHeight(ROW_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

        kind = entry.get("kind")
        is_url = kind == "url"
        btns_w = 74 if is_url else 26
        title_w = PANEL_WIDTH - 12 - 32 - 10 - btns_w - 10

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 10, 6)
        layout.setSpacing(10)

        # 左侧图标（图片显示缩略图，其余用 SVG 图标 + 圆形衬底）
        icon_label = QLabel()
        icon_label.setFixedSize(32, 32)
        icon_label.setAlignment(Qt.AlignCenter)
        if kind == "image" and entry.get("image") is not None:
            pm = QPixmap.fromImage(entry["image"]).scaled(
                32, 32, Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation)
            icon_label.setPixmap(pm)
        else:
            name = "复制" if kind in ("text", "url") else "剪贴板"
            icon_label.setPixmap(_svg_pixmap(name, 18) or QPixmap())
            icon_label.setStyleSheet(
                "background: rgba(255,255,255,26); border-radius: 16px;")
        layout.addWidget(icon_label)

        # 中间两行文字
        title_label = QLabel(self._elided(self._title_text(), title_w, True))
        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: rgba(255,255,255,235);"
                                  "background: transparent;")
        sub_label = QLabel(self._elided(self._sub_text(), title_w, False))
        sub_font = QFont()
        sub_font.setPointSize(8)
        sub_label.setFont(sub_font)
        sub_label.setStyleSheet("color: rgba(255,255,255,125);"
                                "background: transparent;")

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        text_col.addWidget(title_label)
        text_col.addWidget(sub_label)
        text_col.addStretch(1)
        layout.addLayout(text_col, 1)

        # 右侧按钮：链接多一个"打开"
        if is_url:
            open_btn = QToolButton()
            open_btn.setText("打开")
            open_btn.setFixedSize(44, 24)
            open_btn.setCursor(Qt.PointingHandCursor)
            open_btn.setStyleSheet(ROW_BTN_STYLE)
            open_btn.clicked.connect(self._open_link)
            layout.addWidget(open_btn)

        del_btn = QToolButton()
        del_btn.setText("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(ROW_BTN_STYLE)
        del_btn.clicked.connect(self._remove)
        layout.addWidget(del_btn)

    # --- 文案 ---
    def _title_text(self):
        kind = self._entry.get("kind")
        if kind in ("text", "url"):
            return (self._entry.get("text") or "").replace("\n", " ").strip()
        if kind == "file":
            paths = self._entry.get("paths") or []
            if len(paths) == 1:
                return Path(paths[0]).name
            return f"{len(paths)} 个文件"
        img = self._entry.get("image")
        if img is not None:
            return f"图片 {img.width()}×{img.height()}"
        return "图片"

    def _sub_text(self):
        kind = self._entry.get("kind")
        sub = KIND_LABEL.get(kind, "文本")
        sub += " · " + _fmt_ts(self._entry.get("ts", 0))
        return sub

    @staticmethod
    def _elided(text, width, bold):
        text = text or ""
        font = QFont()
        font.setPointSize(10 if bold else 8)
        font.setBold(bool(bold))
        fm = QFontMetrics(font)
        return fm.elidedText(text, Qt.ElideRight, int(width))

    # --- 交互 ---
    def paintEvent(self, event):
        """悬停时画一行浅色圆角背景"""
        if self.underMouse():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()).adjusted(2, 1, -2, -1),
                                10, 10)
            painter.fillPath(path, QColor(255, 255, 255, 18))
            painter.end()
        super().paintEvent(event)

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self._panel.copy_entry(self._entry)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _open_link(self):
        url = normalize_url(self._entry.get("text", ""))
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _remove(self):
        self._panel.delete_entry(self._entry)


class ClipboardPanelWidget(QMainWindow):
    """剪贴板历史面板（黑色圆角卡片，从胶囊下方弹出）"""

    def __init__(self, monitor, parent=None):
        super().__init__(parent)
        self.setWindowTitle("剪贴板历史")
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._monitor = monitor
        self._rows_layout = None
        self._status_label = None
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._hide_status)

        self._init_ui()

        # 液态玻璃背景（几何/显隐/设置跟随全自动；硬件不达标时返回 None）
        self._liquid_glass = None
        settings_backend = None
        try:
            from capsule_app.native_main_window import NativeMainWindow
            for w in QApplication.topLevelWidgets():
                if isinstance(w, NativeMainWindow):
                    settings_backend = w.settings_backend
                    break
        except Exception:
            pass
        if settings_backend is None:
            try:
                from capsule_app.settings_backend import SettingsBackend
                settings_backend = SettingsBackend()
            except Exception:
                pass
        if settings_backend is not None:
            self._liquid_glass = setup_liquid_glass(self, settings_backend)

        # 面板打开期间有新复制：实时刷新列表
        monitor.captured.connect(self._on_history_updated)
        self.refresh()

    # --- UI 构建 ---
    def _init_ui(self):
        central = QWidget()
        central.setObjectName("clipPanelRoot")
        central.setStyleSheet("""
            #clipPanelRoot {
                background: rgba(10, 10, 12, 218);
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 16px;
            }
        """)
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 8)
        root.setSpacing(4)

        # 头部：标题 + 清空 + 关闭
        header = QHBoxLayout()
        header.setContentsMargins(10, 8, 6, 2)
        header.setSpacing(8)

        icon_label = QLabel()
        icon_label.setPixmap(_svg_pixmap("剪贴板", 16) or QPixmap())
        icon_label.setStyleSheet("background: transparent;")
        header.addWidget(icon_label)

        title = QLabel("剪贴板历史")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: rgba(255,255,255,235);"
                            "background: transparent;")
        header.addWidget(title)

        header.addStretch(1)

        clear_btn = QToolButton()
        clear_btn.setText("清空")
        clear_btn.setFixedSize(40, 26)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(HEADER_BTN_STYLE)
        clear_btn.clicked.connect(self._clear_all)
        header.addWidget(clear_btn)

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(HEADER_BTN_STYLE)
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)

        root.addLayout(header)

        # 滚动列表
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 6px;
                                  margin: 2px; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,60);
                                          border-radius: 3px;
                                          min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                                          height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                                          background: transparent; }
        """)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(container)
        self._rows_layout.setContentsMargins(4, 2, 4, 2)
        self._rows_layout.setSpacing(2)
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        # 底部状态提示（复制成功/已清空）
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet(
            "color: rgb(48, 209, 88); font-size: 11px;"
            "background: transparent;")
        self._status_label.setFixedHeight(20)
        self._status_label.hide()
        root.addWidget(self._status_label)

    # --- 列表刷新 ---
    def refresh(self):
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        entries = self._monitor.history
        if not entries:
            empty = QLabel("暂无剪贴板记录\n复制内容后会出现在这里")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: rgba(255,255,255,110);"
                                "font-size: 11px; background: transparent;")
            empty.setFixedHeight(96)
            self._rows_layout.addWidget(empty)
        for entry in entries:
            self._rows_layout.addWidget(ClipboardRow(entry, self))
        self._rows_layout.addStretch(1)
        self._update_height()

    def _update_height(self):
        n = len(self._monitor.history)
        rows_h = (n * ROW_HEIGHT + max(0, n - 1) * 2 + 8) if n else 104
        total = 44 + 4 + rows_h + 26 + 8
        self.setFixedWidth(PANEL_WIDTH)
        self.setFixedHeight(int(min(MAX_PANEL_HEIGHT, total)))

    # --- 显示/隐藏 ---
    def prepare_show(self):
        """打开前刷新列表并按条目数调整高度"""
        self.refresh()

    def show_at(self, pos):
        self.move(pos)
        self.show()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def _on_history_updated(self, _info):
        if self.isVisible():
            self.refresh()

    # --- 条目操作 ---
    def copy_entry(self, entry):
        ok = self._monitor.copy_entry(entry)
        self._show_status("已复制到剪贴板" if ok else "复制失败")

    def delete_entry(self, entry):
        self._monitor.remove_entry(entry)
        self.refresh()

    def _clear_all(self):
        self._monitor.clear_history()
        self.refresh()
        self._show_status("已清空")

    # --- 状态提示 ---
    def _show_status(self, text):
        self._status_label.setText(text)
        self._status_label.show()
        self._status_timer.start(1600)

    def _hide_status(self):
        self._status_label.hide()
