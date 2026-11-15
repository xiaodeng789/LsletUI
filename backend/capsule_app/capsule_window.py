#!/usr/bin/env python3
"""
LsletUI - 轻量级灵动岛应用
iPhone 灵动岛风格胶囊窗口组件
"""

import json
import sys
from pathlib import Path

from PySide6.QtCore import (Qt, QTimer, QSize, QSizeF, QPoint, QPointF,
                            QRect, QRectF, QUrl,
                            QPropertyAnimation, QVariantAnimation, QEasingCurve,
                            Property, QAbstractAnimation, Signal, QDateTime)
from PySide6.QtGui import (QIcon, QColor, QPainter, QBrush, QPen,
                           QPainterPath, QLinearGradient, QFontMetrics,
                           QPixmap, QImage, QDesktopServices)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget,
                               QMessageBox, QSystemTrayIcon, QMenu)
from PySide6.QtGui import QAction

# 导入资源路径兼容模块
import sys as _sys
if not getattr(_sys, 'frozen', False):
    # 开发模式
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from resource_path import get_resource_path, get_config_path

from capsule_app.debug_log import dlog

PROJECT_ROOT = get_resource_path("")
CONFIG_FILE = get_config_path()

# 检测到游戏后，等待首帧帧率数据的宽限时长（毫秒）。
# 超过该时长仍无数据（如用户取消 PresentMon 提权）则兜底切入游戏形态，
# 避免灵动岛「先以空占位的瘦小样式出现、稍后才正常显示帧率」。
GAME_ENTER_GRACE_MS = 2000


