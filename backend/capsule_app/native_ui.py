#!/usr/bin/env python3
"""LsletUI 原生界面：深色毛玻璃风、Segoe UI、中英文字典。

设计基调与灵动岛（DynamicIslandWidget）保持一致：
- 深黑底 #0a0a0f + 深蓝紫点缀 #3a8dff（对应 island 里的 accent QColor(100,180,255)）
- 导航栏选中项有左侧霓虹蓝指示条 + 半透明蓝底
- 卡片 #1a1a22 / 边框 #2a2a35 圆角 10px
- 按钮主色蓝渐变、圆角 6px
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QPainter

# 指向 backend/img 资源目录
_IMG_DIR = Path(__file__).resolve().parent.parent / "img"

STRINGS = {
    "zh": {
        "app.title": "LsletUI",
        "nav.bluetooth": "蓝牙设备",
        "nav.music": "正在播放",
        "nav.home": "主界面",
        "nav.log": "日志",
        "nav.settings": "设置",
        "nav.todo": "待办事项",
        "nav.links": "快捷链接",
        "nav.about": "关于",
        "tray.showMain": "打开主界面",
        "tray.hideMain": "隐藏主界面",
        "tray.showIsland": "显示灵动岛",
        "tray.hideIsland": "隐藏灵动岛",
        "tray.settings": "控制台",
        "tray.exit": "退出",
        "settings.title": "LsletUI 设置",
        "settings.general": "通用",
        "settings.autostart": "开机自启动",
        "settings.autostart.desc": "登录 Windows 后自动运行 LsletUI",
        "settings.autoDim": "自动减淡",
        "settings.autoDim.desc": "一段时间不操作后胶囊自动变暗",
        "settings.liquidGlass": "液态玻璃",
        "settings.liquidGlass.desc": "在灵动岛下方渲染实时折射玻璃层",
        "settings.liquidGlass.unsupported": "当前硬件不满足要求，液态玻璃特效不可用，仅支持基础原皮模式",
        "settings.dimDelay": "无操作延迟",
        "settings.seconds": "{n} 秒",
        "settings.language": "语言",
        "settings.language.desc": "切换界面显示语言",
        "settings.alerts": "灵动岛提醒",
        "settings.notify.bluetooth": "蓝牙连接提醒",
        "settings.notify.bluetooth.desc": "耳机连接/断开时弹出通知",
        "settings.notify.clipboard": "剪贴板记录",
        "settings.notify.clipboard.desc": "复制时弹出提醒并保留历史",
        "settings.notify.hardware": "硬件高负载告警",
        "settings.notify.hardware.desc": "CPU/内存/GPU 过载时提醒",
        "settings.data": "数据",
        "settings.clearClipboard": "清空剪贴板历史",
        "settings.clearClipboard.desc": "删除本地保存的复制记录",
        "settings.clear": "清空",
        "settings.cleared": "已清空剪贴板历史",
        "bt.title": "蓝牙设备",
        "bt.off": "已关闭",
        "bt.on": "已开启",
        "bt.detecting": "检测中...",
        "bt.scanning": "扫描中 {s}s",
        "bt.offHint": "蓝牙已关闭，请在系统设置中开启蓝牙",
        "bt.noDevices": "未识别到设备",
        "bt.battery": "电量 {n}%",
        "todo.title": "待办事项",
        "todo.placeholder": "添加新的待办事项...",
        "todo.add": "添加",
        "todo.empty": "暂无待办事项",
        "todo.filter_all": "全部",
        "todo.filter_active": "进行中",
        "todo.filter_done": "已完成",
        "todo.clearDone": "清空已完成",
        "todo.delete": "删除",
        "todo.remind": "提醒",
        "todo.remindIn10": "10 分钟后",
        "todo.remindIn60": "1 小时后",
        "todo.remindTomorrow": "明天 9 点",
        "todo.remindCustom": "自定义时间…",
        "todo.remindClear": "清除提醒",
        "todo.reminded": "已提醒",
        "music.title": "正在播放",
        "music.subtitle": "Windows SMTC 实时监控",
        "music.playing": "播放中",
        "music.notPlaying": "未播放",
        "music.unknownArtist": "未知歌手",
        "music.noMusic": "暂无正在播放的音乐",
        "music.noMusicHint": "打开网易云、QQ音乐等应用即可看到",
        "music.prev": "上一曲",
        "music.play": "播放/暂停",
        "music.next": "下一曲",
        "wait.title": "快捷链接",
        "wait.website": "官网",
        "wait.thanks": "感谢使用 LsletUI",
        "about.title": "关于 LsletUI",
        "about.help": "帮助",
        "about.history": "剪贴板历史",
        "about.bug": "Bug 反馈",
        "about.bug.fail": "生成日志失败: {err}",
        "about.bug.saved": "Bug 日志已保存到:\n{path}",
        "about.settingsHint": "设置请从系统托盘图标打开，无需点击灵动岛。",
        # 设置页（SettingsPageWidget）
        "settings.theme": "主题",
        "settings.theme.dark": "深色（黑）",
        "settings.theme.light": "浅色（白）",
        "settings.hint": "更改即时生效并自动保存。",
        # 设置页里的提醒开关（与上面 settings.notify.*.desc 不同：
        # 这里是单元格左侧标题，不带描述，简短为主）
        "settings.notify.bluetooth.title": "蓝牙设备连接/断开",
        "settings.notify.clipboard.title": "剪贴板内容变化",
        "settings.notify.hardware.title": "硬件状态（CPU/内存等）",
        "settings.notify.todo.title": "待办到点提醒",
        # 减淡延迟选项
        "settings.delay.5000": "5 秒",
        "settings.delay.10000": "10 秒",
        "settings.delay.30000": "30 秒",
        # 日志页（ConsoleWidget）
        "log.filter": "过滤…（如 SMTC、蓝牙）",
        "log.pause": "暂停",
        "log.autoscroll": "自动滚动",
        "log.pause.tip": "暂停期间日志继续写入缓冲，取消暂停后一次性补齐",
        "log.autoscroll.tip": "新日志自动贴底；手动上滚会临时挂起，滚回底部自动恢复",
        "log.openTerminal": "打开终端",
        "log.openTerminal.tip": "在日志目录打开 Windows 终端 / PowerShell",
        "log.copyAll": "复制全部",
        "log.clear": "清空显示",
    },
    "en": {
        "app.title": "LsletUI",
        "nav.bluetooth": "Bluetooth",
        "nav.music": "Now Playing",
        "nav.home": "Home",
        "nav.log": "Logs",
        "nav.settings": "Settings",
        "nav.todo": "To-dos",
        "nav.links": "Quick Links",
        "nav.about": "About",
        "tray.showMain": "Open main window",
        "tray.hideMain": "Hide main window",
        "tray.showIsland": "Show island",
        "tray.hideIsland": "Hide island",
        "tray.settings": "Console",
        "tray.exit": "Exit",
        "settings.title": "LsletUI Settings",
        "settings.general": "General",
        "settings.autostart": "Launch at startup",
        "settings.autostart.desc": "Run LsletUI automatically after signing in to Windows",
        "settings.autoDim": "Auto dim",
        "settings.autoDim.desc": "Dim the capsule after inactivity",
        "settings.liquidGlass": "Liquid Glass",
        "settings.liquidGlass.desc": "Render a real-time refraction glass layer below the island",
        "settings.liquidGlass.unsupported": "Hardware does not meet requirements. Liquid Glass is unavailable; basic skin mode only.",
        "settings.dimDelay": "Inactivity delay",
        "settings.seconds": "{n}s",
        "settings.language": "Language",
        "settings.language.desc": "Switch the interface language",
        "settings.alerts": "Island alerts",
        "settings.notify.bluetooth": "Bluetooth alerts",
        "settings.notify.bluetooth.desc": "Notify when headphones connect or disconnect",
        "settings.notify.clipboard": "Clipboard",
        "settings.notify.clipboard.desc": "Show a toast on copy and keep history",
        "settings.notify.hardware": "Hardware alerts",
        "settings.notify.hardware.desc": "Alert when CPU / memory / GPU is overloaded",
        "settings.data": "Data",
        "settings.clearClipboard": "Clear clipboard history",
        "settings.clearClipboard.desc": "Delete locally saved copy records",
        "settings.clear": "Clear",
        "settings.cleared": "Clipboard history cleared",
        "bt.title": "Bluetooth devices",
        "bt.off": "Off",
        "bt.on": "On",
        "bt.detecting": "Detecting...",
        "bt.scanning": "Scanning {s}s",
        "bt.offHint": "Bluetooth is off. Turn it on in system settings",
        "bt.noDevices": "No devices found",
        "bt.battery": "Battery {n}%",
        "todo.title": "To-dos",
        "todo.placeholder": "Add a new to-do...",
        "todo.add": "Add",
        "todo.empty": "Nothing to do yet",
        "todo.filter_all": "All",
        "todo.filter_active": "Active",
        "todo.filter_done": "Done",
        "todo.clearDone": "Clear done",
        "todo.delete": "Delete",
        "todo.remind": "Remind",
        "todo.remindIn10": "In 10 minutes",
        "todo.remindIn60": "In 1 hour",
        "todo.remindTomorrow": "Tomorrow 9:00",
        "todo.remindCustom": "Custom time…",
        "todo.remindClear": "Clear reminder",
        "todo.reminded": "Reminded",
        "music.title": "Now Playing",
        "music.subtitle": "Live via Windows SMTC",
        "music.playing": "Playing",
        "music.notPlaying": "Idle",
        "music.unknownArtist": "Unknown artist",
        "music.noMusic": "Nothing playing right now",
        "music.noMusicHint": "Play something in NetEase Cloud Music, QQ Music, etc.",
        "music.prev": "Previous",
        "music.play": "Play/Pause",
        "music.next": "Next",
        "wait.title": "Quick links",
        "wait.website": "Website",
        "wait.thanks": "Thanks for using LsletUI",
        "about.title": "About LsletUI",
        "about.help": "Help",
        "about.history": "Clipboard history",
        "about.bug": "Report bug",
        "about.bug.fail": "Failed to generate log: {err}",
        "about.bug.saved": "Bug report saved to:\n{path}",
        "about.settingsHint": "Open Settings from the system tray. You do not need to click the island.",
        # Settings page (SettingsPageWidget)
        "settings.theme": "Theme",
        "settings.theme.dark": "Dark",
        "settings.theme.light": "Light",
        "settings.hint": "Changes take effect immediately and are saved automatically.",
        "settings.notify.bluetooth.title": "Bluetooth connect / disconnect",
        "settings.notify.clipboard.title": "Clipboard changes",
        "settings.notify.hardware.title": "Hardware (CPU / RAM)",
        "settings.notify.todo.title": "ToDo reminders",
        "settings.delay.5000": "5 s",
        "settings.delay.10000": "10 s",
        "settings.delay.30000": "30 s",
        # Logs page (ConsoleWidget)
        "log.filter": "Filter… (e.g. SMTC, Bluetooth)",
        "log.pause": "Pause",
        "log.autoscroll": "Auto scroll",
        "log.pause.tip": "Logs keep buffering while paused and are flushed on resume",
        "log.autoscroll.tip": "Follow new lines; scrolling up pauses it, returning to the bottom resumes",
        "log.openTerminal": "Open terminal",
        "log.openTerminal.tip": "Open Windows Terminal / PowerShell in the log folder",
        "log.copyAll": "Copy all",
        "log.clear": "Clear view",
    },
    "zh-TW": {
        "app.title": "LsletUI",
        "nav.bluetooth": "藍牙裝置",
        "nav.music": "正在播放",
        "nav.home": "主畫面",
        "nav.log": "日誌",
        "nav.settings": "設定",
        "nav.todo": "待辦事項",
        "nav.links": "快速連結",
        "nav.about": "關於",
        "tray.showMain": "開啟主畫面",
        "tray.hideMain": "隱藏主畫面",
        "tray.showIsland": "顯示動態島",
        "tray.hideIsland": "隱藏動態島",
        "tray.settings": "控制台",
        "tray.exit": "結束",
        "settings.title": "LsletUI 設定",
        "settings.general": "一般",
        "settings.autostart": "開機時自動啟動",
        "settings.autostart.desc": "登入 Windows 後自動執行 LsletUI",
        "settings.autoDim": "自動調暗",
        "settings.autoDim.desc": "一段時間沒有操作後，膠囊會自動變暗",
        "settings.liquidGlass": "液態玻璃",
        "settings.liquidGlass.desc": "在靈動島下方渲染即時折射玻璃層",
        "settings.liquidGlass.unsupported": "目前硬體不符合需求，液態玻璃特效無法使用，僅支援基礎原皮模式",
        "settings.dimDelay": "閒置延遲",
        "settings.seconds": "{n} 秒",
        "settings.language": "語言",
        "settings.language.desc": "切換介面顯示語言",
        "settings.alerts": "動態島提醒",
        "settings.notify.bluetooth": "藍牙連線提醒",
        "settings.notify.bluetooth.desc": "耳機連線/中斷時顯示通知",
        "settings.notify.clipboard": "剪貼簿記錄",
        "settings.notify.clipboard.desc": "複製時顯示提醒並保留歷史記錄",
        "settings.notify.hardware": "硬體高負載警示",
        "settings.notify.hardware.desc": "CPU/記憶體/GPU 過載時提醒",
        "settings.data": "資料",
        "settings.clearClipboard": "清除剪貼簿歷史",
        "settings.clearClipboard.desc": "刪除本機儲存的複製記錄",
        "settings.clear": "清除",
        "settings.cleared": "已清除剪貼簿歷史",
        "bt.title": "藍牙裝置",
        "bt.off": "已關閉",
        "bt.on": "已開啟",
        "bt.detecting": "偵測中...",
        "bt.scanning": "掃描中 {s}s",
        "bt.offHint": "藍牙已關閉，請在系統設定中開啟藍牙",
        "bt.noDevices": "未偵測到裝置",
        "bt.battery": "電量 {n}%",
        "todo.title": "待辦事項",
        "todo.placeholder": "新增待辦事項...",
        "todo.add": "新增",
        "todo.empty": "尚無待辦事項",
        "todo.filter_all": "全部",
        "todo.filter_active": "進行中",
        "todo.filter_done": "已完成",
        "todo.clearDone": "清除已完成",
        "todo.delete": "刪除",
        "todo.remind": "提醒",
        "todo.remindIn10": "10 分鐘後",
        "todo.remindIn60": "1 小時後",
        "todo.remindTomorrow": "明天 9 點",
        "todo.remindCustom": "自訂時間…",
        "todo.remindClear": "清除提醒",
        "todo.reminded": "已提醒",
        "music.title": "正在播放",
        "music.subtitle": "Windows SMTC 即時監控",
        "music.playing": "播放中",
        "music.notPlaying": "未播放",
        "music.unknownArtist": "未知歌手",
        "music.noMusic": "目前沒有正在播放的音樂",
        "music.noMusicHint": "開啟網易雲、QQ 音樂等應用程式即可看到",
        "music.prev": "上一首",
        "music.play": "播放/暫停",
        "music.next": "下一首",
        "wait.title": "快速連結",
        "wait.website": "官方網站",
        "wait.thanks": "感謝使用 LsletUI",
        "about.title": "關於 LsletUI",
        "about.help": "說明",
        "about.history": "剪貼簿歷史",
        "about.bug": "問題回報",
        "about.bug.fail": "產生日誌失敗: {err}",
        "about.bug.saved": "問題日誌已儲存至:\n{path}",
        "about.settingsHint": "請從系統匣圖示開啟設定，無須點選動態島。",
        "settings.theme": "主題",
        "settings.theme.dark": "深色（黑）",
        "settings.theme.light": "淺色（白）",
        "settings.hint": "變更會立即生效並自動儲存。",
        "settings.notify.bluetooth.title": "藍牙裝置連線/中斷",
        "settings.notify.clipboard.title": "剪貼簿內容變更",
        "settings.notify.hardware.title": "硬體狀態（CPU/記憶體等）",
        "settings.notify.todo.title": "待辦到點提醒",
        "settings.delay.5000": "5 秒",
        "settings.delay.10000": "10 秒",
        "settings.delay.30000": "30 秒",
        "log.filter": "篩選…（例如 SMTC、藍牙）",
        "log.pause": "暫停",
        "log.autoscroll": "自動捲動",
        "log.pause.tip": "暫停期間日誌繼續寫入緩衝，取消暫停後一次補齊",
        "log.autoscroll.tip": "新日誌自動貼底；手動上捲會暫時懸掛，捲回底部自動恢復",
        "log.openTerminal": "開啟終端機",
        "log.openTerminal.tip": "在日誌目錄開啟 Windows 終端機 / PowerShell",
        "log.copyAll": "複製全部",
        "log.clear": "清除顯示",
    },
    "ja": {
        "app.title": "LsletUI",
        "nav.bluetooth": "Bluetooth デバイス",
        "nav.music": "再生中",
        "nav.home": "ホーム",
        "nav.log": "ログ",
        "nav.settings": "設定",
        "nav.todo": "ToDo",
        "nav.links": "クイックリンク",
        "nav.about": "情報",
        "tray.showMain": "メイン画面を開く",
        "tray.hideMain": "メイン画面を隠す",
        "tray.showIsland": "アイランドを表示",
        "tray.hideIsland": "アイランドを隠す",
        "tray.settings": "コンソール",
        "tray.exit": "終了",
        "settings.title": "LsletUI 設定",
        "settings.general": "一般",
        "settings.autostart": "スタートアップに登録",
        "settings.autostart.desc": "Windows へのサインイン後に LsletUI を自動起動します",
        "settings.autoDim": "自動減光",
        "settings.autoDim.desc": "一定時間操作がないとカプセルを暗くします",
        "settings.liquidGlass": "リキッドガラス",
        "settings.liquidGlass.desc": "アイランドの下にリアルタイム屈折ガラス層を表示します",
        "settings.liquidGlass.unsupported": "現在のハードウェアは要件を満たしていません。リキッドガラスは利用できず、基本スキンのみ使用できます",
        "settings.dimDelay": "無操作の遅延",
        "settings.seconds": "{n} 秒",
        "settings.language": "言語",
        "settings.language.desc": "表示言語を切り替えます",
        "settings.alerts": "アイランドの通知",
        "settings.notify.bluetooth": "Bluetooth 接続の通知",
        "settings.notify.bluetooth.desc": "ヘッドホンの接続／切断時に通知します",
        "settings.notify.clipboard": "クリップボード履歴",
        "settings.notify.clipboard.desc": "コピー時に通知し、履歴を保持します",
        "settings.notify.hardware": "ハードウェア高負荷の警告",
        "settings.notify.hardware.desc": "CPU／メモリ／GPU の過負荷時に通知します",
        "settings.data": "データ",
        "settings.clearClipboard": "クリップボード履歴を消去",
        "settings.clearClipboard.desc": "ローカルに保存されたコピー履歴を削除します",
        "settings.clear": "消去",
        "settings.cleared": "クリップボード履歴を消去しました",
        "bt.title": "Bluetooth デバイス",
        "bt.off": "オフ",
        "bt.on": "オン",
        "bt.detecting": "検出中...",
        "bt.scanning": "スキャン中 {s}s",
        "bt.offHint": "Bluetooth がオフです。システム設定でオンにしてください",
        "bt.noDevices": "デバイスが見つかりません",
        "bt.battery": "バッテリー {n}%",
        "todo.title": "ToDo",
        "todo.placeholder": "ToDo を追加...",
        "todo.add": "追加",
        "todo.empty": "ToDo はまだありません",
        "todo.filter_all": "すべて",
        "todo.filter_active": "未完了",
        "todo.filter_done": "完了",
        "todo.clearDone": "完了を消去",
        "todo.delete": "削除",
        "todo.remind": "通知",
        "todo.remindIn10": "10分後",
        "todo.remindIn60": "1時間後",
        "todo.remindTomorrow": "明日 9時",
        "todo.remindCustom": "日時を指定…",
        "todo.remindClear": "通知を解除",
        "todo.reminded": "通知済み",
        "music.title": "再生中",
        "music.subtitle": "Windows SMTC でリアルタイム監視",
        "music.playing": "再生中",
        "music.notPlaying": "停止中",
        "music.unknownArtist": "不明なアーティスト",
        "music.noMusic": "再生中の音楽はありません",
        "music.noMusicHint": "NetEase Cloud Music や QQ Music などを開くと表示されます",
        "music.prev": "前へ",
        "music.play": "再生／一時停止",
        "music.next": "次へ",
        "wait.title": "クイックリンク",
        "wait.website": "公式サイト",
        "wait.thanks": "LsletUI をご利用いただきありがとうございます",
        "about.title": "LsletUI について",
        "about.help": "ヘルプ",
        "about.history": "クリップボード履歴",
        "about.bug": "バグ報告",
        "about.bug.fail": "ログの生成に失敗しました: {err}",
        "about.bug.saved": "バグログを保存しました:\n{path}",
        "about.settingsHint": "設定はシステムトレイのアイコンから開いてください。アイランドをクリックする必要はありません。",
        "settings.theme": "テーマ",
        "settings.theme.dark": "ダーク（黒）",
        "settings.theme.light": "ライト（白）",
        "settings.hint": "変更はすぐに反映され、自動で保存されます。",
        "settings.notify.bluetooth.title": "Bluetooth の接続／切断",
        "settings.notify.clipboard.title": "クリップボードの変更",
        "settings.notify.hardware.title": "ハードウェア状態（CPU／メモリなど）",
        "settings.notify.todo.title": "ToDo リマインダー",
        "settings.delay.5000": "5 秒",
        "settings.delay.10000": "10 秒",
        "settings.delay.30000": "30 秒",
        "log.filter": "絞り込み…（例: SMTC、Bluetooth）",
        "log.pause": "一時停止",
        "log.autoscroll": "自動スクロール",
        "log.pause.tip": "一時停止中もログはバッファに溜まり、解除するとまとめて表示します",
        "log.autoscroll.tip": "新ログに自動追従。上へスクロールすると一時停止し、最下部に戻ると再開します",
        "log.openTerminal": "ターミナルを開く",
        "log.openTerminal.tip": "ログフォルダーで Windows ターミナル / PowerShell を開く",
        "log.copyAll": "すべてコピー",
        "log.clear": "表示をクリア",
    },
    "ko": {
        "app.title": "LsletUI",
        "nav.bluetooth": "블루투스 기기",
        "nav.music": "재생 중",
        "nav.home": "홈",
        "nav.log": "로그",
        "nav.settings": "설정",
        "nav.todo": "할 일",
        "nav.links": "빠른 링크",
        "nav.about": "정보",
        "tray.showMain": "메인 창 열기",
        "tray.hideMain": "메인 창 숨기기",
        "tray.showIsland": "아일랜드 표시",
        "tray.hideIsland": "아일랜드 숨기기",
        "tray.settings": "콘솔",
        "tray.exit": "종료",
        "settings.title": "LsletUI 설정",
        "settings.general": "일반",
        "settings.autostart": "시작 시 자동 실행",
        "settings.autostart.desc": "Windows 로그인 후 LsletUI를 자동으로 실행해요",
        "settings.autoDim": "자동 흐리게",
        "settings.autoDim.desc": "일정 시간 조작이 없으면 캡슐이 자동으로 어두워져요",
        "settings.liquidGlass": "리퀴드 글래스",
        "settings.liquidGlass.desc": "아일랜드 아래에 실시간 굴절 글래스 레이어를 표시해요",
        "settings.liquidGlass.unsupported": "현재 하드웨어가 요구 사항을 충족하지 않아 리퀴드 글래스를 사용할 수 없습니다. 기본 스킨 모드만 지원됩니다",
        "settings.dimDelay": "무조작 지연",
        "settings.seconds": "{n}초",
        "settings.language": "언어",
        "settings.language.desc": "인터페이스 표시 언어를 전환해요",
        "settings.alerts": "아일랜드 알림",
        "settings.notify.bluetooth": "블루투스 연결 알림",
        "settings.notify.bluetooth.desc": "헤드폰 연결/해제 시 알림을 표시해요",
        "settings.notify.clipboard": "클립보드 기록",
        "settings.notify.clipboard.desc": "복사 시 알림을 표시하고 기록을 보관해요",
        "settings.notify.hardware": "하드웨어 고부하 경고",
        "settings.notify.hardware.desc": "CPU/메모리/GPU 과부하 시 알려줘요",
        "settings.data": "데이터",
        "settings.clearClipboard": "클립보드 기록 지우기",
        "settings.clearClipboard.desc": "로컬에 저장된 복사 기록을 삭제해요",
        "settings.clear": "지우기",
        "settings.cleared": "클립보드 기록을 지웠어요",
        "bt.title": "블루투스 기기",
        "bt.off": "꺼짐",
        "bt.on": "켜짐",
        "bt.detecting": "감지 중...",
        "bt.scanning": "검색 중 {s}s",
        "bt.offHint": "블루투스가 꺼져 있어요. 시스템 설정에서 켜 주세요",
        "bt.noDevices": "기기를 찾지 못했어요",
        "bt.battery": "배터리 {n}%",
        "todo.title": "할 일",
        "todo.placeholder": "새 할 일 추가...",
        "todo.add": "추가",
        "todo.empty": "아직 할 일이 없어요",
        "todo.filter_all": "전체",
        "todo.filter_active": "진행 중",
        "todo.filter_done": "완료",
        "todo.clearDone": "완료 항목 지우기",
        "todo.delete": "삭제",
        "todo.remind": "알림",
        "todo.remindIn10": "10분 후",
        "todo.remindIn60": "1시간 후",
        "todo.remindTomorrow": "내일 9시",
        "todo.remindCustom": "시간 직접 설정…",
        "todo.remindClear": "알림 삭제",
        "todo.reminded": "알림 완료",
        "music.title": "재생 중",
        "music.subtitle": "Windows SMTC 실시간 모니터링",
        "music.playing": "재생 중",
        "music.notPlaying": "재생 안 함",
        "music.unknownArtist": "알 수 없는 아티스트",
        "music.noMusic": "재생 중인 음악이 없어요",
        "music.noMusicHint": "NetEase Cloud Music, QQ Music 등을 열면 표시돼요",
        "music.prev": "이전 곡",
        "music.play": "재생/일시정지",
        "music.next": "다음 곡",
        "wait.title": "빠른 링크",
        "wait.website": "공식 사이트",
        "wait.thanks": "LsletUI를 사용해 주셔서 감사해요",
        "about.title": "LsletUI 정보",
        "about.help": "도움말",
        "about.history": "클립보드 기록",
        "about.bug": "버그 신고",
        "about.bug.fail": "로그 생성 실패: {err}",
        "about.bug.saved": "버그 로그가 저장되었어요:\n{path}",
        "about.settingsHint": "설정은 시스템 트레이 아이콘에서 열어 주세요. 아일랜드를 클릭할 필요가 없어요.",
        "settings.theme": "테마",
        "settings.theme.dark": "어둡게(검정)",
        "settings.theme.light": "밝게(흰색)",
        "settings.hint": "변경 사항은 즉시 적용되고 자동으로 저장돼요.",
        "settings.notify.bluetooth.title": "블루투스 기기 연결/해제",
        "settings.notify.clipboard.title": "클립보드 내용 변경",
        "settings.notify.hardware.title": "하드웨어 상태(CPU/메모리 등)",
        "settings.notify.todo.title": "할 일 알림",
        "settings.delay.5000": "5초",
        "settings.delay.10000": "10초",
        "settings.delay.30000": "30초",
        "log.filter": "필터… (예: SMTC, 블루투스)",
        "log.pause": "일시정지",
        "log.autoscroll": "자동 스크롤",
        "log.pause.tip": "일시정지 중에도 로그는 버퍼에 쌓이며 해제하면 한 번에 표시합니다",
        "log.autoscroll.tip": "새 로그에 자동 추적. 위로 스크롤하면 잠시 멈추고 맨 아래로 돌아가면 재개합니다",
        "log.openTerminal": "터미널 열기",
        "log.openTerminal.tip": "로그 폴더에서 Windows 터미널 / PowerShell 열기",
        "log.copyAll": "모두 복사",
        "log.clear": "표시 지우기",
    },
    "de": {
        "app.title": "LsletUI",
        "nav.bluetooth": "Bluetooth-Geräte",
        "nav.music": "Wiedergabe",
        "nav.home": "Start",
        "nav.log": "Protokoll",
        "nav.settings": "Einstellungen",
        "nav.todo": "To-dos",
        "nav.links": "Quicklinks",
        "nav.about": "Über",
        "tray.showMain": "Hauptfenster öffnen",
        "tray.hideMain": "Hauptfenster ausblenden",
        "tray.showIsland": "Island anzeigen",
        "tray.hideIsland": "Island ausblenden",
        "tray.settings": "Konsole",
        "tray.exit": "Beenden",
        "settings.title": "LsletUI-Einstellungen",
        "settings.general": "Allgemein",
        "settings.autostart": "Beim Start ausführen",
        "settings.autostart.desc": "LsletUI nach der Windows-Anmeldung automatisch starten",
        "settings.autoDim": "Automatisch dimmen",
        "settings.autoDim.desc": "Die Kapsel nach Inaktivität abdunkeln",
        "settings.liquidGlass": "Flüssigglas",
        "settings.liquidGlass.desc": "Echtzeit-Refraktionsglasschicht unter der Insel rendern",
        "settings.liquidGlass.unsupported": "Die Hardware erfüllt die Anforderungen nicht. Flüssigglas ist nicht verfügbar, nur der Basis-Skin-Modus wird unterstützt",
        "settings.dimDelay": "Verzögerung bei Inaktivität",
        "settings.seconds": "{n} s",
        "settings.language": "Sprache",
        "settings.language.desc": "Sprache der Oberfläche wechseln",
        "settings.alerts": "Island-Benachrichtigungen",
        "settings.notify.bluetooth": "Bluetooth-Benachrichtigungen",
        "settings.notify.bluetooth.desc": "Benachrichtigen, wenn Kopfhörer verbunden oder getrennt werden",
        "settings.notify.clipboard": "Zwischenablage",
        "settings.notify.clipboard.desc": "Beim Kopieren einen Hinweis zeigen und den Verlauf behalten",
        "settings.notify.hardware": "Hardware-Warnungen",
        "settings.notify.hardware.desc": "Warnen, wenn CPU / Arbeitsspeicher / GPU überlastet sind",
        "settings.data": "Daten",
        "settings.clearClipboard": "Zwischenablageverlauf löschen",
        "settings.clearClipboard.desc": "Lokal gespeicherte Kopierverläufe entfernen",
        "settings.clear": "Löschen",
        "settings.cleared": "Zwischenablageverlauf gelöscht",
        "bt.title": "Bluetooth-Geräte",
        "bt.off": "Aus",
        "bt.on": "Ein",
        "bt.detecting": "Wird erkannt...",
        "bt.scanning": "Suche läuft ({s}s)",
        "bt.offHint": "Bluetooth ist aus. Aktiviere es in den Systemeinstellungen",
        "bt.noDevices": "Keine Geräte gefunden",
        "bt.battery": "Akku {n}%",
        "todo.title": "To-dos",
        "todo.placeholder": "Neues To-do hinzufügen...",
        "todo.add": "Hinzufügen",
        "todo.empty": "Noch nichts zu tun",
        "todo.filter_all": "Alle",
        "todo.filter_active": "Aktiv",
        "todo.filter_done": "Erledigt",
        "todo.clearDone": "Erledigte löschen",
        "todo.delete": "Löschen",
        "todo.remind": "Erinnern",
        "todo.remindIn10": "In 10 Minuten",
        "todo.remindIn60": "In 1 Stunde",
        "todo.remindTomorrow": "Morgen 9 Uhr",
        "todo.remindCustom": "Eigene Zeit…",
        "todo.remindClear": "Erinnerung löschen",
        "todo.reminded": "Erinnert",
        "music.title": "Wiedergabe",
        "music.subtitle": "Live über Windows SMTC",
        "music.playing": "Wird abgespielt",
        "music.notPlaying": "Inaktiv",
        "music.unknownArtist": "Unbekannter Künstler",
        "music.noMusic": "Es wird gerade nichts abgespielt",
        "music.noMusicHint": "Spiele etwas in NetEase Cloud Music, QQ Music usw. ab",
        "music.prev": "Zurück",
        "music.play": "Wiedergabe/Pause",
        "music.next": "Weiter",
        "wait.title": "Quicklinks",
        "wait.website": "Website",
        "wait.thanks": "Danke, dass du LsletUI verwendest",
        "about.title": "Über LsletUI",
        "about.help": "Hilfe",
        "about.history": "Zwischenablageverlauf",
        "about.bug": "Fehler melden",
        "about.bug.fail": "Protokoll konnte nicht erstellt werden: {err}",
        "about.bug.saved": "Fehlerprotokoll gespeichert unter:\n{path}",
        "about.settingsHint": "Öffne die Einstellungen über das Symbol im Infobereich. Du musst nicht auf die Island klicken.",
        "settings.theme": "Design",
        "settings.theme.dark": "Dunkel (Schwarz)",
        "settings.theme.light": "Hell (Weiß)",
        "settings.hint": "Änderungen wirken sofort und werden automatisch gespeichert.",
        "settings.notify.bluetooth.title": "Bluetooth verbinden / trennen",
        "settings.notify.clipboard.title": "Änderungen der Zwischenablage",
        "settings.notify.hardware.title": "Hardware (CPU / Arbeitsspeicher)",
        "settings.notify.todo.title": "To-do-Erinnerungen",
        "settings.delay.5000": "5 s",
        "settings.delay.10000": "10 s",
        "settings.delay.30000": "30 s",
        "log.filter": "Filtern… (z. B. SMTC, Bluetooth)",
        "log.pause": "Pause",
        "log.autoscroll": "Automatisch scrollen",
        "log.pause.tip": "Pausiert werden Logs weiter gepuffert und beim Fortsetzen nachgeladen",
        "log.autoscroll.tip": "Folgt neuen Zeilen; aufwärts scrollen pausiert, am Ende wird wieder verfolgt",
        "log.openTerminal": "Terminal öffnen",
        "log.openTerminal.tip": "Windows Terminal / PowerShell im Protokollordner öffnen",
        "log.copyAll": "Alles kopieren",
        "log.clear": "Ansicht leeren",
    },
    "ru": {
        "app.title": "LsletUI",
        "nav.bluetooth": "Устройства Bluetooth",
        "nav.music": "Сейчас играет",
        "nav.home": "Главная",
        "nav.log": "Журнал",
        "nav.settings": "Настройки",
        "nav.todo": "Задачи",
        "nav.links": "Быстрые ссылки",
        "nav.about": "О программе",
        "tray.showMain": "Открыть главное окно",
        "tray.hideMain": "Скрыть главное окно",
        "tray.showIsland": "Показать остров",
        "tray.hideIsland": "Скрыть остров",
        "tray.settings": "Консоль",
        "tray.exit": "Выход",
        "settings.title": "Настройки LsletUI",
        "settings.general": "Общие",
        "settings.autostart": "Запускать при старте",
        "settings.autostart.desc": "Автоматически запускать LsletUI после входа в Windows",
        "settings.autoDim": "Автозатемнение",
        "settings.autoDim.desc": "Затемнять капсулу после периода бездействия",
        "settings.liquidGlass": "Жидкое стекло",
        "settings.liquidGlass.desc": "Отображать слой преломляющего стекла под островом в реальном времени",
        "settings.liquidGlass.unsupported": "Оборудование не соответствует требованиям. Жидкое стекло недоступно, поддерживается только базовый режим оформления",
        "settings.dimDelay": "Задержка бездействия",
        "settings.seconds": "{n} с",
        "settings.language": "Язык",
        "settings.language.desc": "Переключить язык интерфейса",
        "settings.alerts": "Уведомления острова",
        "settings.notify.bluetooth": "Уведомления Bluetooth",
        "settings.notify.bluetooth.desc": "Уведомлять при подключении и отключении наушников",
        "settings.notify.clipboard": "Буфер обмена",
        "settings.notify.clipboard.desc": "Показывать уведомление при копировании и хранить историю",
        "settings.notify.hardware": "Оповещения о нагрузке",
        "settings.notify.hardware.desc": "Предупреждать при перегрузке CPU, памяти или GPU",
        "settings.data": "Данные",
        "settings.clearClipboard": "Очистить историю буфера обмена",
        "settings.clearClipboard.desc": "Удалить локально сохранённые записи копирования",
        "settings.clear": "Очистить",
        "settings.cleared": "История буфера обмена очищена",
        "bt.title": "Устройства Bluetooth",
        "bt.off": "Выключено",
        "bt.on": "Включено",
        "bt.detecting": "Обнаружение...",
        "bt.scanning": "Сканирование {s} с",
        "bt.offHint": "Bluetooth выключен. Включите его в системных настройках",
        "bt.noDevices": "Устройства не найдены",
        "bt.battery": "Заряд {n}%",
        "todo.title": "Задачи",
        "todo.placeholder": "Добавить новую задачу...",
        "todo.add": "Добавить",
        "todo.empty": "Пока нет задач",
        "todo.filter_all": "Все",
        "todo.filter_active": "В работе",
        "todo.filter_done": "Готово",
        "todo.clearDone": "Очистить выполненные",
        "todo.delete": "Удалить",
        "todo.remind": "Напомнить",
        "todo.remindIn10": "Через 10 минут",
        "todo.remindIn60": "Через 1 час",
        "todo.remindTomorrow": "Завтра в 9:00",
        "todo.remindCustom": "Выбрать время…",
        "todo.remindClear": "Убрать напоминание",
        "todo.reminded": "Напомнено",
        "music.title": "Сейчас играет",
        "music.subtitle": "В реальном времени через Windows SMTC",
        "music.playing": "Играет",
        "music.notPlaying": "Не играет",
        "music.unknownArtist": "Неизвестный исполнитель",
        "music.noMusic": "Сейчас ничего не играет",
        "music.noMusicHint": "Включите музыку в NetEase Cloud Music, QQ Music и т. п.",
        "music.prev": "Предыдущий",
        "music.play": "Играть/Пауза",
        "music.next": "Следующий",
        "wait.title": "Быстрые ссылки",
        "wait.website": "Сайт",
        "wait.thanks": "Спасибо за использование LsletUI",
        "about.title": "О LsletUI",
        "about.help": "Справка",
        "about.history": "История буфера обмена",
        "about.bug": "Сообщить об ошибке",
        "about.bug.fail": "Не удалось создать журнал: {err}",
        "about.bug.saved": "Журнал ошибки сохранён:\n{path}",
        "about.settingsHint": "Открывайте настройки из значка в системном трее. Нажимать на остров не нужно.",
        "settings.theme": "Тема",
        "settings.theme.dark": "Тёмная (чёрная)",
        "settings.theme.light": "Светлая (белая)",
        "settings.hint": "Изменения применяются сразу и сохраняются автоматически.",
        "settings.notify.bluetooth.title": "Подключение/отключение Bluetooth",
        "settings.notify.clipboard.title": "Изменения буфера обмена",
        "settings.notify.hardware.title": "Состояние оборудования (CPU/память)",
        "settings.notify.todo.title": "Напоминания о задачах",
        "settings.delay.5000": "5 с",
        "settings.delay.10000": "10 с",
        "settings.delay.30000": "30 с",
        "log.filter": "Фильтр… (например, SMTC, Bluetooth)",
        "log.pause": "Пауза",
        "log.autoscroll": "Автопрокрутка",
        "log.pause.tip": "Во время паузы логи копятся в буфере и догружаются при снятии паузы",
        "log.autoscroll.tip": "Автопрокрутка к новым строкам; прокрутка вверх приостанавливает её, у нижнего края возобновляет",
        "log.openTerminal": "Открыть терминал",
        "log.openTerminal.tip": "Открыть Windows Terminal / PowerShell в папке журналов",
        "log.copyAll": "Копировать всё",
        "log.clear": "Очистить экран",
    },
    "vi": {
        "app.title": "LsletUI",
        "nav.bluetooth": "Thiết bị Bluetooth",
        "nav.music": "Đang phát",
        "nav.home": "Trang chính",
        "nav.log": "Nhật ký",
        "nav.settings": "Cài đặt",
        "nav.todo": "Việc cần làm",
        "nav.links": "Liên kết nhanh",
        "nav.about": "Giới thiệu",
        "tray.showMain": "Mở cửa sổ chính",
        "tray.hideMain": "Ẩn cửa sổ chính",
        "tray.showIsland": "Hiện đảo",
        "tray.hideIsland": "Ẩn đảo",
        "tray.settings": "Bảng điều khiển",
        "tray.exit": "Thoát",
        "settings.title": "Cài đặt LsletUI",
        "settings.general": "Chung",
        "settings.autostart": "Khởi động cùng hệ thống",
        "settings.autostart.desc": "Tự động chạy LsletUI sau khi đăng nhập Windows",
        "settings.autoDim": "Tự động làm mờ",
        "settings.autoDim.desc": "Làm tối viên nang sau khi không thao tác một lúc",
        "settings.liquidGlass": "Kính lỏng",
        "settings.liquidGlass.desc": "Hiển thị lớp kính khúc xạ thời gian thực bên dưới đảo",
        "settings.liquidGlass.unsupported": "Phần cứng hiện tại không đáp ứng yêu cầu. Kính lỏng không khả dụng, chỉ hỗ trợ chế độ giao diện cơ bản",
        "settings.dimDelay": "Thời gian chờ không thao tác",
        "settings.seconds": "{n} giây",
        "settings.language": "Ngôn ngữ",
        "settings.language.desc": "Chuyển ngôn ngữ giao diện",
        "settings.alerts": "Thông báo trên đảo",
        "settings.notify.bluetooth": "Thông báo Bluetooth",
        "settings.notify.bluetooth.desc": "Thông báo khi tai nghe kết nối/ngắt kết nối",
        "settings.notify.clipboard": "Lịch sử clipboard",
        "settings.notify.clipboard.desc": "Hiện thông báo khi sao chép và giữ lịch sử",
        "settings.notify.hardware": "Cảnh báo tải cao phần cứng",
        "settings.notify.hardware.desc": "Cảnh báo khi CPU/bộ nhớ/GPU quá tải",
        "settings.data": "Dữ liệu",
        "settings.clearClipboard": "Xóa lịch sử clipboard",
        "settings.clearClipboard.desc": "Xóa các bản ghi sao chép lưu trên máy",
        "settings.clear": "Xóa",
        "settings.cleared": "Đã xóa lịch sử clipboard",
        "bt.title": "Thiết bị Bluetooth",
        "bt.off": "Đã tắt",
        "bt.on": "Đã bật",
        "bt.detecting": "Đang dò tìm...",
        "bt.scanning": "Đang quét {s}s",
        "bt.offHint": "Bluetooth đã tắt. Hãy bật trong cài đặt hệ thống",
        "bt.noDevices": "Không tìm thấy thiết bị",
        "bt.battery": "Pin {n}%",
        "todo.title": "Việc cần làm",
        "todo.placeholder": "Thêm việc cần làm...",
        "todo.add": "Thêm",
        "todo.empty": "Chưa có việc nào",
        "todo.filter_all": "Tất cả",
        "todo.filter_active": "Đang làm",
        "todo.filter_done": "Đã xong",
        "todo.clearDone": "Xóa mục đã xong",
        "todo.delete": "Xóa",
        "todo.remind": "Nhắc",
        "todo.remindIn10": "Sau 10 phút",
        "todo.remindIn60": "Sau 1 giờ",
        "todo.remindTomorrow": "9 giờ ngày mai",
        "todo.remindCustom": "Chọn thời gian…",
        "todo.remindClear": "Bỏ nhắc",
        "todo.reminded": "Đã nhắc",
        "music.title": "Đang phát",
        "music.subtitle": "Giám sát trực tiếp qua Windows SMTC",
        "music.playing": "Đang phát",
        "music.notPlaying": "Không phát",
        "music.unknownArtist": "Nghệ sĩ không rõ",
        "music.noMusic": "Hiện không có nhạc đang phát",
        "music.noMusicHint": "Mở NetEase Cloud Music, QQ Music, v.v. để xem",
        "music.prev": "Bài trước",
        "music.play": "Phát/Tạm dừng",
        "music.next": "Bài tiếp",
        "wait.title": "Liên kết nhanh",
        "wait.website": "Trang chủ",
        "wait.thanks": "Cảm ơn bạn đã dùng LsletUI",
        "about.title": "Giới thiệu LsletUI",
        "about.help": "Trợ giúp",
        "about.history": "Lịch sử clipboard",
        "about.bug": "Báo lỗi",
        "about.bug.fail": "Tạo nhật ký thất bại: {err}",
        "about.bug.saved": "Nhật ký lỗi đã lưu vào:\n{path}",
        "about.settingsHint": "Mở Cài đặt từ biểu tượng khay hệ thống, không cần nhấp vào đảo.",
        "settings.theme": "Chủ đề",
        "settings.theme.dark": "Tối (đen)",
        "settings.theme.light": "Sáng (trắng)",
        "settings.hint": "Thay đổi có hiệu lực ngay và được tự động lưu.",
        "settings.notify.bluetooth.title": "Kết nối/ngắt Bluetooth",
        "settings.notify.clipboard.title": "Thay đổi nội dung clipboard",
        "settings.notify.hardware.title": "Trạng thái phần cứng (CPU/bộ nhớ...)",
        "settings.notify.todo.title": "Nhắc việc cần làm",
        "settings.delay.5000": "5 giây",
        "settings.delay.10000": "10 giây",
        "settings.delay.30000": "30 giây",
        "log.filter": "Lọc… (ví dụ: SMTC, Bluetooth)",
        "log.pause": "Tạm dừng",
        "log.autoscroll": "Tự động cuộn",
        "log.pause.tip": "Khi tạm dừng, nhật ký vẫn được đệm và bổ sung khi tiếp tục",
        "log.autoscroll.tip": "Tự bám đáy; cuộn lên sẽ tạm dừng, cuộn về đáy sẽ tiếp tục",
        "log.openTerminal": "Mở terminal",
        "log.openTerminal.tip": "Mở Windows Terminal / PowerShell trong thư mục nhật ký",
        "log.copyAll": "Sao chép tất cả",
        "log.clear": "Xóa hiển thị",
    },
}


def tr(lang, key, **kwargs):
    table = STRINGS.get(lang) or STRINGS["zh"]
    text = table.get(key) or STRINGS["zh"].get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def _load_svg_icon(path: Path, color: str, size: int = 16) -> QIcon:
    """加载 SVG 并替换 fill="currentColor" 为指定颜色，返回 QIcon。

    Qt 的 QIcon 不会把 CSS color 传给 SVG 的 currentColor，
    导致深色模式下 SVG 图标渲染为黑色。此函数在加载时直接替换颜色。
    """
    if not path.exists():
        return QIcon()
    data = path.read_bytes()
    # 替换 currentColor 为实际颜色值
    data = data.replace(b'currentColor', color.encode('utf-8'))
    pixmap = QPixmap()
    renderer = QSvgRenderer(QByteArray(data))
    if not renderer.isValid():
        return QIcon(str(path))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def apply_windows_ui(widget: QWidget, theme: str = "dark", glass: bool = False):
    """毛玻璃主题 + 霓虹蓝 accent，风格与灵动岛保持一致。

    theme: "dark" 深色（默认）/ "light" 浅色。
    glass: True 时在基础样式后追加「液态玻璃」覆盖样式——窗口透出下方
           liquid_glass.dll 渲染的折射层，卡片/控件改为半透明叠加。
           关闭或玻璃不可用时保持原不透明样式，保证文字可读。
    """
    global _CURRENT_THEME, _CURRENT_GLASS
    _CURRENT_THEME = theme
    _CURRENT_GLASS = bool(glass)
    if theme == "light":
        qss = _LIGHT_QSS
        if glass:
            qss += _LIGHT_GLASS_QSS
    else:
        qss = _DARK_QSS
        if glass:
            qss += _DARK_GLASS_QSS
    widget.setStyleSheet(qss)
    widget.setFont(QFont("Segoe UI", 9))


# 当前应用的主题 / 是否处于玻璃模式，供其他控件（如日志页、设置页开关）查询配色
_CURRENT_THEME = "dark"
_CURRENT_GLASS = False


_DARK_QSS = """
        /* ===== 基础容器 ===== */
        QMainWindow, QDialog, QWidget#winRoot, QWidget#pageRoot {
            background: #0a0a0f;
            color: #d8d8e4;
        }
        QWidget#bodyRoot {
            background: transparent;
        }
        /* 显式给正文文字色：切换主题时子 QLabel 的调色板不会自动跟随父级 */
        QLabel {
            color: #d8d8e4;
        }

        /* ===== 自绘标题栏（无边框窗口） ===== */
        QWidget#titleBar {
            background: transparent;
        }
        QLabel#titleBarText {
            color: #c9c9d6;
            font-size: 12px;
        }
        QPushButton#winBtn {
            background: transparent;
            border: none;
            border-radius: 6px;
            color: #c9c9d6;
            font-size: 13px;
        }
        QPushButton#winBtn:hover {
            background: rgba(255, 255, 255, 28);
            color: #ffffff;
        }
        QPushButton#winBtn:pressed {
            background: rgba(255, 255, 255, 46);
        }
        QPushButton#winCloseBtn {
            background: transparent;
            border: none;
            border-radius: 6px;
            color: #c9c9d6;
            font-size: 13px;
        }
        QPushButton#winCloseBtn:hover {
            background: #c42b1c;
            color: #ffffff;
        }
        QPushButton#winCloseBtn:pressed {
            background: #a02316;
            color: #ffffff;
        }

        /* ===== 左侧导航栏 ===== */
        QListWidget#navList {
            background: #12121a;
            border: none;
            outline: none;
            padding: 12px 8px;
            border-right: 1px solid #1e1e28;
        }
        QListWidget#navList::item {
            padding: 11px 16px;
            border-radius: 8px;
            margin: 3px 4px;
            color: #a8a8b8;
            font-size: 13px;
        }
        QListWidget#navList::item:hover:!selected {
            background: rgba(58, 141, 255, 0.08);
            color: #e0e0ee;
        }
        QListWidget#navList::item:selected {
            background: rgba(58, 141, 255, 0.18);
            color: #ffffff;
            border-left: 3px solid #3a8dff;
            padding-left: 13px;  /* 补偿左侧 3px 指示条，避免文字跳动 */
        }

        /* ===== 卡片 ===== */
        QFrame#card {
            background: #181822;
            border: 1px solid #242430;
            border-radius: 10px;
        }

        /* ===== 页面标题 ===== */
        QLabel#pageTitle {
            font-size: 22px;
            font-weight: 700;
            color: #ffffff;
            padding-bottom: 4px;
        }
        QLabel#hint {
            color: #6c6c7c;
            font-size: 12px;
        }

        /* ===== 拖放区（待办页复用） ===== */
        QLabel#dropZone {
            background: #12121a;
            color: #8c8c9c;
            border: 1px dashed #33334a;
            border-radius: 12px;
            font-size: 13px;
        }
        QLabel#dropZone:hover {
            border-color: #3a8dff;
            background: rgba(58, 141, 255, 0.08);
            color: #b8c8ff;
        }

        /* ===== 条目行（待办页复用） ===== */
        QFrame#convRow {
            background: #181822;
            border: 1px solid #242430;
            border-radius: 10px;
        }
        QFrame#convRow:hover {
            border-color: #2e2e3c;
        }
        QLabel#convName {
            color: #f0f0fa;
            font-size: 13px;
            font-weight: 600;
        }
        QLabel#convStatus {
            color: #858596;
            font-size: 11px;
        }
        QLabel#convNameDone {
            color: #5f5f72;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton#convBtn {
            padding: 2px 10px;
            min-height: 24px;
            font-size: 11px;
            background: transparent;
            border: 1px solid #2e2e3c;
            border-radius: 6px;
            color: #c8c8d8;
        }
        QPushButton#convBtn:hover {
            border-color: #3a8dff;
            color: #ffffff;
            background: rgba(58, 141, 255, 0.12);
        }
        QPushButton#convBtn:disabled {
            color: #55556a;
            border-color: #242430;
        }
        QPushButton#convRemove {
            padding: 0;
            min-height: 0;
            background: transparent;
            border: none;
            border-radius: 13px;
            color: #6c6c7c;
            font-size: 16px;
        }
        QPushButton#convRemove:hover {
            color: #ff453a;
            background: rgba(255, 69, 58, 0.12);
        }
        QProgressBar#convProgress {
            background: #12121a;
            border: none;
            border-radius: 2px;
        }
        QProgressBar#convProgress::chunk {
            background: #3a8dff;
            border-radius: 2px;
        }
        QFrame#convOut {
            background: #181822;
            border: 1px solid #242430;
            border-radius: 9px;
        }
        QPushButton#convPrimary {
            background: #3a8dff;
            border: 1px solid #3a8dff;
            color: #ffffff;
            font-weight: 600;
        }
        QPushButton#convPrimary:hover {
            background: #4d9bff;
            border-color: #4d9bff;
            color: #ffffff;
        }

        /* ===== GroupBox（设置页用）===== */
        QGroupBox {
            font-weight: 600;
            border: 1px solid #242430;
            border-radius: 10px;
            margin-top: 14px;
            padding: 14px 12px 12px;
            background: #181822;
            color: #e0e0ee;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 8px;
            color: #ffffff;
        }

        /* ===== 按钮 ===== */
        QPushButton {
            padding: 7px 16px;
            min-height: 30px;
            background: #242430;
            color: #d8d8e4;
            border: 1px solid #2e2e3c;
            border-radius: 6px;
            font-size: 12px;
        }
        QPushButton:hover {
            background: #2e2e3c;
            border-color: #3a8dff;
            color: #ffffff;
        }
        QPushButton:pressed {
            background: #3a8dff;
            color: #ffffff;
        }

        /* 日志页开关：和右侧动作按钮同规格，只靠描边与底色区分开/关。
           未选中态完全继承通用按钮，避免 id 选择器盖掉 hover/pressed 反馈 */
        QPushButton#logToggle:checked {
            background: #2b3a55;
            border-color: #3a8dff;
            color: #eaf2ff;
        }
        QPushButton#logToggle:checked:hover {
            background: #334463;
        }
        /* id 选择器压过通用 :pressed，按下态要显式补回来 */
        QPushButton#logToggle:checked:pressed {
            background: #3a8dff;
            color: #ffffff;
        }

        /* ===== 输入框 / 下拉框 ===== */
        QLineEdit, QComboBox {
            min-height: 30px;
            padding: 4px 10px;
            background: #12121a;
            color: #e0e0ee;
            border: 1px solid #2a2a38;
            border-radius: 6px;
            selection-background-color: #3a8dff;
        }
        QLineEdit:focus, QComboBox:focus {
            border-color: #3a8dff;
        }
        QComboBox::drop-down {
            border: none;
            width: 24px;
        }
        QComboBox QAbstractItemView {
            background: #12121a;
            color: #e0e0ee;
            border: 1px solid #2a2a38;
            selection-background-color: rgba(58, 141, 255, 0.28);
            outline: none;
        }

        /* ===== ListWidget（蓝牙列表、待办列表等）===== */
        QListWidget {
            background: #12121a;
            color: #d8d8e4;
            border: 1px solid #242430;
            border-radius: 8px;
            padding: 6px;
            outline: none;
            selection-background-color: rgba(58, 141, 255, 0.22);
            selection-color: #ffffff;
        }
        QListWidget::item {
            padding: 7px 10px;
            border-radius: 4px;
        }
        QListWidget::item:hover:!selected {
            background: rgba(58, 141, 255, 0.06);
        }

        /* ===== CheckBox ===== */
        QCheckBox {
            color: #d8d8e4;
            spacing: 10px;
            font-size: 12px;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #3a3a4a;
            border-radius: 4px;
            background: #12121a;
        }
        QCheckBox::indicator:hover {
            border-color: #3a8dff;
        }
        QCheckBox::indicator:checked {
            background: #3a8dff;
            border-color: #3a8dff;
        }

        /* ===== ScrollArea ===== */
        QScrollArea {
            border: none;
            background: transparent;
        }
        QScrollBar:vertical {
            background: transparent;
            width: 8px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #2a2a38;
            border-radius: 4px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: #3a8dff;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }

        /* ===== 日志控制台 ===== */
        QPlainTextEdit#logView {
            background: #0d0d12;
            color: #c8e6c9;
            border: 1px solid #242430;
            border-radius: 10px;
            padding: 6px 8px;
            selection-background-color: #3a8dff;
            selection-color: #ffffff;
        }
        QPlainTextEdit#logView QScrollBar:vertical {
            background: transparent;
            width: 6px;
            margin: 6px 3px 6px 0;
        }
        QPlainTextEdit#logView QScrollBar::handle:vertical {
            background: rgba(200, 230, 201, 44);
            border-radius: 3px;
            min-height: 32px;
        }
        QPlainTextEdit#logView QScrollBar::handle:vertical:hover {
            background: #3a8dff;
        }
        QPlainTextEdit#logView QScrollBar::add-line:vertical,
        QPlainTextEdit#logView QScrollBar::sub-line:vertical {
            height: 0;
        }
        QPlainTextEdit#logView QScrollBar::add-page:vertical,
        QPlainTextEdit#logView QScrollBar::sub-page:vertical {
            background: transparent;
        }

        /* ===== QMessageBox ===== */
        QMessageBox {
            background: #12121a;
            color: #e0e0ee;
        }
        QMessageBox QLabel {
            color: #e0e0ee;
        }
    """


_DARK_GLASS_QSS = """
        /* lsletui-glass */
        /* ===== 液态玻璃覆盖层（深色）=====
           窗口已开 WA_TranslucentBackground，下方是 liquid_glass.dll 的折射层。
           这里只把「面」的颜色改成半透明叠加，文字色保持原样以保证可读性。 */
        QMainWindow {
            background: transparent;
        }
        QWidget#pageRoot {
            /* 页面层透明，遮罩只由根容器统一施加一次 */
            background: transparent;
        }
        QWidget#winRoot {
            /* 深色遮罩：压住亮色壁纸，保证白字与次要文字可读。
               实机在浅色网页/文档上背景文字会透上来，遮罩取 172（约 67%），
               仍留约 1/3 的折射层可见度。 */
            background: rgba(10, 10, 15, 172);
            /* 一圈细高光边，界定玻璃与桌面的边界；圆角必须与玻璃面板一致，
               否则窗口的直角会盖住玻璃圆角，露出「方形暗角」 */
            border: 1px solid rgba(255, 255, 255, 42);
            border-radius: 20px;
        }

        /* 次要文字在玻璃上需要更高对比度 */
        QLabel#hint, QLabel#convStatus, QLabel#pageSubtitle {
            color: #b0b0c0;
        }
        QLabel#convNameDone {
            color: #8b8ba2;
        }

        /* 左侧导航：玻璃薄片 + 右侧高光分界线 */
        QListWidget#navList {
            background: rgba(22, 22, 32, 176);
            border-right: 1px solid rgba(255, 255, 255, 22);
            /* 导航条贴着窗口左下角，需要单独收圆角，避免方形底色顶破窗口圆角 */
            border-bottom-left-radius: 20px;
        }
        QListWidget#navList::item:selected {
            background: rgba(58, 141, 255, 72);
            border-left: 3px solid #5aa2ff;
        }

        /* 卡片：半透明面 + 细高光边框（折射层负责边缘的玻璃反光） */
        QFrame#card, QFrame#convRow, QFrame#convOut {
            background: rgba(28, 28, 40, 180);
            border: 1px solid rgba(255, 255, 255, 30);
        }
        QFrame#convRow:hover {
            border-color: rgba(255, 255, 255, 46);
        }
        QGroupBox {
            background: rgba(28, 28, 40, 180);
            border: 1px solid rgba(255, 255, 255, 30);
        }

        /* 输入框 / 下拉框：比卡片更深的玻璃凹槽 */
        QLineEdit, QComboBox {
            background: rgba(12, 12, 18, 172);
            border: 1px solid rgba(255, 255, 255, 34);
        }
        QLineEdit:focus, QComboBox:focus {
            border-color: #5aa2ff;
            background: rgba(12, 12, 18, 200);
        }
        QComboBox QAbstractItemView {
            /* 弹出列表不在玻璃层里，保持近不透明避免和桌面混色 */
            background: rgba(20, 20, 28, 246);
            border: 1px solid rgba(255, 255, 255, 36);
        }

        /* 列表 / 拖放区 */
        QListWidget {
            background: rgba(12, 12, 18, 150);
            border: 1px solid rgba(255, 255, 255, 26);
        }
        QLabel#dropZone {
            background: rgba(12, 12, 18, 150);
            border: 1px dashed rgba(255, 255, 255, 46);
        }

        /* 按钮：玻璃薄片 */
        QPushButton {
            background: rgba(255, 255, 255, 22);
            border: 1px solid rgba(255, 255, 255, 34);
        }
        QPushButton:hover {
            background: rgba(255, 255, 255, 38);
            border-color: #5aa2ff;
        }
        QPushButton:pressed {
            background: rgba(58, 141, 255, 140);
        }
        QPushButton#convBtn {
            background: rgba(255, 255, 255, 14);
            border: 1px solid rgba(255, 255, 255, 30);
        }
        QPushButton#convBtn:hover {
            background: rgba(58, 141, 255, 56);
        }
        QPushButton#convPrimary {
            background: rgba(58, 141, 255, 210);
            border: 1px solid rgba(120, 180, 255, 230);
        }
        /* 日志页开关的选中态：玻璃上是一层更实的蓝色薄片 */
        QPushButton#logToggle:checked {
            background: rgba(58, 141, 255, 96);
            border-color: #5aa2ff;
            color: #ffffff;
        }
        QPushButton#logToggle:checked:hover {
            background: rgba(58, 141, 255, 128);
        }
        QPushButton#logToggle:checked:pressed {
            background: rgba(58, 141, 255, 170);
        }

        /* 进度条 / 复选框 / 滚动条 */
        QProgressBar#convProgress {
            background: rgba(255, 255, 255, 26);
        }
        QCheckBox::indicator {
            background: rgba(12, 12, 18, 150);
            border: 1px solid rgba(255, 255, 255, 56);
        }
        QScrollBar::handle:vertical {
            background: rgba(255, 255, 255, 46);
        }

        /* 滚动区域视口透明，避免又把玻璃层盖住 */
        QScrollArea, QScrollArea > QWidget > QWidget {
            background: transparent;
        }

        /* 日志区：Qt 会把带 Alpha 的子控件直接合成到玻璃层上，不会与
           winRoot 遮罩叠加，所以底色要和遮罩同档深度才读得清；比遮罩略深
           一点（186 vs 172）表示「凹槽」，1px 高光细线 + 12px 圆角收边 */
        QPlainTextEdit#logView {
            background: rgba(10, 10, 16, 186);
            border: 1px solid rgba(255, 255, 255, 40);
            border-radius: 12px;
        }
        QPlainTextEdit#logView QScrollBar::handle:vertical {
            background: rgba(255, 255, 255, 56);
        }
        QPlainTextEdit#logView QScrollBar::handle:vertical:hover {
            background: #5aa2ff;
        }
    """


_LIGHT_QSS = """
        /* ===== 基础容器 ===== */
        QMainWindow, QDialog, QWidget#winRoot, QWidget#pageRoot {
            background: #f5f6f8;
            color: #2b2b33;
        }
        QWidget#bodyRoot {
            background: transparent;
        }
        /* 显式给正文文字色：切换主题时子 QLabel 的调色板不会自动跟随父级 */
        QLabel {
            color: #2b2b33;
        }

        /* ===== 自绘标题栏（无边框窗口） ===== */
        QWidget#titleBar {
            background: transparent;
        }
        QLabel#titleBarText {
            color: #4a4a55;
            font-size: 12px;
        }
        QPushButton#winBtn {
            background: transparent;
            border: none;
            border-radius: 6px;
            color: #3a3a45;
            font-size: 13px;
        }
        QPushButton#winBtn:hover {
            background: rgba(0, 0, 0, 22);
            color: #111318;
        }
        QPushButton#winBtn:pressed {
            background: rgba(0, 0, 0, 38);
        }
        QPushButton#winCloseBtn {
            background: transparent;
            border: none;
            border-radius: 6px;
            color: #3a3a45;
            font-size: 13px;
        }
        QPushButton#winCloseBtn:hover {
            background: #c42b1c;
            color: #ffffff;
        }
        QPushButton#winCloseBtn:pressed {
            background: #a02316;
            color: #ffffff;
        }

        /* ===== 左侧导航栏 ===== */
        QListWidget#navList {
            background: #eceef2;
            border: none;
            outline: none;
            padding: 12px 8px;
            border-right: 1px solid #d8dae0;
        }
        QListWidget#navList::item {
            padding: 11px 16px;
            border-radius: 8px;
            margin: 3px 4px;
            color: #5a5a66;
            font-size: 13px;
        }
        QListWidget#navList::item:hover:!selected {
            background: rgba(58, 141, 255, 0.10);
            color: #1a1a22;
        }
        QListWidget#navList::item:selected {
            background: rgba(58, 141, 255, 0.20);
            color: #0a0a0f;
            border-left: 3px solid #3a8dff;
            padding-left: 13px;
        }

        /* ===== 卡片 ===== */
        QFrame#card {
            background: #ffffff;
            border: 1px solid #e2e4ea;
            border-radius: 10px;
        }

        /* ===== 页面标题 ===== */
        QLabel#pageTitle {
            font-size: 22px;
            font-weight: 700;
            color: #0a0a0f;
            padding-bottom: 4px;
        }
        QLabel#hint {
            color: #9a9aa6;
            font-size: 12px;
        }

        /* ===== 拖放区（待办页复用） ===== */
        QLabel#dropZone {
            background: #fbfbfd;
            color: #9a9aa6;
            border: 1px dashed #d0d2da;
            border-radius: 12px;
            font-size: 13px;
        }
        QLabel#dropZone:hover {
            border-color: #3a8dff;
            background: rgba(58, 141, 255, 0.08);
            color: #3a8dff;
        }

        /* ===== 条目行（待办页复用） ===== */
        QFrame#convRow {
            background: #ffffff;
            border: 1px solid #e2e4ea;
            border-radius: 10px;
        }
        QFrame#convRow:hover {
            border-color: #d0d2da;
        }
        QLabel#convName {
            color: #14141c;
            font-size: 13px;
            font-weight: 600;
        }
        QLabel#convStatus {
            color: #8a8a96;
            font-size: 11px;
        }
        QLabel#convNameDone {
            color: #a2a2ae;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton#convBtn {
            padding: 2px 10px;
            min-height: 24px;
            font-size: 11px;
            background: transparent;
            border: 1px solid #e2e4ea;
            border-radius: 6px;
            color: #55555f;
        }
        QPushButton#convBtn:hover {
            border-color: #3a8dff;
            color: #0a0a0f;
            background: rgba(58, 141, 255, 0.08);
        }
        QPushButton#convBtn:disabled {
            color: #b8b8c2;
            border-color: #eff0f4;
        }
        QPushButton#convRemove {
            padding: 0;
            min-height: 0;
            background: transparent;
            border: none;
            border-radius: 13px;
            color: #a0a0ac;
            font-size: 16px;
        }
        QPushButton#convRemove:hover {
            color: #e0342a;
            background: rgba(224, 52, 42, 0.10);
        }
        QProgressBar#convProgress {
            background: #eceef2;
            border: none;
            border-radius: 2px;
        }
        QProgressBar#convProgress::chunk {
            background: #3a8dff;
            border-radius: 2px;
        }
        QFrame#convOut {
            background: #ffffff;
            border: 1px solid #e2e4ea;
            border-radius: 9px;
        }
        QPushButton#convPrimary {
            background: #3a8dff;
            border: 1px solid #3a8dff;
            color: #ffffff;
            font-weight: 600;
        }
        QPushButton#convPrimary:hover {
            background: #4d9bff;
            border-color: #4d9bff;
            color: #ffffff;
        }

        /* ===== GroupBox ===== */
        QGroupBox {
            font-weight: 600;
            border: 1px solid #e2e4ea;
            border-radius: 10px;
            margin-top: 14px;
            padding: 14px 12px 12px;
            background: #ffffff;
            color: #1a1a22;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 8px;
            color: #0a0a0f;
        }

        /* ===== 按钮 ===== */
        QPushButton {
            padding: 7px 16px;
            min-height: 30px;
            background: #eceef2;
            color: #2b2b33;
            border: 1px solid #d0d2da;
            border-radius: 6px;
            font-size: 12px;
        }
        QPushButton:hover {
            background: #dfe2e8;
            border-color: #3a8dff;
            color: #0a0a0f;
        }
        QPushButton:pressed {
            background: #3a8dff;
            color: #ffffff;
        }

        /* 日志页开关：未选中态继承通用按钮，选中态换成蓝色描边 */
        QPushButton#logToggle:checked {
            background: #dce8fb;
            border-color: #3a8dff;
            color: #123a6d;
        }
        QPushButton#logToggle:checked:hover {
            background: #c9dcf8;
        }
        QPushButton#logToggle:checked:pressed {
            background: #3a8dff;
            color: #ffffff;
        }

        /* ===== 输入框 / 下拉框 ===== */
        QLineEdit, QComboBox {
            min-height: 30px;
            padding: 4px 10px;
            background: #ffffff;
            color: #1a1a22;
            border: 1px solid #d0d2da;
            border-radius: 6px;
            selection-background-color: #3a8dff;
        }
        QLineEdit:focus, QComboBox:focus {
            border-color: #3a8dff;
        }
        QComboBox::drop-down {
            border: none;
            width: 24px;
        }
        QComboBox QAbstractItemView {
            background: #ffffff;
            color: #1a1a22;
            border: 1px solid #d0d2da;
            selection-background-color: rgba(58, 141, 255, 0.28);
            outline: none;
        }

        /* ===== ListWidget ===== */
        QListWidget {
            background: #ffffff;
            color: #2b2b33;
            border: 1px solid #e2e4ea;
            border-radius: 8px;
            padding: 6px;
            outline: none;
            selection-background-color: rgba(58, 141, 255, 0.22);
            selection-color: #0a0a0f;
        }
        QListWidget::item {
            padding: 7px 10px;
            border-radius: 4px;
        }
        QListWidget::item:hover:!selected {
            background: rgba(58, 141, 255, 0.08);
        }

        /* ===== CheckBox ===== */
        QCheckBox {
            color: #2b2b33;
            spacing: 10px;
            font-size: 12px;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #c0c2ca;
            border-radius: 4px;
            background: #ffffff;
        }
        QCheckBox::indicator:hover {
            border-color: #3a8dff;
        }
        QCheckBox::indicator:checked {
            background: #3a8dff;
            border-color: #3a8dff;
        }

        /* ===== ScrollArea ===== */
        QScrollArea {
            border: none;
            background: transparent;
        }
        QScrollBar:vertical {
            background: transparent;
            width: 8px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #c8cad2;
            border-radius: 4px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: #3a8dff;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }

        /* ===== 日志控制台 ===== */
        QPlainTextEdit#logView {
            background: #ffffff;
            color: #1a7a3a;
            border: 1px solid #e2e4ea;
            border-radius: 10px;
            padding: 6px 8px;
            selection-background-color: #3a8dff;
            selection-color: #ffffff;
        }
        QPlainTextEdit#logView QScrollBar:vertical {
            background: transparent;
            width: 6px;
            margin: 6px 3px 6px 0;
        }
        QPlainTextEdit#logView QScrollBar::handle:vertical {
            background: rgba(26, 122, 58, 46);
            border-radius: 3px;
            min-height: 32px;
        }
        QPlainTextEdit#logView QScrollBar::handle:vertical:hover {
            background: #3a8dff;
        }
        QPlainTextEdit#logView QScrollBar::add-line:vertical,
        QPlainTextEdit#logView QScrollBar::sub-line:vertical {
            height: 0;
        }
        QPlainTextEdit#logView QScrollBar::add-page:vertical,
        QPlainTextEdit#logView QScrollBar::sub-page:vertical {
            background: transparent;
        }

        /* ===== QMessageBox ===== */
        QMessageBox {
            background: #ffffff;
            color: #1a1a22;
        }
        QMessageBox QLabel {
            color: #1a1a22;
        }
    """


_LIGHT_GLASS_QSS = """
        /* lsletui-glass */
        /* ===== 液态玻璃覆盖层（浅色）=====
           浅色主题下用「白色半透明玻璃 + 深色文字」，避免亮色壁纸导致对比度丢失。 */
        QMainWindow {
            background: transparent;
        }
        QWidget#pageRoot {
            background: transparent;
        }
        QWidget#winRoot {
            /* 淡白色遮罩：浅色玻璃在深色壁纸上也要保证深色文字可读 */
            background: rgba(250, 251, 253, 205);
            border: 1px solid rgba(255, 255, 255, 220);
            /* 与玻璃面板圆角对齐，避免方形窗口角压住玻璃的圆角 */
            border-radius: 20px;
        }
        QLabel#hint, QLabel#convStatus, QLabel#pageSubtitle {
            color: #575763;
        }
        QLabel#convNameDone {
            color: #7c7c8a;
        }

        QListWidget#navList {
            background: rgba(255, 255, 255, 200);
            border-right: 1px solid rgba(0, 0, 0, 20);
            border-bottom-left-radius: 20px;
        }
        QListWidget#navList::item:selected {
            background: rgba(58, 141, 255, 56);
            border-left: 3px solid #2f7ae5;
        }

        QFrame#card, QFrame#convRow, QFrame#convOut {
            background: rgba(255, 255, 255, 205);
            border: 1px solid rgba(255, 255, 255, 200);
        }
        QFrame#convRow:hover {
            border-color: rgba(0, 0, 0, 36);
        }
        QGroupBox {
            background: rgba(255, 255, 255, 205);
            border: 1px solid rgba(255, 255, 255, 200);
        }

        QLineEdit, QComboBox {
            background: rgba(255, 255, 255, 215);
            border: 1px solid rgba(0, 0, 0, 32);
        }
        QLineEdit:focus, QComboBox:focus {
            border-color: #2f7ae5;
            background: rgba(255, 255, 255, 235);
        }
        QComboBox QAbstractItemView {
            background: rgba(255, 255, 255, 248);
            border: 1px solid rgba(0, 0, 0, 36);
        }

        QListWidget {
            background: rgba(255, 255, 255, 190);
            border: 1px solid rgba(255, 255, 255, 190);
        }
        QLabel#dropZone {
            background: rgba(255, 255, 255, 190);
            border: 1px dashed rgba(0, 0, 0, 48);
        }

        QPushButton {
            background: rgba(255, 255, 255, 130);
            border: 1px solid rgba(0, 0, 0, 34);
        }
        QPushButton:hover {
            background: rgba(255, 255, 255, 190);
            border-color: #2f7ae5;
        }
        QPushButton:pressed {
            background: rgba(58, 141, 255, 184);
            color: #ffffff;
        }
        QPushButton#convBtn {
            background: rgba(255, 255, 255, 110);
            border: 1px solid rgba(0, 0, 0, 30);
        }
        QPushButton#convBtn:hover {
            background: rgba(58, 141, 255, 41);
        }
        QPushButton#convPrimary {
            background: rgba(58, 141, 255, 224);
            border: 1px solid rgba(58, 141, 255, 242);
        }
        /* 日志页开关的选中态：白瓷玻璃上压一层浅蓝 */
        QPushButton#logToggle:checked {
            background: rgba(58, 141, 255, 90);
            border-color: #2f7ae5;
            color: #0d2c56;
        }
        QPushButton#logToggle:checked:hover {
            background: rgba(58, 141, 255, 120);
        }
        QPushButton#logToggle:checked:pressed {
            background: rgba(58, 141, 255, 184);
            color: #ffffff;
        }

        QProgressBar#convProgress {
            background: rgba(0, 0, 0, 26);
        }
        QCheckBox::indicator {
            background: rgba(255, 255, 255, 215);
            border: 1px solid rgba(0, 0, 0, 60);
        }
        QScrollBar::handle:vertical {
            background: rgba(0, 0, 0, 60);
        }

        /* 日志区：底色与 winRoot 遮罩同档（205）再略深，读成一层白瓷凹槽；
           边框用近黑细线，亮底上比白线更能勾出边界 */
        QPlainTextEdit#logView {
            background: rgba(255, 255, 255, 215);
            border: 1px solid rgba(0, 0, 0, 30);
            border-radius: 12px;
        }
        QPlainTextEdit#logView QScrollBar::handle:vertical {
            background: rgba(60, 60, 80, 70);
        }
        QPlainTextEdit#logView QScrollBar::handle:vertical:hover {
            background: #2f7ae5;
        }

        QScrollArea, QScrollArea > QWidget > QWidget {
            background: transparent;
        }
    """


def set_app_windows_font():
    app = QApplication.instance()
    if app is None:
        return
    app.setFont(QFont("Segoe UI", 9))
