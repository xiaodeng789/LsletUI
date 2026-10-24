#!/usr/bin/env python3
"""
LsletUI - 轻量级灵动岛应用
iPhone 灵动岛风格胶囊窗口组件
"""

import json
import sys
from pathlib import Path

from PySide6.QtCore import (Qt, QTimer, QSize, QPoint, QRect, QRectF,
                            QPropertyAnimation, QEasingCurve, Property,
                            QAbstractAnimation, Signal, QDateTime)
from PySide6.QtGui import (QIcon, QColor, QPainter, QBrush, QPen,
                           QPainterPath, QLinearGradient, QFontMetrics,
                           QPixmap, QImage)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget,
                               QSystemTrayIcon, QMenu, QGraphicsDropShadowEffect)
from PySide6.QtGui import QAction

# 导入资源路径兼容模块
import sys as _sys
if not getattr(_sys, 'frozen', False):
    # 开发模式
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from resource_path import get_resource_path, get_config_path

PROJECT_ROOT = get_resource_path("")
CONFIG_FILE = get_config_path()


def load_config():
    """加载配置"""
    default = {
        "collapsed": {"width": 200, "height": 44},
        "hover": {"width": 240, "height": 52},
        "music_collapsed": {"width": 260, "height": 44},
        "music_hover": {"width": 320, "height": 56},
        "download_collapsed": {"width": 270, "height": 44},
        "download_hover": {"width": 400, "height": 56},
        "bt_notify": {"width": 300, "height": 64},
        "hw_alert": {"width": 348, "height": 84},
        "background_color": "#000000",
        "background_alpha": 0.92,
        "anchor": "top_center",
        "animation": {"expand_ms": 320, "collapse_ms": 200, "hover_ms": 150},
        "auto_hide": True,
        "auto_hide_delay": 10000,
    }
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                for k, v in loaded.items():
                    if isinstance(v, dict) and k in default and isinstance(default[k], dict):
                        default[k].update(v)
                    else:
                        default[k] = v
    except Exception as e:
        print(f"[Capsule] 加载配置失败: {e}")
    return default


