# -*- mode: python ; coding: utf-8 -*-


from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
    collect_dynamic_libs
)



datas = []

binaries = []

hiddenimports = []



# =========================
# EasyOCR
# =========================

for pkg in [

    "easyocr",

    "cv2",

    "PIL",

]:

    try:

        d,b,h = collect_all(pkg)

        datas += d

        binaries += b

        hiddenimports += h


    except Exception:

        pass



# =========================
# 动态DLL
# =========================


for pkg in [

    "torch",

    "torchvision",

    "cv2",

    "numpy"

]:


    try:

        binaries += collect_dynamic_libs(pkg)


    except Exception:

        pass





# =========================
# EasyOCR模块
# =========================


hiddenimports += collect_submodules(
    "easyocr"
)



hiddenimports += [

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



# =========================
# 图标
# =========================


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