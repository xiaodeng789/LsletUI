#!/usr/bin/env python3
"""
LsletUI - 全局下载进度监控后端
监听浏览器（Edge/Chrome/Brave/Vivaldi）与常见下载器（迅雷等）的下载过程：

1. 轮询扫描下载目录中的未完成文件（.crdownload / .part / .xltd / .td），
   通过文件大小增量计算实时下载速度；
2. 首次发现新的未完成文件时，复制浏览器 History 数据库（浏览器运行中
   也可以复制）并查询 downloads 表，用 current_path 匹配拿到 total_bytes，
   从而得到进度百分比。总大小按路径缓存，不需要反复读库；
3. 未完成文件消失且最终文件存在时判定为下载完成，短暂提示后恢复。

仅依赖标准库，不使用 psutil。
"""

import ctypes
import json
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer

# 未完成文件后缀（Chrome/Edge: .crdownload；Firefox: .part；迅雷: .xltd/.td/.emule、
# FDM: .fpart、百度网盘: .baiduyd、BitComet: .bc!、qBittorrent: .!qB、
# uTorrent: .!ut、Opera: .opdownload）
PARTIAL_SUFFIXES = (".crdownload", ".part", ".xltd", ".td", ".emule",
                    ".fpart", ".baiduyd", ".bc!", ".!qb", ".!ut", ".opdownload")

# Chromium（Edge/Chrome）解析出最终文件名前用 "未确认 NNNNNN.crdownload"
#（英文版 Unconfirmed）作为临时名；文件名解析后/下载完成时会把它改名，
# 不能按"去后缀"推算最终名，完成检测需在同目录找刚落地的真实文件
UNCONFIRMED_RE = re.compile(r"^(?:未确认|Unconfirmed)[\s_]*\d+$", re.IGNORECASE)
RENAME_SCAN_WINDOW_S = 5.0   # 临时文件消失后，在同目录找改名文件的时限

# 发现扫描额外识别 aria2/Motrix 的 .aria2 控制文件（下载本体是同名去掉该后缀）
DISCOVERY_SUFFIXES = PARTIAL_SUFFIXES + (".aria2",)

# 全盘发现扫描跳过的系统目录（小写比较）
SKIP_DIR_NAMES = {
    "windows", "program files", "program files (x86)", "programdata",
    "users", "$recycle.bin", "system volume information", "recovery",
}

# 浏览器 User Data 根目录（内含各 Profile 的 History 数据库与 Preferences）
BROWSER_USER_DATA_DIRS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data",
    Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "User Data",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Vivaldi" / "User Data",
]

POLL_MS = 2000          # 轮询间隔（2秒足够感知下载进度变化，大幅降低 I/O 开销）
PAUSED_AFTER_S = 8.0    # 无活跃信号超过该时间视为已暂停（≥4 个轮询周期，防误判）
PAUSED_DROP_S = 5.0     # "已暂停"显示该时长后转入休眠（磁盘遗留文件不代表还有任务）
MTIME_FRESH_S = 1.5     # mtime 距今小于该值视为活跃（必须 < POLL_MS/1000 避免竞争）
SPEED_ZERO_S = 3.0      # 无增长超过该时间速度归零（避免显示残留速度）
DB_RETRY_MAX = 15       # 新文件查询总大小的最大重试次数
COMPLETED_SHOW_S = 4.0  # 下载完成后胶囊继续显示的时长
SPEED_EMA = 0.55        # 速度指数平滑系数（越大越跟随瞬时值）
SCAN_DEPTH = 3          # 下载目录递归扫描深度

# ── 状态防抖 ──
# 核心原则：状态切换必须经过确认，禁止单次信号翻转
PAUSED_CONFIRM_POLLS = 3    # 连续 3 次无活跃信号 → 确认暂停（≥6 秒）
RESUME_CONFIRM_POLLS = 1    # 1 次活跃信号 → 确认恢复下载
VERIFY_INTERVAL_POLLS = 5   # 每 5 次轮询（10 秒）做一次深度状态校验