def load_config():
    """加载配置"""
    default = {
        "collapsed": {"width": 200, "height": 44},
        "hover": {"width": 240, "height": 52},
        "music_collapsed": {"width": 260, "height": 44},
        "music_hover": {"width": 320, "height": 56},
        # 视频形态：与音乐尺寸相同，但独立配置方便调整
        "video_collapsed": {"width": 280, "height": 44},
        "video_hover": {"width": 340, "height": 56},
        "download_collapsed": {"width": 270, "height": 44},
        "download_hover": {"width": 400, "height": 56},
        "bt_notify": {"width": 300, "height": 64},
        "clipboard_notify": {"width": 310, "height": 48},
        "hw_alert": {"width": 348, "height": 84},
        "calendar_notify": {"width": 320, "height": 64},
        "todo_notify": {"width": 320, "height": 64},
        "call_active": {"width": 248, "height": 44},
        "call_hover": {"width": 310, "height": 56},
        "code_notify": {"width": 320, "height": 56},
        "transfer_notify": {"width": 320, "height": 56},
        # 验证码抓取（Windows 通知中心轮询）
        "code_sniffer": {
            "enabled": True,
            "min_digits": 4,
            "max_digits": 8,
            "poll_interval_ms": 4000,
            "dedup_seconds": 300,
            "ignore_apps": ["LsletUI"],
            "request_access": False,
        },
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
    open_link_requested = Signal(str)  # 剪贴板通知上的"打开"按钮（链接文本）
    calendar_open_requested = Signal(str)  # 日历通知点击：打开 Outlook 约会（EntryID）
    code_copy_requested = Signal()  # 验证码通知点击：复制验证码到剪贴板
    transfer_open_requested = Signal()  # 手机互传完成提示点击：打开接收目录

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

        # 视频形态尺寸（独立于音乐，可配置）
        video_collapsed = config.get("video_collapsed", music_collapsed)
        video_hover = config.get("video_hover", music_hover)
        self._video_collapsed_size = QSize(video_collapsed["width"], video_collapsed["height"])
        self._video_hover_size = QSize(video_hover["width"], video_hover["height"])

        download_collapsed = config.get("download_collapsed", {"width": 270, "height": 44})
        download_hover = config.get("download_hover", {"width": 400, "height": 56})
        self._download_collapsed_size = QSize(download_collapsed["width"], download_collapsed["height"])
        self._download_hover_size = QSize(download_hover["width"], download_hover["height"])

        bt_notify = config.get("bt_notify", {"width": 300, "height": 64})
        self._bt_notify_size = QSize(bt_notify["width"], bt_notify["height"])

        clipboard_notify = config.get(
            "clipboard_notify", {"width": 310, "height": 48})
        self._clipboard_notify_size = QSize(clipboard_notify["width"],
                                            clipboard_notify["height"])

        hw_alert = config.get("hw_alert", {"width": 348, "height": 84})
        self._hw_alert_size = QSize(hw_alert["width"], hw_alert["height"])

        calendar_notify = config.get(
            "calendar_notify", {"width": 320, "height": 64})
        self._calendar_notify_size = QSize(calendar_notify["width"],
                                           calendar_notify["height"])

        # 待办到点提醒形态（与日历通知同尺寸，独立状态）
        todo_notify = config.get("todo_notify", {"width": 320, "height": 64})
        self._todo_notify_size = QSize(todo_notify["width"],
                                       todo_notify["height"])

        # 验证码通知形态（来源 + 验证码 + 点击复制）
        code_notify = config.get("code_notify", {"width": 320, "height": 56})
        self._code_notify_size = QSize(code_notify["width"],
                                       code_notify["height"])

        # 手机互传完成提示形态（与验证码通知同尺寸，独立状态）
        transfer_notify = config.get(
            "transfer_notify", {"width": 320, "height": 56})
        self._transfer_notify_size = QSize(transfer_notify["width"],
                                           transfer_notify["height"])

        call_active = config.get("call_active", {"width": 248, "height": 44})
        call_hover = config.get("call_hover", {"width": 310, "height": 56})
        self._call_active_size = QSize(call_active["width"],
                                       call_active["height"])
        self._call_hover_size = QSize(call_hover["width"],
                                      call_hover["height"])

        # 硬件高负载告警（后端做阈值+迟滞，岛只负责展示与形变）
        self._hw_alert = False
        self._hw_stats = None

        # 游戏帧率（PresentMon 采集，游戏中在岛上直接显示 FPS + 温度/内存）
        self._game_fps = None
        # 游戏形态复用的系统指标（CPU/GPU 温度、内存占用），来源于硬件采样
        self._sys_stats = {}
        game_fps_collapsed = config.get(
            "game_fps_collapsed", {"width": 312, "height": 44})
        game_fps_hover = config.get(
            "game_fps_hover", {"width": 352, "height": 56})
        self._game_fps_collapsed_size = QSize(
            game_fps_collapsed["width"], game_fps_collapsed["height"])
        self._game_fps_hover_size = QSize(
            game_fps_hover["width"], game_fps_hover["height"])

        # 剪贴板复制瞬时通知（dict: kind/preview/url/image/...）
        self._clipboard_event = None
        self._clip_hide_timer = None
        self._clip_icon_scale = 1.0
        self._clipboard_open_url = None
        self._clip_scaled_pixmap = None
        self._clip_scaled_pixmap_key = None

        # 验证码通知（dict: code/source），点击整块即复制
        self._code_event = None
        self._code_hide_timer = None
        self._code_copied = False

        # 手机互传完成提示（dict: name/size/count/dir），点击打开接收目录
        self._transfer_event = None
        self._transfer_hide_timer = None

        # 蓝牙耳机连接/断开瞬时通知（dict: name/connected），仅展示数秒
        self._bt_event = None
        self._bt_hide_timer = None
        self._bt_icon_scale = 1.0

        # 日历下一条日程临近提醒（dict: subject/start/end/location/entry_id）
        self._calendar_event = None
        self._cal_hide_timer = None
        self._cal_icon_scale = 1.0
        self._calendar_open_id = None

        # 待办到点提醒（dict: id/text/remindAt），点击打开控制台待办页
        self._todo_event = None
        self._todo_hide_timer = None
        self._todo_icon_scale = 1.0

        # Teams/微信通话状态（dict: active/app/app_name/started_at/elapsed）
        self._call_info = None
        self._call_end_timer = None
        self._call_icon_scale = 1.0
        self._call_tick_timer = QTimer(self)
        self._call_tick_timer.setInterval(1000)  # 通话计时每秒刷新
        self._call_tick_timer.timeout.connect(self.update)

        # Mora 语音助手状态（dict: state=listening|thinking|speaking/name）
        self._mora_state = None
        self._mora_wave = 0
        self._mora_tick = QTimer(self)
        self._mora_tick.setInterval(200)   # 声波动效 200ms/帧（原 160ms，降低重绘频率）
        self._mora_tick.timeout.connect(self._on_mora_tick)
        mora_state_cfg = config.get("mora_state", {"width": 260, "height": 52})
        self._mora_state_size = QSize(mora_state_cfg["width"],
                                      mora_state_cfg["height"])

        # 音乐信息
        self._music_info = None  # dict: playing/title/artist/thumbnail(b64)
        self._music_thumb = None  # QPixmap
        self._music_thumb_src = None  # 当前封面的 base64，避免每次进度推送重复解码

        # 下载信息（dict: active/state/filename/received/total/speed/count）
        self._download_info = None

        # 下载动画：img/进度条*.svg 五帧循环（未知总大小时的不确定进度）
        self._dl_frame = 0
        self._dl_anim_timer = QTimer(self)
        self._dl_anim_timer.setInterval(160)  # 5 帧 × 160ms = 800ms 一循环（原 120ms，降低重绘频率）
        self._dl_anim_timer.timeout.connect(self._on_dl_anim_tick)

        # 无阴影：阴影边距设为 0
        self._shadow_margin = 0
        self._animated_width = float(self._collapsed_size.width())
        self._animated_height = float(self._collapsed_size.height())

        # 字体缓存（避免每次 paintEvent 创建新 QFont 对象）
        self._font_cache = {}
        # QFontMetrics 缓存（elidedText 高频调用，避免重复构造）
        self._fm_cache = {}

        # 背景直接在 paintEvent 中绘制（阴影为 4 层圆角矩形，无高斯模糊），
        # 动画期间不再因尺寸变化每帧重建 QPixmap 缓存。
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
            "circle_bg_mora": QColor(255, 255, 255, 28),
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

    def _paint_background(self, painter):
        """直接绘制背景：手动柔和阴影 + 主体圆角矩形 + 顶部高光 + 1px 描边

        原实现使用 QGraphicsDropShadowEffect（每帧高斯模糊 blur=28）是卡顿主因；
        后改为 QPixmap 缓存，但动画期间宽高每帧变化导致缓存持续失效、每帧重建
        QPixmap（分配+光栅化）同样开销不小。这里改为每帧直接用 QPainter 绘制
        4 层无模糊圆角矩形阴影 + 主体，绘制量极小（~7 个图元），避免任何离屏
        分配，动画期间稳定 60fps。
        """
        m = float(self._shadow_margin)
        rect = QRectF(m, m, self._animated_width, self._animated_height)
        radius = rect.height() / 2.0

        # --- 无阴影：直接绘制主体圆角矩形 ---
        painter.setPen(Qt.NoPen)

        # --- 主体圆角矩形 ---
        body = QPainterPath()
        body.addRoundedRect(rect, radius, radius)
        alpha = int(self._config.get("background_alpha", 0.92) * 255)
        if self._dimmed:
            alpha = int(alpha * 0.6)
        painter.fillPath(body, QColor(0, 0, 0, alpha))

        # --- 顶部高光（配合液态玻璃，明显加强）---
        highlight = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        highlight.setColorAt(0.0, QColor(255, 255, 255, 26))
        highlight.setColorAt(0.5, QColor(255, 255, 255, 0))
        painter.fillPath(body, QBrush(highlight))

        # --- 底部反光（模拟玻璃下缘的环境反射）---
        bottom_reflect = QLinearGradient(
            rect.bottomLeft(),
            rect.bottomLeft() + QPointF(0, -rect.height() * 0.3))
        bottom_reflect.setColorAt(0.0, QColor(255, 255, 255, 14))
        bottom_reflect.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(body, QBrush(bottom_reflect))

        # --- 1px 描边 ---
        pen = QPen(self._col("stroke"))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(body)

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
        """初始化尺寸动画

        用单个 QSizeF 动画同时驱动宽高，避免原来两个 QPropertyAnimation
        每帧各触发一次 _update_outer_size / sizeChanged.emit / update，
        导致顶层窗口每帧被 DWM  resize 两次（动画卡顿主因）。
        """
        self._size_anim = QPropertyAnimation(self, b"animatedSize", self)
        self._size_anim.setEasingCurve(QEasingCurve.OutCubic)

        # 蓝牙通知图标的弹出（回弹）动画
        self._bt_pop_anim = QPropertyAnimation(self, b"btIconScale", self)
        self._bt_pop_anim.setEasingCurve(QEasingCurve.OutBack)
        self._bt_pop_anim.setDuration(480)

        # 剪贴板通知图标的弹出（回弹）动画
        self._clip_pop_anim = QPropertyAnimation(self, b"clipIconScale", self)
        self._clip_pop_anim.setEasingCurve(QEasingCurve.OutBack)
        self._clip_pop_anim.setDuration(480)

        # 日历通知图标的弹出（回弹）动画
        self._cal_pop_anim = QPropertyAnimation(self, b"calIconScale", self)
        self._cal_pop_anim.setEasingCurve(QEasingCurve.OutBack)
        self._cal_pop_anim.setDuration(480)

        # 待办提醒图标的弹出（回弹）动画
        self._todo_pop_anim = QPropertyAnimation(self, b"todoIconScale", self)
        self._todo_pop_anim.setEasingCurve(QEasingCurve.OutBack)
        self._todo_pop_anim.setDuration(480)

        # 通话状态图标的弹出（回弹）动画
        self._call_pop_anim = QPropertyAnimation(self, b"callIconScale", self)
        self._call_pop_anim.setEasingCurve(QEasingCurve.OutBack)
        self._call_pop_anim.setDuration(480)

    # --- 动画属性 ---
    def _get_animated_size(self):
        return QSizeF(self._animated_width, self._animated_height)

    def _set_animated_size(self, size):
        # 宽高在同一帧内更新，只触发一次窗口 resize 与一次重绘
        self._animated_width = float(size.width())
        self._animated_height = float(size.height())
        self._update_outer_size()
        self.sizeChanged.emit(self._animated_width, self._animated_height)
        self.update()

    animatedSize = Property(QSizeF, _get_animated_size, _set_animated_size)
    sizeChanged = Signal(float, float)

    # --- 蓝牙图标弹出缩放属性 ---
    def _get_bt_icon_scale(self):
        return self._bt_icon_scale

    def _set_bt_icon_scale(self, scale):
        self._bt_icon_scale = float(scale)
        self.update()

    btIconScale = Property(float, _get_bt_icon_scale, _set_bt_icon_scale)

    # --- 剪贴板图标弹出缩放属性 ---
    def _get_clip_icon_scale(self):
        return self._clip_icon_scale

    def _set_clip_icon_scale(self, scale):
        self._clip_icon_scale = float(scale)
        self.update()

    clipIconScale = Property(float, _get_clip_icon_scale, _set_clip_icon_scale)

    # --- 日历图标弹出缩放属性 ---
    def _get_cal_icon_scale(self):
        return self._cal_icon_scale

    def _set_cal_icon_scale(self, scale):
        self._cal_icon_scale = float(scale)
        self.update()

    calIconScale = Property(float, _get_cal_icon_scale, _set_cal_icon_scale)

    # --- 待办提醒图标弹出缩放属性 ---
    def _get_todo_icon_scale(self):
        return self._todo_icon_scale

    def _set_todo_icon_scale(self, scale):
        self._todo_icon_scale = float(scale)
        self.update()

    todoIconScale = Property(float, _get_todo_icon_scale, _set_todo_icon_scale)

    # --- 通话图标弹出缩放属性 ---
    def _get_call_icon_scale(self):
        return self._call_icon_scale

    def _set_call_icon_scale(self, scale):
        self._call_icon_scale = float(scale)
        self.update()

    callIconScale = Property(float, _get_call_icon_scale, _set_call_icon_scale)

    # --- 目标尺寸 ---
    def _download_visible(self):
        """下载胶囊是否可见（下载中 / 暂停 / 完成提示期间）"""
        info = self._download_info
        return bool(info and (info.get("active") or info.get("state") == "completed"))

    def _game_fps_visible(self):
        """游戏帧率胶囊是否可见（检测到游戏即显示，FPS 数据可稍后到达）"""
        info = self._game_fps
        return bool(info and info.get("running"))

    def _current_collapsed_size(self):
        if self._code_event is not None:
            return self._code_notify_size
        if self._transfer_event is not None:
            return self._transfer_notify_size
        if self._clipboard_event is not None:
            return self._clipboard_notify_size
        if self._bt_event is not None:
            return self._bt_notify_size
        if self._calendar_event is not None:
            return self._calendar_notify_size
        if self._todo_event is not None:
            return self._todo_notify_size
        if self._call_info is not None:
            return self._call_active_size
        if self._mora_state is not None:
            return self._mora_state_size
        if self._hw_alert:
            return self._hw_alert_size
        if self._game_fps_visible():
            return self._game_fps_collapsed_size
        if self._download_visible():
            return self._download_collapsed_size
        if self._music_info and self._music_info.get("title"):
            # 视频形态：与音乐互斥，由 media_type 决定
            if self._music_info.get("media_type") == "video":
                return self._video_collapsed_size
            return self._music_collapsed_size
        return self._collapsed_size

    def _current_hover_size(self):
        if self._code_event is not None:
            return self._code_notify_size
        if self._transfer_event is not None:
            return self._transfer_notify_size
        if self._clipboard_event is not None:
            return self._clipboard_notify_size
        if self._bt_event is not None:
            return self._bt_notify_size
        if self._calendar_event is not None:
            return self._calendar_notify_size
        if self._todo_event is not None:
            return self._todo_notify_size
        if self._call_info is not None:
            return self._call_hover_size
        if self._mora_state is not None:
            return self._mora_state_size
        if self._hw_alert:
            return self._hw_alert_size
        if self._game_fps_visible():
            return self._game_fps_hover_size
        if self._download_visible():
            return self._download_hover_size
        if self._music_info and self._music_info.get("title"):
            if self._music_info.get("media_type") == "video":
                return self._video_hover_size
            return self._music_hover_size
        return self._hover_size

    # --- 动画控制 ---
    def _animate_to(self, target_size, duration):
        """动画到目标尺寸（单动画同时驱动宽高，每帧仅一次 resize / 重绘）"""
        self._size_anim.stop()
        self._size_anim.setDuration(duration)
        self._size_anim.setStartValue(
            QSizeF(self._animated_width, self._animated_height))
        self._size_anim.setEndValue(QSizeF(target_size))
        self._size_anim.start()

    def _snap_to(self, target_size):
        """立即切换目标尺寸（无尺寸动画）

        用于形态首次出现时的「直接以正常尺寸呈现」：避免先以旧形态的
        较小尺寸出现、再用动画放大，产生「先瘦小后正常」的观感。
        """
        self._size_anim.stop()
        self._set_animated_size(
            QSizeF(float(target_size.width()), float(target_size.height())))

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

    # --- 媒体信息（音乐 + 视频通用） ---
    def set_music_info(self, info):
        """设置媒体信息（音乐或视频）并触发布局更新"""
        import base64 as _b64
        old_title = (self._music_info or {}).get("title") if self._music_info else None
        old_type = (self._music_info or {}).get("media_type") if self._music_info else None
        self._music_info = info

        thumb_b64 = info.get("thumbnail") if info else None
        # 同一封面不重复解码：视频 1 秒级进度推送时，重复 base64→QImage 解码
        # 会造成明显 CPU 抖动
        if thumb_b64 != self._music_thumb_src:
            self._music_thumb_src = thumb_b64
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

        # 状态/类型变化时，如果当前是收起状态，重新计算尺寸
        new_title = info.get("title") if info else None
        new_type = info.get("media_type") if info else None
        type_changed = (old_type != new_type)
        if self._state == "collapsed" and (old_title != new_title or type_changed):
            self._animate_to(self._current_collapsed_size(), 200)
            # 新歌/新视频出现：短暂展开提示（iPhone 灵动岛标志性行为）
            # （剪贴板/蓝牙瞬时通知展示中不改尺寸，避免内容与尺寸错位）
            if new_title and not old_title and self._clipboard_event is None \
                    and self._bt_event is None \
                    and self._calendar_event is None \
                    and self._todo_event is None \
                    and self._code_event is None \
                    and self._transfer_event is None:
                self._expand(duration=200)
                QTimer.singleShot(2500, self._auto_collapse)
            # 同类型切换但无新标题（极少）：也展开一下
            elif type_changed and self._clipboard_event is None \
                    and self._bt_event is None \
                    and self._code_event is None \
                    and self._transfer_event is None:
                self._expand(duration=200)
                QTimer.singleShot(2000, self._auto_collapse)
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

    # --- 游戏帧率 ---
    def set_game_fps_info(self, info):
        """设置游戏帧率信息（dict: running/fps/process/frame_time）"""
        old_visible = self._game_fps_visible()
        self._game_fps = info if info and info.get("running") else None
        now_visible = self._game_fps_visible()

        if now_visible and not old_visible:
            # 游戏开始：直接切换为瘦小帧率形态（窗口层同步钉到右上角），
            # 不做展开提示，避免遮挡游戏画面；尺寸直接到位，不再从小尺寸放大
            target = (self._current_hover_size() if self._state == "hover"
                      else self._current_collapsed_size())
            self._snap_to(target)
        elif not now_visible and old_visible and self._state == "collapsed":
            self._animate_to(self._current_collapsed_size(), 220)
        self.update()

    def set_system_stats(self, stats):
        """更新游戏形态里展示的系统指标（CPU/GPU 温度、内存占用）

        复用硬件监控的既有采样（约 2s 一次），无游戏形态时只缓存不重绘，
        不额外增加采集或刷新开销。
        """
        if not stats:
            return
        self._sys_stats = {
            "cpu": stats.get("cpu"),
            "cpu_temp": stats.get("cpu_temp"),
            "gpu_temp": stats.get("gpu_temp"),
            "mem": stats.get("mem"),
        }
        if self._game_fps_visible():
            self.update()

    @staticmethod
    def _fmt_temp(value):
        """温度值格式化：拿不到温度时显示 --，不伪造数据"""
        try:
            return f"{int(round(float(value)))}℃"
        except (TypeError, ValueError):
            return "--"

    @staticmethod
    def _fmt_percent(value):
        """百分比格式化：无数据时显示 --"""
        try:
            return f"{int(round(float(value)))}%"
        except (TypeError, ValueError):
            return "--"

    def _paint_game_fps_content(self, painter, rect):
        """绘制游戏帧率：大号 FPS 数字 + 单位 + CPU/GPU 温度 + 内存占用"""
        info = self._game_fps or {}
        stats = self._sys_stats or {}
        fps = float(info.get("fps") or 0)
        alpha = 230 if not self._dimmed else 130

        left, top = rect.left(), rect.top()
        w, h = rect.width(), rect.height()
        pad = 12

        if fps > 0:
            fps_text = str(int(round(fps))) if fps >= 100 else f"{fps:.1f}"
        else:
            # 采集器尚未产出数据（提权中/无输出）时显示占位，避免出现 0.0
            fps_text = "--"
        num_font = self._get_font(19, True)
        fm = self._get_fm(19, True)
        num_w = fm.horizontalAdvance(fps_text)

        painter.setFont(num_font)
        painter.setPen(QColor(255, 255, 255, alpha))
        painter.drawText(QRectF(left + pad, top, num_w + 6, h),
                         Qt.AlignLeft | Qt.AlignVCenter, fps_text)

        unit_x = left + pad + num_w + 5
        unit_fm = self._get_fm(8, True)
        unit_w = unit_fm.horizontalAdvance("FPS")
        painter.setFont(self._get_font(8, True))
        painter.setPen(QColor(255, 255, 255, 150 if not self._dimmed else 90))
        painter.drawText(QRectF(unit_x, top + h * 0.52, unit_w + 2, 14),
                         Qt.AlignLeft | Qt.AlignVCenter, "FPS")

        # FPS 之后依次追加：CPU 温度 / GPU 温度 / 内存占用（无数据时显示 --）
        label_font = self._get_font(8)
        value_font = self._get_font(10, True)
        fm_label = self._get_fm(8)
        fm_value = self._get_fm(10, True)
        label_pen = QColor(255, 255, 255, 140 if not self._dimmed else 85)
        value_pen = QColor(255, 255, 255, 225 if not self._dimmed else 125)

        # CPU：Windows 无可靠的 CPU 温度来源（cpu_temp 恒为 None），
        # 此时显示同一路采样里真实的 CPU 占用率，而不是一直显示 --
        cpu_temp = stats.get("cpu_temp")
        cpu_text = (self._fmt_temp(cpu_temp) if cpu_temp is not None
                    else self._fmt_percent(stats.get("cpu")))
        x = unit_x + unit_w + 10
        groups = (
            ("CPU", cpu_text),
            ("GPU", self._fmt_temp(stats.get("gpu_temp"))),
            ("内存", self._fmt_percent(stats.get("mem"))),
        )
        for index, (label, value) in enumerate(groups):
            if index:
                x += 12
            label_w = fm_label.horizontalAdvance(label)
            painter.setFont(label_font)
            painter.setPen(label_pen)
            painter.drawText(QRectF(x, top, label_w + 1, h),
                             Qt.AlignLeft | Qt.AlignVCenter, label)
            x += label_w + 3
            value_w = fm_value.horizontalAdvance(value)
            painter.setFont(value_font)
            painter.setPen(value_pen)
            painter.drawText(QRectF(x, top, value_w + 2, h),
                             Qt.AlignLeft | Qt.AlignVCenter, value)
            x += value_w

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
            # （剪贴板/蓝牙/日历瞬时通知展示中不改尺寸，避免内容与尺寸错位）
            if self._clipboard_event is None and self._bt_event is None \
                    and self._calendar_event is None \
                    and self._todo_event is None \
                    and self._code_event is None \
                    and self._transfer_event is None:
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

        # 剪贴板通知展示中（更高优先级）：仅记录，不改尺寸，
        # 等剪贴板通知收回后经 _collapse 自然露出蓝牙尺寸
        # （验证码通知优先级最高，同样只记录不抢占）
        if (self._clipboard_event is not None or self._code_event is not None
                or self._transfer_event is not None):
            self._restart_bt_hide_timer()
            self.update()
            return

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

    # --- Mora 语音助手状态形态（聆听中/思考中/朗读中） ---
    def set_mora_state(self, info):
        """Mora 状态变化；info {"state": "listening|thinking|speaking"|None, "name": str}

        state=None 收回。剪贴板/蓝牙瞬时通知展示中仅记录不改尺寸，
        收回后经 _collapse/_expand 自然露出 Mora 形态。
        """
        state = (info or {}).get("state")
        if state is None:
            if self._mora_state is None:
                return
            self._mora_state = None
            self._mora_tick.stop()
            # 被更高优先级瞬时通知压着时不动尺寸
            if (self._code_event is None and self._clipboard_event is None
                    and self._bt_event is None
                    and self._transfer_event is None):
                if self.underMouse():
                    self._expand()
                else:
                    self._collapse()
            self.update()
            return
        self._mora_state = info
        if not self._mora_tick.isActive():
            self._mora_tick.start()
        # 剪贴板/蓝牙/互传通知展示中：仅记录，不改尺寸
        if (self._code_event is not None or self._clipboard_event is not None
                or self._bt_event is not None
                or self._transfer_event is not None):
            self.update()
            return
        self._state = "hover"
        self._animate_to(self._mora_state_size, 240)
        self.update()

    def _on_mora_tick(self):
        """声波动效帧推进"""
        if self._mora_state is None:
            self._mora_tick.stop()
            return
        self._mora_wave = (self._mora_wave + 1) % 6
        self.update()

    def _paint_mora_content(self, painter, rect):
        """绘制 Mora 状态：左侧圆形衬底 + 声波动效 + 状态标题 + 助手名"""
        info = self._mora_state or {}
        state = info.get("state") or "thinking"
        name = info.get("name") or "Mora"
        titles = {"listening": "聆听中…", "thinking": "思考中…",
                  "speaking": "朗读中…"}
        title = titles.get(state, "思考中…")

        left, top = rect.left(), rect.top()
        w, h = rect.width(), rect.height()
        pad = 12

        # 左侧圆形衬底 + 声波动效条（5 根正弦相位错开）
        icon_d = h - 20
        cx = left + pad + icon_d / 2
        cy = top + h / 2
        circle = QRectF(cx - icon_d / 2, cy - icon_d / 2, icon_d, icon_d)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 28))
        painter.drawEllipse(circle)
        painter.setBrush(Qt.NoBrush)

        bars = 5
        bar_w = 2.0
        gap = 2.5
        base_h = icon_d * 0.16
        total_w = bars * bar_w + (bars - 1) * gap
        bx = cx - total_w / 2
        for i in range(bars):
            phase = (self._mora_wave + i) % 6
            frac = 0.35 + 0.65 * (1 - abs(phase - 2.5) / 3.0)   # 0.35~1.0
            bh = base_h * (0.6 + 1.6 * frac)
            bar = QRectF(bx + i * (bar_w + gap), cy - bh / 2, bar_w, bh)
            painter.setBrush(QColor(120, 190, 255, 235))
            painter.drawRoundedRect(bar, bar_w / 2, bar_w / 2)
        painter.setBrush(Qt.NoBrush)

        # 右侧文字：状态标题（蓝）+ 助手名
        text_left = left + pad + icon_d + 12
        text_w = (left + w - pad) - text_left
        painter.setFont(self._get_font(11, True))
        painter.setPen(self._col("accent"))
        painter.drawText(QRectF(text_left, top + h / 2 - 17, text_w, 18),
                         Qt.AlignLeft | Qt.AlignVCenter, title)
        painter.setFont(self._get_font(8.5, False))
        painter.setPen(self._col("text_mid_dim" if self._dimmed else "text_mid"))
        metrics = self._get_fm(8.5, False)
        painter.drawText(
            QRectF(text_left, top + h / 2 + 2, text_w, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            metrics.elidedText(f"{name} · 点击打开对话面板",
                               Qt.ElideRight, int(text_w)))

    # --- 日历下一条日程临近提醒 ---
    CAL_TOAST_MS = 5000  # 临近提醒展示 5 秒

    def set_calendar_event(self, info):
        """下一条日程临近时弹出通知，数秒后自动收回

        info: {"subject", "start", "end", "location", "entry_id", "all_day"}
        """
        self._calendar_open_id = info.get("entry_id")
        self._calendar_event = info

        # 优先级更高的瞬时通知展示中（验证码 / 剪贴板 / 蓝牙）：仅记录不改尺寸，
        # 等其收回后经 _collapse/_expand 自然露出日历形态
        if (self._code_event is not None or self._clipboard_event is not None
                or self._bt_event is not None
                or self._transfer_event is not None):
            self._restart_cal_hide_timer()
            self.update()
            return

        # 打断当前尺寸动画，展开到通知尺寸（灵动岛标志性形变）
        self._state = "hover"
        self._animate_to(self._calendar_notify_size, 320)

        # 图标从 0.35 倍回弹放大
        self._cal_pop_anim.stop()
        self._cal_pop_anim.setStartValue(0.35)
        self._cal_pop_anim.setEndValue(1.0)
        self._cal_pop_anim.start()

        # 连续事件以最后一次为准重新计时
        self._restart_cal_hide_timer()
        self.update()

    def _restart_cal_hide_timer(self):
        """复用日历隐藏定时器（避免每次通知创建新 QTimer 导致泄漏）"""
        if self._cal_hide_timer is None:
            self._cal_hide_timer = QTimer(self)
            self._cal_hide_timer.setSingleShot(True)
            self._cal_hide_timer.timeout.connect(self._dismiss_calendar_event)
        else:
            self._cal_hide_timer.stop()
        self._cal_hide_timer.start(self.CAL_TOAST_MS)

    def _dismiss_calendar_event(self):
        """通知展示结束，回到正常形态"""
        if self._calendar_event is None:
            return
        self._calendar_event = None
        self._calendar_open_id = None
        self._cal_hide_timer = None
        if self.underMouse():
            self._expand()
        else:
            self._collapse()
        self.update()

    def is_calendar_notifying(self):
        """日历通知是否正在展示（点击时打开 Outlook 约会）

        只在日历通知真正可见（更高优先级的剪贴板 / 蓝牙均未展示）时返回 True。
        """
        return (self._calendar_event is not None
                and self._clipboard_event is None
                and self._bt_event is None
                and self._code_event is None
                and self._transfer_event is None)

    def dismiss_calendar_event(self):
        """立即收回日历通知（如点击打开 Outlook 后）"""
        if self._cal_hide_timer is not None:
            self._cal_hide_timer.stop()
        self._dismiss_calendar_event()

    # --- 待办到点提醒 ---
    TODO_TOAST_MS = 6000  # 到点提醒展示 6 秒

    def set_todo_event(self, info):
        """待办到点弹出提醒，数秒后自动收回

        info: {"id", "text", "remindAt"}
        """
        self._todo_event = info

        # 优先级更高的瞬时通知展示中（验证码 / 互传 / 剪贴板 / 蓝牙 / 日历）：
        # 仅记录不改尺寸，等其收回后经 _collapse/_expand 自然露出待办形态
        if (self._code_event is not None or self._transfer_event is not None
                or self._clipboard_event is not None
                or self._bt_event is not None
                or self._calendar_event is not None):
            self._restart_todo_hide_timer()
            self.update()
            return

        # 打断当前尺寸动画，展开到通知尺寸（灵动岛标志性形变）
        self._state = "hover"
        self._animate_to(self._todo_notify_size, 320)

        # 图标从 0.35 倍回弹放大
        self._todo_pop_anim.stop()
        self._todo_pop_anim.setStartValue(0.35)
        self._todo_pop_anim.setEndValue(1.0)
        self._todo_pop_anim.start()

        # 连续事件以最后一次为准重新计时
        self._restart_todo_hide_timer()
        self.update()

    def _restart_todo_hide_timer(self):
        """复用待办隐藏定时器（避免每次通知创建新 QTimer 导致泄漏）"""
        if self._todo_hide_timer is None:
            self._todo_hide_timer = QTimer(self)
            self._todo_hide_timer.setSingleShot(True)
            self._todo_hide_timer.timeout.connect(self._dismiss_todo_event)
        else:
            self._todo_hide_timer.stop()
        self._todo_hide_timer.start(self.TODO_TOAST_MS)

    def _dismiss_todo_event(self):
        """提醒展示结束，回到正常形态"""
        if self._todo_event is None:
            return
        self._todo_event = None
        self._todo_hide_timer = None
        if self.underMouse():
            self._expand()
        else:
            self._collapse()
        self.update()

    def is_todo_notifying(self):
        """待办提醒是否正在展示（点击时打开控制台待办页）

        只在更高优先级的通知均未展示时返回 True。
        """
        return (self._todo_event is not None
                and self._code_event is None
                and self._transfer_event is None
                and self._clipboard_event is None
                and self._bt_event is None
                and self._calendar_event is None)

    def dismiss_todo_event(self):
        """立即收回待办提醒（如点击打开待办页后）"""
        if self._todo_hide_timer is not None:
            self._todo_hide_timer.stop()
        self._dismiss_todo_event()

    # --- Teams/微信通话状态 ---
    CALL_END_TOAST_MS = 3200  # 挂断后"通话结束"展示时长

    def set_call_info(self, info):
        """通话开始/结束（检测与计时在后端），岛负责形变与展示

        info 开始: {active:True, app, app_name, started_at}
        info 结束: {active:False, app, app_name, started_at, ended_at, elapsed}
        """
        active = bool(info and info.get("active"))
        was_active = bool(self._call_info and self._call_info.get("active"))
        transient = (self._code_event is not None
                     or self._clipboard_event is not None
                     or self._bt_event is not None
                     or self._calendar_event is not None
                     or self._transfer_event is not None)

        if active:
            self._call_info = info
            if self._call_end_timer is not None:
                self._call_end_timer.stop()
                self._call_end_timer = None
            if not self._call_tick_timer.isActive():
                self._call_tick_timer.start()

            if transient:
                # 更高优先级瞬时通知展示中：仅记录，收回后自然露出通话形态
                self.update()
                return
            if not was_active:
                # 灵动岛标志性形变：弹出到展开态，2.2s 后自动收起到计时形态
                self._state = "hover"
                self._animate_to(self._call_hover_size, 320)
                self._call_pop_anim.stop()
                self._call_pop_anim.setStartValue(0.35)
                self._call_pop_anim.setEndValue(1.0)
                self._call_pop_anim.start()
                QTimer.singleShot(2200, self._auto_collapse)
            self.update()
            return

        # --- 通话结束：短暂展示"通话结束 + 时长"后收回 ---
        if self._call_info is None:
            return
        if not info.get("app_name"):
            info["app_name"] = self._call_info.get("app_name")
        self._call_info = info
        if self._call_tick_timer.isActive():
            self._call_tick_timer.stop()

        # 结束提示计时独立于当前是否被瞬时通知遮挡
        if self._call_end_timer is None:
            self._call_end_timer = QTimer(self)
            self._call_end_timer.setSingleShot(True)
            self._call_end_timer.timeout.connect(self._dismiss_call_event)
        else:
            self._call_end_timer.stop()
        self._call_end_timer.start(self.CALL_END_TOAST_MS)

        if not transient:
            # 从展开态收落到通话尺寸（收起态已是该尺寸时无视觉跳变）
            self._state = "collapsed"
            self._animate_to(self._call_active_size, 240)
        self.update()

    def _dismiss_call_event(self):
        """结束提示展示完毕，回到正常形态"""
        if self._call_info is None:
            return
        self._call_info = None
        self._call_end_timer = None
        if self._call_tick_timer.isActive():
            self._call_tick_timer.stop()
        if self.underMouse():
            self._expand()
        else:
            self._collapse()
        self.update()

    def is_call_active(self):
        """通话是否正在进行（不含挂断后的结束提示）"""
        return bool(self._call_info and self._call_info.get("active"))

    def clear_call_state(self):
        """清除通话状态（通知关闭时调用）"""
        self._call_info = None
        self._call_end_timer = None
        if self._call_tick_timer.isActive():
            self._call_tick_timer.stop()
        self.update()

    @staticmethod
    def _fmt_elapsed(seconds):
        """秒 -> mm:ss（满 1 小时用 h:mm:ss）"""
        seconds = max(0, int(seconds))
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _call_elapsed(self):
        """当前通话已进行秒数（结束提示里用后端给出的最终 elapsed）"""
        info = self._call_info or {}
        if not info.get("active"):
            return int(info.get("elapsed") or 0)
        import time as _time
        return max(0, int(_time.time() - float(info.get("started_at") or 0)))

    # --- 剪贴板复制通知 ---
    CLIP_TOAST_MS = 2600  # 普通内容展示时长
    CLIP_URL_TOAST_MS = 3400  # 链接（带"打开"按钮）展示时长

    def set_clipboard_event(self, info):
        """复制内容时轻弹通知，数秒后自动收回

        info: {"kind": text|url|file|image, "preview": ..., "url": 链接时有}
        """
        self._clipboard_open_url = info.get("url")
        repeated = self._clipboard_event is not None
        if info.get("kind") == "image" and info.get("image") is not None \
                and "pixmap" not in info:
            info["pixmap"] = QPixmap.fromImage(info["image"])
        self._clipboard_event = info

        if (not repeated and self._code_event is None
                and self._transfer_event is None):
            # 打断当前尺寸动画，轻弹到通知尺寸（灵动岛标志性形变）
            # （验证码/互传通知优先级最高，展示期间不改尺寸）
            self._state = "hover"
            self._animate_to(self._clipboard_notify_size, 260)

            # 图标从 0.35 倍回弹放大
            self._clip_pop_anim.stop()
            self._clip_pop_anim.setStartValue(0.35)
            self._clip_pop_anim.setEndValue(1.0)
            self._clip_pop_anim.start()

        # 连续复制时以最后一次为准重新计时
        ms = self.CLIP_URL_TOAST_MS if info.get("url") else self.CLIP_TOAST_MS
        if self._clip_hide_timer is None:
            self._clip_hide_timer = QTimer(self)
            self._clip_hide_timer.setSingleShot(True)
            self._clip_hide_timer.timeout.connect(self._dismiss_clipboard_event)
        else:
            self._clip_hide_timer.stop()
        self._clip_hide_timer.start(ms)
        self.update()

    def is_clipboard_notifying(self):
        """剪贴板通知是否正在展示（胶囊点击此时打开历史面板）"""
        return self._clipboard_event is not None

    def dismiss_clipboard_event(self):
        """立即收回剪贴板通知（如点击"打开"后）"""
        if self._clip_hide_timer is not None:
            self._clip_hide_timer.stop()
        self._dismiss_clipboard_event()

    def _dismiss_clipboard_event(self):
        """通知展示结束，回到正常形态"""
        if self._clipboard_event is None:
            return
        self._clipboard_event = None
        self._clipboard_open_url = None
        self._clip_hide_timer = None
        self._clip_scaled_pixmap = None
        self._clip_scaled_pixmap_key = None
        if self.underMouse():
            self._expand()
        else:
            self._collapse()
        self.update()

    # --- 验证码通知（点击复制） ---
    CODE_TOAST_MS = 6000  # 验证码展示时长（留足输入时间）
    CODE_COPIED_MS = 1400  # "已复制"反馈停留时长

    def set_code_event(self, info):
        """弹出验证码通知：来源 + 验证码，点击整块复制

        info: {"code": "832941", "source": "QQ邮箱"}
        """
        repeated = self._code_event is not None
        self._code_event = info
        self._code_copied = False
        if not repeated:
            self._state = "hover"
            self._animate_to(self._code_notify_size, 260)
        self._restart_code_hide_timer(self.CODE_TOAST_MS)
        self.update()

    def _restart_code_hide_timer(self, ms):
        if self._code_hide_timer is None:
            self._code_hide_timer = QTimer(self)
            self._code_hide_timer.setSingleShot(True)
            self._code_hide_timer.timeout.connect(self._dismiss_code_event)
        else:
            self._code_hide_timer.stop()
        self._code_hide_timer.start(ms)

    def _dismiss_code_event(self):
        if self._code_event is None:
            return
        self._code_event = None
        self._code_copied = False
        self._code_hide_timer = None
        if self.underMouse():
            self._expand()
        else:
            self._collapse()
        self.update()

    def dismiss_code_event(self):
        """立即收回验证码通知"""
        if self._code_hide_timer is not None:
            self._code_hide_timer.stop()
        self._dismiss_code_event()

    def mark_code_copied(self):
        """复制成功后切换为"已复制"反馈，并缩短停留时间"""
        if self._code_event is None:
            return
        self._code_copied = True
        self._restart_code_hide_timer(self.CODE_COPIED_MS)
        self.update()

    def is_code_notifying(self):
        """验证码通知是否正在展示"""
        return self._code_event is not None

    # --- 手机互传完成提示（点击打开接收目录） ---
    TRANSFER_TOAST_MS = 5200

    def set_transfer_event(self, info):
        """手机传完文件时轻弹提示；info: {"name","size","count","dir"}"""
        if not info:
            return
        self._transfer_event = info
        if self._code_event is None:
            self._state = "hover"
            self._animate_to(self._transfer_notify_size, 260)
        self._restart_transfer_hide_timer(self.TRANSFER_TOAST_MS)
        self.update()

    def _restart_transfer_hide_timer(self, ms):
        if self._transfer_hide_timer is None:
            self._transfer_hide_timer = QTimer(self)
            self._transfer_hide_timer.setSingleShot(True)
            self._transfer_hide_timer.timeout.connect(self._dismiss_transfer_event)
        else:
            self._transfer_hide_timer.stop()
        self._transfer_hide_timer.start(ms)

    def _dismiss_transfer_event(self):
        if self._transfer_event is None:
            return
        self._transfer_event = None
        self._transfer_hide_timer = None
        if self.underMouse():
            self._expand()
        else:
            self._collapse()
        self.update()

    def is_transfer_notifying(self):
        """互传完成提示是否正在展示"""
        return self._transfer_event is not None

    # --- 硬件高负载告警 ---
    def set_hw_alert(self, active, stats):
        """高负载开始/结束（阈值+迟滞在后端），岛负责形变与通知互斥

        验证码/剪贴板/蓝牙瞬时通知展示中只记录不改尺寸，通知收回时经
        _collapse/_expand 自然露出（或离开）硬件形态。
        """
        old = self._hw_alert
        self._hw_alert = active
        self._hw_stats = stats

        if active == old:
            self.update()
            return
        if (self._code_event is not None
                or self._clipboard_event is not None
                or self._bt_event is not None
                or self._calendar_event is not None
                or self._call_info is not None
                or self._transfer_event is not None):
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
        # 背景直接绘制（无离屏 pixmap 缓存），动画期间不产生每帧分配开销
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._paint_background(painter)

        m = self._shadow_margin
        rect = QRectF(m, m, self._animated_width, self._animated_height)

        # 每帧重置媒体控制按钮热区，避免切到其他形态后残留旧坐标导致误触
        # （_paint_control_buttons 绘制音乐按钮时会重新填充）
        self._control_zones = {}

        # 内容（优先级：验证码 > 互传完成 > 剪贴板 > 蓝牙通知 > 日历通知 > 待办提醒 > 通话 > Mora > 硬件告警 > 游戏帧率 > 下载 > 音乐 > 默认）
        if self._code_event is not None:
            self._paint_code_content(painter, rect)
        elif self._transfer_event is not None:
            self._paint_transfer_content(painter, rect)
        elif self._clipboard_event is not None:
            self._paint_clipboard_content(painter, rect)
        elif self._bt_event is not None:
            self._paint_bt_content(painter, rect)
        elif self._calendar_event is not None:
            self._paint_calendar_content(painter, rect)
        elif self._todo_event is not None:
            self._paint_todo_content(painter, rect)
        elif self._call_info is not None:
            self._paint_call_content(painter, rect)
        elif self._mora_state is not None:
            self._paint_mora_content(painter, rect)
        elif self._hw_alert:
            self._paint_hw_content(painter, rect)
        elif self._game_fps_visible():
            self._paint_game_fps_content(painter, rect)
        elif self._download_visible():
            self._paint_download_content(painter, rect)
        elif self._music_info and self._music_info.get("title"):
            # 视频形态与音乐互斥，由 media_type 决定
            if self._music_info.get("media_type") == "video":
                self._paint_video_content(painter, rect)
            else:
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

    # --- 日历临近提醒绘制 ---
    def _paint_calendar_content(self, painter, rect):
        """绘制日历通知：圆形日历图标 + 标题 + 时间/地点 + 右侧"›"打开提示"""
        from datetime import datetime, timedelta
        info = self._calendar_event or {}
        subject = info.get("subject") or "(无标题)"
        location = info.get("location") or ""
        start = info.get("start")
        end = info.get("end")
        all_day = bool(info.get("all_day"))

        left, top = rect.left(), rect.top()
        w, h = rect.width(), rect.height()
        pad = 12

        # 左侧圆形衬底 + 日历图标（图标带弹出缩放）
        icon_d = h - 20
        cx = left + pad + icon_d / 2
        cy = top + h / 2
        circle = QRectF(cx - icon_d / 2, cy - icon_d / 2, icon_d, icon_d)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 30))
        painter.drawEllipse(circle)
        painter.setBrush(Qt.NoBrush)

        side = icon_d * 0.5 * max(0.0, self._cal_icon_scale)
        if side > 1:
            pm = self._get_icon_pixmap("日历", side)
            if pm is not None:
                painter.drawPixmap(QRectF(cx - side / 2, cy - side / 2,
                                          side, side), pm, QRectF(pm.rect()))

        # 右侧"›"打开提示（点击通知任意位置可在 Outlook 中打开该约会）
        hint_x = left + w - pad
        hint_font = painter.font()
        hint_font.setPointSize(14)
        hint_font.setBold(True)
        painter.setFont(hint_font)
        painter.setPen(QColor(255, 255, 255, 140 if not self._dimmed else 90))
        painter.drawText(QRectF(hint_x - 16, top, 16, h),
                         Qt.AlignRight | Qt.AlignVCenter, "›")

        # 文字区
        text_left = left + pad + icon_d + 12
        text_right = hint_x - 18
        text_w = text_right - text_left

        # 时间文案
        now = datetime.now()
        if start is not None and end is not None:
            if all_day:
                if start.date() == now.date():
                    time_text = "今天全天"
                elif start.date() == (now + timedelta(days=1)).date():
                    time_text = "明天全天"
                else:
                    time_text = start.strftime("%m-%d") + " 全天"
            elif end < now:
                time_text = "已结束"
            elif start <= now <= end:
                time_text = "进行中"
            else:
                secs = (start - now).total_seconds()
                mins = int(secs // 60)
                if mins < 1:
                    time_text = "即将开始"
                elif mins < 60:
                    time_text = f"{mins} 分钟后"
                else:
                    hours = mins // 60
                    if hours < 24:
                        mins_remain = mins % 60
                        time_text = (f"{hours} 小时后"
                                     if mins_remain == 0
                                     else f"{hours} 小时 {mins_remain} 分后")
                    else:
                        time_text = start.strftime("%m-%d %H:%M")
        else:
            time_text = ""

        # 标题
        has_sub = bool(time_text or location)
        title_font = painter.font()
        title_font.setPointSize(11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255, 235 if not self._dimmed else 140))
        metrics = QFontMetrics(title_font)
        if has_sub:
            painter.drawText(QRectF(text_left, top + h / 2 - 17, text_w, 18),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             metrics.elidedText(subject, Qt.ElideRight,
                                                int(text_w)))
        else:
            painter.drawText(QRectF(text_left, top, text_w, h),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             metrics.elidedText(subject, Qt.ElideRight,
                                                int(text_w)))

        # 副标题：时间 · 地点
        if has_sub:
            sub_font = painter.font()
            sub_font.setPointSize(8.5)
            sub_font.setBold(False)
            painter.setFont(sub_font)
            painter.setPen(QColor(255, 255, 255, 165 if not self._dimmed else 100))
            sub_metrics = QFontMetrics(sub_font)
            sub_text = time_text
            if location:
                sub_text = (sub_text + " · " + location) if sub_text else location
            painter.drawText(
                QRectF(text_left, top + h / 2 + 2, text_w, 14),
                Qt.AlignLeft | Qt.AlignVCenter,
                sub_metrics.elidedText(sub_text, Qt.ElideRight, int(text_w)))

    # --- 待办到点提醒绘制 ---
    def _paint_todo_content(self, painter, rect):
        """绘制待办提醒：圆形时钟图标 + 待办内容 + 提醒时间 + 右侧"›"打开提示"""
        from datetime import datetime
        info = self._todo_event or {}
        text = info.get("text") or "待办事项"
        ts = info.get("remindAt")

        left, top = rect.left(), rect.top()
        w, h = rect.width(), rect.height()
        pad = 12

        # 左侧圆形衬底 + 时钟图标（图标带弹出缩放）
        icon_d = h - 20
        cx = left + pad + icon_d / 2
        cy = top + h / 2
        circle = QRectF(cx - icon_d / 2, cy - icon_d / 2, icon_d, icon_d)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 30))
        painter.drawEllipse(circle)
        painter.setBrush(Qt.NoBrush)

        side = icon_d * 0.5 * max(0.0, self._todo_icon_scale)
        if side > 1:
            pm = self._get_icon_pixmap("提醒", side)
            if pm is not None:
                painter.drawPixmap(QRectF(cx - side / 2, cy - side / 2,
                                          side, side), pm, QRectF(pm.rect()))

        # 右侧"›"打开提示（点击整块在控制台待办页打开）
        hint_x = left + w - pad
        hint_font = painter.font()
        hint_font.setPointSize(14)
        hint_font.setBold(True)
        painter.setFont(hint_font)
        painter.setPen(QColor(255, 255, 255, 140 if not self._dimmed else 90))
        painter.drawText(QRectF(hint_x - 16, top, 16, h),
                         Qt.AlignRight | Qt.AlignVCenter, "›")

        # 文字区
        text_left = left + pad + icon_d + 12
        text_w = (hint_x - 18) - text_left

        time_text = ""
        if ts:
            try:
                dt = datetime.fromtimestamp(int(ts) / 1000)
                if dt.date() == datetime.now().date():
                    time_text = dt.strftime("%H:%M")
                else:
                    time_text = dt.strftime("%m-%d %H:%M")
            except (TypeError, ValueError, OSError):
                time_text = ""

        title_font = painter.font()
        title_font.setPointSize(11)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255, 235 if not self._dimmed else 140))
        metrics = QFontMetrics(title_font)
        painter.drawText(QRectF(text_left, top + h / 2 - 17, text_w, 18),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         metrics.elidedText(text, Qt.ElideRight, int(text_w)))

        if time_text:
            sub_font = painter.font()
            sub_font.setPointSize(8.5)
            sub_font.setBold(False)
            painter.setFont(sub_font)
            painter.setPen(QColor(255, 255, 255, 165 if not self._dimmed else 100))
            sub_metrics = QFontMetrics(sub_font)
            painter.drawText(
                QRectF(text_left, top + h / 2 + 2, text_w, 14),
                Qt.AlignLeft | Qt.AlignVCenter,
                sub_metrics.elidedText(f"提醒 {time_text}",
                                       Qt.ElideRight, int(text_w)))

    # --- 通话状态绘制 ---
    def _paint_call_content(self, painter, rect):
        """绘制 Teams/微信通话：电话图标(+绿点) + App 名/状态 + 通话时长"""
        info = self._call_info or {}
        active = bool(info.get("active"))
        app_name = info.get("app_name") or "语音通话"
        time_text = self._fmt_elapsed(self._call_elapsed())

        left, top = rect.left(), rect.top()
        w, h = rect.width(), rect.height()
        pad = 12

        # 左侧圆形衬底 + 电话图标（挂断后的结束提示里图标半透明）
        icon_d = h - 14
        cx = left + pad + icon_d / 2
        cy = top + h / 2
        circle = QRectF(cx - icon_d / 2, cy - icon_d / 2, icon_d, icon_d)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 30 if active else 20))
        painter.drawEllipse(circle)
        painter.setBrush(Qt.NoBrush)

        side = icon_d * 0.52 * max(0.0, self._call_icon_scale)
        if side > 1:
            pm = self._get_icon_pixmap("通话", side)
            if pm is not None:
                painter.save()
                if not active:
                    painter.setOpacity(0.55)
                painter.drawPixmap(QRectF(cx - side / 2, cy - side / 2,
                                          side, side), pm, QRectF(pm.rect()))
                painter.restore()

        if active:
            # 图标右下角绿色圆点：麦克风占用中（与系统麦克风指示灯同义）
            dot_d = 8.5
            dx = cx + icon_d / 2 - dot_d + 2
            dy = cy + icon_d / 2 - dot_d + 2
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(10, 10, 12, 235))  # 深色描边圈
            painter.drawEllipse(QRectF(dx - 1.0, dy - 1.0,
                                       dot_d + 2.0, dot_d + 2.0))
            painter.setBrush(QColor(48, 209, 88))
            painter.drawEllipse(QRectF(dx, dy, dot_d, dot_d))
            painter.setBrush(Qt.NoBrush)

        text_left = left + pad + icon_d + 10
        text_right = left + w - pad
        dim_alpha = 230 if not self._dimmed else 130

        if self._state == "hover":
            # 右侧大号计时
            time_w = 88.0
            timer_font = painter.font()
            timer_font.setPointSize(15)
            timer_font.setBold(True)
            painter.setFont(timer_font)
            painter.setPen(QColor(48, 209, 88) if active
                           else QColor(255, 255, 255, dim_alpha))
            painter.drawText(QRectF(text_right - time_w, top, time_w, h),
                             Qt.AlignRight | Qt.AlignVCenter, time_text)

            col_w = (text_right - time_w - 10) - text_left
            title = app_name if active else "通话结束"
            title_font = painter.font()
            title_font.setPointSize(11)
            title_font.setBold(True)
            painter.setFont(title_font)
            painter.setPen(QColor(255, 255, 255, dim_alpha) if active
                           else QColor(255, 128, 128))
            metrics = QFontMetrics(title_font)
            painter.drawText(QRectF(text_left, top + h / 2 - 17, col_w, 18),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             metrics.elidedText(title, Qt.ElideRight,
                                                int(col_w)))

            sub_font = painter.font()
            sub_font.setPointSize(8.5)
            sub_font.setBold(False)
            painter.setFont(sub_font)
            painter.setPen(QColor(255, 255, 255,
                                  165 if not self._dimmed else 100))
            sub_text = "麦克风使用中" if active else app_name
            painter.drawText(QRectF(text_left, top + h / 2 + 2, col_w, 14),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             QFontMetrics(sub_font).elidedText(
                                 sub_text, Qt.ElideRight, int(col_w)))
        else:
            # 收起态：标题 + 右侧计时
            time_w = 64.0
            timer_font = painter.font()
            timer_font.setPointSize(12)
            timer_font.setBold(True)
            painter.setFont(timer_font)
            painter.setPen(QColor(48, 209, 88) if active
                           else QColor(255, 255, 255, dim_alpha))
            painter.drawText(QRectF(text_right - time_w, top, time_w, h),
                             Qt.AlignRight | Qt.AlignVCenter, time_text)

            col_w = (text_right - time_w - 8) - text_left
            title = app_name if active else "通话结束"
            title_font = painter.font()
            title_font.setPointSize(10)
            title_font.setBold(True)
            painter.setFont(title_font)
            painter.setPen(QColor(255, 255, 255, dim_alpha) if active
                           else QColor(255, 128, 128))
            metrics = QFontMetrics(title_font)
            painter.drawText(QRectF(text_left, top, col_w, h),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             metrics.elidedText(title, Qt.ElideRight,
                                                int(col_w)))

    # --- 验证码通知绘制 ---
    def _paint_code_content(self, painter, rect):
        """绘制验证码通知：锁形图标 + 来源 + 右侧大号验证码（整块可点击复制）"""
        info = self._code_event or {}
        source = info.get("source") or "通知"
        code = info.get("code") or ""
        copied = self._code_copied

        left, top = rect.left(), rect.top()
        w, h = rect.width(), rect.height()
        pad = 12

        # 整块都是"点击复制"热区
        self._control_zones["copy_code"] = QRect(
            int(rect.left()), int(rect.top()), int(w), int(h))

        # 左侧圆形衬底 + 锁图标
        icon_d = h - 20
        cx = left + pad + icon_d / 2
        cy = top + h / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 30))
        painter.drawEllipse(QRectF(cx - icon_d / 2, cy - icon_d / 2,
                                   icon_d, icon_d))
        painter.setBrush(Qt.NoBrush)

        side = icon_d * 0.52
        pm = self._get_icon_pixmap("上锁", side)
        if pm is not None:
            painter.drawPixmap(QRectF(cx - side / 2, cy - side / 2,
                                      side, side), pm, QRectF(pm.rect()))

        # 右侧验证码胶囊
        code_font = painter.font()
        code_font.setPointSize(15)
        code_font.setBold(True)
        if hasattr(code_font, "setFamilies"):
            code_font.setFamilies(["Consolas", "Cascadia Mono", "Microsoft YaHei UI"])
        code_metrics = QFontMetrics(code_font)
        block_w = max(78.0, float(code_metrics.horizontalAdvance(code)) + 22.0)
        block_h = 30.0
        block = QRectF(left + w - pad - block_w, cy - block_h / 2,
                       block_w, block_h)

        pill = QPainterPath()
        pill.addRoundedRect(block, 8, 8)
        if copied:
            painter.fillPath(pill, QColor(48, 209, 88, 40))
        else:
            painter.fillPath(pill, QColor(255, 255, 255, 26))

        painter.setFont(code_font)
        painter.setPen(QColor(48, 209, 88) if copied
                       else QColor(255, 214, 102))
        painter.drawText(block, Qt.AlignCenter, code)

        # 左侧文字：来源 + 操作提示
        text_left = left + pad + icon_d + 10
        text_right = block.left() - 10
        text_w = max(40.0, text_right - text_left)

        title_font = painter.font()
        title_font.setPointSize(10.5)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255, 230 if not self._dimmed else 130))
        painter.drawText(
            QRectF(text_left, top + h / 2 - 17, text_w, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            QFontMetrics(title_font).elidedText(source, Qt.ElideRight,
                                                int(text_w)))

        sub_font = painter.font()
        sub_font.setPointSize(8.5)
        sub_font.setBold(False)
        painter.setFont(sub_font)
        painter.setPen(QColor(48, 209, 88) if copied
                       else QColor(255, 255, 255, 165 if not self._dimmed else 100))
        painter.drawText(QRectF(text_left, top + h / 2 + 2, text_w, 14),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         "已复制 ✓" if copied else "验证码 · 点击复制")

    # --- 手机互传完成提示绘制 ---
    @staticmethod
    def _fmt_size(num):
        try:
            num = float(num)
        except (TypeError, ValueError):
            return "--"
        for unit in ("B", "KB", "MB", "GB"):
            if num < 1024 or unit == "GB":
                return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
            num /= 1024.0
        return f"{num:.1f} GB"

    def _paint_transfer_content(self, painter, rect):
        """绘制互传完成提示：下载图标 + 文件名 + 右侧「打开」按钮"""
        info = self._transfer_event or {}
        name = info.get("name") or "文件"
        count = int(info.get("count") or 1)
        size = info.get("size") or 0
        action = info.get("action") or "打开"

        left, top = rect.left(), rect.top()
        w, h = rect.width(), rect.height()
        pad = 12

        self._control_zones["open_transfer"] = QRect(
            int(rect.left()), int(rect.top()), int(w), int(h))

        icon_d = h - 20
        cx = left + pad + icon_d / 2
        cy = top + h / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 30))
        painter.drawEllipse(QRectF(cx - icon_d / 2, cy - icon_d / 2,
                                   icon_d, icon_d))
        painter.setBrush(Qt.NoBrush)

        side = icon_d * 0.52
        pm = self._get_icon_pixmap("下载", side)
        if pm is not None:
            painter.drawPixmap(QRectF(cx - side / 2, cy - side / 2,
                                      side, side), pm, QRectF(pm.rect()))

        # 右侧「打开」胶囊
        btn_font = painter.font()
        btn_font.setPointSize(9.5)
        btn_font.setBold(True)
        btn_metrics = QFontMetrics(btn_font)
        block_w = float(btn_metrics.horizontalAdvance(action)) + 26.0
        block = QRectF(left + w - pad - block_w, cy - 14, block_w, 28)
        pill = QPainterPath()
        pill.addRoundedRect(block, 8, 8)
        painter.fillPath(pill, QColor(76, 154, 255, 40))
        painter.setFont(btn_font)
        painter.setPen(QColor(76, 154, 255))
        painter.drawText(block, Qt.AlignCenter, action)

        # 左侧文字：标题 + 文件信息
        text_left = left + pad + icon_d + 10
        text_w = max(40.0, block.left() - 10 - text_left)
        title_font = painter.font()
        title_font.setPointSize(10.5)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255, 230 if not self._dimmed else 130))
        painter.drawText(
            QRectF(text_left, top + h / 2 - 17, text_w, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            QFontMetrics(title_font).elidedText(
                info.get("title") or
                (f"手机互传 · {count} 个文件" if count > 1 else "手机互传"),
                Qt.ElideRight, int(text_w)))

        sub_font = painter.font()
        sub_font.setPointSize(8.5)
        sub_font.setBold(False)
        painter.setFont(sub_font)
        painter.setPen(QColor(255, 255, 255, 165 if not self._dimmed else 100))
        painter.drawText(
            QRectF(text_left, top + h / 2 + 2, text_w, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            QFontMetrics(sub_font).elidedText(
                info.get("subtitle") or f"{name} · {self._fmt_size(size)}",
                Qt.ElideMiddle, int(text_w)))

    # --- 剪贴板复制通知绘制 ---
    def _paint_clipboard_content(self, painter, rect):
        """绘制复制通知：圆形图标 + 内容预览（链接时右侧带"打开"按钮）"""
        info = self._clipboard_event or {}
        kind = info.get("kind", "text")
        preview = info.get("preview") or ""
        url = info.get("url")

        left, top = rect.left(), rect.top()
        w, h = rect.width(), rect.height()
        pad = 10

        # 左侧圆形衬底 + 图标（图片内容直接显示缩略图）
        icon_d = h - 14
        cx = left + pad + icon_d / 2
        cy = top + h / 2
        circle = QRectF(cx - icon_d / 2, cy - icon_d / 2, icon_d, icon_d)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 30))
        painter.drawEllipse(circle)
        painter.setBrush(Qt.NoBrush)

        pm = info.get("pixmap") if kind == "image" else None
        if pm is not None and not pm.isNull():
            # 缩略图按圆形裁切铺满（缓存缩放结果，避免每帧 SmoothTransformation）
            side = icon_d - 4
            cache_key = (id(pm), int(side))
            if self._clip_scaled_pixmap_key != cache_key:
                self._clip_scaled_pixmap = pm.scaled(
                    int(side * 2), int(side * 2),
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation)
                self._clip_scaled_pixmap_key = cache_key
            scaled = self._clip_scaled_pixmap
            painter.save()
            clip = QPainterPath()
            clip.addEllipse(circle.adjusted(2, 2, -2, -2))
            painter.setClipPath(clip)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap(QRectF(cx - side / 2, cy - side / 2,
                                      side, side),
                               scaled, QRectF(scaled.rect()))
            painter.restore()
        else:
            side = icon_d * 0.5 * max(0.0, self._clip_icon_scale)
            if side > 1:
                pm_copy = self._get_icon_pixmap("复制", side)
                if pm_copy is not None:
                    painter.drawPixmap(QRectF(cx - side / 2, cy - side / 2,
                                              side, side),
                                       pm_copy, QRectF(pm_copy.rect()))

        text_left = left + pad + icon_d + 10
        text_right = left + w - pad

        # 右侧动作区
        if url:
            pill_w, pill_h = 46.0, 22.0
            pill = QRectF(text_right - pill_w, cy - pill_h / 2, pill_w, pill_h)
            pill_path = QPainterPath()
            pill_path.addRoundedRect(pill, pill_h / 2, pill_h / 2)
            painter.fillPath(pill_path, QColor(255, 255, 255, 34))
            painter.setFont(self._get_font(8.5, bold=True))
            painter.setPen(QColor(255, 255, 255, 235 if not self._dimmed else 140))
            painter.drawText(pill, Qt.AlignCenter, "打开")
            # 点击热区（窗口绝对坐标，外扩 4px，与 _paint_control_buttons 一致）
            p = 4
            self._control_zones["open_link"] = QRect(
                int(pill.left()) - p, int(pill.top()) - p,
                int(pill.width()) + p * 2, int(pill.height()) + p * 2)
            text_right = pill.left() - 8
        elif self._state == "hover":
            # 悬停提示：点击胶囊任意处查看历史
            hint_w = 52.0
            painter.setFont(self._get_font(8))
            painter.setPen(QColor(255, 255, 255, 120 if not self._dimmed else 80))
            painter.drawText(QRectF(text_right - hint_w, top, hint_w, h),
                             Qt.AlignRight | Qt.AlignVCenter, "历史 ›")
            text_right -= hint_w + 6

        text_w = text_right - text_left

        f = self._get_font(10, bold=(kind == "url"))
        painter.setFont(f)
        painter.setPen(QColor(255, 255, 255, 235 if not self._dimmed else 140))
        metrics = QFontMetrics(f)
        elide = Qt.ElideMiddle if kind == "url" else Qt.ElideRight
        painter.drawText(QRectF(text_left, top, text_w, h),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         metrics.elidedText(preview, elide, int(text_w)))

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

    # --- 视频内容绘制 ---
    @staticmethod
    def _fmt_media_time(ms):
        """毫秒 → mm:ss（满 1 小时用 h:mm:ss）"""
        ms = max(0, int(ms or 0))
        total_s = ms // 1000
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _paint_video_content(self, painter, rect):
        """绘制视频信息：左侧缩略图 + 播放图标 + 标题 + 平台/UP主 + 进度条"""
        left = rect.left()
        top = rect.top()
        w = rect.width()
        h = rect.height()
        pad = 10

        info = self._music_info or {}
        title = info.get("title", "")
        artist = info.get("artist", "")        # 视频里通常是 UP主/频道名
        platform = info.get("platform", "")     # 识别到的平台名，如 "哔哩哔哩"
        playing = info.get("playing", False)
        position_ms = info.get("position_ms") or 0
        duration_ms = info.get("duration_ms") or 0

        # 视频进度百分比（有 duration 时才绘制）
        progress_frac = 0.0
        if duration_ms > 0 and position_ms > 0:
            progress_frac = max(0.0, min(float(position_ms) / float(duration_ms), 1.0))

        # 缩略图区域（圆形封面 + 中央播放小三角）
        thumb_size = int(h - 8)
        thumb_x = left + pad
        thumb_y = top + (h - thumb_size) / 2

        # 先画缩略图（如果有封面）
        if self._music_thumb and not self._music_thumb.isNull():
            painter.drawPixmap(QRectF(thumb_x, thumb_y, thumb_size, thumb_size),
                               self._music_thumb,
                               QRectF(self._music_thumb.rect()))
            # 视频缩略图上叠一层半透明深色 + 播放三角，增强视频感
            painter.setPen(Qt.NoPen)
            path = QPainterPath()
            path.addEllipse(thumb_x, thumb_y, thumb_size, thumb_size)
            painter.fillPath(path, QColor(0, 0, 0, 60))
            painter.setBrush(Qt.NoBrush)

            # 中央播放小三角（白底）
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 220))
            cx = thumb_x + thumb_size / 2
            cy = thumb_y + thumb_size / 2
            tri_size = thumb_size * 0.28
            tri_path = QPainterPath()
            tri_path.moveTo(cx - tri_size * 0.35, cy - tri_size * 0.6)
            tri_path.lineTo(cx + tri_size * 0.75, cy)
            tri_path.lineTo(cx - tri_size * 0.35, cy + tri_size * 0.6)
            tri_path.closeSubpath()
            painter.drawPath(tri_path)
            painter.setBrush(Qt.NoBrush)
        else:
            # 无封面：圆形衬底 + ▶ 视频图标
            path = QPainterPath()
            path.addEllipse(thumb_x, thumb_y, thumb_size, thumb_size)
            painter.fillPath(path, QColor(255, 255, 255, 30))
            painter.setPen(QColor(255, 255, 255, 200))
            f = painter.font()
            f.setPointSize(int(thumb_size * 0.5))
            painter.setFont(f)
            painter.drawText(QRectF(thumb_x, thumb_y, thumb_size, thumb_size),
                             Qt.AlignCenter, "▶")

        # 文字区域
        text_left = thumb_x + thumb_size + 10
        text_width = w - (text_left - left) - pad

        # 根据状态决定是否显示控制按钮
        show_controls = (self._state == "hover")
        btn_w = 32 if show_controls else 0
        btn_gap = 6 if show_controls else 0
        text_width -= (btn_w * 3 + btn_gap * 2 + 8) if show_controls else 0

        # 标题
        title_font = painter.font()
        title_font.setPointSize(10)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255, 230 if not self._dimmed else 130))
        title_metrics = QFontMetrics(title_font)
        elided_title = title_metrics.elidedText(title, Qt.ElideRight, int(text_width))

        # 第二行文字：平台名 + UP主/频道
        second_line_parts = []
        if platform:
            second_line_parts.append(f"· {platform}")
        if artist:
            second_line_parts.append(artist)
        second_line = "  ".join(second_line_parts)

        has_second = bool(second_line)

        title_rect = QRectF(
            text_left,
            top + (h - 18) / 2 - (10 if has_second else -8),
            text_width, 18
        )
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_title)

        # 第二行（平台 + UP主）
        if has_second:
            second_font = painter.font()
            second_font.setPointSize(8)
            second_font.setBold(False)
            painter.setFont(second_font)
            # 平台名用稍亮的蓝白色，UP主用次亮
            painter.setPen(QColor(255, 255, 255, 150 if not self._dimmed else 90))
            second_metrics = QFontMetrics(second_font)
            elided_second = second_metrics.elidedText(second_line, Qt.ElideRight, int(text_width))
            second_rect = QRectF(text_left, title_rect.bottom() - 2, text_width, 14)
            painter.drawText(second_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_second)

        # 控制按钮（hover 时显示，与音乐共用）
        if show_controls:
            self._paint_control_buttons(painter, rect, btn_w, btn_gap, playing)

        # 进度条：hover 且有 duration 时显示（在文字与按钮之间的区域底部）
        if show_controls and progress_frac > 0:
            bar_h = 3.0
            bar_y = rect.bottom() - pad / 2 - bar_h
            bar_left = text_left
            bar_right = rect.right() - pad - (btn_w * 3 + btn_gap * 2 + 8)
            bar_total_w = bar_right - bar_left
            if bar_total_w > 40:
                # 背景
                painter.setPen(Qt.NoPen)
                bar_path = QPainterPath()
                bar_path.addRoundedRect(
                    QRectF(bar_left, bar_y, bar_total_w, bar_h),
                    bar_h / 2, bar_h / 2)
                painter.fillPath(bar_path, QColor(255, 255, 255, 38))
                # 已播放
                fill_path = QPainterPath()
                fill_path.addRoundedRect(
                    QRectF(bar_left, bar_y, bar_total_w * progress_frac, bar_h),
                    bar_h / 2, bar_h / 2)
                painter.fillPath(fill_path, QColor(255, 255, 255, 220))
                # 时间（右下角，很小）
                time_font = painter.font()
                time_font.setPointSize(7)
                painter.setFont(time_font)
                painter.setPen(QColor(255, 255, 255, 120 if not self._dimmed else 70))
                time_text = f"{self._fmt_media_time(position_ms)} / {self._fmt_media_time(duration_ms)}"
                time_metrics = QFontMetrics(time_font)
                painter.drawText(
                    QRectF(bar_left, bar_y - 12, bar_total_w, 12),
                    Qt.AlignRight | Qt.AlignVCenter, time_text)

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
                    if name == "open_link":
                        self.open_link_requested.emit(
                            self._clipboard_open_url or "")
                    elif name == "copy_code":
                        self.code_copy_requested.emit()
                    elif name == "open_transfer":
                        self.transfer_open_requested.emit()
                    else:
                        self.media_control_clicked.emit(name)
                    event.accept()
                    return
            self.clicked.emit()
            event.accept()


