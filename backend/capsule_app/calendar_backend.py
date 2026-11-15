#!/usr/bin/env python3
"""
LsletUI - 轻量级灵动岛应用
日历后端模块：读取 Outlook 日历，下一条日程临近时弹出瞬时提醒

数据源：通过 Outlook COM（win32com）读默认日历文件夹（olFolderCalendar=9）
       中的下一条日程。未装 / 未运行 Outlook 时静默降级（不弹任何通知）。

触发逻辑：每 POLL_S 秒查询一次下一条日程，若距离开始 ≤ APPROACH_MIN 分钟
         （或已开始但未结束），发 approaching 信号。同一条日程（按
         EntryID + Start 去重）只触发一次，结束后允许下一次临近再触发。
线程：COM 调用走独立 STA 线程（pythoncom.CoInitialize），避免阻塞 Qt 主线程。
"""

import threading
import time
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Signal


POLL_S = 30.0           # 30 秒轮询一次下一条日程
APPROACH_MIN = 5        # 距开始 ≤ 5 分钟时触发通知
MAX_LOOKAHEAD_DAYS = 7  # 只看未来 7 天内的日程
FIRED_TTL_S = 86400     # 已触发去重记录保留 24 小时（防无限增长）
SCAN_LIMIT = 200        # 单次扫描约会项数上限（防御异常日历导致死循环）

OL_FOLDER_CALENDAR = 9


