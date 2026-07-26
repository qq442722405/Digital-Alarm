# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules


datas = []
binaries = []
hiddenimports = []


# EasyOCR

for pkg in [

    "easyocr",
    "cv2",
    "PIL"

]:

    try:

        d,b,h = collect_all(pkg)

        datas += d
        binaries += b
        hiddenimports += h

    except:

        pass



# EasyOCR内部模块

hiddenimports += collect_submodules("easyocr")



# 必要依赖

hiddenimports += [

    "numpy",

    "scipy",

    "skimage",

    "python_bidi",

    "shapely",

    "yaml",

    "PIL.Image",

    "PIL.ImageGrab",

    "torch",

    "torchvision",

]



# 图标

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

        "torch.cuda",

        "tensorboard",

        "matplotlib.tests",

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

    a.datas,

    [],

    name="数字报警",

    debug=False,

    strip=False,

    upx=True,

    console=False,

    icon="1.ico"

)