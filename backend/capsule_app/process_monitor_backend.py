#!/usr/bin/env python3
"""
LsletUI - 轻量级灵动岛应用
进程监控后端模块
"""

import threading
import json
from PySide6.QtCore import QObject, Signal, QTimer


class ProcessMonitorBackend(QObject):
    """进程监控后端，检测eIsland相关进程是否运行，并推送给前端"""
    
    # 进程状态更新信号
    process_status_updated = Signal(bool)
    
    def __init__(self, web_view=None):
        super().__init__()
        self.web_view = web_view
        self.is_eisland_running = False
        self.scanning = False
        
        # 定时器，每60秒扫描一次进程列表 - 优化：增加间隔到60秒
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._start_scan_thread)
        self.refresh_timer.start(60000)  # 60秒刷新一次（原为30秒）
        
        # 监听状态更新，推送至前端
        self.process_status_updated.connect(self._push_to_frontend)
        
        # 首次扫描，延迟5秒执行
        QTimer.singleShot(5000, self._start_scan_thread)
    
    def set_web_view(self, web_view):
        """设置web_view引用"""
        self.web_view = web_view
    
    def _start_scan_thread(self):
        """在独立线程中启动进程扫描，避免阻塞Qt主线程"""
        if self.scanning:
            return
        thread = threading.Thread(target=self._scan_processes, daemon=True)
        thread.start()
    
    def _scan_processes(self):
        """扫描系统进程，检查是否包含eIsland的进程"""
        self.scanning = True
        try:
            is_running = self._check_eisland_process()
            if is_running != self.is_eisland_running:
                self.is_eisland_running = is_running
                self.process_status_updated.emit(is_running)
                print(f"[ProcessMonitor] eIsland进程状态更新: {'运行中' if is_running else '未运行'}")
        except Exception as e:
            print(f"[ProcessMonitor] 扫描进程失败: {e}")
        finally:
            self.scanning = False
    
    def _check_eisland_process(self):
        """使用 psutil 检查是否存在包含eIsland的进程（避免 PowerShell 启动开销）"""
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                name = (proc.info.get('name') or '').lower()
                if 'eisland' in name or 'cisland' in name:
                    return True
            return False
        except Exception as e:
            print(f"[ProcessMonitor] 检查进程失败: {e}")
            return False
    
    def _push_to_frontend(self, is_running):
        """将进程状态推送给前端"""
        if self.web_view and self.web_view.page():
            try:
                js_code = f"window.handleEIslandStatusUpdate && window.handleEIslandStatusUpdate({str(is_running).lower()});"
                self.web_view.page().runJavaScript(js_code)
                print(f"[ProcessMonitor] 已将eIsland状态推送给前端: {is_running}")
            except Exception as e:
                print(f"[ProcessMonitor] 推送状态到前端失败: {e}")
    
    def stop(self):
        """停止后台任务"""
        self.refresh_timer.stop()


class MusicPlayerMonitorBackend(QObject):
    """音乐播放器监控后端，检测多个音乐应用是否运行，并推送给前端"""
    
    # 音乐播放器状态更新信号
    music_player_status_updated = Signal(dict)
    
    # 支持的音乐应用列表
    MUSIC_PLAYERS = [
        {
            "name": "kugou",
            "display_name": "酷狗音乐",
            "process_names": ["KuGou", "KuGou2024", "KuGouMusic"],
            "icon": "kugou"
        },
        {
            "name": "qqmusic",
            "display_name": "QQ音乐",
            "process_names": ["QQMusic"],
            "icon": "qqmusic"
        },
        {
            "name": "qishui",
            "display_name": "汽水音乐",
            "process_names": ["QishuiMusic", "Qishui", "QSMusic"],
            "icon": "qishui"
        },
        {
            "name": "kuwo",
            "display_name": "酷我音乐",
            "process_names": ["KuwoMusic", "KwMusic", "Kuwo"],
            "icon": "kuwo"
        },
        {
            "name": "netease",
            "display_name": "网易云音乐",
            "process_names": ["CloudMusic", "NeteaseMusic", "cloudmusic"],
            "icon": "netease"
        }
    ]
    
    def __init__(self, web_view=None):
        super().__init__()
        self.web_view = web_view
        self.player_status = {}  # 存储每个播放器的状态
        self.scanning = False
        
        # 初始化播放器状态
        for player in self.MUSIC_PLAYERS:
            self.player_status[player["name"]] = {
                "running": False,
                "display_name": player["display_name"],
                "icon": player["icon"]
            }
        
        # 定时器，每60秒扫描一次进程列表（psutil 枚举很快，无需高频）
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._start_scan_thread)
        self.refresh_timer.start(60000)
        
        # 监听状态更新，推送至前端
        self.music_player_status_updated.connect(self._push_to_frontend)
        
        # 首次扫描，延迟3秒执行
        QTimer.singleShot(3000, self._start_scan_thread)
    
    def set_web_view(self, web_view):
        """设置web_view引用"""
        self.web_view = web_view
    
    def _start_scan_thread(self):
        """在独立线程中启动进程扫描，避免阻塞Qt主线程"""
        if self.scanning:
            return
        thread = threading.Thread(target=self._scan_music_players, daemon=True)
        thread.start()
    
    def _scan_music_players(self):
        """使用 psutil 一次性扫描所有音乐应用（避免多次 PowerShell 启动开销）"""
        self.scanning = True
        try:
            import psutil
            running_names = set()
            for proc in psutil.process_iter(['name']):
                name = proc.info.get('name') or ''
                if name:
                    running_names.add(name.lower())

            status_changed = False
            for player in self.MUSIC_PLAYERS:
                player_name = player["name"]
                is_running = any(
                    pn.lower() in running_names
                    for pn in player["process_names"]
                )
                if is_running != self.player_status[player_name]["running"]:
                    self.player_status[player_name]["running"] = is_running
                    status_changed = True
                    print(f"[MusicMonitor] {player['display_name']} 状态更新: {'运行中' if is_running else '未运行'}")

            if status_changed:
                self.music_player_status_updated.emit(self.player_status)

        except Exception as e:
            print(f"[MusicMonitor] 扫描音乐应用失败: {e}")
        finally:
            self.scanning = False
    
    def _push_to_frontend(self, status):
        """将音乐播放器状态推送给前端"""
        if self.web_view and self.web_view.page():
            try:
                # 构建状态数据
                status_data = {
                    player_name: {
                        "running": info["running"],
                        "displayName": info["display_name"],
                        "icon": info["icon"]
                    }
                    for player_name, info in status.items()
                }
                
                # 推送到前端
                payload = json.dumps(status_data, ensure_ascii=True)
                js_code = f"window.handleMusicPlayerStatusUpdate && window.handleMusicPlayerStatusUpdate({payload});"
                self.web_view.page().runJavaScript(js_code)
                print(f"[MusicMonitor] 已将音乐播放器状态推送给前端")
            except Exception as e:
                print(f"[MusicMonitor] 推送状态到前端失败: {e}")
    
    def stop(self):
        """停止后台任务"""
        self.refresh_timer.stop()