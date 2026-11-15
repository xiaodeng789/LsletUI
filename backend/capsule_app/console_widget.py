#!/usr/bin/env python3
"""LsletUI - 日志控制台视图（可嵌入任意窗口的 QWidget）。

数据来自 log_bus 内存环形缓冲，QTimer 每 300ms 增量拉取，
不引入任何跨线程 Qt 信号。
"""

import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout, QLineEdit, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from capsule_app import log_bus
from capsule_app.native_ui import tr

LOG_DIR = Path.home() / ".pyisland_lite" / "logs"


class ConsoleWidget(QWidget):
    """日志查看页：过滤 / 暂停 / 自动滚动 / 复制 / 清空 / 打开终端。"""

    # 距底部多少像素以内算「贴底」，用于自动恢复跟随
    _BOTTOM_TOL = 6

    def __init__(self, parent=None, lang="zh"):
        super().__init__(parent)
        self._lang = lang
        self._last_seq = 0
        self._paused = False
        # 跟随被「上滚」自动挂起，而不是用户亲手关的开关；两者必须分开，
        # 否则用户主动关掉跟随后，滚回底部会被程序又打开。
        self._follow_suspended = False
        # 大于 0 表示当前滚动条变化由程序造成，不参与跟随判断
        self._scroll_guard = 0
        self._build()
        self.retranslate(self._lang)
        self._rerender()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(300)

    def _t(self, key, **kw):
        return tr(self._lang, key, **kw)

    def retranslate(self, lang):
        """语言切换后刷新本页所有可见文案（未知语言由 tr 回落中文）。"""
        self._lang = lang
        self._filter.setPlaceholderText(self._t("log.filter"))
        self._pause.setText(self._t("log.pause"))
        self._pause.setToolTip(self._t("log.pause.tip"))
        self._autoscroll.setText(self._t("log.autoscroll"))
        self._autoscroll.setToolTip(self._t("log.autoscroll.tip"))
        self._term_btn.setText(self._t("log.openTerminal"))
        self._term_btn.setToolTip(self._t("log.openTerminal.tip"))
        self._copy_btn.setText(self._t("log.copyAll"))
        self._clear_btn.setText(self._t("log.clear"))

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # --- 工具栏 ---
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self._filter = QLineEdit()
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._rerender)
        bar.addWidget(self._filter, 1)

        # 两个开关用可点击的胶囊按钮，和右侧动作按钮同规格；
        # 只接 clicked（用户意图），不接 toggled，程序改状态时不会误触发
        self._pause = QPushButton()
        self._pause.setObjectName("logToggle")
        self._pause.setCheckable(True)
        self._pause.clicked.connect(self._on_pause)
        bar.addWidget(self._pause)

        self._autoscroll = QPushButton()
        self._autoscroll.setObjectName("logToggle")
        self._autoscroll.setCheckable(True)
        self._autoscroll.setChecked(True)
        self._autoscroll.clicked.connect(self._on_autoscroll_clicked)
        bar.addWidget(self._autoscroll)

        self._term_btn = QPushButton()
        self._term_btn.clicked.connect(self._open_terminal)
        bar.addWidget(self._term_btn)

        self._copy_btn = QPushButton()
        self._copy_btn.clicked.connect(self._copy_all)
        bar.addWidget(self._copy_btn)

        self._clear_btn = QPushButton()
        self._clear_btn.clicked.connect(self._clear_view)
        bar.addWidget(self._clear_btn)

        lay.addLayout(bar)

        # --- 日志区 ---
        self._view = QPlainTextEdit()
        # 配色由 native_ui 的 _DARK_QSS / _LIGHT_QSS / *_GLASS_QSS 统一提供，
        # 与卡片、输入框共用同一套玻璃语言，避免这里各写一份数值
        self._view.setObjectName("logView")
        self._view.setReadOnly(True)
        self._view.setMaximumBlockCount(log_bus._MAX_LINES)
        # 透明/不透明由 _apply_theme() 按当前是否玻璃模式决定：
        # 非玻璃模式用不透明绘制避免高频日志触发整窗合成；玻璃模式必须
        # 允许 Alpha，否则日志区会变成一块实心色把折射层盖住。
        self._view.setAttribute(Qt.WA_StaticContents)
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.Monospace)
        self._view.setFont(font)
        self._view.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self._apply_theme()
        lay.addWidget(self._view, 1)

    def _apply_theme(self):
        """按当前是否玻璃模式切换日志区的绘制属性（配色见 native_ui QSS）。

        玻璃模式必须关掉 WA_OpaquePaintEvent，QSS 里的半透明底色才会生效；
        非玻璃模式反过来开着它，高频日志不会每帧触发整窗合成。
        """
        from capsule_app import native_ui
        glass = bool(getattr(native_ui, "_CURRENT_GLASS", False))
        self._view.setAttribute(Qt.WA_OpaquePaintEvent, not glass)

    # --- 行为 ---
    def _matches(self, text):
        f = self._filter.text().strip()
        return not f or f.lower() in text.lower()

    def _poll(self):
        if self._paused:
            return
        lines, newest = log_bus.snapshot_after(self._last_seq)
        if not lines:
            return
        self._last_seq = newest
        shown = [t for t in lines if self._matches(t)]
        if shown:
            self._append("\n".join(shown))

    def _append(self, text):
        """追加一批日志行：跟随后贴底，未跟随后把阅读位置钉死不动。"""
        sb = self._view.verticalScrollBar()
        keep = None if self._autoscroll.isChecked() else sb.value()
        self._scroll_guard += 1
        try:
            self._view.appendPlainText(text)
            # appendPlainText 会自己把视口滚到末尾，未跟随时按原值顶回去
            sb.setValue(sb.maximum() if keep is None else keep)
        finally:
            self._scroll_guard -= 1

    def _rerender(self):
        history, newest = log_bus.full_history()
        self._last_seq = newest
        if self._follow_suspended:
            # 整屏内容换了，「上滚挂起」失去意义，恢复用户的跟随意图
            self._follow_suspended = False
            self._autoscroll.setChecked(True)
        self._scroll_guard += 1
        try:
            self._view.setPlainText("\n".join(t for t in history if self._matches(t)))
            if self._autoscroll.isChecked():
                self._scroll_to_bottom()
        finally:
            self._scroll_guard -= 1

    # --- 跟随状态机 ---
    def _on_scroll_changed(self, value):
        """只处理用户真实滚动，程序改滚动条时 guard 已经挡在前面。

        分支1 跟随开启 + 离开底部 → 自动挂起，开关变回未选中
        分支2 挂起中   + 回到底部 → 自动恢复跟随
        分支3 用户亲手关开关      → 挂起标记清零，分支2 不再成立
        """
        if self._scroll_guard:
            return
        sb = self._view.verticalScrollBar()
        at_bottom = value >= sb.maximum() - self._BOTTOM_TOL
        if self._autoscroll.isChecked() and not at_bottom:
            self._follow_suspended = True
            self._autoscroll.setChecked(False)
        elif self._follow_suspended and at_bottom:
            self._follow_suspended = False
            self._autoscroll.setChecked(True)

    def _on_autoscroll_clicked(self, checked):
        """用户点开关：意图优先，清掉自动挂起标记。"""
        self._follow_suspended = False
        if checked:
            self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        sb = self._view.verticalScrollBar()
        self._scroll_guard += 1
        try:
            sb.setValue(sb.maximum())
        finally:
            self._scroll_guard -= 1

    def _on_pause(self, checked):
        self._paused = checked
        if not checked:
            # 解除暂停：把暂停期间积压的日志一次性补齐
            self._poll()

    def _copy_all(self):
        QGuiApplication.clipboard().setText(self._view.toPlainText())

    def _clear_view(self):
        self._view.clear()
        _lines, newest = log_bus.snapshot_after(self._last_seq)
        self._last_seq = newest

    def _open_terminal(self):
        """打开 Windows 终端（优先 wt.exe，回退 PowerShell），目录定位到日志目录。"""
        cwd = str(LOG_DIR)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if shutil.which("wt"):
                subprocess.Popen(["wt", "-d", cwd])
                print("[Console] 已打开 Windows 终端")
                return
        except Exception as e:
            print(f"[Console] 打开 Windows 终端失败: {e}")
        # 回退：独立 PowerShell 窗口
        try:
            subprocess.Popen(
                ["powershell", "-NoExit", "-Command", f"Set-Location '{cwd}'"],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                if sys.platform == "win32" else 0)
            print("[Console] 已打开 PowerShell 窗口")
        except Exception as e:
            print(f"[Console] 打开终端失败: {e}")
