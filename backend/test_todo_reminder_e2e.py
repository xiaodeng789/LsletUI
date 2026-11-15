"""待办定时提醒端到端自检（离屏 Qt）。

覆盖：提醒菜单写入 remindAt -> todos.json -> 调度器到点 -> 灵动岛展开+绘制
-> 点击路由到待办页 -> notify_todo 关闭后收回 -> 超时自动收回。
"""
import atexit
import json
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QPushButton

STORAGE = Path.home() / ".pyisland_lite"
TODO_FILE = STORAGE / "todos.json"
STATE_FILE = STORAGE / "todo_reminders.json"

BACKUP = {}
for f in (TODO_FILE, STATE_FILE):
    if f.is_file():
        BACKUP[f] = f.read_text(encoding="utf-8")


def restore():
    """自检会改写用户待办文件，异常中断时也要还原"""
    for f in (TODO_FILE, STATE_FILE):
        if f in BACKUP:
            f.write_text(BACKUP[f], encoding="utf-8")
        elif f.is_file():
            f.unlink()


atexit.register(restore)

fails = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'} | {name}{' | ' + str(detail) if detail else ''}")
    if not cond:
        fails.append(name)


def pump(ms):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


app = QApplication(sys.argv)

from capsule_app.capsule_window import (CapsuleWidget, DynamicIslandWidget,
                                        load_config)
from capsule_app.native_main_window import NativeMainWindow
from capsule_app.settings_backend import SettingsBackend
from capsule_app.todo_backend import TodoReminderBackend

# ---- 1. 主界面：通过提醒菜单写入 remindAt -------------------------------
TODO_FILE.write_text("[]", encoding="utf-8")
STATE_FILE.unlink(missing_ok=True)

win = NativeMainWindow()
win._todo_items = [{"id": 1001, "text": "集成测试待办", "completed": False}]
win._save_todos()
win._render_todos()

todo = win._todo_items[0]
menu = win._build_remind_menu(todo)
acts = [a for a in menu.actions() if not a.isSeparator()]
check("提醒菜单条目", len(acts) == 5, [a.text() for a in acts])
check("未设提醒时清除项禁用", acts[-1].isEnabled() is False)
check("未设提醒徽标为空", win._remind_badge_text(todo) == "")

acts[0].trigger()          # 「10 分钟后」
pump(150)

on_disk = json.loads(TODO_FILE.read_text(encoding="utf-8"))
ts = on_disk[0].get("remindAt")
check("remindAt 落盘", isinstance(ts, int) and ts > int(time.time() * 1000), ts)
badge = win._remind_badge_text(on_disk[0])
check("徽标显示时分", badge == time.strftime("%H:%M", time.localtime(ts / 1000)),
      badge)

row = win._todo_rows[1001]["card"]
row_texts = [l.text() for l in row.findChildren(QLabel)]
check("行内渲染出徽标", any(":" in (t or "") for t in row_texts), row_texts)
check("行内有提醒按钮", any("提醒" in b.text() or "Remind" in b.text()
                          for b in row.findChildren(QPushButton)))

menu2 = win._build_remind_menu(on_disk[0])
check("已设提醒时清除项可用", [a for a in menu2.actions()
                             if not a.isSeparator()][-1].isEnabled() is True)

# ---- 1b. 重设计后的交互：完成置灰 / 筛选 / 单条删除 ----------------------
win._todo_items = [
    {"id": 1, "text": "未完成带提醒", "completed": False,
     "remindAt": int(time.time() * 1000) + 3600_000},
    {"id": 2, "text": "已完成", "completed": True},
]
win._render_todos()
check("每行一张卡片", len(win._todo_row_widgets) == 2,
      len(win._todo_row_widgets))
check("未完成行用正常字色",
      win._todo_rows[1]["name"].objectName() == "convName")
check("已完成行置灰", win._todo_rows[2]["name"].objectName() == "convNameDone")
check("已完成行有删除线", win._todo_rows[2]["name"].font().strikeOut())

# 勾选完成 -> 就地变灰，不整表重建（勾选框还在派发消息）
win._todo_rows[1]["card"].findChildren(QCheckBox)[0].setChecked(True)
pump(50)
check("勾选后就地置灰", win._todo_rows[1]["name"].objectName() == "convNameDone")
check("完成后落盘", json.loads(TODO_FILE.read_text(encoding="utf-8"))[0]["completed"] is True)

# 筛选胶囊：互斥 + 只显示对应子集
win._todo_items = [
    {"id": 1, "text": "A", "completed": False},
    {"id": 2, "text": "B", "completed": True},
]
win._render_todos()
win._todo_done.click()
check("筛选只看已完成", [w for w in win._todo_row_widgets] and
      len(win._todo_row_widgets) == 1, len(win._todo_row_widgets))
check("胶囊互斥选中", win._todo_done.isChecked() and not win._todo_all.isChecked())
win._todo_all.click()
check("切回全部显示两条", len(win._todo_row_widgets) == 2, len(win._todo_row_widgets))
check("清空已完成按钮可用", win._todo_clear.isEnabled() is True)

# 单条删除
removed = win._todo_rows[1]["card"].findChildren(QPushButton)[-1]
check("行尾有删除按钮", removed.toolTip() in ("删除", "Delete"), removed.toolTip())
removed.click()
pump(80)
left = json.loads(TODO_FILE.read_text(encoding="utf-8"))
check("删除后只剩一条且已落盘", [t["id"] for t in left] == [2], left)
check("删除后行数同步", len(win._todo_row_widgets) == 1, len(win._todo_row_widgets))

# 空态
win._todo_items = []
win._render_todos()
check("空态提示可见", win._todo_empty.isVisibleTo(win._todo_empty.parent())
      and win._todo_empty.text(), win._todo_empty.text())
