#!/usr/bin/env python3
"""LsletUI - 日志总线（控制台窗口的数据源）

把所有 print / traceback 输出同时镜像到内存环形缓冲，供控制台窗口
以 QTimer 轮询方式展示。后台线程（SMTC/蓝牙/下载等）直接调用
sink.write()，全程不触碰 Qt 对象，不存在跨线程信号问题。

用法：
    from capsule_app.log_bus import get_log_sink
    sys.stdout = Tee(sys.stdout, log_file, get_log_sink())
"""

import threading
from collections import deque

_MAX_LINES = 4000

_lock = threading.Lock()
_lines = deque(maxlen=_MAX_LINES)   # 元素: (seq:int, text:str)
_seq = 0


class LogStream:
    """伪装成文件对象的 sink：缓冲到换行符，按行入队。

    print() 底层会分两次 write（内容 + "\\n"），不同线程的 write 可能
    交错，因此加锁拼接，保证队列里永远是完整的一行。
    """

    def __init__(self):
        self._buf = ""

    def write(self, data):
        if not data:
            return 0
        global _seq
        with _lock:
            for ch in data:
                if ch == "\n":
                    _seq += 1
                    _lines.append((_seq, self._buf))
                    self._buf = ""
                else:
                    self._buf += ch
        return len(data)

    def flush(self):
        pass

    # 兼容 _Tee 探测的属性
    def isatty(self):
        return False


_sink = LogStream()


def get_log_sink():
    return _sink


def snapshot_after(last_seq):
    """返回 (新行列表, 最新seq)。新行列表是 seq > last_seq 的所有行。

    若调用方落后太多（行已被挤出环形缓冲），会在结果前补一条提示。
    """
    with _lock:
        items = list(_lines)
    if not items:
        return [], last_seq
    newest = items[-1][0]
    out = [text for seq, text in items if seq > last_seq]
    if items[0][0] > last_seq + 1 and last_seq > 0:
        skipped = items[0][0] - last_seq - 1
        out.insert(0, f"…（缓冲已满，跳过 {skipped} 行历史日志）…")
    return out, newest


def full_history():
    """返回当前缓冲里全部行（用于过滤条件变化时整窗重绘）。"""
    with _lock:
        return [text for _seq_, text in _lines], (_lines[-1][0] if _lines else 0)