def enable_acrylic(widget):
    """为窗口启用 Windows 亚克力毛玻璃效果"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = int(widget.winId())

        # Windows 11 22H2+: DWMWA_SYSTEMBACKDROP_TYPE
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        DWMSBT_TRANSIENTWINDOW = 3  # Acrylic-like
        value = ctypes.c_int(DWMSBT_TRANSIENTWINDOW)
        result = ctypes.WinDLL("dwmapi").DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(DWMWA_SYSTEMBACKDROP_TYPE),
            ctypes.byref(value),
            ctypes.sizeof(value)
        )
        if result == 0:
            print("[Capsule] 亚克力毛玻璃效果已启用")
            return True

        # 兜底：旧版 Windows 10 的 SetWindowCompositionAttribute
        class AccentPolicy(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_ulong),
                ("AnimationId", ctypes.c_int),
            ]

        class WindowCompositionAttributeData(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t),
            ]

        accent = AccentPolicy()
        accent.AccentState = 4  # ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.AccentFlags = 0
        # ABGR 颜色：黑色，alpha=0x40
        accent.GradientColor = 0x40000000
        accent.AnimationId = 0

        data = WindowCompositionAttributeData()
        data.Attribute = 19  # WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.byref(accent), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(accent)

        ctypes.WinDLL("user32").SetWindowCompositionAttribute(
            wintypes.HWND(hwnd),
            ctypes.byref(data)
        )
        print("[Capsule] 亚克力毛玻璃效果已启用（兼容模式）")
        return True
    except Exception as e:
        print(f"[Capsule] 亚克力效果启用失败: {e}")
        return False


class DynamicIslandWidget(QWidget):
    """iPhone 灵动岛风格胶囊组件，支持音乐播放显示"""

    clicked = Signal()
    media_control_clicked = Signal(str)  # "playpause" | "next" | "prev"

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._state = "collapsed"  # collapsed | hover
        self._dimmed = False

        # 尺寸配置
        collapsed = config.get("collapsed", {"width": 200, "height": 44})
        hover = config.get("hover", {"width": 240, "height": 52})
        music_collapsed = config.get("music_collapsed", {"width": 260, "height": 44})
        music_hover = config.get("music_hover", {"width": 320, "height": 56})
        self._collapsed_size = QSize(collapsed["width"], collapsed["height"])
        self._hover_size = QSize(hover["width"], hover["height"])
        self._music_collapsed_size = QSize(music_collapsed["width"], music_collapsed["height"])
        self._music_hover_size = QSize(music_hover["width"], music_hover["height"])

        download_collapsed = config.get("download_collapsed", {"width": 270, "height": 44})
        download_hover = config.get("download_hover", {"width": 400, "height": 56})
        self._download_collapsed_size = QSize(download_collapsed["width"], download_collapsed["height"])
        self._download_hover_size = QSize(download_hover["width"], download_hover["height"])

        bt_notify = config.get("bt_notify", {"width": 300, "height": 64})
        self._bt_notify_size = QSize(bt_notify["width"], bt_notify["height"])

        hw_alert = config.get("hw_alert", {"width": 348, "height": 84})
        self._hw_alert_size = QSize(hw_alert["width"], hw_alert["height"])

        # 硬件高负载告警（后端做阈值+迟滞，岛只负责展示与形变）
        self._hw_alert = False
        self._hw_stats = None

        # 蓝牙耳机连接/断开瞬时通知（dict: name/connected），仅展示数秒
        self._bt_event = None
        self._bt_hide_timer = None
        self._bt_icon_scale = 1.0

        # 音乐信息
        self._music_info = None  # dict: playing/title/artist/thumbnail(b64)
        self._music_thumb = None  # QPixmap

        # 下载信息（dict: active/state/filename/received/total/speed/count）
        self._download_info = None

        # 下载动画：img/进度条*.svg 五帧循环（未知总大小时的不确定进度）
        self._dl_frame = 0
        self._dl_anim_timer = QTimer(self)
        self._dl_anim_timer.setInterval(160)  # 5 帧 × 160ms = 800ms 一循环（原 120ms，降低重绘频率）
        self._dl_anim_timer.timeout.connect(self._on_dl_anim_tick)

        # 阴影留边（外圈需要留出空间绘制阴影）
        self._shadow_margin = 10
        self._animated_width = float(self._collapsed_size.width())
        self._animated_height = float(self._collapsed_size.height())

        # 字体缓存（避免每次 paintEvent 创建新 QFont 对象）
        self._font_cache = {}
        # QFontMetrics 缓存（elidedText 高频调用，避免重复构造）
        self._fm_cache = {}

        # 静态背景缓存（圆角矩形 + 高光 + 描边 + 手动阴影），尺寸/调光变化时重建
        self._bg_pixmap = None
        self._bg_key = None

        # SVG 图标预渲染 QPixmap 缓存（避免每帧 renderer.render 软件光栅化）
        self._svg_pixmap_cache = {}

        # 预创建常用 QColor（避免 paintEvent 中重复构造）
        self._init_color_cache()

        self._init_widget()
        self._init_animation()

    def _init_widget(self):
        """初始化窗口属性"""
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        # 外圈尺寸 = 胶囊 + 阴影边距
        self._update_outer_size()
        self.setCursor(Qt.PointingHandCursor)

    def _update_outer_size(self):
        w = int(self._animated_width) + self._shadow_margin * 2
        h = int(self._animated_height) + self._shadow_margin * 2
        self.setFixedSize(w, h)

    def _init_color_cache(self):
        """预创建常用颜色对象（paintEvent 中 QColor 构造虽轻量但高频，统一缓存）"""
        c = QColor
        self._colors = {
            # 主体与描边
            "bg": QColor(0, 0, 0, 235),
            "bg_dim": QColor(0, 0, 0, 141),
            "stroke": QColor(255, 255, 255, 12),
            # 文字
            "text_hi": QColor(255, 255, 255, 235),
            "text_hi_dim": QColor(255, 255, 255, 140),
            "text_mid": QColor(255, 255, 255, 165),
            "text_mid_dim": QColor(255, 255, 255, 100),
            "text_lo": QColor(255, 255, 255, 150),
            "text_lo_dim": QColor(255, 255, 255, 90),
            "text_hint": QColor(255, 255, 255, 120),
            "text_hint_dim": QColor(255, 255, 255, 80),
            # 圆形衬底
            "circle_bg": QColor(255, 255, 255, 30),
            "circle_bg_soft": QColor(255, 255, 255, 26),
            "circle_bg_weak": QColor(255, 255, 255, 20),
            # 状态色
            "ok": QColor(48, 209, 88),
            "warn": QColor(255, 199, 88),
            "err": QColor(255, 128, 128),
            "err_solid": QColor(255, 105, 105),
            "accent": QColor(100, 180, 255),
            "wave": QColor(120, 190, 255, 235),
            # 进度条
            "bar_bg": QColor(255, 255, 255, 38),
            "bar_fg": QColor(255, 255, 255, 235),
            "btn_bg": QColor(255, 255, 255, 25),
        }

    def _col(self, key):
        return self._colors[key]

    def _rebuild_bg_cache(self):
        """重建静态背景缓存（阴影 + 圆角矩形 + 顶部高光 + 1px 描边）

        原实现使用 QGraphicsDropShadowEffect：每帧把整个 widget 光栅化到离屏
        pixmap 再做高斯模糊（blur=28），在动画/动画帧中是主要卡顿来源。
        这里在背景变化时一次性绘制多层递减透明度的圆角矩形模拟柔和阴影，
        之后每次 paintEvent 仅 drawPixmap 一次即可。
        """
        w = int(self.width())
        h = int(self.height())
        if w <= 0 or h <= 0:
            self._bg_pixmap = None
            return
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)

        m = float(self._shadow_margin)
        rect = QRectF(m, m, self._animated_width, self._animated_height)
        radius = rect.height() / 2.0

        # --- 手动柔和阴影：多层向外扩散的圆角矩形（向下偏移 3px）---
        # 4 层扩散，alpha 由外向内递增，轻柔投影
        p.setPen(Qt.NoPen)
        offset_y = 3.0
        layers = 4
        for i in range(layers, 0, -1):
            frac = i / layers
            expand = m * frac
            alpha = int(4 + (layers - i) * 4)  # 4, 8, 12, 16
            r = QRectF(rect)
            r.adjust(-expand, -expand + offset_y, expand, expand + offset_y)
            rad = r.height() / 2.0
            path = QPainterPath()
            path.addRoundedRect(r, rad, rad)
            p.fillPath(path, QColor(0, 0, 0, alpha))

        # --- 主体圆角矩形 ---
        body = QPainterPath()
        body.addRoundedRect(rect, radius, radius)
        alpha = int(self._config.get("background_alpha", 0.92) * 255)
        if self._dimmed:
            alpha = int(alpha * 0.6)
        p.fillPath(body, QColor(0, 0, 0, alpha))

        # --- 顶部高光 ---
        highlight = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        highlight.setColorAt(0.0, QColor(255, 255, 255, 10))
        highlight.setColorAt(0.5, QColor(255, 255, 255, 0))
        p.fillPath(body, QBrush(highlight))

        # --- 1px 描边 ---
        pen = QPen(self._col("stroke"))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(body)

        p.end()
        self._bg_pixmap = pm
        self._bg_key = (w, h, round(self._animated_width, 2),
                        round(self._animated_height, 2), self._dimmed)

    def _get_font(self, point_size, bold=False):
        """获取缓存的字体对象（避免每次绘制创建新 QFont）"""
        key = (point_size, bold)
        if key not in self._font_cache:
            from PySide6.QtGui import QFont
            font = QFont()
            font.setPointSize(point_size)
            font.setBold(bold)
            self._font_cache[key] = font
        return self._font_cache[key]

    def _get_fm(self, point_size, bold=False):
        """获取缓存的 QFontMetrics（elidedText 每次构造 QFontMetrics 开销不小）"""
        key = (point_size, bold)
        fm = self._fm_cache.get(key)
        if fm is None:
            fm = QFontMetrics(self._get_font(point_size, bold))
            self._fm_cache[key] = fm
        return fm

    def _init_animation(self):
        """初始化尺寸动画"""
        self._size_anim = QPropertyAnimation(self, b"animatedWidth", self)
        self._size_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._size_anim_h = QPropertyAnimation(self, b"animatedHeight", self)
        self._size_anim_h.setEasingCurve(QEasingCurve.OutCubic)

        # 蓝牙通知图标的弹出（回弹）动画
        self._bt_pop_anim = QPropertyAnimation(self, b"btIconScale", self)
        self._bt_pop_anim.setEasingCurve(QEasingCurve.OutBack)
        self._bt_pop_anim.setDuration(480)

    # --- 动画属性 ---
    def _get_animated_width(self):
        return self._animated_width

    def _set_animated_width(self, w):
        self._animated_width = float(w)
        self._update_outer_size()
        self.sizeChanged.emit(self._animated_width, self._animated_height)
        self.update()

    def _get_animated_height(self):
        return self._animated_height

    def _set_animated_height(self, h):
        self._animated_height = float(h)
        self._update_outer_size()
        self.sizeChanged.emit(self._animated_width, self._animated_height)
        self.update()

    animatedWidth = Property(float, _get_animated_width, _set_animated_width)
    animatedHeight = Property(float, _get_animated_height, _set_animated_height)
    sizeChanged = Signal(float, float)

    # --- 蓝牙图标弹出缩放属性 ---
    def _get_bt_icon_scale(self):
        return self._bt_icon_scale

    def _set_bt_icon_scale(self, scale):
        self._bt_icon_scale = float(scale)
        self.update()

    btIconScale = Property(float, _get_bt_icon_scale, _set_bt_icon_scale)

    # --- 目标尺寸 ---
    def _download_visible(self):
        """下载胶囊是否可见（下载中 / 暂停 / 完成提示期间）"""
        info = self._download_info
        return bool(info and (info.get("active") or info.get("state") == "completed"))

    def _current_collapsed_size(self):
        if self._bt_event is not None:
            return self._bt_notify_size
        if self._hw_alert:
            return self._hw_alert_size
        if self._download_visible():
            return self._download_collapsed_size
        if self._music_info and self._music_info.get("title"):
            return self._music_collapsed_size
        return self._collapsed_size

    def _current_hover_size(self):
        if self._bt_event is not None:
            return self._bt_notify_size
        if self._hw_alert:
            return self._hw_alert_size
        if self._download_visible():
            return self._download_hover_size
        if self._music_info and self._music_info.get("title"):
            return self._music_hover_size
        return self._hover_size

    # --- 动画控制 ---
    def _animate_to(self, target_size, duration):
        """动画到目标尺寸"""
        for anim, target in ((self._size_anim, target_size.width()),
                             (self._size_anim_h, target_size.height())):
            anim.stop()
            anim.setDuration(duration)
            anim.setStartValue(self._animated_width if anim is self._size_anim else self._animated_height)
            anim.setEndValue(float(target))
            anim.start()

    def _expand(self, duration=None):
        anim_cfg = self._config.get("animation", {})
        duration = duration or anim_cfg.get("hover_ms", 200)
        self._animate_to(self._current_hover_size(), duration)
        self._state = "hover"

    def _collapse(self, duration=None):
        anim_cfg = self._config.get("animation", {})
        duration = duration or anim_cfg.get("collapse_ms", 240)
        self._animate_to(self._current_collapsed_size(), duration)
        self._state = "collapsed"

    # --- 音乐信息 ---
    def set_music_info(self, info):
        """设置音乐信息并触发布局更新"""
        import base64 as _b64
        old_title = (self._music_info or {}).get("title") if self._music_info else None
        self._music_info = info

        thumb_b64 = info.get("thumbnail") if info else None
        if thumb_b64:
            try:
                img = QImage.fromData(_b64.b64decode(thumb_b64))
                # 预裁切为圆形并缩放到胶囊高度，绘制时直接 drawPixmap，
                # 避免每帧 setClipPath + drawPixmap + setClipping(False)
                self._music_thumb = self._make_circular_thumb(
                    QPixmap.fromImage(img))
            except Exception:
                self._music_thumb = None
        else:
            self._music_thumb = None

        # 音乐状态变化时，如果当前是收起状态且有新歌或无歌了，重新计算尺寸
        new_title = info.get("title") if info else None
        if self._state == "collapsed" and old_title != new_title:
            self._animate_to(self._current_collapsed_size(), 200)
            # 新歌出现：短暂展开提示（iPhone 灵动岛标志性行为）
            # （蓝牙瞬时通知展示中不改尺寸，避免内容与尺寸错位）
            if new_title and not old_title and self._bt_event is None:
                self._expand(duration=200)
                QTimer.singleShot(2500, self._auto_collapse)
        self.update()

    def _make_circular_thumb(self, pixmap):
        """将方形封面裁切成圆形并缓存（音乐封面按胶囊高度一次性预处理）"""
        if pixmap is None or pixmap.isNull():
            return None
        # 胶囊高度最大 56，封面圆形直径最大约 48；预渲染 96px 给高清屏留余量
        side = 96
        scaled = pixmap.scaled(side, side,
                               Qt.KeepAspectRatioByExpanding,
                               Qt.SmoothTransformation)
        out = QPixmap(side, side)
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, side, side)
        p.setClipPath(path)
        p.drawPixmap(0, 0, scaled)
        p.end()
        return out

    def _auto_collapse(self):
        """如果鼠标不在胶囊上，自动收起"""
        if not self.underMouse() and self._state == "hover":
            self._collapse()

    # --- 下载信息 ---
    def set_download_info(self, info):
        """设置下载信息并触发布局更新

        info: active/state(downloading|paused|completed|idle)/
              filename/received/total/speed/count
        """
        old = self._download_info or {}
        old_visible = self._download_visible()
        self._download_info = info
        now_visible = self._download_visible()

        if now_visible and not old_visible:
            # 新下载开始 / 下载完成：灵动岛标志性展开提示后收回
            # （蓝牙瞬时通知展示中不改尺寸，避免内容与尺寸错位）
            if self._bt_event is None:
                self._expand(duration=240)
                QTimer.singleShot(2200, self._auto_collapse)
        elif now_visible and not old.get("active") and self._state == "collapsed":
            # 完成提示结束回到下载中，或反之：收起态尺寸不变，仅重绘
            pass
        elif not now_visible and old_visible and self._state == "collapsed":
            # 下载流程整体结束：从下载尺寸动画回默认/音乐尺寸
            self._animate_to(self._current_collapsed_size(), 220)
        self._update_dl_anim_timer()
        self.update()

    # --- 下载动画（不确定进度五帧） ---
    def _on_dl_anim_tick(self):
        self._dl_frame = (self._dl_frame + 1) % 5
        self.update()

    def _dl_indeterminate(self):
        """是否处于“总大小未知”的活跃下载状态"""
        info = self._download_info
        return bool(info and info.get("active")
                    and info.get("state") == "downloading"
                    and not float(info.get("total") or 0))

    def _update_dl_anim_timer(self):
        """仅在不确定进度下载中播放动画，其余状态停止（暂停时冻结在当前帧）"""
        if self._dl_indeterminate():
            if not self._dl_anim_timer.isActive():
                self._dl_anim_timer.start()
        elif self._dl_anim_timer.isActive():
            self._dl_anim_timer.stop()

    # --- 蓝牙耳机连接/断开通知 ---
    BT_TOAST_MS = 3000

    def set_bluetooth_event(self, info):
        """耳机连接/断开时展开胶囊弹出通知，数秒后自动收回

        info: {"name": 设备名, "connected": True/False}
        """
        self._bt_event = info

        # 打断当前尺寸动画，展开到通知尺寸（灵动岛标志性形变）
        self._state = "hover"
        self._animate_to(self._bt_notify_size, 320)

        # 图标从 0.35 倍回弹放大
        self._bt_pop_anim.stop()
        self._bt_pop_anim.setStartValue(0.35)
        self._bt_pop_anim.setEndValue(1.0)
        self._bt_pop_anim.start()

        # 连续事件（连上又断开）时以最后一次为准重新计时
        self._restart_bt_hide_timer()
        self.update()

    def _restart_bt_hide_timer(self):
        """复用蓝牙隐藏定时器（避免每次通知创建新 QTimer 导致泄漏）"""
        if self._bt_hide_timer is None:
            self._bt_hide_timer = QTimer(self)
            self._bt_hide_timer.setSingleShot(True)
            self._bt_hide_timer.timeout.connect(self._dismiss_bluetooth_event)
        else:
            self._bt_hide_timer.stop()
        self._bt_hide_timer.start(self.BT_TOAST_MS)

    def _dismiss_bluetooth_event(self):
        """通知展示结束，回到正常形态"""
        if self._bt_event is None:
            return
        self._bt_event = None
        self._bt_hide_timer = None
        if self.underMouse():
            self._expand()
        else:
            self._collapse()
        self.update()

    def dismiss_bluetooth_event(self):
        """立即收回蓝牙通知（通知关闭时调用）"""
        if self._bt_hide_timer is not None:
            self._bt_hide_timer.stop()
        self._dismiss_bluetooth_event()

    # --- 硬件高负载告警 ---
    def set_hw_alert(self, active, stats):
        """高负载开始/结束（阈值+迟滞在后端），岛负责形变与通知互斥

        蓝牙瞬时通知展示中只记录不改尺寸，通知收回时经
        _collapse/_expand 自然露出（或离开）硬件形态。
        """
        old = self._hw_alert
        self._hw_alert = active
        self._hw_stats = stats

        if active == old:
            self.update()
            return
        if self._bt_event is not None:
            self.update()
            return

        if active:
            # 灵动岛标志性形变：从当前尺寸弹出到告警形态
            self._state = "hover"
            self._animate_to(self._hw_alert_size, 320)
        else:
            # 负载回落：回到当前内容的正常形态
            if self.underMouse():
                self._expand()
            else:
                self._collapse()
        self.update()

    def set_hardware_stats(self, stats):
        """告警展示期间刷新负载条数据"""
        self._hw_stats = stats
        self.update()

    def is_hw_alerting(self):
        """硬件高负载告警是否正在展示"""
        return self._hw_alert

    @staticmethod
    def _hw_bar_color(value):
        """负载条颜色：>80% 橙，>92% 红"""
        v = float(value)
        if v >= 92:
            return QColor(255, 105, 105)
        if v >= 80:
            return QColor(255, 199, 88)
        return QColor(255, 255, 255, 235)

    def _paint_hw_content(self, painter, rect):
        """绘制硬件告警：左列 CPU/内存/GPU 负载条，右列温度与网速"""
        stats = self._hw_stats or {}
        left, top = rect.left(), rect.top()
        w, h = rect.width(), rect.height()
        pad = 14.0

        # 左列：标签 + 负载条 + 百分比
        col_w = 196.0
        label_w = 30.0
        value_w = 34.0
        bar_w = col_w - label_w - value_w - 12.0
        row_h = (h - pad * 2) / 3.0

        rows = [
            ("CPU", stats.get("cpu")),
            ("内存", stats.get("mem")),
            ("GPU", stats.get("gpu")),
        ]
        for i, (label, value) in enumerate(rows):
            cy = top + pad + row_h * (i + 0.5)

            label_font = painter.font()
            label_font.setPointSize(8)
            label_font.setBold(False)
            painter.setFont(label_font)
            painter.setPen(QColor(255, 255, 255, 165 if not self._dimmed else 100))
            painter.drawText(QRectF(left + pad, cy - 8, label_w, 16),
                             Qt.AlignLeft | Qt.AlignVCenter, label)

            bar_rect = QRectF(left + pad + label_w + 6, cy - 2.5, bar_w, 5.0)
            bar_path = QPainterPath()
            bar_path.addRoundedRect(bar_rect, 2.5, 2.5)
            painter.fillPath(bar_path, QColor(255, 255, 255, 38))

            if value is not None:
                frac = max(0.0, min(float(value) / 100.0, 1.0))
                fill_w = bar_rect.width() * frac
                if fill_w > 0:
                    fill_path = QPainterPath()
                    fill_path.addRoundedRect(
                        QRectF(bar_rect.left(), bar_rect.top(), fill_w, 5.0),
                        2.5, 2.5)
                    painter.fillPath(fill_path, self._hw_bar_color(value))

                value_font = painter.font()
                value_font.setPointSize(8.5)
                value_font.setBold(True)
                painter.setFont(value_font)
                painter.setPen(QColor(255, 255, 255, 230 if not self._dimmed else 130))
                painter.drawText(QRectF(bar_rect.right() + 6, cy - 8, value_w, 16),
                                 Qt.AlignLeft | Qt.AlignVCenter,
                                 f"{int(round(float(value)))}%")
            else:
                painter.setFont(label_font)
                painter.setPen(QColor(255, 255, 255, 110 if not self._dimmed else 70))
                painter.drawText(QRectF(bar_rect.right() + 6, cy - 8, value_w, 16),
                                 Qt.AlignLeft | Qt.AlignVCenter, "--")

        # 右列：GPU 温度 + 上/下行网速（与左列三行对齐）
        rx = left + pad + col_w + 10
        rw = left + w - pad - rx
        gpu_temp = stats.get("gpu_temp")

        temp_font = painter.font()
        temp_font.setPointSize(8.5)
        temp_font.setBold(True)
        painter.setFont(temp_font)
        if gpu_temp is not None:
            painter.setPen(QColor(255, 105, 105) if gpu_temp >= 85
                           else QColor(255, 199, 88) if gpu_temp >= 75
                           else QColor(255, 255, 255, 230 if not self._dimmed else 130))
            temp_text = f"GPU {gpu_temp:.0f}°C"
        else:
            painter.setPen(QColor(255, 255, 255, 110 if not self._dimmed else 70))
            temp_text = "GPU --"
        painter.drawText(QRectF(rx, top + pad + row_h * 0.5 - 8, rw, 16),
                         Qt.AlignLeft | Qt.AlignVCenter, temp_text)

        net_font = painter.font()
        net_font.setPointSize(8)
        net_font.setBold(False)
        painter.setFont(net_font)
        painter.setPen(QColor(255, 255, 255, 170 if not self._dimmed else 100))
        painter.drawText(QRectF(rx, top + pad + row_h * 1.5 - 8, rw, 16),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         f"↑ {self._fmt_speed(stats.get('net_up'))}")
        painter.drawText(QRectF(rx, top + pad + row_h * 2.5 - 8, rw, 16),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         f"↓ {self._fmt_speed(stats.get('net_down'))}")

    # --- 绘制 ---
    def paintEvent(self, event):
        # 静态背景（阴影 + 圆角矩形 + 高光 + 描边）尺寸/调光未变时直接 blit 缓存，
        # 避免每帧重建 QPainterPath / QLinearGradient / 高斯模糊（原 QGraphicsDropShadowEffect）
        w = int(self.width())
        h = int(self.height())
        key = (w, h, round(self._animated_width, 2),
               round(self._animated_height, 2), self._dimmed)
        if self._bg_pixmap is None or self._bg_key != key:
            self._rebuild_bg_cache()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self._bg_pixmap is not None:
            painter.drawPixmap(0, 0, self._bg_pixmap)

        m = self._shadow_margin
        rect = QRectF(m, m, self._animated_width, self._animated_height)

        # 每帧重置媒体控制按钮热区，避免切到其他形态后残留旧坐标导致误触
        # （_paint_control_buttons 绘制音乐按钮时会重新填充）
        self._control_zones = {}

        # 内容（优先级：蓝牙通知 > 硬件告警 > 下载 > 音乐 > 默认）
        if self._bt_event is not None:
            self._paint_bt_content(painter, rect)
        elif self._hw_alert:
            self._paint_hw_content(painter, rect)
        elif self._download_visible():
            self._paint_download_content(painter, rect)
        elif self._music_info and self._music_info.get("title"):
            self._paint_music_content(painter, rect)
        else:
            self._paint_default_content(painter, rect)

        painter.end()

    def _paint_default_content(self, painter, rect):
        """默认显示 LsletUI 文字"""
        painter.setPen(QColor(255, 255, 255, 230 if not self._dimmed else 130))
        font = painter.font()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, "LsletUI")

    # --- 蓝牙连接通知绘制 ---
    def _load_bt_pixmap(self):
        """加载 img/bluetooth-BtTQvFRP.png（透明底蓝色蓝牙符文）并缓存"""
        if not hasattr(self, "_bt_pixmap"):
            img_dir = get_resource_path("img")
            pm = QPixmap(str(img_dir / "bluetooth-BtTQvFRP.png"))
            self._bt_pixmap = None if pm.isNull() else pm
        return self._bt_pixmap

    def _paint_bt_content(self, painter, rect):
        """绘制耳机连接/断开通知：圆形图标 + 状态标题 + 设备名"""
        info = self._bt_event or {}
        connected = bool(info.get("connected"))
        name = info.get("name") or "蓝牙耳机"

        left, top = rect.left(), rect.top()
        w, h = rect.width(), rect.height()
        pad = 12

        # 左侧圆形衬底 + 蓝牙图标（图标带弹出缩放，断开时半透明）
        icon_d = h - 20
        cx = left + pad + icon_d / 2
        cy = top + h / 2
        circle = QRectF(cx - icon_d / 2, cy - icon_d / 2, icon_d, icon_d)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 30 if connected else 20))
        painter.drawEllipse(circle)
        painter.setBrush(Qt.NoBrush)

        pm = self._load_bt_pixmap()
        if pm is not None:
            scale = max(0.0, self._bt_icon_scale)
            # 原图偏高挑（蓝牙符文），按高度适配并保持宽高比
            glyph_h = icon_d * 0.62 * scale
            glyph_w = glyph_h * (pm.width() / pm.height())
            painter.save()
            painter.setOpacity(1.0 if connected else 0.5)
            painter.drawPixmap(
                QRectF(cx - glyph_w / 2, cy - glyph_h / 2, glyph_w, glyph_h),
                pm, QRectF(0, 0, pm.width(), pm.height()))
            painter.restore()

        # 右侧文字：状态标题（绿=已连接，红=已断开）+ 设备名
        text_left = left + pad + icon_d + 12
        text_w = (left + w - pad) - text_left

        title_font = painter.font()
        title_font.setPointSize(11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(48, 209, 88) if connected else QColor(255, 128, 128))
        title = "蓝牙已连接" if connected else "蓝牙已断开"
        painter.drawText(QRectF(text_left, top + h / 2 - 17, text_w, 18),
                         Qt.AlignLeft | Qt.AlignVCenter, title)

        sub_font = painter.font()
        sub_font.setPointSize(8.5)
        sub_font.setBold(False)
        painter.setFont(sub_font)
        painter.setPen(QColor(255, 255, 255, 165 if not self._dimmed else 100))
        metrics = QFontMetrics(sub_font)
        painter.drawText(
            QRectF(text_left, top + h / 2 + 2, text_w, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            metrics.elidedText(name, Qt.ElideRight, int(text_w)))

    # --- 下载内容绘制 ---
    @staticmethod
    def _fmt_bytes(n):
        n = float(n or 0)
        if n < 1024:
            return f"{int(n)} B"
        for unit in ("KB", "MB", "GB"):
            n /= 1024
            if n < 1024 or unit == "GB":
                return f"{n:.1f} {unit}"

    @staticmethod
    def _fmt_speed(bps):
        bps = float(bps or 0)
        if bps < 1024:
            return f"{int(bps)} B/s"
        for unit in ("KB/s", "MB/s", "GB/s"):
            bps /= 1024
            if bps < 1024 or unit == "GB/s":
                return f"{bps:.1f} {unit}"

    def _paint_download_content(self, painter, rect):
        """绘制下载进度内容（收起：环形进度环绕图标；悬停：进度条）"""
        info = self._download_info or {}
        left, top = rect.left(), rect.top()
        w, h = rect.width(), rect.height()
        pad = 10
        state = info.get("state", "idle")
        completed = state == "completed"
        paused = state == "paused"

        received = float(info.get("received") or 0)
        total = float(info.get("total") or 0)
        speed = float(info.get("speed") or 0)
        filename = info.get("filename") or (
            "下载完成" if completed else ("已暂停" if paused else "下载中"))

        progress = (received / total) if total > 0 else None
        if completed:
            progress = 1.0
        indeterminate = (not completed) and progress is None

        # 左侧圆形图标 + 环形进度
        icon_size = (h - 12) if self._state == "hover" else (h - 10)
        cx = left + pad + icon_size / 2
        cy = top + h / 2
        circle = QRectF(cx - icon_size / 2, cy - icon_size / 2, icon_size, icon_size)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 26))
        painter.drawEllipse(circle)
        painter.setBrush(Qt.NoBrush)

        if progress is not None and progress > 0:
            ring_rect = circle.adjusted(2.5, 2.5, -2.5, -2.5)
            pen = QPen(QColor(48, 209, 88) if completed else QColor(255, 255, 255, 225))
            pen.setWidthF(2.6)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            # 从 12 点方向顺时针绘制进度弧
            painter.drawArc(ring_rect, 90 * 16, -int(360 * 16 * min(progress, 1.0)))

        if completed:
            painter.setPen(QColor(48, 209, 88))
            f = painter.font()
            f.setPointSize(max(9, int(icon_size * 0.36)))
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(circle, Qt.AlignCenter, "✓")
        elif indeterminate and self._state != "hover":
            # 收起态 + 未知总大小：在圆内播放 进度条*.svg 五帧动画
            # 预渲染 QPixmap，避免每帧 QSvgRenderer.render 软件光栅化
            frame_names = ("进度条", "进度条-02", "进度条-03",
                           "进度条-04", "进度条-05")
            inner = circle.adjusted(5, 5, -5, -5)
            frame_name = frame_names[self._dl_frame]
            pm_frame = self._get_icon_pixmap(
                frame_name, min(inner.width(), inner.height()))
            if pm_frame is not None:
                painter.drawPixmap(inner, pm_frame, QRectF(pm_frame.rect()))
        else:
            side = icon_size * 0.46
            pm_dl = self._get_icon_pixmap("下载", side) if side > 1 else None
            if pm_dl is not None:
                painter.drawPixmap(QRectF(cx - side / 2, cy - side / 2, side, side),
                                   pm_dl, QRectF(pm_dl.rect()))
            else:
                painter.setPen(QColor(255, 255, 255, 220))
                f = painter.font()
                f.setPointSize(max(9, int(icon_size * 0.4)))
                painter.setFont(f)
                painter.drawText(circle, Qt.AlignCenter, "↓")

        text_left = left + pad + icon_size + 10

        if self._state == "hover":
            right_w = 128
            right_x = left + w - pad - right_w
            col_w = (right_x - 14) - text_left

            # 文件名
            title_font = painter.font()
            title_font.setPointSize(10)
            title_font.setBold(True)
            painter.setFont(title_font)
            painter.setPen(QColor(255, 255, 255, 230 if not self._dimmed else 130))
            metrics = QFontMetrics(title_font)
            painter.drawText(QRectF(text_left, top + 6, col_w, 16),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             metrics.elidedText(filename, Qt.ElideRight, int(col_w)))

            # 进度条
            bar_h = 5.0
            bar_rect = QRectF(text_left, top + h - 13, col_w, bar_h)
            bar_path = QPainterPath()
            bar_path.addRoundedRect(bar_rect, bar_h / 2, bar_h / 2)
            painter.fillPath(bar_path, QColor(255, 255, 255, 38))
            if progress is not None and progress > 0:
                fill_w = max(bar_rect.width() * min(progress, 1.0), bar_h)
                fill_path = QPainterPath()
                fill_path.addRoundedRect(
                    QRectF(bar_rect.left(), bar_rect.top(), fill_w, bar_h),
                    bar_h / 2, bar_h / 2)
                painter.fillPath(fill_path,
                                 QColor(48, 209, 88) if completed
                                 else QColor(255, 255, 255, 235))
            elif indeterminate:
                # 未知总大小：圆点在轨道内 左→中→右 循环
                # （对应 进度条-02/03/04 帧，01/05 帧只有空轨道）
                frac = {1: 0.16, 2: 0.5, 3: 0.84}.get(self._dl_frame)
                if frac is not None:
                    d = bar_h
                    x = bar_rect.left() + (bar_rect.width() - d) * frac
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(255, 255, 255, 235))
                    painter.drawEllipse(QRectF(x, bar_rect.top(), d, d))
                    painter.setBrush(Qt.NoBrush)

            # 右侧：速度 + 已下载/总大小
            speed_font = painter.font()
            speed_font.setPointSize(10)
            speed_font.setBold(True)
            painter.setFont(speed_font)
            if completed:
                painter.setPen(QColor(48, 209, 88, 255))
                speed_text = "已完成"
            elif paused:
                painter.setPen(QColor(255, 199, 88, 235))
                speed_text = "已暂停"
            else:
                painter.setPen(QColor(255, 255, 255, 235 if not self._dimmed else 130))
                # 预分配文件（迅雷eMule/网盘）大小不变测不出速度，显示状态而非 0
                speed_text = self._fmt_speed(speed) if speed >= 1 else "下载中"
            painter.drawText(QRectF(right_x, top + 6, right_w, 16),
                             Qt.AlignRight | Qt.AlignVCenter, speed_text)

            size_font = painter.font()
            size_font.setPointSize(7.5)
            size_font.setBold(False)
            painter.setFont(size_font)
            painter.setPen(QColor(255, 255, 255, 150 if not self._dimmed else 90))
            if total > 0:
                size_text = (f"{self._fmt_bytes(received)} / {self._fmt_bytes(total)}"
                             f" · {int(round(min(progress, 1.0) * 100))}%")
            else:
                size_text = f"已下载 {self._fmt_bytes(received)}"
            count = info.get("count") or 0
            if count > 1 and not completed:
                size_text += f" · 共{count}个"
            painter.drawText(QRectF(right_x, top + h - 22, right_w, 14),
                             Qt.AlignRight | Qt.AlignVCenter, size_text)
        else:
            # 收起态：文件名 + 右侧速度
            text_right = left + w - pad
            speed_w = 72
            col_w = (text_right - speed_w - 8) - text_left

            title_font = painter.font()
            title_font.setPointSize(10)
            title_font.setBold(True)
            painter.setFont(title_font)
            painter.setPen(QColor(255, 255, 255, 230 if not self._dimmed else 130))
            metrics = QFontMetrics(title_font)
            painter.drawText(QRectF(text_left, top, col_w, h),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             metrics.elidedText(filename, Qt.ElideRight, int(col_w)))

            speed_font = painter.font()
            speed_font.setPointSize(8)
            speed_font.setBold(False)
            painter.setFont(speed_font)
            if completed:
                painter.setPen(QColor(48, 209, 88, 235))
                speed_text = "已完成"
            elif paused:
                painter.setPen(QColor(255, 199, 88, 220))
                speed_text = "已暂停"
            else:
                painter.setPen(QColor(255, 255, 255, 170 if not self._dimmed else 110))
                speed_text = self._fmt_speed(speed) if speed >= 1 else "下载中"
            painter.drawText(QRectF(text_right - speed_w, top, speed_w, h),
                             Qt.AlignRight | Qt.AlignVCenter, speed_text)

    def _paint_music_content(self, painter, rect):
        """绘制音乐信息内容"""
        left = rect.left()
        top = rect.top()
        w = rect.width()
        h = rect.height()
        pad = 10

        # 专辑封面（预裁切圆形 QPixmap，直接绘制，避免每帧 clipPath）
        thumb_size = int(h - 8)
        thumb_x = left + pad
        thumb_y = top + (h - thumb_size) / 2
        if self._music_thumb and not self._music_thumb.isNull():
            painter.drawPixmap(QRectF(thumb_x, thumb_y, thumb_size, thumb_size),
                               self._music_thumb,
                               QRectF(self._music_thumb.rect()))
        else:
            # 无封面时画一个默认音符图标
            path = QPainterPath()
            path.addEllipse(thumb_x, thumb_y, thumb_size, thumb_size)
            painter.fillPath(path, QColor(255, 255, 255, 30))
            painter.setPen(QColor(255, 255, 255, 200))
            f = painter.font()
            f.setPointSize(int(thumb_size * 0.45))
            painter.setFont(f)
            painter.drawText(QRectF(thumb_x, thumb_y, thumb_size, thumb_size),
                             Qt.AlignCenter, "♪")

        # 文字区域
        text_left = thumb_x + thumb_size + 10
        text_width = w - (text_left - left) - pad

        # 根据状态决定是否显示控制按钮
        show_controls = (self._state == "hover")
        btn_w = 32 if show_controls else 0
        btn_gap = 6 if show_controls else 0
        text_width -= (btn_w * 3 + btn_gap * 2 + 8) if show_controls else 0

        title = self._music_info.get("title", "")
        artist = self._music_info.get("artist", "")
        playing = self._music_info.get("playing", False)

        # 标题
        title_font = painter.font()
        title_font.setPointSize(10)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255, 230 if not self._dimmed else 130))
        metrics = QFontMetrics(title_font)
        elided_title = metrics.elidedText(title, Qt.ElideRight, int(text_width))
        title_rect = QRectF(text_left, top + (h - 20) / 2 - (10 if artist else -8),
                            text_width, 18)
        if artist:
            painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_title)
        else:
            painter.drawText(QRectF(text_left, top, text_width, h),
                             Qt.AlignLeft | Qt.AlignVCenter, elided_title)

        # 歌手（仅在 hover 或有空间时显示）
        if artist:
            artist_font = painter.font()
            artist_font.setPointSize(8)
            artist_font.setBold(False)
            painter.setFont(artist_font)
            painter.setPen(QColor(255, 255, 255, 150 if not self._dimmed else 90))
            artist_metrics = QFontMetrics(artist_font)
            elided_artist = artist_metrics.elidedText(artist, Qt.ElideRight, int(text_width))
            artist_rect = QRectF(text_left, title_rect.bottom() - 2, text_width, 14)
            painter.drawText(artist_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_artist)

        # 控制按钮（hover 时显示）
        if show_controls:
            self._paint_control_buttons(painter, rect, btn_w, btn_gap, playing)

    def _paint_control_buttons(self, painter, rect, btn_w, gap, playing):
        """绘制播放控制按钮"""
        btn_h = 28
        start_x = rect.right() - 10 - (btn_w * 3 + gap * 2)
        center_y = rect.center().y()

        buttons = [
            ("prev", start_x),
            ("playpause", start_x + btn_w + gap),
            ("next", start_x + (btn_w + gap) * 2),
        ]

        for name, x in buttons:
            btn_rect = QRectF(x, center_y - btn_h / 2, btn_w, btn_h)
            # 按钮背景
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 25))
            painter.drawEllipse(btn_rect)
            painter.setBrush(Qt.NoBrush)

            # 图标（SVG 预渲染 QPixmap）：播放中显示"暂停"，暂停时显示"播放"
            if name == "prev":
                icon_name = "上一个"
            elif name == "playpause":
                icon_name = "暂停" if playing else "播放"
            else:
                icon_name = "下一个"

            icon_side = btn_h * 0.52
            pm_icon = self._get_icon_pixmap(icon_name, icon_side)
            if pm_icon is not None:
                cx, cy = btn_rect.center().x(), btn_rect.center().y()
                icon_rect = QRectF(cx - icon_side / 2, cy - icon_side / 2,
                                   icon_side, icon_side)
                painter.drawPixmap(icon_rect, pm_icon, QRectF(pm_icon.rect()))
            else:
                # 兜底：emoji
                painter.setPen(QColor(255, 255, 255, 220))
                fallback = {"prev": "⏮", "next": "⏭"}.get(
                    name, "⏸" if playing else "▶")
                painter.drawText(btn_rect, Qt.AlignCenter, fallback)

        # 存储按钮区域用于点击检测（四周外扩 4px，提升点击容错）
        pad = 4
        self._control_zones = {
            "prev": QRect(int(start_x) - pad, int(center_y - btn_h / 2) - pad,
                          btn_w + pad * 2, btn_h + pad * 2),
            "playpause": QRect(int(start_x + btn_w + gap) - pad,
                               int(center_y - btn_h / 2) - pad,
                               btn_w + pad * 2, btn_h + pad * 2),
            "next": QRect(int(start_x + (btn_w + gap) * 2) - pad,
                          int(center_y - btn_h / 2) - pad,
                          btn_w + pad * 2, btn_h + pad * 2),
        }

    _control_zones = {}

    def _load_svg_icon(self, name):
        """加载 backend/img/ 下的 SVG 图标并缓存（强制白色填充）"""
        if not hasattr(self, "_svg_cache"):
            self._svg_cache = {}
        if name in self._svg_cache:
            return self._svg_cache[name]

        renderer = None
        try:
            from PySide6.QtSvg import QSvgRenderer
            img_dir = get_resource_path("img")
            svg_path = img_dir / f"{name}.svg"
            # SVG 使用 fill="currentColor"，替换为白色以适配黑色胶囊
            xml = svg_path.read_text(encoding="utf-8").replace("currentColor", "#FFFFFF")
            renderer = QSvgRenderer(xml.encode("utf-8"))
            if not renderer.isValid():
                print(f"[Capsule] SVG 图标无效: {svg_path}")
                renderer = None
        except Exception as e:
            print(f"[Capsule] 加载图标失败 {name}: {e}")

        self._svg_cache[name] = renderer
        return renderer

    def _get_icon_pixmap(self, name, size):
        """将 SVG 图标一次性渲染到 QPixmap 缓存，绘制时直接 drawPixmap

        原实现每帧调用 QSvgRenderer.render()，属于软件光栅化路径，动画期间
        每帧 5+ 个图标累加是主要卡顿来源之一。这里按 (name, 取整尺寸) 缓存
        预渲染好的透明底 QPixmap，绘制成本接近普通图片 blit。
        """
        # 尺寸向上取整到 2 的倍数，减少缓存键数量（视觉差异肉眼不可见）
        s = max(8, int(round(size / 2.0) * 2))
        key = (name, s)
        pm = self._svg_pixmap_cache.get(key)
        if pm is not None:
            return pm

        renderer = self._load_svg_icon(name)
        if renderer is None or not renderer.isValid():
            self._svg_pixmap_cache[key] = None
            return None

        pm = QPixmap(s, s)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        renderer.render(p, QRectF(0, 0, s, s))
        p.end()
        self._svg_pixmap_cache[key] = pm
        return pm

    def set_dimmed(self, dimmed):
        """设置减淡状态"""
        self._dimmed = dimmed
        self.update()

    # --- 事件 ---
    def enterEvent(self, event):
        self._expand()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._collapse()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 注意：_control_zones 存储的是窗口绝对坐标（绘制时 rect 起点
            # 已包含 shadow_margin），因此这里必须直接用 event.position()，
            # 不能再减边距，否则命中区域会比按钮视觉位置偏左上 16px 导致点不中。
            pos = event.position().toPoint()
            for name, zone in self._control_zones.items():
                if zone.contains(pos):
                    self.media_control_clicked.emit(name)
                    event.accept()
                    return
            self.clicked.emit()
            event.accept()


class CapsuleWidget(QMainWindow):
    """胶囊悬浮窗主窗口（灵动岛风格）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LsletUI")
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # 加载配置
        self._config = load_config()

        # 窗口状态
        self._is_dimmed = False
        self._idle_timer = None
        self._side_panel = None
        self._tray_icon = None
        self._smtc_monitor = None
        self._download_monitor = None
        self._bt_monitor = None
        self._settings_window = None
        self._hw_monitor = None
        self._settings_backend = None

        # 拖动相关
        self.drag_position = None
        self._press_pos = None

        # 初始化UI
        self._init_ui()
        self._init_system_tray()
        self._init_settings()
        self._init_idle_timer()
        self._init_smtc()
        self._init_download()
        self._init_bluetooth()
        self._init_hardware()

        # 设置窗口位置
        self._setup_window_geometry()

        # 启用亚克力（需要在窗口句柄创建后）
        # 注意：亚克力效果会让透明背景显示桌面内容，产生白色矩形
        # 如需纯净黑色胶囊，请注释掉下面这行
        # QTimer.singleShot(0, lambda: enable_acrylic(self))

    def _init_ui(self):
        """初始化UI"""
        self.island = DynamicIslandWidget(self._config)
        self.setCentralWidget(self.island)
        self.island.clicked.connect(self._on_capsule_clicked)
        self.island.sizeChanged.connect(self._on_island_size_changed)
        self.island.media_control_clicked.connect(self._on_media_control)

    def _init_smtc(self):
        """初始化 SMTC 音乐监控"""
        try:
            from capsule_app.smtc_monitor_backend import SMTCMonitorBackend
            self._smtc_monitor = SMTCMonitorBackend()
            self._smtc_monitor.music_info_updated.connect(self._on_music_info)
        except Exception as e:
            print(f"[Capsule] SMTC 初始化失败: {e}")

    def _on_music_info(self, info):
        """收到 SMTC 音乐信息更新"""
        self.island.set_music_info(info)

    def _on_media_control(self, command):
        """胶囊上的媒体控制按钮被点击"""
        if self._smtc_monitor:
            self._smtc_monitor.handle_command(command)

    def _init_download(self):
        """初始化全局下载进度监控（浏览器/下载器未完成文件 + History 总大小）"""
        try:
            from capsule_app.download_monitor_backend import DownloadMonitorBackend
            self._download_monitor = DownloadMonitorBackend()
            self._download_monitor.download_updated.connect(self._on_download_info)
        except Exception as e:
            print(f"[Capsule] 下载监控初始化失败: {e}")

    def _on_download_info(self, info):
        """收到下载进度更新"""
        if not self._notify_enabled("notify_download"):
            return
        self.island.set_download_info(info)

    def _init_bluetooth(self):
        """初始化蓝牙耳机连接/断开实时监控"""
        try:
            from capsule_app.bluetooth_backend import BluetoothConnectionMonitor
            self._bt_monitor = BluetoothConnectionMonitor()
            self._bt_monitor.connection_changed.connect(
                self._on_bluetooth_connection)
        except Exception as e:
            print(f"[Capsule] 蓝牙连接监控初始化失败: {e}")

    def _on_bluetooth_connection(self, info):
        """耳机连接/断开：弹出灵动岛通知，并取消可能的闲置减淡"""
        self._reset_idle_timer()
        if not self._notify_enabled("notify_bluetooth"):
            return
        self.island.set_bluetooth_event(info)

    def _init_hardware(self):
        """初始化硬件监控（CPU/内存/GPU/网速/温度，高负载弹出告警）"""
        try:
            from capsule_app.hardware_monitor_backend import HardwareMonitorBackend
            self._hw_monitor = HardwareMonitorBackend()
            self._hw_monitor.alert_changed.connect(self._on_hw_alert)
            self._hw_monitor.stats_updated.connect(self._on_hw_stats)
        except Exception as e:
            print(f"[Capsule] 硬件监控初始化失败: {e}")

    def _on_hw_alert(self, active, stats):
        """高负载开始/结束：弹出或收回硬件告警形态，并取消可能的闲置减淡"""
        self._reset_idle_timer()
        if not self._notify_enabled("notify_hardware"):
            return
        self.island.set_hw_alert(active, stats)

    def _on_hw_stats(self, stats):
        """采样更新：仅在告警展示期间刷新负载条"""
        if self.island.is_hw_alerting():
            self.island.set_hardware_stats(stats)

    def _open_settings_window(self):
        """从侧边栏"高级设置"按钮打开独立设置窗口"""
        if self._settings_window is None:
            from capsule_app.settings_window import SettingsWindow
            self._settings_window = SettingsWindow(
                settings_backend=self._settings_backend)
        # 确保 web_view 已注册（关闭时会注销，重开需重新注册）
        self._settings_backend.set_web_view(self._settings_window.web_view)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _on_island_size_changed(self, w, h):
        """胶囊尺寸变化时，同步窗口大小并保持中心对齐"""
        # 记录当前中心点
        current_center = self.geometry().center()
        # 直接设置窗口大小为 island 的外圈尺寸
        self.setFixedSize(self.island.size())
        # 恢复中心点（仅在拖动未激活时）
        if self.drag_position is None:
            new_geo = self.geometry()
            new_geo.moveCenter(current_center)
            self.setGeometry(new_geo)

    def _setup_window_geometry(self):
        """设置窗口位置 - 顶部居中"""
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()

        anchor = self._config.get("anchor", "top_center")
        w = self.island.width()
        h = self.island.height()

        if anchor == "top_center":
            x = screen_geometry.x() + (screen_geometry.width() - w) // 2
            y = screen_geometry.y() + 10
        else:
            x = screen_geometry.x() + 10
            y = screen_geometry.y() + (screen_geometry.height() - h) // 2

        self.setGeometry(x, y, w, h)

    def _init_system_tray(self):
        """初始化系统托盘图标与菜单。"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self._tray_icon = QSystemTrayIcon(self)
        tray_icon = self.windowIcon()
        if tray_icon.isNull():
            tray_icon = self._load_app_icon()
        if not tray_icon.isNull():
            self._tray_icon.setIcon(tray_icon)

        self._tray_icon.setToolTip("LsletUI")

        tray_menu = QMenu(self)
        show_action = QAction("显示主界面", self)
        show_action.triggered.connect(self._show_from_tray)

        hide_action = QAction("隐藏主界面", self)
        hide_action.triggered.connect(self._hide_to_tray)

        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self._exit_application)

        tray_menu.addAction(show_action)
        tray_menu.addAction(hide_action)
        tray_menu.addSeparator()
        tray_menu.addAction(exit_action)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason not in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            return
        self._show_from_tray()

    def _show_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _hide_to_tray(self):
        if self._side_panel is not None and self._side_panel.isVisible():
            self._side_panel.hide()
        self.hide()

    def _exit_application(self):
        # 停止所有后台监控线程
        if self._smtc_monitor is not None:
            self._smtc_monitor.stop()
        if self._download_monitor is not None:
            self._download_monitor.stop()
        if self._bt_monitor is not None:
            self._bt_monitor.stop()
        if self._hw_monitor is not None:
            self._hw_monitor.stop()
        # 注意：不在此处调用 gc.collect()。各 COM 线程的 stop() 已在
        # 各自套间内 gc.collect() 并 join，主线程做 gc 反而可能跨套间
        # Release 残留 COM 指针 → 0xC0000005 闪退。
        if self._side_panel is not None:
            self._side_panel.close()
        if self._settings_window is not None:
            self._settings_window.close()
        if self._tray_icon is not None:
            self._tray_icon.hide()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def closeEvent(self, event):
        """窗口关闭时确保所有后端线程安全退出，防止崩溃"""
        self._exit_application()
        event.accept()

    def _init_settings(self):
        """初始化用户设置后端（自动减淡等偏好由此驱动）"""
        try:
            from capsule_app.settings_backend import SettingsBackend
            self._settings_backend = SettingsBackend()
            self._settings_backend.settings_changed.connect(self._apply_settings)
        except Exception as e:
            print(f"[Capsule] 设置后端初始化失败: {e}")

    def _apply_settings(self, settings):
        """设置变化时动态生效（无需重启）"""
        if settings.get("auto_dim", True):
            self._init_idle_timer()
        else:
            # 关闭自动减淡：停止计时并立即恢复正常亮度
            if self._idle_timer is not None:
                self._idle_timer.stop()
            if self._is_dimmed:
                self.island.set_dimmed(False)
                self._is_dimmed = False

        # 灵动岛提醒开关关闭时立即收回对应胶囊
        if not settings.get("notify_download", True):
            self.island.set_download_info({"active": False, "state": "idle"})
        if not settings.get("notify_bluetooth", True):
            self.island.dismiss_bluetooth_event()
        if not settings.get("notify_hardware", True):
            self.island.set_hw_alert(False, None)

    def _notify_enabled(self, key):
        """查询某类灵动岛提醒是否开启（设置后端未就绪时默认开启）"""
        if self._settings_backend is None:
            return True
        return self._settings_backend.get_settings().get(key, True)

    def _init_idle_timer(self):
        """初始化/刷新无操作减淡定时器（间隔由设置后端控制）"""
        enabled = True
        delay = self._config.get("auto_hide_delay", 10000)
        if self._settings_backend is not None:
            s = self._settings_backend.get_settings()
            enabled = s.get("auto_dim", True)
            delay = s.get("auto_dim_delay", delay)

        if not enabled or not self._config.get("auto_hide", True):
            if self._idle_timer is not None:
                self._idle_timer.stop()
            return

        if self._idle_timer is None:
            self._idle_timer = QTimer(self)
            self._idle_timer.setSingleShot(True)
            self._idle_timer.timeout.connect(self._on_idle_timeout)
        self._idle_timer.setInterval(int(delay))
        self._idle_timer.start()

    def _reset_idle_timer(self):
        if self._is_dimmed:
            self.island.set_dimmed(False)
            self._is_dimmed = False
        if self._idle_timer is not None:
            self._idle_timer.start()

    def _on_idle_timeout(self):
        if not self._is_dimmed:
            self.island.set_dimmed(True)
            self._is_dimmed = True

    def _on_capsule_clicked(self):
        """胶囊点击事件处理"""
        print("[CapsuleWindow] 点击事件开始")
        try:
            self._reset_idle_timer()

            # 防重复切换：同一点击可能经由子控件 clicked 与主窗口
            # mouseReleaseEvent 两条路径到达，或焦点抖动触发多次，
            # 250ms 内只允许切换一次（否则会出现"点一下又弹回/要点好几次"）。
            now = QDateTime.currentMSecsSinceEpoch()
            if hasattr(self, "_last_toggle_ts") and now - self._last_toggle_ts < 250:
                print("[CapsuleWindow] 点击被防重复机制拦截")
                return
            self._last_toggle_ts = now

            # 如果侧边面板已打开，则关闭
            if self._side_panel is not None and self._side_panel.isVisible():
                print("[CapsuleWindow] 关闭已打开的侧边面板")
                self._side_panel.hide()
                return

            # 打开侧边面板（传入共享的 SMTC/设置实例，避免重复轮询）
            print("[CapsuleWindow] 准备打开侧边面板")
            self._open_side_panel()
            print("[CapsuleWindow] 侧边面板打开完成")
        except Exception as e:
            import traceback
            print(f"[CapsuleWindow] 点击事件处理失败: {e}")
            traceback.print_exc()

    def _open_side_panel(self):
        """打开侧边面板（从胶囊生长出来）"""
        print("[SidePanel] 开始创建侧边面板")
        try:
            if self._side_panel is None:
                print("[SidePanel] 首次创建 SidePanelWidget")
                from capsule_app.side_panel_window import SidePanelWidget
                self._side_panel = SidePanelWidget(
                    smtc=self._smtc_monitor,
                    settings=self._settings_backend)
                print("[SidePanel] SidePanelWidget 创建成功")
                # 前端"高级设置"按钮 → 打开独立设置窗口
                self._side_panel.open_settings_requested.connect(
                    self._open_settings_window)

            screen = QApplication.primaryScreen()
            screen_geometry = screen.availableGeometry()

            panel_width = int(screen_geometry.width() * 0.25)
            panel_height = int(screen_geometry.height() * 0.9)

            capsule_geo = self.geometry()
            capsule_center_x = capsule_geo.center().x()

            # 面板居中于胶囊，但限制在屏幕内
            x = capsule_center_x - panel_width // 2
            x = max(screen_geometry.x() + 10,
                    min(x, screen_geometry.right() - panel_width - 10))
            y = capsule_geo.bottom() + 12

            # 如果下方空间不足，则放在胶囊上方
            if y + panel_height > screen_geometry.bottom() - 10:
                y = max(screen_geometry.y() + 10,
                        capsule_geo.top() - panel_height - 12)

            print(f"[SidePanel] 设置面板位置: {x},{y} {panel_width}x{panel_height}")
            self._side_panel.setGeometry(x, y, panel_width, panel_height)
            print("[SidePanel] 开始显示动画")
            self._side_panel.show_with_animation(capsule_geo.center())
            self._side_panel.raise_()
            print("[SidePanel] 侧边面板显示完成")
        except Exception as e:
            import traceback
            print(f"[SidePanel] 打开侧边面板失败: {e}")
            traceback.print_exc()
            self._side_panel = None

    def mousePressEvent(self, event):
        self._reset_idle_timer()
        if event.button() == Qt.LeftButton:
            global_pos = event.globalPosition().toPoint()
            self.drag_position = global_pos - self.frameGeometry().topLeft()
            self._press_pos = global_pos
            event.accept()

    if sys.platform == "win32":
        def nativeEvent(self, eventType, message):
            """Windows：面板打开时胶囊处于非活动状态，默认情况下
            WM_MOUSEACTIVATE 返回 MA_ACTIVATEANDEAT 会"激活窗口但吞掉第一次点击"，
            表现为面板退不出/要点好几次。这里改为 MA_ACTIVATE：
            激活窗口的同时不吞掉点击，让第一次点击就能正常开关面板。"""
            if eventType == b"windows_generic_MSG":
                try:
                    import ctypes
                    from ctypes import wintypes
                    msg = wintypes.MSG.from_address(int(message))
                    WM_MOUSEACTIVATE = 0x0021
                    MA_ACTIVATE = 1
                    if msg.message == WM_MOUSEACTIVATE:
                        return True, MA_ACTIVATE
                except Exception:
                    pass
            return super().nativeEvent(eventType, message)

    def mouseMoveEvent(self, event):
        self._reset_idle_timer()
        if event.buttons() == Qt.LeftButton and self.drag_position is not None:
            global_pos = event.globalPosition().toPoint()
            new_pos = global_pos - self.drag_position
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._reset_idle_timer()
        if event.button() != Qt.LeftButton:
            return

        global_pos = event.globalPosition().toPoint()
        is_click = False
        if self._press_pos is not None:
            dx = global_pos.x() - self._press_pos.x()
            dy = global_pos.y() - self._press_pos.y()
            if abs(dx) < 5 and abs(dy) < 5:
                is_click = True

        self.drag_position = None
        self._press_pos = None

        if is_click:
            self._on_capsule_clicked()

    def _load_app_icon(self):
        """加载应用图标"""
        from capsule_app.main import APP_ICON_CANDIDATES
        for icon_path in APP_ICON_CANDIDATES:
            if icon_path.exists():
                return QIcon(str(icon_path))
        return QIcon()
