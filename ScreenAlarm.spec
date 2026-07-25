# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# 1. 自动收集 paddle 和 paddleocr 的数据文件与模型资产
datas = [
    ('1.ico', '.'),
]
datas += collect_data_files('paddleocr')
datas += collect_data_files('paddle')

# 2. 收集隐式导入与子模块 (彻底解决 No module named ppocr / tools)
hiddenimports = [
    'paddle',
    'paddleocr',
    'pyclipper',
    'imgaug',
    'shapely',
    'skimage',
    'ppocr',
    'ppocr.utils',
    'ppocr.data',
    'ppocr.postprocess',
    'tools',
    'tools.infer',
    'winsound',
    'ctypes',
]
hiddenimports += collect_submodules('paddleocr')
hiddenimports += collect_submodules('ppocr')

a = Analysis(
    ['ScreenAlarm.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ScreenAlarm',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 无控制台窗口
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='1.ico',
)