def _norm(p):
    """路径标准化（用于 History DB 匹配与字典键）"""
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def _strip_partial(name):
    """去掉未完成文件后缀得到最终文件名；不是已知后缀返回 None"""
    lower = name.lower()
    for suffix in PARTIAL_SUFFIXES:
        if lower.endswith(suffix):
            return name[: -len(suffix)]
    return None


def base_partial_name(path):
    """未完成文件去掉后缀后的基础名（用于判断是否 Chromium 临时命名）"""
    name = Path(path).name
    return _strip_partial(name) or name


def _shell_folders():
    """从注册表读取真实的 下载/桌面/文档 目录（用户迁移到其他盘也能拿到）"""
    dirs = []
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion"
            r"\Explorer\User Shell Folders")
        names = ("{374DE290-123F-4565-9164-39C4925E467B}",  # Downloads
                 "Desktop",                                  # 桌面
                 "Personal",                                 # 文档
                 "{F42EE2D3-909F-4907-8871-4C22FC0BF756}")   # 文档(新)
        for name in names:
            try:
                val, _ = winreg.QueryValueEx(key, name)
                p = winreg.ExpandEnvironmentStrings(val)
                if p and os.path.isdir(p):
                    dirs.append(p)
            except OSError:
                continue
    except Exception:
        pass
    if not dirs:
        home = Path.home()
        dirs = [str(home / "Downloads"), str(home / "Desktop"),
                str(home / "Documents")]
    return dirs


def _fixed_drives():
    """列出所有固定磁盘盘符（DRIVE_FIXED=3，不扫U盘/网络盘）"""
    drives = []
    try:
        _kernel32 = ctypes.WinDLL("kernel32")
        bitmask = _kernel32.GetLogicalDrives()
        for i in range(26):
            if not (bitmask >> i) & 1:
                continue
            root = f"{chr(ord('A') + i)}:\\"
            if _kernel32.GetDriveTypeW(root) == 3:
                drives.append(root)
    except Exception:
        pass
    return drives


def _find_download_dirs_under(root, depth):
    """在 root 下限深扫描，返回包含未完成下载文件的目录（用于发现其他盘下载目录）"""
    if depth > 2:
        return []
    hits = []
    try:
        entries = list(os.scandir(root))
    except OSError:
        return hits
    subdirs = []
    for e in entries:
        try:
            if e.is_dir(follow_symlinks=False):
                name = e.name.lower()
                if name in SKIP_DIR_NAMES or e.name.startswith((".", "$")):
                    continue
                subdirs.append(e.path)
            elif e.name.startswith((".", "~$")):
                continue
            elif e.name.lower().endswith(DISCOVERY_SUFFIXES):
                hits.append(root)
        except OSError:
            continue
    for d in subdirs:
        hits.extend(_find_download_dirs_under(d, depth + 1))
    return hits


