"""待办提醒调度后端。

待办列表由原生主界面写入 ~/.pyisland_lite/todos.json（裸数组，字段
id/text/completed/remindAt，remindAt 为毫秒时间戳）。本类只做调度：
到点发 reminder_due 信号，由灵动岛弹提醒，不依赖主界面是否打开。

「已提醒过」的记录单独写 ~/.pyisland_lite/todo_reminders.json：主界面
只认 todos.json 的裸数组结构，两个写入方共用一个文件会互相破坏格式。
"""

import json
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

# 检查间隔：15 秒足够精确，又不会频繁唤醒
CHECK_INTERVAL_MS = 15 * 1000
# 应用未运行导致错过的提醒，12 小时内补发一次；更早的直接忽略
CATCH_UP_MS = 12 * 60 * 60 * 1000

_STORAGE_DIR = Path.home() / ".pyisland_lite"
TODO_FILE = _STORAGE_DIR / "todos.json"
STATE_FILE = _STORAGE_DIR / "todo_reminders.json"


class TodoReminderBackend(QObject):
    """待办提醒调度器（进程内单例，主界面与灵动岛共享）"""

    # 到点提醒：{"id": 待办 id, "text": 待办内容, "remindAt": 时间戳(ms)}
    reminder_due = Signal(dict)

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        # 待办镜像：[{id, text, completed, remindAt}]
        self._todos = []
        # 已提醒过的键："{id}|{remindAt}"，避免重复弹通知
        self._notified = set()
        # todos.json 的修改时间：外部（另一个入口）改动能被轮询发现
        self._mtime = None

        self._load_state()
        self._reload_todos()

        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self._check_reminders)
        self._timer.start()

        # 启动后 2 秒先检查一次，补发本次启动前刚落点的提醒
        QTimer.singleShot(2000, self._check_reminders)

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def _load_state(self):
        try:
            if STATE_FILE.is_file():
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self._notified = {str(k) for k in data}
        except Exception as e:
            print(f"[TodoReminder] 读取提醒状态失败: {e}")

    def _save_state(self):
        try:
            _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(
                json.dumps(sorted(self._notified), ensure_ascii=False),
                encoding="utf-8")
        except Exception as e:
            print(f"[TodoReminder] 保存提醒状态失败: {e}")

    def _reload_todos(self):
        """从 todos.json 重读待办（文件未变则跳过）"""
        try:
            mtime = TODO_FILE.stat().st_mtime
        except OSError:
            return
        if mtime == self._mtime:
            return
        self._mtime = mtime
        try:
            data = json.loads(TODO_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[TodoReminder] 读取待办文件失败: {e}")
            return
        if isinstance(data, dict):
            # 兼容 0.1.x 的 {"todos": [...], "notified": [...]} 结构
            todos = data.get("todos")
            notified = data.get("notified")
            if isinstance(notified, list) and not self._notified:
                self._notified = {str(k) for k in notified}
        else:
            todos = data
        if not isinstance(todos, list):
            return
        self.set_todos(todos)

    @staticmethod
    def _sanitize(item):
        """只保留调度需要的字段，非法数据返回 None"""
        if not isinstance(item, dict) or item.get("id") is None:
            return None
        try:
            remind_at = item.get("remindAt")
            remind_at = int(remind_at) if remind_at else None
        except (TypeError, ValueError):
            remind_at = None
        return {
            "id": item.get("id"),
            "text": str(item.get("text") or "").strip(),
            "completed": bool(item.get("completed")),
            "remindAt": remind_at,
        }

    # ------------------------------------------------------------------
    # 列表同步
    # ------------------------------------------------------------------
    def set_todos(self, items):
        """接收完整待办列表；主界面保存后立刻调用，省掉一个轮询周期"""
        if not isinstance(items, list):
            return
        self._todos = [
            todo for todo in (self._sanitize(i) for i in items) if todo
        ]
        # 清掉已失效的提醒记录，避免 notified 集合无限增长
        valid = {self._key(t) for t in self._todos if t.get("remindAt")}
        self._notified &= valid
        self._save_state()

    @staticmethod
    def _key(todo):
        return f"{todo.get('id')}|{todo.get('remindAt')}"

    # ------------------------------------------------------------------
    # 到点检查
    # ------------------------------------------------------------------
    def _check_reminders(self):
        self._reload_todos()

        now_ms = int(time.time() * 1000)
        fired = False
        for todo in self._todos:
            remind_at = todo.get("remindAt")
            if not remind_at or todo.get("completed"):
                continue
            key = self._key(todo)
            if key in self._notified or now_ms < remind_at:
                continue

            # 标记为已提醒（无论是否补发），避免下次重复检查
            self._notified.add(key)
            fired = True

            if now_ms - remind_at <= CATCH_UP_MS:
                self.reminder_due.emit({
                    "id": todo.get("id"),
                    "text": todo.get("text") or "待办事项",
                    "remindAt": remind_at,
                })
            else:
                print(f"[TodoReminder] 提醒已过期，跳过: {todo.get('text')}")

        if fired:
            self._save_state()