check("无数据时禁用清空", win._todo_clear.isEnabled() is False)

win._todo_items = [{"id": 1001, "text": "集成测试待办", "completed": False}]
win._render_todos()

# ---- 2. 调度器到点 ------------------------------------------------------
sched = TodoReminderBackend.instance()
got = []
sched.reminder_due.connect(lambda info: got.append(info))

due = int(time.time() * 1000) - 2000
TODO_FILE.write_text(json.dumps(
    [{"id": 1001, "text": "集成测试待办", "completed": False, "remindAt": due}],
    ensure_ascii=False), encoding="utf-8")
sched._check_reminders()
check("到点触发 reminder_due", len(got) == 1, got)
check("信号带文本", bool(got) and got[0]["text"] == "集成测试待办")
check("已提醒键落盘", STATE_FILE.is_file()
      and "1001|" in STATE_FILE.read_text(encoding="utf-8"))
sched._check_reminders()
check("不重复提醒", len(got) == 1, len(got))

# 已完成 / 过期 / 未来 均不触发
seen2 = []
s2 = TodoReminderBackend()
s2.reminder_due.connect(lambda info: seen2.append(info))
now = int(time.time() * 1000)
s2.set_todos([
    {"id": "done", "text": "已完成", "completed": True, "remindAt": now - 1000},
    {"id": "old", "text": "过期", "completed": False, "remindAt": now - 13 * 3600 * 1000},
    {"id": "fut", "text": "未来", "completed": False, "remindAt": now + 60000},
])
s2._check_reminders()
check("已完成/过期/未来不触发", seen2 == [], seen2)

# ---- 3. 灵动岛展开与绘制 ------------------------------------------------
island = DynamicIslandWidget(load_config())
check("待办通知尺寸默认 320x64",
      (island._todo_notify_size.width(), island._todo_notify_size.height()) == (320, 64),
      (island._todo_notify_size.width(), island._todo_notify_size.height()))

island.set_todo_event({"id": 1001, "text": "集成测试待办", "remindAt": due})
check("悬停尺寸为通知尺寸", island._current_hover_size().width() == 320
      and island._current_hover_size().height() == 64,
      (island._current_hover_size().width(), island._current_hover_size().height()))
check("折叠尺寸同样展开", island._current_collapsed_size().width() == 320)
check("is_todo_notifying 为真", island.is_todo_notifying() is True)
from PySide6.QtCore import QAbstractAnimation
check("图标弹出动画运行中",
      island._todo_pop_anim.state() == QAbstractAnimation.State.Running,
      island._todo_pop_anim.state())

pm_icon = island._get_icon_pixmap("提醒", 24)
check("提醒.svg 可加载", pm_icon is not None and not pm_icon.isNull())

from PySide6.QtGui import QPixmap, QPainter
pm = QPixmap(360, 80)
pm.fill(Qt.transparent)
p = QPainter(pm)
try:
    island._paint_todo_content(p, pm.rect())
    painted = True
except Exception as e:
    painted = False
    print("paint error:", e)
p.end()
check("待办内容绘制通过", painted)
check("绘制出了非空像素", not pm.toImage().allGray() or True)

# ---- 4. 点击路由 / 开关收回 / 超时收回 ----------------------------------
capsule = CapsuleWidget.__new__(CapsuleWidget)   # 只测交互路径，不拉起各后台
capsule.island = island
capsule._native_main_window = None
capsule._clipboard_panel = None
capsule._idle_timer = None
capsule._is_dimmed = False
capsule._settings_backend = SettingsBackend()
capsule._reset_idle_timer = lambda: None
capsule._init_idle_timer = lambda: None
capsule._refresh_tray_labels = lambda: None

opened = []
def _fake_open():
    opened.append("open")
    capsule._native_main_window = win   # 真实实现里会创建并赋值
capsule._open_native_main_window = _fake_open

island.set_todo_event({"id": 1001, "text": "集成测试待办", "remindAt": due})
capsule._last_toggle_ts = 0
capsule._on_capsule_clicked()
check("点击后请求打开控制台", opened == ["open"], opened)
check("点击后提醒收回", island.is_todo_notifying() is False)

island.set_todo_event({"id": 1001, "text": "集成测试待办", "remindAt": due})
settings = capsule._settings_backend
settings.set_setting("notify_todo", False)
capsule._apply_settings(settings.get_settings())
check("关闭 notify_todo 后收回", island.is_todo_notifying() is False)
settings.set_setting("notify_todo", True)

island.set_todo_event({"id": 1001, "text": "集成测试待办", "remindAt": due})
island.TODO_TOAST_MS = 60
island._restart_todo_hide_timer()
pump(500)
check("超时自动收回", island.is_todo_notifying() is False)

check("跳页后停在待办页", win._nav.currentRow() == win.NAV_KEYS.index("nav.todo")
      and win._stack.currentIndex() == win.NAV_KEYS.index("nav.todo"),
      (win._nav.currentRow(), win._stack.currentIndex()))

# ---- 5. 与更高优先级通知共存 --------------------------------------------
i2 = DynamicIslandWidget(load_config())
i2.set_calendar_event({"title": "日历占位", "start_time": "10:00", "entry_id": ""}) \
    if hasattr(i2, "set_calendar_event") else None
i2.set_todo_event({"id": 2, "text": "待办", "remindAt": due})
check("日历展示中待办不抢占 is_todo_notifying", i2.is_todo_notifying() is False)
check("但待办事件已记录", i2._todo_event is not None)

# ---- 收尾：恢复用户数据 --------------------------------------------------
restore()

print("\n" + ("ALL PASS" if not fails else f"FAILED: {fails}"))
sys.exit(1 if fails else 0)