class CalendarMonitor(QObject):
    """Outlook 日历下一条日程临近提醒

    未装 / 未运行 Outlook：_fetch_next_appointment 返回 None，
    后端始终静默，不发任何信号，不弹任何通知。
    """

    # 临近提醒：{"subject", "start", "end", "location", "entry_id", "all_day"}
    approaching = Signal(dict)
    # 下一条日程变化（未来扩展用，目前岛主区域不展示）
    next_event_updated = Signal(dict)

    def __init__(self, start=True):
        super().__init__()
        self._stop_event = threading.Event()
        self._wakeup = threading.Event()
        self._thread = None
        # 已触发通知的 (entry_id, start_iso) -> 添加时刻(monotonic)
        self._fired = {}
        # 待处理的打开请求（EntryID；None 表示打开日历视图）
        self._pending_open = None
        if start:
            self.start()

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._wakeup.clear()
        self._thread = threading.Thread(
            target=self._run, name="calendar-monitor", daemon=False)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._wakeup.set()
        # 等待 COM 线程安全退出，避免跨套间 GC 导致 0xC0000005
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            if self._thread.is_alive():
                print("[Calendar] 警告: COM 线程未能在 3 秒内退出")

    def open_in_outlook(self, entry_id=None):
        """在 Outlook 中打开指定约会（在后台线程里做 COM 调用）

        entry_id 为空字符串 / None 时打开日历文件夹视图。
        """
        self._pending_open = entry_id or ""
        self._wakeup.set()

    # --- 后台线程 ---
    def _run(self):
        try:
            import pythoncom
            import win32com.client  # noqa: F401  提前触发 ImportError
        except ImportError as e:
            print(f"[Calendar] 缺少 pywin32，日历监控不可用: {e}")
            return

        pythoncom.CoInitialize()
        try:
            self._loop()
        finally:
            # 绝不能 gc.collect()：GC 回收进程级垃圾链，会把其他 COM 线程
            # （通话/蓝牙）的对象跨套间 Release → 0xC0000005。
            # 本线程查询对象都是局部变量，引用计数确定性释放。
            # 不调用 CoUninitialize()：它会销毁进程级 COM 状态，
            # 导致其他线程的 ctypes.windll 缓存失效 → _ctypes.pyd 0xC0000005
            pass

    def _loop(self):
        # 首次立即查询
        self._poll_once()
        while not self._stop_event.is_set():
            # 等下一次轮询或被唤醒（打开日历）
            triggered = self._wakeup.wait(POLL_S)
            if self._stop_event.is_set():
                return
            if triggered:
                self._wakeup.clear()
                # 处理打开请求（ None / 空串 视为打开日历视图）
                pending = self._pending_open
                self._pending_open = None
                if pending is not None:
                    self._do_open_in_outlook(pending)
                    continue  # 不立即轮询，等下一周期
            self._poll_once()

    def _poll_once(self):
        """查询下一条日程，判定是否需要弹通知"""
        now = datetime.now()
        ev = self._fetch_next_appointment(now)

        # 去重 GC：清理过期的 fired 记录
        now_mono = time.monotonic()
        if self._fired:
            self._fired = {k: v for k, v in self._fired.items()
                           if now_mono - v < FIRED_TTL_S}

        if ev is None:
            return

        # 临近判定：≤ APPROACH_MIN 分钟即将开始，或已开始但未结束
        if ev["end"] < now:
            return  # 已结束（理论上 _fetch_next_appointment 已过滤）

        time_to_start = (ev["start"] - now).total_seconds()
        if time_to_start > APPROACH_MIN * 60:
            return  # 还太远

        dedup_key = (ev["entry_id"], ev["start"].isoformat())
        if dedup_key in self._fired:
            return  # 这一条日程已触发过
        self._fired[dedup_key] = now_mono
        self.approaching.emit(ev)

    def _fetch_next_appointment(self, now):
        """查询下一条未结束的日程，返回 dict 或 None

        - 仅当 Outlook 已运行时查询（避免冷启动 Outlook 拖慢系统）
        - 未运行 / 未装 / 出错时返回 None
        """
        try:
            if not self._is_outlook_running():
                return None
            import win32com.client
            app = win32com.client.Dispatch("Outlook.Application")
            ns = app.GetNamespace("MAPI")
            folder = ns.GetDefaultFolder(OL_FOLDER_CALENDAR)
            items = folder.Items
            items.Sort("[Start]")
            items.IncludeRecurrences = True

            lookahead = now + timedelta(days=MAX_LOOKAHEAD_DAYS)
            scanned = 0
            for item in items:
                scanned += 1
                if scanned > SCAN_LIMIT:
                    break
                try:
                    start = self._parse_dt(item.Start)
                    end = self._parse_dt(item.End)
                    if end < now:
                        continue  # 已结束
                    if start > lookahead:
                        break  # 排序后到未来太远
                    subject = str(item.Subject or "(无标题)")
                    location = str(item.Location or "")
                    entry_id = str(item.EntryID)
                    all_day = bool(item.AllDayEvent)
                    return {
                        "subject": subject,
                        "start": start,
                        "end": end,
                        "location": location,
                        "entry_id": entry_id,
                        "all_day": all_day,
                    }
                except Exception:
                    continue
            return None
        except Exception as e:
            print(f"[Calendar] 查询 Outlook 失败: {e}")
            return None

    @staticmethod
    def _is_outlook_running():
        """Outlook 未运行时跳过 COM Dispatch，避免冷启动拖慢系统"""
        try:
            import psutil
            for p in psutil.process_iter(['name']):
                if (p.info['name'] or '').lower() == 'outlook.exe':
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _parse_dt(value):
        """Outlook COM 返回的日期可能是 datetime / pywintime / 字符串"""
        if isinstance(value, datetime):
            return value
        try:
            from win32com.client import MakeTime
            t = MakeTime(value)
            return datetime(t.year, t.month, t.day,
                            t.hour, t.minute, t.second)
        except Exception:
            pass
        for fmt in ("%m/%d/%Y %I:%M:%S %p", "%Y-%m-%d %H:%M:%S",
                    "%m/%d/%Y %H:%M:%S"):
            try:
                return datetime.strptime(str(value), fmt)
            except ValueError:
                continue
        return datetime.now()

    def _do_open_in_outlook(self, entry_id):
        """通过 EntryID 在 Outlook 中打开指定约会，或打开日历视图"""
        try:
            if not self._is_outlook_running():
                return
            import win32com.client
            app = win32com.client.Dispatch("Outlook.Application")
            ns = app.GetNamespace("MAPI")
            if entry_id:
                item = ns.GetItemFromID(entry_id)
                item.Display(False)
            else:
                folder = ns.GetDefaultFolder(OL_FOLDER_CALENDAR)
                folder.Display()
        except Exception as e:
            print(f"[Calendar] 打开 Outlook 约会失败: {e}")
