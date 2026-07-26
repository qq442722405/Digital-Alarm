# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

# 1. 打包非 Python 资源文件 (图标等)
datas = [('1.ico', '.')]
binaries = []

# 2. 补全 PaddleOCR 及 C 扩展底层隐式导入模块
hiddenimports = [
    'tools',
    'tools.infer',
    'paddleocr',
    'ppocr',
    'ppocr.utils',
    'ppocr.data',
    'ppocr.postprocess',
    'ppocr.modeling',
    'ppocr.optimizer',
    'ppocr.metrics',
    'pyclipper',
    'shapely',
    'shapely.geometry',
    'imgaug',
    'lmdb',
    'scipy',
    'scipy.ndimage',
]

# 3. 自动扫描并搜集 PaddleOCR 所有 C/C++ 动态链接库与数据资源
packages_to_collect = [
    'paddleocr', 
    'paddle', 
    'ppocr', 
    'pyclipper', 
    'shapely', 
    'imgaug', 
    'lmdb'
]

for pkg in packages_to_collect:
    try:
        tmp_datas, tmp_binaries, tmp_hidden = collect_all(pkg)
        datas.extend(tmp_datas)
        binaries.extend(tmp_binaries)
        hiddenimports.extend(tmp_hidden)
    except Exception:
        pass

block_cipher = None

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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ScreenMonitorAlarm',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # 不显示黑框控制台窗口 (--noconsole)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['1.ico'],        # 可执行程序图标
)