#!/usr/bin/env python3
"""
LsletUI - 设置后端
负责用户偏好的持久化（settings.json）与应用：
- autostart：开机自启动（写入 HKCU 注册表 Run 键）
- auto_dim / auto_dim_delay：胶囊无操作自动减淡及延迟
- language：界面语言（zh/en），前端侧边栏据此切换中英文
"""

import json
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal

# 导入资源路径兼容模块
import sys as _sys
if not getattr(_sys, 'frozen', False):
    # 开发模式
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from resource_path import get_resource_path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "LsletUI"

# 允许的自动减淡延迟（毫秒），防止前端传入任意值
ALLOWED_DELAYS = (5000, 10000, 30000)

# 允许的界面语言
ALLOWED_LANGUAGES = ("zh", "en")

DEFAULT_SETTINGS = {
    "autostart": False,
    "auto_dim": True,
    "auto_dim_delay": 10000,
    # 灵动岛提醒开关（各功能独立，关掉则不弹对应胶囊）
    "notify_bluetooth": True,
    "notify_download": True,
    "notify_hardware": True,
    # 界面语言
    "language": "zh",
}


class SettingsBackend(QObject):
    """用户设置管理（前端、胶囊共享同一实例）"""

    settings_changed = Signal(dict)

    def __init__(self, web_view=None, parent=None):
        super().__init__(parent)
        self._web_views = []
        if web_view is not None:
            self._web_views.append(web_view)
        self.storage_dir = Path.home() / ".pyisland_lite"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.settings_file = self.storage_dir / "settings.json"
        self._settings = dict(DEFAULT_SETTINGS)
        self._load()

    # --- 持久化 ---
    def _load(self):
        try:
            if self.settings_file.exists():
                data = json.loads(self.settings_file.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if k in DEFAULT_SETTINGS:
                        self._settings[k] = v
        except Exception as e:
            print(f"[Settings] 加载设置失败: {e}")

        # 开机自启状态始终以注册表实际状态为准（用户可能在任务管理器里手动关过）
        self._settings["autostart"] = self._is_autostart_enabled()
        # 修正非法延迟值
        if self._settings["auto_dim_delay"] not in ALLOWED_DELAYS:
            self._settings["auto_dim_delay"] = 10000
        # 修正非法语言值
        if self._settings["language"] not in ALLOWED_LANGUAGES:
            self._settings["language"] = "zh"

    def _save(self):
        try:
            self.settings_file.write_text(
                json.dumps(self._settings, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as e:
            print(f"[Settings] 保存设置失败: {e}")

    def get_settings(self):
        return dict(self._settings)

    def set_web_view(self, web_view):
        if web_view not in self._web_views:
            self._web_views.append(web_view)

    def remove_web_view(self, web_view):
        if web_view in self._web_views:
            self._web_views.remove(web_view)

    # --- 设置修改 ---
    def set_setting(self, key, value):
        """修改单项设置；成功返回最新设置 dict，key 非法返回 None"""
        if key == "autostart":
            value = bool(value)
            success = self._apply_autostart(value)
            # 写入成功则直接采用目标值；失败则回读注册表取实际状态
            if success:
                self._settings["autostart"] = value
            else:
                self._settings["autostart"] = self._is_autostart_enabled()
        elif key == "auto_dim":
            value = bool(value)
            self._settings["auto_dim"] = value
        elif key == "auto_dim_delay":
            try:
                value = int(value)
            except (TypeError, ValueError):
                return None
            if value not in ALLOWED_DELAYS:
                return None
            self._settings["auto_dim_delay"] = value
        elif key == "language":
            if value not in ALLOWED_LANGUAGES:
                return None
            self._settings["language"] = value
        elif key in ("notify_bluetooth", "notify_download",
                     "notify_hardware"):
            self._settings[key] = bool(value)
        else:
            return None

        self._save()
        print(f"[Settings] 设置已更新: {key}={self._settings.get(key)}")
        self.settings_changed.emit(self.get_settings())
        self._push_to_frontend()
        return self.get_settings()

    # --- 开机自启动（Windows 注册表） ---
    def _autostart_command(self):
        """返回开机自启要执行的命令字符串"""
        # Nuitka 打包后：直接启动 exe 自身
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'

        # 开发环境：用 pythonw.exe 无控制台启动 backend/main.py
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if not pythonw.exists():
            pythonw = Path(sys.executable)
        # 使用 resource_path 兼容模块获取 main.py 路径
        backend_main = get_resource_path("main.py")
        return f'"{pythonw}" "{backend_main}"'

    def _is_autostart_enabled(self):
        if sys.platform != "win32":
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
                return bool(value)
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def _apply_autostart(self, enabled):
        """设置开机自启；返回 True 表示操作成功，False 表示失败"""
        if sys.platform != "win32":
            print("[Settings] 非 Windows 平台，不支持开机自启")
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
                if enabled:
                    winreg.SetValueEx(key, RUN_VALUE_NAME, 0,
                                      winreg.REG_SZ, self._autostart_command())
                    print("[Settings] 已开启开机自启")
                else:
                    try:
                        winreg.DeleteValue(key, RUN_VALUE_NAME)
                        print("[Settings] 已关闭开机自启")
                    except FileNotFoundError:
                        pass
            return True
        except OSError as e:
            print(f"[Settings] 修改开机自启失败: {e}")
            return False

    # --- 前端推送 ---
    def _push_to_frontend(self):
        payload = json.dumps(self.get_settings(), ensure_ascii=True)
        js = f"window.handleSettingsUpdate && window.handleSettingsUpdate({payload});"
        for wv in self._web_views:
            try:
                if wv and wv.page():
                    wv.page().runJavaScript(js)
            except Exception as e:
                print(f"[Settings] 推送到前端失败: {e}")

    def push_to_frontend(self):
        """供面板加载完成时主动补推一次"""
        self._push_to_frontend()

    def stop(self):
        pass
