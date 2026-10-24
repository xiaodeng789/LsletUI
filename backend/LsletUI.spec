# -*- mode: python ; coding: utf-8 -*-
"""
LsletUI 主应用 PyInstaller 打包配置
onedir 模式，禁用 UPX，带版本信息
输出目录: ../exe/LsletUI/
"""

import os
import sys

block_cipher = None

# 基础路径：spec 文件所在目录 (backend/)
BASE_DIR = os.path.dirname(os.path.abspath(SPEC))
# 项目根目录 (pyisland-lite/)
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# 资源路径配置
datas = [
    # 前端资源 (frontend/dist 在项目根目录下)
    (os.path.join(PROJECT_ROOT, 'frontend', 'dist'), 'frontend/dist'),
    # 图标资源
    (os.path.join(BASE_DIR, 'img'), 'img'),
    # 配置文件
    (os.path.join(BASE_DIR, 'island_config.json'), '.'),
    # widget.html
    (os.path.join(BASE_DIR, 'widget.html'), '.'),
]

# 隐式导入配置
hiddenimports = [
    # PySide6 相关
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineQuick',
    'PySide6.QtNetwork',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
    'PySide6.QtOpenGL',
    'PySide6.QtWebChannel',
    'PySide6.QtPositioning',
    'PySide6.QtPrintSupport',
    
    # 系统相关
    'win32api',
    'win32gui',
    'win32con',
    'win32event',
    'win32process',
    'win32com.client',
    'pythoncom',
    'pywintypes',
    
    # psutil
    'psutil',
    'psutil._pswindows',
    
    # 项目模块
    'capsule_app',
    'capsule_app.main',
    'capsule_app.capsule_window',
    'capsule_app.side_panel_window',
    'capsule_app.settings_window',
    'capsule_app.settings_backend',
    'capsule_app.process_monitor_backend',
    'capsule_app.bluetooth_backend',
    'capsule_app.hardware_monitor_backend',
    'capsule_app.download_monitor_backend',
    'capsule_app.smtc_monitor_backend',
    'resource_path',
    
    # 其他依赖
    'requests',
    'json',
    'threading',
    'subprocess',
    'ctypes',
    'ctypes.wintypes',
]

a = Analysis(
    ['main.py'],
    pathex=[BASE_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的模块，减小体积
        'tkinter',
        '_tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
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
    name='LsletUI',
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
    version='version.txt',  # 版本信息
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,  # 禁用UPX压缩
    upx_exclude=[],
    name='LsletUI',
)