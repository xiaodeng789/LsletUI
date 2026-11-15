"""轻量调试日志（仅用于定位实机数据链路问题，可随时关闭）

启用条件（任一满足）：
- 环境变量 LSLETUI_DEBUG=1
- island_config.json 中 "debug_log": true

日志追加写入 %TEMP%\\lsletui_debug.log，每行带时间与标签。
"""

import json
import os
import tempfile
import time
from pathlib import Path

LOG_PATH = Path(tempfile.gettempdir()) / "lsletui_debug.log"
_enabled = None


def _config_flag():
    try:
        from resource_path import get_config_path
        with open(get_config_path(), "r", encoding="utf-8") as f:
            return bool(json.load(f).get("debug_log"))
    except Exception:
        return False


def enabled():
    global _enabled
    if _enabled is None:
        env = os.environ.get("LSLETUI_DEBUG", "").strip().lower()
        _enabled = env in ("1", "true", "yes", "on") or _config_flag()
    return _enabled


def dlog(tag, message):
    """写一行调试日志；未启用或写入失败时静默"""
    if not enabled():
        return
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} [{tag}] {message}\n")
    except OSError:
        pass
