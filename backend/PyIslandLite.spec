# -*- mode: python ; coding: utf-8 -*-
"""
PyIslandLite 后台服务 PyInstaller 打包配置
onedir 模式，禁用 UPX，带版本信息
输出目录: ../exe/PyIslandLite/
"""

import os
import sys

block_cipher = None

# 基础路径：spec 文件所在目录 (backend/)
BASE_DIR = os.path.dirname(os.path.abspath(SPEC))

# 资源路径配置（后台服务只需要配置文件）
datas = [
    # 配置文件
    (os.path.join(BASE_DIR, 'island_config.json'), '.'),
]

# 隐式导入配置（后台服务使用tkinter，不需要PySide6）
hiddenimports = [
    # tkinter
    'tkinter',
    '_tkinter',
    'tkinter.constants',
    
    # 系统相关
    'win32api',
    'win32gui',
    'win32con',
    'win32event',
    'pythoncom',
    'pywintypes',
    
    # psutil
    'psutil',
    'psutil._pswindows',
    
    # 项目模块
    'resource_path',
    
    # 其他依赖
    'json',
    'threading',
    'ctypes',
    'ctypes.wintypes',
]

a = Analysis(
    ['island_service.py'],
    pathex=[BASE_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的模块，减小体积
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
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
    name='PyIslandLite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 禁用UPX压缩
    console=False,  # 无控制台窗口（后台服务）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(BASE_DIR, 'img', 'default_icon.ico'),
    version='version_service.txt',  # 版本信息
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,  # 禁用UPX压缩
    upx_exclude=[],
    name='PyIslandLite',
)