# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules
)


datas=[]

binaries=[]

hiddenimports=[]



# =====================
# 收集依赖
# =====================

for pkg in [

    "easyocr",

    "cv2",

    "PIL",

    "jaraco",

]:

    try:

        d,b,h = collect_all(pkg)

        datas += d

        binaries += b

        hiddenimports += h


    except Exception:

        pass



# =====================
# 强制隐藏模块
# =====================

hiddenimports += [

    "pkg_resources",

    "jaraco",

    "jaraco.text",

    "jaraco.functools",

    "jaraco.context",


    "easyocr",

    "torch",

    "torchvision",

    "numpy",

    "scipy",

    "skimage",

    "yaml",

    "python_bidi",

    "shapely",

    "PIL.Image",

    "PIL.ImageGrab",

]



hiddenimports += collect_submodules(
    "easyocr"
)



# 图标

datas.append(
    (
        "1.ico",
        "."
    )
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

        "torch.cuda",

        "tensorboard",

        "pytest"

    ],

    noarchive=False,

)



pyz = PYZ(

    a.pure

)



exe = EXE(

    pyz,

    a.scripts,

    [],

    exclude_binaries=True,

    name="数字报警",

    debug=False,

    strip=False,

    upx=False,

    console=False,

    icon="1.ico"

)



coll = COLLECT(

    exe,

    a.binaries,

    a.datas,

    strip=False,

    upx=False,

    name="数字报警"

)