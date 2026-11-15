# -*- mode: python ; coding: utf-8 -*-
"""
LsletUI 免费版（Free Edition）PyInstaller 打包配置
onedir 模式，禁用 UPX，带版本信息
输出目录: ../exe/LsletUIFree/

本 spec 只打包免费版代码：Mora AI、跨设备互传、游戏帧率、Steam 云存档、
下载监控、通话提醒、验证码提取、格式转换、Vue 侧边栏（QtWebEngine）等
模块已从源码树物理删除，这里也不携带它们的资源与依赖。
"""

import os
import sys

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# 基础路径：spec 文件所在目录 (backend/)
BASE_DIR = os.path.dirname(os.path.abspath(SPEC))

# 资源路径配置
datas = [
    # 图标资源
    (os.path.join(BASE_DIR, 'img'), 'img'),
    # 配置文件
    (os.path.join(BASE_DIR, 'island_config.json'), '.'),
    # 液态玻璃原生层（与 capsule_app 同级，运行时 ctypes 加载）
    (os.path.join(BASE_DIR, 'capsule_app', 'liquid_glass.dll'), 'capsule_app'),
]

# 原生 DLL (非 Python 扩展，需作为独立文件携带)
binaries = []

# 隐式导入配置
hiddenimports = [
    # PySide6 相关（免费版无 WebEngine/Quick/Qml）
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',

    # 系统相关
    'win32api',
    'win32gui',
    'win32con',
    'win32event',
    'win32process',
    'win32com.client',
    'win32com',
    'pythoncom',
    'pywintypes',

    # psutil
    'psutil',
    'psutil._pswindows',

    # 系统通知（win11toast 内部通过 winrt/comtypes 创建 COM 对象）
    'win11toast',
    'win10toast',
    'winrt',
    'winrt.runtime',
    'winrt.windows.ui.notifications',
    'winrt.windows.ui.notifications.management',
    'winrt.windows.foundation',
    'winrt.windows.foundation.collections',
    'winrt.windows.applicationmodel',
    'comtypes',
    'comtypes.stream',

    # 项目模块
    'capsule_app',
    'capsule_app.main',
    'capsule_app.capsule_window',
    'capsule_app.settings_backend',
    'capsule_app.settings_page',
    'capsule_app.native_main_window',
    'capsule_app.native_ui',
    'capsule_app.bluetooth_backend',
    'capsule_app.hardware_monitor_backend',
    'capsule_app.calendar_backend',
    'capsule_app.todo_backend',
    'capsule_app.clipboard_backend',
    'capsule_app.clipboard_panel_window',
    'capsule_app.smtc_monitor_backend',
    'capsule_app.console_widget',
    'capsule_app.debug_log',
    'capsule_app.log_bus',
    'capsule_app.hw_precheck',
    'capsule_app.liquid_glass',
    'resource_path',

    # NVIDIA 显卡指标（NVML，动态导入，静态分析看不到）
    'pynvml',

    # 标准库
    'json',
    'threading',
    'subprocess',
    'ctypes',
    'ctypes.wintypes',
    'webbrowser',
    'shutil',
    'tempfile',
    'uuid',
    'hashlib',
    'base64',
    'urllib.parse',
]

# 自动收集整个项目包（免费版包内只剩免费模块）：
# capsule_app 下部分模块只在运行时按需导入（如 todo_backend），手写列表容易漏；
# collect_submodules 会把子模块全部打进 PYZ。
hiddenimports += collect_submodules('capsule_app')

a = Analysis(
    ['main.py'],
    pathex=[BASE_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 免费版不需要的第三方与 Qt 模块（排除后 Chromium 不会进包）
        'tkinter',
        '_tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'cv2',
        'PIL',
        'requests',
        'segno',
        'pycaw',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineQuick',
        'PySide6.QtQuick',
        'PySide6.QtQml',
        'PySide6.QtWebChannel',
        'PySide6.QtPositioning',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LsletUIFree',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 禁用UPX压缩
    console=False,  # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(BASE_DIR, 'img', 'default_icon.ico'),
    version=os.path.join(BASE_DIR, 'version.txt'),  # 版本信息（绝对路径，避免依赖 cwd）
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,  # 禁用UPX压缩
    upx_exclude=[],
    name='LsletUIFree',
)