class CapsuleWidget(QMainWindow):
    """胶囊悬浮窗主窗口（灵动岛风格）"""

    def moveEvent(self, event):
        """阻止窗口移动 - 强制回到锚点位置"""
        # 如果锚点已设置，强制窗口回到锚点位置（含游戏模式右上角锚点
        # 与锚点切换滑动偏移，统一走 _apply_anchor_position）
        if hasattr(self, '_anchor_x') and self._anchor_x is not None:
            # 使用 QTimer 延迟设置位置，避免递归调用
            QTimer.singleShot(
                0, lambda: self._apply_anchor_position(self.island.size()))
        event.ignore()

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
        # 硬件高负载告警真实状态（游戏形态期间只记录不展示，退出游戏后可恢复）
        self._hw_alert_active = False
        self._hw_alert_stats = None
        self._native_main_window = None
        self._tray_icon = None
        self._smtc_monitor = None
        self._bt_monitor = None
        self._clipboard_monitor = None
        self._clipboard_panel = None
        self._hw_monitor = None
        self._calendar_monitor = None
        self._todo_backend = None
        self._settings_backend = None

        # 窗口锚点（_setup_window_geometry 中确定，之后固定不变）
        self._anchor_mode = "center_top"
        self._anchor_x = None
        self._anchor_y = None
        # 游戏模式：游戏运行时岛钉到屏幕右上角显示瘦小帧率形态
        self._game_mode = False
        # 检测到游戏但首帧数据尚未到达时的等待信息 / 兜底切换定时器
        self._game_pending_info = None
        self._game_switch_timer = None
        # 锚点切换滑动偏移（动画期间叠加在锚点定位上，无动画时为 0）
        self._pos_offset = QPointF(0, 0)
        self._pos_anim = None

        # 初始化UI
        self._init_ui()
        self._init_system_tray()
        self._init_settings()
        self._init_idle_timer()
        self._init_smtc()
        self._init_bluetooth()
        self._init_clipboard()
        self._init_hardware()
        self._init_calendar()
        self._init_todo_reminder()

        # 设置窗口位置
        self._setup_window_geometry()
        # 屏幕可用区域变化（分辨率/任务栏调整）时重算锚点，保持固定位置
        QApplication.primaryScreen().availableGeometryChanged.connect(
            self._setup_window_geometry)

        # 使用 Windows API 锁定窗口位置
        if sys.platform == "win32":
            self._lock_window_position()

    def _init_ui(self):
        """初始化UI"""
        self.island = DynamicIslandWidget(self._config)
        self.setCentralWidget(self.island)
        self.island.clicked.connect(self._on_capsule_clicked)
        self.island.sizeChanged.connect(self._on_island_size_changed)
        self.island.media_control_clicked.connect(self._on_media_control)
        self.island.open_link_requested.connect(self._on_clipboard_open_link)

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

    def _init_bluetooth(self):
        """初始化蓝牙耳机连接/断开实时监控"""
        # 临时禁用：Python 3.14 下蓝牙 COM 监控线程触发 access violation 杀死进程
        print("[Capsule] 蓝牙连接监控已临时禁用（Python 3.14 兼容性问题）")
        return

    def _on_bluetooth_connection(self, info):
        """耳机连接/断开：弹出灵动岛通知，并取消可能的闲置减淡"""
        self._reset_idle_timer()
        if not self._notify_enabled("notify_bluetooth"):
            return
        self.island.set_bluetooth_event(info)

    def _init_clipboard(self):
        """初始化剪贴板监控（WM_CLIPBOARDUPDATE 挂在本窗口句柄上）"""
        try:
            from capsule_app.clipboard_backend import ClipboardMonitor
            self._clipboard_monitor = ClipboardMonitor()
            self._clipboard_monitor.captured.connect(self._on_clipboard_captured)
            self._clipboard_monitor.attach(int(self.winId()))
        except Exception as e:
            print(f"[Capsule] 剪贴板监控初始化失败: {e}")

    def _on_clipboard_captured(self, info):
        """复制内容：小岛轻弹通知，并取消可能的闲置减淡"""
        self._reset_idle_timer()
        if not self._notify_enabled("notify_clipboard"):
            return
        self.island.set_clipboard_event(info)

    def _on_clipboard_open_link(self, url):
        """剪贴板通知上的"打开"按钮：识别链接一键打开"""
        if url:
            try:
                from capsule_app.clipboard_backend import normalize_url
                normalized = normalize_url(url)
                if normalized:
                    QDesktopServices.openUrl(QUrl(normalized))
            except Exception as e:
                print(f"[Capsule] 打开链接失败: {e}")
        self.island.dismiss_clipboard_event()

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
        """高负载开始/结束：弹出或收回硬件告警形态，并取消可能的闲置减淡

        游戏启动/运行期间静默降级：只记录日志、不向界面弹报警，避免启动
        游戏时被高负载告警打断；退出游戏后若仍处于高负载会恢复展示。
        """
        self._reset_idle_timer()
        self._hw_alert_active = bool(active)
        self._hw_alert_stats = stats if active else None
        if self._game_notification_muted():
            if active:
                print("[Capsule] 游戏形态期间硬件高负载告警已静默（仅记录日志）")
            return
        if not self._notify_enabled("notify_hardware"):
            return
        self.island.set_hw_alert(active, stats)

    def _on_hw_stats(self, stats):
        """采样更新：告警展示期间刷新负载条；游戏形态复用同一份采样显示温度/内存"""
        if self.island.is_hw_alerting():
            self.island.set_hardware_stats(stats)
        self.island.set_system_stats(stats)
        dlog("Island", f"hw payload gpu_temp={stats.get('gpu_temp')} "
                       f"mem={stats.get('mem')} cpu_temp={stats.get('cpu_temp')}")

    def _game_notification_muted(self):
        """游戏启动/运行期间是否静默提醒（不向界面弹任何报警提示）"""
        return self._game_mode or self._game_pending_info is not None

    def _init_calendar(self):
        """初始化日历监控（Outlook COM 读下一条日程，临近时弹提醒）

        未装 / 未运行 Outlook：后端静默不弹任何通知，不影响其他形态。
        """
        try:
            from capsule_app.calendar_backend import CalendarMonitor
            self._calendar_monitor = CalendarMonitor()
            self._calendar_monitor.approaching.connect(
                self._on_calendar_approaching)
        except Exception as e:
            print(f"[Capsule] 日历监控初始化失败: {e}")

    def _on_calendar_approaching(self, info):
        """下一条日程临近：弹出灵动岛通知，并取消可能的闲置减淡"""
        self._reset_idle_timer()
        self.island.set_calendar_event(info)

    def _on_calendar_open(self, entry_id):
        """日历通知被点击：在 Outlook 中打开该约会（EntryID 为空则打开日历视图）"""
        if self._calendar_monitor is not None:
            self._calendar_monitor.open_in_outlook(entry_id or "")
        self.island.dismiss_calendar_event()

    # --- 待办到点提醒 ---
    def _init_todo_reminder(self):
        """启动待办提醒调度器：读取持久化的待办，到点弹灵动岛通知

        调度器是进程内单例：主界面保存待办后推给它，主界面没打开也能提醒。
        """
        try:
            from capsule_app.todo_backend import TodoReminderBackend
            self._todo_backend = TodoReminderBackend.instance()
            self._todo_backend.reminder_due.connect(self._on_todo_reminder)
        except Exception as e:
            print(f"[CapsuleWindow] 初始化待办提醒失败: {e}")

    def _on_todo_reminder(self, info):
        """待办到点：弹出灵动岛提醒，并取消可能的闲置减淡"""
        if not self._notify_enabled("notify_todo"):
            return
        self._reset_idle_timer()
        self.island.set_todo_event(info)

    def _on_todo_remind_open(self):
        """待办提醒被点击：打开控制台并切到待办页"""
        self.island.dismiss_todo_event()
        self._open_native_main_window()
        if self._native_main_window is not None:
            self._native_main_window.select_page("nav.todo")

    def _open_clipboard_panel(self):
        """打开剪贴板历史面板（胶囊下方弹出）"""
        if self._clipboard_panel is None:
            from capsule_app.clipboard_panel_window import ClipboardPanelWidget
            self._clipboard_panel = ClipboardPanelWidget(self._clipboard_monitor)

        panel = self._clipboard_panel
        panel.prepare_show()

        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()

        capsule_geo = self.geometry()
        x = capsule_geo.center().x() - panel.width() // 2
        x = max(screen_geometry.x() + 10,
                min(x, screen_geometry.right() - panel.width() - 10))
        y = capsule_geo.bottom() + 12
        if y + panel.height() > screen_geometry.bottom() - 10:
            y = max(screen_geometry.y() + 10,
                    capsule_geo.top() - panel.height() - 12)

        panel.show_at(QPoint(x, y))

    # ------------------------------------------------------------------
    # 剪贴板历史管理
    # ------------------------------------------------------------------
    def _clear_clipboard_history(self):
        """主界面/设置窗口"清空剪贴板历史"按钮：清空本地剪贴板历史"""
        if self._clipboard_monitor is not None:
            self._clipboard_monitor.clear_history()
            print("[Capsule] 已清空剪贴板历史")

    def _open_native_main_window(self):
        """打开 Windows 原生主界面（Nav 列表 + StackedWidget 多页）"""
        try:
            # 剪贴板面板打开时先收起
            if self._clipboard_panel is not None and self._clipboard_panel.isVisible():
                self._clipboard_panel.hide()

            if self._native_main_window is None:
                from capsule_app.native_main_window import NativeMainWindow
                self._native_main_window = NativeMainWindow(
                    smtc=self._smtc_monitor,
                    settings=self._settings_backend)
                self._native_main_window.open_clipboard_requested.connect(
                    self._open_clipboard_panel)
                self._native_main_window.clear_clipboard_requested.connect(
                    self._clear_clipboard_history)
                self._native_main_window.open_settings_requested.connect(
                    self._open_native_settings_window)

            w = self._native_main_window
            if w.isMinimized():
                w.showNormal()
            w.show()
            w.raise_()
            w.activateWindow()
        except Exception as e:
            import traceback
            print(f"[Capsule] 打开原生主界面失败: {e}")
            traceback.print_exc()

    def _open_native_settings_window(self):
        """托盘"控制台"入口：打开统一主窗口并定位到日志页。

        日志/蓝牙/设置等页面都已并入 NativeMainWindow，
        不再使用独立窗口。
        """
        self._open_native_main_window()
        try:
            if self._native_main_window is not None:
                self._native_main_window.select_page("nav.log")
        except Exception:
            pass

    def _on_island_size_changed(self, w, h):
        """胶囊尺寸变化时，按固定锚点重新定位窗口

        位置只由锚点与新尺寸决定，不读取 self.geometry() 的历史值——
        在高频 setGeometry 期间该缓存可能与真实窗口位置脱节，曾导致
        每次悬停展开/收起循环窗口向右下漂移（增量尺寸的一半）。
        """
        if self._anchor_x is None:
            self._setup_window_geometry()
            return
        self._apply_anchor_position(self.island.size())

    def set_game_mode(self, active):
        """切换游戏模式：岛滑动到屏幕右上角（瘦小帧率形态）或回到配置锚点

        锚点切换伴随一次平滑滑动：先按新锚点定位，再把旧位置作为偏移量
        动画归零，避免窗口横跨屏幕瞬移；滑动期间尺寸动画仍正常叠加。
        """
        active = bool(active)
        if active == self._game_mode:
            return
        print(f"[Capsule] 游戏模式: {'开启(右上角)' if active else '关闭(回锚点)'}")
        old_pos = self.geometry().topLeft()
        self._game_mode = active
        self._pos_offset = QPointF(0, 0)
        if self._anchor_x is None:
            return  # 尚未完成首次定位，由初始化流程按新模式处理
        self._setup_window_geometry()
        dx = old_pos.x() - self.x()
        dy = old_pos.y() - self.y()
        if dx == 0 and dy == 0:
            return
        # 从旧位置滑动到新锚点：先把偏移补回去消除瞬移，再动画归零
        self._pos_offset = QPointF(dx, dy)
        self._apply_anchor_position(self.island.size())
        if self._pos_anim is None:
            self._pos_anim = QVariantAnimation(self)
            self._pos_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._pos_anim.valueChanged.connect(self._on_pos_anim)
        self._pos_anim.stop()
        duration = self._config.get("animation", {}).get("collapse_ms", 240)
        self._pos_anim.setDuration(duration)
        self._pos_anim.setStartValue(QPointF(dx, dy))
        self._pos_anim.setEndValue(QPointF(0, 0))
        self._pos_anim.start()

    def _on_pos_anim(self, offset):
        """锚点滑动帧：更新位置偏移并按当前尺寸重新定位"""
        self._pos_offset = offset
        self._apply_anchor_position(self.island.size())

    def _setup_window_geometry(self):
        """确定锚点并按当前尺寸定位窗口

        锚点在窗口生命周期内固定（仅随屏幕可用区域变化而重算），
        之后所有尺寸变化都按锚点定位，与历史 geometry 无关，
        窗口位置是确定性的，即使被外部因素扰动也会在下次尺寸
        变化时自动回正。
        """
        screen = QApplication.primaryScreen()
        sg = screen.availableGeometry()

        anchor = self._config.get("anchor", "top_center")
        if self._game_mode:
            # 游戏模式：锚点语义为窗口右缘 x + 窗口顶部 y，钉在屏幕右上角
            self._anchor_mode = "right_top"
            self._anchor_x = sg.x() + sg.width() - 10
            self._anchor_y = sg.y() + 10
        elif anchor == "top_center":
            # 锚点语义：窗口中心 x + 窗口顶部 y
            self._anchor_mode = "center_top"
            self._anchor_x = sg.x() + sg.width() // 2
            self._anchor_y = sg.y() + 10
        else:
            # 锚点语义：窗口左缘 x + 窗口中心 y
            self._anchor_mode = "left_center"
            self._anchor_x = sg.x() + 10
            self._anchor_y = sg.y() + sg.height() // 2

        self._apply_anchor_position(self.island.size())

    def _apply_anchor_position(self, size):
        """按已保存的锚点 + 给定尺寸定位窗口（单次 setGeometry）"""
        if self._anchor_mode == "center_top":
            x = self._anchor_x - size.width() // 2
            y = self._anchor_y
        elif self._anchor_mode == "right_top":
            x = self._anchor_x - size.width()
            y = self._anchor_y
        else:
            x = self._anchor_x
            y = self._anchor_y - size.height() // 2
        # 叠加锚点切换滑动偏移（无动画时为 0）
        x += int(round(self._pos_offset.x()))
        y += int(round(self._pos_offset.y()))
        self.setGeometry(x, y, size.width(), size.height())

    def _lock_window_position(self):
        """使用 Windows API 锁定窗口位置，防止被移动"""
        try:
            import ctypes
            from ctypes import wintypes

            # 获取窗口句柄
            hwnd = int(self.winId())

            # 获取当前窗口位置
            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))

            # 使用 SetWindowPos 锁定窗口位置
            # SWP_NOSIZE = 0x0001, SWP_NOZORDER = 0x0004, SWP_NOACTIVATE = 0x0010
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020

            # 设置窗口位置并锁定
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                0,  # hWndInsertAfter
                rect.left,
                rect.top,
                rect.right - rect.left,
                rect.bottom - rect.top,
                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
            )

            # 移除窗口的可移动样式
            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000

            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            # 移除标题栏和可调整大小的边框
            style &= ~WS_CAPTION
            style &= ~WS_THICKFRAME
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)

            print(f"[CapsuleWindow] 窗口位置已锁定：{rect.left}, {rect.top}")
        except Exception as e:
            print(f"[CapsuleWindow] 锁定窗口位置失败：{e}")

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
        self._tray_menu = tray_menu
        self._tray_show_main = QAction("打开主界面", self)
        self._tray_show_main.triggered.connect(self._open_native_main_window)

        self._tray_hide_main = QAction("隐藏主界面", self)
        self._tray_hide_main.triggered.connect(self._hide_main_window)

        self._tray_settings = QAction("设置", self)
        self._tray_settings.triggered.connect(self._open_native_settings_window)

        self._tray_show_island = QAction("显示灵动岛", self)
        self._tray_show_island.triggered.connect(self._show_from_tray)

        self._tray_hide_island = QAction("隐藏灵动岛", self)
        self._tray_hide_island.triggered.connect(self._hide_island_only)

        self._tray_exit = QAction("退出", self)
        self._tray_exit.triggered.connect(self._exit_application)

        tray_menu.addAction(self._tray_show_main)
        tray_menu.addAction(self._tray_hide_main)
        tray_menu.addAction(self._tray_settings)
        tray_menu.addSeparator()
        tray_menu.addAction(self._tray_show_island)
        tray_menu.addAction(self._tray_hide_island)
        tray_menu.addSeparator()
        tray_menu.addAction(self._tray_exit)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()
        self._refresh_tray_labels()

    def _on_tray_activated(self, reason):
        if reason not in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            return
        self._open_native_main_window()

    def _show_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _hide_island_only(self):
        self.hide()

    def _hide_main_window(self):
        if self._native_main_window is not None and self._native_main_window.isVisible():
            self._native_main_window.hide()

    def _hide_to_tray(self):
        self._hide_main_window()
        self.hide()

    def _refresh_tray_labels(self):
        lang = "zh"
        if self._settings_backend is not None:
            lang = self._settings_backend.get_settings().get("language", "zh")
        from capsule_app.native_ui import tr
        if not hasattr(self, "_tray_show_main"):
            return
        self._tray_show_main.setText(tr(lang, "tray.showMain"))
        self._tray_hide_main.setText(tr(lang, "tray.hideMain"))
        self._tray_settings.setText(tr(lang, "tray.settings"))
        self._tray_show_island.setText(tr(lang, "tray.showIsland"))
        self._tray_hide_island.setText(tr(lang, "tray.hideIsland"))
        self._tray_exit.setText(tr(lang, "tray.exit"))

    def _exit_application(self):
        # 停止所有后台监控线程
        if self._clipboard_monitor is not None:
            self._clipboard_monitor.detach()
        if self._smtc_monitor is not None:
            self._smtc_monitor.stop()
        if self._bt_monitor is not None:
            self._bt_monitor.stop()
        if self._hw_monitor is not None:
            self._hw_monitor.stop()
        if self._calendar_monitor is not None:
            self._calendar_monitor.stop()
        # 注意：不在此处调用 gc.collect()。各 COM 线程的 stop() 已在
        # 各自套间内 gc.collect() 并 join，主线程做 gc 反而可能跨套间
        # Release 残留 COM 指针 → 0xC0000005 闪退。
        if self._native_main_window is not None:
            try:
                if hasattr(self._native_main_window, "shutdown"):
                    self._native_main_window.shutdown()
                else:
                    self._native_main_window.close()
            except Exception:
                pass
        if self._clipboard_panel is not None:
            self._clipboard_panel.close()
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
            self._refresh_tray_labels()
            # 启动时应用一次当前设置（让液态玻璃/自动减淡等按已保存偏好立即生效）
            self._apply_settings(self._settings_backend.get_settings())
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
        if not settings.get("notify_bluetooth", True):
            self.island.dismiss_bluetooth_event()
        if not settings.get("notify_clipboard", True):
            self.island.dismiss_clipboard_event()
        if not settings.get("notify_hardware", True):
            self.island.set_hw_alert(False, None)
        if not settings.get("notify_todo", True):
            self.island.dismiss_todo_event()
        self._refresh_tray_labels()

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
        """胶囊点击事件处理（通知形态下打开对应功能，普通点击不弹出窗口）

        普通点击只保持悬停展开效果；主界面仍可从托盘「控制台」进入。
        """
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

            # 如果原生主界面已打开，则关闭
            if self._native_main_window is not None and self._native_main_window.isVisible():
                print("[CapsuleWindow] 关闭已打开的原生主界面")
                self._native_main_window.hide()
                return

            # 剪贴板历史面板打开时：点击胶囊收起
            if self._clipboard_panel is not None and self._clipboard_panel.isVisible():
                print("[CapsuleWindow] 关闭剪贴板历史面板")
                self._clipboard_panel.hide()
                return

            # 剪贴板通知展示期间点胶囊：打开剪贴板历史
            if self.island.is_clipboard_notifying():
                print("[CapsuleWindow] 打开剪贴板历史（通知期间）")
                self._open_clipboard_panel()
                return

            # 日历通知展示期间点胶囊：在 Outlook 中打开该约会
            if self.island.is_calendar_notifying():
                print("[CapsuleWindow] 打开日历")
                self._on_calendar_open(self.island._calendar_open_id or "")
                return

            # 待办提醒展示期间点胶囊：打开控制台待办页
            if self.island.is_todo_notifying():
                print("[CapsuleWindow] 打开待办页（提醒期间）")
                self._on_todo_remind_open()
                return

            # 普通点击不再弹出原生主界面：保持悬停展开即可，
            # 主界面从托盘「控制台」入口打开。
        except Exception as e:
            import traceback
            print(f"[CapsuleWindow] 点击事件处理失败: {e}")
            traceback.print_exc()

    def mousePressEvent(self, event):
        self._reset_idle_timer()
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
                    WM_CLIPBOARDUPDATE = 0x031D
                    if msg.message == WM_MOUSEACTIVATE:
                        return True, MA_ACTIVATE
                    if msg.message == WM_CLIPBOARDUPDATE:
                        # 剪贴板变化：转发给监控后端（GUI 线程）
                        if self._clipboard_monitor is not None:
                            self._clipboard_monitor.on_clipboard_update()
                        return True, 0
                except Exception:
                    pass
            return super().nativeEvent(eventType, message)

    def mouseMoveEvent(self, event):
        self._reset_idle_timer()
        event.accept()

    def mouseReleaseEvent(self, event):
        self._reset_idle_timer()
        # 注意：点击处理由 DynamicIslandWidget.mouseReleaseEvent 中的
        # clicked 信号驱动，这里不再直接调用 _on_capsule_clicked()，
        # 避免一次点击触发两次（信号 + 直接调用）。
        event.accept()

    def _load_app_icon(self):
        """加载应用图标"""
        from capsule_app.main import APP_ICON_CANDIDATES
        for icon_path in APP_ICON_CANDIDATES:
            if icon_path.exists():
                return QIcon(str(icon_path))
        return QIcon()
