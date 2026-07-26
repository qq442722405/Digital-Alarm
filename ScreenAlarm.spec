# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules
)


block_cipher = None


datas = []
binaries = []
hiddenimports = []


# ===============================
# 自动收集依赖
# ===============================

packages = [

    "easyocr",

    "torch",

    "torchvision",

    "cv2",

    "PIL",

    "jaraco",

]


for pkg in packages:

    try:

        d, b, h = collect_all(pkg)

        datas += d

        binaries += b

        hiddenimports += h


    except Exception:

        pass



# ===============================
# EasyOCR子模块
# ===============================

try:

    hiddenimports += collect_submodules(
        "easyocr"
    )

except:

    pass



# ===============================
# 强制隐藏依赖
# ===============================

hiddenimports += [

    # OCR
    "easyocr",

    "python_bidi",

    "shapely",

    "skimage",

    "scipy",


    # 图片
    "PIL",
    "PIL.Image",
    "PIL.ImageGrab",


    # numpy
    "numpy",


    # PyTorch
    "torch",
    "torchvision",


    # setuptools pkg_resources
    "pkg_resources",

    "jaraco",
    "jaraco.text",
    "jaraco.functools",
    "jaraco.context",

]



# ===============================
# 图标
# ===============================

datas.append(
    ("1.ico",".")
)



a = Analysis(

    [
        "ScreenAlarm.py"
    ],

    pathex=[],

    binaries=binaries,

    datas=datas,

    hiddenimports=hiddenimports,

    hookspath=[],

    hooksconfig={},

    runtime_hooks=[],

    excludes=[

        "pytest",

        "matplotlib.tests",

        "torch.cuda"

    ],

    win_no_prefer_redirects=False,

    win_private_assemblies=False,

    cipher=block_cipher,

    noarchive=False,

)



pyz = PYZ(

    a.pure,

    a.zipped_data,

    cipher=block_cipher

)



exe = EXE(

    pyz,

    a.scripts,

    [],

    exclude_binaries=True,

    name="数字报警",

    debug=False,

    strip=False,

    upx=True,

    console=False,

    icon="1.ico"

)



coll = COLLECT(

    exe,

    a.binaries,

    a.datas,

    strip=False,

    upx=True,

    name="数字报警"

)