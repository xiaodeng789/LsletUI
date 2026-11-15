#!/usr/bin/env python3
"""
PyIsland Lite - 剪贴板监控后端
监听系统剪贴板变化（Win32 AddClipboardFormatListener → WM_CLIPBOARDUPDATE），
维护剪贴板历史（文本/链接/文件/图片），识别链接供一键打开。
"""

import json
import re
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QImage

WM_CLIPBOARDUPDATE = 0x031D

# 纯链接（无空白）：http(s)://... 或 www....
URL_RE = re.compile(r"^(?:https?://|www\.)[^\s]+$", re.IGNORECASE)

# 单条文本入史/持久化的最大长度（超长文本截断，避免历史文件膨胀）
MAX_TEXT_LEN = 20000


def normalize_url(text):
    """把剪贴板文本规范成可打开的 URL；不是链接返回 None"""
    t = (text or "").strip()
    if not t or re.search(r"\s", t):
        return None
    if not URL_RE.match(t):
        return None
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", t):
        t = "http://" + t
    return t


def _entry_key(entry):
    """条目内容指纹（用于连续去重 + 同内容移到最前）"""
    kind = entry.get("kind")
    if kind in ("text", "url"):
        return (kind, entry.get("text", ""))
    if kind == "file":
        return (kind, tuple(entry.get("paths") or []))
    return (kind,)


class ClipboardMonitor(QObject):
    """系统剪贴板监控 + 历史管理（运行在 GUI 线程，通过胶囊窗口的
    nativeEvent 收到 WM_CLIPBOARDUPDATE 后回调 on_clipboard_update）"""

    captured = Signal(dict)  # 新剪贴板内容（驱动灵动岛轻弹）

    MAX_HISTORY = 20
    HISTORY_FILE = Path.home() / ".pyisland_lite" / "clipboard_history.json"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hwnd = None
        self._read_pending = False
        self._suppress_until = 0.0  # 自己写剪贴板时抑制弹跳/入史
        self._last_key = None
        self.history = []  # 新条目在前；image 条目仅存在于内存
        self._load_history()

    # --- Win32 监听挂载 ---
    def attach(self, hwnd):
        self._hwnd = hwnd
        try:
            import ctypes
            _user32 = ctypes.WinDLL("user32")
            if not _user32.AddClipboardFormatListener(hwnd):
                print("[Clipboard] AddClipboardFormatListener 失败")
        except Exception as e:
            print(f"[Clipboard] 挂载剪贴板监听失败: {e}")

    def detach(self):
        if self._hwnd is None:
            return
        try:
            import ctypes
            _user32 = ctypes.WinDLL("user32")
            _user32.RemoveClipboardFormatListener(self._hwnd)
        except Exception:
            pass
        self._hwnd = None

    # --- 自己写剪贴板时抑制（避免面板复制回贴再触发弹跳） ---
    def suppress_next(self):
        self._suppress_until = time.time() + 1.2

    # --- WM_CLIPBOARDUPDATE 入口（GUI 线程调用） ---
    def on_clipboard_update(self):
        if self._read_pending:
            return
        self._read_pending = True
        # 延迟读取：避开部分程序写入时短暂持有剪贴板打开状态
        QTimer.singleShot(80, self._read_clipboard)

    def _read_clipboard(self):
        self._read_pending = False
        if time.time() < self._suppress_until:
            return
        try:
            from PySide6.QtWidgets import QApplication
            mime = QApplication.clipboard().mimeData()
        except Exception as e:
            print(f"[Clipboard] 读取剪贴板失败: {e}")
            return
        if mime is None:
            return

        entry = None
        if mime.hasUrls():
            paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
            if paths:
                entry = {"kind": "file", "paths": paths}
        if entry is None:
            text = mime.text() if mime.hasText() else ""
            stripped = (text or "").strip()
            if stripped:
                if len(text) > MAX_TEXT_LEN:
                    text = text[:MAX_TEXT_LEN]
                if URL_RE.match(stripped):
                    entry = {"kind": "url", "text": stripped}
                else:
                    entry = {"kind": "text", "text": text}
        if entry is None and mime.hasImage():
            try:
                img = QApplication.clipboard().image()
                if img is not None and not img.isNull():
                    entry = {"kind": "image", "image": img}
            except Exception:
                pass

        if entry is None:
            return

        key = _entry_key(entry)
        if key == self._last_key:
            return  # 连续重复内容：不弹跳不重复记录
        self._last_key = key

        # 同内容旧记录移到最前
        self.history = [e for e in self.history if _entry_key(e) != key]
        entry["ts"] = time.time()
        self.history.insert(0, entry)
        del self.history[self.MAX_HISTORY:]
        self._save_history()
        self.captured.emit(self._to_event(entry))

    # --- 提供给灵动岛的通知数据 ---
    @staticmethod
    def _to_event(entry):
        kind = entry.get("kind")
        info = {"kind": kind}
        if kind in ("text", "url"):
            text = entry.get("text", "")
            info["text"] = text
            info["preview"] = text
            if kind == "url":
                info["url"] = text
        elif kind == "file":
            paths = entry.get("paths") or []
            info["paths"] = paths
            info["count"] = len(paths)
            info["preview"] = (Path(paths[0]).name if len(paths) == 1
                               else f"{len(paths)} 个文件")
        elif kind == "image":
            img = entry.get("image")
            info["image"] = img
            info["preview"] = (f"图片 {img.width()}×{img.height()}"
                               if img is not None else "图片")
        return info

    # --- 历史持久化（图片不入盘，仅内存） ---
    def _load_history(self):
        try:
            if self.HISTORY_FILE.exists():
                data = json.loads(
                    self.HISTORY_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.history = [
                        e for e in data
                        if isinstance(e, dict)
                        and e.get("kind") in ("text", "url", "file")
                    ]
                    del self.history[self.MAX_HISTORY:]
        except Exception as e:
            print(f"[Clipboard] 读取历史失败: {e}")

    def _save_history(self):
        try:
            self.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = []
            for e in self.history:
                if e.get("kind") == "image":
                    continue
                item = {"kind": e["kind"], "ts": e.get("ts", 0)}
                if "text" in e:
                    item["text"] = e["text"]
                if "paths" in e:
                    item["paths"] = e["paths"]
                data.append(item)
            self.HISTORY_FILE.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[Clipboard] 保存历史失败: {e}")

    # --- 面板操作接口 ---
    def remove_entry(self, entry):
        key = _entry_key(entry)
        self.history = [e for e in self.history if _entry_key(e) != key]
        self._save_history()

    def clear_history(self):
        self.history = []
        self._last_key = None
        self._save_history()

    def copy_entry(self, entry):
        """把历史条目写回系统剪贴板（抑制本次更新触发的弹跳）"""
        self.suppress_next()
        self._last_key = _entry_key(entry)
        try:
            from PySide6.QtCore import QMimeData, QUrl
            from PySide6.QtWidgets import QApplication
            cb = QApplication.clipboard()
            kind = entry.get("kind")
            if kind == "image":
                img = entry.get("image")
                if img is None:
                    return False
                cb.setImage(img)
                return True
            if kind == "file":
                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile(p)
                              for p in entry.get("paths") or []])
                cb.setMimeData(mime)
                return True
            cb.setText(entry.get("text", ""))
            return True
        except Exception as e:
            print(f"[Clipboard] 写回剪贴板失败: {e}")
            return False