class DownloadMonitorBackend(QObject):
    """下载监控后端：轮询未完成文件 + 浏览器 History 总大小查询"""

    download_updated = Signal(dict)

    def __init__(self, web_view=None):
        super().__init__()
        self.web_view = web_view

        self._scanning = False
        self._tracked = {}          # normcase(path) -> entry dict
        self._dormant = {}          # 休眠任务（暂停过久/磁盘遗留）：key -> {size, mtime}
        self._total_cache = {}      # normcase(partial path) -> total_bytes
        self._watch_dirs = []       # 监控的下载目录
        self._base_dirs = []        # 常规目录（注册表 shell folders + 浏览器偏好）
        self._dynamic_dirs = []     # 全盘扫描自动发现的下载目录（其他盘/网盘）
        self._prefs_expire = 0.0    # 浏览器 Preferences 刷新时间
        self._poll_count = 0
        self._completed_payload = None
        self._completed_until = 0.0
        self._last_state = None     # 上次推送的状态（active/paused/completed/idle）

        self._refresh_watch_dirs()

        # 轮询定时器（线程模式与 SMTC 后端一致）
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._start_poll_thread)
        self._poll_timer.start(POLL_MS)
        QTimer.singleShot(600, self._start_poll_thread)

    # --- 目录收集 ---
    def _refresh_watch_dirs(self):
        """收集常规监控目录：注册表真实下载/桌面/文档 + 浏览器 Preferences 下载目录"""
        dirs = list(_shell_folders())

        for user_data in BROWSER_USER_DATA_DIRS:
            if not user_data.is_dir():
                continue
            for prefs_file in user_data.glob("*/Preferences"):
                try:
                    data = json.loads(prefs_file.read_text(encoding="utf-8"))
                except Exception:
                    continue
                d = (data.get("download") or {}).get("default_directory")
                if d and os.path.isdir(d):
                    dirs.append(d)

        self._base_dirs = dirs
        self._rebuild_watch_dirs()

    def _rebuild_watch_dirs(self):
        """合并常规目录与全盘扫描发现的目录（去重保序）"""
        seen = set()
        result = []
        for d in list(self._base_dirs) + list(self._dynamic_dirs):
            n = _norm(d)
            if n not in seen:
                seen.add(n)
                result.append(d)
        self._watch_dirs = result

    def _discover_dynamic_dirs(self):
        """全盘浅层扫描：自动发现其他盘上的下载目录（迅雷/网盘/自定义路径）"""
        found = []
        for drive in _fixed_drives():
            found.extend(_find_download_dirs_under(drive, 0))
        seen = {_norm(d) for d in self._base_dirs}
        dynamic = []
        for d in found:
            n = _norm(d)
            if n not in seen:
                seen.add(n)
                dynamic.append(d)
        if dynamic:
            print(f"[Download] 发现其他盘下载目录: {dynamic}")
        self._dynamic_dirs = dynamic
        self._rebuild_watch_dirs()

    # --- 轮询主流程 ---
    def _start_poll_thread(self):
        if self._scanning:
            return
        thread = threading.Thread(target=self._poll_once, daemon=True)
        thread.start()

    def _poll_once(self):
        self._scanning = True
        try:
            now = time.monotonic()
            self._poll_count += 1
            if self._poll_count % 150 == 1:
                # 启动即扫一次，之后每 150 次轮询（5 分钟）全盘发现一次（降低 I/O 开销）
                self._discover_dynamic_dirs()
            if now >= self._prefs_expire:
                self._refresh_watch_dirs()
                self._prefs_expire = now + 300.0  # 5 分钟刷新一次浏览器偏好

            found = self._scan_partial_files()
            self._update_tracked(found, now)

            # ── 定时深度校验（每 VERIFY_INTERVAL_POLLS 次轮询 = 10 秒）──
            # 兜底：重新 stat 所有跟踪文件，交叉验证 History DB 状态，
            # 修复偶发的信号丢失导致的状态不同步
            if self._poll_count % VERIFY_INTERVAL_POLLS == 0 and self._tracked:
                self._verify_tracked(now)

            payload = self._build_payload(now)
            self._maybe_emit(payload)
        except Exception as e:
            print(f"[Download] 轮询失败: {e}")
        finally:
            self._scanning = False

    # --- 文件扫描 ---
    def _scan_partial_files(self):
        """扫描监控目录中的未完成文件，返回 {normcase(path): info}"""
        found = {}
        for d in self._watch_dirs:
            try:
                self._walk(d, 0, found)
            except Exception:
                continue
        return found

    def _walk(self, directory, depth, found):
        if depth > SCAN_DEPTH:
            return
        try:
            entries = list(os.scandir(directory))
        except OSError:
            return
        for e in entries:
            name = e.name
            try:
                if e.is_dir(follow_symlinks=False):
                    if name.startswith((".", "$")) or name.lower() in {
                            "node_modules", "__pycache__"}:
                        continue
                    self._walk(e.path, depth + 1, found)
                else:
                    if name.startswith((".", "~$")):
                        continue
                    lower = name.lower()
                    if lower.endswith(".aria2"):
                        # aria2/Motrix：控制文件旁边的真实文件才是下载本体
                        target = e.path[:-len(".aria2")]
                        try:
                            st = os.stat(target)
                        except OSError:
                            continue
                        found[_norm(target)] = {
                            "path": target,
                            "size": st.st_size,
                            "mtime": st.st_mtime,
                        }
                        continue
                    if not lower.endswith(PARTIAL_SUFFIXES):
                        continue
                    st = e.stat()
                    found[_norm(e.path)] = {
                        "path": e.path,
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                    }
            except OSError:
                continue

    # --- 状态跟踪 ---
    def _update_tracked(self, found, now):
        # 1. 新出现的文件（休眠中的文件须有新写入活动才重新激活）
        for key, info in found.items():
            if key in self._tracked:
                continue
            if key in self._dormant:
                d = self._dormant[key]
                mtime = info.get("mtime", 0)
                resumed = (info["size"] > d.get("size", 0)
                           or mtime != d.get("mtime")
                           or (time.time() - mtime) < MTIME_FRESH_S)
                if not resumed:
                    continue
                del self._dormant[key]
                print(f"[Download] 暂停任务恢复下载: {Path(info['path']).name}")
            final_name = _strip_partial(Path(info["path"]).name)
            entry = {
                "path": info["path"],
                "final_path": str(Path(info["path"]).parent / (final_name or Path(info["path"]).name)),
                "target_path": None,
                "size": info["size"],
                "prev_size": info["size"],
                "prev_time": now,
                "speed": 0.0,
                "total": self._total_cache.get(key, 0),
                "last_growth": now,
                "created": now,
                "db_tries": 0 if self._total_cache.get(key) is None else DB_RETRY_MAX,
                "needs_total": self._total_cache.get(key) is None,
                "mtime": info["mtime"],
                "last_activity": now,
                "announced": False,
                # ── 状态防抖字段 ──
                "inactive_streak": 0,          # 连续无活跃信号的轮询次数
                "confirmed_state": "downloading",  # 防抖后的确认状态
                "db_state": None,              # History DB 返回的原始状态
            }
            self._tracked[key] = entry
            print(f"[Download] 发现下载任务: {Path(entry['final_path']).name}")

        # 2. 大小变化 -> 速度；消失 -> 完成/取消
        for key in list(self._tracked.keys()):
            entry = self._tracked[key]
            if key in found:
                info = found[key]
                entry["prev_size"] = entry["size"]
                entry["prev_time"] = entry.get("last_poll", now)
                entry["last_poll"] = now
                delta = info["size"] - entry["size"]
                mtime = info.get("mtime", 0)
                prev_mtime = entry.get("mtime", 0)
                # ── 活跃信号判定（优先级从高到低）──
                # 1) 文件大小增长 → 确定活跃
                # 2) mtime 发生变化 → 有写入活动（含预分配文件大小不变的场景）
                # 3) mtime 很新（< 1.5s）→ 刚被写入过
                # 注意：条件 3 的阈值 MTIME_FRESH_S=1.5 严格 < POLL_MS/1000=2.0，
                # 避免"上次轮询时 mtime 恰好 2.0s"在下轮被误判为新鲜
                size_grew = delta > 0
                mtime_changed = mtime != prev_mtime
                mtime_fresh = (time.time() - mtime) < MTIME_FRESH_S
                active_signal = size_grew or mtime_changed or mtime_fresh

                entry["size"] = info["size"]
                entry["mtime"] = mtime
                if delta > 0:
                    dt = max(0.2, now - entry["prev_time"])
                    inst = delta / dt
                    entry["speed"] = inst if entry["speed"] <= 0 else \
                        SPEED_EMA * inst + (1 - SPEED_EMA) * entry["speed"]
                    entry["last_growth"] = now
                elif now - entry["last_growth"] > SPEED_ZERO_S:
                    entry["speed"] = 0.0

                # ── 状态防抖状态机 ──
                # 分支 A：检测到活跃信号 → 立即恢复/保持 downloading
                # 分支 B：无活跃信号 → 累计 inactive_streak
                #   B1：streak >= PAUSED_CONFIRM_POLLS → 确认 paused
                #   B2：streak < PAUSED_CONFIRM_POLLS → 维持当前状态
                if active_signal:
                    entry["last_activity"] = now
                    entry["inactive_streak"] = 0
                    if entry["confirmed_state"] != "downloading":
                        entry["confirmed_state"] = "downloading"
                else:
                    entry["inactive_streak"] = entry.get("inactive_streak", 0) + 1
                    if (entry["confirmed_state"] == "downloading"
                            and entry["inactive_streak"] >= PAUSED_CONFIRM_POLLS):
                        entry["confirmed_state"] = "paused"
                        print(f"[Download] 状态切换 → 已暂停（连续 "
                              f"{entry['inactive_streak']} 次无信号）: "
                              f"{Path(entry['final_path']).name}")
            else:
                # 文件消失：最终文件存在 -> 完成；否则视为取消
                final = Path(entry["final_path"])
                if final.exists():
                    self._completed_payload = {
                        "active": False,
                        "state": "completed",
                        "filename": final.name,
                        "received": entry["size"],
                        "total": entry["total"],
                        "speed": 0.0,
                        "count": 0,
                    }
                    self._completed_until = now + COMPLETED_SHOW_S
                    print(f"[Download] 下载完成: {final.name}")
                elif UNCONFIRMED_RE.match(base_partial_name(entry["path"])):
                    # Edge/Chrome 的 "未确认 NNN.crdownload" 在文件名解析后/
                    # 完成时会被改名成真实文件（最终名 ≠ 去后缀名），在同目录
                    # 找刚落地的最终文件判定完成；找不到则被新 .crdownload 接管
                    #（新任务下一轮自动跟踪），静默处理即可
                    renamed = self._find_renamed_file(Path(entry["path"]).parent)
                    if renamed is not None:
                        try:
                            size = renamed.stat().st_size
                        except OSError:
                            size = entry["size"]
                        self._completed_payload = {
                            "active": False,
                            "state": "completed",
                            "filename": renamed.name,
                            "received": size,
                            "total": entry["total"],
                            "speed": 0.0,
                            "count": 0,
                        }
                        self._completed_until = now + COMPLETED_SHOW_S
                        print(f"[Download] 下载完成（临时名改写）: {renamed.name}")
                    else:
                        print(f"[Download] 未确认临时文件结束（改名接管中）: "
                              f"{Path(entry['path']).name}")
                else:
                    print(f"[Download] 下载已取消: {Path(entry['final_path']).name}")
                del self._tracked[key]

        # 3. "已暂停"显示一段时间后转入休眠（迅雷/网盘任务删除后文件常留在
        #    磁盘上，不能让它一直占着胶囊）；休眠期间文件被删除则直接清理
        for key in list(self._tracked.keys()):
            entry = self._tracked[key]
            if (now - entry.get("last_activity", entry["last_growth"])
                    > PAUSED_AFTER_S + PAUSED_DROP_S):
                self._dormant[key] = {"size": entry["size"],
                                      "mtime": entry.get("mtime", 0)}
                del self._tracked[key]
                print(f"[Download] 任务长时间无活动，暂不再显示: "
                      f"{Path(entry['final_path']).name}")
        for key in list(self._dormant.keys()):
            if key not in found:
                del self._dormant[key]

        # 4. 查询未知总大小（复制浏览器 History 数据库）
        pending = [e for e in self._tracked.values()
                   if e["needs_total"] and e["db_tries"] < DB_RETRY_MAX]
        if pending:
            self._lookup_totals(pending)

    def _verify_tracked(self, now):
        """深度校验：重新 stat 所有跟踪文件 + 交叉验证 History DB 状态

        每 VERIFY_INTERVAL_POLLS 次轮询（10 秒）调用一次。
        目的：修复偶发的信号丢失导致状态不同步。
        """
        for key in list(self._tracked.keys()):
            entry = self._tracked[key]
            fpath = entry["path"]
            try:
                st = os.stat(fpath)
            except OSError:
                # 文件已消失 → 下一轮 _update_tracked 会处理完成/取消判定
                continue

            current_size = st.st_size
            current_mtime = st.st_mtime
            prev_size = entry["size"]  # 保留原始值供后续 DB 校验比较

            # ── 校验 1：文件大小是否与轮询一致 ──
            # 如果不一致，说明常规轮询漏掉了变化，立即修正
            if current_size != prev_size:
                delta = current_size - prev_size
                if delta > 0:
                    entry["speed"] = max(entry["speed"], delta / max(1.0, VERIFY_INTERVAL_POLLS * POLL_MS / 1000))
                    entry["last_growth"] = now
                entry["size"] = current_size
                entry["inactive_streak"] = 0
                if entry["confirmed_state"] != "downloading":
                    entry["confirmed_state"] = "downloading"

            # ── 校验 2：mtime 新鲜度 ──
            # 如果 mtime 很新但 inactive_streak > 0，说明常规轮询误判了
            if (time.time() - current_mtime) < MTIME_FRESH_S:
                if entry["inactive_streak"] > 0:
                    entry["inactive_streak"] = 0
                    if entry["confirmed_state"] != "downloading":
                        entry["confirmed_state"] = "downloading"
                entry["last_activity"] = now

            # ── 校验 3：History DB 状态交叉验证 ──
            # 如果 DB 显示下载已中断/取消，但文件未增长 → 强制暂停
            # 注意：用 prev_size（校验前的大小）比较，避免校验 1 已覆盖 entry["size"]
            db_state = entry.get("db_state")
            if db_state is not None and db_state != 0:
                # state != 0: CANCELLED(1) 或 INTERRUPTED(2)
                # 仅当文件未增长时才信任 DB（DB 更新可能滞后于实际恢复）
                if (entry["confirmed_state"] == "downloading"
                        and current_size <= prev_size):
                    entry["confirmed_state"] = "paused"
                    entry["inactive_streak"] = PAUSED_CONFIRM_POLLS
                    print(f"[Download] DB 校验：任务已中断(state={db_state})，"
                          f"强制暂停: {Path(entry['final_path']).name}")

        # ── 校验 4：定期重新查询 History DB 获取最新状态 ──
        # 每 3 次校验（30 秒）刷新一次 DB 状态，捕获浏览器端的暂停/恢复操作
        if self._poll_count % (VERIFY_INTERVAL_POLLS * 3) == 0:
            self._requery_db_states()

    def _requery_db_states(self):
        """重新查询 History DB 获取所有跟踪任务的最新 state 字段

        不查 total（已有缓存），只更新 state，用于交叉验证。
        """
        targets = {_norm(e["path"]): e for e in self._tracked.values()}
        if not targets:
            return
        for user_data in BROWSER_USER_DATA_DIRS:
            if not user_data.is_dir():
                continue
            for history in user_data.glob("*/History"):
                rows = self._copy_and_query(history, set(targets.keys()))
                for key, row in rows.items():
                    entry = targets.get(key)
                    if entry is not None:
                        entry["db_state"] = row.get("state")

    def _find_renamed_file(self, directory):
        """未确认临时文件消失后，在同目录找 RENAME_SCAN_WINDOW_S 内刚落地的
        最终文件（Chromium 改名完成）；没有返回 None"""
        cutoff = time.time() - RENAME_SCAN_WINDOW_S
        best = None
        try:
            entries = list(os.scandir(directory))
        except OSError:
            return None
        for e in entries:
            name = e.name
            try:
                if name.startswith((".", "~$")):
                    continue
                if name.lower().endswith(DISCOVERY_SUFFIXES):
                    continue
                st = e.stat()
                if st.st_mtime < cutoff:
                    continue
                if best is None or st.st_mtime > best[1]:
                    best = (Path(e.path), st.st_mtime)
            except OSError:
                continue
        return best[0] if best else None

    def _lookup_totals(self, entries):
        """复制浏览器 History 库，按 current_path 匹配 total_bytes 与真实文件名"""
        targets = {_norm(e["path"]) for e in entries}
        for user_data in BROWSER_USER_DATA_DIRS:
            if not user_data.is_dir() or not targets:
                continue
            for history in user_data.glob("*/History"):
                rows = self._copy_and_query(history, targets)
                if not rows:
                    continue
                for e in entries:
                    key = _norm(e["path"])
                    row = rows.get(key)
                    if row is None:
                        continue
                    total = row["total"]
                    e["total"] = total if total and total > 0 else 0
                    if row.get("target"):
                        # History 里的 target_path 是浏览器认定的最终路径，
                        # 未确认临时名的真实文件名只能从这里拿到
                        e["target_path"] = row["target"]
                        e["final_path"] = row["target"]
                    # 记录浏览器报告的下载状态（0=进行中, 1=已取消, 2=已中断）
                    e["db_state"] = row.get("state")
                    e["needs_total"] = False
                    self._total_cache[key] = e["total"]
                    targets.discard(key)
                if not targets:
                    return
        for e in entries:
            if e["needs_total"]:
                e["db_tries"] += 1

    @staticmethod
    def _copy_and_query(history_path, targets):
        """复制 History（含 -wal）到临时目录后用 sqlite 查询 downloads 表"""
        tmpdir = None
        try:
            tmpdir = tempfile.mkdtemp(prefix="pyisland_dl_")
            dst = Path(tmpdir) / "History"
            shutil.copy2(history_path, dst)
            wal = history_path.parent / "History-wal"
            if wal.exists():
                try:
                    shutil.copy2(wal, Path(tmpdir) / "History-wal")
                except OSError:
                    pass

            rows = {}
            con = sqlite3.connect(str(dst))
            try:
                cur = con.execute(
                    "SELECT current_path, target_path, total_bytes, state "
                    "FROM downloads")
                for current_path, target_path, total_bytes, state in cur.fetchall():
                    key = _norm(current_path)
                    if key in targets:
                        rows[key] = {"total": total_bytes or 0,
                                     "target": target_path or "",
                                     "state": state}
            finally:
                con.close()
            return rows
        except Exception:
            return {}
        finally:
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)

    # --- payload 组装与推送 ---
    def _build_payload(self, now):
        if self._tracked:
            primary = max(self._tracked.values(),
                          key=lambda e: e.get("last_activity", e["last_growth"]))

            # ── 状态判定：防抖确认状态为主，时间阈值为兜底 ──
            # 分支 1：防抖状态为 paused → 直接采用
            # 分支 2：防抖状态为 downloading 但时间阈值已超 → 强制暂停（兜底）
            # 分支 3：防抖状态为 downloading 且时间未超 → 确认下载中
            confirmed = primary.get("confirmed_state", "downloading")
            time_since_activity = now - primary.get("last_activity",
                                                     primary["last_growth"])
            if confirmed == "paused":
                state = "paused"
            elif time_since_activity > PAUSED_AFTER_S:
                # 兜底：防抖尚未确认但时间已远超阈值 → 强制暂停
                state = "paused"
                primary["confirmed_state"] = "paused"
                primary["inactive_streak"] = PAUSED_CONFIRM_POLLS
            else:
                state = "downloading"

            speed = sum(e["speed"] for e in self._tracked.values())
            if state == "paused":
                speed = 0.0
            filename = Path(primary["final_path"]).name
            if UNCONFIRMED_RE.match(filename):
                # Chromium 临时命名没解析出真实名，置空让胶囊回退显示"下载中"
                filename = ""
            return {
                "active": True,
                "state": state,
                "filename": filename,
                "received": primary["size"],
                "total": primary["total"],
                "speed": speed,
                "count": len(self._tracked),
            }
        if self._completed_payload and now < self._completed_until:
            return self._completed_payload
        if now >= self._completed_until:
            self._completed_payload = None
        return {"active": False, "state": "idle"}

    def _maybe_emit(self, payload):
        state = payload.get("state")
        # 活动中每秒推送（刷新速度）；状态切换（完成/暂停/空闲）也要推送
        if payload.get("active") or state != self._last_state:
            self._last_state = state
            self.download_updated.emit(payload)
            self._push_to_frontend(payload)

    def _push_to_frontend(self, info):
        if self.web_view and self.web_view.page():
            try:
                payload = json.dumps(info, ensure_ascii=True)
                js = f"window.handleDownloadUpdate && window.handleDownloadUpdate({payload});"
                self.web_view.page().runJavaScript(js)
            except Exception as e:
                print(f"[Download] 推送到前端失败: {e}")

    def set_web_view(self, web_view):
        self.web_view = web_view

    def stop(self):
        if self._poll_timer:
            self._poll_timer.stop()
