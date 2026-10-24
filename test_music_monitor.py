#!/usr/bin/env python3
"""
测试音乐监控功能
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from capsule_app.process_monitor_backend import MusicPlayerMonitorBackend

def test_music_monitor():
    """测试音乐监控功能"""
    print("测试音乐监控功能...")
    
    # 创建监控实例
    monitor = MusicPlayerMonitorBackend()
    
    # 打印支持的音乐应用
    print("支持的音乐应用:")
    for player in monitor.MUSIC_PLAYERS:
        print(f"  - {player['display_name']}: {', '.join(player['process_names'])}")
    
    # 检查当前运行的音乐应用
    print("\n检查当前运行的音乐应用...")
    for player in monitor.MUSIC_PLAYERS:
        is_running = monitor._check_process_running(player['process_names'])
        status = "运行中" if is_running else "未运行"
        print(f"  {player['display_name']}: {status}")
    
    print("\n测试完成!")

if __name__ == "__main__":
    test_music_monitor()