#!/usr/bin/env python3
"""
PyIsland Lite - 灵动岛后台服务
简单的后台运行灵动岛，无前端设置
"""

import sys
import os
import json
import tkinter as tk
from pathlib import Path

# 导入资源路径兼容模块
from resource_path import get_resource_path, get_config_path

# 配置文件路径（使用兼容模块）
CONFIG_FILE = get_config_path()

# 默认配置 - iPhone 灵动岛风格
DEFAULT_CONFIG = {
    "style": "dynamic_island",
    "collapsed": {
        "width": 200,
        "height": 44
    },
    "hover": {
        "width": 240,
        "height": 52
    },
    "expanded": {
        "width": 360,
        "height": 120
    },
    "background_color": "#000000",
    "background_alpha": 0.92,
    "anchor": "top_center",
    "animation": {
        "expand_ms": 320,
        "collapse_ms": 240,
        "hover_ms": 200
    },
    "auto_hide": True,
    "auto_hide_delay": 10000,
    "stay_on_top": True
}


class IslandConfig:
    """灵动岛配置管理"""

    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.load_config()

    def load_config(self):
        """加载配置文件"""
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # 深度合并配置
                    self._deep_update(self.config, loaded_config)
                print(f"[Config] 已加载配置: {CONFIG_FILE}")
            else:
                self.save_config()
                print(f"[Config] 已创建默认配置: {CONFIG_FILE}")
        except Exception as e:
            print(f"[Config] 加载配置失败: {e}")

    def _deep_update(self, base, override):
        """深度更新字典"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value

    def save_config(self):
        """保存配置文件"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] 保存配置失败: {e}")


