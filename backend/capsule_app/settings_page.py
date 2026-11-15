#!/usr/bin/env python3
"""LsletUI - 设置页（嵌入主界面 QStackedWidget 的 QWidget）。

展示 SettingsBackend 管理的高级设置：开机自启、自动减淡、
灵动岛提醒开关、界面语言、界面主题。
开关使用自绘的 ToggleSwitch（iOS 风格滑动开关，瞬间切换）。

i18n：所有可见文案都走 native_ui.tr()，并提供 retranslate(lang)
供主窗口在语言切换时刷新（无需重启）。
"""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QScrollArea, QVBoxLayout, QWidget,
)

from . import native_ui
from .native_ui import tr

from capsule_app.settings_backend import (
    ALLOWED_DELAYS, ALLOWED_LANGUAGES, ALLOWED_THEMES,
)

_LANG_NAMES = {
    "zh": "简体中文",
    "zh-TW": "繁體中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "de": "Deutsch",
    "ru": "Русский",
    "vi": "Tiếng Việt",
}


class ToggleSwitch(QWidget):
    """iOS 风格滑动开关：圆角轨道 + 白色滑块，瞬间切换无动画。

    接口与 QCheckBox 对齐：isChecked() / setChecked() / toggled(bool)，
    可直接替换 checkbox 使用。

    注：原实现带 120ms 动画，但 WA_TranslucentBackground + 高频 update()
    在 Mica 毛玻璃窗口上触发 DWM 合成导致卡顿，故改为无动画瞬间切换。
    """

    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._checked = False
        # 注：这里不再设置 WA_OpaquePaintEvent——控制台窗口已开启
        # WA_TranslucentBackground，声明「不透明绘制」会残留上一帧底色；
        # 开关只在点击时重绘，去掉该属性不会带来高频合成开销。

    # --- 与 QCheckBox 对齐的接口 ---
    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        checked = bool(checked)
        if checked == self._checked:
            return
        self._checked = checked
        self.update()
        self.toggled.emit(checked)

    def toggle(self):
        self.setChecked(not self._checked)

    # --- 交互 ---
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.toggle()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.toggle()
            event.accept()
            return
        super().keyPressEvent(event)

    # --- 绘制 ---
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 1) 非玻璃模式：先用卡片背景色填满整个控件（保持原有的不透明底）
        #    玻璃模式下不填充，让下方的半透明卡片/折射层透出来
        if not native_ui._CURRENT_GLASS:
            bg_color = (QColor("#181822") if native_ui._CURRENT_THEME == "dark"
                        else QColor("#ffffff"))
            p.setPen(Qt.NoPen)
            p.setBrush(bg_color)
            p.drawRect(self.rect())

        # 2) 轨道
        track = QRectF(1.0, 1.0, self.width() - 2.0, self.height() - 2.0)
        off = QColor("#3d3d48")
        on = QColor("#3a8dff")
        track_color = on if self._checked else off
        if not self.isEnabled():
            track_color = track_color.darker(140)

        p.setBrush(track_color)
        radius = track.height() / 2
        p.drawRoundedRect(track, radius, radius)

        # 3) 滑块
        margin = 3.5
        d = track.height() - margin * 2
        x = track.left() + margin + (1.0 if self._checked else 0.0) * (track.width() - d - margin * 2)
        knob_color = QColor("#ffffff") if self.isEnabled() else QColor("#aaaaaa")
        p.setBrush(knob_color)
        p.drawEllipse(QRectF(x, track.top() + margin, d, d))
        p.end()


