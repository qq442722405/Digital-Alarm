# -*- mode: python ; coding: utf-8 -*-


from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules
)



datas = []

binaries = []

hiddenimports = []



# ======================
# 收集模块
# ======================


packages = [

    "easyocr",

    "cv2",

    "PIL",

    "jaraco",

    "platformdirs",

]



for pkg in packages:

    try:

        d,b,h = collect_all(pkg)

        datas += d

        binaries += b

        hiddenimports += h


    except Exception:

        pass




# ======================
# EasyOCR
# ======================

hiddenimports += collect_submodules(
    "easyocr"
)



# ======================
# 强制导入
# ======================

hiddenimports += [


    # setuptools

    "pkg_resources",


    "jaraco",

    "jaraco.text",

    "jaraco.functools",

    "jaraco.context",


    "platformdirs",



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



    # Torch

    "torch",

    "torchvision",


    "numpy",

    "yaml",

]





# ======================
# ICO
# ======================

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

        "pytest",


        "matplotlib.tests"

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