class IslandWindow:
    """iPhone 灵动岛风格窗口（tkinter 版）"""

    def __init__(self, config: IslandConfig):
        self.config = config
        self.root = None
        self.canvas = None
        self.auto_hide_timer = None
        self._is_dimmed = False
        self._hovering = False
        self._animating = False
        self.drag_start_x = 0
        self.drag_start_y = 0

    def create_window(self):
        """创建灵动岛窗口"""
        self.root = tk.Tk()
        self.root.title("PyIsland Lite")

        cfg = self.config.config
        collapsed = cfg.get("collapsed", {"width": 200, "height": 44})
        width = collapsed.get("width", 200)
        height = collapsed.get("height", 44)
        alpha = cfg.get("background_alpha", 0.92)

        # 位置：顶部居中
        anchor = cfg.get("anchor", "top_center")
        screen_w = self.root.winfo_screenwidth()
        if anchor == "top_center":
            x = (screen_w - width) // 2
            y = 10
        else:
            x = 10
            y = 300

        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.attributes('-alpha', alpha)
        self.root.attributes('-topmost', cfg.get("stay_on_top", True))
        self.root.overrideredirect(True)  # 无边框窗口

        # 创建胶囊（使用Canvas绘制圆角矩形）
        self.canvas = tk.Canvas(
            self.root,
            width=width,
            height=height,
            bg='black',
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 绘制黑色胶囊
        self._draw_capsule(width, height)

        # 绑定事件
        self.canvas.bind('<Button-1>', self.on_click)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<Enter>', self.on_enter)
        self.canvas.bind('<Leave>', self.on_leave)

        # 启动自动隐藏定时器
        if cfg.get("auto_hide", True):
            self.start_auto_hide_timer()

        return self.root

    def _draw_capsule(self, width, height):
        """绘制 iPhone 灵动岛风格黑色胶囊"""
        self.canvas.delete("all")
        radius = height // 2
        color = "#000000"

        # 主体：纯黑圆角矩形
        self.draw_rounded_rect(0, 0, width, height, radius, color)

        # 顶部高光（细白线模拟）
        self.canvas.create_arc(2, 2, width - 2, height * 2,
                               start=60, extent=60,
                               outline="#1a1a1a", width=1, style=tk.ARC)

        # 边缘描边
        self.canvas.create_arc(1, 1, width - 1, height - 1,
                               start=0, extent=180,
                               outline="#222222", width=1, style=tk.ARC)

        # 中心文字
        self.canvas.create_text(
            width // 2, height // 2,
            text="PyIsland",
            fill='white',
            font=('Segoe UI', 10, 'bold')
        )

    def on_click(self, event):
        """鼠标点击事件"""
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def on_drag(self, event):
        """鼠标拖动事件"""
        x = self.root.winfo_x() + event.x - self.drag_start_x
        y = self.root.winfo_y() + event.y - self.drag_start_y
        self.root.geometry(f"+{x}+{y}")

    def on_enter(self, event):
        """鼠标进入事件 - 悬停放大"""
        self.reset_auto_hide_timer()
        self._hovering = True
        if not self._animating:
            self._expand()

    def on_leave(self, event):
        """鼠标离开事件 - 恢复常态"""
        self.reset_auto_hide_timer()
        self._hovering = False
        if not self._animating:
            self._collapse()

    def _expand(self):
        """展开动画（简单逐帧）"""
        cfg = self.config.config
        collapsed = cfg.get("collapsed", {"width": 200, "height": 44})
        hover = cfg.get("hover", {"width": 240, "height": 52})
        duration = cfg.get("animation", {}).get("hover_ms", 200)

        self._animate_size(
            collapsed["width"], collapsed["height"],
            hover["width"], hover["height"],
            duration
        )

    def _collapse(self):
        """收起动画"""
        cfg = self.config.config
        collapsed = cfg.get("collapsed", {"width": 200, "height": 44})
        duration = cfg.get("animation", {}).get("collapse_ms", 240)

        geo = self.root.geometry().split('+')[0]
        cur_w, cur_h = map(int, geo.split('x'))

        self._animate_size(
            cur_w, cur_h,
            collapsed["width"], collapsed["height"],
            duration
        )

    def _animate_size(self, start_w, start_h, end_w, end_h, duration_ms):
        """简单的逐帧尺寸动画"""
        if self._animating:
            return

        self._animating = True
        steps = max(1, duration_ms // 16)
        dw = (end_w - start_w) / steps
        dh = (end_h - start_h) / steps

        current_w = start_w
        current_h = start_h
        x = self.root.winfo_x()
        y = self.root.winfo_y()

        def step(i):
            nonlocal current_w, current_h
            if i >= steps:
                self._animating = False
                return
            current_w += dw
            current_h += dh
            w = int(current_w)
            h = int(current_h)
            # 保持中心对齐
            nx = x - (w - int(current_w - dw)) // 2
            ny = y - (h - int(current_h - dh)) // 2
            self.root.geometry(f"{w}x{h}+{nx}+{ny}")
            self._draw_capsule(w, h)
            self.root.after(16, lambda: step(i + 1))

        step(0)

    def start_auto_hide_timer(self):
        """启动自动隐藏定时器"""
        delay = self.config.config.get("auto_hide_delay", 10000)
        self.auto_hide_timer = self.root.after(delay, self.auto_hide)

    def reset_auto_hide_timer(self):
        """重置自动隐藏定时器"""
        if self.auto_hide_timer:
            self.root.after_cancel(self.auto_hide_timer)
        self.start_auto_hide_timer()

    def auto_hide(self):
        """自动隐藏"""
        if self.config.config.get("auto_hide"):
            self._is_dimmed = True
            self.root.attributes('-alpha', 0.6)

    def draw_rounded_rect(self, x1, y1, x2, y2, radius, color):
        """绘制圆角矩形"""
        self.canvas.create_arc(x1, y1, x1 + radius*2, y1 + radius*2,
                               start=90, extent=90, fill=color, outline=color)
        self.canvas.create_arc(x2 - radius*2, y1, x2, y1 + radius*2,
                               start=0, extent=90, fill=color, outline=color)
        self.canvas.create_arc(x1, y2 - radius*2, x1 + radius*2, y2,
                               start=180, extent=90, fill=color, outline=color)
        self.canvas.create_arc(x2 - radius*2, y2 - radius*2, x2, y2,
                               start=270, extent=90, fill=color, outline=color)
        self.canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2,
                                     fill=color, outline=color)
        self.canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius,
                                     fill=color, outline=color)

    def run(self):
        """运行灵动岛"""
        if self.root:
            self.root.mainloop()


def main():
    """主函数"""
    print("=" * 50)
    print("PyIsland Lite - 灵动岛后台服务")
    print("=" * 50)
    print()
    print("功能说明:")
    print("1. 灵动岛在后台运行")
    print("2. 可拖动、点击、自动隐藏")
    print("3. 配置文件: backend/island_config.json")
    print()
    print("按 Ctrl+C 停止服务")
    print()
    
    try:
        # 加载配置
        config = IslandConfig()
        
        # 创建灵动岛窗口
        island = IslandWindow(config)
        island.create_window()
        
        print("[启动] 灵动岛已启动")
        collapsed = config.config.get('collapsed', {})
        print(f"[配置] 样式: {config.config.get('style', 'dynamic_island')}")
        print(f"[配置] 大小: {collapsed.get('width', 200)}x{collapsed.get('height', 44)}")
        print(f"[配置] 位置: 顶部居中")
        
        # 运行灵动岛
        island.run()
        
    except KeyboardInterrupt:
        print("\n[停止] 灵动岛已停止")
    except Exception as e:
        print(f"[错误] 启动失败: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    main()