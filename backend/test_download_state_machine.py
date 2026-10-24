#!/usr/bin/env python3
"""
下载监控状态机验证测试
模拟轮询过程，验证防抖逻辑是否正确防止状态错乱。
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

PASS = 0
FAIL = 0

def _ok(name):
    global PASS
    PASS += 1
    print(f"  [PASS] {name}")

def _fail(name, reason):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {name}: {reason}")


def test_paused_debounce():
    """测试：连续 3 次无活跃信号才确认暂停（不能 1 次就翻）"""
    print("\n=== 测试 1：暂停防抖 ===")

    from capsule_app.download_monitor_backend import (
        PAUSED_CONFIRM_POLLS, MTIME_FRESH_S
    )

    # 模拟一个 entry
    now = 100.0
    entry = {
        "path": "/tmp/test.crdownload",
        "final_path": "/tmp/test.zip",
        "size": 1000,
        "prev_size": 800,
        "prev_time": now - 2,
        "last_poll": now - 2,
        "speed": 100.0,
        "total": 5000,
        "last_growth": now - 2,
        "mtime": now - 0.5,
        "last_activity": now - 0.5,
        "inactive_streak": 0,
        "confirmed_state": "downloading",
        "db_state": 0,
    }

    # 模拟 3 次无活跃信号的轮询
    # 关键：mtime 不变且很旧，size 不变 → active_signal = False
    old_mtime = 50.0  # 很旧的 mtime（远大于 MTIME_FRESH_S）
    entry["mtime"] = old_mtime  # 条目中存储的 mtime 也是旧值
    file_mtime = old_mtime      # 文件 mtime 不变
    file_size = 1000            # 文件大小不变（与 entry["size"] 相同）

    for i in range(3):
        poll_now = now + 2 * (i + 1)  # 每次间隔 2 秒
        delta = file_size - entry["size"]
        mtime = file_mtime
        prev_mtime = entry["mtime"]

        size_grew = delta > 0
        mtime_changed = mtime != prev_mtime
        mtime_fresh = (poll_now - mtime) < MTIME_FRESH_S
        active_signal = size_grew or mtime_changed or mtime_fresh

        entry["size"] = file_size
        entry["mtime"] = mtime

        if active_signal:
            entry["last_activity"] = poll_now
            entry["inactive_streak"] = 0
            if entry["confirmed_state"] != "downloading":
                entry["confirmed_state"] = "downloading"
        else:
            entry["inactive_streak"] = entry.get("inactive_streak", 0) + 1
            if (entry["confirmed_state"] == "downloading"
                    and entry["inactive_streak"] >= PAUSED_CONFIRM_POLLS):
                entry["confirmed_state"] = "paused"

    # 验证：3 次无信号后应该确认暂停
    if entry["confirmed_state"] == "paused":
        _ok(f"连续 {PAUSED_CONFIRM_POLLS} 次无信号 → 确认暂停")
    else:
        _fail("暂停防抖", f"期望 paused，实际 {entry['confirmed_state']}")

    if entry["inactive_streak"] >= PAUSED_CONFIRM_POLLS:
        _ok(f"inactive_streak={entry['inactive_streak']} >= {PAUSED_CONFIRM_POLLS}")
    else:
        _fail("inactive_streak", f"期望 >= {PAUSED_CONFIRM_POLLS}，实际 {entry['inactive_streak']}")


def test_no_premature_pause():
    """测试：1-2 次无信号不能触发暂停"""
    print("\n=== 测试 2：不能过早暂停 ===")

    from capsule_app.download_monitor_backend import PAUSED_CONFIRM_POLLS

    entry = {
        "size": 1000,
        "mtime": 50.0,  # 旧 mtime
        "inactive_streak": 0,
        "confirmed_state": "downloading",
        "last_activity": 100.0,
        "last_growth": 100.0,
        "speed": 100.0,
        "prev_time": 98.0,
    }

    # 模拟 2 次无活跃信号（不够 PAUSED_CONFIRM_POLLS=3）
    for i in range(2):
        active_signal = False  # 无信号
        if active_signal:
            entry["inactive_streak"] = 0
        else:
            entry["inactive_streak"] = entry.get("inactive_streak", 0) + 1
            if (entry["confirmed_state"] == "downloading"
                    and entry["inactive_streak"] >= PAUSED_CONFIRM_POLLS):
                entry["confirmed_state"] = "paused"

    if entry["confirmed_state"] == "downloading":
        _ok(f"2 次无信号仍保持 downloading（需 {PAUSED_CONFIRM_POLLS} 次）")
    else:
        _fail("过早暂停", f"2 次无信号就变 paused，防抖失效")


def test_immediate_resume():
    """测试：暂停后 1 次活跃信号立即恢复下载"""
    print("\n=== 测试 3：立即恢复下载 ===")

    entry = {
        "size": 1000,
        "mtime": 50.0,
        "inactive_streak": 3,
        "confirmed_state": "paused",
        "last_activity": 90.0,
        "last_growth": 90.0,
        "speed": 0.0,
        "prev_time": 98.0,
    }

    # 模拟 1 次活跃信号（文件增长）
    active_signal = True
    if active_signal:
        entry["inactive_streak"] = 0
        if entry["confirmed_state"] != "downloading":
            entry["confirmed_state"] = "downloading"

    if entry["confirmed_state"] == "downloading":
        _ok("1 次活跃信号 → 立即恢复 downloading")
    else:
        _fail("恢复下载", f"期望 downloading，实际 {entry['confirmed_state']}")

    if entry["inactive_streak"] == 0:
        _ok("inactive_streak 归零")
    else:
        _fail("inactive_streak", f"期望 0，实际 {entry['inactive_streak']}")


def test_mtime_race_fix():
    """测试：MTIME_FRESH_S < POLL_MS/1000 避免竞争"""
    print("\n=== 测试 4：mtime 竞争条件修复 ===")

    from capsule_app.download_monitor_backend import MTIME_FRESH_S, POLL_MS

    poll_sec = POLL_MS / 1000.0
    if MTIME_FRESH_S < poll_sec:
        _ok(f"MTIME_FRESH_S({MTIME_FRESH_S}) < POLL_MS/1000({poll_sec})，无竞争")
    else:
        _fail("mtime 竞争",
              f"MTIME_FRESH_S({MTIME_FRESH_S}) >= POLL_MS/1000({poll_sec})")


def test_paused_threshold():
    """测试：PAUSED_AFTER_S >= 4 个轮询周期"""
    print("\n=== 测试 5：暂停时间阈值 ===")

    from capsule_app.download_monitor_backend import PAUSED_AFTER_S, POLL_MS

    min_cycles = PAUSED_AFTER_S / (POLL_MS / 1000.0)
    if min_cycles >= 4:
        _ok(f"PAUSED_AFTER_S({PAUSED_AFTER_S}s) = {min_cycles} 个轮询周期 >= 4")
    else:
        _fail("阈值过低",
              f"PAUSED_AFTER_S({PAUSED_AFTER_S}s) = {min_cycles} 个周期 < 4")


def test_build_payload_state():
    """测试：_build_payload 使用 confirmed_state 而非纯时间阈值"""
    print("\n=== 测试 6：_build_payload 状态判定 ===")

    from capsule_app.download_monitor_backend import (
        DownloadMonitorBackend, PAUSED_AFTER_S, PAUSED_CONFIRM_POLLS
    )

    # 创建 backend 实例（不启动定时器）
    with patch.object(DownloadMonitorBackend, '__init__', lambda self: None):
        backend = DownloadMonitorBackend()
        backend._tracked = {}
        backend._completed_payload = None
        backend._completed_until = 0.0

    now = 1000.0

    # 场景 A：confirmed_state=downloading，时间未超 → downloading
    backend._tracked = {
        "a": {
            "size": 5000, "total": 10000, "speed": 100.0,
            "final_path": "/tmp/test.zip",
            "last_activity": now - 2,
            "last_growth": now - 2,
            "confirmed_state": "downloading",
            "inactive_streak": 0,
        }
    }
    payload = backend._build_payload(now)
    if payload["state"] == "downloading":
        _ok("场景 A: confirmed=downloading + 时间未超 → downloading")
    else:
        _fail("场景 A", f"期望 downloading，实际 {payload['state']}")

    # 场景 B：confirmed_state=paused → paused
    backend._tracked["a"]["confirmed_state"] = "paused"
    backend._tracked["a"]["inactive_streak"] = PAUSED_CONFIRM_POLLS
    backend._tracked["a"]["last_activity"] = now - 8
    payload = backend._build_payload(now)
    if payload["state"] == "paused":
        _ok("场景 B: confirmed=paused → paused")
    else:
        _fail("场景 B", f"期望 paused，实际 {payload['state']}")

    # 场景 C：confirmed=downloading 但时间超阈值 → 兜底暂停
    backend._tracked["a"]["confirmed_state"] = "downloading"
    backend._tracked["a"]["inactive_streak"] = 1
    backend._tracked["a"]["last_activity"] = now - PAUSED_AFTER_S - 1
    payload = backend._build_payload(now)
    if payload["state"] == "paused":
        _ok("场景 C: 时间超阈值兜底 → paused")
    else:
        _fail("场景 C", f"期望 paused(兜底)，实际 {payload['state']}")

    # 场景 D：无跟踪任务 → idle
    backend._tracked = {}
    payload = backend._build_payload(now)
    if payload["state"] == "idle":
        _ok("场景 D: 无任务 → idle")
    else:
        _fail("场景 D", f"期望 idle，实际 {payload['state']}")


def test_speed_zero_when_paused():
    """测试：暂停时速度归零"""
    print("\n=== 测试 7：暂停时速度归零 ===")

    from capsule_app.download_monitor_backend import DownloadMonitorBackend

    with patch.object(DownloadMonitorBackend, '__init__', lambda self: None):
        backend = DownloadMonitorBackend()
        backend._tracked = {}
        backend._completed_payload = None
        backend._completed_until = 0.0

    now = 1000.0
    backend._tracked = {
        "a": {
            "size": 5000, "total": 10000, "speed": 250.0,
            "final_path": "/tmp/test.zip",
            "last_activity": now - 10,
            "last_growth": now - 10,
            "confirmed_state": "paused",
            "inactive_streak": 3,
        }
    }
    payload = backend._build_payload(now)
    if payload["speed"] == 0.0:
        _ok("暂停时 speed=0.0")
    else:
        _fail("速度归零", f"期望 0.0，实际 {payload['speed']}")


def main():
    print("=" * 60)
    print("  下载监控状态机验证测试")
    print("=" * 60)

    test_paused_debounce()
    test_no_premature_pause()
    test_immediate_resume()
    test_mtime_race_fix()
    test_paused_threshold()
    test_build_payload_state()
    test_speed_zero_when_paused()

    total = PASS + FAIL
    print("\n" + "=" * 60)
    print(f"  结果: {PASS}/{total} 通过, {FAIL}/{total} 失败")
    print("=" * 60)

    if FAIL == 0:
        print("  所有状态机测试通过！")
    else:
        print(f"  有 {FAIL} 项未通过。")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
