# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

block_cipher = None

# 收集 paddleocr / paddle / ppocr / tools 等所有模块
datas = []
binaries = []
hiddenimports = []

# PaddleOCR 相关包
for pkg in ['paddleocr', 'paddle', 'ppocr', 'tools', 'ppstructure', 'paddlex']:
    try:
        d, b, h = collect_all(pkg)
        datas.extend(d)
        binaries.extend(b)
        hiddenimports.extend(h)
    except Exception:
        pass

# 常见缺失模块
hiddenimports += ['pyclipper', 'cv2', 'skimage', 'imgaug', 'tqdm', 'yaml', 'json', 'shapely', 'attrdict']

# PaddleOCR 模型目录（打包整个 .paddlex）
import os
paddlex_path = os.path.join(os.environ['USERPROFILE'], '.paddlex')
if os.path.exists(paddlex_path):
    datas.append((paddlex_path, './.paddlex'))

# 图标
datas.append(('1.ico', '.'))

a = Analysis(
    ['ScreenAlarm.py'],
    pathex=[],
    binaries=binaries,
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
    [],
    exclude_binaries=True,
    name='数字报警',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='1.ico'
)