class SettingsPageWidget(QWidget):
    """高级设置表单页。"""

    # 提醒开关的 (key, 翻译键) 列表，类级别以便 retranslate 复用
    NOTIFY_ITEMS = (
        ("notify_bluetooth", "settings.notify.bluetooth.title"),
        ("notify_clipboard", "settings.notify.clipboard.title"),
        ("notify_hardware",  "settings.notify.hardware.title"),
        ("notify_todo",      "settings.notify.todo.title"),
    )

    def __init__(self, settings_backend, parent=None):
        super().__init__(parent)
        self._backend = settings_backend
        self._updating = False
        self._lang = settings_backend.get_settings().get("language", "zh")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(14)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)
        lay.addLayout(form)
        self._form = form

        # 开机自启动
        self._autostart = ToggleSwitch()
        self._row_autostart = self._wrap_switch(self._autostart)
        self._lbl_autostart = QLabel()
        form.addRow(self._lbl_autostart, self._row_autostart)

        # 自动减淡 + 延迟
        self._auto_dim = ToggleSwitch()
        self._row_auto_dim = self._wrap_switch(self._auto_dim)
        self._lbl_auto_dim = QLabel()
        form.addRow(self._lbl_auto_dim, self._row_auto_dim)

        # 液态玻璃层
        self._liquid_glass = ToggleSwitch()
        self._row_liquid_glass = self._wrap_switch(self._liquid_glass)
        self._lbl_liquid_glass = QLabel()
        form.addRow(self._lbl_liquid_glass, self._row_liquid_glass)

        self._dim_delay = QComboBox()
        for d in ALLOWED_DELAYS:
            self._dim_delay.addItem("", d)
        self._lbl_dim_delay = QLabel()
        form.addRow(self._lbl_dim_delay, self._dim_delay)

        # 语言（语言下拉里的选项文本用固有名称，不随界面语言变化）
        self._language = QComboBox()
        for code in ALLOWED_LANGUAGES:
            self._language.addItem(_LANG_NAMES.get(code, code), code)
        self._lbl_language = QLabel()
        form.addRow(self._lbl_language, self._language)

        # 主题（黑/白）
        self._theme = QComboBox()
        for code in ALLOWED_THEMES:
            self._theme.addItem("", code)
        self._lbl_theme = QLabel()
        form.addRow(self._lbl_theme, self._theme)

        # 提醒开关分组
        lay.addSpacing(6)
        self._sep_alerts = QLabel()
        self._sep_alerts.setStyleSheet("font-weight: 600; font-size: 14px;")
        lay.addWidget(self._sep_alerts)

        self._notify = {}       # key -> ToggleSwitch
        self._notify_labels = {}  # key -> QLabel（单元格左侧文字）
        grid = QGridLayout()
        grid.setHorizontalSpacing(32)
        grid.setVerticalSpacing(12)
        for i, (key, _tr_key) in enumerate(self.NOTIFY_ITEMS):
            sw = ToggleSwitch()
            self._notify[key] = sw
            cell, lab = self._switch_cell(sw)
            self._notify_labels[key] = lab
            grid.addWidget(cell, i // 2, i % 2)
        lay.addLayout(grid)

        self._hint = QLabel()
        self._hint.setObjectName("hint")
        lay.addWidget(self._hint)
        lay.addStretch(1)

        # 首次填充文案
        self.retranslate(self._lang)

        # 回填当前值
        self._load()
        # 外部改动（如 Web 高级设置）同步刷新
        self._backend.settings_changed.connect(self._on_external_change)

        # 信号
        self._autostart.toggled.connect(
            lambda v: self._apply("autostart", v))
        self._auto_dim.toggled.connect(
            lambda v: self._apply("auto_dim", v))
        self._liquid_glass.toggled.connect(
            lambda v: self._apply("liquid_glass_enabled", v))
        self._dim_delay.currentIndexChanged.connect(
            lambda _i: self._apply("auto_dim_delay", self._dim_delay.currentData()))
        self._language.currentIndexChanged.connect(
            lambda _i: self._apply("language", self._language.currentData()))
        self._theme.currentIndexChanged.connect(
            lambda _i: self._apply("theme", self._theme.currentData()))
        for key, sw in self._notify.items():
            sw.toggled.connect(
                lambda v, k=key: self._apply(k, v))

    @staticmethod
    def _wrap_switch(switch):
        """开关 + 右侧灰色说明文字（占位，文案由 retranslate 填充）。"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        h.addWidget(switch)
        desc = QLabel()
        desc.setObjectName("hint")
        h.addWidget(desc, 1)
        # 把描述 QLabel 挂到 wrapper 上，方便后续 retranslate 取到
        w._desc_label = desc
        return w

    @staticmethod
    def _switch_cell(switch):
        """提醒分组里的单元格：左文字右开关。返回 (cell_widget, label)。"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)
        lab = QLabel()
        h.addWidget(lab, 1)
        h.addWidget(switch)
        return w, lab

    def retranslate(self, lang):
        """切换语言后刷新本页所有可见文案。"""
        if lang not in ALLOWED_LANGUAGES:
            lang = "zh"
        self._lang = lang
        t = lambda k, **kw: tr(lang, k, **kw)

        self._lbl_autostart.setText(t("settings.autostart"))
        self._row_autostart._desc_label.setText(t("settings.autostart.desc"))
        self._lbl_auto_dim.setText(t("settings.autoDim"))
        self._row_auto_dim._desc_label.setText(t("settings.autoDim.desc"))
        self._lbl_liquid_glass.setText(t("settings.liquidGlass"))
        self._row_liquid_glass._desc_label.setText(t("settings.liquidGlass.desc"))
        self._lbl_dim_delay.setText(t("settings.dimDelay"))
        self._lbl_language.setText(t("settings.language"))
        self._lbl_theme.setText(t("settings.theme"))

        # 减淡延迟选项文本（保留当前选中）
        current_delay = self._dim_delay.currentData()
        self._dim_delay.blockSignals(True)
        self._dim_delay.clear()
        for d in ALLOWED_DELAYS:
            self._dim_delay.addItem(t(f"settings.delay.{d}"), d)
        idx = self._dim_delay.findData(current_delay)
        if idx >= 0:
            self._dim_delay.setCurrentIndex(idx)
        self._dim_delay.blockSignals(False)

        # 主题选项
        current_theme = self._theme.currentData()
        self._theme.blockSignals(True)
        self._theme.clear()
        for code in ALLOWED_THEMES:
            self._theme.addItem(t(f"settings.theme.{code}"), code)
        idx = self._theme.findData(current_theme)
        if idx >= 0:
            self._theme.setCurrentIndex(idx)
        self._theme.blockSignals(False)

        # 提醒分组
        self._sep_alerts.setText(t("settings.alerts"))
        for key, tr_key in self.NOTIFY_ITEMS:
            if key in self._notify_labels:
                self._notify_labels[key].setText(t(tr_key))

        self._hint.setText(t("settings.hint"))

    def _load(self):
        s = self._backend.get_settings()
        self._updating = True
        try:
            self._autostart.setChecked(bool(s.get("autostart")))
            self._auto_dim.setChecked(bool(s.get("auto_dim", True)))
            # 液态玻璃：硬件预检不达标时开关禁用并强制关闭
            hw = s.get("liquid_glass_hw") or {}
            hw_ok = hw.get("supported", True) if isinstance(hw, dict) else True
            self._liquid_glass.setEnabled(hw_ok)
            self._liquid_glass.setChecked(bool(s.get("liquid_glass_enabled", True)) and hw_ok)
            # 不达标时在描述里提示
            if not hw_ok:
                self._row_liquid_glass._desc_label.setText(
                    tr(self._lang, "settings.liquidGlass.unsupported"))
            else:
                self._row_liquid_glass._desc_label.setText(
                    tr(self._lang, "settings.liquidGlass.desc"))
            delay = s.get("auto_dim_delay", 10000)
            idx = self._dim_delay.findData(delay)
            if idx >= 0:
                self._dim_delay.setCurrentIndex(idx)
            lang = s.get("language", "zh")
            idx = self._language.findData(lang)
            if idx >= 0:
                self._language.setCurrentIndex(idx)
            theme = s.get("theme", "dark")
            idx = self._theme.findData(theme)
            if idx >= 0:
                self._theme.setCurrentIndex(idx)
            for key, sw in self._notify.items():
                sw.setChecked(bool(s.get(key, True)))
        finally:
            self._updating = False

    def _on_external_change(self, settings):
        # 语言被外部（托盘/Web）改动时，本页也要刷新文案
        lang = settings.get("language", "zh") if isinstance(settings, dict) else "zh"
        if lang != self._lang:
            self.retranslate(lang)
        self._load()

    def _apply(self, key, value):
        if self._updating:
            return
        self._backend.set_setting(key, value)
